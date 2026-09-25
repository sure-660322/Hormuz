# 数据库与环境交接

> 2026-09-25 当前状态：本机 `ships` 和 `ship_positions` 已清空，模拟船舶交接文件及旧 manifest 已移除；仓库目前没有可导入的四表数据包。`events.jsonl` 和 `news.jsonl` 仍保留，但未作为当前快照重新核验。以下 2026-09-14 的导入命令、预期数量及成功演练均为历史记录，不能直接对现有文件执行。真实 AIS 尚未导入应用库。

历史状态：2026-09-14 曾提供独立 Docker Compose、四表 JSONL 交接数据、空库导入与核验脚本，并在新容器、新数据卷上演练。脚本保留，当前缺少完整数据包。Git 不会同步运行中的数据库。

## 仓库提供哪些数据

| 路径 | 内容与用途 |
| --- | --- |
| data/handoff/current/events.jsonl | 65 个新闻聚合事件及加工字段 |
| data/handoff/current/news.jsonl | 290 条报道的来源、日期、摘要及加工字段；223 条关联事件，67 条无关联 |
| sim_ais_demo/output_news_aligned/ | 旧模拟批次的历史报告；船舶和报位数据文件已删除 |
| sim_ais_demo/config/news_aligned_config.json | 旧模拟配置，仅供历史参考 |

保留的新闻文件不包含 .env、账户、数据库角色或 pg_dump 恢复备份。news 不含文章全文；来源链接与摘要不代表取得原始报道的再许可，使用时保留来源。已有 data/news_data 是历史采集资料，不是当前四表导入入口。

事件封面图单独保存在新闻原始资料的 `images/` 子目录，不在上述 JSONL 或 Git 数据包中。运行后端前可设置环境变量 `NEWS_IMAGE_ROOT` 为该子目录的上一级目录，例如本机 `D:\my_project\news_raw_data`，后端按 `events.image_path` 中的 `images/<文件名>` 读取。未设置时默认使用仓库上一级的 `news_raw_data`；服务器部署时应显式设置服务器自己的目录，并单独传输图片。`GET /events/{event_id}/cover` 在图片缺失或路径无效时返回 404；目前没有图片上传、对象存储或自动同步流程。历史交接数据的图片文件是否齐全需在目标机器另行核验。

历史四表交接设计保留 ships.id、ship_positions.ship_id、events.id、news.event_id 的数据库关系；events.event_id 是业务字符串，和 news.event_id 的整数外键不同。当前缺少船舶文件，不能按旧流程导入。

## 1. 获取代码和安装依赖

安装并启动 Docker Desktop（Linux containers），准备 Python 3.11+、Node.js/npm、Git、PowerShell 7。以下命令均在克隆目录根部执行；路径按自己的机器调整。

```powershell
git clone https://github.com/sure-660322/Hormuz.git
cd Hormuz
py -m venv .\backend\.venv
.\backend\.venv\Scripts\python.exe -m pip install -r .\backend\requirements.txt
```

克隆默认分支 main 即可，交接内容已合并到 main，不需要指定其他分支。已有仓库的成员先提交或保存自己的修改，再执行 `git pull` 更新 main。仓库为私有仓库，需要先由维护者加为协作者才能克隆。

## 2. 配置独立数据库

```powershell
if (-not (Test-Path -LiteralPath .\deploy\handoff.env)) {
    Copy-Item .\deploy\handoff.env.example .\deploy\handoff.env
}
notepad .\deploy\handoff.env
```

将 DB_PASSWORD=CHANGE_ME 改成自己新设的本地密码，建议使用字母和数字组成的较长密码。其余默认值：用户 hormuz、数据库 hormuz_handoff、主机 127.0.0.1、端口 25433。文件已被 Git 忽略，不共享密码，不复制维护者的 .env。

```powershell
docker compose --env-file deploy/handoff.env -f compose.handoff.yaml up -d --wait
docker compose --env-file deploy/handoff.env -f compose.handoff.yaml ps
```

看到 db 为 healthy 后继续。默认使用独立项目 hormuz-handoff 和独立命名数据卷，端口只绑定本机；不会连接维护者的 25432 数据库。端口冲突时修改 handoff.env 的 DB_PORT 后重新启动。

