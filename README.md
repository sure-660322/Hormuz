# 霍尔木兹海峡船舶态势地图

本项目以 Vue 地图工作台展示教学模拟船舶、历史轨迹及已采集的真实新闻报道，后端使用 FastAPI、PostgreSQL 和 PostGIS。新闻聚合事件用于浏览和情景说明，不代表已核实的船舶风险结论。

工作区整合：2026-09-22。SQL-06 已在独立 worktree 完成固定 fixture、一次性 PostgreSQL 17、真实 DeepSeek 和浏览器综合验收；未连接共享业务库，其余业务数量沿用历史核验记录。其他成员的数据库需自行导入，Git 不会同步数据库内容。本地验收不等于远端发布。

当前协作：用户已确认 Kimi 前端优化结束，成果已纳入本轮整理；性能报告见 [地图渲染优化](docs/map_rendering_optimization.md)，性能数值为 Kimi 的历史测量，本轮未重测。后续新工作使用独立分支和 worktree，见 [多会话协作与交接](docs/collaboration.md)。本页维护当前能力摘要；LangChain 第一版候选实现在 `kimi/agent-lc04`，2026-09-23 完整性复核发现 SQL 成功后可在同一请求内再次执行、整体超时返回后后台仍可继续执行工具，以及真实模型联调脚本仍引用已删除入口，当前未合入 `main`。修复与验收阶段见 [智能体开发任务](docs/agent_development_plan.md)，目标方案见 [LangChain 业务智能体第一版](docs/langchain_agent_v1_plan.md)。

交接包注意：本轮文件校验发现 events/news 的 SHA-256 与 manifest 不符，当前工作区快照待重新导出和独立空库验收，不能沿用历史导入成功结论。详见 [数据库交接](docs/database_setup.md)。

## 当前进度

