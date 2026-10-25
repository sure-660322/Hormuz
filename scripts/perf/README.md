# 地图性能复测脚本

保留 Kimi 2026-09-21 测量脚本与 result-old.json / result-new.json 作为历史证据；两者测量口径不同，不能直接计算端到端加速倍数。结论与限制见 ../../docs/README.md#历史材料。

从本目录执行 npm ci，确保系统 Chrome 位于脚本中的 CHROME 路径；其他系统需要自行调整路径。先按根 README 启动前后端，再执行：

```powershell
node driver.mjs 'http://localhost:5174/?perf=1' result.json
```

result.json 是被忽略的本地输出，不覆盖已归档测量。driver-old.mjs 仅用于旧版基线；不能在当前版本运行后仍称其结果为旧版。blank-control、no-tiles-control、diagnose-longtask、scrub-check、which-version 是定位/对照辅助脚本，部分固定使用 5174。它们会启动独立无头浏览器并操作页面，不会自动启动应用服务。

当前整理仅验证构建与工作台检查，未重新执行这些浏览器测量。机器专用的 start-vite.ps1 已移至被忽略的 local-archive/workspace-2026-09-21/；正常启动沿用根 README，不依赖 Kimi 安装路径。

注意：旧长任务与局部渲染探针口径不同，不得直接相除为端到端加速倍数。原测量报告已移至仓库外历史材料。
