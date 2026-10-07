# 区域船舶活动与进出分析：后端验证报告（2026-10-07）

范围：issue #41 第一阶段「后端算法与接口」。**不含**前端矩形交互、三模式面板、智能体业务工具、真实模型与浏览器验收（这些保持未开始，待验收后推进）。
基线：`main` / `ead29ac`；分支 `codex/area-ship-activity`；工作树 `D:\my_project\Hormuz-worktrees\codex-area-ship-activity`。
口径与契约：[区域活动模块文档](area_activity.md)。以下数字均为**本机 2026-10-07 实测值**，不是跨环境常量。

## 一、验证项与结论

| 验证 | 命令（工作树根目录） | 结果 |
| --- | --- | --- |
| 单元 + HTTP 契约测试 | `.\backend\.venv\Scripts\python.exe -m pytest backend/tests/test_area_activity_*.py -q` | **37 passed**（算法 14、服务 14、HTTP 9） |
| 独立样例验证（独立测试库 + 独立复算） | `python -X utf8 scripts\verify_area_activity_samples.py` | **PASS=2131 / WARN=0 / FAIL=0**（52 个场景/校验组，self-check 19/19，退出码 0）；证据 `docs/area_activity_samples_result.json` |
| 真实库只读验证与性能基线 | `python -X utf8 scripts\verify_area_activity_backend.py` | 只读性通过；证据 `docs/area_activity_backend_verification.json` |
| 真实 HTTP 冒烟（uvicorn 8030） | `python -m uvicorn backend.app.main:app --port 8030` + `/health`、`/docs`、`/openapi.json` | `/health` 200；4 个 `/api/area-activity/*` 路径进入 OpenAPI；默认区、快照、1 小时活动均 200；非法矩形与无时区时间均 422 + 标准错误体。验证后已关闭该临时端口（8030 不在其他会话占用端口内） |
| 全量后端回归 | `python -m pytest backend/tests -q` | 见 §五 |

### 1.1 独立样例验证（第三方实现，不引用后端算法）

- 独立测试库 `hormuz_area_test`（重建脚本只操作该库；`aisdb` 全程只读）。
- 34 艘样例船、183 条合成报位；18 个窗口场景（含跳点双阈值回归 `S20_fast_small_step_not_jump`、批次范围一致性 `S21_batch_scope_consistency`、短时外出 `S22_short_excursion`）+ 2 个快照场景 + 2 个 A/B 场景 + 17 个参数校验用例。
- 期望值由**只依据 docs/area_activity.md 重写**的朴素 Python 实现给出（不 import `backend.app.*`），再与 HTTP 接口返回逐字段比对；19 项 self-check 全通过。
- 覆盖：进入+离开、三次往返、两端均区外（有效零结果）、四个半开边界点、边界抖动、窗前已在区内、窗后仍在区内、前置状态未知、长缺报中断、跳点、同秒冲突、跨自然日裁剪、窗前观测进入、双侧裁剪、`left_returned` 探测、`no_data`、快照新鲜度/不回退/异来源、A/B 不等长与零基期、17 个参数错误分支。
- 复验轮（定版口径后）收紧为硬断言并通过：`entry/exit.in_window`、每段 `fix_count`/`segment_count`、每日 = 当日 ∩ 窗口、`status` 优先级与 8 个 `flags`、`unobserved_gap_seconds` 含 gap+jump、`window_days` 与 `window_length_days`、`partial` 触发条件、`wide_bracket` 规则（`bracket_seconds > gap_seconds`）。跳点回归的负向对照（把 `jump_min_distance_km` 置 0）会重现 `jump_break`，说明样例对最小位移条件有区分力。
- 第二轮用户复核后的两个修复也由样例硬断言：S21 证明「排除批次后，其他批次的中间报位不能作为越界证据」（`batch_ids=[9001]` 1 次访问、扫描 6；不筛批次 2 次访问、扫描 7，均有独立 SQL 复核）；S22 证明「20 分钟外出（间隔 1200 s、位移 5.45 km/8.8 kn，不构成跳点）会被拆成两次访问、外出区间不计入时长」，并配负向对照（删掉区外报位后回到 1 次访问、1200 s 计入）。

### 1.2 真实库只读验证

- 全过程监听 `before_cursor_execute`：`statement_prefixes=['select','with']`，无非只读语句。
- `ships` / `ship_positions` / `ais_import_batches` 行数与 `pg_stat_user_tables` 的 `n_tup_ins/upd/del` 前后一致 → 未写入源表。
- 数据库目标：本机 `aisdb`（PostgreSQL 17.10 + PostGIS 3.5.2），只读；未重建派生层、未建索引。

## 二、性能基线（本机，已预热缓存，未 DROP CACHES）

