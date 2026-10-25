"""User-supplied trajectory cases; no inferred news or voyage events."""

CASES = {
    "mraikh": dict(name="MRAIKH", mmsi="228463600", imo="9975507", callsign="FMZH", length=300, width=46),
    "tong-lin-wan": dict(name="TONG LIN WAN", mmsi="477686100", imo="9652014", callsign="VRMV5", length=245, width=42),
    "egret": dict(name="EGRET", mmsi="477123100", imo="9250490", callsign="VRVM5", length=183, width=32),
}


def case_prefix(case_id: str) -> str:
    if case_id not in CASES:
        raise ValueError("Unknown trajectory case")
    return f"case/{case_id}/"


def build_case(case_id, db):
    from datetime import timedelta, timezone
    from sqlalchemy import text

    vessel = CASES[case_id]
    rows = db.execute(text("""
        SELECT s.id, min(p.recorded_at) AS start_at, max(p.recorded_at) AS end_at,
               count(p.id) AS position_count
        FROM ships s JOIN ship_positions p ON p.ship_id=s.id
        JOIN ais_import_batches b ON b.id=p.source_batch_id
        WHERE s.mmsi=:mmsi AND s.imo=:imo AND b.source_file LIKE :prefix
        GROUP BY s.id
    """), dict(mmsi=vessel["mmsi"], imo=vessel["imo"], prefix=case_prefix(case_id) + "%")).mappings().all()
    row = rows[0] if len(rows) == 1 else None
    start, end = (row["start_at"], row["end_at"]) if row else (None, None)
    local_zone = timezone(timedelta(hours=8))
    date_label = (f"{start.astimezone(local_zone):%Y.%m.%d} — {end.astimezone(local_zone):%m.%d}" if row else "观测窗口待载入")
    return dict(
        id=case_id, title=f'{vessel["name"]}：历史轨迹', display_title=vessel["name"],
        vessel_label=f'{"LNG运输船（报道分类；CSV原分类为油轮）" if case_id == "mraikh" else "油轮"} · {vessel["name"]}', date_label=date_label,
        overview_summary="对照新闻描述与用户提供的历史 AIS 观测。实线为观测轨迹，虚线仅连接缺报区间两端，不代表实测航线。",
        mmsi=vessel["mmsi"], imo=vessel["imo"], data_source="nnu_ais",
        supplier="用户提供的 CSV；供应方与授权尚未核实", ready=bool(row),
        ship_id=row["id"] if row else None, start_at=start, end_at=end,
        position_count=row["position_count"] if row else 0,
        unavailable_reason="当前库未导入该船的案例轨迹，或船舶身份不一致。",
        stages=[dict(id="observation", title="完整观测过程", date=start.astimezone(local_zone).date(),
                     start_at=start, end_at=end,
                     summary="按原始报位查看航行过程，并与案例级新闻证据对照；虚线仅示意缺报区间。", articles=[])] if row else [],
        evidence=[dict(id=f"{case_id}-identity", kind="identity", stage_ids=[], title="身份与数据资料",
                       summary=f'MMSI {vessel["mmsi"]}、IMO {vessel["imo"]}；报位来自用户提供的CSV。',
                       observation="按 CSV 中的 MMSI 与 IMO 双标识定位目标船；仅展示本案例导入批次。",
                       boundary="CSV 字段不是独立船籍核验或新闻关联证明；供应方与授权尚未核实。")],
        limitations=["新闻入口为人工审阅的精选案例关联，不表示任意新闻均可自动匹配船舶。",
                     "时间窗口来自实际接受报位，阶段仅用于浏览，不表示自动识别的事件时刻。",
                     "超过90分钟缺报分段；虚线仅作端点示意，不产生报位、航速、方向箭头或过航结论，船位有效期仍为此前1小时。",
                     "沿用 nnu_ais 读取链路是技术兼容标识，不代表已核实供应商或再分发授权。"],
    )
