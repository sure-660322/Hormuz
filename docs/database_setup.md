# 数据库与环境说明

Git 不同步数据库。当前仓库不包含可直接重建应用库的完整交接包；`data/handoff/current/` 只剩旧新闻/事件快照，缺少原四表船舶、报位及完整清单，不能执行旧 `handoff_run import` 恢复当前数据。`create_tables.py` 也不能替代迁移和数据恢复。

## 当前数据与来源

- 七日全船 AIS：2026-09-25 导入 4,462 艘、17,921,533 条；UTC 2026-02-24 16:00 至 03-03 15:59:59。来源、文件哈希、逐日对账与限制见[七日导入](real_ais_seven_day_import.md)。
- 北冰洋案例：11,640 条接受报位；规则、隔离记录与来源见[案例说明](arctic_ocean_case.md)。
- 新三船：2026-10-25 追加 27,255 条接受报位，船数到 4,465；见[轨迹导入](trajectory_cases.md)。案例批次排除在普通态势默认时间范围外。
- 中文新闻：原有 290 篇基础上，[中新网批次](chinanews_news_import.md)新增 67 篇；四案例再追加 5 篇去重报道和 4 个事件，本机当次为 news=362、events=82，见[新闻入口](case_news_entries.md)。

以上为对应日期核验值，本轮不查询或修改数据库。真实 AIS 原文件、数据库 dump 及私有配置不提交。新闻只保留来源、标题、摘要与加工字段，不表示获得全文再分发许可。

## 新环境准备

安装 Python 3.11+、Node.js/npm、Git、PowerShell 7；需要独立容器数据库时安装 Docker。依赖与应用启动见[根 README](../README.md#本地运行)。复制 `.env.example` 后仅在本机配置连接和模型密钥，不读取或复制其他维护者的真实 `.env`。

仓库的 `compose.handoff.yaml` 可用于创建隔离空数据库：

```powershell
if (-not (Test-Path -LiteralPath .\deploy\handoff.env)) {
    Copy-Item .\deploy\handoff.env.example .\deploy\handoff.env
}
# 在本机编辑 handoff.env 的占位密码；不要提交。
docker compose --env-file deploy/handoff.env -f compose.handoff.yaml up -d --wait
```

它使用 `mobilitydb/mobilitydb:17-3.5-1.3`，默认独立库 hormuz_handoff、本机端口 25433、独立数据卷。该命令只创建数据库环境，不提供当前完整表结构与数据。恢复须另行确认目标库、备份格式、版本和空库条件；不要对现有库试跑导入、清库或 `down -v`。

## SQL 与脚本边界

| 文件/入口 | 用途与边界 |
| --- | --- |
| `backend/sql/001`–`007` | 历史演进，不能当空库安装顺序；006 会重建 events/news，需备份、审查和事务保护 |
| `008_fresh_handoff_schema.sql` | 旧空库交接入口；不等于当前最新结构，不对已有库重放 |
| 009–012 与旧 build 脚本 | 遗留轨迹/关联/停留/相遇派生流程，不属于当前初始化、部署或待重建步骤 |
| `013_agent_analytics_readonly.sql` | 旧模拟批次 SQL 语义层，会改变 PUBLIC 权限，不对真实应用库重放 |
| `014_real_ais_import.sql` | AIS 来源审计字段扩展，不导入数据；七日导入由 `backend.import_real_ais_days` 实施 |
| `015_retire_simulation_agent_view.sql` | 旧视图实际存在时以 RESTRICT 退役，不借此重建派生任务 |
| `016_agent_views_nnu_ais.sql` | 真实 AIS 的 ships/events/news 语义视图及只读角色；本机曾验收，含 TimescaleDB 集群的只读账号还需相应禁载设置 |
| `017_agent_analysis_snapshots.sql` | 在 016 上增加受控分析快照与清单；独立测试库已验证，应用库未实施 |
| `create_tables.py` | 只补缺失 ORM 表，不准备全部扩展、空间结构和索引 |
| `seed_data.py` / `generate_demo_data.py` | 旧事件语义，不能用作当前初始化入口 |

`ship_positions.location` 由数据库生成列维护，应用不写入。恢复须保留 ID、外键、序列、索引、约束及扩展兼容性。结构变更使用递增编号 SQL，遇错即停。数据库备份可读目录不等于演练过完整恢复。

内部 SQL catalog v3 的快照规则及显式刷新流程见[分析语义层](agent_analysis_semantic_layer.md)和[安全契约](query_analytics_contract.md)。源船位变化可能令快照失效，必须显式重建并核对；这不恢复已取消的旧派生任务。

## 图片与地图资源

封面从 `NEWS_IMAGE_ROOT/images/` 读取；未配置时默认仓库上一级 `news_raw_data`。Git 中的中文批次图片不会自动复制到服务目录，部署者需提供文件并核对 `events.image_path`；缺图时 `/events/{event_id}/cover` 返回 404。数据库、图片和瓦片必须分别交接，不能由代码更新代替。

## 自用部署材料

旧 Docker 部署代码、数据包和使用说明已按用户要求仅保留本地，见[本地入口](README.md#本地部署材料)。10 月 19 日旧包不含 10 月 25 日案例增量，不能直接宣称与当前代码/数据配套。本轮没有执行迁移、导入、恢复或服务器部署。
