<script setup lang="ts">
import { computed } from 'vue'
import type { ApiEvent, ApiMapShip, ApiEncounter, ApiDataHealth } from '../api'
import { eventKind, formatTime, shipType } from '../domain/maritime'
const props = defineProps<{
  time: string | null
  viewShips: ApiMapShip[]
  viewEvents: ApiEvent[]
  events: ApiEvent[]
  totalShips: number
  totalEvents: number
  averageSpeed: string
  eventsLoading: boolean
  encounters: ApiEncounter[]
  health: ApiDataHealth | null
  encountersLoading: boolean
  encounterError: string
}>()
const emit = defineEmits<{
  selectShip: [ship: ApiMapShip]
  selectEvent: [event: ApiEvent]
  openEvents: []
  openShips: []
  selectEncounter: [encounter: ApiEncounter]
  reanalyzeEncounters: []
}>()
// 热点事件：报道数 coverage_count 降序，并列时按首次报道日期新的在前。
const hotEvents = computed(() =>
  [...props.events]
    .sort(
      (a, b) =>
        b.coverage_count - a.coverage_count ||
        (b.publish_date_min ?? '').localeCompare(a.publish_date_min ?? ''),
    )
    .slice(0, 5),
)
const topShips = computed(() =>
  [...props.viewShips].sort((a, b) => b.speed - a.speed).slice(0, 5),
)
// 相遇列表：按最近距离升序取前 12 对；接近是模拟时空邻近，不代表实际交互。
const nearestEncounters = computed(() =>
  [...props.encounters].sort((a, b) => a.min_distance_m - b.min_distance_m).slice(0, 12),
)
const derivedTables = computed(() => props.health?.derived ?? [])
</script>
<template>
  <section class="panel-content overview-panel">
    <header class="panel-heading">
      <p>
        {{ totalShips }} 艘模拟船 · {{ totalEvents }} 条新闻事件 · 快照
        {{ formatTime(time, true) }}
      </p>
      <p>历史快照 · 非实时 AIS；新闻与模拟船舶相互独立，不因时空接近建立关联。</p>
    </header>
    <div class="overview-chips">
      <span
        ><strong>{{ viewShips.length }}</strong> 快照船舶</span
      ><span
        ><strong>{{ viewEvents.length }}</strong> 可定位新闻</span
      ><span
        >平均航速 <strong>{{ averageSpeed }}</strong> kn</span
      >
    </div>
    <section class="overview-section" aria-label="热点事件">
      <div class="section-title">
        <h3>热点事件</h3>
        <span>按报道数排序</span>
      </div>
      <p v-if="eventsLoading" class="empty compact" role="status">正在加载事件…</p>
      <template v-else>
        <button
          v-for="event in hotEvents"
          :key="event.event_id"
          class="overview-row"
          @click="emit('selectEvent', event)"
        >
          <time>{{ event.publish_date_min?.slice(5) || '—' }}</time>
          <span class="event-dot" :style="{ color: eventKind(event.event_type).color }"><img :src="eventKind(event.event_type).icon" alt=""></span>
          <span class="overview-row-title">{{ event.title }}</span>
          <small>{{ event.coverage_count }} 篇</small>
        </button>
        <p v-if="!hotEvents.length" class="empty compact">暂无新闻事件。</p>
        <button class="overview-more" @click="emit('openEvents')">
          查看全部 {{ totalEvents }} 条 ›
        </button>
      </template>
    </section>
    <section class="overview-section" aria-label="当前快照船舶">
      <div class="section-title">
        <h3>当前快照船舶</h3>
        <span>按航速降序</span>
      </div>
      <button
        v-for="ship in topShips"
        :key="ship.id"
        class="overview-row"
        @click="emit('selectShip', ship)"
      >
        <span class="overview-row-title"
          >{{ ship.name }}<small>{{ shipType(ship.ship_type) }}</small></span
        >
        <small>{{ ship.speed.toFixed(1) }} kn</small>
      </button>
      <p v-if="!topShips.length" class="empty compact">当前视野暂无船舶。</p>
      <button class="overview-more" @click="emit('openShips')">全部船舶 ›</button>
    </section>
    <section class="overview-section" aria-label="相遇分析">
      <div class="section-title">
        <h3>相遇分析</h3>
        <span>按最近距离排序</span>
      </div>
      <p v-if="encountersLoading" class="empty compact" role="status">正在加载相遇分析…</p>
      <template v-else>
        <p v-if="encounterError" class="empty compact">{{ encounterError }}</p>
        <button
          v-for="enc in nearestEncounters"
          :key="`${enc.ship_a.id}-${enc.ship_b.id}`"
          class="overview-row"
          @click="emit('selectEncounter', enc)"
        >
          <span class="overview-row-title"
            >{{ enc.ship_a.name }}<small>× {{ enc.ship_b.name }}</small></span
          >
          <small>{{ enc.min_distance_nm.toFixed(2) }} NM · 重叠 {{ (enc.overlap_minutes / 60).toFixed(1) }} h</small>
        </button>
        <p v-if="!nearestEncounters.length && !encounterError" class="empty compact">当前阈值下暂无相遇记录。</p>
        <button class="overview-more" @click="emit('reanalyzeEncounters')">
          按默认参数重新分析（3 NM / 30 分钟）›
        </button>
        <p class="empty compact">接近为模拟时空邻近，不代表实际交互。</p>
      </template>
    </section>
    <section class="overview-section" aria-label="数据健康">
      <div class="section-title">
        <h3>数据健康</h3>
        <span>源覆盖与派生层新鲜度</span>
      </div>
      <template v-if="health">
        <button
          v-for="d in derivedTables"
          :key="d.table"
          class="overview-row"
          :title="d.built_at ? `构建于 ${formatTime(d.built_at, true)}` : '未构建'"
        >
          <span class="overview-row-title">{{ d.table }}</span>
          <small>{{ d.rows ?? '—' }} 行 · {{ d.stale ? '待重建' : '最新' }}</small>
        </button>
        <p class="empty compact">
          源报位 {{ health.source.totals.positions.toLocaleString() }} 条 / {{ health.source.totals.ships }} 艘；
          派生层随源数据变化标记为待重建，需显式重新构建。
        </p>
      </template>
      <p v-else class="empty compact">数据健康状态不可用。</p>
    </section>
  </section>
</template>
