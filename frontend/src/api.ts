export interface ApiShip{   //描述FastAPI/ships返回的数据结构
    id:number
    mmsi:string
    name:string | null
    ship_type:string | null
    ship_type_cn_raw:string | null
    flag:string | null
    imo:string | null
    callsign:string | null
}

export interface ApiCaseStage {
  id: string
  title: string
  date: string
  start_at: string
  end_at: string
  summary: string
  articles: { title: string; media: string; publish_date: string; url: string; image_url: string | null; image_source_url: string | null; image_kind: string | null; summary: string }[]
}
// issue #56：证据必须有明确类型与适用范围。stage_ids 为空 = 适用于整个案例。
export type CaseEvidenceKind = 'ais_observation' | 'report' | 'boundary' | 'identity'
export interface ApiCaseEvidence {
  id: string; kind: CaseEvidenceKind; stage_ids: string[]; summary: string
  title: string; observation: string; boundary: string; at: string | null; url: string | null
}
export interface ApiMaritimeCase {
  id: string; title: string; mmsi: string; imo: string; data_source: string; supplier: string
  ready: boolean; ship_id: number | null; start_at: string | null; end_at: string | null
  position_count: number; stages: ApiCaseStage[]; limitations: string[]
  display_title?: string; vessel_label?: string; date_label?: string; overview_summary?: string
  unavailable_reason?: string; evidence?: ApiCaseEvidence[]
}
export type MaritimeCaseId = 'arctic-ocean' | 'athe-nova'
export async function fetchMaritimeCase(id: MaritimeCaseId): Promise<ApiMaritimeCase> {
  const response = await fetch(`${API_BASE_URL}/cases/${id}`, { signal: AbortSignal.timeout(20_000) })
  if (!response.ok) throw new Error(`案例加载失败：${response.status}`)
  return response.json()
}

export interface ApiShipPosition {
  id: number
  ship_id: number
  latitude: number
  longitude: number
  speed: number
  course: number
  heading: number | null
  recorded_at: string
}

export interface ApiMapShip{
    id: number
    mmsi: string
    name: string | null
    ship_type: string | null
    ship_type_cn_raw: string | null
    flag: string | null
    imo: string | null
    callsign: string | null
    latitude: number
    longitude: number
    speed: number
    course: number
    heading: number | null
    recorded_at: string
}

export interface EventRecord {
  id: number
  event_id: string
  title_zh: string
  summary_zh: string
  event_type: string
  event_datetime: string | null
  event_time_text: string | null
  event_location_text: string | null
  event_region: string | null
  event_lat: number | null
  event_lng: number | null
  geo_method: string | null
  geo_note: string | null
  coverage_count: number
  perspectives: string[]
  mentioned_vessels: string[]
  publish_date_min: string | null
  publish_date_max: string | null
}

// View aliases keep existing components readable; nullable values stay nullable.
export interface ApiEvent extends EventRecord {
  title: string
  description: string
  latitude: number | null
  longitude: number | null
  occurred_at: string | null
}
export interface ApiEventNews {
  story_id: string
  title_zh: string
  summary_zh: string
  title: string
  canonical_url: string
  media_name: string
  perspective: string
  publish_date: string
}

export function toEventView(e: EventRecord): ApiEvent {
  return { ...e, title: e.title_zh, description: e.summary_zh,
    latitude: e.event_lat, longitude: e.event_lng, occurred_at: e.event_datetime }
}

export async function fetchEventNews(eventId: string, signal?: AbortSignal): Promise<ApiEventNews[]> {
  const response = await fetch(`${API_BASE_URL}/events/${encodeURIComponent(eventId)}/news`, {
    signal: signal ? AbortSignal.any([signal, AbortSignal.timeout(20_000)]) : AbortSignal.timeout(20_000),
  })
  if (!response.ok) throw new Error(`关联新闻加载失败：${response.status}`)
  return response.json()
}

export interface ApiSimulationMeta {
  start_at: string | null
  end_at: string | null
  frame_interval_seconds: number
  frame_count: number
  ship_count: number
  position_count: number
  event_count: number
  is_simulated: boolean
  has_events: boolean
  has_derived: boolean
}

declare const __API_BASE_URL__: string
const API_BASE_URL = typeof __API_BASE_URL__ === 'undefined' ? 'http://127.0.0.1:8000' : __API_BASE_URL__

export function eventCoverUrl(eventId: string): string {
  return `${API_BASE_URL}/events/${encodeURIComponent(eventId)}/cover`
}

export async function fetchShips():Promise<ApiShip[]>{
    const response =await fetch(`${API_BASE_URL}/ships`, { signal: AbortSignal.timeout(20_000) })    //fetch：浏览器原生HTTP请求功能

    //检查HTTP状态是否为成功
    if(!response.ok){       
        throw new Error(`获取船舶数据失败：${response.status}`)
    }

    return response.json()      //把后端json转换成JavaScript数据
}

export async function fetchMapShips():Promise<ApiMapShip[]>{
    const response = await fetch(`${API_BASE_URL}/ships/map`, { signal: AbortSignal.timeout(20_000) })

    if(!response.ok)
    {
        throw new Error(`获取船舶数据失败：${response.status}`)
    }

    return response.json()
}

export async function fetchShipSnapshot(at: string, signal?: AbortSignal): Promise<ApiMapShip[]> {
  const params = new URLSearchParams({ at })
  const response = await fetch(`${API_BASE_URL}/ships/snapshot?${params}`, {
    signal: signal ? AbortSignal.any([signal, AbortSignal.timeout(20_000)]) : AbortSignal.timeout(20_000),
  })
  if (!response.ok) throw new Error(`获取船位快照失败：${response.status}`)
  return response.json()
}

