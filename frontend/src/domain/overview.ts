import type { ApiEvent, ApiMapShip } from '../api'
export const shipGroups = [
  { key: 'tanker', label: '油轮', color: '#609080' },
  { key: 'cargo', label: '货船', color: '#6088A8' },
  { key: 'other', label: '其他', color: '#9080A0' },
  { key: 'unknown', label: '类型未知', color: '#788890' },
] as const
export type ShipGroup = typeof shipGroups[number]['key']
const types: Record<string, ShipGroup> = {}
for (const t of ['油轮', 'tanker']) types[t] = 'tanker'
for (const t of ['货船', '集装箱', '集装箱船', '散货船', 'cargo', 'container', 'container_ship', 'bulk', 'bulk_carrier']) types[t] = 'cargo'
for (const t of ['备用-用于当地船舶的任务分配', '捕捞', '地效应船', '帆船航行', '符合18号决议(mob-83)的船舶', '港口供应船', '高速船', '客船', '其他类型的船舶', '其他船舶', '潜水作业', '疏浚或水下作业', '搜救船', '拖轮', '拖引', '拖引并且船长>200m或船宽>25m', '引航船', '娱乐船', '液化天然气船', '液化石油气船', 'lng', 'lng_carrier', 'lpg', 'tug', 'fishing', 'passenger', 'other']) types[t] = 'other'
export function shipGroup(type: string | null): ShipGroup {
  return types[type?.trim().toLowerCase().replaceAll(' ', '_') ?? ''] ?? 'unknown'
}
export function shipComposition(ships: ApiMapShip[]) {
  return shipGroups.map(group => {
    const count = ships.filter(ship => shipGroup(ship.ship_type) === group.key).length
    return { ...group, count, percent: ships.length ? count / ships.length * 100 : 0 }
  })
}
export function sourceEventDay(event: Pick<ApiEvent, 'occurred_at'>): string | null {
  const day = event.occurred_at?.slice(0, 10)
  if (!day || !/^\d{4}-\d{2}-\d{2}$/.test(day) || !Number.isFinite(Date.parse(event.occurred_at!))) return null
  return new Date(`${day}T00:00:00Z`).toISOString().slice(0, 10) === day ? day : null
}
export function keyEvents(events: ApiEvent[], start: string | undefined, end: string | undefined) {
  if (!start || !end || !Number.isFinite(Date.parse(start)) || !Number.isFinite(Date.parse(end))) return []
  return events.filter(event => {
    const day = sourceEventDay(event)
    return day && day >= start.slice(0, 10) && day <= end.slice(0, 10)
  }).sort((a, b) => b.coverage_count - a.coverage_count || a.event_id.localeCompare(b.event_id)).slice(0, 6)
    .sort((a, b) => a.occurred_at!.slice(0, 10).localeCompare(b.occurred_at!.slice(0, 10)) || a.event_id.localeCompare(b.event_id))
}
export function eventSeekTime(event: ApiEvent, start: string, zone: string) {
  const day = sourceEventDay(event)
  if (!day || !Number.isFinite(Date.parse(start))) return null
  const target = Date.parse(`${day}T00:00:00Z`) - (zone === 'Asia/Shanghai' ? 8 * 3600000 : 0)
  return new Date(Math.max(Date.parse(start), target)).toISOString()
}
