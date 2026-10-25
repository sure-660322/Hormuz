> 当前入口（2026-10-25第二阶段）：已接入数据库新闻引用与四条中文新闻事件入口，并以灰色虚线示意缺报端点，见[当前说明](case_news_entries.md)及[收尾记录](case_news_closeout_20261025.md)。下文保留第一阶段新增轨迹、当时无新闻入口的实施与验收事实。

# 三艘新增轨迹案例

2026-10-25：**已验证；未提交、未推送、未合入 main、未部署**。负责人 Codex，基线 `98ff673`，独立分支 `codex/three-vessel-cases`、独立工作树 `three-vessel-cases/Hormuz`。预览前端 5187、后端 8007；未修改共享 8000 服务、未合入 main、未推送或部署。

## 范围与契约

沿用中海北冰洋的案例面板、过程/证据页签、完整窗口、单船回放、速度着色、稀疏方向箭头、默认关闭报位点、航速图、退出恢复与约 4.5 秒快速回放；不调整页面结构或数据库结构。当前选择器为中海北冰洋、MRAIKH、TONG LIN WAN、EGRET。ATHE NOVA 从选择器与引导移除，历史代码、API 与数据保留。

新增 `GET /cases/mraikh`、`GET /cases/tong-lin-wan`、`GET /cases/egret`，沿用 MaritimeCaseResponse。按 MMSI + IMO 双标识与 `case/<case-id>/` 批次前缀定位，不按本机 ship_id 固定身份。无数据时 ready=false、时间/ship_id 为空且 stages=[]，禁止回放；不展示其他船代替。

| 案例 | 船名 | MMSI | IMO | 北京时间文件覆盖 |
| --- | --- | --- | --- | --- |
| mraikh | MRAIKH | 228463600 | 9975507 | 2026-06-17 至 06-19 |
| tong-lin-wan | TONG LIN WAN | 477686100 | 9652014 | 2026-06-17 至 06-19 |
| egret | EGRET | 477123100 | 9250490 | 2026-03-25 至 03-26 |

新闻证据由用户后续提供。目前 articles=[]，仅登记 CSV 身份资料；每船只设置“完整观测过程”浏览阶段，不编造首次尝试、折返、通过等业务情节。没有新闻点击入口、自动船舶匹配或新闻真实性结论。

## 本机导入（2026-10-25）

源文件由用户提供，保留桌面原文件，不入 Git：`228463600_20261025133758.csv`、`477686100_20261025133724.csv`、`477123100_20261025133638.csv`。CSV 使用北京时间，Unix 秒转换为带时区 UTC 存库。供应方、授权与完整覆盖尚未核实；沿用 nnu_ais 只是现有轨迹读取链路的技术兼容标识，不能视为供应商已核验。

| 案例 | 原始行 | 接受行 | 隔离行 | UTC 接受范围 | >90分钟空缺 |
| --- | --- | --- | --- | --- | --- |
| mraikh | 19,910 | 19,891 | 19 | 2026-06-16T16:00:15+00:00 至 2026-06-19T15:59:55+00:00 | 1 |
| tong-lin-wan | 7,162 | 7,158 | 4 | 2026-06-16T16:18:14+00:00 至 2026-06-19T15:59:20+00:00 | 5 |
| egret | 206 | 206 | 0 | 2026-03-24T16:31:17+00:00 至 2026-03-26T15:51:18+00:00 | 3 |

MRAIKH 原始第 10908 行航速 102.29 节，超出现有允许范围，整条隔离，不将它改写为合理航速。另有 9 组同秒记录，共 18 行隔离；TONG LIN WAN 有 2 组同秒记录，共 4 行隔离。沿用北冰洋规则，同秒组不任意保留一条（包括完全重复记录）。原始数据与 SHA-256、行号审计均保留。heading/ROT/draught 同步检查有效值。缺报不插值，>90分钟断线，船位有效期仍为此前1小时。

