# 项目概览

## 定位

霍尔木兹海峡海事态势教学项目：以后端数据库 + 前端地图回放展示海峡船舶态势，
并配有问答智能体。项目用于教学演示，不是生产级监控系统。

## 技术栈

前端 Vue 3 + TypeScript + Vite + Leaflet；后端 FastAPI + SQLAlchemy；
数据库 PostgreSQL + PostGIS；旧 MobilityDB 派生停留、相遇、observed 关联及 simplified 回放切换已取消，不作为当前能力建设目标。

## 能力边界

- 船舶与船位为 nnu_ais 七日历史 AIS；events/news 是报道聚合。来源覆盖、授权和船舶实体对应仍需核验。
- 智能体只读：不提供任何写库、导入或派生层重建能力。
- 无实时 AIS、无认证授权、无实时推送、无正式部署。
- 新闻 mentioned 是原文船名提及，不自动认定 AIS 船舶身份或因果。旧 observed 时空邻近关联已退出当前范围，不建议重建。
- 区域活动的观测停留船时与旧 ship_dwell 锚泊识别不同，区域业务继续保留。
