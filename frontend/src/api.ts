export interface ApiShip{   //描述FastAPI/ships返回的数据结构
    id:number
    mmsi:string
    name:string
    ship_type:string
    flag:string
    imo:string | null
    callsign:string | null
}

export interface ApiShipPosition {
  id: number
  ship_id: number
  latitude: number
  longitude: number
  speed: number | null
  course: number | null
  heading: number | null
  recorded_at: string
  received_at?: string | null
}

export interface ApiMapShip{
    id: number
    mmsi: string
    name: string
    ship_type: string
    flag: string
    imo: string | null
    callsign: string | null
    latitude: number
    longitude: number
    speed: number | null
    course: number | null
    heading: number | null
    recorded_at: string
    received_at?: string | null
    destination?: string | null
    draught?: number | null
    length?: number | null
    width?: number | null
}

export interface ApiEvent {
  id: number
  title: string
  description: string
  event_type: string
  latitude: number
  longitude: number
  occurred_at: string
  source_name: string | null
  source_url: string | null
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

export interface ApiAisDatasetMeta {
  dataset_id: number
  name: string
  source_url: string | null
  source_version: string | null
  source_sha256: string
  start_at: string
  end_at: string
  vessel_count: number
  position_count: number
  frame_interval_seconds: number
  is_simulated: boolean
  coverage_note: string
}

export interface ApiAisVessel {
  id: number
  mmsi: string
  name: string | null
  ship_type: number | null
  flag: string | null
  destination: string | null
  draught: number | null
  length: number | null
  width: number | null
  first_seen: string
  last_seen: string
}

export interface ApiAisMapShip {
  id: number
  mmsi: string
  name: string | null
  ship_type: number | null
  flag: string | null
  destination: string | null
  draught: number | null
  length: number | null
  width: number | null
  first_seen: string
  last_seen: string
  position_id: number
  latitude: number
  longitude: number
  speed: number | null
  course: number | null
  heading: number | null
  recorded_at: string
  received_at: string | null
}

const API_BASE_URL = 'http://127.0.0.1:8000'    //当前的FastAPI地址

export async function fetchShips():Promise<ApiShip[]>{
    const response =await fetch(`${API_BASE_URL}/ships`)    //fetch：浏览器原生HTTP请求功能

    //检查HTTP状态是否为成功
    if(!response.ok){       
        throw new Error(`获取船舶数据失败：${response.status}`)
    }

    return response.json()      //把后端json转换成JavaScript数据
}

export async function fetchMapShips():Promise<ApiMapShip[]>{
    const response = await fetch(`${API_BASE_URL}/ships/map`)

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
    )
    if(!response.ok){
        throw new Error(`获取船舶轨迹失败：${response.status}`)
    }
    return response.json()
}

export async function fetchEvents(): Promise<ApiEvent[]> {
  const response = await fetch(`${API_BASE_URL}/events`)

  if (!response.ok) {
    throw new Error(`获取事件数据失败：${response.status}`)
  }

  return response.json()
}

export async function fetchSimulationMeta(): Promise<ApiSimulationMeta> {
  const response = await fetch(`${API_BASE_URL}/simulation/meta`)

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
  const response = await fetch(`${API_BASE_URL}/ships/playback?${params}`)

  if (!response.ok) {
    throw new Error(`获取回放数据失败：${response.status}`)
  }

  return response.json()
}

async function requireJson<T>(response: Response, action: string): Promise<T> {
  if (!response.ok) {
    let detail = ''
    try {
      const body = await response.json()
      detail = typeof body.detail === 'string' ? `：${body.detail}` : ''
    } catch {
      // 后端未返回 JSON 时保留 HTTP 状态作为错误依据。
    }
    throw new Error(`${action}失败（${response.status}）${detail}`)
  }
  return response.json()
}

export async function fetchAisMeta(): Promise<ApiAisDatasetMeta> {
  return requireJson(
    await fetch(`${API_BASE_URL}/ais/meta`),
    '获取 AIS 数据说明',
  )
}

export async function fetchAisVessels(): Promise<ApiAisVessel[]> {
  return requireJson(
    await fetch(`${API_BASE_URL}/ais/vessels`),
    '获取 AIS 船舶',
  )
}

export async function fetchAisMapShips(at: string): Promise<ApiAisMapShip[]> {
  const params = new URLSearchParams({ at })
  return requireJson(
    await fetch(`${API_BASE_URL}/ais/ships/map?${params}`),
    '获取历史船位快照',
  )
}

export async function fetchAisPlaybackPositions(
  startAt: string,
  endAt: string,
): Promise<ApiShipPosition[]> {
  const params = new URLSearchParams({
    start_at: startAt,
    end_at: endAt,
  })
  return requireJson(
    await fetch(`${API_BASE_URL}/ais/ships/playback?${params}`),
    '获取 AIS 回放数据',
  )
}

export async function fetchAisShipPositions(
  shipId: number,
): Promise<ApiShipPosition[]> {
  return requireJson(
    await fetch(`${API_BASE_URL}/ais/ships/${shipId}/positions`),
    '获取 AIS 原始轨迹',
  )
}
