"""中新网「霍尔木兹」批次一次性导入脚本（2026-02-23 ~ 2026-03-03，67 条）。

只做数据插入与事件归并，不做任何表结构变更。
用法：backend/.venv/Scripts/python.exe _analysis_chinanews/import_chinanews.py [--dry-run]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from datetime import date, datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import select, text  # noqa: E402

from backend.app.database import SessionLocal, engine  # noqa: E402
from backend.app.models import Event, News  # noqa: E402

BATCH_DIR = PROJECT_ROOT / "_analysis_chinanews" / "chinanews_霍尔木兹_20260223-20260303"
JSON_PATH = BATCH_DIR / "chinanews_霍尔木兹_20260223-20260303.json"
IMAGE_TARGET_ROOT = PROJECT_ROOT.parent / "news_raw_data"  # 与 routers/events.py 默认一致

STRAIT = (26.57, 56.25)   # 霍尔木兹海峡参考点
TEHRAN = (35.6892, 51.3890)
BANGKOK = (13.7563, 100.4908)


def dt(y, m, d):
    return datetime(y, m, d, tzinfo=timezone.utc)


# --- 归并方案：JSON 数组下标 -> 现有事件或新事件 slug -----------------------------

EXISTING_ASSIGN = {
    "evt_021": [0],
    "evt_009": [3],
    "evt_011": [5],
    "evt_007": [6, 17, 19, 25, 40, 41, 44, 46, 47, 48, 49, 50, 51, 59],
    "evt_030": [7, 12, 13, 26, 31],
    "evt_024": [8, 43],
    "evt_029": [14, 29, 32],
    "evt_058": [4, 21, 24],
    "evt_028": [27],
    "evt_031": [34],
    "evt_037": [22],
    "evt_012": [57],
    "evt_014": [2, 35, 36, 52, 53, 54, 58, 60, 61],
    "evt_001": [64, 65],
}

# slug, 标题, 摘要, 类型, event_datetime, 时间文本, 地点文本, 区域, (lat,lng,geo_method), 成员下标
NEW_EVENTS = [
    ("china_a_share_oil_stocks_surge",
     "A股油气板块暴涨：三桶油历史首次集体涨停",
     "3月2日至3日，受美以袭击伊朗、霍尔木兹海峡航运受阻影响，A股油气板块连续大涨：中国石油、中国石化、"
     "中国海油3月2日集体涨停，为历史首次，中国石油总市值突破2万亿元；3月3日三桶油再度爆发，石油基金LOF"
     "复牌涨停，多只油气主题ETF涨停，部分基金年内收益超40%。",
     "finance", dt(2026, 3, 2), "2026年3月2日至3日", "中国A股市场", "其他",
     (None, None, None), [15, 16, 20, 23, 28]),
    ("gold_price_war_analysis",
     "冲突下黄金与资产价格展望：避险与通胀双驱动",
     "美以袭击伊朗后黄金、白银与油价联动波动。2月28日白银大涨、黄金创月内新高；市场分析普遍认为金价走向"
     "取决于霍尔木兹海峡局势：伊朗有限报复则金价高位震荡，封锁海峡则黄金成为资金“终极避风港”；3月1日黄金"
     "暗盘价格一度下跌，3月3日分析指出支撑黄金长期牛市的去美元化与央行购金因素未根本改变。",
     "finance", None, "2026年2月28日至3月3日", None, "不明",
     (None, None, None), [10, 45, 55, 56, 62]),
    ("day4_tehran_struck_hezbollah_front",
     "战事第四日：德黑兰凌晨再遭袭、以色列双线打击真主党",
     "3月3日凌晨德黑兰再次遭美以空袭，美方行动规模持续扩大，伊朗称已做好长期战争准备；2日深夜伊朗伊斯兰"
     "革命卫队称霍尔木兹海峡已关闭，将打击所有试图通过的船只；以色列国防军宣布同时打击黎巴嫩和伊朗，在"
     "黎巴嫩南部大规模空袭真主党70个军事目标。",
     "military", dt(2026, 3, 3), "2026年3月3日凌晨", "伊朗德黑兰、黎巴嫩南部", "其他",
     (*TEHRAN, "nominatim"), [18]),
    ("tanker_freight_rate_record",
     "中东冲突推高油轮运费至历史新高：日收益达42.4万美元",
     "受美伊冲突、霍尔木兹海峡航运受阻影响，超大型油轮运费飙升至历史最高水平：波罗的海交易所基准油轮日收益"
     "达42.4万美元；韩国新科航运3月2日报出700个Worldscale点的高价，较2月27日上涨逾三倍。",
     "freight", dt(2026, 3, 3), "2026年3月3日报道", "霍尔木兹海峡及波斯湾航线", "霍尔木兹海峡",
     (*STRAIT, "region_centroid"), [9]),
    ("thailand_halts_oil_exports",
     "泰国暂停石油出口并设立能源紧急情况监测中心",
     "鉴于伊朗关闭霍尔木兹海峡，泰国能源部长阿塔蓬3月1日下令暂停石油出口，责成设立能源紧急情况监测中心，"
     "密切跟踪事态进展，并要求各相关单位评估石油储备数量与价格影响、制定应对预案。",
     "energy", dt(2026, 3, 1), "2026年3月1日（3月2日报道）", "泰国", "其他",
     (*BANGKOK, "nominatim"), [33]),
    ("goldman_europe_gas_130",
     "高盛：霍尔木兹海峡中断一个月欧洲天然气价格或飙升130%",
     "彭博社援引高盛集团3月1日报告称，若霍尔木兹海峡运输停止一个月，欧洲天然气价格可能上涨一倍以上"
     "（约130%）；目前欧洲和亚洲基准价格几乎没有计入与伊朗相关的风险溢价。",
     "finance", dt(2026, 3, 1), "2026年3月1日报告", None, "霍尔木兹海峡",
     (None, None, None), [30]),
    ("japan_economy_hormuz_shock",
     "野村测算：海峡封锁或使日本GDP最多下降0.65%",
     "野村综合研究所经济学家木内登英测算，若霍尔木兹海峡被完全封锁，WTI原油价格将涨至每桶140美元，日本"
     "油价一年内涨超1%；若局势恶化，日本GDP最多可能下降0.65%，甚至陷入衰退。",
     "finance", None, "2026年3月3日报道", None, "不明",
     (None, None, None), [1]),
    ("global_food_crisis_warning",
     "经济学家警告：美以袭击伊朗或引发全球粮食危机",
     "伊朗伊斯兰革命卫队2月28日晚宣布禁止任何船只通过霍尔木兹海峡。黎巴嫩经济学家奥马尔警告：伊朗及其他"
     "海湾国家是全球化石燃料和化肥的重要生产国，石油开采中断或使油价升至每桶120美元，化肥供应链一旦断裂"
     "将推高全球农业生产成本，引发粮食危机。",
     "other", None, "2026年3月1日", None, "不明",
     (None, None, None), [39]),
    ("iran_fm_no_hormuz_blockade",
     "伊朗外长：新最高领袖或一两日内选出、伊朗无意封锁霍尔木兹海峡",
     "3月1日晚，伊朗外长阿拉格齐表示，伊朗新任最高领袖可能在一两天内选出；伊朗目前没有“封锁”霍尔木兹海峡"
     "航道的意图。",
     "diplomacy", dt(2026, 3, 1), "2026年3月1日晚", "伊朗德黑兰", "伊朗沿岸",
     (*TEHRAN, "nominatim"), [37]),
    ("taiwan_evacuation_controversy",
     "台当局称台胞随大陆撤侨“有风险”引争议",
     "3月1日凌晨，中国驻以色列使馆发布通知，开放在以中国公民转移撤离登记，登记对象包括持中国护照及港澳台"
     "相关证件人员。中东战火升级之际，台当局竟称台胞随大陆撤侨“有风险”，引发争议。",
     "diplomacy", dt(2026, 3, 3), "2026年3月3日", None, "其他",
     (None, None, None), [11]),
    ("eu_aspides_extension",
     "欧盟延长“阿斯皮德斯”红海护航行动期限",
     "欧盟2月24日决定延长“阿斯皮德斯”红海护航行动期限。该行动2024年2月发起，总部设在希腊拉里萨市，核心"
     "任务为维护红海及周边海域航行自由，行动范围覆盖曼德海峡附近主要海上交通线，并监控霍尔木兹海峡及红海、"
     "亚丁湾、阿拉伯海、阿曼湾和波斯湾公海海域的海事状况。",
     "military", dt(2026, 2, 24), "2026年2月24日", "红海及曼德海峡", "其他",
     (None, None, None), [66]),
    ("tanker_sunk_hormuz_blockade_run",
     "油轮硬闯霍尔木兹海峡被击中并开始沉没",
     "3月1日，一艘试图通过霍尔木兹海峡的油轮被击中并开始下沉。此前2月28日晚，伊朗伊斯兰革命卫队宣布禁止"
     "任何船只通过霍尔木兹海峡，随着油轮等船只穿行交通停止，该海峡实际上已被关闭。",
     "passage", dt(2026, 3, 1), "2026年3月1日", "霍尔木兹海峡", "霍尔木兹海峡",
     (*STRAIT, "region_centroid"), [42]),
    ("wallet_shock_explainer_video",
     "视频解读：美伊开战如何冲击全球人的钱包",
     "2月28日晚，伊朗宣布禁止船只通过霍尔木兹海峡，每天超2000万桶原油停摆，油价已跳涨8%，专家预警很快"
     "或突破100美元；金价飙升、股市震荡、通胀预期升温，冲突通过能源与金融渠道传导至普通人的生活成本。",
     "finance", None, "2026年3月1日", None, "不明",
     (None, None, None), [38]),
]

UNASSIGNED = [63]  # relevant=false，不挂事件

MEDIA_FALLBACK = {
    "": "中国新闻网",
}
PERSPECTIVE_MAP = [
    ("三里河", "中国评论"),
    ("中新经纬", "中国财经媒体"),
    ("央视新闻", "中国官方媒体"),
]


def perspective_for(media: str) -> str:
    for key, value in PERSPECTIVE_MAP:
        if key in media:
            return value
    return "中国官方媒体"


def story_id_for(canonical_url: str) -> str:
    return hashlib.sha256(canonical_url.encode("utf-8")).hexdigest()


def parse_publish(raw: str) -> date:
    return datetime.strptime(raw.strip(), "%Y-%m-%d %H:%M").date()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    items = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    assert len(items) == 67, f"预期 67 条，实际 {len(items)} 条"

    # 成员下标全覆盖且互不重复
    assigned = [i for members in EXISTING_ASSIGN.values() for i in members]
    assigned += [i for *_, members in NEW_EVENTS for i in members]
    assigned += UNASSIGNED
    assert sorted(assigned) == list(range(67)), "归并方案未覆盖全部 67 条或存在重复"

    for item in items:
        item["media"] = MEDIA_FALLBACK.get(item["media_name"], item["media_name"])
        item["canonical"] = item["canonical_url"] or item["url"]
        item["story_id"] = story_id_for(item["canonical"])
        item["pub_date"] = parse_publish(item["publish_date"])
        item["perspective"] = perspective_for(item["media"])

    # ---------- 图片先落位（封面数据源，幂等） ----------
    copied = 0
    for img in (BATCH_DIR / "images").iterdir():
        if img.is_file():
            target = IMAGE_TARGET_ROOT / "images" / img.name
            if not target.exists():
                shutil.copy2(img, target)
                copied += 1
    print(f"== 图片落位 news_raw_data/images/：新增 {copied} 个文件 ==")

    db = SessionLocal()
    with db.begin():
        existing_events = {e.event_id: e for e in db.scalars(select(Event)).all()}
        existing_story_ids = set(db.scalars(select(News.story_id)).all())
        existing_urls = set(db.scalars(select(News.canonical_url)).all())
        existing_keys = set(db.scalars(select(Event.event_key)).all())
        max_evt_no = db.execute(
            text("select max(cast(substring(event_id from 5) as int)) from events")
        ).scalar()

        # ---------- 预检：唯一性 ----------
        new_story_ids = [it["story_id"] for it in items]
        assert len(set(new_story_ids)) == 67, "新批次内部 story_id 重复"
        dup_story = set(new_story_ids) & existing_story_ids
        dup_url = {it["canonical"] for it in items} & existing_urls
        assert not dup_story, f"story_id 与库内冲突: {dup_story}"
        assert not dup_url, f"canonical_url 与库内冲突: {dup_url}"

        new_evt_ids = [f"evt_{max_evt_no + 1 + k:03d}" for k in range(len(NEW_EVENTS))]
        dup_evt = set(new_evt_ids) & set(existing_events)
        dup_key = {slug for slug, *_ in NEW_EVENTS} & existing_keys
        assert not dup_evt, f"event_id 与库内冲突: {dup_evt}"
        assert not dup_key, f"event_key 与库内冲突: {dup_key}"

        # 事件配图文件可用性（封面走 /events/{id}/cover）
        for slug, *_rest, members in NEW_EVENTS:
            for idx in members:
                p = items[idx]["image_path"]
                if p and not (IMAGE_TARGET_ROOT / p).is_file():
                    print(f"[warn] 事件 {slug} 成员 #{idx} 配图缺失: {p}")

        # ---------- 新建事件 ----------
        slug_to_event: dict[str, Event] = {}
        for k, (slug, title, summary, etype, ev_dt, time_text, loc_text, region,
                (lat, lng, geo_method), members) in enumerate(NEW_EVENTS):
            dates = [items[i]["pub_date"] for i in members]
            cover_idx = next((i for i in members if items[i]["image_path"]), members[0])
            event = Event(
                event_id=new_evt_ids[k],
                event_key=slug,
                title_zh=title,
                summary_zh=summary,
                event_type=etype,
                event_datetime=ev_dt,
                event_time_text=time_text,
                event_location_text=loc_text,
                event_region=region,
                event_lat=lat,
                event_lng=lng,
                mentioned_vessels=[],
                image_url=items[cover_idx]["image_url"] or None,
                image_path=items[cover_idx]["image_path"] or None,
                event_points=None,
                geo_method=geo_method,
                geo_note=None if geo_method else "无 event_location_text",
                coverage_count=len(members),
                perspectives=sorted({items[i]["perspective"] for i in members}),
                story_ids=[items[i]["story_id"] for i in members],
                publish_date_min=min(dates),
                publish_date_max=max(dates),
            )
            db.add(event)
            slug_to_event[slug] = event
        db.flush()

        # ---------- 归并到现有事件 ----------
        evt_pk: dict[str, int] = {slug: e.id for slug, e in slug_to_event.items()}
        for evt_no, members in EXISTING_ASSIGN.items():
            event = existing_events[evt_no]
            story_ids = list(event.story_ids)
            persps = set(event.perspectives)
            dates = [event.publish_date_min, event.publish_date_max]
            for idx in members:
                it = items[idx]
                story_ids.append(it["story_id"])
                persps.add(it["perspective"])
                dates.append(it["pub_date"])
            event.story_ids = story_ids
            event.perspectives = sorted(persps)
            event.coverage_count = len(story_ids)
            event.publish_date_min = min(d for d in dates if d)
            event.publish_date_max = max(d for d in dates if d)
            evt_pk[evt_no] = event.id

        # ---------- 插入新闻 ----------
        idx_to_slug = {i: slug for slug, *_rest, members in NEW_EVENTS for i in members}
        idx_to_evt = {}
        for evt_no, members in EXISTING_ASSIGN.items():
            for i in members:
                idx_to_evt[i] = evt_no

        for idx, item in enumerate(items):
            if idx in UNASSIGNED:
                parent, relevant = None, False
                etype, ev_dt, time_text, loc_text, region, lat, lng = "other", None, None, None, None, None, None
            else:
                evt_no = idx_to_evt.get(idx)
                if evt_no:
                    parent = existing_events[evt_no]
                else:
                    parent = slug_to_event[idx_to_slug[idx]]
                relevant = True
                etype = parent.event_type
                ev_dt, time_text, loc_text, region = (parent.event_datetime,
                                                      parent.event_time_text,
                                                      parent.event_location_text,
                                                      parent.event_region)
                lat, lng = parent.event_lat, parent.event_lng
            db.add(News(
                story_id=item["story_id"],
                source_id=None,
                title=item["title"],
                url=item["url"],
                canonical_url=item["canonical"],
                publish_date=item["pub_date"],
                language=item["language"] or "zh",
                media_name=item["media"],
                perspective=item["perspective"],
                description_en=None,
                enrich_status=1,
                title_zh=item["title_zh"],
                summary_zh=item["summary_zh"],
                event_type=etype,
                event_datetime=ev_dt,
                event_time_text=time_text,
                event_location_text=loc_text,
                event_region=region,
                event_lat=lat,
                event_lng=lng,
                mentioned_vessels=[],
                image_url=item["image_url"] or None,
                image_path=item["image_path"] or None,
                relevant=relevant,
                event_id=None if parent is None else parent.id,
            ))

        print(f"== 预检通过：67 条新闻、{len(NEW_EVENTS)} 个新事件（{new_evt_ids[0]}~{new_evt_ids[-1]}）、"
              f"{len(EXISTING_ASSIGN)} 个现有事件归并 ==")
        for slug, title, *_r, members in NEW_EVENTS:
            print(f"  {slug:38s} {len(members)} 条  {title}")
        for evt_no, members in EXISTING_ASSIGN.items():
            print(f"  {evt_no:38s} +{len(members)} 条")

        if args.dry_run:
            db.rollback()
            print("== dry-run：已回滚，未写入 ==")
            return

    # ---------- 落库后核对 ----------
    with engine.connect() as c:
        print("news 总数:", c.execute(text("select count(*) from news")).scalar(),
              "| events 总数:", c.execute(text("select count(*) from events")).scalar())
        print("新事件明细:", list(c.execute(text(
            "select event_id, event_key, coverage_count, publish_date_min, publish_date_max "
            "from events where event_id >= :e order by event_id"), {"e": new_evt_ids[0]})))
        print("evt_014 现 coverage:", c.execute(text(
            "select coverage_count from events where event_id='evt_014'")).scalar())


if __name__ == "__main__":
    main()
