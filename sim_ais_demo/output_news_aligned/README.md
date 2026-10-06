# 新闻对应模拟数据（2026-09-13）

> 2026-09-25：本批次已从本机应用数据库移除，Git 跟踪的船舶、清洗报位、原始报文和隔离报文文件也已删除。2026-10-06 经用户授权，主目录旧模拟备份和重复生成目录已清理；历史报告保留。以下数量和验收结论仅记录 2026-09-13 的历史批次；文内旧复现命令所需完整输入文件已不存在。

历史生成结果：30 艘、9,354 条清洗后船位、9,403 条含模拟异常的原始报文，覆盖 2026-02-26 至 2026-03-04 共七个 UTC 自然日。全部为教学模拟，不是真实 AIS，不对应新闻中的真实涉事船。

## 为什么以等待为主

2月28日[路透报道](https://www.investing.com/news/commodities-news/oil-and-gas-majors-and-traders-suspend-shipments-via-hormuz-as-us-attacks-iran-sources-say-4533427)提到船东及贸易商暂停运输；3月1日[路透报道转载](https://gcaptain.com/tankers-anchored-strait-hormuz-iran-strikes/)提到海峡两侧停船与等待。因此采用两侧待命，不设全体立即返航。具体响应时刻、船数、等待位置与比例都是模拟参数，不能当成统计估计。

- `evt_007` 正文为2月28日晚禁行警告；数据库时间为3月1日00:00 UTC，与正文时分并不一致，按日级锚点使用。警告响应起点设为2月28日15:00 UTC（约伊朗当地18:30），明确属于模拟假设。
- 警告后，海峡两侧船逐步减速，已进入狭窄水域的船先驶离，再待命。连续检查，不允许远处船后来靠近时绕过规则。
- 21 艘穿峡船最终漂航待命；9 艘湾内支线船继续活动，不穿峡。等待点未核实水深，所以低速待命标为“漂航”，不声称是安全锚地。
- `evt_028/065` 袭击、`evt_040` 避行、`evt_049` 保险变化支持持续等待；不虚构袭击或伤亡轨迹。3月5日撤保生效在窗口终点，未提前模拟为已生效。
- 3月3日至4日为“延续等待”的模拟假设，取消旧版无证据的试探复航。未用机场复航报道推导海运复航。

## 新批次验证结果

| 阶段 | 完整穿越次数 |
| --- | ---: |
| 事件前：2月26日–2月28日06:00 UTC | 22 |
| 影响出现：2月28日06:00–3月1日00:00 UTC | 2 |
| 封锁影响：3月1日–3月3日 | 0 |
| 延续等待：3月3日–3月5日 | 0 |

统计跨过56.2°E与56.7°E两条门线的完整穿越，带内多次报位保留状态，不把进入单条门线当成过境。以 `news_alignment_report.json` 为本批次通航验收依据；通用报告中的旧 `strait_throughput` 为旧单线指标，不作完整过境统计。以上各阶段长度不同，次数不能直接当作同口径日均交通量。

文件级验收：0 失败、0 警告；清洗船位落陆地为0，宣告封锁后核心区船位为0。独立按坐标与时间重算9,275对相邻报位（间隔不超过6小时），最大推算航速22.51节；在航相对速度差中位数2.19%。原有不规则报位、异步、缺报、长空窗、定位噪声、异常注入与去重隔离继续保留。最大单日2,130条，低于回放限制。同种子、同配置重复生成的内容摘要一致。

岸线仍为 Natural Earth 1:10m，仅筛查明显陆地相交。没有核实水深、法定航道、船间避碰或实际锚地，不能用于航行安全或碰撞风险分析。零穿越是本教学情景选择，不声称现实完全无任何例外通行。

## 文件与复现

- `ships.jsonl`：船舶静态资料，模拟标识前缀898，船名含SIM V2。
- `positions_by_date/`：可供现有导入器读取的每日船位。
- `raw_observations/`、`quarantine/`、`anomaly_labels.json`：原始报文及异常处理证据。
- `scenario_links.json`：新闻关联、逐船行为、假设和来源。
- `acceptance_report_file_only.json`：独立质量验收。
- `news_alignment_report.json`：完整过境与封锁后待命验证。
- 配置：`../config/news_aligned_config.json`；生成工具：`../tools/generate.py`。

从 `D:\my_project\Hormuz` 执行以下完整命令，可重新生成并验证本批次：

```powershell
.\backend\.venv\Scripts\python.exe .\sim_ais_demo\tools\generate.py --config .\sim_ais_demo\config\news_aligned_config.json --no-db-check --repeat-check
.\backend\.venv\Scripts\python.exe .\sim_ais_demo\tools\verify.py --config .\sim_ais_demo\config\news_aligned_config.json --outdir .\sim_ais_demo\output_news_aligned
.\backend\.venv\Scripts\python.exe .\sim_ais_demo\tools\verify_news_alignment.py
```

**2026-09-13 22:53（北京时间）已完成数据库替换。** 原150艘、58,567条模拟船位已备份后删除，新30艘、9,354条船位已在同一事务插入，并逐条读回核对。65条事件与290条新闻的数量及内容摘要保持不变。MobilityDB试验已重建为10艘、114段、2,740个参与采样点。前后端继续运行于 http://localhost:5174/ 和 http://127.0.0.1:8000/ ，浏览器已验证新船、封锁后待命画面及七个回放分片加载成功，控制台无错误或警告。

旧数据备份：`database_backups/20260913T145301618376Z/`；备份已回读校验并记录摘要。替换记录见 `database_replace_report.json`，接口及页面验证见 `api_startup_report.json`。旧本地生成文件保留作为历史材料，不再参与网页回放。
