<script setup lang="ts">
import { createCountryLayer } from '../services/countryLayer'
import { hasEventLocation, type LocatedEvent } from '../domain/maritime'
import type { ApiTrackSegment, ApiTrackWindow } from '../api'
import { onMounted, onBeforeUnmount, ref, watch } from 'vue'
import * as L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import type { ApiEvent, ApiMapShip, ApiShipPosition, ApiDwellResponse, ApiEncounter } from '../api'
import {
  displayZone,
  type LayerState,
  type ViewBounds,
} from '../domain/maritime'
import { RenderScheduler } from '../services/map/renderScheduler'
import { ShipLayerManager } from '../services/map/shipLayer'
import { EventLayerManager } from '../services/map/eventLayer'
import { TrackLayerManager } from '../services/map/trackLayer'
const props = defineProps<{
  ships: ApiMapShip[]
  events: LocatedEvent[]
  selectedShipId: number | null
  selectedEvent: ApiEvent | null
  track: ApiShipPosition[]
  trackVisible: boolean
  speedSegments: ApiTrackSegment[] | null
  windowSegments: ApiTrackWindow['segments'] | null
  backgroundSegments?: ApiTrackWindow['segments'] | null
  focusSegments?: ApiTrackWindow['segments']
  windowSpeedColor: boolean
  windowPointsVisible: boolean
  isolated: boolean
  layers: LayerState
  globalViewRequest: number
  focusShipRequest: number
  focusTrackRequest: number
  nearbyShipIds: number[]
  theme: 'dark' | 'light'
  time: string | null
  vectorMinutes: number
  trackRecent24h: boolean
  dwell: ApiDwellResponse | null
  encounters: ApiEncounter[] | null
  selectedEncounter: ApiEncounter | null
  // issue #41：分析区域矩形（独立于地图视野，缩放/平移不改变它）
  areaVisible?: boolean
  areaBounds?: { west: number; south: number; east: number; north: number } | null
  areaLabel?: string
  areaMeta?: string
  areaIsDefault?: boolean
  areaDrawing?: boolean
  // issue #56：案例证据「定位地图」的观测点高亮；null 时清除。
  locatePoint?: { latitude: number; longitude: number; at: string } | null
}>()
const emit = defineEmits<{
  selectShip: [ship: ApiMapShip]
  selectEvent: [event: ApiEvent]
  boundsChange: [bounds: ViewBounds]
  harbourStatus: [status: string]
  countryStatus: [status: string]
  clearSelection: []
  selectEncounter: [encounter: ApiEncounter]
  areaDrawn: [bounds: { west: number; south: number; east: number; north: number }]
  areaDrawCancel: []
}>()
const container = ref<HTMLElement | null>(null)
const tileError = ref(false)
let map: L.Map | undefined
let countryLayer: ReturnType<typeof createCountryLayer> | undefined
let observer: ResizeObserver | undefined
let shipLayer: L.LayerGroup,
  eventLayer: L.LayerGroup,
  trackLayer: L.LayerGroup,
  harbourLayer: L.LayerGroup,
  dwellLayer: L.LayerGroup,
  encounterLayer: L.LayerGroup,
  areaLayer: L.LayerGroup
