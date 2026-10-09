// 区域船舶活动面板（issue #41 阶段二-A）的纯展示层工具。
//
// 约定：本文件不做任何业务判定（在场、进入、离开、停留时长、状态分类全部取后端字段），
// 只做四件事，且全部无副作用、无 import，便于 checks/area-activity.cjs 单独编译执行：
//   1. 视图类型：字段名与 backend/app/schemas_area_activity.py 一一对应；
//   2. 响应归一化：把后端 JSON 读成面板类型；字段缺失记 null 并显示「—」，不回填 0；
//   3. 展示换算：UTC 时间、时长、数字、change_rate 空值说明、截断提示、状态与标记文案；
//   4. 交互装配：datetime-local 与 ISO Z 互转、船型多选到查询值、emit 参数、对话提示词。

export type AreaPanelMode = 'snapshot' | 'activity' | 'compare'

export const AREA_PANEL_MODES: ReadonlyArray<{ value: AreaPanelMode; label: string; hint: string }> = [
  { value: 'snapshot', label: '时刻在场', hint: '某个 UTC 时刻，区域内最新且未过期的报位' },
  { value: 'activity', label: '时段活动', hint: 'UTC 半开区间 [start, end)，观测进入/离开、停留与按日统计' },
  { value: 'compare', label: '两时段比较', hint: '同区域同筛选的 A/B 两期指标对比，允许不等长' },
]

export interface AreaBounds {
  west: number
  south: number
  east: number
  north: number
}

// 兼容后端 area 的两种写法：嵌套 bounds（当前实现）或扁平 west/south/east/north。
export function readBounds(raw: unknown): AreaBounds | null {
  const obj = asRecord(raw)
  if (!obj) return null
  const nested = asRecord(obj.bounds)
  const source = nested ?? obj
  const west = numOrNull(source.west)
  const south = numOrNull(source.south)
  const east = numOrNull(source.east)
  const north = numOrNull(source.north)
  if (west === null || south === null || east === null || north === null) return null
  return { west, south, east, north }
}

export function boundsEqual(a: AreaBounds | null | undefined, b: AreaBounds | null | undefined): boolean {
  if (!a || !b) return a === b
  return a.west === b.west && a.south === b.south && a.east === b.east && a.north === b.north
}

export function boundsText(bounds: AreaBounds | null | undefined): string {
  if (!bounds) return '—'
  return `${formatLatitude(bounds.south)}–${formatLatitude(bounds.north)}，${formatLongitude(bounds.west)}–${formatLongitude(bounds.east)}`
}

export interface AreaInfo {
  area_id: string
  name: string
  version: string | null
  is_default: boolean
  basis: string | null
  bounds: AreaBounds | null
  span_deg: { lat: number; lon: number } | null
  containment: string | null
}

export interface AreaAlgorithm {
  name: string
  version: string
  params: Record<string, unknown>
}

export interface AreaCoverage {
  source: string | null
  batch_ids: number[]
  batch_days: string[]
  scope_start: string | null
  scope_end: string | null
  scoped_fix_count: number | null
  region_fix_count: number | null
  window_region_fix_count: number | null
  first_fix_at: string | null
  last_fix_at: string | null
  note: string | null
}

export interface AreaSnapshotSummary {
  in_area_count: number | null
  out_of_area_fresh_count: number | null
  stale_fix_count: number | null
  evaluated_ship_count: number | null
  freshness_seconds: number | null
}

export interface AreaActivitySummary {
  ships_observed: number | null
  observed_entry_count: number | null
  observed_exit_count: number | null
  observed_ship_seconds: number | null
  observed_ship_hours: number | null
  visit_count: number | null
  complete_visit_count: number | null
  truncated_start_visit_count: number | null
  truncated_end_visit_count: number | null
  interrupted_visit_count: number | null
  uncertain_visit_count: number | null
  prior_state_unknown_visit_count: number | null
  near_boundary_event_count: number | null
  unobserved_gap_seconds: number | null
}

export interface AreaSnapshotShip {
  ship_id: number
  name: string | null
  mmsi: string | null
  ship_type: string | null
  flag?: string | null
  fix_id?: number | null
  latitude: number
  longitude: number
  speed: number | null
  recorded_at: string
  age_seconds: number
  fresh: boolean
  inside: boolean
}

export interface AreaFix {
  id: number | null
  recorded_at: string | null
  latitude: number | null
  longitude: number | null
}

export interface AreaEvent {
  observed: boolean
  observed_at: string | null
  bracket_seconds: number | null
  inside_fix: AreaFix | null
  outside_fix: AreaFix | null
  outside_evidence_in_context?: boolean
  near_boundary?: boolean
  wide_bracket?: boolean
  same_second_conflict?: boolean
  in_window: boolean
}

