"""Curated case evidence, kept separate from inferred news events."""
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session
from backend.app.database import get_db
from backend.app.schemas import MaritimeCaseResponse
from backend.app.services import athe_nova_case

router = APIRouter(prefix="/cases", tags=["cases"])


@router.get("/athe-nova", response_model=MaritimeCaseResponse)
def athe_nova(db: Session = Depends(get_db)):
    rows = db.execute(text("""
        SELECT s.id, count(p.id) AS position_count,
               min(p.recorded_at) AS start_at, max(p.recorded_at) AS end_at
        FROM ships s
        LEFT JOIN ship_positions p ON p.ship_id = s.id
            AND p.data_source = :source
            AND p.recorded_at BETWEEN :start AND :end
            AND EXISTS (SELECT 1 FROM ais_import_batches b
                        WHERE b.id = p.source_batch_id
                          AND b.source_file = b.source_day::text || '.csv')
        WHERE s.mmsi = :mmsi AND s.imo = :imo
        GROUP BY s.id
    """), dict(source="nnu_ais", mmsi="334931000", imo="9188116",
                 start="2026-02-24T16:00:00Z", end="2026-03-03T15:59:59Z")).mappings().all()
    row = rows[0] if len(rows) == 1 else None
    ready = bool(row and row["position_count"])
    return dict(id="athe-nova", title="ATHE NOVA：报道与报位的对照",
                display_title="ATHE NOVA", vessel_label="沥青船（平台分类） · ATHE NOVA",
                date_label="2026.02.25 — 03.03",
                overview_summary="先看身份与先前缺报，再对照3月2日报道和当天轨迹，最后核对3月3日仍存在的报位。缺报不补线；不把报道说法当作AIS结论。",
                mmsi="334931000", imo="9188116", data_source="nnu_ais",
                supplier="现有七日AIS批次；供应商授权与覆盖完整性未核实",
                ready=ready, ship_id=row["id"] if row else None,
                start_at=row["start_at"] if ready else None,
                end_at=row["end_at"] if ready else None,
                position_count=row["position_count"] if row else 0,
                unavailable_reason="当前库没有双标识一致的目标船及七日来源报位；可阅读调查证据，不能播放。",
                stages=athe_nova_case.STAGES, evidence=athe_nova_case.EVIDENCE,
                limitations=["证据卡为2026-10-08本机七日来源调查快照，报位数量与可播放范围按当前库查询。",
                             "报道发布日期不是精确事件时刻；阶段按北京时间组织。",
                             "超过90分钟缺报断线，船位仅在此前1小时内有效；不从缺报推断损伤或关闭AIS。",
                             "只用现有七日原始报位，不导入新数据，不重建MobilityDB。",
                             "AIS来源授权、接收覆盖与字段质量仍有待核实；不宣称具备公开再分发授权。"])

STAGES = [
    dict(id="first-attempt", title="首次尝试与折返", date="2026-03-27", start_at="2026-03-26T16:01:33Z", end_at="2026-03-27T15:59:59Z",
         summary="报道记录两船尝试驶离波斯湾后折返。查看当天报位，并与中远海运当日回应对照；折返原因不能仅凭轨迹认定。",
         articles=[dict(title="Chinese ships halt attempt to exit Hormuz despite Iran safe passage assurances",media="路透社（The Economic Times 刊载）",publish_date="2026-03-27",url="https://economictimes.indiatimes.com/news/international/world-news/chinese-ships-halt-attempt-to-exit-hormuz-despite-iran-safe-passage-assurances/articleshow/129849179.cms",
                        summary="报道两艘中国集装箱船尝试驶离波斯湾后折返，尽管伊朗方面称提供安全通行。"),
                   dict(title="两艘集装箱船穿越霍尔木兹海峡？中远海运集运最新回应",media="上海证券报（新浪转载）",publish_date="2026-03-27",url="https://finance.sina.com.cn/wm/2026-03-27/doc-inhsmnzp9465557.shtml",
                        summary="中远海运集运对“两船穿越海峡”消息的回应，与当日折返报道对照阅读。")]),
    dict(id="waiting",title="两次尝试之间",date="2026-03-28",start_at="2026-03-27T16:00:00Z",end_at="2026-03-29T15:59:59Z",
         summary="查看再次过航前的报位。部分时段缺报，轨迹断线表示观测空缺，不能解释为船舶停留或消失。此阶段没有单独的点名报道。",articles=[]),
    dict(id="second-attempt",title="再次尝试并通过",date="2026-03-30",start_at="2026-03-29T16:00:00Z",end_at="2026-03-30T15:59:59Z",
         summary="Kpler 的3月30日文章点名两船，并引用 MarineTraffic 数据确认成功通过。这里展示当天观测轨迹，不预设精确过航时刻。",
         articles=[dict(title="The 1 million TEU question: Do Gulf ports have capacity?",media="Kpler",publish_date="2026-03-30",url="https://cn.kpler.com/blog/the-1-million-teu-question-do-gulf-overland-ports-have-the-capacity",
                        summary="讨论海湾港口陆路承接能力，点名两船并引用 MarineTraffic 数据称3月30日已通过海峡。"),
                   dict(title="三艘中国船舶通过霍尔木兹海峡（图）",media="银柿财经（新浪转载）",publish_date="2026-03-30",url="https://finance.sina.com.cn/stock/marketresearch/2026-03-30/doc-inhsuknu9624238.shtml",
                        summary="报道三艘中国船舶通过霍尔木兹海峡并附现场图。")]),
    dict(id="confirmation",title="后续报道与官方回应",date="2026-03-31",start_at="2026-03-30T16:00:00Z",end_at="2026-03-31T15:59:51Z",
         summary="外交部称近日中方有3艘船舶经协调过航，没有公布船名。与北冰洋号的关联来自点名报道的交叉对照。新闻日期不代表轨迹中的发生时刻。",
         articles=[dict(title="两艘中国巨轮顺利通过霍尔木兹海峡",media="财联社",publish_date="2026-03-31",url="https://www.cls.cn/detail/2330131",
                        summary="报道两艘中国巨轮顺利通过霍尔木兹海峡。"),
                   dict(title="2026年3月31日外交部发言人毛宁主持例行记者会",media="外交部",publish_date="2026-03-31",url="https://www.mfa.gov.cn/wjdt_674879/fyrbt_674889/202603/t20260331_11884120.shtml",
                        summary="外交部例行记者会：近日中方有3艘船舶经协调过航，未公布船名。")]),
]


