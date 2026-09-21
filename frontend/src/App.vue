<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount, ref, watch } from 'vue'
import { fetchEvents, fetchShipTracks, fetchDwell, fetchEncounters, analyzeEncounters, fetchDataHealth, describeApiError, type ApiEvent, type ApiMapShip, type ApiTrackSegment, type ApiDwellResponse, type ApiEncounter, type ApiDataHealth } from './api'
import { usePlayback } from './composables/usePlayback'
import {
  inBounds,
  formatTime,
  displayZone, zoneLabel, hasEventLocation, eventTimeText, eventCoordinates, eventRevealTime, eventKinds,
  type GeoPoint,
  type LayerState,
  type Panel,
  type ViewBounds,
} from './domain/maritime'
import { localWorkbench } from './services/workbench'
import logoUrl from './assets/logo.png'
import MapView from './components/MapView.vue'
import EventPanel from './components/EventPanel.vue'
import AgentPanel from './components/AgentPanel.vue'
import ShipInspector from './components/ShipInspector.vue'
import TimelineControls from './components/TimelineControls.vue'
import ShipSearch from './components/ShipSearch.vue'
import WorkspaceTools from './components/WorkspaceTools.vue'
import ToolRail from './components/ToolRail.vue'
import OverviewPanel from './components/OverviewPanel.vue'
import LayersPopover from './components/LayersPopover.vue'

