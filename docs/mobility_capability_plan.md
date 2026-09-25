# MobilityDB 时空数据能力底座技术方案

> 2026-09-25 当前状态：**P0–P4 代码已有实现，P5 部分实现**；本机模拟源船位和全部对应派生记录已删除，真实 AIS 尚未导入应用库。2026-09-19/20 数量及测试为历史验收，不代表当前库。新数据接入后的派生重建、核对和浏览器验收均待开始。
>
> 目标：以 MobilityDB 为核心建立可复用的时空数据能力层，支撑 AIS 船舶轨迹 + 海事事件 + GIS 地图 + 后续真实数据接入。当前应用库没有船位；真实数据接入和兼容性尚待验证。

## 设计总则

1. **派生分析优先下沉数据库**。P0–P4 使用 MobilityDB/PostGIS/SQL；既有海峡通行工具仍在 Python 判定，前端本地半径查询也仍存在，不能把本原则当作全项目已完成的架构约束。
2. **四张源表是事实源，永不改写**（ships / ship_positions / events / news）；一切时空产物都是可重建派生表。
3. **派生表显式重建 + 版本留痕**：每次重建写入 manifest（行数、校验和、built_at），API 暴露新鲜度。
4. **模拟与真实共用管线是后续目标**：`data_source` 字段已存在；真实接入、身份映射、质量校验、参数适配与隔离仍需验证，不能承诺下游完全无感。
5. 所有 Repository 层 SQL 参数化、只读——智能体工具也只允许触碰这一层。

## 1. 整体后端架构

```
接入层            能力底座（本方案核心）           服务/API层            前端
─────────        ─────────────────────          ─────────          ──────
SimBatchAdapter  ┌─────────────────────────┐    Routers(校验)     Leaflet地图
RealAisAdapter ─→│ ships / ship_positions  │        │             回放组件
(都写同一目标表,   │ (源表, 事实源)            │    Services(编排/   着色/柱图/分析
 data_source区分) └──────────┬──────────────┘     阈值/装配)        页签
                             │ 显式重建任务
              ┌──────────────┴───────────────┐      │
              │ 派生层(可重建, manifest留痕)   │←── Repository/SQL
              │ ship_tracks (tgeompoint+speed)│    (只读/参数化)
              │ ship_dwell / encounters /     │        │
              │ event_ship_links / playback   │    MobilityDB 1.3
              └──────────────────────────────┘
```

分层理由：接入层可替换（模拟 jsonl / 真实供应商文件都落成同一张源表），派生层可重建（坏了重跑即可，不污染事实源），Repository 层是唯一允许出现 SQL 的地方——复用现有 `routers → 手写 SQL text()` 的朴素结构，将其显式化。

## 2. 数据模型设计

### 2.1 源表（基本不动）

- **`ships`**：现状保留。注意点：真实 AIS 中 MMSI 会变更/复用，内部 `id` 做永久主键，MMSI 仅作属性；未来若需要可按 MMSI+时间段追溯身份，现在不建。
- **`ship_positions`**：字段已覆盖真实 AIS 核心需求（lat/lon/speed/course/heading/recorded_at/unix_time/nav_status/rot/draught/ais_type/`data_source`）。`location` 生成列（002）保留。**需补的索引**：
  - `(ship_id, recorded_at)` btree——按船+时间窗查询的主路径；
  - `recorded_at` BRIN——大批量真实数据为追加型时序，BRIN 极小且快；
  - `(data_source)` 或部分索引——模拟/真实分析隔离与并行期过滤。

### 2.2 派生表（009+ 迁移，当前用 SQL 定义扩展类型，未实现 SQLAlchemy 自定义类型映射）

**`ship_tracks`（泛化派生表；当前与 `mobility_demo_segments` 并存，尚未替代旧试验）**

| 列 | 类型 | 说明 |
| --- | --- | --- |
| ship_id, segment_no | 复合主键 | 同 007 |
| track | `tgeompoint(SRID 32640)` | 投影后线性插值轨迹 |
| speed | `tfloat` | 与 track 同步的实测航速序列（step 插值），**着色用实测值而非几何反推** |
| point_count, t_start, t_end | | 便于过滤与统计 |
| built_at | timestamptz | 重建留痕 |

