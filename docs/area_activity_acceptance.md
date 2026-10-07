# 区域船舶活动与进出分析：第二、三阶段独立验收报告

验收日期：2026-10-07（本机，UTC 记录）
初轮验收人：verifier（独立验证，未修改实现代码）；§七接手复测：Codex（修复并复测）
范围：issue #41 第二阶段（前端矩形圈选、三模式面板、地图联动）与第三阶段（三个区域智能体工具、当前区域上下文、「查看区域分析」动作）。第一阶段后端算法与 REST API 的验收见 [area_activity_backend_verification.md](area_activity_backend_verification.md)（当时批次），§一至六保留初轮实测，修复后结果在 §七；历史报告中 165 字段的计数有误，脚本实际为 163 项断言（含状态项）。

## 状态四项

| 项 | 状态 | 依据 |
| --- | --- | --- |
| 实现 | 已实现（工作树内） | 第二阶段与第三阶段代码已在工作树；本报告对应 HEAD 见 §一 |
| 测试 | 见 §二（含失败项与缺陷清单） | 初轮 366/14 与 49 PASS/3 FAIL 保留为历史；最终 390/14、前端检查通过、浏览器 62 PASS/0 FAIL/0 BLOCKED，详见 §七 |
| 提交 | 已提交本地分支 | `371afe3 feat(area-activity): 手动矩形圈选、三模式面板与智能体区域工具（issue #41 第二、三阶段）`（`codex/area-activity-ui`）；验收期间的后续修复见 §一 |
| 推送 / 部署 | 任务分支交付到 PR，未合并/未部署 | 当前交付 PR 见 §七；main 尚不含 #41 |

## 一、环境与基线

| 项 | 值 |
| --- | --- |
| 工作树 | `D:\my_project\Hormuz-worktrees\codex-area-activity-ui` |
| 分支 | `codex/area-activity-ui` |
| 任务基线 | `aca8d3c`（第一阶段修复提交） |
| 验收时 HEAD | 见 §七「最终复测记录」（本次先记录 `371afe32d4e9fccf36af42753d9e3b214131b1fd`，Lead 后续修复后复测） |
| 后端服务 | `.\backend\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --port 8031`（Lead 启动，无 `--reload`） |
| 前端服务 | `npm run dev -- --port 5177 --strictPort`（vite dev，`--host 127.0.0.1`，`VITE_API_PROXY_TARGET=http://127.0.0.1:8031`；**必须用 `127.0.0.1:5177`**，用 `localhost` 会绕过代理） |
| 其他会话端口 | 5174、8000 未触碰（5174 仅做过页面加载冒烟，用于校验验收脚本机制） |
| 数据库 | 只读 `aisdb@127.0.0.1:25432`；实测 `ships=4,462`、`ship_positions=17,933,173`、`ais_import_batches=8`（本轮核验值，非跨环境常量） |
| 模型 | `deepseek-chat`（`backend/app/services/agent/model_client.py: default_model()`；`.env` 未设 `DEEPSEEK_MODEL`），经 8031 后端调用；密钥未读取、未输出 |
| 浏览器 | Playwright 1.63.0（npx 缓存）+ msedge headless；`NODE_PATH=C:\Users\18242\AppData\Local\npm-cache\_npx\e41f203b7505f1fb\node_modules` |
| 验收脚本与证据 | `output/acceptance/`（脚本、JSON、截图、日志） |

## 二、验证项与结论

