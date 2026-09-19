# 海事态势工作台

状态更新：2026-10-04，按当前前端代码核对；2026-09-19 增补 P1/P2 派生层前端能力（速度着色、事件×船舶关联）。全项目状态见 [README](README.md)，智能体契约与接入记录见 [智能体接入](docs/agent_integration.md)。

## 当前功能

| 模块 | 已实现与边界 |
| --- | --- |
| 地图 | Leaflet、OSM、OpenSeaMap、港口参考图层、国家边界与标签；在线参考源依赖网络 |
| 搜索与检查 | 按船名、MMSI、IMO 搜索，查看模拟船身份、当前位置、历史轨迹和航速曲线 |
| 回放 | 多日数据分窗加载，单窗最多24小时；5分钟展示步长，使用当前时刻之前最近报位，不插值；支持暂停、倍速和跳转 |
| 时间与主题 | 默认 UTC，可切换 UTC+8；深浅主题；分享 URL 保存视图、选择和回放等状态，不上传数据库 |
| 新闻事件 | 按类型和报道日期浏览，查看关联报道和来源；有代表点时定位，缺坐标时保持列表可读 |
| 区域查询 | 浏览器球面距离近似，海里为单位，仅查询当前模拟船舶快照；不是后端 PostGIS 结果 |
| 模拟围栏 | 查询圆可显示回放步进间的进入/离开提示，仅本次会话有效，不检测两个采样之间的真实穿越 |
| 停留试验入口 | 打开独立 MobilityDB 页面，固定区域及前后窗口；不是主地图双屏分析 |
| 派生轨迹速度着色 | ShipInspector「速度着色」按回放时刻前溯窗口（15 分钟量化、≤24h）取 `GET /api/tracks` 派生层，<3 / 3–8 / 8–12 / >12 kn 四档色带渲染；几何与速度同为数据库插值结果，前端不做插值 |
| 事件×船舶关联 | EventPanel 事件详情内「事件 × 船舶关联」区：`observed`（模拟轨迹时空邻近演示，带距离/置信度，可地图定位船）与 `mentioned`（新闻原文船名，`ship` 恒为空）严格分列 |
| 异常与空状态 | 请求失败、空结果和重试提示；新闻请求有20秒超时 |
| 智能体问答 | 右侧工作面板「智能体」页签（AgentPanel.vue）调用 POST /agent/analyze；独立异步加载，支持取消，前端 75 秒超时覆盖后端 60 秒预算，与新闻 20 秒超时分开；回答附船只、证据、统计与限制说明 |

## 数据语义

- 当前数据库为30艘、9354条模拟船位，来自 output_news_aligned。数量不在前端写死。
- 新闻已接入，船舶为模拟；当前两者对应同一时期，但新闻仍独立浏览。代码中的旧“日期不重合”注释不再代表现状。
- 选择新闻不会跳转模拟回放；区域查询仍不接入事件（空事件集不等于范围内无真实新闻）。事件详情另有演示级 observed 关联（模拟数据时空邻近，明确标注不构成真实因果）与 mentioned 原文船名，二者不按名称互通。
- 新闻按报道日期排序，事件时间及坐标允许为空；不能把日期级记录解释成精确时刻。代表点并非完整事件影响范围。
- 回放不使用 /ships/map 的最新位置代替历史位置。最近报位保留真实记录时间；当前没有完善的陈旧度阈值策略。
- 多地点新闻完整绘制、真实 AIS、自动新闻风险判定、通用双地图及密度分析尚未实现。
- WorkspaceTools 中“单日模拟回放”的旧规划提示尚未随多日回放更新；本次仅改文档，未修改页面文案。

## 代码职责

| 路径 | 作用 |
| --- | --- |
| frontend/src/App.vue | 选择、面板、回放、图层、分享与区域状态 |
| frontend/src/api.ts | 后端请求、响应类型、事件展示字段适配 |
| frontend/src/composables/usePlayback.ts | 时间范围加载及最近报位回放 |
| frontend/src/components/MapView.vue | 地图对象、船位、轨迹（含派生层速度着色渲染）、事件代表点和参考图层 |
| frontend/src/components/EventPanel.vue | 事件筛选、详情、关联报道与事件×船舶关联区 |
| frontend/src/components/ShipInspector.vue | 船舶详情、航速曲线与派生层速度着色开关 |
| frontend/src/components/WorkspaceTools.vue | 图层与本地区域查询 |
| frontend/src/components/TimelineControls.vue | 回放控件 |
| frontend/src/domain/maritime.ts | 时间格式、展示类型和距离计算 |
| frontend/src/services/workbench.ts | 本地同步查询及尚未实现的服务契约 |
| frontend/src/services/countryLayer.ts | 国家边界与标签 |
| frontend/checks/workbench.cjs | 工作台轻量语义检查 |

## 智能体接入（契约 v3）

POST /agent/analyze 已注册（schemas、统一错误、CORS POST 均已同步），前端 AgentPanel.vue 位于右侧工作面板「智能体」页签。契约 v3 起支持多工具（海峡通行 / 船舶检索 / 单船轨迹 / 新闻事件）与多轮 history（最近 10 轮）：对话按轮次堆叠展示（问题 + 状态徽标 + 工具标签 + 回答 + 上下文/统计/证据），「清空对话」重置全部轮次。回答中的船只与事件带「地图定位」按钮，经 App.vue 选中当前回放快照中的船/事件（目标不在当前快照或事件无位置时如实提示，不伪造）。

智能体请求是独立异步加载，不放入 computed：由 AgentPanel 管理加载、取消、超时与错误状态，过期响应被忽略。前端 75 秒超时覆盖后端 60 秒整体预算，与新闻 20 秒超时分开。样例响应均有显式标识（request_id、批次与工具结果）。地图定位的是当前回放时刻的位置，非历史轨迹点。

## 验证

在项目根目录执行：

```powershell
cd .\frontend
npm run build
npm run check:workbench
```

2026-10-04 本地提交前以上两项已通过。2026-10-05 契约 v3：npm run build 与 npm run check:workbench 通过；浏览器端到端联调通过（多轮追问渲染两轮、事件结果与定位按钮渲染、定位后选中船、控制台无未处理错误）；历史浏览器记录见 sim_ais_demo/output_news_aligned/api_startup_report.json，不等于完整端到端覆盖。2026-09-19 P1/P2：npm run build 与 npm run check:workbench 通过；无头 Chrome 端到端验证通过——事件关联区渲染（observed/mentioned 分列）、关联船定位选中、速度着色轨迹与图例渲染均正常，控制台无错误；截图为本地临时产物（screenshots/，不入库）。
