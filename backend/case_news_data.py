"""Reviewed summaries and explicit case associations, verified 2026-10-25.

Original bodies are read for verification, not republished or stored as full text.
One original story can support several vessel-focused events via story_ids.
"""
from hashlib import sha256

ARTICLES = {
    "xinhua": dict(
        url="https://www.news.cn/world/20260618/ab5bf42c1e334018b3c47e8891b32e69/c.html",
        title="通过霍尔木兹海峡的油轮和LNG运输船增多",
        title_zh="通过霍尔木兹海峡的油轮和LNG运输船增多",
        summary_zh="新华网6月18日报道，追踪数据显示LNG运输船“穆赖赫”号当日通过海峡，计划驶往巴基斯坦加西姆港。",
        date="2026-06-18", language="zh", media="新华网", perspective="中国官方媒体",
        vessels=["MRAIKH", "穆赖赫"], primary_case="mraikh"),
    "baird": dict(
        url="https://www.bairdmaritime.com/shipping/ships-reactivate-transponders-in-strait-of-hormuz-after-us-iran-deal",
        title="Ships reactivate transponders in Strait of Hormuz after US-Iran deal",
        title_zh="美伊协议后，船舶恢复发送霍尔木兹海峡航行报位",
        summary_zh="Baird Maritime刊载的路透社稿援引LSEG数据，称桐林湾号于6月18日通过海峡；文章也点名MRAIKH，援引LSEG和Kpler数据称其同日过航。",
        date="2026-06-18", language="en", media="Baird Maritime（路透社稿）", perspective="国际航运媒体",
        vessels=["TONG LIN WAN", "MRAIKH", "YE CHI"], primary_case="tong-lin-wan"),
    "anadolu": dict(
        url="https://www.aa.com.tr/en/economy/only-7-commercial-vessels-transited-strait-of-hormuz-over-past-2-days/3881452",
        title="Only 7 commercial vessels transited Strait of Hormuz over past 2 days",
        title_zh="过去两天仅七艘商船通过霍尔木兹海峡",
        summary_zh="阿纳多卢通讯社3月27日报道，油化船EGRET与SAVONA于3月25日空载由东向西通过海峡。文中航运情况援引MarineTraffic数据。",
        date="2026-03-27", language="en", media="阿纳多卢通讯社", perspective="国际通讯社",
        vessels=["EGRET", "SAVONA"], primary_case="egret"),
    "straits": dict(
        url="https://www.straitstimes.com/asia/east-asia/china-expresses-gratitude-after-three-ships-transit-strait-of-hormuz",
        title="China expresses ‘gratitude’ after three ships transit Strait of Hormuz",
        title_zh="三船过航获致谢", summary_zh="提及EGRET。",
        date="2026-03-31", language="en", media="海峡时报（法新社稿）", perspective="国际媒体",
        vessels=["EGRET"], primary_case="egret"),
    "kpler": dict(
        url="https://cn.kpler.com/blog/the-1-million-teu-question-do-gulf-overland-ports-have-the-capacity",
        title="The 1 million TEU question: Do Gulf ports have capacity?",
        title_zh="百万标准箱之问：海湾港口能否承接陆路转运需求",
        summary_zh="Kpler于3月30日点名中海北冰洋号与中海印度洋号，称两船此前折返后，已于当日通过霍尔木兹海峡，文中引用MarineTraffic数据。",
        date="2026-03-30", language="en", media="Kpler", perspective="航运数据机构",
        vessels=["CSCL ARCTIC OCEAN", "CSCL INDIAN OCEAN"], primary_case="arctic-ocean"),
}

CASE_NEWS = {
    "arctic-ocean": dict(
        event_id="case_arctic_ocean", mmsi="477967700", imo="9695169", name="中海北冰洋",
        title="中海北冰洋号再次尝试后通过霍尔木兹海峡",
        summary="Kpler报道，中海北冰洋号此前尝试后折返，3月30日再次过航。点击对照该船五日AIS观测与已有阶段证据。",
        event_day="2026-03-30", primary="kpler", sources=["kpler"]),
    "mraikh": dict(
        event_id="case_mraikh", mmsi="228463600", imo="9975507", name="穆赖赫（MRAIKH）",
        title="“穆赖赫”号LNG运输船通过霍尔木兹海峡",
        summary="新华网6月18日报道“穆赖赫”号通过海峡；路透社转载稿点名MRAIKH。点击查看6月17—19日AIS观测过程。",
        event_day="2026-06-18", primary="xinhua", sources=["xinhua", "baird"]),
    "tong-lin-wan": dict(
        event_id="case_tong_lin_wan", mmsi="477686100", imo="9652014", name="桐林湾（TONG LIN WAN）",
        title="“桐林湾”号油轮通过霍尔木兹海峡",
        summary="路透社转载稿援引LSEG数据，称此前滞留海湾的桐林湾号于6月18日通过海峡。点击查看该船对应时段的AIS观测。",
        event_day="2026-06-18", primary="baird", sources=["baird"]),
    "egret": dict(
        event_id="case_egret", mmsi="477123100", imo="9250490", name="EGRET",
        title="EGRET号油化船由东向西通过霍尔木兹海峡",
        summary="阿纳多卢通讯社报道EGRET于3月25日空载由东向西过航。点击查看3月25—26日AIS轨迹；缺报区间用虚线示意。",
        event_day="2026-03-25", primary="anadolu", sources=["anadolu", "straits"]),
}


def story_id(source):
    return sha256(ARTICLES[source]["url"].encode()).hexdigest()


def event_key(case_id):
    return sha256(f"curated-news-case:{case_id}".encode()).hexdigest()
