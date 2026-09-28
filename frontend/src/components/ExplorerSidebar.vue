<script setup lang="ts">
import { computed, nextTick, reactive, ref, watch } from 'vue'
import { eventCoverUrl, type ApiEvent, type ApiMapShip } from '../api'
import { displayZone, eventKind, eventKinds, eventTimeText, shipType } from '../domain/maritime'
import ShipSearch from './ShipSearch.vue'

const props = defineProps<{
  events: ApiEvent[]
  ships: ApiMapShip[]
  totalEvents: number
  eventsLoading: boolean
  eventsError: string
  eventsAvailable: boolean
  shipsLoading: boolean
  currentTime: string | null
  untimedEvents: ApiEvent[]
  eventType: string
  eventSort: 'asc' | 'desc'
  selectedEventId: string | null
  selectedShipId: number | null
}>()
const emit = defineEmits<{
  selectEvent: [event: ApiEvent]
  selectShip: [ship: ApiMapShip]
  typeChange: [type: string]
  sortChange: [sort: 'asc' | 'desc']
  retry: []
}>()
const category = defineModel<'events' | 'ships'>({ default: 'events' })
const eventView = ref<'timeline' | 'list'>('timeline')
const failedCovers = reactive(new Set<string>())
const sortedShips = computed(() => [...props.ships].sort((a, b) => (a.name ?? a.mmsi).localeCompare(b.name ?? b.mmsi, 'zh-CN')))
const shipListLimit = ref(100)
const visibleShips = computed(() => sortedShips.value.slice(0, shipListLimit.value))
watch(() => props.ships, () => { shipListLimit.value = 100 })
function selectEvent(event: ApiEvent) { category.value = 'events'; emit('selectEvent', event) }
function selectShip(ship: ApiMapShip) { category.value = 'ships'; emit('selectShip', ship) }
const dayGroups = computed(() => {
  const groups = new Map<string, ApiEvent[]>()
  for (const event of [...props.events].sort((a, b) =>
    a.occurred_at!.slice(0, 10).localeCompare(b.occurred_at!.slice(0, 10)) || a.event_id.localeCompare(b.event_id))) {
    const day = event.occurred_at!.slice(0, 10)
    if (!groups.has(day)) groups.set(day, [])
    groups.get(day)!.push(event)
  }
  return [...groups].map(([day, events]) => ({ day, events }))
})
const currentDay = computed(() => {
  const at = Date.parse(props.currentTime ?? '')
  if (!Number.isFinite(at)) return ''
  return new Date(at + (displayZone.value === 'Asia/Shanghai' ? 8 * 60 * 60 * 1000 : 0)).toISOString().slice(0, 10)
})
const timelineList = ref<HTMLElement | null>(null)
function dayLabel(day: string) {
  const [year, month, date] = day.split('-')
  return `${year}年${Number(month)}月${Number(date)}日`
}
function scrollToCurrentDay() {
  const target = [...(timelineList.value?.querySelectorAll<HTMLElement>('[data-day]') ?? [])]
    .find(node => node.dataset.day === currentDay.value)
    ?? [...(timelineList.value?.querySelectorAll<HTMLElement>('[data-day]') ?? [])].at(-1)
  target?.scrollIntoView({ block: 'start', behavior: 'smooth' })
}
let initialTimelinePositioned = false
watch([dayGroups, currentDay], () => {
  if (initialTimelinePositioned || !dayGroups.value.length || !currentDay.value) return
  initialTimelinePositioned = true
  void nextTick(scrollToCurrentDay)
})
watch(eventView, view => { if (view === 'timeline') void nextTick(scrollToCurrentDay) })
</script>

