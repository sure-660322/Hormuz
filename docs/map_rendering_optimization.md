# 地图回放渲染性能优化报告

> 历史报告：以下性能与「事件随回放时刻显隐」记录属于 2026-09-21 当时的界面版本。2026-09-23 地图布局和新闻代表点显示规则已调整，当前行为与本轮验证见 [前端工作台](../FRONTEND_WORKBENCH.md)；本轮未重测本文性能数值。

日期：2026-09-21 · 范围：frontend 地图渲染层（Vue 3 + TypeScript + Leaflet，未换技术栈）

## 1. 原始性能瓶颈

瓶颈全部在前端渲染层，网络与数据加载无瓶颈（回放数据一次性加载）：

| 瓶颈 | 原实现 | 代价 |
| --- | --- | --- |
| 船舶 Marker | 每帧对 ~30 艘船无条件 `setIcon()` + `setTooltipContent()` | 每帧替换全部图标 DOM/SVG |
| 事件图层 | 每帧 `eventLayer.clearLayers()` + 全量重建 | 每帧销毁/重建几十个 Marker |
| 轨迹图层 | 每帧 `trackLayer.clearLayers()` + 重建 Polyline + 数百个 SVG circleMarker | 选船后每帧数百 DOM 节点重建 |
| 向量线/船簇 | 每帧 `clearLayers()` + 重建 ~250 条 canvas 路径 | 每帧全量重建 |
| 渲染链路 | `index -> watch -> Leaflet 同步渲染`，无调度 | 快速拖动时过时状态积压，每帧 450~535ms（中位 476ms） |

## 2. 修改文件

- `frontend/src/components/MapView.vue` — 渲染逻辑迁出，仅保留接线（图层组、watch、调度入队）
- `frontend/src/services/map/renderScheduler.ts` — 新增，requestAnimationFrame 统一调度（latest-state-wins）
- `frontend/src/services/map/renderPerf.ts` — 新增，URL `?perf=1` 门控的性能探针（`window.__hormuzPerf`）
- `frontend/src/services/map/shipLayer.ts` — 新增，船舶/船簇/向量线增量管理
- `frontend/src/services/map/eventLayer.ts` — 新增，事件 Marker 生命周期管理
- `frontend/src/services/map/trackLayer.ts` — 新增，轨迹/速度着色增量管理
- `scripts/perf/` — 开发环境测量 harness（puppeteer-core + 系统 Chrome，非前端运行时依赖）

## 3. 核心修改与解决的问题

1. **船舶 Marker 稳定复用**：以 `ship.id`（库内主键，稳定唯一）为键维护 `Map<id, L.Marker>`。位置变化只 `setLatLng`；航向变化直接写已有 SVG `<g>` 的 `transform` 属性（`g.vessel-rotor`），不重建 icon；颜色/船型/选中态签名变化才 `setIcon`；tooltip 文本变化才更新；弱化/选中 class 走 `classList`。
2. **事件图层一次创建 + 增量显隐**：以坐标组为键维护 `Map<key, Marker>`；回放时间门控只改变显隐集合，通过 `addLayer/removeLayer` 控制；选中/弱化/紧急等可视签名变化只换 icon；同坐标组构成变化才重建（弹窗闭包依赖组内容）。
3. **轨迹独立生命周期**：Polyline 一次创建，连续回放按公共前缀增量 `addLatLng`；报位点 Marker 只增量补齐新增点；向后拖动/换船/过滤条件变化才整体重建。速度着色按“段内连续同色 run”缓存 Polyline，几何签名不变时复用，变化时 `setLatLngs/setStyle`。
4. **向量线/船簇签名化**：每船一个常驻 LayerGroup，几何签名（位置/航向/速度/时间窗/缩放/颜色/透明度）不变时整体跳过；船簇按聚合桶签名，只在缩放/聚合结果变化时重建。
5. **停留/相遇派生层**：按稳定键增量建点，选中态变化只 `setStyle`，不再 `clearLayers` 全量重建。
6. **rAF 渲染调度**：所有 watcher 改为向 `RenderScheduler` 入队同名任务，一帧内只执行最新状态；组件卸载时 `cancel()`。
7. **Vue/Leaflet 解耦**：Vue 只拥有回放时间、选中态等 UI 状态；Leaflet 图层对象由 Manager 长期持有，watcher 不再同步触发渲染。

## 4. “全量重建” → “增量更新”清单

