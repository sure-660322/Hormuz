import * as L from 'leaflet'
import type { ApiShipPosition, ApiTrackSegment, ApiTrackWindow } from '../../api'
import { formatTime, riskColors } from '../../domain/maritime'

// 轨迹渲染上下文：track 为按回放时刻过滤后的可见报位点（随回放推进单调追加）。
export interface TrackRenderContext {
  track: ApiShipPosition[]
  visible: boolean
  layersTracks: boolean
  speedSegments: ApiTrackSegment[] | null
  windowSegments: ApiTrackWindow['segments'] | null
  backgroundSegments?: ApiTrackWindow['segments'] | null
  windowSpeedColor: boolean
  windowPointsVisible: boolean
}

interface SpeedRun {
  line: L.Polyline
  signature: string
}

interface TrackLayerManagerOptions {
  trackLayer: L.LayerGroup
  canvas: L.Canvas
}

const safeText = (value: string) => {
  const el = document.createElement('span')
  el.textContent = value
  return el
}

function speedBucketColor(v: number): string {
  return v < 3 ? '#8a97a3' : v < 8 ? '#2e9e5b' : v < 12 ? '#e6a23c' : '#d64f4f'
}

function pointMarker(point: ApiShipPosition): L.CircleMarker {
  return L.circleMarker([point.latitude, point.longitude], {
    radius: 3,
    color: riskColors.selected,
    weight: 1,
    fillColor: '#f5fafb',
    fillOpacity: 1,
  }).bindTooltip(
    safeText(
      `报位 ${formatTime(point.recorded_at, true)} · ${point.latitude.toFixed(4)}, ${point.longitude.toFixed(4)} · ${point.speed.toFixed(1)} kn · 航向 ${point.course.toFixed(0)}°`,
    ),
    { direction: 'top' },
  )
}

// 轨迹图层生命周期：
// - Polyline 一次创建，连续回放只增量 addLatLng，不再每帧重建；
// - 报位点 Marker 按“新增点”增量补齐，数量不随回放帧数增长；
// - 仅向后拖动/换船/过滤条件变化时才整体重建；
// - 速度着色按“段内连续同色 run”拆分并缓存 Polyline，几何没变时复用。
export class TrackLayerManager {
  private polyline: L.Polyline | null = null
  private renderedPoints: ApiShipPosition[] = []
  private pointMarkers: L.CircleMarker[] = []
  private speedRuns = new Map<string, SpeedRun>()
  private renderedWindowSegments: ApiTrackWindow['segments'] | null = null
  private renderedBackground: ApiTrackWindow['segments'] | null | undefined = null
  private renderedWindowSpeedColor = false
  private renderedWindowPointsVisible = false
  private options: TrackLayerManagerOptions

  constructor(options: TrackLayerManagerOptions) {
    this.options = options
  }

  update(ctx: TrackRenderContext) {
    if (!ctx.visible || !ctx.layersTracks) {
      this.clear()
      return
    }
    if (ctx.windowSegments !== null) {
      if (ctx.backgroundSegments === this.renderedBackground && ctx.windowSegments === this.renderedWindowSegments &&
          ctx.windowSpeedColor === this.renderedWindowSpeedColor &&
          ctx.windowPointsVisible === this.renderedWindowPointsVisible) return
      this.clear()
      for (const segment of ctx.backgroundSegments ?? []) {
        if (segment.points.length > 1) L.polyline(segment.points.map(p => [p.latitude, p.longitude] as L.LatLngTuple), {
          renderer: this.options.canvas, color: '#8198ac', weight: 2, opacity: 0.35, interactive: false,
        }).addTo(this.options.trackLayer)
      }
      for (const segment of ctx.windowSegments) {
        const points = segment.points
        if (points.length > 1) {
          if (ctx.windowSpeedColor) {
            let color = speedBucketColor(points[0]!.speed)
            let run: L.LatLngTuple[] = [[points[0]!.latitude, points[0]!.longitude]]
            const drawRun = () => {
              if (run.length > 1) L.polyline(run, {
                renderer: this.options.canvas, color, weight: 3, opacity: 0.9, interactive: false,
              }).addTo(this.options.trackLayer)
            }
            for (let i = 0; i < points.length - 1; i++) {
              const nextColor = speedBucketColor(points[i]!.speed)
              if (nextColor !== color) {
                drawRun()
                run = [[points[i]!.latitude, points[i]!.longitude]]
                color = nextColor
              }
              run.push([points[i + 1]!.latitude, points[i + 1]!.longitude])
            }
            drawRun()
          } else {
            L.polyline(points.map((p): L.LatLngTuple => [p.latitude, p.longitude]), {
              renderer: this.options.canvas, color: riskColors.selected, weight: 3, opacity: 0.9,
              interactive: false,
            }).addTo(this.options.trackLayer)
          }
        }
        for (const point of ctx.windowPointsVisible ? points : []) {
          L.circleMarker([point.latitude, point.longitude], {
            radius: 3, color: riskColors.selected, weight: 1, fillColor: '#fff', fillOpacity: 1,
          }).bindTooltip(safeText(
            `采样报位 ${formatTime(point.recorded_at, true)} · ${point.latitude.toFixed(4)}, ${point.longitude.toFixed(4)} · ${point.speed.toFixed(1)} kn`,
          )).addTo(this.options.trackLayer)
        }
      }
      this.renderedBackground = ctx.backgroundSegments
      this.renderedWindowSegments = ctx.windowSegments
      this.renderedWindowSpeedColor = ctx.windowSpeedColor
      this.renderedWindowPointsVisible = ctx.windowPointsVisible
      return
    }
    const points = ctx.track
    const common = this.commonPrefix(points)
    if (common === this.renderedPoints.length && common === points.length) {
      // 轨迹无变化：只需推进速度着色窗口
      this.updateSpeedRuns(ctx)
      return
    }
    if (this.polyline && common === this.renderedPoints.length) {
      // 向前追加：增量扩展 Polyline 与报位点 Marker
      for (let i = common; i < points.length; i++) this.polyline.addLatLng([points[i]!.latitude, points[i]!.longitude])
      // Marker 覆盖除最后一个点外的全部报位点：补上旧末尾点 + 新增的中间点
      for (let i = Math.max(0, this.pointMarkers.length); i < points.length - 1; i++) {
        const marker = pointMarker(points[i]!)
        marker.addTo(this.options.trackLayer)
        this.pointMarkers.push(marker)
      }
      this.renderedPoints = points
      this.updateSpeedRuns(ctx)
      return
    }
    this.rebuild(ctx)
  }