算法版本 `area_activity/1.0.1`（含越界探测阈值 480 s）。证据文件时间 2026-10-07T11:33Z。

| 场景 | run1 | run2 | 读取报位数 | 区域内报位数 | 结果 |
| --- | --- | --- | --- | --- | --- |
| 时刻在场（默认区，2026-02-28T12:00Z） | 59.4 ms | 39.9 ms | 3,853 艘参与判定 | — | 在场 175 艘（区域外新鲜 1,438、过期 2,240） |
| 时段 1 小时（默认区） | 2,104 ms | 2,059 ms | 235,742 | 211,639 | 193 艘、进入 13、离开 23、195 次访问 |
| 时段 1 天（默认区） | 2,755 ms | 2,756 ms | 533,371 | 478,093 | 430 艘、进入 298、离开 313、577 次访问、4,098 船时 |
| 时段 7 天（默认区） | 7,245 ms | 7,174 ms | 2,615,969 | 2,335,417 | 1,145 艘、进入 1,256、离开 1,280、1,695 次访问、26,036 船时 |
| 时段 1 天（船型=油轮） | 2,073 ms | — | 176,524 | 156,566 | 105 艘、进入 115、离开 123 |
| 时段 1 天（批次=[4]） | 2,716 ms | — | 380,134 | 343,050 | 399 艘、进入 243、离开 244；`coverage.batch_ids=[4]`，未筛批次时读取 533,371 → **统计与覆盖同批次** |
| 时段 1 天（自选矩形 26.0–26.8N/56.0–56.9E） | 2,241 ms | — | 307,698 | 181,512 | 220 艘、进入 256、离开 283 |
| A/B：1 天 vs 2 天（默认区） | 5,605 ms | — | 两次查询 | — | 变化率按实际窗口长度给日均；明细截断时警告提示 |
| 执行计划（1 天默认区，EXPLAIN ANALYZE BUFFERS） | 规划 1.1 ms / 执行 3,111 ms | — | 计划全文见证据 JSON | | |

要点与限制：

- 成本主要由「时间范围 + 区域」扫描与窗口函数排序决定；规划器选择并行顺序扫描 + BRIN，未使用 `location` 的 gist 索引，因此**已移除**逐行 `location && ST_MinEnvelope` 粗筛（实测 7 天从 5.6 s 降到 4.7 s），内外判定仍用半开规则。
- 会话内 `set_config('work_mem','64MB',true)`：避免 7 天窗口的排序落盘（默认 4 MB 时 `Sort Method: external merge`）。
- 读取上限：单次扫描 ≤ 4,000,000 报位、候选船 ≤ 5,000、访问明细 ≤ 2,000（默认返回 500）、语句超时 20 s、窗口 ≤ 7 天、矩形单边 ≤ 10°。超限**拒绝**（422/503），不截断汇总。
- 交互预算（本机、单请求、已预热）：1 小时 ≤ 3 s、1 天 ≤ 5 s、7 天 ≤ 12 s、快照 ≤ 0.5 s、A/B ≈ 两期之和；超过则返回超时错误而不是部分结果。
- 进一步优化（**未实施，需单独授权**）：`ship_positions(recorded_at)` 与区域组合的索引、把 `stats` 合并进同一次窗口扫描以避免二次读 CTE、或按日预计算。任何数据库写入都不在本轮授权范围。

## 三、本轮发现并修复的缺陷

1. **segment 边界判定错误**：初版用 `break_kind IS NOT NULL` 作为边界条件，而 `'none'` 也是非空 → 每条区域内报位都成为 segment 边界（1 小时窗口产生 >10,000 条边界行并触发上限拒绝）。改为 `IN ('gap','jump','left_returned')`，并用「前一条区外/未知」单独判定。
2. **跳点阈值在短间隔上失效**：先用样本校准：区域内七日相邻报位对中，间隔 ≤15 s 组（130 万对）位移中位数 42 m，仅按 30 kn 推算速度会把 69,677 对 GPS 抖动判成跳点。改为「位移 ≥ 1 km **且** 推算速度 > 30 kn」，七日短间隔组只剩 59 对需要审查。
3. **PostGIS 逐行粗筛拖慢查询**：`location && envelope::geography` 在 1,790 万行上逐行求 geography 包围盒，规划器又未选择 gist 索引；移除后 7 天查询从 5.6 s 降至 4.7 s（见 §二）。

### 3.4 用户复核发现的两处缺陷（2026-10-07 第二轮，版本升到 1.0.1）

