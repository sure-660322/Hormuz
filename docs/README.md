# 文档索引

当前功能、实现与验收范围以代码和各批次证据为准。2026-10-06 整理文档入口；本轮未查询数据库或重验历史部署。

## 使用与数据

- [项目说明](../README.md)、[前端工作台](../FRONTEND_WORKBENCH.md)
- [数据库初始化与交接](database_setup.md)
- [真实 AIS 七日导入](real_ais_seven_day_import.md)、[中海北冰洋案例](arctic_ocean_case.md)、[ATHE NOVA证据案例](athe_nova_case.md)
- [新闻批次导入](chinanews_news_import.md)、[每日油轮观测口径](daily_tanker_passages_2026-09-30.md)
- [国家边界与中文标注](country_overlay.md)

## 架构、接口与协作

- [智能体接入契约](agent_integration.md)、[开发任务及验证状态](agent_development_plan.md)
- [LangChain 方案](langchain_agent_v1_plan.md)、[SQL 安全契约](query_analytics_contract.md)
- [Kimi Work 个人插件打包与安装](../plugins/kimi/personal/hormuz/README.md)
- [Kimi 本机 MCP 验收与手测问题](issue50_kimi_acceptance.md)
- [本机 MCP 双传输适配与验证边界](mcp_local_adapter.md)（#50 第一阶段，Kimi 双传输业务样本通过；SQL 客户端待验证）
- [停留工具](agent_tool_dwell.md)、[相遇工具](agent_tool_encounters.md)、[事件关联工具](agent_tool_event_ship_links.md)
- [地图动作](agent_map_actions_issue20.md)、[智能体能力题集](agent_capability_eval_issue15.md)
- [MobilityDB 方案](mobility_capability_plan.md)、[地图性能报告](map_rendering_optimization.md)
- [多会话协作](collaboration.md)、[性能脚本](../scripts/perf/README.md)

## 本轮整理与历史

- [2026-10-06 清理记录](repository_cleanup_2026-10-06.md)
- [2026-10-09 本地工作区清理](workspace_cleanup_2026-10-09.md)
- [历史阶段与交付索引](archive/README.md)

backend/app/services/agent/knowledge 下的 Markdown 是运行时知识库输入，不能按历史文档清除。历史批次报告不代表当前数据库数量；付费 AIS 源数据和数据库备份不通过文档归档自动公开。
