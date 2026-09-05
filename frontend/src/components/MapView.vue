<script setup lang="ts">
import {
  nextTick,
  onBeforeUnmount,
  onMounted,
  ref,
  watch,
} from 'vue'
import * as L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { fetchAisShipPositions } from '../api'
import type {
  ApiAisMapShip,
  ApiShipPosition,
} from '../api'

const props = defineProps<{
    mapShips: ApiAisMapShip[]
    currentPlaybackTime: string | null
}>()

const emit = defineEmits<{
    isolationChange: [isIsolated: boolean]
}>()

let map: L.Map | undefined
let selectedTrackLayer: L.Polyline | undefined
let shipLayer: L.LayerGroup | undefined
let harbourLayer: L.LayerGroup | undefined
let trackPointLayer: L.LayerGroup | undefined

const GLOBAL_CENTER: L.LatLngTuple = [26.5, 56.5]
const GLOBAL_ZOOM = 8

const shipMarkersById = new Map<number, L.Marker>()
const shipsById = new Map<number, ApiAisMapShip>()
const trackCache = new Map<number, ApiShipPosition[]>()

const selectedShip = ref<ApiAisMapShip | null>(null)
const trackLoading = ref(false)
const trackError = ref('')
const trackVisible = ref(false)
const isolatedShipId = ref<number | null>(null)

let trackRequestSequence = 0

const shipIcon = L.divIcon({
  className: 'ship-marker',
  html: '▲',
  iconSize: [24, 24],
  iconAnchor: [12, 12],
})

const selectedShipIcon = L.divIcon({
  className: 'ship-marker ship-marker-selected',
  html: '▲',
  iconSize: [32, 32],
  iconAnchor: [16, 16],
})

function displayText(value: string | number | null | undefined) {
  return value === null || value === undefined || value === ''
    ? '无数据'
    : String(value)
}

function escapeHtml(value: string) {
  return value
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;')
}

function displayNumber(value: number | null | undefined, suffix = '') {
  return value === null || value === undefined
    ? '无数据'
    : `${value.toFixed(1)}${suffix}`
}

function createShipPopupContent(ship: ApiAisMapShip) {
  return `
    <strong>船名：</strong>${escapeHtml(displayText(ship.name))}<br>
    <strong>MMSI：</strong>${escapeHtml(ship.mmsi)}<br>
    <strong>船型代码：</strong>${escapeHtml(displayText(ship.ship_type))}<br>
    <strong>船旗：</strong>${escapeHtml(displayText(ship.flag))}<br>
    <strong>速度：</strong>${displayNumber(ship.speed, ' 节')}<br>
    <strong>对地航向：</strong>${displayNumber(ship.course, '°')}<br>
    <strong>船首向：</strong>${displayNumber(ship.heading, '°')}<br>
    <strong>位置：</strong>${ship.latitude.toFixed(4)}, ${ship.longitude.toFixed(4)}<br>
    <strong>AIS 报位：</strong>${new Date(ship.recorded_at).toLocaleString('zh-CN')}<br>
    <strong>来源：</strong>yasumorishima / aisstream.io 历史数据
  `
}

function syncShipMarkers(ships: ApiAisMapShip[]) {
  if (!shipLayer) return

  const visibleShipIds = new Set(ships.map((ship) => ship.id))
  for (const [shipId, marker] of shipMarkersById) {
    if (visibleShipIds.has(shipId)) continue
    shipLayer.removeLayer(marker)
    shipMarkersById.delete(shipId)
    shipsById.delete(shipId)
  }

  if (
    selectedShip.value &&
    !visibleShipIds.has(selectedShip.value.id)
  ) {
    trackRequestSequence += 1
    selectedShip.value = null
    trackError.value = ''
    clearSelectedTrack()
    map?.closePopup()
  }

  for (const ship of ships) {
    shipsById.set(ship.id, ship)
    const existingMarker = shipMarkersById.get(ship.id)
    if (existingMarker) {
      existingMarker.setLatLng([ship.latitude, ship.longitude])
      existingMarker.setPopupContent(createShipPopupContent(ship))
    } else {
      const marker = L.marker([ship.latitude, ship.longitude], {
        icon: selectedShip.value?.id === ship.id ? selectedShipIcon : shipIcon,
      })
        .bindPopup(createShipPopupContent(ship))
        .addTo(shipLayer)

      marker.on('click', () => {
        const currentShip = shipsById.get(ship.id)
        if (currentShip) selectShip(currentShip)
      })
      shipMarkersById.set(ship.id, marker)
    }

    if (selectedShip.value?.id === ship.id) {
      selectedShip.value = ship
    }
  }
}

