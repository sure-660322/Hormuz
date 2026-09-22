# SQL-06 综合验收

状态：**已验证**（2026-09-22，worktree `D:/my_project/Hormuz-codex-sql06`，分支 `codex/sql06-validation`，基线 `6b46d64`）。`query_analytics` 已通过固定 fixture、一次性 PostgreSQL 17、真实 DeepSeek Tool Calling 和浏览器展示验收；功能开关仍默认关闭，且远端部署限制不变。

## 本阶段补强

- 在系统提示中加入 catalog v1 的三个视图、字段及唯一批准 JOIN，模型不再依赖猜测数据库结构。
- 将 AG-01 矩阵中的澄清、拒绝、非数据问题和当前 catalog 不支持项落为确定性前置分类；这些分支不调用模型或数据库。
- 增加自由回答防回显门。若模型回答包含疑似来自新闻/数据库文本的指令性内容，后端隐藏整段回答并追加明确限制；结构化查询结果和来源标识仍保留。
- `scripts/check_agent_api.py` 更新为 v4 `call_id` 结果结构，默认不再硬编码共享数据库的船数或零结果；只有显式声明固定 fixture 时才断言具体数量。
- 新增可重复的 SQL-06 验证脚本和本地浏览器 fixture。fixture 只验证真实 Vue 页面渲染，不代替后端数据库与模型链路。

## 自动验证

普通全量后端回归：

```powershell
& 'D:\my_project\Hormuz\backend\.venv\Scripts\python.exe' -m pytest backend/tests -q
# 207 passed, 13 skipped, 1 warning
```

一次性 PostgreSQL 17 + 真实 DeepSeek：

```powershell
.\scripts\verify_query_analytics_sql06.ps1 `
  -Python 'D:\my_project\Hormuz\backend\.venv\Scripts\python.exe' `
  -RunRealModel -SecretsEnvPath '<本机密钥文件>'
# 57 passed, 1 warning
# PASS: SQL-06 isolated PostgreSQL 17 query analytics verification completed.
```

脚本使用固定 digest 的官方 PostgreSQL 17 镜像、随机回环端口、随机数据库密码和固定 fixture，完成后自动删除容器。密钥只临时导入当前进程并在结束后恢复，不复制进 worktree。未连接、查询或修改共享业务数据库。

验证覆盖：

- SQL-03/04/05 既有策略、权限、超时、并发、限额、错误映射和 runner 集成回归；
- `query_analytics` 结果与源表人工 SQL 对照，真实零结果和注入字符串作为绑定参数；
- 28 个问题矩阵前置分支，以及 `/health`、`/docs`、`/agent/analyze` v4；
- 真实 DeepSeek 对船旗聚合、事件类别聚合均选择 `query_analytics` 并完成回答；
- 恶意新闻标题仅作为不可信数据返回，未执行其中要求，且指令性文字未进入自由回答。

前端构建与工作台语义检查：

```powershell
cd frontend
npm run build
npm run check:workbench
```

两项均通过。浏览器使用本地固定 fixture 验证了“成功 + 受限分析表格”“待澄清”“已拒绝”三种状态；表格展示列名、行、catalog 版本、视图和 query ID，控制台 0 error / 0 warning。浏览器 fixture 不含数据库和模型密钥，后端真实链路由上述 PostgreSQL/DeepSeek 测试独立证明。

## 开放边界

- `AGENT_QUERY_ENABLED=false` 继续作为默认值。综合验收通过不等于允许公网开放。
- 只有回环绑定、独立 `agent_reader_login`、完整 catalog 配置及现有安全校验同时成立时才可本地启用。
- 本轮没有验证共享业务库的当前统计数量，也没有迁移或修改共享数据库；固定 fixture 的数量不能写成业务库现状。
- 尚未完成认证、限流、正式部署、长时间多 worker 压力测试和自由回答逐事实核验。防回显门只处理疑似指令文本，不是通用事实核查器。
