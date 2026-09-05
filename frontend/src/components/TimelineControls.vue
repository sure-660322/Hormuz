<script setup lang="ts">
import {
  computed,
  onBeforeUnmount,
  ref,
  watch,
} from 'vue'

const props = defineProps<{
  frameTimes: string[]
  modelValue: number
  loading: boolean
  errorMessage: string
}>()

const emit = defineEmits<{
  'update:modelValue': [frameIndex: number]
  retry: []
}>()

type PlaybackSpeed = 0.5 | 1 | 2 | 4

const isPlaying = ref(false)
const playbackSpeed = ref<PlaybackSpeed>(1)
let timerId: number | undefined

const hasFrames = computed(() => props.frameTimes.length > 0)
const lastFrameIndex = computed(() =>
  Math.max(0, props.frameTimes.length - 1),
)
const currentTime = computed(
  () => props.frameTimes[props.modelValue] ?? null,
)

function formatTime(value: string | null, includeDate = true) {
  if (!value) return '尚未加载'

  return new Intl.DateTimeFormat('zh-CN', {
    timeZone: 'Asia/Shanghai',
    ...(includeDate
      ? { month: '2-digit', day: '2-digit' }
      : {}),
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(new Date(value))
}

function clearTimer() {
  if (timerId === undefined) return
  window.clearInterval(timerId)
  timerId = undefined
}

function advanceFrame() {
  const nextFrameIndex = props.modelValue + 1

  if (nextFrameIndex >= lastFrameIndex.value) {
    emit('update:modelValue', lastFrameIndex.value)
    isPlaying.value = false
    return
  }

  emit('update:modelValue', nextFrameIndex)
}

function restartTimer() {
  clearTimer()
  if (!isPlaying.value || !hasFrames.value) return

  timerId = window.setInterval(
    advanceFrame,
    1000 / playbackSpeed.value,
  )
}

function togglePlayback() {
  if (!hasFrames.value) return

  if (isPlaying.value) {
    isPlaying.value = false
    return
  }

  if (props.modelValue >= lastFrameIndex.value) {
    emit('update:modelValue', 0)
  }

  isPlaying.value = true
}

function resetPlayback() {
  isPlaying.value = false
  emit('update:modelValue', 0)
}

function handleSliderInput(event: Event) {
  isPlaying.value = false
  const input = event.target as HTMLInputElement
  emit('update:modelValue', Number(input.value))
}

function handleSpeedChange(event: Event) {
  const select = event.target as HTMLSelectElement
  playbackSpeed.value = Number(select.value) as PlaybackSpeed
}

watch([isPlaying, playbackSpeed], restartTimer)

watch(
  () => props.frameTimes.length,
  () => {
    isPlaying.value = false
    emit('update:modelValue', 0)
  },
)

onBeforeUnmount(clearTimer)
</script>

<template>
  <section
    class="timeline-controls"
    aria-label="船舶轨迹回放时间轴"
  >
    <div v-if="loading" class="timeline-status" aria-live="polite">
      正在加载模拟回放数据……
    </div>

    <div v-else-if="errorMessage" class="timeline-status timeline-error">
      <span>{{ errorMessage }}</span>
      <button type="button" @click="emit('retry')">重试</button>
    </div>

    <template v-else>
      <div class="timeline-toolbar">
        <button
          type="button"
          :disabled="!hasFrames"
          @click="resetPlayback"
        >
          ↺ 回到起点
        </button>

        <button
          type="button"
          class="play-button"
          :disabled="!hasFrames"
          @click="togglePlayback"
        >
          {{ isPlaying ? '❚❚ 暂停' : '▶ 播放' }}
        </button>

        <span class="current-time">
          当前时间（北京时间）：{{ formatTime(currentTime) }}
        </span>

        <label class="speed-control">
          播放速度

          <select
            :value="playbackSpeed"
            :disabled="!hasFrames"
            @change="handleSpeedChange"
          >
            <option :value="0.5">0.5×</option>
            <option :value="1">1×</option>
            <option :value="2">2×</option>
            <option :value="4">4×</option>
          </select>
        </label>
      </div>

      <div class="slider-row">
        <span>{{ formatTime(frameTimes[0] ?? null, false) }}</span>

        <input
          type="range"
          min="0"
          :max="lastFrameIndex"
          step="1"
          :value="modelValue"
          :disabled="!hasFrames"
          aria-label="回放时间"
          @input="handleSliderInput"
        >

        <span>{{ formatTime(frameTimes[lastFrameIndex] ?? null, false) }}</span>
        <output>{{ modelValue + 1 }} / {{ frameTimes.length }} 帧</output>
      </div>
    </template>
  </section>
</template>

<style scoped>
.timeline-controls {
  box-sizing: border-box;
  height: 112px;
  padding: 13px 20px;
  border-top: 1px solid #cbd5e1;
  background-color: #f8fafc;
  color: #0f172a;
}

.timeline-toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
}

.timeline-toolbar button,
.timeline-status button {
  padding: 7px 12px;
  border: 1px solid #94a3b8;
  border-radius: 6px;
  background-color: #ffffff;
  color: #334155;
  font: inherit;
  font-size: 13px;
  cursor: pointer;
}

.timeline-controls .timeline-toolbar button:not(:disabled),
.timeline-controls .timeline-status button:not(:disabled) {
  cursor: pointer;
}

.timeline-toolbar .play-button {
  border-color: #2563eb;
  background-color: #2563eb;
  color: #ffffff;
}

.timeline-toolbar button:disabled,
.speed-control select:disabled {
  cursor: not-allowed;
  opacity: 0.55;
}

.current-time {
  flex: 1;
  min-width: 220px;
  font-size: 14px;
  font-weight: 700;
  text-align: center;
}

.speed-control {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}

.speed-control select {
  padding: 5px 8px;
  border: 1px solid #cbd5e1;
  border-radius: 5px;
  background: #ffffff;
  color: #0f172a;
}

.slider-row {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto 76px;
  align-items: center;
  gap: 12px;
  margin-top: 12px;
  color: #64748b;
  font-size: 12px;
}

.slider-row input {
  width: 100%;
  accent-color: #2563eb;
  cursor: pointer;
}

.slider-row output {
  text-align: right;
}

.timeline-status {
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  color: #64748b;
  font-size: 14px;
}

.timeline-error {
  color: #b91c1c;
}

@media (max-width: 820px) {
  .timeline-controls {
    height: 142px;
  }

  .timeline-toolbar {
    flex-wrap: wrap;
  }

  .current-time {
    order: -1;
    flex-basis: 100%;
  }
}
</style>
