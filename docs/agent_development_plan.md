# 智能体下一阶段开发任务

## 2026-10-02 Issue #28 态势总览第一轮增强

状态：**已验证，[PR #29](https://github.com/sure-660322/Hormuz/pull/29) 已提交并推送，待审查，未合入 main**。负责人 Codex。用户授权先提交上一轮主目录精简改动（`e58eac1`），再从此提交创建独立分支 `codex/issue-28-overview` / worktree `D:/my_project/Hormuz-worktrees/codex-issue-28-overview`；原 main 的其他任务目录均保留。修改范围：总览/图表/事件带/船型分类与筛选、App 联动、相关前端语义检查及 README/本模块文档/历史统计入口；无新依赖。

实现：完整油价/观测通行窗口，方向切换复用既有核验表（总 253 次，入湾 132、出湾 121 是 2026-09-30 批次，不是本轮重算）；UTC 时间轴及当前完成快照竖线，UTC+8 只改变显示和事件日期定位，不重新归日。事件带按报道数选最多六条再按来源发生日期排序，同日折叠；发生日期、首次报道日期和报道数分列；缺日期/无效日期/窗外记录排除，无坐标仍可开详情。事件晚于当前帧时先 seek 来源日对应显示时区的首个有效帧，等待快照完成后开详情；请求失败或用户改变目标时取消待打开事件。船舶构成油轮/货船（含集装箱/散货）/已识别其他/未知互斥覆盖，按全快照统计，船型筛选、搜索及列表共用归类集合，支持清除；空结果百分比为 0。保留原新闻回放门控、地图相遇图层与智能体工具。

船型核对：只读 GET `/ships/snapshot?at=2026-02-24T16:05:00Z` 样本 1,585 艘，真实值含油轮、货船、集装箱、拖引、捕捞、未知等；明确白名单归类，未识别值进入未知，不能按船名猜类型。未重新查询全库船型历史属性。

验证（2026-10-02）：

- 独立前端 `npm ci`、`npm run build`、`npm run check:workbench`、根目录 `git diff --check` 通过；语义检查覆盖已核验八日方向值/总量相等、船型互斥/空构成、六事件选择/无效日期排除、UTC/UTC+8 seek 边界，并保留快照等待与缓存回归。
- Playwright CLI 在 5176 的临时同源代理连接现有 8000 后端，只读现有应用库。代理位于忽略的 `frontend/node_modules/.tmp/issue28-preview.ts`，不修改跟踪 API 配置、后端 CORS 或 5174 现有服务；端口 5176 保持运行供用户审查。
- 浏览器直接读取 ECharts 实际 option，核对总次数/入湾/出湾八日值、窗口外 null、油价/通行量开关、UTC+8 切换不移动同一时刻标记；回放推进后标记更新而完整事件带保持不变。UTC+8 点击 2 月 28 日事件定位到当地 00:00，实际新闻详情保留 12 个来源链接。
- 初始已完成快照 30 艘，构成 7/7/10/6；四类点击后列表分别为 7/7/10/6，清除恢复全部。地图缩放不改变构成；延迟窗口响应期间仍显示旧快照，完成后更新到 16:05；点击未来日期跳转、回到起点通过。
- 模拟响应页单独验证同日折叠、无日期/无效日期/窗外事件排除、无坐标事件日期跳转与详情、空快照/无 NaN/四类禁用；不改数据库。
- 1440px/390px 验证与截图检查通过，390px 无横向溢出，图表减少为 4 个刻度分段并保持可读；隐藏总览切回正常初始化。最终浏览器控制台 0 error / 0 warning（消除原隐藏容器图表 warning）。本地证据：`output/playwright/issue28-acceptance.js`、`issue28-edge-acceptance.js`、`issue28-overview-desktop.png`、`issue28-overview-details.png`、`issue28-chart-mobile.png`，忽略产物不提交。

限制：无新增动态统计 API，不重算历史批次或校准门线/来源完整性；图表展示固定历史窗口，不代表实时数据。没有因果判断、风险评分或源数据修改；未做整周连续播放、典型案例完整回归或真实模型问答。Vite 仍提示既有大 bundle 警告；本轮未进行无关代码拆包。PR 提交与部署是不同状态，未授权合并。

## 2026-09-30 地图探索与总览精简

交付状态更新（2026-10-02）：用户授权后，已单独本地提交为 `e58eac1`，随 PR #29 的功能分支推送；尚未合入远端 main。下方保留 2026-09-30 的验收与当时交付状态。

状态：**已验证，待用户审查；未提交、未推送**。用户明确指定在主目录 main 修改，基线 `8c199d7`，负责人 Codex；复用 5174/8000，只读验证现有应用库。真实 AIS 默认起始帧，移除时间轴分析展开及内容、总览相遇分析和数据健康；地图相遇图层与智能体工具保留。build/check:workbench/diff 检查与首帧、逐帧、总览删除、窄屏浏览器核对通过；未做整周播放、案例完整回归或真实模型问答。详细验证与现存图表 warning 见[前端工作台](../FRONTEND_WORKBENCH.md)。

## Issue #26 中海北冰洋典型案例（2026-09-30）

状态：**已验证，PR #27已合入main（2830ae6），本地同步与清理完成**。负责人Codex；原独立分支 `codex/arctic-ocean-case`，基线937556b；前端5176/后端8002，独立验证库 `hormuz_arctic_case_test`，应用追加目标aisdb。已实现独立案例层、三航行阶段/后续回应与六篇引用、统一五日回放/一次分片轨迹、固定详情区/四张原文配图/报位点默认关闭/速度着色默认开启/稀疏方向箭头（地图探索同步）、精简案例文字与日期、原态势恢复、CSV事务导入及案例内智能体范围。独立库及后端针对性27项、最终全量294 passed / 12 skipped、前端build/check:workbench、阶段与真实模型浏览器样本通过；原七日保留，应用追加11,640条接受报位。本任务分支/工作区已删除，预览5176/8002已关闭；未正式部署。完整进度与限制见[案例任务记录](arctic_ocean_case.md)。

## 2026-09-30 Issue #20 自然语言地图联动

交付状态：2026-09-30 用户测试通过后，[PR #22](https://github.com/sure-660322/Hormuz/pull/22) 已合入 `main`（`ac46b10`），本地主目录已快进同步；本地/远端 `codex/issue-20-agent-map` 分支已删除。本轮未新增 worktree，其他任务工作树和未跟踪 `.tmp_eia/` 保留。5174 使用 main；未正式部署。

状态：**已验证，用户测试通过，PR #22 已合入 main**。负责人 Codex，主目录分支 `codex/issue-20-agent-map`，基线 `7136bea`；本轮用户明确指定不新增 worktree。复用 5174/8000 与现有应用库。Issue 已补充单点定位/高亮、保持聊天面板、取消及多轮指代要求。实现轨迹与位置结构化动作、权威有界窗口、唯一指代、本轮工具重新核实、取消过期请求、图层渲染和避开面板的聚焦确认；修正首次从船簇选中时的高亮 DOM 状态。后端全量 276 passed / 12 skipped，前端 build/check:workbench 通过；真实模型及 5174 浏览器验证默认窗口 STALLION 轨迹、追问定位、旧 UTC 流程、无数据、注入 503 与取消。完整范围、命令、批次样本与未验证项见[任务记录](agent_map_actions_issue20.md)。未修改数据库/依赖/API 地址/CORS；已合入 main，未正式部署。

2026-09-29 #16 已通过 PR #19 合入 main；下面保留当时分支验收与限制，当前地图动作规则以 #20 记录为准。

## 2026-09-29 Issue #13 / #15 / #16

状态：**#15 评测已完成、工具扩展待开始；#16 已实现并在本分支样本验证，待 PR 评审与更多异常样本验收**。基线 `main` / `1f1c1ca`，负责人 Codex，worktree `codex/issue-13-map-agent`。12 题、实际工具状态、HTTP 504、身份与 `not_built` 边界及新增工具优先级见[能力题集](agent_capability_eval_issue15.md)。本轮不扩展 SQL 视图、不构建停留/相遇派生层。

#16 在 v4 响应中增加 `map_actions`（`ship_track` / `event`，`automatic` / `suggested`，已核实 ID、适用时的 UTC 起止、来源）。服务端仅从成功工具结果产生动作：唯一且有报位的单船轨迹 + 用户明确显示意图及明确窗口可自动触发；多目标、无数据、无坐标不产生动作。前端执行前复核 AIS 覆盖、≤24 小时、快照与轨迹接口结果；事件沿用发生日期门控和代表坐标；仅成功选中后显示完成。聊天组件保持挂载，切换详情后可返回继续追问。2026-09-29 本分支后端全量 `260 passed / 12 skipped`（含地图动作测试 3 passed），`frontend` build/check:workbench 通过；8001 新后端真实模型问题“船 ID 360，2026-02-28T14:00Z—15:00Z”返回 `get_ship_track:ok` 与 automatic 结构化动作，5176 浏览器加载轨迹接口和快照并选中 FAIR TIGER，返回对话后原问答仍在。动作由工具证据产生，不把模型正文当成已执行地图状态。其余边界见[接入契约](agent_integration.md)。

## 2026-09-26 智能体聊天面板 A 档交互

状态：**已实现并快进合入本地 main；前端构建、工作台检查、浏览器模拟响应与 5174 页面打开面板已验证；待真实模型浏览器问答验收**。负责人 Codex；基线 `main` / `7f69663`，实现提交 `1d1ae41`，开发分支 `codex/agent-chat-ui-main` 位于主目录（用户指定不使用独立 worktree）。修改范围：`frontend/src/components/AgentPanel.vue`、前端依赖清单及本节相关文档；后端契约、数据库、密钥未改。5178 为已结束的模拟响应预览；本地 5174 使用现有 8000 后端。

- 实现：固定输入区与滚动消息流；Enter 发送、Shift+Enter 换行，IME 组字不提交；发送/停止/清空/设置等图标使用 `@tabler/icons-vue`，等待三点动效参考 Amicro 后以 CSS 实现。回答 Markdown 使用 `markdown-it`（禁用原始 HTML）与 DOMPurify 消毒；新闻来源链接经过安全 URL 过滤。v4 `results` 按 call_id 显示工具名称、服务端状态与实际返回的关键字段；没有返回的参数不补造。上下文和统计折叠，保留结构化证据与地图定位；错误可重试原问题。
- 验证（2026-09-26）：`frontend` 中 `npm run build` 与 `npm run check:workbench` 均通过；Playwright 在 `http://127.0.0.1:5178/` 以模拟 v4 `/agent/analyze` 响应验证 Shift+Enter 换行、Enter 提交、等待计时与停止、Markdown 表格、恶意脚本未执行、`javascript:` 链接未渲染成可点击链接、工具过程展开、503 错误后重试成功，以及长对话向上阅读时新消息不强制滚动。模拟请求不验证后端模型质量、真实工具结果或跨会话持久化。背景地图与事件请求因该端口未连接后端产生连接错误，非智能体 UI 新增错误。
- 本地 main 合入复核（2026-09-26）：`git merge --ff-only codex/agent-chat-ui-main` 将实现提交 `1d1ae41` 合入本地 `main`；现有 `http://localhost:5174/` 和 `http://127.0.0.1:8000/health` 均返回 200。Playwright 在 5174 打开地图工具栏「智能体」并看到新输入区，实际 AIS/新闻正常加载，浏览器控制台 0 error / 0 warning；同页在应用内浏览器再次确认面板可打开。未发送真实模型请求，故工具选择和回答质量未验收；未推送远端或部署。
- 未实现/待验收：SSE 流式输出、模型内部推理展示、真实后端/真实 DeepSeek 浏览器问答与移动端布局。历史 `results` 仅在完整响应返回后可展示。

## 2026-09-25 受限 SQL 三工具 nnu_ais 适配

状态：**已验证（应用库执行器全链路 + 离线回归 + 真实模型问答），已合入本地 main**。负责人 Kimi；工作目录 `D:/my_project/Hormuz`，本地 `main` 直接推进（用户确认单人开发）。

- 目标：让 `get_database_schema` / `check_sql` / `execute_sql` 在真实 AIS 主链重新可用，解决「一共多少艘油轮」这类通用聚合统计没有工具承接的问题（此前模型只能退到 `search_ships` 给部分数据，且系统提示与工具注册不一致）。
- 方案（改后复用，不删重写）：SQLGlot 全树白名单校验（SQL-03）与独立只读执行器（SQL-04，角色/视图哈希/权限运行时核验）整体保留；新增 `backend/sql/016_agent_views_nnu_ais.sql` 重建 `agent_data` 语义层与只读角色；新增 `backend/app/query_analytics_catalog_v2.json`；`sql_tools_enabled()` 放行条件由「数据源是 simulation」改为「catalog v2 声明口径与 `SHIP_DATA_SOURCE` 一致 + 执行器配置完整」，保持 fail-closed。
- catalog v2 视图设计：`agent_data.v_ships` 一船一行（仅含 ≥1 条 `nnu_ais` 报位的船，列形状与 v1 相同，`data_source` 常量 `nnu_ais`、`is_simulated=false`，COUNT(*) 即船数，不依赖 DISTINCT）；`v_events` / `v_news` 定义与 v1 逐字一致（视图哈希不变，批准 JOIN 仍只有 `v_news.event_id = v_events.event_id`）。**不含报位级视图**：执行器语句超时 5 秒，17,921,533 条报位的全表/大范围聚合不可靠；报位级分析继续走 8 个业务工具。
- 环境事实（本机 `aisdb`，只读核验）：PG 17.10，应用角色 `aisdb` 是库属主且为超级用户；`_timescaledb_*` / `tiger` / `tiger_data` / `topology` 等扩展模式的 USAGE 均经 PUBLIC 授予。执行器的会话 schema 白名单校验要求 `agent_reader_login` 仅能 USAGE `agent_data`，故 016 需收回上述 PUBLIC 默认授权并对应用角色显式补授（属主与超级用户身份不受影响）；`public` schema 与数据库 TEMP 同步按 013 口径收紧。影响面仅限 `aisdb` 库内 PUBLIC 默认授权。
- 密钥边界：`agent_reader_login` 口令只进本机 `.env`（`AGENT_DB_PASSWORD` 等 `AGENT_DB_*` 变量），不进 Git、不进日志与回答。
- 验证顺序与结果：回滚事务预演（视图/权限/口径核验通过，v_ships=4,462 与源表一致）→ 哈希写入 catalog v2 → 代码改造（policy 指向 v2、`sql_tools_enabled` 改为 catalog 口径校验 + 执行器配置、系统提示与知识库表述同步、测试隔离 .env）→ 离线全量回归 **257 passed / 12 skipped**（新增 4 项开关/口径守卫测试）→ 正式执行 016 → 执行器实测（油轮计数 793、按船型分布 25 行、报道总数 290，`DELETE` 被只读策略拒绝）→ 真实 DeepSeek 问答验收（见下）。
- TimescaleDB 兼容性发现（写入 016 注释与 catalog environment_notes）：本机集群 `shared_preload_libraries` 含 timescaledb（2.22.0），收回 `_timescaledb_functions` 等 PUBLIC 授权后，**任何聚合查询**（甚至 `SELECT count(*) FROM pg_namespace`）都会报 `permission denied for schema _timescaledb_functions`；`timescaledb.enable_optimizations=off` 无效，而为 `agent_reader_login` 设置 `timescaledb.disable_load=on`（016 已内置）后完全正常。SQL-04/06 历史验收环境无 TimescaleDB，故未覆盖此模式。
- 视图哈希口径修正：catalog 哈希必须按 catalog 声明的方法在 `search_path=pg_catalog` 下计算（读者会话口径）；应用角色默认 search_path 下 `pg_get_viewdef` 的 schema 限定不同，哈希不同。v_events/v_news 的读者口径哈希与 v1 catalog 完全一致（定义逐字未变）。
- 真实模型问答验收（2026-09-25，本机 aisdb + 真实 DeepSeek）：提问「这批七日历史AIS数据里，一共出现了多少艘油轮？」，模型自主按 get_database_schema → check_sql → execute_sql 链路回答 **793 艘（ship_type 标注为「油轮」）**，并主动说明 NULL/未知船型 707/348 艘不计入、AIS 自报口径与七日覆盖边界；catalog limitations 正确流入响应。对照修复前同一问题只能返回 search_ships 部分数据并误述「SQL 工具不可用」。
- 本机启用方式：`.env` 追加 `AGENT_QUERY_ENABLED=true` 与 `AGENT_DB_*`（`agent_reader_login` 口令仅本机保存，未提交）；`sql_tools_enabled()` 保持 fail-closed（catalog v2 `data_source_scope` 必须等于 `SHIP_DATA_SOURCE` 且执行器配置完整）。
- 未验证：浏览器端到端（AgentPanel 问答交互，本轮无浏览器环境）；远端推送；其他机器/集群的 016 重放（TimescaleDB 版本差异需复核 disable_load 行为）；报位级 SQL 有意不在 catalog v2 范围（17,921,533 行聚合不可行，走业务工具）。

## 2026-09-25 旧 SQL 船舶视图退役与业务工具复核

状态：**已验证（应用库只读工具及退役迁移），已合入本地 main**。承接 `codex/real-ais-agent-passage` 的 `208f39d`，功能提交 `7f1b89a` 已快进合入本地 `main`；本轮未调用真实模型或改动船位、新闻、事件数据。应用库检查发现 `agent_data` schema 及三个旧 SQL 视图均不存在，`ship_positions` 只有 `nnu_ais` 来源 17,921,533 条。新增 `015_retire_simulation_agent_view.sql`，在其他环境有旧 `agent_data.v_ships` 时只以 `DROP VIEW ... RESTRICT` 删除它；历史 013 与 v1 catalog 保留为旧批次验收资料并标明不得对当前库重放。本机 `aisdb` 在事务内执行 015 前后 `v_ships` 均不存在；另在同一库的回滚事务内临时创建 `agent_data.v_ships`，执行 015 后确认视图被删，回滚后 schema 仍不存在。四个业务源表数量仍为 ships 4,462 / ship_positions 17,921,533 / events 65 / news 290。

逐一通过 `make_business_tools` 在本机 `aisdb` 只读调用（固定 2026-02-28T15:00Z–16:00Z；新闻/派生工具使用其自身参数），记录如下。工具可执行不等于其派生数据已构建，更不等于真实模型会准确选择或表述：

| 工具 | 当前结果 | 判定 |
| --- | --- | --- |
| `search_ships` | MMSI `538009322` 命中 1 艘 | 可用，仅历史 `nnu_ais` |
| `get_ship_track` | `ship_id=9757` 一小时 354 条报位 | 可用，仍受 5 万条上限 |
| `query_strait_passages` | 同船同窗 1 次虚拟门线通行 | 可用，口径及阈值限制见下节 |
| `get_event_context` | `evt_002` 返回事件与报道 | 可用，报道与 AIS 船身份未核对 |
| `get_data_health` | `ok`，约 56.6 秒 | 可调用，但接近智能体 60 秒预算，性能待优化 |
| `query_ship_dwell` | `not_built` | 工具可用，七日 AIS 派生层未构建 |
| `query_encounters` | `not_built` | 工具可用，七日 AIS 派生层未构建 |
| `query_event_ship_links` | `evt_002` 的 mentioned 返回 3 条；observed 原返回 `no_data` | mentioned 可用；已修正无 observed manifest 时返回 `not_built`，按事件与按船查询均复核通过 |

旧 SQL 三工具 `get_database_schema` / `check_sql` / `execute_sql` 在当前 AIS 主链强制隐藏；旧 SQL-02～06 测试只证明历史模拟 fixture 的安全链，不是当前业务库 SQL 能力。下一步表述优化应按工具状态生成措辞：真实 AIS 的观测通行需注明虚拟门线和覆盖限制；`not_built` 应说“尚未构建”，不能说“没有停留/相遇/关联”；新闻 mentioned 只是文本提及；数据健康超时须如实报告而非编造统计。真实 DeepSeek、浏览器问答、SQL 新视图及 6 小时/30 kn 阈值仍待验证。

验证命令：`D:\my_project\Hormuz\backend\.venv\Scripts\python.exe -m pytest backend/tests -q` → **254 passed / 12 skipped**；015 使用 SQLAlchemy 事务执行，测试了视图不存在的空操作及回滚事务内真实删除分支。未运行前端构建（未改前端）。本地 `main` 合并后重跑同一后端全量命令仍为 **254 passed / 12 skipped**；远端未推送。

## 2026-09-25 七日真实 AIS 语义与虚拟门线适配

状态：**已验证（后端工具与应用库只读查询），已合入本地 main**。负责人 Codex；基线 `main` / `9bc9f6b`；工作目录 `D:/my_project/Hormuz-worktrees/codex-real-ais-agent-passage`，分支 `codex/real-ais-agent-passage`，提交 `208f39d`。本轮仅修改 `backend/app/services/agent/`、`backend/app/services/data_health.py`、相关后端测试及 README/智能体文档；未启动服务端口，数据库目标为本机 `aisdb`，只读验证，不修改源表或派生表。

- 原因：原智能体将船位写成 `simulation`，`search_ships` 只检索模拟来源；通行查询会把截止时间之前所有源报位读入 Python，七日 `nnu_ais` 数据下超限。旧 SQL 语义视图 `agent_data.v_ships` 仍筛 `simulation`，不能用于真实 AIS。
- 实现：船舶搜索以 `nnu_ais` 报位存在性过滤，MMSI/IMO 等关键字作字面检索，截断时返回真实匹配数；单船轨迹只读该来源，纠正来源说明。系统提示、知识库、业务工具描述、结果 context 与 data-health 批次说明改为七日历史 AIS，保留新闻实体核验边界。缺省 2026-02-28T15:00Z 仅是兼容旧接口的查询起点，不再称为真实封锁时刻。旧 SQL 视图仍筛 `simulation`，因此生产工具注册强制隐藏 SQL 三工具，待视图与权限按真实 AIS 重做并验证。
- 虚拟门线：沿用西侧 `<56.2°E`、东侧 `>56.7°E`，只使用纬度 25.8–27.1°N、经度 55.8–57.1°E 的 `nnu_ais` 实测报位；门线之间的报位不改变侧别。窗口最长 24 小时，前置侧别最多回看 24 小时。数据库内按船、时间、数据库报位 ID 排序并筛出侧别变化，仅返回聚合和变化证据；最多处理 100 万门线侧别报位、返回 5000 个变化候选，超限拒绝。两侧报位之间若另有报位离开判定区域、相隔超过 6 小时或推算速度超过 30 kn，候选单列为不确定；可用 `ship_id` 只核对一船。完成时间是完成侧首条报位时间，不是精确越线时刻。阈值尚未用七日 AIS 独立校准；零匹配不证明未通过。
- 2026-09-25 验证：`D:\my_project\Hormuz\backend\.venv\Scripts\python.exe -m pytest backend/tests -q` → **253 passed / 12 skipped**；工作树内 `compileall` 与 `git diff --check` 通过。应用库只读查询：2026-02-28T15:00Z–16:00Z 的门线侧别报位 282,900 条、确定通行 4 次；同窗 `ship_id=9757` 确定西向东 1 次，两侧报位为 12:29:06Z `(56.199355,26.4012)` 和 15:21:38Z `(56.700098,26.235923)`；该船 MMSI `538009322` 搜索命中且两小时轨迹返回 638 条。同起点 24 小时为门线侧别报位 449,765 条、确定通行 35 次、长间隔不确定候选 4 次；这些数值只属于本次本机应用库与上述口径。FastAPI TestClient 只读 GET `/health`、`/docs`、`/api/data-health` 均为 200，data-health 显示 `nnu_ais=17,921,533`；该全量健康统计约 58 秒，尚需性能优化。
- 用 `ScriptedFakeLLM` 走真实应用库 `run_lc_agent`：显式 1 小时窗口与 `ship_id=9757` 返回 `status=ok`、`context.ship_data_source=nnu_ais`、1 次通行及对应船 ID；这验证 LangChain 工具往返与结构化结果，不能替代真实模型自主选工具。
- 未验证：真实 DeepSeek 对新工具与知识的自主选择、前端浏览器问答、七天每个窗口的独立人工通行核对、来源授权和区域覆盖、6 小时/30 kn 阈值校准、并发性能、受限 SQL 语义视图真实 AIS 适配。七日 AIS 的停留、相遇与 observed 事件关联派生层未重建；四艘新闻船关联本轮不处理。已合入本地 main，远端未推送。

更新：2026-09-23。LangChain 第一版及安全修复已合入本地 `main`，来源为 `kimi/agent-lc04` 的 `6bf739c` 与 `codex/lc-safety-fix` 的 `1afd34b`；远端尚未推送。当前实现见 [LangChain 第一版方案](langchain_agent_v1_plan.md) 与 [接入契约](agent_integration.md)，全项目摘要见 [README](../README.md)。

## 2026-09-23 整合前复核与修复

`main` 的 `f14eceb` 记录了候选实现的三项阻塞事实，作为历史复核保留：① 同一请求连续两次 `execute_sql` 都返回 `ok`，假执行器调用两次；② `ThreadPoolExecutor.shutdown(wait=False)` 使 0.062 秒返回的整体超时之后，后台仍于 0.172 秒调用 SQL 执行器，可能使用已释放的请求 Session；③ `scripts/test_deepseek_toolcall.py` 导入已删除的 `runner.run_agent`，启动即报 `ModuleNotFoundError`。当次候选全量测试 231 passed / 12 skipped、智能体专项 54 passed，前端 build/check:workbench 通过；这些通过记录并未覆盖上述缺陷。

当前状态：**安全修复已通过确定性离线验证并整合到本地 main；整版已实现待真实环境验证**。SQL 执行分支首次成功、拒绝、超时或不可重试失败即关闭；只有第一次尚未实际执行的语法错误可以重交一次，数据库实际执行最多一次。业务、知识库、schema、check、execute 共用每请求 8 次工具调用预算，超额请求返回带 `call_id`/`tool_name`/`TOOL_BUDGET_EXCEEDED` 的结构化结果并停止继续调用模型。整体预算 60 秒，超时设置取消事件；新工具被拒绝，执行中 SQL 收到取消事件；同步业务工具无法强制中断时，响应等工作线程结束才返回，确保 HTTP 504 后不会触库或使用已释放 Session。该等待可能使 HTTP 504 的实际响应时间超过 60 秒，属于保证资源生命周期的代价。

2026-09-23 修复分支验证：使用 `D:\my_project\Hormuz-kimi-agent-lc04\backend\.venv\Scripts\python.exe -m pytest backend/tests -q`，**245 passed / 12 skipped**；离线测试覆盖 SQL 成功后二次拒绝、拒绝/超时/不可重试错误、语法修复一次、统一预算、晚返回模型调用、在途业务与 SQL 超时、HTTP 504 后 Session 释放及脚本无密钥 SKIP。`frontend` 中 `npm run build` 与 `npm run check:workbench` 通过；以占位环境变量和 FastAPI TestClient 对 `/health`、`/docs`、`/openapi.json` 冒烟均 200，没有连接数据库。真实 DeepSeek、独立 PostgreSQL SQL 链路和浏览器当次未验证；当次没有连接共享数据库、推送或合入 main。这是合并前的历史验证记录。

2026-09-23 本地 `main` 合并后验证：`D:\my_project\Hormuz\backend\.venv\Scripts\python.exe -m pytest backend/tests -q` 为 **245 passed / 12 skipped**；`D:\my_project\Hormuz\frontend` 中 `npm run build` 与 `npm run check:workbench` 通过；FastAPI TestClient 对 `/health`、`/docs`、`/openapi.json` 均为 200（未执行数据查询）。依赖按 `backend/requirements.txt` 的 LangChain 1.4.2、langchain-openai 1.6.3、openai 3.17.0 补入 `main` 的虚拟环境。真实 DeepSeek 工具选择、独立 PostgreSQL SQL 链路及浏览器交互仍待验证；本地合并不代表远端推送。

## 当前判断

- SQL-02～06 已完成语义视图、SQLGlot 校验、独立只读执行、工具接入和隔离验收；这些成果作为新 SQL Agent 的安全执行底座保留。
- ~~当前 `runner.py` 仍是自定义 Tool Calling 循环，并包含大量固定短语分类；它是现状，不是下一版目标。~~ LC-04 起该循环与固定短语分类已删除（`runner.py` 移除，`langchain_runner.py` 为唯一编排入口），当前判断以 LC-04 实施记录为准。
- 当前已使用 LangChain 单智能体，让模型基于系统提示、项目知识、Tool 描述和数据库 schema 选择自然回答、知识检索、业务 Skill 或 SQL；真实模型选择准确率尚未在本版复验。
- 第一版不直接编写 LangGraph、不做多智能体和服务端会话持久化。
- LC-01 已完成基础接入（见下方实施记录）：统一序列化修复了 `median_gap_minutes: Decimal` 导致的 HTTP 500，编排切换到 `create_agent`；范围外与问候由模型自然回答。

## 实施看板

| 编号 | 范围 | 状态 | 验收重点 |
| --- | --- | --- | --- |
| LC-01 | LangChain/DeepSeek 基础接入、简洁系统提示、统一序列化和错误降级 | **已实现待验证** | 自然问候；范围外回答；模型/工具错误不产生未处理 500；`Decimal` 可序列化 |
| LC-02 | 现有 8 个只读业务服务包装为 LangChain Tools；轻量 Markdown 知识库 | **已实现待验证** | 模型能按多种表达自主选择知识或 Skill；多轮代词可用 |
| LC-03 | `get_database_schema`、`check_sql`、`execute_sql`；本地受限 SQL Agent | **已实现待验证** | 普通筛选/排序/聚合可问答；复杂业务继续走 Skill；写 SQL 被只读底座拒绝 |
| LC-04 | 前端兼容、旧 runner/固定规则清理、真实模型和浏览器验收 | **已实现待验证** | 不要求固定问法；澄清、故障降级、表格、来源和地图引用正常 |

| 修复阶段 | `f14eceb` 的审查要求 | 当前状态 |
| --- | --- | --- |
| LC-R1 | SQL 首次成功或终止失败后关闭、统一请求预算、实际执行最多一次 | **已验证（离线）**：重复执行及预算耗尽回归通过 |
| LC-R2 | 超时后不得再触库或使用已释放的请求 Session | **已验证（离线）**：模型晚返回、在途工具、HTTP 504 生命周期回归通过；同步调用结束前延迟响应 |
| LC-R3 | 联调脚本迁到 LangChain 入口并清理旧预算描述 | **已验证（离线）**：无密钥 SKIP，当前代码无旧 `runner.run_agent` 导入 |
| LC-R4 | 后端全量、前端两项检查及三个 HTTP 冒烟；整合到 main | **已验证（非浏览器）**：修复分支和本地 main 全量检查通过；本地 main 合并已完成，远端未推送 |
| LC-R5 | 独立数据库、真实 DeepSeek、浏览器交互 | **待验证**：需分别记录，不沿用 SQL-06 的历史验收 |

### LC-01 实施记录（2026-09-22，分支 kimi/agent-lc01）

- 依赖锁定：`langchain==1.4.2`、`langchain-openai==1.6.3`（独立 worktree 虚拟环境实测 `create_agent` 可用；langchain 1.x 内置工具循环执行基础，项目不直接编写 LangGraph）。
- 新增 `backend/app/services/agent/serialization.py` 统一序列化（Decimal→int/float、datetime/date、UUID、dataclass、pydantic、SQLAlchemy Row、未知类型 str 兜底），修复 `median_gap_minutes: Decimal` 导致的 HTTP 500；旧 `runner._jsonable` 委托同一实现。
- 新增 `backend/app/services/agent/langchain_runner.py`：DeepSeek 经 ChatOpenAI 接入 `create_agent`；8 个现有只读业务工具由 v4 注册表适配为 LangChain Tools（业务算法未重写）；简洁系统提示；工具错误降级为 `{status, code, message}` observation；整体 60 秒预算；固定短语前置分类暂保留拒绝/澄清子集。
- `routers/agent.py` 内部改调 `run_lc_agent`，**v4 响应契约保持不变**（schema_version 仍为 "4"）。
- 已验证（2026-09-22，离线，无真实模型/数据库）：后端全量 229 passed / 13 skipped（新增 22 项：序列化、问候/范围外无工具回答、模型不可用 503、Decimal 不再 500、工具错误降级、超时 504、history 透传、路由层往返）；/health、/docs、/openapi.json 冒烟 200。
- 未验证：真实 DeepSeek 问答与工具选择、浏览器端到端、前端兼容（留 LC-04）；`query_analytics` 在 LC-01 不向模型暴露（LC-03 接入）。

### LC-02 实施记录（2026-09-22，分支 kimi/agent-lc02）

- 新增 `backend/app/services/agent/knowledge/` 轻量知识库：`project_overview`、`data_semantics`、`passage_rules`、`mobility_rules`、`agent_capabilities` 五份 Markdown（第一版不引入向量数据库）。
- 新增 `backend/app/services/agent/knowledge_base.py`：按章节切分、中文 bigram + 拉丁词切词、标题命中加权的相关度检索，返回 3～5 个片段（单片段 ≤900 字符）。
- `langchain_runner.py` 新增 `search_project_knowledge` 工具（结果计入 results/tools_used，与业务工具同一 envelope 口径）；系统提示规则 2 改为「项目知识优先调用知识库工具」。
- 已验证（2026-09-22，离线，无真实模型/数据库）：后端全量 237 passed / 13 skipped（新增 8 项：知识检索命中/空结果/上限、知识工具被调用、能力边界回答、多轮指代「它」结合 history 继续调用业务工具、知识结果可序列化）。
- 未验证：真实模型对知识工具的选择准确率（脚本化假模型只验证链路）；浏览器端到端（LC-04）。

### LC-03 实施记录（2026-09-22，分支 kimi/agent-lc03）

- 新增 `backend/app/services/agent/sql_tools.py`：`get_database_schema`（catalog 视图/字段/批准 JOIN/上限）、`check_sql`（SQLGlot 策略纯校验，不触库）、`execute_sql`（复用 SQL-04 独立只读执行器，SELECT-only、超时、结果上限、query_id）；拒绝/超时/执行失败后关闭后续 execute_sql，仅未执行的普通语法错误可修正一次。
- 工具仅在功能开关完整（`ExecutorConfig.from_env`）时暴露；系统提示按需追加受限 SQL 工具说明。
- 按方案 §7 的移除条件（LC-01/03 完成）删除 `langchain_runner` 中的固定短语前置分类：问候、范围外、知识、写库/越权意图、澄清全部交给模型与工具底座（写 SQL 由只读策略拒绝）。旧 `runner.py` 及其测试保留至 LC-04 等价回归后清理。
- 已验证（2026-09-22，离线，无真实模型/数据库）：后端全量 245 passed / 13 skipped（新增 10 项：schema 返回、合法 SELECT 校验、DELETE/字面量拒绝、execute_sql 经假执行器返回行/列/query_id、拒绝后 SQL 关闭、开关关闭时工具不暴露、写意图经策略拒绝；改写 4 项前置分类依赖测试）。
- 未验证：真实 PostgreSQL + 真实 DeepSeek 的 SQL 问答链路（本地演示环境启用后验收，随 LC-04 或单独环境验证）；浏览器端到端（LC-04）。

### LC-04 实施记录（2026-09-22，分支 kimi/agent-lc04）

- 新增 `backend/app/services/agent/business_tools.py`：8 个现有只读业务服务包装为**原生 LangChain Tools**（`make_business_tools`），直接复用已验证的服务层算法（strait_passages/ship_search/ship_tracks/event_context/data_health/dwell/encounters/event_ship_links），不重写业务逻辑；参数校验统一经 Pydantic args_schema（枚举/类型），服务层 ValueError 降级为 `INVALID_TOOL_ARGS` observation、数据库错误降级为 `DATABASE_UNAVAILABLE` observation，不再产生未处理 500。
- 新增 `backend/app/services/agent/results.py`：v4 响应组装从旧 `runner.py` 迁出（build_result/normalize_status/safe_model_answer/parse_time_arg 等）；`normalize_status` 新增「已纠正错误豁免」——同工具后续出现成功 envelope 时，早前的 error envelope 不把顶层状态降为 partial（与 syntax_error 豁免同口径，保持 v4 纠正循环的顶层状态语义）。
- 删除 `backend/app/services/agent/runner.py`（手写模型工具循环 + TOOL_REGISTRY/TOOL_SCHEMAS）；`langchain_runner.py` 整体改写为 create_agent + business_tools + sql_tools + results，路由 `routers/agent.py` 改经 results/serialization 组装响应，`schemas_agent.py` 注释同步。
- 测试改造（方案 §7）：dwell/encounters/data_health/event_ship_links 四个 AG 套件迁到 `run_lc_agent` + ScriptedFakeLLM（纠正链路断言改用 `llm.received[i]` 的 ToolMessage；假 OpenAI 客户端类删除）；`test_query_analytics_integration.py` 与 `test_query_analytics_sql06.py` 重写为 HTTP 层 + 执行器层用例（固定问句矩阵删除）；新增 `test_agent_expressions.py` 多表达矩阵（问候/范围外/知识/SQL 统计链/通行技能/澄清/故障降级各 3～4 种表述，共 24 项），固定问句选择准确率的真实验证仍需真实模型。`ScriptedFakeLLM` 增加 `received` 与 `bound_tools` 记录，支撑纠正链路与「模型可见工具 schema」断言。
- 已验证（2026-09-22，离线，无真实模型/数据库）：后端全量 **231 passed / 12 skipped**（LC-03 基线 245/13，差额为按方案 §7 删除的固定问句矩阵与旧消息循环用例）；前端 `npm run build` 与 `npm run check:workbench` 通过（lc04 worktree 全新 npm install 后验证，AgentPanel 无需改动，v4 响应契约未变）。
- 未验证：真实 DeepSeek 问答与工具选择准确率（脚本化假模型只验证链路，选择准确率依赖真实模型）；真实 PostgreSQL + 真实模型的受限 SQL 链路（本地演示环境启用后验收）；浏览器端到端三状态（需前后端联调环境）；以上为 LC-04 验收项，因无密钥/无浏览器环境本轮无法执行。

## 保留与清理边界

保留：现有业务查询服务、`agent_data` 视图、catalog、SQLGlot 策略、独立只读执行器、超时/结果限制、前端 AgentPanel 及结构化展示。

LC-04 已按 [第一版方案 §7](langchain_agent_v1_plan.md#7-现有代码去留) 的删除条件完成清理：固定短语前置分类（LC-03）、手工 `TOOL_REGISTRY`/schema、手写模型工具循环（`runner.py`）与重复 `_run_*` 适配层均已移除，只验证固定句式的测试由 `test_agent_expressions.py` 多表达矩阵替代。

不能移除：模拟船/真实新闻边界、新闻文本不可信、数据库只读、禁止写入、超时和结果限制，以及通行/停留/相遇/事件关联的业务语义。

## 历史证据

SQL-02～06 的阶段验收文档继续保留，但不再作为当前任务看板：

- [SQL-02 语义视图与只读角色](query_analytics_sql02.md)
- [SQL-03 AST 策略](query_analytics_sql03.md)
- [SQL-04 独立执行器](query_analytics_sql04.md)
- [SQL-05 工具循环接入](query_analytics_sql05.md)
- [SQL-06 综合验收](query_analytics_sql06.md)
- [受限 Text-to-SQL 历史契约](query_analytics_contract.md)

这些记录证明已有底座当时的实现和验证状态，不表示 LangChain 第一版已经完成。

## 工作规则

- 每阶段使用独立分支和 worktree，开始前记录基线与文件所有权。
- 状态严格区分“待开始 / 进行中 / 已实现待验证 / 已验证”。
- 文档和页面不得把方案写成已实现功能。
- 第一版按学生比赛项目控制复杂度；不为尚未出现的商业部署问题增加框架。
- 依赖版本、模型 Tool Calling 和 SQL Agent 行为必须实际测试后锁定。

## Issue #24 轨迹模型上下文优化（2026-09-30）

- 状态：后端实现及离线回归已验证；浏览器夹具联动已验证；PR #25 已合入 main（af41d37），本地 main 已同步；本次任务 worktree、本地和远端分支已清理，未部署。真实模型 token/费用对比未验证。
- 负责人：Codex；基线 `e9518fea2291b6d42436beaae1a995506213b73a`；分支 `codex/issue-24-track-summary`；worktree `D:/my_project/Hormuz-worktrees/codex-issue-24-track-summary`。本任务负责 business_tools.py、langchain_runner.py、新增 track_observation.py/model_usage.py、对应测试及 README/本计划/接入契约的任务段落。未改其他会话 worktree。
- 本轮未启动服务，未连接或修改数据库。浏览器使用现有 5174 前端与 8000 只读地图 API；仅本任务独立浏览器会话拦截 `/agent/analyze`，响应由本 worktree 的 run_lc_agent + ScriptedFakeLLM + 轨迹夹具生成，无收费模型调用。完整夹具报位不代表真实 AIS 观测。
- 实现：record_envelope 将完整轨迹留在 state/results，仅给模型发送有界 JSON 摘要。包含查询/覆盖时间、身份、数量、首末报位、来源及限制，无完整 fixes。地图位置动作仍读取末报位 recorded_at，轨迹动作仍读取身份与窗口；响应 v4/前端类型不变。
- 用量：每个模型 run 的完成/失败记录与问答汇总通过 Uvicorn INFO 日志输出，按 run_id 去重，优先供应商标准 usage_metadata、兼容 token_usage；缺失为 null/unavailable。model_calls 为 LangChain 调用数，SDK 内部重试不可见，network_attempts=null。某轮缺失时完整累计为 null，不把已知的部分用量冒充总量；缓存数据独立标明缺失。不输出原始消息、错误正文、密钥，不估算费用。
- 本轮命令：主目录后端 venv Python 在该 worktree 执行 `-m pytest backend/tests -q`：286 passed / 12 skipped。新增测试覆盖 0/2/50,000 条夹具、大小上限、长文本及限制省略、两次后续模型轮次均无 fixes、完整服务端证据、轨迹/定位动作、usage 缺失/失败/缓存/去重及请求汇总。沿用地图测试覆盖歧义、代词、否定、无数据、时间窗口等边界。未修改 Vue/TypeScript，未重跑无关前端构建。

| 相同字段的轨迹夹具 | 原结果字符/UTF-8 字节 | 模型摘要字符/UTF-8 字节 |
| --- | --- | --- |
| 0 条 | 298 / 298 | 495 / 617 |
| 2 条 | 563 / 563 | 789 / 911 |
| 50,000 条 | 6,800,295 / 6,800,295 | 793 / 915 |

以上为固定测试夹具的 JSON 大小，不是 tokenizer 或供应商实际 token；少量报位的摘要有说明开销，大量报位时长度不随报位数量线性增长。不声称具体费用节省比例。

浏览器：Playwright 独立会话 `issue24`，两次提问后聊天面板和上一轮结果保留；显示 FAIR TIGER（ID 360）14:00–15:00 UTC 轨迹成功，第二轮定位/高亮成功（界面以真实地图 API 返回的 14:58:39Z 报位时间为准）。`/ships/360/track-window` 与 `/ships/snapshot-window` 返回 200。控制台 0 errors、1 条现有 ECharts 零尺寸 warning；未将该图表警告归因于本任务。临时证据原在任务 worktree 的 `output/playwright/` 与 `.playwright-cli/`；清理前已复制保存到主目录本地忽略路径 `local-archive/issue24-2026-09-30/playwright/` 和 `playwright-cli/`（含 snapshot、network、generate_fixture.py 和生成响应），不提交原始数据与临时输出。后端真实模型日志、原始 9 次账单归因、真实供应商缓存/费用及全量端到端模型验收未验证。

2026-09-30 合并与同步核验：`gh pr view 25` 确认 base=main、state=MERGED；fetch 后 `git merge-base --is-ancestor af41d37 origin/main` 及任务提交 19e3cba 对本地 HEAD 的祖先检查通过，主目录 fast-forward。用户授权合并、清理与同步，本会话作为整合者仅同步本任务共享文档段落。旧 8000 reloader/worker 未自动加载变更，因此核对精确进程后停止并从主目录重启；启动日志确认监听主目录、Application startup complete。新运行日志位于上述本地归档的 `runtime/`。8000 `/health`、`/docs` 与 5174 首页均 HTTP 200；在最新主目录执行 `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_agent_track_observation.py backend/tests/test_agent_map_actions.py -q`，29 passed。该检查是合入后相关回归，不冒充重新执行全量 286 项，也未调用收费模型。当前 5174 的后续问答使用修复后端，原有回答不重算；其他会话 worktree/服务保留。
