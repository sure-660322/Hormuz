# Issue #50：Kimi 本机业务 MCP 验收

2026-10-09，Codex 在 `codex/mcp-local-transports` 工作树执行；基线 `74dcbdc`。
用户追加授权 Kimi 测试和 PR 交付。本批次 stdio、Streamable HTTP 各完成同一组四题，
**8 次真实 MCP 调用全部与同条件既有业务服务结果一致**。仅为本机业务子集验收，
受控 SQL 的真实客户端链路未验证，#50/#46 不关闭；未合并、未部署。

交付：实现提交 `15a9cfb` 已推送并创建 [PR #62](https://github.com/sure-660322/Hormuz/pull/62)（Draft）；因真实 SQL 客户端链路待验证，
不宣称 #50 全部验收完成。工作树保留供 Kimi 手测。

## 环境与证据

- 独立客户端：官方 `@moonshot-ai/kimi-code 2.1.1` CLI，模型
  `kimi-code/kimi-for-coding-highspeed`（K2.7 Code Highspeed）。默认模型本批次遇到
  429 引擎过载，成功验收使用 Highspeed；不把失败重试计为成功。
- CLI 使用独立 Kimi home/cache，复用既有登录；测试 profile 只允许
  `mcp__hormuz__*`，无文件、Shell、浏览器或子智能体工具。全程未用 computer use。
- 数据库：已有独立测试库 `hormuz_sql_test`，本机端口 25432。通过 Windows
  Credential Manager 的既有具名凭据在子进程内解析连接密码，不读取 `.env`，
  不把真实密码写入配置、命令行、日志或 Git。业务登录角色为既有 `aisdb`，
  本模块对查询事务设置 READ ONLY；本轮没有创建/授权专用业务登录角色，
  不能将此样本当作最小数据库权限验收。
- stdio：客户端启动独立 Python 子进程。HTTP：临时监听 `127.0.0.1:8046/mcp`，
  每次请求携带进程内生成的临时 Bearer 凭据；测试结束关闭本任务服务。
- SQL 开关为 false，仅发现 7 个业务工具。未取得专用 `agent_reader_login` 的
  运行凭据，未绕过原执行器，不复用业务账号开启 SQL。
- 原始 CLI 协议/回答与直接业务基线保留在本任务 Git 忽略的
  `local-archive/kimi-acceptance/`、`local-archive/kimi-baseline.json`。
  [精简证据 JSON](issue50_kimi_acceptance.json)记录八次输入、实际 request_id、
  状态、指标、版本和被测 MCP 源文件 SHA-256；不含凭据或船舶列表。

## 同条件对账

时间均为 UTC，统计窗为 `[2026-02-26 00:00, 2026-02-27 00:00)`；
区域为默认 `hormuz_core_v1 / 1.0.0`，区域算法 `1.0.1`。

| 问题 / 工具 | 内部业务基线 = Kimi stdio = Kimi HTTP | 状态 |
| --- | --- | --- |
| ATHE NOVA / search_ships | ship_id 628，MMSI 334931000，IMO 9188116 | ok |
| 全天通行 / query_strait_passage_statistics | 通行 132，独立船 131，入湾 81，出湾 51，不确定候选 8 | partial |
| 12:00 在场 / query_area_ship_snapshot | 区域内 199，评估 960，新鲜度 3600 秒 | ok |
| 全天区域活动 / query_area_ship_activity | 出现船 477，观测进入 229，离开 224，累计 4719.027 船小时 | partial |

通行版本 `strait-gates-v1+stats-2026-10-07`。基线是同测试库的既有服务调用，
没有以当前网页应用库结果冒充同条件基线，也未再次独立校准算法。
两个客户端回答均保留 request_id、状态、区域/算法/通行版本及覆盖限制。
partial 未被写成全部真实交通；名称未被自动认定为新闻实体，缺报未推断成事故。

首次 Highspeed 运行发现 Kimi 对长结果截断，区域活动汇总位于截断点后。
修复后将汇总、质量说明前置，并添加由既有 area/algorithm.version 派生的紧凑
`versions` 字段；原业务字段和值完整保留。最终双传输四题均能直接回答汇总。
客户端仍可能截断大明细，不能宣称外部模型已读到全部轨迹/访问证据。

## 回归与剩余范围

最终代码执行 `backend/.venv/Scripts/python.exe -m pytest backend/tests -q`：
**466 passed / 14 skipped**，新增 MCP 检查 50 项（协议、安全边界、取消、
一次性 SQL 令牌、具名凭据选择和客户端截断回归）。真实数据库八次业务调用单独验证，
不能用这些离线替身测试证明真实 SQL 权限或真实取消链路。

待验证：专用业务角色最小权限、真实 Kimi schema→check→execute、其他三个业务工具
及多轮/空结果/错误题、网络断开至数据库取消全链、多客户端持续负载与部署身份体系。
本批次不修改源数据、不迁移/重建快照、不停止共享数据库或 Kimi Desktop。

## 用户手测

2026-10-10 用户反馈：Kimi 桌面插件列表未见 Hormuz。只读检查确认
`C:\Users\18242\.kimi-code\mcp.json` 的 hormuz 条目及启动文件存在；安装的
Kimi 桌面应用版本为 3.2.15。此前配置的是 **Kimi Code MCP**，没有制作或安装
Hormuz 桌面插件，不能将 CLI 验收或配置文件存在视为该桌面应用接入成功。

Kimi Code 的官方说明将 MCP 配置与插件清单区分；Kimi Work 的个人插件须经
创建/转换、登记、安装流程，见[个人插件说明](https://www.kimi.com/help/plugins-and-skills/create)。
若使用 Kimi Code，配置入口见[官方 MCP 文档](https://www.kimi.com/code/docs/kimi-code-cli/customization/mcp.html)。
2026-10-10 追加授权后：[Hormuz 个人插件](../plugins/kimi/personal/hormuz/README.md)
0.1.1 已制作，Kimi 自带 Plugin Builder 校验 0 error / 0 warning，官方 CLI
已登记到当前桌面端的 personal 市场，回读 id/version/sourcePath 通过、health=ok。
Windows 本机运行配置保存在 `%LOCALAPPDATA%/Hormuz/kimi-mcp.json`，只含目标元数据
和具名凭据名称，无密码；插件本身仅有相对路径启动器及 Skill，不携带本机配置。
启动器实测发现 7 工具，四题实际查询与同条件既有基线一致；缺失配置时 exit 1，
stdout 为空、stderr 为通用错误。未改变后端实现，因此没有重复运行不相关回归。

**状态：已登记，未安装，桌面会话加载/回答待用户验证。** 官方 CLI 拒绝直接安装
市场管理插件，要求使用个人市场安装入口；独立安装实验也缺运行时网关 key，未注入假 key
或复制真实登录凭据来绕过。用户在 **插件 → 个人 → Hormuz 船舶分析 → ＋ 安装**；
详情链接 `kimi-work://plugin?id=hormuz`。重新打开插件页刷新条目，无需停止现有会话。
全程未用 computer use。下列问题应在桌面安装完成且发现工具后再测。

以下问题可以逐条发送，要求 Kimi 实际调用 Hormuz MCP 并列出状态与 request_id：

1. 查找 ATHE NOVA，给我船舶 ID、MMSI、IMO。名称相同能否确认它就是新闻里的船？
2. UTC 2026-02-26 00:00 到 2026-02-27 00:00，全部船型通行次数、独立船数、入湾/出湾次数和不确定候选各是多少？说明判定版本与覆盖限制。
3. UTC 2026-02-26 12:00，默认分析区域内观测在场多少艘船？说明区域版本、新鲜度和过期报位的处理。
4. UTC 2026-02-26 00:00 到 2026-02-27 00:00，默认区域出现船数、观测进入/离开次数、累计船小时各是多少？缺报区间是否计入？
5. 查询 ATHE NOVA 从 UTC 2026-02-26 00:00 到 2026-02-28 00:00 的连续轨迹。如果超过工具窗口，请说明限制，先不要自行拆分或缩短。

前四题预期见上表；第 5 题轨迹窗口超过 24 小时，应告知限制或返回
`INVALID_TOOL_ARGS`，不能伪称取得完整两日轨迹。第 5 题为提供给用户的待手测项，
本批次未跑真实模型拒绝题。

## 2026-10-10 用户桌面安装后反馈

用户截图显示 Skill 已加载但查询工具未发现。只读回查 installed.json 确认
hormuz 0.1.1 已安装并 enabled=true；本机 `%LOCALAPPDATA%/Hormuz/kimi-mcp.json`
确实存在。桌面日志确认新任务已解析 hormuz 插件，用户会话协议仅发现 GitHub MCP，
没有 Hormuz 查询工具。Kimi 的“本机配置不存在”来自 Bash 中反斜杠/正斜杠混合路径的
失败检查，不能作为真实配置缺失证据。

当前状态更新为 **已安装启用，桌面 MCP 工具发现失败，启动原因待查**；
不能直接归因未重启，尚未请求或执行桌面重启，不修改插件或配置，不用 computer use。
前述“待点击安装”为该次登记时的状态；不代表安装已完成真实桌面查询验收。