| 模块 | 当前状态 |
| --- | --- |
| 船舶与船位 | 30 艘模拟船、9,354 条清洗后船位；不是实际 AIS |
| 模拟时间 | 2026-02-26 02:43:10 至 2026-03-04 23:59:14，UTC |
| 新闻 | 65 个新闻聚合事件、290 条报道（223 条关联事件，67 条未关联）；40 个事件有代表坐标，27 个有非空事件时间，非空不等于精确到时分 |
| 地图工作台 | 概览面板与地图工具栏、船舶搜索、检查面板、轨迹（默认全部已回放报位，可切换只看最近 24h）、航速曲线、图层控制、国家边界及本地半径船舶查询；选中船舶支持派生层速度着色轨迹（<3 / 3–8 / 8–12 / >12 kn，默认与显示轨迹同范围，可切换仅最近 24h） |
| 历史回放 | 按不超过 24 小时的窗口加载，5 分钟展示步长，共 1,985 个刻度；取当前时刻前最近报位，不插值 |
| 新闻浏览 | 分类及报道日期排序、关联报道和来源链接、有代表坐标的事件定位；与船舶回放独立 |
| MobilityDB / PostGIS | **P0–P4 已实现，P5 部分实现**：派生轨迹、速度着色、事件关联、停留和相遇分析、data-health 已有代码；主回放仍读原始船位，未切换 simplified 派生层。旧停留试验仍并存；历史数量与验收见下表 |
| TimescaleDB | 扩展已安装，尚未使用时序表能力 |
| 智能体 | `main` **当前实现**仍为 v4 自定义工具循环：POST /agent/analyze + 前端问答页签，注册表含 8 个确定性只读工具及默认关闭的受限 `query_analytics`；LangChain 候选分支已完成主体实现并通过离线回归，但因 SQL 单请求单次执行边界回退尚未合入 |

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
| GET | `/api/tracks/{ship_id}?from=&to=&level=full\|simplified` | P1 派生轨迹：MobilityDB 插值几何 + 对齐速度序列（full）或时间桶抽稀（simplified）；窗口可选、带时区、≤24 小时；返回 manifest 新鲜度与 `stale`、`is_simulated` 标识 |
| GET | `/api/events/{event_id}/ships` | P2 事件×船舶关联：`observed`（模拟轨迹时空邻近，演示，不构成真实因果）与 `mentioned`（原文船名文本证据，`ship` 恒为空）严格分列 |
| GET | `/api/ships/{ship_id}/events?from=&to=` | P2 反向查询某船的 observed 关联事件（时间窗可选、带时区、≤24 小时）；文本提及类不指向模拟船 |
| GET | `/api/dwell?kind=&from=&to=` | P3 停留识别派生层（`ship_dwell`）：GeoJSON FeatureCollection（中心点 + kind/时长/位移半径/最大速度），`kind` 为 `at_anchor`/`drift`/`slow_transit`；返回 manifest 新鲜度与 `stale` |
| GET | `/api/encounters?from=&to=&max_distance_nm=` | P4 相遇分析派生层（`encounters`）：一船对一行（最近距离 NM/米、时间重叠分钟、最近接近点、period），阈值快照入 params |
| POST | `/api/encounters/analyze` | P4 受控同步重建相遇派生层：body `{distance_nm, overlap_min, sample_seconds}`，成功后写表并回 summary；模拟时空邻近，接近不等于实际交互 |
| GET | `/api/data-health` | P5 数据健康：按 `data_source` 的报位数/船数/覆盖区间/中位 gap、全局计数、四张派生表行数 + built_at + stale |
| GET | `/events` | 新闻聚合事件，按最早报道日期排序 |
| GET | `/events/{event_id}/news` | 使用业务事件字符串 ID 查询关联报道，不是数据库整数主键 |
| GET | `/simulation/meta` | 模拟船位范围及刻度；`event_count=0` 指不含回放模拟事件，不是新闻数为零 |
| POST | `/agent/analyze` | 智能体问答：问题 + 可选封锁窗口（带时区、≤24 小时）+ 可选多轮 history（≤10 条消息，user/assistant 各计一条）；返回回答、船只、通行证据、统计、tools_used 与各工具结构化结果；错误统一为 detail{code,message,request_id} |
| GET | `/mobility-demo` | 停留分析独立试验页 |
| GET | `/mobility-demo/analysis?area=strait` | 固定两个时窗；区域可选 `strait` 或 `approach` |
| GET | `/mobility-demo/tracks` | 派生轨迹 GeoJSON |
| GET | `/ships/{ship_id}/nearby-events?radius_km=` | 遗留路由仍注册，但引用迁移前事件字段，未适配当前新闻表；不能作为可用能力调用 |

前端区域查询目前只接入模拟船舶，事件近邻关联未启用。新闻的多地点字段尚未完整展示。

## 智能体当前能力与后续范围

设计见[智能体接入契约与任务](docs/agent_integration.md)。最小版（v2）与 v3 多工具版均已实现并联调：POST /agent/analyze 已注册，前端右侧工作面板「智能体」页签支持多轮提问，回答带船只/事件引用与「地图定位」按钮，可定位到当前回放快照中的船或事件位置。

> **候选实现待修复后整合**：`kimi/agent-lc04` 已使用 LangChain `create_agent` 完成主体重构，并通过后端离线回归与前端非浏览器检查。2026-09-23 复核确认同一请求可连续成功执行两次 `execute_sql`，违反冻结的单请求数据库实际执行最多一次约束；整体超时返回 504 后后台 Agent 线程仍可继续调用工具；`scripts/test_deepseek_toolcall.py` 也仍引用已删除的旧入口。因此 `main` 暂不合入，修复后需重新跑安全回归、真实模型联调和非浏览器验收。完整阶段见 [智能体开发任务](docs/agent_development_plan.md)。

当前旧实现采用 **大模型 API + 自定义只读查询工具循环**，集成现有 FastAPI，尚未引入 LangChain；下一版将由 LangChain `create_agent` 接管编排，继续复用现有 FastAPI、业务服务和 SQL 安全底座。

历史验收记录：默认问题曾返回 1 艘 SIM V2 化学品船 019（证据 P1，观测完成于 2026-02-28T18:14:54Z）；v3 三场景联调记录见 [当前契约](docs/agent_integration.md)。本轮未重新调用模型，不能把历史数量当作当前查询结果；自由回答正文尚无逐项事实核验器。

