# 霍尔木兹海峡船舶态势地图

Vue 地图工作台展示历史船位、轨迹回放、真实新闻聚合事件及有界智能体问答；后端使用 FastAPI、PostgreSQL、PostGIS/MobilityDB。新闻与 AIS 观测不自动构成身份或因果关联。

当前主线已合入案例、自然语言地图动作、态势图表及 Issue #30 UI 升级；各功能的历史验证和未验证范围见[任务计划](docs/agent_development_plan.md)。未正式部署，认证授权、数据展示许可和公开前整改尚未完成。

2026-10-06：废弃 AIS CSV、旧模拟本地输出及示例/中间清单已清理，文档整理已随提交 `2acd881` 合入 main 并推送，任务 worktree 与本地分支已清理。验证和范围见[清理记录](docs/repository_cleanup_2026-10-06.md)。这不清除 Git 历史，也不改变实际应用数据库。

2026-10-09：本地临时输出和遗留任务工作树已整理，独有材料归档，废弃报告配图没有合入 main；主目录未提交文件已清空。范围与残留空目录见[本轮清理记录](docs/workspace_cleanup_2026-10-09.md)；本轮只同步状态文档，不包含本地归档材料。

文档入口：[当前文档索引](docs/README.md) · [前端工作台](FRONTEND_WORKBENCH.md) · [数据库说明](docs/database_setup.md) · [历史交付记录](docs/archive/delivery_notes_2026-10-03.md)。

协作入口：[智能体规则](AGENTS.md) · [GitHub 任务技能](.agents/skills/github-issue-workflow/SKILL.md) · [协作与技能接入](docs/collaboration.md)。使用「处理 #编号」交付 PR，「收尾」合并、同步、清理，或「闭环处理 #编号」完成全过程；共享 main 按指定整合者规则处理。

## 当前进度

