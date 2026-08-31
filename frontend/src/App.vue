<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { fetchEvents } from './api'
import type { ApiEvent } from './api'
import EventPanel from './components/EventPanel.vue'
import MapView from './components/MapView.vue'

const events = ref<ApiEvent[]>([])
const selectedEvent = ref<ApiEvent | null>(null)
const eventsLoading = ref(true)
const eventsError = ref('')

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
</script>

<template>
  <main class="app-layout">
    <section class="map-area">
      <MapView
        :events="events"
        :selected-event="selectedEvent"
      />
    </section>

    <EventPanel
      :events="events"
      :loading="eventsLoading"
      :error-message="eventsError"
      :selected-event-id="selectedEvent?.id ?? null"
      @select-event="selectEvent"
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

.map-area {
  min-width: 0;
  min-height: 0;
  overflow: hidden;
}
</style>