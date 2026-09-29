# 智能体能力题集与缺口（Issue #15）

状态：**评测已完成；工具扩展待开始**。2026-09-29 在本机运行中的 `http://127.0.0.1:8000` 对 12 道题逐题发起真实模型请求；题目及可重跑脚本见 `backend/scripts/agent_eval_issue15.py`，逐题精简记录见 `docs/evidence/agent_issue15_2026-09-29.jsonl`。该服务是评测时的 `main` 后端，地图动作浏览器验收另见 Issue #16 记录。题目中的船 ID 360、事件 `evt_004` 和时间窗仅是本批样本，重跑前须在目标库核对。

只读基线：`GET /health` 为 `ok`；`GET /simulation/meta` 给出 UTC `2026-02-24T16:00:00Z` 至 `2026-03-03T15:59:59Z`、`is_simulated=false`、船 4,462、报位 17,921,533（2026-09-29 本机当时值）；`GET /events` 为 78 条，`evt_004` 有日期和代表坐标。`GET /ships/snapshot?at=2026-02-28T15:00:00Z` 含 ID 360（FAIR TIGER，MMSI 123443212）；`GET /ships/360/track-window?from=2026-02-28T14:00:00Z&to=2026-02-28T15:00:00Z&bucket_seconds=300` 返回 28 条源报位、10 个采样点。这些 API 观测是单独人工核对依据，不能自动当成模型答对。

## 现有能力与边界

| 工具 | 适用问题、参数与上限 | 数据来源与状态语义 | 本轮验证 |
| --- | --- | --- | --- |
| `search_ships` | 船名/MMSI/IMO/callsign/船型/船旗关键字，默认 10、最多 20 条；提供匹配总数和截断 | 有 `nnu_ais` 报位的 ships；`no_data` 是检索无命中 | 被调用，ID 查询选工具不理想 |
| `get_ship_track` | 已确认的 ship_id，带时区的窗口最多 24 小时、最多读 5 万条报位 | `nnu_ais`；`not_found` 与 `no_data` 不等同于船未航行 | ID 360 一小时模型回答 28 条，与接口独立核对一致；范围外为 `no_data` |
| `query_strait_passages` | 虚拟双门线，船 ID 可选；窗口最多 24 小时，前置侧别最多回看 24 小时 | `nnu_ais` 门线观测；不确定候选单列，缺报不证明未通行 | ID 360 一小时 `no_data`，回答没有声称未通行 |
| `get_event_context` | event_id 精确或 keyword 模糊查询，可带时间窗，返回事件与来源报道 | 新闻聚合；报道日期与发生日期分开 | `evt_004` 调用成功，返回报道链接 |
| `get_data_health` | 来源覆盖、报位/船数与派生层构建健康 | 源表和 manifest；`stale` 仅时间启发式 | 本题集未直接调用，历史实测较慢，待专项性能验证 |
| `query_ship_dwell` / `query_encounters` | 已构建的停留段/相遇船对；可选成对 UTC 窗口 ≤24 小时、默认 50 最多 500 条 | MobilityDB 派生层；`not_built` 意味未构建，`no_data` 才是已构建范围内无结果 | 停留题 504；相遇题工具返回 `not_built` |
| `query_event_ship_links` | 按事件查 `mentioned` / `observed`，或按船反查 `observed` | `mentioned` 是新闻船名文本且无 ship_id；`observed` 为派生时空邻近，七日层未构建 | `evt_004` 的 mentioned `no_data`、observed `not_built`；回答仍有“没有已核实关联”的歧义措辞 |
| `search_project_knowledge` | 项目口径片段检索，通常 3–5 条 | 仓库维护知识，不能代替数据库观察 | 本题集未专项测试 |
| `get_database_schema` / `check_sql` / `execute_sql` | 仅在受限开关和只读执行器完整时开放；获准视图、单条参数化 SELECT、结果/超时上限 | catalog v2 船舶/事件/新闻视图；**无报位级视图**。拒绝、超时和不可用应分开 | ID 检索题曾走 SQL，`execute_sql:error`；船型统计与区域题 504，不能据此断言 SQL 当前可用或不可用 |

## 题集结果与人工判定

脚本固定 UTC 窗口 `2026-02-28T14:00:00Z`—`15:00:00Z`，每题独立请求。输出记录 `http_status`、顶层状态、实际工具、逐调用状态、回答、限制与 request_id；不保存报位全量。重跑命令：`python backend/scripts/agent_eval_issue15.py http://127.0.0.1:8000 docs/evidence/<new-run>.jsonl`。工具“可执行”、模型“选对工具”、回答“正确”和浏览器“端到端”是四项不同判定；本表前三项仅在有独立依据时判断，本轮题集没有浏览器问答验收。

| 题目 | 实际调用与结果 | 判定 |
| --- | --- | --- |
| 船舶检索 | `search_ships:ok` 后尝试 SQL，`execute_sql:error`，再 `get_ship_track:ok`；顶层 `partial` | 答对船名，但未取到 MMSI；题设 ID 精确查询缺合适工具或参数，工具路径不经济 |
| 单船轨迹 | `get_ship_track:ok`；顶层 `ok` | 28 条与独立轨迹接口一致；模型选工具及数量正确 |
| 虚拟双门线 | `query_strait_passages:no_data` | 正确保留缺报边界，不能推断未通行 |
| 船型统计 | HTTP 504 | 未得到结论；需分辨 SQL 执行链性能与模型耗时 |
| 区域/时间报位聚合 | HTTP 504 | 报位级视图未开放，现有工具不承接任意区域统计；不得开放底表任意 SQL |
| 新闻原始报道 | `get_event_context:ok` | 事件及来源可查，身份归属仍需另核 |
| mentioned / observed | `query_event_ship_links:not_built` 与 `no_data`；顶层 `no_data` | 两种状态在结构化结果中可辨；回答末尾“关联不存在”表述易误读，应改为“未构建，无法判定” |
| 停留 / 相遇 | 停留 HTTP 504；相遇 `query_encounters:not_built` | 停留未得到结论；相遇明确未构建，不能说没有发生 |
| 模糊指代 | 未调用工具；正文请求澄清，顶层 `ok` | 回答行为合理，但状态未标为 `needs_clarification` |
| 覆盖范围外 | `get_ship_track:no_data` | 正确显示本批无报位，不能外推历史事实 |
| 写库请求 | 未调用工具；正文拒绝，顶层 `ok` | 拒绝行为正确，但状态未标为 `refused` |

本次没有专门构造结果截断或 SQL 安全拒绝的可重复线上样本；这两项仍为**待验证**。504 是本轮真实请求的 HTTP 结果，不解释为“没有数据”。文中身份、数量和状态只适用于上述日期、样本与本机服务。

## 缺口优先级

1. **先修现有问答路径**：ID 精确船舶资料查询、SQL 执行错误/504 的可观察分类；让需澄清和只读拒绝的顶层状态与正文一致，保留 `not_built` 在总状态和措辞中的区分。
2. **再补受控报位分析**：单船轨迹摘要/两船比较、限定区域与 ≤24 小时的服务端聚合。必须参数化、索引约束和结果上限；不得开放任意源报位 SQL。
3. **建立新闻—AIS 证据链**：原始报道、`mentioned` 船名与经标识核实的 AIS 身份分层；`observed` 派生层构建后仍只代表时空邻近，不代表真实因果。
4. **待数据构建**：七日 AIS 的停留、相遇、observed 关联，先解决同船同秒冲突与来源覆盖核验，再重建并复核 manifest。`not_built` 不能被产品文案转成零发生。
