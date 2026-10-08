# Issue #47 综合多轮问答与证据联动验收记录

> 2026-10-08，负责人 Kimi，闭环模式；分支 `kimi/issue-47`，worktree
> `D:/my_project/Hormuz-worktrees/kimi-issue-47`，基线 `origin/main`（33f2b69）。
> 数据库目标：本机应用库 `aisdb` **只读**（无写入/迁移/重建）；前端 5175（临时，
> 代理至本任务后端 8033），用户既有 5174/8000 服务未改动。真实模型 DeepSeek
> （deepseek-flash），模型调用费用按既有演示环境口径。

## 结论

三组「对话 → 分析 → 证据 → 地图」演示在真实模型下全部通过；同条件手动 API 与
智能体工具核心结果逐项一致；验收中发现的 6 处缺陷已修复并回归通过。
后端 393 passed / 14 skipped；前端 build 与 check:workbench 通过；
Playwright（本机 Edge）浏览器验收 9/9 通过。未部署。

## 演示与追问（真实模型，2026-10-08，后端 8033）

原始请求/响应转录：`output/issue47/*_group*.json`、`*_retest.json`
（Git 忽略目录，含完整工具调用参数与回答，可复核）。

### 组 1：同船型两期通行比较 + 两条条件修改追问

| 轮 | 问题 | 工具调用 | 关键结果 |
| --- | --- | --- | --- |
| 1 | 比较 02-25 与 02-28 油轮通行 | `compare_strait_passage_statistics`（油轮，全方向） | 53→43 次；入湾 24→17；出湾 29→26；partial（缺报） |
| 2 | 「那货船呢？」 | 同工具重新调用（船型改货船，参数隔离 ✓） | 22→32 次 |
| 3 | 「还是油轮，只看东向西」 | 同工具重新调用（direction=east_to_west） | 24→17 次；未统计方向为 null（未当 0）✓ |

### 组 2：默认区 → 圈选矩形 → 两期比较 → 恢复默认

| 轮 | 问题 | 区域 | 工具调用 | 结果 |
| --- | --- | --- | --- | --- |
| 1 | 02-27 全天活动 | 默认区 hormuz_core_v1 | `query_area_ship_activity` | 429 艘 / 461 次访问 / partial |
| 2 | 「同样问题在我圈选矩形」 | custom 56.2–56.7E/26.1–26.7N | 同上 | 186 艘 / 191 次访问 |
| 3 | 两期比较（圈选区） | custom | `compare_area_ship_activity` | 180→198 艘等 |
| 4 | 「恢复默认区域再比较」 | 默认区（请求不带矩形） | 同上重新调用 | 510/577 访问等（修复后） |

修复前第 3、4 轮模型**未调工具直接编造比较数字**（两次），违反验收条件 2；
系统提示增加「多轮引用纪律」（规则 9）与「恢复默认区域直接省略矩形调工具」指引后复测通过。

### 组 3：并列分析 + 证据单船轨迹

| 轮 | 问题 | 工具调用 | 结果 |
| --- | --- | --- | --- |
| 1 | 02-28 油轮通行 + 默认区活动并列 | `query_strait_passage_statistics` + `query_area_ship_activity` 同轮并联 | 两类 analysis_actions 同轮共存不混用 ✓ |
| 2 | 「把这段时间通过海峡的一艘油轮轨迹显示在地图」 | `query_strait_passages`（证据 22 条） | 多船候选 → 列出候选表请用户指定（澄清正确） |
| 3 | 「显示 STALLION 的轨迹」 | `search_ships` + `get_ship_track` | 2085 条报位；自动生成 `ship_track/automatic` 地图动作 ✓ |

## 同条件对账（手动 API vs 工具）

`scripts/issue47_reconcile.py` 依据转录中工具实际生效参数重放手动接口：

- 通行比较 3 组（油轮/货船/东向西）：两期 `passage_count / unique_ship_count /
  inbound_count / outbound_count / uncertain_candidate_count` 共 30 项全部一致。
- 区域活动/比较 5 组（默认区 + 圈选矩形）：`visit_count` 等汇总全部一致。
- 已知语义差异：带方向过滤时**工具**把未统计方向置 `null`（未统计），**手动
  API** 该字段为 `0`；计数本体一致，null≠0 的口径在智能体提示与知识库中已声明，
  属 #40 既有设计，不在本轮改动范围。