export interface AreaSegment {
  segment_no: number
  start_at: string
  end_at: string
  start_fix_id: number | null
  end_fix_id: number | null
  seconds: number
  in_window_seconds: number
  fix_count: number
}

export interface AreaVisit {
  visit_key: string
  ship_id: number
  ship_name: string | null
  mmsi: string | null
  ship_type: string | null
  entry: AreaEvent
  exit: AreaEvent
  prior_state: string
  first_inside_at: string
  last_inside_at: string
  fix_count: number
  segment_count: number
  segments: AreaSegment[]
  observed_seconds: number
  window_seconds: number
  unobserved_gap_seconds: number
  started_before_window: boolean
  touches_window: boolean
  status: string
  flags: string[]
}

export interface AreaDaily {
  date: string
  ships_observed: number
  observed_entry_count: number
  observed_exit_count: number
  observed_ship_seconds: number
  observed_ship_hours: number
  visits_touching_day: number
  complete_visit_count: number
  truncated_visit_count: number
  interrupted_visit_count: number
  uncertain_visit_count: number
}

export interface AreaMetric {
  key: string
  label: string
  unit: string
  a: number
  b: number
  delta: number
  change_rate: number | null
}

export interface AreaComparability {
  same_area: boolean
  same_filters: boolean
  same_algorithm: boolean
  equal_length: boolean
  window_days_a: number | null
  window_days_b: number | null
  window_length_days_a: number | null
  window_length_days_b: number | null
  per_day_denominator: string | null
  warnings: string[]
}

export interface AreaWindowInfo {
  start: string | null
  end: string | null
  days: number | null
  length_hours: number | null
  length_days: number | null
}

export interface AreaLimits {
  [key: string]: unknown
}

export interface AreaSnapshotResult {
  status: string
  area: AreaInfo
  algorithm: AreaAlgorithm
  coverage: AreaCoverage
  summary: AreaSnapshotSummary
  ships: AreaSnapshotShip[]
  limits: AreaLimits
  limitations: string[]
  query: unknown
}

export interface AreaActivityResult {
  status: string
  area: AreaInfo
  algorithm: AreaAlgorithm
  coverage: AreaCoverage
  summary: AreaActivitySummary
  daily: AreaDaily[]
  visits: AreaVisit[]
  limits: AreaLimits
  limitations: string[]
  query: unknown
}

export interface AreaPeriodResult {
  status: string
  summary: AreaActivitySummary
  coverage: AreaCoverage
  daily: AreaDaily[]
}

export interface AreaCompareResult {
  status: string
  area: AreaInfo
  algorithm: AreaAlgorithm
  windows: { a: AreaWindowInfo; b: AreaWindowInfo }
  metrics: AreaMetric[]
  comparability: AreaComparability
  a: AreaPeriodResult
  b: AreaPeriodResult
  limitations: string[]
}

export interface AreaShipTypeOption {
  value: string
  label: string
  count: number | null
  count_scope: string | null
}

export interface AreaShipTypesResult {
  status: string
  source: string | null
  total_ships: number | null
  options: AreaShipTypeOption[]
  limitations: string[]
}

// —— 归一化 ——

export function readAreaInfo(raw: unknown): AreaInfo {
  const obj = asRecord(raw) ?? {}
  const span = asRecord(obj.span_deg)
  const lat = span ? numOrNull(span.lat) : null
  const lon = span ? numOrNull(span.lon) : null
  return {
    area_id: strOrNull(obj.area_id) ?? '',
    name: strOrNull(obj.name) ?? '',
    version: strOrNull(obj.version),
    is_default: obj.is_default === true,
    basis: strOrNull(obj.basis),
    bounds: readBounds(obj),
    span_deg: lat !== null && lon !== null ? { lat, lon } : null,
    containment: strOrNull(obj.containment),
  }
}

export function readAlgorithm(raw: unknown): AreaAlgorithm {
  const obj = asRecord(raw) ?? {}
  return {
    name: strOrNull(obj.name) ?? '',
    version: strOrNull(obj.version) ?? '',
    params: asRecord(obj.params) ?? {},
  }
}

export function readCoverage(raw: unknown): AreaCoverage {
  const obj = asRecord(raw) ?? {}
  return {
    source: strOrNull(obj.source),
    batch_ids: numberList(obj.batch_ids),
    batch_days: stringList(obj.batch_days),
    scope_start: strOrNull(obj.scope_start),
    scope_end: strOrNull(obj.scope_end),
    scoped_fix_count: numOrNull(obj.scoped_fix_count),
    region_fix_count: numOrNull(obj.region_fix_count),
    window_region_fix_count: numOrNull(obj.window_region_fix_count),
    first_fix_at: strOrNull(obj.first_fix_at),
    last_fix_at: strOrNull(obj.last_fix_at),
    note: strOrNull(obj.note),
  }
}

