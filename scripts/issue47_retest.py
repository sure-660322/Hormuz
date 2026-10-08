"""Issue #47 定向复测：恢复默认区域追问 + 组 3 并列分析与证据轨迹。"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from issue47_demos import analyze, summarize  # noqa: E402

OUT_DIR = Path(__file__).resolve().parent.parent / "output" / "issue47"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://localhost:8033")
    args = parser.parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    transcript: list[dict] = []

    custom_area = {"west": 56.2, "south": 26.1, "east": 56.7, "north": 26.7, "area_id": "custom", "label": "用户圈选矩形A"}
    history: list[dict] = []

    def ask(q, extra=None):
        run = analyze(args.base, q, history, extra)
        print(summarize(run))
        resp = run["response"]
        if resp.get("answer"):
            history.append({"role": "user", "content": q})
            history.append({"role": "assistant", "content": resp["answer"]})
        return run

    print("=== 复测：圈选区比较 → 恢复默认区域再比较 ===")
    runs = [
        ask("比较 2026-02-26 和 2026-02-28 两天这个区域内的船只活动", {"area_context": custom_area}),
        ask("恢复默认区域，再比较同样的两天"),
    ]
    transcript.append({"group": "retest-restore-default", "runs": runs})

    print("=== 组 3：通行与区域并列分析 + 证据单船轨迹 ===")
    history = []
    runs = [
        ask("2026-02-28 这一天，油轮通过海峡的情况和默认分析区域的活动情况分别是什么样的？"),
        ask("把刚才通过海峡的一艘油轮的轨迹在地图上显示出来"),
    ]
    transcript.append({"group": 3, "runs": runs})

    path = OUT_DIR / f"{stamp}_retest.json"
    path.write_text(json.dumps(transcript, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[saved] {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
