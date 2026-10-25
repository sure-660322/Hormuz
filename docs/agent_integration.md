# 智能体接入契约

当前实现为 LangChain create_agent，HTTP 响应保持 v4。使用地图工具栏“智能体”右侧停靠面板；通行/区域 analysis_actions 打开对应面板并恢复工具当次条件。[架构](langchain_agent_v1_plan.md)和[当前验证状态](agent_development_plan.md)分别维护实现与限制，不在此重复交付流水。

## 查询口径

- `POST /agent/analyze` 请求含 question（去空白后 1–2000 字符）、可选 closure_at/end_at、history、map_context 和 area_context。
- 时间须带时区；history 最多十条，每条 1–2000 字符，角色仅 user/assistant。map_context 包含 playback_at 与可选 target_ship_id；area_context 提供完整矩形。
- 显式请求窗口优先，缺省时由工具参数或默认窗口解析；默认封锁时刻是查询假设，不是已核实事件发生时刻。通行窗口与前置观测规则见[通行说明](agent_tool_strait_statistics.md)。
- 无区域上下文时使用版本化默认区域；当前区域、地图视野和新闻地理位置不能互相替代。区域参数、半开边界和覆盖见[区域契约](area_activity.md)。
- 报道日期、事件日期及船位时间不同；报道提船名不等于完成 AIS 实体鉴定，空间邻近不能推导因果。

## 已实现接口与工具

业务注册项：search_ships、get_ship_track、query_strait_passages、get_event_context、get_data_health、query_ship_dwell、query_encounters、query_event_ship_links，以及两个[通行统计工具](agent_tool_strait_statistics.md)和三个[区域工具](area_agent_tools.md)。旧派生停留、相遇和 observed 已退出建设范围；空表/not_built 不能称为有业务结果。mentioned 证据保留。

知识库工具 search_project_knowledge 读取四个运行时主题。内部 SQL 为 get_database_schema / check_sql / execute_sql，受[安全契约](query_analytics_contract.md)约束，不能执行任意 SQL 或回退到主应用账号。应用库未实施 catalog v3 的 017 快照；外部 MCP 固定七业务工具、不开放 SQL。

单船轨迹读取最多 50,000 报位；模型 observation 仅接收身份、查询/覆盖窗口、数量与首末报位摘要，JSON UTF-8 上限 8,192 字节。完整轨迹仍在服务端 results，地图按 ID/窗口加载；摘要首末点不能代替精确轨迹。

整体预算 60 秒、统一最多八次工具调用、LangChain 递归步数 40；SQL 最多一次实际执行，仅首次尚未执行的普通语法错误允许一次修正。超时取消后等待线程退出，再释放 Session。模型密钥、原始工具资料及数据库异常不进入日志；用量记录缺失为 null，不把模型调用数当供应商 HTTP 重试次数。

## 当前响应与错误

| 字段 | 含义 |
| --- | --- |
| schema_version / request_id | 契约版本（本版为 "4"）和请求标识 |
| status | ok、no_data、partial、needs_clarification、refused（响应枚举保留；当前编排不会主动生成 needs_clarification） |
| answer | 根据工具结果回答，并说明历史 AIS 覆盖、门线及新闻实体边界 |
| context | 历史 AIS 来源、closure_at、end_at、默认起点来源、通行规则、ship_data_source=nnu_ais；context 时间字段必填 |
| ships | ship_id、name、passage_count；数据库 ID，按船去重；仅执行过 query_strait_passages 时非空 |
| evidence | evidence_id、ship_id、direction、两侧报位时间及经纬度、observed_completion_at；正文用 [P1] 等引用 |
| query_summary | position_count 为查询窗及前置 24 小时内、空间范围内的门线侧别报位数；另有 matched_ship_count、passage_count、uncertain_candidate_count、coverage_start、coverage_end、truncated；未执行通行工具时为 null |
| tools_used | 本次实际执行的工具名列表（执行顺序去重） |
| results | 各工具的结构化结果（按服务端 call_id 键入，值含 call_id/tool_name），供前端展示与追溯；字段由各工具定义 |
| limitations | 覆盖不足、判定限制、AIS 与新闻实体边界或超限说明 |
| clarification | 待补充问题；非澄清状态为空 |

