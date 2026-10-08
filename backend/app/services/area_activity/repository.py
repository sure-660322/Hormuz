"""区域活动的只读 SQL 仓储。

全部语句固定且参数化；`ship_type` 片段只拼接固定文本（值仍走绑定参数），
不拼接任何调用方数据。读取上限在服务层判定，SQL 只负责返回有界结果。
"""
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.app.services.area_activity import params

# 观测上下文：矩形外扩后的读取范围。内外判定一律使用与 AreaBounds.contains
# 相同的半开规则；这里不额外加 PostGIS 的 `location && envelope` 粗筛——实测
# 规划器不会为该形状选择 gist 索引，逐行求 geography 包围盒反而更慢（见验证报告）。
# 来源批次条件必须与统计、越界探测一致，否则会出现「覆盖说明是一个批次、统计
# 包含其他批次」；:batch_ids 为 NULL 表示不筛批次。
SCOPE_PREDICATE = """
    p.data_source = :source
      AND (CAST(:batch_ids AS bigint[]) IS NULL
           OR p.source_batch_id = ANY(CAST(:batch_ids AS bigint[])))
      AND p.recorded_at >= :scope_start AND p.recorded_at < :scope_end
      AND p.longitude >= :ctx_west AND p.longitude < :ctx_east
      AND p.latitude >= :ctx_south AND p.latitude < :ctx_north
"""

# 越界探测同样受来源批次约束（别名 b / x 指向 ship_positions）。
BATCH_PROBE_FILTER = """b.data_source = :source
                        AND (CAST(:batch_ids AS bigint[]) IS NULL
                             OR b.source_batch_id = ANY(CAST(:batch_ids AS bigint[])))"""

BATCH_PROBE_FILTER_X = """x.data_source = :source
                   AND (CAST(:batch_ids AS bigint[]) IS NULL
                        OR x.source_batch_id = ANY(CAST(:batch_ids AS bigint[])))"""

INSIDE_EXPRESSION = """(
        p.longitude >= :west AND p.longitude < :east
        AND p.latitude >= :south AND p.latitude < :north
    )"""

SHIP_TYPE_SCOPE_FILTER = """
      AND p.ship_id IN (
          SELECT s.id FROM ships AS s
          WHERE s.ship_type = ANY(CAST(:ship_types AS varchar[]))
             OR (s.ship_type IS NULL AND :include_missing)
             OR (s.ship_type = :unknown_label AND :include_unknown)
      )
"""

SHIP_TYPE_ROW_FILTER = """(
        s.ship_type = ANY(CAST(:ship_types AS varchar[]))
        OR (s.ship_type IS NULL AND :include_missing)
        OR (s.ship_type = :unknown_label AND :include_unknown)
    )"""

# 时刻在场：每船取 at 之前的最新报位。不使用「更早的区域内点」兜底，
# 过期报位在服务层按 freshness_seconds 剔除。
LATEST_FIXES = text("""
SELECT s.id AS ship_id, s.mmsi, s.name, s.ship_type, s.flag,
       p.id AS fix_id, p.latitude, p.longitude, p.speed, p.recorded_at,
       p.source_batch_id
FROM ships AS s
JOIN LATERAL (
    SELECT p.id, p.latitude, p.longitude, p.speed, p.recorded_at, p.source_batch_id
    FROM ship_positions AS p
    WHERE p.ship_id = s.id
      AND p.data_source = :source
      AND p.recorded_at <= :at
      AND (CAST(:batch_ids AS bigint[]) IS NULL
           OR p.source_batch_id = ANY(CAST(:batch_ids AS bigint[])))
    ORDER BY p.recorded_at DESC, p.id DESC
    LIMIT 1
) AS p ON TRUE
WHERE 1 = 1
{ship_type_filter}
ORDER BY s.id
LIMIT :limit
""")

