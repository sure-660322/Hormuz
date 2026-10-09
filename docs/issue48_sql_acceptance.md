# issue #48 SQL 分析事实层验收记录（catalog v3）

> 日期：2026-10-08。环境：**独立测试库 `hormuz_sql_test`**（016+017 已应用，快照已构建）。
> **应用库 `aisdb` 未执行 017、未建快照**；本记录不声称应用库或部署环境已实施。
> 复现入口见设计文档 [agent_analysis_semantic_layer.md](agent_analysis_semantic_layer.md) §8。

## 1. 对账（验收 #1）

命令：`python scripts/issue48_reconcile.py --db-name hormuz_sql_test` → **ALL PASS**（0 项不一致）。

| 项目 | 结果 |
| --- | --- |
| 快照清单行存在且窗口一致（analysis_batch_v1，3.0） | PASS |
| 通行证据 8 个 UTC 日逐行一致（稳定键/船/方向/观测完成时间/候选标记） | PASS（536 行 = 504 确定 + 32 候选） |
| 通行按日汇总一致（计数/独立船数/候选数） | PASS |
| 区域访问 1810 条 visit_key 集合与逐字段一致（时间/观测秒/段数/状态/标记） | PASS |
| 区域按日 8 天数值一致（独立船数/进出/船时/各状态访问数） | PASS |
| 覆盖元数据 8 天一致（报位数/独立船数/首末报位） | PASS |
| 样本-跨日（27 艘跨日多次判定） | PASS |
| 样本-重复通行（2 组同船同方向 ≥2 次，如船 1718 东→西 ×2） | PASS |
| 样本-边界访问（665 条 truncated/started_before_window） | PASS |
| 样本-缺报（30 条 long_gap/jump 候选） | PASS |
| 样本-未知船型（16 条 ship_type=未知/NULL） | PASS |
| 样本-A=0（4 行候选数=0 真实零值；无匹配筛选返回 0 行不报错） | PASS |
| 样本-部分覆盖首日 2026-02-24（32.4 万报位，16:00Z 起非整天） | PASS |
| 反加性：西→东逐日独立船数相加 251 ≠ 全窗去重 250 | PASS（反例成立） |

## 2. 真实模型三题（验收 #2）

命令：后端以 `AGENT_DB_NAME=hormuz_sql_test` 启动后
`python scripts/issue48_demos.py --base http://localhost:8038`。

| 题 | 工具链 | 结果 |
| --- | --- | --- |
| 筛选：2026-02-26 西向东油轮确定通行 | get_database_schema → check_sql → execute_sql | **VERIFY-OK**（v_passage_evidence，query_id `aq_20261008T144326…` 等，catalog 3.0，limitations 注入） |
| 分组：按天×方向确定通行次数/独立船数 | 同上 | **VERIFY-OK**（v_passage_daily 14 行，query_id `aq_20261008T144519_82581c74aee1`；回答说明逐日独立船数不可相加） |
| 排名：默认区域 2026-02-25 观测停留前 5 | 同上 | **VERIFY-OK**（v_area_visit 5 行，query_id `aq_20261008T144605_6a9e9e76c59e`，带 area_version 1.0.0 与状态） |

三题回答均带窗口/区域/版本/来源与 query_id；原始转录在 `output/issue48/*_demos.json`（本地，不入库）。
未把采样航速或不完整船时写成全量事实（limitations 随结果注入）。

## 3. 失败关闭（验收 #3）

命令：`python scripts/issue48_acceptance_evidence.py` → **15 项全 PASS**（原始 JSON 在 `output/issue48/*_acceptance_evidence.json`）。

| 用例 | 结果 |
| --- | --- |
| catalog 漂移（真实删 manifest 行） | `CatalogMismatchError: manifest_row:agent_data.v_snapshot_manifest`，fail closed，事后恢复 |
| 写入拒绝 | `25006 cannot execute INSERT in a read-only transaction`（agent_reader_login 实测） |
| 底表访问（策略层） | `QueryRefusedError: 关系必须使用 agent_data 全限定名` |
| 底表访问（DB 层） | `42501 permission denied for schema public` |
| 缺必要过滤（无边界/缺 area_id） | `QueryRefusedError: 缺少必要过滤…`（refused，非语法错误） |
| 超范围（30h 证据窗） | `QueryRefusedError: 查询时间跨度 30.0h 超过上限 24h` |
| 合法对照（齐过滤） | 通过，catalog_version=3.0 |
| 进程并发上限（2） | `AGENT_QUERY_BUSY`，query_executed=False |
| 全局并发上限（4 槽咨询锁） | `AGENT_QUERY_BUSY` |
| 锁超时（1s lock_timeout） | `AGENT_QUERY_TIMEOUT` |
| 取消（cancel_event + 持锁） | `AGENT_QUERY_TIMEOUT`；`pg_stat_activity` 无残留活动查询 |

catalog 列签名漂移与视图哈希漂移的 fail closed 另由离线测试
`backend/tests/test_query_analytics_v3_snapshots.py`（19 项）覆盖。

## 4. 资源预算（验收 #4）

同一证据脚本内以 `agent_reader_login` 对 3 条代表查询 `EXPLAIN (ANALYZE, TIMING OFF, FORMAT JSON)`：

| 查询 | 计划 | 执行耗时 |
| --- | --- | --- |
| v_passage_daily 7 天聚合 | Bitmap Heap Scan（仅 v_passage_daily） | 0.28 ms |
| v_area_visit 24h 窗口 top5（Limit→Sort→Bitmap Heap Scan） | 仅扫描 v_area_visit | 1.14 ms |
| v_data_coverage 全窗口 | Bitmap Heap Scan（仅 v_data_coverage） | 0.02 ms |

快照表全表 < 1 万行（通行证据 536、访问 1810、按日/覆盖各数十行），
任何目录内查询都是毫秒级小扫描；原始 `ship_positions`（17.9M 行）不在 catalog 内，
模型 SQL 路径不存在全库无界扫描。迁移与权限在独立测试库验证（本文件 §1–§3），应用库未执行 017。