export interface ApiSnapshotWindow {
  frames: { at: string; ships: ApiMapShip[] }[]
  max_age_seconds: number
}

export async function fetchShipSnapshotWindow(at: string[], signal?: AbortSignal): Promise<ApiSnapshotWindow> {
  const params = new URLSearchParams()
  at.forEach((time) => params.append('at', time))
  const response = await fetch(`${API_BASE_URL}/ships/snapshot-window?${params}`, {
    signal: signal ? AbortSignal.any([signal, AbortSignal.timeout(20_000)]) : AbortSignal.timeout(20_000),
  })
  if (!response.ok) throw new Error(`获取船位快照窗口失败：${response.status}`)
  return response.json()
}

export async function fetchShipPositions(
    shipId:number,
):Promise<ApiShipPosition[]>{
    const response = await fetch(
        `${API_BASE_URL}/ships/${shipId}/positions`,
        { signal: AbortSignal.timeout(20_000) },
    )
    if(!response.ok){
        throw new Error(`获取船舶轨迹失败：${response.status}`)
    }
    return response.json()
}

export interface ApiTrackWindowPoint {
  id: number
  latitude: number
  longitude: number
  speed: number
  recorded_at: string
}

export interface ApiTrackWindow {
  ship_id: number
  from: string
  to: string
  bucket_seconds: number
  gap_minutes: number
  source_count: number
  point_count: number
  segments: { segment_no: number; points: ApiTrackWindowPoint[] }[]
  gaps: { from: string; to: string; minutes: number }[]
}

export async function fetchShipTrackWindow(
  shipId: number, from: string, to: string, bucketSeconds: number, signal?: AbortSignal,
): Promise<ApiTrackWindow> {
  const params = new URLSearchParams({ from, to, bucket_seconds: String(bucketSeconds) })
  const response = await fetch(`${API_BASE_URL}/ships/${shipId}/track-window?${params}`, {
    signal: signal ? AbortSignal.any([signal, AbortSignal.timeout(20_000)]) : AbortSignal.timeout(20_000),
  })
  if (!response.ok) throw new Error(`获取单船轨迹失败：${response.status}`)
  return response.json()
}

export async function fetchEvents(): Promise<ApiEvent[]> {
  const response = await fetch(`${API_BASE_URL}/events`, { signal: AbortSignal.timeout(20_000) })

  if (!response.ok) {
    throw new Error(`获取事件数据失败：${response.status}`)
  }

  const records: EventRecord[] = await response.json()
  return records.map(toEventView)
}

export async function fetchSimulationMeta(): Promise<ApiSimulationMeta> {
  const response = await fetch(`${API_BASE_URL}/simulation/meta`, { signal: AbortSignal.timeout(20_000) })

  if (!response.ok) {
    throw new Error(`获取船位时段失败：${response.status}`)
  }

  return response.json()
}

export async function fetchPlaybackPositions(
  startAt: string,
  endAt: string,
): Promise<ApiShipPosition[]> {
  const params = new URLSearchParams({
    start_at: startAt,
    end_at: endAt,
  })
  const response = await fetch(`${API_BASE_URL}/ships/playback?${params}`, { signal: AbortSignal.timeout(20_000) })

  if (!response.ok) {
    throw new Error(`获取回放数据失败：${response.status}`)
  }

  return response.json()
}

// P1 派生轨迹：/api/tracks/{ship_id}（MobilityDB 派生层，几何与速度序列同源于数据库）。
export interface ApiTrackSegment {
  segment_no: number
  t_start: string | null
  t_end: string | null
  point_count: number
  geometry: { type: 'LineString'; coordinates: [number, number][] }
  speed: [number, number][]
}

export interface ApiTracksResponse {
  status: string
  ship: { id: number; mmsi: string; name: string; ship_type: string; flag: string | null }
  level: string
  bucket_seconds: number | null
  gap_minutes: number
  built_at: string
  stale: boolean
  is_simulated: boolean
  segments: ApiTrackSegment[]
}

export async function fetchShipTracks(
  shipId: number,
  from?: string,
  to?: string,
): Promise<ApiTracksResponse> {
  const params = new URLSearchParams()
  if (from && to) {
    params.set('from', from)
    params.set('to', to)
  }
  const query = params.toString()
  const response = await fetch(
    `${API_BASE_URL}/api/tracks/${shipId}${query ? `?${query}` : ''}`,
    { signal: AbortSignal.timeout(20_000) },
  )

  if (!response.ok) {
    throw new Error(`获取派生轨迹失败：${response.status}`)
  }

  return response.json()
}

// P2 事件—船舶关联：mentioned（文本证据，不指向模拟船）与 observed（模拟数据演示）严格分开。
export interface ApiEventShipLink {
  link_type: 'mentioned' | 'observed'
  vessel_name: string | null
  ship: { id: number; mmsi: string; name: string; ship_type: string } | null
  confidence: number | null
  min_distance_m: number | null
  note: string
}

export interface ApiEventShipsResponse {
  status: string
  event_id: string
  title_zh: string
  links: ApiEventShipLink[]
  built_at: string | null
}

export async function fetchEventShips(eventId: string): Promise<ApiEventShipsResponse> {
  const response = await fetch(
    `${API_BASE_URL}/api/events/${encodeURIComponent(eventId)}/ships`,
    { signal: AbortSignal.timeout(20_000) },
  )

  if (!response.ok) {
    throw new Error(`获取事件关联失败：${response.status}`)
  }

  return response.json()
}

