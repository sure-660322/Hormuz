"""只读验证：backend/app/services/agent/strait_passages.py 的 query_strait_passages。

预期值来自 sim_ais_demo/output_news_aligned 批次的文件级参考实现
（sim_ais_demo/tools/verify_news_alignment.py 的同一判定口径，实测该批次
完整穿越完成时间共 24 条），并与 news_alignment_report.json 的验收结论对照。

从仓库根目录运行：
    backend/.venv/Scripts/python.exe scripts/verify_strait_passages.py
"""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.database import SessionLocal
from backend.app.services.agent.config import DEFAULT_CLOSURE_AT
from backend.app.services.agent.strait_passages import query_strait_passages

ROOT = Path(__file__).resolve().parents[1]
REPORT = json.loads(
    (ROOT / "sim_ais_demo/output_news_aligned/news_alignment_report.json").read_text(
        encoding="utf-8"
    )
)

# 文件级参考实现实测的该批次穿越完成时间（temp_ship_id 口径，仅用于按窗口计数）
COMPLETIONS_UTC = [
    "2026-02-26T11:17:38+00:00",
    "2026-02-26T17:00:17+00:00",
    "2026-02-26T19:33:32+00:00",
    "2026-02-26T21:25:23+00:00",
    "2026-02-27T02:49:26+00:00",
    "2026-02-27T02:53:27+00:00",
    "2026-02-27T04:22:13+00:00",
    "2026-02-27T04:53:30+00:00",
    "2026-02-27T05:49:11+00:00",
    "2026-02-27T06:10:08+00:00",
    "2026-02-27T06:15:37+00:00",
    "2026-02-27T06:29:49+00:00",
    "2026-02-27T06:41:26+00:00",
    "2026-02-27T09:07:48+00:00",
    "2026-02-27T09:17:57+00:00",
    "2026-02-27T09:51:23+00:00",
    "2026-02-27T10:15:21+00:00",
    "2026-02-27T11:50:54+00:00",
    "2026-02-27T11:55:21+00:00",
    "2026-02-27T16:09:01+00:00",
    "2026-02-27T19:07:50+00:00",
    "2026-02-28T00:18:08+00:00",
    "2026-02-28T09:40:32+00:00",
    "2026-02-28T18:14:54+00:00",
]
COMPLETIONS = [datetime.fromisoformat(stamp) for stamp in COMPLETIONS_UTC]


def file_reference_count(closure_at: datetime, end_at: datetime) -> int:
    """文件级参考实现在 [closure_at, end_at) 内的穿越完成数。"""
    return sum(1 for t in COMPLETIONS if closure_at <= t < end_at)


failures = []


def run_case(title, closure_at, end_at, expected_passages, extra_checks=None):
    print(f"\n=== {title} ===")
    print(f"输入: closure_at={closure_at.isoformat()}  end_at={end_at.isoformat()}")
    with SessionLocal() as db:
        result = query_strait_passages(db, closure_at, end_at)
    summary = result.query_summary
    print(
        "结果: "
        f"status={result.status} "
        f"matched_ships={summary.matched_ship_count} "
        f"passages={summary.passage_count} "
        f"uncertain={summary.uncertain_candidate_count} "
        f"positions_read={summary.position_count} "
        f"coverage={summary.coverage_start} .. {summary.coverage_end}"
    )
    for item in result.evidence:
        print(
            f"  [{item.evidence_id}] ship={item.ship_id}({item.direction}) "
            f"start={item.start_fix.recorded_at} "
            f"completed={item.observed_completion_at} "
            f"lon={item.completion_fix.longitude:.3f} lat={item.completion_fix.latitude:.3f}"
        )
    for item in result.uncertain_candidates:
        print(f"  [{item.evidence_id}] UNCERTAIN ship={item.ship_id} reason={item.uncertain_reason}")
    for note in result.limitations:
        print(f"  limitation: {note}")

    ok = True
    if summary.passage_count != expected_passages:
        ok = False
        failures.append(f"{title}: 通行数 {summary.passage_count} != 预期 {expected_passages}")
    if summary.matched_ship_count != len({e.ship_id for e in result.evidence}):
        ok = False
        failures.append(f"{title}: 船只数未按 ship_id 去重")
    if extra_checks:
        try:
            extra_checks(result)
        except AssertionError as exc:
            ok = False
            failures.append(f"{title}: {exc}")
    print(f"断言: {'PASS' if ok else 'FAIL'}（预期通行数={expected_passages}）")
    return result


def expect_value_error(title, closure_at, end_at, keyword):
    print(f"\n=== {title} ===")
    try:
        with SessionLocal() as db:
            query_strait_passages(db, closure_at, end_at)
    except ValueError as exc:
        assert keyword in str(exc), f"错误消息缺少关键词 {keyword}: {exc}"
        print(f"PASS: 抛出 ValueError: {exc}")
        return
    failures.append(f"{title}: 未抛出 ValueError")
    print("FAIL: 未抛出 ValueError")