  /** 当前渲染点列与新点列的公共前缀长度（按报位记录 id 比较） */
  private commonPrefix(points: ApiShipPosition[]): number {
    const limit = Math.min(this.renderedPoints.length, points.length)
    let i = 0
    while (i < limit && this.renderedPoints[i]!.id === points[i]!.id) i++
    return i
  }

  private rebuild(ctx: TrackRenderContext) {
    this.clear()
    const points = ctx.track
    if (points.length > 1) {
      this.polyline = L.polyline(
        points.map((p): L.LatLngTuple => [p.latitude, p.longitude]),
        { renderer: this.options.canvas, color: riskColors.selected, weight: 2, opacity: 0.8, interactive: false },
      ).addTo(this.options.trackLayer)
    }
    // 用默认 SVG 渲染而非 canvas：canvas 路径的 hover tooltip 不可靠
    for (let i = 0; i < points.length - 1; i++) {
      const marker = pointMarker(points[i]!)
      marker.addTo(this.options.trackLayer)
      this.pointMarkers.push(marker)
    }
    this.renderedPoints = points
    this.updateSpeedRuns(ctx)
  }

  // 后端契约：segment.geometry 顶点与 segment.speed 序列一一对应，speed[i] = [epoch 秒, kn]。
  // 这里按顶点时间戳裁剪到当前显示的轨迹范围 [tFirst, tLast]，保证着色不多余延伸。
  private updateSpeedRuns(ctx: TrackRenderContext) {
    const track = this.renderedPoints
    const tFirst = track.length ? Date.parse(track[0]!.recorded_at) : 0
    const tLast = track.length ? Date.parse(track[track.length - 1]!.recorded_at) : Number.POSITIVE_INFINITY
    const desired = new Set<string>()
    for (const segment of ctx.speedSegments ?? []) {
      const coords = segment.geometry.coordinates
      interface Run {
        color: string
        coords: [number, number][]
      }
      let run: Run | null = null
      const runs: Run[] = []
      const flush = () => {
        if (run) runs.push(run)
        run = null
      }
      for (let i = 0; i < coords.length - 1; i++) {
        const t = (segment.speed[i]?.[0] ?? NaN) * 1000
        if (!Number.isFinite(t) || t < tFirst || t > tLast) {
          // 时间窗口外的顶点断开着色 run，着色不多余延伸
          flush()
          continue
        }
        const color = speedBucketColor(segment.speed[i]?.[1] ?? 0)
        if (!run || run.color !== color) {
          flush()
          run = { color, coords: [[coords[i]![1], coords[i]![0]]] }
        }
        run.coords.push([coords[i + 1]![1], coords[i + 1]![0]])
      }
      flush()
      let index = 0
      for (const r of runs) {
        const key = `${segment.segment_no}:${index++}`
        desired.add(key)
        const first = r.coords[0]!
        const last = r.coords[r.coords.length - 1]!
        const signature = `${r.color}|${r.coords.length}|${first[0]},${first[1]}|${last[0]},${last[1]}`
        const existing = this.speedRuns.get(key)
        if (existing && existing.signature === signature) continue
        const latLngs = r.coords as L.LatLngTuple[]
        if (existing) {
          existing.line.setStyle({ color: r.color })
          existing.line.setLatLngs(latLngs)
          existing.signature = signature
        } else if (r.coords.length > 1) {
          const line = L.polyline(latLngs, {
            renderer: this.options.canvas,
            color: r.color,
            weight: 3,
            opacity: 0.9,
            interactive: false,
          }).addTo(this.options.trackLayer)
          this.speedRuns.set(key, { line, signature })
        }
      }
    }
    for (const [key, run] of this.speedRuns) {
      if (!desired.has(key)) {
        this.options.trackLayer.removeLayer(run.line)
        this.speedRuns.delete(key)
      }
    }
  }

  clear() {
    if (this.renderedWindowSegments !== null) {
      this.options.trackLayer.clearLayers()
      this.renderedWindowSegments = null
      this.renderedWindowSpeedColor = false
      this.renderedWindowPointsVisible = false
    }
    if (this.polyline) {
      this.options.trackLayer.removeLayer(this.polyline)
      this.polyline = null
    }
    for (const marker of this.pointMarkers) this.options.trackLayer.removeLayer(marker)
    this.pointMarkers = []
    for (const run of this.speedRuns.values()) this.options.trackLayer.removeLayer(run.line)
    this.speedRuns.clear()
    this.renderedPoints = []
  }
}
