# MobilityDB 时空数据能力底座技术方案

> 状态：**P0–P1 已实施（2026-09-19），P2–P5 未实施**。本文描述方案；已实施部分以代码、`backend/sql/009_ship_tracks.sql`、`backend/build_ship_tracks.py`、`scripts/verify_ship_tracks.py` 及 `sim_ais_demo/output_news_aligned/ship_tracks_{build,verification}.json` 为准。
>
> 目标：以 MobilityDB 为核心建立可复用的时空数据能力层，支撑 AIS 船舶轨迹 + 海事事件 + GIS 地图 + 后续真实数据接入。当前使用模拟数据，但本方案以真实生产数据能够直接承接为设计目标，不因模拟数据做临时实现。

## 设计总则

1. **插值与时空语义只存在于数据库层**。Python 和前端拿到的永远是"已完成时空计算"的结果，不做二次推导。
2. **四张源表是事实源，永不改写**（ships / ship_positions / events / news）；一切时空产物都是可重建派生表。
3. **派生表显式重建 + 版本留痕**：每次重建写入 manifest（行数、校验和、built_at），API 暴露新鲜度。
4. **模拟与真实共用同一条管线**：差别只在接入层写入 `data_source`（字段已存在），下游模型、计算、API 完全无感。
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

### 2.2 派生表（009+ 迁移，DDL 用裸 SQL，不走 ORM——`tgeompoint` 无法被 SQLAlchemy 建模，沿用 007 的惯例）

**`ship_tracks`（泛化版 `mobility_demo_segments`，替代它）**

| 列 | 类型 | 说明 |
| --- | --- | --- |
| ship_id, segment_no | 复合主键 | 同 007 |
| track | `tgeompoint(SRID 32640)` | 投影后线性插值轨迹 |
| speed | `tfloat` | 与 track 同步的实测航速序列（step 插值），**着色用实测值而非几何反推** |
| point_count, t_start, t_end | | 便于过滤与统计 |
| built_at | timestamptz | 重建留痕 |

GiST(track) 索引。**为什么加 `speed tfloat`**：速度着色的业务语义是"AIS 实测速度"，几何插值反推的速度在长报位间隔下是假信号；tfloat 与 tgeompoint 时间基对齐，`speedAtTimestamp` 语义天然同步。

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
| min_distance_m, closest_geom | `nearestApproachDistance` 结果 |
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

## 3. 核心时空计算方案（全部在 MobilityDB 内）

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

**轨迹查询**：按船 + 时间窗（`atTime`）、按船 + 空间范围（`atGeometry`）、按区域找船（GiST(track) 索引 + `intersects`）三类主查询，全部由索引支撑，不走全表扫描。

## 4. 预计算派生层原则

- **一次性重算、多次读取**：停留、相遇、事件关联都是 O(n) 以上的批量计算，绝不在 API 请求路径上实时跑；API 只查派生表。
- **阈值入参快照**：dwell/encounters 表存当时的参数快照，调阈值重建后历史结果可解释、可对比。
- **重建是显式运维动作**，配套独立 Python 核对脚本，沿用 `verify_mobility_demo` 的验收模式。
- 相遇分析注意组合爆炸：先按时间窗 + GiST 粗筛候选船对，再 `tdwithin` 细算。

## 5. Service / Repository 职责划分

- **Repository 层**（`backend/app/repositories/`）：只有参数化的 `text()` SQL 与行→dict 映射。禁止在这里拼字符串 SQL、禁止写操作。**所有路由和智能体工具共用这一层**，天然满足"智能体只读、受限、参数化"的红线。
- **Service 层**（`backend/app/services/`）：阈值与参数默认值、结果装配（GeoJSON/响应模型）、新鲜度检查（对比 manifest 与源表 max(recorded_at)，过期则响应带 `stale: true`）、模拟/真实数据过滤策略。
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
3. **锚地/等待识别**：MobilityDB 侧 `speedAtTimestamp` 逐段扫描找 `speed < threshold` 连续区间（`duration` 计长、`atGeometry` 校验位置稳定），形态特征（漂移 vs 锚泊）用位移半径区分；结果落 `ship_dwell`，前端纯展示。阈值可配、入快照。
4. **相遇分析**：候选对 = 时间窗重叠且外包盒相交（GiST 粗筛）→ `tdwithin(track_a, track_b, d)` + `nearestApproachDistance` 细算 → `overlap_min` 过滤 → 落 `encounters`。距离/时间阈值 API 参数可配。
5. **回放抽稀**：**原始层不动**；`level=simplified` 走另一输出：时间桶抽稀（如 30s/桶取中位点）+ 三条保留规则——桶跨 gap 不合并、速度低于阈值的密集点保留（锚泊形态不能丢）、转向率高的区段加密保留。这保证抽稀不破坏停留/相遇特征。前端回放永远消费 simplified 层，全量层仅供下载/深入分析。

