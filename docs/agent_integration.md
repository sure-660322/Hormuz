# 智能体接入契约与任务

> 本文保留 **v4 响应契约**；本分支 `codex/lc-safety-fix` 使用 LangChain `create_agent` 编排并保持响应字段兼容，尚未合入 `main`。`main` 的 `f14eceb` 仍是旧 v4 自定义工具循环；下文描述旧循环、九工具注册表及固定分类的段落均为 LC-01 之前的历史契约背景，不代表本分支运行时实现。当前实现与验收见 [开发任务](agent_development_plan.md)，目标架构见 [第一版方案](langchain_agent_v1_plan.md)。

2026-09-23 本分支修复：`main` 的 `f14eceb` 审查记录了 SQL 成功后二次执行、超时响应后后台触库和联调脚本引用旧入口。三项已修复并通过确定性离线测试；每请求统一最多 8 次工具调用（8 个业务工具、知识库、SQL schema/check/execute 共用），模型递归步数上限 40、整体预算 60 秒。SQL 数据库实际执行最多一次；仅首次尚未执行的普通语法错误允许一次修正。预算耗尽返回含稳定错误码与 call_id 的结果；整体超时先设置取消事件并等待线程停止，之后才返回 504 和释放请求 Session。同步业务工具无法强制中断时，504 实际返回可能晚于 60 秒。后端全量 245 passed / 12 skipped、前端 build/check:workbench、`/health`/`/docs`/`/openapi.json` 非浏览器冒烟通过；真实模型、独立 PostgreSQL 和浏览器未验证，代码尚未合入 main。

2026-09-22 LC-04 状态核对：LC-04 已实现待验证——8 个只读业务服务包装为原生 LangChain Tools（复用已验证服务层算法，参数经 Pydantic args_schema 校验，服务层错误降级为 `INVALID_TOOL_ARGS`/`DATABASE_UNAVAILABLE` observation），v4 响应组装迁至 `results.py`（`normalize_status` 增加「已纠正错误豁免」，保持纠正循环顶层状态语义），旧 `runner.py` 及手工 TOOL_REGISTRY/固定短语分类已按计划 §7 移除，固定问句测试由 `test_agent_expressions.py` 多表达矩阵替代。离线回归 231 passed / 12 skipped，前端 build 与 check:workbench 通过。未验证：真实 DeepSeek 问答与工具选择准确率、真实 PG SQL 链路、浏览器端到端（无密钥/无浏览器环境，本轮无法执行）。

2026-09-22 LC-03 状态核对：受限 SQL 工具（`get_database_schema` / `check_sql` / `execute_sql`）已接入，复用 SQL-03/04 策略与独立只读执行器，仅在功能开关完整时向模型暴露；普通筛选/排序/聚合/批准 JOIN 走 schema→check→execute 链路，写入被只读策略拒绝且拒绝后关闭重试。固定短语前置分类已按方案 §7 移除（LC-01/03 完成条件达成），问候、范围外、知识、写库/越权意图和澄清全部交给模型与工具底座处理。LC-02 起已有轻量知识库与 `search_project_knowledge` 工具。统一序列化已修复 `Decimal`（median_gap_minutes）导致的 HTTP 500；工具错误降级为可理解 observation。以下「当前实现」段落中关于自定义工具循环、固定分类与手工 TOOL_REGISTRY 的描述指 LC-01 之前的 v4 实现，旧 `runner.py` 已于 LC-04 清理。

2026-09-22 状态核对（LC-01 之前的事实，保留作契约背景）：data-health、停留、相遇、事件—船舶关联与受限 `query_analytics` 均已注册，注册表共 9 个只读工具；`query_analytics` 功能开关默认关闭，关闭时不向模型暴露，只有本地回环绑定和独立只读配置完整时才可启用。SQL-06 已完成一次性 PostgreSQL 17、真实 DeepSeek 与浏览器综合验收，见 [SQL-06 说明](query_analytics_sql06.md)。

历史核对：2026-09-20 的 v3 多工具版采用“大模型 API + 自定义只读查询工具”，当时未引入 LangChain、LangGraph 或扣子平台。POST /agent/analyze 已注册并通过 schemas_agent.py 与统一错误对外提供；前端智能体面板（frontend/src/components/AgentPanel.vue）已接入问答。该段只说明旧版演进背景，不再代表下一步架构决定。

## 已实现目标与分工