// 智能体 POST /agent/analyze 的请求与响应类型，字段对齐 backend/app/schemas_agent.py（契约 v4）。
export interface AgentTurn {
  role: 'user' | 'assistant'
  content: string
}

// issue #40：分析面板动作（passage_analysis），打开「通行分析」并恢复该次调用的条件与结果。
export interface AgentAnalysisAction {
  type: 'passage_analysis'
  trigger: 'suggested'
  query: {
    mode: 'single' | 'compare'
    start_at?: string | null
    end_at?: string | null
    a_start_at?: string | null
    a_end_at?: string | null
    b_start_at?: string | null
    b_end_at?: string | null
    ship_types?: string[] | null
    direction?: string | null
  }
  summary: Record<string, unknown>
  tool: string
  call_id: string
}

export interface AgentAreaContextRequest {
  west: number
  south: number
  east: number
  north: number
  area_id?: string | null
  label?: string | null
}

export interface AgentAnalyzeRequest {
  question: string
  closure_at: string | null
  end_at: string | null
  history?: AgentTurn[]  // 多轮对话历史，最多最近 10 轮；单轮不传
  map_context?: { playback_at: string; target_ship_id: number | null }
  // issue #41：本请求当前选定的分析区域；后端以它为权威值，模型不得悄悄改写。
  area_context?: AgentAreaContextRequest | null
}

export interface AgentContext {
  batch: string
  ship_data_source: string
  closure_at: string
  end_at: string
  closure_source: string
  passage_rule: string
  schema_version: string
}

export interface AgentShip {
  ship_id: number
  name: string
  passage_count: number
}

export interface AgentPositionFix {
  recorded_at: string
  longitude: number
  latitude: number
}

export interface AgentEvidence {
  evidence_id: string
  ship_id: number
  direction: string
  start_fix: AgentPositionFix
  completion_fix: AgentPositionFix
  observed_completion_at: string
}

export interface AgentQuerySummary {
  position_count: number
  matched_ship_count: number
  passage_count: number
  uncertain_candidate_count: number
  coverage_start: string | null
  coverage_end: string | null
  truncated: boolean
}

// 智能体产出的「查看分析」动作（issue #41 区域活动；issue #40 另有 passage_analysis）。
export interface AgentAreaAnalysisAction {
  type: 'area_activity'
  trigger: 'suggested'
  mode: 'snapshot' | 'activity' | 'compare'
  query: {
    west: number
    south: number
    east: number
    north: number
    area_id: string | null
    area_is_default: boolean
    at?: string | null
    start_at?: string | null
    end_at?: string | null
    start_a?: string | null
    end_a?: string | null
    start_b?: string | null
    end_b?: string | null
    ship_types?: string[] | null
  }
  summary: Record<string, unknown>
  tool: string
  call_id: string
}

export interface AgentAnalyzeResponse {
  schema_version: string
  request_id: string
  status: 'ok' | 'no_data' | 'partial' | 'needs_clarification' | 'refused'
  answer: string
  context: AgentContext
  ships: AgentShip[]
  evidence: AgentEvidence[]
  query_summary: AgentQuerySummary | null
  tools_used: string[]  // 本次实际执行的工具名（执行顺序去重）
  results: Record<string, AgentToolResult>  // 各工具结构化结果，按服务端 call_id
  limitations: string[]
  clarification: string | null
  map_actions: AgentMapAction[]
  // issue #40 / #41：一次回答可能同时给出通行分析与区域活动两类「查看分析」动作，按 type 过滤。
  analysis_actions: (AgentAnalysisAction | AgentAreaAnalysisAction)[]
}

// 两类「查看分析」动作的联合类型（前端按 type 过滤后渲染各自的入口）。
export type AgentAnyAnalysisAction = AgentAnalysisAction | AgentAreaAnalysisAction

export type AgentMapAction =
  | { type: 'ship_track' | 'ship_position'; trigger: 'automatic' | 'suggested'; ship_id: number; start_at: string; end_at: string; source: 'nnu_ais'; recorded_at?: string; window_source?: string; clamp_to_coverage?: boolean }
  | { type: 'event'; trigger: 'suggested'; event_id: string; source: 'news' }

// 非通行工具的结构化结果（字段定义见 docs/agent_integration.md 与后端工具模块）
export interface AgentToolEnvelope {
  call_id: string
  tool_name: string
  status: string
}

export interface AgentToolEventNews {
  story_id: string
  media_name: string
  publish_date: string | null
  perspective: string
  title_zh: string
  url: string
}

export interface AgentToolEvent {
  event_id: string
  event_type: string
  title_zh: string
  summary_zh: string
  event_datetime: string | null
  event_time_text: string | null
  event_location_text: string | null
  event_region: string | null
  event_lat: number | null
  event_lng: number | null
  mentioned_vessels: string[]
  perspectives: string[]
  story_count: number
  news: AgentToolEventNews[]
}

export interface AgentToolEventContextResult extends AgentToolEnvelope {
  status: string
  returned_event_count: number
  truncated: boolean
  events: AgentToolEvent[]
}

export interface AgentToolShipSearchResult extends AgentToolEnvelope {
  status: string
  keyword: string
  returned_count: number
  matched_count: number
  truncated: boolean
  matches: { ship_id: number; name: string; mmsi: string; ship_type: string; flag: string | null }[]
}

export interface AgentToolShipTrackResult extends AgentToolEnvelope {
  status: string
  ship_id: number
  ship_name: string
  fix_count: number
  coverage_start: string | null
  coverage_end: string | null
}

