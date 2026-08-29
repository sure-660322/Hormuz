"""Clean and manually review the ten-article Media Cloud test batch."""

from __future__ import annotations

import argparse
import html
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REVIEWS: dict[str, dict[str, Any]] = {
    "How Decarbonization Helps Weather Fuel Price Shocks": {
        "summary": "霍尔木兹通航中断推高油气价格，文章讨论企业通过脱碳降低能源价格冲击。",
        "article_type": "business_analysis",
        "relevance": "medium",
        "analysis_role": "context",
        "event_at": "2026-03-13",
        "event_type": ["strait_disruption", "energy_price_impact"],
        "locations": ["Strait of Hormuz", "Persian Gulf"],
        "ais_alignment": "indirect",
        "jebel_ali_alignment": "none",
        "alignment_note": "可作为通航受阻和能源冲击背景，不能单独证明船舶变化。",
        "metrics": ["vessel_count", "ship_type_mix", "speed"],
    },
    "Iran conflict tests Pakistan amid own border clashes as Islamabad touted as venue for US-Tehran talks": {
        "summary": "文章讨论巴基斯坦在伊朗冲突中的外交处境，并提到一艘巴基斯坦油轮通过近乎封锁的霍尔木兹海峡。",
        "article_type": "geopolitical_report",
        "relevance": "medium",
        "analysis_role": "context",
        "event_at": None,
        "event_type": ["negotiated_passage", "energy_supply"],
        "locations": ["Strait of Hormuz", "Pakistan", "Iran"],
        "ais_alignment": "possible",
        "jebel_ali_alignment": "none",
        "alignment_note": "存在具体油轮通行线索，但缺少船名、MMSI和可靠事件日期，只能作辅助材料。",
        "metrics": ["tanker_count", "ship_type_mix"],
        "date_confidence": "low",
    },
    "LIVE UPDATES: Cargo ship struck in Strait of Hormuz as Iran launches drone, missile attacks": {
        "cleaned_title": "Cargo ship hit by projectile north of Jebel Ali",
        "summary": "UKMTO称一艘集装箱船在Jebel Ali以北约35海里处遭不明弹体击中并发生小火，船员安全。",
        "article_type": "live_incident_report",
        "relevance": "high",
        "analysis_role": "primary_event",
        "event_at": "2026-03-12",
        "event_type": ["vessel_attack", "onboard_fire"],
        "locations": ["Jebel Ali", "Dubai", "United Arab Emirates"],
        "ais_alignment": "direct_post_event_only",
        "jebel_ali_alignment": "direct_post_event_only",
        "alignment_note": "空间上最接近现有Jebel Ali数据，但事件早于AIS和穿越数据起点，只能观察事后变化，不能做完整前后对照。",
        "metrics": ["vessel_count", "transit_count", "speed", "cargo_vessel_count"],
    },
    "More than 100 Iranian naval vessels destroyed, and ‘we aren’t done,’ CENTCOM leader says": {
        "summary": "报道美军打击伊朗海军、布雷设施和导弹目标，并讨论以军舰保障霍尔木兹通航。",
        "article_type": "military_report",
        "relevance": "high",
        "analysis_role": "primary_context",
        "event_at": "2026-03-16",
        "event_type": ["military_strike", "mine_threat", "navigation_security"],
        "locations": ["Strait of Hormuz", "Kharg Island", "Iran"],
        "ais_alignment": "indirect_same_period",
        "jebel_ali_alignment": "indirect",
        "alignment_note": "发生在AIS覆盖期内，可检查区域船舶数量和速度是否随后变化，但不是单船或Jebel Ali闸线事件。",
        "metrics": ["vessel_count", "speed", "ship_type_mix"],
    },
    "Iran begins laying mines in Strait of Hormuz, sources say": {
        "cleaned_title": "Iran begins laying mines in the Strait of Hormuz",
        "summary": "报道称伊朗开始在霍尔木兹海峡布雷，构成直接通航风险。",
        "article_type": "security_incident_report",
        "relevance": "high",
        "analysis_role": "primary_event",
        "event_at": "2026-03-10",
        "event_type": ["mine_laying", "navigation_disruption"],
        "locations": ["Strait of Hormuz"],
        "ais_alignment": "direct_post_event_only",
        "jebel_ali_alignment": "indirect_post_event_only",
        "alignment_note": "事件早于AIS起点约4天，可解释数据开始时的低流量或绕航，但无法用现有AIS还原事件前基线。",
        "metrics": ["vessel_count", "speed", "route_change", "ship_type_mix"],
    },
    "Anthony Scaramucci Says Iran's Strait Of Hormuz Closure Is Economic Warfare, Warns Reopening It 'Via Force' Will Drag Conflict Into 'Proxy Hell'": {
        "summary": "文章引用Scaramucci观点，将海峡关闭描述为经济战并讨论油价和供应链风险。",
        "article_type": "commentary",
        "relevance": "low",
        "analysis_role": "exclude_from_event_analysis",
        "event_at": None,
        "event_type": ["commentary", "energy_market"],
        "locations": ["Strait of Hormuz"],
        "ais_alignment": "none",
        "jebel_ali_alignment": "none",
        "alignment_note": "主要是观点，不提供新的可核验海事事件。",
        "metrics": [],
    },
    "Monday Executive News Summary": {
        "summary": "综合新闻摘要提到海峡关闭、布雷和船舶不愿通行，但同时混入大量无关政治内容。",
        "article_type": "news_digest",
        "relevance": "low",
        "analysis_role": "exclude_from_event_analysis",
        "event_at": "2026-03-16",
        "event_type": ["news_summary", "navigation_disruption"],
        "locations": ["Strait of Hormuz"],
        "ais_alignment": "context_only",
        "jebel_ali_alignment": "none",
        "alignment_note": "相关段落可供人工参考，但不是独立原始报道，且正文噪声很大。",
        "metrics": [],
    },
    "Why Gulf states aren’t joining the war against Iran — despite attacks on their soil": {
        "summary": "报道海湾国家面对伊朗袭击仍倾向克制，并提及针对海湾航运和能源设施的多起攻击。",
        "article_type": "regional_policy_report",
        "relevance": "medium",
        "analysis_role": "context",
        "event_at": None,
        "event_type": ["regional_attacks", "diplomatic_response"],
        "locations": ["Persian Gulf", "Strait of Hormuz", "United Arab Emirates"],
        "ais_alignment": "indirect",
        "jebel_ali_alignment": "indirect",
        "alignment_note": "可解释区域风险环境，但没有可与某一条AIS或穿越记录直接匹配的单一事件。",
        "metrics": ["vessel_count", "speed"],
    },
    "Morning Mail: Trump’s fury at reticent Europeans, EVs key to energy security, inside One Nation’s SA surge": {
        "summary": "晨间新闻摘要涉及欧洲拒绝派军舰保护霍尔木兹航道及能源安全，但主体并非海事事件。",
        "article_type": "news_digest",
        "relevance": "low",
        "analysis_role": "exclude_from_event_analysis",
        "event_at": "2026-03-16",
        "event_type": ["diplomatic_response", "energy_market"],
        "locations": ["Strait of Hormuz", "Europe", "Australia"],
        "ais_alignment": "context_only",
        "jebel_ali_alignment": "none",
        "alignment_note": "只能作为国际反应背景，不适合作为船舶变化的事件锚点。",
        "metrics": [],
    },
    "Glimpsing Victory in Iran": {
        "summary": "战略评论评估对伊军事行动，并将水雷、快艇、反舰导弹和无人机列为商业航运威胁。",
        "article_type": "opinion_analysis",
        "relevance": "medium",
        "analysis_role": "context",
        "event_at": "2026-03-16",
        "event_type": ["military_analysis", "navigation_security"],
        "locations": ["Strait of Hormuz", "Iran", "Kharg Island"],
        "ais_alignment": "indirect",
        "jebel_ali_alignment": "none",
        "alignment_note": "可用于解释风险机制，但属于评论分析，不能单独作为已发生事件。",
        "metrics": ["vessel_count", "speed", "route_change"],
    },
}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def normalize_content(value: str) -> str:
    value = html.unescape(value).replace("\u00a0", " ")
    paragraphs = []
    for paragraph in value.split("\n\n"):
        cleaned = re.sub(r"[ \t\r\f\v]+", " ", paragraph).strip()
        if not cleaned:
            continue
        if len(cleaned) < 180 and re.search(r"(?i)subscribe|sign up|newsletter|click here", cleaned):
            continue
        paragraphs.append(cleaned)
    return "\n\n".join(paragraphs)