function updateShipMarkerHighlight(selectedShipId: number | null) {
  for (const [shipId, marker] of shipMarkersById) {
    marker.setIcon(
      shipId === selectedShipId
        ? selectedShipIcon
        : shipIcon,
    )
  }
}

function clearSelectedTrack() {
  selectedTrackLayer?.remove()
  selectedTrackLayer = undefined
  trackPointLayer?.clearLayers()
  trackVisible.value = false
}

function selectShip(ship: ApiAisMapShip) {
  if (selectedShip.value?.id === ship.id) {
    updateShipMarkerHighlight(ship.id)
    return
  }

  trackRequestSequence += 1
  trackLoading.value = false
  trackError.value = ''
  clearSelectedTrack()

  selectedShip.value = ship
  updateShipMarkerHighlight(ship.id)
}

function renderSelectedShipTrack(
  trackPoints: ApiShipPosition[],
  moveMap = true,
) {
  if (!map || !trackPointLayer || trackPoints.length === 0) {
    trackError.value = '当前时刻之前没有该船舶的轨迹采样点'
    return
  }

  clearSelectedTrack()

  const trackLatLngs = trackPoints.map(
    (point): L.LatLngTuple => [
      point.latitude,
      point.longitude,
    ],
  )

  if (trackLatLngs.length >= 2) {
    selectedTrackLayer = L.polyline(trackLatLngs, {
      pane: 'selectedTrackPane',
      color: '#f59e0b',
      weight: 4,
      opacity: 0.95,
    }).addTo(map)
  }

  for (const point of trackPoints) {
    L.circleMarker(
      [point.latitude, point.longitude],
      {
        pane: 'selectedTrackPane',
        radius: 4,
        color: '#92400e',
        weight: 1,
        fillColor: '#fbbf24',
        fillOpacity: 0.95,
      },
    )
      .bindPopup(`
        <strong>轨迹采样点</strong><br>
        <strong>时间：</strong>${new Date(point.recorded_at).toLocaleString('zh-CN')}<br>
        <strong>位置：</strong>${point.latitude.toFixed(4)}, ${point.longitude.toFixed(4)}<br>
        <strong>速度：</strong>${displayNumber(point.speed, ' 节')}<br>
        <strong>航向：</strong>${displayNumber(point.course, '°')}
      `)
      .addTo(trackPointLayer)
  }

  trackVisible.value = true
  trackError.value = ''

  if (moveMap && selectedTrackLayer) {
    map.fitBounds(selectedTrackLayer.getBounds(), {
      padding: [40, 40],
    })
  } else if (moveMap) {
    map.flyTo(trackLatLngs[0], 11)
  }
}

function getTrackPointsAtCurrentTime(trackPoints: ApiShipPosition[]) {
  if (!props.currentPlaybackTime) return trackPoints

  const currentTimestamp = Date.parse(props.currentPlaybackTime)
  return trackPoints.filter(
    (point) => Date.parse(point.recorded_at) <= currentTimestamp,
  )
}

async function showSelectedShipTrack() {
  const ship = selectedShip.value
  if (!ship) return

  const requestSequence = ++trackRequestSequence
  trackLoading.value = true
  trackError.value = ''

  try {
    let trackPoints = trackCache.get(ship.id)

    if (!trackPoints) {
      trackPoints = await fetchAisShipPositions(ship.id)
      trackPoints = [...trackPoints].sort(
        (firstPoint, secondPoint) =>
          Date.parse(firstPoint.recorded_at) -
          Date.parse(secondPoint.recorded_at),
      )
      trackCache.set(ship.id, trackPoints)
    }

    if (
      requestSequence !== trackRequestSequence ||
      selectedShip.value?.id !== ship.id
    ) {
      return
    }

    renderSelectedShipTrack(getTrackPointsAtCurrentTime(trackPoints))
  } catch (error) {
    if (requestSequence !== trackRequestSequence) return

    trackError.value =
      error instanceof Error
        ? error.message
        : '船舶轨迹加载失败'
  } finally {
    if (requestSequence === trackRequestSequence) {
      trackLoading.value = false
    }
  }
}