| # | 验证项 | 命令 / 脚本 | 结果 |
| --- | --- | --- | --- |
| 1 | 后端全量回归 | `.\backend\.venv\Scripts\python.exe -m pytest backend/tests -q` | **366 passed / 14 skipped in 12.09s**（第一阶段基线 329/14；新增 37 项区域智能体工具测试） |
| 2 | 独立复算 + 与 API 逐字段核对 | `python -X utf8 output\acceptance\independent_recompute.py` → `compare_api_vs_recompute.py` | **14 组条件 / 165 个字段全部一致**（快照 4 字段×1、活动 5 摘要+5 每日+1 场景、A/B 4 指标×a/b/delta/change_rate） |
| 3a | 前端构建 | `cd frontend; npm run build` | 见 §三（验收期间失败：`vue-tsc` 类型错误；Lead 修复后复测） |
| 3b | 工作台语义检查 | `npm run check:workbench` | PASS（`spatial distance, temporal filtering, search, identity, replay ordering/seeking, bounded real AIS snapshots, empty/error/retry states`） |
| 3c | 区域面板语义检查 | `node checks/area-activity.cjs` | **30/30 checks passed，退出码 0** |
| 3d | 空白/行尾检查 | `git diff --check` | 退出码 0（干净） |
| 4 | 浏览器验收（桌面 1440 / 窄屏 390） | `node output\acceptance\area_activity_browser.cjs --base http://127.0.0.1:5177` | **49 PASS / 3 FAIL**；截图同目录 `shot-*.png`，结构化结果 `browser_acceptance.json` |
| 5 | 手动面板数字 ↔ 原始 API ↔ 智能体工具 三方一致 | 脚本 4 项 + `agent_result_recheck.py` | 数字全一致（§五、§六）；发现区域身份回显不一致（缺陷 F2/F5） |
| 6 | 真实模型三问 | `python -X utf8 output\acceptance\agent_real_model_check.py --limit 3` | 3 次调用（预算 8），全部 HTTP 200；`ok`/`partial`；工具与数字全部符合（§六） |
| 7 | 未验证项 | —— | 见 §八 |

## 三、逐项证据

### 3.1 后端全量回归（验证项 1）

```
.\backend\.venv\Scripts\python.exe -m pytest backend/tests -q
... 366 passed, 14 skipped in 12.09s
```

对照第一阶段基线 329 passed / 14 skipped：新增 37 项（`backend/tests/test_agent_area_tools.py` 等），无回归、无新增 skip。退出码 0。

### 3.2 独立复算（验证项 2，不引用后端算法模块）

脚本 `output/acceptance/independent_recompute.py`（自写 SQL + 朴素 Python 实现，只依据 `docs/area_activity.md` 口径；`SET TRANSACTION READ ONLY` 生效，运行前后 `ships` / `ship_positions` / `ais_import_batches` 行数与 `pg_stat_user_tables` 写计数完全一致，语句前缀只有 `select/set/show`）。证据：`independent_recompute.json`。

本轮独立复算结果（本机实测）：

| 场景 | 参数 | 结果 |
| --- | --- | --- |
| 时刻在场 | 默认区（25.8/55.8/27.1/57.1），2026-02-28T12:00:00Z | 在场 175；区域外新鲜 1,438；过期 2,240；参与判定 3,853 |
| 时段活动 1 天 | 默认区，[2026-02-28T00:00Z, 2026-03-01T00:00Z) | 去重船 430；进入 298；离开 313；累计船时 4,098.465；访问 577 |
| 时段活动 3 天 | 默认区，[2026-02-26T00:00Z, 2026-03-01T00:00Z) | 去重船 818；进入 742；离开 758；累计船时 13,424.081；访问 1,080；Σ每日船秒 = 全窗船秒（self-check 通过） |
| 自选矩形 | 26.0–26.8N / 56.0–56.9E，1 天 | 去重船 220；进入 256；离开 283；船时 1,032.807 |
| 自选矩形 A（西半） | 25.8–27.1N / 55.8–56.45E，1 天 | 去重船 352；进入 240；离开 239；船时 2,949.767 |
| 自选矩形 B（东半） | 25.8–27.1N / 56.45–57.1E，1 天 | 去重船 185；进入 171；离开 188；船时 1,145.427 |
| 批次=[4] | 默认区 1 天 | 去重船 399；进入 243；离开 244（批次口径独立核对） |
| 船型=油轮 | 默认区 1 天 | 去重船 105；进入 115；离开 123；船时 999.847 |
| A/B（同矩形两期） | 默认区 [02-27,02-28) vs [02-28,03-01) | delta：+1 艘 / +94 进入 / +98 离开 / −508.124 船时；change_rate：0.002331 / 0.460784 / 0.455814 / −0.110304 |
| A/B（矩形 A 两期） | 55.8–56.45E | delta：−11 / −54 / +23 / −367.934 |
| A/B（矩形 B 两期） | 56.45–57.1E | delta：−29 / +21 / +41 / −139.897 |