下表数量与验收日期来自已记录的历史批次；2026-10-08文档核对不重新验证数据库或模型。下一阶段任务与依赖见[路线图 #46](https://github.com/sure-660322/Hormuz/issues/46)及[任务计划](docs/agent_development_plan.md#2026-10-08-当前摘要与下一阶段路线图)。

| 模块 | 当前状态 |
| --- | --- |
| 船舶与船位 | 应用库已导入七天：4,462 艘、17,921,533 条；来源批次和行号逐日对账 |
| 回放时间 | 应用库七日覆盖 UTC 2026-02-24 16:00 至 2026-03-03 15:59:59；跨日快照、三帧窗口及单船轨迹接口已验证。地图探索首次加载显示起始帧（2026-09-30 本机为 02-24 16:00 UTC）；保留日期刻度、滑杆与播放控件，已移除“展开分析”及其密度图、事件节点、范围缩放。Issue #5 的自然日主刻度已随 [PR #11](https://github.com/sure-660322/Hormuz/pull/11) 合入 main；连续播放 UI 的浏览器验收仍是此前独立单日试点历史结果 |
| 新闻 | 78 个新闻聚合事件、357 条报道（289 条关联事件，68 条未关联；含 2026-09-25 导入的中新网中文批次 67 条，见[导入记录](docs/chinanews_news_import.md)）；45 个事件有代表坐标，36 个有非空事件时间，非空不等于精确到时分 |
| 地图工作台 | **七日应用库跨日 API 与单船点击、轨迹、速度着色浏览器交互已验证；整周浏览器未验收**；原有态势总览与地图探索双视图、模拟回放路径仍在。2026-09-30 已移除态势总览的相遇分析和数据健康区块，取消总览重建按钮及页面初始化的数据健康请求；地图相遇图层与后端接口保留。地图探索的回放轴已移到顶部，桌面新闻区与地图按 2:3 排列，船舶入口仍在左侧；此布局已通过 [PR #7](https://github.com/sure-660322/Hormuz/pull/7) 合入 main。真实 AIS 模式逐窗加载船位快照，选船后按需查询有界轨迹，并可切换实测航速着色及采样点显示。新闻事件与船位独立；应用库状态见上。详见 [前端工作台](FRONTEND_WORKBENCH.md)。Issue #30（UI 与动效升级，#31–#36）已随 [PR #37](https://github.com/sure-660322/Hormuz/pull/37) 合入 main：回放轴紧凑/展开、侧栏与面板调宽、新闻层级与吸顶、总览首屏压缩、案例阶段导航、智能体上下文摘要与地图动作四态反馈均已落地；构建与工作台检查通过，四尺寸浏览器验收未单独补做。 |
| 历史回放 | 原模拟数据分窗加载路径仍在；真实 AIS 以至多 4 帧的小窗口预取和有界缓存连续播放，未下载七日 1,792 万条报位。单船轨迹按时间桶抽稀并分段；1,985 个刻度为旧模拟批次历史结果 |
| 新闻浏览 | Issue #6 已在左侧新增「时间线 / 列表」切换：纵向时间线按来源发生日期分组，宽屏两侧交错、窄屏单侧；日期级事件在当前显示时区进入该日时与地图同步出现，不声称具体小时。[PR #11](https://github.com/sure-660322/Hormuz/pull/11) 已合入 main。[Issue #17](https://github.com/sure-660322/Hormuz/issues/17) 在两种视图的事件分类文字前显示统一分类图标，前端构建、工作台检查和当时可见事件的浏览器核对通过，详见[前端工作台](FRONTEND_WORKBENCH.md)。列表保留封面缩略图，地图事件弹卡保留配图与回退；有发生日期但无代表坐标的事件仍可读详情。缺少 `event_datetime` 的事件放在可展开的「时间未明确」区，仅能阅读详情，不用报道日期补造发生日期或地图回放点。关联报道与来源仍在事件详情中。 |
| MobilityDB / PostGIS | **P0–P4 已实现，P5 部分实现**：派生轨迹、速度着色、事件关联、停留和相遇分析、data-health 已有代码；主回放仍读原始船位，未切换 simplified 派生层。本机新数据的派生表仍为空；旧试验数量与验收见下表 |
| 区域船舶活动分析 | **三个阶段已实现，2026-10-07 修复后复测通过（issue #41，算法 1.0.1，任务分支 codex/area-activity-ui）**：默认项目分析区域、鼠标矩形圈选、时刻在场/时段活动与每日汇总/双时段比较、船型多选、访问证据与地图轨迹，以及三个区域智能体工具与「查看区域分析」回填，共用同一服务。已在任务分支整合最新 main（含 #40/#43）；后端 390 passed / 14 skipped，前端 build/check:workbench/区域 30 项与类型检查通过；14 组 API 的 163 项断言与已有独立复算证据一致。真实 PostgreSQL 20 秒超时映射 503 已验；浏览器结果见[验收报告](docs/area_activity_acceptance.md) §七。**2026-10-08 已随 [PR #45](https://github.com/sure-660322/Hormuz/pull/45) 合入 main（3bcfea1）并同步，任务工作树/分支/验收服务已清理；未部署。用户确认暂不做触屏与纯键盘相关范围，Issue #41 已按已交付范围关闭；并发等验证限制保留** |
| TimescaleDB | 扩展已安装，尚未使用时序表能力 |
| 动态海峡通行统计 | **已实现并经样本验证，PR #42 已合入 main（f555ec7）**：历史窗口按日统计、船型/方向筛选、两期比较、分页证据与地图轨迹；手动面板与两个智能体工具共用服务。2026-10-07 真实模型、面板回填、浏览器查询/比较与轨迹加载已有记录；可见相机最终聚焦、窄屏及综合多轮等限制见[模块说明](docs/agent_tool_strait_statistics.md)，未部署。 |
| 智能体 | **已实现，部分真实链路已验证**：LangChain create_agent，13 个只读业务工具（8 个既有 + 2 个通行统计 + 3 个区域活动）、知识库及受限 SQL 三工具，v4 响应包含地图与分析动作。通行/区域各有真实模型和浏览器样本；跨业务多轮仍待系统验收。SQL catalog v2 仅开放船舶、事件、新闻，2026-09-25 有只读执行及油轮聚合真实模型样本，SQL 浏览器链路未重新验收；**catalog v3（[PR #59](https://github.com/sure-660322/Hormuz/pull/59) 已合入 main）新增 5 张受控分析快照表与必要过滤，已在独立测试库完成构建/对账/真实模型三题/失败关闭与 EXPLAIN 验收（[记录](docs/issue48_sql_acceptance.md)），应用库未实施 017**；产品 MCP Server 未实现。当前契约见[接入说明](docs/agent_integration.md)，后续任务见[任务计划](docs/agent_development_plan.md)。 |

旧模拟批次依据同期新闻构造等待等行为，具体船数、响应时刻、航迹及比例属于模拟假设；其报告仅作历史记录，见[旧批次说明](sim_ais_demo/output_news_aligned/README.md)。用这些 AIS 作研究结论前仍须核验来源、授权、覆盖和完整性。

## 技术与目录

- 前端：Vue 3、TypeScript、Vite、Leaflet；底图使用 OpenStreetMap（可切换自建本地瓦片服务，见下），海事参考使用 OpenSeaMap。
- 后端：FastAPI、SQLAlchemy、Psycopg。
- 本机数据库：PostgreSQL；已核对扩展 PostGIS 3.5.2、MobilityDB 1.3.0、TimescaleDB 2.22.0。
- 区域显示交互 #54：分析面板、边界显示偏好与圈选状态已分离；隐藏保留条件与结果，案例退出恢复偏好，详细坐标收进「区域详情」。用户注释返工已修复案例提示遮挡，压缩探索筛选区并完整显示事件标题，船型支持重要类型与「其它」分组，默认时段来自AIS数据。[PR #58](https://github.com/sure-660322/Hormuz/pull/58) 已于2026-10-09合入 main（`5ac0565`）；本地已同步，5184 预览、工作树登记与本地任务分支已清理，验收资料已归档。验证与清理范围见[本轮记录](docs/issue54_area_boundary.md)；未部署。
- 主数据流：数据库 → FastAPI → Vue / Leaflet；前端地图视野内的船舶筛选仍在浏览器内计算；区域活动分析（圈选矩形、三模式、证据联动）改由后端 `/api/area-activity/*` 计算，前端只展示后端字段，智能体三个区域工具与手动界面共用同一服务。

| 路径 | 用途 |
| --- | --- |
| `frontend/src/api.ts` | API 地址和前端接口类型 |
| `frontend/src/App.vue` | 工作台状态及组件编排 |
| `frontend/src/composables/usePlayback.ts` | 分窗加载及回放 |
| `frontend/src/services/` | 本地空间计算、国家边界图层 |
| `backend/app/routers/` | 船舶、新闻事件、模拟元数据、停留试验路由 |
| `backend/app/models.py`、`schemas.py` | ORM 模型及接口响应结构 |
| `backend/sql/` | 历史迁移与派生表 SQL |
| `sim_ais_demo/config/news_aligned_config.json` | 旧模拟情景配置，仅供历史参考 |
| `sim_ais_demo/output_news_aligned/` | 旧模拟批次的历史验收记录；船舶报位文件已删除 |
| `sim_ais_demo/output/` | 上一批次输出及历史验证记录，不是当前库数量依据 |
| `data/`、`scripts/` | 原始资料、新闻处理和验证脚本 |
| `docs/` | 模块说明、阶段记录和智能体接入规划 |

## 本地运行

以下示例从项目根目录执行，Windows 使用 PowerShell 7。其他成员将第一行替换为自己的克隆目录。

新成员先按[数据库与环境交接](docs/database_setup.md)配置独立环境。目前仓库不提供完整四表交接包，不能执行旧导入步骤；下面命令供已配置根目录 .env 的现有环境使用。

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

### 本地底图瓦片服务（可选）

OSM 官方瓦片在国内网络不可直接访问，可改用自建本地瓦片服务（数据为 OSM，需保留署名）。状态：**已实现并验证（2026-10-06）——13.6 万张 z0–z12 全框下载完成（0 失败）；nginx 服务健康检查、z0/z8/z12 分层级抽查与浏览器端到端验证通过（页面瓦片全部来自 localhost:8080，含 z12 放大；OpenSeaMap 注记层当时网络可达）**。

```powershell
cd D:\my_project\Hormuz
python scripts/download_tiles.py                          # 约 13.6 万张 / 约 3 GB，可断点续传（需代理）
powershell -File deploy/tiles/start-tile-server.ps1     # nginx，端口 8080
```

瓦片源为 OSM 官方（tile.openstreetmap.org）；本机直连会被限速断连，下载脚本默认走本地代理混合端口 `http://127.0.0.1:7897`（可用环境变量 `TILE_PROXY` 覆盖，置空则直连）。范围：z0–z12 全覆盖 bbox 33.5–64°E / 15.5–38°N（全部高亮国家），约 13.6 万张 / 约 3 GB。前端在 `frontend/.env` 设 `VITE_TILE_URL=http://localhost:8080/tiles/{z}/{x}/{y}.png` 即切换（仓库提供 `.env.example`；不设则回退 OSM 官方瓦片）。OpenSeaMap 海事注记层仍为境外服务，未纳入自建范围。部署到服务器时拷贝 `tiles/` 目录与 `deploy/tiles/nginx.conf`（改端口和 alias 路径）即可；若服务器本身可流畅访问国际网络，也可在服务器上直接重跑下载脚本（直连或配代理均可）。

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
| GET | `/ships/{ship_id}/track-window?from=&to=&bucket_seconds=` | 原始 AIS 单船有界轨迹：带时区、≤24 小时，最多读取 10 万条并返回 5,000 采样点；相邻报位超过 90 分钟分段，不依赖 MobilityDB 派生表 |
| GET | `/api/events/{event_id}/ships` | P2 事件×船舶关联：`observed`（模拟轨迹时空邻近，演示，不构成真实因果）与 `mentioned`（原文船名文本证据，`ship` 恒为空）严格分列 |
| GET | `/api/ships/{ship_id}/events?from=&to=` | P2 反向查询某船的 observed 关联事件（时间窗可选、带时区、≤24 小时）；文本提及类不指向模拟船 |
| GET | `/api/dwell?kind=&from=&to=` | P3 停留识别派生层（`ship_dwell`）：GeoJSON FeatureCollection（中心点 + kind/时长/位移半径/最大速度），`kind` 为 `at_anchor`/`drift`/`slow_transit`；返回 manifest 新鲜度与 `stale` |
| GET | `/api/encounters?from=&to=&max_distance_nm=` | P4 相遇分析派生层（`encounters`）：一船对一行（最近距离 NM/米、时间重叠分钟、最近接近点、period），阈值快照入 params |
| POST | `/api/encounters/analyze` | P4 受控同步重建相遇派生层：body `{distance_nm, overlap_min, sample_seconds}`，成功后写表并回 summary；模拟时空邻近，接近不等于实际交互 |
| GET | `/api/data-health` | P5 数据健康：按 `data_source` 的报位数/船数/覆盖区间/中位 gap、全局计数、四张派生表行数 + built_at + stale |
| GET | `/api/area-activity/default-area` | 默认分析区域（`hormuz_core_v1`）的版本、半开边界、跨度与依据；供前端「开启功能/恢复默认区域」使用 |
| GET | `/api/area-activity/ship-types` | 船型候选目录（来自 `ships` 当前取值分布，含保留值 `__missing__`/`__unknown__`），手动多选与智能体共用，不在前端硬编码 |
| POST | `/api/area-activity/resolve-area` | 圈选矩形解析/校验：与查询同一套半开与跨度规则，非法/超限/跨 180° 直接 422，避免前端拿无效区域去查询 |
| GET | `/api/area-activity/snapshot?at=&west=&south=&east=&north=&ship_type=` | 历史时刻区域在场：每船取 `at` 之前最新有效报位（默认 3600 s 新鲜度），过期不计入、不回退到更早的区域内报位；返回在场摘要与有界船舶列表 |
| GET | `/api/area-activity/activity?start=&end=&west=&south=&east=&north=&ship_type=&batch_ids=` | 时段出现/进出/停留：按船去重出现数、观测进入/离开次数、观测支持的停留时长与按 UTC 自然日汇总；窗口 ≤7 天，超限或超读取上限直接拒绝 |
| GET | `/api/area-activity/compare?start_a=&end_a=&start_b=&end_b=&…` | 同一矩形/筛选/算法版本下的 A/B 两时段比较：绝对差与变化率（基期 0 时为 null）、日均分母为窗口实际长度、覆盖可比性警告 |
| GET | `/api/strait-passages/meta` | 动态通行统计元数据：船型选项（含 `__unknown__` 未知/缺失桶）与按 `source_batch_id` 的来源批次覆盖（七日全船批次/案例单船补充区分），不硬编码历史数量 |
| POST | `/api/strait-passages/statistics` | 单时段（≤7 个 UTC 自然日）按日通行统计与全窗汇总：body `{start_at, end_at, ship_types?, direction?}`；与智能体 `query_strait_passage_statistics` 工具共用同一服务，同条件结果一致 |
| POST | `/api/strait-passages/compare` | A/B 两期通行统计比较：两期指标、差值、`(B-A)/A` 变化率（A=0 为 null）、窗口长度与覆盖可比性说明；body 含 a/b 起止与共享筛选 |
| GET | `/api/strait-passages/evidence` | 通行证据明细分页（船舶标识、方向、两端报位时间/位置、观测完成时间；`include_uncertain=true` 附候选及原因）；分页不影响 `matched_count` 完整统计 |
| GET | `/events` | 新闻聚合事件，按最早报道日期排序 |
| GET | `/events/{event_id}/cover` | 按业务事件 ID 读取关联报道配图；从 `NEWS_IMAGE_ROOT` 下受限的 `images/` 路径返回图片，缺失时 404 |
| GET | `/events/{event_id}/news` | 使用业务事件字符串 ID 查询关联报道，不是数据库整数主键 |
| GET | `/simulation/meta` | 模拟船位范围及刻度；`event_count=0` 指不含回放模拟事件，不是新闻数为零 |
| POST | `/agent/analyze` | 智能体问答：问题 + 可选封锁窗口（带时区、≤24 小时）+ 可选多轮 history（≤10 条消息）+ 可选 map_context（回放时刻、唯一参考船 ID）；返回回答、船只、证据、工具结果与 map_actions（轨迹/位置/事件）；错误统一为 detail{code,message,request_id} |
| GET | `/mobility-demo` | 停留分析独立试验页 |
| GET | `/mobility-demo/analysis?area=strait` | 固定两个时窗；区域可选 `strait` 或 `approach` |
| GET | `/mobility-demo/tracks` | 派生轨迹 GeoJSON |
| GET | `/ships/{ship_id}/nearby-events?radius_km=` | 遗留路由仍注册，但引用迁移前事件字段，未适配当前新闻表；不能作为可用能力调用 |

区域活动面板查询真实 AIS，由后端计算；遗留模拟半径查询仅属历史路径。新闻的多地点字段尚未完整展示。

## 智能体当前能力与后续范围

设计见[智能体接入契约与任务](docs/agent_integration.md)。POST /agent/analyze 已注册，前端地图工具栏的「智能体」按钮打开右侧详情浮层，支持多轮提问；回答带船只/事件引用与「地图定位」按钮。船定位到当前回放快照；新闻事件仅在发生时间已进入当前回放帧且有代表坐标时按自身位置定位。

2026-09-26 前端交互改动已从 `codex/agent-chat-ui-main` 快进合入本地 `main`（实现提交 `1d1ae41`）：智能体面板改为消息流和固定输入区，Enter 发送、Shift+Enter 换行；回答用 Markdown 渲染并消毒，真实 v4 `results` 可展开查看工具调用，等待时显示计时与取消。`npm run build`、`npm run check:workbench` 和模拟响应的浏览器交互已验证；本地 5174 页面已打开智能体面板且控制台无错误。真实后端/模型浏览器问答及 SSE 流式输出未在本轮验收或实现。详细记录见[前端工作台](FRONTEND_WORKBENCH.md)与[开发计划](docs/agent_development_plan.md)。

> **2026-09-23 修复记录**：`f14eceb` 复核发现候选实现可重复执行 SQL、超时后后台继续触库、联调脚本导入旧入口。已在本地 `main` 合入修复并通过离线回归：SQL 三工具、知识库和业务工具共用 8 次请求预算；第一次 SQL 成功或终止失败后关闭执行分支，只有第一次未执行的普通语法错误允许一次修正；整体超时取消后等待工作线程退出，再由路由释放请求 Session。联调脚本已切换到 `run_lc_agent`；无密钥返回 SKIP。真实 DeepSeek、独立 PostgreSQL 和浏览器仍待验证。

当前实现采用 **LangChain `create_agent` + 原生业务 Tools + 现有只读业务服务/SQL 安全底座**，集成现有 FastAPI；手写工具循环与固定短语分类器已按计划 §7 移除。

历史验收记录：默认问题曾返回 1 艘 SIM V2 化学品船 019（证据 P1，观测完成于 2026-02-28T18:14:54Z）；v3 三场景联调记录见 [当前契约](docs/agent_integration.md)。本轮未重新调用模型，不能把历史数量当作当前查询结果；自由回答正文尚无逐项事实核验器。

当前地图位置采用所选回放快照，轨迹/证据动作已支持有界时间跳转、选船与聚焦；案例另有分段回放。服务端会话持久化未实现（history 由客户端逐请求携带）。受限 SQL 的 catalog v2/016 已按真实 AIS 适配，目录仅含船舶、事件与新闻；报位级分析仍走业务工具。停留、相遇及 observed 事件关联未构建，不能以零结果推断无真实行为。通行与区域手动面板、智能体调用和 analysis_actions 均已合入，真实模型/浏览器单业务样本见模块验收；综合多轮、SQL 新分析事实层和 MCP 是后续任务。**2026-10-09 更新：catalog v3（5 张受控分析快照表 + 清单核验 + required_filters 必要过滤）已随 [PR #59](https://github.com/sure-660322/Hormuz/pull/59) 合入 main（#48 关闭），独立测试库完成全部验收（[issue48 验收记录](docs/issue48_sql_acceptance.md)）；应用库未执行 017/未建快照，授权后才能在应用库实施。**

受限分析主链 SQL-01～06 已完成。SQL-02～06 文档作为现有安全执行底座的历史验收证据继续保留；它们不再定义下一版交互方式。LC-01～04 已按阶段引入 LangChain 单智能体、轻量知识库、原生业务 Skills 和受限 SQL Agent，并完成等价回归：固定短语分类器和手写模型工具循环已移除（LC-03/LC-04），旧 `runner.py` 已删除。任务状态见 [开发计划](docs/agent_development_plan.md)。

## MobilityDB 时空能力底座：P0–P5 进度

当前底座使用 MobilityDB/PostGIS 构建派生轨迹和分析结果，显式重建并留痕（manifest）。七日 AIS 原始报位已接入；派生层因同船同秒冲突尚未重建，跨来源隔离仍需独立适配和验证。旧的小规模停留试验（历史记录为 10 艘样本船 114 段）只作历史记录。

下表保留 2026-09-19/20 的实施及验收记录；2026-09-21 的有限回归见协作记录，不代表以下历史验收全部重跑。

| 阶段 | 内容 | 状态 |
| --- | --- | --- |
| P0 | 泛化派生表与重建管线（009：`ship_tracks` + `track_build_manifest` + 源表索引；参数化重建脚本；独立核对） | ✅ **已完成**（2026-09-19）：30 艘模拟船 289 段，插值采样误差 0 m、速度 0 不符，manifest 留痕 |
| P1 | 轨迹/速度 API 与着色（`/api/tracks` full/simplified + 前端速度着色） | ✅ **已完成**（2026-09-19）：三分支验证通过，浏览器端到端通过。2026-09-20 增强：着色默认覆盖整条显示轨迹（超 24h 分片取回合并），可切换仅最近 24h |
| P2 | 事件—船舶关联（010：`event_ship_links` mentioned/observed 分列 + 双向 API + 事件面板关联区） | ✅ **已完成**（2026-09-19）：27 条 mentioned + 29 条 observed，逐条独立重算核对通过 |
| P3 | 锚地/等待识别（`ship_dwell` 派生表 + 等待区图层） | ✅ **代码已完成**（2026-09-20 历史验收）：`011_ship_dwell.sql` + 构建脚本（阈值入 manifest，默认锚泊 <3 kn/30 min、慢速 <8 kn/60 min），当时库 231 行（199 锚泊/21 漂航/11 慢速）；GET `/api/dwell` 三分支验证通过；前端图层「停留识别」按需加载打点；独立核对 231 行全一致。当前库 0 行，新数据待验证 |
| P4 | 相遇分析（`encounters` 派生表 + analyze/query API） | ✅ **已完成**（2026-09-20）：`012_encounters.sql` + 构建脚本（候选对时间重叠粗筛 → 等时长重采样 → 逐时刻 geography 距离，默认 3 NM/30 min/60 s），当时模拟库 136 对；真实 AIS 派生层尚未重建；GET/POST 三分支验证通过；当时前端概览「相遇分析」列表 + 点击定位与重新分析按钮（2026-09-30 已移除总览入口，地图图层保留）；独立核对最近距离最大差 19 m |
| P5 | 回放抽稀层 + data-health（回放主链路切换 simplified 层、覆盖率体检） | ✅ **部分完成**（2026-09-20）：`GET /api/data-health` 已实现（源覆盖统计 + 四张派生表新鲜度），当时前端概览「数据健康」区块（2026-09-30 已移除）；回放主链路切换 simplified 层与抽稀保留规则未实施，真实数据接入前补强 |

历史派生层边界：旧模拟批次的 observed 事件关联只是时空邻近演示，不构成真实因果；当前应用库仅有 mentioned 船名文本提及，未核对真实 AIS ship_id。七日真实 AIS 的停留、相遇和 observed 派生层尚未重建。旧批次实施过程中发现的 MobilityDB 陷阱（`tstzspan` 文本参数静默错解析；`&&` 非保守空间粗筛；`nearestApproachDistance` 离散时刻高估；EPSG:32640 跨 UTM 带失真）见技术方案 §3，不代表当前新数据已验收。

完整方案与各阶段验收细节见 [MobilityDB 时空能力底座技术方案](docs/mobility_capability_plan.md)（P0–P5 均已按实施更新）。

## 尚未实现与限制

- 真实 AIS 派生层重建、四艘新闻船关联、整周浏览器与并发验收、来源授权及区域覆盖核实、实时推送、自动刷新、认证授权和正式部署。七日已在本机应用库导入，未推送或部署。
- 智能体契约为 v4：工具集为 13 个只读业务工具（8 个既有 + issue #40 的通行统计 2 个 + issue #41 的区域活动 3 个）+ 知识库工具，受限 SQL 工具（`get_database_schema`/`check_sql`/`execute_sql`）在 catalog v2 口径与 `SHIP_DATA_SOURCE` 一致且功能开关完整时暴露（本机已启用，fail-closed）；多轮 history 仍由客户端逐请求携带。真实 DeepSeek 聚合问答已于 2026-09-25 在本机验收（油轮计数 793）；SQL 浏览器端到端未重验；通行/区域已有独立样本，综合多轮未系统验收。共享业务库统计、认证限流、正式部署、长时间多 worker 压测和无密钥 503 仍未做本轮实测。
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

后端变更需检查 `/health`、`/docs` 和相关接口；数据库变更需回查字段、约束和索引。2026-09-22 SQL-06 worktree：`python -m pytest backend/tests -q` 为 207 passed / 13 skipped；`npm run build` 与 `npm run check:workbench` 通过；一次性 PostgreSQL 17 + 真实 DeepSeek 为 57 passed，容器自动删除；浏览器验证成功表格、待澄清和已拒绝，控制台 0 error / 0 warning。验证覆盖固定 fixture 人工 SQL 对照、真实零结果、注入参数、问题矩阵、真实模型工具选择及恶意文本防回显。未连接或修改共享数据库；`query_analytics` 已注册但仍默认关闭。详见 [SQL-06 综合验收](docs/archive/query_analytics_sql06.md)。

<details>
<summary>历史验证记录（2026-09-14 至 2026-09-20，不代表当前在途版本已通过）</summary>

后端变更需检查 `/health`、`/docs` 和相关接口；数据库变更需回查字段、约束和索引。2026-09-20 MobilityDB P3–P5：011 建 ship_dwell（at_anchor/drift/slow_transit + 位移半径），backend/build_ship_dwell.py 构建 231 行（199 锚泊/21 漂航/11 慢速，阈值入 manifest），scripts/verify_ship_dwell.py 独立核对全一致；012 建 encounters（一船对一行 + params 快照），backend/build_encounters.py 默认参数（3 NM/30 min/60 s）构建 136 对，scripts/verify_encounters.py 独立核对最近距离最大差 19 m；GET /api/dwell、GET/POST /api/encounters、GET /api/data-health 三分支验证通过；前端新增图层「停留识别」（按需加载打点）与概览「相遇分析」（点击定位 + 默认参数重新分析）、「数据健康」区块；npm run build 与 npm run check:workbench 通过；本机无可用无头浏览器， dwell/相遇图层未做浏览器端到端验证（接口与构建已验证）。实测发现并规避三个 MobilityDB 陷阱（`&&` 非保守空间粗筛、`nearestApproachDistance` 离散时刻高估约 30–50%、EPSG:32640 跨 UTM 带失真 >20%，度量距离一律改 geography），详见技术方案 §3；010 event_ship_links 的距离仍在 32640 下计算、受同一失真影响，本次未改动，真实数据接入前迁移。2026-09-20 轨迹与速度着色范围：轨迹默认展示全部已回放报位点，图层尾迹滑杆改为船舶面板「只看最近 24h」开关；速度着色默认与显示轨迹同范围，超过后端 24h 单窗上限时按 ≤24h 分片并行取回、按 segment_no 去重合并（修复长轨迹拖长后早期着色消失的问题），另可切换为仅最近 24h 着色；npm run build 与 npm run check:workbench 通过。2026-09-19 MobilityDB P2：010 建 event_ship_links（mentioned/observed 分列，mentioned 恒不指向模拟船）；backend/build_event_ship_links.py 构建 27 mentioned + 29 observed（半径 50 km 演示级时空邻近）；scripts/verify_event_ship_links.py 独立核对通过（逐条重算距离 ≤2 m、源表指纹未变）；/api/events/{id}/ships 与 /api/ships/{id}/events 三分支验证通过；事件面板新增关联区；无头 Chrome 端到端验证通过（关联区渲染、定位选中船、控制台无错误）。过程中发现并修复 MobilityDB 陷阱：tstzspan 文本经参数传入会静默错解析（atTime 失效），统一改用 span(t, t) 构造器。2026-09-19 MobilityDB P1：/api/tracks（full/simplified）已注册（Repository 层参数化只读 SQL），三分支验证通过（成功/空窗 not_found 与 no_data/422 参数错误）；前端船舶面板新增速度着色（回放窗口量化 15 分钟取派生层，色带 <3/3–8/8–12/>12 kn）；npm run build 与 npm run check:workbench 通过；无头 Chrome 端到端验证通过（着色轨迹与图例渲染正常、控制台无错误，截图为本地临时产物不入库）。2026-09-19 MobilityDB P0：009 建 ship_tracks/track_build_manifest 及源表索引；backend/build_ship_tracks.py 全量重建 30 船 289 段并写 manifest；scripts/verify_ship_tracks.py 独立核对通过（分段一致、采样插值误差 0 m、速度 0 不符、源表指纹未变）；demo 表与 /health 未受影响。2026-09-19 README 同步智能体 v3 多工具版实现状态（docs/agent_integration.md 与 FRONTEND_WORKBENCH.md 已先行更新核对）；纯文档修改，未重新核验数据库数量与构建。智能体前端接入历史验收（原标注日期晚于本次文档核对日，实际验收日期待核对）：npm run build 与 npm run check:workbench 通过，浏览器实测智能体页签问答返回预期结果。2026-09-14 本次文档更新核对了代码、数据库数量和扩展；未重新执行数据生成或迁移。此前同日本地提交前构建、工作台检查及新闻和停留分析接口检查已通过。

</details>

- [当前前端工作台](FRONTEND_WORKBENCH.md)
- [数据库与环境交接](docs/database_setup.md)
- [智能体接入契约](docs/agent_integration.md)
- [LangChain 业务智能体第一版技术方案](docs/langchain_agent_v1_plan.md)
- [MobilityDB 停留试验](docs/archive/mobility_demo.md)
- [MobilityDB 时空能力底座方案](docs/mobility_capability_plan.md)（P0–P4 已实现、P5 部分实现，含历史验收与限制）
- [智能体下一阶段任务与验收](docs/agent_development_plan.md)
- [多会话协作、工作区交接与文档审计](docs/collaboration.md)
- [新闻适配阶段记录](docs/archive/event_adaptation_phase1.md)
- [006 新闻迁移记录](backend/sql/006_migration_report.md)
- [项目智能体工作规则](AGENTS.md)

带日期的阶段记录保留当时结果；当前状态以本页、现有代码及实际数据库核对为准。
# 2026-09-30 典型案例增量

Issue #26 分支新增“中海北冰洋：两次过航尝试”案例入口，串联三个航行阶段、完整五日单船 AIS 回放与六篇报道引用（含后续回应）。独立批次已在本机导入11,640条接受报位；原七日17,921,533条保留，当前总报位17,933,173条（本机本轮核验，非跨环境常量）。默认态势范围排除案例补充，案例使用统一五日时间轴，阶段仅定位时间/视野；固定详情区、四张原文配图与默认关闭报位点、默认速度着色和稀疏方向箭头已验证（地图探索同样默认着色并显示箭头）；数据不随 Git 共享。后端294 passed / 12 skipped、前端构建/工作台、阶段与真实智能体浏览器样本通过；PR #27已合入main（2830ae6），本地同步及任务分支/工作区清理完成；未正式部署。实现、导入、证据与限制见[案例说明](docs/arctic_ocean_case.md)。

## 2026-10-07 北冰洋故事交互（Issue #43）

PR #44 已合入 main（b0ed92f），本地已同步并保留原技能提交，未部署；前端/浏览器样本验证通过：三个航行阶段、从阶段起点播放并在末界停止、采样航速曲线与地图时间定位、便捷收起/退出，以及手机下方故事面板。复用已有真实案例与只读接口，不新增后端业务工具；缺报不解释为停船，报道与AIS分别提供证据。本轮未重新验证真实模型或导入数据。记录见[案例说明](docs/arctic_ocean_case.md#2026-10-07-issue-43-故事与交互升级)。

## 2026-10-08 第二典型案例（Issue #49）

ATHE NOVA已完成双标识对照，复用现有七日AIS实现独立案例、三阶段回放、证据时间定位与案例切换/退出恢复。报道后仍有报位，缺报不解释为击沉或关闭AIS；无新增导入，供应商授权与覆盖完整性仍未核实。已通过后端394 passed/14 skipped、前端构建/工作台和浏览器样本验收；记录见[案例调查与说明](docs/athe_nova_case.md)，[PR #52](https://github.com/sure-660322/Hormuz/pull/52)已于2026-10-08合入main（`39eb3d7`），Issue #49已关闭；本地已同步，任务工作树/分支与预览已清理，未部署。