export function readSnapshotSummary(raw: unknown): AreaSnapshotSummary {
  const obj = asRecord(raw) ?? {}
  return {
    in_area_count: numOrNull(obj.in_area_count),
    out_of_area_fresh_count: numOrNull(obj.out_of_area_fresh_count),
    stale_fix_count: numOrNull(obj.stale_fix_count),
    evaluated_ship_count: numOrNull(obj.evaluated_ship_count),
    freshness_seconds: numOrNull(obj.freshness_seconds),
  }
}

export function readActivitySummary(raw: unknown): AreaActivitySummary {
  const obj = asRecord(raw) ?? {}
  return {
    ships_observed: numOrNull(obj.ships_observed),
    observed_entry_count: numOrNull(obj.observed_entry_count),
    observed_exit_count: numOrNull(obj.observed_exit_count),
    observed_ship_seconds: numOrNull(obj.observed_ship_seconds),
    observed_ship_hours: numOrNull(obj.observed_ship_hours),
    visit_count: numOrNull(obj.visit_count),
    complete_visit_count: numOrNull(obj.complete_visit_count),
    truncated_start_visit_count: numOrNull(obj.truncated_start_visit_count),
    truncated_end_visit_count: numOrNull(obj.truncated_end_visit_count),
    interrupted_visit_count: numOrNull(obj.interrupted_visit_count),
    uncertain_visit_count: numOrNull(obj.uncertain_visit_count),
    prior_state_unknown_visit_count: numOrNull(obj.prior_state_unknown_visit_count),
    near_boundary_event_count: numOrNull(obj.near_boundary_event_count),
    unobserved_gap_seconds: numOrNull(obj.unobserved_gap_seconds),
  }
}

export function toAreaSnapshotResult(raw: unknown): AreaSnapshotResult {
  const obj = asRecord(raw) ?? {}
  return {
    status: strOrNull(obj.status) ?? 'unknown',
    area: readAreaInfo(obj.area),
    algorithm: readAlgorithm(obj.algorithm),
    coverage: readCoverage(obj.coverage),
    summary: readSnapshotSummary(obj.summary),
    ships: asArray<AreaSnapshotShip>(obj.ships),
    limits: asRecord(obj.limits) ?? {},
    limitations: stringList(obj.limitations),
    query: obj.query,
  }
}

export function toAreaActivityResult(raw: unknown): AreaActivityResult {
  const obj = asRecord(raw) ?? {}
  return {
    status: strOrNull(obj.status) ?? 'unknown',
    area: readAreaInfo(obj.area),
    algorithm: readAlgorithm(obj.algorithm),
    coverage: readCoverage(obj.coverage),
    summary: readActivitySummary(obj.summary),
    daily: asArray<AreaDaily>(obj.daily),
    visits: asArray<AreaVisit>(obj.visits),
    limits: asRecord(obj.limits) ?? {},
    limitations: stringList(obj.limitations),
    query: obj.query,
  }
}

export function readAreaWindowInfo(raw: unknown): AreaWindowInfo {
  const obj = asRecord(raw) ?? {}
  return {
    start: strOrNull(obj.start),
    end: strOrNull(obj.end),
    days: numOrNull(obj.days),
    length_hours: numOrNull(obj.length_hours),
    length_days: numOrNull(obj.length_days),
  }
}

export function readComparability(raw: unknown): AreaComparability {
  const obj = asRecord(raw) ?? {}
  return {
    same_area: obj.same_area === true,
    same_filters: obj.same_filters === true,
    same_algorithm: obj.same_algorithm === true,
    equal_length: obj.equal_length === true,
    window_days_a: numOrNull(obj.window_days_a),
    window_days_b: numOrNull(obj.window_days_b),
    window_length_days_a: numOrNull(obj.window_length_days_a),
    window_length_days_b: numOrNull(obj.window_length_days_b),
    per_day_denominator: strOrNull(obj.per_day_denominator),
    warnings: stringList(obj.warnings),
  }
}

