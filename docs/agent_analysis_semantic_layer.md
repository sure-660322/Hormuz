# 智能体分析事实层：受控快照语义层设计（issue #48，catalog v3）

> 状态：设计 + 独立测试库验证（2026-10-08）。**应用库 `aisdb` 未执行 017 迁移、未建快照**；
> 应用库实施需按项目规则另行确认目标与授权。本文档状态标注见 §9。

## 1. 目标与边界

目标：让受限 Text-to-SQL（沿用 `get_database_schema` / `check_sql` / `execute_sql`，
不新增 SQL 工具）能对通行分析与区域活动分析做**筛选、分组、排名**，
同时与确定性业务工具（`query_strait_passages` / `query_strait_statistics` /
`query_area_ship_activity` 等）保持同一口径。

明确不做：

- 不开放 `ship_positions` 底表或任何无界底表视图（17.9M 行聚合放不进 5s 语句超时）。
- 不让模型写任意空间表达式圈选区域；区域由快照的 `area_id`/`area_version` 绑定。
- 不替代确定性业务工具；能用业务工具回答的问题仍走业务工具。
- 不用提示词当安全控制；安全仍由词法门 + AST 白名单 + 只读角色 + 执行器限额多层强制。

## 2. 语义层方案选择：受控分析快照（普通表，经评审构建脚本填充）

候选方案与取舍：

| 方案 | 取舍 |
| --- | --- |
| 实时视图直通底表 | 否决。通行/区域判定是带读取上限（`MAX_GATE_FIXES_SCANNED` 1M / `MAX_SCANNED_FIXES` 4M）的状态机，视图无法执行「超限拒绝而非截断」的口径，只能靠 5s 超时，违反「不用无界底表视图绕过限制」。 |
| 受限函数（SECURITY DEFINER） | 否决。函数体内不受 AST 白名单约束，等于在模型可达路径上放开自定义代码执行面；且 catalog 冻结 `agent_data` 不承载任何函数（执行器 `function_inventory` 校验为 0）。 |
| **受控分析快照（本方案）** | 采纳。输入有界（固定批次窗口），执行成本 O(快照行数)，EXPLAIN 天然有界；数据由**评审过的构建脚本**调用既有业务服务生成，与业务工具逐行同口径（同一 service 调用，不是 SQL 重写状态机）；刷新与失效规则显式（§6）。 |

快照表位于 `agent_data` schema，owner `agent_view_owner`，`agent_reader` 仅 SELECT；
写入仅由构建脚本经应用库 owner 角色完成（017 将 DML 授予 `pg_database_owner`）。

## 3. 粒度、稳定键、版本与窗口

### 3.1 通行事实（`agent_data.v_passage_evidence`，证据粒度）

每行 = 一次侧别变迁（确定通行或不确定候选），来自 `query_strait_passages`
在**逐日 24h 判定窗**上的调用的并集。

| 列 | 口径 |
| --- | --- |
| `passage_key` | 稳定键：`{window_day}|{direction}|s{start_fix_id}|c{completion_fix_id}`。源报位 id 不变则键不变。 |
| `window_day` / `window_start` / `window_end` | 该次判定所属的 UTC 自然日窗 `[start,end)`。逐日并集 ≠ 一次大窗判定（侧别链只在 24h 前置内回看），使用时必须按 `window_day` 过滤，不能把跨日条件当一次判定。 |
| `direction` | `west_to_east` / `east_to_west`（虚拟双门线口径，56.2°E/56.7°E、25.8–27.1°N）。 |
| `observed_completion_at` / `start_observed_at` | 完成侧首报位 / 起始侧最后报位时间；**观测完成时间，不是精确越线时刻**。 |
| `start_fix_id` / `completion_fix_id` | 源报位 `ship_positions.id`，稳定证据键组成部分。 |
| `uncertain` / `uncertain_reason` | 候选标记与原因（`left_corridor`/`long_gap`/`jump`）；确定行 `uncertain=false, reason=null`。 |
| `ship_name` / `ship_type` | `ships` 当前快照值，可能是 NULL/未知；不声称历史已核实。 |
| `schema_version` / `built_at` | 通行判定契约版本（v4）与快照构建时间。 |

