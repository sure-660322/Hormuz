<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'
import type { ApiEvent } from '../api'

const props = defineProps<{
  events: ApiEvent[]
  totalEventCount: number
  eventTypes: string[]
  selectedEventType: string
  sortDirection: 'asc' | 'desc'
  loading: boolean
  errorMessage: string
  selectedEvent: ApiEvent | null
  currentTime: string | null
}>()

const emit = defineEmits<{
  selectEvent: [maritimeEvent: ApiEvent]
  changeEventType: [eventType: string]
  changeSortDirection: [direction: 'asc' | 'desc']
  restoreGlobalView: []
}>()

const eventList = ref<HTMLElement | null>(null)

watch(
  () => props.selectedEvent?.id ?? null,
  async (eventId) => {
    if (eventId === null) return

    await nextTick()

    const eventCard = eventList.value?.querySelector<HTMLElement>(
      `[data-event-id="${eventId}"]`,
    )

    eventCard?.scrollIntoView({
      behavior: 'smooth',
      block: 'nearest',
    })
  },
)

function formatEventTime(value: string) {
  return new Date(value).toLocaleString('zh-CN')
}

function hasEventOccurred(maritimeEvent: ApiEvent) {
  if (!props.currentTime) return true

  return (
    Date.parse(maritimeEvent.occurred_at) <=
    Date.parse(props.currentTime)
  )
}

function handleEventTypeChange(event: Event) {
  const select = event.target as HTMLSelectElement
  emit('changeEventType', select.value)
}

function handleSortDirectionChange(event: Event) {
  const select = event.target as HTMLSelectElement

  emit(
    'changeSortDirection',
    select.value as 'asc' | 'desc',
  )
}
</script>

<template>
  <aside class="event-panel">
    <header>
      <p class="data-label">教学模拟数据</p>
      <h1>事件目录</h1>
      <p class="description">
        显示 {{ events.length }} / 共
        {{ totalEventCount }} 条模拟事件
      </p>
    </header>

    <div v-if="loading" class="status-message">
      正在加载事件……
    </div>

    <div v-else-if="errorMessage" class="status-message error-message">
      {{ errorMessage }}
    </div>

    <div v-else-if="totalEventCount === 0" class="status-message">
      暂无事件
    </div>

    <template v-else>
      <div class="filter-controls">
        <label>
          事件类型

          <select
            :value="selectedEventType"
            @change="handleEventTypeChange"
          >
            <option value="all">全部类型</option>

            <option
              v-for="eventType in eventTypes"
              :key="eventType"
              :value="eventType"
            >
              {{ eventType }}
            </option>
          </select>
        </label>

        <label>
          时间顺序

          <select
            :value="sortDirection"
            @change="handleSortDirectionChange"
          >
            <option value="asc">从早到晚</option>
            <option value="desc">从晚到早</option>
          </select>
        </label>
      </div>

      <section
        v-if="selectedEvent"
        class="selected-event-detail"
      >
        <div class="detail-header">
          <span>当前选中事件</span>

          <button
            type="button"
            @click="emit('restoreGlobalView')"
          >
            恢复全局视野
          </button>
        </div>

        <h2>{{ selectedEvent.title }}</h2>
        <p>{{ selectedEvent.description }}</p>

        <dl>
          <div>
            <dt>类型</dt>
            <dd>{{ selectedEvent.event_type }}</dd>
          </div>

          <div>
            <dt>发生时间</dt>
            <dd>{{ formatEventTime(selectedEvent.occurred_at) }}</dd>
          </div>

          <div>
            <dt>位置</dt>
            <dd>
              {{ selectedEvent.latitude.toFixed(4) }},
              {{ selectedEvent.longitude.toFixed(4) }}
            </dd>
          </div>

          <div>
            <dt>来源</dt>
            <dd>{{ selectedEvent.source_name ?? '教学模拟数据' }}</dd>
          </div>
        </dl>
      </section>

      <div v-if="events.length === 0" class="status-message">
        没有符合筛选条件的事件
      </div>

      <ul
        v-else
        ref="eventList"
        class="event-list"
      >
        <li
          v-for="maritimeEvent in events"
          :key="maritimeEvent.id"
        >
          <button
            type="button"
            class="event-card"
            :data-event-id="maritimeEvent.id"
            :class="{
              selected: maritimeEvent.id === selectedEvent?.id,
              future: !hasEventOccurred(maritimeEvent),
            }"
            @click="emit('selectEvent', maritimeEvent)"
          >
            <span class="event-type">
              {{ maritimeEvent.event_type }}
            </span>

            <span
              class="event-state"
              :class="{ occurred: hasEventOccurred(maritimeEvent) }"
            >
              {{ hasEventOccurred(maritimeEvent) ? '已发生' : '尚未发生' }}
            </span>

            <strong>{{ maritimeEvent.title }}</strong>

            <time>
              {{ formatEventTime(maritimeEvent.occurred_at) }}
            </time>
          </button>
        </li>
      </ul>
    </template>
  </aside>
