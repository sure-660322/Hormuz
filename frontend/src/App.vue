<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount, ref, watch } from 'vue'
import { fetchEvents, describeApiError, type ApiEvent, type ApiMapShip } from './api'
import { usePlayback } from './composables/usePlayback'
import {
  inBounds,
  formatTime,
  displayZone, zoneLabel, hasEventLocation, eventTimeText, eventCoordinates,
  type GeoPoint,
  type LayerState,
  type Panel,
  type ViewBounds,
} from './domain/maritime'
import { localWorkbench } from './services/workbench'
import MapView from './components/MapView.vue'
import EventPanel from './components/EventPanel.vue'
import AgentPanel from './components/AgentPanel.vue'
import ShipInspector from './components/ShipInspector.vue'
import TimelineControls from './components/TimelineControls.vue'
import ShipSearch from './components/ShipSearch.vue'
import WorkspaceTools from './components/WorkspaceTools.vue'

const {
  ships,
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
const panel = ref<Panel>('events')
const panelTabs = [
  ['events', '事件'],
  ['ships', '船舶'],
  ['layers', '图层'],
  ['analysis', '分析'],
  ['agent', '智能体'],
] as const
const panelOpen = ref(!window.matchMedia('(max-width: 760px)').matches)
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
const tailMinutes = ref(360)
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
const mapEvents = computed(() => filteredEvents.value.filter(hasEventLocation))
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
  await Promise.all([load(), loadEvents()])
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
function chooseEvent(event: ApiEvent) {
  clearShip()
  if (eventType.value !== 'all' && eventType.value !== event.event_type)
    eventType.value = 'all'
  selectedEvent.value = event
  panel.value = 'events'
  panelOpen.value = true
  layers.value.events = true
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
function chooseCenter(point: GeoPoint) {
  center.value = point
  picking.value = false
  panel.value = 'analysis'
  panelOpen.value = true
}
function startPicking() {
  picking.value = !picking.value
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
        <svg viewBox="0 0 32 32" aria-hidden="true">
          <path d="M4 25 16 4l12 21-12-6Z" />
          <path d="M16 4v15M4 29h24" />
        </svg>
        <div>
          <h1>霍尔木兹<span>海事态势分析</span></h1>
          <p>航运态势与历史调查工作台</p>
        </div>
      </div>
      <div class="top-status">
        <span class="simulation-label">模拟船舶 · 新闻事件</span
        ><span class="data-status">{{
          loading
            ? '数据加载中'
            : error
              ? '数据不可用'
              : `${ships.length} 艘船舶已载入`
        }}</span
        ><button class="alert-count" @click="togglePanel('events')">{{ events.length }} 条新闻事件</button>
        <button @click="displayZone = displayZone === 'UTC' ? 'Asia/Shanghai' : 'UTC'" aria-label="切换时区">{{ zoneLabel() }}</button>
        <a href="http://127.0.0.1:8000/mobility-demo" target="_blank" rel="noopener" style="color:inherit;font-size:12px">停留分析试验</a>
        <button @click="theme = theme === 'dark' ? 'light' : 'dark'" aria-label="切换地图主题">{{ theme === 'dark' ? '浅色' : '深色' }}</button>
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
    <section class="map-workspace" aria-label="霍尔木兹海峡态势地图">
      <MapView
        :ships="currentShips"
        :events="mapEvents"
        :selected-ship-id="selectedShipId"
        :selected-event="selectedEvent"
        :track="selectedTrack"
        :track-visible="trackVisible"
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
        :tail-minutes="tailMinutes"
        :share-request="shareRequest"
        :shared-view="sharedView"
        @share-view="shareView"
        @clear-selection="selectedEvent = null; clearShip()"
        @select-ship="chooseShip"
        @select-event="chooseEvent"
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
      <div class="map-side-tools">
        <button class="map-tool" @click="shareRequest++">分享视图</button>
        <button class="map-tool" @click="printReport">导出 / 打印 PDF</button>
        <button
          class="map-tool"
          :class="{ active: panel === 'layers' && panelOpen }"
          @click="togglePanel('layers')"
        >
          ▱ 图层</button
        ><button
          class="map-tool"
          :class="{ active: picking }"
          @click="openAreaAnalysis"
        >
          ⊕ 半径分析
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
        <span>当前视野</span><strong>{{ viewShips.length }}</strong> 船舶 <i></i
        ><strong>{{ viewEvents.length }}</strong> 新闻事件 <i></i
        ><span class="hud-speed"
          >平均航速 <strong>{{ averageSpeed }}</strong> kn</span
        >
      </div>
      <div class="map-legend">
        <span><b class="vessel-key">▲</b> 当前船位</span
        ><span><b class="track-key">─•─</b> 已航行轨迹</span
        ><span>船位为教学模拟；事件为代表点，非精确事发位置</span>
      </div>
      <div v-if="loading || error" class="map-data-status" role="status">
        {{ error || '正在载入船舶与历史采样…'
        }}<button v-if="error" @click="load">重试</button>
      </div>
    </section>
    <aside v-show="panelOpen" class="inspector" aria-label="上下文工作面板">
      <nav class="panel-tabs" aria-label="工作面板分类">
        <button
          v-for="item in panelTabs"
          :key="item[0]"
          :class="{ active: panel === item[0] }"
          :aria-pressed="panel === item[0]"
          @click="togglePanel(item[0])"
        >
          {{ item[1]
          }}<span v-if="item[0] === 'events'">{{ events.length }}</span>
        </button>
      </nav>
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
        :isolated="isolated"
        :nearby-events="nearbyEvents"
        :events-error="eventsError"
        :events-loading="eventsLoading"
        @select="chooseShip"
        @clear="clearShip"
        @track="toggleTrack"
        @isolate="isolated = !isolated"
        @event="chooseEvent"
        @locate="focusShipRequest++"
      />
      <AgentPanel v-if="panel === 'agent'" />
      <WorkspaceTools
        v-if="panel === 'layers' || panel === 'analysis'"
        :panel="panel"
        v-model:layers="layers"
        v-model:radius="radius"
        :center="center"
        :result="areaResult"
        :view-ships="viewShips"
        :view-event-count="viewEvents.length"
        :time="time"
        :picking="picking"
        :harbour-status="harbourStatus"
        :country-status="countryStatus"
        :loading="loading"
        :error="error"
        @pick="startPicking"
        @clear="clearArea"
        @select-ship="chooseShip"
        @select-event="chooseEvent"
      />
      <div v-if="panel === 'layers'" class="display-settings">
        <label>速度矢量 <select v-model.number="vectorMinutes"><option :value="3">3 分钟</option><option :value="6">6 分钟</option><option :value="12">12 分钟</option></select></label>
        <label><input type="checkbox" v-model="vectorLinked" /> 随回放倍率调整（当前 {{ effectiveVector }} 分钟）</label>
        <label>尾迹 {{ tailMinutes }} 分钟 <input aria-label="尾迹长度" type="range" v-model.number="tailMinutes" min="15" max="1440" step="15" /></label>
        <p class="caption">实线为有效船首向；虚线为 COG/SOG 等速外推。无 ROT 与船体尺寸数据，不绘制转向旗和真尺度轮廓。</p>
      </div>
      <div v-if="panel === 'analysis' && center" class="display-settings"><label><input type="checkbox" v-model="fenceEnabled" /> 将查询圆设为模拟电子围栏</label><p class="caption">{{ fenceEnabled ? `围栏内 ${fenceInside.length} 艘；随回放提示进入/离开。` : '仅本次会话有效；不判断两个采样之间的穿越。' }}</p></div>
      <footer class="inspector-footer">
        {{ formatTime(time, true) }} <span>历史快照 · 非实时 AIS</span>
      </footer>
    </aside>
    <TimelineControls
      v-model="index"
      :frame-times="times"
      :events="[]"
      :selected-event-id="null"
      :seek-request="seekRequest"
      :loading="loading"
      :error-message="error"
      event-type="all"
      @speed-change="playbackSpeed = $event"
      @retry="load"
      @select-event="chooseEvent"
    />
    <section class="print-report">
      <h2>霍尔木兹海峡 · 船位与新闻概览</h2><p>{{ formatTime(time, true) }} {{ zoneLabel() }} · 船位为教学模拟，新闻事件为独立历史资料</p>
      <p>当前视野 {{ viewShips.length }} 艘船舶、{{ viewEvents.length }} 条新闻事件。选中船：{{ selectedShip?.name ?? '无' }}；选中事件：{{ selectedEvent?.title ?? '无' }}。</p>
      <table><thead><tr><th>事件时间文字</th><th>事件</th><th>经纬度</th></tr></thead><tbody><tr v-for="e in viewEvents" :key="e.id"><td>{{ eventTimeText(e) }}</td><td>{{ e.title }}</td><td>{{ eventCoordinates(e) }}</td></tr></tbody></table>
    </section>
  </main>
</template>
