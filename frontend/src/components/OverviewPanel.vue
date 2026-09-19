<script setup lang="ts">
import { computed } from 'vue'
import type { ApiEvent, ApiMapShip } from '../api'
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
}>()
const emit = defineEmits<{
  selectShip: [ship: ApiMapShip]
  selectEvent: [event: ApiEvent]
  openEvents: []
  openShips: []
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
        ><strong>{{ viewShips.length }}</strong> 视野船舶</span
      ><span
        ><strong>{{ viewEvents.length }}</strong> 视野事件</span
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
          <span class="event-dot" :style="{ color: eventKind(event.event_type).color }">{{ eventKind(event.event_type).symbol }}</span>
          <span class="overview-row-title">{{ event.title }}</span>
          <small>{{ event.coverage_count }} 篇</small>
        </button>
        <p v-if="!hotEvents.length" class="empty compact">暂无新闻事件。</p>
        <button class="overview-more" @click="emit('openEvents')">
          查看全部 {{ totalEvents }} 条 ›
        </button>
      </template>
    </section>
    <section class="overview-section" aria-label="视野船舶">
      <div class="section-title">
        <h3>视野船舶</h3>
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
  </section>
</template>