</template>

<style scoped>
.event-panel {
  box-sizing: border-box;
  height: 100vh;
  padding: 24px;
  overflow-y: auto;
  border-left: 1px solid #cbd5e1;
  background-color: #ffffff;
  color: #0f172a;
  text-align: left;
}

.data-label {
  margin: 0 0 8px;
  color: #dc2626;
  font-size: 13px;
  font-weight: 700;
}

h1 {
  margin: 0;
  color: #0f172a;
  font-size: 24px;
}

.description {
  margin: 8px 0 0;
  color: #64748b;
  font-size: 14px;
}

.filter-controls {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: 10px;
  margin-top: 20px;
}

.filter-controls label {
  display: flex;
  flex-direction: column;
  gap: 6px;
  color: #475569;
  font-size: 12px;
  font-weight: 600;
}

.filter-controls select {
  width: 100%;
  padding: 7px 8px;
  border: 1px solid #cbd5e1;
  border-radius: 6px;
  background-color: #ffffff;
  color: #0f172a;
  font: inherit;
}

.selected-event-detail {
  margin-top: 16px;
  padding: 14px;
  border: 1px solid #fca5a5;
  border-radius: 8px;
  background-color: #fff7ed;
}

.detail-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  color: #b91c1c;
  font-size: 12px;
  font-weight: 700;
}

.detail-header button {
  padding: 5px 8px;
  border: 1px solid #fca5a5;
  border-radius: 5px;
  background-color: #ffffff;
  color: #b91c1c;
  font: inherit;
  cursor: pointer;
}

.selected-event-detail h2 {
  margin: 12px 0 8px;
  color: #0f172a;
  font-size: 16px;
  line-height: 1.4;
}

.selected-event-detail > p {
  color: #475569;
  font-size: 13px;
  line-height: 1.5;
}

.selected-event-detail dl {
  display: grid;
  gap: 6px;
  margin: 12px 0 0;
  font-size: 12px;
}

.selected-event-detail dl div {
  display: grid;
  grid-template-columns: 64px minmax(0, 1fr);
  gap: 8px;
}

.selected-event-detail dt {
  color: #64748b;
}

.selected-event-detail dd {
  margin: 0;
  color: #0f172a;
  overflow-wrap: anywhere;
}

.status-message {
  margin-top: 24px;
  padding: 24px 12px;
  border: 1px dashed #cbd5e1;
  border-radius: 8px;
  color: #64748b;
  text-align: center;
}

.error-message {
  border-color: #fecaca;
  color: #b91c1c;
  background-color: #fef2f2;
}

.event-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin: 24px 0 0;
  padding: 0;
  list-style: none;
}

.event-card {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 14px;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  background-color: #f8fafc;
  color: #0f172a;
  font: inherit;
  text-align: left;
  cursor: pointer;
}

.event-card:hover {
  border-color: #94a3b8;
  background-color: #f1f5f9;
}

.event-card.selected {
  border-color: #dc2626;
  background-color: #fef2f2;
}

.event-card.future {
  opacity: 0.52;
}

.event-card.future:hover,
.event-card.future.selected {
  opacity: 0.78;
}

.event-type {
  color: #dc2626;
  font-size: 12px;
  font-weight: 700;
}

.event-state {
  align-self: flex-start;
  padding: 2px 7px;
  border-radius: 999px;
  background-color: #e2e8f0;
  color: #64748b;
  font-size: 11px;
  font-weight: 700;
}

.event-state.occurred {
  background-color: #dcfce7;
  color: #166534;
}

.event-card time {
  color: #64748b;
  font-size: 12px;
}
</style>