# 活动分析：一次窗口函数扫描，只返回 segment 边界报位与覆盖统计。
# - inside 用半开规则；
# - 相邻两条区域内报位之间若存在同船其它报位（说明船被观测到在区外），
#   该对拆成两次访问（left_returned）；否则按缺报(gap)或跳点(jump)处理；
# - 跳点需同时满足位移 >= jump_min_km 与推算速度 > jump_kn：
#   短间隔对的位移中位数只有几十米，单看航速会把 GPS 抖动全部误判为跳点；
# - segment 边界 = 首行(前一条区外/未知或前一对有真实断点)与末行(后一条区外/未知或后一对有真实断点)。
ACTIVITY_BOUNDARIES = text("""
WITH scoped AS MATERIALIZED (
    SELECT p.id, p.ship_id, p.recorded_at, p.latitude, p.longitude, p.speed,
           {inside} AS inside
    FROM ship_positions AS p
    WHERE {scope}
    {ship_type_scope_filter}
), stats AS (
    SELECT count(*) AS scoped_fix_count,
           count(*) FILTER (WHERE inside) AS region_fix_count,
           count(*) FILTER (WHERE inside AND recorded_at >= :start AND recorded_at < :end)
               AS window_region_fix_count,
           min(recorded_at) AS first_fix_at,
           max(recorded_at) AS last_fix_at
    FROM scoped
), ordered AS (
    SELECT s.*,
           row_number() OVER w AS ship_fix_seq,
           lag(s.inside) OVER w AS prev_inside,
           lag(s.recorded_at) OVER w AS prev_at,
           lag(s.id) OVER w AS prev_fix_id,
           lag(s.latitude) OVER w AS prev_lat,
           lag(s.longitude) OVER w AS prev_lon,
           lead(s.inside) OVER w AS next_inside,
           lead(s.recorded_at) OVER w AS next_at,
           lead(s.id) OVER w AS next_fix_id,
           lead(s.latitude) OVER w AS next_lat,
           lead(s.longitude) OVER w AS next_lon,
           CASE WHEN s.recorded_at > lag(s.recorded_at) OVER w THEN
               2 * 6371.0 * asin(sqrt(
                   power(sin(radians(s.latitude - lag(s.latitude) OVER w) / 2), 2)
                   + cos(radians(lag(s.latitude) OVER w)) * cos(radians(s.latitude))
                     * power(sin(radians(s.longitude - lag(s.longitude) OVER w) / 2), 2)
               ))
           END AS pair_km
    FROM scoped AS s
    WINDOW w AS (PARTITION BY s.ship_id ORDER BY s.recorded_at, s.id)
), probed AS (
    -- 只对“可疑对”做一次索引探测：两条区域内报位之间是否还有同船报位。
    SELECT o.*,
           CASE WHEN o.pair_km IS NOT NULL AND o.recorded_at > o.prev_at THEN
               o.pair_km / 1.852
               / (extract(epoch FROM (o.recorded_at - o.prev_at)) / 3600.0)
           END AS implied_speed_kn,
           CASE WHEN o.inside AND o.prev_inside IS true AND (
                    (o.recorded_at - o.prev_at) > make_interval(secs => :probe_seconds)
                    OR (o.pair_km >= :jump_min_km AND o.pair_km / 1.852
                        / NULLIF(extract(epoch FROM (o.recorded_at - o.prev_at)) / 3600.0, 0) > :jump_kn))
                THEN (SELECT b.id FROM ship_positions AS b
                      WHERE b.ship_id = o.ship_id AND {batch_probe_filter}
                        AND (b.recorded_at, b.id) > (o.prev_at, o.prev_fix_id)
                        AND (b.recorded_at, b.id) < (o.recorded_at, o.id)
                      ORDER BY b.recorded_at, b.id LIMIT 1)
           END AS between_first_fix_id,
           CASE WHEN o.inside AND o.prev_inside IS true AND (
                    (o.recorded_at - o.prev_at) > make_interval(secs => :probe_seconds)
                    OR (o.pair_km >= :jump_min_km AND o.pair_km / 1.852
                        / NULLIF(extract(epoch FROM (o.recorded_at - o.prev_at)) / 3600.0, 0) > :jump_kn))
                THEN (SELECT b.recorded_at FROM ship_positions AS b
                      WHERE b.ship_id = o.ship_id AND {batch_probe_filter}
                        AND (b.recorded_at, b.id) > (o.prev_at, o.prev_fix_id)
                        AND (b.recorded_at, b.id) < (o.recorded_at, o.id)
                      ORDER BY b.recorded_at, b.id LIMIT 1)
           END AS between_first_at
    FROM ordered AS o
), marked AS (
    SELECT b.*,
           CASE WHEN b.between_first_fix_id IS NOT NULL THEN
                (SELECT x.recorded_at FROM ship_positions AS x
                 WHERE x.ship_id = b.ship_id AND {batch_probe_filter_x}
                   AND (x.recorded_at, x.id) > (b.prev_at, b.prev_fix_id)
                   AND (x.recorded_at, x.id) < (b.recorded_at, b.id)
                 ORDER BY x.recorded_at DESC, x.id DESC LIMIT 1)
           END AS between_last_at,
           CASE WHEN b.between_first_fix_id IS NOT NULL THEN
                (SELECT x.id FROM ship_positions AS x
                 WHERE x.ship_id = b.ship_id AND {batch_probe_filter_x}
                   AND (x.recorded_at, x.id) > (b.prev_at, b.prev_fix_id)
                   AND (x.recorded_at, x.id) < (b.recorded_at, b.id)
                 ORDER BY x.recorded_at DESC, x.id DESC LIMIT 1)
           END AS between_last_fix_id,
           CASE
             WHEN NOT b.inside OR b.prev_inside IS DISTINCT FROM true THEN NULL
             WHEN b.between_first_fix_id IS NOT NULL THEN 'left_returned'
             WHEN (b.recorded_at - b.prev_at) > make_interval(secs => :gap_seconds) THEN 'gap'
             WHEN b.pair_km >= :jump_min_km AND b.implied_speed_kn > :jump_kn THEN 'jump'
             ELSE 'none'
           END AS break_kind
    FROM probed AS b
), grouped AS (
    SELECT m.*,
           sum(CASE WHEN m.break_kind IN ('gap', 'jump', 'left_returned') THEN 1 ELSE 0 END)
               OVER w AS seg_no,
           lead(m.break_kind) OVER w AS next_break_kind
    FROM marked AS m
    WINDOW w AS (PARTITION BY m.ship_id ORDER BY m.recorded_at, m.id)
), boundary_rows AS (
    SELECT g.*,
           (g.inside AND (g.prev_inside IS DISTINCT FROM true
                          OR g.break_kind IN ('gap', 'jump', 'left_returned')))
               AS is_seg_start,
           (g.inside AND (g.next_inside IS DISTINCT FROM true
                          OR g.next_break_kind IN ('gap', 'jump', 'left_returned')))
               AS is_seg_end
    FROM grouped AS g
)
SELECT b.ship_id, s.name AS ship_name, s.mmsi, s.ship_type,
       b.id AS fix_id, b.recorded_at, b.latitude, b.longitude, b.speed,
       b.seg_no, b.ship_fix_seq, b.is_seg_start, b.is_seg_end,
       b.break_kind AS start_break_kind,
       b.prev_inside, b.prev_at, b.prev_fix_id, b.prev_lat, b.prev_lon,
       b.between_first_fix_id, b.between_first_at,
       b.between_last_fix_id, b.between_last_at,
       b.next_inside, b.next_at, b.next_fix_id, b.next_lat, b.next_lon,
       st.scoped_fix_count, st.region_fix_count, st.window_region_fix_count,
       st.first_fix_at, st.last_fix_at
FROM boundary_rows AS b
JOIN ships AS s ON s.id = b.ship_id
CROSS JOIN stats AS st
WHERE b.is_seg_start OR b.is_seg_end
ORDER BY b.ship_id, b.recorded_at, b.id
LIMIT :boundary_limit
""")