let seamarks: L.TileLayer
let vectorLayer: L.LayerGroup, clusterLayer: L.LayerGroup
let canvas: L.Canvas
let shipManager: ShipLayerManager
let eventManager: EventLayerManager
let trackManager: TrackLayerManager
let locateLayer: L.LayerGroup
// 统一渲染调度：watcher 只入队最新状态，实际渲染按浏览器帧批量执行（latest-state-wins）
const scheduler = new RenderScheduler()
let initialFitDone = false
let harbourRequest: AbortController | null = null
let harbourTimer: ReturnType<typeof setTimeout> | undefined
const center: L.LatLngTuple = [26.35, 56.5]
const safeText = (value: string) => {
  const el = document.createElement('span')
  el.textContent = value
  return el
}
// ---- 渲染任务：每次执行时读取最新 props，只提交增量差异到 Leaflet ----
function scheduleShips() {
  scheduler.schedule('ships', () => {
    shipManager.update({
      ships: props.ships,
      selectedShipId: props.selectedShipId,
      nearbyShipIds: props.nearbyShipIds,
      selectedEvent: props.selectedEvent,
      layers: props.layers,
      isolated: props.isolated,
      time: props.time,
      vectorMinutes: props.vectorMinutes,
    })
    if (!initialFitDone && props.ships.length) {
      initialFitDone = true
      if (!props.backgroundSegments) globalView()
    }
  })
}
function scheduleEvents() {
  scheduler.schedule('events', () => {
    eventManager.update({
      events: props.events,
      selectedEvent: props.selectedEvent,
      layers: props.layers,
      isolated: props.isolated,
    })
  })
}
function scheduleTrack() {
  scheduler.schedule('tracks', () => {
    // 默认展示全部已回放报位点；开启“只看最近 24h”时按回放时刻前溯过滤。
    const cutoff = props.trackRecent24h && props.time
      ? Date.parse(props.time) - 24 * 60 * 60 * 1000
      : null
    const track = cutoff === null
      ? props.track
      : props.track.filter((p) => Date.parse(p.recorded_at) >= cutoff)
    trackManager.update({
      track,
      visible: props.trackVisible,
      layersTracks: props.layers.tracks,
      speedSegments: props.speedSegments,
      windowSegments: props.windowSegments,
      backgroundSegments: props.backgroundSegments,
      windowSpeedColor: props.windowSpeedColor,
      windowPointsVisible: props.windowPointsVisible,
    })
  })
}
const dwellKindMeta: Record<string, { label: string; color: string }> = {
  at_anchor: { label: '锚泊', color: '#2E9E6B' },
  drift: { label: '漂航', color: '#EF9F27' },
  slow_transit: { label: '慢速航行', color: '#7A8FA6' },
}
// 停留识别图层：按 (ship_id, dwell_no) 稳定建点，数据变化只做增量增删
const dwellMarkers = new Map<string, L.CircleMarker>()
// 相遇图层：按 (ship_a, ship_b, period_start, 最近距离) 稳定建点，选中态变化只 setStyle
const encounterMarkers = new Map<string, { circle: L.CircleMarker; signature: string }>()
let encounterSelectionCircle: L.Circle | null = null
function scheduleDerived() {
  scheduler.schedule('derived', () => {
    renderDwell()
    renderEncounters()
  })
}
function renderDwell() {
  if (!map) return
  const show = props.layers.dwell && !props.isolated && props.dwell
  const keys = new Set<string>()
  if (show && props.dwell) {
    for (const feature of props.dwell.features) {
      const [lng, lat] = feature.geometry.coordinates
      const p = feature.properties
      const key = `${p.ship_id}:${p.dwell_no}`
      keys.add(key)
      if (dwellMarkers.has(key)) continue
      const meta = dwellKindMeta[p.kind] ?? dwellKindMeta.slow_transit!
      const marker = L.circleMarker([lat, lng], {
        radius: 5,
        color: meta.color,
        weight: 1.5,
        fillColor: meta.color,
        fillOpacity: 0.55,
      }).bindTooltip(
        safeText(
          `${p.ship_name} · ${meta.label} ${(p.duration_min / 60).toFixed(1)} 小时 · ` +
          `位移半径 ${Math.round(p.displacement_radius_m)} m · 最大 ${p.max_speed_kn.toFixed(1)} kn` +
          `（基于船位识别）`,
        ),
        { direction: 'top' },
      )
      dwellMarkers.set(key, marker)
      marker.addTo(dwellLayer)
    }
  }
  for (const [key, marker] of dwellMarkers) {
    if (keys.has(key)) continue
    dwellLayer.removeLayer(marker)
    dwellMarkers.delete(key)
  }
}
function renderEncounters() {
  if (!map) return
  const show = !props.isolated && props.encounters !== null && props.layers.encounters
  const selected = props.selectedEncounter
  const keys = new Set<string>()
  if (show && props.encounters) {
    for (const enc of props.encounters) {
      if (!enc.closest_point) continue
      const [lng, lat] = enc.closest_point.coordinates
      const isSel = selected === enc
      // min_distance_m 进 key：受控重建后闭包携带的是旧对象，重建避免选中高亮失效
      const key = `${enc.ship_a.id}:${enc.ship_b.id}:${enc.period_start}:${Math.round(enc.min_distance_m)}`
      keys.add(key)
      let entry = encounterMarkers.get(key)
      if (!entry) {
        const circle = L.circleMarker([lat, lng], { bubblingMouseEvents: false })
          .on('click', () => {
            emit('selectEncounter', enc)
          })
        entry = { circle, signature: '' }
        encounterMarkers.set(key, entry)
      }
      const signature = JSON.stringify([isSel, enc.min_distance_nm, enc.overlap_minutes])
      if (entry.signature !== signature) {
        entry.signature = signature
        const radius = Math.max(4, Math.min(10, 10 - enc.min_distance_nm))
        entry.circle.setStyle({
          radius: isSel ? radius + 3 : radius,
          color: isSel ? '#38BDF8' : '#9588A7',
          weight: isSel ? 2.5 : 1.5,
          fillColor: '#9588A7',
          fillOpacity: isSel ? 0.85 : 0.5,
        })
        entry.circle.bindTooltip(
          safeText(
            `${enc.ship_a.name} × ${enc.ship_b.name} · 最近 ${enc.min_distance_nm.toFixed(2)} NM` +
            ` · 时间重叠 ${(enc.overlap_minutes / 60).toFixed(1)} 小时（时空邻近，不代表实际交互）`,
          ),
          { direction: 'top' },
        )
      }
      if (!encounterLayer.hasLayer(entry.circle)) entry.circle.addTo(encounterLayer)
    }
  }
  for (const [key, entry] of encounterMarkers) {
    if (keys.has(key)) continue
    encounterLayer.removeLayer(entry.circle)
    encounterMarkers.delete(key)
  }
  if (selected?.closest_point && show) {
    const [lng, lat] = selected.closest_point.coordinates
    const radius = Math.max(selected.min_distance_m, 150)
    if (!encounterSelectionCircle) {
      encounterSelectionCircle = L.circle([lat, lng], {
        radius,
        color: '#38BDF8',
        weight: 1.5,
        dashArray: '4 4',
        fillOpacity: 0.05,
        interactive: false,
      }).addTo(encounterLayer)
    } else {
      encounterSelectionCircle.setLatLng([lat, lng])
      encounterSelectionCircle.setRadius(radius)
      if (!encounterLayer.hasLayer(encounterSelectionCircle)) encounterSelectionCircle.addTo(encounterLayer)
    }
  } else if (encounterSelectionCircle) {
    encounterLayer.removeLayer(encounterSelectionCircle)
    encounterSelectionCircle = null
  }
}
function emitBounds() {
  if (!map) return
  const b = map.getBounds()
  emit('boundsChange', {
    south: b.getSouth(),
    north: b.getNorth(),
    west: b.getWest(),
    east: b.getEast(),
  })
}
// ---- issue #41：分析区域矩形（显示、手动圈选）----
// 分析与地图视野解耦：缩放/平移不改变矩形；重新圈选框在松手后交给后端校验，
// 校验失败时由父组件回滚 bounds，这里只负责呈现当前生效的矩形。
type AreaRect = { west: number; south: number; east: number; north: number }
const AREA_STYLE: L.PathOptions = {
  color: '#38BDF8',
  weight: 1.6,
  dashArray: '6 5',
  fillColor: '#38BDF8',
  fillOpacity: 0.07,
  interactive: false,
}
const DRAW_STYLE: L.PathOptions = {
  color: '#F0B45A',
  weight: 1.4,
  dashArray: '4 4',
  fillColor: '#F0B45A',
  fillOpacity: 0.12,
  interactive: false,
}
let areaRect: L.Rectangle | null = null
let drawRect: L.Rectangle | null = null
let drawStart: L.LatLng | null = null
let drawing = false

