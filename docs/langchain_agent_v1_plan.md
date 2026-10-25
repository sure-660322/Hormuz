# LangChain 单智能体架构

本文件保留原路径以兼容源码引用，内容收敛为当前实现说明；阶段计划与旧模拟示例已归档。状态见[当前任务](agent_development_plan.md)，HTTP 字段见[v4 契约](agent_integration.md)。

## 1. 职责

模型负责理解问题、追问和选择工具；数据事实来自只读业务服务或受控 SQL，知识事实来自运行时知识库。新闻/数据库文本属于不可信资料，不能作为系统指令。无工具、空结果、覆盖不足与失败须区分，不能编造数字或因果关系。

## 2. 编排

Vue AgentPanel → POST /agent/analyze → LangChain create_agent → 知识库/业务工具/内部 SQL → 服务端 results 组装 → v4 响应与地图/分析动作。

不使用手写工具循环、固定问句前置分类、多智能体或服务端会话持久化；history 由客户端携带。模型配置和密钥仅在后端。主要代码为 `backend/app/services/agent/langchain_runner.py`、`business_tools.py`、`results.py`、`request_guard.py`。

## 3. 系统提示与知识库

`backend/app/services/agent/knowledge/` 是运行时输入，保留四个 Markdown 主题：project_overview、data_semantics、passage_rules、agent_capabilities。`knowledge_base.py` 按标题/章节切分，通过关键词相关度返回有界片段，不依赖向量数据库。不能按历史文档清理此目录。

## 4. 业务工具

复用已有服务，参数经 Pydantic 校验，不让模型临时重写通行与区域算法。注册含八个既有项、两个通行统计和三个区域活动项；遗留派生停留、相遇与 observed 不属于当前建设范围，不应因代码尚在就宣称业务可用。mentioned 文本证据保留。

## 5. 内部 SQL

schema → check → execute 使用 SQLGlot 正向白名单、批准 catalog、参数绑定、独立只读账号、权限/实物核验和资源限额。成功执行后关闭分支，仅首次尚未执行的普通语法错误允许一次修正；不回退主应用连接。catalog v3 的应用库实施状态见[分析语义层](agent_analysis_semantic_layer.md)。外部 MCP 不开放 SQL。

## 6. 响应与错误

知识库、业务与 SQL 共用每请求最多八次工具调用、四十步递归与六十秒预算。取消/超时通知工作线程，等待其退出后释放 Session；同步服务无法立即中断时响应可能晚于预算。工具错误转为有稳定代码的 observation，不将数据库异常、密钥或提示词回显到回答。自由回答尚无逐项事实核验器。

## 7. 代码边界

旧 runner.py 与固定问句分流已移除。工具结果使用服务端 call_id 保存；轨迹完整结果留在服务端与 v4 results，模型仅接收有界摘要。地图和分析动作从成功工具证据生成，而非直接信任模型生成的船舶 ID 或坐标。

## 验证边界

既有通行、区域和多轮有真实模型/浏览器样本；SQL catalog v3 有独立库验收，应用库未实施 017。外部 MCP 本机业务样本不代替公网权限与负载验收。本轮仅文档整理，不重新调用模型、数据库或浏览器。