const {
  tracks,
  index,
  loading,
  error,
  time,
  times,
  currentShips,
  load,
  seek,
} = usePlayback()
const events = ref<ApiEvent[]>([])
const eventsLoading = ref(true)
const eventsError = ref('')
const panel = ref<Panel>('overview')
const panelOpen = ref(!window.matchMedia('(max-width: 760px)').matches)
const layersOpen = ref(false)
const legendOpen = ref(false)
const selectedShipId = ref<number | null>(null)
const selectedEvent = ref<ApiEvent | null>(null)
const eventType = ref('all')
const eventSort = ref<'asc' | 'desc'>('asc')
const isolated = ref(false)
const trackVisible = ref(false)
const globalViewRequest = ref(0)
const focusShipRequest = ref(0)
const seekRequest = ref(0)
const bounds = ref<ViewBounds | null>(null)
const center = ref<GeoPoint | null>(null)
const radius = ref(10)
const picking = ref(false)
const harbourStatus = ref('按需加载')
const countryStatus = ref('按需加载')
const theme = ref<'dark' | 'light'>('dark')
const vectorMinutes = ref(6)
// 轨迹展示范围：默认显示全部已回放报位点；开启后只看回放时刻前 24 小时。
const trackRecent24h = ref(false)
const playbackSpeed = ref(1)
const vectorLinked = ref(false)
const effectiveVector = computed(() => vectorMinutes.value * (vectorLinked.value ? playbackSpeed.value : 1))
const notice = ref('')
const fenceEnabled = ref(false)
const shareRequest = ref(0)
const sharedView = ref<{ lat: number; lon: number; zoom: number } | null>(null)
const printReport = () => window.print()
const layers = ref<LayerState>({
  countries: true,
  ships: true,
  tracks: true,
  events: true,
  seamarks: true,
  harbours: false,
  dwell: false,
  encounters: false,
})
const selectedShip = computed(
  () =>
    currentShips.value.find((ship) => ship.id === selectedShipId.value) ?? null,
)
const selectedTrack = computed(() =>
  selectedShipId.value === null
    ? []
    : (tracks.value[selectedShipId.value] ?? []).filter(
        (p) =>
          time.value && Date.parse(p.recorded_at) <= Date.parse(time.value),
      ),
)
const filteredEvents = computed(() =>
  [...events.value].filter(e => eventType.value === 'all' || e.event_type === eventType.value)
    .sort((a, b) => {
      const left = a.publish_date_min, right = b.publish_date_min
      if (!left || !right) return left ? -1 : right ? 1 : a.event_id.localeCompare(b.event_id)
      return (left.localeCompare(right) || a.event_id.localeCompare(b.event_id)) * (eventSort.value === 'asc' ? 1 : -1)
    }),
)
// 地图事件随回放时刻逐步呈现：呈现时刻不晚于当前回放时刻才标注到地图，
// 反映事件先后发生顺序。回放时间未就绪时不做门控，避免空数据状态下地图无事件。
// 没有可用时间（发生日期与报道日期皆无）的事件不按时间补造，暂不标注。
const mapEvents = computed(() => {
  const located = filteredEvents.value.filter(hasEventLocation)
  if (!time.value) return located
  const at = Date.parse(time.value)
  return located.filter((e) => {
    const reveal = eventRevealTime(e)
    return reveal !== null && reveal <= at
  })
})
// 仅传入 occurred_at 非空的事件：报道无明确发生时刻时不补造时间，不进时间轴。
const timelineEvents = computed(
  () =>
    filteredEvents.value.filter((e) => e.occurred_at) as (ApiEvent & {
      occurred_at: string
    })[],
)
const viewShips = computed(() =>
  bounds.value
    ? currentShips.value.filter((s) => inBounds(s, bounds.value!))
    : currentShips.value,
)
const viewEvents = computed(() =>
  bounds.value
    ? mapEvents.value.filter((e) => inBounds(e, bounds.value!))
    : mapEvents.value,
)
const averageSpeed = computed(() =>
  viewShips.value.length
    ? (
        viewShips.value.reduce((sum, ship) => sum + ship.speed, 0) /
        viewShips.value.length
      ).toFixed(1)
    : '—',
)
// 新闻与模拟船位属同一时期但相互独立：不因时间或空间接近建立关联。
const nearbyEvents: (ApiEvent & { distance: number })[] = []
const nearbyShipIds: number[] = []
const areaResult = computed(() =>
  center.value && time.value
    ? localWorkbench.queryArea(
        { center: center.value, radiusNm: radius.value, at: time.value },
        currentShips.value,
        [],
      )
    : null,
)
const fenceInside = computed(() => fenceEnabled.value ? areaResult.value?.ships.map(s => s.id) ?? [] : [])
let previousFenceTime: string | null = null
watch(fenceInside, (ids, previous) => {
  const advanced = previousFenceTime !== null && previousFenceTime !== time.value
  previousFenceTime = time.value
  if (!fenceEnabled.value || !advanced) return
  const entered = ids.filter(id => !previous.includes(id)).length
  const left = previous.filter(id => !ids.includes(id)).length
  if (entered || left) notice.value = `模拟围栏变化：${entered} 艘进入，${left} 艘离开（相邻回放快照）`
})
watch(theme, value => document.documentElement.dataset.theme = value, { immediate: true })
async function shareView(view: { lat: number; lon: number; zoom: number }) {
  const url = new URL(window.location.href)
  url.hash = new URLSearchParams({ lat: view.lat.toFixed(5), lon: view.lon.toFixed(5), z: String(view.zoom), at: time.value ?? '', ship: String(selectedShipId.value ?? ''), event: selectedEvent.value?.event_id ?? '', theme: theme.value, zone: displayZone.value }).toString()
  history.replaceState(null, '', url)
  try { await navigator.clipboard.writeText(url.href); notice.value = '当前视野、时间与选中目标链接已复制。同一数据服务下可复现。' }
  catch { notice.value = '视图状态已写入地址栏，可复制地址分享。' }
}
async function initialize() {
  await Promise.all([load(), loadEvents(), loadEncounters(), loadHealth()])
  const state = new URLSearchParams(location.hash.slice(1))
  if (state.get('theme') === 'light') theme.value = 'light'
  if (state.get('zone') === 'Asia/Shanghai') displayZone.value = 'Asia/Shanghai'
  const event = events.value.find(e => e.event_id === state.get('event'))
  if (event) chooseEvent(event)
  const at = state.get('at')
  if (at && Number.isFinite(Date.parse(at))) seek(at)
  const ship = currentShips.value.find(s => String(s.id) === state.get('ship'))
  if (ship) chooseShip(ship)
  const lat = Number(state.get('lat')), lon = Number(state.get('lon')), zoom = Number(state.get('z'))
  if (state.has('lat') && state.has('lon') && Number.isFinite(lat) && Math.abs(lat) <= 85 && Number.isFinite(lon) && Math.abs(lon) <= 180 && zoom >= 3 && zoom <= 19)
    sharedView.value = { lat, lon, zoom }
}

