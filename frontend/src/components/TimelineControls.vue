<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount, ref, watch } from 'vue'
import { displayZone, formatTime, zoneLabel } from '../domain/maritime'
const props = defineProps<{
  frameTimes: string[]
  modelValue: number
  loading: boolean
  errorMessage: string
  seekRequest: number
  snapshotMode?: boolean
  frameReady?: boolean
  frameError?: string
  compact?: boolean
}>()
const emit = defineEmits<{
  'update:modelValue': [index: number]
  retry: []
  speedChange: [speed: number]
  toggleCompact: []
}>()
const playing = ref(false)
const speed = ref(1)
function keyboard(event: KeyboardEvent) {
  if (event.target instanceof HTMLElement && (event.target.closest('input, select, textarea, button, [contenteditable="true"]') || event.ctrlKey || event.metaKey || event.altKey)) return
  if (event.code === 'Space') { event.preventDefault(); play() }
  if (event.key === 'ArrowRight') { event.preventDefault(); move(props.modelValue + 1) }
  if (event.key === 'ArrowLeft') { event.preventDefault(); move(props.modelValue - 1) }
}
let timer: ReturnType<typeof setInterval> | undefined
const body = ref<HTMLElement | null>(null)
const laneWidth = ref(700)
let observer: ResizeObserver | undefined
const last = computed(() => Math.max(0, props.frameTimes.length - 1))
const current = computed(() => props.frameTimes[props.modelValue])
const fullCurrentTime = computed(() => current.value
  ? new Intl.DateTimeFormat('zh-CN', { timeZone: displayZone.value, year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false }).format(new Date(current.value))
  : '—')