后续再做：地图定位当前指向回放快照位置，历史轨迹逐点回放联动尚未实现；服务端会话持久化未做（history 由客户端逐请求携带）。受限 Text-to-SQL 已完成 SQL-01～06 并注册为 `query_analytics`，但功能开关默认关闭；只有本地回环绑定、独立只读身份和完整安全配置同时满足时才向模型暴露，不能视为远端可用能力。事件—船舶关联工具已接入，但 mentioned 文本提及与 observed 模拟邻近严格分列，查询不证明真实因果，零结果必须与数据不足或派生层未构建区分。

受限分析主链 SQL-01～06 已完成。SQL-02～06 文档作为现有安全执行底座的历史验收证据继续保留；它们不再定义下一版交互方式。下一阶段按 LC-01～04 逐步引入 LangChain、知识库、现有业务 Skills 和受限 SQL Agent，完成等价回归后移除固定短语分类器和手写模型工具循环。任务状态见 [开发计划](docs/agent_development_plan.md)。

## MobilityDB 时空能力底座：P0–P5 进度

当前底座使用 MobilityDB/PostGIS 构建派生轨迹和分析结果，显式重建并留痕（manifest）。真实 AIS 接入与跨来源隔离仍需独立适配和验证，不能保证只换来源字段即可投入使用。旧的小规模停留试验（历史记录为 10 艘样本船 114 段）仍并存。

下表保留 2026-09-19/20 的实施及验收记录；2026-09-21 的有限回归见协作记录，不代表以下历史验收全部重跑。

| 阶段 | 内容 | 状态 |
| --- | --- | --- |
| P0 | 泛化派生表与重建管线（009：`ship_tracks` + `track_build_manifest` + 源表索引；参数化重建脚本；独立核对） | ✅ **已完成**（2026-09-19）：30 艘模拟船 289 段，插值采样误差 0 m、速度 0 不符，manifest 留痕 |
| P1 | 轨迹/速度 API 与着色（`/api/tracks` full/simplified + 前端速度着色） | ✅ **已完成**（2026-09-19）：三分支验证通过，浏览器端到端通过。2026-09-20 增强：着色默认覆盖整条显示轨迹（超 24h 分片取回合并），可切换仅最近 24h |
| P2 | 事件—船舶关联（010：`event_ship_links` mentioned/observed 分列 + 双向 API + 事件面板关联区） | ✅ **已完成**（2026-09-19）：27 条 mentioned + 29 条 observed，逐条独立重算核对通过 |
| P3 | 锚地/等待识别（`ship_dwell` 派生表 + 等待区图层） | ✅ **已完成**（2026-09-20）：`011_ship_dwell.sql` + 构建脚本（阈值入 manifest，默认锚泊 <3 kn/30 min、慢速 <8 kn/60 min），当前库 231 行（199 锚泊/21 漂航/11 慢速）；GET `/api/dwell` 三分支验证通过；前端图层「停留识别」按需加载打点；独立核对 231 行全一致 |
| P4 | 相遇分析（`encounters` 派生表 + analyze/query API） | ✅ **已完成**（2026-09-20）：`012_encounters.sql` + 构建脚本（候选对时间重叠粗筛 → 等时长重采样 → 逐时刻 geography 距离，默认 3 NM/30 min/60 s），当前库 136 对；GET/POST 三分支验证通过；前端概览「相遇分析」列表 + 点击定位与重新分析按钮；独立核对最近距离最大差 19 m |
| P5 | 回放抽稀层 + data-health（回放主链路切换 simplified 层、覆盖率体检） | ✅ **部分完成**（2026-09-20）：`GET /api/data-health` 已实现（源覆盖统计 + 四张派生表新鲜度），前端概览「数据健康」区块；回放主链路切换 simplified 层与抽稀保留规则未实施，真实数据接入前补强 |