已实现的基础流程：用户问“封锁后有哪些船还通过了海峡？” → 模型提出工具调用 → 后端查询数据库并判定通行 → 返回对应模拟船只、数量和依据。回答内船只/事件的地图定位已实现；历史轨迹逐点回放联动尚未实现。

用户反馈新生成的小规模模拟数据已表现出封锁后停止通过海峡；本次文档修改不重新核验数据库批次或数量，不将其写成已验证的数据库结论。事件面板和智能体均已接入 P2 关联读取，但 observed 演示邻近与 mentioned 文本提及严格分列；通行及关联工具都不得推导真实事件对具体船只的因果影响。

已集成现有 FastAPI：路由位于 backend/app/routers/agent.py，编排、模型适配及查询服务位于 backend/app/services/agent/。本分支通过 `langchain-openai` 的 ChatOpenAI 接入 DeepSeek OpenAI 兼容 API；配置和密钥仅由后端环境提供。

历史 v4 Tool Calling：8 个确定性工具由开发者写 SQL/SQLAlchemy；第 9 个 `query_analytics` 在 catalog v1 内允许模型生成受限 SELECT 和绑定参数，仍必须经过 SQL-03 全树白名单校验与 SQL-04 专用只读执行器。LangChain 分支把它拆成 schema/check/execute 三工具，不提供任意 SQL HTTP 接口，也不回退主应用数据库连接。

| 责任 | 交付 |
| --- | --- |
| 数据与地图成员 | 核对批次与数据库 ID、通行规则、查询工具、参数验证、最小问答入口 |
| 智能体成员 | 模型 API 适配、工具定义、简单调用循环、回答组织和超时处理 |
| 共同 | 固定请求/响应样例、封锁时间语义、通行证据与联调验收 |

## 查询口径

- 封锁时间来自已核验的模拟配置或用户明确输入，返回其来源；不能将报道日期补成精确封锁时刻。当前实现缺省使用已配置的模拟封锁时间与 24 小时窗口，不产生主动澄清状态。
- 查询限定数据库中的明确模拟批次，返回批次标识。生成文件 temp_ship_id 必须经导入映射转换为 ships.id，不得混用；不能用文件验收结果冒充数据库查询。
- “通过”指完整穿越，不以速度大于零、位于海峡内、transit 状态或跨单条线替代。
- 参考 sim_ais_demo/tools/verify_news_alignment.py：在纬度 25.8–27.1 内，从 56.2°E 西侧到 56.7°E 东侧，或反向观测到侧别变化，保留门线之间的状态。该脚本是生成文件验收参考，尚不是数据库工具或通用真实航道判定。
- 数据库版按船排序，保存两侧报位、时间和方向。根据实际采样间隔确定长间隔及异常跳点规则；不充分的候选标为不确定，不能硬算为完整通行。
- 第一版按完成侧首个报位时间属于 [closure_at, end_at) 筛选，封锁前进入、封锁后完成也计入。该时间是观测完成时间，不是精确越线时刻。
- 需要读取窗口前的必要报位或已计算通行状态，不能只截取封锁后的报位；缺少前置状态须报告覆盖不足。
- ship_id 去重计算船只数，通行次数单列。同一船多次穿越不重复计为多艘。
- 足够数据中匹配为 0 是有效结果；无报位或证据不足不能写成“没有船通过”。结论限于所选模拟批次、时间范围和规则。

## 已实现接口与工具

POST /agent/analyze，一次请求返回完整回答。未实现流式输出和多智能体；前端已支持回答内船只/事件地图定位，定位到当前回放快照，不跳转历史轨迹点。

以下日期仅为结构示例，不代表真实封锁时间；联调需替换成核验后的参数：

```json
{
  "question": "封锁后有哪些船还通过了海峡？",
  "closure_at": "2026-03-01T00:00:00Z",
  "end_at": "2026-03-02T00:00:00Z",
  "history": [{"role": "user", "content": "之前的问题"}, {"role": "assistant", "content": "之前的回答"}]
}
```

question 必填，去除首尾空白后 1–2000 字符。时间字段可省略，但须从明确表述或已核验情景上下文补齐；缺失时使用后端默认封锁时刻（当前模拟批次假设的警告响应起点）和 24 小时窗口，不反问用户。时间须带时区，统一 UTC，closure_at < end_at；最多 24 小时，超限报错，不静默截断。不要求选定单船。

