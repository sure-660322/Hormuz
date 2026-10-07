# 区域船舶活动与进出分析：矩形圈选、手动与智能体共用（issue #41）

状态（2026-10-07）：第一阶段「后端算法与接口」**已实现、已在独立测试库与真实库只读验证，待用户验收**；第二、三阶段「手动矩形圈选/三模式面板/地图证据联动」「三个智能体业务工具/当前区域上下文/查看区域分析」**已实现，浏览器端到端冒烟通过，完整独立验收见[验收报告](area_activity_acceptance.md)**。未推送、未合并、未部署。

工作树 `D:\my_project\Hormuz-worktrees\codex-area-activity-ui`，分支 `codex/area-activity-ui`，基线 `aca8d3c`（含第一阶段两个提交）。两种入口共用同一后端服务：手动界面调用 `GET/POST /api/area-activity/*`，智能体调用三个只读工具（`query_area_ship_snapshot`/`query_area_ship_activity`/`compare_area_ship_activity`），同一参数返回一致结果。智能体侧细节见[区域活动智能体工具](area_agent_tools.md)与[智能体接入契约](agent_integration.md)；前端组件与展示规则见[区域活动前端](area_activity_frontend.md)。

数据现状（2026-10-07 本机只读核验）：`ships=4,462`、`ship_positions=17,933,173`、`data_source='nnu_ais'` 单一来源；批次 1–7 为 2026-02-24T16:00Z–2026-03-03T15:59:59Z 的逐日文件，批次 8 为北极案例单船（1 艘，2026-03-26–03-31）。本机最近一次核验值，不是跨环境常量。

---

## 一、边界规则

### 1.1 矩形包含规则（v1 固定）

| 项 | 规则 |
| --- | --- |
| 经度 | `west <= longitude < east`（西含东不含） |
| 纬度 | `south <= latitude < north`（南含北不含） |
| 形状 | 仅轴对齐矩形；不支持任意多边形、不支持跨 180° |
| 一致性 | SQL 侧与 Python 侧使用同一半开规则；边界点归属于「内侧」的只有西/南边 |

理由：半开区间让相邻矩形不重不漏，避免「边界点算两次」；SQL 侧与 Python 侧写死同一规则。查询不使用 PostGIS 的 `location && envelope` 粗筛——实测规划器不会为该形状选择 gist 索引，逐行求 geography 包围盒反而更慢（验证报告 §二）。

### 1.2 默认分析区域（版本 `hormuz_core_v1`）

| 字段 | 值 |
| --- | --- |
| `area_id` | `hormuz_core_v1` |
| 名称 | 霍尔木兹海峡核心通行区（项目分析区域） |
| 版本 | `1.0.0`（2026-10-07 定版） |
| `south` / `west` / `north` / `east` | `25.8` / `55.8` / `27.1` / `57.1` |
| 跨度 | 纬度 1.3°、经度 1.3°（约 144 km × 129 km） |
| 依据 | 现有「海峡虚拟双门线」判定走廊的包围盒：门线 56.2°E / 56.7°E、判定纬度带 25.8–27.1°N、邻域经度 55.8–57.1°E，定义见 `backend/app/services/agent/config.py` 与 `docs/agent_integration.md`；与前端默认地图中心 `[26.35, 56.5]`（`frontend/src/components/MapView.vue`）一致 |
| 性质 | **项目分析区域**，不是官方航道（TAS/TSS）边界，也不是「核心区」的权威定义；可在接口中用 `west/south/east/north` 覆盖 |

`area_id` 在请求显式给出矩形时为 `custom`，并回显 `is_default=false`；默认区域请求回显 `hormuz_core_v1`。

### 1.3 参数校验（后端为权威，拒绝而非截断）

- `west < east`、`south < north`，且在 `[-180,180]`、`[-90,90]` 内；四个边界必须同时给出或同时省略（省略即默认区域）。跨 180°（`west > east`）直接拒绝。
- 矩形跨度上限：`lat_span <= 10°` 且 `lon_span <= 10°`；超限 422。
- 时间必须带显式时区（`utcoffset()` 非空）；`start < end`；`end - start <= 7 天`（已核验的逐日覆盖范围）；超限 422。
- 船型、来源、批次参数见 §3。