先在独立测试库 `hormuz_three_cases_test_20261025` 从当前三张真实表复制结构（含 PostGIS 生成列、约束、索引），验证真实文件导入、幂等、故障回滚、字段逐条一致，再写入应用库 aisdb。未重放历史演进 SQL，没有结构迁移。应用库完整 custom-format 备份：`data/db_backups/hormuz-before-three-cases-20261025.dump`，365,457,943 字节，已用 pg_restore --list 检查目录；未做全库灾备恢复演练。

应用库一次事务导入 batch 9/10/11，新增 3 艘船（4,462→4,465），接受报位共 27,255 条；本机 ship_id 16077/16078/16079 仅为本轮结果。原批次元数据未改变，未覆盖原报位。默认态势 /simulation/meta 继续排除 case/% 补充批次，不延长默认全量回放日期。

## 复现与安全边界

现有导入器默认仍为北冰洋；新增 --case 仅选择三个固定案例。先只读审计：

```powershell
python -m backend.import_case_ais <本机CSV绝对路径> --case mraikh --report local-archive/mraikh-audit.json
```

完成独立库验证、明确目标且备份后才使用 --apply --database <目标库>。文件哈希幂等、已有 MMSI 的 IMO 冲突、同船时间重叠均按现有规则检查，失败整体回滚。不将 CSV、备份、凭据或本机报告提交 Git。

## 验证记录

2026-10-25：

- 针对性后端：`python -m pytest backend/tests/test_trajectory_cases.py backend/tests/test_arctic_case.py backend/tests/test_athe_nova_case.py backend/tests/test_case_fast_playback.py -q`：提供旧北冰洋私有 CSV 后最终为 23 passed / 1 skipped（初次未指定私有 CSV 时为22/2）；只跳过旧北冰洋指定隔离库集成测试。北冰洋真实文件解析已复验；三船真实文件独立库验证另行执行。
- 新三船独立库实测：导入成功与重复幂等、诱发计数不符后的完整回滚、未入库 ready=false、入库契约、逐条 UTC/坐标/航速/航向/行号/生成 location 对账一致；/health、/docs 成功，轨迹分日成功、空窗0点、>24小时422。独立库默认态势报位数0，案例补充未进入全量态势。
- `npm run build`、`npm run check:workbench`、`git diff --check` 通过；构建保留既有大包提示。
- 独立库证据 `local-archive/isolated-verification.json`；应用库审计与备份哈希 `local-archive/application-import.json`；各文件完整行号、缺口与哈希在 `local-archive/*-audit.json`；均为本机忽略文件。

- 真实浏览器1440×900：四船依次切换、目标案例/源报位数正确、完整播放到末帧；播放期间额外轨迹/快照请求均为0；三船无伪造新闻卡。MRAIKH、TONG LIN WAN、EGRET 与北冰洋的桌面截图均已逐张查看。
- 浏览器内按点击事件到完成提示测时：MRAIKH 4,557 ms、TONG LIN WAN 4,579 ms、EGRET 4,536 ms；均小于5秒。自动化外部计时6.6–7.1秒包含操作框架等待，不将其当成页面实际播放时间；精确测时使用浏览器 performance.now 与 MutationObserver。
- EGRET 390×844证据视图无横向溢出，身份资料与“新闻证据待补充”可见；退出后恢复普通回放速度选择器和进入前2026/02/24 16:05UTC。此窄屏样本不是全设备矩阵验收。
- 上述采样期间 pageerror=[]、HTTP失败=[]。首次加载普通新闻列表有36次封面404（任务预览缺少主目录既有新闻图片目录）；不宣称全程零网络错误，未改变图片配置或新闻数据。证据 `output/playwright/three-cases-results.json`、`playback-timing.json`、四船 `*-finished.png` 与 `egret-mobile-evidence.png`。
- 实际8007接口：/health、/docs、四案例、/simulation/meta均200；普通态势仍17,921,533条、UTC 2026-02-24 16:00 至2026-03-03 15:59:59，新增案例没有延长全量窗口。记录 `local-archive/live-api-verification.json`。

未验证新闻关联、供应商授权、任意新闻自动识别、真实模型问答、全设备与持续并发、公网部署。新闻证据待补充与新闻入口后续实现属于明确后续范围，不阻塞本轮轨迹交付。