跨矩形同窗口（A 与 B 同一天）也独立算过（−167 艘 / −69 进入 / −51 离开 / −1,804.340 船时），但 `/api/area-activity/compare` 按契约 §2.5 要求两期同一矩形，因此该组只作几何对照，不作为 API 期望值。

**与 API 逐字段核对**（`compare_api_vs_recompute.py`，期望值全部来自上面的独立复算）：

```
OK snapshot_default_2026-02-28T12:00Z : 5/5
OK activity_default_1d_2026-02-28 : 10/10
OK activity_custom_26.0-26.8N_56.0-56.9E_1d : 10/10
OK activity_rectA_west_1d : 10/10
OK activity_rectB_east_1d : 10/10
OK activity_default_1d_batch4 : 10/10
OK activity_default_1d_ship_type_oil : 10/10
OK activity_default_prev1d_2026-02-27 : 10/10
OK activity_default_3d_2026-02-26_03-01 : 20/20   ← 含 3 天每日船秒、每日进入/离开、visits_touching_day
OK activity_rectA_west_prev1d : 10/10
OK activity_rectB_east_prev1d : 10/10
OK compare_default_prev1d_vs_1d : 16/16
OK compare_rectA_prev1d_vs_1d : 16/16
OK compare_rectB_prev1d_vs_1d : 16/16
PASS
```

说明（不是缺陷，但需随数字表述）：API 把 `change_rate` 四舍五入到 4 位小数（0.46078431 → 0.4608），`compare_api_vs_recompute.py` 因此按 5.1e-5 容差判定并额外校验 `equals_round_4dp`；`a/b/delta` 为精确值。`observed_ship_hours` 容差 0.01 h、每日船秒容差 1 s。

### 3.3 前端（验证项 3）

| 命令 | 结果 |
| --- | --- |
| `cd frontend; npm run build` | 见 §七（Lead 修复后复测）；验收期间失败：`App.vue` 引用未声明的 `agentDraft`（TS2304/TS2339）、`MapView.vue` 的 `L.DomEvent.on` handler 类型不匹配（TS2769）。完整日志 `output/acceptance/frontend_build.log` |
| `npm run check:workbench` | PASS，退出码 0 |
| `node checks/area-activity.cjs` | 30/30 checks passed，退出码 0 |
| `git diff --check` | 退出码 0 |

补充接口核对（只读，用于前端契约）：

- `GET /api/area-activity/ship-types` → `status=ok, source=nnu_ais, total_ships=4462`，25 个船型选项；保留值 `__missing__`=707（缺失/空）、`__unknown__`=348（未知），与 `ships` 表取值分布一致。
- `POST /api/area-activity/resolve-area`（超跨度）→ `422`，`{"detail":{"code":"INVALID_REQUEST","message":"矩形单边跨度不能超过 10°，当前纬度 10°、经度 12°","request_id":"…"}}`。
- `GET /api/area-activity/default-area` → `hormuz_core_v1 / 1.0.0 / is_default=true`，边界 55.8/25.8/57.1/27.1，`algorithm.version=1.0.1`。

### 3.4 浏览器验收（验证项 4）

命令：

```powershell
$env:NODE_PATH='C:\Users\18242\AppData\Local\npm-cache\_npx\e41f203b7505f1fb\node_modules'
node .\output\acceptance\area_activity_browser.cjs --base http://127.0.0.1:5177
```

结果：**49 PASS / 3 FAIL**（`output/acceptance/browser_acceptance.json`，截图 `shot-S*.png`）。逐条：

