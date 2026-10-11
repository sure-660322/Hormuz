> 2026-10-11：旧派生停留/相遇/observed 关联与 P5 simplified 回放切换已取消。下方历史设计中的这些条目不属于当前建设或验收范围。

# LangChain 业务智能体第一版技术方案

状态：**本地 main 已整合，整版已实现待真实环境验证**（2026-09-23，来源 `kimi/agent-lc04` 的 `6bf739c` 与 `codex/lc-safety-fix` 的 `1afd34b`；远端未推送）。`f14eceb` 曾因 SQL 可二次成功执行、超时后后台触库和联调脚本引用删除入口而阻塞整合；修复分支已通过确定性离线回归 245 passed / 12 skipped、前端 build/check:workbench 及三个 HTTP 冒烟入口。真实 DeepSeek、独立 PostgreSQL SQL 链路和浏览器尚未按本版验收。编排使用 LangChain `create_agent`，响应保持 v4 契约；8 个原生业务工具、知识库和受限 SQL 三工具均接入，旧 `runner.py` 手写循环已删除。详细复核和修复记录见 [开发任务](agent_development_plan.md)。

## 1. 目标体验

第一版要把当前“固定问句分类器”改造成真正放入霍尔木兹业务场景的单智能体：

- 用户问候时自然介绍身份和能力，不依赖固定字符串。
- 用户询问项目外问题时说明主要职责；若已有外部工具则补问必要参数后调用，没有工具则明确说明不能可靠查询。
- 用户询问项目知识时，从系统提示和轻量知识库获取依据。
- 用户询问数据时，由模型判断应调用业务 Skill 还是生成 SQL。
- 条件不足时自然追问；工具失败时说明暂时不可用，不编造数据，也不把后端异常伪装成“无法连接”。
- 多轮对话能理解“它”“刚才那艘船”等上下文。

示例：

| 用户输入 | 第一版预期行为 |
| --- | --- |
| 你好 | 自然问候，简述船舶、轨迹、通行、新闻和统计能力 |
| 今天天气怎么样 | 说明主要职责；缺地点时追问，具备天气工具后再查询 |
| 地图上的船是真的吗 | 查询项目知识，说明船位为教学模拟、新闻为真实报道聚合 |
| 数据库里有多少艘模拟船，按船型统计 | SQL Agent 查看语义结构、生成并执行只读 SQL、根据结果回答 |
| 封锁后有哪些船完整通过海峡 | 调用 `query_strait_passages`，不让通用 SQL 临时重写通行业务算法 |

## 2. 第一版架构

```text
Vue AgentPanel
  → POST /agent/analyze
  → LangChain create_agent（DeepSeek OpenAI 兼容接口）
      ├─ 简洁系统提示词
      ├─ 最近对话 history
      ├─ search_project_knowledge
      ├─ 8 个现有只读业务 Skills
      ├─ get_database_schema / check_sql / execute_sql
      └─ get_weather（非核心演示工具）
  → 统一序列化与结构化结果
  → 自然语言回答、来源、表格和地图定位信息
```

第一版使用 LangChain `create_agent`，不直接编写 LangGraph、不做多智能体、不做服务端会话持久化。LangChain Agent 内部可使用其现有执行基础；只有后续出现人工审批、断点恢复或复杂长流程时才单独评估 LangGraph。

建议依赖：`langchain`、`langchain-openai`、`langchain-community`，具体版本在 LC-01 独立环境实测后锁定。模型继续使用现有 DeepSeek 配置。

## 3. 系统提示与知识库

系统提示只保留身份和长期规则：

1. 你是霍尔木兹海峡海事态势分析智能体。
2. 船舶/轨迹是教学模拟数据；events/news 是真实报道聚合，两者不得自动认定为同一实体或因果关系。
3. 普通交流自然回答；项目事实优先查知识库；数据事实必须调用 Skill 或 SQL 工具。
4. 条件不足时追问；没有工具或查询失败时诚实说明，不猜数字。
5. 专门业务算法优先调用对应 Skill，普通筛选、排序和聚合交给 SQL Agent。

第一版不引入向量数据库。新增 `backend/app/services/agent/knowledge/`，按主题维护小型 Markdown 知识库，并提供 `search_project_knowledge(query)` 工具，通过标题、关键词和简单相关度返回 3～5 个片段。知识规模扩大后再评估 embeddings/RAG。

建议知识文件：

- `project_overview.md`：定位、技术栈、能力边界。
- `data_semantics.md`：模拟船、新闻、事件和时间语义。
- `passage_rules.md`：完整通行口径。
- 旧 `mobility_rules` 知识条目已于 2026-10-11 删除；当前能力范围见 `project_overview.md` 与 `agent_capabilities.md`。
- `agent_capabilities.md`：当前工具和不可用能力。

