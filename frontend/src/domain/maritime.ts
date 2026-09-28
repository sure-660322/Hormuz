import { ref } from 'vue'
import type { ApiEvent, ApiMapShip } from '../api'

export const displayZone = ref<'UTC' | 'Asia/Shanghai'>('UTC')
export const zoneLabel = () => displayZone.value === 'UTC' ? 'UTC' : 'UTC+8'
export const riskColors = { high: '#E24B4A', warning: '#EF9F27', selected: '#38BDF8', normal: '#2E9E6B', stale: '#7A8FA6' }
// Presentation priority for teaching events, not an upstream severity assessment.
export function eventPriority(type: string) {
  return ['military', 'civil'].includes(type) ? 'high' : ['passage', 'energy', 'freight'].includes(type) ? 'warning' : 'normal'
}
export function sampleAge(ship: ApiMapShip, at: string | null) {
  return at ? Math.max(0, (Date.parse(at) - Date.parse(ship.recorded_at)) / 60000) : 0
}
export function shipStatus(ship: ApiMapShip, at: string | null) {
  return sampleAge(ship, at) > 30 ? { label: '采样陈旧', color: riskColors.stale, rank: 1 } : { label: '采样有效', color: riskColors.normal, rank: 0 }
}
export function shipShape(type: string | null) {
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

// 事件类别共八类（military…other）；颜色取自原设计图主色（八类设计源图已于 2026-09-28 移出仓库）。
// 图标置于 public/event-kinds/，以根路径引用（避免 workbench 裸 tsc/require 检查引入资源导入）。
export const eventKinds: Record<
  string,
  { label: string; color: string; symbol: string; icon: string }
> = {
  military: { label: '军事行动与安全事件', color: '#B06860', symbol: '盾', icon: '/event-kinds/military.png' },
  passage: { label: '海峡通行与航运动态', color: '#609080', symbol: '舶', icon: '/event-kinds/passage.png' },
  energy: { label: '能源生产与供应', color: '#C09040', symbol: '燃', icon: '/event-kinds/energy.png' },
  freight: { label: '运费与航运保险', color: '#6088A8', symbol: '险', icon: '/event-kinds/freight.png' },
  finance: { label: '金融市场与经济影响', color: '#7880B0', symbol: '市', icon: '/event-kinds/finance.png' },
  diplomacy: { label: '政治外交与政策表态', color: '#9080A0', symbol: '交', icon: '/event-kinds/diplomacy.png' },
  civil: { label: '民生影响与人员撤离', color: '#C88848', symbol: '民', icon: '/event-kinds/civil.png' },
  other: { label: '其他', color: '#788890', symbol: '他', icon: '/event-kinds/other.png' },
}
export function eventKind(type: string) {
  return (
    eventKinds[type] ?? { label: '其他', color: '#788890', symbol: '他', icon: '/event-kinds/other.png' }
  )
}
export function shipType(type: string | null) {
  if (!type) return '类型未提供'
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
export interface LayerState {
  countries: boolean
  ships: boolean
  tracks: boolean
  events: boolean
  seamarks: boolean
  harbours: boolean
  dwell: boolean
  encounters: boolean
}
export type Panel = 'overview' | 'events' | 'ships' | 'agent'
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
export function eventOccurredBy(e: Pick<ApiEvent, 'occurred_at'>, at: string | null): boolean {
  if (!e.occurred_at || !at) return false
  const eventDay = e.occurred_at.slice(0, 10)
  const current = Date.parse(at)
  if (!/^\d{4}-\d{2}-\d{2}$/.test(eventDay) || !Number.isFinite(Date.parse(e.occurred_at)) || !Number.isFinite(current)) return false
  if (new Date(`${eventDay}T00:00:00Z`).toISOString().slice(0, 10) !== eventDay) return false
  // Event timestamps often encode a calendar day without an observed hour.
  // Keep that source day fixed; compare it with the replay day in the chosen display zone.
  const offset = displayZone.value === 'Asia/Shanghai' ? 8 * 60 * 60 * 1000 : 0
  return eventDay <= new Date(current + offset).toISOString().slice(0, 10)
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