边界声明：observed 事件关联为模拟数据时空邻近**演示**，不构成真实因果；mentioned 为新闻原文船名文本证据，恒不指向模拟船。停留与相遇同属模拟派生层：接近/停留形态是数据库时空计算的客观结果，但不推导真实因果，前端 tooltip 与面板均已标注。实施过程中发现并规避的 MobilityDB 陷阱（`tstzspan` 文本参数静默错解析；`&&` 非保守空间粗筛；`nearestApproachDistance` 离散时刻高估；EPSG:32640 跨 UTM 带失真，度量距离一律走 geography）已记录在技术方案 §3。

完整方案与各阶段验收细节见 [MobilityDB 时空能力底座技术方案](docs/mobility_capability_plan.md)（P0–P5 均已按实施更新）。

## 尚未实现与限制

- 真实 AIS 接入、实时推送、自动刷新、认证授权和正式部署。
- 智能体契约为 v4：注册表含 9 个只读工具，多轮 history 仍由客户端逐请求携带；`query_analytics` 默认关闭且仅允许本地教学环境启用，其他 8 个工具不受开关影响。真实 DeepSeek 工具模式和浏览器三状态已在 SQL-06 隔离验证；共享业务库统计、认证限流、正式部署、长时间多 worker 压测和无密钥 503 仍未做本轮实测。
- 新闻事件与模拟船舶的自动因果关联、事件多点完整展示。事件面板现提供演示级 observed 关联（模拟数据时空邻近，明确标注不构成真实因果）与 mentioned 原文船名，二者严格分列。
- 通用双地图对比、AIS 密度分析；MobilityDB 底座 P0–P4 已实现、P5 部分实现，回放主链路切换 simplified 抽稀层及特征保留规则未实施，见 [技术方案](docs/mobility_capability_plan.md)。
- 派生层 stale 当前只比较 built_at 与源报位最大时间，不能识别所有历史更正/删除；事件关联仍有 EPSG:32640 距离误差限制，相遇分析已使用 geography 采样距离。上述限制不能在智能体中省略。
- 完整浏览器端到端测试；已有独立 Docker 空库导入及后端接口验证、工作台语义检查和专项脚本。
- 已预留船讯网相关 ORM 字段，但未接入真实供应方；新增字段也未全部暴露给前端。

## 验证与文档入口

前端检查：

```powershell
cd D:\my_project\Hormuz\frontend
npm run build
npm run check:workbench
```

后端变更需检查 `/health`、`/docs` 和相关接口；数据库变更需回查字段、约束和索引。2026-09-22 SQL-06 worktree：`python -m pytest backend/tests -q` 为 207 passed / 13 skipped；`npm run build` 与 `npm run check:workbench` 通过；一次性 PostgreSQL 17 + 真实 DeepSeek 为 57 passed，容器自动删除；浏览器验证成功表格、待澄清和已拒绝，控制台 0 error / 0 warning。验证覆盖固定 fixture 人工 SQL 对照、真实零结果、注入参数、问题矩阵、真实模型工具选择及恶意文本防回显。未连接或修改共享数据库；`query_analytics` 已注册但仍默认关闭。详见 [SQL-06 综合验收](docs/query_analytics_sql06.md)。

<details>
<summary>历史验证记录（2026-09-14 至 2026-09-20，不代表当前在途版本已通过）</summary>

