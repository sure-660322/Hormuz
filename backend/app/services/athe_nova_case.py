"""Curated, dated evidence; no inferred attack time or AIS disappearance."""

IDENTITY_URL = "https://www.vesselfinder.com/vessels/details/9188116"
REUTERS_URL = "https://www.al-monitor.com/originals/2026/03/fuel-tanker-ablaze-strait-hormuz-after-drone-strike-iran-revolutionary-guards-say"
AA_URL = "https://www.aa.com.tr/en/middle-east/iran-s-revolutionary-guard-corps-claims-it-hit-oil-tanker-passing-through-strait-of-hormuz/3847113"

STAGES = [
    dict(id="before-report", title="先前观测与长缺口", date="2026-02-25",
         start_at="2026-02-25T02:00:49Z", end_at="2026-03-01T15:59:59Z",
         summary="2月25—26日有报位，此后至3月2日北京时间07:21恢复观测。2月27—3月1日文件存在，目标船没有报位；这不是整批文件结束，也不能证明停船或关闭AIS。", articles=[]),
    dict(id="reported-day", title="报道当日与局部缺报", date="2026-03-02",
         start_at="2026-03-01T16:00:00Z", end_at="2026-03-02T15:59:59Z",
         summary="路透社转述伊朗革命卫队关于两架无人机及起火的说法，并指出船东未能联系、管理方未立即评论。当天16:16—21:12北京时间存在约4小时56分缺报。报道没有给出可独立确认的精确袭击时刻，不能把缺口端点当成袭击时间。",
         articles=[dict(title="Fuel tanker ablaze in Strait of Hormuz after drone strike, Iran Revolutionary Guards say", media="路透社（Al-Monitor 刊载）", publish_date="2026-03-02", url=REUTERS_URL,
                        summary="转述伊朗革命卫队说法：两架无人机袭击后油轮起火；船东未能联系，管理方未立即评论。"),
                   dict(title="Iran’s Revolutionary Guard Corps claims it hit oil tanker passing through Strait of Hormuz", media="Anadolu Agency", publish_date="2026-03-02", url=AA_URL,
                        summary="转述同一方声明称击中过航油轮；使用 Athena Nova 拼写，无独立现场细节。")]),
    dict(id="after-report", title="后续报位与范围结束", date="2026-03-03",
         start_at="2026-03-02T16:00:00Z", end_at="2026-03-03T15:57:03Z",
         summary="3月3日仍有5,500条目标船报位，最后一条为北京时间23:57:03。七日来源批次到这一天结束，不能把尾部无数据解释为被击沉或关闭AIS；有后续报位也不能据此排除损伤。", articles=[]),
]

# issue #56：每条证据有稳定 id、明确类型与适用范围（stage_ids 为空 = 适用于整个案例）。
# 映射依据：ais_observation 的 at 落在对应阶段的 start_at/end_at 窗口内；
# report 对应阶段报道；boundary/identity 为案例级资料，不按阶段切分。
EVIDENCE = [
    dict(id="athe-identity", kind="identity", stage_ids=[],
         title="身份对照（2026-10-08核对）",
         summary="库中 MMSI/IMO 与 VesselFinder 一致；新闻里的拼写差异不是身份依据。",
         observation="库中ATHE NOVA与VesselFinder的MMSI 334931000、IMO 9188116一致；库中长度96米，平台95.50米。",
         boundary="双标识匹配；新闻出现Athen Nova或Athena Nova的拼写差异，名称相似本身不是身份依据。平台属性不是船籍登记证。", url=IDENTITY_URL),
    dict(id="athe-gap-last-fix", kind="ais_observation", stage_ids=["before-report"],
         title="长缺口前最后报位",
         summary="02.26 06:35 UTC 最后观测；此后约88小时46分缺报。",
         at="2026-02-26T06:35:21Z",
         observation="26.352100°N, 54.657497°E。",
         boundary="至3月2日07:21:28北京时间才恢复观测，约88小时46分缺报；中间文件存在，不补线。"),
    dict(id="athe-local-gap-before", kind="ais_observation", stage_ids=["reported-day"],
         title="局部缺口之前",
         summary="03.02 08:16 UTC 局部缺口前的最后报位。",
         at="2026-03-02T08:16:26Z",
         observation="26.525838°N, 56.398847°E。",
         boundary="报位只证明此时此处的观测，不证明遇袭。"),
    dict(id="athe-local-gap-after", kind="ais_observation", stage_ids=["reported-day"],
         title="局部缺口之后",
         summary="03.02 13:12 UTC 局部缺口后恢复报位，相隔约4小时56分。",
         at="2026-03-02T13:12:07Z",
         observation="25.457837°N, 56.619807°E。",
         boundary="相隔4小时55分41秒；航迹断线不能确定缺报原因。"),
    dict(id="athe-report-summary", kind="report", stage_ids=["reported-day"],
         title="报道说了什么",
         summary="3月2日路透社与Anadolu转述同一方起火说法，无精确袭击时刻。",
         observation="3月2日路透社转述起火说法；Anadolu使用Athena Nova拼写并转述同一方声明。",
         boundary="两篇转述不等于两份独立现场证据；无精确袭击时刻，不定位成当天00:00。", url=REUTERS_URL),
    dict(id="athe-uncertain", kind="boundary", stage_ids=[],
         title="不能确认的结论",
         summary="缺口原因、停船、主动关闭AIS、伤亡等均不能确认。",
         observation="当前批次仍含3月3日报位；供应商授权与区域覆盖完整性尚未核实。",
         boundary="不能确认被击沉、停船、主动关闭AIS、缺口原因、伤亡或报道所称军事关联。仅链接来源和摘要，不复制全文或图片。"),
]
