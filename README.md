# 霍尔木兹海峡船舶态势地图

> 2026-09-11 MobilityDB 小规模试验：已为10艘模拟船构建71段派生轨迹，提供区域停留时长对比。主地图顶部“停留分析试验”进入；说明及复现命令见 [试验记录](docs/mobility_demo.md)。这是局部试点，主回放仍使用原始船位，源表保持不变；下方“尚未使用MobilityDB”的旧说明已被本试点部分取代。

> 2026-09-11 模拟回放适配：当前库保留新批次150艘模拟船、58,567条船位，UTC范围为2026-02-26 01:02:41至2026-03-04 23:59:41。旧批次150艘船及14,400条船位已备份后删除，65个新闻事件和290条新闻未变。前端以不超过24小时的窗口加载船位，并按5分钟展示步长回放（共2,005个刻度，末刻度覆盖最后报位）；保留原始不规则报位，以当前时刻前最近报位显示，不插值。新闻仍独立浏览。备份位于 `sim_ais_demo/output/old_batch_backup/`，接口验收见 `sim_ais_demo/output/playback_verification.json`。下方旧批次数量及生成器说明属于历史记录，勿使用旧清库命令。

> 2026-09-09 基础适配完成：65条新闻事件可独立浏览，详情可查看关联报道，40个代表点可定位；新闻不再联动8月模拟船舶回放。接口、验证结果和剩余边界见 [基础适配记录](docs/event_adaptation_phase1.md)。多点展示和旧附近事件接口尚未适配。下方迁移说明为此前阶段记录。

> 2026-09-09 数据库更新：`events` 已替换为65个新闻聚合事件，新增 `news` 表并导入290条已采集新闻；船舶和船位仍为模拟数据。前端与旧事件相关接口尚未适配新结构。下文旧事件字段、模拟事件生成和新库初始化说明属于迁移前状态，当前操作请先阅读 [006迁移报告](backend/sql/006_migration_report.md)。

这是一个用于学习前后端与空间数据库协作方式的船舶态势地图项目。项目当前使用可重复生成的教学模拟船舶、轨迹和事件，完成了从 PostgreSQL 到 FastAPI，再到 Vue 与 Leaflet 地图的数据闭环。

> 当前所有船舶、轨迹和事件均为教学用模拟数据，不代表真实 AIS 船舶活动或真实海上事件。

前端已升级为地图主导的海事分析工作台，包含船名/MMSI/IMO 搜索、右侧船舶与事件检查面板、分类事件时间轨、图层控制、本地模拟快照半径查询及航速曲线。完整改动、数据边界、验证记录与后端接口建议见 [前端工作台说明](FRONTEND_WORKBENCH.md)。

## 当前功能

### 地图

- 默认定位到霍尔木兹海峡附近；
- 使用 OpenStreetMap 显示基础地图；
- 使用 OpenSeaMap 叠加航标、浮标和灯塔等海事信息；
- 根据当前地图范围加载 OpenSeaMap 港口图标；
- 支持鼠标拖动和滚轮缩放。

### 船舶与事件

- 从 FastAPI 获取船舶基本信息；
- 从 FastAPI 获取每艘船的历史位置；
- 在地图上显示船舶当前位置和历史轨迹；
- 点击船舶 Marker 在右侧检查面板查看船名、MMSI、类型、速度、航向和位置；
- 从 FastAPI 获取模拟事件并显示事件 Marker；
- 点击事件 Marker 在右侧查看标题、描述、中文类型、时间和位置，并跳转至对应回放时刻。

### 数据库与空间查询

- 使用 `ships` 保存船舶基本信息；
- 使用 `ship_positions` 保存船舶历史位置；
- 使用 `events` 保存地图事件；
- 使用 PostGIS 的 `geography(Point, 4326)` 生成空间位置；
- 已在数据库中验证 `ST_Distance` 距离计算；
- 已在数据库中验证 `ST_DWithin` 范围查询；
- 已为事件和船舶位置建立 GiST 空间索引。

PostGIS 距离和范围查询已封装为 `GET /ships/{ship_id}/nearby-events` 接口，可基于船舶最新位置查询指定半径内的模拟事件。

## 技术栈

### 前端

- Vue 3
- TypeScript
- Vite
- Leaflet
- OpenStreetMap
- OpenSeaMap

### 后端

- Python
- FastAPI
- Uvicorn
- SQLAlchemy 2
- Psycopg 3

### 数据库

- PostgreSQL 17
- PostGIS 3.5
- TimescaleDB 2.22
- MobilityDB 1.3

当前核心功能使用 PostgreSQL 和 PostGIS。TimescaleDB 与 MobilityDB 已安装，但尚未在业务代码中使用。

## 数据流

```text
PostgreSQL / PostGIS
        ↓
      FastAPI
        ↓
       Vue 3
        ↓
 Leaflet 地图页面
```