function hideSelectedShipTrack() {
  trackRequestSequence += 1
  trackLoading.value = false
  trackError.value = ''
  clearSelectedTrack()
}

async function clearSelectedShip() {
  const wasIsolated = isolatedShipId.value !== null

  trackRequestSequence += 1
  trackLoading.value = false
  trackError.value = ''
  clearSelectedTrack()

  selectedShip.value = null
  updateShipMarkerHighlight(null)
  map?.closePopup()

  if (wasIsolated) {
    await restoreAllShips()
  }
}

function handleWindowKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape' && selectedShip.value) {
    void clearSelectedShip()
  }
}

async function enterShipIsolation() {
  const activeMap = map
  const activeShipLayer = shipLayer
  const ship = selectedShip.value
  if (!activeMap || !activeShipLayer || !ship) return

  isolatedShipId.value = ship.id
  activeShipLayer.clearLayers()
  shipMarkersById.get(ship.id)?.addTo(activeShipLayer)

  if (harbourLayer && activeMap.hasLayer(harbourLayer)) {
    activeMap.removeLayer(harbourLayer)
  }

  emit('isolationChange', true)
  await nextTick()
  activeMap.invalidateSize()

  if (selectedTrackLayer) {
    activeMap.fitBounds(selectedTrackLayer.getBounds(), {
      padding: [40, 40],
    })
  } else {
    activeMap.flyTo(
      [ship.latitude, ship.longitude],
      11,
    )
  }
}

async function restoreAllShips() {
  const activeMap = map
  const activeShipLayer = shipLayer
  if (!activeMap || !activeShipLayer) return

  isolatedShipId.value = null
  activeShipLayer.clearLayers()

  for (const marker of shipMarkersById.values()) {
    marker.addTo(activeShipLayer)
  }

  if (harbourLayer && !activeMap.hasLayer(harbourLayer)) {
    harbourLayer.addTo(activeMap)
  }

  emit('isolationChange', false)
  await nextTick()
  activeMap.invalidateSize()
  activeMap.flyTo(GLOBAL_CENTER, GLOBAL_ZOOM)
}

watch(
  () => props.mapShips,
  (ships) => {
    syncShipMarkers(ships)
  },
)

