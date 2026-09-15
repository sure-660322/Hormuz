import { ref } from 'vue'
import type { ApiEvent, ApiMapShip } from '../api'

export const displayZone = ref<'UTC' | 'Asia/Shanghai'>('UTC')
export const zoneLabel = () => displayZone.value === 'UTC' ? 'UTC' : 'UTC+8'
export const riskColors = { high: '#E24B4A', warning: '#EF9F27', selected: '#38BDF8', normal: '#2E9E6B', stale: '#7A8FA6' }
// Presentation priority for teaching events, not an upstream severity assessment.
export function eventPriority(type: string) {
  return type === 'conflict' ? 'high' : ['bad_weather', 'equipment_failure', 'navigation_control'].includes(type) ? 'warning' : 'normal'
}
export function sampleAge(ship: ApiMapShip, at: string | null) {
  return at ? Math.max(0, (Date.parse(at) - Date.parse(ship.recorded_at)) / 60000) : 0
}
export function shipStatus(ship: ApiMapShip, at: string | null) {
  return sampleAge(ship, at) > 30 ? { label: '采样陈旧', color: riskColors.stale, rank: 1 } : { label: '采样有效', color: riskColors.normal, rank: 0 }
}
export function shipShape(type: string) {
  const name = shipType(type)
  return name.includes('油') || name.includes('天然气') ? '△' : name.includes('集装箱') ? '■' : name.includes('货') ? '▶' : '◆'
}
export function projectPosition(point: GeoPoint, bearing: number, nauticalMiles: number): GeoPoint {
  const rad = Math.PI / 180, distance = nauticalMiles / 3440.065
  const lat = point.latitude * rad, lon = point.longitude * rad, angle = bearing * rad
  const nextLat = Math.asin(Math.sin(lat) * Math.cos(distance) + Math.cos(lat) * Math.sin(distance) * Math.cos(angle))
  const nextLon = lon + Math.atan2(Math.sin(angle) * Math.sin(distance) * Math.cos(lat), Math.cos(distance) - Math.sin(lat) * Math.sin(nextLat))
  return { latitude: nextLat / rad, longitude: ((nextLon / rad + 540) % 360) - 180 }
}

export const eventKinds: Record<
  string,
  { label: string; color: string; symbol: string }
> = {
  attack: { label: '袭击', color: '#B66A60', symbol: '!' },
  blockade: { label: '封锁', color: '#AA8753', symbol: '⊘' },
  passage: { label: '通航', color: '#5F927D', symbol: '↗' },
  market: { label: '市场', color: '#7791A7', symbol: '≋' },
  analysis: { label: '分析', color: '#9588A7', symbol: '◇' },
  other: { label: '其他', color: '#687681', symbol: '●' },
}
export function eventKind(type: string) {
  return (
    eventKinds[type] ?? { label: '其他事件', color: '#687681', symbol: '●' }
  )
}
export function shipType(type: string) {
  if (/[\u4e00-\u9fff]/.test(type)) return type
  const names: Record<string, string> = {
    tanker: '油轮',
    container: '集装箱船',
    container_ship: '集装箱船',
    cargo: '货船',
    bulk_carrier: '散货船',
    bulk: '散货船',
    lng: '液化天然气船',
    lng_carrier: '液化天然气船',
    lpg: '液化石油气船',
    tug: '拖轮',
    fishing: '渔船',
    passenger: '客船',
    other: '其他船舶',
  }
  return names[type.toLowerCase().replaceAll(' ', '_')] ?? '其他船舶'
}
export function formatTime(value: string | null | undefined, date = false) {
  if (!value) return '—'
  return new Intl.DateTimeFormat('zh-CN', {
    timeZone: displayZone.value,
    ...(date ? { month: '2-digit', day: '2-digit' } : {}),
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(new Date(value))
}
export interface GeoPoint {
  latitude: number
  longitude: number
}
export interface ViewBounds {
  south: number
  north: number
  west: number
  east: number
}
export interface AreaQuery {
  center: GeoPoint
  radiusNm: number
  at: string
}
export interface AreaResult {
  ships: ApiMapShip[]
  events: ApiEvent[]
  source: 'local-simulation'
}
export interface LayerState {
  countries: boolean
  ships: boolean
  tracks: boolean
  events: boolean
  seamarks: boolean
  harbours: boolean
}
export type Panel = 'events' | 'ships' | 'layers' | 'analysis' | 'agent'
export function distanceNm(a: GeoPoint, b: GeoPoint) {
  const rad = Math.PI / 180
  const dlat = (b.latitude - a.latitude) * rad
  const dlon = (b.longitude - a.longitude) * rad
  const h =
    Math.sin(dlat / 2) ** 2 +
    Math.cos(a.latitude * rad) *
      Math.cos(b.latitude * rad) *
      Math.sin(dlon / 2) ** 2
  return 3440.065 * 2 * Math.asin(Math.sqrt(Math.min(1, h)))
}
export function inBounds(p: GeoPoint, b: ViewBounds) {
  return (
    p.latitude >= b.south &&
    p.latitude <= b.north &&
    p.longitude >= b.west &&
    p.longitude <= b.east
  )
}

export type LocatedEvent = ApiEvent & GeoPoint
export function hasEventLocation(e: ApiEvent): e is LocatedEvent {
  return typeof e.latitude === 'number' && Number.isFinite(e.latitude) && Math.abs(e.latitude) <= 90
    && typeof e.longitude === 'number' && Number.isFinite(e.longitude) && Math.abs(e.longitude) <= 180
}
export function eventTimeText(e: ApiEvent) {
  return e.event_time_text || (e.event_datetime ? `${e.event_datetime.slice(0, 10)}（日期记录）` : '时间未明确')
}
export function eventCoordinates(e: ApiEvent) {
  return hasEventLocation(e) ? `${e.latitude.toFixed(4)}, ${e.longitude.toFixed(4)}` : '暂无可定位坐标'
}
export function safeNewsUrl(value: string): string | undefined {
  try { const url = new URL(value); return ['http:', 'https:'].includes(url.protocol) ? url.href : undefined }
  catch { return undefined }
}

export function eventLocationLabel(e: ApiEvent) {
  if (!hasEventLocation(e)) return '暂无定位'
  if (e.geo_method === 'multi') return '多点中心 · 非事发点'
  if (e.geo_method === 'region_centroid' || /coarse|国家中心|国家代表点|国家点/.test(e.geo_note ?? ''))
    return '区域代表点 · 非精确位置'
  return '地名代表点 · 非精确位置'
}