## 目录结构

```text
Hormuz/
├── backend/
│   ├── app/
│   │   ├── routers/          # 船舶和事件接口
│   │   ├── database.py       # 数据库连接与会话
│   │   ├── main.py           # FastAPI 应用入口
│   │   ├── models.py         # SQLAlchemy 数据模型
│   │   └── schemas.py        # FastAPI 响应数据结构
│   ├── sql/                  # 按编号执行的数据库结构变更脚本
│   ├── create_tables.py      # 创建基础数据表
│   ├── seed_data.py          # 插入少量模拟数据
│   ├── generate_demo_data.py # 生成并验收完整教学模拟数据
│   └── requirements.txt      # Python 依赖
├── frontend/
│   ├── src/
│   │   ├── api.ts            # 调用 FastAPI
│   │   ├── App.vue           # 工作台状态与组件编排
│   │   ├── components/       # 地图、检查面板、搜索与时间轴
│   │   ├── composables/      # 回放数据与时间状态
│   │   ├── domain/           # 展示规范与空间类型
│   │   ├── services/         # 本地查询与未来接口契约
│   │   └── main.ts           # Vue 应用入口
│   └── package.json          # 前端依赖与命令
├── data/                     # 现有新闻测试数据，当前地图主流程未使用
├── scripts/                  # 新闻测试数据处理脚本，当前地图主流程未使用
├── .env                      # 本机数据库配置，不提交版本管理
├── .env.example              # 可提交的数据库配置模板，不包含真实密码
├── AGENTS.md                 # Codex 项目协作规则
└── README.md
```

## 本地运行条件

运行项目前，需要准备：

- Python 3；
- Node.js 与 npm；
- 可访问的 PostgreSQL 数据库；
- 已启用 PostGIS 扩展；
- 当前开发环境使用 Docker 容器 `mobilitydb`，本机端口为 `25432`。

当前仓库没有提供 `docker-compose.yml`，因此不会自动创建数据库容器。

## 后端配置与启动

以下命令均从项目根目录 `D:\my_project\Hormuz` 开始执行。

### 1. 创建并激活虚拟环境

```powershell
py -m venv .\backend\.venv
.\backend\.venv\Scripts\Activate.ps1
```

### 2. 安装后端依赖

```powershell
python -m pip install -r .\backend\requirements.txt
```

### 3. 配置数据库环境变量

先复制环境变量模板：

```powershell
Copy-Item .\.env.example .\.env
```

然后打开根目录 `.env`，把占位密码替换为本机数据库密码：

```env
DB_USER=aisdb
DB_PASSWORD=请填写本机数据库密码
DB_HOST=127.0.0.1
DB_PORT=25432
DB_NAME=aisdb
```

不要把真实数据库密码写进 README，也不要提交 `.env`。

### 4. 创建基础数据表

```powershell
python -m backend.create_tables
```

### 5. 按顺序执行 PostGIS 结构变更

```powershell
Get-Content -Raw .\backend\sql\001_add_events_location.sql |
    docker exec -i mobilitydb psql -U aisdb -d aisdb -v ON_ERROR_STOP=1

Get-Content -Raw .\backend\sql\002_add_ship_positions_location.sql |
    docker exec -i mobilitydb psql -U aisdb -d aisdb -v ON_ERROR_STOP=1

Get-Content -Raw .\backend\sql\003_add_location_indexes.sql |
    docker exec -i mobilitydb psql -U aisdb -d aisdb -v ON_ERROR_STOP=1

Get-Content -Raw .\backend\sql\004_add_ship_positions_latest_index.sql |
    docker exec -i mobilitydb psql -U aisdb -d aisdb -v ON_ERROR_STOP=1
```

这些脚本分别负责：

1. 为 `events` 添加自动生成的空间位置；
2. 为 `ship_positions` 添加自动生成的空间位置；
3. 为两个空间位置字段建立 GiST 索引；
4. 为按船舶和时间查询最新位置建立 B-tree 索引。

### 6. 生成教学模拟数据

先在内存中生成并检查，不修改数据库：

```powershell
python -m backend.generate_demo_data --validate-only
```

确认需要替换三张业务表中的现有模拟数据后，执行：

```powershell
python -m backend.generate_demo_data --confirm-reset
```

生成器使用固定随机种子，重建并验收 150 艘模拟船舶、14,400 条模拟位置和 80 条模拟事件。它只清空并重建 `ships`、`ship_positions` 和 `events`，任何验收错误都会回滚整个事务。

如果只需要最小数据闭环，也可以在空表中执行：

```powershell
python -m backend.seed_data
```

该最小数据脚本会插入 3 艘模拟船舶、10 条模拟位置和 2 条模拟事件。如果对应表中已经存在数据，脚本会跳过重复插入。

### 7. 启动 FastAPI