---

## 二、算法口径（版本 `area_activity/1.0.1`）

变更记录：`1.0.0` 首版；`1.0.1`（2026-10-07）来源批次条件同时作用于上下文、越界探测与覆盖统计；越界探测阈值由 `gap_seconds` 改为 `excursion_probe_seconds`，覆盖「短时间内驶出外扩范围再返回」的漏检。

### 2.0 公共定义

- **报位（fix）**：`ship_positions` 一行，`nnu_ais` 来源，按 `(recorded_at, id)` 排序，`id` 只用于同一时刻的稳定排序，不用于业务键。
- **内外判定**：§1.1 半开矩形。
- **观测上下文（scope）**：`[start - lookback, end + lookahead)` ∩ `context_bbox` ∩ 来源批次。`context_bbox` = 分析矩形按 `context_margin_deg`（默认 0.05°，约 5.5 km）外扩。状态序列（`lag/lead`、segment 划分）在该范围内计算：上下文内的区外报位**保留在序列里**，不先删区外点再判定。**来源批次条件同时作用于上下文、越界探测与覆盖统计**，三者的批次范围必须一致，不允许「覆盖说明是一个批次、统计包含其他批次」。
- **有界越界探测（v1.0.1 起覆盖短时外出）**：对「待探测对」做一次按 `(ship_id, recorded_at, id)` 索引的**存在性探测**：这两条区内报位之间是否还有该船的任何其它报位（不限位置，可越出 `context_bbox`）。探测只返回「有/无」与首末报位的 `id` 与时间，不读取该区间内的全部报位；有中间报位即证明船被观测到在区外，访问被拆开（`left_returned`）。
  - **待探测对的判据**：相邻两条区内报位，间隔 > `excursion_probe_seconds`（默认 480 s）**或**（位移 ≥ `jump_min_distance_km` 且推算速度 > `jump_speed_kn`）。
  - **480 s 的来源**：船要离开上下文矩形再返回，至少要走 2 倍外扩距离。经度方向 `0.05° × 111.32 × cos(26.5°) ≈ 4.98 km`，往返 ≥ 9.96 km；按最大可信航速 `max_plausible_speed_kn = 40`（20.58 m/s）折算 ≈ 484 s，取 480 s。因此**间隔 ≤ 480 s 的相邻对不可能完成一次外出往返**，无需探测；超过 480 s 就必须探测。该阈值只依赖外扩范围与最大可信航速两个已声明常量。
  - 残余限制：若船在区外**完全没有报位**（AIS 静默），任何探测都找不到证据，此时按连续观测或 `gap` 处理，属采样漏检，见 §6。
- **候选船**：在 `[start, end)` 内至少有一条区域内报位的船。
- **统计时区**：全部按 UTC 归日、按 UTC 输出；`[start, end)` 半开。
- **稳定键**：访问键 `visit_key = "s{ship_id}:f{第一个区域内报位 id}"`；事件证据使用源报位 `id`，不使用每次查询重置的序号。同一访问在重叠窗口/两期比较中得到同一键，不重复生成证据。

### 2.1 时刻在场（snapshot）

1. 对每艘船取 `recorded_at <= at` 的最新报位（`ships` JOIN LATERAL，走 `idx_ship_positions_ship_recorded_at`）。
2. 该报位的龄期 `age = at - recorded_at`：
   - `age <= freshness_seconds`（默认 3600 s，与 `/ships/snapshot` 的 `SNAPSHOT_MAX_AGE` 一致）→ 新鲜报位；
   - `age > freshness_seconds` → **过期**，不计入在场，也不回退到更早的区域内报位；计入 `summary.stale_fix_count`。
3. 新鲜报位在矩形内 → 计入在场；在矩形外 → 不计入（**不得**用更早的区域内点把船补回）。
4. 返回：在场船数、有界船舶列表（含 `recorded_at`、`age_seconds`、`fresh`、`inside`）、过期船数、区域外新鲜报位数、评估船数。`evaluated_ship_count` = 在 `at` 之前至少有一条该来源报位的船（其最新报位要么新鲜要么过期，过期计入 `stale_fix_count`；`at` 之前完全没有报位的船不计入）。报位是历史观测，不保证 `at` 时刻的真实位置。