export function toAreaCompareResult(raw: unknown): AreaCompareResult {
  const obj = asRecord(raw) ?? {}
  const windows = asRecord(obj.windows) ?? {}
  return {
    status: strOrNull(obj.status) ?? 'unknown',
    area: readAreaInfo(obj.area),
    algorithm: readAlgorithm(obj.algorithm),
    windows: { a: readAreaWindowInfo(windows.a), b: readAreaWindowInfo(windows.b) },
    metrics: asArray<AreaMetric>(obj.metrics).map(metric => ({
      key: String(metric?.key ?? ''),
      label: String(metric?.label ?? metric?.key ?? ''),
      unit: String(metric?.unit ?? ''),
      a: numOrNull(metric?.a) ?? 0,
      b: numOrNull(metric?.b) ?? 0,
      delta: numOrNull(metric?.delta) ?? 0,
      change_rate: numOrNull(metric?.change_rate),
    })),
    comparability: readComparability(obj.comparability),
    a: readPeriodResult(obj.a),
    b: readPeriodResult(obj.b),
    limitations: stringList(obj.limitations),
  }
}

function readPeriodResult(raw: unknown): AreaPeriodResult {
  const obj = asRecord(raw) ?? {}
  return {
    status: strOrNull(obj.status) ?? 'unknown',
    summary: readActivitySummary(obj.summary),
    coverage: readCoverage(obj.coverage),
    daily: asArray<AreaDaily>(obj.daily),
  }
}

// 船型列表：ship_types 与保留值 reserved（__missing__/__unknown__ 等）合并，不在前端硬编码。
export function mergeShipTypeOptions(shipTypes: unknown, reserved: unknown): AreaShipTypeOption[] {
  const list: AreaShipTypeOption[] = []
  const seen = new Set<string>()
  const push = (value: unknown, label: unknown, count: unknown, scope: unknown) => {
    const text = typeof value === 'string' ? value.trim() : ''
    if (!text || seen.has(text)) return
    seen.add(text)
    list.push({
      value: text,
      label: typeof label === 'string' && label.trim() ? label.trim() : text,
      count: numOrNull(count),
      count_scope: strOrNull(scope),
    })
  }
  for (const option of asArray<Record<string, unknown>>(shipTypes)) {
    push(option?.value, option?.label, option?.count, option?.count_scope)
  }
  for (const option of asArray<Record<string, unknown>>(reserved)) {
    push(option?.value, option?.label, null, 'reserved')
  }
  return list
}

export function toAreaShipTypesResult(raw: unknown): AreaShipTypesResult {
  const obj = asRecord(raw) ?? {}
  return {
    status: strOrNull(obj.status) ?? 'unknown',
    source: strOrNull(obj.source),
    total_ships: numOrNull(obj.total_ships),
    options: mergeShipTypeOptions(obj.ship_types, obj.reserved),
    limitations: stringList(obj.limitations),
  }
}

// —— 船型筛选 ——

// 后端语义：为空表示全部船型；默认全选等价于不带该参数（null）。
export function shipTypeQueryValues(selected: readonly string[], allValues: readonly string[]): string[] | null {
  if (!allValues.length) return null
  const effective = selected.filter(value => allValues.includes(value))
  if (!effective.length || effective.length === allValues.length) return null
  return [...effective]
}

export function allShipTypesSelected(selected: readonly string[], allValues: readonly string[]): boolean {
  if (!allValues.length) return true
  return allValues.every(value => selected.includes(value))
}

export function shipTypeSelectionText(selected: readonly string[], options: readonly AreaShipTypeOption[]): string {
  if (!options.length) return '全部船型（船型列表未加载）'
  const labels = options.filter(option => selected.includes(option.value)).map(option => option.label)
  if (labels.length === options.length) return '全部船型'
  if (!labels.length) return '未选择船型'
  if (labels.length <= 4) return labels.join('、')
  return `${labels.slice(0, 4).join('、')} 等 ${labels.length} 种`
}

// —— 时间（界面按 UTC 输入，内部一律 ISO 8601 Z） ——

export function utcToday(now: Date = new Date()): string {
  return now.toISOString().slice(0, 10)
}

export function shiftUtcDay(day: string, days: number): string {
  const ms = Date.parse(`${day}T00:00:00Z`)
  if (!Number.isFinite(ms)) return day
  return new Date(ms + days * 86_400_000).toISOString().slice(0, 10)
}

// ISO（或 Date）→ datetime-local 值 'YYYY-MM-DDTHH:mm'，按 UTC 读数，不做本地时区换算。
export function utcInputValue(value: string | Date | null | undefined): string {
  const date = value instanceof Date ? value : parseUtc(value)
  if (!date) return ''
  return date.toISOString().slice(0, 16)
}

