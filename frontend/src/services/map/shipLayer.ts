import * as L from 'leaflet'
import type { ApiEvent, ApiMapShip } from '../../api'
import { riskColors, shipShape, shipStatus } from '../../domain/maritime'
import { projectPosition } from '../../domain/maritime'
import type { LayerState } from '../../domain/maritime'

// 船舶渲染上下文：由 MapView 在每次渲染时从最新 props 构造，
// Leaflet 图层对象在本管理器内长期复用，与 Vue 响应式状态解耦。
export interface ShipRenderContext {
  ships: ApiMapShip[]
  selectedShipId: number | null
  nearbyShipIds: number[]
  selectedEvent: ApiEvent | null
  layers: LayerState
  isolated: boolean
  time: string | null
  vectorMinutes: number
  picking: boolean
}

interface ShipEntry {
  marker: L.Marker
  iconSignature: string
  tooltipText: string
  zIndexOffset: number
  rotor: SVGGElement | null
  lat: number
  lng: number
  vector: {
    group: L.LayerGroup
    signature: string
    attached: boolean
  } | null
}

interface ShipLayerManagerOptions {
  shipLayer: L.LayerGroup
  clusterLayer: L.LayerGroup
  vectorLayer: L.LayerGroup
  canvas: L.Canvas
  getMap: () => L.Map | undefined
  onSelectShip: (ship: ApiMapShip) => void
}

const safeText = (value: string) => {
  const el = document.createElement('span')
  el.textContent = value
  return el
}

// 船舶 Marker 增量更新：按稳定 ship id 复用 Marker 对象。
// 普通回放帧只更新 setLatLng 与 SVG 旋转角度；只有船型/颜色/选中态等
// 签名真正变化时才重建 icon DOM，避免每帧全量替换图标造成的布局抖动。
export class ShipLayerManager {
  private entries = new Map<number, ShipEntry>()
  private clusterSignature = ''
  private lastCtx: ShipRenderContext | null = null
  private options: ShipLayerManagerOptions

  constructor(options: ShipLayerManagerOptions) {
    this.options = options
  }

  update(ctx: ShipRenderContext) {
    this.lastCtx = ctx
    const { getMap } = this.options
    const map = getMap()
    if (!map) return
    const zoom = map.getZoom()
    const { ships } = ctx

    // ---- 船簇：只有网格聚合结果（缩放级别 + 聚合桶 + 数量 + 弱化态）变化时才重建 ----
    const groupedIds = new Set<number>()
    const clustering =
      (zoom < 8 || ships.length > 500) && ctx.layers.ships && !ctx.isolated
    let clusterSignature = ''
    if (clustering) {
      const buckets = new Map<string, number>()
      for (const ship of ships) {
        if (ship.id === ctx.selectedShipId || ctx.nearbyShipIds.includes(ship.id)) continue
        const p = map.project([ship.latitude, ship.longitude])
        const key = `${Math.floor(p.x / 44)}:${Math.floor(p.y / 44)}`
        const count = buckets.get(key) ?? 0
        if (count >= 1) groupedIds.add(ship.id)
        buckets.set(key, count + 1)
      }
      clusterSignature =
        zoom.toFixed(1) +
        '|' +
        (ctx.selectedEvent ? 'muted' : '') +
        '|' +
        [...buckets.entries()].sort().map(([k, c]) => `${k}=${c}`).join(';')
    }
    if (clusterSignature !== this.clusterSignature) {
      this.clusterSignature = clusterSignature
      this.options.clusterLayer.clearLayers()
      if (clustering) {
        const buckets = new Map<string, ApiMapShip[]>()
        for (const ship of ships) {
          if (ship.id === ctx.selectedShipId || ctx.nearbyShipIds.includes(ship.id)) continue
          const p = map.project([ship.latitude, ship.longitude])
          const key = `${Math.floor(p.x / 44)}:${Math.floor(p.y / 44)}`
          const group = buckets.get(key) ?? []
          group.push(ship)
          buckets.set(key, group)
        }
        for (const group of buckets.values()) {
          if (group.length < 2) continue
          group.forEach((s) => groupedIds.add(s.id))
          const lat = group.reduce((sum, s) => sum + s.latitude, 0) / group.length
          const lon = group.reduce((sum, s) => sum + s.longitude, 0) / group.length
          L.marker([lat, lon], {
            icon: L.divIcon({
              className: `ship-cluster${ctx.selectedEvent ? ' muted' : ''}`,
              html: `<span>${group.length}</span>`,
              iconSize: [34, 34],
            }),
            title: `${group.length} 艘模拟船，点击放大`,
            bubblingMouseEvents: false,
          })
            .on('click', () => {
              if (!this.lastCtx?.picking) map.setView([lat, lon], Math.min(19, map.getZoom() + 2))
            })
            .addTo(this.options.clusterLayer)
        }
      }
    }

    // ---- 船舶 Marker：创建 / 更新 / 删除 ----
    const visible = ctx.layers.ships && !ctx.isolated
    const ids = new Set<number>()
    for (const ship of ships) {
      if (groupedIds.has(ship.id)) continue
      ids.add(ship.id)
      this.updateShip(ship, ctx, zoom, visible, map)
    }
    // 消失或进入聚合的船舶：从地图上移除并释放，Marker 数量不随回放时间增长
    for (const [id, entry] of this.entries) {
      if (ids.has(id)) continue
      this.options.shipLayer.removeLayer(entry.marker)
      if (entry.vector) this.options.vectorLayer.removeLayer(entry.vector.group)
      this.entries.delete(id)
    }
  }

