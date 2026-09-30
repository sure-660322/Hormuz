export interface ScreenTrackPoint { x: number; y: number; speed: number }
export interface TrackArrow extends ScreenTrackPoint { angle: number }
// Chronological segment direction, with screen-space spacing and no gap bridging.
export function sparseTrackArrows(segments: ScreenTrackPoint[][], width: number, height: number): TrackArrow[] {
  const arrows: TrackArrow[] = []
  for (const points of segments) {
    let distance = 0
    let anchor = points[0]
    for (let i = 1; i < points.length; i++) {
      const a = points[i - 1]!, b = points[i]!
      const dx = b.x - a.x, dy = b.y - a.y
      const length = Math.hypot(dx, dy)
      if (!Number.isFinite(length) || length < 0.2) continue
      distance += length
      if (distance < 90) continue
      const x = (a.x + b.x) / 2, y = (a.y + b.y) / 2
      if (anchor && Math.hypot(x - anchor.x, y - anchor.y) < 20) continue
      if (x < 12 || y < 12 || x > width - 12 || y > height - 12) continue
      if (arrows.some(p => Math.hypot(p.x - x, p.y - y) < 65)) continue
      arrows.push({ x, y, speed: a.speed, angle: Math.atan2(dy, dx) * 180 / Math.PI + 90 })
      distance = 0
      anchor = b
      if (arrows.length >= 32) return arrows
    }
  }
  return arrows
}
