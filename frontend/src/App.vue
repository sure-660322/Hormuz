<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount, ref, watch } from 'vue'
import { fetchEvents, fetchShipTracks, fetchShipTrackWindow, fetchDwell, fetchEncounters, analyzeEncounters, fetchDataHealth, describeApiError, type AgentMapAction, type ApiEvent, type ApiMapShip, type ApiTrackSegment, type ApiTrackWindow, type ApiDwellResponse, type ApiEncounter, type ApiDataHealth } from './api'
import { usePlayback } from './composables/usePlayback'
import {
  inBounds,
  formatTime,
  displayZone, zoneLabel, hasEventLocation, eventOccurredBy, eventKinds,
  type LayerState,
  type Panel,
  type ViewBounds,
} from './domain/maritime'
import logoUrl from './assets/logo.png'
import MapView from './components/MapView.vue'
import EventPanel from './components/EventPanel.vue'
import AgentPanel from './components/AgentPanel.vue'
import ShipInspector from './components/ShipInspector.vue'
import TimelineControls from './components/TimelineControls.vue'
import ToolRail from './components/ToolRail.vue'
import OverviewPanel from './components/OverviewPanel.vue'
import LayersPopover from './components/LayersPopover.vue'
import ExplorerSidebar from './components/ExplorerSidebar.vue'