// datetime-local 值 → ISO Z；非法输入返回 null（由表单提示，不发给后端）。
export function utcInputToIso(value: string | null | undefined): string | null {
  if (typeof value !== 'string') return null
  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::(\d{2}))?$/.exec(value.trim())
  if (!match) return null
  const [year, month, day, hour, minute] = [match[1], match[2], match[3], match[4], match[5]]
  const second = match[6] ?? '00'
  const text = `${year}-${month}-${day}T${hour}:${minute}:${second}`
  const ms = Date.parse(`${text}Z`)
  if (!Number.isFinite(ms)) return null
  // 拒绝被 Date 自动纠正的日期（例如 2026-02-30）。
  if (new Date(ms).toISOString().slice(0, 19) !== text) return null
  return `${text}Z`
}

export function utcDayStartIso(day: string | null | undefined): string | null {
  return utcInputToIso(`${String(day ?? '').slice(0, 10)}T00:00`)
}

export function utcDayEndIso(day: string | null | undefined): string | null {
  const start = utcDayStartIso(day)
  if (!start) return null
  return utcInputToIso(`${shiftUtcDay(start.slice(0, 10), 1)}T00:00`)
}

// Presentation groups use only options returned by the API; never invent query values.
export function groupAreaShipTypes(options: AreaShipTypeOption[]) {
  const labels = ['油轮', '集装箱', '货船']
  return {
    primary: labels.flatMap(label => options.filter(option => option.label === label)),
    other: options.filter(option => !labels.includes(option.label)),
  }
}

// Seed once from loaded AIS coverage, never from the computer clock.
export function areaInitialWindows(startAt: string, endAt: string) {
  const start = Date.parse(startAt), end = Date.parse(endAt)
  if (!Number.isFinite(start) || !Number.isFinite(end) || end <= start) return null
  const day = 86400000
  const firstMidnight = Math.ceil(start / day) * day
  const from = firstMidnight + day <= end ? firstMidnight : start
  const to = Math.min(from + day, end)
  const secondFrom = to + day <= end ? to : from
  const secondTo = Math.min(secondFrom + day, end)
  return {
    start: utcInputValue(new Date(from)), end: utcInputValue(new Date(to)),
    startA: utcInputValue(new Date(from)), endA: utcInputValue(new Date(to)),
    startB: utcInputValue(new Date(secondFrom)), endB: utcInputValue(new Date(secondTo)),
  }
}

// 默认时段：当日 UTC 自然日 [今天 00:00Z, 明天 00:00Z)。
export function defaultActivityWindow(now: Date = new Date()): { start: string; end: string } {
  const today = utcToday(now)
  return { start: `${today}T00:00`, end: `${shiftUtcDay(today, 1)}T00:00` }
}

// 默认比较：A = 前一日 UTC 自然日，B = 当日 UTC 自然日。
export function defaultCompareWindows(now: Date = new Date()): { startA: string; endA: string; startB: string; endB: string } {
  const today = utcToday(now)
  const yesterday = shiftUtcDay(today, -1)
  return {
    startA: `${yesterday}T00:00`,
    endA: `${today}T00:00`,
    startB: `${today}T00:00`,
    endB: `${shiftUtcDay(today, 1)}T00:00`,
  }
}

export function utcRangeText(start: string | null | undefined, end: string | null | undefined): string {
  const from = formatUtc(start)
  const to = formatUtc(end)
  if (from === '—' && to === '—') return '未填写'
  return `${from} → ${to}（UTC，终点不含）`
}

// 轻量表单校验：只拦「必填 + 顺序」，跨度/格式等业务规则以后端 422 为准。
export function windowOrderError(start: string | null, end: string | null): string | null {
  if (!start || !end) return '请填写完整的起止时刻（UTC）'
  const from = Date.parse(start)
  const to = Date.parse(end)
  if (!Number.isFinite(from) || !Number.isFinite(to)) return '时间格式无效，请重新选择（UTC）'
  if (from >= to) return '结束时刻必须晚于开始时刻（半开区间 [start, end)）'
  return null
}

// —— 数字与时间格式化 ——

export function dash(value: unknown): string {
  if (value === null || value === undefined || value === '') return '—'
  return String(value)
}

export function formatCount(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—'
  const rounded = Math.round(value)
  const sign = rounded < 0 ? '-' : ''
  return sign + Math.abs(rounded).toString().replace(/\B(?=(\d{3})+(?!\d))/g, ',')
}

export function formatDecimal(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—'
  return value.toFixed(digits)
}

export function formatSeconds(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || !Number.isFinite(seconds) || seconds < 0) return '—'
  const total = Math.round(seconds)
  const days = Math.floor(total / 86_400)
  const hours = Math.floor((total % 86_400) / 3_600)
  const minutes = Math.floor((total % 3_600) / 60)
  const secs = total % 60
  const clock = `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(secs).padStart(2, '0')}`
  return days > 0 ? `${days} 天 ${clock}` : clock
}

