export interface ApiShip{   //描述FastAPI/ships返回的数据结构
    id:number
    mmsi:string
    name:string
    ship_type:string
    flag:string | null
    imo:string | null
    callsign:string | null
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
    name: string
    ship_type: string
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
}

const API_BASE_URL = 'http://127.0.0.1:8000'    //当前的FastAPI地址

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
    throw new Error(`获取模拟时段失败：${response.status}`)
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

// 智能体 POST /agent/analyze 的请求与响应类型，字段对齐 backend/app/schemas_agent.py（契约 v2）。
export interface AgentAnalyzeRequest {
  question: string
  closure_at: string | null
  end_at: string | null
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

export interface AgentAnalyzeResponse {
  schema_version: string
  request_id: string
  status: string  // ok / no_data / partial / needs_clarification
  answer: string
  context: AgentContext
  ships: AgentShip[]
  evidence: AgentEvidence[]
  query_summary: AgentQuerySummary | null
  limitations: string[]
  clarification: string | null
}

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