GiST(track) 索引。`speed tfloat` 保存源报位 speed 字段的 step 插值，避免用几何反推速度；当前源报位是模拟数据，不能称为真实 AIS 实测速度。实际查询函数以 Repository SQL 为准。

**`ship_dwell`（锚地/等待识别结果）**

| 列 | 说明 |
| --- | --- |
| ship_id, enter_at, leave_at, duration_min | 停留区间 |
| geom (4326) | 停留中心位置 |
| kind | `at_anchor` / `drift` / `slow_transit`（由速度与形态区分）|
| max_speed_kn, point_count | 识别依据快照，供前端解释与人工复核 |

**`encounters`（相遇分析结果）**

| 列 | 说明 |
| --- | --- |
| ship_a_id, ship_b_id | 船舶对 |
| period | `tstzspan`，接近发生的时间区间 |
| min_distance_m, closest_point | 对齐采样时刻的 geography 最小距离及最近接近点；采样近似，不是连续时间精确最小值 |
| params jsonb | 本次判定用的距离/时间阈值快照 |

**`event_ship_links`（事件—船舶关联，区分两种语义）**

| 列 | 说明 |
| --- | --- |
| event_id, ship_id | 外键 |
| link_type | `mentioned`（报道文本提及，来自 events JSONB）/ `observed`（时空计算关联）|
| evidence jsonb | 关联依据：时间窗、距离、轨迹片段标识 |
| confidence | observed 类给数值，mentioned 类为空 |

**为什么必须分 `link_type`**：项目纪律明确"模拟船与真实新闻船舶不得按名称自动认定为同一实体"。`mentioned` 是新闻侧文本证据，`observed` 是数据库侧时空证据，前端展示和智能体回答必须分开标注。

**`track_build_manifest`**：每次重建一行（表名、行数、sha256、built_at、参数快照：gap 阈值、投影 SRID、源批次）。API 用它回答"数据有多新、按什么参数算的"。

## 3. 核心时空计算方案（MobilityDB、PostGIS 与 SQL）

**轨迹构建（重建任务）**：源表按 `ship_id, recorded_at` 顺序取点 → 投影到 UTM 40N（EPSG:32640，与 007 一致）→ `tgeompoint` 线性插值组装 → 超过 `gap_minutes`（默认 90，可配）断开为新 segment → `speed` 列以 step 插值并行组装 → 单事务重建 + manifest。这套语义已在 007/验证脚本里被 Python 独立核对过（差异 <0.36s），直接沿用其正确性验收方法。

**时空操作符 → 业务能力映射**：

| MobilityDB 能力 | 支撑的业务 |
| --- | --- |
| `atTime` / `atGeometry` | 时间窗/区域裁剪（停留、事件窗分析） |
| `duration(...,false)` | 区域停留累计（现有 demo 已验证） |
| `speedAtTimestamp` / `getValue` | 速度着色、速度剖面 |
| `tdwithin` | 相遇判定（距离阈值 + 时间重叠） |
| `nearestApproachDistance` | 最近接近距离、相遇强度排序 |
| `ever` / `always` + 时空关系 | "某船是否曾进入区域""是否始终在限速区"类谓词 |
| 时间跨度比较（`&&` 等） | 事件时间窗与轨迹覆盖判定 |

当前轨迹 API 提供按船和时间窗查询。按空间范围/区域找船是扩展方向；存在 GiST 索引不保证查询计划一定用索引，需用真实 EXPLAIN 验证，不能承诺没有全表扫描。

