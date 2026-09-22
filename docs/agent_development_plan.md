# 智能体下一阶段开发任务

更新：2026-09-22。下一步目标已经调整为 [LangChain 业务智能体第一版](langchain_agent_v1_plan.md)。当前实际运行状态仍见 [智能体接入契约](agent_integration.md)，全项目摘要见 [README](../README.md)。本页只维护实施顺序和状态，不重复技术方案。

## 当前判断

- SQL-02～06 已完成语义视图、SQLGlot 校验、独立只读执行、工具接入和隔离验收；这些成果作为新 SQL Agent 的安全执行底座保留。
- 当前 `runner.py` 仍是自定义 Tool Calling 循环，并包含大量固定短语分类；它是现状，不是下一版目标。
- 下一版确定使用 LangChain 单智能体，让模型基于系统提示、项目知识、Tool 描述和数据库 schema 自主选择自然回答、知识检索、业务 Skill 或 SQL。
- 第一版不直接编写 LangGraph、不做多智能体和服务端会话持久化。
- LC-01 已完成基础接入（见下方实施记录）：统一序列化修复了 `median_gap_minutes: Decimal` 导致的 HTTP 500，编排切换到 `create_agent`；范围外与问候由模型自然回答。

## 实施看板

| 编号 | 范围 | 状态 | 验收重点 |
| --- | --- | --- | --- |
| LC-01 | LangChain/DeepSeek 基础接入、简洁系统提示、统一序列化和错误降级 | **已实现待验证** | 自然问候；范围外回答；模型/工具错误不产生未处理 500；`Decimal` 可序列化 |
| LC-02 | 现有 8 个只读业务服务包装为 LangChain Tools；轻量 Markdown 知识库 | **已实现待验证** | 模型能按多种表达自主选择知识或 Skill；多轮代词可用 |
| LC-03 | `get_database_schema`、`check_sql`、`execute_sql`；本地受限 SQL Agent | **已实现待验证** | 普通筛选/排序/聚合可问答；复杂业务继续走 Skill；写 SQL 被只读底座拒绝 |
| LC-04 | 前端兼容、旧 runner/固定规则清理、真实模型和浏览器验收 | **待开始** | 不要求固定问法；澄清、故障降级、表格、来源和地图引用正常 |

### LC-01 实施记录（2026-09-22，分支 kimi/agent-lc01）

- 依赖锁定：`langchain==1.4.2`、`langchain-openai==1.6.3`（独立 worktree 虚拟环境实测 `create_agent` 可用；langchain 1.x 内置工具循环执行基础，项目不直接编写 LangGraph）。
- 新增 `backend/app/services/agent/serialization.py` 统一序列化（Decimal→int/float、datetime/date、UUID、dataclass、pydantic、SQLAlchemy Row、未知类型 str 兜底），修复 `median_gap_minutes: Decimal` 导致的 HTTP 500；旧 `runner._jsonable` 委托同一实现。
- 新增 `backend/app/services/agent/langchain_runner.py`：DeepSeek 经 ChatOpenAI 接入 `create_agent`；8 个现有只读业务工具由 v4 注册表适配为 LangChain Tools（业务算法未重写）；简洁系统提示；工具错误降级为 `{status, code, message}` observation；整体 60 秒预算；固定短语前置分类暂保留拒绝/澄清子集。
- `routers/agent.py` 内部改调 `run_lc_agent`，**v4 响应契约保持不变**（schema_version 仍为 "4"）。
- 已验证（2026-09-22，离线，无真实模型/数据库）：后端全量 229 passed / 13 skipped（新增 22 项：序列化、问候/范围外无工具回答、模型不可用 503、Decimal 不再 500、工具错误降级、超时 504、history 透传、路由层往返）；/health、/docs、/openapi.json 冒烟 200。
- 未验证：真实 DeepSeek 问答与工具选择、浏览器端到端、前端兼容（留 LC-04）；`query_analytics` 在 LC-01 不向模型暴露（LC-03 接入）。

### LC-02 实施记录（2026-09-22，分支 kimi/agent-lc02）