// AG-03 query_ship_dwell 的结构化结果（字段见 docs/agent_tool_dwell.md）
export interface AgentToolDwellEntry {
  ship_id: number
  ship_name: string
  mmsi: string
  ship_type: string
  dwell_no: number
  kind: string  // at_anchor / drift / slow_transit
  enter_at: string
  leave_at: string
  duration_min: number
  displacement_radius_m: number
  max_speed_kn: number
  point_count: number
  center: { lng: number | null; lat: number | null }
  is_simulated: boolean
}

export interface AgentToolDwellResult extends AgentToolEnvelope {
  status: string  // ok / no_data / not_built
  kind: string | null
  window: [string, string] | null
  dwells: AgentToolDwellEntry[]
  returned_count: number
  matched_count: number
  truncated: boolean
  params: Record<string, unknown> | null
  built_at: string | null
  stale: boolean | null
  limitations: string[]
}

// AG-04 query_encounters 的结构化结果（字段见 docs/agent_tool_encounters.md）
export interface AgentToolEncounterPair {
  ship_a: { id: number; name: string; mmsi: string; ship_type: string }
  ship_b: { id: number; name: string; mmsi: string; ship_type: string }
  min_distance_m: number
  min_distance_nm: number
  overlap_minutes: number
  period_start: string
  period_end: string
  closest_point: { type: string; coordinates: number[] } | null
  is_simulated: boolean
}

export interface AgentToolEncountersResult extends AgentToolEnvelope {
  status: string  // ok / no_data / not_built
  window: [string, string] | null
  max_distance_nm_filter: number | null
  requested_max_distance_nm: number | null
  encounters: AgentToolEncounterPair[]
  returned_count: number
  matched_count: number
  truncated: boolean
  params: Record<string, unknown> | null
  built_at: string | null
  stale: boolean | null
  limitations: string[]
}

// AG-05 query_event_ship_links 的结构化结果（字段见 docs/agent_tool_event_ship_links.md）
export interface AgentToolEventShipLink {
  link_type: string  // observed / mentioned
  vessel_name: string | null  // mentioned：原文船名文本证据
  ship: { id: number; name: string; mmsi: string; ship_type: string } | null  // mentioned 恒为 null
  confidence: number | null
  min_distance_m: number | null
  window: unknown | null
  is_simulated: boolean | null
  note: string
}

export interface AgentToolEventShipEvent {
  event_id: string
  title_zh: string
  event_type: string
  event_datetime: string | null
  event_time_text: string | null
  publish_date_min: string | null
  publish_date_max: string | null
  representative_point: { lng: number; lat: number } | null
  confidence: number | null
  min_distance_m: number | null
  note: string
}

export interface AgentToolEventShipLinksResult extends AgentToolEnvelope {
  status: string  // ok / no_data
  direction: string  // by_event / by_ship
  event_id?: string
  title_zh?: string
  ship_id?: number
  ship_name?: string
  link_type: string
  window: [string, string] | null
  links: AgentToolEventShipLink[]
  events: AgentToolEventShipEvent[]
  returned_count: number
  built_at: string | null
  params: Record<string, unknown> | null
  limitations: string[]
}

export interface AgentToolAnalyticsResult extends AgentToolEnvelope {
  query_id: string
  columns: string[]
  rows: unknown[][]
  returned_row_count: number
  truncated: boolean
  source: {
    catalog_version: string
    views: string[]
    data_scope: Record<string, unknown>
  }
  limitations: string[]
  code?: string
  message?: string
}

export type AgentToolResult =
  | AgentToolEventContextResult
  | AgentToolShipSearchResult
  | AgentToolShipTrackResult
  | AgentToolDwellResult
  | AgentToolEncountersResult
  | AgentToolEventShipLinksResult
  | AgentToolAnalyticsResult
  | Record<string, unknown>

export interface AgentErrorDetail {
  code: string
  message: string
  request_id: string
}

// 智能体接口错误：message 为后端返回的原文，code/request_id 供面板做友好提示与定位。
export class AgentRequestError extends Error {
  code: string
  requestId: string
  constructor(detail: AgentErrorDetail | null, status: number) {
    super(detail ? detail.message : `智能体请求失败：${status}`)
    this.name = 'AgentRequestError'
    this.code = detail?.code ?? 'UNKNOWN'
    this.requestId = detail?.request_id ?? ''
  }
}

export async function fetchAgentAnalyze(
  payload: AgentAnalyzeRequest,
  signal?: AbortSignal,
): Promise<AgentAnalyzeResponse> {
  const response = await fetch(`${API_BASE_URL}/agent/analyze`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
    // 智能体后端整体预算为 60 秒（契约 v2），需覆盖该预算，不沿用新闻查询的 20 秒惯例。
    signal: signal ? AbortSignal.any([signal, AbortSignal.timeout(75_000)]) : AbortSignal.timeout(75_000),
  })
  if (!response.ok) {
    let detail: AgentErrorDetail | null = null
    try {
      const body = await response.json()
      if (body && typeof body === 'object' && body.detail && typeof body.detail === 'object' && 'code' in body.detail)
        detail = body.detail as AgentErrorDetail
    } catch {
      // 非契约错误体时按 HTTP 状态提示
    }
    throw new AgentRequestError(detail, response.status)
  }
  return response.json()
}

export function describeApiError(error: unknown, fallback: string): string {
  if (error instanceof Error && error.name === 'TimeoutError') return '数据请求超时，请重试。'
  if (error instanceof TypeError && /fetch|network/i.test(error.message)) return '无法连接数据服务，请确认后端与访问地址后重试。'
  return error instanceof Error ? error.message : fallback
}