> 实施陷阱（2026-09-19 实测）：`tstzspan` 的文本形式**经参数绑定传入会被 MobilityDB 静默错解析**（`atTime` 不报错但不裁剪），字面量内嵌则正常。所有参数化 SQL 必须用 `span(CAST(:a AS timestamptz), CAST(:b AS timestamptz))` 构造时间跨度。`scripts/verify_event_ship_links.py` 的逐条独立重算曾捕获此问题。
>
> 实施陷阱（2026-09-20 P4 实测，三条都写在 `build_encounters.py` 注释里）：
> 1. `tgeompoint` 的 `&&`（stbox 相交）**不是保守空间粗筛**——真实距离 700 m 的两段轨迹因时间基不重叠/外包盒构造方式返回 false，会漏候选；粗筛只能用时间重叠 + 采样外包盒，禁用 `&&` 做空间过滤。
> 2. `nearestApproachDistance(t, t)` 只在两条轨迹的**离散时刻并集**上求值，比真实同步最小距离系统性高估（实测 5351 m vs 独立重算 4115 m，偏差约 30–50%），不能作为权威距离；P4 最终方案是对候选对做等时长重采样对齐后逐时刻用 `geography` 距离取最小。
> 3. **EPSG:32640 跨 UTM 带失真**：作业海域 51–57.3°E 跨 39N/40N 两个带，54°E 以西平面距离失真 >20%（51.5°E 处 683 m vs 真实 554 m）。所有度量距离一律走 `geography`（WGS84 米），32640 只用于插值几何。**遗留说明**：010（`event_ship_links`）的距离与缓冲判定在 32640 下计算，同样受跨带失真影响（50 km 尺度下相对偏差约百分之几，事件级展示可接受）；本次未改动 010，真实数据接入前应迁移到 geography 并重跑核对。

## 4. 预计算派生层原则

- **一次性重算、多次读取**：停留、相遇、事件关联都是 O(n) 以上的批量计算，绝不在 API 请求路径上实时跑；API 只查派生表。
- **阈值入参快照**：dwell/encounters 表存当时的参数快照，调阈值重建后历史结果可解释、可对比。
- **重建是显式运维动作**，配套独立 Python 核对脚本，沿用 `verify_mobility_demo` 的验收模式。
- 相遇分析注意组合爆炸：先按时间窗 + GiST 粗筛候选船对，再 `tdwithin` 细算。

## 5. Service / Repository 职责划分

- **Repository 层**（`backend/app/repositories/`）：只有参数化的 `text()` SQL 与行→dict 映射。禁止在这里拼字符串 SQL、禁止写操作。**所有路由和智能体工具共用这一层**，天然满足"智能体只读、受限、参数化"的红线。
- **Service 层**（`backend/app/services/`）：阈值与参数默认值、结果装配（GeoJSON/响应模型）、新鲜度检查（对比 manifest 与源表 max(recorded_at)，过期则响应带 `stale: true`）、模拟/真实数据过滤策略。

当前新鲜度限制：built_at 与 max(recorded_at) 的比较只是时间启发式，无法检测历史船位修改/删除或未推进最大时间的补录。完整源版本/指纹失效检测尚未实现；模拟/真实并行过滤也不能仅凭字段存在认定已验收。
- **Router 层**：参数校验、HTTP 语义、错误体（沿用现有 422 统一格式）。
- **前端**：渲染与着色（按后端给的速度值做色带映射）、回放动画、图表。**不做任何插值、距离、时长计算**。

## 6. API 设计（新增 `/api` 前缀模块，现有路由不动）

```
GET /api/tracks/{ship_id}?from=&to=&level=full|simplified
  → { ship:{...}, gap_minutes, built_at, stale,
      segments:[ { segment_no, t_start, t_end,
                   geometry: GeoJSON(LineString, 4326),   -- 轨迹
                   speed: [[t, kn], ...] } ] }            -- 与几何对齐的速度序列

GET /api/ships/{ship_id}/speed-profile?from=&to=&bucket_minutes=5
  → { buckets: [{t, avg_kn, max_kn, p50_kn}] }            -- 柱图/剖面直出

GET /api/events/{event_id}/ships
  → { links: [ { ship:{id,mmsi,name}, link_type, evidence, confidence } ] }

GET /api/ships/{ship_id}/events?from=&to=
  → { mentioned: [...], observed: [...] }                 -- 两类分开列

GET /api/dwell?area=<bbox或区域id>&from=&to=&kind=
  → GeoJSON FeatureCollection（中心点+时长+kind 属性，前端直接打点/热力）

POST /api/encounters/analyze
  body: { distance_nm, overlap_min, from, to, ship_ids? }
  → { job_id }  异步或受控同步执行，写 encounters 表
GET  /api/encounters?from=&to=&max_distance_nm=
  → { encounters: [ { ship_a, ship_b, period, min_distance_m } ] }

GET /api/data-health
  → { source_counts(按 data_source), track_manifest, coverage_stats }
     构建时输出覆盖率/报位间隔分布——真实数据第一天就是排查缺口的第一工具
```

