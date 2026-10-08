> 2026-10-08 收尾：用户授权整合已交付范围，[PR #45](https://github.com/sure-660322/Hormuz/pull/45) 已合入 main（3bcfea1），本地 main 已快进同步；codex/area-activity-ui 的工作树、本地/远端分支及验收服务已清理。未部署。用户随后确认触屏与纯键盘相关范围暂不做，已移出本 Issue 的待办；[Issue #41](https://github.com/sure-660322/Hormuz/issues/41) 已按已交付范围关闭。并发预算等未验证限制不因关闭而视为已验证。下方 2026-10-07 的状态与数字为当时记录，不表示本轮重做浏览器或模型验收。

# 区域船舶活动面板：前端展示层（issue #41 阶段二-A）

状态：**已实现；2026-10-07 整合后的构建、工作台检查与区域检查通过，浏览器与真实后端复测见[验收报告](area_activity_acceptance.md) §七**。
范围：本文维护组件契约；App.vue、MapView.vue、api.ts 已完成接入，统一状态以验收报告为准。下方初始隔离构建日志保留为当时记录。
基线：分支 `codex/area-activity-ui`，commit `aca8d3c`，工作树 `D:\my_project\Hormuz-worktrees\codex-area-activity-ui`。
字段事实来源：`backend/app/schemas_area_activity.py`、`backend/app/services/area_activity/service.py`、`docs/area_activity.md` §4.5/§4.6。前端不重算业务判定，汇总数字直接取后端字段。

## 一、交付文件与职责

| 文件 | 职责 |
| --- | --- |
| `frontend/src/domain/areaActivity.ts` | 纯函数：视图类型、响应归一化、UTC 时间换算、数值/时长格式化、`change_rate` 空值文案、截断提示、状态与标记文案、emit 参数与对话提示词。无副作用、无 import |
| `frontend/src/components/AreaActivityPanel.vue` | 三模式面板：区域/模式/船型/条件表单 + 结果展示 + 请求守卫 + 无障碍与窄屏；样式全部在 `<style scoped>` 内（不改 `style.css`） |
| `frontend/checks/area-activity.cjs` | 静态语义检查（30 项）+ 纯函数行为检查；`--types` 追加隔离类型检查 |
| `docs/area_activity_frontend.md` | 本文档 |

组件只调用 4 个 `api.ts` 函数：`fetchAreaShipTypes()`、`fetchAreaSnapshot(query, signal?)`、`fetchAreaActivity(query, signal?)`、`fetchAreaCompare(query, signal?)`；不自己拼 URL，不调用 `fetch`。`fetchAreaDefault()` / `resolveAreaBounds()` 未使用：区域名称/版本/默认标记由 props 传入、结果区回显响应里的 `area`。

## 二、组件契约（App.vue 对接点）

```ts
// props
{
  open: boolean
  bounds: ApiAreaBounds              // 当前分析矩形 { west, south, east, north }
  defaultBounds: ApiAreaBounds       // 默认区域矩形（用于对照展示）
  areaLabel: string                  // 例如「霍尔木兹海峡核心通行区」或「自定义分析矩形」
  areaIsDefault: boolean
  agentContext?: { shipTypes?: string[] | null; at?: string | null; start?: string | null; end?: string | null } | null
  pendingAction?: unknown | null     // 不透明：命中 mode/at/start/end/startA..endB/shipTypes 时应用并自动查询
}

// emits
close: []
'update:bounds': []                                            // 无参数：请父组件进入重新圈选流程
'results-updated': []                                          // 每次成功得到新结果时一次；失败/取消不发
'locate-ship': [{ shipId: number; startAt: string; endAt: string }]        // startAt/endAt = visit.first_inside_at / last_inside_at（ISO Z）
'focus-visit': [{ shipId: number; startAt: string; endAt: string; visitKey: string }]
'use-area-in-dialog': [{
  text: string                                                 // 可直接填入对话输入框的中文提示词
  mode: 'snapshot' | 'activity' | 'compare'
  bounds: { west: number; south: number; east: number; north: number }
  areaLabel: string; areaIsDefault: boolean
  shipTypes: string[] | null                                   // null = 全部
  at: string | null; start: string | null; end: string | null
  startA: string | null; endA: string | null; startB: string | null; endB: string | null
}]
```

行为语义：

- `agentContext` 只在面板打开（`open` false→true）或挂载时已打开时用于**预填**条件，不自动查询；预填后给出「确认后点击查询」提示。
- `pendingAction` 只在值变化且能识别出字段时生效：面板已打开则应用并自动查询一次；未打开则先记住，打开时应用并查询。识别不了的输入被忽略（`readAreaHint` 返回 null）。
- 根元素 `<aside class="aa-panel">`：`display:flex;flex-direction:column;width:100%;height:100%;min-height:0;overflow:hidden`，自身不做 fixed/absolute 定位，位置与宽度由 App.vue 的容器决定（App.vue 现用 `<div class="area-panel-placement">` 绝对定位包裹）；内部滚动区为 `.aa-scroll`。
- `results-updated` 只在成功写入一组新结果后 emit 一次（查询成功、切模式后重新查询成功、`pendingAction` 恢复并查询成功都走同一成功路径）；失败、取消、被请求版本守卫丢弃的旧响应都不 emit。父组件据此把「结果版本」推进到当前区域版本。

## 三、三模式与表单

| 模式 | 表单 | 默认值 | 说明 |
| --- | --- | --- | --- |
| 时刻在场 | 时刻 `datetime-local` | 当前 UTC 时刻 | 标签与说明均标注 UTC；内部转 ISO Z |
| 时段活动 | 起止 `datetime-local` | 当日 UTC 自然日 `[今天 00:00, 明天 00:00)` | 界面写明终点不含（半开区间） |
| 两时段比较 | A/B 各起止 | A = 前一日、B = 当日 UTC 自然日 | 说明两期共用区域/筛选/算法，允许不等长 |

- `<input type="datetime-local">` 的值按 UTC 读数，`utcInputToIso` 补 `:00Z`；非法日期（如 `2026-02-30`）返回 null 并在提交前拦下，不发请求。
- 高级参数（可折叠）：`freshness_seconds`（时刻在场）、`visit_limit`（时段活动/两时段比较），留空用后端默认。
- 表单只做「必填 + start < end」的轻量校验；矩形跨度、窗口上限等业务规则以后端 422 为准（错误经 `describeApiError` 展示后端原文）。

## 四、船型筛选

- 选项来自 `fetchAreaShipTypes()`，由 `mergeShipTypeOptions(ship_types, reserved)` 合并后端 `ship_types` 与 `reserved`（含 `__missing__`/`__unknown__`），前端不硬编码任何船型值。
- 默认全选；全选等价于查询值 `null`（不带 `ship_type` 参数），部分选择传数组。
- 「清空」后禁止提交并提示：后端把「空船型」解释为全部，静默提交会变成全选。
- 船型列表加载失败或为空时按「全部船型」提交，并如实提示失败原因；`count`/`count_scope` 逐项展示（`raw_values` 不展示，label 已足够）。
- 列表响应的 `source`/`total_ships`/`limitations` 在筛选区内展示。

## 五、结果展示

**概览区（三模式共用，出现在结果最前）**：`status` 徽标与说明、`area.name` + `area.version` + `is_default`、`area.bounds` 与 `span_deg`、`area_id`、`area.basis`、`algorithm.name/version`、`coverage`（来源/批次/批次日期/扫描报位/区域内报位/窗口内区域内报位/覆盖时间/note）、`limitations[]` 全文逐条。

- `status=no_data` 显示「读取范围内没有任何可判定报位，不能解释为『零船』」，与「有报位但区域内无船」（`ok`/`partial` 且计数为 0，显示「有效零结果」）分开处理，两种分支的文案不同。
- `partial` 说明为「有观测，但存在不确定候选或明细被截断；汇总数字仍完整」。

**时刻在场**：`in_area_count`、`out_of_area_fresh_count`、`stale_fix_count`、`evaluated_ship_count`、`freshness_seconds`；船舶表（船名/MMSI/船型/位置/航速/报位时间/龄期/新鲜度与内外标记）；`limits.list_truncated` 为真时给出截断提示（返回条数/上限/参与判定数）。

**时段活动**：全窗汇总（去重出现船数、观测进入、观测离开、累计船时、访问数、未观测间隔）、访问状态计数（完整/起点截断/终点截断/缺报中断/含质量标记/前置状态未知/边界近邻事件）；每日表（10 列）与 ECharts 每日趋势图（去重船数、进入、离开；`prefers-reduced-motion` 关闭动画，窄屏减少横轴刻度）；访问明细表可展开：进入/离开证据（`observed`、`observed_at`、`bracket_seconds`、`inside_fix`/`outside_fix` 的报位 id+时刻+经纬度、`in_window`、`near_boundary`/`wide_bracket`/`same_second_conflict`/`outside_evidence_in_context`）、`segments[]`（段号、起止时刻、起止报位 id、段时长、窗口内时长、报位数）、`prior_state`、`status`、`flags[]` 文案；`limits.detail_truncated` 为真时给出 `visit_limit` 截断提示。

**两时段比较**：A/B 窗口（起止、覆盖自然日数、实际小时数）、两期 `coverage`、`comparability` 四个布尔 + 自然日/实际天数 + `warnings[]` 全文、7 条指标表（指标/单位/A/B/delta/change_rate）。`change_rate` 为 null 时显示「基期为 0，无法计算变化率」，不显示 0 或 NaN；`unit` 直接取后端（含「艘/日」「次/日」「小时/日」）。比较模式按后端契约不渲染访问明细，A/B `daily` 分两组展示。

**证据联动**：访问行的「地图定位」发 `locate-ship`（用 `first_inside_at`/`last_inside_at`，不用可能落在窗外的事件时间），「显示区间」发 `focus-visit`（带 `visit_key`）；`segment` 级别可看到起止时刻与报位 id。

## 六、状态、错误与请求守卫

- 加载中显示 `aria-live` 状态行与「取消」按钮；取消走 `AbortController`，并提示「查询已取消」。
- 错误经 `describeApiError` 展示；后端 `422/503` 的 `detail.message` 由 `AreaRequestError` 保留并显示。
- 请求版本守卫：每次查询 `requestSeq += 1` 并新建 `AbortController`；响应只在 `seq === requestSeq` 时写入结果，旧响应一律丢弃。切换模式、修改区域（`props.bounds` 变化）、连续查询、关闭面板、卸载组件都会 `abort` 并递增版本号。
- 区域变更后：旧结果标「区域已变更，待查询：以下结果属于 <区域名>（<边界>）」，并常驻显示「结果所属区域 + 查询条件」，避免把旧结果误读成新区域的结果。

## 七、无障碍与窄屏

label/`for` 关联（含船型复选）、`role="status"` + `aria-live="polite"` 状态区、`role="alert"` 错误、结果区 `aria-busy`、展开按钮 `aria-expanded`/`aria-controls`、表格 `<caption>` 与 `scope="col"`/`scope="row"`、每个表格容器 `role="region"` + `tabindex="0"` + `aria-label`、图表 `role="img"` + `aria-label`。窄屏：所有表格包在 `overflow-x:auto` 容器内（不撑破面板），`@media (max-width: 640px)` 收紧间距、单列事实网格、图表降高，ECharts 横轴刻度自动减少。不新增依赖（仅使用已有 vue / echarts）。

## 八、验证证据

工作目录 `frontend/`，2026-10-07 本机执行。

1）语义检查 + 纯函数行为检查（退出码 0 才算通过）：

```powershell
cd frontend
node checks/area-activity.cjs
```

输出（本轮实测，30 项完整列出）：

```text
ok   01 - 三模式齐全（时刻在场/时段活动/两时段比较）
ok   02 - emit 名称齐全且参数形状正确
ok   03 - results-updated 只在成功写入新结果时 emit（失败/取消不发）
ok   04 - 请求版本守卫 + AbortController
ok   05 - 船型筛选来自接口、默认全选、不在前端硬编码
ok   06 - 清空船型时不提交（后端空船型=全部）
ok   07 - no_data 与有效零结果分开渲染
ok   08 - change_rate 为 null 时显示说明而不是 0
ok   09 - 截断提示读后端 limits 标志
ok   10 - 结果区展示区域名称/版本/默认标记、算法版本、coverage、limitations 全文
ok   11 - compare 展示可比性 warnings，且不渲染访问明细
ok   12 - 证据联动：地图定位/显示区间 + segment 起止与报位 id
ok   13 - 不自己拼 URL、不新增依赖、只调用 api.ts 函数
ok   14 - 无障碍与窄屏：label/aria-live/表格 caption+scope/横向滚动
ok   15 - ECharts 按需引入并尊重 prefers-reduced-motion、窄屏减少刻度
ok   16 - UTC 时间输入/输出互转（不随本机时区漂移）
ok   17 - 默认时段为 UTC 自然日半开区间，跨月边界正确
ok   18 - 半开区间表单校验：只拦必填与顺序
ok   19 - 区域归一化：兼容后端嵌套 bounds（含 version=null / custom）
ok   20 - 区域归一化：兼容扁平 west/south/east/north，缺失字段记 null 不回填 0
ok   21 - no_data 与有效零结果的语义分开
ok   22 - change_rate 空值显示说明，数值带符号百分比
ok   23 - 截断提示由后端标志驱动，未截断时不提示
ok   24 - 船型多选：全部=null、部分=数组、列表为空=null
ok   25 - 保留船型值来自后端 reserved，合并去重且不硬编码
ok   26 - 每日序列与 compare windows/metrics 归一化
ok   27 - 访问 emit 参数：locate 用 first/last inside，focus 带 visitKey
ok   28 - 格式化：时长/数量/坐标/龄期/单位
ok   29 - 区域比较与边界文本
ok   30 - 对话联动：读取 agentContext/pendingAction 与生成提示词

30/30 checks passed
area-activity 前端语义检查通过（退出码 0）
```

2）隔离类型检查（只查本组件 + domain + api.ts，不受 App.vue 在途改动影响；退出码 0）：

```powershell
cd frontend
node checks/area-activity.cjs --types
```

```text
运行隔离 vue-tsc（AreaActivityPanel.vue + areaActivity.ts + api.ts）…
隔离类型检查通过：0 errors
```

3）完整构建：

```powershell
cd frontend
npm run build
```

本轮结果（2026-10-07）：`vue-tsc -b && vite build` 通过，退出码 0，`✓ built in 8.01s`（`dist/assets/index-*.js` 1,126.00 kB / gzip 384.91 kB，CSS 90.95 kB）。构建期间 App.vue / AgentPanel.vue 的在途改动曾报错，Lead 接线完成后已消除；`AreaActivityPanel.vue` / `areaActivity.ts` 全程无错误。已核对 App.vue 接入与本契约一致：`:open/:bounds/:default-bounds/:area-label/:area-is-default/:agent-context/:pending-action` + `@close/@update:bounds/@locate-ship/@focus-visit/@use-area-in-dialog/@results-updated`，面板被包在 `<div class="area-panel-placement">` 内；dist 产物中可检索到面板样式类与「区域活动分析」文案，说明组件确实被打进构建。
仅剩 Vite 的 chunk > 500 kB 通用提示（项目既有，与本组件无关；本组件未新增依赖、未改 `package.json`）。

## 九、验证范围与限制

2026-10-07：三模式、真实接口、默认区域身份、取消与旧响应守卫、圈选/回滚、证据轨迹和智能体回填已纳入浏览器复测。手动数字与已有独立复算证据一致，详见[验收报告](area_activity_acceptance.md) §七。

- 矩形绘制目前只实现鼠标拖拽与 ESC 取消；触屏手势及纯键盘绘制尚未支持，表单全流程键盘可达性未验收。
- 窄屏溢出与减少动态检查覆盖 390×844；不代表移动设备触屏验收。
- 真实超时已通过只读慢查询注入验证；并发响应预算、真实模型多轮追问仍未验证。

## 十、组件接入约定（已接入）

1. `area` 采用后端真实结构（嵌套 `bounds`、`version` 可为 null、`containment` 字符串）；`domain/areaActivity.ts` 的 `readBounds` 同时兼容嵌套与扁平写法，因此 api.ts 保持现在的 `ApiAreaInfo.bounds` 即可，无需改动。
2. 组件不 import api.ts 的响应 interface，只用 `type ApiAreaBounds` + 4 个函数；响应经 `toAreaXxxResult()` 宽松归一化。若后续 api.ts 增删字段，只要函数名/参数名不变，组件不受影响。
3. 截断提示只认 `limits.list_truncated` / `limits.detail_truncated`；比较模式没有顶层 `coverage`，组件按 `a.coverage`/`b.coverage` 展示两期覆盖。
4. 未使用 `fetchAreaDefault()`/`resolveAreaBounds()`；若希望面板显示后端默认区域版本或让「重新圈选」先经 `resolve-area` 规范化，需要在 App.vue 侧已完成并把结果经 `areaLabel`/`bounds` 传入。
5. 面板根元素不做定位；App.vue 需要给它一个确定高度/宽度的容器（推荐右侧栏或浮层，`min-height: 0` 保证内部滚动）。