| 对象 | 原方式 | 现方式 |
| --- | --- | --- |
| 船舶 Marker | 每帧 setIcon + tooltip 重建 | setLatLng + SVG transform，签名变化才重建 |
| 事件 Marker | 每帧 clearLayers + 全量重建 | 一次创建，显隐用 addLayer/removeLayer |
| 轨迹 Polyline | 每帧 clearLayers + 重建 | 增量 addLatLng，跳变才 setLatLngs/重建 |
| 轨迹报位点 | 每帧重建数百 circleMarker | 增量补齐新增点 |
| 速度着色 | 每帧重建全部着色线 | run 级缓存，setLatLngs/setStyle 更新 |
| 向量线/船首向 | 每帧 clearLayers + 重建 | 每船常驻组，签名跳过 |
| 船簇 | 每帧 clearLayers + 重建 | 聚合签名变化才重建 |
| 停留/相遇点 | clearLayers + 全量重建 | 稳定键增量建点 |
| 回放渲染 | watch 同步渲染，状态积压 | rAF 调度，latest-state-wins |

## 5. 实测性能对比

以下为 Kimi 提交的历史测量，本轮整理未独立复测。使用同机无头 Chrome 152，但旧代码用 `PerformanceObserver(longtask)` 测主线程长任务，新代码表中主要引用应用内探针（`?perf=1`）的局部渲染任务耗时；二者口径不同，不能直接相除作为端到端加速倍数。原始结果保留在 scripts/perf/result-old.json 与 result-new.json；后者仍记录主线程长任务，不能宣称全部卡顿已消除。

| 场景 | 旧代码 | 新代码 |
| --- | --- | --- |
| 普通播放 1×（未选船，zoom≈8） | 每帧长任务 155~195ms | ships 0.2ms / events 0.1ms（中位） |
| 选中船 + 轨迹播放 | **中位 471ms / 最大 547ms**（与原基线 450~535ms 一致） | ships 0.7ms / tracks 0.2ms |
| 快速拖动 150 跳变 | 20 跳 3.64s（≈180ms/帧，全部 >50ms） | ships 1.9ms / events 1.1ms；无底图对照 **0 长任务** |
| 拖动 + 轨迹 + 速度着色 | —（叠加后 >500ms/帧） | tracks 14.7ms 中位 / p95 48.9ms / max 100ms（随机跳触发的整轨重建） |
| 速度着色播放 | — | tracks 1.0ms |
| 2× / 4× 播放 | — | ships 0.6~0.8ms / tracks 0.6~0.7ms |
| 事件显隐（拖动中） | 每帧全量重建 | 1.1ms；首次创建 20 个 Marker 一次性 ~70ms |

功能正确性同轮验证：30 船 Marker 稳定复用（150 帧拖动后数量不增长）、事件随回放时刻显隐、轨迹随时间增长、速度着色、选中/隔离、2×/4× 均正常。`npm run build`、`npm run check:workbench` 通过。

## 6. 剩余主要瓶颈

1. **底图瓦片与深色滤镜合成**：无头软渲染下间歇出现 ~400ms 合成任务，空闲时也存在、与回放渲染无关（无底图对照归零）；真实 GPU 浏览器中代价小得多，但 `.dark-map` 的 CSS filter 仍是大合成层，值得未来单独评估。
2. **大跨度跳变的整轨重建**：p95 ~49ms，属设计内行为（“大跨度拖动允许重建”）。
3. **轨迹点 SVG DOM 随轨迹长度增长**（数百点）：当前每帧零成本，但 DOM 节点本身占内存；规模更大时需 Canvas 化。
4. **Leaflet canvas renderer 全量重绘**：任何路径变化会重绘视口内全部 canvas 路径，当前 ~250 条无压力。

## 7. 数据规模增长路线

- **100 艘**：预计可沿用当前架构，但尚未做此规模压测；建议向量线 tick 随缩放抽稀。下列 1000/10000 艘同为规划，不是已验证容量。
- **1000 艘**：船舶 Marker 转共享 Canvas renderer 画点（保留选中船的 DOM Marker），或常驻网格聚合 + 视口内渲染；轨迹点 Canvas 化 + 按缩放抽稀（ Douglas-Peucker / min-max）。
- **10000 艘**：上 WebGL（deck.gl / MapLibre custom layer / pixi-overlay）：船位降为 GPU 点精灵，聚合用预计算（Supercluster 类），轨迹走 line layer + 抽稀 + 视口裁剪。

## 8. 架构演进能力确认

当前分层 `Vue 状态 → RenderScheduler(rAF) → LayerManager(create/update/remove) → Leaflet(DOM/Canvas)` 已具备演进能力：

- **Leaflet 增量渲染**：已完成。
- **Leaflet Canvas**：地图已 `preferCanvas`，向量线/着色线共享 `L.canvas`；船舶/事件 Marker 若转 Canvas 只需改 Manager 内部实现，上下文与调度契约不变。
- **WebGL 大规模**：替换 Manager 绘制后端即可，上层（回放状态、调度、生命周期语义）原样复用。