| 步骤 | 检查 | 结果 |
| --- | --- | --- |
| S0 | 面板可打开、控制台 0 error | PASS |
| S1 | 状态条显示默认区域（名称/边界/「默认项目分析区域（非官方航道）」）、面板 `p.aa-area-name` 与「默认区域」chip、默认区无「待查询」标记 | PASS |
| S2 | 地图缩放（滚轮）+ 平移后，状态条坐标与面板边界完全不变 | PASS |
| S3 | 拖拽圈选 → 状态条变「自选矩形（非官方航道）」、`area_id=custom`；ESC 取消不改变区域且 `area-draw-hint` 消失；超大矩形（缩放 3 步后拖出 4.31°×14.68°）被后端拒绝（422「矩形单边跨度不能超过 10°…」）且区域回滚；「恢复默认区域」回到 `hormuz_core_v1` 并恢复默认标记 | PASS ×4 |
| S4 | 三模式成功查询：快照 在场船数=175（独立复算 175）；活动 430/298/313/4098.5 h（独立复算 430/298/313/4098.465）；比较表 4 项指标 A/B/delta/change_rate 与独立复算一致 | PASS ×6，另 1 项 FAIL（缺陷 F2） |
| S5 | 有效零结果（2026-03-05T00:00Z，报位全部过期 → 在场 0 且 `p.aa-empty` 提示）；参数错误（start ≥ end）被前端拦截并提示 | PASS ×2 |
| S6 | 7 天长查询点「取消」后 20 s 内加载态结束；取消/切模式后旧响应不覆盖新条件（新条件结果=175，与独立复算一致）；查询后变更区域 → 面板标「区域已变更，待查询」 | PASS ×3 |
| S7 | 访问明细 500 行；正常时长访问（`s6026:f11707360`，02-27T18:00→02-28T06:24:36）点「地图定位」→ 轨迹请求 `from/to` 与访问时段一致、船号一致，地图图形 76→162 | PASS；跨度 36.00 h 的访问 FAIL（缺陷 F1）；另有 1 项控制台 FAIL（环境项，见 §五） |
| S8 | 1440×900 与 390×844 均无横向溢出（doc/body scrollWidth == clientWidth）；`prefers-reduced-motion: reduce` 生效且无报错 | PASS ×3 |
| S9 | 智能体回答 → `.area-suggest-bar` →「查看区域分析」→ 面板打开并回填模式/时刻 | 见 §七（Lead 修复 build 后复测，1 次模型调用） |

### 3.5 三方一致性（验证项 5）

同一参数下：

1. **独立复算 ↔ 原始 API**：§3.2，165 字段 0 差异。
2. **面板显示 ↔ 独立复算**：浏览器 S4 在页面 DOM 上逐字段核对（在场 175、出现 430、进入 298、离开 313、累计船时 4098.5、A/B A=429/B=430 delta=1/94/98/−508.12），全部一致。
3. **智能体工具 envelope ↔ 独立复算**：`agent_result_recheck.py` 对三问共 42 项字段核对全部一致（§六）。

唯一不一致的是「区域身份」而非数字：面板/智能体在默认矩形下把结果显示为 `area_id=custom / is_default=false`（缺陷 F2、F5）。

### 3.6 真实模型验收（验证项 6）

脚本 `output/acceptance/agent_real_model_check.py --limit 3`（**共 3 次调用，预算 8 次**），直接 POST `http://127.0.0.1:8031/agent/analyze`，请求带 `area_context = {west:55.8, south:25.8, east:57.1, north:27.1, area_id:"hormuz_core_v1", label:"霍尔木兹海峡核心通行区（项目分析区域）"}`。证据 `agent_real_model.json` / `agent_real_model_answers.txt` / `agent_consistency.json`。

| # | question（摘要） | 时间/耗时 | HTTP/status | tools_used | analysis_actions(mode) | 关键数字（与独立复算） |
| --- | --- | --- | --- | --- | --- | --- |
| a | 「2026-02-28T12:00:00Z 这一时刻，当前分析区域内有多少艘船在航？给出在场船数、区域外新鲜报位数、过期报位数、参与判定的船数。」 | 12:30:54Z / 5.7 s | 200 / `ok` | `query_area_ship_snapshot` | snapshot | 175 / 1,438 / 2,240 / 3,853 —— 与独立复算一致 |
| b | 「2026-02-28T00:00:00Z 到 2026-03-01T00:00:00Z（UTC 半开），当前分析区域内船型为「油轮」的船舶活动：出现多少艘、观测进入/离开多少次、累计船时多少小时？」 | 12:30:59Z / 7.4 s | 200 / `partial` | `query_area_ship_activity` | activity | 105 / 115 / 123 / 999.847 h —— 与独立复算一致 |
| c | 「比较当前分析区域 A=2026-02-27→02-28 与 B=2026-02-28→03-01 的出现船数、进入、离开、累计船时的 delta 与 change_rate」 | 12:31:07Z / 11.2 s | 200 / `partial` | `compare_area_ship_activity` | compare | A 429 / B 430（delta +1，rate 0.0023）；进入 204/298（+94，0.4608）；离开 215/313（+98）；船时 4,606.589/4,098.465（−508.124）—— 与独立复算一致 |

