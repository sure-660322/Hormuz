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