function areaLatLngs(bounds: AreaRect): L.LatLngBounds {
  return L.latLngBounds([bounds.south, bounds.west], [bounds.north, bounds.east])
}

function formatCoord(value: number): string {
  return value.toFixed(3)
}

function areaTooltipHtml(bounds: AreaRect): string {
  const label = props.areaLabel || '分析区域'
  const meta = props.areaMeta ? ` · ${props.areaMeta}` : ''
  const tag = props.areaIsDefault ? '默认项目分析区域' : '自选矩形'
  return (
    `<strong>${label}</strong>（${tag}）${meta}<br/>` +
    `${formatCoord(bounds.south)}–${formatCoord(bounds.north)}°N · ` +
    `${formatCoord(bounds.west)}–${formatCoord(bounds.east)}°E<br/>` +
    '半开区间：西/南含、东/北不含；缩放平移地图不改变该区域'
  )
}

function scheduleArea() {
  scheduler.schedule('area', renderArea)
}

function renderArea() {
  if (!map || !areaLayer) return
  const bounds = props.areaBounds
  if (!bounds || !props.areaVisible) {
    if (areaRect) {
      areaLayer.removeLayer(areaRect)
      areaRect = null
    }
    return
  }
  const latLngs = areaLatLngs(bounds)
  if (!areaRect) {
    areaRect = L.rectangle(latLngs, AREA_STYLE).addTo(areaLayer)
  } else {
    areaRect.setBounds(latLngs)
  }
  areaRect.bindTooltip(areaTooltipHtml(bounds), { direction: 'top', sticky: true })
}