  private updateShip(
    ship: ApiMapShip,
    ctx: ShipRenderContext,
    zoom: number,
    layerVisible: boolean,
    map: L.Map,
  ) {
    const { shipLayer, onSelectShip } = this.options
    const selected = ship.id === ctx.selectedShipId
    const nearby = ctx.nearbyShipIds.includes(ship.id)
    const color = selected || nearby ? riskColors.selected : shipStatus(ship, ctx.time).color
    const validHeading = ship.heading !== null && ship.heading >= 0 && ship.heading < 360
    const angle = validHeading ? ship.heading! : ship.course
    const complete = selected || zoom >= 10
    const shape = shipShape(ship.ship_type)
    const path =
      complete || shape === '△'
        ? 'M14 3 20 23 14 19 8 23Z'
        : shape === '■'
          ? 'M8 8H20V20H8Z'
          : shape === '▶'
            ? 'M14 5 22 22H6Z'
            : 'M14 5 22 14 14 23 6 14Z'

    let entry = this.entries.get(ship.id)
    if (!entry) {
      const marker = L.marker([ship.latitude, ship.longitude], {
        title: ship.name,
        alt: ship.name,
        bubblingMouseEvents: false,
      })
      marker.bindTooltip(safeText(`${ship.name} · ${ship.speed.toFixed(1)} kn`), {
        direction: 'top',
      })
      marker.on('click', () => {
        const current = this.lastCtx?.ships.find((s) => s.id === ship.id)
        if (current && !this.lastCtx?.picking) onSelectShip(current)
      })
      entry = {
        marker,
        iconSignature: '',
        tooltipText: '',
        zIndexOffset: Number.NaN,
        rotor: null,
        lat: Number.NaN,
        lng: Number.NaN,
        vector: null,
      }
      this.entries.set(ship.id, entry)
    }

    // 位置：仅在坐标真正变化时调用 setLatLng
    if (ship.latitude !== entry.lat || ship.longitude !== entry.lng) {
      entry.lat = ship.latitude
      entry.lng = ship.longitude
      entry.marker.setLatLng([ship.latitude, ship.longitude])
    }

    // 图标：签名（颜色/形状/完整模式/选中）变化才重建 DOM
    const iconSignature = [color, path, complete, selected].join('|')
    if (iconSignature !== entry.iconSignature) {
      entry.iconSignature = iconSignature
      entry.rotor = null
      entry.marker.setIcon(
        L.divIcon({
          className: 'vessel-marker',
          html:
            `<svg viewBox="0 0 28 28" aria-hidden="true">` +
            `<g class="vessel-rotor" transform="rotate(0 14 14)">` +
            `<path d="${path}" fill="${color}" stroke="#EAF1F8" stroke-width="1"/>` +
            (complete ? '' : `<path d="M14 5V-2" stroke="${color}" stroke-width="2"/>`) +
            `</g>` +
            (selected
              ? '<path d="M1 8V1H8M20 1H27V8M27 20V27H20M8 27H1V20" fill="none" stroke="#38BDF8" stroke-width="1.5"/>'
              : '') +
            `</svg>`,
          iconSize: [28, 28],
          iconAnchor: [14, 14],
        }),
      )
    }
    // 弱化态只切换 CSS class，不触碰 icon DOM
    const muted = ctx.selectedShipId !== null && !selected
    const element = entry.marker.getElement()
    if (element) {
      element.classList.toggle('selected', selected)
      element.classList.toggle('muted', muted)
      if (!entry.rotor) {
        entry.rotor = element.querySelector<SVGGElement>('g.vessel-rotor')
      }
    }
    // 航向/航迹向：直接改已有 SVG 的 transform，普通帧不再重建 icon
    entry.rotor?.setAttribute('transform', `rotate(${complete ? angle : ship.course} 14 14)`)

    // tooltip：内容变化才更新
    const tooltipText = `${ship.name} · ${ship.speed.toFixed(1)} kn`
    if (tooltipText !== entry.tooltipText) {
      entry.tooltipText = tooltipText
      entry.marker.setTooltipContent(safeText(tooltipText))
    }

    const zIndexOffset = selected ? 1000 : 0
    if (zIndexOffset !== entry.zIndexOffset) {
      entry.zIndexOffset = zIndexOffset
      entry.marker.setZIndexOffset(zIndexOffset)
    }

    // 可见性：整层关闭或隔离模式下的非选中船只移出图层，Marker 保留复用
    const markerVisible = layerVisible && (!ctx.isolated || selected)
    if (markerVisible && !shipLayer.hasLayer(entry.marker)) entry.marker.addTo(shipLayer)
    else if (!markerVisible && shipLayer.hasLayer(entry.marker)) shipLayer.removeLayer(entry.marker)

    this.updateVector(ship, ctx, zoom, map, entry)
  }

