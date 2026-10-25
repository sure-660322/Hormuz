# 区域活动前端契约

当前已接入 App/MapView，手动面板与智能体共用后端口径；本页仅保留组件职责、状态和展示契约。历史独立构建与验收日志见[历史材料](README.md#历史材料)，本轮未重跑。

## 一、交付文件与职责

| 文件 | 职责 |
| --- | --- |
| `frontend/src/domain/areaActivity.ts` | 纯函数：视图类型、响应归一化、UTC 时间换算、数值/时长格式化、`change_rate` 空值文案、截断提示、状态与标记文案、emit 参数与对话提示词。无副作用、无 import |
| `frontend/src/components/AreaActivityPanel.vue` | 三模式面板：区域/模式/船型/条件表单 + 结果展示 + 请求守卫 + 无障碍与窄屏；样式全部在 `<style scoped>` 内（不改 `style.css`） |
| `frontend/checks/area-activity.cjs` | 静态语义检查（32 项）+ 纯函数行为检查；`--types` 追加隔离类型检查 |
| `docs/area_activity_frontend.md` | 本文档 |

组件只调用 4 个 `api.ts` 函数：`fetchAreaShipTypes()`、`fetchAreaSnapshot(query, signal?)`、`fetchAreaActivity(query, signal?)`、`fetchAreaCompare(query, signal?)`；不自己拼 URL，不调用 `fetch`。`fetchAreaDefault()` / `resolveAreaBounds()` 未使用：区域名称/版本/默认标记由 props 传入、结果区回显响应里的 `area`。

## 二、组件契约（App.vue 对接点）

```ts
// props
{
  open: boolean
  boundaryVisible: boolean          // 用户显示偏好，与查询区域独立
  drawing: boolean
  resolving: boolean
  areaNotice: string
  dataWindow?: { start: string; end: string } | null // 已加载AIS时间轴范围；只初始化一次
  bounds: ApiAreaBounds              // 当前分析矩形 { west, south, east, north }
  defaultBounds: ApiAreaBounds       // 默认区域矩形（用于对照展示）
  areaLabel: string                  // 例如「霍尔木兹海峡核心通行区」或「自定义分析矩形」
  areaIsDefault: boolean
  agentContext?: { shipTypes?: string[] | null; at?: string | null; start?: string | null; end?: string | null } | null
  pendingAction?: unknown | null     // 不透明：命中 mode/at/start/end/startA..endB/shipTypes 时应用并自动查询
}

// emits
close: []
'update:boundary-visible': [visible: boolean]
'restore-default': []
'cancel-draw': []
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
| 时刻在场 | 时刻 `datetime-local` | 当前地图回放时刻（未回填时用数据范围起点） | 标签与说明均标注 UTC；内部转 ISO Z |
| 时段活动 | 起止 `datetime-local` | 数据范围内第一个完整 UTC 自然日 | 界面写明终点不含（半开区间） |
| 两时段比较 | A/B 各起止 | A = 数据范围内第一个完整UTC日，B = 紧接的下一个UTC日；短范围回退到有效区间 | 说明两期共用区域/筛选/算法，允许不等长 |

- `<input type="datetime-local">` 的值按 UTC 读数，`utcInputToIso` 补 `:00Z`；非法日期（如 `2026-02-30`）返回 null 并在提交前拦下，不发请求。
- 高级参数（可折叠）：`freshness_seconds`（时刻在场）、`visit_limit`（时段活动/两时段比较），留空用后端默认。
- 表单只做「必填 + start < end」的轻量校验；矩形跨度、窗口上限等业务规则以后端 422 为准（错误经 `describeApiError` 展示后端原文）。

## 四、船型筛选

- 选项来自 `fetchAreaShipTypes()`，由 `mergeShipTypeOptions(ship_types, reserved)` 合并后端 `ship_types` 与 `reserved`（含 `__missing__`/`__unknown__`），前端不硬编码任何船型值。
- 展示默认保留油轮、集装箱、货船三个重要标签，其余真实选项放进可展开「其它」。总开关选中/取消全部子项，单个子项选择产生部分选中状态；分组只改变展示，查询仍提交接口返回的具体 value，缺失/未知均保留。来源与限制集中在折叠说明。
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

## 十、组件接入约定（已接入）

1. `area` 采用后端真实结构（嵌套 `bounds`、`version` 可为 null、`containment` 字符串）；`domain/areaActivity.ts` 的 `readBounds` 同时兼容嵌套与扁平写法，因此 api.ts 保持现在的 `ApiAreaInfo.bounds` 即可，无需改动。
2. 组件不 import api.ts 的响应 interface，只用 `type ApiAreaBounds` + 4 个函数；响应经 `toAreaXxxResult()` 宽松归一化。若后续 api.ts 增删字段，只要函数名/参数名不变，组件不受影响。
3. 截断提示只认 `limits.list_truncated` / `limits.detail_truncated`；比较模式没有顶层 `coverage`，组件按 `a.coverage`/`b.coverage` 展示两期覆盖。
4. 面板不直接使用 `fetchAreaDefault()`/`resolveAreaBounds()`；App.vue 已负责加载默认区域、规范化圈选与失败回滚，经 `areaLabel`/`bounds` 传入。
5. 面板根元素不做定位；App.vue 需要给它一个确定高度/宽度的容器（推荐右侧栏或浮层，`min-height: 0` 保证内部滚动）。

## 2026-10-08 Issue #54 显示状态与分析状态

App.vue 分别维护面板打开、边界偏好和临时绘制；有效可见性为「面板打开且偏好开启且不在案例」。MapView 仅据有效可见性增删已确认矩形，不修改父层 bounds。默认面板首次开启才初始化显示偏好，以后关闭/重开沿用偏好。

面板首次打开后保留组件，关闭用 v-show 隐藏，筛选、日期、现有结果及版本保留；关闭仍取消在途查询。对话建议仅消费新动作，重开不重复查询或重新预填。圈选自动显示边界，完成经真实 resolve-area 校验；取消、隐藏、关闭面板与进入案例递增校验序号，迟到响应不提交。恢复默认沿用已有区域变更/结果过期规则，不修改显示偏好。

「当前区域：默认区域 / 自定义区域」常显；坐标、半开规则与范围依据放进「区域详情（非官方航道边界）」。隐藏时面板提示分析范围不变；绘制/取消与失败反馈收进面板，地图不再常驻长坐标条。区域编辑限地图探索；案例入口给出解释与切换按钮，案例退出恢复原面板/显示状态，不恢复拖拽。

本轮状态、复跑命令及截图见[历史材料](README.md#历史材料)。开关的 Space 键与 aria-checked 纳入本轮验证；触屏和纯键盘创建矩形仍未支持。

2026-10-08 用户注释返工（实现 `5ff7735`）：案例提示改为右侧独立高层级浮层；左侧筛选头部紧凑化、事件标题完整换行；船型分组与AIS默认时段已验证。区域纯函数/语义检查32/32、S11回归28项、S12专项15项通过，证据见[历史材料](README.md#历史材料)。