4. **批次筛选没有真正作用于活动统计**：`batch_ids` 只进了快照查询的 LATERAL；活动 SQL 的上下文过滤与三处越界探测子查询都没带 `source_batch_id`，而覆盖说明按批次返回，出现「说明是一个批次、统计包含其他批次」。修复：批次条件下沉到 `SCOPE_PREDICATE`（统计、`region_fix_count` 同源）与 `b_probe`/`x_probe` 子查询，并用真实库核对：批次=[4] 时 `coverage.batch_ids=[4]`、读取报位 380,134（未筛批次 533,371）、进入 243/离开 244（未筛 298/313），统计与覆盖一致。
5. **短时间驶出外扩范围再返回被当成连续停留**：探测只在「间隔 > `gap_seconds`(1800 s) 或跳点」时触发；船在 30 分钟内驶出 0.05°（约 5 km）外扩带再回到相近位置时，两端间隔小于缺报阈值、两端位移又小，于是既不探测也不拆分，多计停留并漏掉一次进出。修复：探测阈值改为 `excursion_probe_seconds = 480 s`——离开外扩带再返回至少要走 2×4.98 km ≈ 9.96 km，按最大可信航速 40 kn 折算 ≈ 484 s，故间隔超过 480 s 的相邻对**必然存在**外出可能，一律探测。
   - 真实库量化：7 天上下文内需探测 35,925 对（1 天上下文 8,110 对）；其中 25 对确有中间报位（`left_returned`），全部落在 >1800 s 区间，**新覆盖的 480–1800 s 区间在本七日样本中命中 0 次**——即修复是正确性防护，当前已报告的数量不变，但漏洞在物理上被界住（≤480 s 不可能完成往返）。
   - 代价：7 天查询仍在 7.2–7.5 s 区间（探测为索引点查，未改变数量级）；1 天 2.76 s、1 小时 2.06 s。
   - 残余限制：若船在区外**完全无报位**（AIS 静默），探测无证据，仍按连续观测处理，属采样漏检，已写入 §6 与文档 §2.0。

## 四、验证暴露的文档歧义（已定版）

独立验证脚本提出 9 条歧义，本轮已在 [docs/area_activity.md](area_activity.md) 中逐条定版，实现未改口径、只补齐文档：

1. `left_returned` 与「极大连续 inside 段」定义冲突 → §2.0 明确：状态序列基于上下文范围，另对可疑对做**有界存在性探测**（可越出上下文，只取有/无与首末报位标识）。
2. 每日裁剪与窗口裁剪不自洽 → §2.4 明确每日 = 当日 ∩ `[start, end)`，Σ每日 = 全窗船时。
3. 事件时间是否必须落在窗口内未定义 → §2.4 明确只在 `[start, end)` 内计数，明细用 `entry.in_window` / `exit.in_window` 显式标记。
4. §4.5 明细缺 `in_window` 字段 → 实现与 schema 已补齐（唯一硬失败）。
5. `flags` 取值域未定义 → §2.4 固定 8 个取值，并说明 `prior_state_unknown` / `started_before_window` 由 `status` 表达。
6. `status` 优先级与 `partial` 触发条件未穷举 → §2.4/§2.6 明确优先级与触发条件（窗口边缘截断不触发 `partial`）；`unobserved_gap_seconds` 明确包含 `gap` 与 `jump` 两类未计入区间。
7. `window_days` 含义不明 → §2.5 区分 `window_days`（自然日个数，用于 `daily[]`）与 `window_length_days`（实际长度，日均分母），`equal_length` 按实际长度比较。
8. 测试库依赖表未写全 → §5.1 补 `ais_import_batches`（coverage / `batch_ids` 读取）。
9. 单报位访问的 segments 表示 → §2.4 明确为一条 0 长度 segment。
10. 复验轮追加的 4 条小口径亦已定版：出现去重船数 = 范围内至少一条区域内报位的船；每日状态计数按访问的全窗口 `status` 归类；未观测事件的 `bracket_seconds=null`；`evaluated_ship_count` = `at` 之前至少有一条报位的船。

## 五、回归与未验证项

- 全量后端回归（工作树内 `python -m pytest backend/tests -q`）：**329 passed / 14 skipped**。
- 本轮只新增 `backend/app/services/area_activity/`、`backend/app/routers/area_activity.py`、`backend/app/schemas_area_activity.py`、三个测试文件、两个验证脚本与文档，`backend/app/main.py` 仅新增一行导入与一行路由注册。
- **未验证 / 未开始**：前端矩形交互与三模式面板、地图轨迹联动、智能体三个业务工具与知识库、真实模型问答、浏览器（桌面/窄屏）、并发与多用户下的响应预算、`statement_timeout` 真实触发路径（只在单元测试中以注入异常覆盖）、AIS 来源授权与覆盖完整性。
- 与 #40 的共享文件（`App.vue`、前端 API 类型、智能体 schema）本轮**未改动**，不构成所有权冲突。
