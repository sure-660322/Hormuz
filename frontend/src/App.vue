<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import {
  fetchEvents,
  fetchPlaybackPositions,
  fetchSimulationMeta,
} from './api'
import type { ApiEvent, ApiShipPosition } from './api'
import EventPanel from './components/EventPanel.vue'
import MapView from './components/MapView.vue'
import TimelineControls from './components/TimelineControls.vue'

const events = ref<ApiEvent[]>([])
const selectedEvent = ref<ApiEvent | null>(null)
const globalViewRequest = ref(0)
const eventsLoading = ref(true)
const eventsError = ref('')
type EventSortDirection = 'asc' | 'desc'

const selectedEventType = ref('all')
const eventSortDirection = ref<EventSortDirection>('asc')
const shipIsolationMode = ref(false)
const playbackFrames = ref<
  { time: string; positions: ApiShipPosition[] }[]
>([])
const playbackTracksByShip = ref<Record<number, ApiShipPosition[]>>({})
const playbackFrameIndex = ref(0)
const playbackLoading = ref(true)
const playbackError = ref('')

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

const playbackFrameTimes = computed(() =>
  playbackFrames.value.map((frame) => frame.time),
)

const currentPlaybackTime = computed(
  () => playbackFrames.value[playbackFrameIndex.value]?.time ?? null,
)

const currentPlaybackPositions = computed(
  () => playbackFrames.value[playbackFrameIndex.value]?.positions ?? [],
)

const mapEvents = computed(() => {
  const currentTime = currentPlaybackTime.value
  if (!currentTime) return visibleEvents.value

  const currentTimestamp = Date.parse(currentTime)
  return visibleEvents.value.filter(
    (maritimeEvent) =>
      Date.parse(maritimeEvent.occurred_at) <= currentTimestamp,
  )
})

async function loadEvents() {
  eventsLoading.value = true
  eventsError.value = ''

  try {
    events.value = await fetchEvents()
  } catch (error) {
    eventsError.value =
      error instanceof Error ? error.message : '事件数据加载失败'
  } finally {
    eventsLoading.value = false
  }
}

async function loadPlayback() {
  playbackLoading.value = true
  playbackError.value = ''

  try {
    const meta = await fetchSimulationMeta()
    if (!meta.start_at || !meta.end_at || meta.frame_count === 0) {
      playbackFrames.value = []
      playbackError.value = '暂无可回放的模拟位置数据'
      return
    }

    const positions = await fetchPlaybackPositions(
      meta.start_at,
      meta.end_at,
    )
    const positionsByTime = new Map<string, ApiShipPosition[]>()
    const tracksByShip: Record<number, ApiShipPosition[]> = {}

    for (const position of positions) {
      const framePositions = positionsByTime.get(position.recorded_at)
      if (framePositions) {
        framePositions.push(position)
      } else {
        positionsByTime.set(position.recorded_at, [position])
      }

      if (tracksByShip[position.ship_id]) {
        tracksByShip[position.ship_id].push(position)
      } else {
        tracksByShip[position.ship_id] = [position]
      }
    }

    playbackFrames.value = [...positionsByTime.entries()]
      .sort(
        ([firstTime], [secondTime]) =>
          Date.parse(firstTime) - Date.parse(secondTime),
      )
      .map(([time, framePositions]) => ({
        time,
        positions: framePositions,
      }))
    playbackTracksByShip.value = tracksByShip
    playbackFrameIndex.value = 0
  } catch (error) {
    playbackFrames.value = []
    playbackTracksByShip.value = {}
    playbackError.value =
      error instanceof Error ? error.message : '回放数据加载失败'
  } finally {
    playbackLoading.value = false
  }
}

onMounted(() => {
  void loadEvents()
  void loadPlayback()
})

function selectEvent(maritimeEvent: ApiEvent) {
  selectedEvent.value =
    selectedEvent.value?.id === maritimeEvent.id
      ? null
      : maritimeEvent
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
  globalViewRequest.value += 1
}

function changeShipIsolationMode(isIsolated: boolean) {
  shipIsolationMode.value = isIsolated
}
</script>

<template>
  <main
    class="app-layout"
    :class="{ isolated: shipIsolationMode }"
  >
    <section class="map-column">
      <section class="map-area">
        <MapView
          :events="mapEvents"
          :selected-event="selectedEvent"
          :global-view-request="globalViewRequest"
          :playback-positions="currentPlaybackPositions"
          :playback-tracks-by-ship="playbackTracksByShip"
          :current-playback-time="currentPlaybackTime"
          @select-event="selectEvent"
          @isolation-change="changeShipIsolationMode"
        />
      </section>
      <TimelineControls
        v-model="playbackFrameIndex"
        :frame-times="playbackFrameTimes"
        :loading="playbackLoading"
        :error-message="playbackError"
        @retry="loadPlayback"
      />
    </section>

    <EventPanel
      v-if="!shipIsolationMode"
      :events="visibleEvents"
      :total-event-count="events.length"
      :event-types="eventTypes"
      :selected-event-type="selectedEventType"
      :sort-direction="eventSortDirection"
      :loading="eventsLoading"
      :error-message="eventsError"
      :selected-event="selectedEvent"
      :current-time="currentPlaybackTime"
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

.app-layout.isolated {
  grid-template-columns: minmax(0, 1fr);
}

.map-column{
  min-width: 0;
  min-height: 0;
  display: grid;
  grid-template-rows: minmax(0, 1fr) 112px;
}

@media (max-width: 820px) {
  .map-column {
    grid-template-rows: minmax(0, 1fr) 142px;
  }
}

.map-area {
  min-width: 0;
  min-height: 0;
  overflow: hidden;
}
</style>