使用官方 mobilitydb/mobilitydb:17-3.5-1.3 镜像，提供 PostgreSQL 17、PostGIS 3.5、MobilityDB 1.3。镜像来源见 [官方镜像仓库](https://github.com/MobilityDB/MobilityDB-docker)。本环境不包含 TimescaleDB；当前业务未使用其能力，四表查询、地图回放与 MobilityDB 试验不依赖它。官方版本标签可能更新构建，本次验证镜像 digest 为 sha256:e5b7428cc613cfa278c89107d14991466a7d8e5984aa131a4bec3d002ce50f40。

## 3. 创建当前结构并导入

> 以下为 2026-09-14 历史演练命令；当前缺少 `ships.jsonl`、`ship_positions.jsonl` 和 `manifest.json`，执行会失败。待新真实数据经过来源与格式核验、重新导出完整交接包并在独立空库验收后，才能恢复此流程。

```powershell
.\backend\.venv\Scripts\python.exe -m backend.handoff_run import --database hormuz_handoff
if ($LASTEXITCODE -ne 0) { throw '导入未完成，请检查空库、配置与数据文件。' }
.\backend\.venv\Scripts\python.exe -m backend.handoff_run verify
```

如更改 DB_NAME，--database 必须填写同样的名称。handoff_run 只使用 deploy/handoff.env，覆盖当前进程的数据库配置，不改根目录 .env。

导入前验证数据文件 SHA-256 和字段，再检查目标库不存在五张应用表。已有任何应用表（即使为空）就拒绝导入；不会 DROP/TRUNCATE 或覆盖现有数据。建表、插入、序列设置与回查在同一事务中完成，遇错回滚。

2026-09-14 历史预期数量：ships=30、ship_positions=9354、events=65、news=290。verify 逐行对比所有导入字段，不只是核对数量。首次导入后 location 由 PostGIS 生成列重建，主键、唯一约束、外键、空间和最新船位索引由 008 建立。

重复执行 import 失败是保护机制。已有导入结果只需 verify；需要另一份测试环境时使用新的 Compose 项目、空数据卷和端口，不清理已有数据库。本数据包是定时快照，以后数据库更新不会自动推送，需要重新导出、验证和提交。

## 4. 重建 MobilityDB 派生轨迹

```powershell
.\backend\.venv\Scripts\python.exe -m backend.handoff_run build-mobility
```

2026-09-14 历史演练预期为 114 段。当前无船位数据，不运行本节命令。主回放仍读取 ship_positions；新源数据接入后需要另行核验并显式重建派生数据。

## 5. 验证并启动应用

```powershell
.\backend\.venv\Scripts\python.exe -m backend.verify_handoff
.\backend\.venv\Scripts\python.exe -m backend.handoff_run serve
```

verify_handoff 在 18001 端口临时启动测试 API，完成后关闭；该端口需空闲。serve 在 8000 启动后端，若已有后端占用此端口，先停止旧进程。

另开 PowerShell 终端，在仓库根部执行：

```powershell
cd frontend
npm ci
npm run dev -- --port 5174
```

打开 [地图](http://localhost:5174)、[健康检查](http://127.0.0.1:8000/health)、[接口文档](http://127.0.0.1:8000/docs)、[停留分析](http://127.0.0.1:8000/mobility-demo)。检查新闻列表、船位、回放及浏览器网络请求。本次交接已验证后端 HTTP，不宣称完成新机器的浏览器端验收。

暂停独立数据库而保留数据：

```powershell
docker compose --env-file deploy/handoff.env -f compose.handoff.yaml stop
```

再次使用时执行第 2 步的 up 命令，无需重新导入。不要使用 down -v，它会删除该 Compose 环境的数据卷。

## 当前验证记录

2026-09-14：独立官方 Docker 镜像空库导入成功；四源表逐行一致；PostGIS 生成列、两项船位索引、源表外键和序列已核验；重复导入被拒绝；114 段派生轨迹重建成功。/health、/docs、/ships、/ships/map、/events、/events/evt_001/news、/simulation/meta、/mobility-demo/analysis、/mobility-demo/tracks 均返回 200。原数据库只读回查仍与导出数据一致。

## 旧脚本边界

- 008_fresh_handoff_schema.sql 是新空库入口，由 handoff 脚本在事务和空库保护下执行；不要对已有库直接重放。
- 001–007 是历史演进，不能无条件顺序执行；006 会重建新闻表。
- 009_ship_tracks.sql 是 P0 泛化派生层（ship_tracks、track_build_manifest、源表 BRIN/data_source 索引），全部由 backend/build_ship_tracks.py 以幂等 DDL 执行并负责重建与 manifest 留痕；不进交接包，新库首次重建时自动建立。
- 010_event_ship_links.sql 是 P2 事件×船舶关联派生表，由 backend/build_event_ship_links.py 幂等执行与重建（mentioned 恒不指向模拟船）；同样不进交接包。
- 011_ship_dwell.sql 是 P3 停留识别派生表（at_anchor/drift/slow_transit），由 backend/build_ship_dwell.py 幂等执行与重建，阈值入 manifest；同样不进交接包。
- 012_encounters.sql 是 P4 相遇分析派生表（一船对一行 + params 快照），由 backend/build_encounters.py 幂等执行与重建；POST /api/encounters/analyze 是受控同步重建入口；同样不进交接包。
- 013_agent_analytics_readonly.sql 是 SQL-02 的语义视图与最小权限角色迁移，会撤销目标数据库 `PUBLIC` 的 TEMP 及 `public` schema 默认权限；不得随普通交接导入自动执行。先按 [SQL-02 说明](query_analytics_sql02.md) 在独立库验证并由 DBA 评审既有角色依赖，再单独部署。
- create_tables.py 只补 ORM 表，不准备全部扩展、空间结构和索引。
- migrate_real_news.py 仍是维护者历史迁移工具，依赖仓库外源路径；新成员使用本页的导入入口。
- seed_data.py、generate_demo_data.py 使用旧事件语义，不作为当前初始化入口。
- 数据库恢复备份继续留在本地，不提交 Git。本数据包不替代完整灾备。

智能体当前接入见 [agent_integration.md](agent_integration.md)：v4 自定义工具循环已接入前端，注册表包含 8 个确定性只读工具和默认关闭的受限分析工具；模型配置需在后端环境单独准备，数据导入不会自动配置模型服务。下一版 LangChain 方案见 [langchain_agent_v1_plan.md](langchain_agent_v1_plan.md)。本页的历史交接验收不包含智能体联调。
