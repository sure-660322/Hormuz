> 2026-10-07 Issue #40（分支 `kimi/strait-passage-stats`，待合入）：v4 响应新增 `analysis_actions`（当前仅 `passage_analysis`），由成功的 `query_strait_passage_statistics` / `compare_strait_passage_statistics` 工具结果生成并绑定该次调用自己的查询参数；前端据此在总览打开「通行分析」面板并恢复条件与结果。业务工具由 8 个增至 10 个（新增两工具与手动面板 `/api/strait-passages/*` 共用同一统计服务，同条件结果一致；船型过滤含 `__unknown__` 未知/缺失桶，A/B 比较变化率 A=0 为 null）。手动 API 为 GET/POST，CORS 既有白名单与 Vite 代理已覆盖；`query_strait_passages` 单船能力不变。口径、性能预算与验证见[通行统计模块说明](agent_tool_strait_statistics.md)；真实模型问答与浏览器端到端待验收。

> 2026-09-30 Issue #24（PR #25 已合入 main，合并提交 af41d37）：`get_ship_track` 的模型 observation 改为 `track_summary`，无完整 `fixes` 数组，只含身份、UTC 查询/覆盖窗口、报位数、首末报位及限制。JSON UTF-8 上限 8192 字节，字符串字段最多 80 字符，原限制最多保留 8 条并给出省略计数；首末报位不是采样轨迹，不能用于精确通行/停留推断。完整 envelope 继续保存在服务端 state 和 v4 `results`，地图动作仍从完整证据生成，前端按 ID/窗口读取轨迹，HTTP 契约不变。后端 `uvicorn.error.agent_usage` 在 INFO 记录 `agent_model_usage`（每次调用）与 `agent_request_usage`（整次问答）；缺失 token/cache 数值为 null、usage_status 为 unavailable，缓存缺失不单独影响输入/输出完整性。model_calls 是 LangChain 模型调用数；SDK 内部网络重试次数不可见，network_attempts 为 null，不能当作供应商 HTTP 请求次数。无价格估算；日志不含提示词、工具原始数据、错误正文或密钥。验证范围见[开发任务](agent_development_plan.md#issue-24-轨迹模型上下文优化2026-09-30)。

# 智能体接入契约与任务

> 当前增量（2026-09-30 Issue #20，PR #22 已合入 main，用户测试通过）：v4 增加可选请求 `map_context={playback_at:带时区时间,target_ship_id:正整数或null}`，动作支持 `ship_position`；ship_position/ship_track 追加 `window_source`，位置动作另有 `recorded_at`。明确自然语言显示指令可使用回放附近的有界默认窗口，无需填写 UTC 双端点；前端保持聊天面板、核验高亮/轨迹与可见视野后反馈完成，可取消。接口字段、时间优先级、边界与当前验收见[地图联动记录](agent_map_actions_issue20.md)。下方 #16 描述为 PR #19 已合入 main 的历史实现，不代表 #20 当前窗口限制。

> 2026-09-29 Issue #16 分支 `codex/issue-13-map-agent`：v4 响应新增可选 `map_actions` 列表（旧字段保留）。`ship_track` 含 `ship_id`、`start_at`、`end_at`、`source=nnu_ais`；`event` 含 `event_id`、`source=news`；`trigger` 为 `automatic` 或 `suggested`。服务端只从单一成功且有报位、≤24 小时的 `get_ship_track` 结果产生轨迹动作；必须有用户明确 UTC 双端点（或请求明确窗口），并且有显示意图才自动执行，没有显示意图时给按钮；时间不明确或多目标不生成动作，需继续澄清。仅从唯一有日期和代表点的成功 `get_event_context` 结果建议事件动作。前端校验覆盖/身份/时窗并请求有界轨迹、目标回放帧，失败提示原因；成功加载、选中和开图层之后才提示完成。事件继续使用原有时间门控和坐标规则。聊天面板保持挂载，可从船/事件详情返回对话。2026-09-29 本分支后端动作测试 3 passed、前端 build/check:workbench 通过；8001 真实模型与 5176 浏览器只验收 ID 360 的一小时自动轨迹样本，其他失败分支和事件建议的浏览器端到端待验收。#15 能力评测见[12 题报告](agent_capability_eval_issue15.md)。下文 2026-09-26 的“真实模型浏览器未验收”是当时版本的历史状态。

