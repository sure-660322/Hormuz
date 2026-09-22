# SQL-02 语义视图与只读角色

状态：**已完成并通过隔离验证**（2026-09-21，分支 `codex/sql02-agent-reader`，本轮接续基线 `260678b`；SQL-04 于同日补全固定 `search_path=pg_catalog` 的哈希条件并复跑 56 项通过）。本阶段建设数据库读取边界和 catalog v1；后续 SQL-04 执行器和 SQL-05 工具注册均已验证，功能开关仍默认关闭。

## 交付内容

- `backend/sql/013_agent_analytics_readonly.sql`：创建 `agent_data.v_ships`、`agent_data.v_events`、`agent_data.v_news`，以及 `agent_view_owner`、`agent_reader`、`agent_reader_login` 三个最小权限角色。
- `backend/app/query_analytics_catalog_v1.json`：catalog v1，记录字段顺序、PostgreSQL 类型、nullable、语义说明、数据范围、限制、单视图行数上限、时间条件要求、允许 JOIN 和三个视图定义哈希。
- `scripts/verify_agent_analytics_readonly.ps1`：自动创建无主机端口的一次性 PostgreSQL 17，加载 008 中四张源表的实际定义及固定 fixture，重复执行 013，并完成允许/拒绝、角色、catalog 一致性及额外对象漂移验证；结束后自动删除容器。
- `.env.example`：只提供独立只读连接的占位配置，功能开关保持 `AGENT_QUERY_ENABLED=false`；密码不进入 Git，迁移也不设置密码。

`agent_reader_login` 通过唯一成员关系继承 `agent_reader` 的读取权限，默认事务只读，`search_path=pg_catalog`，连接上限 4，`statement_timeout=5s`、`lock_timeout=1s`、`idle_in_transaction_session_timeout=5s`。视图由不可登录的 `agent_view_owner` 持有；读取角色不拥有视图或业务表。

## catalog v1 与哈希绑定

catalog 版本为 `1.0`，目标数据库主版本为 PostgreSQL 17。定义指纹固定为：事务内先设 `search_path=pg_catalog`，再读取 `pg_get_viewdef(regclass, false)` 的原始 UTF-8 字节并计算 SHA-256；不能用迁移编号代替定义指纹。SQL-04 实测发现 `pg_get_viewdef` 输出会受调用者 search_path 影响，因而补全这一规范化条件并在固定 PostgreSQL 17 镜像中重新生成指纹；视图 SQL 本身未改变。

| 视图 | `pg_get_viewdef` SHA-256 |
| --- | --- |
| `agent_data.v_ships` | `d30b58dc52154a1a6bbb5686caaece6bfed6ff4a19a358c429365156b2979f79` |
| `agent_data.v_events` | `a68a9c54168e8d5e6e6a72487045a067c8b236c1fbb5d23125436c0bc241f3cc` |
| `agent_data.v_news` | `5c90da2c942cd37e02f96dbb7f8938bee1436791585325b7fe3b5c5204431488` |

视图定义、字段、类型、nullable、owner 或 PostgreSQL 主版本变化时，必须评审语义变更、递增 catalog 版本、从目标版本数据库重新生成三个哈希并完整复跑验证。禁止只修改 JSON 哈希来绕过漂移。SQL-04 加载 catalog 时仍须执行同一套实物核验，任一不一致即 fail closed。

## 数据库级部署影响

PostgreSQL 的数据库 TEMP 和 `public` schema 权限可通过 `PUBLIC` 继承，单独对读取角色执行 `REVOKE` 不能形成负向覆盖。013 因而会：

- 从 `PUBLIC` 撤销目标数据库 TEMP；
- 从 `PUBLIC` 撤销 `public` schema 的全部权限；
- 只向 `agent_view_owner` 明确授予 `public` schema USAGE 和底表必要字段的 SELECT；
- 只向 `agent_reader` 授予 `agent_data` USAGE 和三个批准视图的 SELECT。
- 每次执行先撤销 `agent_data` 所有现存表和函数对 `PUBLIC`、`agent_reader`、`agent_reader_login` 的权限，再授权三个批准视图；同时关闭视图 owner 新建函数的默认 PUBLIC EXECUTE。

这是目标数据库范围的权限变化。部署到既有数据库前，DBA 必须盘点其他业务角色是否依赖这些默认权限；如确有需要，只向明确角色恢复最小权限，不能恢复给 `PUBLIC`。本轮没有对任何共享或当前项目数据库执行 013。

## 2026-09-21 完整隔离验证

执行命令：

```powershell
.\scripts\verify_agent_analytics_readonly.ps1
```

验证环境为脚本新建的一次性容器和数据库 `hormuz_sql02_verify`，使用官方 `postgres:17` 镜像 digest `sha256:f4c66b820c6f974249089d3d16d86a3698eae11e8746eb6644b2271031e91232`。容器未映射主机端口；测试结构直接截取受版本控制的 008 四张源表定义，跳过与 SQL-02 无关的 PostGIS/MobilityDB 派生部分；fixture 为 1 艘模拟船、1 条模拟船位、1 个事件和 1 条新闻。

结果：`PASS: SQL-02 isolated verification completed (56 checks).`

已验证：

- 013 首次执行和重复执行均成功；
- 三个角色的 LOGIN/INHERIT、连接上限及 superuser、createdb、createrole、replication、bypassrls 属性符合冻结值，登录角色只有 `agent_reader` 一个成员关系；
- 登录角色的只读事务、固定 search_path 和三项超时生效；
- 三个语义视图均可读取固定 fixture，四张 `public` 源表均拒绝读取；
- INSERT、UPDATE、DELETE、TRUNCATE、建表、建 schema、删视图、TEMP 均被拒绝；
- `SET ROLE agent_view_owner` 和切换到管理员角色均被拒绝；
- 登录角色有且仅有 `agent_data` schema USAGE，无 `public` USAGE 和数据库 TEMP；
- catalog 的视图存在性、owner、字段顺序、类型、nullable 和定义哈希均与数据库一致；人为篡改一个哈希时验证器能够检测漂移并失败。
- 注入额外表和函数并授予旧权限后，重复执行 013 会清除读取角色的访问；catalog 验证器同时拒绝额外 relation/function 对象。

## 仍未实现或未验证

- SQL-04 的专用连接池、运行时 catalog 加载审计和只读执行器已在隔离 PostgreSQL 17 验证；后续 SQL-05 已注册工具，SQL-06 已完成真实模型/浏览器综合验收，但开关仍默认关闭。
- 未在当前共享数据库或远端环境部署，也未使用当前业务数据验证统计结果；本轮只证明 SQL-02 固定 fixture 下的结构和权限边界。
- 未配置认证与限流前，`query_analytics` 不得在远端可访问环境启用。