history 可选，为此前对话的消息列表（role 限 user/assistant，content 去除首尾空白后 1–2000 字符），最多携带最近 10 条消息（user/assistant 各计一条，通常为 5 组问答）；服务端将 history 插在 system 与本次问题之间。单轮问答不传 history。

以下九工具注册表为 LC-01 前历史实现；本分支保留八个业务工具，新增知识库工具并将 `query_analytics` 拆成 schema/check/execute 三工具。SQL 默认关闭时三工具均不向模型暴露；所有工具只通过 `/agent/analyze` 使用，不单独公开 SQL 路由：

| 工具 | 参数 | 说明 |
| --- | --- | --- |
| query_strait_passages | closure_at, end_at | [closure_at, end_at) 内观测完成的海峡完整通行（门线 56.2°E / 56.7°E 侧别变化口径） |
| search_ships | keyword（必填）, limit | 按关键字模糊检索教学模拟船（船名/MMSI/IMO/callsign/船型/船旗），返回 ship_id 等；limit 默认 10、上限 20 |
| get_ship_track | ship_id（必填）, start_at, end_at | 单船窗口内全部轨迹报位（时间/经纬度/航速/航向）；时间缺省用默认封锁窗口 |
| get_event_context | event_id 或 keyword（二选一）, start_at, end_at | 新闻聚合事件及关联真实报道；事件是真实新闻数据，与模拟船相互独立，不得按船名关联 |
| get_data_health | 无 | 复用 P5 /api/data-health 服务：各 data_source 报位数/船数/覆盖区间/中位间隔 + 四张派生表行数/built_at/params/stale（含未构建标记）；stale 仅为时间启发式，stale=false 不证明历史数据未被修改；来源缺失表示未导入，不得解释为真实数量为零；工具只读，不触发迁移、导入或派生层重建。派生层无源时间基准时 stale 返回 null（不可判定），不报 false |
| query_ship_dwell | kind, start_at/end_at, limit | 只读既有 ship_dwell；kind 限 at_anchor/drift/slow_transit，窗口成对且 ≤24h，缺省为全批次；返回阈值快照、stale、真实匹配数与截断状态，不重建 |
| query_encounters | start_at/end_at, max_distance_nm, limit | 只读既有 encounters；距离过滤只能缩小构建阈值，窗口筛选为与预计算 period 重叠，最小距离是离散采样近似；不调用写入型 analyze |
| query_event_ship_links | event_id 或 ship_id（二选一）, link_type, start_at/end_at | 按事件查 mentioned/observed 或按模拟船反查 observed；mentioned 不映射模拟 ship_id，observed 只表示模拟时空邻近；不重建 |
| query_analytics | sql（必填）, params, purpose（必填） | catalog v1 内单条参数化 SELECT，覆盖筛选、排序、聚合和批准 JOIN；默认关闭，仅本地回环 + 独立 agent_reader 配置完整时暴露，所有输入经 AST/权限/限额强制校验 |

AG-02～05 已合入。SQL-06 后完整后端回归 207 passed / 13 skipped，前端 build 与 check:workbench 通过；一次性 PostgreSQL 17 + 真实 DeepSeek 共 57 项通过，浏览器成功表格、待澄清、已拒绝三状态通过且控制台无错误。共享业务库统计未执行，固定 fixture 数量不能视为当前业务数据。服务侧此前同步修正：来源无任何报位时 stale 由 false 改为 null（缺数据不报「未过期」）。

时间窗语义：请求显式提供 closure_at/end_at 时以请求为准（模型自拟时间参数忽略）；否则用模型在工具参数里给的时间，缺省回退默认封锁时刻 + 24 小时窗口。search_ships 不带时间窗。

```text
接收问题及上下文 → 校验参数并补齐默认时间窗口
→ 模型接收问题、规则与工具说明
→ 模型返回工具名称、参数和调用标识
→ 后端检查白名单并二次校验，执行只读函数
→ 按模型 API 协议回传工具结果
→ 模型组织回答 → 后端从工具结果装配结构化 ID、数量和证据 → 返回页面
```

历史 v4 实现：确定性分类先处理条件不足、写库/泄露意图等；本分支已移除固定分类，由模型选择工具，SQL 安全仍由策略和只读执行器强制。结构化结果以服务端生成的 `call_001`、`call_002` 为键并带 `tool_name`；自由回答仍未逐项事实核验，疑似外部指令文本防回显门继续保留。

