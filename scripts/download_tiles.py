"""下载 OSM 栅格瓦片到本地目录，用于自建底图服务。

范围与高亮国家（伊朗、伊拉克、叙利亚、沙特、科威特、卡塔尔、阿联酋、
阿曼、以色列、巴勒斯坦）外接框一致，含少量边距。

用法：
    python scripts/download_tiles.py

产物：tiles/{z}/{x}/{y}.png，可断点续传（已存在且非空的文件跳过）。
日志：tiles_download.log；失败清单：tiles_failed.log。
"""

from __future__ import annotations

import math
import sys
import time
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.request import Request, build_opener, ProxyHandler, urlopen
from urllib.error import HTTPError, URLError

# ---- 范围：刚好包裹所有高亮国家（含少量边距） ----
LON_MIN, LON_MAX = 33.5, 64.0
LAT_MIN, LAT_MAX = 15.5, 38.0
Z_MIN, Z_MAX = 0, 12

# ---- 下载参数 ----
# 本机直连国际瓦片 CDN 会被限速/断连，必须走本地代理（urllib 按 env 代理配置）。
# 注意：OSM 官方瓦片服务器的 Tile Usage Policy 不鼓励批量下载，
# 并发与频率刻意保持保守，失败自动退避重试。
WORKERS = 14
REQUEST_DELAY = 0.1           # 每个 worker 两次请求之间的间隔（秒）
MAX_RETRIES = 5
RETRY_BACKOFF = 5.0           # 基础退避秒数，按 2^n 倍增
REQUEST_TIMEOUT = 15          # 单次请求超时（秒），连接抖动时尽快释放 worker
URL_TEMPLATE = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
USER_AGENT = "HormuzStudentProject/1.0 (local dev basemap; non-commercial)"

ROOT = Path(__file__).resolve().parent.parent
TILES_DIR = ROOT / "tiles"
LOG_FILE = ROOT / "tiles_download.log"
FAIL_FILE = ROOT / "tiles_failed.log"


def lon_to_x(lon: float, z: int) -> int:
    return int((lon + 180.0) / 360.0 * 2**z)


def lat_to_y(lat: float, z: int) -> int:
    lat = max(-85.05112878, min(85.05112878, lat))
    r = math.radians(lat)
    return int((1.0 - math.log(math.tan(r) + 1.0 / math.cos(r)) / math.pi) / 2.0 * 2**z)


def tile_list():
    for z in range(Z_MIN, Z_MAX + 1):
        x1, x2 = lon_to_x(LON_MIN, z), lon_to_x(LON_MAX, z)
        y1, y2 = lat_to_y(LAT_MAX, z), lat_to_y(LAT_MIN, z)
        for x in range(x1, x2 + 1):
            for y in range(y1, y2 + 1):
                yield z, x, y


def log(msg: str) -> None:
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


_lock = threading.Lock()
_done = 0
_failed = 0
_total = 0

# 走本地代理（Clash/V2Ray 混合端口），避免直连被限速；可用 env 覆盖或关闭
import os
_PROXY = os.environ.get("TILE_PROXY", "http://127.0.0.1:7897")
_opener = build_opener(ProxyHandler({"http": _PROXY, "https": _PROXY})) if _PROXY else build_opener()


def download_one(z: int, x: int, y: int) -> bool:
    global _done, _failed
    path = TILES_DIR / str(z) / str(x) / f"{y}.png"
    if path.exists() and path.stat().st_size > 0:
        with _lock:
            _done += 1
        return True
    url = URL_TEMPLATE.format(z=z, x=x, y=y)
    for attempt in range(MAX_RETRIES):
        try:
            req = Request(url, headers={"User-Agent": USER_AGENT})
            with _opener.open(req, timeout=REQUEST_TIMEOUT) as resp:
                data = resp.read()
            if not data:
                raise URLError("empty response")
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            tmp.write_bytes(data)
            tmp.replace(path)
            time.sleep(REQUEST_DELAY)
            with _lock:
                _done += 1
            return True
        except HTTPError as e:
            if e.code == 404:
                # 海区空白瓦片（纯海洋高缩放级）不存在，记为失败但不重试太多次
                time.sleep(0.1)
                continue
            wait = RETRY_BACKOFF * (2**attempt)
            log(f"HTTP {e.code} z{z}/{x}/{y}, retry {attempt + 1} in {wait:.0f}s")
            time.sleep(wait)
        except (URLError, TimeoutError, OSError) as e:
            wait = RETRY_BACKOFF * (2**attempt)
            log(f"{type(e).__name__} z{z}/{x}/{y}: {e}, retry {attempt + 1} in {wait:.0f}s")
            time.sleep(wait)
    with _lock:
        _failed += 1
        _done += 1
    with open(FAIL_FILE, "a", encoding="utf-8") as f:
        f.write(f"{z} {x} {y}\n")
    return False


def main() -> int:
    global _total
    tiles = list(tile_list())
    _total = len(tiles)
    LOG_FILE.write_text("", encoding="utf-8")
    log(f"start: {_total} tiles, z{Z_MIN}-z{Z_MAX}, "
        f"bbox lon {LON_MIN}-{LON_MAX}, lat {LAT_MIN}-{LAT_MAX}, workers={WORKERS}")
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        for z, x, y in tiles:
            pool.submit(download_one, z, x, y)
    dt = time.time() - t0
    log(f"done: {_total - _failed} ok, {_failed} failed, {dt / 60:.1f} min")
    return 0 if _failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
