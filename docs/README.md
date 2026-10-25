# 必要文档索引

当前文档用于运行、维护和解释业务口径；不再保存每轮 PR/Issue 验收流水。当前事实以代码、数据库结构和对应批次记录为准。

| 用途 | 文档 |
| --- | --- |
| 项目、运行与协作 | [README](../README.md)、[AGENTS](../AGENTS.md)、[工作台](../FRONTEND_WORKBENCH.md)、[协作](collaboration.md)、[当前任务](agent_development_plan.md) |
| 数据库与来源 | [数据库](database_setup.md)、[七日 AIS](real_ais_seven_day_import.md)、[中新网批次](chinanews_news_import.md) |
| 案例与证据 | [新闻入口](case_news_entries.md)、[三船来源](trajectory_cases.md)、[北冰洋来源](arctic_ocean_case.md) |
| 智能体与 SQL | [v4 接口](agent_integration.md)、[LangChain 架构](langchain_agent_v1_plan.md)、[SQL 安全契约](query_analytics_contract.md)、[分析快照](agent_analysis_semantic_layer.md)、[地图动作](agent_map_actions_issue20.md) |
| 业务算法 | [动态通行](agent_tool_strait_statistics.md)、[历史固定油轮序列](daily_tanker_passages_2026-09-30.md)、[区域口径](area_activity.md)、[区域前端](area_activity_frontend.md)、[区域工具](area_agent_tools.md) |
| 本机接入与资源 | [MCP/DSH 配置](mcp_local_adapter.md)、[Kimi 插件](../plugins/kimi/personal/hormuz/README.md)、[本地瓦片](../deploy/tiles/README.md)、[国界图层](country_overlay.md)、[性能脚本](../scripts/perf/README.md) |

运行时知识库 `backend/app/services/agent/knowledge/` 和插件 SKILL.md 是功能输入，不作为历史文档删除。SQL 006 迁移说明与旧数据包 README 保留各自的安全边界，不是推荐安装入口。

## 本地部署材料

部署资料仅本地保留：`D:/my_project/Hormuz-deployment/local-only-20261025/README.md`。原两个数据包在 `D:/my_project/Hormuz-deployment/2026-10-19/`。PR #64 已关闭且未合并，远端分支/Release/部署标签已移除。旧包不含 10 月 25 日案例增量，后续部署须更新并验证恢复。

## 历史材料

2026-10-25 原始文档在仓库外 `D:/my_project/Hormuz-document-archive/2026-10-25/` 保存：

- `documents-before-trim.zip`：本轮开始时全部 66 份 Git 跟踪 Markdown 的原文，保留原相对路径。
- `manifest.json`：基线 ab9e659、文件大小与 SHA-256；ZIP 内容逐项核对通过。
- `historical/`：本轮移出的 30 份旧验收、交接、清理记录与过时案例资料，可直接阅读。
- `review.json`、`remove.json`、`verification.json`：归档判定、清单及静态检查结果，仅本地保存。

已完成的原案例验收附件仍保留在主目录 `local-archive/`；这里归档原文不搬动数据库、CSV、配置或其他任务工作区。旧 SQL 安全验收全文仍可恢复，当前约束继续由安全契约、代码与测试保留。归档不赋予数据再分发许可，也不改写 Git 历史。

## 本轮验证

仅整理 Markdown，核对本地链接、锚点、原文备份、引用和 Git 差异；不重新运行模型、接口、数据库或浏览器。文档精简已应用主目录。2026-10-25 用户追加授权收尾，本任务进入提交、PR 合并与同步流程；原图标、截图与其他工作树保留。AGENTS.md 仅更新一处归档路径，规则未改变。实际检查结果见仓库外 verification.json。