async function loadEvents() {
  eventsLoading.value = true
  eventsError.value = ''
  try {
    events.value = await fetchEvents()
  } catch (e) {
    eventsError.value = describeApiError(e, '事件加载失败')
  } finally {
    eventsLoading.value = false
  }
}
// P3/P4/P5：MobilityDB 派生层。相遇与健康随初始化加载；停留图层按需加载一次。
const dwellData = ref<ApiDwellResponse | null>(null)
const encounterList = ref<ApiEncounter[]>([])
const selectedEncounter = ref<ApiEncounter | null>(null)
const health = ref<ApiDataHealth | null>(null)
const encountersLoading = ref(true)
const encounterError = ref('')

async function loadEncounters() {
  encountersLoading.value = true
  encounterError.value = ''
  try {
    const data = await fetchEncounters()
    encounterList.value = data.encounters
  } catch (e) {
    encounterError.value = describeApiError(e, '相遇分析加载失败')
  } finally {
    encountersLoading.value = false
  }
}
async function loadHealth() {
  try {
    health.value = await fetchDataHealth()
  } catch {
    health.value = null
  }
}
async function loadDwellOnce() {
  if (dwellData.value) return
  try {
    dwellData.value = await fetchDwell()
  } catch (e) {
    notice.value = describeApiError(e, '停留识别加载失败')
  }
}
watch(() => layers.value.dwell, (on) => {
  if (on) void loadDwellOnce()
})
// 选中相遇：高亮该对并在地图定位；接近不等于实际交互，仅模拟时空邻近。
function chooseEncounter(enc: ApiEncounter) {
  selectedEncounter.value = enc
  layers.value.encounters = true
}
// 按默认参数（3 NM / 30 分钟重叠 / 60 秒采样）受控重建相遇派生层，随后刷新列表与健康状态。
async function reanalyzeEncounters() {
  encountersLoading.value = true
  encounterError.value = ''
  try {
    const result = await analyzeEncounters({ distance_nm: 3, overlap_min: 30, sample_seconds: 60 })
    notice.value = `相遇分析重建完成：${result.summary.rows} 对（阈值 ${result.params.distance_nm} NM / 重叠 ${result.params.overlap_min} 分钟）。`
    await loadEncounters()
    void loadHealth()
  } catch (e) {
    encounterError.value = describeApiError(e, '相遇分析重建失败')
  } finally {
    encountersLoading.value = false
  }
}
function chooseShip(ship: ApiMapShip) {
  if (selectedShipId.value !== ship.id) trackVisible.value = false
  selectedShipId.value = ship.id
  selectedEvent.value = null
  panel.value = 'ships'
  panelOpen.value = true
  layers.value.ships = true
  focusShipRequest.value++
}
function clearShip() {
  selectedShipId.value = null
  trackVisible.value = false
  isolated.value = false
}
// P2：事件面板「地图定位」关联船——在回放快照中找船并选中聚焦。
function focusShipById(shipId: number) {
  const ship = currentShips.value.find((item) => item.id === shipId)
  if (ship) chooseShip(ship)
}
function chooseEvent(event: ApiEvent) {
  clearShip()
  if (eventType.value !== 'all' && eventType.value !== event.event_type)
    eventType.value = 'all'
  selectedEvent.value = event
  panel.value = 'events'
  panelOpen.value = true
  layers.value.events = true
  // 地图按回放时刻逐步呈现事件：选中尚未到呈现时刻（或无可排序时间）的事件时如实提示。
  const reveal = eventRevealTime(event)
  if (reveal === null)
    notice.value = '该事件缺少发生日期与报道日期，无法放入时间序列，地图暂不标注。'
  else if (time.value && reveal > Date.parse(time.value))
    notice.value = `该事件记录时间晚于当前回放时刻，地图暂不标注；回放推进到 ${formatTime(new Date(reveal).toISOString(), true)} 后显示。`
}
// 智能体回答中的「地图定位」：定位的是地图当前回放时刻的位置；
// 目标不在当前回放快照或缺少位置时如实提示，不伪造。
function locateAgentShip(shipId: number) {
  const ship = currentShips.value.find((item) => item.id === shipId)
  if (!ship) {
    notice.value = `当前回放时刻没有 ID ${shipId} 的船位；地图显示的是当前时刻快照，可调整时间后再定位。`
    return
  }
  chooseShip(ship)
}
function locateAgentEvent(eventId: string) {
  const event = events.value.find((item) => item.event_id === eventId)
  if (!event) {
    notice.value = `未找到事件 ${eventId}。`
    return
  }
  if (!hasEventLocation(event)) {
    notice.value = `事件 ${eventId} 没有地图位置（报道未给出可定位地点）。`
    return
  }
  chooseEvent(event)
}
function restore() {
  clearShip()
  selectedEvent.value = null
  globalViewRequest.value++
}
function togglePanel(value: Panel) {
  panel.value = value
  panelOpen.value = true
  picking.value = false
}
const panelTitles: Record<Panel, string> = {
  overview: '态势概览',
  events: '新闻事件',
  ships: '船舶',
  agent: '智能体',
  analysis: '半径分析',
}
const headTitle = computed(() => panelTitles[panel.value])
const headContext = computed(() => {
  if (panel.value === 'events' && selectedEvent.value) return selectedEvent.value.title
  if (panel.value === 'ships' && selectedShip.value) return selectedShip.value.name
  return ''
})
function backToOverview() {
  clearShip()
  selectedEvent.value = null
  panel.value = 'overview'
}
function chooseCenter(point: GeoPoint) {
  center.value = point
  picking.value = false
  panel.value = 'analysis'
  panelOpen.value = true
}
function startPicking() {
  picking.value = !picking.value
  layersOpen.value = false
  if (picking.value && window.matchMedia('(max-width: 760px)').matches)
    panelOpen.value = false
}
function openAreaAnalysis() {
  togglePanel('analysis')
  startPicking()
}
function changeEventType(value: string) {
  eventType.value = value
  selectedEvent.value = null
}
function toggleTrack() {
  trackVisible.value = !trackVisible.value
  layers.value.tracks = true
}
// P1 速度着色：消费 /api/tracks 派生层（数据库插值 + 实测速度序列）。
const speedColorOn = ref(false)
// 开启后只着色回放时刻前 24 小时；关闭则与显示的轨迹同范围（超出 24h 的部分分片取回）。
const speedColorRecent24h = ref(false)
const speedSegments = ref<ApiTrackSegment[]>([])
// 着色范围与地图当前显示的轨迹一致：起点为首个可见报位点，终点为回放时刻。
// 边界量化到 15 分钟边界，避免回放步进触发频繁重取；量化后仍不超出显示范围。
// 后端单次查询窗口上限 24h，跨度更长时拆成多个 ≤24h 的分片并行取回，按 segment_no 去重合并；
// 分片起点对齐首个可见报位点，随回放推进分片边界保持稳定，只有末分片需要重取。
const speedChunks = computed(() => {
  if (!time.value || selectedShipId.value === null) return null
  const endMs = Date.parse(time.value)
  const cutoff = trackRecent24h.value ? endMs - 24 * 60 * 60 * 1000 : null
  const visible = (tracks.value[selectedShipId.value] ?? []).filter(
    (p) =>
      Date.parse(p.recorded_at) <= endMs &&
      (cutoff === null || Date.parse(p.recorded_at) >= cutoff),
  )
  if (!visible.length) return null
  const toMs = Math.floor(endMs / 900000) * 900000
  let fromMs = Math.ceil(Date.parse(visible[0]!.recorded_at) / 900000) * 900000
  if (speedColorRecent24h.value)
    fromMs = Math.max(fromMs, toMs - 24 * 60 * 60 * 1000)
  if (toMs <= fromMs)
    return [{ from: visible[0]!.recorded_at, to: new Date(endMs).toISOString() }]
  const DAY = 24 * 60 * 60 * 1000
  const chunks: { from: string; to: string }[] = []
  for (let start = fromMs; start < toMs; start += DAY)
    chunks.push({
      from: new Date(start).toISOString(),
      to: new Date(Math.min(start + DAY, toMs)).toISOString(),
    })
  return chunks
})
watch(
  () => [
    selectedShipId.value,
    speedColorOn.value,
    speedChunks.value?.map((c) => `${c.from}|${c.to}`).join(';'),
  ],
  async () => {
    const chunks = speedChunks.value
    if (!speedColorOn.value || selectedShipId.value === null || !chunks) {
      speedSegments.value = []
      return
    }
    const id = selectedShipId.value
    try {
      const results = await Promise.all(
        chunks.map((c) => fetchShipTracks(id, c.from, c.to)),
      )
      if (selectedShipId.value !== id) return
      // 相邻分片都会返回跨边界的整条 segment，按 segment_no 去重（保留顶点更全的一份），
      // 超出显示范围的顶点由 MapView 按时间戳裁剪。
      const merged = new Map<number, ApiTrackSegment>()
      for (const data of results) {
        if (data.status !== 'ok') continue
        for (const segment of data.segments) {
          const existing = merged.get(segment.segment_no)
          if (
            !existing ||
            segment.geometry.coordinates.length > existing.geometry.coordinates.length
          )
            merged.set(segment.segment_no, segment)
        }
      }
      speedSegments.value = [...merged.values()].sort(
        (a, b) => a.segment_no - b.segment_no,
      )
    } catch {
      if (selectedShipId.value === id) speedSegments.value = []
    }
  },
  { immediate: true },
)
function toggleSpeedColor() {
  speedColorOn.value = !speedColorOn.value
  if (speedColorOn.value) {
    trackVisible.value = true
    layers.value.tracks = true
  }
}
function clearArea() {
  fenceEnabled.value = false
  center.value = null
  picking.value = false
}
function onKey(event: KeyboardEvent) {
  if (event.key === 'Escape') {
    clearShip()
    selectedEvent.value = null
    picking.value = false
    layersOpen.value = false
    legendOpen.value = false
    panel.value = 'overview'
  }
}
onMounted(() => {
  void initialize()
  window.addEventListener('keydown', onKey)
})
onBeforeUnmount(() => window.removeEventListener('keydown', onKey))
</script>