核对结论：

- `analysis_actions[0].type="area_activity"`、`mode` 与提问一致；四边界 55.8/25.8/57.1/27.1 与请求一致；时间字段（`at` / `start_at,end_at` / `start_a,end_a,start_b,end_b`）与提问一致。
- `status=partial` 的原因在 `summary` 中给出：明细被截断（`detail_truncated=true`、`visits_not_shown`），汇总仍完整；回答未把 `partial` 说成 `no_data`。
- 三问的 `analysis_actions.query.area_id` 均为 `custom`、`area_is_default=false`，与请求的 `hormuz_core_v1` 不一致（缺陷 F5）。

## 四、本轮发现的缺陷（附最小复现）

### F1（中）访问明细「地图定位」对跨度 >24 h 或 =0 的访问失效

- 现象：默认区 1 天窗口（2026-02-28）明细 500 行中 **138 行跨度 >24 h 或 =0**（36.00 h 例：`s381:f10487701`，2026-02-27T18:00:00 → 2026-03-01T05:59:58）；点击这类行的「地图定位」提示「轨迹时间窗无效或超出本批 AIS 覆盖；单次最多 24 小时。」，地图无轨迹。
- 根因链：`frontend/src/domain/areaActivity.ts:822 visitLocateArgs()` 原样传 `first_inside_at/last_inside_at` → `frontend/src/App.vue:623` 判定 `end - start > 86400000` 即 `fail(...)`（同样拦截 `start >= end`，即单报位访问）。
- 期望：对超 24 h 的访问裁剪到「窗口 ∩ 24 h」或按钮置灰并说明；否则验收项「点击访问记录后地图显示对应有界轨迹」对 27.6% 的明细行不成立。
- 对照（正常行通过）：`s6026:f11707360` 02-27T18:00→02-28T06:24:36（12.4 h）→ 轨迹请求 `from/to` 与访问完全一致、船号一致、地图 path 76→162。

### F2（中）面板在默认区域下仍回显 `area_id=custom`

- 现象：状态条与面板显示「默认项目分析区域 / 默认区域」，但结果概览显示「区域=自定义分析矩形、area_id=custom、is_default=false」。
- 根因：`frontend/src/components/AreaActivityPanel.vue:359` `const bounds = { ...props.bounds }` 无条件带四边界提交，后端按契约 §1.2 回显 `custom`。
- 最小复现：`GET /api/area-activity/snapshot?at=2026-02-28T12:00:00Z` → `area_id=hormuz_core_v1, is_default=true`；同一请求加 `&west=55.8&south=25.8&east=57.1&north=27.1` → `area_id=custom, is_default=false`（两者 `in_area_count` 都是 175）。UI 路径：打开区域面板 → 时刻在场 → 查询。
- 影响：身份/一致性（数字不受影响）；与档案 §1.2「默认区域请求回显 `hormuz_core_v1`」不一致。

### F3（中）智能体 `analysis_actions.query` 区域身份与请求 `area_context` 不一致

- 现象：请求 `area_context.area_id="hormuz_core_v1"`（默认矩形），三问的 `analysis_actions[0].query` 均回 `area_id="custom"`、`area_is_default=false`。
- 影响：前端「查看区域分析」按自定义矩形回填，默认区身份丢失（与 F2 同一类问题，两条入口表现一致）。
- 最小复现：POST `/agent/analyze`，`area_context` 用上面的默认区值，问「2026-02-28T12:00Z …多少艘船」，检查 `analysis_actions[0].query.area_id`。

### F4（低）轨迹已渲染但提示「地图聚焦未能完成」

- 现象：正常时长访问点「地图定位」后轨迹已加载（地图图形 76→162，`from/to` 正确），但 toast 显示「目标已加载，但地图聚焦未能完成，请重试。」。
- 复现：S7 正常访问行点击「地图定位」，读取 `.alert-toast` 文本。

### F5（阻断，验收期间）`npm run build` 失败

