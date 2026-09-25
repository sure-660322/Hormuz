<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount, ref, watch } from 'vue'
import type { ApiEvent as NewsEvent } from '../api'
type ApiEvent = NewsEvent & { occurred_at: string }
import { displayZone, eventKind, eventKinds, formatTime, zoneLabel } from '../domain/maritime'
const props = defineProps<{
  frameTimes: string[]
  modelValue: number
  loading: boolean
  errorMessage: string
  events: ApiEvent[]
  selectedEventId: number | null
  seekRequest: number
  eventType: string
  snapshotMode?: boolean
  frameReady?: boolean
  frameError?: string
}>()
const emit = defineEmits<{
  'update:modelValue': [index: number]
  retry: []
  selectEvent: [event: ApiEvent]
  typeChange: [type: string]
  speedChange: [speed: number]
}>()
const playing = ref(false)
const speed = ref(1)
const zoomStart = ref(0)
const zoomEnd = ref<number | null>(null)
const dragStart = ref<number | null>(null)
const dragEnd = ref<number | null>(null)
const expanded = ref(false)
const rangeEnd = computed(() => Math.min(last.value, zoomEnd.value ?? last.value))
const visibleFrames = computed(() => props.frameTimes.slice(zoomStart.value, rangeEnd.value + 1))
function resetZoom() { zoomStart.value = 0; zoomEnd.value = null }
function pointerPercent(event: PointerEvent) {
  const rect = (event.currentTarget as HTMLElement).getBoundingClientRect()
  return Math.max(0, Math.min(100, (event.clientX - rect.left) / rect.width * 100))
}
function startBrush(event: PointerEvent) { if (!hasFrames.value || event.button !== 0) return; stop(); dragStart.value = pointerPercent(event); dragEnd.value = dragStart.value; (event.currentTarget as HTMLElement).setPointerCapture(event.pointerId) }
function finishBrush(event: PointerEvent) {
  if (dragStart.value === null) return
  const from = dragStart.value, to = pointerPercent(event), span = rangeEnd.value - zoomStart.value, base = zoomStart.value
  dragStart.value = null; dragEnd.value = null
  if (Math.abs(from - to) < 2) { move(base + Math.round(to / 100 * span)); return }
  const low = base + Math.floor(Math.min(from, to) / 100 * span), high = base + Math.ceil(Math.max(from, to) / 100 * span)
  zoomStart.value = low; zoomEnd.value = Math.max(low + 1, high); move(low)
}
const histogram = computed(() => {
  const bins = Array.from({ length: 40 }, () => 0)
  for (const e of props.events) {
    const t = Date.parse(e.occurred_at)
    if (t < start.value || t > end.value) continue
    bins[Math.min(39, Math.floor(percent(e.occurred_at) / 100 * 40))]!++
  }
  const max = Math.max(1, ...bins)
  return bins.map(count => ({ count, height: count / max * 100 }))
})
const nextEvent = computed(() => props.events.filter(e => Date.parse(e.occurred_at) > Date.parse(current.value ?? '')).sort((a, b) => Date.parse(a.occurred_at) - Date.parse(b.occurred_at))[0])
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
const start = computed(() => Date.parse(props.frameTimes[zoomStart.value] ?? ''))
const end = computed(() => Date.parse(props.frameTimes[rangeEnd.value] ?? ''))
const percent = (value: string) =>
  Math.max(
    0,
    Math.min(
      100,
      ((Date.parse(value) - start.value) /
        Math.max(1, end.value - start.value)) *
        100,
    ),
  )
