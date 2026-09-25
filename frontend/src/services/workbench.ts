import type { ApiMapShip, ApiEvent } from '../api'
import { hasEventLocation, distanceNm, type AreaQuery, type AreaResult } from '../domain/maritime'

// These adapters operate on the currently loaded ship snapshot.
export interface WorkbenchService {
  searchShips(query: string, ships: ApiMapShip[]): ApiMapShip[]
  queryArea(
    query: AreaQuery,
    ships: ApiMapShip[],
    events: ApiEvent[],
    source?: AreaResult['source'],
  ): AreaResult
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
  queryArea(query, ships, events, source = 'local-simulation') {
    return {
      ships: ships.filter(
        (ship) => distanceNm(query.center, ship) <= query.radiusNm,
      ),
      events: events.filter(
        (event) =>
          hasEventLocation(event) && event.occurred_at !== null &&
          Date.parse(event.occurred_at) <= Date.parse(query.at) &&
          distanceNm(query.center, event) <= query.radiusNm,
      ),
      source,
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