  // 向量线/箭头：每个船舶一个常驻 LayerGroup，几何签名不变时完全跳过重建
  private updateVector(
    ship: ApiMapShip,
    ctx: ShipRenderContext,
    zoom: number,
    map: L.Map,
    entry: ShipEntry,
  ) {
    const { vectorLayer, canvas } = this.options
    const selected = ship.id === ctx.selectedShipId
    const active = selected || zoom >= 10
    const rank0 = shipStatus(ship, ctx.time).rank === 0
    const eligible = ctx.layers.ships && (!ctx.isolated || selected) && active && rank0

    if (!eligible) {
      if (entry.vector) {
        vectorLayer.removeLayer(entry.vector.group)
        entry.vector.attached = false
      }
      return
    }
    const nearby = ctx.nearbyShipIds.includes(ship.id)
    const color =
      selected || nearby ? riskColors.selected : riskColors.normal
    const opacity =
      (ctx.selectedEvent && !nearby) || (ctx.selectedShipId !== null && !selected) ? 0.4 : 0.9
    const hasHeading = ship.heading !== null && ship.heading >= 0 && ship.heading < 360
    // 位置/航向/速度/时间窗/缩放都会改变向量几何；签名一致时跳过全部重建
    const signature = JSON.stringify([
      Math.round(ship.latitude * 1e5),
      Math.round(ship.longitude * 1e5),
      Math.round(ship.course * 10),
      Math.round(ship.speed * 100),
      hasHeading ? Math.round(ship.heading! * 10) : null,
      ctx.vectorMinutes,
      color,
      opacity,
      Math.round(zoom * 10),
    ])
    if (entry.vector && entry.vector.signature === signature) {
      if (!entry.vector.attached) {
        vectorLayer.addLayer(entry.vector.group)
        entry.vector.attached = true
      }
      return
    }
    const group = entry.vector?.group ?? L.layerGroup()
    group.clearLayers()
    if (hasHeading) {
      const p = map.latLngToLayerPoint([ship.latitude, ship.longitude])
      const angle = (ship.heading! * Math.PI) / 180
      const head = map.layerPointToLatLng(L.point(p.x + Math.sin(angle) * 52, p.y - Math.cos(angle) * 52))
      const bow = map.layerPointToLatLng(L.point(p.x + Math.sin(angle) * 11, p.y - Math.cos(angle) * 11))
      L.polyline([bow, head], { renderer: canvas, color, weight: 1, opacity, interactive: false }).addTo(group)
    }
    const end = projectPosition(ship, ship.course, (ship.speed * ctx.vectorMinutes) / 60)
    L.polyline(
      [
        [ship.latitude, ship.longitude],
        [end.latitude, end.longitude],
      ],
      { renderer: canvas, color, weight: 2, dashArray: '4 4', opacity, interactive: false },
    ).addTo(group)
    for (let minute = 1; minute <= ctx.vectorMinutes; minute++) {
      const tick = projectPosition(ship, ship.course, (ship.speed * minute) / 60)
      L.circleMarker([tick.latitude, tick.longitude], {
        renderer: canvas,
        radius: minute === ctx.vectorMinutes ? 3 : 1.5,
        color,
        weight: 1,
        opacity,
        fillOpacity: opacity,
        interactive: false,
      }).addTo(group)
    }
    if (!entry.vector) entry.vector = { group, signature, attached: false }
    else entry.vector.signature = signature
    if (!entry.vector.attached || !vectorLayer.hasLayer(group)) {
      vectorLayer.addLayer(group)
      entry.vector.attached = true
    }
  }

  clear() {
    for (const entry of this.entries.values()) {
      this.options.shipLayer.removeLayer(entry.marker)
      if (entry.vector) this.options.vectorLayer.removeLayer(entry.vector.group)
    }
    this.entries.clear()
    this.options.clusterLayer.clearLayers()
    this.clusterSignature = ''
    this.lastCtx = null
  }
}