> 2026-09-26 前端分支 `codex/agent-chat-ui-main` 已快进合入本地 `main`（实现提交 `1d1ae41`）：`AgentPanel.vue` 已按现有 v4 非流式响应实现聊天消息流、Enter/Shift+Enter、Markdown 消毒渲染、等待计时和可折叠 `results` 工具过程；后端接口、schema 与路由未变。前端构建、工作台检查及浏览器模拟响应通过，本地 5174 页面已验证智能体面板可打开；真实模型浏览器问答和 SSE 流式输出未验证/未实现，不能把展开的工具结果称为模型思考链。任务记录见[开发计划](agent_development_plan.md)。

> 2026-09-25 真实 AIS 适配（`208f39d`、`7f1b89a` 已合入本地 main）：船舶搜索、单船轨迹、来源说明和项目知识已改为 `nnu_ais`；通行工具沿用现有 56.2°E / 56.7°E 虚拟双门线，但限定纬度 25.8–27.1°N、经度 55.8–57.1°E 和最多 24 小时查询窗 + 24 小时前置观察。数据库只向应用返回聚合与侧别变化，最多扫描 100 万门线侧别报位、最多返回 5000 个变化候选，超限报错；可选 ship_id。中间报位离开判定区域、6 小时长间隔或 30 kn 跳点列为不确定候选，不计入确定通行。阈值尚未用真实 AIS 独立校准，未观测到不等于未通过。当前应用库只读验证和未验证项见[开发任务](agent_development_plan.md)。下文标有“模拟批次”的实施与验收数字均属历史记录，不代表当前 AIS 口径。

2026-09-25 起 SQL 三工具经 catalog v2 重新向真实 AIS 主链开放（本机已启用）：`016_agent_views_nnu_ais.sql` 重建 `agent_data` 语义视图（`v_ships` 一船一行、仅含 ≥1 条 `nnu_ais` 报位的船；`v_events`/`v_news` 定义与 v1 逐字一致）与 `agent_view_owner`/`agent_reader`/`agent_reader_login` 只读角色；`query_analytics_catalog_v2.json` 记录视图哈希（按 `search_path=pg_catalog` 口径计算）与 `data_source_scope: nnu_ais`。`sql_tools_enabled()` 要求 catalog 口径与 `SHIP_DATA_SOURCE` 一致且执行器配置完整（fail-closed）。含 TimescaleDB 的集群须为读者角色设 `timescaledb.disable_load=on`（016 已内置），否则聚合查询报 `_timescaledb_functions` 权限错误。原始报位不在 catalog 内（5 秒语句超时下大范围聚合不可行），报位级分析走业务工具。历史 v1 catalog 与 013 保留为旧批次资料，不得重放。

2026-09-25 工具查验：八个业务工具在本机 `aisdb` 均可调用；`search_ships`、`get_ship_track`、`query_strait_passages`、`get_event_context`、`get_data_health`、`query_event_ship_links(mentioned)` 返回现有数据，`query_ship_dwell` 与 `query_encounters` 返回 `not_built`。`query_event_ship_links(observed)` 已改为无构建记录时返回 `not_built`，不再把未构建说成 `no_data`。完整证据与时间见[开发任务](agent_development_plan.md)。这只是确定性工具核对，真实模型表述与浏览器问答仍待验证。

2026-09-25 SQL 三工具真实 AIS 适配验收：本机 `aisdb` 已执行 016 并启用 `AGENT_QUERY_ENABLED`；执行器全链路通过（catalog 角色/权限/视图哈希核验，油轮计数 793、按船型分布 25 行、报道 290，写入被只读策略拒绝）；真实 DeepSeek 对「一共多少艘油轮」自主完成 schema→check→execute 并回答 793 艘（含 NULL/未知船型不计入的口径说明），catalog limitations 正确流入响应。离线回归 257 passed / 12 skipped。未验证：浏览器端到端、远端推送。详见[开发任务](agent_development_plan.md)。

> 本文保留 **v4 响应契约**；本地 `main` 已合入 LangChain `create_agent` 编排及 `codex/lc-safety-fix` 安全修复，响应字段兼容。`f14eceb` 是合并前的旧 v4 自定义工具循环复核提交；下文描述旧循环、九工具注册表及固定分类的段落均为 LC-01 之前的历史契约背景，不代表当前运行实现。当前验收见 [开发任务](agent_development_plan.md)，架构见 [第一版方案](langchain_agent_v1_plan.md)。