BATCH_COVERAGE = text("""
SELECT id, source_day, inserted_rows, data_source, source_file
FROM ais_import_batches
WHERE data_source = :source
  AND (CAST(:batch_ids AS bigint[]) IS NULL OR id = ANY(CAST(:batch_ids AS bigint[])))
ORDER BY id
""")

# 没有任何边界行时单独取覆盖统计，用于区分 no_data 与「有报位但区域内无船」。
SCOPE_STATS = text("""
WITH scoped AS MATERIALIZED (
    SELECT p.id, p.recorded_at, {inside} AS inside
    FROM ship_positions AS p
    WHERE {scope}
    {ship_type_scope_filter}
)
SELECT count(*) AS scoped_fix_count,
       count(*) FILTER (WHERE inside) AS region_fix_count,
       count(*) FILTER (WHERE inside AND recorded_at >= :start AND recorded_at < :end)
           AS window_region_fix_count,
       min(recorded_at) AS first_fix_at,
       max(recorded_at) AS last_fix_at
FROM scoped
""")


def fetch_latest_fixes(
    db: Session,
    *,
    at,
    source: str,
    batch_ids,
    limit: int,
    ship_type_filter: bool,
    ship_types,
    include_missing: bool,
    include_unknown: bool,
    unknown_label: str,
):
    sql = LATEST_FIXES
    if ship_type_filter:
        sql = text(str(sql).replace("{ship_type_filter}", "AND " + SHIP_TYPE_ROW_FILTER))
    else:
        sql = text(str(sql).replace("{ship_type_filter}", ""))
    return db.execute(sql, {
        "at": at, "source": source, "batch_ids": batch_ids, "limit": limit,
        "ship_types": ship_types, "include_missing": include_missing,
        "include_unknown": include_unknown, "unknown_label": unknown_label,
    }).mappings().all()


