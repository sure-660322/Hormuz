<script setup lang="ts">
import { computed } from 'vue'
import type { ApiTrackWindow } from '../api'
import { clipCaseTracks } from '../domain/casePlayback'
const props = defineProps<{ track: ApiTrackWindow | null; from: string; to: string; at: string | null; disabled: boolean }>()
const emit = defineEmits<{ seek: [at: string] }>()
const start = computed(() => Date.parse(props.from)), end = computed(() => Date.parse(props.to))
const segments = computed(() => clipCaseTracks(props.track, props.from, props.to))
const points = computed(() => segments.value.flatMap(s => s.points))
const valid = (v: number) => Number.isFinite(v) && v >= 0 && v <= 100
const ceiling = computed(() => Math.max(5, Math.ceil(Math.max(0, ...points.value.filter(p => valid(p.speed)).map(p => p.speed)) / 5) * 5))
const x = (t: string) => 32 + (Date.parse(t) - start.value) / Math.max(1, end.value - start.value) * 280
const y = (v: number) => 91 - v / ceiling.value * 65
const paths = computed(() => segments.value.map(s => {
  let connected = false
  return s.points.map(p => {
    if (!valid(p.speed)) { connected = false; return '' }
    const command = connected ? 'L' : 'M'; connected = true
    return command + x(p.recorded_at).toFixed(2) + ',' + y(p.speed).toFixed(2)
  }).join(' ')
}))
const cursor = computed(() => Math.max(start.value, Math.min(end.value, Date.parse(props.at ?? props.from))))
const latest = computed(() => points.value.filter(p => Date.parse(p.recorded_at) <= cursor.value).at(-1))
const reading = computed(() => latest.value && cursor.value - Date.parse(latest.value.recorded_at) <= 3600000 && valid(latest.value.speed) ? latest.value.speed.toFixed(1) + ' 节' : '暂无有效值')
function label(at: number, full = false) {
  return new Intl.DateTimeFormat('zh-CN', { timeZone: 'Asia/Shanghai', month: '2-digit', day: '2-digit', ...(full ? { hour: '2-digit', minute: '2-digit', hour12: false as const } : {}) }).format(new Date(at))
}
function locate(event: MouseEvent) {
  if (props.disabled) return
  const rect = (event.currentTarget as SVGSVGElement).getBoundingClientRect()
  const ratio = Math.max(0, Math.min(1, ((event.clientX - rect.left) / rect.width * 330 - 32) / 280))
  emit('seek', new Date(start.value + ratio * (end.value - start.value)).toISOString())
}
</script>
<template>
  <section class="speed-evidence" aria-label="案例航速与时间定位">
    <div class="plot-head"><h3>航速与观测</h3><span>{{ points.length }} 个采样点</span></div>
    <template v-if="points.length">
      <svg viewBox="0 0 330 120" role="img" aria-label="报位航速曲线，断开处表示缺报；下方滑块可定位时间" @click="locate">
        <g v-for="tick in [0, ceiling / 2, ceiling]" :key="tick"><line x1="32" x2="312" :y1="y(tick)" :y2="y(tick)" class="grid" /><text x="25" :y="y(tick) + 3" text-anchor="end">{{ tick }}</text></g>
        <text x="32" y="15">航速 / 节</text>
        <path v-for="(path, i) in paths" :key="i" :d="path" class="curve" />
        <circle v-for="p in segments.filter(s => s.points.length === 1).flatMap(s => s.points).filter(p => valid(p.speed))" :key="p.id" :cx="x(p.recorded_at)" :cy="y(p.speed)" r="2" class="sample" />
        <line :x1="32 + (cursor - start) / Math.max(1, end - start) * 280" :x2="32 + (cursor - start) / Math.max(1, end - start) * 280" y1="23" y2="95" class="cursor" />
        <text x="32" y="113">{{ label(start) }}</text><text x="312" y="113" text-anchor="end">{{ label(end) }}</text>
      </svg>
      <label class="scrub-label">定位时间 <span>{{ label(cursor, true) }} 北京时间</span>
        <input type="range" :min="start" :max="end" :value="cursor" step="300000" :disabled="disabled" aria-label="定位案例航速曲线时间" @change="emit('seek', new Date(Number(($event.target as HTMLInputElement).value)).toISOString())">
      </label>
      <p class="reading">此前一小时内最新采样航速 <strong>{{ reading }}</strong></p>
      <p class="plot-note">点击曲线或拖动滑块定位地图。{{ track?.bucket_seconds ?? 120 }} 秒桶采样报位，断线保留缺报，不代表全量航速统计。</p>
    </template>
    <p v-else class="plot-note">此范围暂无轨迹采样，可先阅读报道。</p>
  </section>
</template>
<style scoped>
.speed-evidence { padding: 17px 0; border-bottom: 1px solid var(--line) }
.plot-head { display:flex; justify-content:space-between; align-items:baseline; gap:8px }
h3 { margin:0; font-size:14px }.plot-head span,.plot-note,.reading { color:var(--muted); font-size:11px; line-height:1.7 }
svg { width:100%; display:block; margin:8px 0; cursor:crosshair }text { fill:var(--muted); font-size:10px }.grid { stroke:var(--line); stroke-dasharray:2 4 }
.curve { fill:none; stroke:#59c7bd; stroke-width:1.7; stroke-linejoin:round; stroke-linecap:round }.sample { fill:#59c7bd }.cursor { stroke:var(--ink); stroke-width:1; stroke-dasharray:3 3 }
.scrub-label { font-size:11px; display:flex; flex-wrap:wrap; justify-content:space-between; gap:6px }.scrub-label span { color:var(--muted) }
input { width:100%; accent-color:var(--accent); cursor:pointer }input:focus-visible { outline:2px solid var(--accent); outline-offset:3px }
.reading { margin:6px 0; display:flex; justify-content:space-between; gap:8px }.reading strong { color:var(--ink); font-weight:500 }.plot-note { margin:5px 0 0 }
</style>