def date_confidence(candidate_date: str | None, page_date: str | None) -> str:
    if not candidate_date or not page_date:
        return "low"
    match = re.match(r"(\d{4})-(\d{2})-(\d{2})", page_date)
    if not match:
        return "low"
    page_day = datetime.strptime("-".join(match.groups()), "%Y-%m-%d").date()
    candidate_day = datetime.strptime(candidate_date[:10], "%Y-%m-%d").date()
    difference = abs((page_day - candidate_day).days)
    return "high" if difference == 0 else "medium" if difference <= 1 else "low"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    if args.output.exists() and not args.force:
        raise FileExistsError(f"Cleaned output already exists: {args.output}")
    raw_records = read_jsonl(args.raw)
    candidates = {record["url"]: record for record in read_jsonl(args.candidates)}
    if len(raw_records) != 10 or len(candidates) != 10:
        raise ValueError("The test cleaner requires exactly ten raw and ten candidate records")

    cleaned_records = []
    for raw in raw_records:
        candidate = candidates.get(raw["url"])
        if candidate is None:
            raise KeyError(f"Candidate metadata missing for {raw['url']}")
        candidate_title = candidate["title"]
        review = REVIEWS.get(candidate_title)
        if review is None:
            raise KeyError(f"Manual review missing for {candidate_title}")
        cleaned = {
            "id": raw["id"],
            "title": review.get("cleaned_title", candidate_title),
            "source": raw["source"],
            "published_date": candidate.get("published_at"),
            "page_published_at": raw.get("published_at"),
            "date_confidence": review.get(
                "date_confidence",
                date_confidence(candidate.get("published_at"), raw.get("published_at")),
            ),
            "url": raw["url"],
            "canonical_url": raw["canonical_url"],
            "content": normalize_content(raw["content"]),
            "images": raw["images"],
            "language": raw.get("language") or "en",
            "retrieved_at": raw["retrieved_at"],
            "query_source": raw["query_source"],
            "reviewed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            **review,
        }
        cleaned_records.append(cleaned)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    if temporary.exists():
        raise FileExistsError(f"Temporary output already exists: {temporary}")
    with temporary.open("x", encoding="utf-8", newline="\n") as handle:
        for record in cleaned_records:
            handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
    temporary.replace(args.output)
    print(
        json.dumps(
            {
                "records": len(cleaned_records),
                "high": sum(r["relevance"] == "high" for r in cleaned_records),
                "medium": sum(r["relevance"] == "medium" for r in cleaned_records),
                "low": sum(r["relevance"] == "low" for r in cleaned_records),
                "primary_events": sum(r["analysis_role"] == "primary_event" for r in cleaned_records),
                "output": str(args.output),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