本分支当前实现：整体预算 60 秒、统一最多 8 次工具调用、LangChain 递归步数上限 40；没有旧版 4 轮模型请求或 3 次业务工具执行上限。读取上限 50000 个报位，船舶检索上限 20 条，事件查询上限 5 个事件、每事件 10 条报道。读取超限要求缩小范围，不能截断后宣称零匹配；仅展示截断时保留实际总数并标记 truncated。前端超时覆盖后端预算，不沿用新闻查询的 20 秒。

模型密钥和数据库凭据只保留在后端环境，不进入前端、回答或日志。除经过固定解析器、正向白名单、catalog 实物核验和独立只读角色的 `query_analytics` 外，不执行模型生成的 Python/SQL。数据库文本和新闻属于不可信数据，不执行其中指令。遗留 nearby-events 接口和 MobilityDB 固定窗口试验不作为本版通用工具。

## 当前响应与错误

| 字段 | 含义 |
| --- | --- |
| schema_version / request_id | 契约版本（本版为 "4"）和请求标识 |
| status | ok、no_data、partial、needs_clarification、refused（后端/前端均为明确枚举） |
| answer | 根据工具结果回答，并说明模拟边界 |
| context | 实际批次、closure_at、end_at、封锁时间来源、通行规则版本、ship_data_source=simulation；当前 context 时间字段必填，不返回待澄清空值 |
| ships | ship_id、name、passage_count；数据库 ID，按船去重；仅执行过 query_strait_passages 时非空 |
| evidence | evidence_id、ship_id、direction、两侧报位时间及经纬度、observed_completion_at；正文用 [P1] 等引用 |
| query_summary | position_count、matched_ship_count、passage_count、uncertain_candidate_count、coverage_start、coverage_end、truncated；后端计算；未执行通行工具时为 null |
| tools_used | 本次实际执行的工具名列表（执行顺序去重） |
| results | 各工具的结构化结果（按服务端 call_id 键入，值含 call_id/tool_name），供前端展示与追溯；字段由各工具定义 |
| limitations | 覆盖不足、判定限制、数据集边界（模拟/真实新闻相互独立）或截断说明 |
| clarification | 待补充问题；非澄清状态为空 |

- ok：判定完整完成，包括零匹配。零匹配时 ships/evidence 为空，数量为 0，回答限定为“指定模拟数据范围内未发现符合规则的完整通行”。
- no_data：无可用报位或必要前置状态不足，无法判定，不能解释成封锁有效；仅使用 search_ships / get_event_context 等非通行工具且全部无命中时，ships/evidence/query_summary 为空。
- partial：存在已确认结果和数据缺口/不确定候选，仅说明已确认部分。
- needs_clarification：确定性分类确认对象/指标均不足时不调用模型和工具，results 为空；缺通行情景时间仍按既有规则使用默认窗口，不主动追问。
- refused：调用前识别出的明确写库/越权/泄露意图，或 query_analytics 的安全策略拒绝；HTTP 200，不当作系统故障，不自动重试。

模型完全不可用时返回错误，不用硬编码样例冒充成功。验收样例须使用实际数据库 ID，区分成功、零匹配和无数据，不编造数量；历史验收记录见下文。

错误体为 detail 对象，含 code、message、request_id：

| HTTP | code | 情况 |
| --- | --- | --- |
| 422 | INVALID_REQUEST | 参数、时区、窗口或读取限额不合法 |
| 503 | AGENT_UNAVAILABLE | 模型未配置或不可用 |
| 503 | AGENT_QUERY_UNAVAILABLE | query_analytics catalog、专用只读角色、权限或独立连接配置不可用 |
| 503 | DATA_CONTEXT_UNAVAILABLE | 预留错误码；当前路由未实现独立映射，不得作为已验证分支 |
| 504 | AGENT_TIMEOUT | 模型或整体执行超时 |
| 504 | AGENT_QUERY_TIMEOUT | query_analytics 是唯一能力且达到数据库执行超时 |
| 500 | DATA_QUERY_FAILED | 查询失败，不泄露连接信息 |
| 502 | AGENT_INVALID_RESPONSE | 调用或回答反复不符合契约 |

## 实施与验收

下列勾选项保留既有阶段实施/验收记录，不表示本轮重跑全部用例；正文事实校验以本页「当前实现」说明为准。scripts/check_agent_api.py 对默认批次写死一艘船的预期，重跑前需核对 fixture/批次；模型主动澄清当前未实现，无密钥 503 路径在该脚本中仍为 SKIP。