const {
  tracks,
  index,
  loading,
  error,
  time,
  requestedTime,
  times,
  currentShips,
  frameReady,
  isRealAis,
  hasEvents,
  hasDerived,
  snapshotLoading,
  snapshotError,
  load,
  seek,
  retrySnapshot,
} = usePlayback()
const events = ref<ApiEvent[]>([])
const eventsLoading = ref(true)
const eventsError = ref('')
const panel = ref<Panel>('overview')
const panelOpen = ref(false)
const workspaceMode = ref<'overview' | 'explore'>('explore')
const exploreCategory = ref<'events' | 'ships'>('events')
const sidebarOpen = ref(false)
const layersOpen = ref(false)
const legendOpen = ref(false)
const selectedShipId = ref<number | null>(null)
const selectedEvent = ref<ApiEvent | null>(null)
const eventType = ref('all')
const eventSort = ref<'asc' | 'desc'>('desc')
const isolated = ref(false)
const trackVisible = ref(false)
const globalViewRequest = ref(0)
const focusShipRequest = ref(0)
const focusTrackRequest = ref(0)
const agentTrack = ref<ApiTrackWindow | null>(null)
let mapActionVersion = 0
watch(time, at => {
  if (!agentTrack.value || !at) return
  const current = Date.parse(at)
  if (current < Date.parse(agentTrack.value.from) || current > Date.parse(agentTrack.value.to)) {
    agentTrack.value = null
    trackVisible.value = false
    mapActionVersion++
  }
})
const seekRequest = ref(0)
const bounds = ref<ViewBounds | null>(null)
const harbourStatus = ref('按需加载')
const countryStatus = ref('按需加载')
const theme = ref<'dark' | 'light'>('dark')
const vectorMinutes = ref(6)
// 轨迹展示范围：默认显示全部已回放报位点；开启后只看回放时刻前 24 小时。
const trackRecent24h = ref(false)
const realTrackHours = ref<1 | 6 | 24>(24)
const realPointsVisible = ref(false)
const realTrack = ref<ApiTrackWindow | null>(null)
const realTrackLoading = ref(false)
const realTrackError = ref('')
watch(
  () => [isRealAis.value, selectedShipId.value, trackVisible.value, time.value, realTrackHours.value] as const,
  (state, _old, onCleanup) => {
    const [real, shipId, visible, at, hours] = state
    realTrack.value = null
    realTrackError.value = ''
    realTrackLoading.value = false
    if (!real || shipId === null || !visible || !at || !times.value.length) return
    const end = Date.parse(at)
    const start = Math.max(Date.parse(times.value[0]!), end - hours * 3600_000)
    if (end <= start) return
    const controller = new AbortController()
    const timer = setTimeout(async () => {
      realTrackLoading.value = true
      try {
        realTrack.value = await fetchShipTrackWindow(shipId, new Date(start).toISOString(), at,
          hours === 1 ? 30 : hours === 6 ? 120 : 300, controller.signal)
      } catch (e) {
        if (!controller.signal.aborted) realTrackError.value = describeApiError(e, '单船轨迹加载失败')
      } finally {
        if (!controller.signal.aborted) realTrackLoading.value = false
      }
    }, 150)
    onCleanup(() => { clearTimeout(timer); controller.abort() })
  },
)
const playbackSpeed = ref(1)
const vectorLinked = ref(false)
const effectiveVector = computed(() => vectorMinutes.value * (vectorLinked.value ? playbackSpeed.value : 1))
const notice = ref('')
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
  [...events.value].filter(e =>
    (eventType.value === 'all' || e.event_type === eventType.value) && eventOccurredBy(e, time.value),
  )
    .sort((a, b) => {
      const left = a.occurred_at!.slice(0, 10), right = b.occurred_at!.slice(0, 10)
      return (left.localeCompare(right) || a.event_id.localeCompare(b.event_id)) * (eventSort.value === 'asc' ? 1 : -1)
    }),
)
// 地图与列表共用事件发生时间门控；无代表坐标的已发生事件只进入列表。
const mapEvents = computed(() => filteredEvents.value.filter(hasEventLocation))
const untimedEvents = computed(() => events.value.filter(e =>
  !e.occurred_at && (eventType.value === 'all' || e.event_type === eventType.value),
))
watch([time, displayZone], () => {
  if (!selectedEvent.value || !selectedEvent.value.occurred_at || eventOccurredBy(selectedEvent.value, time.value)) return
  selectedEvent.value = null
  if (panel.value === 'events') panelOpen.value = false
})
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
const snapshotAverageSpeed = computed(() =>
  currentShips.value.length
    ? (currentShips.value.reduce((sum, ship) => sum + ship.speed, 0) / currentShips.value.length).toFixed(1)
    : '—',
)
// 新闻与船位来源独立：不因时间或空间接近建立关联。
const nearbyEvents: (ApiEvent & { distance: number })[] = []
const nearbyShipIds: number[] = []
watch(theme, value => document.documentElement.dataset.theme = value, { immediate: true })
async function initialize() {
  await load()
  const supplementary: Promise<void>[] = []
  if (hasEvents.value) supplementary.push(loadEvents())
  else {
    exploreCategory.value = 'ships'
    events.value = []
    eventsLoading.value = false
    eventsError.value = '当前试点库未接入新闻事件。'
  }
  if (hasDerived.value) {
    supplementary.push(loadEncounters(), loadHealth())
  } else {
    encountersLoading.value = false
  }
  await Promise.all(supplementary)
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
    if (data.status === 'not_built') {
      encounterList.value = []
      encounterError.value = data.message
    } else {
      encounterList.value = data.encounters
    }
  } catch (e) {
    encounterList.value = []
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
  if (!hasDerived.value) return
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
// 选中相遇：高亮该对并在地图定位；接近不等于实际交互。
function chooseEncounter(enc: ApiEncounter) {
  selectedEncounter.value = enc
  layers.value.encounters = true
}
// 按默认参数（3 NM / 30 分钟重叠 / 60 秒采样）受控重建相遇派生层，随后刷新列表与健康状态。
async function reanalyzeEncounters() {
  if (!hasDerived.value) return
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
  agentTrack.value = null
  mapActionVersion++
  if (selectedShipId.value !== ship.id) {
    trackVisible.value = false
    if (isRealAis.value) {
      realPointsVisible.value = false
      speedColorOn.value = false
    }
  }
  selectedShipId.value = ship.id
  selectedEvent.value = null
  panel.value = 'ships'
  workspaceMode.value = 'explore'
  exploreCategory.value = 'ships'
  panelOpen.value = true
  sidebarOpen.value = false
  layers.value.ships = true
  focusShipRequest.value++
}
function clearShip() {
  agentTrack.value = null
  mapActionVersion++
  selectedShipId.value = null
  trackVisible.value = false
  realPointsVisible.value = false
  isolated.value = false
}
// P2：事件面板「地图定位」关联船——在回放快照中找船并选中聚焦。
function focusShipById(shipId: number) {
  const ship = currentShips.value.find((item) => item.id === shipId)
  if (ship) chooseShip(ship)
}
function chooseEvent(event: ApiEvent) {
  if (event.occurred_at && !eventOccurredBy(event, time.value)) {
    notice.value = '该新闻事件尚未到达发生日期，请向后拖动时间轴。'
    return
  }
  clearShip()
  if (eventType.value !== 'all' && eventType.value !== event.event_type)
    eventType.value = 'all'
  selectedEvent.value = event
  panel.value = 'events'
  workspaceMode.value = 'explore'
  exploreCategory.value = 'events'
  panelOpen.value = true
  sidebarOpen.value = false
  layers.value.events = true
  if (!event.occurred_at) notice.value = '发生日期未明确：可阅读详情，但地图回放不显示此事件点。'
  else if (!hasEventLocation(event)) notice.value = '该新闻事件没有可定位的代表坐标，详情仍可阅读。'
}
// 智能体回答中的「地图定位」只定位当前回放时刻已出现的事件和船位。
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
async function executeMapAction(action: AgentMapAction): Promise<string> {
  if (action.type === 'event') {
    if (action.source !== 'news' || !action.event_id) return '事件标识或来源无效。'
    const event = events.value.find(item => item.event_id === action.event_id)
    if (!event) return `未找到事件 ${action.event_id}。`
    if (!hasEventLocation(event)) return `事件 ${action.event_id} 没有可定位的代表坐标。`
    if (!event.occurred_at || !eventOccurredBy(event, time.value)) return '事件发生日期尚未进入当前回放范围；请调整时间轴。'
    chooseEvent(event)
    return selectedEvent.value?.event_id === action.event_id ? '事件已在地图选中。' : '事件未能选中。'
  }
  if (action.source !== 'nnu_ais' || !Number.isSafeInteger(action.ship_id) || action.ship_id <= 0) return '船舶标识或来源无效。'
  const start = Date.parse(action.start_at), end = Date.parse(action.end_at)
  const first = Date.parse(times.value[0] ?? ''), last = Date.parse(times.value.at(-1) ?? '')
  if (![start, end, first, last].every(Number.isFinite) || start >= end || end - start > 86400000 || start < first || end > last)
    return '轨迹时间窗无效或超出本批 AIS 覆盖；单次最多 24 小时。'
  const version = ++mapActionVersion
  let loaded: ApiTrackWindow
  try {
    loaded = await fetchShipTrackWindow(action.ship_id, new Date(start).toISOString(), new Date(end).toISOString(), 300)
  } catch (e) { return describeApiError(e, '轨迹加载失败') }
  if (version !== mapActionVersion) return '地图目标已变更，本次操作已取消。'
  const points = loaded.segments.flatMap(segment => segment.points)
  if (points.length < 2) return points.length
    ? '指定时间窗只有一个采样报位，无法绘制轨迹。'
    : '指定时间窗没有该船报位，无法显示轨迹。'
  const latest = points.at(-1)!
  seek(latest.recorded_at)
  const deadline = Date.now() + 20000
  while (version === mapActionVersion && !snapshotError.value && !frameReady.value && Date.now() < deadline)
    await new Promise(resolve => setTimeout(resolve, 100))
  const ready = frameReady.value && !snapshotError.value && requestedTime.value !== null && Date.parse(requestedTime.value) >= Date.parse(latest.recorded_at)
  if (version !== mapActionVersion) return '地图目标已变更，本次操作已取消。'
  if (!ready) return snapshotError.value || '回放快照未能加载，轨迹未选中。'
  const ship = currentShips.value.find(item => item.id === action.ship_id)
  if (!ship) return '轨迹有报位，但所选回放帧没有该船的有效快照。'
  chooseShip(ship)
  agentTrack.value = loaded
  trackVisible.value = true
  layers.value.tracks = true
  focusTrackRequest.value++
  return `已在地图显示船 ID ${action.ship_id} 的轨迹（${new Date(start).toISOString()} 至 ${new Date(end).toISOString()}）。`
}
function restore() {
  clearShip()
  selectedEvent.value = null
  globalViewRequest.value++
}
function togglePanel(value: Panel) {
  panel.value = value
  workspaceMode.value = 'explore'
  panelOpen.value = true
}
const panelTitles: Record<Panel, string> = {
  overview: '态势概览',
  events: '新闻事件',
  ships: '船舶',
  agent: '智能体',
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
  panelOpen.value = false
}
function openExplorer(category: 'events' | 'ships') {
  workspaceMode.value = 'explore'
  exploreCategory.value = category
  backToOverview()
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
function toggleRealPoints() {
  realPointsVisible.value = !realPointsVisible.value
  if (realPointsVisible.value) {
    trackVisible.value = true
    layers.value.tracks = true
  }
}
function onKey(event: KeyboardEvent) {
  if (event.key === 'Escape') {
    clearShip()
    selectedEvent.value = null
    layersOpen.value = false
    legendOpen.value = false
    panel.value = 'overview'
    panelOpen.value = false
    sidebarOpen.value = false
  }
}
onMounted(() => {
  void initialize()
  window.addEventListener('keydown', onKey)
})
onBeforeUnmount(() => window.removeEventListener('keydown', onKey))
</script>

<template>
  <main class="workbench" :class="{ 'show-overview': workspaceMode === 'overview', 'detail-open': panelOpen }">
    <header class="topbar">
      <div class="brand">
        <img class="brand-logo" :src="logoUrl" alt="" aria-hidden="true" />
        <div>
          <h1>霍尔木兹<span>海事态势分析</span></h1>
        </div>
      </div>
      <nav class="workspace-nav" aria-label="工作视图">
        <button :class="{ active: workspaceMode === 'overview' }" :aria-current="workspaceMode === 'overview' ? 'page' : undefined" @click="workspaceMode = 'overview'; panelOpen = false">态势总览</button>
        <button :class="{ active: workspaceMode === 'explore' }" :aria-current="workspaceMode === 'explore' ? 'page' : undefined" @click="workspaceMode = 'explore'">地图探索</button>
      </nav>
      <div class="top-status">
        <span class="simulation-label">{{ isRealAis ? '历史 AIS 船位 · 新闻独立' : '船舶轨迹 · 新闻事件' }}</span>
        <button @click="displayZone = displayZone === 'UTC' ? 'Asia/Shanghai' : 'UTC'" aria-label="切换时区">{{ zoneLabel() }}</button>
        <button @click="theme = theme === 'dark' ? 'light' : 'dark'" aria-label="切换地图主题">{{ theme === 'dark' ? '浅色' : '深色' }}</button>
      </div>
      <button class="sidebar-toggle" :aria-expanded="sidebarOpen" @click="sidebarOpen = !sidebarOpen; workspaceMode = 'explore'">{{ sidebarOpen ? '收起列表' : '查找' }}</button>
    </header>
    <ExplorerSidebar
      v-model="exploreCategory"
      class="explorer-placement"
      :class="{ 'mobile-open': sidebarOpen }"
      :events="filteredEvents"
      :ships="currentShips"
      :total-events="events.length"
      :events-loading="eventsLoading"
      :events-error="eventsError"
      :events-available="hasEvents"
      :ships-loading="loading"
      :current-time="time"
      :untimed-events="untimedEvents"
      :event-type="eventType"
      :event-sort="eventSort"
      :selected-event-id="selectedEvent?.event_id ?? null"
      :selected-ship-id="selectedShipId"
      @select-event="chooseEvent"
      @select-ship="chooseShip"
      @type-change="changeEventType"
      @sort-change="eventSort = $event"
      @retry="loadEvents"
    />
    <section class="map-workspace" aria-label="霍尔木兹海峡态势地图">
      <ToolRail
        :layers-active="layersOpen"
        :agent-active="panel === 'agent' && panelOpen"
        @open-layers="layersOpen = !layersOpen"
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
        :real-ais="isRealAis"
        @close="layersOpen = false"
      />
      <MapView
        :ships="currentShips"
        :events="mapEvents"
        :selected-ship-id="selectedShipId"
        :selected-event="selectedEvent && eventOccurredBy(selectedEvent, time) ? selectedEvent : null"
        :track="selectedTrack"
        :track-visible="trackVisible"
        :speed-segments="speedColorOn ? speedSegments : null"
        :window-segments="agentTrack ? agentTrack.segments : (isRealAis ? (realTrack?.segments ?? []) : null)"
        :window-speed-color="isRealAis && speedColorOn"
        :window-points-visible="isRealAis && realPointsVisible"
        :isolated="isolated"
        :layers="layers"
        :global-view-request="globalViewRequest"
        :focus-ship-request="focusShipRequest"
        :focus-track-request="focusTrackRequest"
        :nearby-ship-ids="nearbyShipIds"
        :theme="theme"
        :time="time"
        :vector-minutes="effectiveVector"
        :track-recent-24h="trackRecent24h"
        :dwell="dwellData"
        :encounters="encounterList"
        :selected-encounter="selectedEncounter"
        @clear-selection="selectedEvent = null; clearShip(); panelOpen = false"
        @select-ship="chooseShip"
        @select-event="chooseEvent"
        @select-encounter="chooseEncounter"
        @bounds-change="bounds = $event"
        @harbour-status="harbourStatus = $event"
        @country-status="countryStatus = $event"
      />
      <div class="map-top-tools">
        <button
          class="map-tool"
          @click="restore"
          title="回到霍尔木兹海峡全局视野"
        >
          ⌖ 全局视野
        </button>
      </div>
      <div v-if="isRealAis" class="ais-snapshot-strip" role="status">
        <strong>历史 AIS · {{ formatTime(time, true) }} {{ zoneLabel() }}</strong>
        <span>快照 {{ currentShips.length }} 艘，视野内 {{ viewShips.length }} 艘</span>
        <span>仅采用此前 1 小时内的最新报位</span>
        <span v-if="snapshotLoading && requestedTime !== time">正在获取 {{ formatTime(requestedTime, true) }} 的快照</span>
      </div>
      <div v-if="notice" class="alert-toast" role="status"><span>{{ notice }}</span><button @click="notice = ''" aria-label="关闭提醒">×</button></div>
      <div v-if="isolated" class="isolation-banner">
        仅显示选中船舶 <button @click="isolated = false">恢复全部</button>
      </div>
      <div class="map-hud">
        <span v-if="isRealAis" title="历史 AIS；每艘船采用所选时刻前一小时内最新报位"><strong>历史 AIS</strong> · {{ formatTime(time, true) }} {{ zoneLabel() }} · 1 小时有效窗</span>
        <span
          ><strong>{{ viewShips.length }}</strong> 船</span
        ><span
          ><strong>{{ viewEvents.length }}</strong> 视野新闻事件</span
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
        ><span>船位来源以接入数据为准；事件为代表点，非精确事发位置</span
        ><span>新闻按事件发生时间随回放出现；日期级记录不代表精确时刻</span>
      </div>
      <div v-if="loading || error || snapshotLoading || snapshotError" class="map-data-status" role="status">
        {{ error || snapshotError || (isRealAis ? '正在查询所选时刻的船位快照…' : '正在载入船舶与历史采样…')
        }}<button v-if="error || snapshotError" @click="error ? load() : retrySnapshot()">重试</button>
      </div>
    </section>
    <section class="overview-stage" aria-label="态势总览">
      <header class="overview-stage-head"><div><p class="eyebrow">霍尔木兹海峡 · 历史船位与新闻</p><h2>从海峡动态，进入地图调查</h2><p>{{ isRealAis ? `当前接入历史 AIS：${formatTime(times[0], true)} 至 ${formatTime(times.at(-1), true)} ${zoneLabel()}；地图为所选时刻前 1 小时内的最新报位。` : '计划接入船位时段：2026-02-25 至 2026-03-03（UTC）；实际回放范围以入库数据为准。' }} 新闻事件来自独立报道，两类资料分别浏览，不据时空邻近推断真实关联。</p></div><button class="primary" @click="workspaceMode = 'explore'">进入地图探索</button></header>
      <OverviewPanel
        :time="time" :view-ships="currentShips" :view-events="mapEvents" :events="filteredEvents"
        :total-ships="currentShips.length" :total-events="events.length" :average-speed="snapshotAverageSpeed"
        :events-loading="eventsLoading" :encounters="encounterList" :health="health"
        :has-derived="hasDerived"
        :encounters-loading="encountersLoading" :encounter-error="encounterError"
        @select-ship="chooseShip" @select-event="chooseEvent" @select-encounter="chooseEncounter"
        @reanalyze-encounters="reanalyzeEncounters" @open-events="openExplorer('events')" @open-ships="openExplorer('ships')"
      />
    </section>
    <div class="timeline-dock">
      <TimelineControls
        v-model="index" :frame-times="times" :events="[]" :snapshot-mode="isRealAis" :frame-ready="frameReady" :frame-error="snapshotError"
        :selected-event-id="selectedEvent?.id ?? null" :seek-request="seekRequest"
        :loading="loading" :error-message="error" :event-type="eventType"
        @speed-change="playbackSpeed = $event" @retry="load"
        @select-event="chooseEvent" @type-change="changeEventType"
      />
    </div>
    <aside v-show="panelOpen" class="inspector" aria-label="上下文工作面板">
      <header class="inspector-head">
        <h2>
          {{ headTitle
          }}<span v-if="headContext" :title="headContext">· {{ headContext }}</span>
        </h2>
        <button v-if="panel !== 'agent'" type="button" class="locate-btn" @click="panel = 'agent'">返回对话</button>
        <button class="detail-close" aria-label="关闭详情" @click="backToOverview">×</button>
      </header>
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
        @clear="selectedEvent = null; panelOpen = false"
        @retry="loadEvents"
      />
      <ShipInspector
        v-if="panel === 'ships'"
        :time="time"
        :ship="selectedShip"
        :ships="currentShips"
        :track="selectedTrack"
        :track-visible="trackVisible"
        :track-available="true"
        :real-ais="isRealAis"
        :real-track="realTrack"
        :real-track-loading="realTrackLoading"
        :real-track-error="realTrackError"
        :real-track-hours="realTrackHours"
        :real-points-visible="realPointsVisible"
        @update:real-track-hours="realTrackHours = $event"
        :speed-color="speedColorOn"
        v-model:track-recent-24h="trackRecent24h"
        v-model:speed-color-recent-24h="speedColorRecent24h"
        :isolated="isolated"
        :nearby-events="nearbyEvents"
        :events-error="eventsError"
        :events-loading="eventsLoading"
        @select="chooseShip"
        @clear="clearShip(); panelOpen = false"
        @track="toggleTrack"
        @speed-color="toggleSpeedColor"
        @real-points="toggleRealPoints"
        @isolate="isolated = !isolated"
        @event="chooseEvent"
        @locate="focusShipRequest++"
      />
      <AgentPanel
        v-show="panel === 'agent'"
        :execute-map-action="executeMapAction"
        @locate-ship="locateAgentShip"
        @locate-event="locateAgentEvent"
      />
    </aside>
  </main>
</template>
