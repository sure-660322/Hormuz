# SQL-02 语义视图与只读角色

状态：进行中（2026-09-21，分支 `codex/sql02-agent-reader`，基线 `9336543`）。迁移已在一次性 PostgreSQL 16 隔离容器完成首轮权限验证；catalog 实物定义哈希和完整验证脚本尚未完成。本阶段只建设并验证数据库读取边界；`query_analytics` 仍未实现、未注册且默认关闭。

## 当前交付范围

- `backend/sql/013_agent_analytics_readonly.sql`：创建 `agent_data` 三个 catalog v1 视图，以及 `agent_view_owner`、`agent_reader`、`agent_reader_login` 最小权限角色。
- 密码不进入 Git。迁移只创建无密码登录角色，凭据由受保护的 DBA 操作另行配置。
- 首批仅开放 `v_ships`、`v_events`、`v_news`；不开放船位、停留、相遇、源表或写接口。
- `agent_reader_login` 默认事务只读、`search_path=pg_catalog`、连接上限 4；运行时权限来自无登录组角色 `agent_reader`。

## 重要部署影响

PostgreSQL 默认通过 `PUBLIC` 授予数据库 TEMP 权限，部分版本/既有数据库还可能允许 `PUBLIC` 在 public schema 创建对象，无法只对单个角色做负向覆盖。因此迁移会在目标数据库撤销 `PUBLIC` 的 TEMP 和 public schema CREATE。这是数据库级变更，必须先在独立测试数据库验证，并确认其他业务角色不依赖这些默认权限；如确有依赖，应由 DBA 仅向明确角色恢复，不能恢复给 PUBLIC。

## 完成门槛

SQL-02 目前不能标记完成。后续必须在独立测试数据库执行并保存以下证据：

1. 三个视图字段、类型、nullable、owner 与规范化 `pg_get_viewdef` 哈希。
2. `agent_reader_login` 能读取三个视图，不能读取 public 源表。
3. INSERT/UPDATE/DELETE/DDL、CREATE、TEMP、SET ROLE 到 owner、访问其他 schema 均失败。
4. `transaction_read_only=on`，`search_path=pg_catalog`，角色无高权限属性或额外角色成员关系。
5. catalog JSON 与数据库实物一致；任一漂移时验证失败并保持功能关闭。
6. 在未配置认证与限流前，不把 query_analytics 开放到远端环境。

本文件记录当前设计与未验证范围，不代表迁移已在任何共享数据库执行。

## 2026-09-21 隔离验证记录

目标为本轮新建的一次性 `postgres:16` 容器和独立数据库 `aisdb_sql02`，没有连接项目当前数据库。使用 008 中四张源表的字段定义建立最小 fixture，插入 1 艘模拟船、1 条模拟船位、1 个事件和 1 条新闻后执行 013。

已验证：

- 013 首次执行成功，第二次重复执行成功；第二次未重置已单独配置的测试密码。
- `agent_reader_login` 的 `transaction_read_only=on`、`search_path=pg_catalog`。
- 三个视图各返回 1 行；视图 owner 均为 `agent_view_owner`。
- 登录角色只有 `agent_reader` 成员关系，连接上限为 4；三个角色均非 superuser/createdb/createrole/replication/bypassrls。
- 登录角色对三个 agent_data 视图有 SELECT，对 public.ships/events/news 无 SELECT。
- 读取源表、DELETE/UPDATE 视图、CREATE TEMP、在 public 创建表、SET ROLE agent_view_owner 均被拒绝。

未验证：

- 尚未生成并提交 catalog JSON，也未比对规范化 `pg_get_viewdef` SHA-256。
- 尚未在包含全部扩展、真实约束和当前数据量的独立完整副本验证查询结果。
- 尚未建立 SQL-04 专用连接池；模型和 query_analytics 均未接入。