- [x] 核对数据库批次、ID 映射、覆盖和封锁时间来源，确定异常间隔阈值及通行规则。
- [x] 独立实现并验证查询函数，对照人工样例与文件验收脚本，解释差异。
- [x] 命令行跑通一次模型 API、工具调用及结果回传，保留无密钥的参数和结果摘要。
- [x] 实现 schemas、注册 /agent/analyze、统一错误并为 CORS 增加 POST。
- [x] 最小页面展示输入、加载、回答、船只和证据，同步前端类型与超时；v3 起支持多轮对话渲染与回答内船只/事件的地图定位。
- [x] 验证封锁前进入/后完成、起止边界、单门线折返、多次通行、乱序报位、跳点、长间隔、无报位、零匹配、缺参数、未知工具和超时。
- [x] 新批次若为零通行则如实展示，用封锁前窗口或独立测试数据验证正例，不改源数据制造演示结果。
- [x] 核对查询前后源数据未变、回答 ID/数量/证据与工具结果一致，不推导真实因果。
- [x] 验证 /health、/docs 和新接口；改前端后运行 npm run build，涉及工作台语义运行 npm run check:workbench，并检查网络请求与后端日志。
- [x] v3：新增 search_ships / get_ship_track / get_event_context 三个只读工具，参数校验、命中上限与数据集边界声明（模拟船与真实新闻不关联）随工具返回。
- [x] v3：runner 改为工具注册表多工具循环（预算 3 次工具执行），请求显式时间窗为权威值，缺省回退默认封锁窗口。
- [x] v3：请求支持 history（≤10 条消息，user/assistant 各计一条），多轮追问仍强制重新调用工具核对，不得仅凭历史回答。
- [x] 历史 v3：响应新增 tools_used 与 results（当时按工具名键入）；v4 已改为服务端 call_id，通行结果仍填充 ships/evidence/query_summary 顶层字段。
- [x] AG-02～05：注册 get_data_health / query_ship_dwell / query_encounters / query_event_ship_links，保留派生层阈值、stale、截断、模拟边界和只读约束；合并后离线回归及前端构建通过。
- [x] v4 / SQL-05：注册 query_analytics，但默认关闭时不向模型暴露；接入 SQL-03/04 唯一安全执行链、服务端 call_id、状态枚举、一次语法修复、拒绝/超时/不可用映射和最小表格展示。
- [x] v4 / SQL-05：一次性 PostgreSQL 17 完成 SQL-04+05 22 项端到端验证；后端全量 177 passed / 8 skipped，前端 build/check:workbench 通过。未调用真实模型或共享数据库。
- [x] v3：scripts/test_deepseek_toolcall.py 三场景（通行回归 / search+track 链式 / 事件查询）真实联调通过；scripts/check_agent_api.py 覆盖 history 校验并通过。

## 后续范围

回答中的船/事件地图定位已实现；历史轨迹逐点回放联动与服务端会话持久化尚未实现；更细粒度的事件与模拟船交互建模仍需设计。旧版 get_ship_context、find_news_events、get_event_evidence 保留为参考，不是本版必做项；新闻扩展仍须区分报道日期与事件时间，保留来源标识，不按船名自动匹配真实与模拟船。

历史 SQL-01～06 已完成并在旧 v4 循环注册默认关闭的 `query_analytics`。SQL-06 曾验证真实 DeepSeek 工具 schema、固定 fixture 人工 SQL 对照和浏览器交互，不能视为本分支已重验。本分支已用 LangChain 单智能体复用 SQL 底座，SQL 三工具默认关闭；第一版不直接编写 LangGraph，复杂恢复或持久化需求出现后再评估。

最小版（v2）已实现并联调：后端 /agent/analyze 与前端智能体面板已跑通默认问题（返回 1 艘 SIM V2 化学品船 019，证据 P1，观测完成于 2026-02-28T18:14:54Z）；npm run build 与 npm run check:workbench 已通过。v3 多工具版历史联调记录（原标注日期晚于本次文档核对日，实际验收日期待核对；以下不代表本次重新验证）：通行回归问题 1 次工具调用 4.1s；「油轮 SIM V2 油轮 004 轨迹」问题链式调用 search_ships + get_ship_track 共 2 次 5.7s；「evt_001 事件与报道」1 次 get_event_context 3.1s，回答均保留来源链接与模拟边界声明。环境交接见 [database_setup.md](database_setup.md)。
