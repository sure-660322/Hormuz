<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import {
  fetchAisMapShips,
  fetchAisMeta,
  fetchAisPlaybackPositions,
  fetchAisVessels,
} from './api'
import type {
  ApiAisDatasetMeta,
  ApiAisMapShip,
  ApiAisVessel,
  ApiShipPosition,
} from './api'
import MapView from './components/MapView.vue'
import TimelineControls from './components/TimelineControls.vue'

const datasetMeta = ref<ApiAisDatasetMeta | null>(null)
const vessels = ref<ApiAisVessel[]>([])
const windowStartSnapshot = ref<ApiAisMapShip[]>([])
const windowPositions = ref<ApiShipPosition[]>([])
const playbackFrameTimes = ref<string[]>([])
const playbackFrameIndex = ref(0)
const selectedDate = ref('')
const playbackLoading = ref(true)
const playbackError = ref('')
const shipIsolationMode = ref(false)

const currentPlaybackTime = computed(
  () => playbackFrameTimes.value[playbackFrameIndex.value] ?? null,
)

const vesselsById = computed(() =>
  new Map(vessels.value.map((vessel) => [vessel.id, vessel])),
)

const currentMapShips = computed<ApiAisMapShip[]>(() => {
  const currentTime = currentPlaybackTime.value
  const currentTimestamp = currentTime ? Date.parse(currentTime) : Number.NaN
  const latestByShip = new Map<number, ApiAisMapShip>(
    windowStartSnapshot.value.map((ship) => [ship.id, ship]),
  )

  if (Number.isFinite(currentTimestamp)) {
    for (const position of windowPositions.value) {
      if (Date.parse(position.recorded_at) > currentTimestamp) break

      const vessel = vesselsById.value.get(position.ship_id)
      if (!vessel) continue

      latestByShip.set(position.ship_id, {
        ...vessel,
        position_id: position.id,
        latitude: position.latitude,
        longitude: position.longitude,
        speed: position.speed,
        course: position.course,
        heading: position.heading,
        recorded_at: position.recorded_at,
        received_at: position.received_at ?? null,
      })
    }
  }

  return [...latestByShip.values()]
})

const minDate = computed(() => datasetMeta.value?.start_at.slice(0, 10) ?? '')
const maxDate = computed(() => datasetMeta.value?.end_at.slice(0, 10) ?? '')

function buildFrameTimes(startAt: Date, endAt: Date, intervalSeconds: number) {
  const intervalMilliseconds = intervalSeconds * 1000
  const frameTimes: string[] = []
  for (
    let timestamp = startAt.getTime();
    timestamp <= endAt.getTime();
    timestamp += intervalMilliseconds
  ) {
    frameTimes.push(new Date(timestamp).toISOString())
  }

  const exactEnd = endAt.toISOString()
  if (frameTimes.at(-1) !== exactEnd) frameTimes.push(exactEnd)
  return frameTimes
}

function getWindowBounds(dateText: string, meta: ApiAisDatasetMeta) {
  const dayStart = new Date(`${dateText}T00:00:00.000Z`)
  const dayEnd = new Date(dayStart.getTime() + 24 * 60 * 60 * 1000 - 1)
  const datasetStart = new Date(meta.start_at)
  const datasetEnd = new Date(meta.end_at)

  return {
    startAt: dayStart < datasetStart ? datasetStart : dayStart,
    endAt: dayEnd > datasetEnd ? datasetEnd : dayEnd,
  }
}

async function loadSelectedDate(dateText = selectedDate.value) {
  const meta = datasetMeta.value
  if (!meta || !dateText) return

  playbackLoading.value = true
  playbackError.value = ''
  try {
    const { startAt, endAt } = getWindowBounds(dateText, meta)
    const [snapshot, positions] = await Promise.all([
      fetchAisMapShips(startAt.toISOString()),
      fetchAisPlaybackPositions(startAt.toISOString(), endAt.toISOString()),
    ])

    selectedDate.value = dateText
    windowStartSnapshot.value = snapshot
    windowPositions.value = positions
    playbackFrameTimes.value = buildFrameTimes(
      startAt,
      endAt,
      meta.frame_interval_seconds,
    )
    playbackFrameIndex.value = Math.max(
      0,
      playbackFrameTimes.value.length - 1,
    )
  } catch (error) {
    windowStartSnapshot.value = []
    windowPositions.value = []
    playbackFrameTimes.value = []
    playbackFrameIndex.value = 0
    playbackError.value =
      error instanceof Error ? error.message : 'AIS 回放数据加载失败'
  } finally {
    playbackLoading.value = false
  }
}

async function initializeAis() {
  playbackLoading.value = true
  playbackError.value = ''
  try {
    const [meta, vesselRows] = await Promise.all([
      fetchAisMeta(),
      fetchAisVessels(),
    ])
    datasetMeta.value = meta
    vessels.value = vesselRows
    selectedDate.value = meta.end_at.slice(0, 10)
    await loadSelectedDate(selectedDate.value)
  } catch (error) {
    playbackError.value =
      error instanceof Error ? error.message : 'AIS 数据加载失败'
    playbackLoading.value = false
  }
}

function changeSelectedDate(dateText: string) {
  if (dateText === selectedDate.value) return
  void loadSelectedDate(dateText)
}

function changeShipIsolationMode(isIsolated: boolean) {
  shipIsolationMode.value = isIsolated
}

onMounted(() => {
  void initializeAis()
})
</script>

<template>
  <main class="app-layout" :class="{ isolated: shipIsolationMode }">
    <section class="data-notice" aria-live="polite">
      <strong>历史 AIS 数据</strong>
      <span v-if="datasetMeta">
        {{ datasetMeta.vessel_count.toLocaleString('zh-CN') }} 艘船 ·
        {{ datasetMeta.position_count.toLocaleString('zh-CN') }} 条原始位置
      </span>
      <span>{{ datasetMeta?.coverage_note ?? '正在读取数据说明……' }}</span>
    </section>

    <section class="map-column">
      <section class="map-area">
        <MapView
          :map-ships="currentMapShips"
          :current-playback-time="currentPlaybackTime"
          @isolation-change="changeShipIsolationMode"
        />
      </section>

      <TimelineControls
        v-model="playbackFrameIndex"
        :frame-times="playbackFrameTimes"
        :loading="playbackLoading"
        :error-message="playbackError"
        :selected-date="selectedDate"
        :min-date="minDate"
        :max-date="maxDate"
        @change-date="changeSelectedDate"
        @retry="initializeAis"
      />
    </section>
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
  position: relative;
  width: 100%;
  height: 100vh;
  overflow: hidden;
}

.map-column {
  width: 100%;
  height: 100%;
  min-width: 0;
  min-height: 0;
  display: grid;
  grid-template-rows: minmax(0, 1fr) 128px;
}

.map-area {
  min-width: 0;
  min-height: 0;
  overflow: hidden;
}

.data-notice {
  position: absolute;
  z-index: 1050;
  top: 12px;
  left: 52px;
  display: flex;
  max-width: min(720px, calc(100% - 84px));
  flex-wrap: wrap;
  gap: 4px 12px;
  padding: 9px 12px;
  border: 1px solid #f59e0b;
  border-radius: 8px;
  background: rgb(255 251 235 / 94%);
  color: #78350f;
  font-size: 12px;
  box-shadow: 0 4px 14px rgb(15 23 42 / 18%);
}

@media (max-width: 820px) {
  .map-column {
    grid-template-rows: minmax(0, 1fr) 172px;
  }

  .data-notice {
    left: 48px;
    max-width: calc(100% - 64px);
  }
}
</style>