前端入口更新（2026-09-23）：地图探索页工具栏的「智能体」按钮在右侧详情浮层打开 `AgentPanel.vue`；前端布局与本轮浏览器验证见 [前端工作台](../FRONTEND_WORKBENCH.md)。本次仅改入口布局，未重新验收真实模型链路。

2026-09-24 前端定位规则修正已合入本地 `main`：智能体引用的新闻事件仅在其 `event_datetime` 不晚于当前回放帧且有代表坐标时可在地图定位；未到时间、缺发生时间或缺坐标时提示，不提前显示新闻点。仅前端交互变更，真实模型链路未重新验收。

2026-09-23 整合记录：`f14eceb` 审查记录了 SQL 成功后二次执行、超时响应后后台触库和联调脚本引用旧入口。三项已修复并整合到本地 `main`；每请求统一最多 8 次工具调用（8 个业务工具、知识库、SQL schema/check/execute 共用），模型递归步数上限 40、整体预算 60 秒。SQL 数据库实际执行最多一次；仅首次尚未执行的普通语法错误允许一次修正。预算耗尽返回含稳定错误码与 call_id 的结果；整体超时先设置取消事件并等待线程停止，之后才返回 504 和释放请求 Session。同步业务工具无法强制中断时，504 实际返回可能晚于 60 秒。修复分支离线后端全量 245 passed / 12 skipped、前端 build/check:workbench、`/health`/`/docs`/`/openapi.json` 非浏览器冒烟通过；真实模型、独立 PostgreSQL 和浏览器本版仍待验收，远端未推送。

2026-09-22 LC-04 状态核对：LC-04 已实现待验证——8 个只读业务服务包装为原生 LangChain Tools（复用已验证服务层算法，参数经 Pydantic args_schema 校验，服务层错误降级为 `INVALID_TOOL_ARGS`/`DATABASE_UNAVAILABLE` observation），v4 响应组装迁至 `results.py`（`normalize_status` 增加「已纠正错误豁免」，保持纠正循环顶层状态语义），旧 `runner.py` 及手工 TOOL_REGISTRY/固定短语分类已按计划 §7 移除，固定问句测试由 `test_agent_expressions.py` 多表达矩阵替代。离线回归 231 passed / 12 skipped，前端 build 与 check:workbench 通过。未验证：真实 DeepSeek 问答与工具选择准确率、真实 PG SQL 链路、浏览器端到端（无密钥/无浏览器环境，本轮无法执行）。

2026-09-22 LC-03 状态核对：受限 SQL 工具（`get_database_schema` / `check_sql` / `execute_sql`）已接入，复用 SQL-03/04 策略与独立只读执行器，仅在功能开关完整时向模型暴露；普通筛选/排序/聚合/批准 JOIN 走 schema→check→execute 链路，写入被只读策略拒绝且拒绝后关闭重试。固定短语前置分类已按方案 §7 移除（LC-01/03 完成条件达成），问候、范围外、知识、写库/越权意图和澄清全部交给模型与工具底座处理。LC-02 起已有轻量知识库与 `search_project_knowledge` 工具。统一序列化已修复 `Decimal`（median_gap_minutes）导致的 HTTP 500；工具错误降级为可理解 observation。以下「当前实现」段落中关于自定义工具循环、固定分类与手工 TOOL_REGISTRY 的描述指 LC-01 之前的 v4 实现，旧 `runner.py` 已于 LC-04 清理。

2026-09-22 状态核对（LC-01 之前的事实，保留作契约背景）：data-health、停留、相遇、事件—船舶关联与受限 `query_analytics` 均已注册，注册表共 9 个只读工具；`query_analytics` 功能开关默认关闭，关闭时不向模型暴露，只有本地回环绑定和独立只读配置完整时才可启用。SQL-06 已完成一次性 PostgreSQL 17、真实 DeepSeek 与浏览器综合验收，见 [SQL-06 说明](archive/query_analytics_sql06.md)。

