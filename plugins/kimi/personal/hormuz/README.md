# Hormuz 船舶分析：Kimi 本机个人插件

面向 Windows Kimi Work 的本地 MCP + Skill 插件。只提供历史 AIS 船舶检索、
有界轨迹、通行统计/比较、区域在场/活动/比较；受控 SQL 三工具保持关闭。
需要本机已有 PowerShell 7、Hormuz MCP 虚拟环境及 Windows Credential Manager 的具名数据库凭据。
本插件不安装依赖、不创建凭据、不运行模型，也不迁移或修改数据库。

## 配置

从包含 MCP 实现的 Hormuz 工作树安装 `backend/requirements-mcp.txt`。
然后用 PowerShell 7 调用本目录的 `configure.ps1`，传入明确的工作树、数据库账号、
具名凭据名称、目标测试库、主机和端口；这些参数均不包含密码。
配置写到 `%LOCALAPPDATA%/Hormuz/kimi-mcp.json`，不进入插件包或 Git。
已有配置默认拒绝覆盖；审查后才可显式传 `-Force`。

0.1.2 清单执行 `pwsh -NoLogo -NoProfile -NonInteractive -File ./scripts/launch.ps1`，
cwd 在插件目录内，避免桌面将 node 改写为失效的 Kimi.exe __plugin_run_node 入口。
启动器从本机配置定位
后端虚拟环境，清除继承的 DB/MCP/受控 SQL 环境设置，再启动只读 stdio Server；
密码仅由后端在进程内读取具名凭据。源目录与 Kimi 的受管副本均使用同一份外部本机配置。
通过原始字节异步转发 stdin/stdout/stderr，保留 Unicode、大结果、EOF 和子进程退出码；
不使用 PowerShell 对象管道传输协议。配置缺失/无效时只向 stderr 写通用错误，
不污染协议 stdout。不读取 .env；SQL 工具保持关闭。

## 登记和安装

使用 Kimi 自带 Plugin Builder 的 `validate_plugin.py` 校验，再通过
`register_personal.py` 或官方 `kimi-daimon kimi-plugin register-personal` 登记，
显式指定当前 Kimi 的 share-dir。插件 ID 为 `hormuz`，展示名为 **Hormuz 船舶分析**。
个人插件详情链接：`kimi-work://plugin?id=hormuz`。

登记后在桌面端 **插件 → 个人 → Hormuz 船舶分析 → ＋ 安装**。
市场管理的插件须走该入口；官方直接安装 CLI 会拒绝，不应移除市场登记或直接编辑
installed.json 来绕过。安装动作将源目录复制为受管副本；之后仅改源目录，重新登记/更新。
没有用 computer use 读取或点击桌面界面时，必须区分登记、安装、工具加载和模型回答的状态。

查询时要求实际使用 Hormuz MCP，并给出 request_id、状态、版本和覆盖限制。
四题基线与手测问题见仓库 `docs/issue50_kimi_acceptance.md`；对应数据批次为独立测试库，
不能将结果视为任何数据库或任意时间的常量。此包没有授予源码或 AIS 数据新的分发许可。

## 2026-10-10 修复与桌面验收状态

0.1.2 源入口已发现 7 工具，ATHE NOVA 身份及通行/区域四题与既有测试库基线对账通过；
启动器和具名凭据相关回归 11 passed。官方 Plugin Builder 校验 0 error / 0 warning，
个人市场已登记 0.1.2、health=ok。官方控制接口 `kimiPlugin.personal.updatePlugin`
（仅 id=hormuz）因运行中 Kimi Code 会话返回 update deferred；回读受管版本仍为
0.1.1。原失败会话中的 Hormuz 重连返回该会话已不存在。

当前为**源修复已验证并登记，桌面更新/真实回答验收阻塞**。不应直接改受管副本、
installed.json 或停止其他任务。等任务自然空闲后，在个人插件详情点“更新”，
通过官方方式加载 0.1.2，再在新查询会话按验收文档四题测试；当前未重启 Kimi。