### 2.2 时段出现与进出

1. 状态序列：候选船在 scope 内的报位按 `(recorded_at, id)` 排序，逐条标 `inside`（上下文内的区外报位保留在序列中）。
2. **访问（visit）**：序列中一段极大连续的 `inside=true` 报位。`prev_inside` 不是 `true` 的行开启新访问。若两条相邻区域内报位经 §2.0 的越界探测证明其**之间存在区外报位**，该段被切成两次访问（`left_returned`）——这是「段落不连续」的唯一例外，依据是观测证据而不是插值。
3. **观测进入**：访问首条报位的 `prev_inside = false` → 观测到「区外→区内」转换。事件时间取**区内首点**时刻；证据区间 `[prev_fix, first_inside_fix]`（外侧相邻报位与内侧首点）。`prev_inside IS NULL`（lookback 内没有更早报位）→ `prior_state="unknown"`，**不计进入**，访问 `status` 记 `truncated_start`。
4. **观测离开**：访问末条报位的 `next_inside = false` → 观测到「区内→区外」转换。事件时间取**区内末点**时刻；证据区间 `[last_inside_fix, next_fix]`。`next_inside IS NULL` → 结束状态未知，`exit.observed=false`，不计离开，访问 `status` 记 `truncated_end`。
5. **窗前已在区内**：访问首点早于 `start` 且 `prior_state="unknown"`（lookback 内全是区内点）→ 访问 `started_before_window=true`，计为截断访问，不计进入。
6. **窗后仍在区内**：访问末点之后 scope 内无更晚报位，或更晚报位仍在区内 → `exit.observed=false`，不计离开，由 `last_inside_at` 与 `exit.in_window` 区分「窗后仍在区内」与「此后无报位」。
7. **两端均区外**：连续两条区外报位之间不做任何插值补造穿越；只有存在至少一条区域内报位才产生访问。
8. `候选船发现` 只用于缩范围；判定读取必要的区外前后报位（scope 内 `lag/lead`），不先删区外点。

### 2.3 缺报、跳点与边界抖动（v1 固定规则）

对同一访问内相邻两条报位 `(prev, cur)`：

| 情形 | 判定 | 处理 |
| --- | --- | --- |
| `cur - prev <= gap_seconds`，且不满足跳点条件 | 连续观测 | 该区间计入停留时长 |
| 间隔 `> excursion_probe_seconds` **或**（位移 `>= jump_min_distance_km` 且推算速度 `> jump_speed_kn`），且探测到**两报位之间存在同船其它报位** | `left_returned`：船在期间被观测到在区外 | **拆成两次访问**（离开+进入均计入）；两侧事件按 §2.3 统一规则判定 `wide_bracket`（即 `bracket_seconds > gap_seconds` 才为 true，不是无条件置位），区外证据在上下文之外时另标 `outside_evidence_out_of_context` |
| 间隔 `> gap_seconds`，中间无任何同船报位 | `gap`：缺报中断 | **不拆分、不累计该区间**，访问标 `gap_interrupted`，区间计入 `unobserved_gap_seconds` |
| 间隔 `<= gap_seconds`，位移 `>= jump_min_distance_km` 且推算速度 `> jump_speed_kn` | `jump`：疑似异常跳点 | 不累计该区间（同样计入 `unobserved_gap_seconds`），访问标 `jump_break` |

