# MobilityDB 小规模引入（2026-09-11）

本试验已使用本机 MobilityDB 1.3.0 和 PostGIS 3.5.2 实际构建派生轨迹，计算区域停留时间。数据全部来自教学模拟船位，不代表真实 AIS，也不能证明新闻事件的因果影响。

## 使用

启动项目后，从主地图顶部“停留分析试验”进入，或打开 http://127.0.0.1:8000/mobility-demo 。选择大小两个区域，点击船名查看轨迹及前后时长柱形对比。

- `GET /mobility-demo/analysis?area=strait`：海峡附近小范围，56.15–56.75°E、26.20–26.95°N。
- `GET /mobility-demo/analysis?area=approach`：邻近水域大范围，56.0–57.3°E、25.8–27.1°N。
- `GET /mobility-demo/tracks`：派生轨迹的 GeoJSON。
- 两个窗口：2026-02-26 至 02-28、2026-03-01 至 03-03；均为 UTC、48 小时、右端不包含。

## 范围与计算

从曾在小范围内报位的模拟船中，按 MMSI 排序固定选前10艘。不是随机样本，不代表150艘船队。使用7天轨迹构建71段派生数据，保留于独立表 `mobility_demo_segments`，使用 `tgeompoint` 和 GiST 索引。未改变现有船位、新闻、事件或主地图回放语义。

将 EPSG:4326 坐标转换到 UTM 40N（EPSG:32640），在相邻报位之间线性插值；超过90分钟的间隔断开，孤立点不贡献持续时间。查询使用 `atTime` 截取时间、`atGeometry` 裁剪区域、`duration(..., false)` 累计各段时长，不把中间空窗加入持续时间。

区域停留包括航行通过与等待，不等于锚泊时长。覆盖率是可构建轨迹时长除以48小时；未覆盖部分包括缺报、出区及尚未进入观测等情况，不能当作零停留。90分钟阈值尚未做敏感性分析，锚泊的天然长报位间隔也可能被排除。投影后区域边界按角点直线连接；轨迹示意无海岸线，不用于航道安全判断。

派生表是手动构建快照，不会自动跟随源数据刷新。重建脚本仅清理这个试验派生表，保留四张源表，并核对源表内容摘要。SQL结构变更按007编号记录，未引入新依赖或自动迁移框架。

## 验证与复现

在项目根目录的 PowerShell 7 执行：

```powershell
cd D:\my_project\Hormuz
.\backend\.venv\Scripts\python.exe -m backend.build_mobility_demo
.\backend\.venv\Scripts\python.exe -m scripts.verify_mobility_demo
```

构建脚本在单个遇错回滚事务中执行007结构及派生数据构建。验证脚本已检查实际列类型、GiST索引、源表完整性；独立用Python对相邻报位做时间和凸多边形裁剪，核对两个区域全部10艘船两期结果。差异均小于0.0001小时（0.36秒），来自接口保留4位小数。另有合成例：跨越区域的1小时航段应停留30分钟、含2小时间断的两段轨迹应累计2小时，均通过。

结果保存在 `sim_ais_demo/output/mobility_build.json` 和 `mobility_verification.json`。尚未进行大规模性能基准测试，因此不声称快于普通SQL/PostGIS。

HTTP实测：`/health`、`/docs`、演示页、两个区域分析接口和轨迹接口均200，未知区域参数422；结果见 `mobility_http_verification.json`。前端构建与现有回归检查通过。浏览器已验证选中散货船012、切换大小范围、柱形图及轨迹更新，控制台未见错误或警告。小范围样本累计停留31.94→93.96船·小时，大范围68.66→174.91船·小时。散货船012在小范围为3.79→40.90小时，两期轨迹覆盖率约73%和85%。

官方功能参考：https://mobilitydb.com/project.html ，https://mobilitydb.github.io/MobilityDB/master/apas06.html 。实际函数签名以本机数据库目录及运行结果为准。
