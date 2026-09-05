# 霍尔木兹海峡船舶态势地图

这是一个用于学习前后端与空间数据库协作方式的船舶态势地图项目。当前功能分支已经把公开历史 AIS 位置导入独立数据表，并完成从 PostgreSQL、FastAPI 到 Vue 与 Leaflet 地图的展示闭环。

> 当前页面只显示历史 AIS 数据，不显示教学模拟船舶和模拟事件。该数据主要覆盖迪拜/杰贝阿里，陆基接收存在盲区，不代表完整霍尔木兹海峡态势；数据集页面未声明 License，公开发布前还需确认授权。

## 当前功能

### 地图

- 默认定位到霍尔木兹海峡附近；
- 使用 OpenStreetMap 显示基础地图；
- 使用 OpenSeaMap 叠加航标、浮标和灯塔等海事信息；
- 根据当前地图范围加载 OpenSeaMap 港口图标；
- 支持鼠标拖动和滚轮缩放。

### 历史 AIS 船舶

- 显示 619 艘 AIS 船舶在所选时刻的最后已知位置；
- 点击 Marker 查看 MMSI、报位时间、速度、航向、船首向和来源；
- 点击“查看轨迹”加载该船在原始文件中的完整位置序列；
- 按 UTC 日期加载不超过 24 小时的历史窗口；
- 使用 5 分钟时间轴播放、暂停、回到起点和调整速度；
- 原始速度和航向伪值暂不清洗，页面按原值展示。

### 数据库与空间查询

- 使用 `ships` 保存船舶基本信息；
- 使用 `ship_positions` 保存船舶历史位置；
- 使用 `events` 保存地图事件；
- 使用 `ais_datasets` 保存来源、版本、校验值和覆盖说明；
- 使用 `ais_vessels` 保存按 MMSI 汇总的展示信息；
- 使用 `ais_positions` 原样保存 Parquet 的 15 个业务字段；
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
│   │   ├── App.vue           # 地图页面与 Leaflet 逻辑
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

Get-Content -Raw .\backend\sql\005_add_ais_history_tables.sql |
    docker exec -i mobilitydb psql -U aisdb -d aisdb -v ON_ERROR_STOP=1
```

这些脚本分别负责：

1. 为 `events` 添加自动生成的空间位置；
2. 为 `ship_positions` 添加自动生成的空间位置；
3. 为两个空间位置字段建立 GiST 索引；
4. 为按船舶和时间查询最新位置建立 B-tree 索引；
5. 新增独立 AIS 数据集、船舶、原始位置表及查询索引。

### 6. 导入原始 AIS 位置

以下命令直接读取 `positions.parquet`，不使用已有的清洗 CSV，也不会删除或修改模拟表：

```powershell
python -m backend.import_ais_data `
  --source "C:\Users\18242\Desktop\web\Hormuz-AIS公开数据-2026-07-27\positions.parquet" `
  --confirm-import
```

不加 `--confirm-import` 时只校验字段、SHA-256、记录数、船舶数和时间范围。相同 SHA-256 已导入时会跳过，避免重复写入。

### 7. 生成教学模拟数据（当前 AIS 页面不读取）

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

### 8. 启动 FastAPI

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
| GET | `/ais/meta` | 获取当前 AIS 数据集的来源、范围和数量 |
| GET | `/ais/vessels` | 获取 AIS 船舶展示信息 |
| GET | `/ais/ships/map?at=` | 获取指定时刻每艘船的最后已知位置 |
| GET | `/ais/ships/playback?start_at=&end_at=` | 获取不超过 24 小时的原始 AIS 回放位置 |
| GET | `/ais/ships/{vessel_id}/positions` | 获取单船完整原始 AIS 轨迹 |

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
backend/sql/005_add_ais_history_tables.sql
        ↓
backend/import_ais_data.py --source <positions.parquet> --confirm-import
```

当前暂未引入 Alembic，数据库结构变化通过编号 SQL 文件记录。

## 当前进度

已完成：

- Vue、Leaflet 与两类在线地图图层；
- 模拟船舶 Marker、Popup 和历史轨迹；
- 模拟事件 Marker 与 Popup；
- PostgreSQL 三张业务表；
- FastAPI 船舶、轨迹和事件查询接口；
- FastAPI 地图船舶最新位置批量接口；
- PostGIS 船舶附近事件查询接口；
- 底部时间轴、播放/暂停、回到起点和 `0.5× / 1× / 2× / 4×` 回放；
- 船位、事件发生状态和选中船已航行轨迹随模拟时间联动；
- 模拟时段元数据与批量回放接口；
- 175,773 条原始 AIS 位置和 619 艘船的独立数据层；
- AIS 最新位置、日期窗口回放和单船完整轨迹接口；
- 当前前端只读取 AIS 接口，模拟船舶和事件已从页面数据流屏蔽；
- 可重复生成并自动验收的大规模教学模拟数据；
- 前端从 FastAPI 加载数据库数据；
- PostGIS 空间字段、距离计算、范围查询和 GiST 索引。

尚未实现：

- AIS 数据清洗、实时接入和来源授权确认；
- 用户登录与权限管理；
- 船舶实时更新；
- TimescaleDB 时序表；
- MobilityDB 移动物体模型；
- 自动化测试与正式部署。

## 数据与安全说明

- 当前功能分支地图中的船舶来自历史 AIS 数据，模拟表仍保留但页面不读取；
- `transit_events.parquet` 的 260 条记录全部属于迪拜/杰贝阿里闸线，本阶段未导入为霍尔木兹事件；
- 新闻测试数据不在当前地图主流程中使用；
- 不应把模拟结果描述为真实海上态势；
- 不要提交 `.env`、数据库密码或其他密钥；
- 引入真实数据前，需要单独确认数据来源、授权范围、时间范围和覆盖区域。