- 新增 `backend/app/services/agent/knowledge/` 轻量知识库：`project_overview`、`data_semantics`、`passage_rules`、`mobility_rules`、`agent_capabilities` 五份 Markdown（第一版不引入向量数据库）。
- 新增 `backend/app/services/agent/knowledge_base.py`：按章节切分、中文 bigram + 拉丁词切词、标题命中加权的相关度检索，返回 3～5 个片段（单片段 ≤900 字符）。
- `langchain_runner.py` 新增 `search_project_knowledge` 工具（结果计入 results/tools_used，与业务工具同一 envelope 口径）；系统提示规则 2 改为「项目知识优先调用知识库工具」。
- 已验证（2026-09-22，离线，无真实模型/数据库）：后端全量 237 passed / 13 skipped（新增 8 项：知识检索命中/空结果/上限、知识工具被调用、能力边界回答、多轮指代「它」结合 history 继续调用业务工具、知识结果可序列化）。
- 未验证：真实模型对知识工具的选择准确率（脚本化假模型只验证链路）；浏览器端到端（LC-04）。

### LC-03 实施记录（2026-09-22，分支 kimi/agent-lc03）

- 新增 `backend/app/services/agent/sql_tools.py`：`get_database_schema`（catalog 视图/字段/批准 JOIN/上限）、`check_sql`（SQLGlot 策略纯校验，不触库）、`execute_sql`（复用 SQL-04 独立只读执行器，SELECT-only、超时、结果上限、query_id）；拒绝/超时/执行失败后关闭后续 execute_sql，仅未执行的普通语法错误可修正一次。
- 工具仅在功能开关完整（`ExecutorConfig.from_env`）时暴露；系统提示按需追加受限 SQL 工具说明。
- 按方案 §7 的移除条件（LC-01/03 完成）删除 `langchain_runner` 中的固定短语前置分类：问候、范围外、知识、写库/越权意图、澄清全部交给模型与工具底座（写 SQL 由只读策略拒绝）。旧 `runner.py` 及其测试保留至 LC-04 等价回归后清理。
- 已验证（2026-09-22，离线，无真实模型/数据库）：后端全量 245 passed / 13 skipped（新增 10 项：schema 返回、合法 SELECT 校验、DELETE/字面量拒绝、execute_sql 经假执行器返回行/列/query_id、拒绝后 SQL 关闭、开关关闭时工具不暴露、写意图经策略拒绝；改写 4 项前置分类依赖测试）。
- 未验证：真实 PostgreSQL + 真实 DeepSeek 的 SQL 问答链路（本地演示环境启用后验收，随 LC-04 或单独环境验证）；浏览器端到端（LC-04）。

## 保留与清理边界

保留：现有业务查询服务、`agent_data` 视图、catalog、SQLGlot 策略、独立只读执行器、超时/结果限制、前端 AgentPanel 及结构化展示。

待 LangChain 等价能力通过后移除：`_classify_preflight` 及固定短语表、手工 `TOOL_REGISTRY` schema、手工模型工具循环、重复 `_run_*` 适配层，以及只验证固定句式的测试。精确文件和删除条件见 [第一版方案 §7](langchain_agent_v1_plan.md#7-现有代码去留)。

不能移除：模拟船/真实新闻边界、新闻文本不可信、数据库只读、禁止写入、超时和结果限制，以及通行/停留/相遇/事件关联的业务语义。

## 历史证据

SQL-02～06 的阶段验收文档继续保留，但不再作为当前任务看板：

- [SQL-02 语义视图与只读角色](query_analytics_sql02.md)
- [SQL-03 AST 策略](query_analytics_sql03.md)
- [SQL-04 独立执行器](query_analytics_sql04.md)
- [SQL-05 工具循环接入](query_analytics_sql05.md)
- [SQL-06 综合验收](query_analytics_sql06.md)
- [受限 Text-to-SQL 历史契约](query_analytics_contract.md)

这些记录证明已有底座当时的实现和验证状态，不表示 LangChain 第一版已经完成。

## 工作规则

- 每阶段使用独立分支和 worktree，开始前记录基线与文件所有权。
- 状态严格区分“待开始 / 进行中 / 已实现待验证 / 已验证”。
- 文档和页面不得把方案写成已实现功能。
- 第一版按学生比赛项目控制复杂度；不为尚未出现的商业部署问题增加框架。
- 依赖版本、模型 Tool Calling 和 SQL Agent 行为必须实际测试后锁定。