## 4. 业务 Skills

把现有服务包装成 LangChain `@tool`，不重写已经验证的业务算法：

- `search_ships`
- `get_ship_track`
- `query_strait_passages`
- `get_event_context`
- `get_data_health`
- `query_ship_dwell`
- `query_encounters`
- `query_event_ship_links`

Tool 描述负责告诉模型何时使用以及结果边界。例如“完整通过海峡”必须使用 `query_strait_passages`；`observed` 只表示模拟时空邻近；相遇结果不证明真实互动。选择工具由模型完成，不再由 Python 固定问句分流。

为复现范围外问题示例，可增加只读 `get_weather(location)`：缺少地点时由模型追问；工具不可用时明确说明。天气能力与海事数据库完全隔离，不作为项目核心验收阻塞项。

## 5. SQL Agent

SQL Agent 是主智能体的一组工具，不是另一个模型：

- `get_database_schema`：返回允许视图、字段和业务说明。
- `check_sql`：调用现有 SQLGlot 策略检查并返回可理解的拒绝原因。
- `execute_sql`：只执行检查后的规范化 SQL，返回列、行、数量、截断、来源和 query_id。

典型循环：

```text
理解统计问题 → 查看 schema → 生成 SQL → 检查 → 执行
→ 成功则回答；普通语法问题最多修正一次；仍失败则说明原因
```

当前请求边界（2026-09-23 已合入本地 main）：每请求统一最多 8 次工具调用，计入 8 个业务工具、知识库及 SQL 的 schema/check/execute；LangChain `create_agent` 的递归步数上限为 40，整体执行预算为 60 秒，没有旧版“4 轮模型请求、3 次业务工具执行”的限制。第 9 次工具请求以结构化 `TOOL_BUDGET_EXCEEDED` 返回，并停止后续模型调用。`execute_sql` 第一次成功、拒绝、超时或不可重试失败后关闭；第一次尚未实际执行的普通语法错误才允许一次修正，数据库实际执行最多一次。整体超时后的任务先取消后收尾，HTTP 超时响应须等线程停止，不能让后台继续访问请求级 Session。

保留现有 `agent_data` 语义视图、`query_analytics_policy.py` 和 `query_analytics_executor.py`。第一版支持常见 SELECT、WHERE、排序、聚合和批准 JOIN；需要更多数据时扩展语义视图，而不是开放业务底表。

最低保护继续保留：独立只读账号、只读事务、SELECT-only、超时、结果上限和 query_id。它们不是商业级过度设计，而是避免比赛演示时误写数据库、查询卡死或返回过大结果的最低保障。

## 6. 响应与错误

所有工具结果先经过统一 JSON 转换，覆盖 `Decimal`、日期时间、UUID、Pydantic/dataclass 和 SQLAlchemy Row。已发现的 `median_gap_minutes: Decimal` 导致 HTTP 500 是 LC-01 必修复项。

工具错误作为可理解的 observation 返回 Agent，由模型形成最终回答：

```json
{
  "status": "error",
  "code": "DATABASE_UNAVAILABLE",
  "message": "数据库暂时不可用，请稍后重试"
}
```

第一版保留现有响应中的 `answer`、`request_id`、`results`、船舶/事件引用和地图定位数据。前端状态可逐步收敛为 `thinking / needs_input / completed / failed`；迁移期保持 v4 兼容，避免一次性重写页面。

## 7. 现有代码去留

### 保留并复用

| 文件/模块 | 原因 |
| --- | --- |
| `backend/app/routers/agent.py` | 保留 `/agent/analyze` 入口，内部改调 LangChain Agent |
| `backend/app/schemas_agent.py` | 迁移期保持前端兼容，后续再简化状态 |
| `backend/app/services/agent/*_query.py`、船舶/事件服务 | 已验证的只读业务 Skill 实现 |
| `query_analytics_policy.py` | SQLGlot 只读检查底座 |
| `query_analytics_executor.py` | 独立只读执行、超时、并发和结果限制 |
| `backend/app/query_analytics_catalog_v1.json` | SQL schema 与语义目录基础 |
| `frontend/src/components/AgentPanel.vue`、`frontend/src/api.ts` | 保留页面和结构化展示，做兼容性调整 |

### LangChain接管后可以移除（均已于 LC-03/LC-04 执行）

下表移除项已按计划执行完毕（LC-04 等价回归 231 passed / 12 skipped 后），保留作决策记录：