## 8. 模拟与真实数据的接入

- **统一目标表**：两个 Adapter 都把数据写成 `ships` + `ship_positions`，`data_source` 分别打 `sim_batch_xx` / 真实供应商名。下游零感知。
- **SimBatchAdapter**：读 `sim_ais_demo/output_news_aligned/`（handoff jsonl），即现有导入流程的包装。
- **RealAisAdapter**：读供应商文件/流，`recorded_at` 从 `unix_time` 推导（模型注释里已有此约定）；接入时先跑 `data-health` 核对覆盖率与间隔分布，再触发重建。
- **并行期隔离**：按 `data_source` 过滤分析范围；派生重建任务以"源子集"为单位（可指定只重建某 data_source 的船），真实数据逐步接入时不推翻模拟演示。
- **身份纪律**：真实船与模拟船永不合并；`event_ship_links` 中跨来源的 observed 关联默认不生成，除非未来明确允许。

## 9. 性能与索引提前量

- 索引清单见 2.1/2.2；真实数据量上来后 `ship_positions` 可按月分区（TimescaleDB 已装，可作为选项，不强制）。
- 所有列表型 API 强制时间窗参数；GeoJSON 输出在 Service 层截断 `max_points` 并提示降级到 simplified。
- 重建任务批量 `COPY`/批量 `INSERT`，禁止逐行；重建后 `ANALYZE` + 需要时 `CLUSTER`。
- 上线前做合成压测（模拟点复制扰动到 50–100 倍）验证构建耗时与查询响应，把数字写进文档——补上现有"未做基准测试"的空白。

## 10. 开发优先级建议

| 阶段 | 内容 | 理由 |
| --- | --- | --- |
| P0 ✅ | 009 迁移（ship_tracks 泛化表+索引+manifest）、参数化重建任务、独立 Python 核对 | 底座先立；替代 demo 表，验证管线与规模。已验收：009 建表+索引；重建 30 船 289 段（gap 90 分钟，32640）；manifest id 1 留痕；独立核对 segmentation 全一致、41 组采样插值误差 0 m、速度 0 不符 |
| P1 ✅ | `/api/tracks` + speed 输出 + 速度着色前端 | 展示冲击力最强，打通"派生→API→地图"全链路。已实施：GET /api/tracks/{ship_id}（full=整段几何+对齐 [[epoch,kn]] 速度序列，simplified=时间桶抽稀）；ShipInspector「速度着色」按回放窗口（15 分钟量化）取派生层，四档色带渲染；三分支验证与 build/check:workbench 通过（2026-09-19） |
| P2 | `event_ship_links` 模型 + 事件/船舶双向 API + 高亮 | 项目核心叙事（事件×船） |
| P3 | dwell 识别 + 等待区图层 | 复用 P0 管线，纯增量 |
| P4 | encounters 分析与查询 | 组合复杂度最高，放稳态后 |
| P5 | 回放抽稀层 + data-health 完善 | 真实数据临近时重点强化 |
| 全程 | 每个迁移 `ON_ERROR_STOP`、HTTP 三分支验证、文档同步 | 项目既有验收纪律 |

**为什么不先做相遇/锚地**：它们都站在 P0 的派生表之上，底座没立之前做任何一个都是临时实现。

## 11. 与现有资产的关系

- `mobility_demo_segments` 与 `/mobility-demo/*` 在 P0 验收前保留不动；当前两者均在库（demo 114 段 / 10 船未受影响）。后续可将其标记为 legacy 或改造为 `ship_tracks` 的只读视图，避免文档与历史验收记录失真。
- `handoff.py` 交接包流程继续用于源表迁移；派生表不进交接包（服务器端重建），manifest 可随包传递供核对。
- 数据库变更全部走 `backend/sql/009+` 递增文件，遵守 006 的重放禁令。
