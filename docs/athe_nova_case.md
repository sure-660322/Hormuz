# ATHE NOVA 报道与AIS对照（Issue #49）

> 2026-10-23 阶段提示（2026-10-25 已随 PR #66 合入 main，本地已同步）：快速播放时高亮当前经过的航行阶段，保持所选全程/阶段范围，结束显示完成提示。新一轮全程 4,567 ms，三个阶段均出现高亮；未调用真实模型。详见[任务记录](agent_development_plan.md#2026-10-23-地图工具停靠与案例阶段提示)。

> 2026-10-23 回放调整（2026-10-25 已随 PR #66 合入 main）：案例资料就绪后使用本地采样报位，约 4.5 秒播放完整故事或所选阶段；不改变地图探索播放速度。该分支同时扩展轨迹采样点的源航向字段，保留缺报断线与真实时间。最新状态和验证见[任务记录](agent_development_plan.md#2026-10-23-典型案例五秒内快速回放)；下方逐帧快照等待描述为原版本历史记录。

## 范围与身份门槛

2026-10-08，负责人Codex；技能github-issue-workflow 1.0.0，处理模式。基线`33f2b69715be824d4c15a91cf966a149504c9ad2`，任务分支`codex/athe-nova-evidence`。只修改案例API/schema、案例选择与面板、相关测试和文档；不改数据库、依赖、底图或共享服务。实现及验收已完成；[PR #52](https://github.com/sure-660322/Hormuz/pull/52)已于2026-10-08合入main（`39eb3d7`），Issue #49已关闭；本地已同步，任务工作树/分支与预览已清理，未部署。

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

状态：**已验证，已合并**。[PR #52](https://github.com/sure-660322/Hormuz/pull/52)已于2026-10-08合入main（`39eb3d7`），Issue #49已关闭；本地已同步，任务工作树/分支与预览已清理，未部署。

- `python -m pytest backend/tests -q`：394 passed、14 skipped。跳过项包含需显式独立测试库/源CSV的检查，未执行写库测试；针对本案例身份与无数据门槛另有4种情况通过，既有北冰洋解析回归一并覆盖。
- `frontend/`下`npm run build`、`npm run check:workbench`通过；保留既有大bundle警告。`git diff --check`与变更文档相对链接核对通过。
- 本轮实际新后端的`/health`、`/docs`、`/cases/athe-nova`返回200，案例ready=true、ship_id=628、position_count=16086，与只读DB调查一致；前端真实读取现有船位与轨迹，无DB写入。
- Playwright实际浏览器：北冰洋→ATHE NOVA→北冰洋→ATHE NOVA切换，三个阶段与播放/暂停、观测时间定位、来源新页阅读、退出恢复初始`2026/02/24 16:00UTC`通过；ATHE NOVA全窗1817个120秒桶采样点。08:16:26Z/13:12:07Z观测定位到邻近回放帧08:20/13:15UTC，界面卡片保留精确观测时间，回放不是精确事件时间。
- 路由夹具只在浏览器中替换响应：ready=false禁止播放并可读资料；503显示错误，移除夹具后重试加载真实数据；1280×720及390×844/reduced-motion布局、手机面板滚动、无横向溢出通过。操作监听pageerror为空。
- 本机截图为任务目录内`output/playwright/athe-nova-desktop.png`、`athe-nova-mobile.png`，降级记录`output/playwright/issue49-degradation.txt`；其他CLI快照/控制台位于`.playwright-cli/`。三阶段切换新增轨迹请求0、收起再展开与退出后迟到响应隔离记录见`output/playwright/issue49-isolation.txt`。这些本地验收资料不提交Git。
- 控制台存在既有新闻封面404：本工作树没有主目录的忽略封面缓存，卡片降级占位；首次预览在后端启动前有3次502，重载后API正常；503夹具产生预期资源错误。未宣称控制台零资源错误，新案例未发生页面脚本异常。
- 未验证：真实模型问答、数据供应商授权/接收覆盖、历史船籍登记、精确袭击时刻/损伤/军事关联、公开部署与跨环境数据复制。无新增依赖、导入、迁移或派生重建；现有七日范围未变。

交接：仓库sure-660322/Hormuz，Issue #49；负责人/本轮整合者Codex，用户在本聊天授权收尾。技能1.0.0/收尾，基线33f2b69；验收head为`13abafd62966cd112eefc40fe4c64f67b8e39997`，合并commit为`39eb3d7921406b485664f38f3c1b9a7c0f45ba31`。同步README、FRONTEND_WORKBENCH、案例说明、docs索引、agent_integration与agent_development_plan。已核对GitHub当前head、无未解决审查、合并状态与本地祖先关系，并完成串行main同步与本任务清理。

## 2026-10-08 收尾核验

用户授权收尾后，PR head仍为13abafd，覆盖上述同日验收，无代码变化；GitHub无未解决审查/冲突、无配置CI检查项。采用merge commit合并PR #52，Issue #49自动关闭；本地main快进至39eb3d7并核对包含13abafd，再单独同步本段收尾文档。没有重跑业务/模型验收或重查数据库，先前来源与损伤结论限制仍然保留。

任务工作树已通过Codex归档并移除；本地/远端codex/athe-nova-evidence分支已删除。只关闭本任务前端5184、后端8004及Playwright issue49浏览器；原8000和其他工作树保留。原主目录未跟踪output/未改动。

忽略的验收资料已移至主目录`local-archive/issue49-pr52-20261008/`，其中`playwright/`为截图/夹具记录/交接资料，`.playwright-cli/`为快照与控制台；13个文件逐一SHA256核对一致。前文“任务目录内”路径是实现验收时的位置，清理后使用此归档入口。未正式部署，不将合并视为来源授权或伤损结论已核实。

## 2026-10-09 Issue #55 停靠侧栏与阅读视图

负责人 Kimi，模式「处理」，技能 github-issue-workflow 1.0.0；独立分支 `kimi/issue-55`，worktree `Hormuz-worktrees/kimi-issue-55`，基线 `01b3f77`。范围为 `CasePanel.vue`、`App.vue`、`style.css` 案例模式样式；不改案例源事实、数据库、后端契约或地图服务。

实现：案例面板由覆盖地图的长滚动浮层改为停靠左侧栏（340px，320–360 区间内），地图按真实剩余区域计算尺寸（MapView 既有 ResizeObserver 自动 invalidateSize）；「过程 / 证据」页签只改变阅读视图，不改动案例、阶段、时间、播放状态或地图选择，两视图各自保留滚动位置。案名选择器与日期、船舶资料（MMSI/IMO/船型来源/源报位数量/数据范围）置于固定头部，仅内容区滚动；收起保留案例模式并出现带案例名的「展开 ××× 案例栏」入口，退出为明确文字按钮，删除底部重复退出。切换案例回到新案例过程视图与全程概况并清空本地阅读状态（App 侧版本号继续拦截旧响应）。智能体面板与案例栏同屏时自动收起案例栏，保留恢复入口。航速图移入过程视图次级展开区（原生 details，可键盘操作），采样说明保留在图表说明内。证据视图复用当前全案例证据/报道/限制并标明「尚未按阶段关联，不标为本段证据」；全程按钮文案改为「全程」。

2026-10-09 验证（本机应用库只读，5177 预览复用 8000 后端）：

- `npm run build`、`npm run check:workbench`、`git diff --check` 通过；保留既有大 bundle 警告。
- 内置浏览器实测 1280×720：首屏不滚动即可选全程与全部阶段、读当前摘要与必要限制（断线≠停船/消失）、访问播放/查看轨迹/图例/报位点/航速展开；面板 340px、地图 left=340 无横向溢出（docScrollW=1280）。
- 1440×900、1024×800、390×844：无横向溢出；窄屏为底部可收起阅读面板，地图保留上方可见区，页签与退出可达。
- 页签切换不重置业务状态且独立保留滚动位置；左右方向键可在页签间移动焦点并切换；切换案例回过程视图+全程概况，阶段/日期/摘要为新案例内容；选阶段后摘要回到阅读位置、状态反馈留在操作处；收起/展开地图尺寸正确变化；智能体打开时案例栏自动收起并可恢复；退出恢复原态势（地图探索、列表、时间轴）。
- 航速展开/收起与点击曲线定位时间可用；证据视图 6 张证据卡、阶段报道与限制完整；过程交互期间无新增控制台错误、无失败资源。
- 未验证：后端故障/未导入路径本轮未复测（沿用 #49/#43 已验收的 ready=false 与 503 重试 markup，本轮未改动）；真实模型案例内问答未重验；未部署。

状态：**已验证，PR #60 已合入 main（`a500923`），Issue #55 已关闭；本地已同步，任务工作树/分支已清理，未部署**。

### 2026-10-09 收尾核验

用户授权收尾后，核对 PR #60 head 为 `0ce8f9bc5477187c9c17e2aad232bd9a1eb42bd3`（7554bcb 实现 + 文档 PR 链接）、base=main、无未解决审查意见，采用 merge commit 合入为 `a500923`，Issue #55 关闭；本地主目录 fast-forward 至 a500923 并核对任务 head 为祖先。本轮仅文档状态同步与 Git 核验，未重跑业务/模型验收；5177 临时预览已停止，后端 8000 为原主目录服务、未改动。任务 worktree `Hormuz-worktrees/kimi-issue-55`（先移除 node_modules 目录联接）与本地/远端 `kimi/issue-55` 分支已清理。

## 2026-10-09 Issue #56 阶段关联证据视图

负责人 Kimi，模式「处理」，技能 github-issue-workflow 1.0.0；独立分支 `kimi/issue-56`，worktree `Hormuz-issue-56`，基线 `74dcbdc`（#55 合入后 main）。父任务 #53；依赖 #55 的过程/证据视图框架。

实现：证据与阶段建立明确关联，浏览链路为「当前阶段 → 相关证据 → 原始细节/来源/地图观测」。

- 契约最小扩展（不改数据库、不重导入）：`CaseEvidenceResponse` 增加稳定 `id`、`kind`（ais_observation / report / boundary / identity）、`stage_ids`（空 = 适用于整个案例）与 1–2 句 `summary`；`CaseArticleResponse` 增加 `summary`。映射依据：ais_observation 的 `at` 必须落在声明阶段的 start_at/end_at 窗口内（后端测试断言）；报道证据由各阶段文章按 url 去重合成，同一报道不因多阶段引用重复铺开。
- ATHE NOVA 六条证据重新登记：身份对照与「不能确认的结论」为案例级；长缺口前最后报位归 before-report；局部缺口之前/之后与「报道说了什么」归 reported-day。各报道补 1–2 句摘要。
- 证据视图：范围控件「当前阶段 / 全部」，默认跟随当前阶段（全程概况 → 全部），手动切换后保持选择，范围名称常显；按 AIS观测 / 报道 / 结论边界 / 身份与数据资料 分组列表，默认只显示类型、标题、时间/日期、摘要与对应动作；精确坐标、采样说明、身份匹配过程与适用阶段收进单层「展开详情」（按用户要求不展示来源文件与行号，不暴露数据组织形式）；案例级证据标注「适用于整个案例」。无图不画占位块，有图仅在展开详情中作可选辅助并保留失败降级与来源说明；缺失/不安全链接显示「来源链接不可用」，不保留看似可点击的空链接；本阶段无报道时明确提示可查看 AIS 观测或全部证据。
- 过程视图新增「查看相关证据」：切到证据视图、按当前阶段筛选并带到阅读位置；证据视图「返回过程」保留案例/阶段/地图状态。AIS 证据「定位地图」仅在具备明确观测时刻且落在可定位范围时可用：执行时暂停播放、复用 seek 链路，地图以脉冲标记突出观测点（尊重减少动态模式），证据行保持「已定位」反馈；轨迹未导入/加载中/缺报区间/超出覆盖范围分别显示具体原因，不用相邻点冒充定位成功；快速连续点击时 caseVersion 保证最后一次选择生效。
- 报道只有发布日期时不生成任何定位动作；无精确观测时刻的报道证据不提供「定位地图」。

2026-10-09 验证（本机应用库只读；工作树后端 8004 + 前端 5176，Vite 代理指向 8004；主目录 8000/5174 服务未改动）：

- `npm run build`、`npm run check:workbench`（含新增 trackPointAt 定位语义检查）、`git diff --check` 通过；后端 `test_athe_nova_case.py`、`test_arctic_case.py` 11 passed / 2 skipped（新增证据契约断言：id 唯一、kind 合法、stage_ids 指向真实阶段、AIS 时刻落在声明窗口、摘要非空）。
- 内置浏览器实测（DOM 级，面板未渲染无法截图，为本轮限制）：中海北冰洋全程证据视图含报道 6 / 阶段级缺报边界 1 / 身份 1，案例级标注清楚、全部列表无重复；选「两次尝试之间」后当前阶段范围只含该阶段边界 + 案例级身份资料，并提示「本阶段无单独报道」。
- ATHE NOVA「报道当日」当前阶段范围含 AIS 2 / 报道 3（含 curated「报道说了什么」）/ 边界 1 / 身份 1；全部范围 AIS 3，按 url 去重无重复报道；展开详情可见坐标、边界与适用阶段。
- 「定位地图」：暂停播放、seek 生效、地图出现观测点标记；连续快速点击三次，最终「已定位」反馈停留在最后一次点击的行，标记唯一；范围控件手动切「全部」后换阶段仍保持，「查看相关证据」重新按当前阶段筛选。
- 键盘：页签获焦后方向键切换过程/证据视图；1280×720、约 1024、390×844 视口无横向溢出，窄屏为底部阅读面板；减少动态模式下定位标记动画关闭（animation-name: none，静态圆环保留）；图片加载失败时降级为无图并保留来源说明（注入 error 事件实测）；ATHE NOVA 报道无图不渲染占位块。
- 未验证：真实缺报区间内的定位禁用文案未在浏览器复测（现有 curated 观测时刻均为实际报位点；缺报/范围外返回 null 由 workbench 检查覆盖）；后端故障/未导入路径沿用 #49/#43 已验收 markup，本轮未改动；真实模型案例内问答未重验；内置浏览器面板不可见导致无法截图存档；未部署。

状态：**已验证，[PR #61](https://github.com/sure-660322/Hormuz/pull/61) 已合入 main（`4e46299`），Issue #56 已关闭；本地已同步，任务工作树/分支已清理，未部署**.

### 2026-10-10 收尾核验

用户授权收尾后，核对 PR #61 head 为 `e889d96`、base=main（`74dcbdc`）、无未解决审查意见，采用 merge commit 合入为 `4e46299`，Issue #56 关闭；本地主目录 fast-forward 至 `4e46299` 并核对与远端一致。合并后在主目录复核：后端案例契约测试 11 passed / 2 skipped、`npm run build`、`npm run check:workbench` 通过；本轮仅合并与 Git/构建核验，未重跑浏览器验收（实现与 2026-10-09 已验收内容一致）。任务工作树 `Hormuz-issue-56`（先移除 node_modules 目录联接与 .env 硬链接）与本地/远端 `kimi/issue-56` 分支已清理；预览用后端 8004 已停止，主目录 8000/5174 服务未改动。按用户要求，界面证据详情不展示来源文件与行号（commit `e889d96`）。
