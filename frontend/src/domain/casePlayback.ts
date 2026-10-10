import type { ApiTrackWindow, ApiTrackWindowPoint } from '../api'

export function caseTrackChunks(from: string, to: string): [string, string][] {
  const start = Date.parse(from), end = Date.parse(to)
  if (!Number.isFinite(start) || !Number.isFinite(end) || start >= end) return []
  const chunks: [string, string][] = []
  for (let at = start; at < end; at += 86400000)
    chunks.push([new Date(at).toISOString(), new Date(Math.min(at + 86400000, end)).toISOString()])
  return chunks
}

export function mergeCaseTracks(windows: ApiTrackWindow[]): ApiTrackWindow | null {
  const first = windows[0], last = windows.at(-1)
  if (!first || !last) return null
  const unique = new Map<number, ApiTrackWindowPoint>()
  let duplicateCount = 0
  for (const window of windows) for (const segment of window.segments) for (const point of segment.points) {
    if (unique.has(point.id)) duplicateCount++
    unique.set(point.id, point)
  }
  const points = [...unique.values()].sort((a,b) => Date.parse(a.recorded_at)-Date.parse(b.recorded_at))
  const segments: ApiTrackWindow['segments'] = []
  const gaps: ApiTrackWindow['gaps'] = []
  for (const point of points) {
    const previous = segments.at(-1)?.points.at(-1)
    if (!previous || Date.parse(point.recorded_at)-Date.parse(previous.recorded_at) > first.gap_minutes*60000) {
      if (previous) gaps.push({ from: previous.recorded_at, to: point.recorded_at, minutes: (Date.parse(point.recorded_at)-Date.parse(previous.recorded_at))/60000 })
      segments.push({ segment_no: segments.length, points: [] })
    }
    segments.at(-1)!.points.push(point)
  }
  return { ...first, to: last.to, source_count: windows.reduce((n,w) => n+w.source_count,0)-duplicateCount,
    point_count: points.length, segments, gaps }
}

// 按观测时刻在合并轨迹上取位置：优先精确报位点，否则在相邻两点间线性插值。
// 处于缺报区间或覆盖范围外时返回 null，调用方不得用相邻点冒充定位成功。
export function trackPointAt(track: ApiTrackWindow | null, at: string): { latitude: number; longitude: number } | null {
  if (!track) return null
  const target = Date.parse(at)
  if (!Number.isFinite(target)) return null
  for (const segment of track.segments) {
    const points = segment.points
    if (points.length < 1) continue
    const first = Date.parse(points[0].recorded_at), last = Date.parse(points[points.length - 1].recorded_at)
    if (target < first || target > last) continue
    let previous = points[0]
    for (const point of points) {
      const recorded = Date.parse(point.recorded_at)
      if (recorded === target) return { latitude: point.latitude, longitude: point.longitude }
      if (recorded > target) {
        const span = recorded - Date.parse(previous.recorded_at)
        const ratio = span > 0 ? (target - Date.parse(previous.recorded_at)) / span : 0
        return { latitude: previous.latitude + (point.latitude - previous.latitude) * ratio,
                 longitude: previous.longitude + (point.longitude - previous.longitude) * ratio }
      }
      previous = point
    }
    return { latitude: previous.latitude, longitude: previous.longitude }
  }
  return null
}

// Clip each original segment separately: observation gaps remain gaps.
export function clipCaseTracks(track: ApiTrackWindow | null, from: string, to: string): ApiTrackWindow['segments'] {
  const start = Date.parse(from), end = Date.parse(to)
  if (!track || !Number.isFinite(start) || !Number.isFinite(end) || start > end) return []
  return track.segments.map(segment => ({ ...segment,
    points: segment.points.filter(point => {
      const at = Date.parse(point.recorded_at)
      return at >= start && at <= end
    }),
  })).filter(segment => segment.points.length > 0)
}