const hasFrames = computed(() => props.frameTimes.length > 0)
const start = computed(() => Date.parse(props.frameTimes[0] ?? ''))
const end = computed(() => Date.parse(props.frameTimes[last.value] ?? ''))
const DAY_MS = 24 * 60 * 60 * 1000
const HOUR_MS = 60 * 60 * 1000
const multiDayScale = computed(() => end.value - start.value > 36 * HOUR_MS)
const ticks = computed(() => {
  if (!Number.isFinite(start.value) || !Number.isFinite(end.value) || end.value <= start.value) return []
  const offset = displayZone.value === 'Asia/Shanghai' ? 8 * HOUR_MS : 0
  const compact = laneWidth.value < 550
  const firstYear = new Date(start.value + offset).getUTCFullYear()
  const lastYear = new Date(end.value + offset).getUTCFullYear()
  const yearChanges = firstYear !== lastYear
  const result: { time: string; left: number; label: string; yearLabel: string; fullLabel: string; major: boolean }[] = []
  if (multiDayScale.value) {
    const firstMidnight = Math.ceil((start.value + offset) / DAY_MS) * DAY_MS - offset
    // The range can begin partway through a day; show that partial day when space permits.
    if ((firstMidnight - start.value) / (end.value - start.value) > (compact ? 0.09 : 0.06)) {
      const date = new Date(start.value + offset)
      const label = compact ? `${date.getUTCMonth() + 1}/${date.getUTCDate()}` : `${date.getUTCMonth() + 1}月${date.getUTCDate()}日`
      result.push({ time: new Date(start.value).toISOString(), left: 0, label, yearLabel: yearChanges ? String(date.getUTCFullYear()) : '', fullLabel: `${date.getUTCFullYear()}年${date.getUTCMonth() + 1}月${date.getUTCDate()}日`, major: true })
    }
    for (let at = firstMidnight; at <= end.value; at += DAY_MS) {
      const date = new Date(at + offset)
      const month = date.getUTCMonth() + 1, day = date.getUTCDate(), year = date.getUTCFullYear()
      result.push({ time: new Date(at).toISOString(), left: (at - start.value) / (end.value - start.value) * 100,
        label: compact ? `${month}/${day}` : `${month}月${day}日`,
        yearLabel: yearChanges && (result.length === 0 || (month === 1 && day === 1)) ? String(year) : '',
        fullLabel: `${year}年${month}月${day}日 00:00 ${zoneLabel()}`, major: true })
    }
  } else {
    const spanHours = (end.value - start.value) / HOUR_MS
    const stepHours = spanHours <= 6 ? 1 : spanHours <= 12 ? 2 : spanHours <= 24 ? 4 : 6
    const step = stepHours * HOUR_MS
    for (let at = Math.ceil((start.value + offset) / step) * step - offset; at <= end.value; at += step) {
      const date = new Date(at + offset)
      const hour = date.getUTCHours(), month = date.getUTCMonth() + 1, day = date.getUTCDate()
      result.push({ time: new Date(at).toISOString(), left: (at - start.value) / (end.value - start.value) * 100,
        label: `${String(hour).padStart(2, '0')}:00`, yearLabel: hour === 0 ? `${month}/${day}` : '',
        fullLabel: `${date.getUTCFullYear()}年${month}月${day}日 ${String(hour).padStart(2, '0')}:00 ${zoneLabel()}`, major: hour === 0 })
    }
    if (!result.length) {
      const date = new Date(start.value + offset)
      const hour = String(date.getUTCHours()).padStart(2, '0'), minute = String(date.getUTCMinutes()).padStart(2, '0')
      result.push({ time: new Date(start.value).toISOString(), left: 0, label: `${hour}:${minute}`,
        yearLabel: `${date.getUTCMonth() + 1}/${date.getUTCDate()}`,
        fullLabel: `${date.getUTCFullYear()}年${date.getUTCMonth() + 1}月${date.getUTCDate()}日 ${hour}:${minute} ${zoneLabel()}`, major: true })
    }
  }
  return result
})
function stop() {
  playing.value = false
  clearInterval(timer)
  timer = undefined
}
function move(index: number) {
  stop()
  emit('update:modelValue', Math.max(0, Math.min(last.value, index)))
}
function play() {
  if (props.snapshotMode && props.frameError) return
  if (playing.value) {
    stop()
    return
  }
  if (!hasFrames.value) return
  if (props.modelValue >= last.value || props.modelValue < 0) emit('update:modelValue', 0)
  playing.value = true
}
watch([playing, speed], () => {
  clearInterval(timer)
  if (!playing.value) return
  timer = setInterval(() => {
    if (props.snapshotMode && !props.frameReady) return
    const next = Math.min(last.value, props.modelValue + 1)
    emit('update:modelValue', next)
    if (next === last.value) stop()
  }, 1000 / speed.value)
})
watch(speed, value => emit('speedChange', value))
watch(() => props.frameError, (message) => { if (message) stop() })
watch(() => props.seekRequest, () => { stop() })
watch(
  () => props.loading,
  (loading) => {
    if (loading) stop()
  },
)
watch(() => props.frameTimes, () => { stop() })
onMounted(() => {
  window.addEventListener('keydown', keyboard)
  observer = new ResizeObserver(() => {
    if (body.value) laneWidth.value = Math.max(100, body.value.clientWidth - 88)
  })
  // The body mounts after async data; observe the stable parent section.
  if (body.value) observer.observe(body.value)
})
watch(body, (el) => {
  if (el) {
    observer?.observe(el)
    laneWidth.value = Math.max(100, el.clientWidth - 88)
  }
})
onBeforeUnmount(() => {
  window.removeEventListener('keydown', keyboard)
  stop()
  observer?.disconnect()
})
</script>
<template>
  <section
    class="timeline"
    aria-label="船位与新闻事件回放时间轴"
  >
    <div v-if="loading || errorMessage" class="timeline-status" role="status">
      {{ errorMessage || '正在加载回放数据…'
      }}<button v-if="errorMessage" @click="emit('retry')">重试</button>
    </div>
    <template v-else>
      <div class="timeline-toolbar">
        <div class="replay-title">
          <strong>{{ snapshotMode ? '历史 AIS 回放' : '船舶回放' }}</strong
          ><span
            >{{ formatTime(frameTimes[0], true).split(' ')[0] }} ·
            非实时 AIS</span
          >
        </div>
        <div class="playback-buttons">
          <button
            aria-label="回到起点"
            title="回到起点"
            :disabled="!hasFrames"
            @click="move(0)"
          >
            ↶</button
          ><button
            aria-label="上一帧"
            title="上一帧"
            :disabled="modelValue <= 0"
            @click="move(modelValue - 1)"
          >
            ‹</button
          ><button
            class="primary play-button"
            :disabled="!hasFrames || (snapshotMode && !!frameError)"
            :title="snapshotMode ? '按 5 分钟推进；目标快照未就绪时暂停等待' : undefined"
            @click="play"
          >
            {{ playing ? 'Ⅱ 暂停' : '▶ 播放' }}</button
          ><button
            aria-label="下一帧"
            title="下一帧"
            :disabled="modelValue >= last"
            @click="move(modelValue + 1)"
          >
            ›</button
          ><select v-model.number="speed" aria-label="播放速度">
            <option :value="0.5">0.5×</option>
            <option :value="1">1×</option>
            <option :value="2">2×</option>
            <option :value="4">4×</option>
          </select>
        </div>
        <output class="current-time"
          >{{ fullCurrentTime }}<small>{{ zoneLabel() }}</small></output
        ><button
          class="timeline-compact-toggle"
          type="button"
          :aria-pressed="compact"
          :title="compact ? '展开日期刻度' : '收起日期刻度，保留播放与时间滑块'"
          @click="emit('toggleCompact')"
        >
          {{ compact ? '展开轴' : '紧凑轴' }}</button
        ><span class="frame-count"
          >{{ modelValue + 1 }} / {{ frameTimes.length }} 帧</span
        >
      </div>
      <div ref="body" class="timeline-body">
        <div class="timeline-scale">
          <span>{{ multiDayScale ? '日期' : '时间' }}</span>
          <div class="tick-track">
            <time
              v-for="tick in ticks"
              :key="tick.time"
              :style="{ left: tick.left + '%' }"
              :class="{ first: tick.left < 2, last: tick.left > 98, major: tick.major }"
              :title="tick.fullLabel"
              :aria-label="tick.fullLabel"
              ><span>{{ tick.label }}</span><small v-if="tick.yearLabel">{{ tick.yearLabel }}</small></time
            >
          </div>
        </div>
        <div class="time-slider-row">
          <label for="replay-time">船位采样</label
          ><input
            id="replay-time"
            type="range"
            :min="0"
            :max="last"
            step="1"
            :value="modelValue"
            :disabled="!hasFrames"
            aria-label="回放时间"
            :aria-valuetext="formatTime(current, true)"
            @input="move(Number(($event.target as HTMLInputElement).value))"
          />
        </div>
      </div>
    </template>
  </section>
</template>
