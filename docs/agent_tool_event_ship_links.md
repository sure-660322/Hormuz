# query_event_ship_links 智能体工具（AG-05）

2026-09-21，分支 `kimi/ag05-event-ship-links`，基线 `af888e9`。只读查询 `event_ship_links` 派生层既有结果，复用 P2 事件—船舶关联服务（`backend/app/services/event_links.py` 的 `get_event_ships` / `get_ship_events`）与 repository，不触发重建。语义草拟由 Kimi 完成（本分支），整合时由 Codex 核对。

## 参数（模型侧 JSON Schema）

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| event_id | string | 事件 ID（如 evt_001），与 ship_id **二选一** |
| ship_id | integer | 模拟船 ID（ships.id，先用 search_ships 确认），与 event_id **二选一** |
| link_type | string，可选 | `observed` / `mentioned`，省略默认 `observed`；**mentioned 仅支持 event_id 方向**（不指向模拟船，不参与反向） |
| start_at / end_at | string，可选 | 仅 ship_id 反查方向可用：成对、带时区、≤24 小时；省略时按整个已构建批次反查 |

## 两个方向与两类关联（严格分列）

- **by_event**（event_id）：返回该事件下的关联列表，按 link_type 过滤。`mentioned` 为新闻原文提及的真实船名（文本证据，`ship_id` 恒为空，与数据库中模拟船不按名称关联，未认定同一实体）；`observed` 为模拟船（含 ship_id、mmsi、置信度、最小距离、时间窗证据），仅表示模拟轨迹在事件时间窗内进入构建半径。
- **by_ship**（ship_id）：observed 反查，返回事件列表（event_id、标题、事件时间叙述、代表坐标、置信度、距离）。mentioned 类不指向模拟船，不参与反向。

## 返回（results.query_event_ship_links）

| 字段 | 含义 |
| --- | --- |
| status | `ok` / `no_data`（派生层内无此类关联，有效零结果） |
| direction | `by_event` / `by_ship` |
| links / events | 按方向返回关联列表或事件列表（结构见前端 `AgentToolEventShipLinksResult`） |
| returned_count | 返回条数 |
| built_at / params | 构建时间与构建参数快照（radius_km、half_window_hours、srid 等） |
| limitations | 固定边界说明（见下） |

## 边界与限制（随结果返回，模型不得越过）

- mentioned 是原文船名文本证据，`ship_id` 恒为空；真实船名与模拟船不按名称关联为同一实体。
- observed 是模拟数据时空邻近演示，不构成真实因果；零条仅表示派生层内无此类关联（受事件坐标/时间覆盖与关联构建限制）。
- **关联距离为构建时 EPSG:32640 平面投影近似（跨 UTM 带存在失真），不是精确地理度量**；现有 32640 关联距离不得标成已修复的 geography 度量。
- 事件时间精度：event_datetime 缺失时按 event_time_text / 报道日期叙述，不虚构精确发生时刻。
- 未知 event_id / ship_id 是纠正分支（提示先用 get_event_context / search_ships 检索），**不得当成零结果**。

## 验证

- 离线自动测试 `backend/tests/test_agent_event_ship_links.py` 10 项通过（2026-09-21）：正查 observed、正查 mentioned、反查 by_ship（含窗口下推）、未知 event_id 纠正、未知 ship_id 纠正、空结果有效零、非法参数七例、模型选择工具、响应契约、全流程无数据库写入（记录型假会话承载真实 SQL，3 条只读 SELECT，写方法即失败）。
- 运行：`python -m pytest backend/tests/test_agent_event_ship_links.py -q`（不连真实库、不需要模型密钥）。
- 真实库只读抽测与真实模型联调未重跑，状态「已实现待验证」。
- 未改动 `backend/app/services/event_links.py` 与 repository 层语义。
