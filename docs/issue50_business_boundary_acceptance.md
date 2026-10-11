# Issue #50 业务 MCP 边界验收（2026-10-11）

当前状态：外部 SQL 已移除并验证；内部受控 SQL 实现及安全底座保留。Issue #50 已按用户授权调整为外部业务 MCP，不拆分。必要真实安全证据尚有缺口，交付 Draft PR，不使用 Closes、不关闭 Issue、不合并或部署。PR #62 合并后的旧 DSH 运行工作树及已验收配置保持原样；本轮源码并未加载到既有桌面会话。

## 基线、所有权与半成品处理

负责人 Codex；github-issue-workflow 1.0.0「处理」。本机 main 和 origin/main 均核对为 93ec54f；PR #62 MERGED，merge b5d8a60。沿用 codex/issue50-external-sql 独立工作树，未在共享 main 编辑；允许范围为 MCP 模块、对应测试/验收脚本和相关文档。开发不启动前后端端口；只启动本任务短时 stdio 客户端子进程，目标测试库 hormuz_sql_test，127.0.0.1:25432。

中断时只有 __main__.py、credentials.py、launch.ps1 三个未提交修改，无提交/推送/PR。撤回本任务新增的 SQL 启用校验、可选 SQL 元数据及启动器启用分支；launch.ps1 最终与基线源码相同。保留只解析业务具名凭据的通用安全改进，并移除原历史外部 SQL 工具/令牌/执行器分支。未修改任何本机运行配置，未有实验常驻服务，未读取或复制 .env/密码/密钥，未创建数据库角色、改变权限/数据或执行迁移。

仅复用保留 worktree 的已安装 Python 环境运行新目录源码，没有写入其源码或环境、切换分支/升级依赖或影响 DSH/Kimi。具名业务凭据仅由 MCP 后端子进程按既有机制在内存中使用；SDK 客户端只读取获授权的非敏感运行元数据。

## 验证命令与源码

源码提交 `04ee93a42efd21db70c76ed766a1bf1045997db1`（04ee93a）；adapter 0.2.0。证据 JSON 另存源码 SHA256，后续文档提交未改变运行代码。

```powershell
python -m pytest backend/tests/test_mcp_adapter.py backend/tests/test_mcp_transports.py backend/tests/test_mcp_credentials.py backend/tests/test_kimi_plugin_launcher.py backend/tests/test_agent_sql_tools.py backend/tests/test_query_analytics_policy.py backend/tests/test_query_analytics_executor.py backend/tests/test_query_analytics_v3_snapshots.py -q
python scripts/issue50_business_mcp_acceptance.py --runtime <既有非敏感运行元数据 JSON> --output <本机证据路径>
python -m pip check
git diff --check
```

相关回归 **228 passed / 7 skipped**；7 项是未启用的真实 PostgreSQL 内部 SQL 执行器集成 fixture，不能列为本轮真实 SQL 验收。内部工具注册、schema/check/execute 假执行器路径、AST/必要过滤、catalog 漂移、并发/结果限制离线检查通过，内部 SQL 文件未修改。pip check 无破损。前端和 FastAPI 路由未改，不重跑无关前端或全量业务检查。

中途一次测试编辑错误导致断言失败，已修正后得到上述最终结果；一次 diff 检查发现尾部空行，已修正。失败不计通过。

## 独立协议与真实业务样本

客户端 Python MCP SDK 2.3.0 / stdio，独立 ClientSession + 实际 MCP 子进程；不是内部函数调用或模型问答。正常关闭/旧开关 true 两次初始化均返回相同 7 工具；SQL 三工具共 6 次直接调用全部 refused / TOOL_UNAVAILABLE。设置无效的旧开关也能启动并拒绝 SQL，由子进程协议回归覆盖。SQL 专用凭据 sentinel 未被读取；HTTP ASGI 协议回归也验证发现与直接调用拒绝，并使 dispatch 接缝失败以证明不进入执行路径。

完整工具清单、输入、状态、request_id、版本、窗口、汇总与限制见[JSON](issue50_business_boundary_acceptance.json)。业务、空结果及非法参数如下：

