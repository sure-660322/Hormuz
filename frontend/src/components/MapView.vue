<script setup lang="ts">
import { createCountryLayer } from '../services/countryLayer'
import { hasEventLocation, eventLocationLabel, type LocatedEvent } from '../domain/maritime'
import type { ApiTrackSegment } from '../api'
import { onMounted, onBeforeUnmount, ref, watch } from 'vue'
import * as L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import type { ApiEvent, ApiMapShip, ApiShipPosition } from '../api'
import {
  eventKind,
  formatTime,
  displayZone, riskColors, shipShape, shipStatus, projectPosition, eventPriority,
  type GeoPoint,
  type LayerState,
  type ViewBounds,
} from '../domain/maritime'
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
  tailMinutes: number
  shareRequest: number
  sharedView: { lat: number; lon: number; zoom: number } | null
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
  harbourLayer: L.LayerGroup
let seamarks: L.TileLayer
let vectorLayer: L.LayerGroup, linkLayer: L.LayerGroup, clusterLayer: L.LayerGroup
let canvas: L.Canvas
const markers = new Map<number, L.Marker>()
let initialFitDone = false
let harbourRequest: AbortController | null = null
let harbourTimer: ReturnType<typeof setTimeout> | undefined
const center: L.LatLngTuple = [26.35, 56.5]
const safeText = (value: string) => {
  const el = document.createElement('span')
  el.textContent = value
  return el
}
function shipIcon(ship: ApiMapShip) {
  const selected = ship.id === props.selectedShipId
  const nearby = props.nearbyShipIds.includes(ship.id)
  const color = selected || nearby ? riskColors.selected : shipStatus(ship, props.time).color
  const validHeading = ship.heading !== null && ship.heading >= 0 && ship.heading < 360
  const angle = validHeading ? ship.heading! : ship.course
  const complete = selected || (map?.getZoom() ?? 0) >= 10
  const shape = shipShape(ship.ship_type)
  const path = complete || shape === '△' ? 'M14 3 20 23 14 19 8 23Z' : shape === '■' ? 'M8 8H20V20H8Z' : shape === '▶' ? 'M14 5 22 22H6Z' : 'M14 5 22 14 14 23 6 14Z'
  const dimmed = props.selectedShipId !== null && !selected
  return L.divIcon({
    className: `vessel-marker${selected ? ' selected' : ''}${dimmed ? ' muted' : ''}`,
    html: `<svg viewBox="0 0 28 28" aria-hidden="true"><g transform="rotate(${complete ? angle : ship.course} 14 14)"><path d="${path}" fill="${color}" stroke="#EAF1F8" stroke-width="1"/>${!complete ? `<path d="M14 5V-2" stroke="${color}" stroke-width="2"/>` : ''}</g>${selected ? '<path d="M1 8V1H8M20 1H27V8M27 20V27H20M8 27H1V20" fill="none" stroke="#38BDF8" stroke-width="1.5"/>' : ''}</svg>`,
    iconSize: [28, 28],
    iconAnchor: [14, 14],
  })
}
function renderShips() {
  if (!map) return
  clusterLayer.clearLayers()
  vectorLayer.clearLayers()
  const groupedIds = new Set<number>()
  if ((map.getZoom() < 8 || props.ships.length > 500) && props.layers.ships && !props.isolated) {
    const groups = new Map<string, ApiMapShip[]>()
    for (const ship of props.ships) {
      if (ship.id === props.selectedShipId || props.nearbyShipIds.includes(ship.id)) continue
      const p = map.project([ship.latitude, ship.longitude])
      const key = `${Math.floor(p.x / 44)}:${Math.floor(p.y / 44)}`
      const group = groups.get(key) ?? []; group.push(ship); groups.set(key, group)
    }
    for (const group of groups.values()) {
      if (group.length < 2) continue
      group.forEach(s => groupedIds.add(s.id))
      const lat = group.reduce((sum, s) => sum + s.latitude, 0) / group.length
      const lon = group.reduce((sum, s) => sum + s.longitude, 0) / group.length
      L.marker([lat, lon], { icon: L.divIcon({ className: `ship-cluster${props.selectedEvent ? ' muted' : ''}`, html: `<span>${group.length}</span>`, iconSize: [34, 34] }), title: `${group.length} 艘模拟船，点击放大`, bubblingMouseEvents: false })
        .on('click', () => { if (!props.picking) map?.setView([lat, lon], Math.min(19, map.getZoom() + 2)) }).addTo(clusterLayer)
    }
  }
  const ids = new Set(props.ships.map((s) => s.id))
  for (const [id, marker] of markers)
    if (!ids.has(id)) {
      shipLayer.removeLayer(marker)
      markers.delete(id)
    }
  for (const ship of props.ships) {
    if (groupedIds.has(ship.id)) { const old = markers.get(ship.id); if (old) { shipLayer.removeLayer(old); markers.delete(ship.id) } continue }
    let marker = markers.get(ship.id)
    if (!marker) {
      marker = L.marker([ship.latitude, ship.longitude], {
        icon: shipIcon(ship),
        title: ship.name,
        alt: ship.name,
        bubblingMouseEvents: false,
      })
      marker.bindTooltip(
        safeText(`${ship.name} · ${ship.speed.toFixed(1)} kn`),
        { direction: 'top' },
      )
      marker.on('click', () => {
        const current = props.ships.find((s) => s.id === ship.id)
        if (current && !props.picking) emit('selectShip', current)
      })
      markers.set(ship.id, marker)
    }
    marker.setLatLng([ship.latitude, ship.longitude]).setIcon(shipIcon(ship))
    marker.setTooltipContent(
      safeText(`${ship.name} · ${ship.speed.toFixed(1)} kn`),
    )
    marker.setZIndexOffset(ship.id === props.selectedShipId ? 1000 : 0)
    if (
      props.layers.ships &&
      (!props.isolated || props.selectedShipId === ship.id)
    ) {
      if (!shipLayer.hasLayer(marker)) marker.addTo(shipLayer)
      const active = ship.id === props.selectedShipId || map.getZoom() >= 10
      if (active && shipStatus(ship, props.time).rank === 0) {
        const color = ship.id === props.selectedShipId || props.nearbyShipIds.includes(ship.id) ? riskColors.selected : riskColors.normal
        const opacity = (props.selectedEvent && !props.nearbyShipIds.includes(ship.id)) || (props.selectedShipId !== null && props.selectedShipId !== ship.id) ? 0.4 : 0.9
        if (ship.heading !== null && ship.heading >= 0 && ship.heading < 360) {
          const p = map.latLngToLayerPoint([ship.latitude, ship.longitude]), angle = ship.heading * Math.PI / 180
          const head = map.layerPointToLatLng(L.point(p.x + Math.sin(angle) * 52, p.y - Math.cos(angle) * 52))
          const bow = map.layerPointToLatLng(L.point(p.x + Math.sin(angle) * 11, p.y - Math.cos(angle) * 11))
          L.polyline([bow, head], { renderer: canvas, color, weight: 1, opacity, interactive: false }).addTo(vectorLayer)
        }
        const end = projectPosition(ship, ship.course, ship.speed * props.vectorMinutes / 60)
        L.polyline([[ship.latitude, ship.longitude], [end.latitude, end.longitude]], { renderer: canvas, color, weight: 2, dashArray: '4 4', opacity, interactive: false }).addTo(vectorLayer)
        for (let minute = 1; minute <= props.vectorMinutes; minute++) {
          const tick = projectPosition(ship, ship.course, ship.speed * minute / 60)
          L.circleMarker([tick.latitude, tick.longitude], { renderer: canvas, radius: minute === props.vectorMinutes ? 3 : 1.5, color, weight: 1, opacity, fillOpacity: opacity, interactive: false }).addTo(vectorLayer)
        }
      }
    } else shipLayer.removeLayer(marker)
  }
  renderLinks()
  if (!initialFitDone && props.ships.length) {
    initialFitDone = true
    globalView()
  }
}
function renderLinks() {
  if (!linkLayer) return
  linkLayer.clearLayers()
  // Cross-period news-to-ship links are intentionally disabled.

}
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
function renderEvents() {
  if (!map) return
  eventLayer.clearLayers()
  renderLinks()
  if (!props.layers.events || props.isolated) return
  const groups = new Map<string, LocatedEvent[]>()
  for (const event of props.events) {
    // Only co-located records share a marker; nearby coordinates must not move.
    const key = `${event.latitude},${event.longitude}`
    const group = groups.get(key) ?? []; group.push(event); groups.set(key, group)
  }
  for (const group of groups.values()) {
    const event = group.find(item => item.id === props.selectedEvent?.id) ?? group[0]!
    const kind = eventKind(event.event_type)
    const selected = props.selectedEvent?.id === event.id
    const locationLabel = eventLocationLabel(event)
    const markerTitle = group.length > 1 ? `${group.length} 条同坐标事件（点击展开）` : `${kind.label} · ${locationLabel} · ${event.title}`
    const icon = L.divIcon({
      className: `incident-marker${selected ? ' selected' : ''}${props.selectedEvent && !selected ? ' muted' : ''}${selected && eventPriority(event.event_type) !== 'normal' ? ' urgent' : ''}`,
      html: `<div class="incident-symbol" style="--risk:${kind.color}">${selected ? '<i class="incident-halo"></i><i class="selection-corners"></i>' : ''}<span class="incident-core">${kind.symbol}</span>${group.length > 1 ? `<b class="incident-count">${group.length}</b>` : ''}${selected ? `<span class="incident-label"><b>●</b> ${locationLabel} · 报道 ${event.publish_date_min ?? '日期未明'}</span>` : ''}</div>`,
      iconSize: [24, 24],
      iconAnchor: [12, 12],
    })
    const marker = L.marker([event.latitude, event.longitude], {
      icon,
      title: markerTitle,
      bubblingMouseEvents: false,
    })
      .bindTooltip(safeText(`${markerTitle} · ${event.latitude.toFixed(4)}, ${event.longitude.toFixed(4)}`))
      .on('click', () => {
        if (props.picking) return
        if (group.length === 1) emit('selectEvent', event)
        else {
          const list = document.createElement('div'); list.className = 'cluster-list'
          for (const item of group) {
            const button = document.createElement('button'); button.textContent = `${eventKind(item.event_type).label} · ${eventLocationLabel(item)} · ${item.title}`
            button.onclick = () => { map?.closePopup(); emit('selectEvent', item) }; list.append(button)
          }
          L.popup().setLatLng([event.latitude, event.longitude]).setContent(list).openOn(map!)
        }
      })
      .addTo(eventLayer)
    marker
      .getElement()
      ?.setAttribute('aria-label', markerTitle)
    const element = marker.getElement()
    if (element) {
      element.dataset.eventIds = group.map(item => item.event_id).join(',')
      element.dataset.latitude = String(event.latitude)
      element.dataset.longitude = String(event.longitude)
    }
    marker.setZIndexOffset(selected ? 2000 : 300)
  }
}
function speedBucketColor(v: number): string {
  return v < 3 ? '#8a97a3' : v < 8 ? '#2e9e5b' : v < 12 ? '#e6a23c' : '#d64f4f'
}
function renderSpeedSegments() {
  if (!props.speedSegments?.length) return
  for (const segment of props.speedSegments) {
    const coords = segment.geometry.coordinates
    let group: L.LatLngTuple[] = []
    let currentColor = ''
    const flush = () => {
      if (group.length > 1)
        L.polyline(group, {
          renderer: canvas,
          color: currentColor,
          weight: 3,
          opacity: 0.9,
          interactive: false,
        }).addTo(trackLayer)
    }
    for (let i = 0; i < coords.length - 1; i++) {
      const color = speedBucketColor(segment.speed[i]?.[1] ?? 0)
      if (color !== currentColor && group.length) {
        flush()
        group = []
      }
      currentColor = color
      if (!group.length) group.push([coords[i][1], coords[i][0]])
      group.push([coords[i + 1][1], coords[i + 1][0]])
    }
    flush()
  }
}
function renderTrack() {
  if (!map) return
  trackLayer.clearLayers()
  if (!props.trackVisible || !props.layers.tracks) return
  renderSpeedSegments()
  const tail = props.track.filter(p => !props.time || Date.parse(p.recorded_at) >= Date.parse(props.time) - props.tailMinutes * 60000)
  const points = tail.map((p): L.LatLngTuple => [
    p.latitude,
    p.longitude,
  ])
  if (points.length > 1 && !props.speedSegments?.length)
    L.polyline(points, {
      renderer: canvas,
      color: riskColors.selected,
      weight: 2,
      opacity: 0.8,
      interactive: false,
    }).addTo(trackLayer)
  for (const point of tail.slice(0, -1)) {
    L.circleMarker([point.latitude, point.longitude], {
      radius: 3,
      renderer: canvas,
      color: riskColors.selected,
      weight: 1,
      fillColor: '#f5fafb',
      fillOpacity: 1,
    })
      .bindTooltip(
        safeText(
          `${formatTime(point.recorded_at, true)} | ${point.latitude.toFixed(4)}, ${point.longitude.toFixed(4)} | ${point.speed.toFixed(1)} kn | 航向 ${point.course.toFixed(0)}° | 教学模拟采样`,
        ),
        { direction: 'top' },
      )
      .addTo(trackLayer)
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
  renderShips()
  renderEvents()
  renderTrack()
}
watch(
  () => [props.ships, props.selectedShipId, props.nearbyShipIds, props.selectedEvent, props.vectorMinutes],
  renderShips,
)
watch(() => [props.events, props.selectedEvent, displayZone.value], renderEvents)
watch(() => [props.track, props.trackVisible, props.tailMinutes, props.speedSegments, displayZone.value], renderTrack)
watch(() => props.shareRequest, () => { if (map) { const c = map.getCenter(); emit('shareView', { lat: c.lat, lon: c.lng, zoom: map.getZoom() }) } })
watch(() => props.sharedView, view => { if (view) map?.setView([view.lat, view.lon], view.zoom, { animate: false }) }, { flush: 'post' })
watch(() => [props.layers, props.isolated], syncLayers, { deep: true })
watch(() => [props.areaCenter, props.radiusNm], renderArea)
watch(() => props.focusShipRequest, focusShip)
watch(
  () => props.picking,
  (active) => {
    if (active) {
      markers.forEach((marker) => marker.closeTooltip())
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
  linkLayer = L.layerGroup().addTo(map)
  clusterLayer = L.layerGroup().addTo(map)
  trackLayer = L.layerGroup().addTo(map)
  areaLayer = L.layerGroup().addTo(map)
  shipLayer = L.layerGroup().addTo(map)
  eventLayer = L.layerGroup().addTo(map)
  harbourLayer = L.layerGroup()
  map.on('moveend', () => {
    emitBounds()
    clearTimeout(harbourTimer)
    if (props.layers.harbours) harbourTimer = setTimeout(loadHarbours, 350)
  })
  map.on('zoomend', () => { renderShips(); renderEvents() })
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
  observer?.disconnect()
  harbourRequest?.abort()
  clearTimeout(harbourTimer)
  countryLayer?.destroy()
  map?.remove()
  map = undefined
  markers.clear()
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
