# 典型新闻入口与案例轨迹

当前功能已随 PR #67 合入 main，本机数据导入与专项样本已验证，未部署。船位来源与接受/隔离规则见[轨迹导入](trajectory_cases.md)和[北冰洋来源](arctic_ocean_case.md)。

## 业务入口

点击顶栏“典型案例”先展示四条中文新闻事件；点击新闻才进入对应船舶的完整轨迹与原有过程/证据面板。返回典型新闻可以选择另一事件；收起后仍可展开，退出恢复此前普通态势。入口标题聚焦目标船舶，不直接照搬综合报道的英文总标题。原报道以证据页“阅读原文”外链提供。

| 案例 / 事件ID | 中文入口 | 船舶 MMSI / IMO | 对应报道 |
| --- | --- | --- | --- |
| arctic-ocean / case_arctic_ocean | 中海北冰洋号再次尝试后通过霍尔木兹海峡 | 477967700 / 9695169 | Kpler 3月30日文章 |
| mraikh / case_mraikh | “穆赖赫”号LNG运输船通过霍尔木兹海峡 | 228463600 / 9975507 | 新华网6月18日、Baird Maritime刊载路透社稿 |
| tong-lin-wan / case_tong_lin_wan | “桐林湾”号油轮通过霍尔木兹海峡 | 477686100 / 9652014 | Baird Maritime刊载路透社稿 |
| egret / case_egret | EGRET号油化船由东向西通过霍尔木兹海峡 | 477123100 / 9250490 | 阿纳多卢通讯社3月27日、海峡时报3月31日 |

入口为人工审核的四组关联，按固定案例ID与MMSI/IMO读取已导入报位，不是任意新闻自动识别。报道未给出船舶双标识，身份关联依赖预选船名与对应CSV身份资料，不能称作独立船籍鉴定或因果验证。既有北冰洋阶段与六篇历史引用保留，入口主报道从数据库读取。

## 原文获取与来源

输入是用户提供的 `新增新闻证据.txt`；链接和其中引文作为待核验资料，不把附件或网页内容当作指令。