<template>
  <main class="workbench" :class="{ 'panel-collapsed': !panelOpen }">
    <header class="topbar">
      <div class="brand">
        <img class="brand-logo" :src="logoUrl" alt="" aria-hidden="true" />
        <div>
          <h1>霍尔木兹<span>海事态势分析</span></h1>
        </div>
      </div>
      <div class="top-status">
        <span class="simulation-label">模拟船舶 · 新闻事件</span>
        <button @click="displayZone = displayZone === 'UTC' ? 'Asia/Shanghai' : 'UTC'" aria-label="切换时区">{{ zoneLabel() }}</button>
        <button @click="theme = theme === 'dark' ? 'light' : 'dark'" aria-label="切换地图主题">{{ theme === 'dark' ? '浅色' : '深色' }}</button>
        <details class="top-more">
          <summary aria-label="更多" title="更多">⋯</summary>
          <div class="top-more-menu">
            <a href="http://127.0.0.1:8000/mobility-demo" target="_blank" rel="noopener">停留分析试验</a>
          </div>
        </details>
      </div>
      <button
        class="panel-toggle"
        :aria-expanded="panelOpen"
        aria-label="切换工作面板"
        @click="panelOpen = !panelOpen"
      >
        {{ panelOpen ? '收起面板' : '工作面板' }}
      </button>
    </header>
    <ToolRail
      :layers-active="layersOpen"
      :area-active="picking"
      :agent-active="panel === 'agent' && panelOpen"
      @open-layers="layersOpen = !layersOpen"
      @start-area="openAreaAnalysis"
      @share="shareRequest++"
      @print="printReport"
      @open-agent="togglePanel('agent')"
    />
    <LayersPopover
      v-if="layersOpen"
      v-model:layers="layers"
      v-model:vector-minutes="vectorMinutes"
      v-model:vector-linked="vectorLinked"
      :harbour-status="harbourStatus"
      :country-status="countryStatus"
      :effective-vector="effectiveVector"
      @close="layersOpen = false"
    />
    <section class="map-workspace" aria-label="霍尔木兹海峡态势地图">
      <MapView
        :ships="currentShips"
        :events="mapEvents"
        :selected-ship-id="selectedShipId"
        :selected-event="selectedEvent"
        :track="selectedTrack"
        :track-visible="trackVisible"
        :speed-segments="speedColorOn ? speedSegments : null"
        :isolated="isolated"
        :layers="layers"
        :global-view-request="globalViewRequest"
        :focus-ship-request="focusShipRequest"
        :nearby-ship-ids="nearbyShipIds"
        :area-center="center"
        :radius-nm="radius"
        :picking="picking"
        :theme="theme"
        :time="time"
        :vector-minutes="effectiveVector"
        :track-recent-24h="trackRecent24h"
        :share-request="shareRequest"
        :shared-view="sharedView"
        :dwell="dwellData"
        :encounters="encounterList"
        :selected-encounter="selectedEncounter"
        @share-view="shareView"
        @clear-selection="selectedEvent = null; clearShip()"
        @select-ship="chooseShip"
        @select-event="chooseEvent"
        @select-encounter="chooseEncounter"
        @bounds-change="bounds = $event"
        @pick-center="chooseCenter"
        @harbour-status="harbourStatus = $event"
        @country-status="countryStatus = $event"
      />
      <div class="map-top-tools">
        <ShipSearch
          :ships="currentShips"
          :loading="loading"
          :events="events"
          @select-event="chooseEvent"
          @select="chooseShip"
        /><button
          class="map-tool"
          @click="restore"
          title="回到霍尔木兹海峡全局视野"
        >
          ⌖ 全局视野
        </button>
      </div>
      <div v-if="notice" class="alert-toast" role="status"><span>{{ notice }}</span><button @click="notice = ''" aria-label="关闭提醒">×</button></div>
      <div v-if="picking" class="map-instruction" role="status">
        点击地图选点，或按 Enter 使用视野中心
        <button @click="picking = false">取消</button>
      </div>
      <div v-if="isolated" class="isolation-banner">
        仅显示选中船舶 <button @click="isolated = false">恢复全部</button>
      </div>
      <div class="map-hud">
        <span
          ><strong>{{ viewShips.length }}</strong> 船</span
        ><span
          ><strong>{{ viewEvents.length }}</strong> 已呈现事件</span
        ><span class="hud-speed"
          >均速 <strong>{{ averageSpeed }}</strong> kn</span
        >
      </div>
      <button
        class="legend-toggle"
        :aria-expanded="legendOpen"
        aria-label="图例与数据说明"
        title="图例与数据说明"
        @click="legendOpen = !legendOpen"
      >
        ⓘ
      </button>
      <div v-if="legendOpen" class="map-legend">
        <div class="legend-events">
          <span v-for="(kind, key) in eventKinds" :key="key" class="legend-event"
            ><img :src="kind.icon" alt="">{{ kind.label }}</span
          >
        </div>
        <span><b class="vessel-key">▲</b> 当前船位</span
        ><span><b class="track-key">─•─</b> 已航行轨迹</span
        ><span>船位为教学模拟；事件为代表点，非精确事发位置</span
        ><span>事件随回放时刻按记录时间先后逐步呈现</span>
      </div>
      <div v-if="loading || error" class="map-data-status" role="status">
        {{ error || '正在载入船舶与历史采样…'
        }}<button v-if="error" @click="load">重试</button>
      </div>
      <div class="timeline-dock">
        <TimelineControls
          v-model="index"
          :frame-times="times"
          :events="timelineEvents"
          :selected-event-id="selectedEvent?.id ?? null"
          :seek-request="seekRequest"
          :loading="loading"
          :error-message="error"
          :event-type="eventType"
          @speed-change="playbackSpeed = $event"
          @retry="load"
          @select-event="chooseEvent"
          @type-change="changeEventType"
        />
      </div>
    </section>
    <aside v-show="panelOpen" class="inspector" aria-label="上下文工作面板">
      <header class="inspector-head">
        <button
          v-if="panel !== 'overview'"
          class="head-back"
          aria-label="返回态势概览"
          title="返回态势概览"
          @click="backToOverview"
        >
          ‹</button
        >
        <h2>
          {{ headTitle
          }}<span v-if="headContext" :title="headContext">· {{ headContext }}</span>
        </h2>
      </header>
      <OverviewPanel
        v-if="panel === 'overview'"
        :time="time"
        :view-ships="viewShips"
        :view-events="viewEvents"
        :events="filteredEvents"
        :total-ships="currentShips.length"
        :total-events="events.length"
        :average-speed="averageSpeed"
        :events-loading="eventsLoading"
        :encounters="encounterList"
        :health="health"
        :encounters-loading="encountersLoading"
        :encounter-error="encounterError"
        @select-ship="chooseShip"
        @select-event="chooseEvent"
        @select-encounter="chooseEncounter"
        @reanalyze-encounters="reanalyzeEncounters"
        @open-events="togglePanel('events')"
        @open-ships="togglePanel('ships')"
      />
      <EventPanel
        v-if="panel === 'events'"
        :events="filteredEvents"
        :total-count="events.length"
        :event-type="eventType"
        :sort="eventSort"
        :selected="selectedEvent"
        :loading="eventsLoading"
        :error="eventsError"
        @select="chooseEvent"
        @select-ship="focusShipById"
        @type-change="changeEventType"
        @sort-change="eventSort = $event"
        @clear="selectedEvent = null"
        @retry="loadEvents"
      />
      <ShipInspector
        v-if="panel === 'ships'"
        :time="time"
        :ship="selectedShip"
        :ships="currentShips"
        :track="selectedTrack"
        :track-visible="trackVisible"
        :speed-color="speedColorOn"
        v-model:track-recent-24h="trackRecent24h"
        v-model:speed-color-recent-24h="speedColorRecent24h"
        :isolated="isolated"
        :nearby-events="nearbyEvents"
        :events-error="eventsError"
        :events-loading="eventsLoading"
        @select="chooseShip"
        @clear="clearShip"
        @track="toggleTrack"
        @speed-color="toggleSpeedColor"
        @isolate="isolated = !isolated"
        @event="chooseEvent"
        @locate="focusShipRequest++"
      />
      <AgentPanel
        v-if="panel === 'agent'"
        @locate-ship="locateAgentShip"
        @locate-event="locateAgentEvent"
      />
      <WorkspaceTools
        v-if="panel === 'analysis'"
        v-model:radius="radius"
        :center="center"
        :result="areaResult"
        :view-ships="viewShips"
        :view-event-count="viewEvents.length"
        :time="time"
        :picking="picking"
        :loading="loading"
        :error="error"
        @pick="startPicking"
        @clear="clearArea"
        @select-ship="chooseShip"
        @select-event="chooseEvent"
      />
      <div v-if="panel === 'analysis' && center" class="display-settings"><label><input type="checkbox" v-model="fenceEnabled" /> 将查询圆设为模拟电子围栏</label><p class="caption">{{ fenceEnabled ? `围栏内 ${fenceInside.length} 艘；随回放提示进入/离开。` : '仅本次会话有效；不判断两个采样之间的穿越。' }}</p></div>
    </aside>
    <section class="print-report">
      <h2>霍尔木兹海峡 · 船位与新闻概览</h2><p>{{ formatTime(time, true) }} {{ zoneLabel() }} · 船位为教学模拟，新闻事件为独立历史资料</p>
      <p>当前视野 {{ viewShips.length }} 艘船舶、{{ viewEvents.length }} 条已呈现新闻事件（随回放时刻逐步出现）。选中船：{{ selectedShip?.name ?? '无' }}；选中事件：{{ selectedEvent?.title ?? '无' }}。</p>
      <table><thead><tr><th>事件时间文字</th><th>事件</th><th>经纬度</th></tr></thead><tbody><tr v-for="e in viewEvents" :key="e.id"><td>{{ eventTimeText(e) }}</td><td>{{ e.title }}</td><td>{{ eventCoordinates(e) }}</td></tr></tbody></table>
    </section>
  </main>
</template>
