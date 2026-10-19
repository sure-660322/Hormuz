# 小组服务器部署

代码、Docker 配置、本文及静态资源附件放 GitHub；含 AIS 的数据库备份只由维护者私发。
适用 Linux Docker Engine + Compose v2，本轮本地验收平台为 linux/amd64；目标为 2 核 / 4 GB / 40 GB SSD 的小组试运行。
无需在服务器另装 Node.js、Python 或 PostgreSQL；构建时需要联网下载基础镜像和项目依赖。

## 1. 获取代码与两个包

仓库为私有仓库，队员需已有访问权限。发布入口：
[server-deploy-20261019](https://github.com/sure-660322/Hormuz/releases/tag/server-deploy-20261019)。

```bash
git clone --branch server-deploy-20261019 https://github.com/sure-660322/Hormuz.git
cd Hormuz
```

从该 GitHub 发布页下载 `hormuz-web-resources-20261019.tar.gz` 和同名 `.sha256`；从维护者私下接收 `hormuz-ais-database-20261019.tar.gz` 和同名 `.sha256`。
将这四个文件放到服务器仓库根目录。数据库包不要上传 GitHub、发布附件或公开链接。

```bash
sha256sum --check hormuz-web-resources-20261019.tar.gz.sha256
sha256sum --check hormuz-ais-database-20261019.tar.gz.sha256
tar -xzf hormuz-web-resources-20261019.tar.gz
tar -xzf hormuz-ais-database-20261019.tar.gz
```

解压后目录为：`deployment-data/database/`、`deployment-data/news/images/`、`deployment-data/tiles/`。
根目录 `.gitignore` 已忽略 deployment-data 和这两个命名系列的压缩包/校验文件，避免私发 AIS 包被误提交。
静态包只有新闻图片、地图瓦片和校验清单，不包含 AIS、数据库或密码。数据库包包括完整业务表，保留新闻/事件与船位之间的 ID/外键。
数据日期和数量见 database-manifest.json。勿用旧 data/handoff/current 的新闻 JSONL 替代此数据库包。

```bash
(cd deployment-data && sha256sum --check --quiet SHA256SUMS.resources)
```

## 2. 检查资源并生成服务器配置

先确认服务器剩余资源；建议部署前至少剩余 25 GB 磁盘，已有系统/网站、备份和 Docker 数据占用另算。
选择新工作目录，不覆盖其他网站或其数据库卷。Docker 构建与恢复使用额外临时空间。

```bash
docker compose version
bash deploy/server/configure.sh
```

输入网站用户名与至少 12 位的密码。脚本生成 `.env.server` 中的新数据库密码及 `deploy/server/config/htpasswd`，不会读取维护者 .env。
这些配置仅保存在服务器，不上传 GitHub。需要智能体时，在服务器编辑 .env.server 的 DEEPSEEK_API_KEY（可选 BASE_URL/MODEL）。
模型密钥空缺时地图功能可用，智能体返回未配置。受控 SQL 默认关闭；不实施 017、不建分析快照、不启外部 MCP。

## 3. 构建并恢复

```bash
bash deploy/server/build.sh
bash deploy/server/restore.sh
```

build.sh 串行构建两个应用镜像，减少 4 GB 机器构建时的内存压力。
数据库镜像为 `mobilitydb/mobilitydb:17-3.5-1.3`，带 PostgreSQL 17、PostGIS 3.5、MobilityDB 1.3。
源库没有 TimescaleDB 时序表，备份不携带其内部对象，目标无须额外安装该扩展。

恢复只接受空业务库；发现任一业务表就拒绝，不覆盖现有数据。单事务串行恢复完成后，用应用只读账号核对全部表数量、索引、约束和地理生成列。
不要对当前库重放旧 001–007 迁移或运行 seed_data.py。旧派生表按源快照保留，不重建已取消分析。
若恢复失败，保存错误日志并联系维护者，勿直接删卷或清库。

## 4. 启动并接入网址

```bash
bash deploy/server/start.sh
bash deploy/server/dc.sh ps
```

默认仅绑定服务器 `127.0.0.1:8088`，供现有 Nginx/Caddy 的 HTTPS 入口转发。数据库/API 不发布主机端口。
让服务器负责人把域名 HTTPS 反代至此地址，保留 Authorization 请求头；页面、API、图片与地图共用入口，不用改 CORS 或重新写入服务器 IP。
入口密码保护全部业务接口；智能体另有限频。这是团队共用入口，应用内用户权限系统尚未实现。

无域名时可先用 SSH 隧道验收，在自己的电脑执行（替换用户名和 IP）：

```bash
ssh -L 8088:127.0.0.1:8088 USER@SERVER_IP
```

然后访问 http://127.0.0.1:8088。若要直接经公网 IP 分享，由负责人先配置 HTTPS 或团队 VPN，再设置入口绑定；不要直接开放数据库或后端端口。

## 5. 核验与维护

```bash
bash deploy/server/dc.sh run --rm --no-deps --entrypoint python api /app/deploy/verify_database.py
bash deploy/server/dc.sh logs --tail 100 api
```

浏览器检查底图、船位、七日回放、两个案例、新闻图片、区域/通行统计；配置模型密钥后单独验收真实问答。
本地瓦片有区域与缩放限制，缺瓦用透明占位图；OpenSeaMap 注记、港口查询和案例原报道图片仍依赖外网。
AIS 是历史观测数据；来源授权、覆盖与身份/因果证据边界沿用项目现有说明，团队入口不作为公开数据发布。

```bash
bash deploy/server/dc.sh stop
bash deploy/server/dc.sh start
```

stop 保留数据；不要用 `down -v` 删除卷。修改模型配置后用 `bash deploy/server/dc.sh up -d api` 重建服务环境。
数据库密码在首次空卷初始化时设置，改 .env.server 不会自动修改已有数据库角色密码。
更新代码和导入新数据是两回事，先备份服务器业务库；本恢复脚本不承担升级和覆盖。
详细本地验收及未验证项见 [validation.md](validation.md)。
