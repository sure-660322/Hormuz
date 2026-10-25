# 霍尔木兹海峡船舶态势地图

Vue 3 / TypeScript / Leaflet 地图工作台，FastAPI 后端，PostgreSQL / PostGIS 数据库。展示历史 AIS、新闻聚合事件、通行与区域活动分析，并提供 LangChain 单智能体问答。

## 当前功能与边界

| 功能 | 当前范围 |
| --- | --- |
| 地图探索与回放 | 按窗口读取真实 AIS 快照；选船查看有界分段轨迹、实测航速与采样点；不一次下载全部船位 |
| 典型新闻事件 | 四条中文新闻分别关联中海北冰洋、MRAIKH、桐林湾和 EGRET 的真实轨迹，提供来源链接；关联由人工审核，未实现任意新闻自动识船 |
| 案例回放 | 全程或所选阶段约 4.5 秒快速播放；过程/证据页签、阶段定位、退出恢复；灰色虚线仅示意缺报端点，不是实测航迹 |
| 新闻浏览 | 时间线/列表、类型筛选、事件详情及关联报道；无发生时间或坐标时不补造地图点 |
| 通行与区域分析 | 虚拟双门线观测通行；矩形区域在场、时段活动、每日汇总与两期比较；手动面板和智能体共用业务服务 |
| 智能体 | LangChain `create_agent`、知识库、13 个只读业务工具注册项及条件启用的内部 SQL 三工具，v4 响应与地图/分析动作 |
| 外部 MCP | 本机 stdio / Streamable HTTP，固定 7 个只读业务工具；不开放 Text-to-SQL |

截至 2026-10-25 已记录的本机批次：七日全船 AIS 为 4,462 艘、17,921,533 条报位，UTC 2026-02-24 16:00 至 03-03 15:59:59；随后增加北冰洋 11,640 条及新三船 27,255 条案例报位。船舶总数 4,465，新闻 362 篇、事件 82 个。案例批次不扩展普通态势的默认时间范围。这些是历史导入核验值，本轮文档整理没有重查数据库。

新闻描述、AIS 观测与推断须分别表述。缺报不能证明停航、遇袭或关闭 AIS；名称、时间邻近或空间邻近不能证明身份及因果关系。数据来源、授权及覆盖完整性仍需核实。

旧 MobilityDB 停留识别、相遇、observed 邻近关联与 P5 simplified 切换已退出业务范围，不作为建设待办；保留区域活动中的观测船时及新闻 mentioned 文本证据。部分遗留代码和接口仍存在。

## 本地运行

Windows 使用 PowerShell 7，从仓库根目录执行。首次安装：

```powershell
py -m venv .\backend\.venv
.\backend\.venv\Scripts\python.exe -m pip install -r .\backend\requirements.txt
if (-not (Test-Path -LiteralPath .\.env)) { Copy-Item .\.env.example .\.env }
```

在本机配置数据库与模型环境，真实密码和密钥不提交。仓库不包含可直接恢复当前应用库的完整数据包，新环境先读[数据库说明](docs/database_setup.md)。已有环境启动后端：

```powershell
.\backend\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --reload
```

另开终端启动前端：

```powershell
cd frontend
npm ci
npm run dev -- --port 5174
```

访问[工作台](http://localhost:5174)、[健康检查](http://127.0.0.1:8000/health)和[接口文档](http://127.0.0.1:8000/docs)。前端默认使用 Vite 同源代理；不要为解决临时端口冲突擅自改 API/CORS。可选[本地瓦片服务](deploy/tiles/README.md)须保留地图来源署名。

## 开发与验证

修改前读取 [AGENTS.md](AGENTS.md)，使用独立分支和 worktree，保留其他会话修改。协作与任务模式见[协作规则](docs/collaboration.md)。

```powershell
.\backend\.venv\Scripts\python.exe -m pytest backend/tests -q
cd frontend
npm run build
npm run check:workbench
```

按修改范围选择检查；数据库相关测试有独立库要求，skip 不等于通过。完整后端测试不代表浏览器、模型或部署验收。前端目录、后端路由及 SQL 结构分别见 `frontend/src/`、`backend/app/routers/`、`backend/sql/`；实时接口字段以 `/docs` 和 schemas 为准。

## 部署与限制

尚未正式部署；当前没有应用内认证授权、实时推送或服务端会话持久化。整周浏览器回放、持续并发、完整灾备恢复及数据再分发许可未全面验证。SQL catalog v3 已有独立测试库验收，应用库未实施 017 / 未建分析快照，不能把代码合并当成数据库迁移。

2026-10-25 已按要求关闭部署 PR #64，撤下对应远端分支、Release 和标签；部署资料仅保留本地，入口见[文档索引](docs/README.md#本地部署材料)。Git 更新不会自动同步数据库、图片或瓦片。

## 文档入口

[必要文档索引](docs/README.md) · [工作台说明](FRONTEND_WORKBENCH.md) · [当前状态与待办](docs/agent_development_plan.md) · [智能体接口](docs/agent_integration.md) · [典型新闻与轨迹](docs/case_news_entries.md)

2026-10-25 文档精简仅归档历史材料、收敛重复说明并检查引用；原始文档已在仓库外校验备份，没有改动业务代码、配置、数据库或服务。历史验证不能视为本轮复测。