## 验收中发现并修复的缺陷

1. **`AgentAnalyzeResponse.analysis_actions` 合并损坏（HTTP 500）**：#40/#41 合并时
   两个动作成员被写进同一个 `AgentAnalysisAction` 类（第二类字段覆盖第一类），
   任何含 `passage_analysis` 动作的智能体响应在校验层 500。拆分为
   `AgentPassageAnalysisAction | AgentAreaAnalysisAction` 判别联合；
   新增 `backend/tests/test_agent_analysis_actions_schema.py` 3 项回归。
2. **追问编造数字**：历史回答中的数字被模型直接引用/计算。系统提示新增规则 9
   （多轮引用纪律）与区域提示「恢复默认区域」指引。
3. **compare 工具信封缺 `daily`**：面板回填后证据按日选择器为空、证据无法加载。
   `a_period/b_period` 增补 `daily`（方向过滤时未统计方向同步置 null）。
4. **通行分析回填首挂载失效**：`PassageAnalysisPanel` 的 restore watch 无
   `immediate`，面板随 `analysisOpen` 首次挂载时动作已就位导致漏回填；
   `OverviewPanel` 收到 restore 也不自动展开。修复：restore watch 改 immediate
   （并移至证据状态声明之后），OverviewPanel 监听 restore 自动展开。
5. **元数据默认值覆盖回填**：`onMounted` 的 meta 到达后无条件重置日期与船型，
   把已恢复条件改回默认（证据守卫因此丢弃回填响应）。meta 默认值仅在无
   `resultStamp`（未回填/未查询）时应用。
6. **区域面板首挂载 bootstrap 失效**：`AreaActivityPanel` 的 `open` watch 无
   `immediate`，首次打开时 `bootstrapOnOpen`（含智能体回填）不执行。补 immediate。
7. 工具过程展示补齐 5 个新工具的中文标签（通行统计/通行比较/区域在场/区域活动/区域比较）。

## 边界与异常样本（2026-10-08，8033）

- 超限均正确 422：通行统计 >7 天、agent 窗口 >24h、矩形跨度 >10°。
- 远海矩形（40–41°E/10–11°N）：`status=no_data`、`scoped_fix_count=0`，
  未被误述为「零船」；缺报/部分覆盖在演示中以 `partial` 真实出现。
- 取消：浏览器点击「停止」→ 前端 AbortController 取消、回合不悬挂（验收 9/9）。
- 快切：连续两次提交，旧响应不覆盖新回合（验收 9/9）。
- 超时：整体 60s 预算与取消门的离线回归在 LC-R2 用例覆盖（本轮未做真实慢查询注入；
  #41 曾以只读慢查询验证真实超时路径）。

## 浏览器验收（Playwright + 本机 Edge 126，5175→8033）

`output/issue47/e2e/acceptance.js`，结果 9/9 PASS（截图在同目录 `shots/`）：
页面加载、通行比较回答与入口、面板回填条件与结果、证据轨迹加载与地图联动
（track-window 请求 2 次）、追问改船型重新调用、取消、取消后无悬挂回合、
快切唯一结果、控制台无错误。

- 既有数据缺口：`/events/evt_076/cover` 404（新闻封面素材缺失，与本轮无关，
  属 chinanews 素材任务范围），验收脚本已按既有问题豁免并在此声明。
- 区域回填冒烟：`debug-area.js` 两步入口（回答内按钮 → 建议条「查看区域分析」）
  条件与汇总恢复成功（截图 `shots-area/06-area-restore.png`）。

## 命令记录

- 后端：`python -m pytest backend/tests -q` → 393 passed / 14 skipped。
- 前端：`npm run build` ✓；`npm run check:workbench` PASS。
- 演示：`python scripts/issue47_demos.py --base http://localhost:8033`；
  复测 `scripts/issue47_retest.py`；对账 `scripts/issue47_reconcile.py`。

## 未验证 / 不包含

- 未部署；真实模型仅 deepseek-flash 样本，未做更多模型横评。
- 真实慢查询超时注入本轮未重跑（沿用 #41 记录）；并发预算未验收。
- 触屏/纯键盘圈选维持 #41 已排除范围。
- evt_076 封面 404 未修复（不属本任务）。
