> 2026-10-11 用户确认：旧 MobilityDB 派生停留识别、相遇分析、observed 时空邻近事件关联及 P5 simplified 回放切换已退出当前项目范围，不再作为待办、验收缺口或业务就绪条件。区域活动服务中的观测停留船时、真实 AIS 原始报位轨迹与实测航速、新闻 mentioned 文本证据继续保留。遗留代码/API 的存在不代表当前业务目标；本轮只清理文档，不删除代码、不操作数据库或服务。

# 真实 AIS 七日导入与对账

> 状态（2026-09-25）：**应用库已导入并完成逐日对账、接口冒烟、单船浏览器交互和代码测试**。用户在执行中明确取消独立测试库要求，故七日独立测试库验证未执行。四艘新闻船关联未处理；MobilityDB 派生层未重建，见下方限制。此处是本机 `aisdb` 的状态，不代表远端部署。

代码状态：导入 `ee7b81e` 与船舶详情修复 `5b663bd` 已于 2026-09-25 快进合入本地 `main`；未推送。数据库内容不随 Git 提交或合并复制。

## 来源与方法

- 来源为 `D:\my_project\AisData\20260922175235_0922南京师范大学_202602` 及同批次 `_202603` 下的七个原始 CSV。原文件未改动。`data/ais_seven_day_audit.jsonl` 记录每个文件的绝对路径、字节数、SHA-256、25 列表头、GB18030 严格解码结果、逐列空值、MMSI/经纬度/时间检查及 UTC 边界；扫描按行进行，未将整批 CSV 装入内存。
- 入库前 `aisdb` 为 `ships=0`、`ship_positions=0`、`ais_import_batches=0`、`events=65`、`news=290`。使用容器内 `pg_dump -Fc` 完整备份到 `D:\my_project\AisData\backups\aisdb_before_real_ais_20260925.dump`（300,218 字节，SHA-256 `F287090036CE6026343344CBC00AFD1E21D130E2A2D16E102300D664F52461A8`）；`pg_restore -l` 可读取目录。未演练恢复。备份留在仓库外。
- `backend/import_real_ais_days.py` 对照审计清单重新计算每个文件哈希，用 PostgreSQL `COPY` 流式写会话临时表；检查源行、主字段、时间/坐标和已有时窗后，按日事务写入船舶、报位与批次。来源批次和逻辑 CSV 行号分别保存在 `ais_import_batches`、`ship_positions.source_batch_id/source_row`；原 CSV 保留。已存在的同日批次只有文件、哈希、大小、行数和行号范围一致才可重跑跳过；冲突直接失败，不覆盖或静默丢行。单独重跑 2 月 25 日返回 `already_imported`、3,634,184 条，未重复插入。
- 文件日界按 UTC+8 解释，连续覆盖 UTC 2026-02-24 16:00:00 至 2026-03-03 15:59:59。每个源文件的全部 UnixTime 都落在各自本地日内；七个半开 UTC 日期区间互不相交。导入时逐日检查目标时窗已有报位数为 0，因此跨文件不存在同一时间报位重复；**单文件内部仍可有同一 MMSI、同一秒的多条不同报位，全部原样保留**。

## 逐日结果

执行日期：2026-09-25。`data/ais_seven_day_import.jsonl` 是逐日提交后的完整机器可读对账结果。`COPY` 行数、批次 `expected_rows/inserted_rows`、实际报位数及来源行号唯一数均逐日相等；`location` 空值与跨文件时窗重叠均为 0。

| UTC+8 文件日 | CSV/入库报位 | 文件内 MMSI 数 | 新增船舶 | 累计船舶 | 累计报位 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 2026-02-25 | 3,634,184 | 2,801 | 2,801 | 2,801 | 3,634,184 |
| 2026-02-26 | 3,141,413 | 2,441 | 407 | 3,208 | 6,775,597 |
| 2026-02-27 | 2,748,940 | 2,325 | 321 | 3,529 | 9,524,537 |
| 2026-02-28 | 2,809,848 | 2,421 | 385 | 3,914 | 12,334,385 |
| 2026-03-01 | 2,108,102 | 2,028 | 220 | 4,134 | 14,442,487 |
| 2026-03-02 | 1,982,987 | 1,889 | 163 | 4,297 | 16,425,474 |
| 2026-03-03 | 1,496,059 | 1,841 | 165 | 4,462 | 17,921,533 |