- 推算速度 = haversine(prev, cur) / 间隔小时数（节）；两个阈值必须**同时**满足才算跳点。阈值 `jump_speed_kn=30.0`、`jump_min_distance_km=1.0`，依据：区域内七日样本相邻对里，间隔 ≤15 s 组的位移中位数只有 42 m（GPS 抖动），只按航速判定会把 69,677 对误判为跳点；加上 ≥1 km 位移后，短间隔对七日只剩 59 次要审查。
- `gap_seconds=1800`（30 min）默认值依据：区域内 2026-02-28 单船相邻报位间隔 p50=12 s、p90=96 s、p99=636 s，30 min ≈ 2.8×p99；**尚未用全部七日样本独立校准**，按版本参数暴露。
- 边界抖动：v1 **不做缓冲/滞回**，包含规则严格按 §1.1。若事件两侧报位中**区内一侧**距离矩形边界 `< boundary_band_m`（默认 500 m，haversine 到矩形的最近边），事件标 `near_boundary=true` 并计入 `near_boundary_event_count`，**不改变计数**。该标记只提示抖动风险，未识别出的抖动仍会计次。
- 同秒冲突：同一 `recorded_at` 多条报位按 `id` 稳定排序；若相邻两条同秒报位内外状态不同，事件标 `same_second_conflict=true`（区间长度为 0，不影响时长）。

### 2.4 停留时长与按日统计

- **观测支持的停留时长** = 访问内所有「连续观测」区间长度之和；即每个 `segment` 的 `end_at - start_at`：相邻报位区间全部计入，缺报区间、跳点区间、进入括号区间（区外末点→区内首点）与离开括号区间（区内末点→区外首点）**都不计入**。不做插值估计。
- 一个 segment = 访问内被 `gap`/`jump` 断开的连续段；`segment` 的起止报位 id、时刻、`fix_count` 一并返回，便于核对。单条报位的访问表示为一个 0 长度的 segment（不是空数组）。
- `unobserved_gap_seconds` = 访问内所有**未计入时长**的区间之和（`gap` 与 `jump` 断点两侧的时间差）。
- **窗口裁剪**：`window_seconds` = 各 segment 与 `[start, end)` 的交集之和。
- **按日裁剪**：每日 `observed_ship_seconds` = 各 segment 与（当日 `[00:00Z, 24:00Z)` ∩ `[start, end)`）的交集之和；同一天内不重复计入，跨日访问按交集拆分，Σ每日 = 全窗 `observed_ship_seconds`。
- **事件计数**：`observed_entry_count` / `observed_exit_count` 只计 **事件时间（区内首点/末点）落在 `[start, end)`（按日时落在当日）** 的事件。因此明细里 `entry.observed=true` 而事件时间早于 `start` 时，汇总不计数——这类访问同时体现为 `truncated_start_visit_count`，明细中的 `entry.in_window=false` 是同一事实的显式标记。
- 每日与全窗分别给出：出现去重船数（当日/全窗各自去重）、观测进入次数、观测离开次数、累计船时、访问数（当日涉及的访问）。**出现去重船数** = 在该时间范围内至少有一条区域内报位的船（与「与该范围相交的访问所涉船」等价）；每日的 4 个状态计数按访问的**全窗口** `status` 归类（同一访问不会在不同自然日被算成不同状态），`visits_touching_day` 为当日涉及的访问数。**每日去重船数不得相加当作全窗去重**；进入次数不要求等于离开次数（窗外进入/窗内离开/缺报都会造成差额）。
- 访问状态分类（`status`，优先级从高到低；多个条件同时成立时取先命中者，全部条件另在 `flags` 中列出）：
  1. `truncated_start`：访问在窗口开始前已在区内（首点 < `start`），或前置状态未知（lookback 内无更早报位）；
  2. `truncated_end`：离开未被观测到（访问在窗口内未闭合）；
  3. `interrupted`：存在缺报中断（`gap_interrupted`）；
  4. `uncertain`：存在其它质量标记（跳点、宽括号、边界近邻、同秒冲突、区外证据在上下文之外）；
  5. `complete`：进入与离开都被观测到，且无上述标记（事件时间是否计入本窗口由 `entry.in_window` / `exit.in_window` 单独标记）。
- `flags` 取值固定为：`gap_interrupted`、`jump_break`、`wide_entry_bracket`、`wide_exit_bracket`、`near_boundary_entry`、`near_boundary_exit`、`same_second_conflict`、`outside_evidence_out_of_context`。前置状态未知与窗前已在区内不进入 `flags`，由 `status`、`prior_state` 与 `entry.observed` 表达。

### 2.5 两时段比较（A/B）