def fetch_activity_boundaries(
    db: Session,
    *,
    start,
    end,
    scope_start,
    scope_end,
    source: str,
    batch_ids,
    bounds,
    context,
    gap_seconds: int,
    jump_kn: float,
    boundary_limit: int,
    ship_type_filter: bool,
    ship_types,
    include_missing: bool,
    include_unknown: bool,
    unknown_label: str,
):
    sql = str(ACTIVITY_BOUNDARIES).format(
        inside=INSIDE_EXPRESSION,
        scope=SCOPE_PREDICATE,
        ship_type_scope_filter=SHIP_TYPE_SCOPE_FILTER if ship_type_filter else "",
        batch_probe_filter=BATCH_PROBE_FILTER,
        batch_probe_filter_x=BATCH_PROBE_FILTER_X,
    )
    return db.execute(text(sql), {
        "start": start, "end": end,
        "scope_start": scope_start, "scope_end": scope_end,
        "source": source, "batch_ids": batch_ids,
        "gap_seconds": gap_seconds, "jump_kn": jump_kn,
        "jump_min_km": params.JUMP_MIN_DISTANCE_KM,
        "probe_seconds": params.EXCURSION_PROBE_SECONDS,
        "boundary_limit": boundary_limit,
        "west": bounds.west, "east": bounds.east,
        "south": bounds.south, "north": bounds.north,
        "ctx_west": context.west, "ctx_east": context.east,
        "ctx_south": context.south, "ctx_north": context.north,
        "ship_types": ship_types, "include_missing": include_missing,
        "include_unknown": include_unknown, "unknown_label": unknown_label,
    }).mappings().all()


def fetch_batch_coverage(db: Session, *, source: str, batch_ids):
    return db.execute(
        BATCH_COVERAGE, {"source": source, "batch_ids": batch_ids}
    ).mappings().all()


def fetch_scope_stats(
    db: Session,
    *,
    start,
    end,
    scope_start,
    scope_end,
    source: str,
    batch_ids,
    bounds,
    context,
    ship_type_filter: bool,
    ship_types,
    include_missing: bool,
    include_unknown: bool,
    unknown_label: str,
):
    sql = str(SCOPE_STATS).format(
        inside=INSIDE_EXPRESSION,
        scope=SCOPE_PREDICATE,
        ship_type_scope_filter=SHIP_TYPE_SCOPE_FILTER if ship_type_filter else "",
    )
    return db.execute(text(sql), {
        "start": start, "end": end,
        "scope_start": scope_start, "scope_end": scope_end,
        "source": source, "batch_ids": batch_ids,
        "west": bounds.west, "east": bounds.east,
        "south": bounds.south, "north": bounds.north,
        "ctx_west": context.west, "ctx_east": context.east,
        "ctx_south": context.south, "ctx_north": context.north,
        "ship_types": ship_types, "include_missing": include_missing,
        "include_unknown": include_unknown, "unknown_label": unknown_label,
    }).mappings().one()


def apply_session_settings(db: Session, milliseconds: int, work_mem_mb: int) -> None:
    """SET LOCAL 不接受绑定参数，用 set_config(..., true) 限制本事务的语句耗时与排序内存。"""
    db.execute(text("SELECT set_config('statement_timeout', :value, true)"),
               {"value": str(int(milliseconds))})
    db.execute(text("SELECT set_config('work_mem', :value, true)"),
               {"value": f"{int(work_mem_mb)}MB"})
