> 2026-10-09 收尾：[PR #59](https://github.com/sure-660322/Hormuz/pull/59)（#48 受控 Text-to-SQL catalog v3 受控分析快照）已合入 main（45cfe83），[Issue #48](https://github.com/sure-660322/Hormuz/issues/48) 已关闭；kimi/issue-48 工作树与本地分支已清理。catalog v3 快照层仅在独立测试库 hormuz_sql_test 验证，应用库 aisdb 未执行 017/未建快照；应用库实施与部署待另行授权。

> 2026-10-08 收尾：用户授权整合已交付范围，[PR #45](https://github.com/sure-660322/Hormuz/pull/45) 已合入 main（3bcfea1），本地 main 已快进同步；codex/area-activity-ui 的工作树、本地/远端分支及验收服务已清理。未部署。用户随后确认触屏与纯键盘相关范围暂不做，已移出本 Issue 的待办；[Issue #41](https://github.com/sure-660322/Hormuz/issues/41) 已按已交付范围关闭。并发预算等未验证限制不因关闭而视为已验证。下方 2026-10-07 的状态与数字为当时记录，不表示本轮重做浏览器或模型验收。

# 智能体下一阶段开发任务

## 2026-10-09 Issue #50 本机前三阶段

负责人 Codex，固定工作流 1.0.0；基线 `74dcbdc`，独立分支
`codex/mcp-local-transports`。用户先授权接口核对、适配实现与调用边界，随后追加
Kimi 测试和成功后 PR 交付。stdio/Streamable HTTP 共用 7 个业务工具与条件启用 SQL 三工具，
显式窗口/区域、一次性 SQL 令牌、独立只读事务与超时/取消/限流已实现。
2026-10-09 Kimi CLI 2.1.1 / Highspeed 两种传输各完成同一组四题，八次真实调用
与独立测试库同条件业务基线一致，见[验收记录](issue50_kimi_acceptance.md)。
本轮未读取 `.env`、未修改源数据/迁移/建快照；临时 HTTP 验收服务已关闭。
后端回归 466 passed / 14 skipped。配置与边界见[本机 MCP 记录](mcp_local_adapter.md)。
[PR #62](https://github.com/sure-660322/Hormuz/pull/62)（Draft）已创建，实现提交 `15a9cfb` 已推送；交付本机实现和业务样本，未合并、未部署；真实 SQL 客户端链路因缺少
专用只读账号运行凭据保持待验证。Issue #50/#46 不关闭。
2026-10-10：用户当前 Kimi 桌面端未见 Hormuz。此前仅添加 Kimi Code MCP 配置，
未安装桌面插件；CLI 验收成立；随后按授权补做 Hormuz 个人插件 0.1.1，官方校验/登记通过，启动器发现 7 工具并通过四题对账。用户随后已安装启用；当前桌面会话未发现 Hormuz MCP 工具，只读控制接口已确认启动错误：Kimi 将 node 转换为 Kimi.exe __plugin_run_node，运行时却把后者当作模块，MODULE_NOT_FOUND；0.1.2 已改用 PowerShell 7 入口并通过 7 工具发现、四题对账和 11 项相关回归，官方登记成功。官方个人市场更新因运行中会话被延后，受管副本仍为 0.1.1；仅对原失败会话的 Hormuz 重连返回该会话已不存在。桌面查询验收阻塞，需等待任务自然空闲后官方更新，见[记录](issue50_kimi_acceptance.md)。

2026-10-10 DSH：用户追加授权接入 DeepSeek Harness。官方 MCP client / stdio 与独立 headless 真实模型四题已验证，与同参数业务基线一致；独立 profile 已持久配置。桌面 profile 单条增量已保存并保留原配置及本机备份，运行进程核对路径正确，但桌面 MCP 启动和问答未证实；状态为「已配置待桌面验证」。没有重启或停止其他任务。大型区域工具的 DSH 事件截断明细，前置汇总完整。SQL 仍关闭，HTTP/其余工具/多轮/负载未测，PR #62 保持 Draft。详见[DSH 验收及使用](dsh_mcp_acceptance.md)。

同日收到桌面 agent 的“本机配置不存在”报告后复核：真实 Windows 路径下文件存在，SDK 7 工具发现和持久 DSH profile 的 ATHE NOVA 查询均再次成功。两份 profile 仅增加显式 HORMUZ_KIMI_CONFIG 路径；不重新生成配置、不枚举凭据、不重启。桌面连接继续待验证，执行环境差异未核实，详见 DSH 记录。

23:25 后桌面复核：真实桌面 MCP 子进程也看不到旧 AppData 配置，先前仅凭 CLI 可见性否定其报告的判断不完整。改用 DSH profile 内白名单运行元数据后，桌面配置可读、Python/MCP 模块可见，真实桌面 tools/list 返回 7 工具且无协议错误；状态更新为「桌面协议发现已验证，桌面模型问答待验收」。只重载 Hormuz 条目，未重启、未读取复制凭据；底层文件系统隔离机制未确认。

桌面所属同连接 search_ships 只读探测也已通过（req_d62c66dd64bf43c9bb8bde1b42d6f02d）；临时诊断入口已撤除，正常 pwsh/launch.ps1 恢复。桌面协议发现与进程内数据库调用已验证，模型实际回答仍待用户发送验收题。

2026-10-11：用户确认 DSH 桌面 ATHE NOVA 身份查询成功，随后六题（轨迹/通行/在场/区域活动/连续两日区域比较/空结果）均成功。桌面样本验收更新为「已验证（用户确认）」；未采集逐题回答/request_id，也未独立复核这些回答的数值。SQL/DSH HTTP/其余工具/多轮/负载仍未验证，Kimi 桌面更新状态不变，PR #62 保持 Draft。本轮仅文档同步，未重跑查询或修改运行配置。

## 2026-10-08 当前摘要与下一阶段路线图

状态核对：通行统计 #40（PR #42 / f555ec7）、区域活动 #41（PR #45 / 3bcfea1）及北冰洋交互 #43（PR #44 / b0ed92f）已合入 main。当前 LangChain 单智能体有13个只读业务工具（8既有+2通行+3区域）、知识库及条件启用的SQL三工具；catalog v2 仍仅含船舶/事件/新闻。通行与区域各有2026-10-07真实模型/浏览器样本，综合多轮已随 #47 / PR #57 合入并在 2026-10-08 验收（[记录](issue47_multi_turn_acceptance.md)）；SQL分析事实层（#48）已随 PR #59 合入，并完成独立测试库验收（catalog v3：5 张受控分析快照表+清单核验+必要过滤；对账 ALL PASS、真实模型筛选/分组/排名三题、15 项失败关闭实测、EXPLAIN 毫秒级小扫描，见[issue48 验收记录](issue48_sql_acceptance.md)），**应用库 aisdb 未执行 017/未建快照**；产品 MCP 本机 stdio/Streamable HTTP 适配已在 #50 任务分支实现并经开发验证，Kimi 双传输业务样本已验证，完整 SQL 客户端验收、合并及部署待完成，见[说明](mcp_local_adapter.md)。下方旧分支状态和历史数量不代表本轮重新验收。

总路线图：[Issue #46](https://github.com/sure-660322/Hormuz/issues/46)。路线图发布时四项均为待开始；2026-10-08 #49已完成身份调查并实现案例，验证与交付见[案例记录](athe_nova_case.md)。2026-10-09 核对：#47/#48/#49 已关闭且关联 PR 已合入；#50 已实施本机前三阶段并按追加授权完成 Kimi 双传输业务四题测试，交付部分范围 PR；完整 SQL 客户端验收仍待完成。

| 优先级 | 任务 | 硬依赖 / 可并行范围 | 工具取舍 |
| --- | --- | --- | --- |
| 1 | [#47 综合多轮问答与证据联动](https://github.com/sure-660322/Hormuz/issues/47) | #47 已关闭，PR #57 已合入；三组验收见 issue47_multi_turn_acceptance.md | 复用现有通行/区域工具，不默认新增综合工具 |
| 2 | [#48 受控SQL分析事实层](https://github.com/sure-660322/Hormuz/issues/48) | #48 已关闭，PR #59 已合入；仅测试库实施，应用库未迁移 | 沿用schema/check/execute，新增有界分析数据与质量语义 |
| 3 | [#49 第二典型案例](https://github.com/sure-660322/Hormuz/issues/49) | #49 已关闭，PR #52 已合入；身份与案例验收见 athe_nova_case.md | 优先复用案例与轨迹服务，不开发“击沉识别”工具 |
| 4 | [#50 MCP Server](https://github.com/sure-660322/Hormuz/issues/50) | #47/#48 已合入；本机双传输已实现，Kimi 业务样本通过，完整 SQL 客户端验收待完成 | 对外协议适配，不复制算法或放宽SQL权限 |

主链为 **#47 → #48 → #50**；#49可并行调查。GitHub已设置#46的四个子任务及上述阻塞关系。各Issue列出功能、技术、验收与排除范围；不得因优先级编号误认为所有任务都串行等待。

任务#47验收三组“对话→分析→证据→地图”展示与追问，补全可见相机确认；#48对账通行/区域事实、稳定键、按日与全窗去重并验证SQL边界及预算；#49先核实用户所称ATHE NOVA的拼写、唯一身份、报道与报位缺口，不能确认时交付阻塞调查结果；#50用独立外部客户端核验工具发现、业务/SQL链路、权限、取消与资源边界。新任务不默认要求MobilityDB重建，不授权公网部署或直接迁移当前应用库。

### 本轮文档交付与核验

2026-10-08，负责人Codex；独立分支codex/analysis-roadmap-docs，基线9661f19，只修改README、FRONTEND_WORKBENCH、智能体接入、通行说明及本计划。统一13个业务工具、后端区域查询、已合并与历史验收范围，修正把单业务已验收写成全面待验收的描述，历史LC看板保留但明确标为历史。与其他会话的工作树隔离，共享文档整合止于PR交付，未在main编辑。

静态核验：核对business_tools/area_tools/langchain_runner、catalog v2三视图、GitHub PR #42/#45/#29合并状态、既有通行/区域验收记录及Issue依赖；检查Markdown相对链接、重复摘要和git diff --check。本轮未读取凭据、未查询或修改数据库、未运行模型/浏览器验收、未启动或停止服务，历史数量与日期没有冒充本轮测试。文档任务状态为已静态核验，PR #51 已合入 main（e8e843c），本地主目录已快进同步；当次路线图业务任务仍为待开始；#49后续实施见本文新增记录。



## 2026-10-07 Issue #40 动态海峡通行统计（分支 `kimi/strait-passage-stats`）

状态：**已实现待验证**（2026-10-07；基线 `ead29ac`，负责人 Kimi；worktree
`D:/my_project/Hormuz-worktrees/kimi-strait-passage-stats`）。按 issue 范围交付：
手动「通行分析」面板（总览图表旁内联展开，不新增 Dashboard 页）+ 智能体两个新工具，
复用同一统计/比较服务；多日按日统计（≤7 天/时段）、船型多选（含未知/缺失桶，
SQL 候选计算前过滤）、方向筛选、A/B 比较（差值/变化率 A=0 为 null/窗口长度与覆盖
可比性）、证据明细分页（matched_count 不受分页影响）、来源批次元数据（七日批次 1–7
与案例补充批次 8 区分）。服务端逐日编排保留 24h 回看，稳定证据键
`ship_id:起始报位id:完成报位id` 跨窗去重；判定口径与阈值不变
（`determination_version=strait-gates-v1+stats-2026-10-07`）。v4 增量 `analysis_actions`
绑定调用自身参数，前端「查看通行分析」恢复条件/结果；证据行地图联动复用智能体地图
动作执行器（证据时段 ±6h，与回放时段分别标明）。

- 验证（2026-10-07 本机应用库只读）：后端 306 passed / 14 skipped（新增
  `test_strait_statistics.py` 14 项）；HTTP 成功/无时区 422/超 7 天 422 分支通过；
  7 日全船型 475 次/候选 32 与逐日基线一致，全窗去重 447 艘；性能预算逐项达标
  （meta 热 1.08s、statistics 7 天 11.48s、compare 油轮 3v3 7.36s、evidence 7 天 10.89s）；
  前端 `npm run build` 与 `npm run check:workbench` 通过。
- 性能基线（改码前实测）：1 日全船型热 median 1.62s（日扫描约 75.3 万门线报位），
  7 日逐日合计 11.17s；基线脚本保留在 `scripts/measure_strait_baseline.py`。
- 允许修改路径：backend/app/services/agent/（strait_passages/strait_statistics/config/
  business_tools/results/langchain_runner/knowledge）、backend/app/routers/strait_passages.py、
  backend/app/main.py、backend/app/schemas_agent.py、backend/tests/test_strait_statistics.py、
  frontend/src（api.ts/App.vue/OverviewPanel.vue/AgentPanel.vue/PassageAnalysisPanel.vue）、
  docs/、README.md、FRONTEND_WORKBENCH.md、scripts/measure_strait_baseline.py。
  数据库目标：本机应用库只读（无写入/迁移/重建）；前端 5174 由用户既有 dev 服务占用，
  本轮未另起服务。共享文件（README、agent_integration、agent_development_plan、
  schemas_agent）由本会话按本任务整合。
- 未验证：真实 DeepSeek 对统计/比较问题的工具选择与表述、浏览器端到端（控件/图表/
  地图联动/窄屏/控制台）、独立测试库验证；历史油轮固定批次数字仅作对照。
## 2026-10-07 Issue #41 接手与最终复测

状态：三个阶段已实现，[草稿 PR #45](https://github.com/sure-660322/Hormuz/pull/45) 已创建、任务分支已推送，接手文档已保存；已在任务分支整合最新远端 main（4ce8184）与本地 main（2efd0ef），未合入 main、未部署。负责人 Codex，处理模式，交付到 PR。原始实现基线 aca8d3c，整合代码基线 6c5ff4d，交付 HEAD 以 PR 为准。

本轮验证：后端 390 passed / 14 skipped；前端 build、check:workbench、区域检查 30/30 与隔离类型检查通过；14 组 API 条件与已有独立复算证据的 163 项断言全部一致（162 数值/字段 + 1 状态，历史报告的 165 计数有误）。完整浏览器复测与真实模型调用见[验收报告](area_activity_acceptance.md) §七。知识库已补齐区域工具口径；#40 通行与 #41 区域工具/动作均保留。

限制：触屏及纯键盘矩形绘制尚未支持；真实超时已通过只读慢查询注入验证；并发预算、纯键盘表单走查、真实模型多轮追问仍未验收。共享库只读，未迁移、未改凭据、未重启已有服务。本轮使用独立 8032/5178，资源收尾见验收报告。下方阶段记录保留当时事实，不以历史数量替代复测。

## 2026-10-07 Issue #41 第一阶段：区域活动后端算法与接口

状态：**已实现、已在独立测试库与真实库只读验证，本地分支已提交，待用户验收；未推送、未合并、未部署**。负责人 Codex（本会话）。基线 `main` / `ead29ac`，分支 `codex/area-ship-activity`，工作树 `D:/my_project/Hormuz-worktrees/codex-area-ship-activity`。数据库目标：只读 `aisdb`（本机 PostgreSQL 17.10 + PostGIS 3.5.2）+ 独立测试库 `hormuz_area_test`；未建索引、未迁移、未重建派生层、未写业务库。允许修改路径：`backend/app/services/area_activity/**`、`backend/app/routers/area_activity.py`、`backend/app/schemas_area_activity.py`、`backend/app/main.py`（仅注册）、`backend/tests/test_area_activity_*.py`、`scripts/area_activity_samples.py`、`scripts/verify_area_activity_samples.py`、`scripts/verify_area_activity_backend.py`、`docs/area_activity*.md|json`、README 摘要。

- 交付：默认项目分析区域 `hormuz_core_v1`（25.8/55.8/27.1/57.1，半开矩形，附来源与版本）、`/api/area-activity/default-area|snapshot|activity|compare`、共享服务 `backend/app/services/area_activity/`（边界、参数、固定参数化 SQL、状态机、按日裁剪与 A/B）。口径与契约见[区域活动模块](area_activity.md)。
- 算法：时刻在场用每船最新有效报位（默认 3600 s 新鲜度，过期不回退）；时段分析按状态转换识别访问与进出，`left_returned` 拆访问、`gap` 标缺报中断、`jump` 标跳点，停留时长只累计连续观测区间并按窗口/自然日交集裁剪；A/B 允许不等长窗口，基期 0 时变化率为 null。
- 验证：单元+HTTP 契约 37 passed；全量后端 **329 passed / 14 skipped**；独立测试库样例验证 **PASS=2131 / WARN=0 / FAIL=0**（52 个场景/校验组，self-check 19/19，脚本只依据文档重写规则，不引用后端实现；含跳点双阈值回归 S20、批次范围一致性 S21、短时外出 S22 及其负向对照）；真实库只读验证通过（无非只读语句、源表行数与写入计数不变），性能基线 1 小时 ≈2.1 s、1 天 ≈2.8 s、7 天 ≈7.2 s、快照 40–60 ms；真实 HTTP 冒烟（8030，验证后关闭）通过。证据见[验证报告](area_activity_backend_verification.md)与 `docs/area_activity_*_result.json`。
- 本轮修复：segment 边界误判（`IS NOT NULL` 含 `'none'`）、短间隔 GPS 抖动被当成跳点（加入 ≥1 km 位移条件）、PostGIS 逐行粗筛拖慢查询（移除，7 天 5.6 s→4.7 s）。用户复核后追加两处修复（算法版本升到 `1.0.1`）：**批次筛选下沉到上下文与越界探测**（此前只作用于快照，统计与覆盖说明可能不同批次）、**越界探测阈值改为 480 s**（此前只在 >30 min 缺报或跳点时探测，船短时驶出 0.05° 外扩带再返回会被当成连续停留）。验证暴露的 9 条文档歧义已逐条定版，见验证报告 §四。
- **未开始（待验收后推进）**：前端矩形圈选与三模式面板、地图轨迹联动、三个智能体业务工具（`query_area_ship_snapshot/activity/compare`）与知识库/系统提示同步、真实模型问答、浏览器（桌面/窄屏）验收。与 #40 的共享文件（`App.vue`、前端 API 类型、智能体 schema）本轮未改动。

## 2026-10-07 Issue #41 第二、三阶段：手动矩形圈选、三模式面板与智能体区域工具

状态：**已实现，前端构建/语义检查与后端全量回归通过，浏览器手动全链路冒烟 15/15 通过，独立验收报告见[验收报告](area_activity_acceptance.md)；未推送、未合并、未部署**。负责人：Lead（整合）+ 两名 teammate（前端面板、智能体工具）+ 独立验证 teammate。分支 `codex/area-activity-ui`，worktree `D:/my_project/Hormuz-worktrees/codex-area-activity-ui`；基线 `aca8d3c`（含第一阶段两个提交）。数据库目标：只读 `aisdb`（本机）+ 独立测试库；未迁移、未重建派生层、未写业务库。端口：后端 8031、前端 5177（验证用临时实例，其他会话的 5174/8000 未改动）。

- 交付（第二阶段）：`AreaActivityPanel.vue` + `domain/areaActivity.ts` 三模式面板（时刻在场/时段活动含每日汇总与趋势/两时段比较）、船型多选（`GET /api/area-activity/ship-types`）、访问证据明细（entry/exit 证据报位、segments、flags）、`limits` 截断提示、`limitations` 原文、`no_data` 与有效零结果分流、`requestSeq`+`AbortController` 旧响应守卫、无障碍与窄屏；`MapView.vue` 分析区域矩形显示与拖拽圈选（原生事件 + Esc 取消 + 后端 `POST /api/area-activity/resolve-area` 校验后回滚）；`App.vue`/`ToolRail`/`style.css` 区域入口、状态条（重新圈选/恢复默认/取消绘制/「区域已变更，待查询」）、面板右下停靠与证据联动（复用既有 `ship_track` 有界轨迹，>24h 访问裁剪为末 24 小时并提示）。
- 交付（第三阶段）：三个只读工具 `query_area_ship_snapshot`/`query_area_ship_activity`/`compare_area_ship_activity`，与 `/api/area-activity` **共用同一 service 与算法版本**；`area_context` 请求字段（当前区域为权威值，默认区域不传以保留 `hormuz_core_v1` 身份）；`analysis_actions[type=area_activity]` 与前端「查看区域分析」入口（恢复区域、模式、时间、船型）；系统提示与知识库口径追加；工具数 8→13（含 #40 的 2 个通行统计工具）。
- 验证：后端 **366 passed / 14 skipped**（新增区域工具 32 项、区域上下文 8 项）；`frontend` 的 `npm run build`、`npm run check:workbench`、`node checks/area-activity.cjs`（30/30，`--types` 0 errors）通过；浏览器手动全链路 15/15（默认区查询与 API 一致、圈选、区域变更标记、恢复默认、三模式、Esc 取消）；独立验收（复算 14 组/165 字段、浏览器 S0–S8、真实模型三问）见验收报告。证据：`output/acceptance/**`（忽略目录，不提交）。
- 验收修复（提交 `4edec3e`）：`agentDraft` 漏声明导致「写入对话」ReferenceError 与构建失败；`L.DomEvent` handler 类型改为 `Event` 内部收窄；默认区域面积身份（面板传 `bounds=null`、`context.resolve_area_context` 兜底）；>24h 访问的轨迹裁剪。
- 与 #40 的合并预检：main 已含 #40（`acfc7af`）。在临时 worktree 做过一次合并预检，10 个文件冲突、解决口径与合并后 390 passed / 14 skipped 记录在[合并预检](area_activity_merge_check.md)；**没有执行真实合并**。
- 未验证/未包含：真实合并与 main 同步、推送与部署；并发与多用户响应预算、`statement_timeout` 真实触发路径、AIS 来源授权与覆盖完整性；知识库区域章节已在接手复测时补齐。

## 2026-10-06 仓库清理与文档整理

状态：已验证、已合入 main 并推送，任务 worktree 与本地分支已清理（2026-10-06；实施分支 codex/repository-cleanup，基线49895f9，清理提交2acd881）。本轮只删除用户确认废弃的数据/示例/中间清单，清理主目录忽略的旧模拟输出，并整理文档和引用；测试、知识库、真实 AIS 导入代码及真实数据库备份保留。验证及整合状态统一维护在[清理记录](repository_cleanup_2026-10-06.md)，未改写历史、公开仓库或部署。


2026-10-02：用户审查后，[PR #29](https://github.com/sure-660322/Hormuz/pull/29) 已合入 main（`2e4270a`，Issue #28 已关闭），本地主目录已同步。任务 worktree 与本地/远端 codex/issue-28-overview 分支已清理，5176 预览已关闭；5174/8000 与其他任务目录保留。5174 浏览器核对真实起始快照、饼图、两个开关和三个日期入口通过，控制台 0 error / 0 warning。验收资料归档为本地忽略的 local-archive/issue28-2026-10-02/browser-evidence.zip，原 output/playwright 路径属于清理前的历史证据。未正式部署，原有数据与验证限制保留。

## 2026-10-02 Issue #30 UI 与动效升级（分支 `kimi/ui-upgrade`）

状态：**已合并，[PR #37](https://github.com/sure-660322/Hormuz/pull/37) 合入 main（合并提交 `739793b`），本地已同步，任务 worktree 与本地/远端分支已清理（2026-10-03）；浏览器四尺寸验收未单独补做，遗留未验证项见下**。负责人 Kimi。worktree `D:/my_project/Hormuz-worktrees/kimi-ui-upgrade`（已删除），基于 main `ea31262`。按 #31→#32→#33→#35→#34→#36 顺序一次性完成父任务全部六项子任务；App.vue / style.css 等共享文件由本会话按顺序整合，无新增依赖，不改数据库、底图、API 地址与 CORS。另有 `2f29dba`：vite dev 改为同源 + 代理 `/agent /api /cases /events /ships /simulation` 到 8000，开发服务器任意端口（含预览 7100）不再受后端 CORS 白名单（仅 5174）限制。

- #31 基础规范：style.css 增加 `--dur-feedback/--dur-panel/--dur-map`、`--ease-out`、圆角与 `--accent/--ok/--warn/--danger` 语义令牌；正文/辅助字号整体上移（多处 9–10px → 10–11px，列表条目标题 12→13px）；开关、箭头、选中项接入动效令牌；相遇定位 flyTo 与两张 ECharts 图（趋势折线、构成饼图）响应 `prefers-reduced-motion`，偏好改变时实时切换。
- #32 布局：回放轴新增「紧凑轴/展开轴」切换（紧凑 96px，保留播放、当前时刻与滑块）；探索侧栏可拖拽调宽（280px–60vw，把手支持左右方向键）并可收起（顶栏重开）；上下文工作面板（详情/智能体）左缘拖拽调宽（300px–60vw，键盘可微调）；Leaflet 尺寸随布局自动 invalidateSize 为既有能力，保持。
- #33 新闻浏览：时间线中等宽度（容器 ≤560px）改单列、够宽再交错；日期组标题在列表内吸顶；选中新闻后详情标题短暂强调（列表项、地图标记选中态为既有联动）。
- #35 案例：阶段导航改为编号步骤（aria-current="step"）+ 阶段状态行（加载案例 / 等待快照与轨迹 / 已定位并说明亮线淡线语义）；快速连续切阶段的版本守卫与取消为既有能力。
- #34 总览：首屏标题区压缩、数据范围与口径说明收入可展开摘要；图下来源说明移除开发文档路径表述；图例（曲线开关）悬停/聚焦时对应曲线加粗强调；日期导航锚点跳转后目标事件组短暂高亮。
- #36 智能体面板：输入区上下文摘要改为紧凑条（案例可展开细节，选中船舶/事件时显示对应摘要）；空状态提供与案例相关的示例问题，点击只填入输入框不自动发送；地图动作反馈分 正在定位/成功/失败/已取消 四态着色，成功后提供「撤销地图定位」恢复；回答轻微淡入，用户阅读历史时不抢滚动并给出「有新回答，回到最新」可点击提示；面板宽度可调（见 #32）。

验证（2026-10-02 本 worktree）：frontend `npm run build`、`npm run check:workbench`、根目录 `git diff --check` 通过；dev 服务器临时启动返回 200（8000 后端健康）。**未验证项**：1440px / 1280×720 / 约 1024px / 390px 四尺寸浏览器核对、减少动态偏好实机切换、紧凑轴与拖拽把手的真实数据交互、智能体模拟响应验收——待用户在前端预览中检查。实现、验收、提交、推送、合并分开报告。

## 2026-10-02 Issue #28 态势总览第一轮增强

状态：**已验证，[PR #29](https://github.com/sure-660322/Hormuz/pull/29) 已合入 main（2e4270a），本地同步与清理完成**。负责人 Codex。用户授权先提交上一轮主目录精简改动（`e58eac1`），再从此提交创建独立分支 `codex/issue-28-overview` / worktree `D:/my_project/Hormuz-worktrees/codex-issue-28-overview`；原 main 的其他任务目录均保留。修改范围：总览/图表/事件带/船型分类与筛选、App 联动、相关前端语义检查及 README/本模块文档/历史统计入口；无新依赖。

实现：完整油价/观测通行窗口，方向切换复用既有核验表（总 253 次，入湾 132、出湾 121 是 2026-09-30 批次，不是本轮重算）；UTC 时间轴及当前完成快照竖线，UTC+8 只改变显示和事件日期定位，不重新归日。事件带按报道数选最多六条再按来源发生日期排序，同日折叠；发生日期、首次报道日期和报道数分列；缺日期/无效日期/窗外记录排除，无坐标仍可开详情。事件晚于当前帧时先 seek 来源日对应显示时区的首个有效帧，等待快照完成后开详情；请求失败或用户改变目标时取消待打开事件。船舶构成油轮/货船（含集装箱/散货）/已识别其他/未知互斥覆盖，按全快照统计，船型筛选、搜索及列表共用归类集合，支持清除；空结果百分比为 0。保留原新闻回放门控、地图相遇图层与智能体工具。

审查修正与验证（2026-10-02）：构成改为可点击饼图；开关显示滑块与显示/隐藏状态；原点标记改为日期/条数/跳转入口。折线采用稳定标识，仅目标曲线播放动画；关闭先以 400ms 淡出再移除，快速反向切换取消旧退出流程，卸载清理动画帧。饼图提示框限制在图表范围内。build/check:workbench/diff 与浏览器扇区点击、键盘开关、折叠组导航、未变曲线实例和动画状态、淡出中间透明度/延迟移除/同时退出/方向变更、1069px/390px 提示框完整可见验证通过。原验收记录的 5176/工作树路径属于合并清理前状态，证据已归档到上述 zip。

船型核对：只读 GET `/ships/snapshot?at=2026-02-24T16:05:00Z` 样本 1,585 艘，真实值含油轮、货船、集装箱、拖引、捕捞、未知等；明确白名单归类，未识别值进入未知，不能按船名猜类型。未重新查询全库船型历史属性。

验证（2026-10-02）：

- 独立前端 `npm ci`、`npm run build`、`npm run check:workbench`、根目录 `git diff --check` 通过；语义检查覆盖已核验八日方向值/总量相等、船型互斥/空构成、六事件选择/无效日期排除、UTC/UTC+8 seek 边界，并保留快照等待与缓存回归。
- Playwright CLI 在 5176 的临时同源代理连接现有 8000 后端，只读现有应用库。代理位于忽略的 `frontend/node_modules/.tmp/issue28-preview.ts`，不修改跟踪 API 配置、后端 CORS 或 5174 现有服务；端口 5176 保持运行供用户审查。
- 浏览器直接读取 ECharts 实际 option，核对总次数/入湾/出湾八日值、窗口外 null、油价/通行量开关、UTC+8 切换不移动同一时刻标记；回放推进后标记更新而完整事件带保持不变。UTC+8 点击 2 月 28 日事件定位到当地 00:00，实际新闻详情保留 12 个来源链接。
- 初始已完成快照 30 艘，构成 7/7/10/6；四类点击后列表分别为 7/7/10/6，清除恢复全部。地图缩放不改变构成；延迟窗口响应期间仍显示旧快照，完成后更新到 16:05；点击未来日期跳转、回到起点通过。
- 模拟响应页单独验证同日折叠、无日期/无效日期/窗外事件排除、无坐标事件日期跳转与详情、空快照/无 NaN/四类禁用；不改数据库。
- 1440px/390px 验证与截图检查通过，390px 无横向溢出，图表减少为 4 个刻度分段并保持可读；隐藏总览切回正常初始化。最终浏览器控制台 0 error / 0 warning（消除原隐藏容器图表 warning）。本地证据：`output/playwright/issue28-acceptance.js`、`issue28-edge-acceptance.js`、`issue28-overview-desktop.png`、`issue28-overview-details.png`、`issue28-chart-mobile.png`，忽略产物不提交。

限制：无新增动态统计 API，不重算历史批次或校准门线/来源完整性；图表展示固定历史窗口，不代表实时数据。没有因果判断、风险评分或源数据修改；未做整周连续播放、典型案例完整回归或真实模型问答。Vite 仍提示既有大 bundle 警告；本轮未进行无关代码拆包。PR 提交与部署是不同状态，用户已授权合并并完成。

## 2026-09-30 地图探索与总览精简

交付状态更新（2026-10-02）：用户授权后，已单独本地提交为 `e58eac1`，随 PR #29 的功能分支推送；已随 PR #29 合入远端 main。下方保留 2026-09-30 的验收与当时交付状态。

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

## 当前判断（2026-10-08 文档核对）

- SQL-02～06 已完成语义视图、SQLGlot 校验、独立只读执行、工具接入和隔离验收；这些成果作为新 SQL Agent 的安全执行底座保留。
- ~~当前 `runner.py` 仍是自定义 Tool Calling 循环，并包含大量固定短语分类；它是现状，不是下一版目标。~~ LC-04 起该循环与固定短语分类已删除（`runner.py` 移除，`langchain_runner.py` 为唯一编排入口），当前契约以本文件顶部摘要为准，LC-04保留历史实施证据。
- 当前已使用 LangChain 单智能体，让模型基于系统提示、项目知识、Tool 描述和数据库 schema 选择自然回答、知识检索、业务 Skill 或 SQL；通行/区域已有2026-10-07真实模型单业务样本；跨业务多轮已有 #47 的 2026-10-08 验收（issue47_multi_turn_acceptance.md）；更广题集仍未系统验收，见本文件顶部当前摘要。
- 第一版不直接编写 LangGraph、不做多智能体和服务端会话持久化。
- LC-01 已完成基础接入（见下方实施记录）：统一序列化修复了 `median_gap_minutes: Decimal` 导致的 HTTP 500，编排切换到 `create_agent`；范围外与问候由模型自然回答。

## 历史实施看板（2026-09-22 起的 LC 阶段记录）

此看板保留当时阶段状态；当前工具与验证范围以顶部摘要为准。

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

- [SQL-02 语义视图与只读角色](archive/query_analytics_sql02.md)
- [SQL-03 AST 策略](archive/query_analytics_sql03.md)
- [SQL-04 独立执行器](archive/query_analytics_sql04.md)
- [SQL-05 工具循环接入](archive/query_analytics_sql05.md)
- [SQL-06 综合验收](archive/query_analytics_sql06.md)
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

## 2026-10-07 Issue #43 北冰洋故事交互

状态：**已验证，PR #44 已合入 main（b0ed92f），本地已同步并保留原技能提交；未部署**。负责人 Codex，独立分支 `codex/arctic-story` / worktree `codex-arctic-story`；初始基线acfc7af，交付以origin/main的f555ec7为基线，只携带任务改动。预览5182只读复用8000，不更改数据库、后端契约或依赖。实现三个阶段/完整故事、分段起点播放与末界停止、航速采样曲线/滑块定位、缺报与报道证据边界、手机下方面板、收起/退出、阶段完整范围聚焦。

2026-10-07 build/check:workbench/diff检查通过；Playwright验证真实案例2352采样点、阶段切换新增轨迹请求0、播放暂停/末界/快速切换/时间定位、1280×720及390×844/reduced-motion/退出恢复；路由夹具验证未导入、图片失败、503重试，无pageerror。保留既有大bundle警告；后端/真实模型与导入未重验。无新业务工具，沿用既有案例上下文及轨迹接口。详细实现、证据与限制见[案例说明](arctic_ocean_case.md#2026-10-07-issue-43-故事与交互升级)。README、案例说明和FRONTEND_WORKBENCH已在本任务分支同步；与区域业务共享文件的合入需由整合者串行协调。


2026-10-08 文档PR收尾：核对PR #51 head 737027b、无未解决审查意见，合并为e8e843c；88个相对文件链接与重复摘要断言、git diff --check再次通过。本轮仅文档与Git核验，未运行模型/数据库/浏览器业务测试，未启动或停止服务。任务草稿与核验脚本归档在主目录Git忽略目录local-archive/analysis-roadmap-docs-2026-10-08；清理范围仅本任务工作树与分支，其他工作树及output/保留。

## 2026-10-08 Issue #49 第二典型案例

负责人Codex，处理模式，基线33f2b69，独立分支codex/athe-nova-evidence。唯一双标识ATHE NOVA / 334931000 / 9188116通过库与外部平台对照，16,086条现有七日报位用于案例。实现三阶段、六张证据卡、双案例选择、时间定位和退出恢复；两段缺报与3月3日后续观测分别标明，不能确认击沉/主动关闭AIS/缺口原因。无迁移、导入、新业务工具或模型调用。状态已验证、已合并；394 passed/14 skipped、构建/工作台及浏览器样本通过，未验证边界见[案例说明](athe_nova_case.md)；[PR #52](https://github.com/sure-660322/Hormuz/pull/52)已于2026-10-08合入main（`39eb3d7`），Issue #49已关闭；本地已同步，任务工作树/分支与预览已清理，未部署。

## 2026-10-08 Issue #54 区域边界显示

当前状态（2026-10-09）：[PR #58](https://github.com/sure-660322/Hormuz/pull/58) 已合入 main（`5ac0565`），本地已同步；用户授权清理后，5184 预览、工作树登记和本地任务分支已清理，验收资料归档并核对 SHA-256。下方为 2026-10-08 交付事实，本轮不重做业务验收；未部署。详情见[记录](issue54_area_boundary.md)。

负责人 Codex，模式「处理」，独立分支 `codex/issue-54-area-visibility`，基线 `fe39137`。范围为 App.vue / MapView.vue / AreaActivityPanel.vue、必要样式与浏览器验收脚本；不修改统计服务、数据库、依赖清单或凭据。三个区域交互状态已分离，条件/结果保留、案例暂停与退出恢复已实现，旧坐标条移至面板详情。当前为任务分支交付，未合并、未部署；验证证据与限制见[本轮记录](issue54_area_boundary.md)。与总任务 #53 的其他界面任务串行整合共享组件，保留各自任务范围。

2026-10-08 #54 同分支继续用户注释返工，新增 ExplorerSidebar 与区域展示纯函数范围：修复提示层级、压缩左侧顶部、保留完整标题、聚合其它船型选项、以 AIS 已加载时间轴初始化活动/比较日期。实现commit `5ff7735`，S11 28项与S12 15项通过，语义检查32/32及构建/工作台通过；PR #58 待整合，未合并/部署，详见[返工记录](issue54_area_boundary.md#2026-10-08-用户注释返工)。

## 2026-10-09 Issue #55 典型案例布局

负责人 Kimi，模式「处理」，独立分支 `kimi/issue-55`，基线 `01b3f77`，worktree `Hormuz-worktrees/kimi-issue-55`。范围为 CasePanel.vue、App.vue 案例状态与 style.css 案例模式样式；不改案例源事实、数据库、后端契约或地图服务。父任务 #53 的另一界面子任务。

实现案例停靠侧栏与「过程 / 证据」阅读视图：面板停靠地图左侧（340px），地图按真实剩余区域计算尺寸；页签只改变阅读视图，两视图独立滚动；案名选择器/日期/船舶资料固定头部；收起保留案例模式并带案例名恢复入口，退出为文字按钮；智能体同屏自动收起案例栏；航速图移入次级展开区；证据视图标明全案例范围、不做阶段关联。build/check:workbench/git diff --check 通过；内置浏览器 1280×720 首屏、1440/1024/390 响应式、页签/键盘/切案例/收起展开/退出恢复核验通过，无新增控制台错误。详情与未验证范围见[案例说明](athe_nova_case.md#2026-10-09-issue-55-停靠侧栏与阅读视图)。

状态：**已验证，PR #60 已合入 main（`a500923`），Issue #55 已关闭；本地已同步，任务工作树/分支已清理，未部署**。

## 2026-10-09 Issue #56 典型案例证据阶段关联

负责人 Kimi，模式「处理」，独立分支 `kimi/issue-56`，基线 `74dcbdc`，worktree `Hormuz-issue-56`。父任务 #53；依赖 #55 的阅读视图框架。范围：后端案例契约最小扩展（`schemas.py` 证据/文章展示元数据、`athe_nova_case.py` 与 `routers/cases.py` 证据登记与映射）、前端 CasePanel 证据视图重组、App.vue/MapView 定位链路、api.ts 类型、workbench 检查与四份文档；不改数据库、不重导入、不新增新闻采集或因果推断。

实现「当前阶段 → 相关证据 → 原始细节/来源/地图观测」链路：证据带稳定 id、kind（ais_observation / report / boundary / identity）与 stage_ids（空 = 案例级）；报道按 url 去重合成并补摘要；证据视图「当前阶段 / 全部」筛选默认跟随当前阶段、手动保持，分组列表默认只显摘要，坐标/行号/身份匹配收进单层展开详情；AIS 证据「定位地图」暂停播放 + seek + 地图观测点标记（尊重减少动态），缺报/范围外/未加载给具体原因，`trackPointAt` 不向缺报区间外推；快速定位末次生效（caseVersion）。build/check:workbench（新增 trackPointAt 断言）/git diff --check 与后端案例契约测试（11 passed / 2 skipped）通过；内置浏览器 DOM 实测两案例筛选/去重/展开/定位/键盘/多视口。详情与未验证范围见[案例说明](athe_nova_case.md#2026-10-09-issue-56-阶段关联证据视图)。

状态：**已验证，[PR #61](https://github.com/sure-660322/Hormuz/pull/61) 已合入 main（`4e46299`），Issue #56 已关闭；本地已同步，任务工作树/分支已清理，未部署**.