### 3.2 通行按日汇总（`agent_data.v_passage_daily`）

`day`（UTC 自然日）× `direction`：确定通行次数、确定独立船数、不确定候选数。
**限制（catalog 强制注入）**：逐日独立船数**不可相加**当作更大窗口的去重船数；
每日只是该日判定窗内的去重。

### 3.3 区域访问事实（`agent_data.v_area_visit`，访问粒度）

每行 = `query_area_ship_activity`（默认区域 `hormuz_core_v1` v1.0.0，
窗口 `[2026-02-24T16:00Z, 2026-03-03T16:00Z)` = 批次实际覆盖，≤7 天）返回的一次访问。

| 列 | 口径 |
| --- | --- |
| `area_id` / `area_version` | 分析区域版本绑定；模型查询必须带 `area_id` 条件（catalog 强制）。 |
| `visit_key` | `s{ship_id}:f{segment.start_fix_id}`（业务服务原生稳定键）。 |
| `status` | `complete`/`truncated_start`/`truncated_end`/`interrupted`/`uncertain`。 |
| `flags` | 逗号连接的质量标记（宽括号/近边界/同秒冲突/区外证据出上下文等）。 |
| `observed_seconds` / `window_seconds` | 观测停留秒 / 与查询窗交集秒；缺报区间不计入、不插值。 |
| `entry_observed` / `exit_observed` | 观测进入/离开是否成立及时间；不要求相等。 |

### 3.4 区域按日汇总（`agent_data.v_area_daily`）

`area_id` × UTC 自然日：出现去重船数、观测进入/离开次数、累计船时、触日访问数、
各状态访问数。**逐日去重船数同样不可相加。**

### 3.5 覆盖/质量元数据（`agent_data.v_data_coverage`）

每个 UTC 自然日一行（`nnu_ais`，判定走廊范围）：报位数、独立船数、
首末报位时间、`coverage_scope` 说明（走廊子集 ≠ 全源覆盖）。

### 3.6 快照清单（`agent_data.v_snapshot_manifest`，meta 表）

构建脚本写入一行：快照名、catalog 版本、窗口、区域清单、算法版本
（通行 v4 / 区域活动 1.0.1）、源范围、构建时间、明细是否截断、备注。
执行器每次执行前核验该清单行存在且与 catalog 声明一致；**清单缺失即 fail closed**。

## 4. 只读语义层的安全增量（catalog v3）

catalog v3（`backend/app/query_analytics_catalog_v3.json`）相对 v2 的变化：

1. 视图条目新增 `kind`（`view`/`table`）；表条目**无定义哈希**，
   漂移检测 = 列签名（名称/类型/可空性）+ owner + SELECT 权限 + 清单行存在。
   视图仍按 `pg_get_viewdef` 哈希核验（016 三视图定义不变，哈希延续 v2）。
2. 快照表条目带 `required_filters`：证据粒度表（`v_passage_evidence`/`v_area_visit`）
   必须在 WHERE 中对时间列给出**双边界**（下界 + 上界）且跨度 ≤ 24h；
   按日表（`v_passage_daily`/`v_area_daily`/`v_data_coverage`）跨度 ≤ 7 天；
   `v_area_visit`/`v_area_daily` 还必须带 `area_id` 等值条件。
   缺必要过滤或超范围 → 策略拒绝（refused，非语法错误），失败关闭。
3. `meta_tables`（清单表）由执行器核验但**不对模型开放**：catalog 不列出它、schema 载荷不含它，策略只放行 catalog 内关系，模型 SQL 无法引用。reader 角色持有其 SELECT（017 已授）仅供执行器核验清单行存在；行缺失即 fail closed。
4. 行数上限沿用 500 行/256KB；快照表体积小（通行证据数千行、访问数千行），无全库扫描路径。

`query_analytics_policy.py` 新增「必要过滤校验」：从 AST 顶层 WHERE 收集
`>=`/`>`/`<`/`<=`/`BETWEEN` 条件，按列聚合时间边界（只认绑定参数，
与字面量冻结规则一致），校验双边界与最大跨度。`query_analytics_executor.py`
的 catalog 核验按 `kind` 分派。除此之外校验链、角色、连接池、限额全部不变。