历史核对：2026-09-20 的 v3 多工具版采用“大模型 API + 自定义只读查询工具”，当时未引入 LangChain、LangGraph 或扣子平台。POST /agent/analyze 已注册并通过 schemas_agent.py 与统一错误对外提供；前端智能体面板（frontend/src/components/AgentPanel.vue）已接入问答。该段只说明旧版演进背景，不再代表下一步架构决定。

## 已实现目标与分工

已实现的基础流程：用户问“指定时间有哪些船符合海峡虚拟门线通行规则？” → 模型提出工具调用 → 后端查询数据库并返回有证据的 AIS 船 ID、次数和两侧报位。回答内船只/事件的地图定位已实现；历史轨迹逐点回放联动尚未实现。真实模型在新数据上的自主工具选择仍待验收。

用户反馈新生成的小规模模拟数据已表现出封锁后停止通过海峡；本次文档修改不重新核验数据库批次或数量，不将其写成已验证的数据库结论。事件面板和智能体均已接入 P2 关联读取，但 observed 演示邻近与 mentioned 文本提及严格分列；通行及关联工具都不得推导真实事件对具体船只的因果影响。

已集成现有 FastAPI：路由位于 backend/app/routers/agent.py，编排、模型适配及查询服务位于 backend/app/services/agent/。当前版本通过 `langchain-openai` 的 ChatOpenAI 接入 DeepSeek OpenAI 兼容 API；配置和密钥仅由后端环境提供。

历史 v4 Tool Calling：8 个确定性工具由开发者写 SQL/SQLAlchemy；第 9 个 `query_analytics` 在 catalog v1 内允许模型生成受限 SELECT 和绑定参数，仍必须经过 SQL-03 全树白名单校验与 SQL-04 专用只读执行器。LangChain 分支把它拆成 schema/check/execute 三工具，不提供任意 SQL HTTP 接口，也不回退主应用数据库连接。

| 责任 | 交付 |
| --- | --- |
| 数据与地图成员 | 核对批次与数据库 ID、通行规则、查询工具、参数验证、最小问答入口 |
| 智能体成员 | 模型 API 适配、工具定义、简单调用循环、回答组织和超时处理 |
| 共同 | 固定请求/响应样例、封锁时间语义、通行证据与联调验收 |

## 查询口径

- 缺省查询起点 2026-02-28T15:00Z 仅沿用历史模拟方案以兼容接口，不是已经核验的真实封锁时刻；用户指定时间时须使用其带时区的参数，不能将报道日期补成精确时刻。
- 当前船舶查询限定 `ship_positions.data_source=nnu_ais`；来源批次和行号仍保存在源表。不得将旧模拟批次或新闻实体当成当前 AIS 船舶。
- “通过”指完整穿越，不以速度大于零、位于海峡内、transit 状态或跨单条线替代。
- 当前数据库工具在纬度 25.8–27.1°N、经度 55.8–57.1°E 区域内，按 56.2°E 西侧和 56.7°E 东侧的虚拟双门线判断侧别变化；门线之间保留状态。它是可追溯的观测口径，不是通用真实航道或精确越线判定。
- 数据库版按船排序，保存两侧报位、时间和方向。根据实际采样间隔确定长间隔及异常跳点规则；不充分的候选标为不确定，不能硬算为完整通行。
- 第一版按完成侧首个报位时间属于 [closure_at, end_at) 筛选，封锁前进入、封锁后完成也计入。该时间是观测完成时间，不是精确越线时刻。
- 最多回看窗口前 24 小时的门线侧别报位；缺少更早前置状态时不得断言未通过。SQL 限定时间、空间、来源并在库内排序；应用层只接收汇总和侧别变化，不读取全量报位。
- ship_id 去重计算船只数，通行次数单列。同一船多次穿越不重复计为多艘。
- 门线侧别报位充足时匹配为 0 是此口径的有效零结果；无报位或证据不足不能写成“船肯定没通过”。结论限于 `nnu_ais`、所选时间范围、空间边界和规则。

## 已实现接口与工具

POST /agent/analyze，一次请求返回完整回答。未实现流式输出和多智能体；前端已支持回答内船只/事件地图定位：船定位到当前模拟回放快照，不跳转历史轨迹点；新闻事件须有代表坐标且其发生时间已进入当前回放帧，方可按自身位置定位。

