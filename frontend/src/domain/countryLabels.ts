import type { Feature, FeatureCollection, MultiPolygon, Polygon } from 'geojson'
import type { ViewBounds } from './maritime'

export interface CountryProperties { code: string; name_zh: string; label: [number, number] }
export type CountryFeature = Feature<Polygon | MultiPolygon, CountryProperties>
export type CountryData = FeatureCollection<Polygon | MultiPolygon, CountryProperties>

// Horizontal scan lines include every ring: holes and disconnected territories stay distinct.
export function countryLabelPosition(feature: CountryFeature, bounds: ViewBounds): [number, number] | null {
  const polygons = feature.geometry.type === 'Polygon' ? [feature.geometry.coordinates] : feature.geometry.coordinates
  const intervalsAt = (latitude: number) => polygons.flatMap(rings => {
    const intersections: number[] = []
    for (const ring of rings) for (let i = 0; i < ring.length - 1; i++) {
      const a = ring[i]!, b = ring[i + 1]!
      if ((a[1]! > latitude) !== (b[1]! > latitude))
        intersections.push(a[0]! + (latitude - a[1]!) * (b[0]! - a[0]!) / (b[1]! - a[1]!))
    }
    intersections.sort((a, b) => a - b)
    const result: [number, number][] = []
    for (let i = 0; i + 1 < intersections.length; i += 2) {
      const west = Math.max(bounds.west, intersections[i]!), east = Math.min(bounds.east, intersections[i + 1]!)
      if (east > west) result.push([west, east])
    }
    return result
  })
  const [lat, lng] = feature.properties.label
  if (lat > bounds.south && lat < bounds.north && intervalsAt(lat).some(([w, e]) => lng > w && lng < e))
    return [lat, lng]
  let best: [number, number] | null = null, score = -Infinity
  const middle = (bounds.north + bounds.south) / 2
  // Also scan each polygon's own extent, so tiny islands are not skipped at low zoom.
  for (const rings of polygons) {
    const ys = rings[0]!.map(p => p[1]!)
    const south = Math.max(bounds.south, Math.min(...ys)), north = Math.min(bounds.north, Math.max(...ys))
    if (south >= north) continue
    for (let i = 1; i < 24; i++) {
      const y = south + (north - south) * i / 24
      for (const [w, e] of intervalsAt(y)) {
        const value = Math.min(e - w, (bounds.east - bounds.west) * .65) - Math.abs(y - middle) * .2
        if (value > score) { score = value; best = [y, (w + e) / 2] }
      }
    }
  }
  return best
}