# Original-page illustrations checked 2026-09-30; they are article evidence,
# not verified portraits of this vessel. No logo/sidebar image is substituted.
ARTICLE_IMAGES = {
    STAGES[0]['articles'][0]['url']: ('https://img.etimg.com/thumb/msid-129849211,width-1200,height-630,imgsize-193652,overlay-economictimes/articleshow.jpg', 'page_cover'),
    STAGES[0]['articles'][1]['url']: ('https://n.sinaimg.cn/spider20260327/151/w554h397/20260327/44e2-9d9fae15e2db8c4974872a2e342a828e.png', 'body_image'),
    STAGES[2]['articles'][0]['url']: ('https://cdn.prod.website-files.com/65059ad784ac02253c62356c/69ca7321fc52142445edddf2_Screenshot%202026-03-30%20at%2013.56.31.webp', 'page_cover'),
    STAGES[2]['articles'][1]['url']: ('https://n.sinaimg.cn/finance/crawl/68/w550h318/20260330/9179-bc28d114fa7475c033ec659a7b8d9567.png', 'body_image'),
}
for stage in STAGES:
    for article in stage['articles']:
        image = ARTICLE_IMAGES.get(article['url'])
        article.update(image_url=image[0] if image else None,
                       image_source_url=article['url'] if image else None,
                       image_kind=image[1] if image else None)


# issue #56：北极案例的证据清单。ais_observation 类型的精确坐标观测在 curated 数据中不存在，
# 观测事实以各阶段摘要与轨迹本身为准；这里只登记身份资料与阶段级缺报边界，不散布无坐标依据的“观测点”。
EVIDENCE = [
    dict(id="arctic-identity", kind="identity", stage_ids=[],
         title="身份与数据来源",
         summary="MMSI 477967700、IMO 9695169；报位来自船讯网补充批次（用户确认）。",
         observation="案例报位来自船讯网来源的 case/arctic-ocean/ 补充批次，按 MMSI 477967700 与 IMO 9695169 双标识定位目标船。",
         boundary="平台属性不是船籍登记证；名称相似本身不是身份依据。"),
    dict(id="arctic-waiting-gap", kind="boundary", stage_ids=["waiting"],
         title="两次尝试之间的缺报",
         summary="03.28–03.29 再次过航前部分时段缺报。",
         observation="“两次尝试之间”阶段的窗口内部分时段没有报位，轨迹断线表示观测空缺。",
         boundary="断线不能解释为船舶停留或消失；阶段日期是浏览窗口，不是精确事件时刻。"),
]


@router.get("/arctic-ocean", response_model=MaritimeCaseResponse)
def arctic_ocean(db: Session = Depends(get_db)):
    row = db.execute(text("""SELECT s.id, min(p.recorded_at) AS start_at,max(p.recorded_at) AS end_at,count(*) AS position_count
      FROM ships s JOIN ship_positions p ON p.ship_id=s.id
      JOIN ais_import_batches b ON b.id=p.source_batch_id
      WHERE s.mmsi='477967700' AND s.imo='9695169' AND b.source_file LIKE 'case/arctic-ocean/%'
      GROUP BY s.id""")).mappings().first()
    return dict(id="arctic-ocean",title="中海北冰洋：两次过航尝试",mmsi="477967700",imo="9695169",
                data_source="nnu_ais",supplier="船讯网（用户确认）",ready=bool(row),
                ship_id=row["id"] if row else None,start_at=row["start_at"] if row else None,
                end_at=row["end_at"] if row else None,position_count=row["position_count"] if row else 0,
                stages=STAGES, evidence=EVIDENCE, limitations=["阶段窗口按北京时间日界线划分，不是自动识别的折返或通行时刻。",
                    "同秒冲突两条报位隔离；超过90分钟的报位间隔断线；船位仅在此前1小时内有效。",
                    "中文报道与追踪平台的时间表述存在差异，精确过航时刻尚未独立核定。",
                    "案例报道以独立引用保存，不补造新闻发生位置，不据空间邻近建立因果。"])