const progress = computed(() => (current.value ? percent(current.value) : 0))
const ticks = computed(() => {
  const indexes = [
    ...new Set(
      Array.from({ length: Math.min(7, visibleFrames.value.length) }, (_, i) =>
        zoomStart.value + Math.round(
          (i * (rangeEnd.value - zoomStart.value)) /
            Math.max(1, Math.min(7, visibleFrames.value.length) - 1),
        ),
      ),
    ),
  ]
  return indexes.map((i) => ({
    time: props.frameTimes[i]!,
    left: percent(props.frameTimes[i]!),
  }))
})
const lanes = computed(() =>
  Object.entries(eventKinds).filter(([type]) => type === props.eventType).map(([type, kind]) => {
    const groups: { time: string; events: ApiEvent[] }[] = []
    props.events
      .filter(
        (e) =>
          e.event_type === type &&
          Date.parse(e.occurred_at) >= start.value &&
          Date.parse(e.occurred_at) <= end.value,
      )
      .sort(
        (a, b) =>
          Date.parse(a.occurred_at) - Date.parse(b.occurred_at) || a.id - b.id,
      )
      .forEach((e) => {
        const previous = groups.at(-1)
        if (
          previous &&
          ((percent(e.occurred_at) - percent(previous.time)) *
            laneWidth.value) /
            100 <
            23
        )
          previous.events.push(e)
        else groups.push({ time: e.occurred_at, events: [e] })
      })
    return { type, kind, groups }
  }),
)
function stop() {
  playing.value = false
  clearInterval(timer)
  timer = undefined
}
function move(index: number) {
  stop()
  emit('update:modelValue', Math.max(zoomStart.value, Math.min(rangeEnd.value, index)))
}
function play() {
  if (props.snapshotMode && props.frameError) return
  if (playing.value) {
    stop()
    return
  }
  if (!hasFrames.value) return
  if (props.modelValue >= rangeEnd.value || props.modelValue < zoomStart.value) emit('update:modelValue', zoomStart.value)
  playing.value = true
}
function selectGroup(events: ApiEvent[]) {
  stop()
  const selected = events.findIndex(
    (event) => event.id === props.selectedEventId,
  )
  emit('selectEvent', events[(selected + 1) % events.length]!)
}
watch([playing, speed], () => {
  clearInterval(timer)
  if (!playing.value) return
  timer = setInterval(() => {
    if (props.snapshotMode && !props.frameReady) return
    const next = Math.min(rangeEnd.value, props.modelValue + 1)
    emit('update:modelValue', next)
    if (next === rangeEnd.value) stop()
  }, 1000 / speed.value)
})
watch(speed, value => emit('speedChange', value))
watch(() => props.frameError, (message) => { if (message) stop() })
watch(() => props.seekRequest, () => { stop(); resetZoom() })
watch(
  () => props.loading,
  (loading) => {
    if (loading) stop()
  },
)
watch(() => props.frameTimes, () => { stop(); resetZoom() })
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
    :class="{ expanded }"
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
            :disabled="modelValue <= zoomStart"
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
            :disabled="modelValue >= rangeEnd"
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
        ><span class="frame-count"
          >{{ modelValue + 1 }} / {{ frameTimes.length }} 帧</span
        >
        <button class="timeline-expand" :aria-expanded="expanded" @click="expanded = !expanded">{{ expanded ? '收起分析' : '展开分析' }}</button>
      </div>
      <div class="timeline-mini" aria-hidden="true">
        <div class="mini-bins">
          <i
            v-for="(bin, i) in histogram"
            :key="i"
            :style="{ height: `${Math.max(bin.count ? 15 : 0, bin.height)}%` }"
          ></i>
        </div>
        <span class="mini-progress" :style="{ width: progress + '%' }"></span>
      </div>
      <div class="timeline-detail">
        <div v-if="events.length" class="timeline-options"><select aria-label="时间轴事件类别" :value="eventType" @change="emit('typeChange', ($event.target as HTMLSelectElement).value)"><option value="all">全部 · 密度概览</option><option v-for="(kind, type) in eventKinds" :key="type" :value="type">{{ kind.label }} · 展开节点</option></select><button :disabled="!nextEvent" @click="nextEvent && emit('selectEvent', nextEvent)">下一事件</button><button :disabled="zoomStart === 0 && zoomEnd === null" @click="resetZoom">恢复全时段</button><span>{{ zoneLabel() }} · 拖动柱图缩放</span></div>
      <div ref="body" class="timeline-body">
        <div class="timeline-scale">
          <span>时间</span>
          <div class="tick-track">
            <time
              v-for="(tick, i) in ticks"
              :key="tick.time"
              :style="{ left: tick.left + '%' }"
              :class="{ first: i === 0, last: i === ticks.length - 1 }"
              >{{ formatTime(tick.time) }}</time
            >
          </div>
        </div>
        <div class="time-slider-row">
          <label for="replay-time">船位采样</label
          ><input
            id="replay-time"
            type="range"
            :min="zoomStart"
            :max="rangeEnd"
            step="1"
            :value="modelValue"
            :disabled="!hasFrames"
            aria-label="回放时间"
            :aria-valuetext="formatTime(current, true)"
            @input="move(Number(($event.target as HTMLInputElement).value))"
          />
        </div>
        <div v-if="events.length" class="density-row"><span>事件密度</span><div class="density-chart" aria-label="事件密度，拖动选择时间范围；下方也可使用键盘选择范围" @pointerdown="startBrush" @pointermove="dragStart !== null && (dragEnd = pointerPercent($event))" @pointerup="finishBrush" @pointercancel="dragStart = null; dragEnd = null"><div v-for="(bin, i) in histogram" :key="i" class="density-bin" :title="`${bin.count} 条事件`"><i :style="{ height: `${Math.max(bin.count ? 8 : 0, bin.height)}%` }"></i></div><span class="density-head" :style="{ left: progress + '%' }"></span><div v-if="dragStart !== null && dragEnd !== null" class="brush-selection" :style="{ left: Math.min(dragStart, dragEnd) + '%', width: Math.abs(dragStart - dragEnd) + '%' }"></div></div></div>
        <div v-if="events.length" class="event-lanes">
          <div
            class="playhead"
            :style="{ left: `calc(78px + (100% - 78px) * ${progress / 100})` }"
          ></div>
          <div v-for="lane in lanes" :key="lane.type" class="timeline-lane">
            <span>{{ lane.kind.label }}</span>
            <div class="lane-track">
              <button
                v-for="group in lane.groups"
                :key="group.time"
                class="timeline-event"
                :class="{
                  selected: group.events.some((e) => e.id === selectedEventId),
                }"
                :style="{
                  left: percent(group.time) + '%',
                  color: eventKind(lane.type).color,
                }"
                :aria-label="`${formatTime(group.time)} ${group.events.map((e) => e.title).join('、')}${group.events.length > 1 ? '，重复点击切换合并事件' : ''}`"
                :title="`${formatTime(group.time)} ${group.events.map((e) => e.title).join(' / ')}${group.events.length > 1 ? '（重复点击切换）' : ''}`"
                @click="selectGroup(group.events)"
              >
                <img class="lane-icon" :src="lane.kind.icon" alt=""><sup v-if="group.events.length > 1">{{
                  group.events.length
                }}</sup>
              </button>
            </div>
          </div>
        </div>
      </div>
      <div class="timeline-caption">
        <span>空格播放 / 暂停 · ← → 逐帧 · 新闻按发生时间逐步出现</span
        ><span>1× 每秒推进一帧 · 仅显示载入时段</span>
      </div>
      <details class="time-range-accessible"><summary>精确选择时间范围</summary><label>开始 <select :value="zoomStart" @change="stop(); zoomStart = Math.min(rangeEnd, Number(($event.target as HTMLSelectElement).value))"><option v-for="(t, i) in frameTimes" :key="t" :value="i">{{ formatTime(t) }}</option></select></label><label>结束 <select :value="rangeEnd" @change="stop(); zoomEnd = Math.max(zoomStart, Number(($event.target as HTMLSelectElement).value))"><option v-for="(t, i) in frameTimes" :key="t" :value="i">{{ formatTime(t) }}</option></select></label></details>
      </div>
    </template>
  </section>
</template>