- ok：工具结果均为成功，或模型未调用工具而直接回答。通行工具零匹配时 ships/evidence 为空，只能说“该窗口内未观测到符合虚拟门线规则的通行”，不能说船一定没通过。
- no_data：工具均未取得成功或部分结果时的顶层状态；无可用报位或必要前置状态不足不能解释成封锁有效。非通行工具的空结果不会生成通行证据。
- partial：工具成功结果与错误/数据缺口并存，或工具返回部分结果；仅说明已确认部分。
- needs_clarification：保留在 v4 响应枚举中，当前 LangChain 编排不主动生成此状态；模型可在 answer 中自然追问，此时若没有工具结果，顶层状态为 ok、clarification 为 null。缺通行情景时间使用默认窗口。
- refused：工具返回结构化 refused observation 时，顶层状态为 refused、HTTP 200，不自动重试。当前没有调用前的固定意图分类；模型直接用文字拒绝且未调用工具时，顶层状态为 ok。

模型完全不可用时返回错误，不用硬编码样例冒充成功。验收样例须使用实际数据库 ID，区分成功、零匹配和无数据，不编造数量；历史验收记录见仓库外归档。

错误体为 detail 对象，含 code、message、request_id：

| HTTP | code | 情况 |
| --- | --- | --- |
| 422 | INVALID_REQUEST | 参数、时区、窗口或读取限额不合法 |
| 503 | AGENT_UNAVAILABLE | 模型未配置或不可用 |
| 503 | AGENT_QUERY_UNAVAILABLE | 仅当 QueryExecutionError 传播到路由时；当前 SQL 工具通常将 catalog、专用只读角色、权限或独立连接错误收进结构化 results |
| 503 | DATA_CONTEXT_UNAVAILABLE | 预留错误码；当前路由未实现独立映射，不得作为已验证分支 |
| 504 | AGENT_TIMEOUT | 模型或整体执行超时 |
| 504 | AGENT_QUERY_TIMEOUT | 仅当 QueryExecutionError 传播到路由时；当前 SQL 工具通常将数据库执行超时收进结构化 results，整体超时仍为 AGENT_TIMEOUT |
| 500 | DATA_QUERY_FAILED | 查询失败，不泄露连接信息 |
| 502 | AGENT_INVALID_RESPONSE | 调用或回答反复不符合契约 |


## 地图与分析动作

`map_actions` 支持 ship_track、ship_position、event，含 automatic/suggested 触发方式、船舶/事件 ID、有界窗口、source、window_source，位置动作可带 recorded_at。明确地图指令可结合 map_context 解析有界时间；前端校验真实选船、轨迹与视野后反馈完成，可取消。事件未到回放日期或缺坐标时不定位。

`analysis_actions` 支持 passage_analysis 与 area_activity，来自成功工具结果并绑定该次参数；区域动作另带 mode/tool/call_id。前端不得用当前条件覆盖历史结果。详细字段以 `backend/app/schemas_agent.py` 与 `frontend/src/api.ts` 为准。

`get_event_context` 同时查询 news.event_id 主关联与 events.story_ids 引用，共享报道去重；不由新闻关联生成 observed 因果证据。四新闻入口是[人工审核案例](case_news_entries.md)，不等于模型可自动识别任意文章。

## 验证与限制

通行/区域/综合多轮有历史真实模型样本；内部 SQL 浏览器链路、全场景事实核验、持续负载与公网部署未全面验证。DSH 桌面后续样本由用户确认，不冒充独立逐字段对账。原验收全文已移至[历史材料](README.md#历史材料)，本轮不重跑业务测试。