- 同一矩形、同一船型与来源筛选、同一算法版本；允许不等长窗口，回显 `window_days_a/b`（窗口覆盖的 UTC 自然日个数，用于 `daily[]` 分桶）与 `window_length_days_a/b`（窗口实际长度，含小数天）。
- 指标：出现去重船数、观测进入次数、观测离开次数、累计船时（小时），以及各自的「日均」（分母 = **窗口实际长度**，不是自然日个数；12 小时窗口按 0.5 天计，避免日均被整天数压低）。
- `delta = b - a`；`change_rate = (b - a) / a`，`a == 0` 时 `change_rate = null` 并给出说明；不产生 `NaN`/`Infinity`，无观测不回填 0。
- `comparability.equal_length` 比较两期**实际长度**是否相等，因此 12 h 与 24 h 判为不等长。
- 覆盖可比性：返回 `same_area/same_filters/same_algorithm/equal_length`，覆盖不一致（批次不同、区域内有观测的时间跨度不同）或任一窗口无报位时在 `warnings` 中提示；不输出无条件的「活动增减」结论。

### 2.6 快照/活动的状态取值

| status | 含义 |
| --- | --- |
| `ok` | 有观测且无不确定候选，明细未被截断 |
| `partial` | 有观测，但存在不确定候选（缺报/跳点/宽括号/边界近邻/同秒冲突/前置状态未知）**或**访问明细被 `visit_limit` 截断（汇总仍完整） |
| `no_data` | 读取范围内没有任何可判定报位 → 不能解释为「零船」 |
| `ok` + 零结果 | 有报位但窗口内区域内无船 → **有效零结果**，与 `no_data` 区分 |

`complete` 之外的访问状态（`truncated_*`）本身不触发 `partial`：窗口边缘的截断是正常现象，只有质量标记与明细截断才触发。

---

## 三、参数与默认值（`area_activity/1.0.1`）

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `freshness_seconds` | 3600 | 时刻在场的新鲜度阈值 |
| `gap_seconds` | 1800 | 缺报断开阈值 |
| `jump_speed_kn` | 30.0 | 异常跳点推算速度阈值 |
| `jump_min_distance_km` | 1.0 | 异常跳点最小位移（与速度阈值同时满足） |
| `state_lookback_seconds` | 21600（6 h） | 窗口前读取前置状态的范围 |
| `state_lookahead_seconds` | 21600（6 h） | 窗口后读取结束状态的范围 |
| `context_margin_deg` | 0.05 | 观测上下文矩形外扩（约 5.5 km） |
| `max_plausible_speed_kn` | 40.0 | 推导游界探测阈值用的最大可信航速 |
| `excursion_probe_seconds` | 480 | 相邻区内报位间隔超过它就必须探测中间报位（由外扩范围与最大可信航速推出，见 §2.0） |
| `boundary_band_m` | 500.0 | 边界近邻标记距离 |
| `day_bucket_time_zone` | `UTC` | 归日时区 |
| `source` | `nnu_ais` | 受控来源 |
| `batch_ids` | `null`（全部） | 可选批次白名单；**同时**约束上下文读取、越界探测与覆盖统计 |
| `max_scanned_fixes` | 4,000,000 | 超过直接拒绝，不截断 |
| `max_candidate_ships` | 5,000 | 超过直接拒绝 |
| `max_visit_rows` | 2,000 | 明细返回上限（汇总不受截断影响） |
| `max_snapshot_ships` | 5,000 | 时刻在场列表上限 |
| `max_window_days` | 7 | 时段与 A/B 单窗上限 |
| `max_rect_span_deg` | 10.0 | 矩形单边跨度上限 |
| `statement_timeout_ms` | 20000 | 服务端语句超时，超时返回 503 |
| `work_mem_mb` | 64 | 该查询会话的排序内存（`set_config(..., true)`，避免 7 天窗口排序落盘） |

船型筛选：`ship_type` 可重复；取值为 `ships.ship_type` 精确匹配；两个保留值 `__missing__`（NULL/空）与 `__unknown__`（`未知`）。为空表示全部船型。不按船名推断，不使用历史船型反推。

---

## 四、REST API 契约（前缀 `/api/area-activity`）