watch(
  () => props.currentPlaybackTime,
  () => {
    const shipId = selectedShip.value?.id
    if (!trackVisible.value || shipId === undefined) return

    const trackPoints = trackCache.get(shipId)
    if (!trackPoints) return

    renderSelectedShipTrack(
      getTrackPointsAtCurrentTime(trackPoints),
      false,
    )
  },
)
onMounted(() => {
  window.addEventListener('keydown', handleWindowKeydown)

  map = L.map('map').setView(GLOBAL_CENTER, GLOBAL_ZOOM)

  const selectedTrackPane = map.createPane('selectedTrackPane')
  selectedTrackPane.style.zIndex = '650'

  L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19,
    attribution:
      '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
  }).addTo(map)

  L.tileLayer('https://tiles.openseamap.org/seamark/{z}/{x}/{y}.png', {
    maxZoom: 18,
    attribution:
      'Seamark data &copy; <a href="https://www.openseamap.org">OpenSeaMap</a>',
  }).addTo(map)

  shipLayer = L.layerGroup().addTo(map)
  trackPointLayer = L.layerGroup().addTo(map)
  syncShipMarkers(props.mapShips)

  harbourLayer = L.layerGroup().addTo(map)

  const harbourIcon = L.icon({
    iconUrl: 'https://map.openseamap.org/resources/places/harbour_32.png',
    iconSize: [24, 24],
    iconAnchor: [12, 12],
    popupAnchor: [0, -12],
  })

  const loadHarbours = async () => {
    const activeHarbourLayer = harbourLayer
    if (!map || !activeHarbourLayer) return

    const bounds = map.getBounds()
    const zoom = Math.round(map.getZoom())

    let maxSize = 1

    if (zoom >= 7) maxSize = 2
    if (zoom >= 8) maxSize = 3
    if (zoom >= 9) maxSize = 4
    if (zoom >= 10) maxSize = 6

    const params = new URLSearchParams({
      b: bounds.getSouth().toFixed(5),
      t: bounds.getNorth().toFixed(5),
      l: bounds.getWest().toFixed(5),
      r: bounds.getEast().toFixed(5),
      ucid: '0',
      maxSize: maxSize.toString(),
      zoom: zoom.toString(),
    })

    const response = await fetch(
      `https://harbour.openseamap.org/getHarbours.php?${params}`,
    )

    if (!response.ok) {
      throw new Error(`港口接口请求失败：${response.status}`)
    }

    const text = await response.text()
    const rows = text
      .replace(/(\r|\n)/g, '')
      .replace(/putHarbourMarker\(/g, '')
      .replace(/\);/g, ';')
      .split(';')
      .filter(Boolean)

    activeHarbourLayer.clearLayers()

    for (const row of rows) {
      const [, longitudeText, latitudeText, nameText] = row.split(', ')
      const longitude = Number.parseFloat(longitudeText)
      const latitude = Number.parseFloat(latitudeText)
      const name = nameText?.replace(/'/g, '') || '未命名港口'

      if (!Number.isFinite(longitude) || !Number.isFinite(latitude)) {
        continue
      }

      L.marker([latitude, longitude], { icon: harbourIcon })
        .bindPopup(name)
        .addTo(activeHarbourLayer)
    }
  }

  loadHarbours().catch((error) => {
    console.error('港口数据加载失败：', error)
  })
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', handleWindowKeydown)
  trackRequestSequence += 1
  selectedTrackLayer?.remove()
  selectedTrackLayer = undefined
  trackPointLayer?.clearLayers()
  shipMarkersById.clear()
  shipsById.clear()
  trackCache.clear()
  shipLayer = undefined
  harbourLayer = undefined
  trackPointLayer = undefined
  map?.remove()
  map = undefined
})
</script>




<template>
  <div class="map-container">
    <div id="map"></div>

    <aside
      v-if="selectedShip"
      class="ship-detail-card"
      aria-label="当前选中船舶"
    >
      <p class="ship-detail-label">当前选中船舶</p>
      <h2>{{ displayText(selectedShip.name) }}</h2>

      <dl>
        <div>
          <dt>MMSI</dt>
          <dd>{{ selectedShip.mmsi }}</dd>
        </div>

        <div>
          <dt>船型代码</dt>
          <dd>{{ displayText(selectedShip.ship_type) }}</dd>
        </div>

        <div>
          <dt>船旗</dt>
          <dd>{{ displayText(selectedShip.flag) }}</dd>
        </div>

        <div>
          <dt>当前位置</dt>
          <dd>
            {{ selectedShip.latitude.toFixed(4) }},
            {{ selectedShip.longitude.toFixed(4) }}
          </dd>
        </div>

        <div>
          <dt>速度 / 航向</dt>
          <dd>
            {{ displayNumber(selectedShip.speed, ' 节') }} /
            {{ displayNumber(selectedShip.course, '°') }}
          </dd>
        </div>

        <div>
          <dt>更新时间</dt>
          <dd>
            {{ new Date(selectedShip.recorded_at).toLocaleString('zh-CN') }}
          </dd>
        </div>

        <div>
          <dt>数据来源</dt>
          <dd>yasumorishima / aisstream.io 历史数据</dd>
        </div>
      </dl>

      <p
        v-if="trackLoading"
        class="track-status"
        aria-live="polite"
      >
        正在加载轨迹……
      </p>

      <p
        v-else-if="trackError"
        class="track-status track-error"
        aria-live="polite"
      >
        {{ trackError }}
      </p>

      <p v-else-if="trackVisible" class="track-hint">
        点击轨迹采样点可查看位置和采样时间。
      </p>

      <div class="ship-actions">
        <button
          v-if="!trackVisible"
          type="button"
          :disabled="trackLoading"
          @click="showSelectedShipTrack"
        >
          {{ trackLoading ? '加载中……' : '查看轨迹' }}
        </button>

        <button
          v-else
          type="button"
          @click="hideSelectedShipTrack"
        >
          隐藏轨迹
        </button>

        <button
          v-if="isolatedShipId === null"
          type="button"
          class="secondary-button"
          @click="enterShipIsolation"
        >
          仅看此船
        </button>

        <button
          v-else
          type="button"
          class="secondary-button"
          @click="restoreAllShips"
        >
          恢复全部
        </button>

        <button
          type="button"
          class="cancel-selection-button"
          @click="clearSelectedShip"
        >
          取消选中
        </button>
      </div>
    </aside>
  </div>