以下日期仅为结构示例，不代表真实封锁时间；联调需替换成核验后的参数：

```json
{
  "question": "封锁后有哪些船还通过了海峡？",
  "closure_at": "2026-03-01T00:00:00Z",
  "end_at": "2026-03-02T00:00:00Z",
  "history": [{"role": "user", "content": "之前的问题"}, {"role": "assistant", "content": "之前的回答"}]
}
```

question 必填，去除首尾空白后 1–2000 字符。时间字段可省略；缺失时使用后端兼容性默认起点和 24 小时窗口，该起点不代表实际封锁时刻。时间须带时区，统一 UTC，closure_at < end_at；最多 24 小时，超限报错，不静默截断。通行工具可选 ship_id 只查一艘船。

history 可选，为此前对话的消息列表（role 限 user/assistant，content 去除首尾空白后 1–2000 字符），最多携带最近 10 条消息（user/assistant 各计一条，通常为 5 组问答）；服务端将 history 插在 system 与本次问题之间。单轮问答不传 history。

以下九工具注册表为 LC-01 前历史实现；当前版本保留十一个业务工具，新增知识库工具并将 `query_analytics` 拆成 schema/check/execute 三工具。SQL 默认关闭时三工具均不向模型暴露；所有工具只通过 `/agent/analyze` 使用，不单独公开 SQL 路由：

| 工具 | 参数 | 说明 |
| --- | --- | --- |
| query_strait_passages | closure_at, end_at, ship_id（可选） | `nnu_ais` 历史报位的有界虚拟双门线观测通行；长间隔/跳点分列；不读取全部源报位到应用 |
| search_ships | keyword（必填）, limit | 按关键字检索有 `nnu_ais` 报位的船（船名/MMSI/IMO/callsign/船型/船旗），返回 ship_id 等；limit 默认 10、上限 20 |
| get_ship_track | ship_id（必填）, start_at, end_at | 服务端保留窗口内全部报位；模型只收到身份、数量、时间覆盖与首末报位摘要；时间缺省用默认封锁窗口 |
| get_event_context | event_id 或 keyword（二选一）, start_at, end_at | 新闻聚合事件及关联报道；不能仅凭船名与 AIS 船认定同一实体 |
| get_data_health | 无 | 复用 P5 /api/data-health 服务：各 data_source 报位数/船数/覆盖区间/中位间隔 + 四张派生表行数/built_at/params/stale（含未构建标记）；stale 仅为时间启发式，stale=false 不证明历史数据未被修改；来源缺失表示未导入，不得解释为真实数量为零；工具只读，不触发迁移、导入或派生层重建。派生层无源时间基准时 stale 返回 null（不可判定），不报 false |
| query_ship_dwell | kind, start_at/end_at, limit | 只读既有 ship_dwell；kind 限 at_anchor/drift/slow_transit，窗口成对且 ≤24h，缺省为全批次；返回阈值快照、stale、真实匹配数与截断状态，不重建 |
| query_encounters | start_at/end_at, max_distance_nm, limit | 只读既有 encounters；距离过滤只能缩小构建阈值，窗口筛选为与预计算 period 重叠，最小距离是离散采样近似；不调用写入型 analyze |
| query_event_ship_links | event_id 或 ship_id（二选一）, link_type, start_at/end_at | 按事件查 mentioned/observed 或按船反查 observed；当前七日 AIS 的 observed 未重建，mentioned 没有已核验的 AIS ship_id；不重建 |
| query_area_ship_snapshot | at（必填）, west/south/east/north（可选，四个同给）, ship_type, freshness_seconds | 某历史时刻在分析区域内的船（每船最新有效报位，过期报位不计入在场）；矩形省略时用本轮请求区域，无请求则用默认分析区域 `hormuz_core_v1`；明细最多 50 艘并说明未列出数量；与 `/api/area-activity` 共用同一 service |
| query_area_ship_activity | start_at/end_at（必填）, west/south/east/north（可选）, ship_type, batch_ids | 时段出现去重船数、观测进入/离开、累计船时、每日汇总与 ≤30 条访问明细；窗口最长 7 天；明细截断不裁剪汇总；no_data 只表示读取范围内没有报位 |
| compare_area_ship_activity | start_a/end_a/start_b/end_b（必填）, west/south/east/north（可选）, ship_type, batch_ids | 同区域同筛选的两期比较：`metrics` 给 a/b/delta/change_rate（基期为 0 时 change_rate 为 null 并单独说明）、`comparability` 与 `warnings`；只返回聚合指标，不返回逐次访问明细 |
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

