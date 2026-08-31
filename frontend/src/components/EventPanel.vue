<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'
import type { ApiEvent } from '../api'

const props = defineProps<{
  events: ApiEvent[]
  loading: boolean
  errorMessage: string
  selectedEventId: number | null
}>()

const emit = defineEmits<{
  selectEvent: [maritimeEvent: ApiEvent]
}>()

const eventList = ref<HTMLElement | null>(null)

watch(
  () => props.selectedEventId,
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
</script>

<template>
  <aside class="event-panel">
    <header>
      <p class="data-label">教学模拟数据</p>
      <h1>事件目录</h1>
      <p class="description">
        共 {{ events.length }} 条模拟事件
      </p>
    </header>

    <div v-if="loading" class="status-message">
      正在加载事件……
    </div>

    <div v-else-if="errorMessage" class="status-message error-message">
      {{ errorMessage }}
    </div>

    <div v-else-if="events.length === 0" class="status-message">
      暂无事件
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
            selected: maritimeEvent.id === selectedEventId,
          }"
          @click="emit('selectEvent', maritimeEvent)"
        >
          <span class="event-type">
            {{ maritimeEvent.event_type }}
          </span>

          <strong>{{ maritimeEvent.title }}</strong>

          <time>
            {{ formatEventTime(maritimeEvent.occurred_at) }}
          </time>
        </button>
      </li>
    </ul>
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

.event-type {
  color: #dc2626;
  font-size: 12px;
  font-weight: 700;
}

.event-card time {
  color: #64748b;
  font-size: 12px;
}
</style>