</template>

<style>

.map-container {
  position: relative;
  width: 100%;
  height: 100%;
}

#map {
  width: 100%;
  height: 100%;
  background-color: #dbeafe;
}

.ship-marker {
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
  background-color: #2563eb;
  border: 2px solid white;
  border-radius: 50%;
  box-sizing: border-box;
  font-size: 14px;
  line-height: 1;
  box-shadow: 0 1px 4px rgb(0 0 0 / 40%);
}

.event-marker {
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
  background-color: #dc2626;
  border: 2px solid white;
  border-radius: 50%;
  box-sizing: border-box;
  font-size: 17px;
  font-weight: 700;
  line-height: 1;
  box-shadow: 0 1px 4px rgb(0 0 0 / 40%);
}

.ship-marker-selected {
  background-color: #0f766e;
  border-width: 3px;
  font-size: 18px;
  box-shadow: 0 0 0 4px rgb(15 118 110 / 25%),
    0 2px 8px rgb(0 0 0 / 45%);
}

.event-marker-selected {
  background-color: #f59e0b;
  border-width: 3px;
  font-size: 21px;
  box-shadow: 0 0 0 4px rgb(245 158 11 / 25%),
    0 2px 8px rgb(0 0 0 / 45%);
}

.ship-detail-card {
  position: absolute;
  z-index: 1100;
  top: 16px;
  right: 16px;
  box-sizing: border-box;
  width: min(320px, calc(100% - 32px));
  max-height: calc(100% - 32px);
  padding: 16px;
  overflow-y: auto;
  border: 1px solid #bfdbfe;
  border-radius: 10px;
  background-color: rgb(255 255 255 / 96%);
  color: #0f172a;
  text-align: left;
  box-shadow: 0 8px 24px rgb(15 23 42 / 22%);
}

.ship-detail-label {
  margin: 0;
  color: #0f766e;
  font-size: 12px;
  font-weight: 700;
}

.ship-detail-card h2 {
  margin: 6px 0 12px;
  color: #0f172a;
  font-size: 18px;
  line-height: 1.4;
}

.ship-detail-card dl {
  display: grid;
  gap: 6px;
  margin: 0;
  font-size: 12px;
}

.ship-detail-card dl div {
  display: grid;
  grid-template-columns: 76px minmax(0, 1fr);
  gap: 8px;
}

.ship-detail-card dt {
  color: #64748b;
}

.ship-detail-card dd {
  margin: 0;
  color: #0f172a;
  overflow-wrap: anywhere;
}

.track-status,
.track-hint {
  margin: 12px 0 0;
  color: #475569;
  font-size: 12px;
}

.track-error {
  color: #b91c1c;
}

.ship-actions {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: 8px;
  margin-top: 14px;
}

.ship-actions button {
  padding: 8px 10px;
  border: 1px solid #0f766e;
  border-radius: 6px;
  background-color: #0f766e;
  color: #ffffff;
  font: inherit;
  font-size: 12px;
  cursor: pointer;
}

.ship-actions button:disabled {
  cursor: wait;
  opacity: 0.6;
}

.ship-actions .secondary-button {
  border-color: #94a3b8;
  background-color: #ffffff;
  color: #334155;
}

.ship-actions .cancel-selection-button {
  grid-column: 1 / -1;
  border-color: #cbd5e1;
  background-color: #f8fafc;
  color: #475569;
}

</style>
