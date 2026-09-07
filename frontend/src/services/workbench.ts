import type { ApiMapShip, ApiEvent } from '../api'
import { distanceNm, type AreaQuery, type AreaResult } from '../domain/maritime'

// These adapters operate on the loaded simulation, never on invented AIS/news.
export interface WorkbenchService {
  searchShips(query: string, ships: ApiMapShip[]): ApiMapShip[]
  queryArea(
    query: AreaQuery,
    ships: ApiMapShip[],
    events: ApiEvent[],
  ): AreaResult
}
export const localWorkbench: WorkbenchService = {
  searchShips(query, ships) {
    const q = query.trim().toLocaleLowerCase()
    return ships.filter((ship) =>
      [ship.name, ship.mmsi, ship.imo ?? ''].some((value) =>
        value.toLocaleLowerCase().includes(q),
      ),
    )
  },
  queryArea(query, ships, events) {
    return {
      ships: ships.filter(
        (ship) => distanceNm(query.center, ship) <= query.radiusNm,
      ),
      events: events.filter(
        (event) =>
          Date.parse(event.occurred_at) <= Date.parse(query.at) &&
          distanceNm(query.center, event) <= query.radiusNm,
      ),
      source: 'local-simulation',
    }
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
