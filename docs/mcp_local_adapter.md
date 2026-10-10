# 本机 MCP 适配层（Issue #50，第一阶段）

2026-10-09：负责人 Codex，基线 `74dcbdc`，分支 `codex/mcp-local-transports`。
用户只授权接口核对、适配实现、调用边界三个阶段，并要求同时提供 stdio 和
Streamable HTTP。本阶段已实现并经开发检查验证；用户追加授权 Kimi 业务测试及 PR 交付。
Kimi 双传输四题/八次真实调用已通过同条件业务对账，见[验收记录](issue50_kimi_acceptance.md)。
受控 SQL 完整客户端验收、合并及部署均未完成，#50/#46 不因此关闭。
MCP 服务本身不调用模型；本轮 Kimi 客户端调用模型做验收，不修改应用库、不执行 017 或构建快照。

交付：实现提交 `15a9cfb` 已推送并创建 [PR #62](https://github.com/sure-660322/Hormuz/pull/62)（Draft）；因真实 SQL 客户端链路待验证，
不宣称 #50 全部验收完成。工作树保留供 Kimi 手测。

## 接口与实现来源

`backend/mcp_server/` 使用官方 Python SDK `mcp==2.3.0`，独立于 FastAPI 网页入口；
两个传输共用 `Adapter`，直接调用业务服务，不调用 LangChain Tool 对象、LLM 或网页动作。
输入 schema 从严格 Pydantic 模型生成，拒绝额外字段；输出为同一 JSON 的 text 和
structuredContent，含 `request_id/tool_name/adapter_version`。汇总和质量说明排在长明细前，
`versions` 回显已有 area/algorithm.version，便于会截断长结果的客户端读取；不删减业务字段。业务结果保留原始状态、
窗口、区域、版本、证据与质量。逐工具输出 schema 声明公共 envelope 与核心字段类型，
只要求 status（错误分支可以没有业务字段）；嵌套证据的细粒度语义沿用各服务契约及 catalog。

| MCP 工具 | 既有服务 | 窗口和输出边界 |
| --- | --- | --- |
| search_ships | agent/ship_search.search_ships | 关键字 1–100 字符；1–20 条身份匹配 |
| get_ship_track | agent/ship_tracks.get_ship_track | 显式时区半开窗 ≤24h；原服务 ≤50,000 点，结果 >2MiB 则拒绝，不能截断 |
| query_strait_passage_statistics | agent/strait_statistics 同名服务 | ≤7 天；每日和全窗计数/质量，不把轨迹缺报补成事实 |
| compare_strait_passage_statistics | agent/strait_statistics 同名服务 | A/B 各 ≤7 天，共享筛选；变化率由服务计算 |
| query_area_ship_snapshot | area_activity/service.query_snapshot | 显式历史时刻，最多 50 船，新鲜度 1–86400 秒 |
| query_area_ship_activity | area_activity/service.query_activity | ≤7 天；最多 30 条访问明细，质量和明细限制沿用服务 |
| compare_area_ship_activity | area_activity/service.compare_activity | A/B 各 ≤7 天，同一区域和筛选，明细限制 30 |
| get_database_schema | query_analytics_policy.load_catalog | catalog v3 元数据；不证明数据库已安装该目录 |
| check_sql | query_analytics_policy.validate_query | 只离线校验；120 秒一次性令牌 |
| execute_sql | query_analytics_executor.QueryAnalyticsExecutor | 原有 SELECT 白名单、角色/清单核验、超时、行数和大小上限 |

没有公开尚未构建的停留/相遇/事件关联能力。网页地图动作不属于本 MCP 接口。
区域参数是完整 `bounds={west,south,east,north}`，省略则每次使用版本化默认区域；
没有隐含“当前视野”、跨调用继承或服务器保存的聊天上下文。SQL 区域仍由 catalog 的
area_id/window 过滤约束，不把自定义矩形自动转为数据库空间 SQL。

## 两种传输与协议兼容

- stdio：由本机客户端启动子进程；每个进程具有独立身份域。stdout 只承载协议，日志写 stderr。
- Streamable HTTP：固定监听 `127.0.0.1`，默认端口 8036、路径 `/mcp`；不提供公网绑定参数。
  SDK 同时处理现代协议和旧初始化协议，本轮开发检查覆盖 `2026-07-28` 与 `2025-11-25`。
  不另建旧 HTTP+SSE 入口；当前 JSON response 模式不提供服务器主动通知/订阅功能。

HTTP 使用无连接会话模式，避免连接复用保存错误上下文。每次请求都验证本机来源和
Bearer 凭据；每个客户端配置不同令牌，身份隔离以凭据为边界。同一凭据的两个进程
视为同一客户端，不能把它们当作互相隔离的用户。这里的静态令牌是本机开发配置，
并非公网 OAuth 实现；只支持自动 OAuth 配置的客户端可能需要额外适配。
SDK 验证 Host/Origin；CLI 关闭代理头信任，不能用 X-Forwarded-For 绕过本机限制。

参考：[官方传输规范](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports)、
[官方 Python SDK](https://github.com/modelcontextprotocol/python-sdk)、
[SDK 旧客户端兼容](https://github.com/modelcontextprotocol/python-sdk/blob/main/docs/run/legacy-clients.md)。

## 启动与配置

从拥有本阶段代码的工作区根目录运行；不要默认从尚未合入这些文件的 main 启动。

```powershell
python -m venv backend/.venv
./backend/.venv/Scripts/python.exe -m pip install -r backend/requirements-mcp.txt
```

仅读取当前进程中显式的 MCP 配置，不复制共享主目录 .env。业务连接使用：

```text
MCP_DB_USER=<预先配置的受限查询账号>
MCP_DB_PASSWORD=<仅保留在本机运行环境>
MCP_DB_HOST=127.0.0.1
MCP_DB_PORT=5432
MCP_DB_NAME=<明确选择的测试库>
MCP_SQL_ENABLED=false
```

Windows 可用 `MCP_DB_PASSWORD_CREDENTIAL=<既有具名凭据>` 代替 PASSWORD，
SQL 账号对应 `AGENT_DB_PASSWORD_CREDENTIAL`；仅在子进程内读取 Windows Credential Manager，
同时设置两种密码来源会拒绝启动。模块不创建凭据、不读取 `.env`。

上述值需要在启动进程环境里设置，文本不是可直接执行的配置文件。数据库角色的创建、
授权与迁移均不由本模块执行。业务查询每次使用独立 Session/事务，先执行 READ ONLY，
设置 statement_timeout=5s、lock_timeout=1s；原服务的时间、扫描及空间边界仍生效。
构造连接引擎不触库。模型相关密钥无需提供，MCP Server 本身不调用模型。

```powershell
./backend/.venv/Scripts/python.exe -m backend.mcp_server --transport stdio
./backend/.venv/Scripts/python.exe -m backend.mcp_server --transport streamable-http --port 8036
```

HTTP 还需 `MCP_HTTP_TOKENS` 环境变量：JSON 对象形式
`{"client-a":"<独立随机令牌，至少32字符>"}`；1–64 个不同令牌，每个 32–256 字符。
客户端携带 `Authorization: Bearer <自己的令牌>`；禁止把真实值写入仓库或启动参数。
stdio 不需要 HTTP 令牌，授权边界为本机进程的启动权限。

若显式启用 SQL，设置 `MCP_SQL_ENABLED=true`、`AGENT_QUERY_ENABLED=true` 及既有
`AGENT_DB_USER/PASSWORD/HOST/PORT/NAME`，登录角色必须是 `agent_reader_login`。
业务与 SQL 的 HOST/PORT/NAME 必须完全一致，否则启动拒绝；用户名不同是正常的。
SQL 目录数据源必须是 nnu_ais，三个 SQL 工具默认不发现。启用开关后只是允许发现，
执行仍由旧执行器核验真实权限、目录及快照清单，失败即拒绝。
应用库 aisdb 未实施 017、未建快照；不得为使 MCP 可用而擅自实施。建议后续验收使用
#48 的独立测试库，先复核其当前状态。

## 调用边界

每进程最多 4 个执行线程，无等待任务队列；每身份每分钟最多 60 次工具调用。
外层查询预算 30 秒，HTTP 请求体 ≤128KiB，工具结果 ≤2MiB。
超时/取消设置取消事件、取消当前 psycopg 查询，并在后续业务 SQL 前检查取消状态；
线程真正结束才释放并发槽。SQL 复用原执行器取消事件与原有进程/数据库并发限制。
边界不是多进程全局业务限流，长时间多 worker 压测仍未做。

check_sql 令牌绑定客户端身份、完整 SQL/参数/purpose、catalog 内容，最多保存 256 个，
120 秒有效、原子单次消费；不同身份无法执行或撤销他人的令牌。修改参数、目录漂移、
过期或重放均拒绝。execute_sql 再次经过旧策略与只读执行器；错误返回后令牌已消费。
这是每条检查/执行链的关闭，不是永久封禁该客户端；新的分析须重新 check_sql。

错误仅返回稳定 code/公开说明，不回显数据库异常、连接串和配置值。审计只记录请求 ID、
已知工具名、状态和 code；不记录凭据、SQL、参数、船名或查询行。保留 ok/partial/no_data/
no_match/not_found 等业务状态；refused/timeout/error 为 MCP 工具失败，零结果不改写为缺报。

## 2026-10-09 开发验证与未验证范围

执行环境为本任务独立虚拟环境，未升级共享主目录依赖；未启动常驻服务。
本轮命令：`python -m pytest backend/tests -q`：**466 passed / 14 skipped**。
新增 50 项测试包含 stdio 真实子进程发现与离线 SQL 检查、HTTP ASGI 请求（2025/2026）、
身份/Host/Origin/大小拒绝、一次性令牌隔离/过期/修改/并发重放、策略拒绝、状态保留、
超时和取消、区域不继承及脱敏。执行器/业务使用替身，绝不查询真实数据库。

Kimi CLI 2.1.1 / Highspeed 经两种传输各完成检索、通行、在场和区域活动四题，
八次真实数据库调用与同条件业务服务一致，见[验收](issue50_kimi_acceptance.md)。
未验证：专用业务角色最小权限；Kimi 真实 SQL 三工具链路；其余业务/多轮/错误题；
网络断开至数据库取消全链；多客户端持续负载、部署与公网身份认证。
协议及四题样本不等于 Issue #50 的全部独立客户端验收。
前端没有改动，因此不重复 build/check:workbench 或浏览器地图验收。

## Kimi Work 桌面个人插件（2026-10-10）

Kimi Code 的 mcp.json 不会自动生成桌面插件卡片。本项目新增
[Hormuz 个人插件](../plugins/kimi/personal/hormuz/README.md)，以相对路径 Node 启动器
读取 Windows 本机配置，启动既有 stdio MCP；SQL 保持关闭。
0.1.1 已经官方校验/登记并验证启动器四题，尚未在用户桌面点击安装或完成桌面回答验收。
入口为 **插件 → 个人 → Hormuz 船舶分析 → ＋ 安装**，完整状态见[记录](issue50_kimi_acceptance.md)。
