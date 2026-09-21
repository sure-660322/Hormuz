# query_ship_dwell 智能体工具（AG-03）

2026-09-21，来源分支 `kimi/ag03-ship-dwell`（基线 `af888e9`），后由 Codex 合入本地 main。只读查询 `ship_dwell` 停留派生层的既有结果，复用 P3 `/api/dwell` 的服务与 repository（`backend/app/services/dwell.py`、`backend/app/repositories/dwell.py`），不重写停留识别算法、不触发重建或任何写入。

## 参数（模型侧 JSON Schema）

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| kind | string，可选 | `at_anchor` / `drift` / `slow_transit`，省略时返回全部类型 |
| start_at / end_at | string，可选 | ISO 8601，必须带时区（统一 UTC）；成对提供，窗口 ≤24 小时；省略时返回整个已构建批次 |
| limit | integer，可选 | 返回条数上限，默认 50，最大 500 |

参数在适配层 `backend/app/services/agent/dwell_query.py` 二次校验后才下推服务；非法参数抛 `ValueError`，由 runner 纠正循环回传模型（最多 2 次纠正）。

## 返回（results.query_ship_dwell）

| 字段 | 含义 |
| --- | --- |
| status | `ok` / `no_data`（派生层内零段，有效零结果）/ `not_built`（派生层未构建） |
| kind / window | 实际使用的过滤条件；window 为 null 表示全批次 |
| dwells | 停留段列表：ship_id、船名/MMSI/船型、dwell_no、kind、enter_at/leave_at、duration_min、displacement_radius_m、max_speed_kn、point_count、center（派生层中心点经纬度）、is_simulated |
| returned_count / matched_count | 实际返回条数 / 窗口与 kind 过滤后的匹配总数（超 limit 时保留真实计数） |
| truncated | 结果因 limit 或服务层 5000 条上限被截断 |
| params / built_at / stale | 构建参数快照（阈值来源）、构建时间、stale 时间启发式 |
| limitations | 固定边界说明（见下） |

## 边界与限制（随结果返回，模型不得越过）

- 锚泊/漂航/慢速航行阈值由构建参数快照决定（`params.anchor_max_kn` 等），查询层不能调整，不由模型重新定义。
- 结果为派生层预计算快照；`stale` 仅为时间启发式（built_at 早于最新源报位），`stale=false` 不证明历史数据未被修改。
- 教学模拟数据的停留识别结果，不代表真实锚地/漂航认定。
- 未提供时间窗时返回整个已构建批次，而非套用通行工具的默认封锁窗口。
- 派生层未构建（`not_built`）如实说明，不得答成「没有船停留」。

## 验证

- 离线自动测试 `backend/tests/test_agent_dwell.py` 8 项通过（2026-09-21）：正常结果、空结果有效零、未构建、非法 kind 纠正循环、截断计数保留、模型选择工具、响应契约、全流程无数据库写入（记录型假会话承载真实 SQL，3 条只读 SELECT，写方法即失败）。
- 运行：`python -m pytest backend/tests/test_agent_dwell.py -q`（不连真实库、不需要模型密钥）。
- 真实库只读抽测与真实模型联调未重跑，状态「已实现待验证」。
- 未改动 `backend/app/services/dwell.py` 与 repository 层语义。
- 合并后后端全量 167 项、前端 build/check:workbench 通过；真实库只读抽测与真实模型联调仍未重跑。
