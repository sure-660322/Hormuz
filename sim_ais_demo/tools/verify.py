"""Independent acceptance run over an already generated batch.

Reads only the files in the output directory; it never imports the generator and does
not depend on any in-memory state. Model-side numbers (intervals before dropout, land
clamping, injected anomaly counts) are absent by design in this mode and are reported
as "not available in file-only mode" rather than being guessed.

    python tools/verify.py --outdir output
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import acceptance  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="对已生成的批次做独立文件级验收")
    parser.add_argument("--config", default=str(ROOT / "config" / "scenario_config.json"))
    parser.add_argument("--outdir", default=str(ROOT / "output"))
    parser.add_argument("--report", default=None)
    args = parser.parse_args()

    outdir = Path(args.outdir)
    if not (outdir / "ships.jsonl").exists():
        print(f"未找到 {outdir / 'ships.jsonl'}，请先生成数据。")
        return 2

    cfg = json.loads(Path(args.config).read_text(encoding="utf-8"))
    snapshot = ROOT / "reference" / "news_snapshot.json"
    report = acceptance.run_acceptance(
        outdir, cfg, model_stats=None, news_snapshot_available=snapshot.exists()
    )

    labels_path = outdir / "anomaly_labels.json"
    if labels_path.exists():
        labels = json.loads(labels_path.read_text(encoding="utf-8"))
        report["checks"]["anomalies_injected"] = {
            "source": "anomaly_labels.json（生成过程写入的注入记录，文件级验收可读取其计数）",
            "by_type": labels.get("by_type", {}),
            "blackout_windows": len(labels.get("blackout_windows", [])),
            "position_jump_records": len(labels.get("position_jump_records", [])),
            "duplicate_records": len(labels.get("duplicate_records", [])),
        }
        report["checks"]["model_side_statistics"]["note_zh"] = (
            "文件级验收无法取得生成过程中的“缺报前生成间隔”等内存统计，"
            "因此本报告中该部分为空。如需对比，请查看生成时写出的 acceptance_report.json。"
        )

    target = Path(args.report) if args.report else outdir / "acceptance_report_file_only.json"
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    summary = report["summary"]
    print(f"船舶 {summary['ships']}，船位 {summary['positions']}，原始 {summary['raw_records']}，天数 {summary['days']}")
    print(f"失败 {summary['failures']} 项，警告 {summary['warnings']} 项")
    for item in report["failures"]:
        print(f"  [失败] {item}")
    for item in report["warnings"]:
        print(f"  [警告] {item}")
    print(f"报告：{target}")
    return 1 if report["failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