- 验收期间（HEAD `371afe3` + 在场未提交修改）`npm run build` 退出码 2：`src/App.vue(905,3) TS2304: Cannot find name 'agentDraft'`、`src/App.vue(1376,25) TS2339`、`src/components/MapView.vue(708/709/736/737) TS2769`（`L.DomEvent.on` 的 handler 类型）；Lead 修复过程中的中间态又出现 `L.EventHandlerFn` 不存在（应为 `L.LeafletEventHandlerFn`）。完整日志 `output/acceptance/frontend_build.log`。
- 影响：类型检查不通过；`agentDraft` 未声明会使「把区域条件带入对话」在运行时报 ReferenceError、`pending-draft` 传 undefined。
- 状态：见 §七复测记录。

## 五、已知环境项（非本功能引入，单列不计为实现缺陷）

| 项 | 证据 | 结论 |
| --- | --- | --- |
| 主页面新闻封面 `404 /events/evt_076/cover` | 5177 上 console 报此 404；`backend/app/routers/events.py:24` 取 `PROJECT_ROOT.parent/"news_raw_data"`，工作树父目录 `D:\my_project\Hormuz-worktrees\news_raw_data` 不存在，而 `D:\my_project\news_raw_data\images` 存在；主仓库 8000 同请求 200（32,761 B） | 工作树路径导致，仅 worktree 出现 |
| `403 /@fs/D:/my_project/Hormuz/frontend/node_modules/leaflet/dist/images/marker-icon.png` | 5177 → 403；5174 同资源 → 200（1,466 B）；`frontend/node_modules` 是指向主仓库的 Junction，Vite `@fs` 白名单拒绝 | 工作树 junction 导致，表现为轨迹点默认 Leaflet 图标加载失败 |

验收脚本对上述两类做了「已知环境项」单独记录（`browser_acceptance.json` 中带独立条目），其余不符预期的 4xx/控制台错误仍判 FAIL。

## 六、数字证据索引

- `output/acceptance/independent_recompute.json`：独立复算全部场景、SQL 原文、只读证据。
- `output/acceptance/api_vs_recompute.json`：14 组条件 165 字段逐项对比。
- `output/acceptance/browser_acceptance.json` + `shot-S*.png`：浏览器逐检查结果与截图。
- `output/acceptance/agent_real_model.json` / `agent_real_model_answers.txt`：真实模型三问原文与结构化记录。
- `output/acceptance/agent_consistency.json`：智能体结果与独立复算的三方一致性核对。
- `output/acceptance/frontend_build.log`、`browser_smoke.json`、`browser_recheck*.json`：构建日志与分步复测记录。

## 七、修复后复测记录（2026-10-07）

状态：三个阶段已实现；接手的 7 份文档保存为 e585eda，已在任务分支合入最新远端 main（4ce8184）及本地 main（2efd0ef）。业务代码验收 commit 为 **904e5ba**；之后提交仅验收脚本与文档，交付 HEAD 以 PR 为准。主目录与 main 未修改，未部署。

### 新发现并修复的 F6：证据轨迹后面板/提示条被遮挡

访问「地图定位」会选船并打开船舶详情，详情遮住区域访问表；提示条的关闭按钮也在区域面板下方。旧验收脚本用 DOM click 兜底，掩盖真实点击不可达。修复为区域面板打开时隐藏上下文详情、切换工具/写入对话时关闭区域面板，区域面板开启时提高提示条层级。脚本取消 DOM click 兜底并逐断言落盘。最终 S7/S9/S10 全部采用真实点击。

### 复测结果与证据