def main():
    announced_closure = datetime(2026, 3, 1, 0, 0, 0, tzinfo=timezone.utc)

    # 场景 1：默认封锁时刻（警告响应起点 02-28 15:00Z）起 24h
    # 口径说明：news_alignment_report 的「封锁后零穿越」以宣告锚点 03-01T00:00Z 判定；
    # 以警告响应起点 15:00Z 为 closure_at 时，02-28T18:14:54 有一次警告后完成的穿越，
    # 属「封锁前进入、封锁后完成也计入」的契约行为。
    def check_default_window(r):
        assert r.status == "ok", f"status={r.status}"
        assert not r.uncertain_candidates, "无不确定候选时不应为 partial"
        assert r.query_summary.uncertain_candidate_count == 0
        assert r.ships[0].name.startswith("SIM V2")
        assert all(e.direction == "west_to_east" for e in r.evidence)

    run_case(
        "场景1 默认封锁时刻（警告响应起点）+24h",
        DEFAULT_CLOSURE_AT,
        DEFAULT_CLOSURE_AT + timedelta(hours=24),
        file_reference_count(
            DEFAULT_CLOSURE_AT, DEFAULT_CLOSURE_AT + timedelta(hours=24)
        ),
        extra_checks=check_default_window,
    )

    # 场景 2：宣告封锁锚点 03-01T00:00Z 起 24h → 零穿越（对照 news_alignment_report）
    assert REPORT["post_closure_completed_crossings"] == []
    assert REPORT["completed_crossings_by_phase"]["P2_peak"] == 0

    def check_zero(r):
        assert r.status == "ok", "有窗口报位时零匹配应为有效结果 ok"
        assert r.ships == [] and r.evidence == [], "零匹配时 ships/evidence 应为空"

    run_case(
        "场景2 宣告封锁锚点（03-01T00:00Z）+24h，对照验收零穿越",
        announced_closure,
        announced_closure + timedelta(hours=24),
        0,
        extra_checks=check_zero,
    )

    # 场景 3：封锁前自然日 02-27 全天 → 与文件参考实现一致
    day = datetime(2026, 2, 27, tzinfo=timezone.utc)

    def check_preclosure_day(r):
        assert r.status == "ok", f"status={r.status}"

    run_case(
        "场景3 封锁前自然日 2026-02-27 全天",
        day,
        day + timedelta(hours=24),
        file_reference_count(day, day + timedelta(hours=24)),
        extra_checks=check_preclosure_day,
    )

    # 场景 4：数据首日 02-26 全天
    first_day = datetime(2026, 2, 26, tzinfo=timezone.utc)
    run_case(
        "场景4 批次首日 2026-02-26 全天",
        first_day,
        first_day + timedelta(hours=24),
        file_reference_count(first_day, first_day + timedelta(hours=24)),
    )

    # 场景 5：边界 —— 完成时刻恰等于 closure_at 计入；晚 1 秒不计入
    completion = datetime.fromisoformat("2026-02-28T18:14:54+00:00")
    run_case(
        "场景5a 边界：closure_at 恰等于穿越完成时刻（含）",
        completion,
        completion + timedelta(hours=24),
        1,
    )
    run_case(
        "场景5b 边界：closure_at 比穿越完成时刻晚 1 秒",
        completion + timedelta(seconds=1),
        completion + timedelta(seconds=1) + timedelta(hours=24),
        0,
    )

    # 场景 6：数据范围外的窗口 → 覆盖不足（no_data），不能解释成零匹配
    def check_no_data(r):
        assert r.status == "no_data", f"应为 no_data，实际 {r.status}"
        assert not r.uncertain_candidates, "无报位时不应产生不确定候选"
        assert r.query_summary.position_count == 0
        assert r.ships == [] and r.evidence == []

    before_batch = datetime(2026, 1, 10, tzinfo=timezone.utc)
    run_case(
        "场景6 数据范围外窗口（2026-01-10 全天）",
        before_batch,
        before_batch + timedelta(hours=24),
        0,
        extra_checks=check_no_data,
    )

    # 场景 7：参数校验
    naive = datetime(2026, 2, 28, 15, 0, 0)
    aware = DEFAULT_CLOSURE_AT
    expect_value_error("场景7a naive closure_at 拒绝", naive, aware + timedelta(hours=1), "时区")
    expect_value_error("场景7b naive end_at 拒绝", aware, naive + timedelta(hours=1), "时区")
    expect_value_error(
        "场景7c 窗口超 24h 拒绝",
        aware,
        aware + timedelta(hours=24, seconds=1),
        "24 小时",
    )
    expect_value_error(
        "场景7d end_at 不晚于 closure_at 拒绝",
        aware,
        aware,
        "早于",
    )

    # 汇总：批次级对照（P0/P1 阶段穿越数 vs news_alignment_report）
    print("\n=== 批次级对照（文件验收报告口径）===")
    counts = REPORT["completed_crossings_by_phase"]
    p0 = file_reference_count(
        datetime(2026, 2, 26, tzinfo=timezone.utc),
        datetime(2026, 2, 28, 6, 0, tzinfo=timezone.utc),
    )
    p1 = file_reference_count(
        datetime(2026, 2, 28, 6, 0, tzinfo=timezone.utc),
        datetime(2026, 3, 1, 0, 0, tzinfo=timezone.utc),
    )
    print(f"P0_pre_incident: 文件参考={p0} 报告={counts['P0_pre_incident']}")
    print(f"P1_onset:        文件参考={p1} 报告={counts['P1_onset']}")
    if p0 != counts["P0_pre_incident"] or p1 != counts["P1_onset"]:
        failures.append("批次级阶段计数与 news_alignment_report 不一致")
    print(f"全程穿越总数: 文件参考={len(COMPLETIONS)}（数据库读取范围实测见各场景）")

    print("\n=== 汇总 ===")
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        raise SystemExit(1)
    print("PASS: 全部场景通过")


if __name__ == "__main__":
    main()