## 5. 与确定性业务工具的口径关系

- 快照**不是** SQL 重写的判定结果：构建脚本直接调用 `query_strait_passages` /
  `area_service.query_activity`，写入的每行就是业务服务返回的证据/汇总。
- 对账（验收 #1）在独立测试库上进行：同一数据库上同时跑业务服务与快照 SQL，
  固定同条件样本（跨日、重复通行、边界访问、缺报/未知船型、A=0、部分覆盖）逐项比对。
- 已知语义差异（写进 catalog limitations）：
  - 通行快照是**逐日 24h 判定窗并集**；窗口首日的侧别链无更早历史，
    首日候选可能多于「事后大窗判定」（口径上等同业务工具当日查询）。
  - 方向筛选时业务工具对未统计方向置 null（#47 修复后工具侧语义），
    快照按行存 direction，模型自行 GROUP BY，不再涉及该差异。
  - 区域快照只覆盖清单中登记的 `area_id`（默认区域）；圈选矩形仍走业务工具与
    受控动作契约，不进模型 SQL。

## 6. 刷新、失效与过期规则

- 快照**不自动刷新**。源船位变更（重新导入、批次增删）后必须显式重跑构建脚本
  （与 MobilityDB 派生层「源变更后显式重建」同一项目规则）。
- 每次构建整表重写（TRUNCATE + INSERT，单事务），`built_at` 与清单行同步更新；
  构建失败整个事务回滚，旧快照不被半更新。
- 执行器只核验清单存在与结构一致；`built_at` 新旧本身不构成拒绝条件
  （staleness 由构建流程管理，不由模型查询路径猜测）。

## 7. 验收设计对照

1. **对账**：`scripts/issue48_reconcile.py` 在测试库上同条件逐项比对业务服务与快照
   （含跨日、重复通行、边界访问、缺报/未知船型、A=0、部分覆盖；
   并显式验证「按日独立船数相加 ≠ 全窗去重」的反例存在）。
2. **真实模型查询**：三道题（筛选/分组/排名）经 `/agent/analyze` 走
   `execute_sql` 查快照表，返回答案须带窗口/区域/版本/来源与 query_id；
   采样航速/不完整船时不会被写成全量事实（limitations 注入）。
3. **失败关闭**：catalog 漂移（视图哈希/表列签名/清单缺失）、禁止写入、
   底表/系统目录访问、缺必要过滤、超范围、超时/并发/取消，分别有自动化测试或
   独立测试库上的可核验命令结果。
4. **资源预算**：代表查询在测试库上 EXPLAIN，记录计划与执行耗时；快照表全表
   < 1 万行，任何目录内查询都是毫秒级小扫描，无全库无界扫描路径。
5. **文档**：本文档、`query_analytics_contract.md` 附录、`database_setup.md`、
   `agent_integration.md`、`README.md`、`docs/agent_development_plan.md` 同步。

## 8. 构建与验证入口

- 迁移：`backend/sql/017_agent_analysis_snapshots.sql`（测试库执行；应用库未执行）。
- 测试库准备：`scripts/issue48_prepare_test_db.py`（独立库 `hormuz_sql_test`，
  只读抽取 `aisdb` 判定走廊子集，绝不写 `aisdb`；随后跑 016+017）。
- 快照构建：`scripts/build_agent_analysis_snapshots.py --db-name hormuz_sql_test`。
- 对账：`scripts/issue48_reconcile.py --db-name hormuz_sql_test`。
- 真实模型演示：`scripts/issue48_demos.py`（后端指向测试库，DeepSeek 三题）。

## 9. 各环境状态（截至 2026-10-08）

| 环境 | 状态 |
| --- | --- |
| 独立测试库 `hormuz_sql_test` | 016+017 已执行、快照已构建、对账与验收完成（见 `docs/issue48_sql_acceptance.md`）。 |
| 本机应用库 `aisdb` | **未执行 017、未建快照**；本轮仅有只读 SELECT（业务服务对账与统计）。 |
| 部署环境 | 不适用（当前无正式部署；功能开关仅允许本地回环）。 |