// P3 停留识别派生层：/api/dwell（GeoJSON FeatureCollection，属性含 kind/时长/位移半径）。
export interface ApiDwellFeatureProperties {
  ship_id: number
  ship_name: string
  mmsi: string
  ship_type: string
  dwell_no: number
  kind: 'at_anchor' | 'drift' | 'slow_transit'
  enter_at: string
  leave_at: string
  duration_min: number
  displacement_radius_m: number
  max_speed_kn: number
  point_count: number
  is_simulated: boolean
}

export interface ApiDwellResponse {
  status: string
  type: 'FeatureCollection'
  features: {
    type: 'Feature'
    geometry: { type: 'Point'; coordinates: [number, number] }
    properties: ApiDwellFeatureProperties
  }[]
  feature_count: number
  truncated: boolean
  params: Record<string, unknown> | null
  built_at: string | null
  stale: boolean
  is_simulated: boolean | null
  note: string
}

export async function fetchDwell(kind?: string): Promise<ApiDwellResponse> {
  const query = kind ? `?kind=${encodeURIComponent(kind)}` : ''
  const response = await fetch(`${API_BASE_URL}/api/dwell${query}`, {
    signal: AbortSignal.timeout(20_000),
  })
  if (!response.ok) throw new Error(`获取停留识别结果失败：${response.status}`)
  return response.json()
}

// P4 相遇分析派生层：GET /api/encounters 读取，POST /api/encounters/analyze 触发重建。
export interface ApiEncounterShip {
  id: number
  name: string
  mmsi: string
  ship_type: string
}

export interface ApiEncounter {
  ship_a: ApiEncounterShip
  ship_b: ApiEncounterShip
  min_distance_m: number
  min_distance_nm: number
  overlap_minutes: number
  period_start: string
  period_end: string
  closest_point: { type: 'Point'; coordinates: [number, number] } | null
  is_simulated: boolean
}

export interface ApiEncountersReadyResponse {
  status: 'ok' | 'no_data'
  encounters: ApiEncounter[]
  count: number
  truncated: boolean
  params: Record<string, unknown> | null
  built_at: string | null
  stale: boolean
  note: string
}

export interface ApiEncountersNotBuiltResponse {
  status: 'not_built'
  message: string
}

export type ApiEncountersResponse = ApiEncountersReadyResponse | ApiEncountersNotBuiltResponse

export async function fetchEncounters(maxDistanceNm?: number): Promise<ApiEncountersResponse> {
  const query = maxDistanceNm !== undefined ? `?max_distance_nm=${maxDistanceNm}` : ''
  const response = await fetch(`${API_BASE_URL}/api/encounters${query}`, {
    signal: AbortSignal.timeout(20_000),
  })
  if (!response.ok) throw new Error(`获取相遇分析结果失败：${response.status}`)
  return response.json()
}

export interface ApiEncountersAnalyzeResponse {
  status: string
  manifest_id: number
  summary: { rows: number; ships: number; min_distance_m: number; max_distance_m: number }
  params: { distance_nm: number; overlap_min: number; sample_seconds: number }
}

export async function analyzeEncounters(
  params: { distance_nm: number; overlap_min: number; sample_seconds: number },
): Promise<ApiEncountersAnalyzeResponse> {
  const response = await fetch(`${API_BASE_URL}/api/encounters/analyze`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
    signal: AbortSignal.timeout(120_000),
  })
  if (!response.ok) throw new Error(`相遇分析失败：${response.status}`)
  return response.json()
}

// P5 数据健康：/api/data-health（源覆盖统计 + 派生层新鲜度）。
export interface ApiDataHealthDerived {
  table: string
  rows: number | null
  built_at: string | null
  stale: boolean | null
  params: Record<string, unknown> | null
  status?: string
}

export interface ApiDataHealth {
  status: string
  batch: string
  source: {
    by_data_source: {
      data_source: string
      position_count: number
      ship_count: number
      coverage_start: string | null
      coverage_end: string | null
      median_gap_minutes: number | null
    }[]
    totals: { ships: number; events: number; news: number; positions: number }
  }
  derived: ApiDataHealthDerived[]
  note: string
}

export async function fetchDataHealth(): Promise<ApiDataHealth> {
  const response = await fetch(`${API_BASE_URL}/api/data-health`, {
    signal: AbortSignal.timeout(20_000),
  })
  if (!response.ok) throw new Error(`获取数据健康状态失败：${response.status}`)
  return response.json()
}

// ---------------------------------------------------------------------------
// 动态海峡通行统计（issue #40）：手动「通行分析」面板与智能体工具共用同一后端服务。
// 日期按 UTC 自然日选择，后端使用半开区间 [start, end)。
export interface ApiPassageMetaOption {
  value: string
  label: string
  ship_count: number
}

export interface ApiPassageCoverage {
  batch_id: number | null
  kind: 'seven_day_batch' | 'case_supplement' | 'unclassified'
  kind_label: string
  position_count: number
  ship_count: number
  coverage_start: string | null
  coverage_end: string | null
}

export interface ApiPassageMeta {
  ship_type_options: ApiPassageMetaOption[]
  coverage: ApiPassageCoverage[]
  coverage_start: string | null
  coverage_end: string | null
  determination: Record<string, unknown>
  schema_version: string
}

export interface ApiDailyStats {
  day: string
  status: 'ok' | 'zero' | 'partial' | 'no_observation'
  passage_count: number
  unique_ship_count: number
  inbound_count: number
  outbound_count: number
  uncertain_candidate_count: number
  position_count: number
  window_position_count: number
  coverage_start: string | null
  coverage_end: string | null
}

export interface ApiWindowStats {
  passage_count: number
  unique_ship_count: number
  inbound_count: number
  outbound_count: number
  uncertain_candidate_count: number
  position_count: number
}