function cancelDraw() {
  if (!drawing && !drawRect) {
    if (props.areaDrawing) emit('areaDrawCancel')
    return
  }
  drawing = false
  drawStart = null
  if (drawRect && areaLayer) {
    areaLayer.removeLayer(drawRect)
    drawRect = null
  }
  emit('areaDrawCancel')
}

function onAreaDrawStart(rawEvent: Event) {
  const event = rawEvent as MouseEvent
  if (!map || !areaLayer || !props.areaDrawing || event.button !== 0) return
  drawing = true
  drawStart = map.mouseEventToLatLng(event)
  if (drawRect) {
    areaLayer.removeLayer(drawRect)
    drawRect = null
  }
  drawRect = L.rectangle(L.latLngBounds(drawStart, drawStart), DRAW_STYLE).addTo(areaLayer)
}

function onAreaDrawing(rawEvent: Event) {
  if (!drawing || !drawStart || !drawRect || !map) return
  drawRect.setBounds(L.latLngBounds(drawStart, map.mouseEventToLatLng(rawEvent as MouseEvent)))
}

function onAreaDrawEnd() {
  if (!drawing) return
  drawing = false
  drawStart = null
  const rectangle = drawRect
  drawRect = null
  if (rectangle && areaLayer) areaLayer.removeLayer(rectangle)
  if (!rectangle) return
  const b = rectangle.getBounds()
  const spanLat = b.getNorth() - b.getSouth()
  const spanLon = b.getEast() - b.getWest()
  // 明显是误触（跨度小于 0.01°，约 1 km）时不算一次圈选；其余一律交后端校验，
  // 前端不自行决定跨度上限（与 REST 拒绝规则保持单一事实来源）。
  if (spanLat < 0.01 || spanLon < 0.01) {
    emit('areaDrawCancel')
    return
  }
  emit('areaDrawn', {
    west: b.getWest(),
    south: b.getSouth(),
    east: b.getEast(),
    north: b.getNorth(),
  })
}

function onAreaKeyDown(event: KeyboardEvent) {
  if (event.key === 'Escape' && props.areaDrawing) cancelDraw()
}

function focusArea() {
  const bounds = props.areaBounds
  if (!map || !bounds) return false
  map.stop()
  map.fitBounds(areaLatLngs(bounds), { padding: [40, 40], animate: false })
  return true
}

