# ATHE NOVA 报道与AIS对照（Issue #49）

## 范围与身份门槛

2026-10-08，负责人Codex；技能github-issue-workflow 1.0.0，处理模式。基线`33f2b69715be824d4c15a91cf966a149504c9ad2`，任务分支`codex/athe-nova-evidence`。只修改案例API/schema、案例选择与面板、相关测试和文档；不改数据库、依赖、底图或共享服务。实现已完成，验收见下；交付止于PR，未合并、未部署。

当前ships中唯一双标识匹配为ATHE NOVA：MMSI **334931000**、IMO **9188116**；本机ship_id=628仅为此次数据库编号，API不硬编码此ID。呼号HQZT4，库中长度96米、船型未知、旗国为空。[VesselFinder](https://www.vesselfinder.com/vessels/details/9188116)显示相同MMSI/IMO、95.50米、洪都拉斯旗、沥青船；不回写库中缺失属性。该平台是信息资料，不是船籍登记证，当前页面不是3月2日的登记快照。模糊检索athe/athen/athena/nova及历史名OCEAN TOPAZ I、GP ASPHALT III后，其他候选标识不同，不关联。

路透社稿件同时使用Athe Nova/Athen Nova；Anadolu稿件使用Athena Nova但未提供双标识，只作为同一声明的拼写分歧资料，不以名称相似新增船舶绑定。身份对照达到当前案例的双标识门槛，袭击与损伤结论仍有不确定性。

## 报道 / AIS / 不能确认

| 证据 | 报道或观测 | 不能推出 |
| --- | --- | --- |
| [路透社，Al-Monitor刊载](https://www.al-monitor.com/originals/2026/03/fuel-tanker-ablaze-strait-hormuz-after-drone-strike-iran-revolutionary-guards-say)，2026-03-02 | 转述伊朗革命卫队称两架无人机命中并起火；稿件称未能联系船东、管理方未立即评论 | 不是独立确认的精确袭击时间、击沉或军事关联证据 |
| [Anadolu Agency](https://www.aa.com.tr/en/middle-east/iran-s-revolutionary-guard-corps-claims-it-hit-oil-tanker-passing-through-strait-of-hormuz/3847113)，发布03-02，更新03-03 | 使用Athena Nova，转述革命卫队声明 | 两篇转述不等于两次独立现场确认；更新日期不是事件时刻 |
| 02-26 06:35:21Z → 03-01 23:21:28Z | 26.352100N,54.657497E → 26.185335N,54.657187E；相隔319,567秒（88小时46分7秒） | 中间三个日文件存在而目标船无报位；不能确定离开接收范围、停船或主动关闭AIS |
| 03-02 08:16:26Z → 13:12:07Z | 26.525838N,56.398847E → 25.457837N,56.619807E；相隔17,741秒（4小时55分41秒）；03-02.csv来源行1394346/1394347 | 不能将缺口边界当成袭击时刻或补造跨缺口航线 |
| 03-03最后观测15:57:03Z | 报道日之后仍有5,500条该船报位；当前七日来源到03-03结束 | 尾部无数据不是消失/击沉；有报位也不证明没有损伤 |

以上UTC时刻与北京时间相差8小时。面板阶段按北京时间组织，定位按现有回放采样帧；卡片保留精确来源观测时间，不宣称回放帧是精确事件时刻。新闻库检索得到news.id=183/218/276（story_id分别为`0e77806437d48c2982c263ab29fbf988afd76023c8175be7f66a9f489195e0f7`、`87e354ac372764d229e501713230c993d0d4e9701f1bf1467c82c844ee5a4ceb`、`84e97b063b828c043d38f6e1a881e15846c51d143377917f505cd628b503e264`）。这些是加工新闻线索，不用于补造精确事件时间；本案例引用独立原页面，不回写news/events。

## 来源批次与覆盖

本机只读调查：16,086条报位，首次2026-02-25 02:00:49Z，末次2026-03-03 15:57:03Z。来源nnu_ais，以下为2026-10-08本机查询快照，非跨环境常量。

| 文件 / source_batch_id | 目标船报位 | 来源SHA256 |
| --- | ---: | --- |
| 2026-02-25.csv / 1 | 3952 | 20c51da23f8d81c7f00c13a95135f259810839c3701761d99145e547731a7ccf |
| 2026-02-26.csv / 2 | 1069 | 8003b264cfaafb12e3225009bbf8223f97d800ad916cd9c445781ab0ad5fb892 |
| 2026-03-02.csv / 6 | 5565 | 8cd9dacf5d154d56eec0d700679b7924d347cba503b996bf51813f3b7c022ed3 |
| 2026-03-03.csv / 7 | 5500 | e4d9266858a4d8869b9c546f546da10f7d3900d5e851f73adaca3706d5d73b1b |

02-27/02-28/03-01批次分别已有2,748,940/2,809,848/2,108,102条全船报位，目标船没有报位。来源批次存在不证明目标位置全天接收覆盖。当前AIS供应商授权、区域完整性与异常字段质量仍未核实，沿用[七日来源限制](real_ais_seven_day_import.md)，不宣称公开再分发授权。报道仅引用链接和短摘要，无全文/图片复制。印度海军IFC-IOR周报搜索索引提供相同双标识，但PDF直接读取502，本轮未把它作为已核验正文证据。无新增AIS导入，无MobilityDB重建，默认七日范围不变。

可复核只读SQL（先用MMSI/IMO得到实际ship_id，不将628跨环境复用）：

```sql
SELECT id, name, mmsi, imo, callsign, length_m FROM ships
WHERE mmsi = '334931000' OR imo = '9188116';
SELECT p.source_batch_id, b.source_file, b.source_sha256,
       count(*) AS positions, min(p.recorded_at), max(p.recorded_at)
FROM ship_positions p JOIN ships s ON s.id = p.ship_id
LEFT JOIN ais_import_batches b ON b.id = p.source_batch_id
WHERE s.mmsi = '334931000' AND s.imo = '9188116'
GROUP BY p.source_batch_id, b.source_file, b.source_sha256;
WITH ordered AS (
 SELECT p.recorded_at, p.latitude, p.longitude, p.source_row,
        lag(p.recorded_at) OVER (ORDER BY p.recorded_at,p.id) AS previous_at
 FROM ship_positions p JOIN ships s ON s.id=p.ship_id
 WHERE s.mmsi='334931000' AND s.imo='9188116'
)
SELECT * FROM ordered
ORDER BY recorded_at-previous_at DESC NULLS LAST LIMIT 10;
```

## 实现与降级契约

`GET /cases/athe-nova`复用MaritimeCaseResponse，用双标识及七日时间、nnu_ais、日文件批次过滤；不硬编码本机ID或按同名绑定。返回三个浏览阶段、两篇来源和六张证据卡。既有`/cases/arctic-ocean`保留，schema新增可选展示字段/证据列表的默认值；前端保留fetchArcticOceanCase兼容封装。

案例选择器切换目标时停止播放、丢弃旧轨迹与地图动作，并复用已有≤24小时分片、>90分钟断线、航速曲线与阶段回放。切换不覆盖首次进入前保存的态势，退出恢复原时间、视野、选中项及图层。未匹配/未导入时ready=false、窗口为空且说明原因；可读资料但播放禁用。失败可重试或退出，不继续显示上一船的案例时间轴。请求版本防止退出后迟到响应重新进入案例。

## 验证（2026-10-08）

状态：**已验证，待PR整合**，未合并、未部署。

- `python -m pytest backend/tests -q`：394 passed、14 skipped。跳过项包含需显式独立测试库/源CSV的检查，未执行写库测试；针对本案例身份与无数据门槛另有4种情况通过，既有北冰洋解析回归一并覆盖。
- `frontend/`下`npm run build`、`npm run check:workbench`通过；保留既有大bundle警告。`git diff --check`与变更文档相对链接核对通过。
- 本轮实际新后端的`/health`、`/docs`、`/cases/athe-nova`返回200，案例ready=true、ship_id=628、position_count=16086，与只读DB调查一致；前端真实读取现有船位与轨迹，无DB写入。
- Playwright实际浏览器：北冰洋→ATHE NOVA→北冰洋→ATHE NOVA切换，三个阶段与播放/暂停、观测时间定位、来源新页阅读、退出恢复初始`2026/02/24 16:00UTC`通过；ATHE NOVA全窗1817个120秒桶采样点。08:16:26Z/13:12:07Z观测定位到邻近回放帧08:20/13:15UTC，界面卡片保留精确观测时间，回放不是精确事件时间。
- 路由夹具只在浏览器中替换响应：ready=false禁止播放并可读资料；503显示错误，移除夹具后重试加载真实数据；1280×720及390×844/reduced-motion布局、手机面板滚动、无横向溢出通过。操作监听pageerror为空。
- 本机截图为任务目录内`output/playwright/athe-nova-desktop.png`、`athe-nova-mobile.png`，降级记录`output/playwright/issue49-degradation.txt`；其他CLI快照/控制台位于`.playwright-cli/`。三阶段切换新增轨迹请求0、收起再展开与退出后迟到响应隔离记录见`output/playwright/issue49-isolation.txt`。这些本地验收资料不提交Git。
- 控制台存在既有新闻封面404：本工作树没有主目录的忽略封面缓存，卡片降级占位；首次预览在后端启动前有3次502，重载后API正常；503夹具产生预期资源错误。未宣称控制台零资源错误，新案例未发生页面脚本异常。
- 未验证：真实模型问答、数据供应商授权/接收覆盖、历史船籍登记、精确袭击时刻/损伤/军事关联、公开部署与跨环境数据复制。无新增依赖、导入、迁移或派生重建；现有七日范围未变。

交接：仓库sure-660322/Hormuz，Issue #49；负责人Codex，指定整合者未指定。技能1.0.0/处理，基线33f2b69；当前head以关联PR为准。同步README、FRONTEND_WORKBENCH、案例说明、docs索引、agent_integration与agent_development_plan。下一步由指定整合者核验PR当前head后按“收尾”流程合并；本任务不直接操作main。