export interface ApiPassageStatistics {
  status: 'ok' | 'partial' | 'no_data'
  start_at: string
  end_at: string
  requested_days: number
  ship_types: string[] | null
  direction: string | null
  daily: ApiDailyStats[]
  window: ApiWindowStats
  determination_version: string
  schema_version: string
  data_source: string
  limitations: string[]
}

export interface ApiMetricComparison {
  metric: string
  a_value: number
  b_value: number
  delta: number
  change_rate: number | null
}

// issue #41 区域船舶活动与进出分析：/api/area-activity/*
// 口径与契约见 docs/area_activity.md §4；手动面板与智能体工具共用同一后端服务，
// 前端只调用这些函数并直接展示后端字段，不重算业务判定。
// ---------------------------------------------------------------------------

export interface ApiAreaBounds {
  west: number
  south: number
  east: number
  north: number
}

export interface ApiAreaInfo {
  area_id: string
  name: string
  version: string | null
  is_default: boolean
  basis: string
  bounds: ApiAreaBounds
  span_deg: { lat: number; lon: number }
  containment: string
}

export interface ApiAreaAlgorithm {
  name: string
  version: string
  params: Record<string, unknown>
}

export interface ApiAreaCoverage {
  source: string
  batch_ids: number[]
  batch_days: string[]
  scope_start: string | null
  scope_end: string | null
  scoped_fix_count: number | null
  region_fix_count: number | null
  window_region_fix_count: number | null
  first_fix_at: string | null
  last_fix_at: string | null
  note: string
}

export interface ApiAreaDefaultResponse {
  status: string
  area: ApiAreaInfo
  algorithm: ApiAreaAlgorithm
  limitations: string[]
}

export interface ApiAreaResolveResponse {
  status: string
  area: ApiAreaInfo
  message: string
  limitations: string[]
}

export interface ApiAreaShipTypeOption {
  value: string
  label: string
  raw_values: string[]
  count: number
  count_scope: string
}

export interface ApiAreaShipTypesResponse {
  status: string
  source: string
  total_ships: number
  ship_types: ApiAreaShipTypeOption[]
  reserved: ApiAreaShipTypeOption[]
  count: number
  limitations: string[]
}

export interface ApiAreaFix {
  id: number | null
  recorded_at: string | null
  latitude: number | null
  longitude: number | null
}

export interface ApiAreaEvent {
  observed: boolean
  observed_at: string | null
  bracket_seconds: number | null
  inside_fix: ApiAreaFix | null
  outside_fix: ApiAreaFix | null
  outside_evidence_in_context: boolean
  near_boundary: boolean
  wide_bracket: boolean
  same_second_conflict: boolean
  in_window: boolean
}

export interface ApiAreaSegment {
  segment_no: number
  start_at: string
  end_at: string
  start_fix_id: number | null
  end_fix_id: number | null
  seconds: number
  in_window_seconds: number
  fix_count: number
}

export interface ApiAreaVisit {
  visit_key: string
  ship_id: number
  ship_name: string | null
  mmsi: string | null
  ship_type: string | null
  entry: ApiAreaEvent
  exit: ApiAreaEvent
  prior_state: string
  first_inside_at: string
  last_inside_at: string
  fix_count: number
  segment_count: number
  segments: ApiAreaSegment[]
  observed_seconds: number
  window_seconds: number
  unobserved_gap_seconds: number
  started_before_window: boolean
  touches_window: boolean
  status: string
  flags: string[]
}