导入后独立 SQL 回查：7 个批次各自 `expected_rows = inserted_rows = SELECT count(*) FROM ship_positions WHERE source_batch_id=...`；全库 4,462 艘、17,921,533 条，生成 `location` 空值 0；`events=65`、`news=290`，未清空。来源唯一索引 `idx_ship_positions_source_row` 与查询索引 `idx_ship_positions_ship_recorded_at` 均存在。

## 接口与测试

同日通过应用库 FastAPI `TestClient` 请求 `/health`、`/docs`、`/simulation/meta`（均 200）；跨 2 月 25/26 UTC 16:00 日界的 `/ships/snapshot` 返回 1,767 / 1,763 艘，三帧 `/ships/snapshot-window` 返回 1,767 / 1,765 / 1,763 艘；3 月 3 日日末快照 1,063 艘。跨日单船 `ship_id=342` 的一小时 `/ships/342/track-window` 返回 2 条源报位、2 个采样点、1 段。无时区快照及反向轨迹窗口均返回 422。结果见 `data/ais_api_verification.json`。这验证接口与跨日读取，不是七日浏览器验收或并发性能证明。

`python -m pytest backend/tests -q`：246 passed、12 skipped；`frontend/npm run build` 与 `npm run check:workbench` 均通过。上述测试不替代独立测试库验证。

同日七日应用库页面补验：相遇派生层尚未构建时，`/api/encounters` 的 `not_built` 响应没有 `encounters` 数组，旧前端曾因此在态势总览渲染时报错，阻断船舶交互。前端已按响应状态处理；在 5174/8000 浏览器中，从列表和地图标记点击船只可打开详情，查看轨迹（样本船 107 条原始报位、46 个采样点、2 段）并开启按实测航速的速度着色；控制台 0 error / 0 warning。仍未做整周浏览器和并发验收。

## 重跑与限制

从仓库根目录，以已审计的原始文件顺序运行；脚本仅接受 `DB_NAME=aisdb` 环境，`--target app` 指向应用库。重新运行先逐文件哈希与已入库批次/来源行号对账，同日不同文件或记录冲突会停止。新增批次前应再次备份并核对应用库。

```powershell
$files = Get-ChildItem -LiteralPath 'D:\my_project\AisData' -Recurse -File -Filter '2026-*.csv' |
    Where-Object { $_.BaseName -ge '2026-02-25' -and $_.BaseName -le '2026-03-03' } |
    Sort-Object Name | Select-Object -ExpandProperty FullName
.\backend\.venv\Scripts\python.exe -m backend.import_real_ais_days --target app --audit .\data\ais_seven_day_audit.jsonl $files
```

- 供应商授权、目标海峡覆盖完整性及字段单位未核实；`nnu_ais` 只是内部来源标签，不能当作授权或区域代表性证明。十位标识原样保留，不能推定为标准九位 MMSI。`ships` 保存各船最后出现日的属性快照，历史属性变化仍须回到原 CSV。
- 源数据中查到 2,922 组同船同秒的多报位，部分组有不同坐标。现有 `build_ship_tracks.py` 的 MobilityDB 序列要求严格时间顺序；同一时间、不同坐标的两点最小 SQL 复现报错 `Timestamps for temporal value must be increasing`。不能在不制定冲突取舍规则的情况下把这些记录静默合并；本轮未重建 `ship_tracks`、停留或相遇派生表，实查 `ship_tracks=0`、`ship_dwell=0`、`mobility_demo_segments=0`。基于原始 `ship_positions` 的快照、播放窗口与单船轨迹接口已验证，派生分析仍未验证。
- 四艘新闻船的身份关联、整周浏览器操作、并发性能、完整数据库恢复及独立测试库均未验证。数据库内容和仓库提交是两份状态；提交与推送不会复制本机 `aisdb`。