所有响应带 `is_simulated` / `data_source` 标识，沿用现有 demo 的诚实标注惯例。

## 7. 五大功能实现要点

1. **速度着色轨迹**：`track` + `speed tfloat` 同步输出；前端收到逐顶点速度，按固定色带（如 <3 / 3–8 / 8–12 / >12 kn）渐变。**简化参数化**：`level=simplified` 时由数据库做时间桶抽稀，速度取桶内代表值。
2. **事件—船舶关联**：关联计算离线跑（事件时间±窗 × 事件位置缓冲区内轨迹 `atGeometry`），写 `event_ship_links`；`mentioned` 类由现有 `mentioned_vessels` 迁移生成。地图上高亮 = 前端拿 `observed` 关联的 ship_id 调 `/api/tracks`。**保留红线**：模拟船的 observed 关联在展示与智能体回答中标注"演示，不构成真实因果"。
3. **锚地/等待识别（已实现）**：build_ship_dwell.py 对原始 ship_positions 按速度档和 gap 分组，再按时长和位移半径区分 at_anchor/drift/slow_transit；参数入 manifest。不是调用 speedAtTimestamp 扫描 MobilityDB 轨迹。
4. **相遇分析（已实现）**：同来源轨迹段的时间重叠和 geography 轨迹距离粗筛 → 对齐时间网格采样 → geography 距离取最小 → 按构建阈值聚合到船对。实际 SQL 以 build_encounters.py 为准，未使用旧设计中的外包盒交集及 nearestApproachDistance 作为权威距离。period 是合格重叠区间的外包范围，不代表整段一直在距离阈值内；按窗口读取也不重算子窗口最小距离。
5. **回放抽稀（部分实现）**：/api/tracks 已提供 simplified 时间桶输出。主回放 usePlayback.ts 仍调用原始船位接口；切换主链路及 gap/低速/转向特征保留规则待实现与验证，不能保证当前抽稀保留全部分析特征。

## 8. 模拟与真实数据的接入

本节为后续设计，不是已注册 Adapter 或已完成真实 AIS 接入的说明。

- **统一目标表**：两个 Adapter 都把数据写成 `ships` + `ship_positions`，`data_source` 分别打 `sim_batch_xx` / 真实供应商名。下游零感知。
- **SimBatchAdapter**：读 `sim_ais_demo/output_news_aligned/`（handoff jsonl），即现有导入流程的包装。
- **RealAisAdapter**：读供应商文件/流，`recorded_at` 从 `unix_time` 推导（模型注释里已有此约定）；接入时先跑 `data-health` 核对覆盖率与间隔分布，再触发重建。
- **并行期隔离**：按 `data_source` 过滤分析范围；派生重建任务以"源子集"为单位（可指定只重建某 data_source 的船），真实数据逐步接入时不推翻模拟演示。
- **身份纪律**：真实船与模拟船永不合并；`event_ship_links` 中跨来源的 observed 关联默认不生成，除非未来明确允许。

## 9. 性能与索引提前量

本节为后续优化/验收目标；目前并非所有列表都强制时间窗，且未完成所述大规模压测。

- 索引清单见 2.1/2.2；真实数据量上来后 `ship_positions` 可按月分区（TimescaleDB 已装，可作为选项，不强制）。
- 所有列表型 API 强制时间窗参数；GeoJSON 输出在 Service 层截断 `max_points` 并提示降级到 simplified。
- 重建任务批量 `COPY`/批量 `INSERT`，禁止逐行；重建后 `ANALYZE` + 需要时 `CLUSTER`。
- 上线前做合成压测（模拟点复制扰动到 50–100 倍）验证构建耗时与查询响应，把数字写进文档——补上现有"未做基准测试"的空白。

## 10. 开发优先级建议

