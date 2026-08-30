# 霍尔木兹海峡船舶态势地图

这是一个用于学习前后端与空间数据库协作方式的船舶态势地图项目。项目当前使用少量模拟船舶、模拟轨迹和模拟事件，完成了从 PostgreSQL 到 FastAPI，再到 Vue 与 Leaflet 地图的最小数据闭环。

> 当前所有船舶、轨迹和事件均为教学用模拟数据，不代表真实 AIS 船舶活动或真实海上事件。

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
- 点击船舶 Marker 查看船名、MMSI、类型、速度、航向和位置；
- 从 FastAPI 获取模拟事件并显示事件 Marker；
- 点击事件 Marker 查看事件标题、描述、类型、时间和位置。

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
```

这些脚本分别负责：

1. 为 `events` 添加自动生成的空间位置；
2. 为 `ship_positions` 添加自动生成的空间位置；
3. 为两个空间位置字段建立 GiST 索引。

### 6. 插入模拟数据

```powershell
python -m backend.seed_data
```

脚本会插入 3 艘模拟船舶、10 条模拟位置和 2 条模拟事件。如果对应表中已经存在数据，脚本会跳过重复插入。

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
| GET | `/ships/{ship_id}/positions` | 获取指定船舶的历史位置 |
| GET | `/ships/{ship_id}/nearby-events` | 根据船舶最新位置查询指定半径内的模拟事件 |
| GET | `/events` | 获取事件列表 |

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
backend/seed_data.py
```

当前暂未引入 Alembic，数据库结构变化通过编号 SQL 文件记录。

## 当前进度

已完成：

- Vue、Leaflet 与两类在线地图图层；
- 模拟船舶 Marker、Popup 和历史轨迹；
- 模拟事件 Marker 与 Popup；
- PostgreSQL 三张业务表；
- FastAPI 船舶、轨迹和事件查询接口；
- PostGIS 船舶附近事件查询接口；
- 前端从 FastAPI 加载数据库数据；
- PostGIS 空间字段、距离计算、范围查询和 GiST 索引。

尚未实现：

- 真实 AIS 数据接入；
- 用户登录与权限管理；
- 船舶实时更新；
- TimescaleDB 时序表；
- MobilityDB 移动物体模型；
- 自动化测试与正式部署。

## 数据与安全说明

- 当前地图中的船舶和事件均为模拟数据；
- 新闻测试数据不在当前地图主流程中使用；
- 不应把模拟结果描述为真实海上态势；
- 不要提交 `.env`、数据库密码或其他密钥；
- 引入真实数据前，需要单独确认数据来源、授权范围、时间范围和覆盖区域。