历史 v4 实现：确定性分类先处理条件不足、写库/泄露意图等；当前版本已移除固定分类，由模型选择工具，SQL 安全仍由策略和只读执行器强制。结构化结果以服务端生成的 `call_001`、`call_002` 为键并带 `tool_name`；自由回答仍未逐项事实核验，疑似外部指令文本防回显门继续保留。

当前实现：整体预算 60 秒、统一最多 8 次工具调用、LangChain 递归步数上限 40。单船轨迹读取上限 50000 个报位；通行查询在数据库限定时间和海峡区域，门线侧别报位最多 100 万、侧别变化候选最多 5000，超限要求缩小窗口。船舶检索上限 20 条，事件查询上限 5 个事件、每事件 10 条报道。前端超时覆盖后端预算，不沿用新闻查询的 20 秒。

模型密钥和数据库凭据只保留在后端环境，不进入前端、回答或日志。除经过固定解析器、正向白名单、catalog 实物核验和独立只读角色的 `query_analytics` 外，不执行模型生成的 Python/SQL。数据库文本和新闻属于不可信数据，不执行其中指令。遗留 nearby-events 接口和 MobilityDB 固定窗口试验不作为本版通用工具。

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

模型完全不可用时返回错误，不用硬编码样例冒充成功。验收样例须使用实际数据库 ID，区分成功、零匹配和无数据，不编造数量；历史验收记录见下文。

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

## 实施与验收

下列勾选项保留既有阶段实施/验收记录，不表示本轮重跑全部用例；正文事实校验以本页「当前实现」说明为准。scripts/check_agent_api.py 对默认批次写死一艘船的预期，重跑前需核对 fixture/批次；模型可自然追问，但独立的 needs_clarification 状态当前未生成；无密钥 503 路径在该脚本中仍为 SKIP。

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

历史 SQL-01～06 已完成并在旧 v4 循环注册默认关闭的 `query_analytics`。SQL-06 曾验证真实 DeepSeek 工具 schema、固定 fixture 人工 SQL 对照和浏览器交互，不能视为当前版本已重验。当前版本已用 LangChain 单智能体复用 SQL 底座，SQL 三工具默认关闭；第一版不直接编写 LangGraph，复杂恢复或持久化需求出现后再评估。

最小版（v2）已实现并联调：后端 /agent/analyze 与前端智能体面板已跑通默认问题（返回 1 艘 SIM V2 化学品船 019，证据 P1，观测完成于 2026-02-28T18:14:54Z）；npm run build 与 npm run check:workbench 已通过。v3 多工具版历史联调记录（原标注日期晚于本次文档核对日，实际验收日期待核对；以下不代表本次重新验证）：通行回归问题 1 次工具调用 4.1s；「油轮 SIM V2 油轮 004 轨迹」问题链式调用 search_ships + get_ship_track 共 2 次 5.7s；「evt_001 事件与报道」1 次 get_event_context 3.1s，回答均保留来源链接与模拟边界声明。环境交接见 [database_setup.md](database_setup.md)。
# Issue #26 案例上下文增量（2026-09-30）

案例内提问复用v4请求字段：`map_context.target_ship_id` 为案例船，`playback_at` 为回放时刻；缺省 `closure_at/end_at` 为选中阶段内、当前回放之前最多24h（回放早于阶段时用阶段末界）；概况用完整案例内当前回放之前最多24h。显式问题/高级设置优先；其他船的地图动作提示退出案例，越出阶段提示返回概况或选择对应阶段。v4响应与服务端工具契约不变；真实AIS来源说明包含原七日及独立单船补充，不能把单船覆盖解释为全海峡覆盖。阶段切换取消旧请求，普通上下文对象刷新不取消。后端全量294 passed / 12 skipped、真实模型北冰洋号阶段轨迹自动动作与浏览器选中聚焦通过，详见[案例记录](arctic_ocean_case.md)。本节增量已通过PR #27合入main（2830ae6），本地主目录已同步，任务分支/工作区及预览已清理；未正式部署。
