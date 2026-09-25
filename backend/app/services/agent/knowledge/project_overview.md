# 项目概览

## 定位

霍尔木兹海峡海事态势教学项目：以后端数据库 + 前端地图回放展示海峡船舶态势，
并配有问答智能体。项目用于教学演示，不是生产级监控系统。

## 技术栈

前端 Vue 3 + TypeScript + Vite + Leaflet；后端 FastAPI + SQLAlchemy；
数据库 PostgreSQL + PostGIS，并使用 MobilityDB 派生能力（P0–P4 已实现，P5 部分实现）。

## 能力边界

- 船舶与船位为 nnu_ais 七日历史 AIS；events/news 是报道聚合。来源覆盖、授权和船舶实体对应仍需核验。
- 智能体只读：不提供任何写库、导入或派生层重建能力。
- 无实时 AIS、无认证授权、无实时推送、无正式部署。
- 事件—船舶关联目前只有 mentioned 文本提及；observed 派生层尚未基于七日 AIS 重建，均不构成真实因果。
