# 霍尔木兹海峡船舶态势地图

本项目以 Vue 地图工作台展示教学模拟船舶、历史轨迹及已采集的真实新闻报道，后端使用 FastAPI、PostgreSQL 和 PostGIS。新闻聚合事件用于浏览和情景说明，不代表已核实的船舶风险结论。

状态更新：2026-10-04。以下数量已通过当前本机数据库只读查询核对；其他成员的数据库需自行导入，Git 不会同步数据库内容。

## 当前进度

| 模块 | 当前状态 |
| --- | --- |
| 船舶与船位 | 30 艘模拟船、9,354 条清洗后船位；不是实际 AIS |
| 模拟时间 | 2026-02-26 02:43:10 至 2026-03-04 23:59:14，UTC |
| 新闻 | 65 个新闻聚合事件、290 条报道（223 条关联事件，67 条未关联）；40 个事件有代表坐标，27 个有非空事件时间，非空不等于精确到时分 |
| 地图工作台 | 船舶搜索、检查面板、轨迹、航速曲线、图层、国家边界及本地半径船舶查询 |
| 历史回放 | 按不超过 24 小时的窗口加载，5 分钟展示步长，共 1,985 个刻度；取当前时刻前最近报位，不插值 |
| 新闻浏览 | 分类及报道日期排序、关联报道和来源链接、有代表坐标的事件定位；与船舶回放独立 |
| MobilityDB | 已实现局部停留分析试验：10 艘样本船、114 段派生轨迹；不是主回放存储 |
| TimescaleDB | 扩展已安装，尚未使用时序表能力 |
| 智能体 | 最小版已接入：POST /agent/analyze + 前端「智能体」问答页签；大模型 API + 自定义只读查询工具，地图联动后续再做，见下文 |

当前模拟批次依据同期新闻构造等待等行为，具体船数、响应时刻、航迹及比例属于模拟假设。新闻中的真实船名不能与模拟船自动认定为同一船；时空接近不能作为因果证据。参见[当前批次说明](sim_ais_demo/output_news_aligned/README.md)。

## 技术与目录

- 前端：Vue 3、TypeScript、Vite、Leaflet；底图使用 OpenStreetMap，海事参考使用 OpenSeaMap。
- 后端：FastAPI、SQLAlchemy、Psycopg。
- 本机数据库：PostgreSQL；已核对扩展 PostGIS 3.5.2、MobilityDB 1.3.0、TimescaleDB 2.22.0。
- 主数据流：数据库 → FastAPI → Vue / Leaflet；区域船舶查询目前在浏览器内计算。

| 路径 | 用途 |
| --- | --- |
| `frontend/src/api.ts` | API 地址和前端接口类型 |
| `frontend/src/App.vue` | 工作台状态及组件编排 |
| `frontend/src/composables/usePlayback.ts` | 分窗加载及回放 |
| `frontend/src/services/` | 本地空间计算、国家边界图层 |
| `backend/app/routers/` | 船舶、新闻事件、模拟元数据、停留试验路由 |
| `backend/app/models.py`、`schemas.py` | ORM 模型及接口响应结构 |
| `backend/sql/` | 历史迁移与派生表 SQL |
| `sim_ais_demo/config/news_aligned_config.json` | 当前模拟情景配置 |
| `sim_ais_demo/output_news_aligned/` | 当前模拟批次及验收记录 |
| `sim_ais_demo/output/` | 上一批次输出及历史验证记录，不是当前库数量依据 |
| `data/`、`scripts/` | 原始资料、新闻处理和验证脚本 |
| `docs/` | 模块说明、阶段记录和智能体接入规划 |

## 本地运行

以下示例从项目根目录执行，Windows 使用 PowerShell 7。其他成员将第一行替换为自己的克隆目录。

新成员先按[数据库与环境交接](docs/database_setup.md)启动独立 Docker、导入仓库附带的当前模拟船位和新闻数据。已提供 compose.handoff.yaml、空库导入及核验脚本；使用交接环境时按该文档的 handoff_run serve 启动。下面命令供已配置根目录 .env 的现有环境使用。

后端首次安装（已有虚拟环境时跳过创建）：

```powershell
cd D:\my_project\Hormuz
py -m venv .\backend\.venv
.\backend\.venv\Scripts\python.exe -m pip install -r .\backend\requirements.txt
if (-not (Test-Path -LiteralPath .\.env)) { Copy-Item .\.env.example .\.env }
```

在本机配置数据库环境变量，禁止提交密码。已有环境启动：

```powershell
cd D:\my_project\Hormuz
.\backend\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --reload
```

另开终端启动前端：

```powershell
cd D:\my_project\Hormuz\frontend
npm ci
npm run dev -- --port 5174
```