| 当前代码/规则 | 移除条件与替代方案 | 执行 |
| --- | --- | --- |
| `runner.py::_classify_preflight` | LC-01/03 完成后删除；问候、范围外、澄清和能力判断交给模型 | LC-03 移除前置分类 |
| `clarification_rules`、`deferred_patterns`、`unsafe_requests` 等固定短语表 | 不再为每种中文说法添加关键词；SQL写入由执行边界拒绝，语义澄清由 Agent处理 | LC-03/04 移除 |
| 当前超长 `SYSTEM_PROMPT` 中的固定工具优先级和样例句 | 改为简洁身份规则 + Tool 描述 + 按需知识检索 | LC-01 起为新系统提示 |
| 手工 `TOOL_REGISTRY` JSON Schema | 业务服务包装为 LangChain `@tool` 后删除 | LC-04 由 `business_tools.py` 替代 |
| `run_agent` 的手工四轮 Tool Calling 循环 | LC-04 完成等价回归后由 `create_agent` 替代 | LC-04 删除 `runner.py` |
| `_run_*` 适配函数 | 对应 LangChain Tool wrapper 稳定后删除；底层服务保留 | LC-04 原生 Tools 直接调用服务层 |
| `test_query_analytics_sql06.py` 中固定问句分类矩阵 | 替换为问候、范围外、知识、SQL、Skill、澄清和错误降级的多表达测试 | LC-04 由 `test_agent_expressions.py` 替代 |
| `test_query_analytics_integration.py` 中模拟旧消息循环的测试 | LangChain集成测试稳定后删除；SQL策略/执行器专项测试继续保留 | LC-04 重写为 HTTP 层用例 |

### 不能移除

- 模拟船位与真实新闻相互独立的事实边界。
- 新闻和数据库文本是不可信数据，不能作为系统指令执行。
- 数据库只读账号和禁止写入。
- 查询超时、返回条数/大小限制。
- 通行、停留、相遇、事件关联等专门业务语义。
- 查询失败不能编造结果。

## 8. 文档整理决定

本方案成为智能体唯一的下一阶段设计入口。以下文档删除：

- `DEVELOPMENT_ROADMAP.md`：2026-08-30 旧总路线，数据规模和任务状态已失效。
- `agent_question_matrix.md`：以固定问题分类为中心，与新 Agent 自由理解方向冲突。
- `query_analytics_review_resolution.md`：SQL-01 评审过程记录，决定已落实到实现、契约和阶段验收文档。

以下文档保留：

- `agent_integration.md`：描述当前仍在运行的 v4 契约，直到 LangChain 版替换。
- `query_analytics_contract.md`：保留为当前 SQL 安全底座契约，并标记为历史实现依据。
- `query_analytics_sql02.md`～`query_analytics_sql06.md`：保留实现和验收证据，不作为新架构任务清单。
- 三个 `agent_tool_*.md`：保留现有 Skill 业务语义。

## 9. 实施阶段

| 阶段 | 交付 | 完成标准 |
| --- | --- | --- |
| LC-01 | 锁定 LangChain 依赖；DeepSeek `create_agent`；新系统提示；统一序列化和错误降级 | 问候、范围外问题、模型不可用、Decimal 工具结果不再 500 |
| LC-02 | 8 个现有业务服务包装为 LangChain Tools；轻量知识库 | 多种表达可自动选 Skill/知识库，多轮代词可继续查询 |
| LC-03 | schema/check/execute SQL Tools；本地演示环境启用受限 SQL Agent | 普通筛选、排序、聚合和批准 JOIN 可自然问答；写 SQL 被底座拒绝 |
| LC-04 | 前端兼容、旧 runner/固定规则清理、浏览器与真实模型验收 | 同义表达、澄清、故障降级、表格和地图引用通过；文档与代码状态一致 |

每阶段使用独立分支/worktree；只有实际通过测试后才更新为“已实现”。

## 10. 第一版验收

至少覆盖以下自然表达，而不是只覆盖标准句：

- 问候与能力介绍：你好、在吗、你能做什么、谢谢。
- 范围外：今天天气怎么样、上海天气如何、你会写诗吗。
- 项目知识：船是真实 AIS 吗、新闻和模拟船有什么关系、相遇代表真实接触吗。
- SQL统计：一共有几艘船、多少条船、按船型统计、哪种事件最多、哪个事件报道最多。
- Skills：穿越海峡、找船、轨迹、停留、相遇、事件附近船舶。
- 澄清：那艘船、这个事件、最近有多少船、那天发生了什么。
- 故障：数据库/模型/天气工具不可用，SQL错误修正一次，所有失败均有自然回答且不编造。

第一版完成的核心判据：用户不需要背固定问法；模型能基于系统提示、知识、数据库 schema 和 Tool 描述自行选择合理路径，并且任何失败都不会退化成未处理的 HTTP 500。
