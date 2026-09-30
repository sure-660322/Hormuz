# 霍尔木兹海峡船舶态势地图

当前交付：2026-09-30 [PR #23](https://github.com/sure-660322/Hormuz/pull/23)（Issue #21，油价 × 油轮通行量双轴展板）已合入 `main`（`7447fcb`），任务 worktree 与本地/远端分支已清理；5174 可用最新 main 查看。上一个交付：[PR #22](https://github.com/sure-660322/Hormuz/pull/22) 已合入 `main`（`ac46b10`）。未正式部署。

> 2026-09-30 Issue #21（PR #23 已合入 main，浏览器可视验收待用户在 5174 确认）：态势总览新增数据展板「油价 · 油轮通行量」双轴折线图（ECharts 按需引入），覆盖 AIS 回放窗口（2026-02-25 至 2026-03-03）前后各一周。油价数据取自 [EIA RBRTED 日度现货价](https://www.eia.gov/dnav/pet/hist/RBRTED.htm) 并于当日对照官网核对；通行量为本机 AIS 观测统计（UTC 归日、虚拟门线口径，独立 SQL 复核一致，报告 [daily_tanker_passages_2026-09-30](docs/daily_tanker_passages_2026-09-30.md)）。横轴为连续日历日，油价周末无报价显示断点；两条序列有开关控制，开启时以描线动画渐入，底图（坐标轴/网格/回放窗口高亮）常驻。静态数据在 `frontend/src/domain/brentPrices.ts` 与 `frontend/src/domain/tankerPassages.ts`。`npm run build` 与 `npm run check:workbench` 通过，开关交互经 DOM 验证。观测量下降不能单凭本统计解释为实际通行下降或新闻因果。

> 2026-09-30 Issue #20（PR #22 已合入 main，用户测试通过）：智能体自然语言轨迹/定位指令返回结构化地图动作，支持回放附近默认窗口、最近 N 小时与唯一历史指代；自动高亮/绘制并聚焦，保持聊天面板。后端 276 passed / 12 skipped，前端 build/check:workbench、真实模型与 5174 浏览器成功/无数据/503/取消样本通过。范围、时间规则与未验证项见[地图联动记录](docs/agent_map_actions_issue20.md)。PR #19 已合入 main；下方 #13/#16 的待评审及必须显式 UTC 窗口描述属于 2026-09-29 历史版本。

> 2026-09-29 Issue #13（分支 `codex/issue-13-map-agent`，待 PR 评审）：#14 时间线卡片复用事件封面并在失败时回退类型图标；#15 的 [12 题真实模型能力评测](docs/agent_capability_eval_issue15.md)已完成，工具扩展待开始；#16 的结构化地图动作在已核实工具结果上生成，明确单船 UTC 窗口可自动加载轨迹，建议动作由用户点击，切换详情后可返回同一对话。前端 build/check:workbench、后端动作测试、实时模型与浏览器样本已验证；其他样本和整周连续回放未逐项验收。下文旧版状态描述以本条为当前增量入口。

本项目以 Vue 地图工作台展示船舶轨迹及已采集的真实新闻报道，后端使用 FastAPI、PostgreSQL 和 PostGIS。新闻聚合事件用于浏览和情景说明，不代表已核实的船舶风险结论。

> 2026-09-25 真实 AIS 七日接入：本机应用库 `aisdb` 已按 UTC+8 文件日导入 2026-02-25 至 2026-03-03 七天数据，共 4,462 艘、17,921,533 条报位；逐日来源、哈希、行数和接口对账见[七日导入记录](docs/real_ais_seven_day_import.md)。用户在执行中取消独立测试库验证；本轮只在应用库验证，未推送或部署。

> 2026-09-25 中新网中文批次：应用库新增 67 条中文报道（中国新闻网系，2026-02-24 至 2026-03-03），按时间/主题聚类新建 13 个事件（evt_066–evt_078）并归并 45 条到 14 个现有事件；新闻 290→357 条、事件 65→78 个。逐条映射、唯一性规则与前后端验证见[中新网批次导入记录](docs/chinanews_news_import.md)。未推送或部署。

> 2026-09-26 来源文件交接：上述 67 条新闻的原始 JSON 与 65 张配图已纳入 `_analysis_chinanews/chinanews_霍尔木兹_20260223-20260303/` 的 Git 版本管理，67 条记录与 65 个图片路径逐一核对。其他成员拉取代码后仍需单独导入数据库；运行封面接口时需另行配置 `NEWS_IMAGE_ROOT` 并提供图片。见[数据库与环境交接](docs/database_setup.md)。各处“未推送”记录描述的是对应日期的历史状态，远端进度以当前 Git 分支比较为准。

> 2026-09-25 前端真实 AIS 能力：快照、最多四帧的连续播放窗口和有界单船轨迹已在此前独立单日试点做过浏览器验收；本轮七日应用库验证了跨日 API，整周浏览器和并发性能未验收。单日历史证据见[试导记录](docs/real_ais_import_pilot.md)，当前数据对账见[七日导入记录](docs/real_ais_seven_day_import.md)。MobilityDB 派生层未重建，四艘新闻船关联暂缓。

> 2026-09-25 七日应用库页面修复：未构建的相遇派生层会返回 `not_built`，前端现正确显示此状态；点击船只可打开详情，并显示有界单船轨迹与实测航速着色。应用库浏览器单船验证和限制见[前端工作台](FRONTEND_WORKBENCH.md)。

> 2026-09-25 智能体真实 AIS 适配已合入本地 `main`（`208f39d`、`7f1b89a`）：来源说明、船舶搜索和单船轨迹改为 `nnu_ais`；海峡通行使用既有 56.2°E / 56.7°E 虚拟双门线，限定时间与空间，在数据库内筛出侧别变化，可选船 ID。八个业务工具的应用库只读验证及局限见[智能体开发任务](docs/agent_development_plan.md)；真实模型和浏览器问答尚未验收，远端未推送。


工作区整合：2026-09-22。SQL-06 已在独立 worktree 完成固定 fixture、一次性 PostgreSQL 17、真实 DeepSeek 和浏览器综合验收；未连接共享业务库，其余业务数量沿用历史核验记录。其他成员的数据库需自行导入，Git 不会同步数据库内容。本地验收不等于远端发布。

当前协作：用户已确认 Kimi 前端优化结束，成果已纳入本轮整理；性能报告见 [地图渲染优化](docs/map_rendering_optimization.md)，性能数值为 Kimi 的历史测量，本轮未重测。另一个未合并的回放试验分支 `kimi/replay-positions-at` 已按用户决定放弃，其改动未进入 main；下文回放能力以 main 代码为准。后续新工作使用独立分支和 worktree，见 [多会话协作与交接](docs/collaboration.md)。LangChain 第一版及 `codex/lc-safety-fix` 安全修复已合入本地 `main`；`f14eceb` 的候选复核事实和本轮验收见 [智能体开发任务](docs/agent_development_plan.md)。远端尚未推送。

2026-09-23 前端布局任务由用户明确指定直接在主目录 `main` 实施，属于本次单项例外；布局改动已在本地 `main` 整合，未推送远端。当前页面结构与当时的验证见 [前端工作台](FRONTEND_WORKBENCH.md)。

2026-09-24 新闻时间回放修正从独立分支 `codex/news-timeline-reveal` 快进合入本地 `main`；地图与左侧新闻列表共用事件发生时间筛选，具体规则和本轮验证见 [前端工作台](FRONTEND_WORKBENCH.md)。远端未推送。

2026-09-24 事件封面图已接入左侧新闻列表和地图事件弹卡；图片由后端按事件编号提供，部署时通过 `NEWS_IMAGE_ROOT` 指向新闻图片目录，见 [前端工作台](FRONTEND_WORKBENCH.md) 和 [环境交接](docs/database_setup.md)。本地已验证代码与页面，远端未部署。

2026-09-25 七日导入由用户明确指定在当前目录从 `da5f4eb` 建立 `codex/ais-seven-day-import` 分支，不创建 worktree；用户随后取消独立测试库验证。应用库导入及验证见[七日记录](docs/real_ais_seven_day_import.md)。此前单日试导仍见[历史记录](docs/real_ais_import_pilot.md)。

2026-09-25 七日导入和船舶详情修复已从 `codex/ais-seven-day-import` 快进合入本地 `main`（功能提交 `ee7b81e`、`5b663bd`）；未推送远端。数据库数据仍只在本机，不随 Git 合并。

交接包注意：模拟船舶文件及旧 manifest 已移除，当前仓库没有可导入的四表交接包。历史导入验收不代表当前可导入；详见 [数据库交接](docs/database_setup.md)。

## 当前进度

| 模块 | 当前状态 |
| --- | --- |
| 船舶与船位 | 应用库已导入七天：4,462 艘、17,921,533 条；来源批次和行号逐日对账 |
| 回放时间 | 应用库七日覆盖 UTC 2026-02-24 16:00 至 2026-03-03 15:59:59；跨日快照、三帧窗口及单船轨迹接口已验证。Issue #5 的自然日主刻度与单日缩放小时刻度已随 [PR #11](https://github.com/sure-660322/Hormuz/pull/11) 合入 main；连续播放 UI 的浏览器验收仍是此前独立单日试点历史结果 |
| 新闻 | 78 个新闻聚合事件、357 条报道（289 条关联事件，68 条未关联；含 2026-09-25 导入的中新网中文批次 67 条，见[导入记录](docs/chinanews_news_import.md)）；45 个事件有代表坐标，36 个有非空事件时间，非空不等于精确到时分 |
| 地图工作台 | **七日应用库跨日 API 与单船点击、轨迹、速度着色浏览器交互已验证；整周浏览器未验收**；原有态势总览与地图探索双视图、模拟回放路径仍在。地图探索的回放轴已移到顶部，桌面新闻区与地图按 2:3 排列，船舶入口仍在左侧；此布局已通过 [PR #7](https://github.com/sure-660322/Hormuz/pull/7) 合入 main。真实 AIS 模式逐窗加载船位快照，选船后按需查询有界轨迹，并可切换实测航速着色及采样点显示。新闻事件与船位独立；应用库状态见上。详见 [前端工作台](FRONTEND_WORKBENCH.md)。 |
| 历史回放 | 原模拟数据分窗加载路径仍在；真实 AIS 以至多 4 帧的小窗口预取和有界缓存连续播放，未下载七日 1,792 万条报位。单船轨迹按时间桶抽稀并分段；1,985 个刻度为旧模拟批次历史结果 |
| 新闻浏览 | Issue #6 已在左侧新增「时间线 / 列表」切换：纵向时间线按来源发生日期分组，宽屏两侧交错、窄屏单侧；日期级事件在当前显示时区进入该日时与地图同步出现，不声称具体小时。[PR #11](https://github.com/sure-660322/Hormuz/pull/11) 已合入 main。[Issue #17](https://github.com/sure-660322/Hormuz/issues/17) 在两种视图的事件分类文字前显示统一分类图标，前端构建、工作台检查和当时可见事件的浏览器核对通过，详见[前端工作台](FRONTEND_WORKBENCH.md)。列表保留封面缩略图，地图事件弹卡保留配图与回退；有发生日期但无代表坐标的事件仍可读详情。缺少 `event_datetime` 的事件放在可展开的「时间未明确」区，仅能阅读详情，不用报道日期补造发生日期或地图回放点。关联报道与来源仍在事件详情中。 |
| MobilityDB / PostGIS | **P0–P4 已实现，P5 部分实现**：派生轨迹、速度着色、事件关联、停留和相遇分析、data-health 已有代码；主回放仍读原始船位，未切换 simplified 派生层。本机新数据的派生表仍为空；旧试验数量与验收见下表 |
| TimescaleDB | 扩展已安装，尚未使用时序表能力 |
| 智能体 | **本地 main 已接入七日真实 AIS 语义并通过工具层验证**：LangChain `create_agent`、8 个只读业务工具与知识库保持 v4 契约。船舶检索、轨迹和有界虚拟门线通行已在应用库只读验证；**SQL 三工具已按 catalog v2 + 016 只读语义层在本机恢复启用**（`agent_data.v_ships` 一船一行，`v_ships=4,462` 与源表一致；执行器全链路核验通过，真实 DeepSeek 对「多少艘油轮」自主完成 schema→check→execute 并回答 793 艘）。含 TimescaleDB 的集群须为读者角色设 `timescaledb.disable_load=on`（016 已内置）。浏览器端到端仍未验证；合并后后端 257 passed / 12 skipped，旧版 254/245 passed 为历史离线验收 |

旧模拟批次依据同期新闻构造等待等行为，具体船数、响应时刻、航迹及比例属于模拟假设；其报告仅作历史记录，见[旧批次说明](sim_ais_demo/output_news_aligned/README.md)。用这些 AIS 作研究结论前仍须核验来源、授权、覆盖和完整性。

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
| GET | `/events` | 新闻聚合事件，按最早报道日期排序 |
| GET | `/events/{event_id}/cover` | 按业务事件 ID 读取关联报道配图；从 `NEWS_IMAGE_ROOT` 下受限的 `images/` 路径返回图片，缺失时 404 |
| GET | `/events/{event_id}/news` | 使用业务事件字符串 ID 查询关联报道，不是数据库整数主键 |
| GET | `/simulation/meta` | 模拟船位范围及刻度；`event_count=0` 指不含回放模拟事件，不是新闻数为零 |
| POST | `/agent/analyze` | 智能体问答：问题 + 可选封锁窗口（带时区、≤24 小时）+ 可选多轮 history（≤10 条消息）+ 可选 map_context（回放时刻、唯一参考船 ID）；返回回答、船只、证据、工具结果与 map_actions（轨迹/位置/事件）；错误统一为 detail{code,message,request_id} |
| GET | `/mobility-demo` | 停留分析独立试验页 |
| GET | `/mobility-demo/analysis?area=strait` | 固定两个时窗；区域可选 `strait` 或 `approach` |
| GET | `/mobility-demo/tracks` | 派生轨迹 GeoJSON |
| GET | `/ships/{ship_id}/nearby-events?radius_km=` | 遗留路由仍注册，但引用迁移前事件字段，未适配当前新闻表；不能作为可用能力调用 |

前端区域查询目前只接入模拟船舶，事件近邻关联未启用。新闻的多地点字段尚未完整展示。

## 智能体当前能力与后续范围

设计见[智能体接入契约与任务](docs/agent_integration.md)。POST /agent/analyze 已注册，前端地图工具栏的「智能体」按钮打开右侧详情浮层，支持多轮提问；回答带船只/事件引用与「地图定位」按钮。船定位到当前回放快照；新闻事件仅在发生时间已进入当前回放帧且有代表坐标时按自身位置定位。

2026-09-26 前端交互改动已从 `codex/agent-chat-ui-main` 快进合入本地 `main`（实现提交 `1d1ae41`）：智能体面板改为消息流和固定输入区，Enter 发送、Shift+Enter 换行；回答用 Markdown 渲染并消毒，真实 v4 `results` 可展开查看工具调用，等待时显示计时与取消。`npm run build`、`npm run check:workbench` 和模拟响应的浏览器交互已验证；本地 5174 页面已打开智能体面板且控制台无错误。真实后端/模型浏览器问答及 SSE 流式输出未在本轮验收或实现。详细记录见[前端工作台](FRONTEND_WORKBENCH.md)与[开发计划](docs/agent_development_plan.md)。

> **2026-09-23 修复记录**：`f14eceb` 复核发现候选实现可重复执行 SQL、超时后后台继续触库、联调脚本导入旧入口。已在本地 `main` 合入修复并通过离线回归：SQL 三工具、知识库和业务工具共用 8 次请求预算；第一次 SQL 成功或终止失败后关闭执行分支，只有第一次未执行的普通语法错误允许一次修正；整体超时取消后等待工作线程退出，再由路由释放请求 Session。联调脚本已切换到 `run_lc_agent`；无密钥返回 SKIP。真实 DeepSeek、独立 PostgreSQL 和浏览器仍待验证。

当前实现采用 **LangChain `create_agent` + 原生业务 Tools + 现有只读业务服务/SQL 安全底座**，集成现有 FastAPI；手写工具循环与固定短语分类器已按计划 §7 移除。

历史验收记录：默认问题曾返回 1 艘 SIM V2 化学品船 019（证据 P1，观测完成于 2026-02-28T18:14:54Z）；v3 三场景联调记录见 [当前契约](docs/agent_integration.md)。本轮未重新调用模型，不能把历史数量当作当前查询结果；自由回答正文尚无逐项事实核验器。

后续再做：地图定位当前指向回放快照位置，历史轨迹逐点回放联动尚未实现；服务端会话持久化未做（history 由客户端逐请求携带）。受限 SQL 底座已按真实 AIS 重做并启用：`016` 重建 `agent_data` 语义层与只读角色，catalog v2 哈希与口径已在本机核验，真实模型聚合问答通过；报位级 SQL 不在 catalog 范围，报位级分析仍走业务工具。八个业务工具的应用库复核见[智能体开发任务](docs/agent_development_plan.md)：停留、相遇及 observed 事件关联未构建，不能据零结果推断没有真实行为或关联；mentioned 文本提及仍可查询。

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
| P4 | 相遇分析（`encounters` 派生表 + analyze/query API） | ✅ **已完成**（2026-09-20）：`012_encounters.sql` + 构建脚本（候选对时间重叠粗筛 → 等时长重采样 → 逐时刻 geography 距离，默认 3 NM/30 min/60 s），当前库 136 对；GET/POST 三分支验证通过；前端概览「相遇分析」列表 + 点击定位与重新分析按钮；独立核对最近距离最大差 19 m |
| P5 | 回放抽稀层 + data-health（回放主链路切换 simplified 层、覆盖率体检） | ✅ **部分完成**（2026-09-20）：`GET /api/data-health` 已实现（源覆盖统计 + 四张派生表新鲜度），前端概览「数据健康」区块；回放主链路切换 simplified 层与抽稀保留规则未实施，真实数据接入前补强 |

历史派生层边界：旧模拟批次的 observed 事件关联只是时空邻近演示，不构成真实因果；当前应用库仅有 mentioned 船名文本提及，未核对真实 AIS ship_id。七日真实 AIS 的停留、相遇和 observed 派生层尚未重建。旧批次实施过程中发现的 MobilityDB 陷阱（`tstzspan` 文本参数静默错解析；`&&` 非保守空间粗筛；`nearestApproachDistance` 离散时刻高估；EPSG:32640 跨 UTM 带失真）见技术方案 §3，不代表当前新数据已验收。

完整方案与各阶段验收细节见 [MobilityDB 时空能力底座技术方案](docs/mobility_capability_plan.md)（P0–P5 均已按实施更新）。

## 尚未实现与限制

- 真实 AIS 派生层重建、四艘新闻船关联、整周浏览器与并发验收、来源授权及区域覆盖核实、实时推送、自动刷新、认证授权和正式部署。七日已在本机应用库导入，未推送或部署。
- 智能体契约为 v4：工具集为 8 个只读业务工具 + 知识库工具，受限 SQL 工具（`get_database_schema`/`check_sql`/`execute_sql`）在 catalog v2 口径与 `SHIP_DATA_SOURCE` 一致且功能开关完整时暴露（本机已启用，fail-closed）；多轮 history 仍由客户端逐请求携带。真实 DeepSeek 聚合问答已于 2026-09-25 在本机验收（油轮计数 793）；浏览器端到端未重验。共享业务库统计、认证限流、正式部署、长时间多 worker 压测和无密钥 503 仍未做本轮实测。
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