function smoothlyCenterOn(point: L.LatLngExpression) {
  if (!map) return
  const reduceMotion = window.matchMedia(
    '(prefers-reduced-motion: reduce)',
  ).matches
  map.flyTo(point, map.getZoom(), {
    animate: !reduceMotion,
    duration: reduceMotion ? undefined : 0.55,
    easeLinearity: 0.22,
  })
}
function focusShip() {
  const ship = props.ships.find((s) => s.id === props.selectedShipId)
  if (ship && map) {
    map.stop()
    map.fitBounds(L.latLngBounds([[ship.latitude, ship.longitude]]), {
      ...focusPadding(), maxZoom: Math.max(map.getZoom(), 10), animate: false,
    })
  }
}
function focusPadding() {
  const area = container.value?.getBoundingClientRect()
  const panel = container.value?.closest('.workbench')?.querySelector('.inspector')?.getBoundingClientRect()
  const casePanel = container.value?.closest('.workbench')?.querySelector('.case-panel')?.getBoundingClientRect()
  let left = 40, right = 40, bottom = 40
  if (area && casePanel && casePanel.width) {
    if (area.width <= 760) bottom = Math.min(area.height - 100, area.bottom - casePanel.top + 20)
    else left = Math.min(area.width * 0.55, casePanel.right - area.left + 25)
  }
  if (area && panel && panel.width && panel.height && panel.left < area.right && panel.top < area.bottom) {
    if (panel.height > area.height * 0.7) right = Math.min(area.width - 100, area.right - panel.left + 30)
    else bottom = Math.min(area.height - 100, area.bottom - panel.top + 30)
  }
  return { paddingTopLeft: L.point(left, 40), paddingBottomRight: L.point(right, bottom) }
}
async function confirmFocus(shipId: number, withTrack: boolean): Promise<boolean> {
  // Wait for the existing render queue and camera animation before reporting success.
  for (let attempt = 0; attempt < 20; attempt++) {
    if (!map || props.selectedShipId !== shipId) return false
    const ship = props.ships.find(item => item.id === shipId)
    const points = withTrack ? (props.windowSegments ?? []).flatMap(segment => segment.points) : []
    const padding = focusPadding().paddingBottomRight
    const visible = (latitude: number, longitude: number) => {
      const point = map!.latLngToContainerPoint([latitude, longitude]), size = map!.getSize()
      return point.x >= 0 && point.y >= 0 && point.x <= size.x - padding.x + 30 && point.y <= size.y - padding.y + 30
    }
    if (ship && container.value?.querySelector('.vessel-marker.selected') && props.layers.ships &&
        visible(ship.latitude, ship.longitude) &&
        (!withTrack || (props.trackVisible && props.layers.tracks && trackLayer.getLayers().length > 0 && points.length >= 2 && points.every(point => visible(point.latitude, point.longitude))))) return true
    await new Promise(resolve => setTimeout(resolve, 100))
  }
  return false
}
function captureView() {
  if (!map) return null
  const c = map.getCenter()
  return { latitude: c.lat, longitude: c.lng, zoom: map.getZoom() }
}
function restoreView(view: { latitude: number; longitude: number; zoom: number } | null) {
  if (map && view) { map.stop(); map.setView([view.latitude, view.longitude], view.zoom, { animate: false }) }
}
defineExpose({ confirmFocus, captureView, restoreView, focusArea, cancelAreaDraw: cancelDraw })
async function loadHarbours() {
  harbourRequest?.abort()
  if (!map || !props.layers.harbours || props.isolated) return
  const request = new AbortController()
  harbourRequest = request
  emit('harbourStatus', '加载中')
  const b = map.getBounds(),
    zoom = Math.round(map.getZoom())
  const params = new URLSearchParams({
    b: b.getSouth().toFixed(5),
    t: b.getNorth().toFixed(5),
    l: b.getWest().toFixed(5),
    r: b.getEast().toFixed(5),
    ucid: '0',
    maxSize: String(zoom >= 10 ? 6 : zoom >= 8 ? 3 : 2),
    zoom: String(zoom),
  })
  const timeout = setTimeout(() => request.abort(), 10000)
  try {
    const response = await fetch(
      `https://harbour.openseamap.org/getHarbours.php?${params}`,
      { signal: request.signal },
    )
    if (!response.ok) throw new Error('港口服务不可用')
    const text = await response.text()
    if (harbourRequest !== request || !map) return
    harbourLayer.clearLayers()
    // Parse legacy data as text; never execute third-party JavaScript.
    const pattern =
      /putHarbourMarker\(\s*[^,]+,\s*([-\d.]+),\s*([-\d.]+),\s*'([^']*)'/g
    let match: RegExpExecArray | null,
      count = 0
    while ((match = pattern.exec(text))) {
      const lon = Number(match[1]),
        lat = Number(match[2])
      if (!Number.isFinite(lon) || !Number.isFinite(lat)) continue
      L.marker([lat, lon], {
        icon: L.divIcon({
          className: 'harbour-marker',
          html: '⚓',
          iconSize: [22, 22],
        }),
        title: match[3],
      })
        .bindTooltip(safeText(match[3] ?? '港口'))
        .addTo(harbourLayer)
      count++
    }
    emit(
      'harbourStatus',
      count ? `当前视野 ${count} 个` : '当前视野暂无港口返回',
    )
  } catch {
    if (harbourRequest === request && map) {
      harbourLayer.clearLayers()
      emit('harbourStatus', '在线服务暂不可用，关闭后可重试')
    }
  } finally {
    clearTimeout(timeout)
  }
}
function syncLayers() {
  if (!map) return
  void countryLayer?.setVisible(props.layers.countries)
  if (props.layers.seamarks) {
    if (!map.hasLayer(seamarks)) seamarks.addTo(map)
  } else seamarks.remove()
  if (props.layers.harbours && !props.isolated) {
    if (!map.hasLayer(harbourLayer)) harbourLayer.addTo(map)
    void loadHarbours()
  } else {
    harbourRequest?.abort()
    harbourRequest = null
    harbourLayer.remove()
  }
  scheduleShips()
  scheduleEvents()
  scheduleTrack()
  scheduleDerived()
}
watch(
  () => [props.ships, props.selectedShipId, props.nearbyShipIds, props.selectedEvent, props.vectorMinutes],
  scheduleShips,
)
watch(() => [props.events, props.selectedEvent, props.time, displayZone.value], scheduleEvents)
watch(() => [props.track, props.trackVisible, props.trackRecent24h, props.time, props.speedSegments, props.windowSegments, props.backgroundSegments, props.windowSpeedColor, props.windowPointsVisible, displayZone.value], scheduleTrack)
watch(() => [props.dwell, props.encounters, props.selectedEncounter, props.isolated], scheduleDerived)
// 从概览面板选中相遇时，地图飞到最近接近点并保证相遇图层可见。
watch(() => props.selectedEncounter, (enc) => {
  if (!map || !enc?.closest_point) return
  const [lng, lat] = enc.closest_point.coordinates
  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  map.flyTo([lat, lng], Math.max(map.getZoom(), 9), { duration: reduceMotion ? 0 : 0.6 })
})
watch(() => [props.layers, props.isolated], syncLayers, { deep: true })
watch(() => props.focusShipRequest, focusShip)
watch(() => props.focusTrackRequest, () => {
  const points = (props.focusSegments ?? props.windowSegments ?? []).flatMap(segment => segment.points)
  if (map && points.length) { map.stop(); map.fitBounds(
    L.latLngBounds(points.map(point => [point.latitude, point.longitude] as L.LatLngTuple)),
    { ...focusPadding(), maxZoom: 11, animate: false },
  ) }
})
// issue #56：证据「定位地图」的观测点高亮。只随最新定位请求更新，旧动画不覆盖新定位。
watch(() => props.locatePoint, (point) => {
  if (!map) return
  locateLayer.clearLayers()
  if (!point) return
  const icon = L.divIcon({
    className: 'case-locate-marker',
    html: '<span class="case-locate-dot"></span><span class="case-locate-ring"></span>',
    iconSize: [28, 28],
    iconAnchor: [14, 14],
  })
  L.marker([point.latitude, point.longitude], { icon, interactive: false, keyboard: false, zIndexOffset: 800 }).addTo(locateLayer)
  smoothlyCenterOn([point.latitude, point.longitude])
})
watch(
  () => props.selectedEvent,
  (event) => {
    if (event && hasEventLocation(event)) smoothlyCenterOn([event.latitude, event.longitude])
  },
)
watch(() => props.globalViewRequest, globalView)
watch(
  () => [props.areaVisible, props.areaBounds, props.areaLabel, props.areaMeta, props.areaIsDefault],
  scheduleArea,
)
watch(() => props.areaDrawing, (active) => {
  if (!map) return
  if (active) {
    // 观察模式：禁用地图拖动，左键拖拽交给圈选逻辑
    map.dragging.disable()
    map.getContainer().classList.add('area-draw-ready')
  } else {
    map.dragging.enable()
    map.getContainer().classList.remove('area-draw-ready', 'area-drawing')
    if (drawRect && areaLayer) {
      areaLayer.removeLayer(drawRect)
      drawRect = null
    }
    drawing = false
    drawStart = null
  }
})
watch(
  () => props.trackVisible,
  (visible) => {
    if (visible && props.track.length > 1)
      map?.fitBounds(
        L.latLngBounds(
          props.track.map((p) => [p.latitude, p.longitude] as L.LatLngTuple),
        ),
        { padding: [70, 70], maxZoom: 11, animate: false },
      )
  },
)
function globalView() {
  if (props.ships.length)
    map?.fitBounds(
      L.latLngBounds(
        props.ships.map((s) => [s.latitude, s.longitude] as L.LatLngTuple),
      ),
      {
        paddingTopLeft: [65, 85],
        paddingBottomRight: [60, 105],
        maxZoom: 8,
        animate: false,
      },
    )
  else map?.setView(center, 8, { animate: false })
}
onMounted(() => {
  if (!container.value) return
  map = L.map(container.value, { zoomControl: false, minZoom: 3, preferCanvas: true, keyboard: false }).setView(
    center,
    8,
  )
  L.control
    .zoom({
      position: 'bottomright',
      zoomInTitle: '放大地图',
      zoomOutTitle: '缩小地图',
    })
    .addTo(map)
  L.control.scale({ position: 'bottomleft', imperial: false }).addTo(map)
  // 底图瓦片地址可配置：本地/自建服务用 VITE_TILE_URL 指向 nginx 瓦片服务；
  // 不配置时回退到 OSM 官方瓦片。自建瓦片目前只下载到 z12，默认相应限制缩放上限。
  const tileUrl: string =
    import.meta.env.VITE_TILE_URL ?? 'https://tile.openstreetmap.org/{z}/{x}/{y}.png'
  const tileMaxZoom = Number(import.meta.env.VITE_TILE_MAX_ZOOM ?? (import.meta.env.VITE_TILE_URL ? 12 : 19))
  const basemap = L.tileLayer(
    tileUrl,
    {
      className: 'neutral-basemap',
      maxZoom: tileMaxZoom,
      attribution:
        import.meta.env.VITE_TILE_ATTRIBUTION ??
        '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
    },
  ).addTo(map)
  basemap.on('tileerror', () => {
    tileError.value = true
  })
  basemap.on('tileload', () => {
    tileError.value = false
  })
  seamarks = L.tileLayer(
    'https://tiles.openseamap.org/seamark/{z}/{x}/{y}.png',
    {
      maxZoom: 18,
      attribution:
        'Seamarks &copy; <a href="https://www.openseamap.org">OpenSeaMap</a>',
    },
  )
  countryLayer = createCountryLayer(map, status => emit('countryStatus', status))
  canvas = L.canvas({ padding: 0.5 })
  vectorLayer = L.layerGroup().addTo(map)
  clusterLayer = L.layerGroup().addTo(map)
  trackLayer = L.layerGroup().addTo(map)
  shipLayer = L.layerGroup().addTo(map)
  eventLayer = L.layerGroup().addTo(map)
  harbourLayer = L.layerGroup()
  dwellLayer = L.layerGroup().addTo(map)
  encounterLayer = L.layerGroup().addTo(map)
  areaLayer = L.layerGroup().addTo(map)
  locateLayer = L.layerGroup().addTo(map)
  shipManager = new ShipLayerManager({
    shipLayer,
    clusterLayer,
    vectorLayer,
    canvas,
    getMap: () => map,
    onSelectShip: (ship) => { if (!props.areaDrawing) emit('selectShip', ship) },
  })
  eventManager = new EventLayerManager({
    eventLayer,
    getMap: () => map,
    onSelectEvent: (event) => { if (!props.areaDrawing) emit('selectEvent', event) },
  })
  trackManager = new TrackLayerManager({ trackLayer, canvas, map })
  map.on('moveend', () => {
    scheduleTrack()
    emitBounds()
    clearTimeout(harbourTimer)
    if (props.layers.harbours) harbourTimer = setTimeout(loadHarbours, 350)
  })
  map.on('zoomend', () => { eventManager.setZoom(map!.getZoom()); scheduleShips(); scheduleEvents() })
  map.on('popupclose', () => { eventManager.onPopupClosed(); scheduleEvents() })
  map.on('click', () => {
    if (props.areaDrawing) return
    emit('clearSelection')
  })
  // 圈选绘制：仅在 areaDrawing 时绑定，避免影响既有选船/选事件交互
  // 圈选绘制：直接绑定容器原生事件（Leaflet 在拖动被禁时会 preventDefault，map.on('mousedown')
  // 不一定会派发）；mouseup 挂在 window 上，保证松手落在面板/状态条上时也能结束绘制。
  const drawContainer = container.value
  L.DomEvent.on(drawContainer, 'mousedown', onAreaDrawStart)
  L.DomEvent.on(drawContainer, 'mousemove', onAreaDrawing)
  window.addEventListener('mouseup', onAreaDrawEnd)
  window.addEventListener('keydown', onAreaKeyDown)
  observer = new ResizeObserver(() => {
    map?.invalidateSize({ pan: false })
    emitBounds()
  })
  observer.observe(container.value)
  syncLayers()
  scheduleArea()
  emitBounds()
})
onBeforeUnmount(() => {
  scheduler.cancel()
  shipManager?.clear()
  eventManager?.clear()
  trackManager?.clear()
  dwellMarkers.clear()
  encounterMarkers.clear()
  observer?.disconnect()
  harbourRequest?.abort()
  clearTimeout(harbourTimer)
  countryLayer?.destroy()
  areaRect = null
  drawRect = null
  map?.getContainer().classList.remove('area-drawing')
  if (container.value) {
    L.DomEvent.off(container.value, 'mousedown', onAreaDrawStart)
    L.DomEvent.off(container.value, 'mousemove', onAreaDrawing)
  }
  window.removeEventListener('mouseup', onAreaDrawEnd)
  window.removeEventListener('keydown', onAreaKeyDown)
  map?.remove()
  map = undefined
})
</script>
<template>
  <div
    ref="container"
    class="maritime-map"
    :data-background-point-count="(backgroundSegments ?? []).reduce((count, segment) => count + segment.points.length, 0)"
    :data-speed-color="windowSpeedColor"
    :data-points-visible="windowPointsVisible"
    :data-track-point-count="(windowSegments ?? []).reduce((count, segment) => count + segment.points.length, 0)"
    :data-track-end="windowSegments?.at(-1)?.points.at(-1)?.recorded_at ?? ''"
    :class="{ spotlight: !!selectedEvent, 'dark-map': theme === 'dark' }"
    aria-label="交互地图"
    tabindex="0"
  ></div>
  <div v-if="tileError" class="tile-notice" role="status">
    部分在线底图加载失败，船舶数据仍可使用
  </div>
  <div v-if="areaDrawing" class="area-draw-hint" role="status" aria-live="polite">
    在地图上按住左键拖动圈选矩形（西/南含、东/北不含，单边 ≤ 10°）；Esc 取消
  </div>
</template>