所有时间为带时区 ISO 8601，响应统一 UTC。参数错误返回 422 且错误体与现有路由一致：`{"detail": {"code": "INVALID_REQUEST", "message": "...", "request_id": "..."}}`。

### 4.1 `GET /api/area-activity/default-area`

返回默认区域版本、边界、依据与算法版本，供前端展示与「恢复默认区域」。响应：`{status, area, algorithm, limitations}`。

### 4.1.1 `GET /api/area-activity/ship-types`

船型候选目录（手动多选与智能体共用，不在前端硬编码）。响应：
`{status, source, total_ships, ship_types[], reserved[], count, limitations[]}`，
其中 `ship_types[]` 为 `{value, label, raw_values[], count, count_scope}`，按数量降序；保留值 `__missing__`（NULL/空，label「缺失（空值或 NULL）」）与 `__unknown__`（数据库取值「未知」，label「未知」）同时出现在 `reserved` 中；`Σcount == total_ships`。
口径：来自 `ships.ship_type` 的当前取值分布，是当前快照属性，不代表历史船型已逐条核实；不按船名推断。空表返回 `status="no_data"` 与空列表（有效零结果，不是错误）。
本机 2026-10-07 实测：25 项、`total_ships=4462`（货船 999、油轮 793、`__missing__` 707、`__unknown__` 348、…）。

### 4.1.2 `POST /api/area-activity/resolve-area`

把手动圈选或智能体给出的矩形解析成带版本的区域标识，**与 snapshot/activity/compare 使用同一套半开规则与跨度校验**：非法、超跨度或跨 180° 的矩形在这里就以 422 拒绝（`INVALID_REQUEST`），避免前端拿着后端不接受的区域去查询。

请求体：`{west, south, east, north, area_id?}`（四个边界必填）。响应：`{status, area, message, limitations}`；`area` 与查询响应同构（`area_id`/`name`/`version`/`is_default`/`basis`/`bounds`/`span_deg`/`containment`），调用方给出的 `area_id` 在自定义矩形时回显。
注意：默认区域请直接用 `default-area` 的返回值，不要把默认矩形当自定义矩形提交（坐标相同但 `area_id` 会变成 `custom`）。

### 4.2 `GET /api/area-activity/snapshot`

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| `at` | 是 | 历史时刻（带时区） |
| `west`/`south`/`east`/`north` | 否 | 四者同时给出则替换默认区域 |
| `ship_type` | 否 | 可重复 |
| `freshness_seconds` | 否 | 覆盖默认 3600 |
| `limit` | 否 | 列表上限，默认 500，最大 5000 |

响应：`{status, area, query, algorithm, coverage, summary, ships[], limits, limitations[]}`。`ships[]` 仅含在场船，含 `ship_id, name, mmsi, ship_type, latitude, longitude, speed, recorded_at, age_seconds, fresh, inside`。`summary` 含 `in_area_count, out_of_area_fresh_count, stale_fix_count, evaluated_ship_count, freshness_seconds`。

### 4.3 `GET /api/area-activity/activity`

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| `start`/`end` | 是 | `[start, end)`，最长 7 天 |
| `west`/`south`/`east`/`north` | 否 | 分析矩形 |
| `ship_type` | 否 | 可重复 |
| `batch_ids` | 否 | 来源批次白名单，可重复；同一批次条件同时作用于统计、上下文与越界探测，`coverage.batch_ids` 回显实际生效批次 |
| `state_lookback_seconds` / `state_lookahead_seconds` | 否 | 0–86400 |
| `visit_limit` | 否 | 明细上限，默认 500，最大 2000 |

响应：`{status, area, query, algorithm, coverage, summary, daily[], visits[], limits, limitations[]}`。
`visits[]` 结构见 §4.5；`daily[]` 字段见 §4.6。

### 4.4 `GET /api/area-activity/compare`

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| `start_a`/`end_a`/`start_b`/`end_b` | 是 | 两个 `[start, end)` 窗口 |
| 其余 | 同 activity | 两期共用 |

响应：`{status, area, algorithm, windows{a,b}, metrics[], comparability, a, b, limitations[]}`。