后端变更需检查 `/health`、`/docs` 和相关接口；数据库变更需回查字段、约束和索引。2026-09-20 MobilityDB P3–P5：011 建 ship_dwell（at_anchor/drift/slow_transit + 位移半径），backend/build_ship_dwell.py 构建 231 行（199 锚泊/21 漂航/11 慢速，阈值入 manifest），scripts/verify_ship_dwell.py 独立核对全一致；012 建 encounters（一船对一行 + params 快照），backend/build_encounters.py 默认参数（3 NM/30 min/60 s）构建 136 对，scripts/verify_encounters.py 独立核对最近距离最大差 19 m；GET /api/dwell、GET/POST /api/encounters、GET /api/data-health 三分支验证通过；前端新增图层「停留识别」（按需加载打点）与概览「相遇分析」（点击定位 + 默认参数重新分析）、「数据健康」区块；npm run build 与 npm run check:workbench 通过；本机无可用无头浏览器， dwell/相遇图层未做浏览器端到端验证（接口与构建已验证）。实测发现并规避三个 MobilityDB 陷阱（`&&` 非保守空间粗筛、`nearestApproachDistance` 离散时刻高估约 30–50%、EPSG:32640 跨 UTM 带失真 >20%，度量距离一律改 geography），详见技术方案 §3；010 event_ship_links 的距离仍在 32640 下计算、受同一失真影响，本次未改动，真实数据接入前迁移。2026-09-20 轨迹与速度着色范围：轨迹默认展示全部已回放报位点，图层尾迹滑杆改为船舶面板「只看最近 24h」开关；速度着色默认与显示轨迹同范围，超过后端 24h 单窗上限时按 ≤24h 分片并行取回、按 segment_no 去重合并（修复长轨迹拖长后早期着色消失的问题），另可切换为仅最近 24h 着色；npm run build 与 npm run check:workbench 通过。2026-09-19 MobilityDB P2：010 建 event_ship_links（mentioned/observed 分列，mentioned 恒不指向模拟船）；backend/build_event_ship_links.py 构建 27 mentioned + 29 observed（半径 50 km 演示级时空邻近）；scripts/verify_event_ship_links.py 独立核对通过（逐条重算距离 ≤2 m、源表指纹未变）；/api/events/{id}/ships 与 /api/ships/{id}/events 三分支验证通过；事件面板新增关联区；无头 Chrome 端到端验证通过（关联区渲染、定位选中船、控制台无错误）。过程中发现并修复 MobilityDB 陷阱：tstzspan 文本经参数传入会静默错解析（atTime 失效），统一改用 span(t, t) 构造器。2026-09-19 MobilityDB P1：/api/tracks（full/simplified）已注册（Repository 层参数化只读 SQL），三分支验证通过（成功/空窗 not_found 与 no_data/422 参数错误）；前端船舶面板新增速度着色（回放窗口量化 15 分钟取派生层，色带 <3/3–8/8–12/>12 kn）；npm run build 与 npm run check:workbench 通过；无头 Chrome 端到端验证通过（着色轨迹与图例渲染正常、控制台无错误，截图为本地临时产物不入库）。2026-09-19 MobilityDB P0：009 建 ship_tracks/track_build_manifest 及源表索引；backend/build_ship_tracks.py 全量重建 30 船 289 段并写 manifest；scripts/verify_ship_tracks.py 独立核对通过（分段一致、采样插值误差 0 m、速度 0 不符、源表指纹未变）；demo 表与 /health 未受影响。2026-09-19 README 同步智能体 v3 多工具版实现状态（docs/agent_integration.md 与 FRONTEND_WORKBENCH.md 已先行更新核对）；纯文档修改，未重新核验数据库数量与构建。智能体前端接入历史验收（原标注日期晚于本次文档核对日，实际验收日期待核对）：npm run build 与 npm run check:workbench 通过，浏览器实测智能体页签问答返回预期结果。2026-09-14 本次文档更新核对了代码、数据库数量和扩展；未重新执行数据生成或迁移。此前同日本地提交前构建、工作台检查及新闻和停留分析接口检查已通过。

</details>

- [当前前端工作台](FRONTEND_WORKBENCH.md)
- [数据库与环境交接](docs/database_setup.md)
- [智能体接入契约](docs/agent_integration.md)
- [LangChain 业务智能体第一版技术方案](docs/langchain_agent_v1_plan.md)
- [MobilityDB 停留试验](docs/mobility_demo.md)
- [MobilityDB 时空能力底座方案](docs/mobility_capability_plan.md)（P0–P4 已实现、P5 部分实现，含历史验收与限制）
- [智能体下一阶段任务与验收](docs/agent_development_plan.md)
- [多会话协作、工作区交接与文档审计](docs/collaboration.md)
- [新闻适配阶段记录](docs/event_adaptation_phase1.md)
- [006 新闻迁移记录](backend/sql/006_migration_report.md)
- [项目智能体工作规则](AGENTS.md)

带日期的阶段记录保留当时结果；当前状态以本页、现有代码及实际数据库核对为准。
