# SQL-05 工具循环与最小展示接入

状态：**已实现并通过隔离验证**（2026-09-21，worktree `D:/my_project/Hormuz-codex-sql05`，分支 `codex/sql05-integration`，基线 `c866af4`）。`query_analytics` 已注册，但 `AGENT_QUERY_ENABLED=false` 仍是默认值；关闭时不会出现在发送给模型的工具表中。

## 实现范围

- `runner.py` 注册第 9 个只读工具，并把 SQL、绑定参数、purpose 只交给 SQL-04 专用执行器；不使用或回退到主应用 `Session`。
- 启用时仍强制本机回环绑定、`agent_reader_login`、catalog 实物核验、SQL-03 同 AST 正向白名单、只读事务及 SQL-04 的超时/并发/结果上限。
- 响应契约升级为 v4：顶层状态收紧为 `ok / no_data / partial / needs_clarification / refused`；`results` 使用编排层生成的 `call_001`、`call_002` 键，值同时包含 `call_id` 和 `tool_name`，同名工具不再互相覆盖。模型供应商的 tool_call ID 不作为可信服务端 ID。
- 普通语法解析错误仅在首次 SQL 尚未执行时允许修复一次；成功、超时、安全拒绝、权限或 catalog/连接失败后禁止再次调用 query_analytics。安全拒绝返回 HTTP 200 + 顶层 `refused`；唯一能力超时为 504 `AGENT_QUERY_TIMEOUT`；catalog/角色/权限/连接异常为 503 `AGENT_QUERY_UNAVAILABLE`；已有其他成功工具时，超时或不可用可保留为 `partial`。
- 窄范围确定性前置分类覆盖明确写库/泄露意图、对象和指标均缺失的泛问，以及项目能力/数据来源/通行规则类非数据问题；这些分支不构建模型客户端、不调用工具。未明确命中的问题仍进入正常模型工具路由，避免用宽泛正则代替理解。
- 前端同步 v4 状态与 call-id 结果类型；`refused` 使用提示样式，`query_analytics` 成功结果显示列、行、catalog、实际视图、截断和 query_id。页面不显示 SQL 正文、参数或数据库凭据。

## 验证记录

普通后端回归：

```powershell
& 'D:\my_project\Hormuz\backend\.venv\Scripts\python.exe' -m pytest backend/tests -q
# 177 passed, 8 skipped, 1 warning
```

8 个 skip 是一次性 PostgreSQL 集成场景在普通回归中默认跳过；warning 为既有 Starlette/httpx 弃用提示。SQL-05 新增离线覆盖包括默认关闭、启用后工具表、独立执行器调用参数、服务端 call_id、一次语法修复、安全拒绝终止、唯一能力超时上抛、澄清/拒绝/非数据前置分支、响应枚举和 HTTP 稳定错误体。

一次性 PostgreSQL 17：

```powershell
.\scripts\verify_query_analytics_integration.ps1 `
  -Python 'D:\my_project\Hormuz\backend\.venv\Scripts\python.exe'
# 22 passed
# PASS: SQL-05 isolated PostgreSQL 17 query analytics verification completed.
```

脚本使用固定 digest 的官方 PostgreSQL 17 镜像、随机回环端口和随机密码，加载固定 fixture 与 013 迁移，运行 SQL-04 全部安全场景及 SQL-05 runner→真实执行器→catalog v1→聚合结果→同一模型回传链路，并校验多工具状态不会互相掩盖；结束后自动删除容器。未连接或修改共享数据库。

前端：

```powershell
cd frontend
npm run build
npm run check:workbench
# 均通过
```

SQL-05 worktree 没有独立安装依赖，验证时临时将 `frontend/node_modules` 链接到主工作区已有依赖，完成后已删除链接；未修改 lockfile 或依赖版本。

## 保持关闭与未验证范围

- `.env.example` 继续保持 `AGENT_QUERY_ENABLED=false`。未增加认证和限流前，不得在非回环或远端可访问部署启用。
- 本轮没有使用共享业务数据库，没有执行 013 迁移，没有真实业务数据统计，也没有调用真实 DeepSeek。供应商是否接受当前 `params.items.value` 的宽类型 JSON Schema、模型能否稳定优先选择确定性工具，仍须 SQL-06 少量真实调用验证。
- 未做浏览器端到端、真实模型提示注入行为或多 worker 长时间压力测试。后端能阻止查询结果诱导的第二次 query_analytics，但自由回答正文仍没有逐项事实核验器。
- SQL-06 应以固定 fixture 人工 SQL 对照、旧 8 工具回归、真实模型正常/澄清/拒绝/恶意新闻场景、`/health`/`/docs`/`/agent/analyze` 和浏览器展示为最终开放门槛；未通过前默认开关不变。
