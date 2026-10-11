> 2026-10-11 本机范围收尾复核：现有业务凭据已成功查询，无需新增 SQL 账号；最小权限审计属于后续加固。独立 SDK 真实 stdio 取消及 4 槽并发/第 5 项拒绝已验证。本机 7 工具交付满足调整后的验收，持续压测、HTTP TCP 断线和公网认证/许可为保留限制。PR #63 已合并（24fb258），#50 已关闭，本地 main 已同步；本轮新 worktree 已归档，旧 DSH 运行工作树及桌面配置保留，未部署。下方 Draft 阻塞是上一轮判断，已由本次复核替代。

# 本机只读业务 MCP（Issue #50）

2026-10-11 范围调整：外部 MCP 固定提供下列 7 个业务工具；Text-to-SQL 仅供项目内部智能体使用。PR #62（b5d8a60）曾实现默认关闭的 SQL MCP 适配，此任务分支已移除该分支，不因环境变量、配置或 tools/call 重新开放。当前验证与未完成项见[本轮记录](issue50_business_boundary_acceptance.md)。未合并、未部署，现有 DSH 桌面仍运行保留的旧 worktree。

## 工具与契约

| 工具 | 边界 |
| --- | --- |
| search_ships | 历史 AIS 身份检索；关键词 1–100 字符，最多 20 条；名称不能证明新闻实体身份 |
| get_ship_track | 显式时区半开窗 ≤24h；原服务 ≤50,000 点；超过传输预算整项拒绝 |
| query_strait_passage_statistics | ≤7 天；每日和全窗统计、虚拟门线口径与不确定候选 |
| compare_strait_passage_statistics | A/B 各 ≤7 天，共享筛选 |
| query_area_ship_snapshot | 完整矩形或版本化默认区域，历史时刻，新鲜度 1–86400 秒，最多 50 船 |
| query_area_ship_activity | ≤7 天；访问明细最多 30 条，保留质量及部分覆盖 |
| compare_area_ship_activity | A/B 各 ≤7 天，同一区域与筛选，明细限制 30 |

backend/mcp_server 的 TOOLS、Adapter.names 与 dispatch 仅承认业务工具。get_database_schema、check_sql、execute_sql 全部返回 TOOL_UNAVAILABLE；不加载 SQL policy、catalog、执行器或外部令牌存储。旧 MCP_SQL_ENABLED 和 AGENT_QUERY_* / AGENT_DB_* 不启用工具，不读取 SQL 具名凭据。内部 SQL 的 schema→check→execute、AST/参数/权限/catalog/快照/超时/结果限额保持原实现，见[内部契约](query_analytics_contract.md)。无外部 SQL 专用配置或依赖新增。

严格 Pydantic 参数拒绝额外字段。输出 text 与 structuredContent 是相同 JSON，保留 request_id、tool_name、adapter_version（0.2.0）、status、服务版本、窗口、区域、质量和限制。汇总优先排列，超出 2MiB 整项拒绝，不静默截断。网页地图动作不属于 MCP。无隐含视野或聊天区域状态：bounds 省略时每次重新使用默认区域。

## 启动与配置

使用包含当前实现的独立运行目录及已安装 backend/requirements-mcp.txt 的 Python。模块不读取 .env，密码只由 MCP 后端进程按具名机制在内存中解析。

```text
MCP_DB_USER=<预先配置的受限业务查询账号>
MCP_DB_PASSWORD_CREDENTIAL=<既有 Windows 具名凭据目标>
MCP_DB_HOST=127.0.0.1
MCP_DB_PORT=<测试端口>
MCP_DB_NAME=<明确的测试库>
```

也可使用受控进程环境的 MCP_DB_PASSWORD；与具名来源同时存在会拒绝。不要把真实密码写入文件、命令行或 Git。账号的数据库权限由管理员预先配置，本模块不创建角色或迁移。

```powershell
python -m backend.mcp_server --transport stdio
python -m backend.mcp_server --transport streamable-http --port 8036
```

Windows 插件 launch.ps1 只接受 python/workspace/database 五项数据库元数据，清除继承 DB/MCP/AGENT_DB/AGENT_QUERY 设置并原始字节转发 stdio。含额外 sql 配置的文件拒绝启动；configure.ps1 仍只生成业务配置。DSH profile 格式见[说明](dsh_mcp_acceptance.md)。本轮不改其桌面 profile、本机已通过验收的 runtime 路径或旧运行 worktree。

## 传输、身份和资源

官方 Python MCP SDK 2.3.0；stdio 每客户端子进程独立，无共享聊天上下文。Streamable HTTP 只绑定 127.0.0.1，路径 /mcp，默认 8036，stateless + JSON response，不提供旧 HTTP+SSE 或服务器主动订阅。2025-11-25/2026-07-28 协议兼容由 SDK 处理并回归验证。

HTTP 必须提供 MCP_HTTP_TOKENS：JSON 对象 {"client-a":"<32–256 字符随机令牌>"}，1–64 个不同值；请求携带 Authorization: Bearer。逐请求验证回环客户端、Host/Origin 和身份，禁用代理头信任。同一 bearer 是同一客户端，不能视为不同用户。静态本机令牌不是公网 OAuth。

每进程最多 4 线程，无等待队列；每身份每分钟最多 60 次工具调用；外层预算 30 秒，HTTP 请求体 ≤128KiB。业务独立 Session/READ ONLY 事务，statement_timeout 5s、lock_timeout 1s。取消/超时设置事件并取消 psycopg 查询，后续 SQL 前检查取消，线程结束才释放并发槽。日志只写 ID/已知工具名/状态/code；错误不回显数据库异常、配置值或连接串。

这些是本机边界，不是全局多进程业务限流。尚缺真实网络断开→数据库无残留查询验收、专用业务账号最小权限核验和持续负载；因此本轮 Draft PR，不关闭 #50。公网身份认证授权、数据展示许可、预算与部署均另行授权。

## 历史证据

PR #62 的本机业务子集已合并；Kimi CLI 双传输四题/八次与业务基线一致，[历史记录](issue50_kimi_acceptance.md)。DSH headless 真实模型四题与基线一致，桌面后续样本由用户确认，[记录](dsh_mcp_acceptance.md)。历史 SQL MCP 令牌测试不属于当前公开能力；内部 catalog v3 独立测试库验收见[Issue #48](issue48_sql_acceptance.md)，不能把它称为外部 SQL 验收。