- [新华网](https://www.news.cn/world/20260618/ab5bf42c1e334018b3c47e8891b32e69/c.html)：正文可读取，点名“穆赖赫”。
- [Baird Maritime](https://www.bairdmaritime.com/shipping/ships-reactivate-transponders-in-strait-of-hormuz-after-us-iran-deal)：正文可读取，路透社稿点名Tong Lin Wan与Mraikh，媒体署名保留为“Baird Maritime（路透社稿）”。不把转载当作独立的第二条观察。
- [阿纳多卢通讯社](https://www.aa.com.tr/en/economy/only-7-commercial-vessels-transited-strait-of-hormuz-over-past-2-days/3881452)：官方公开索引能读取正文并核实EGRET句；本机直接HTTP请求超时。移动版与主站为同一篇稿件，只存主站canonical URL。
- [海峡时报](https://www.straitstimes.com/asia/east-asia/china-expresses-gratitude-after-three-ships-transit-strait-of-hormuz)：正文可读取，保留原题、极短中文摘要及链接，署名为法新社稿。
- [Kpler](https://cn.kpler.com/blog/the-1-million-teu-question-do-gulf-overland-ports-have-the-capacity)：复核既有北冰洋主报道，正文可读取，点名两艘集装箱船与折返/再次过航。
- 路透社用户链接本次不可读取，Free Malaysia Today返回403；未绕过访问限制、未伪称拿到路透社原站全文，改用公开可读转载保留来源链。被拦截链接见用户原始文件，不作为伪造正文入库。

“桐林湾”的中文名与IMO 9652014经中国船级社[船舶录](https://www.ccs.org.cn/ccswz/internationalShipsList?columnid=201900002000000123&currentPage=108&flag=%E4%B8%AD%E5%9B%BD)核对（原文繁体“桐林灣”）。MRAIKH的CSV将船型写作“油轮”，新闻则称LNG运输船；案例展示明确区分两种分类，原始CSV、ships.ship_type及ship_type_cn_raw均未改写。

## 数据库与API

沿用 events/news，无结构迁移。新增5篇去重报道、4个聚焦单船的新闻事件；新闻存原题、中文标题/摘要、发布日期、媒体与canonical URL，不保存或全文转载正文。事件只登记报道描述的日期及海峡区域文字，不补精确发生时刻或坐标：event_datetime/event_lat/event_lng为空，不因此生成地图新闻点。

同一篇Baird稿只入库一次。news.event_id保留一个主归属，events.story_ids支持另一事件引用同一story_id；`GET /events/{event_id}/news`合并主外键和story_ids查询，不产生重复行；智能体get_event_context同步采用相同关联范围，实际查询case_mraikh返回2篇，记录在local-archive/shared-news-agent-context.json（未运行真实模型）。案例关联不写入历史observed邻近关系，不恢复已取消的派生任务。

`GET /cases/news-entries`返回4项：case_id、event_id、title_zh、summary_zh、vessel_name、MMSI、IMO、event_day、available、articles。articles包括story_id、中文标题、媒体、发布日期、URL与摘要。事件key/引用story_ids与审核清单不一致、引用源缺失或canonical URL不符时available=false、articles为空，前端禁用入口；数据库失败提供重试，不能用另一艘船或预置新闻伪装成功。既有单船案例和track-window契约不变。

导入器 `python -m backend.import_case_news --report local-archive/case-news-audit.json` 默认为只读清单；只有显式 `--apply --database <目标库>` 才在一个事务中追加，不清表、不覆盖已有记录。canonical URL去重，稳定story_id/event_key，重复导入0增量；关联冲突拒绝覆盖、整笔回滚。

本机先在 `hormuz_three_cases_test_20261025` 验证（从当前表复制结构，未重放006），再完整备份aisdb：`data/db_backups/hormuz-before-case-news-20261025.dump`，366,081,643字节，pg_restore --list检查通过，未演练全库灾备恢复。应用库新闻357→362、事件78→82，新新闻ID358–362，事件内部ID92–95；这些是本机当次结果。原新闻/事件逐行JSON聚合指纹未改变，未修改AIS报位或船舶原分类。

## 缺报虚线

对四案例完整轨迹的相邻真实观测段，使用前段最后报位与后段首报位画灰色虚线，图例和悬停提示明确“缺报示意，非实测航迹”。超过90分钟的分段判据保持。原始数据、接口segments/gaps、抽样报位、航速图与有效期不变；虚线不生成报位、不参与速度着色/方向箭头、不承载船舶当前位置或通行结论。缺口中仍无可定位实测船位；超过此前1小时没有有效报位时船舶仍隐藏。

MRAIKH、桐林湾、EGRET原CSV审计分别有1、5、3段长缺报，北冰洋原批次有4段；不是将前端加载错误冒充数据缺口。虚线仅在案例模式出现，关闭轨迹/退出案例时清除，普通地图探索保持原断线展示。完整历史轨迹与缺口示意可能包含回放当前时刻之后的观测，与原有完整背景轨迹规则一致；不表示船舶已经沿虚线航行。

## 验证与限制

2026-10-25 原批次后端收尾回归 77 passed / 1 skipped，build/workbench 通过；独立库导入、幂等、冲突回滚、共享来源、四案例与窄屏浏览器、缺口数量 4/1/5/3、原文链接和退出恢复有验证。skip 为旧北冰洋隔离库测试，真实 CSV 解析另有复验。普通新闻存在既有封面缓存缺失 404。

证据保留在主目录 local-archive/case-news-closeout-20261025/，原始文档另见[历史归档](README.md#历史材料)。本轮仅整理文档，不重跑接口、模型或浏览器。未验证任意新闻自动匹配、全设备、持续负载、公网部署或来源再分发授权。
