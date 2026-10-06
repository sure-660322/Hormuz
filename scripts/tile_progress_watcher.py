"""瓦片下载进度监视器：每 10 秒统计 tiles/ 目录，重写 progress.html。

浏览器打开 progress.html 即可直观查看下载进度（页面每 8 秒自动刷新）。

用法：
    python scripts/tile_progress_watcher.py

停止：结束 pythonw 进程或 Ctrl+C（前台运行时）。
"""

from __future__ import annotations

import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TILES_DIR = ROOT / "tiles"
LOG_FILE = ROOT / "tiles_download.log"
FAIL_FILE = ROOT / "tiles_failed.log"
HTML_FILE = ROOT / "progress.html"
STATE_FILE = ROOT / "tiles_progress_state.json"

# 与 scripts/download_tiles.py 保持一致
TOTAL = 135_615

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta http-equiv="refresh" content="8">
<title>瓦片下载进度</title>
<style>
  body {{ font-family: "Segoe UI", "Microsoft YaHei", sans-serif; background: #14181f; color: #dde3ea;
         max-width: 720px; margin: 40px auto; padding: 0 24px; }}
  h1 {{ font-size: 20px; font-weight: 600; }}
  .bar {{ background: #232a34; border-radius: 8px; height: 28px; overflow: hidden; margin: 16px 0 8px; }}
  .fill {{ background: linear-gradient(90deg, #2E9E6B, #4ec98a); height: 100%; width: {pct:.2f}%;
          transition: width .5s; }}
  .stats {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin: 20px 0; }}
  .card {{ background: #1c232d; border-radius: 8px; padding: 12px 14px; }}
  .num {{ font-size: 22px; font-weight: 650; }}
  .lbl {{ font-size: 12px; color: #8b95a3; margin-top: 4px; }}
  .eta {{ color: #4ec98a; }}
  .warn {{ color: #e0a03c; }}
  pre {{ background: #1c232d; border-radius: 8px; padding: 12px 14px; font-size: 12px;
        color: #8b95a3; max-height: 180px; overflow: auto; white-space: pre-wrap; }}
  .done {{ color: #4ec98a; font-size: 18px; font-weight: 650; }}
</style>
</head>
<body>
  <h1>OSM 瓦片下载进度 {status_icon}</h1>
  <div class="bar"><div class="fill"></div></div>
  <div>{pct:.2f}% — {count:,} / {total:,} 张</div>
  <div class="stats">
    <div class="card"><div class="num">{rate:.1f}/s</div><div class="lbl">当前速度</div></div>
    <div class="card"><div class="num eta">{eta}</div><div class="lbl">预计剩余</div></div>
    <div class="card"><div class="num">{size_mb:.0f} MB</div><div class="lbl">已占空间</div></div>
    <div class="card"><div class="num {warn_class}">{fails}</div><div class="lbl">失败张数</div></div>
  </div>
  {done_msg}
  <h1 style="margin-top:28px;font-size:15px;">最近日志</h1>
  <pre>{log_tail}</pre>
</body>
</html>
"""


def count_tiles() -> int:
    if not TILES_DIR.exists():
        return 0
    return sum(1 for p in TILES_DIR.rglob("*.png") if p.is_file())


def dir_size_mb() -> float:
    if not TILES_DIR.exists():
        return 0.0
    return sum(p.stat().st_size for p in TILES_DIR.rglob("*.png") if p.is_file()) / 1024 / 1024


def main() -> None:
    state = {"history": []}
    if STATE_FILE.exists():
        try:
            state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass

    while True:
        now = time.time()
        count = count_tiles()

        hist = [(t, c) for t, c in state["history"] if now - t < 600]
        hist.append((now, count))
        state["history"] = hist

        rate = 0.0
        if len(hist) >= 2:
            dt = hist[-1][0] - hist[0][0]
            if dt > 0:
                rate = (hist[-1][1] - hist[0][1]) / dt

        remain = TOTAL - count
        eta = "—"
        if rate > 0.5 and remain > 0:
            h = remain / rate / 3600
            eta = f"{h:.1f} 小时" if h >= 1 else f"{remain / rate / 60:.0f} 分钟"
        if remain <= 0:
            eta = "已完成"

        fails = 0
        if FAIL_FILE.exists():
            fails = sum(1 for line in FAIL_FILE.read_text(encoding="utf-8").splitlines() if line.strip())

        log_tail = ""
        if LOG_FILE.exists():
            lines = LOG_FILE.read_text(encoding="utf-8", errors="replace").splitlines()
            log_tail = "\n".join(lines[-12:]) or "（日志为空）"
        else:
            log_tail = "（还没有日志）"

        finished = LOG_FILE.exists() and any("done:" in l for l in LOG_FILE.read_text(encoding="utf-8", errors="replace").splitlines())
        done_msg = '<div class="done">✔ 下载完成</div>' if (finished or remain <= 0) else ""

        html = HTML_TEMPLATE.format(
            pct=count / TOTAL * 100,
            count=count,
            total=TOTAL,
            rate=rate,
            eta=eta,
            size_mb=dir_size_mb(),
            fails=fails,
            warn_class="warn" if fails else "",
            status_icon="✔" if finished else "⏳",
            done_msg=done_msg,
            log_tail=log_tail.replace("&", "&amp;").replace("<", "&lt;"),
        )
        HTML_FILE.write_text(html, encoding="utf-8")
        STATE_FILE.write_text(json.dumps(state), encoding="utf-8")
        time.sleep(10)


if __name__ == "__main__":
    main()
