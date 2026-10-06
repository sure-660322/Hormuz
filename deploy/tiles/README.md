# 本地底图瓦片服务

OSM 官方瓦片（tile.openstreetmap.org）在国内网络不可直接访问，本目录提供自建本地瓦片服务的配置与启停脚本。数据为 OSM 栅格瓦片（保留 © OpenStreetMap contributors 署名）。

## 组成

- `nginx.conf` — Windows Nginx 配置：监听 8080，`/tiles/{z}/{x}/{y}.png` 映射仓库根目录 `tiles/`，带 CORS 头；缺瓦返回透明占位图 `blank.png`
- `start-tile-server.ps1` / `stop-tile-server.ps1` — 启停脚本（nginx 程序本体在 git 忽略的 `local-archive/nginx-1.30.5/`）
- 瓦片数据由 `scripts/download_tiles.py` 下载（z0–z12 全框 33.5–64°E / 15.5–38°N，共约 13.6 万张 / 约 3 GB，可断点续传）

## 使用

```powershell
# 1. 下载瓦片（首次；中断后重跑即可续传。本机需代理，默认 http://127.0.0.1:7897，
#    可用 $env:TILE_PROXY 覆盖，置空字符串则直连）
python scripts/download_tiles.py

# 2. 启动服务
powershell -File deploy/tiles/start-tile-server.ps1

# 3. 前端 frontend/.env 配置（不设则回退 OSM 官方瓦片）
#    VITE_TILE_URL=http://localhost:8080/tiles/{z}/{x}/{y}.png
```

验证：`curl http://localhost:8080/health` 返回 `tile server ok`；前端地图正常显示即通。

## 来源与署名

瓦片来自 OSM 官方服务器（`tile.openstreetmap.org` 的标准 Carto 样式），署名 © OpenStreetMap contributors，必须保留。本机直连该服务器会被限速/断连，下载走本地代理；OSM Tile Usage Policy 不鼓励批量下载，脚本并发保持保守（14 线程 + 请求间隔 + 失败退避），如换用其他来源注意各自条款。

## 部署到服务器

1. 拷贝 `tiles/` 目录到服务器；
2. 拷贝 `nginx.conf`，修改 `listen` 端口与 `alias` 路径；
3. 前端构建时把 `VITE_TILE_URL` 指向服务器地址。

若服务器可流畅访问国际网络，更简单的做法是在服务器上直接重跑 `scripts/download_tiles.py` 拉取（直连即可，或将 `TILE_PROXY` 指向服务器上的代理）。国内服务器且出口受限时，推荐改用 Geofabrik PBF（分段并发下载）→ tilemaker → tileserver-gl 的自渲染管线。

OpenSeaMap 海事注记层（tiles.openseamap.org）目前仍为境外服务，未纳入自建范围；如目标网络不可达，需另行处理。