打开 [地图工作台](http://localhost:5174)、[健康检查](http://127.0.0.1:8000/health)、[接口文档](http://127.0.0.1:8000/docs)。

前端 API 地址目前写在 `frontend/src/api.ts`；CORS 目前只允许 `http://localhost:5174`，GET 与智能体 POST 均已放行。

## 已注册接口

| 方法 | 路径 | 状态与语义 |
| --- | --- | --- |
| GET | `/health` | 健康检查 |
| GET | `/ships` | 船舶静态列表 |
| GET | `/ships/map` | 每艘船最新报位，不代表任意历史时刻 |
| GET | `/ships/playback?start_at=&end_at=` | 带时区时间参数，单次不超过 24 小时及 50,000 点 |
| GET | `/ships/{ship_id}/positions` | 单船完整历史位置 |
| GET | `/events` | 新闻聚合事件，按最早报道日期排序 |
| GET | `/events/{event_id}/news` | 使用业务事件字符串 ID 查询关联报道，不是数据库整数主键 |
| GET | `/simulation/meta` | 模拟船位范围及刻度；`event_count=0` 指不含回放模拟事件，不是新闻数为零 |
| POST | `/agent/analyze` | 智能体最小问答：问题 + 可选封锁窗口（带时区、≤24 小时），返回回答、船只、通行证据与统计；错误统一为 detail{code,message,request_id} |
| GET | `/mobility-demo` | 停留分析独立试验页 |
| GET | `/mobility-demo/analysis?area=strait` | 固定两个时窗；区域可选 `strait` 或 `approach` |
| GET | `/mobility-demo/tracks` | 派生轨迹 GeoJSON |
| GET | `/ships/{ship_id}/nearby-events?radius_km=` | 遗留路由仍注册，但引用迁移前事件字段，未适配当前新闻表；不能作为可用能力调用 |

前端区域查询目前只接入模拟船舶，事件近邻关联未启用。新闻的多地点字段尚未完整展示。

## 下一步：智能体后续范围

设计见[智能体接入契约与任务](docs/agent_integration.md)。最小版已实现并联调：POST /agent/analyze 已注册，前端右侧工作面板「智能体」页签可提问并查看带引用的回答（状态、上下文、船只、证据、统计与限制）。

第一版采用 **大模型 API + 自定义只读查询工具**，集成现有 FastAPI，未引入 LangChain、LangGraph 或扣子平台。

已验证：默认问题“封锁后有哪些船还通过了海峡？”返回 1 艘 SIM V2 化学品船 019（证据 P1，观测完成于 2026-02-28T18:14:54Z）；边界、零匹配、数据不足、非法参数与超时用例已按契约核对。

后续再做地图定位、轨迹回放联动与新闻引用扩展。SQL 由开发者编写，本版不是 Text-to-SQL。事件与具体船只的交互关联尚未实现；查询不证明真实因果，零通行必须与数据不足区分。

## 下一步：MobilityDB 时空能力扩展

现有 MobilityDB 仅有固定窗口的停留分析试验（`mobility_demo_segments`）。接下来的计划是以 MobilityDB 为核心建立可复用的时空数据能力底座：轨迹插值与时空计算全部下沉数据库层，派生表显式重建并留痕，统一 API 支撑速度着色轨迹、事件—船舶关联、锚地/等待识别、船舶相遇分析和回放抽稀五类前端能力。设计以未来真实 AIS 数据直接承接为目标：模拟与真实数据共用同一条管线，仅在接入层以 `data_source` 区分，换源不重构。

完整方案见 [MobilityDB 时空能力底座技术方案](docs/mobility_capability_plan.md)（当前为设计稿，未实施）。实施优先级：P0 泛化派生表与重建管线 → P1 轨迹/速度 API 与着色 → P2 事件关联 → P3 停留识别 → P4 相遇分析 → P5 回放抽稀。

## 尚未实现与限制

- 真实 AIS 接入、实时推送、自动刷新、认证授权和正式部署。
- 智能体仅为初步最小版：仅一个查询工具（海峡通行）、仅 DeepSeek 一家模型、无会话持久化；模型主动澄清、大结果集截断、无密钥 503 等路径未实测。
- 新闻事件与船舶回放的自动关联、事件多点完整展示。
- 通用双地图对比、AIS 密度分析；MobilityDB 仅有固定窗口局部试验，扩展规划见上文及 [技术方案](docs/mobility_capability_plan.md)。
- 完整浏览器端到端测试；已有独立 Docker 空库导入及后端接口验证、工作台语义检查和专项脚本。
- 已预留船讯网相关 ORM 字段，但未接入真实供应方；新增字段也未全部暴露给前端。

## 验证与文档入口

前端检查：

```powershell
cd D:\my_project\Hormuz\frontend
npm run build
npm run check:workbench
```

后端变更需检查 `/health`、`/docs` 和相关接口；数据库变更需回查字段、约束和索引。2026-10-04 智能体前端接入：npm run build 与 npm run check:workbench 通过，浏览器实测智能体页签问答返回预期结果。2026-09-14 本次文档更新核对了代码、数据库数量和扩展；未重新执行数据生成或迁移。此前同日本地提交前构建、工作台检查及新闻和停留分析接口检查已通过。

- [当前前端工作台](FRONTEND_WORKBENCH.md)
- [数据库与环境交接](docs/database_setup.md)
- [智能体接入契约](docs/agent_integration.md)
- [MobilityDB 停留试验](docs/mobility_demo.md)
- [MobilityDB 时空能力扩展方案](docs/mobility_capability_plan.md)（设计稿，未实施）
- [新闻适配阶段记录](docs/event_adaptation_phase1.md)
- [006 新闻迁移记录](backend/sql/006_migration_report.md)
- [项目智能体工作规则](AGENTS.md)

带日期的阶段记录保留当时结果；当前状态以本页、现有代码及实际数据库核对为准。