| 工具 | 状态 | request_id |
| --- | --- | --- |
| get_database_schema | refused | req_080d4db985c74bb0bb6f813f07592154 |
| check_sql | refused | req_f6818cf3eb70483e81a095dc0744d55b |
| execute_sql | refused | req_d2369029422042bab194566ee94dea7e |
| search_ships | ok | req_115a2cc201e94666bea41ce0170eae71 |
| get_ship_track | no_data | req_61f69b2456264314851facafeb79ecbd |
| query_strait_passage_statistics | partial | req_bda76d72170543a5aa5fb0d0fabafa83 |
| compare_strait_passage_statistics | partial | req_c2c9a4597343421b95105994e0deffec |
| query_area_ship_snapshot | ok | req_c0a598703f2b46f7b5c8e86308a6cc7a |
| query_area_ship_activity | partial | req_cde57a69b62244b6a2781c347b9de01b |
| compare_area_ship_activity | partial | req_b38b52df40ef4772ace16913391fddf4 |
| search_ships | no_match | req_b8527ee92f1046dfb0eae70284acc9a8 |
| search_ships | error | req_084beaf916cb4358a6db56346d502a12 |

身份查询 ID 628 / MMSI 334931000 / IMO 9188116；2026-02-26 UTC 单日通行 132 次、131 船、81 inbound / 51 outbound，8 不确定候选；默认区域 12:00 UTC 在场 199；该日活动 477 船、229 进入、224 离开、4719.027 船小时。脚本自动对比 2026-10-10 DSH 历史同条件业务基线，PASS；本轮没有重算内部函数基线。两项比较亦返回 partial 与 A/B 汇总，所选 ATHE NOVA 全天轨迹返回 no_data（0 点），空船名查询 no_match，非法 limit=True 返回 INVALID_TOOL_ARGS，不冒充成功或无真实行为。

DSH 已有独立真实模型业务四题对账及桌面用户确认，见[历史记录](dsh_mcp_acceptance.md)。本轮未调用模型、未修改 DSH profile；Kimi 桌面未完成更新/问答情况仍保留，但不是唯一客户端要求。

## 安全覆盖与 #50 剩余验收

| 要求 | 本轮证据与状态 |
| --- | --- |
| 公开能力边界 | 7 工具；stdio/HTTP 无 SQL，旧环境变量及直接调用不能重开；启动器 sql 配置拒绝；已验证 |
| 参数、状态、版本和质量 | 严格参数与真实业务/空结果；text 与 structuredContent 一致、前置汇总/超限整项拒绝；已验证 |
| 无凭据/身份越权 | 具名缺失与冲突 fail closed 替身测试；HTTP 无/错 bearer、非本机、Host/Origin 拒绝；已验证（离线/ASGI） |
| 跨客户端上下文 | stateless、可信 HTTP 身份、不同客户端自定义区域后默认查询不继承；已验证（替身） |
| 超时/取消/并发/限流/脱敏 | 事件与 driver.cancel、后续 SQL 拦截、线程结束前槽位保留、MCP_BUSY、每身份限流及异常/日志不泄漏测试；已验证（替身） |
| 真实网络断开→DB 取消无残留 | 未验证；缺必要真实链路证据，保留 Draft |
| 专用业务账号最小权限 | 现有凭据不推定满足最小授权；本轮未核验，不创建账号/改权限；保留 Draft |
| 持续与多进程负载 | 未验证；无全局业务限流承诺 |
| 文档、Issue、PR | 已同步当前与历史边界；Issue 保持 OPEN；关联 Draft PR，不合并/关闭 |

因此调整后的 #50 **尚未满足全部验收**。下一步只在获准独立环境补齐业务最小权限与真实取消/负载证据；不重新开放外部 SQL。公网 OAuth/用户授权、数据许可、成本预算和部署均未实施。

可直接在 DSH 业务会话测试：「实际调用 Hormuz MCP 查询 ATHE NOVA，给出 ID、MMSI、IMO、request_id」；「查询 2026-02-26 00:00 UTC 至 2026-02-27 00:00 UTC 海峡通行统计，保留不确定候选、状态、版本和覆盖限制」。当前桌面沿用旧运行源码，这些业务问题可继续使用；本轮固定边界需在经审查的新运行目录加载后才能作为桌面版本验收。
