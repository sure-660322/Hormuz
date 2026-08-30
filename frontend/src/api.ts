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