# SQL-04 独立只读执行器

状态：**已验证**（2026-09-21，worktree `D:/my_project/Hormuz-codex-sql04`，分支 `codex/sql04-executor`，共同基线 `af888e9`）。本阶段完成执行安全边界；后续 SQL-05 已接入 runner/schema/前端，但功能开关仍默认关闭。

## 交付内容

- `backend/app/services/agent/query_analytics_executor.py`：独立配置、独立 SQLAlchemy/psycopg 连接池、SQL-03 强制校验、数据库实物 catalog 核验、只读事务、结果流式读取、取消/超时、并发门、稳定错误映射和结构化审计。
- `backend/tests/test_query_analytics_executor.py`：4 项纯离线边界测试及 7 项 PostgreSQL 集成场景，共 11 项；普通后端回归不连接数据库，集成项默认跳过。
- `scripts/verify_query_analytics_executor.ps1`：创建随机回环端口的一次性 PostgreSQL 17，加载固定 fixture、013 迁移和随机运行时密码，运行专项测试后自动删除容器。
- `.env.example`：继续默认 `AGENT_QUERY_ENABLED=false`，增加本地绑定地址占位；真实密码不写入 Git、日志或测试输出。

执行器不导入 `backend/app/database.py`，不会使用或回退到应用主连接。启用时要求登录身份精确为 `agent_reader_login`，配置缺失、非回环服务绑定、角色/成员关系/权限异常、额外对象、字段或视图定义漂移均 fail closed。

## 强制执行链

每次调用依次执行：

1. 校验 request/call 标识，加载 catalog v1；
2. 调用 SQL-03 校验器，从同一棵已接受 AST 生成最终规范化 SQL；
3. 非阻塞取得每进程 2 个执行槽之一；
4. 专用连接内开启事务并强制 `READ ONLY`、`search_path=pg_catalog`、`statement_timeout=5s`、`lock_timeout=1s`、`idle_in_transaction_session_timeout=5s`；
5. 通过 4 个事务级 advisory-lock 槽实现跨进程非排队并发门，并保留数据库登录角色 `CONNECTION LIMIT 4` 作为第二层边界；
6. 使用当前只读连接核对 PostgreSQL 主版本、登录/边界角色属性、成员关系、schema/TEMP/CREATE 权限、agent_data relation/function 精确清单、视图 owner/SELECT、字段顺序/类型/可空性、定义哈希及源表不可读；
7. 只执行 SQL-03 返回的规范化 SQL，通过服务端游标分批读取，最多返回 500 行或 256 KiB；读取到下一条超限记录即停止并标记 `truncated=true`；
8. 成功显式提交，失败/取消显式回滚；所有会话设置均为事务局部，连接池归还时再次 rollback 清理。

可选 `cancel_event` 会由监控线程调用 psycopg 连接取消；数据库 `57014` 和锁超时 `55P03` 统一映射为 `AGENT_QUERY_TIMEOUT`。连接/目录异常和权限异常不暴露数据库正文，统一对外为 503 `AGENT_QUERY_UNAVAILABLE`；策略拒绝为 HTTP 200 `AGENT_QUERY_REFUSED`；并发满为非排队的 `AGENT_QUERY_BUSY`。SQL-05 需按冻结契约把这些稳定结果接入顶层状态，不能放宽或自动重试。

## 审计边界

审计记录 request/call/query ID、原始及规范化 SQL 的 SHA-256、参数与 purpose 的 SHA-256、catalog 版本/核验时间/检查数、实际视图、耗时、返回行数/字节数、截断状态、稳定错误码和目标查询是否已执行。日志不记录 SQL 正文、参数值、purpose 正文、连接串、用户名密码或数据库异常正文；catalog 漂移只记录稳定的差异类别。

## PostgreSQL 17 隔离验证

执行命令：

```powershell
.\scripts\verify_query_analytics_executor.ps1 -Python 'D:\my_project\Hormuz\backend\.venv\Scripts\python.exe'
```

使用官方 `postgres:17` 固定 digest、一次性数据库 `hormuz_sql04_verify` 和随机回环端口；未连接共享数据库。结果：`11 passed`，随后脚本报告 `PASS: SQL-04 isolated PostgreSQL 17 executor verification completed.`

覆盖：默认关闭、专用角色/本地绑定配置、策略拒绝不触库、date 真实绑定、正常/零行/聚合/批准 JOIN、500 行截断、256 KiB 增量截断、catalog 哈希漂移 fail closed、锁超时、请求取消后无遗留活动查询、权限失败稳定映射、全局并发非排队拒绝，以及审计日志不含 SQL/参数/密码。

完整后端回归：

```powershell
& 'D:\my_project\Hormuz\backend\.venv\Scripts\python.exe' -m pytest backend/tests -q
# SQL-04 分支当时：140 passed, 7 skipped, 1 warning
```

7 个 skip 是上述需要一次性 PostgreSQL 的集成用例；专项脚本已单独全部执行。SQL-02 验证器按新的固定 search_path 哈希规则复跑：`PASS ... (56 checks)`。

## 验证中修正的 SQL-02 指纹条件

PostgreSQL 17 实测表明，`pg_get_viewdef(regclass, false)` 会根据调用者 `search_path` 选择是否给底层对象加 schema 前缀。SQL-02 原验证器以管理员默认路径计算哈希，运行时只读角色固定 `search_path=pg_catalog`，二者会对同一视图产生不同文本。

本轮没有修改视图定义，只把 catalog 的指纹条件补全为 `search_path=pg_catalog`，重新生成三个 SHA-256，并同步 SQL-02 验证器与说明。这样运行时读者可以在冻结的安全路径下直接复现哈希；篡改哈希测试仍会 fail closed。

## 仍未实现或未验证

- SQL-05 后续已注册 `query_analytics` 并完成 HTTP/前端类型及最小展示接入；SQL-06 已完成真实模型和浏览器交互验收，共享业务数据统计仍未验证。
- SQL-05 必须把实际服务绑定地址传入并保持本地限制；本模块只能校验其配置值，不能独立证明外层 uvicorn 未被其他参数绑定到远端地址。
- 多进程边界已在真实 PostgreSQL 中用 4 个全局锁槽验证“满时立即拒绝”；未做多 worker 长时间压力测试。

2026-09-21 后续整合验证：SQL-04 与 AG-03～05 合入 main 后，后端全量 `167 passed, 7 skipped`，前端 build/check:workbench 通过；本专项的一次性 PostgreSQL 17 仍为 11 项通过，SQL-02 仍为 56 项通过。未连接共享数据库。