export interface ApiAreaDaily {
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

export interface ApiAreaSnapshotShip {
  ship_id: number
  name: string | null
  mmsi: string | null
  ship_type: string | null
  flag: string | null
  fix_id: number | null
  latitude: number
  longitude: number
  speed: number | null
  recorded_at: string
  age_seconds: number
  fresh: boolean
  inside: boolean
}

export interface ApiAreaSnapshotSummary {
  in_area_count: number
  out_of_area_fresh_count: number
  stale_fix_count: number
  evaluated_ship_count: number
  freshness_seconds: number
}

export interface ApiAreaActivitySummary {
  ships_observed: number
  observed_entry_count: number
  observed_exit_count: number
  observed_ship_seconds: number
  observed_ship_hours: number
  visit_count: number
  complete_visit_count: number
  truncated_start_visit_count: number
  truncated_end_visit_count: number
  interrupted_visit_count: number
  uncertain_visit_count: number
  prior_state_unknown_visit_count: number
  near_boundary_event_count: number
  unobserved_gap_seconds: number
}

export type ApiAreaStatus = 'ok' | 'partial' | 'no_data'

export interface ApiAreaSnapshotResponse {
  status: ApiAreaStatus
  area: ApiAreaInfo
  query: Record<string, unknown>
  algorithm: ApiAreaAlgorithm
  coverage: ApiAreaCoverage
  summary: ApiAreaSnapshotSummary
  ships: ApiAreaSnapshotShip[]
  limits: Record<string, number | boolean>
  limitations: string[]
}

export interface ApiAreaActivityResponse {
  status: ApiAreaStatus
  area: ApiAreaInfo
  query: Record<string, unknown>
  algorithm: ApiAreaAlgorithm
  coverage: ApiAreaCoverage
  summary: ApiAreaActivitySummary
  daily: ApiAreaDaily[]
  visits?: ApiAreaVisit[]
  limits: Record<string, number | boolean>
  limitations: string[]
}

export interface ApiAreaComparePeriod {
  status: ApiAreaStatus
  summary: ApiAreaActivitySummary
  coverage: ApiAreaCoverage
  daily: ApiAreaDaily[]
}

export interface ApiAreaCompareMetric {
  key: string
  label: string
  unit: string
  a: number
  b: number
  delta: number
  change_rate: number | null
}

export interface ApiPassageCompare {
  status: 'ok' | 'partial' | 'no_data'
  ship_types: string[] | null
  direction: string | null
  a: ApiPassageStatistics
  b: ApiPassageStatistics
  metrics: ApiMetricComparison[]
  a_period_days: number
  b_period_days: number
  a_avg_passages_per_day: number
  b_avg_passages_per_day: number
  windows_overlap: boolean
  comparability_notes: string[]
  determination_version: string
}

export interface ApiPassageEvidenceItem {
  evidence_id: string
  stable_key: string
  ship_id: number
  ship_name: string | null
  direction: string
  start_fix: { recorded_at: string; longitude: number; latitude: number }
  completion_fix: { recorded_at: string; longitude: number; latitude: number }
  observed_completion_at: string
  uncertain: boolean
  uncertain_reason: string | null
  ship_type: string | null
}

export interface ApiPassageEvidence {
  status: string
  page: number
  page_size: number
  returned_count: number
  matched_count: number
  confirmed_count: number
  uncertain_candidate_count: number
  page_count: number
  determination_version: string
  items: ApiPassageEvidenceItem[]
  limitations: string[]
}

export const UNKNOWN_SHIP_TYPE = '__unknown__'

export async function fetchPassageMeta(signal?: AbortSignal): Promise<ApiPassageMeta> {
  const response = await fetch(`${API_BASE_URL}/api/strait-passages/meta`, {
    signal: signal ? AbortSignal.any([signal, AbortSignal.timeout(20_000)]) : AbortSignal.timeout(20_000),
  })
  if (!response.ok) throw new Error(`获取通行统计元数据失败：${response.status}`)
  return response.json()
}

export interface PassageQuerySpec {
  ship_types?: string[] | null
  direction?: string | null
}

export async function fetchPassageStatistics(
  startAt: string, endAt: string, spec: PassageQuerySpec, signal?: AbortSignal,
): Promise<ApiPassageStatistics> {
  const response = await fetch(`${API_BASE_URL}/api/strait-passages/statistics`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ start_at: startAt, end_at: endAt, ship_types: spec.ship_types ?? null, direction: spec.direction ?? null }),
    signal: signal ? AbortSignal.any([signal, AbortSignal.timeout(60_000)]) : AbortSignal.timeout(60_000),
  })
  if (!response.ok) throw new Error(await _passageErrorMessage(response))
  return response.json()
}

export async function fetchPassageCompare(
  aStart: string, aEnd: string, bStart: string, bEnd: string,
  spec: PassageQuerySpec, signal?: AbortSignal,
): Promise<ApiPassageCompare> {
  const response = await fetch(`${API_BASE_URL}/api/strait-passages/compare`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      a_start_at: aStart, a_end_at: aEnd, b_start_at: bStart, b_end_at: bEnd,
      ship_types: spec.ship_types ?? null, direction: spec.direction ?? null,
    }),
    signal: signal ? AbortSignal.any([signal, AbortSignal.timeout(90_000)]) : AbortSignal.timeout(90_000),
  })
  if (!response.ok) throw new Error(await _passageErrorMessage(response))
  return response.json()
}

async function _passageErrorMessage(response: Response): Promise<string> {
  try {
    const body = await response.json()
    if (body && typeof body === 'object' && body.detail && typeof body.detail === 'object' && 'message' in body.detail)
      return `通行统计查询失败：${(body.detail as { message: string }).message}`
  } catch {
    // 非契约错误体按 HTTP 状态提示
  }
  return `通行统计查询失败：${response.status}`
}

export async function fetchPassageEvidence(
  startAt: string, endAt: string, params: {
    day?: string; ship_types?: string[] | null; direction?: string | null
    include_uncertain?: boolean; page?: number; page_size?: number
  }, signal?: AbortSignal,
): Promise<ApiPassageEvidence> {
  const search = new URLSearchParams({ start_at: startAt, end_at: endAt })
  if (params.day) search.set('day', params.day)
  if (params.ship_types) params.ship_types.forEach((value) => search.append('ship_types', value))
  if (params.direction) search.set('direction', params.direction)
  if (params.include_uncertain) search.set('include_uncertain', 'true')
  search.set('page', String(params.page ?? 1))
  search.set('page_size', String(params.page_size ?? 50))
  const response = await fetch(`${API_BASE_URL}/api/strait-passages/evidence?${search}`, {
    signal: signal ? AbortSignal.any([signal, AbortSignal.timeout(60_000)]) : AbortSignal.timeout(60_000),
  })
  if (!response.ok) throw new Error(await _passageErrorMessage(response))
  return response.json()
}
export interface ApiAreaCompareResponse {
  status: ApiAreaStatus
  area: ApiAreaInfo
  algorithm: ApiAreaAlgorithm
  windows: {
    a: { start: string; end: string; days: number; length_hours: number }
    b: { start: string; end: string; days: number; length_hours: number }
  }
  comparability: {
    same_area: boolean
    same_filters: boolean
    same_algorithm: boolean
    equal_length: boolean
    window_days_a: number
    window_days_b: number
    window_length_days_a: number
    window_length_days_b: number
    per_day_denominator: string
    warnings: string[]
  }
  metrics: ApiAreaCompareMetric[]
  a: ApiAreaComparePeriod
  b: ApiAreaComparePeriod
  limitations: string[]
}

export interface ApiAreaSnapshotQuery {
  at: string
  bounds: ApiAreaBounds | null
  ship_types?: string[] | null
  freshness_seconds?: number | null
  limit?: number | null
}

