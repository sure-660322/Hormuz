<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { fetchEvents } from './api'
import type { ApiEvent } from './api'
import EventPanel from './components/EventPanel.vue'
import MapView from './components/MapView.vue'
import TimelineControls from './components/TimelineControls.vue'

const events = ref<ApiEvent[]>([])
const selectedEvent = ref<ApiEvent | null>(null)
const eventsLoading = ref(true)
const eventsError = ref('')
type EventSortDirection = 'asc' | 'desc'

const selectedEventType = ref('all')
const eventSortDirection = ref<EventSortDirection>('asc')

const eventTypes = computed(() => {
  return [
    ...new Set(
      events.value.map((maritimeEvent) => maritimeEvent.event_type),
    ),
  ].sort()
})

const visibleEvents = computed(() => {
  const filteredEvents =
    selectedEventType.value === 'all'
      ? events.value
      : events.value.filter(
          (maritimeEvent) =>
            maritimeEvent.event_type === selectedEventType.value,
        )

  return [...filteredEvents].sort((firstEvent, secondEvent) => {
    const comparison =
      Date.parse(firstEvent.occurred_at) -
        Date.parse(secondEvent.occurred_at) ||
      firstEvent.id - secondEvent.id

    return eventSortDirection.value === 'asc'
      ? comparison
      : -comparison
  })
})

onMounted(async () => {
  try {
    events.value = await fetchEvents()
  } catch (error) {
    eventsError.value =
      error instanceof Error ? error.message : '事件数据加载失败'
  } finally {
    eventsLoading.value = false
  }
})

function selectEvent(maritimeEvent: ApiEvent) {
  selectedEvent.value = maritimeEvent
}

function changeEventType(eventType: string) {
  selectedEventType.value = eventType
  selectedEvent.value = null
}

function changeEventSortDirection(direction: EventSortDirection) {
  eventSortDirection.value = direction
  selectedEvent.value = null
}

function restoreGlobalView() {
  selectedEvent.value = null
}
</script>

<template>
  <main class="app-layout">
    <section class="map-column">
      <section class="map-area">
        <MapView
          :events="visibleEvents"
          :selected-event="selectedEvent"
          @select-event="selectEvent"
        />
      </section>
      <TimelineControls />
    </section>

    <EventPanel
      :events="visibleEvents"
      :total-event-count="events.length"
      :event-types="eventTypes"
      :selected-event-type="selectedEventType"
      :sort-direction="eventSortDirection"
      :loading="eventsLoading"
      :error-message="eventsError"
      :selected-event="selectedEvent"
      @select-event="selectEvent"
      @change-event-type="changeEventType"
      @change-sort-direction="changeEventSortDirection"
      @restore-global-view="restoreGlobalView"
    />
  </main>
</template>

<style>
html,
body,
#app {
  width: 100%;
  height: 100%;
  margin: 0;
}

#app {
  max-width: none;
  min-height: 0;
  border: 0;
  display: block;
}

.app-layout {
  width: 100%;
  height: 100vh;
  display: grid;
  grid-template-columns: minmax(0, 1fr) 380px;
  overflow: hidden;
}

.map-column{
  min-width: 0;
  min-height: 0;
  display: grid;
  grid-template-rows: minmax(0, 1fr) 96px;
}

.map-area {
  min-width: 0;
  min-height: 0;
  overflow: hidden;
}
</style>