### 4.5 明细行（`visits[]`）

```json
{
  "visit_key": "s1234:f987654",
  "ship_id": 1234, "ship_name": "…", "mmsi": "…", "ship_type": "油轮",
  "entry": {"observed": true, "observed_at": "…", "bracket_seconds": 420.0,
            "inside_fix": {"id": 987654, "recorded_at": "…", "latitude": 26.4, "longitude": 56.6},
            "outside_fix": {"id": 987600, "recorded_at": "…", "latitude": 26.2, "longitude": 56.1},
            "outside_evidence_in_context": true, "near_boundary": false,
            "wide_bracket": false, "same_second_conflict": false, "in_window": true},
  "exit": {"observed": true, "observed_at": "…", "bracket_seconds": 300.0,
           "inside_fix": {...}, "outside_fix": {...}, "outside_evidence_in_context": true,
           "near_boundary": true, "wide_bracket": false, "same_second_conflict": false,
           "in_window": true},
  "prior_state": "outside",
  "first_inside_at": "…", "last_inside_at": "…", "fix_count": 120, "segment_count": 1,
  "segments": [{"segment_no": 1, "start_at": "…", "end_at": "…",
                "start_fix_id": 987654, "end_fix_id": 987800,
                "seconds": 1800.0, "in_window_seconds": 1500.0, "fix_count": 120}],
  "observed_seconds": 1800.0, "window_seconds": 1500.0, "unobserved_gap_seconds": 0.0,
  "started_before_window": false, "touches_window": true,
  "status": "complete", "flags": ["near_boundary_exit"]
}
```

`entry.in_window` / `exit.in_window` 表示该事件时间是否落在本查询窗口内，与 §2.4 的计数规则一致。未观测到的进入/离开为 `observed=false`、`observed_at=null`、`bracket_seconds=null`、`outside_fix=null`，`inside_fix` 仍给出区内首点/末点。

### 4.6 `daily[]`

```json
{"date": "2026-02-25", "ships_observed": 320, "observed_entry_count": 210,
 "observed_exit_count": 205, "observed_ship_seconds": 317880.0, "observed_ship_hours": 88.3,
 "visits_touching_day": 260, "complete_visit_count": 180, "truncated_visit_count": 60,
 "interrupted_visit_count": 4, "uncertain_visit_count": 12}
```

---

## 四之二、手动界面与智能体入口（issue #41 第二、三阶段）

### 4.7 手动界面（frontend）

- 入口：地图左侧工具栏「区域」（`data-testid="tool-area"`）打开区域活动面板；区域状态条显示当前区域名称、`area_id`、四边界与跨度，并提供「重新圈选」「恢复默认区域」「取消绘制」。
- 圈选：点「重新圈选」进入绘制模式（地图显示提示条），在**地图上按住左键拖动**画矩形，松手后由父组件调用 `POST resolve-area` 校验；失败则回滚到原区域并显示后端 `message`，不把无效矩形留给查询。`Esc` 取消绘制；跨度小于 0.01° 视为误触，不提交。缩放/平移地图不改变分析区域。
- 三模式：时刻在场（默认时刻对齐当前地图回放时刻，避免用「现在」查历史 AIS）、时段活动（UTC 半日区间 `[start, end)`，界面标注终点不含）、两时段比较（A/B 两组，同一矩形与船型条件）。
- 船型筛选：默认全部，数据来自 `ship-types`；`__missing__`/`__unknown__` 显示为「缺失（空值或 NULL）」「未知」。
- 结果展示：摘要、每日表与趋势图、访问明细（entry/exit 证据报位、segments、flags、观测/窗口/未观测秒数）、A/B 指标表（`change_rate=null` 显示「基期为 0，无法计算变化率」）；`limits.list_truncated`/`limits.detail_truncated` 显式提示；`limitations` 与 `coverage` 原文展示；`status=no_data` 与「有效零结果」分开表述。
- 区域变更：旧结果立即标记「区域已变更，待查询」并注明结果所属区域；重新查询成功后清除标记。
- 证据联动：访问行「地图定位」/「显示区间」→ 复用现有 `ship_track` 地图动作加载该访问 `first_inside_at → last_inside_at` 的有界轨迹，与回放时刻区分。
- 请求守卫：`requestSeq` + `AbortController`，快速换区/换模式/连续查询时旧响应不覆盖新状态。