export interface ApiAreaActivityQuery {
  start: string
  end: string
  bounds: ApiAreaBounds | null
  ship_types?: string[] | null
  batch_ids?: number[] | null
  lookback_seconds?: number | null
  lookahead_seconds?: number | null
  visit_limit?: number | null
}

export interface ApiAreaCompareQuery {
  start_a: string
  end_a: string
  start_b: string
  end_b: string
  bounds: ApiAreaBounds | null
  ship_types?: string[] | null
  batch_ids?: number[] | null
  visit_limit?: number | null
}

// 区域活动接口错误：保留后端 detail.code / detail.message，便于区分参数错误与超时。
export class AreaRequestError extends Error {
  code: string
  requestId: string
  status: number
  constructor(code: string, message: string, requestId: string, status: number) {
    super(message)
    this.name = 'AreaRequestError'
    this.code = code
    this.requestId = requestId
    this.status = status
  }
}

async function areaRequest<T>(path: string, init: RequestInit, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    signal: signal
      ? AbortSignal.any([signal, AbortSignal.timeout(30_000)])
      : AbortSignal.timeout(30_000),
  })
  if (!response.ok) {
    let code = 'HTTP_ERROR'
    let message = `区域分析请求失败：${response.status}`
    let requestId = ''
    try {
      const body = await response.json()
      const detail = body?.detail
      if (detail && typeof detail === 'object' && typeof detail.code === 'string') {
        code = detail.code
        message = typeof detail.message === 'string' ? detail.message : message
        requestId = typeof detail.request_id === 'string' ? detail.request_id : ''
      }
    } catch {
      // 非契约错误体时保留通用提示
    }
    throw new AreaRequestError(code, message, requestId, response.status)
  }
  return response.json() as Promise<T>
}

function appendAreaBounds(params: URLSearchParams, bounds: ApiAreaBounds | null): void {
  if (!bounds) return
  params.set('west', String(bounds.west))
  params.set('south', String(bounds.south))
  params.set('east', String(bounds.east))
  params.set('north', String(bounds.north))
}

function appendShipTypes(params: URLSearchParams, shipTypes: string[] | null | undefined): void {
  // 空数组表示「全部船型」（不传参数），与后端「为空表示全部」一致。
  for (const value of shipTypes ?? []) {
    if (value) params.append('ship_type', value)
  }
}

function appendBatchIds(params: URLSearchParams, batchIds: number[] | null | undefined): void {
  for (const value of batchIds ?? []) params.append('batch_ids', String(value))
}

export async function fetchAreaDefault(): Promise<ApiAreaDefaultResponse> {
  return areaRequest<ApiAreaDefaultResponse>('/api/area-activity/default-area', { method: 'GET' })
}

export async function fetchAreaShipTypes(): Promise<ApiAreaShipTypesResponse> {
  return areaRequest<ApiAreaShipTypesResponse>('/api/area-activity/ship-types', { method: 'GET' })
}

export async function resolveAreaBounds(
  bounds: ApiAreaBounds,
  areaId?: string | null,
): Promise<ApiAreaResolveResponse> {
  return areaRequest<ApiAreaResolveResponse>('/api/area-activity/resolve-area', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      west: bounds.west,
      south: bounds.south,
      east: bounds.east,
      north: bounds.north,
      ...(areaId ? { area_id: areaId } : {}),
    }),
  })
}

export async function fetchAreaSnapshot(
  query: ApiAreaSnapshotQuery,
  signal?: AbortSignal,
): Promise<ApiAreaSnapshotResponse> {
  const params = new URLSearchParams({ at: query.at })
  appendAreaBounds(params, query.bounds)
  appendShipTypes(params, query.ship_types)
  if (query.freshness_seconds != null) params.set('freshness_seconds', String(query.freshness_seconds))
  if (query.limit != null) params.set('limit', String(query.limit))
  return areaRequest<ApiAreaSnapshotResponse>(`/api/area-activity/snapshot?${params}`, { method: 'GET' }, signal)
}

export async function fetchAreaActivity(
  query: ApiAreaActivityQuery,
  signal?: AbortSignal,
): Promise<ApiAreaActivityResponse> {
  const params = new URLSearchParams({ start: query.start, end: query.end })
  appendAreaBounds(params, query.bounds)
  appendShipTypes(params, query.ship_types)
  appendBatchIds(params, query.batch_ids)
  if (query.lookback_seconds != null) params.set('state_lookback_seconds', String(query.lookback_seconds))
  if (query.lookahead_seconds != null) params.set('state_lookahead_seconds', String(query.lookahead_seconds))
  if (query.visit_limit != null) params.set('visit_limit', String(query.visit_limit))
  return areaRequest<ApiAreaActivityResponse>(`/api/area-activity/activity?${params}`, { method: 'GET' }, signal)
}

export async function fetchAreaCompare(
  query: ApiAreaCompareQuery,
  signal?: AbortSignal,
): Promise<ApiAreaCompareResponse> {
  const params = new URLSearchParams({
    start_a: query.start_a,
    end_a: query.end_a,
    start_b: query.start_b,
    end_b: query.end_b,
  })
  appendAreaBounds(params, query.bounds)
  appendShipTypes(params, query.ship_types)
  appendBatchIds(params, query.batch_ids)
  if (query.visit_limit != null) params.set('visit_limit', String(query.visit_limit))
  return areaRequest<ApiAreaCompareResponse>(`/api/area-activity/compare?${params}`, { method: 'GET' }, signal)
}


export const fetchArcticOceanCase = () => fetchMaritimeCase('arctic-ocean')