export function formatHours(hours: number | null | undefined): string {
  if (hours === null || hours === undefined || !Number.isFinite(hours)) return '—'
  return `${hours.toFixed(1)} h`
}

export function formatAge(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || !Number.isFinite(seconds) || seconds < 0) return '—'
  if (seconds < 90) return `${Math.round(seconds)} 秒`
  if (seconds < 5_400) return `${Math.round(seconds / 60)} 分钟`
  if (seconds < 172_800) return `${(seconds / 3_600).toFixed(1)} 小时`
  return `${(seconds / 86_400).toFixed(1)} 天`
}

export function formatSpeed(speed: number | null | undefined): string {
  if (speed === null || speed === undefined || !Number.isFinite(speed)) return '—'
  return `${speed.toFixed(1)} kn`
}

export function formatLatitude(lat: number | null | undefined): string {
  if (lat === null || lat === undefined || !Number.isFinite(lat)) return '—'
  return `${Math.abs(lat).toFixed(4)}°${lat >= 0 ? 'N' : 'S'}`
}

export function formatLongitude(lon: number | null | undefined): string {
  if (lon === null || lon === undefined || !Number.isFinite(lon)) return '—'
  return `${Math.abs(lon).toFixed(4)}°${lon >= 0 ? 'E' : 'W'}`
}

export function formatPosition(lat: number | null | undefined, lon: number | null | undefined): string {
  return `${formatLatitude(lat)} ${formatLongitude(lon)}`
}

export function formatSpan(span: { lat: number; lon: number } | null | undefined): string {
  if (!span) return '—'
  return `${span.lat.toFixed(2)}° × ${span.lon.toFixed(2)}°`
}

export function parseUtc(value: string | null | undefined): Date | null {
  if (!value) return null
  const ms = Date.parse(value)
  return Number.isFinite(ms) ? new Date(ms) : null
}

export function formatUtc(value: string | null | undefined): string {
  const date = parseUtc(value)
  if (!date) return '—'
  const iso = date.toISOString()
  return `${iso.slice(0, 10)} ${iso.slice(11, 19)}`
}

export function formatUtcShort(value: string | null | undefined): string {
  const date = parseUtc(value)
  if (!date) return '—'
  return date.toISOString().slice(5, 16).replace('T', ' ')
}

export function formatUtcDay(value: string | null | undefined): string {
  const date = parseUtc(value)
  return date ? date.toISOString().slice(0, 10) : dash(value)
}

// —— change_rate / delta ——

export function hasChangeRate(rate: number | null | undefined): rate is number {
  return typeof rate === 'number' && Number.isFinite(rate)
}

// 基期为 0 时后端返回 null：显示说明，绝不显示 0 或 NaN。
export function changeRateText(rate: number | null | undefined): string {
  if (!hasChangeRate(rate)) return '基期为 0，无法计算变化率'
  const sign = rate > 0 ? '+' : ''
  return `${sign}${(rate * 100).toFixed(1)}%`
}

export function formatSigned(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—'
  const sign = value > 0 ? '+' : ''
  return `${sign}${value.toFixed(digits)}`
}

// —— 状态 ——

export function isNoData(status: string | null | undefined): boolean {
  return status === 'no_data'
}

export function statusLabel(status: string | null | undefined): string {
  if (status === 'ok') return '完整'
  if (status === 'partial') return '部分结果'
  if (status === 'no_data') return '无数据'
  return dash(status)
}

export function statusTone(status: string | null | undefined): 'ok' | 'warn' | 'empty' {
  if (status === 'ok') return 'ok'
  if (status === 'partial') return 'warn'
  return 'empty'
}

export function statusDescription(status: string | null | undefined): string {
  if (status === 'ok') return '有观测且无不确定候选，明细未被截断。'
  if (status === 'partial') return '有观测，但存在不确定候选或明细被截断；汇总数字仍完整。'
  if (status === 'no_data') return '读取范围内没有任何可判定报位，不能解释为「零船」，请检查时间窗、区域与批次范围。'
  return `未知状态：${dash(status)}`
}

export function isEmptyResult(status: string | null | undefined, count: number | null | undefined): boolean {
  return !isNoData(status) && count === 0
}

export function emptyResultText(mode: AreaPanelMode): string {
  if (mode === 'snapshot') return '有报位，但该时刻区域内没有新鲜在场船舶（有效零结果）。'
  if (mode === 'activity') return '有报位，但该窗口内区域内没有船舶活动（有效零结果）。'
  return '两期都有报位，但窗口内区域内没有可比活动（有效零结果）。'
}

// —— 截断提示（读后端 limits.list_truncated / limits.detail_truncated） ——

