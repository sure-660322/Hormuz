<script setup lang="ts">
import { computed, nextTick, onMounted, onBeforeUnmount, ref, watch } from 'vue'
import { fetchEvents, fetchShipTracks, fetchShipTrackWindow, fetchDwell, fetchEncounters, describeApiError, type AgentAnalysisAction, type AgentMapAction, type ApiEvent, type ApiMapShip, type ApiTrackSegment, type ApiTrackWindow, type ApiDwellResponse, type ApiEncounter } from './api'
import {
  fetchAreaDefault, resolveAreaBounds,
  type AgentAreaAnalysisAction, type ApiAreaBounds,
} from './api'
import { usePlayback } from './composables/usePlayback'
import {
  inBounds,
  formatTime,
  displayZone, zoneLabel, hasEventLocation, eventOccurredBy, eventKinds,
  type LayerState,
  type Panel,
  type ViewBounds,
} from './domain/maritime'
import { eventSeekTime, type ShipGroup } from './domain/overview'
import logoUrl from './assets/logo.png'
import MapView from './components/MapView.vue'
import EventPanel from './components/EventPanel.vue'
import AgentPanel from './components/AgentPanel.vue'
import AreaActivityPanel from './components/AreaActivityPanel.vue'
import ShipInspector from './components/ShipInspector.vue'
import TimelineControls from './components/TimelineControls.vue'
import ToolRail from './components/ToolRail.vue'
import OverviewPanel from './components/OverviewPanel.vue'
import LayersPopover from './components/LayersPopover.vue'
import ExplorerSidebar from './components/ExplorerSidebar.vue'
import CasePanel from './components/CasePanel.vue'
import { fetchMaritimeCase, type MaritimeCaseId, type ApiMaritimeCase } from './api'
import { caseTrackChunks, mergeCaseTracks, clipCaseTracks } from './domain/casePlayback'

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
const caseOpen = ref(false)
const caseDetailsOpen = ref(true)
const caseData = ref<ApiMaritimeCase | null>(null)
const caseId = ref<MaritimeCaseId>('arctic-ocean')
let caseLoadVersion = 0
const caseLoading = ref(false)
const caseError = ref('')
const caseActive = ref(false)
const caseStageId = ref('overview')
const caseFullTrack = ref<ApiTrackWindow | null>(null)
const caseAgentWindow = computed(() => {
  const stage = caseData.value?.stages.find(s => s.id === caseStageId.value)
  return stage ? { start_at: stage.start_at, end_at: stage.end_at } : caseWindow.value
})
const caseHighlight = computed(() => {
  if (!time.value || !caseAgentWindow.value) return []
  const end = new Date(Math.min(Date.parse(time.value), Date.parse(caseAgentWindow.value.end_at))).toISOString()
  return clipCaseTracks(caseFullTrack.value, caseAgentWindow.value.start_at, end)
})
const caseWindow = ref<{ start_at: string; end_at: string } | null>(null)
const caseSwitching = ref(false)
const casePlaying = ref(false)
const timelineControls = ref<InstanceType<typeof TimelineControls> | null>(null)
const savedCaseView = ref<{
  time: string | null; view: ReturnType<InstanceType<typeof MapView>['captureView']>
  ship: number | null; event: ApiEvent | null; panel: Panel; panelOpen: boolean
  workspace: 'overview' | 'explore'; layers: LayerState; isolated: boolean; trackVisible: boolean
  sidebarOpen: boolean; category: 'events' | 'ships'
} | null>(null)
let caseVersion = 0
async function loadCase() {
  const version = ++caseLoadVersion
  caseLoading.value = true
  caseError.value = ''
  try {
    const data = await fetchMaritimeCase(caseId.value)
    if (version === caseLoadVersion && caseOpen.value) caseData.value = data
  } catch (e) { if (version === caseLoadVersion) caseError.value = describeApiError(e, '案例加载失败') }
  finally { if (version === caseLoadVersion) caseLoading.value = false }
}
async function switchCase(id: MaritimeCaseId) {
  if (id === caseId.value || caseLoading.value || caseSwitching.value) return
  pauseCase()
  caseVersion++
  cancelMapAction()
  clearShip()
  agentTrack.value = null
  caseActive.value = false
  caseFullTrack.value = null
  caseWindow.value = null
  caseStageId.value = 'overview'
  caseData.value = null
  caseId.value = id
  await loadCase()
  if (!caseOpen.value) return
  const selected = caseData.value as ApiMaritimeCase | null
  if (!caseError.value && selected?.ready) await initializeCase()
  else {
    // A failed/empty selection must not leave the previous vessel's timeline visible.
    await load()
    if (savedCaseView.value?.time) seek(savedCaseView.value.time)
  }
}
async function openCase() {
  caseDetailsOpen.value = true
  if (caseOpen.value) return
  if (!savedCaseView.value) savedCaseView.value = {
    time: time.value, view: mapView.value?.captureView() ?? null, ship: selectedShipId.value,
    event: selectedEvent.value, panel: panel.value, panelOpen: panelOpen.value,
    workspace: workspaceMode.value, layers: { ...layers.value }, isolated: isolated.value,
    trackVisible: trackVisible.value, sidebarOpen: sidebarOpen.value, category: exploreCategory.value,
  }
  caseOpen.value = true
  workspaceMode.value = 'explore'
  panelOpen.value = false
  if (!caseData.value) await loadCase()
  if (caseOpen.value) await initializeCase()
}
async function initializeCase() {
  const data = caseData.value
  if (!caseOpen.value || !data?.ready || !data.ship_id || !data.start_at || !data.end_at) return
  const version = ++caseVersion
  caseSwitching.value = true
  caseError.value = ''
  clearShip()
  caseFullTrack.value = null
  selectedEvent.value = null
  panelOpen.value = false
  caseActive.value = true
  caseStageId.value = 'overview'
  caseWindow.value = { start_at: data.start_at, end_at: data.end_at }
  try {
    const windows = caseTrackChunks(data.start_at, data.end_at)
    const [, results] = await Promise.all([
      load({ ...caseWindow.value, ship_id: data.ship_id }),
      Promise.all(windows.map(([from, to]) => fetchShipTrackWindow(data.ship_id!, from, to, 120))),
    ])
    if (version !== caseVersion || !caseOpen.value) return
    if (error.value) throw new Error(error.value)
    caseFullTrack.value = mergeCaseTracks(results)
    seek(data.end_at)
    seekRequest.value++
    selectedShipId.value = data.ship_id
    trackVisible.value = true
    realPointsVisible.value = false
    speedColorOn.value = true
    isolated.value = false
    layers.value.ships = true
    layers.value.tracks = true
    layers.value.dwell = false
    layers.value.encounters = false
    await nextTick()
    const deadline = Date.now() + 20000
    while (version === caseVersion && !frameReady.value && !snapshotError.value && Date.now() < deadline)
      await new Promise(resolve => setTimeout(resolve, 100))
    if (version !== caseVersion || !caseOpen.value) return
    focusTrackRequest.value++
  } catch (e) {
    if (version === caseVersion) caseError.value = describeApiError(e, '完整案例加载失败')
  } finally { if (version === caseVersion) caseSwitching.value = false }
}
async function selectCaseStage(id: string, position: 'start' | 'end' = 'end') {
  caseStageId.value = id
  if (!caseActive.value || caseSwitching.value) return false
  const version = ++caseVersion
  cancelMapAction()
  agentTrack.value = null
  const stage = caseData.value?.stages.find(s => s.id === id)
  const end = stage?.end_at ?? caseWindow.value!.end_at
  // Use the last existing frame within the phase, rather than the next day's frame.
  const start = stage?.start_at ?? caseWindow.value!.start_at
  const target = position === 'start'
    ? times.value.find(at => Date.parse(at) >= Date.parse(start)) ?? start
    : times.value.filter(at => Date.parse(at) <= Date.parse(end)).at(-1) ?? end
  seek(target)
  seekRequest.value++
  selectedShipId.value = caseData.value!.ship_id
  trackVisible.value = true
  await nextTick()
  const deadline = Date.now() + 20000
  while (version === caseVersion && !frameReady.value && !snapshotError.value && Date.now() < deadline)
    await new Promise(resolve => setTimeout(resolve, 100))
  if (version !== caseVersion || !caseOpen.value) return false
  focusTrackRequest.value++
  return frameReady.value && !snapshotError.value
}
async function playCaseStage(id: string) {
  if (await selectCaseStage(id, 'start')) timelineControls.value?.start()
}
function seekCaseTime(at: string) {
  if (!caseActive.value) return
  caseVersion++
  cancelMapAction()
  agentTrack.value = null
  seekRequest.value++
  seek(at)
}
function pauseCase() {
  caseVersion++
  timelineControls.value?.stop()
}
async function exitCase() {
  const previous = savedCaseView.value
  caseLoadVersion++
  caseLoading.value = false
  pauseCase()
  cancelMapAction()
  const version = ++caseVersion
  const reload = caseWindow.value !== null || !!savedCaseView.value
  clearShip()
  caseActive.value = false
  caseOpen.value = false
  caseSwitching.value = false
  caseWindow.value = null
  caseFullTrack.value = null
  if (reload) { await load(); if (version !== caseVersion) return }
  if (previous) {
    if (previous.time && reload) seek(previous.time)
    selectedShipId.value = previous.ship
    selectedEvent.value = previous.event
    panel.value = previous.panel
    panelOpen.value = previous.panelOpen
    workspaceMode.value = previous.workspace
    layers.value = previous.layers
    isolated.value = previous.isolated
    trackVisible.value = previous.trackVisible
    sidebarOpen.value = previous.sidebarOpen
    exploreCategory.value = previous.category
    await nextTick()
    mapView.value?.restoreView(previous.view)
  }
  savedCaseView.value = null
}
async function changeWorkspace(mode: 'overview' | 'explore') {
  pendingKeyEvent.value = null
  if (savedCaseView.value) await exitCase()
  workspaceMode.value = mode
  if (mode === 'overview') panelOpen.value = false
}
// issue #40：智能体「查看通行分析」→ 打开总览通行分析面板并恢复该次调用条件/结果。
const analysisRestore = ref<AgentAnalysisAction | null>(null)
async function openPassageAnalysis(action: AgentAnalysisAction) {
  analysisRestore.value = action
  await changeWorkspace('overview')
}
async function retryCase() {
  await loadCase()
  if (caseOpen.value && !caseError.value) await initializeCase()
}
// issue #35：阶段切换的明确反馈序列（选中 → 等待快照/轨迹 → 调整视野 → 强调阶段轨迹）。
const caseStageStatus = computed(() => {
  if (caseSwitching.value) return '正在加载完整案例轨迹…'
  if (!caseActive.value || caseStageId.value === 'overview') return ''
  if (snapshotError.value) return '阶段快照加载失败，可点击地图状态中的重试。'
  if (snapshotLoading.value || !frameReady.value) return '阶段已选中：等待快照与轨迹…'
  return casePlaying.value ? '正在回放本阶段；亮线随观测时间推进。' : '已定位；点击曲线查看过程，或从阶段起点播放。'
})
async function retryPlayback() {
  if (caseActive.value) await initializeCase()
  else await load()
}
const events = ref<ApiEvent[]>([])
const eventsLoading = ref(true)
const eventsError = ref('')
const panel = ref<Panel>('overview')
const panelOpen = ref(false)
const workspaceMode = ref<'overview' | 'explore'>('explore')
const shipFilter = ref<ShipGroup | 'all'>('all')
const pendingKeyEvent = ref<ApiEvent | null>(null)
let pendingKeyEventFrame: string | null = null
const exploreCategory = ref<'events' | 'ships'>('events')
const sidebarOpen = ref(false)
// issue #32：紧凑回放轴与可调整/可收起侧栏。宽度仅保存在会话内，不写入存储。
const timelineCompact = ref(false)
const sidebarCollapsed = ref(false)
const sidebarWidth = ref<number | null>(null)
const inspectorWidth = ref(390)
const workbenchEl = ref<HTMLElement | null>(null)
const workbenchStyle = computed(() => ({
  ...(sidebarWidth.value ? { '--sidebar-w': `${sidebarWidth.value}px` } : {}),
}))
const SIDEBAR_MIN = 280
const SIDEBAR_MAX_RATIO = 0.6
function clampSidebarWidth(width: number) {
  return Math.round(Math.min(Math.max(width, SIDEBAR_MIN), window.innerWidth * SIDEBAR_MAX_RATIO))
}
function beginSidebarDrag(event: PointerEvent) {
  const handle = event.currentTarget as HTMLElement
  const sidebar = workbenchEl.value?.querySelector('.explorer-sidebar')
  const startX = event.clientX
  const startWidth = sidebar?.getBoundingClientRect().width ?? 420
  handle.classList.add('dragging')
  handle.setPointerCapture(event.pointerId)
  const onMove = (move: PointerEvent) => { sidebarWidth.value = clampSidebarWidth(startWidth + move.clientX - startX) }
  const onUp = () => {
    handle.classList.remove('dragging')
    handle.removeEventListener('pointermove', onMove)
    handle.removeEventListener('pointerup', onUp)
    handle.removeEventListener('pointercancel', onUp)
  }
  handle.addEventListener('pointermove', onMove)
  handle.addEventListener('pointerup', onUp)
  handle.addEventListener('pointercancel', onUp)
}
function nudgeSidebar(delta: number) {
  const sidebar = workbenchEl.value?.querySelector('.explorer-sidebar')
  const current = sidebarWidth.value ?? sidebar?.getBoundingClientRect().width ?? 420
  sidebarWidth.value = clampSidebarWidth(current + delta)
}
function beginInspectorDrag(event: PointerEvent) {
  const handle = event.currentTarget as HTMLElement
  const startX = event.clientX
  const startWidth = inspectorWidth.value
  handle.classList.add('dragging')
  handle.setPointerCapture(event.pointerId)
  const onMove = (move: PointerEvent) => {
    inspectorWidth.value = Math.round(Math.min(Math.max(startWidth + (startX - move.clientX), 300), window.innerWidth * 0.6))
  }
  const onUp = () => {
    handle.classList.remove('dragging')
    handle.removeEventListener('pointermove', onMove)
    handle.removeEventListener('pointerup', onUp)
    handle.removeEventListener('pointercancel', onUp)
  }
  handle.addEventListener('pointermove', onMove)
  handle.addEventListener('pointerup', onUp)
  handle.addEventListener('pointercancel', onUp)
}
function nudgeInspector(delta: number) {
  inspectorWidth.value = Math.round(Math.min(Math.max(inspectorWidth.value + delta, 300), window.innerWidth * 0.6))
}
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
let pendingMapController: AbortController | null = null
let pendingFrame: string | null = null
let agentSelectedShipId: number | null = null
const mapView = ref<InstanceType<typeof MapView> | null>(null)
function cancelMapAction() {
  pendingMapController?.abort()
  pendingMapController = null
  pendingFrame = null
  mapActionVersion++
  if (agentSelectedShipId !== null && selectedShipId.value === agentSelectedShipId) {
    agentTrack.value = null
    trackVisible.value = false
    realTrack.value = null
    selectedShipId.value = null
  }
  agentSelectedShipId = null
}
watch(requestedTime, at => { if (pendingFrame && at !== pendingFrame) cancelMapAction() })
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
  () => [isRealAis.value, selectedShipId.value, trackVisible.value, time.value, realTrackHours.value, caseActive.value, caseWindow.value] as const,
  (state, _old, onCleanup) => {
    const [real, shipId, visible, at, hours] = state
    realTrack.value = null
    realTrackError.value = ''
    realTrackLoading.value = false
    if (caseActive.value) return
    if (!real || shipId === null || !visible || !at || !times.value.length) return
    const end = Date.parse(at)
    const start = Math.max(Date.parse(times.value[0]!), end - hours * 3600_000)
    if (end <= start) return
    const controller = new AbortController()
    const timer = setTimeout(async () => {
      realTrackLoading.value = true
      try {
        const windows = caseTrackChunks(new Date(start).toISOString(), at)
        const results = await Promise.all(windows.map(([from,to]) => fetchShipTrackWindow(shipId, from, to,
          hours === 1 ? 30 : hours === 6 ? 120 : 300, controller.signal)))
        if (controller.signal.aborted) return
        realTrack.value = mergeCaseTracks(results)

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
    supplementary.push(loadEncounters())
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
// MobilityDB 派生层：相遇图层数据随初始化加载；停留图层按需加载一次。
const dwellData = ref<ApiDwellResponse | null>(null)
const encounterList = ref<ApiEncounter[]>([])
const selectedEncounter = ref<ApiEncounter | null>(null)

async function loadEncounters() {
  try {
    const data = await fetchEncounters()
    if (data.status === 'not_built') {
      encounterList.value = []
    } else {
      encounterList.value = data.encounters
    }
  } catch {
    encounterList.value = []
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
function chooseShip(ship: ApiMapShip, keepChat = false) {
  pendingKeyEvent.value = null
  cancelMapAction()
  agentTrack.value = null
  mapActionVersion++
  if (selectedShipId.value !== ship.id) {
    trackVisible.value = false
    if (isRealAis.value) {
      realPointsVisible.value = false
      speedColorOn.value = true
    }
  }
  selectedShipId.value = ship.id
  selectedEvent.value = null
  if (!keepChat) panel.value = 'ships'
  workspaceMode.value = 'explore'
  exploreCategory.value = 'ships'
  panelOpen.value = true
  sidebarOpen.value = false
  layers.value.ships = true
  focusShipRequest.value++
}
function clearShip() {
  cancelMapAction()
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
  pendingKeyEvent.value = null
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
function chooseKeyEvent(event: ApiEvent) {
  if (eventOccurredBy(event, time.value)) { chooseEvent(event); return }
  const target = times.value[0] && eventSeekTime(event, times.value[0], displayZone.value)
  if (!target) return
  pendingKeyEvent.value = event
  selectedEvent.value = null
  workspaceMode.value = 'explore'
  seekRequest.value++
  seek(target)
  pendingKeyEventFrame = requestedTime.value
}
watch(requestedTime, at => {
  if (pendingKeyEvent.value && at !== pendingKeyEventFrame) pendingKeyEvent.value = null
})
watch([time, frameReady, snapshotError, displayZone], () => {
  const event = pendingKeyEvent.value
  if (!event) return
  if (snapshotError.value) { pendingKeyEvent.value = null; notice.value = '事件日期快照加载失败，请重试后打开详情。'; return }
  if (frameReady.value && eventOccurredBy(event, time.value)) chooseEvent(event)
})
function openShipGroup(group: ShipGroup) {
  openExplorer('ships')
  shipFilter.value = group
  sidebarOpen.value = true
}
// 智能体回答中的「地图定位」只定位当前回放时刻已出现的事件和船位。
function locateAgentShip(shipId: number) {
  const ship = currentShips.value.find((item) => item.id === shipId)
  if (!ship) {
    notice.value = `当前回放时刻没有 ID ${shipId} 的船位；地图显示的是当前时刻快照，可调整时间后再定位。`
    return
  }
  chooseShip(ship, true)
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
// 地图动作结果：message 面向用户；outcome 驱动面板中的 正在定位/已定位/失败/已取消 状态反馈（issue #36）。
type MapActionResult = { message: string; outcome: 'ok' | 'error' | 'cancelled' }
async function executeMapAction(action: AgentMapAction, signal: AbortSignal): Promise<MapActionResult> {
  const fail = (message: string): MapActionResult => ({ message, outcome: 'error' })
  const cancelled = (message = '地图操作已取消。'): MapActionResult => ({ message, outcome: 'cancelled' })
  cancelMapAction()
  if (signal.aborted) return cancelled()
  if (caseActive.value && (action.type === 'event' || action.ship_id !== caseData.value?.ship_id))
    return fail('该操作目标不属于当前单船案例。请退出案例后在地图探索中执行。')
  if (action.type === 'event') {
    if (action.source !== 'news' || !action.event_id) return fail('事件标识或来源无效。')
    const event = events.value.find(item => item.event_id === action.event_id)
    if (!event) return fail(`未找到事件 ${action.event_id}。`)
    if (!hasEventLocation(event)) return fail(`事件 ${action.event_id} 没有可定位的代表坐标。`)
    if (!event.occurred_at || !eventOccurredBy(event, time.value)) return fail('事件发生日期尚未进入当前回放范围；请调整时间轴。')
    const previousPanel = panel.value
    chooseEvent(event)
    panel.value = previousPanel
    return selectedEvent.value?.event_id === action.event_id
      ? { message: '事件已在地图选中。', outcome: 'ok' }
      : fail('事件未能选中。')
  }
  if (action.source !== 'nnu_ais' || !Number.isSafeInteger(action.ship_id) || action.ship_id <= 0) return fail('船舶标识或来源无效。')
  const start = Date.parse(action.start_at), end = Date.parse(action.end_at)
  if (caseActive.value && caseAgentWindow.value && (start < Date.parse(caseAgentWindow.value.start_at) || end > Date.parse(caseAgentWindow.value.end_at)))
    return fail('轨迹窗口超出当前阶段。请返回案例概况或选择对应阶段。')
  const first = Date.parse(times.value[0] ?? ''), last = Date.parse(times.value.at(-1) ?? '')
  if (![start, end, first, last].every(Number.isFinite) || start >= end || end - start > 86400000)
    return fail('轨迹时间窗无效或超出本批 AIS 覆盖；单次最多 24 小时。')
  // 通行分析证据等「围绕某时刻」的场景允许裁剪到本批覆盖内，而非直接失败。
  const windowStart = action.clamp_to_coverage ? Math.max(start, first) : start
  const windowEnd = action.clamp_to_coverage ? Math.min(end, last) : end
  if (windowStart >= windowEnd || (!action.clamp_to_coverage && (start < first || end > last)))
    return fail('轨迹时间窗无效或超出本批 AIS 覆盖；单次最多 24 小时。')
  const version = ++mapActionVersion
  pendingMapController?.abort()
  const controller = new AbortController()
  pendingMapController = controller
  signal.addEventListener('abort', () => controller.abort(), { once: true })
  const isCancelled = () => signal.aborted || controller.signal.aborted || version !== mapActionVersion
  let loaded: ApiTrackWindow
  try {
    loaded = await fetchShipTrackWindow(action.ship_id, new Date(windowStart).toISOString(), new Date(windowEnd).toISOString(), 300, controller.signal)
  } catch (e) { return fail(describeApiError(e, '轨迹加载失败')) }
  if (isCancelled()) return cancelled('地图目标已变更，本次操作已取消。')
  const points = loaded.segments.flatMap(segment => segment.points)
  if (points.length < (action.type === 'ship_position' ? 1 : 2)) return fail(points.length
    ? '指定时间窗只有一个采样报位，无法绘制轨迹。'
    : '指定时间窗没有该船报位，无法显示轨迹。')
  const latest = points.at(-1)!
  const targetIndex = times.value.findIndex(at => Date.parse(at) >= Date.parse(latest.recorded_at))
  pendingFrame = times.value[targetIndex] ?? times.value.at(-1) ?? null
  seek(latest.recorded_at)
  await nextTick()
  const deadline = Date.now() + 20000
  while (!isCancelled() && !snapshotError.value && !frameReady.value && Date.now() < deadline)
    await new Promise(resolve => setTimeout(resolve, 100))
  const ready = frameReady.value && !snapshotError.value && requestedTime.value !== null && Date.parse(requestedTime.value) >= Date.parse(latest.recorded_at)
  if (isCancelled()) return cancelled('地图目标已变更，本次操作已取消。')
  if (!ready) return fail(snapshotError.value || '回放快照未能加载，轨迹未选中。')
  const ship = currentShips.value.find(item => item.id === action.ship_id)
  if (!ship) return fail('轨迹有报位，但所选回放帧没有该船的有效快照。')
  pendingMapController = null
  pendingFrame = null
  chooseShip(ship, true)
  agentSelectedShipId = ship.id
  trackVisible.value = action.type === 'ship_track'
  agentTrack.value = trackVisible.value ? loaded : null
  if (trackVisible.value) { layers.value.tracks = true; focusTrackRequest.value++ }
  const committedVersion = mapActionVersion
  await nextTick()
  const focused = await mapView.value?.confirmFocus(action.ship_id, trackVisible.value)
  if (signal.aborted || committedVersion !== mapActionVersion) return cancelled('地图目标已变更，本次操作已取消。')
  // 目标已加载并选中时不再按失败处理：视野聚焦受面板/缩放限制时只补充说明，
  // 否则会出现「轨迹其实已渲染，提示却说聚焦失败」的矛盾（独立验收 F4）。
  const focusNote = focused
    ? ''
    : '（目标已加载并选中；地图视野可能受面板或缩放限制，可用「全局视野」或手动缩放查看）'
  return {
    outcome: 'ok',
    message: (action.type === 'ship_position'
      ? `已在地图定位并高亮 ${ship.name}（ID ${ship.id}）；AIS 报位时刻 ${ship.recorded_at}，地图回放时刻 ${time.value}。`
      : `已在地图显示 ${ship.name}（ID ${ship.id}）的轨迹（${new Date(windowStart).toISOString()} 至 ${new Date(windowEnd).toISOString()}）。`) + focusNote,
  }
}
function restore() {
  clearShip()
  selectedEvent.value = null
  globalViewRequest.value++
}
function togglePanel(value: Panel) {
  closeAreaPanel()
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
// issue #36：智能体输入区的简短上下文摘要（案例/船舶/事件），详细说明悬停可见。
const agentContextSummary = computed(() => {
  if (caseActive.value && caseData.value?.ship_id) {
    return { label: `当前案例：${caseData.value.title} · 船舶 ID ${caseData.value.ship_id}`, detail: '提问默认限定在当前案例阶段窗口内。' }
  }
  if (selectedShip.value) {
    return { label: `当前船舶：${selectedShip.value.name}（ID ${selectedShip.value.id}）`, detail: '提问可引用该船；地图定位类操作以当前回放时刻为准。' }
  }
  if (selectedEvent.value) {
    return { label: `当前事件：${selectedEvent.value.title}`, detail: '新闻与船位来源独立；提问不会把事件与邻近船舶自动关联。' }
  }
  return null
})
// ---------------------------------------------------------------------------
// issue #41：区域船舶活动与进出分析（手动面板 + 智能体共用同一后端服务）
// 分析区域独立于地图视野：缩放/平移不改变它；手动圈选与智能体「查看区域分析」
// 都走同一套 resolve-area 校验，保证两侧区域口径一致。
// ---------------------------------------------------------------------------
const areaOpen = ref(false)
const areaDrawing = ref(false)
const areaResolving = ref(false)
const areaNotice = ref('')
const areaBounds = ref<ApiAreaBounds>({ west: 55.8, south: 25.8, east: 57.1, north: 27.1 })
const areaDefaultBounds = ref<ApiAreaBounds>({ west: 55.8, south: 25.8, east: 57.1, north: 27.1 })
const areaLabel = ref('霍尔木兹海峡核心通行区（项目分析区域）')
const areaIsDefault = ref(true)
const areaVersionLabel = ref<string | null>('1.0.0')
const areaResultVersion = ref(0)
const areaBoundsVersion = ref(0)
const areaPendingAction = ref<Record<string, unknown> | null>(null)
// 智能体本轮回答建议的区域分析入口：暂存动作，用户点击后再打开面板。
const areaSuggestedAction = ref<AgentAreaAnalysisAction | null>(null)
const areaSuggestedLabel = computed(() => {
  const mode = areaSuggestedAction.value?.mode
  return mode === 'snapshot' ? '时刻在场' : mode === 'compare' ? '两时段比较' : '时段活动'
})
const areaAgentContext = ref<{ shipTypes?: string[] | null; at?: string | null; start?: string | null; end?: string | null } | null>(null)
// 面板条件预填：默认把「时刻在场」的时刻对齐到当前地图回放时刻（历史数据窗口内），
// 避免默认用「现在」查历史 AIS 得到必然的空结果；用户可以再改成任意历史时刻。
const areaPanelContext = computed(() => {
  const context = areaAgentContext.value ?? {}
  return { ...context, at: context.at ?? time.value ?? null }
})
const agentDraft = ref<{ text: string; version: number } | null>(null)
let agentDraftVersion = 0
let areaDefaultLoaded = false

function areaSummaryText(bounds: ApiAreaBounds = areaBounds.value): string {
  const lat = (bounds.north - bounds.south).toFixed(3)
  const lon = (bounds.east - bounds.west).toFixed(3)
  return `${bounds.south.toFixed(3)}–${bounds.north.toFixed(3)}°N · ${bounds.west.toFixed(3)}–${bounds.east.toFixed(3)}°E（跨度 ${lat}°×${lon}°）`
}

async function loadAreaDefault() {
  if (areaDefaultLoaded) return null
  try {
    const data = await fetchAreaDefault()
    areaDefaultBounds.value = { ...data.area.bounds }
    if (areaIsDefault.value && areaBoundsVersion.value === 0) areaBounds.value = { ...data.area.bounds }
    areaVersionLabel.value = data.area.version
    if (areaIsDefault.value) areaLabel.value = data.area.name
    areaDefaultLoaded = true
    return data
  } catch (e) {
    areaNotice.value = describeApiError(e, '默认分析区域加载失败')
    return null
  }
}

function openAreaPanel() {
  areaOpen.value = true
  workspaceMode.value = 'explore'
  void loadAreaDefault()
}

function onAreaAnalysisSuggested(action: AgentAreaAnalysisAction) {
  // 只暂存入口；用户点击「查看区域分析」后再打开面板并恢复该次条件。
  areaSuggestedAction.value = action
  areaNotice.value = ''
}

function dismissAreaSuggestion() {
  areaSuggestedAction.value = null
}

async function openSuggestedArea() {
  const action = areaSuggestedAction.value
  if (action) await openAreaAnalysis(action)
}

function closeAreaPanel() {
  areaOpen.value = false
  areaDrawing.value = false
}

function startAreaDraw() {
  areaOpen.value = true
  areaDrawing.value = true
  areaNotice.value = ''
  void loadAreaDefault()
}

function cancelAreaDraw() {
  areaDrawing.value = false
}

async function applyAreaBounds(bounds: ApiAreaBounds, options: { label?: string | null; areaId?: string | null } = {}) {
  areaResolving.value = true
  areaNotice.value = ''
  const previous = { ...areaBounds.value }
  try {
    const result = await resolveAreaBounds(bounds, options.areaId ?? 'custom')
    areaBounds.value = { ...result.area.bounds }
    areaIsDefault.value = result.area.is_default
    areaLabel.value = options.label?.trim() || result.area.name
    areaVersionLabel.value = result.area.version
    areaBoundsVersion.value += 1
    areaNotice.value = result.message
    return true
  } catch (e) {
    areaBounds.value = previous
    areaNotice.value = describeApiError(e, '区域校验失败：矩形无效或超出跨度上限，已保留原区域')
    return false
  } finally {
    areaResolving.value = false
  }
}

async function onAreaDrawn(bounds: ApiAreaBounds) {
  areaDrawing.value = false
  await applyAreaBounds(bounds, { areaId: 'custom' })
}

async function restoreDefaultArea() {
  // 直接使用 default-area 的权威值：不把「默认矩形」重新当成自定义矩形提交，
  // 否则 resolve-area 会按自定义矩形返回 area_id=custom（同一坐标但语义不同）。
  const data = (await loadAreaDefault()) ?? (await fetchAreaDefault().catch(() => null))
  if (!data) {
    areaNotice.value = '默认分析区域加载失败，未改变当前区域'
    return
  }
  areaBounds.value = { ...data.area.bounds }
  areaDefaultBounds.value = { ...data.area.bounds }
  areaIsDefault.value = true
  areaLabel.value = data.area.name
  areaVersionLabel.value = data.area.version
  areaBoundsVersion.value += 1
  areaNotice.value = `已恢复默认分析区域：${data.area.name}（v${data.area.version}）`
  areaDrawing.value = false
}

function requestAreaDrawFromPanel() {
  areaDrawing.value = true
  areaNotice.value = ''
}

// 智能体「查看区域分析」：打开面板并恢复该次调用的区域、模式与条件。
async function openAreaAnalysis(action: AgentAreaAnalysisAction) {
  const query = action.query
  areaSuggestedAction.value = null
  const bounds: ApiAreaBounds = {
    west: Number(query.west), south: Number(query.south),
    east: Number(query.east), north: Number(query.north),
  }
  areaPendingAction.value = {
    mode: action.mode,
    shipTypes: query.ship_types ?? null,
    at: query.at ?? null,
    start: query.start_at ?? null,
    end: query.end_at ?? null,
    startA: query.start_a ?? null,
    endA: query.end_a ?? null,
    startB: query.start_b ?? null,
    endB: query.end_b ?? null,
    summary: action.summary,
    tool: action.tool,
  }
  areaAgentContext.value = {
    shipTypes: query.ship_types ?? null,
    at: query.at ?? null,
    start: query.start_at ?? null,
    end: query.end_at ?? null,
  }
  await loadAreaDefault()
  if (query.area_is_default && areaDefaultBounds.value) {
    areaBounds.value = { ...areaDefaultBounds.value }
    areaIsDefault.value = true
    areaLabel.value = '霍尔木兹海峡核心通行区（项目分析区域）'
    areaVersionLabel.value = '1.0.0'
    areaBoundsVersion.value += 1
  } else {
    await applyAreaBounds(bounds, { areaId: query.area_id ?? 'custom' })
  }
  areaOpen.value = true
  workspaceMode.value = 'explore'
}

// 证据联动：加载该访问时段的有界轨迹（复用现有轨迹接口与地图图层）。
// 地图轨迹单次最多 24 小时（executeMapAction 的既有约束），长于 24 小时的访问按
// 「末次区内报位向前 24 小时」裁剪并明确说明，而不是整条拒绝。
const VISIT_TRACK_LIMIT_MS = 24 * 60 * 60 * 1000
async function showVisitTrack(payload: { shipId: number; startAt: string; endAt: string; visitKey?: string }) {
  const rawStart = Date.parse(payload.startAt)
  const end = Date.parse(payload.endAt)
  if (!Number.isFinite(rawStart) || !Number.isFinite(end) || end <= rawStart) {
    notice.value = '该访问的观测区间无效（首末区内报位时间缺失或倒置），无法显示轨迹'
    return
  }
  const clamped = end - rawStart > VISIT_TRACK_LIMIT_MS
  const start = clamped ? end - VISIT_TRACK_LIMIT_MS : rawStart
  await executeMapAction(
    {
      type: 'ship_track', trigger: 'suggested', ship_id: payload.shipId,
      start_at: new Date(start).toISOString(), end_at: new Date(end).toISOString(),
      source: 'nnu_ais',
      window_source: clamped ? '区域访问证据区间（已裁剪为末 24 小时）' : '区域访问证据区间',
    },
    new AbortController().signal,
  ).then(result => {
    notice.value = clamped
      ? `${result.message} 该访问跨度超过 24 小时，地图轨迹已裁剪为末次区内报位前的 24 小时（访问完整区间见明细）。`
      : result.message
  })
}

function useAreaInDialog(payload: { text: string }) {
  closeAreaPanel()
  agentDraftVersion += 1
  agentDraft.value = { text: payload.text, version: agentDraftVersion }
  panel.value = 'agent'
  panelOpen.value = true
  workspaceMode.value = 'explore'
}

// 默认区域不传 area_context（后端按版本化默认区处理，area_id=hormuz_core_v1）；
// 只有自选矩形才把四边界与 custom 标记交给后端，避免默认区身份被覆盖成 custom。
const areaAgentAreaContext = computed(() => (areaIsDefault.value
  ? null
  : {
      west: areaBounds.value.west,
      south: areaBounds.value.south,
      east: areaBounds.value.east,
      north: areaBounds.value.north,
      area_id: 'custom',
      label: areaLabel.value,
    }))

watch(areaBoundsVersion, () => {
  // 区域变更后，已展示的结果立即标记为「区域已变更，待查询」；
  // 重新查询成功时由面板回报 results-updated，把版本推进到当前边界。
  areaDrawing.value = false
})
// issue #33：选中新闻后，详情标题与列表项、地图标记同步强调。
const headFlash = ref(false)
let headFlashTimer: ReturnType<typeof setTimeout> | undefined
watch(selectedEvent, (event) => {
  if (!event) return
  headFlash.value = false
  void nextTick(() => {
    headFlash.value = true
    clearTimeout(headFlashTimer)
    headFlashTimer = setTimeout(() => { headFlash.value = false }, 1300)
  })
})
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
  pendingKeyEvent.value = null
  if (category === 'ships') shipFilter.value = 'all'
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
const speedColorOn = ref(true)
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
  <main ref="workbenchEl" class="workbench" :class="{ 'show-overview': workspaceMode === 'overview', 'detail-open': panelOpen, 'case-mode': caseOpen, 'sidebar-collapsed': sidebarCollapsed, 'timeline-compact': timelineCompact, 'area-open': areaOpen }" :style="workbenchStyle">
    <header class="topbar">
      <div class="brand">
        <img class="brand-logo" :src="logoUrl" alt="" aria-hidden="true" />
        <div>
          <h1>霍尔木兹<span>海事态势分析</span></h1>
        </div>
      </div>
      <nav class="workspace-nav" aria-label="工作视图">
        <button :class="{ active: workspaceMode === 'overview' && !caseOpen }" :aria-current="workspaceMode === 'overview' && !caseOpen ? 'page' : undefined" @click="changeWorkspace('overview')">态势总览</button>
        <button :class="{ active: workspaceMode === 'explore' && !caseOpen }" :aria-current="workspaceMode === 'explore' && !caseOpen ? 'page' : undefined" @click="changeWorkspace('explore')">地图探索</button>
        <button :class="{ active: caseOpen }" :aria-current="caseOpen ? 'page' : undefined" @click="openCase">典型案例</button>
      </nav>
      <div class="top-status">
        <span class="simulation-label">{{ isRealAis ? '历史 AIS 船位 · 新闻独立' : '船舶轨迹 · 新闻事件' }}</span>
        <button @click="displayZone = displayZone === 'UTC' ? 'Asia/Shanghai' : 'UTC'" aria-label="切换时区">{{ zoneLabel() }}</button>
        <button @click="theme = theme === 'dark' ? 'light' : 'dark'" aria-label="切换地图主题">{{ theme === 'dark' ? '浅色' : '深色' }}</button>
      </div>
      <button v-if="!caseOpen && sidebarCollapsed" class="sidebar-reopen" @click="sidebarCollapsed = false">新闻与船舶列表 ›</button>
      <button class="sidebar-toggle" :aria-expanded="sidebarOpen" @click="sidebarOpen = !sidebarOpen; workspaceMode = 'explore'">{{ sidebarOpen ? '收起列表' : '查找' }}</button>
    </header>
    <ExplorerSidebar
      v-show="!caseOpen"
      v-model="exploreCategory"
      v-model:ship-filter="shipFilter"
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
      @resize-drag="beginSidebarDrag"
      @resize-key="nudgeSidebar"
      @collapse="sidebarCollapsed = true"
    />
    <section class="map-workspace" aria-label="霍尔木兹海峡态势地图">
      <ToolRail
        :layers-active="layersOpen"
        :agent-active="panel === 'agent' && panelOpen"
        :area-active="areaOpen"
        @open-layers="layersOpen = !layersOpen"
        @open-agent="togglePanel('agent')"
        @open-area="areaOpen ? closeAreaPanel() : openAreaPanel()"
      />
      <CasePanel v-if="caseOpen && caseDetailsOpen" :data="caseData" :case-id="caseId" @switch-case="switchCase" :active-stage="caseStageId" :loading="caseLoading || caseSwitching" :error="caseError || realTrackError" :active="caseActive" :points-visible="realPointsVisible" :stage-status="caseStageStatus" :track="caseFullTrack" :at="time" :playing="casePlaying" @select="selectCaseStage" @play="playCaseStage" @pause="pauseCase" @seek="seekCaseTime" @toggle-points="realPointsVisible = !realPointsVisible" @close="caseDetailsOpen = false" @retry="retryCase" @exit="exitCase" />
      <button v-if="caseOpen && !caseDetailsOpen" class="case-reopen" @click="caseDetailsOpen = true">展开案例阶段与报道</button>
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
        ref="mapView"
        :ships="caseOpen && (!caseActive || caseSwitching) ? [] : currentShips"
        :events="caseOpen ? [] : mapEvents"
        :selected-ship-id="selectedShipId"
        :selected-event="!caseOpen && selectedEvent && eventOccurredBy(selectedEvent, time) ? selectedEvent : null"
        :track="selectedTrack"
        :track-visible="trackVisible"
        :speed-segments="speedColorOn ? speedSegments : null"
        :window-segments="agentTrack ? agentTrack.segments : (caseActive ? caseHighlight : isRealAis ? (realTrack?.segments ?? []) : null)"
        :background-segments="caseActive ? caseFullTrack?.segments ?? null : null"
        :focus-segments="caseActive && !agentTrack && caseAgentWindow ? clipCaseTracks(caseFullTrack, caseAgentWindow.start_at, caseAgentWindow.end_at) : undefined"
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
        :area-bounds="areaBounds"
        :area-label="areaLabel"
        :area-meta="areaIsDefault ? `area_id hormuz_core_v1 · v${areaVersionLabel ?? '—'}` : '自定义矩形（未做权威性核验）'"
        :area-is-default="areaIsDefault"
        :area-drawing="areaDrawing"
        @clear-selection="selectedEvent = null; clearShip(); panelOpen = false"
        @select-ship="chooseShip"
        @select-event="chooseEvent"
        @select-encounter="chooseEncounter"
        @bounds-change="bounds = $event"
        @harbour-status="harbourStatus = $event"
        @country-status="countryStatus = $event"
        @area-drawn="onAreaDrawn"
        @area-draw-cancel="cancelAreaDraw"
      />
      <div v-if="areaOpen" class="area-panel-placement">
        <AreaActivityPanel
          :open="areaOpen"
          :bounds="areaBounds"
          :default-bounds="areaDefaultBounds"
          :area-label="areaLabel"
          :area-is-default="areaIsDefault"
          :agent-context="areaPanelContext"
          :pending-action="areaPendingAction"
          @close="closeAreaPanel"
          @update:bounds="requestAreaDrawFromPanel"
          @locate-ship="showVisitTrack"
          @focus-visit="showVisitTrack"
          @use-area-in-dialog="useAreaInDialog"
          @results-updated="areaResultVersion = areaBoundsVersion"
        />
      </div>
      <div class="map-top-tools">
        <button
          class="map-tool"
          @click="restore"
          title="回到霍尔木兹海峡全局视野"
        >
          ⌖ 全局视野
        </button>
      </div>
      <div v-if="isRealAis && (!caseOpen || caseActive) && !caseSwitching && !loading" class="ais-snapshot-strip" role="status">
        <strong v-if="caseActive">案例窗口：仅{{ caseData?.display_title ?? caseData?.title }}，非海峡全量船舶</strong>
        <strong>历史 AIS · {{ formatTime(time, true) }} {{ zoneLabel() }}</strong>
        <span>快照 {{ currentShips.length }} 艘，视野内 {{ viewShips.length }} 艘</span>
        <span>仅采用此前 1 小时内的最新报位</span>
        <span v-if="caseActive && !currentShips.length">该时刻缺少有效报位，不表示船舶不存在</span>
        <span v-if="snapshotLoading && requestedTime !== time">正在获取 {{ formatTime(requestedTime, true) }} 的快照</span>
      </div>
      <div
        v-if="areaOpen || !areaIsDefault"
        class="area-status-bar"
        role="status"
        aria-live="polite"
        data-testid="area-status"
        :data-area-id="areaIsDefault ? 'hormuz_core_v1' : 'custom'"
        :data-bounds="`${areaBounds.west},${areaBounds.south},${areaBounds.east},${areaBounds.north}`"
        :data-stale="areaResultVersion < areaBoundsVersion ? 'true' : 'false'"
        :data-drawing="areaDrawing ? 'true' : 'false'"
      >
        <strong>分析区域</strong>
        <span>{{ areaLabel }}</span>
        <span class="area-coord">{{ areaSummaryText() }}</span>
        <span v-if="areaIsDefault" class="area-tag ok">默认项目分析区域（非官方航道）</span>
        <span v-else class="area-tag">自选矩形（非官方航道）</span>
        <span v-if="areaResolving" class="area-tag warn">正在校验新区域…</span>
        <span v-else-if="areaResultVersion > areaBoundsVersion" class="area-tag warn">区域已变更，待查询</span>
        <button type="button" class="area-btn" :disabled="areaResolving" @click="startAreaDraw">重新圈选</button>
        <button type="button" class="area-btn" :disabled="areaResolving" @click="restoreDefaultArea">恢复默认区域</button>
        <button v-if="areaDrawing" type="button" class="area-btn" @click="cancelAreaDraw">取消绘制</button>
        <span v-if="areaNotice" class="area-note">{{ areaNotice }}</span>
      </div>
      <div v-if="areaSuggestedAction" class="area-suggest-bar" role="status">
        <span>本轮回答可用区域分析复现：{{ areaSuggestedLabel }}（{{ areaSuggestedAction.tool }}）</span>
        <button type="button" class="area-btn" data-testid="open-area-analysis" @click="openSuggestedArea">查看区域分析</button>
        <button type="button" class="area-btn" @click="dismissAreaSuggestion">忽略</button>
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
        }}<button v-if="error || snapshotError" @click="error ? retryPlayback() : retrySnapshot()">重试</button>
      </div>
    </section>
    <section class="overview-stage" aria-label="态势总览">
      <header class="overview-stage-head"><div><p class="eyebrow">霍尔木兹海峡 · 历史船位与新闻</p><h2>从海峡动态，进入地图调查</h2><details class="overview-scope"><summary>数据范围与口径说明</summary><p>{{ isRealAis ? `当前接入历史 AIS：${formatTime(times[0], true)} 至 ${formatTime(times.at(-1), true)} ${zoneLabel()}；地图为所选时刻前 1 小时内的最新报位。` : '计划接入船位时段：2026-02-25 至 2026-03-03（UTC）；实际回放范围以入库数据为准。' }} 新闻事件来自独立报道，两类资料分别浏览，不据时空邻近推断真实关联。</p></details></div><button class="primary" @click="workspaceMode = 'explore'">进入地图探索</button></header>
      <OverviewPanel
        :time="time" :view-ships="currentShips" :view-events="mapEvents" :events="filteredEvents" :all-events="events" :range-start="times[0]" :range-end="times.at(-1)"
        :total-ships="currentShips.length" :total-events="events.length" :average-speed="snapshotAverageSpeed"
        :events-loading="eventsLoading"
        :execute-map-action="executeMapAction"
        :analysis-restore="analysisRestore"
        @select-event="chooseEvent" @select-key-event="chooseKeyEvent" @open-ship-group="openShipGroup"
        @open-events="openExplorer('events')" @open-ships="openExplorer('ships')"
      />
    </section>
    <div class="timeline-dock" :class="{ compact: timelineCompact }">
      <TimelineControls
        ref="timelineControls" :playback-end="caseActive ? caseAgentWindow?.end_at : undefined" @playing-change="casePlaying = $event"
        v-model="index" :frame-times="times" :snapshot-mode="isRealAis" :frame-ready="frameReady" :frame-error="snapshotError"
        :seek-request="seekRequest"
        :loading="loading" :error-message="error" :compact="timelineCompact"
        @speed-change="playbackSpeed = $event" @retry="retryPlayback" @toggle-compact="timelineCompact = !timelineCompact"
      />
    </div>
    <aside v-show="panelOpen && !areaOpen" class="inspector" aria-label="上下文工作面板" :style="{ width: `min(${inspectorWidth}px, calc(100vw - 48px))` }">
      <button
        class="inspector-resize-handle"
        role="separator"
        aria-orientation="vertical"
        :aria-valuenow="inspectorWidth"
        aria-label="调整面板宽度，左右方向键微调"
        @pointerdown="beginInspectorDrag"
        @keydown.left.prevent="nudgeInspector(-24)"
        @keydown.right.prevent="nudgeInspector(24)"
      ></button>
      <header class="inspector-head">
        <h2 :class="{ flash: headFlash }">
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
        :case-context="caseActive && caseAgentWindow && caseData?.ship_id ? { ship_id: caseData.ship_id, title: caseData.title, start_at: caseAgentWindow.start_at, end_at: caseAgentWindow.end_at } : null"
        :context-summary="agentContextSummary"
        v-show="panel === 'agent'"
        :execute-map-action="executeMapAction"
        :cancel-map-action="cancelMapAction"
        :playback-at="requestedTime"
        :area-context="areaAgentAreaContext"
        :pending-draft="agentDraft"
        @locate-ship="locateAgentShip"
        @locate-event="locateAgentEvent"
        @open-analysis="openPassageAnalysis"
        @area-analysis-suggested="onAreaAnalysisSuggested"
      />
    </aside>
  </main>
</template>
