<script setup lang="ts">
import { createCountryLayer } from '../services/countryLayer'
import { hasEventLocation, type LocatedEvent } from '../domain/maritime'
import type { ApiTrackSegment } from '../api'
import { onMounted, onBeforeUnmount, ref, watch } from 'vue'
import * as L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import type { ApiEvent, ApiMapShip, ApiShipPosition, ApiDwellResponse, ApiEncounter } from '../api'
import {
  displayZone,
  type GeoPoint,
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
  isolated: boolean
  layers: LayerState
  globalViewRequest: number
  focusShipRequest: number
  nearbyShipIds: number[]
  areaCenter: GeoPoint | null
  radiusNm: number
  picking: boolean
  theme: 'dark' | 'light'
  time: string | null
  vectorMinutes: number
  trackRecent24h: boolean
  shareRequest: number
  sharedView: { lat: number; lon: number; zoom: number } | null
  dwell: ApiDwellResponse | null
  encounters: ApiEncounter[] | null
  selectedEncounter: ApiEncounter | null
}>()
const emit = defineEmits<{
  selectShip: [ship: ApiMapShip]
  selectEvent: [event: ApiEvent]
  boundsChange: [bounds: ViewBounds]
  pickCenter: [point: GeoPoint]
  harbourStatus: [status: string]
  countryStatus: [status: string]
  clearSelection: []
  shareView: [view: { lat: number; lon: number; zoom: number }]
  selectEncounter: [encounter: ApiEncounter]
}>()
const container = ref<HTMLElement | null>(null)
const tileError = ref(false)
let map: L.Map | undefined
let countryLayer: ReturnType<typeof createCountryLayer> | undefined
let observer: ResizeObserver | undefined
let shipLayer: L.LayerGroup,
  eventLayer: L.LayerGroup,
  trackLayer: L.LayerGroup,
  areaLayer: L.LayerGroup,
  harbourLayer: L.LayerGroup,
  dwellLayer: L.LayerGroup,
  encounterLayer: L.LayerGroup
let seamarks: L.TileLayer
let vectorLayer: L.LayerGroup, clusterLayer: L.LayerGroup
let canvas: L.Canvas
let shipManager: ShipLayerManager
let eventManager: EventLayerManager
let trackManager: TrackLayerManager
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
      picking: props.picking,
    })
    if (!initialFitDone && props.ships.length) {
      initialFitDone = true
      globalView()
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
      picking: props.picking,
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
            if (!props.picking) emit('selectEncounter', enc)
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
function renderArea() {
  if (!map) return
  areaLayer.clearLayers()
  if (props.areaCenter)
    L.circle([props.areaCenter.latitude, props.areaCenter.longitude], {
      radius: props.radiusNm * 1852,
      color: '#386d99',
      weight: 1.5,
      dashArray: '5 5',
      fillOpacity: 0.06,
      interactive: false,
    }).addTo(areaLayer)
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
  if (ship) smoothlyCenterOn([ship.latitude, ship.longitude])
}
function pickViewCenter(event: KeyboardEvent) {
  if (!props.picking || !map || event.target !== container.value) return
  event.preventDefault()
  const point = map.getCenter()
  emit('pickCenter', { latitude: point.lat, longitude: point.lng })
}
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
watch(() => [props.track, props.trackVisible, props.trackRecent24h, props.time, props.speedSegments, displayZone.value], scheduleTrack)
watch(() => props.shareRequest, () => { if (map) { const c = map.getCenter(); emit('shareView', { lat: c.lat, lon: c.lng, zoom: map.getZoom() }) } })
watch(() => [props.dwell, props.encounters, props.selectedEncounter, props.isolated], scheduleDerived)
// 从概览面板选中相遇时，地图飞到最近接近点并保证相遇图层可见。
watch(() => props.selectedEncounter, (enc) => {
  if (!map || !enc?.closest_point) return
  const [lng, lat] = enc.closest_point.coordinates
  map.flyTo([lat, lng], Math.max(map.getZoom(), 9), { duration: 0.6 })
})
watch(() => props.sharedView, view => { if (view) map?.setView([view.lat, view.lon], view.zoom, { animate: false }) }, { flush: 'post' })
watch(() => [props.layers, props.isolated], syncLayers, { deep: true })
watch(() => [props.areaCenter, props.radiusNm], renderArea)
watch(() => props.focusShipRequest, focusShip)
watch(
  () => props.picking,
  (active) => {
    if (active) {
      shipLayer.eachLayer((layer) => {
        if (layer instanceof L.Marker) layer.closeTooltip()
      })
      container.value?.focus()
    }
  },
)
watch(
  () => props.selectedEvent,
  (event) => {
    if (event && hasEventLocation(event)) smoothlyCenterOn([event.latitude, event.longitude])
  },
)
watch(() => props.globalViewRequest, globalView)
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
  const basemap = L.tileLayer(
    'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
    {
      className: 'neutral-basemap',
      maxZoom: 19,
      attribution:
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
  areaLayer = L.layerGroup().addTo(map)
  shipLayer = L.layerGroup().addTo(map)
  eventLayer = L.layerGroup().addTo(map)
  harbourLayer = L.layerGroup()
  dwellLayer = L.layerGroup().addTo(map)
  encounterLayer = L.layerGroup().addTo(map)
  shipManager = new ShipLayerManager({
    shipLayer,
    clusterLayer,
    vectorLayer,
    canvas,
    getMap: () => map,
    onSelectShip: (ship) => { if (!props.picking) emit('selectShip', ship) },
  })
  eventManager = new EventLayerManager({
    eventLayer,
    getMap: () => map,
    onSelectEvent: (event) => emit('selectEvent', event),
  })
  trackManager = new TrackLayerManager({ trackLayer, canvas })
  map.on('moveend', () => {
    emitBounds()
    clearTimeout(harbourTimer)
    if (props.layers.harbours) harbourTimer = setTimeout(loadHarbours, 350)
  })
  map.on('zoomend', () => { eventManager.setZoom(map!.getZoom()); scheduleShips(); scheduleEvents() })
  map.on('popupclose', () => { eventManager.onPopupClosed(); scheduleEvents() })
  map.on('click', (e: L.LeafletMouseEvent) => {
    if (props.picking)
      emit('pickCenter', { latitude: e.latlng.lat, longitude: e.latlng.lng })
    else emit('clearSelection')
  })
  observer = new ResizeObserver(() => {
    map?.invalidateSize({ pan: false })
    emitBounds()
  })
  observer.observe(container.value)
  syncLayers()
  renderArea()
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
  map?.remove()
  map = undefined
})
</script>
<template>
  <div
    ref="container"
    class="maritime-map"
    :class="{ picking, spotlight: !!selectedEvent, 'dark-map': theme === 'dark' }"
    aria-label="交互地图"
    tabindex="0"
    @keydown.enter="pickViewCenter"
  ></div>
  <div v-if="tileError" class="tile-notice" role="status">
    部分在线底图加载失败，船舶数据仍可使用
  </div>
</template>
