# query_encounters 智能体工具（AG-04）

2026-09-21，来源分支 `kimi/ag04-encounters`（基线 `af888e9`），后由 Codex 合入本地 main。只读查询 `encounters` 相遇派生层的既有结果，复用 P4 `/api/encounters` GET 路径的服务与 repository（`backend/app/services/encounters.py`、`backend/app/repositories/encounters.py`），绝不调用 `analyze_encounters` 重建写路径（POST /api/encounters/analyze）。

## 参数（模型侧 JSON Schema）

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| start_at / end_at | string，可选 | ISO 8601，必须带时区（统一 UTC）；成对提供，窗口 ≤24 小时；省略时返回全部已构建船对 |
| max_distance_nm | number，可选 | 按最小距离过滤（海里）；**只能 ≤ 构建阈值**（`params.distance_nm`，默认 3 NM）；省略时按构建阈值不过滤 |
| limit | integer，可选 | 返回条数上限，默认 50，最大 500 |

阈值超过构建参数时抛 `ValueError`（「查询层只能缩小不能扩大覆盖」），由 runner 纠正循环回传模型——**能力不支持不得返回 0 结果**。

## 返回（results.query_encounters）

| 字段 | 含义 |
| --- | --- |
| status | `ok` / `no_data`（构建阈值内零对，有效零结果）/ `not_built` |
| window | 实际使用的窗口；null 表示全部已构建船对 |
| max_distance_nm_filter / requested_max_distance_nm | 实际生效阈值 / 模型请求阈值 |
| encounters | 船对列表：ship_a/ship_b（id、name、mmsi、ship_type）、min_distance_m 与 min_distance_nm（双单位）、overlap_minutes、period_start/period_end、closest_point（GeoJSON）、is_simulated |
| returned_count / matched_count | 实际返回条数 / 过滤后匹配总数（超 limit 时保留真实计数） |
| truncated | 因 limit 或服务层 2000 条上限被截断 |
| params / built_at / stale | 构建参数快照（distance_nm/overlap_min/sample_seconds）、构建时间、stale 时间启发式 |
| limitations | 固定边界说明（见下） |

## 边界与限制（随结果返回，模型不得越过）

- 相遇判定的距离/时长/采样阈值由构建参数快照决定，查询层 `max_distance_nm` 只能缩小不能扩大覆盖。
- `min_distance_m/NM` 为离散采样（采样间隔 `params.sample_seconds` 秒）近似的最小距离，**不是连续时间精确值**。
- 窗口筛选的是与窗口重叠的预计算船对（period 与窗口求交），最小距离不一定发生在所查子窗口之内；不得把整段最小距离说成在所查子窗口内重算的结果。
- 时空接近不等于实际交互；结果为教学模拟数据，不指向真实船舶行为。
- stale 仅为时间启发式；未构建（`not_built`）如实说明，零对是有效零结果。

## 验证

- 离线自动测试 `backend/tests/test_agent_encounters.py` 9 项通过（2026-09-21）：正常结果、省略阈值默认取构建阈值、空结果有效零、未构建、超阈值纠正循环、截断计数保留、模型选择工具、响应契约、全流程无数据库写入（记录型假会话承载真实 SQL，4 条只读 SELECT，写方法即失败）。
- 运行：`python -m pytest backend/tests/test_agent_encounters.py -q`（不连真实库、不需要模型密钥）。
- 真实库只读抽测与真实模型联调未重跑，状态「已实现待验证」。
- 未改动 `backend/app/services/encounters.py` 与 repository 层语义。
- 合并后后端全量 167 项、前端 build/check:workbench 通过；真实库只读抽测与真实模型联调仍未重跑。
