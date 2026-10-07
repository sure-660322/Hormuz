"""区域船舶活动与进出分析：固定边界、算法参数、读取上限。

本模块是 issue #41「区域船舶活动与进出分析」第一阶段（后端算法与接口）的唯一
参数来源，口径说明见 docs/area_activity.md。所有阈值都是**版本化常量**，不由模型
或调用方临时决定；调用方可覆盖的只有明确列出的请求参数。
"""
from datetime import timedelta

# ---- 版本 ----
ALGORITHM_NAME = "area_activity"
ALGORITHM_VERSION = "1.0.0"
CONTAINMENT_RULE = "half_open"  # west <= lon < east, south <= lat < north

# ---- 默认分析区域（项目分析区域，非官方航道边界）----
DEFAULT_AREA_ID = "hormuz_core_v1"
DEFAULT_AREA_NAME = "霍尔木兹海峡核心通行区（项目分析区域）"
DEFAULT_AREA_VERSION = "1.0.0"
DEFAULT_AREA_BASIS = (
    "现有海峡虚拟双门线判定走廊的包围盒（门线 56.2°E/56.7°E、判定纬度带 "
    "25.8–27.1°N、邻域经度 55.8–57.1°E，见 backend/app/services/agent/config.py 与 "
    "docs/agent_integration.md），与前端默认地图中心 [26.35, 56.5] 一致；"
    "属项目分析区域，不是官方航道（TAS/TSS）边界"
)
DEFAULT_SOUTH = 25.8
DEFAULT_WEST = 55.8
DEFAULT_NORTH = 27.1
DEFAULT_EAST = 57.1

# ---- 数据来源 ----
SOURCE = "nnu_ais"

# ---- 算法阈值（默认值；依据见 docs/area_activity.md §2.3/§3）----
# 时刻在场：报位新鲜度上限，与 routers/ships.py 的 SNAPSHOT_MAX_AGE 一致。
FRESHNESS_SECONDS = 3600
# 缺报断开阈值：区域内 2026-02-28 单船相邻报位间隔 p99 = 636 s，30 min≈2.8×p99。
GAP_SECONDS = 1800
# 异常跳点：位移与推算速度需同时超阈值。区域内七日样本显示短间隔对（<=15 s）
# 的位移中位数仅 42 m，只看航速会把 GPS 抖动全部误判为跳点；>=1 km 的短间隔对
# 七日只有 59 次。
JUMP_SPEED_KN = 30.0
JUMP_MIN_DISTANCE_KM = 1.0
# 窗口前后读取前置/结束状态的范围。
STATE_LOOKBACK_SECONDS = 21600
STATE_LOOKAHEAD_SECONDS = 21600
# 观测上下文矩形外扩（度，约 5.5 km）；只影响读取范围，不改变内外判定。
CONTEXT_MARGIN_DEG = 0.05
# 边界近邻标记距离（米）。
BOUNDARY_BAND_M = 500.0
# 归日时区。
DAY_TIME_ZONE = "UTC"

# ---- 船型筛选保留值 ----
SHIP_TYPE_MISSING = "__missing__"  # 匹配 NULL/空
SHIP_TYPE_UNKNOWN = "__unknown__"  # 匹配「未知」
SHIP_TYPE_ALL = "all"  # 显式全部

# ---- 读取与输出上限（超限拒绝，不截断汇总）----
MAX_SCANNED_FIXES = 4_000_000
MAX_CANDIDATE_SHIPS = 5_000
MAX_VISIT_ROWS = 2_000
MAX_SNAPSHOT_SHIPS = 5_000
MAX_WINDOW_DAYS = 7
MAX_RECT_SPAN_DEG = 10.0
MAX_STATE_LOOKBACK_SECONDS = 86_400
MAX_LOOKBACK_SECONDS = 86_400
STATEMENT_TIMEOUT_MS = 20_000
# 排序内存：窗口函数需要按 (ship_id, recorded_at, id) 排序，默认 4MB 会落盘。
WORK_MEM_MB = 64
# 边界行上限：每条 segment 最多两行边界报位，另留余量；超限视为明细过大而拒绝。
MAX_BOUNDARY_ROWS = 4 * MAX_VISIT_ROWS + 2_000

DEFAULT_VISIT_LIMIT = 500
DEFAULT_SNAPSHOT_LIMIT = 500

MAX_WINDOW = timedelta(days=MAX_WINDOW_DAYS)


def algorithm_descriptor() -> dict:
    """返回随结果回显的算法版本与全部生效参数。"""
    return {
        "name": ALGORITHM_NAME,
        "version": ALGORITHM_VERSION,
        "params": {
            "containment": CONTAINMENT_RULE,
            "freshness_seconds": FRESHNESS_SECONDS,
            "gap_seconds": GAP_SECONDS,
            "jump_speed_kn": JUMP_SPEED_KN,
            "jump_min_distance_km": JUMP_MIN_DISTANCE_KM,
            "default_state_lookback_seconds": STATE_LOOKBACK_SECONDS,
            "default_state_lookahead_seconds": STATE_LOOKAHEAD_SECONDS,
            "context_margin_deg": CONTEXT_MARGIN_DEG,
            "boundary_band_m": BOUNDARY_BAND_M,
            "day_bucket_time_zone": DAY_TIME_ZONE,
            "visit_split_rule": "observed_outside_fix_between_consecutive_in_area_fixes",
            "duration_rule": "sum_of_consecutive_in_area_intervals_split_by_gap_or_jump",
            "interpolation": "none",
            "max_window_days": MAX_WINDOW_DAYS,
            "max_scanned_fixes": MAX_SCANNED_FIXES,
            "max_candidate_ships": MAX_CANDIDATE_SHIPS,
            "max_visit_rows": MAX_VISIT_ROWS,
            "max_snapshot_ships": MAX_SNAPSHOT_SHIPS,
            "max_rect_span_deg": MAX_RECT_SPAN_DEG,
            "statement_timeout_ms": STATEMENT_TIMEOUT_MS,
            "work_mem_mb": WORK_MEM_MB,
        },
    }