| 阶段 | 内容 | 理由 |
| --- | --- | --- |
| P0 ✅ | 009 迁移（ship_tracks 泛化表+索引+manifest）、参数化重建任务、独立 Python 核对 | 底座先立；替代 demo 表，验证管线与规模。已验收：009 建表+索引；重建 30 船 289 段（gap 90 分钟，32640）；manifest id 1 留痕；独立核对 segmentation 全一致、41 组采样插值误差 0 m、速度 0 不符 |
| P1 ✅ | `/api/tracks` + speed 输出 + 速度着色前端 | 展示冲击力最强，打通"派生→API→地图"全链路。已实施：GET /api/tracks/{ship_id}（full=整段几何+对齐 [[epoch,kn]] 速度序列，simplified=时间桶抽稀）；ShipInspector「速度着色」按回放窗口（15 分钟量化）取派生层，四档色带渲染；显示范围超过后端 24h 单窗上限时按 ≤24h 分片并行取回、按 segment_no 去重合并，覆盖整条显示轨迹，另可切换为仅最近 24h 着色；三分支验证与 build/check:workbench 通过（2026-09-19，分片合并 2026-09-20） |
| P2 ✅ | `event_ship_links` 模型 + 事件/船舶双向 API + 高亮 | 项目核心叙事（事件×船）。已实施：010 迁移（mentioned/observed 分列，mentioned ship_id 恒空）；构建脚本（50 km 半径时空邻近，阈值入 manifest）；双向 API（/api/events/{id}/ships、/api/ships/{id}/events）；事件面板关联区（observed 可定位船）；独立核对逐条重算距离 ≤2 m（2026-09-19） |
| P3 ✅ | dwell 识别 + 等待区图层 | 复用 P0 管线，纯增量。已实施：`011_ship_dwell.sql`（kind at_anchor/drift/slow_transit、enter/leave_at、duration_min、geom 4326、displacement_radius_m）；`build_ship_dwell.py`（速度档 run + 90 分钟 gap 断开 + 时长过滤 + 位移半径分类，阈值入 manifest，默认锚泊 <3 kn/30 min、慢速 <8 kn/60 min、位移半径 926 m）；GET `/api/dwell?kind=&from=&to=`；前端图层开关「停留识别」按需加载打点（kind 配色 + tooltip）；独立核对 `verify_ship_dwell.py` 纯 Python 重算 231 行全一致（位移容忍 max(60 m, 1%)）。2026-09-20 当时库 231 行（199 锚泊 / 21 漂航 / 11 慢速）；2026-09-25 当前库 0 行 |
| P4 ✅ | encounters 分析与查询 | 组合复杂度最高，放稳态后。已实施：`012_encounters.sql`（一船对一行：period tstzspan、min_distance_m、closest_point 4326、overlap_minutes 累计、params 快照）；`build_encounters.py`（候选对时间重叠粗筛 → 等时长重采样对齐 → 逐时刻 geography 距离，默认 3 NM / 30 min / 60 s）；GET `/api/encounters?max_distance_nm=` + POST `/api/encounters/analyze`（受控同步重建）；前端概览「相遇分析」列表（最近距离排序、点击地图定位 + 最小距离虚线圈）与「按默认参数重新分析」按钮。独立核对 `verify_encounters.py`：136 对、最近距离最大差 19 m。当前库 136 行（默认参数 manifest id 12）（2026-09-20） |
| P5 部分完成 | 回放抽稀层 + data-health 完善 | data-health API 和前端区块已实现；/api/tracks 的 simplified 输出已由 P1 提供，但主回放未切换，三条特征保留规则尚未实现。stale 启发式限制见 §5；真实数据接入前补强 |
| 全程 | 每个迁移 `ON_ERROR_STOP`、HTTP 三分支验证、文档同步 | 项目既有验收纪律 |

**为什么不先做相遇/锚地**：它们都站在 P0 的派生表之上，底座没立之前做任何一个都是临时实现。

## 11. 与现有资产的关系

- `mobility_demo_segments` 与 `/mobility-demo/*` 在 P0 验收前保留不动；当前两者均在库（demo 114 段 / 10 船未受影响）。后续可将其标记为 legacy 或改造为 `ship_tracks` 的只读视图，避免文档与历史验收记录失真。
- `handoff.py` 交接包流程继续用于源表迁移；派生表不进交接包（服务器端重建），manifest 可随包传递供核对。
- 数据库变更全部走 `backend/sql/009+` 递增文件，遵守 006 的重放禁令。