```powershell
python -m uvicorn backend.app.main:app --reload
```

启动后可以访问：

- 健康检查：<http://127.0.0.1:8000/health>
- Swagger 接口文档：<http://127.0.0.1:8000/docs>

## 前端安装与启动

打开另一个 PowerShell 窗口：

```powershell
cd D:\my_project\Hormuz\frontend
npm install
npm run dev -- --port 5174
```

浏览器访问：<http://localhost:5174>

当前 FastAPI 的 CORS 配置允许来源 `http://localhost:5174`，因此开发服务器应使用 5174 端口。

构建前端生产文件：

```powershell
cd D:\my_project\Hormuz\frontend
npm run build
```

## 当前接口

| 方法 | 路径 | 作用 |
| --- | --- | --- |
| GET | `/health` | 检查 FastAPI 是否正常运行 |
| GET | `/ships` | 获取船舶列表 |
| GET | `/ships/map` | 批量获取每艘船及其最新位置 |
| GET | `/ships/playback?start_at=&end_at=` | 一次获取指定模拟时段内的全部回放位置 |
| GET | `/ships/{ship_id}/positions` | 获取指定船舶的历史位置 |
| GET | `/ships/{ship_id}/nearby-events` | 根据船舶最新位置查询指定半径内的模拟事件 |
| GET | `/events` | 获取事件列表 |
| GET | `/simulation/meta` | 获取模拟数据起止时间、帧数和数据量 |

## 数据库脚本执行顺序

新建数据库时应按以下顺序执行：

```text
backend/create_tables.py
        ↓
backend/sql/001_add_events_location.sql
        ↓
backend/sql/002_add_ship_positions_location.sql
        ↓
backend/sql/003_add_location_indexes.sql
        ↓
backend/sql/004_add_ship_positions_latest_index.sql
        ↓
backend/generate_demo_data.py --confirm-reset
```

当前暂未引入 Alembic，数据库结构变化通过编号 SQL 文件记录。

## 当前进度

已完成：

- Vue、Leaflet 与两类在线地图图层；
- 模拟船舶 Marker、右侧检查面板和历史轨迹；
- 模拟事件 Marker、事件流与回放联动；
- PostgreSQL 三张业务表；
- FastAPI 船舶、轨迹和事件查询接口；
- FastAPI 地图船舶最新位置批量接口；
- PostGIS 船舶附近事件查询接口；
- 底部时间轴、播放/暂停、回到起点和 `0.5× / 1× / 2× / 4×` 回放；
- 船位、事件发生状态和选中船已航行轨迹随模拟时间联动；
- 模拟时段元数据与批量回放接口；
- 可重复生成并自动验收的大规模教学模拟数据；
- 前端从 FastAPI 加载数据库数据；
- PostGIS 空间字段、距离计算、范围查询和 GiST 索引。

尚未实现：

- 真实 AIS 数据接入；
- 用户登录与权限管理；
- 船舶实时更新；
- TimescaleDB 时序表；
- MobilityDB 移动物体模型；
- 完整端到端自动化测试体系与正式部署（已有 `npm run check:workbench` 轻量语义回归检查）。

## 数据与安全说明

- 当前地图中的船舶和事件均为模拟数据；
- 新闻测试数据不在当前地图主流程中使用；
- 不应把模拟结果描述为真实海上态势；
- 不要提交 `.env`、数据库密码或其他密钥；
- 引入真实数据前，需要单独确认数据来源、授权范围、时间范围和覆盖区域。


## 船讯网字段预留（005 迁移）

在 004 后执行 `backend/sql/005_add_shipxy_fields.sql`：

```powershell
Get-Content -Raw .\backend\sql\005_add_shipxy_fields.sql |
    docker exec -i mobilitydb psql -U aisdb -d aisdb -v ON_ERROR_STOP=1
```

- `ships` 新增可空 `length_m`、`width_m`；`flag` 改为可空；`ship_type` 保存中文。
- `ship_positions` 新增可空 `unix_time`、`nav_status`（中文）、`rot`、`draught_m`、`destination`、`ais_type`，以及非空 `data_source`（默认 `unknown`）。
- 本次迁移将现有教学船位标记为 `simulation`；模拟生成脚本显式写入该来源。未来真实数据导入必须显式写入 `shipxy`。
- 新供应方字段不向历史模拟记录填造数值。未来导入时从 Unix 秒时间生成带时区的 `recorded_at`，此转换目前尚未实现。
- ROT 原始值的单位与编码待供应方确认，不可直接据此判定紧急转弯。
- 不新增英文船型、英文航行状态、度分坐标、ETA、独立 Receivedtime 列；`events` 不变。
- 本次仅预留数据库和 ORM 字段；除船旗空值兼容外，新增字段尚未接入 API 输出与页面展示，尚无真实数据导入。
