# 智能体下一阶段开发任务

更新：2026-09-22。下一步目标已经调整为 [LangChain 业务智能体第一版](langchain_agent_v1_plan.md)。当前实际运行状态仍见 [智能体接入契约](agent_integration.md)，全项目摘要见 [README](../README.md)。本页只维护实施顺序和状态，不重复技术方案。

## 当前判断

- SQL-02～06 已完成语义视图、SQLGlot 校验、独立只读执行、工具接入和隔离验收；这些成果作为新 SQL Agent 的安全执行底座保留。
- 当前 `runner.py` 仍是自定义 Tool Calling 循环，并包含大量固定短语分类；它是现状，不是下一版目标。
- 下一版确定使用 LangChain 单智能体，让模型基于系统提示、项目知识、Tool 描述和数据库 schema 自主选择自然回答、知识检索、业务 Skill 或 SQL。
- 第一版不直接编写 LangGraph、不做多智能体和服务端会话持久化。
- 当前已知缺陷：问题“现在海上有几艘船”绕过固定短语后调用 data-health，`Decimal` 工具结果未正确 JSON 化并产生 HTTP 500；LC-01 必须修复。

## 实施看板

| 编号 | 范围 | 状态 | 验收重点 |
| --- | --- | --- | --- |
| LC-01 | LangChain/DeepSeek 基础接入、简洁系统提示、统一序列化和错误降级 | **待开始** | 自然问候；范围外回答；模型/工具错误不产生未处理 500；`Decimal` 可序列化 |
| LC-02 | 现有 8 个只读业务服务包装为 LangChain Tools；轻量 Markdown 知识库 | **待开始** | 模型能按多种表达自主选择知识或 Skill；多轮代词可用 |
| LC-03 | `get_database_schema`、`check_sql`、`execute_sql`；本地受限 SQL Agent | **待开始** | 普通筛选/排序/聚合可问答；复杂业务继续走 Skill；写 SQL 被只读底座拒绝 |
| LC-04 | 前端兼容、旧 runner/固定规则清理、真实模型和浏览器验收 | **待开始** | 不要求固定问法；澄清、故障降级、表格、来源和地图引用正常 |

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