### 4.8 智能体入口

- 三个只读工具与 `area_context` 请求字段、`analysis_actions` 响应动作见[智能体接入契约](agent_integration.md)与[区域活动智能体工具](area_agent_tools.md)。
- 前端把当前选定区域通过 `area_context` 传给 `/agent/analyze`（请求区域的权威值，模型不得悄悄改写）；回答携带 `analysis_actions[type=area_activity]` 时，地图区出现「查看区域分析」入口，点击后打开面板并恢复该次调用的区域、模式、时间与船型条件。
- 「写入对话」把面板当前区域与条件生成中文提示词填入智能体输入框（不自动发送）。

---

1. **独立测试库**：脚本在同一个 PostgreSQL 实例上创建独立库 `hormuz_area_test`（只影响测试库，绝不写 `aisdb`），按真实结构建最小表：`ships`、`ship_positions`（含 PostGIS 生成列 `location`）与 `ais_import_batches`（coverage / `batch_ids` 会读取它；缺表时接口按数据库错误处理），插入构造报位。
2. **独立复算**：样例与期望值由**不引用后端算法模块**的朴素 Python 实现独立算出（只读本文档），再与 HTTP API / 服务函数结果逐字段比对。
3. 覆盖样例：进入+离开、多次往返、两端均区外、边界点（半开规则）、边界抖动、窗前已在区内、窗后仍在区内、前置状态未知、长缺报中断、跳点、同秒冲突、跨日裁剪、跨窗裁剪、A/B 不等长与零基期、无效矩形/超大矩形/超时窗拒绝。
4. **只读真实库核对**：在 `aisdb` 上用同一服务跑 1 日与多日只读查询，记录 EXPLAIN (ANALYZE)、扫描量、冷/暖耗时，核对源表未被写入（查询前后行数与 `pg_stat` 写计数不变）。
5. 单元测试（不连库，假会话）覆盖纯算法与参数校验；HTTP 契约测试覆盖成功/空结果/参数错误分支。

验证证据与命令记录：
- 第一阶段：`docs/area_activity_backend_verification.md`（后端算法与真实库只读基线）。
- 第二、三阶段：`docs/area_activity_acceptance.md`（前端 build/check、浏览器手动与智能体入口、真实模型、独立复算）。
- 前端组件层面的检查：`docs/area_activity_frontend.md`。

---

## 六、已知限制（必须随结果一起表述）

- 默认区域是项目分析区域，不是官方航道边界；`area_id/version/basis` 随结果回显。
- 报位是历史观测，时刻在场所给位置不保证 `at` 时刻真实位置；过期报位不计入在场。
- 出现数不是进出次数，也不是连续在场人数；报位频率差异不能换算成交通量。
- 缺报区间不计入停留时长；不做插值；采样漏检可能漏掉短暂穿越（间隔 ≤ `gap_seconds` 且无中间报位时按连续观测处理）。
- 进入次数不要求等于离开次数；窗外进入/窗内离开/缺报都会造成差额。
- AIS 来源授权与覆盖尚未核实；批次 1–7 为逐日文件，批次 8 为案例单船。
- 圈选只支持轴对齐矩形（不支持任意多边形、不支持跨 180°）；矩形单边跨度上限 10°，超限由后端拒绝而不是截断。第一版不做缓冲/滞回，边界抖动只标记近边界不改计数。
- 智能体明细有界（快照 ≤50 艘、访问 ≤30 条），被裁剪时必须在回答与面板里说明「还有 N 条未列出」；汇总不受裁剪影响。
- 未实现：结果缓存（每次请求实时读取；如需缓存，键必须包含区域版本、时间窗、筛选、来源批次与算法版本）、并发配额、任意多边形、实时 AIS、按小时统计、等待/锚泊语义、精确越界时刻、MobilityDB 派生层重建。两期比较在两条语句中读取，业务库当前不并发写入。