export function limitNumber(limits: AreaLimits | null | undefined, key: string): number | null {
  return numOrNull(limits?.[key])
}

export function limitFlag(limits: AreaLimits | null | undefined, key: string): boolean {
  return limits?.[key] === true
}

export function snapshotTruncationNote(limits: AreaLimits | null | undefined): string | null {
  if (!limitFlag(limits, 'list_truncated')) return null
  const returned = limitNumber(limits, 'returned_ship_count')
  const max = limitNumber(limits, 'max_snapshot_ships')
  const evaluated = limitNumber(limits, 'evaluated_ship_count')
  const parts = [`船舶列表已截断：返回 ${formatCount(returned)} 艘`]
  if (max !== null) parts.push(`列表上限 ${formatCount(max)}`)
  if (evaluated !== null) parts.push(`参与判定 ${formatCount(evaluated)} 艘`)
  return `${parts.join('，')}。summary 汇总计数不受列表截断影响。`
}

export function activityTruncationNote(limits: AreaLimits | null | undefined): string | null {
  if (!limitFlag(limits, 'detail_truncated')) return null
  const returned = limitNumber(limits, 'returned_visit_count')
  const limit = limitNumber(limits, 'visit_limit')
  const max = limitNumber(limits, 'max_visit_rows')
  const candidates = limitNumber(limits, 'candidate_ship_count')
  const parts = [`访问明细已截断：返回 ${formatCount(returned)} 条访问`]
  if (limit !== null) parts.push(`visit_limit=${formatCount(limit)}`)
  if (max !== null) parts.push(`后端上限 ${formatCount(max)}`)
  if (candidates !== null) parts.push(`候选船 ${formatCount(candidates)} 艘`)
  return `${parts.join('，')}。summary 与每日统计不受明细截断影响（status 记为 partial）。`
}

// —— 访问明细文案与 emit 参数 ——

const VISIT_STATUS_LABELS: Record<string, string> = {
  complete: '完整（进入与离开都被观测）',
  truncated_start: '起点截断（窗口前已在区内或前置状态未知）',
  truncated_end: '终点截断（未观测到离开）',
  interrupted: '缺报中断',
  uncertain: '含质量标记',
}

export function visitStatusLabel(status: string | null | undefined): string {
  const key = String(status ?? '')
  return VISIT_STATUS_LABELS[key] ?? dash(status)
}

const VISIT_FLAG_LABELS: Record<string, string> = {
  gap_interrupted: '缺报中断（区间不计入停留时长）',
  jump_break: '疑似跳点（区间不计入停留时长）',
  wide_entry_bracket: '进入证据括号偏宽',
  wide_exit_bracket: '离开证据括号偏宽',
  near_boundary_entry: '进入点贴近边界（<500 m）',
  near_boundary_exit: '离开点贴近边界（<500 m）',
  same_second_conflict: '同秒内外状态冲突',
  outside_evidence_out_of_context: '区外证据不在观测上下文中',
}

export function flagLabel(flag: string): string {
  return VISIT_FLAG_LABELS[flag] ?? flag
}

// prior_state 取值来自后端：outside / inside / unknown（lookback 内无更早报位）。
const PRIOR_STATE_LABELS: Record<string, string> = {
  outside: '窗口前在区外（进入可判定）',
  inside: '窗口前已在区内',
  unknown: '前置状态未知（lookback 内无更早报位）',
}

export function priorStateLabel(state: string | null | undefined): string {
  const key = String(state ?? '')
  return PRIOR_STATE_LABELS[key] ?? dash(state)
}

export function eventFlagLabels(event: AreaEvent | null | undefined): string[] {
  if (!event) return []
  const labels: string[] = []
  if (event.near_boundary) labels.push('事件点贴近边界（<500 m），可能是边界抖动')
  if (event.wide_bracket) labels.push('证据括号偏宽（超过 gap_seconds）')
  if (event.same_second_conflict) labels.push('同一秒内内外状态冲突')
  if (event.outside_evidence_in_context === false) labels.push('区外证据不在观测上下文中')
  return labels
}

// 地图定位：用访问的首/末区内报位时间，不用事件时间（事件可能落在窗外）。
export function visitLocateArgs(visit: AreaVisit): { shipId: number; startAt: string; endAt: string } {
  return { shipId: visit.ship_id, startAt: visit.first_inside_at, endAt: visit.last_inside_at }
}

export function visitFocusArgs(visit: AreaVisit): { shipId: number; startAt: string; endAt: string; visitKey: string } {
  return {
    shipId: visit.ship_id,
    startAt: visit.first_inside_at,
    endAt: visit.last_inside_at,
    visitKey: visit.visit_key,
  }
}

