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
    flag: string
    imo: string | null
    callsign: string | null
    latitude: number
    longitude: number
    speed: number
    course: number
    heading: number | null
    recorded_at: string
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

  return response.json()
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

export function describeApiError(error: unknown, fallback: string): string {
  if (error instanceof Error && error.name === 'TimeoutError') return '数据请求超时，请重试。'
  if (error instanceof TypeError && /fetch|network/i.test(error.message)) return '无法连接数据服务，请确认后端与访问地址后重试。'
  return error instanceof Error ? error.message : fallback
}
