<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { eventCoverUrl, type ApiEvent, type ApiMapShip } from '../api'
import { eventKind, eventKinds, eventTimeText, shipType } from '../domain/maritime'
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
  untimedEvents: number
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
const failedCovers = reactive(new Set<string>())
const sortedShips = computed(() => [...props.ships].sort((a, b) => (a.name ?? a.mmsi).localeCompare(b.name ?? b.mmsi, 'zh-CN')))
const shipListLimit = ref(100)
const visibleShips = computed(() => sortedShips.value.slice(0, shipListLimit.value))
watch(() => props.ships, () => { shipListLimit.value = 100 })
function selectEvent(event: ApiEvent) { category.value = 'events'; emit('selectEvent', event) }
function selectShip(ship: ApiMapShip) { category.value = 'ships'; emit('selectShip', ship) }
</script>

<template>
  <aside class="explorer-sidebar" aria-label="事件与船舶探索">
    <div class="explorer-intro">
      <h2>海峡动态</h2>
      <p>查找历史新闻与船舶，点选后在地图中查看。</p>
      <ShipSearch :ships="ships" :events="events" :loading="shipsLoading" @select="selectShip" @select-event="selectEvent" />
    </div>
    <div class="explorer-tabs" role="group" aria-label="探索类别">
      <button :class="{ active: category === 'events' }" :aria-pressed="category === 'events'" @click="category = 'events'">新闻事件</button>
      <button :class="{ active: category === 'ships' }" :aria-pressed="category === 'ships'" @click="category = 'ships'">船舶</button>
    </div>
    <template v-if="category === 'events'">
      <div class="explorer-filters">
        <select aria-label="新闻事件类型" :value="eventType" @change="emit('typeChange', ($event.target as HTMLSelectElement).value)">
          <option value="all">全部类型</option>
          <option v-for="(kind, key) in eventKinds" :key="key" :value="key">{{ kind.label }}</option>
        </select>
        <select aria-label="新闻排序" :value="eventSort" @change="emit('sortChange', ($event.target as HTMLSelectElement).value as 'asc' | 'desc')">
          <option value="desc">较晚发生在前</option><option value="asc">较早发生在前</option>
        </select>
      </div>
      <p class="explorer-count">截至当前回放时刻 {{ events.length }} / {{ totalEvents }} 条新闻事件</p>
      <p v-if="untimedEvents" class="explorer-count">{{ untimedEvents }} 条缺少发生时间，未纳入时间回放。</p>
      <div v-if="eventsLoading" class="explorer-message" role="status">正在加载新闻事件…</div>
      <div v-else-if="eventsError" class="explorer-message" role="alert">{{ eventsError }} <button v-if="eventsAvailable" @click="emit('retry')">重试</button></div>
      <div v-else class="explorer-list">
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
      </div>
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
