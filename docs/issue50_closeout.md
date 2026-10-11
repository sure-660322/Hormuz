# Issue #50 本机业务接入子集收尾

2026-10-11，负责人及本轮整合者 Codex；github-issue-workflow 1.0.0，模式「收尾」。用户确认 DSH 桌面测试成功并授权收尾；本地主目录无其他任务写入已由用户确认。

## 合并与验证

[PR #62](https://github.com/sure-660322/Hormuz/pull/62) 已按本机业务接入子集合入 main，merge commit `b5d8a60db96f95e2cc7b00758d380c9609efc48b`，交付 head `e1577542f4503fdb809ff43f1ab6adc932305893`。GitHub 显示 MERGED；合并前无未解决审查线程、无配置的 CI 检查，未绕过保护或强制合并。不是 Issue #50 的全部验收；#50/#46 保持打开，不部署。

合并前当前交付 head：

```powershell
.ackend\.venv\Scripts\python.exe -m pytest backend/tests/test_mcp_adapter.py backend/tests/test_mcp_transports.py backend/tests/test_mcp_credentials.py backend/tests/test_kimi_plugin_launcher.py -q
.ackend\.venv\Scripts\python.exe -m pip check
```

55 passed，依赖无破损；diff 检查通过。远端合并后主目录经 fetch + ff-only 同步到上述 merge commit；在主目录执行同四份测试（使用保留任务虚拟环境的 Python）再次 55 passed，验证的是合并后源码。首次 fetch 曾因 GitHub 连接失败未同步，后续重试成功；首次缺测试文件的尝试不计作通过。最终收尾文档再做链接及 diff 检查，不重复业务查询或数据库操作。

历史和用户验收：Kimi CLI 双传输四题/八次真实业务调用、源启动器四题对账、DSH headless 四题、桌面协议发现和同连接只读探测分别见 [Kimi 记录](issue50_kimi_acceptance.md) 与 [DSH 记录](dsh_mcp_acceptance.md)。2026-10-11 用户确认桌面身份查询及后续六题均成功；逐题原文/request_id 未采集，也未独立对账这些回答，不改变历史证据等级。

## 保留资源与后续

DSH desktop 和独立 hormuz-mcp-check profile 的 cwd、Python 虚拟环境及运行 workspace 仍引用任务工作树 `codex/mcp-local-transports`。只读核对两份 profile 已恢复正常 launch.ps1、没有临时诊断入口。当前配置和凭据隔离保持原样；原 Kimi 配置、个人市场源路径、本机独立证据和忽略的运行依赖均保留。

因此本轮不删除或归档任务工作树、Python 环境、本地/远端任务分支；不能把仍在运行的 MCP 源目录当作清理对象。没有停止进程、重启 Kimi/DSH、复制密码/密钥/.env、修改数据库或迁移。后续先在独立稳定运行目录准备依赖和配置，验证后仅切换 Hormuz 运行引用，再单独清理；本轮不为清理而改变已通过验收的运行路径。

尚未完成的 Issue 范围：真实外部 SQL schema→check→execute 与专用账号最小权限；Kimi 桌面官方更新及模型问答；DSH HTTP、其余工具/综合多轮、实际网络断开至数据库取消、持续负载，以及公开部署/数据授权。SQL 在当前插件/DSH 入口继续关闭。

状态：远端已合并；本地 main 已同步并记录收尾；文档已同步；任务运行资源保留，清理延期，未部署。下一位负责人须重新核对 Issue、运行路径、会话与资源状态，不能直接删除工作树。
