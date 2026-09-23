# 智能体下一阶段开发任务

更新：2026-09-23。下一步目标已经调整为 [LangChain 业务智能体第一版](langchain_agent_v1_plan.md)。当前实际运行状态仍见 [智能体接入契约](agent_integration.md)，全项目摘要见 [README](../README.md)。本页只维护实施顺序和状态，不重复技术方案。

## 2026-09-23 候选实现完整性复核

`kimi/agent-lc01`～`kimi/agent-lc04` 为串联分支，最终候选为 `kimi/agent-lc04`（`6bf739c`），四个 worktree 均干净。候选实现具备 LangChain `create_agent`、8 个原生业务工具、轻量知识库、受限 SQL 三工具、统一序列化和 v4 响应兼容；本轮使用候选 worktree 自带虚拟环境复跑后端全量测试为 **231 passed / 12 skipped**，智能体核心专项为 **54 passed**，前端 `npm run build` 与 `npm run check:workbench` 通过。本轮按用户要求未打开浏览器，也未调用真实 DeepSeek 或共享数据库。

当前状态：**阻塞整合，未合入 main**。必须先解决以下三项：

1. 安全阻塞：`execute_sql` 成功后未关闭 SQL 分支，且 SQL 三工具未纳入请求级工具预算。最小复现实验在同一 Agent 请求中连续得到两次 `ok`，执行器调用 2 次、产生 `aq_test_001` 与 `aq_test_002`，违反 `query_analytics_contract.md` 冻结的“单次回答数据库实际执行最多 1 次”约束，也破坏工具结果不得诱导第二次查询的防护。
2. 超时阻塞：`ThreadPoolExecutor.shutdown(wait=False)` 不会取消正在执行的 Agent。最小实验在 0.062 秒返回 `AgentTimeoutError` 后，SQL 执行器仍于 0.172 秒被后台线程调用；生产中可能在 HTTP 504 和请求级数据库 Session 释放后继续读库。
3. 完整性阻塞：`scripts/test_deepseek_toolcall.py` 仍导入已删除的 `backend.app.services.agent.runner.run_agent`，当前真实模型联调入口启动即 `ModuleNotFoundError`。

### 修复后的下一步阶段

| 阶段 | 范围 | 完成标准 |
| --- | --- | --- |
| LC-R1 安全闭环 | 第一次 `execute_sql` 成功、拒绝、超时或非重试失败后关闭 SQL 分支；schema/check/execute 与业务/知识工具统一纳入明确的请求级预算；补充二次成功执行和预算耗尽回归 | 假执行器证明同一请求数据库实际执行最多 1 次；第二次执行稳定返回关闭错误；既有 SQL-03/04 安全测试与后端全量测试通过 |
| LC-R2 超时生命周期 | 重新设计整体超时与取消路径；超时后设置请求取消状态，所有工具在触库前再次检查，且不得让后台线程继续使用已释放的请求级 Session；补充“模型晚返回工具调用”和“工具执行中超时”回归 | 返回 504 后执行器/业务仓库调用计数不再增长；没有后台任务继续使用请求 Session；线程与连接可回收 |
| LC-R3 联调入口与契约清理 | 将 `scripts/test_deepseek_toolcall.py` 切换到 `run_lc_agent`/当前模型构造；清除当前文档中仍把 3 次工具/4 轮模型写成现状的过期描述，明确最终预算值 | 无密钥时脚本可正常 SKIP，不再导入失败；静态检索无当前代码引用旧 `runner.py`；README、接入契约和计划一致 |
| LC-R4 非浏览器整合验收 | 在修复分支复跑后端全量、SQL 专项、前端 build/check:workbench、`/health`/`/docs`/OpenAPI 冒烟；不连接共享数据库 | 全部通过；跳过项和环境原因明确；合入 `main` 后重新验证提交祖先、工作树和文档状态 |
| LC-R5 真实环境验收 | 使用本地独立数据库和真实 DeepSeek 验证问候、知识、业务 Skill、SQL 聚合、澄清、拒绝、失败降级；浏览器三状态单列为后续验收，不阻塞本次非浏览器修复 | 工具选择和回答引用与结构化结果一致；SQL 仍最多实际执行 1 次；未通过项保持“已实现待验证”，不得写成已验证 |

## 当前判断

- SQL-02～06 已完成语义视图、SQLGlot 校验、独立只读执行、工具接入和隔离验收；这些成果作为新 SQL Agent 的安全执行底座保留。
- 当前 `runner.py` 仍是自定义 Tool Calling 循环，并包含大量固定短语分类；它是现状，不是下一版目标。
- 下一版确定使用 LangChain 单智能体，让模型基于系统提示、项目知识、Tool 描述和数据库 schema 自主选择自然回答、知识检索、业务 Skill 或 SQL。
- 第一版不直接编写 LangGraph、不做多智能体和服务端会话持久化。
- 当前已知缺陷：问题“现在海上有几艘船”绕过固定短语后调用 data-health，`Decimal` 工具结果未正确 JSON 化并产生 HTTP 500；LC-01 必须修复。

## 实施看板

| 编号 | 范围 | 状态 | 验收重点 |
| --- | --- | --- | --- |
| LC-01 | LangChain/DeepSeek 基础接入、简洁系统提示、统一序列化和错误降级 | **待整合** | 候选分支离线回归通过；随 LC-R1～R4 重新验收 |
| LC-02 | 现有 8 个只读业务服务包装为 LangChain Tools；轻量 Markdown 知识库 | **待整合** | 候选分支离线回归通过；真实模型选择准确率未验证 |
| LC-03 | `get_database_schema`、`check_sql`、`execute_sql`；本地受限 SQL Agent | **阻塞** | 存在同一请求成功执行两次 SQL 的安全契约回退，须完成 LC-R1 |
| LC-04 | 前端兼容、旧 runner/固定规则清理、真实模型和浏览器验收 | **进行中** | 前端非浏览器检查通过；真实模型脚本入口损坏，浏览器与真实环境未验收 |

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