export function visitDetailId(visitKey: string | null | undefined): string {
  return `aa-visit-${String(visitKey ?? '').replace(/[^A-Za-z0-9_-]/g, '-')}`
}

// —— 每日序列（趋势图；缺失字段按 0 画线，表格仍按原值显示） ——

export interface AreaDailySeries {
  dates: string[]
  shipsObserved: number[]
  entries: number[]
  exits: number[]
  hours: number[]
}

export function dailySeries(daily: readonly AreaDaily[] | null | undefined): AreaDailySeries {
  const rows = Array.isArray(daily) ? daily : []
  return {
    dates: rows.map(row => String(row?.date ?? '')),
    shipsObserved: rows.map(row => numOrNull(row?.ships_observed) ?? 0),
    entries: rows.map(row => numOrNull(row?.observed_entry_count) ?? 0),
    exits: rows.map(row => numOrNull(row?.observed_exit_count) ?? 0),
    hours: rows.map(row => numOrNull(row?.observed_ship_hours) ?? 0),
  }
}

// —— 对话联动 ——

export interface AreaConditionHint {
  mode: AreaPanelMode | null
  at: string | null
  start: string | null
  end: string | null
  startA: string | null
  endA: string | null
  startB: string | null
  endB: string | null
  shipTypes: string[] | null
}

// 读取 agentContext / pendingAction 这类不可信外部输入；无可识别字段时返回 null。
export function readAreaHint(value: unknown): AreaConditionHint | null {
  const obj = asRecord(value)
  if (!obj) return null
  const rawMode = obj.mode
  const mode: AreaPanelMode | null =
    rawMode === 'snapshot' || rawMode === 'activity' || rawMode === 'compare' ? rawMode : null
  const at = strOrNull(obj.at)
  const start = strOrNull(obj.start)
  const end = strOrNull(obj.end)
  const startA = strOrNull(obj.startA)
  const endA = strOrNull(obj.endA)
  const startB = strOrNull(obj.startB)
  const endB = strOrNull(obj.endB)
  const shipTypes = Array.isArray(obj.shipTypes)
    ? obj.shipTypes.filter((item): item is string => typeof item === 'string' && item.trim() !== '')
    : null
  if (!mode && !at && !start && !end && !startA && !endA && !startB && !endB && !shipTypes?.length) return null
  return {
    mode, at, start, end, startA, endA, startB, endB,
    shipTypes: shipTypes && shipTypes.length ? shipTypes : null,
  }
}

export interface AreaQueryDraft {
  mode: AreaPanelMode
  bounds: AreaBounds
  areaLabel: string
  areaIsDefault: boolean
  shipTypes: string[] | null
  at: string | null
  start: string | null
  end: string | null
  startA: string | null
  endA: string | null
  startB: string | null
  endB: string | null
}

// 把当前区域与条件写成可直接填入对话输入框的中文提示词。
export function areaQueryText(draft: AreaQueryDraft): string {
  const lines: string[] = []
  lines.push(`区域：${draft.areaLabel || '自定义矩形'}（${draft.areaIsDefault ? '默认分析区域' : '自定义矩形'}，${boundsText(draft.bounds)}）`)
  if (draft.mode === 'snapshot') {
    lines.push(`模式：时刻在场，时刻 ${formatUtc(draft.at)} UTC`)
  } else if (draft.mode === 'activity') {
    lines.push(`模式：时段活动，窗口 ${utcRangeText(draft.start, draft.end)}`)
  } else {
    lines.push(`模式：两时段比较，A ${utcRangeText(draft.startA, draft.endA)}；B ${utcRangeText(draft.startB, draft.endB)}`)
  }
  lines.push(`船型：${draft.shipTypes === null ? '全部' : draft.shipTypes.join('、')}`)
  return `请分析以下区域船舶活动：\n${lines.map(line => `- ${line}`).join('\n')}\n（时间均为 UTC；时段为半开区间 [start, end)，终点不含。）`
}

// —— 内部小工具 ——

function asRecord(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === 'object' && !Array.isArray(value) ? (value as Record<string, unknown>) : null
}

function asArray<T>(value: unknown): T[] {
  return Array.isArray(value) ? (value as T[]) : []
}

function numOrNull(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function strOrNull(value: unknown): string | null {
  if (typeof value !== 'string') return null
  const text = value.trim()
  return text === '' ? null : text
}

function numberList(value: unknown): number[] {
  return asArray<unknown>(value)
    .map(item => numOrNull(item))
    .filter((item): item is number => item !== null)
}

function stringList(value: unknown): string[] {
  return asArray<unknown>(value).filter((item): item is string => typeof item === 'string' && item.trim() !== '')
}