<template>
  <aside class="explorer-sidebar" aria-label="事件与船舶探索">
    <div class="explorer-intro">
      <h2>海峡动态</h2>
      <p>查找历史新闻与船舶，点选后在地图中查看。</p>
      <ShipSearch :ships="ships" :events="[...events, ...untimedEvents]" :loading="shipsLoading" @select="selectShip" @select-event="selectEvent" />
    </div>
    <div class="explorer-tabs" role="group" aria-label="探索类别">
      <button :class="{ active: category === 'events' }" :aria-pressed="category === 'events'" @click="category = 'events'">新闻事件</button>
      <button :class="{ active: category === 'ships' }" :aria-pressed="category === 'ships'" @click="category = 'ships'">船舶</button>
    </div>
    <template v-if="category === 'events'">
      <div class="event-view-switch" role="group" aria-label="新闻事件展示方式">
        <button :class="{ active: eventView === 'timeline' }" :aria-pressed="eventView === 'timeline'" @click="eventView = 'timeline'">时间线</button>
        <button :class="{ active: eventView === 'list' }" :aria-pressed="eventView === 'list'" @click="eventView = 'list'">列表</button>
      </div>
      <div class="explorer-filters" :class="{ single: eventView === 'timeline' }">
        <select aria-label="新闻事件类型" :value="eventType" @change="emit('typeChange', ($event.target as HTMLSelectElement).value)">
          <option value="all">全部类型</option>
          <option v-for="(kind, key) in eventKinds" :key="key" :value="key">{{ kind.label }}</option>
        </select>
        <select v-if="eventView === 'list'" aria-label="新闻排序" :value="eventSort" @change="emit('sortChange', ($event.target as HTMLSelectElement).value as 'asc' | 'desc')">
          <option value="desc">较晚日期在前</option><option value="asc">较早日期在前</option>
        </select>
      </div>
      <p class="explorer-count">截至当前回放时刻 {{ events.length }} / {{ totalEvents }} 条新闻事件</p>
      <p class="explorer-count">{{ eventView === 'timeline' ? '按发生日期展示，不代表具体时刻。' : '日期未明确的事件可在下方单独阅读。' }}</p>
      <div v-if="eventsLoading" class="explorer-message" role="status">正在加载新闻事件…</div>
      <div v-else-if="eventsError" class="explorer-message" role="alert">{{ eventsError }} <button v-if="eventsAvailable" @click="emit('retry')">重试</button></div>
      <div v-else-if="eventView === 'list'" class="explorer-list">
        <button v-for="event in events" :key="event.event_id" class="explorer-item event-item" :class="{ selected: selectedEventId === event.event_id }" @click="selectEvent(event)">
          <span class="explorer-item-cover" title="关联报道配图">
            <img v-if="!failedCovers.has(event.event_id)" :src="eventCoverUrl(event.event_id)" alt="" loading="lazy" decoding="async" @error="failedCovers.add(event.event_id)" />
            <img v-else class="cover-fallback" :src="eventKind(event.event_type).icon" alt="" />
          </span>
          <span class="explorer-item-copy">
            <span class="explorer-item-title">{{ event.title }}</span>
            <span class="explorer-item-meta"><time :title="eventTimeText(event)">发生日期 {{ event.occurred_at?.slice(0, 10) }}</time><span :style="{ color: eventKind(event.event_type).color }">{{ eventKind(event.event_type).label }}</span><span>{{ event.coverage_count }} 篇</span></span>
          </span>
        </button>
        <p v-if="!currentTime" class="explorer-message">回放时间不可用，暂无法按发生时间显示新闻事件。</p>
        <p v-else-if="!events.length" class="explorer-message">截至当前回放时刻暂无此类新闻事件，可拖动时间轴或切换类型。</p>
        <details v-if="untimedEvents.length" class="untimed-events"><summary>时间未明确 · {{ untimedEvents.length }} 条</summary>
          <button v-for="event in untimedEvents" :key="event.event_id" class="untimed-event" :class="{ selected: selectedEventId === event.event_id }" @click="selectEvent(event)"><strong>{{ event.title }}</strong><small>{{ eventTimeText(event) }}</small></button>
        </details>
      </div>
      <div v-else ref="timelineList" class="explorer-list dayline-scroll">
        <div class="dayline">
          <section v-for="group in dayGroups" :key="group.day" class="dayline-day" :class="{ current: group.day === currentDay }" :data-day="group.day">
            <h3><time :datetime="group.day">{{ dayLabel(group.day) }}</time><small>{{ group.events.length }} 条</small></h3>
            <div class="dayline-cards">
              <button v-for="(event, i) in group.events" :key="event.event_id" class="dayline-card" :class="{ right: i % 2 === 1, selected: selectedEventId === event.event_id }" :title="eventTimeText(event)" @click="selectEvent(event)">
                <span class="dayline-card-kind" :style="{ color: eventKind(event.event_type).color }">{{ eventKind(event.event_type).label }}</span>
                <strong>{{ event.title }}</strong><small>{{ event.coverage_count }} 篇报道</small>
              </button>
            </div>
          </section>
        </div>
        <p v-if="!currentTime" class="explorer-message">回放时间不可用，暂无法按日期显示新闻事件。</p>
        <p v-else-if="!dayGroups.length" class="explorer-message">截至当前日期暂无此类新闻事件，可拖动上方时间轴或切换类型。</p>
        <details v-if="untimedEvents.length" class="untimed-events"><summary>时间未明确 · {{ untimedEvents.length }} 条</summary>
          <button v-for="event in untimedEvents" :key="event.event_id" class="untimed-event" :class="{ selected: selectedEventId === event.event_id }" @click="selectEvent(event)"><strong>{{ event.title }}</strong><small>{{ eventTimeText(event) }}</small></button>
        </details>
      </div>
      <button v-if="!eventsLoading && !eventsError && eventView === 'timeline' && dayGroups.length" class="dayline-jump" @click="scrollToCurrentDay">回到当前日期</button>
    </template>
    <template v-else>
      <p class="explorer-count">当前船位快照 · {{ ships.length }} 艘船舶</p>
      <div class="explorer-list">
        <button v-for="ship in visibleShips" :key="ship.id" class="explorer-item" :class="{ selected: selectedShipId === ship.id }" @click="selectShip(ship)">
          <span class="explorer-item-title">{{ ship.name ?? ship.mmsi }}</span>
          <span class="explorer-item-meta"><span>{{ shipType(ship.ship_type) }}</span><span>{{ ship.speed.toFixed(1) }} kn</span></span>
        </button>
        <button v-if="shipListLimit < ships.length" class="overview-more" @click="shipListLimit += 100">再显示 100 艘（已显示 {{ visibleShips.length }} / {{ ships.length }}）</button>
        <p v-if="!ships.length" class="explorer-message">当前时刻暂无船位，可调整底部回放时间。</p>
      </div>
    </template>
  </aside>
</template>
