import type { ApiMapShip } from '../api'

// These adapters operate on the currently loaded ship snapshot.
export interface WorkbenchService {
  searchShips(query: string, ships: ApiMapShip[]): ApiMapShip[]
}
export const localWorkbench: WorkbenchService = {
  searchShips(query, ships) {
    const q = query.trim().toLocaleLowerCase()
    return ships.filter((ship) =>
      [ship.name ?? '', ship.mmsi, ship.imo ?? ''].some((value) =>
        value.toLocaleLowerCase().includes(q),
      ),
    )
  },
}

export interface NewsItem {
  id: string
  title: string
  publishedAt: string
  sourceName: string
  sourceUrl: string
  latitude: number | null
  longitude: number | null
}
export interface ComparisonRequest {
  beforeAt: string
  afterAt: string
  bounds: { south: number; north: number; west: number; east: number }
}
export interface FutureIntelligenceService {
  // Contract only: no request or fake result until a backend is connected.
  newsNearShip(
    shipId: number,
    at: string,
    radiusNm: number,
  ): Promise<NewsItem[]>
  compare(
    request: ComparisonRequest,
  ): Promise<{ beforeCount: number; afterCount: number; source: string }>
}