| 项目 | 本轮结果 | 命令或证据 |
| --- | --- | --- |
| 后端全量 | 390 passed / 14 skipped（12.68 s） | backend/.venv/Scripts/python.exe -m pytest backend/tests -q；含 #40 和 #41 回归 |
| 前端构建/语义/类型 | build、check:workbench、区域 30/30、隔离 vue-tsc 0 errors | frontend 下 npm run build、npm run check:workbench、node checks/area-activity.cjs --types；F6 修复后重跑 |
| API 与已有独立复算 | 14 组、163 项断言全一致，0 差异 | output/acceptance/api_vs_recompute_current.json；期望值沿用初轮 independent_recompute.json，未冒充重扫源表 |
| 浏览器整轮 S0–S10 | **62 PASS / 0 FAIL / 0 BLOCKED** | output/acceptance/browser_current_final.json；其中 11 条为已知工作树环境项记录，不代表环境错误被修复 |
| 真实模型与面板回填 | 1 次新增模型请求；snapshot、默认区 ID/标记/四边界正确；回填 at=2026-02-28T11:59，写入对话 168 字，无 ReferenceError | S9/S10；初轮三问及数字证据保留，未重复三问或声称多轮已验收 |
| 真实 PostgreSQL 超时 | **只读 on / timeout 20s / 20.056 s / HTTP 503 / QUERY_TIMEOUT** | output/acceptance/statement_timeout_current.json；在独立 TestClient 进程注入 SELECT pg_sleep(21)，由真实 PostgreSQL 取消，service 与 router 保持原逻辑；非全局配置、非源表写入、非并发压测 |
| 格式与知识库 | git diff --check 通过；区域章节可检索 | search_knowledge('区域船舶活动 query_area_ship_activity') 命中新增区域章节 |

S3 鼠标圈选/ESC/超大矩形拒绝回滚/恢复默认通过；S4 默认身份及三模式数字通过；S5 有效零与错误通过；S6 取消、旧响应守卫、区域变更标记通过。S7 正常访问和 36 h 长访问分别加载正确船舶与窗口（长访问为末 24 h，地图图形 162→298），零长度访问明确拒绝且无额外轨迹。S8 的 1440×900/390×844 均无横向溢出、减少动态生效；已查看截图确认遮挡修复与窄屏表单展示，不代表触屏设备走查。

运行资源：本轮独立 API 8032/Vite 5178，工作目录仍为 codex-area-activity-ui，数据库 aisdb 只读；原有 8031/5177、8000/5174 未重启。独立临时服务完成验收后停止，工作树与本地证据保留。

版本化的结构化证据见 [area_activity_final_verification.json](area_activity_final_verification.json)。可复跑脚本：

```powershell
# 独立期望值（会读取真实库；输出位于忽略的 output/acceptance）
backend/.venv/Scripts/python.exe -X utf8 scripts/verify_area_activity_independent.py
backend/.venv/Scripts/python.exe -X utf8 scripts/verify_area_activity_api_recompute.py --base http://127.0.0.1:8032
# Playwright 必须可解析（可通过已有 NODE_PATH）；S9 额外调用一次真实模型
node scripts/verify_area_activity_browser.cjs --base http://127.0.0.1:5178 --out browser_current_final.json
# 超时验证：独立只读会话，约 20 秒，未改运行中的 API
backend/.venv/Scripts/python.exe scripts/verify_area_activity_timeout.py
```

交付状态：任务分支已提交，PR 交付信息见本节后续记录；未合并、未部署。并发与触屏/键盘范围未完成，不能据此声称 Issue 的全部验收条件已满足。

## 八、未验证项（按实际列出）

1. 高负载真实查询超时未做压测；已通过 §七真实 PostgreSQL 慢查询注入验证 20 s 取消与 503 映射。
2. 并发与多用户响应预算——单请求实测（1 天查询约 2–6 s、A/B 约 11 s），未做并发压测。
3. 触摸/移动端手势圈选——本轮只验证鼠标事件（桌面 1440 与窄屏 390 视口，仍用鼠标）；当前代码仅注册鼠标绘制事件，触屏手势尚未支持。
4. 键盘全流程可达性——只验证了 ESC 取消绘制与表单 label/for；未做纯键盘表单走查，纯键盘矩形绘制尚未支持。
5. `no_data` 状态的浏览器展示——本轮浏览器验证的是「有效零结果（ok + 0 在场）」，`no_data` 分支由单元/契约测试覆盖，未在页面上构造（例如批量数据范围外的窗口）。
6. 跨 180°、超大经纬度、`visit_limit` 极端值等参数错误的 UI 呈现——只在 API 层与前端语义检查覆盖。
7. 视觉细节（配色、图例、趋势图在窄屏的具体呈现）需人工确认；本轮只做了溢出与控制台检查。
8. 真实模型的措辞质量与拒答边界——只验证了工具调用、`analysis_actions` 与关键数字，未做多轮追问与对抗性提问。
9. 合并与部署未执行；PR 交付状态见 §七。
