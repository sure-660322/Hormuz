<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts/core'
import { BarChart } from 'echarts/charts'
import { GridComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import type { ComposeOption } from 'echarts/core'
import type { BarSeriesOption } from 'echarts/charts'
import type { GridComponentOption, TooltipComponentOption } from 'echarts/components'
import {
  describeApiError,
  fetchPassageCompare,
  fetchPassageEvidence,
  fetchPassageMeta,
  fetchPassageStatistics,
  type AgentAnalysisAction,
  type AgentMapAction,
  type ApiDailyStats,
  type ApiPassageCompare,
  type ApiPassageEvidence,
  type ApiPassageMeta,
  type ApiPassageStatistics,
} from '../api'

echarts.use([BarChart, GridComponent, TooltipComponent, CanvasRenderer])

type ChartOption = ComposeOption<BarSeriesOption | GridComponentOption | TooltipComponentOption>

const props = defineProps<{
  // 证据→地图联动复用智能体地图动作执行器（App.vue 注入）。
  executeMapAction: (action: AgentMapAction, signal: AbortSignal) => Promise<{ message: string; outcome: 'ok' | 'error' | 'cancelled' }>
  // 智能体「查看通行分析」动作：恢复该次调用的条件与结果（一次性，置 null 忽略）。
  restore: AgentAnalysisAction | null
}>()

const DIRECTIONS = [
  { value: '', label: '全部方向' },
  { value: 'inbound', label: '入湾（东→西）' },
  { value: 'outbound', label: '出湾（西→东）' },
] as const

const DAY_STATUS_LABEL: Record<string, string> = {
  ok: '正常',
  zero: '有效零结果',
  partial: '含不确定候选',
  no_observation: '无观测',
}

const METRIC_LABEL: Record<string, string> = {
  passage_count: '确定通行次数',
  unique_ship_count: '去重艘数',
  inbound_count: '入湾次数',
  outbound_count: '出湾次数',
  uncertain_candidate_count: '不确定候选',
}

// ------------------------------------------------------------- 查询条件
const mode = ref<'single' | 'compare'>('single')
const startDate = ref('2026-02-26')
const endDate = ref('2026-02-27')
const aStartDate = ref('2026-02-25')
const aEndDate = ref('2026-02-27')
const bStartDate = ref('2026-02-28')
const bEndDate = ref('2026-03-02')
const direction = ref<'' | 'inbound' | 'outbound'>('')
const selectedTypes = ref<string[]>([])
const meta = ref<ApiPassageMeta | null>(null)
const metaError = ref('')

const allTypeValues = computed(() => (meta.value?.ship_type_options ?? []).map((option) => option.value))
const allTypesSelected = computed({
  get: () => allTypeValues.value.length > 0 && allTypeValues.value.every((value) => selectedTypes.value.includes(value)),
  set: (on: boolean) => { selectedTypes.value = on ? [...allTypeValues.value] : [] },
})

function dateToUtcIso(day: string, endExclusive: boolean): string {
  // 日期按 UTC 自然日解释；结束端点为半开区间（endDate 的下一天 00:00 UTC）。
  const base = Date.parse(`${day}T00:00:00Z`)
  const ms = endExclusive ? base + 24 * 3600_000 : base
  return new Date(ms).toISOString()
}

const dayCount = (from: string, to: string) => Math.round((Date.parse(`${to}T00:00:00Z`) - Date.parse(`${from}T00:00:00Z`)) / 86400_000)

// 含首尾的完整 UTC 天数（结束日期当日计入区间）。
const inclusiveDays = (from: string, to: string) => dayCount(from, to) + 1

// 后端返回半开区间终点（end_at 为次日 00:00 UTC）；展示为含尾 UTC 日时回退 1 秒。
function inclusiveEndDay(endAt: string): string {
  return new Date(Date.parse(endAt) - 1000).toISOString().slice(0, 10)
}

function validateConditions(): string | null {
  if (mode.value === 'single') {
    if (!startDate.value || !endDate.value) return '请选择起止日期。'
    if (inclusiveDays(startDate.value, endDate.value) < 1) return '结束日期不能早于开始日期。'
    if (inclusiveDays(startDate.value, endDate.value) > 7) return '单时段最多 7 天（含首尾），请缩小范围。'
  } else {
    for (const [label, from, to] of [['A', aStartDate.value, aEndDate.value], ['B', bStartDate.value, bEndDate.value]] as const) {
      if (!from || !to) return `请选择 ${label} 段的起止日期。`
      if (inclusiveDays(from, to) < 1) return `${label} 段结束日期不能早于开始日期。`
      if (inclusiveDays(from, to) > 7) return `${label} 段最多 7 天（含首尾），请缩小范围。`
    }
  }
  return null
}

// ------------------------------------------------------------- 结果状态
const loading = ref(false)
const error = ref('')
const singleResult = ref<ApiPassageStatistics | null>(null)
const compareResult = ref<ApiPassageCompare | null>(null)
// 结果与条件的绑定：展示统计摘要时必须连同发起条件一起，防止旧响应覆盖新条件。
const resultStamp = ref<{ key: string; at: number } | null>(null)
let requestController: AbortController | null = null
let requestSeq = 0

function currentConditionsKey(): string {
  const types = [...selectedTypes.value].sort().join(',')
  if (mode.value === 'single')
    return `single|${startDate.value}|${endDate.value}|${direction.value}|${types}`
  return `compare|${aStartDate.value}|${aEndDate.value}|${bStartDate.value}|${bEndDate.value}|${direction.value}|${types}`
}

function spec() {
  const ship_types = selectedTypes.value.length ? [...selectedTypes.value] : null
  return { ship_types, direction: direction.value || null }
}

async function runQuery() {
  const invalid = validateConditions()
  if (invalid) { error.value = invalid; return }
  requestController?.abort()
  const controller = new AbortController()
  requestController = controller
  const seq = ++requestSeq
  const key = currentConditionsKey()
  loading.value = true
  error.value = ''
  evidence.value = null
  evidenceError.value = ''
  try {
    if (mode.value === 'single') {
      const result = await fetchPassageStatistics(
        dateToUtcIso(startDate.value, false), dateToUtcIso(endDate.value, true), spec(), controller.signal)
      if (seq !== requestSeq) return
      singleResult.value = result
      compareResult.value = null
    } else {
      const result = await fetchPassageCompare(
        dateToUtcIso(aStartDate.value, false), dateToUtcIso(aEndDate.value, true),
        dateToUtcIso(bStartDate.value, false), dateToUtcIso(bEndDate.value, true),
        spec(), controller.signal)
      if (seq !== requestSeq) return
      compareResult.value = result
      singleResult.value = null
    }
    resultStamp.value = { key, at: Date.now() }
    await nextEvidencePage(1)
  } catch (e) {
    if (seq === requestSeq && !controller.signal.aborted) {
      error.value = describeApiError(e, '通行统计查询失败')
      singleResult.value = null
      compareResult.value = null
    }
  } finally {
    if (seq === requestSeq) { loading.value = false; requestController = null }
  }
}

function cancelQuery() {
  requestSeq++
  requestController?.abort()
  requestController = null
  loading.value = false
}

// ------------------------------------------------------------- 恢复（智能体交接）
watch(() => props.restore, (action) => {
  if (!action) return
  const query = action.query
  mode.value = query.mode
  direction.value = (query.direction as '' | 'inbound' | 'outbound') ?? ''
  if (query.ship_types && meta.value) {
    const known = new Set(allTypeValues.value)
    selectedTypes.value = query.ship_types.filter((value) => known.has(value))
  }
  if (query.mode === 'single') {
    if (query.start_at) { startDate.value = query.start_at.slice(0, 10); endDate.value = (query.end_at ?? query.start_at).slice(0, 10) }
    if (action.summary && typeof action.summary.window === 'object') {
      singleResult.value = restoreSingleFromSummary(action.summary)
      compareResult.value = null
      resultStamp.value = { key: currentConditionsKey(), at: Date.now() }
    }
  } else {
    if (query.a_start_at) aStartDate.value = query.a_start_at.slice(0, 10)
    if (query.a_end_at) aEndDate.value = query.a_end_at.slice(0, 10)
    if (query.b_start_at) bStartDate.value = query.b_start_at.slice(0, 10)
    if (query.b_end_at) bEndDate.value = query.b_end_at.slice(0, 10)
    if (action.summary && Array.isArray(action.summary.metrics)) {
      compareResult.value = restoreCompareFromSummary(action.summary)
      singleResult.value = null
      resultStamp.value = { key: currentConditionsKey(), at: Date.now() }
    }
  }
  if (singleResult.value || compareResult.value) void nextEvidencePage(1)
})

function restoreSingleFromSummary(summary: Record<string, unknown>): ApiPassageStatistics {
  return {
    status: (summary.status as ApiPassageStatistics['status']) ?? 'ok',
    start_at: String(summary.start_at ?? dateToUtcIso(startDate.value, false)),
    end_at: String(summary.end_at ?? dateToUtcIso(endDate.value, true)),
    requested_days: Number(summary.requested_days ?? dayCount(startDate.value, endDate.value)),
    ship_types: (summary.ship_types as string[] | null) ?? null,
    direction: (summary.direction as string | null) ?? null,
    daily: (summary.daily as ApiDailyStats[]) ?? [],
    window: summary.window as ApiPassageStatistics['window'],
    determination_version: String(summary.determination_version ?? ''),
    schema_version: '4',
    data_source: 'nnu_ais',
    limitations: (summary.limitations as string[]) ?? [],
  }
}

function restoreCompareFromSummary(summary: Record<string, unknown>): ApiPassageCompare {
  const period = (value: unknown): ApiPassageStatistics => {
    const record = (value ?? {}) as Record<string, unknown>
    return {
      status: (record.status as ApiPassageStatistics['status']) ?? 'ok',
      start_at: String(record.start_at ?? ''),
      end_at: String(record.end_at ?? ''),
      requested_days: 0, ship_types: null, direction: null, daily: [],
      window: record.window as ApiPassageStatistics['window'],
      determination_version: String(summary.determination_version ?? ''),
      schema_version: '4', data_source: 'nnu_ais', limitations: [],
    }
  }
  const a = period(summary.a_period)
  const b = period(summary.b_period)
  a.requested_days = dayCount(aStartDate.value, aEndDate.value)
  b.requested_days = dayCount(bStartDate.value, bEndDate.value)
  return {
    status: (summary.status as ApiPassageCompare['status']) ?? 'ok',
    ship_types: (summary.ship_types as string[] | null) ?? null,
    direction: (summary.direction as string | null) ?? null,
    a, b,
    metrics: (summary.metrics as ApiPassageCompare['metrics']) ?? [],
    a_period_days: a.requested_days, b_period_days: b.requested_days,
    a_avg_passages_per_day: Number(summary.a_avg_passages_per_day ?? 0),
    b_avg_passages_per_day: Number(summary.b_avg_passages_per_day ?? 0),
    windows_overlap: Boolean(summary.windows_overlap),
    comparability_notes: (summary.comparability_notes as string[]) ?? [],
    determination_version: String(summary.determination_version ?? ''),
  }
}

// ------------------------------------------------------------- 证据明细
const evidence = ref<ApiPassageEvidence | null>(null)
const evidenceError = ref('')
const evidenceDay = ref('')
const evidencePage = ref(1)
const includeUncertain = ref(false)
const mapMessage = ref('')
const mapBusyKey = ref('')

function activeQueryWindow(): { start: string; end: string } | null {
  if (singleResult.value) return { start: singleResult.value.start_at, end: singleResult.value.end_at }
  if (compareResult.value && evidenceDay.value) {
    const day = evidenceDay.value
    const inA = compareResult.value.a.daily.some((d) => d.day === day)
    const period = inA ? compareResult.value.a : compareResult.value.b
    return { start: period.start_at, end: period.end_at }
  }
  return null
}

async function nextEvidencePage(page: number) {
  const window = activeQueryWindow()
  if (!window) return
  evidencePage.value = page
  evidenceError.value = ''
  try {
    const result = await fetchPassageEvidence(window.start, window.end, {
      day: evidenceDay.value || undefined,
      ship_types: spec().ship_types,
      direction: spec().direction,
      include_uncertain: includeUncertain.value,
      page,
      page_size: 10,
    })
    if (resultStamp.value?.key !== currentConditionsKey()) return  // 条件已变，旧明细不覆盖
    evidence.value = result
  } catch (e) {
    evidenceError.value = describeApiError(e, '证据明细加载失败')
    evidence.value = null
  }
}

watch([evidenceDay, includeUncertain], () => { if (resultStamp.value) void nextEvidencePage(1) })

async function showEvidenceOnMap(item: ApiPassageEvidence['items'][number]) {
  const window = activeQueryWindow()
  if (!window) return
  mapMessage.value = ''
  mapBusyKey.value = item.stable_key
  // 证据时段：完成观测时间前后各 6 小时，裁剪到查询窗口内；与地图回放时段分别标明。
  const completionMs = Date.parse(item.observed_completion_at)
  const startMs = Math.max(Date.parse(window.start), completionMs - 6 * 3600_000)
  const endMs = Math.min(Date.parse(window.end), completionMs + 6 * 3600_000)
  const controller = new AbortController()
  try {
    const result = await props.executeMapAction({
      type: 'ship_track', trigger: 'suggested', ship_id: item.ship_id,
      start_at: new Date(startMs).toISOString(), end_at: new Date(endMs).toISOString(),
      source: 'nnu_ais', window_source: '通行分析证据时段（非回放时段）', clamp_to_coverage: true,
    }, controller.signal)
    mapMessage.value = result.message
  } catch (e) {
    mapMessage.value = describeApiError(e, '地图加载失败')
  } finally {
    mapBusyKey.value = ''
  }
}

// ------------------------------------------------------------- 图表
const chartEl = ref<HTMLElement | null>(null)
let chart: ReturnType<typeof echarts.init> | null = null
let resizeObserver: ResizeObserver | null = null

function singleSeries(): { option: ChartOption; empty: boolean } {
  const daily = singleResult.value?.daily ?? []
  const empty = daily.every((day) => day.status === 'no_observation')
  return {
    empty,
    option: {
      animation: false,
      grid: { top: 24, right: 16, bottom: 24, left: 40 },
      tooltip: {
        trigger: 'axis',
        formatter: (params) => {
          const list = (Array.isArray(params) ? params : [params]) as unknown as Array<{ dataIndex: number }>
          const day = daily[list[0]?.dataIndex ?? 0]
          if (!day) return ''
          return [
            `${day.day} UTC`,
            `确定通行 <b>${day.passage_count}</b> 次 · 去重 <b>${day.unique_ship_count}</b> 艘`,
            `入湾 ${day.inbound_count} · 出湾 ${day.outbound_count} · 候选 ${day.uncertain_candidate_count}`,
            `状态：${DAY_STATUS_LABEL[day.status] ?? day.status}`,
          ].join('<br/>')
        },
      },
      xAxis: { type: 'category', data: daily.map((day) => day.day.slice(5)), axisLabel: { color: '#8B98A8', fontSize: 10 } },
      yAxis: { type: 'value', minInterval: 1, axisLabel: { color: '#8B98A8', fontSize: 10 }, splitLine: { lineStyle: { color: '#28323F' } } },
      series: [{
        type: 'bar', name: '确定通行次数', barMaxWidth: 28,
        data: daily.map((day) => day.passage_count),
        itemStyle: {
          color: (params) => {
            const status = daily[params.dataIndex]?.status
            if (status === 'no_observation') return '#3a4552'
            if (status === 'zero') return '#5b6b7d'
            return '#5AA2E8'
          },
        },
      }],
    },
  }
}

function compareSeries(): { option: ChartOption; empty: boolean } {
  const a = compareResult.value?.a.daily ?? []
  const b = compareResult.value?.b.daily ?? []
  const count = Math.max(a.length, b.length)
  const empty = count === 0
  const axis = Array.from({ length: count }, (_, index) => `第${index + 1}天`)
  return {
    empty,
    option: {
      animation: false,
      grid: { top: 24, right: 16, bottom: 24, left: 40 },
      tooltip: {
        trigger: 'axis',
        formatter: (params) => {
          const list = (Array.isArray(params) ? params : [params]) as unknown as Array<{ seriesIndex: number; dataIndex: number }>
          const index = list[0]?.dataIndex ?? 0
          const lines = [`按各自窗口第 ${index + 1} 天对齐（两期不一定同时发生）`]
          for (const point of list) {
            const day = point.seriesIndex === 0 ? a[index] : b[index]
            const label = point.seriesIndex === 0 ? 'A 期' : 'B 期'
            lines.push(day
              ? `${label} <b>${day.passage_count}</b> 次（${day.day} UTC）`
              : `${label} 无该日`)
          }
          return lines.join('<br/>')
        },
      },
      xAxis: { type: 'category', data: axis, axisLabel: { color: '#8B98A8', fontSize: 10 } },
      yAxis: { type: 'value', minInterval: 1, axisLabel: { color: '#8B98A8', fontSize: 10 }, splitLine: { lineStyle: { color: '#28323F' } } },
      series: [
        { type: 'bar', name: 'A 期', barMaxWidth: 20, itemStyle: { color: '#5AA2E8' }, data: a.map((day) => day.passage_count) },
        { type: 'bar', name: 'B 期', barMaxWidth: 20, itemStyle: { color: '#E8B14E' }, data: b.map((day) => day.passage_count) },
      ],
    },
  }
}

function renderChart() {
  if (!chartEl.value) return
  const built = mode.value === 'single' ? singleSeries() : compareSeries()
  if (!chart) chart = echarts.init(chartEl.value)
  chart.setOption(built.option, { replaceMerge: ['series', 'xAxis', 'yAxis'] })
}

watch([singleResult, compareResult, mode], async () => {
  await nextTick()
  if (chartEl.value) renderChart()
})

function resizeChart() {
  if (!chartEl.value) return
  if (!chart) { chart = echarts.init(chartEl.value); renderChart() }
  else chart.resize()
}

// ------------------------------------------------------------- 元数据
onMounted(() => {
  resizeObserver = new ResizeObserver(resizeChart)
  if (chartEl.value) resizeObserver.observe(chartEl.value)
  void fetchPassageMeta()
    .then((result) => {
      meta.value = result
      selectedTypes.value = result.ship_type_options.map((option) => option.value)
      const sevenDay = result.coverage.filter((batch) => batch.kind === 'seven_day_batch')
      if (sevenDay.length) {
        const starts = sevenDay.map((batch) => batch.coverage_start).filter((value): value is string => !!value).sort()
        const ends = sevenDay.map((batch) => batch.coverage_end).filter((value): value is string => !!value).sort()
        if (starts.length && ends.length) {
          // coverage 为含首尾时刻；首日常为部分日窗（如 02-24T16:00 起），
          // 默认窗口取首日起 7 个含首尾 UTC 日，避免超后端 7 天上限。
          const firstMs = Date.parse(starts[0]!)
          const first = new Date(firstMs).toISOString().slice(0, 10)
          const capped = new Date(firstMs + 6 * 86400_000).toISOString().slice(0, 10)
          const lastInstantDay = new Date(Date.parse(ends.at(-1)!)).toISOString().slice(0, 10)
          const last = capped < lastInstantDay ? capped : lastInstantDay
          startDate.value = first
          aStartDate.value = first
          endDate.value = last
          aEndDate.value = new Date(firstMs + 2 * 86400_000).toISOString().slice(0, 10)
          bStartDate.value = new Date(Date.parse(`${last}T00:00:00Z`) - 2 * 86400_000).toISOString().slice(0, 10)
          bEndDate.value = last
        }
      }
    })
    .catch((e) => { metaError.value = describeApiError(e, '元数据加载失败') })
})

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  resizeObserver = null
  chart?.dispose()
  chart = null
  requestController?.abort()
})

// ------------------------------------------------------------- 展示辅助
const summaryCards = computed(() => {
  const window = singleResult.value?.window
  if (!window) return []
  return [
    { label: '确定通行次数', value: window.passage_count },
    { label: '去重艘数（全窗）', value: window.unique_ship_count },
    { label: '入湾次数', value: window.inbound_count },
    { label: '出湾次数', value: window.outbound_count },
    { label: '不确定候选', value: window.uncertain_candidate_count },
  ]
})

const noObservationDays = computed(() => {
  if (singleResult.value) return singleResult.value.daily.filter((day) => day.status === 'no_observation').length
  if (compareResult.value)
    return [...compareResult.value.a.daily, ...compareResult.value.b.daily].filter((day) => day.status === 'no_observation').length
  return 0
})

const activeLimitations = computed<string[]>(() => {
  if (singleResult.value) return singleResult.value.limitations
  if (compareResult.value) return [...compareResult.value.a.limitations, ...compareResult.value.b.limitations]
    .filter((item, index, list) => list.indexOf(item) === index)
  return []
})

function formatRate(value: number | null): string {
  return value === null ? '—（A 期为 0）' : `${value > 0 ? '+' : ''}${(value * 100).toFixed(1)}%`
}

function formatFix(fix: { recorded_at: string; longitude: number; latitude: number }): string {
  return `${fix.recorded_at.slice(0, 16).replace('T', ' ')}Z · ${fix.longitude.toFixed(2)}°E ${fix.latitude.toFixed(2)}°N`
}
</script>

<template>
  <section class="passage-analysis" aria-label="通行分析">
    <div class="analysis-controls">
      <div class="mode-switch" role="group" aria-label="分析模式">
        <button :class="{ active: mode === 'single' }" :aria-pressed="mode === 'single'" @click="mode = 'single'">单时段</button>
        <button :class="{ active: mode === 'compare' }" :aria-pressed="mode === 'compare'" @click="mode = 'compare'">A/B 比较</button>
      </div>
      <div v-if="mode === 'single'" class="date-row">
        <label>开始（UTC 日）<input v-model="startDate" type="date" required /></label>
        <label>结束（含）<input v-model="endDate" type="date" required /></label>
      </div>
      <div v-else class="date-row">
        <fieldset><legend>A 段（UTC 日）</legend>
          <input v-model="aStartDate" type="date" required /><span>至</span><input v-model="aEndDate" type="date" required />
        </fieldset>
        <fieldset><legend>B 段（UTC 日）</legend>
          <input v-model="bStartDate" type="date" required /><span>至</span><input v-model="bEndDate" type="date" required />
        </fieldset>
      </div>
      <label class="direction-select">方向
        <select v-model="direction">
          <option v-for="item in DIRECTIONS" :key="item.value" :value="item.value">{{ item.label }}</option>
        </select>
      </label>
      <div class="type-select" role="group" aria-label="船型多选">
        <label class="type-all"><input v-model="allTypesSelected" type="checkbox" />全部船型</label>
        <label v-for="option in meta?.ship_type_options ?? []" :key="option.value">
          <input v-model="selectedTypes" type="checkbox" :value="option.value" />
          {{ option.label }}<small>{{ option.ship_count }}艘</small>
        </label>
        <p v-if="metaError" class="analysis-note error">{{ metaError }}</p>
      </div>
      <div class="query-row">
        <button class="primary" type="button" :disabled="loading" @click="runQuery">
          {{ loading ? '正在查询…' : '查询通行统计' }}
        </button>
        <button v-if="loading" type="button" @click="cancelQuery">取消</button>
        <span class="utc-note">日期按 UTC 自然日；结束日期当日含在区间内（后端为半开区间）</span>
      </div>
    </div>

    <p v-if="error" class="analysis-note error" role="alert">{{ error }}</p>

    <div v-if="singleResult" class="analysis-result">
      <p class="analysis-note" :class="{ error: singleResult.status === 'no_data' }">
        状态：{{ singleResult.status === 'no_data' ? '时段内无观测（不能解释为真实零通行）' : singleResult.status === 'partial' ? '含不确定候选（不计入确定量）' : '正常' }}
        · 判定版本 {{ singleResult.determination_version }}
        <template v-if="resultStamp && resultStamp.key !== currentConditionsKey()">· 条件已修改，结果对应上次查询</template>
      </p>
      <div class="summary-cards">
        <div v-for="card in summaryCards" :key="card.label" class="summary-card">
          <strong>{{ card.value }}</strong><span>{{ card.label }}</span>
        </div>
      </div>
      <p v-if="noObservationDays" class="analysis-note">其中 {{ noObservationDays }} 天无门线观测，日均与汇总不代表完整覆盖。</p>
      <div ref="chartEl" class="analysis-chart" role="img" aria-label="按日通行次数柱状图"></div>
      <p v-if="!singleResult.daily.length" class="analysis-note">该时段没有可统计的自然日。</p>
    </div>

    <div v-if="compareResult" class="analysis-result">
      <p class="analysis-note">
        A 段 {{ compareResult.a.start_at.slice(0, 10) }} 至 {{ inclusiveEndDay(compareResult.a.end_at) }}（{{ compareResult.a_period_days }} 天，
        日均 {{ compareResult.a_avg_passages_per_day.toFixed(2) }} 次）·
        B 段 {{ compareResult.b.start_at.slice(0, 10) }} 至 {{ inclusiveEndDay(compareResult.b.end_at) }}（{{ compareResult.b_period_days }} 天，
        日均 {{ compareResult.b_avg_passages_per_day.toFixed(2) }} 次）
        <template v-if="compareResult.windows_overlap">· 两期重叠，统计不独立</template>
      </p>
      <table class="compare-table">
        <thead><tr><th>指标</th><th>A 期</th><th>B 期</th><th>差值（B−A）</th><th>变化率（B−A）/A</th></tr></thead>
        <tbody>
          <tr v-for="metric in compareResult.metrics" :key="metric.metric">
            <td>{{ METRIC_LABEL[metric.metric] ?? metric.metric }}</td>
            <td>{{ metric.a_value }}</td><td>{{ metric.b_value }}</td>
            <td>{{ metric.delta > 0 ? '+' + metric.delta : metric.delta }}</td>
            <td>{{ formatRate(metric.change_rate) }}</td>
          </tr>
        </tbody>
      </table>
      <div ref="chartEl" class="analysis-chart" role="img" aria-label="两期按日通行次数对比柱状图"></div>
      <ul v-if="compareResult.comparability_notes.length" class="analysis-notes">
        <li v-for="note in compareResult.comparability_notes" :key="note">{{ note }}</li>
      </ul>
    </div>

    <div v-if="(singleResult || compareResult) && (singleResult?.window.passage_count || compareResult)" class="evidence-block">
      <div class="evidence-head">
        <h4>通行证据明细</h4>
        <label>日期
          <select v-model="evidenceDay">
            <option value="">全部日期</option>
            <option v-for="day in (singleResult ? singleResult.daily : [...compareResult!.a.daily, ...compareResult!.b.daily])"
                    :key="day.day" :value="day.day">{{ day.day }}（{{ DAY_STATUS_LABEL[day.status] }}）</option>
          </select>
        </label>
        <label><input v-model="includeUncertain" type="checkbox" />含不确定候选</label>
      </div>
      <p v-if="evidenceError" class="analysis-note error" role="alert">{{ evidenceError }}</p>
      <p v-else-if="evidence" class="analysis-note">
        确定通行 {{ evidence.confirmed_count }} 次{{ evidence.uncertain_candidate_count ? `，不确定候选 ${evidence.uncertain_candidate_count} 条（不含在本表，除非勾选）` : '' }}
        · 第 {{ evidence.page }}/{{ evidence.page_count || 1 }} 页
        <template v-if="evidence.matched_count > evidence.returned_count">
          <button type="button" :disabled="evidencePage <= 1" @click="nextEvidencePage(evidencePage - 1)">上一页</button>
          <button type="button" :disabled="evidencePage >= evidence.page_count" @click="nextEvidencePage(evidencePage + 1)">下一页</button>
        </template>
      </p>
      <table v-if="evidence?.items.length" class="evidence-table">
        <thead><tr><th>船舶</th><th>方向</th><th>起始侧报位</th><th>完成侧报位</th><th>观测完成时间</th><th>地图</th></tr></thead>
        <tbody>
          <tr v-for="item in evidence.items" :key="item.stable_key" :class="{ uncertain: item.uncertain }">
            <td>{{ item.ship_name ?? '—' }}<small>ID {{ item.ship_id }}</small></td>
            <td>{{ item.direction === 'east_to_west' ? '入湾' : '出湾' }}</td>
            <td>{{ formatFix(item.start_fix) }}</td>
            <td>{{ formatFix(item.completion_fix) }}</td>
            <td>{{ item.observed_completion_at.slice(0, 16).replace('T', ' ') }}Z</td>
            <td>
              <button type="button" :disabled="mapBusyKey === item.stable_key" @click="showEvidenceOnMap(item)">
                {{ mapBusyKey === item.stable_key ? '加载中…' : '查看轨迹' }}
              </button>
            </td>
          </tr>
        </tbody>
      </table>
      <p v-else-if="evidence" class="analysis-note">
        {{ evidence.confirmed_count === 0 && evidence.uncertain_candidate_count > 0 ? '该日只有不确定候选（勾选「含不确定候选」查看），不计入确定量。' : '该筛选条件下没有确定通行证据。' }}
      </p>
      <p v-if="mapMessage" class="analysis-note" role="status">{{ mapMessage }}</p>
    </div>

    <details v-if="singleResult || compareResult" class="limitations">
      <summary>口径与限制</summary>
      <ul>
        <li v-for="item in activeLimitations" :key="item">{{ item }}</li>
      </ul>
    </details>
  </section>
</template>

<style scoped>
.passage-analysis { display: flex; flex-direction: column; gap: 12px; }
.analysis-controls { display: flex; flex-direction: column; gap: 10px; }
.mode-switch { display: inline-flex; gap: 0; border: 1px solid var(--line); border-radius: 8px; overflow: hidden; width: fit-content; }
.mode-switch button { padding: 6px 14px; background: transparent; color: var(--ink); border: 0; cursor: pointer; font-size: 13px; }
.mode-switch button.active { background: var(--accent); color: #0d1117; }
.date-row { display: flex; flex-wrap: wrap; gap: 10px 18px; align-items: center; }
.date-row label, .direction-select { display: inline-flex; align-items: center; gap: 6px; font-size: 12px; color: #8B98A8; }
.date-row fieldset { display: inline-flex; align-items: center; gap: 6px; border: 1px solid var(--line); border-radius: 8px; padding: 6px 10px; }
.date-row legend { font-size: 11px; color: #8B98A8; padding: 0 4px; }
.passage-analysis input[type="date"], .passage-analysis select {
  background: var(--panel); color: var(--ink); border: 1px solid var(--line); border-radius: 6px; padding: 5px 8px; font-size: 12px;
}
.type-select { display: flex; flex-wrap: wrap; gap: 6px 14px; font-size: 12px; }
.type-select label { display: inline-flex; align-items: center; gap: 4px; color: var(--ink); cursor: pointer; }
.type-select small { color: #8B98A8; }
.type-all { font-weight: 600; }
.query-row { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.query-row .primary { padding: 7px 18px; border-radius: 8px; border: 0; background: var(--accent); color: #0d1117; font-weight: 600; cursor: pointer; }
.query-row .primary:disabled { opacity: 0.6; cursor: default; }
.query-row button:not(.primary) { padding: 6px 12px; border-radius: 8px; border: 1px solid var(--line); background: transparent; color: var(--ink); cursor: pointer; }
.utc-note { font-size: 11px; color: #8B98A8; }
.analysis-note { font-size: 12px; color: #8B98A8; margin: 0; }
.analysis-note.error { color: #E5A54B; }
.analysis-result { display: flex; flex-direction: column; gap: 10px; }
.summary-cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(110px, 1fr)); gap: 8px; }
.summary-card { border: 1px solid var(--line); border-radius: 8px; padding: 8px 10px; display: flex; flex-direction: column; }
.summary-card strong { font-size: 20px; color: var(--ink); }
.summary-card span { font-size: 11px; color: #8B98A8; }
.analysis-chart { width: 100%; height: 220px; }
.compare-table, .evidence-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.compare-table th, .compare-table td, .evidence-table th, .evidence-table td {
  border: 1px solid var(--line); padding: 5px 8px; text-align: left; color: var(--ink);
}
.compare-table th, .evidence-table th { background: var(--panel); color: #8B98A8; font-weight: 600; }
.evidence-table td small { display: block; color: #8B98A8; }
.evidence-table tr.uncertain td { color: #8B98A8; }
.evidence-table button, .evidence-head button {
  padding: 3px 10px; border-radius: 6px; border: 1px solid var(--line); background: transparent; color: var(--ink); cursor: pointer; font-size: 12px;
}
.evidence-block { display: flex; flex-direction: column; gap: 8px; border-top: 1px solid var(--line); padding-top: 10px; }
.evidence-head { display: flex; align-items: center; gap: 14px; flex-wrap: wrap; }
.evidence-head h4 { margin: 0; font-size: 13px; color: var(--ink); }
.evidence-head label { display: inline-flex; align-items: center; gap: 6px; font-size: 12px; color: #8B98A8; }
.analysis-notes { margin: 0; padding-left: 18px; font-size: 12px; color: #E5A54B; display: flex; flex-direction: column; gap: 4px; }
.limitations summary { cursor: pointer; font-size: 12px; color: #8B98A8; }
.limitations ul { margin: 6px 0 0; padding-left: 18px; font-size: 12px; color: #8B98A8; display: flex; flex-direction: column; gap: 4px; }
.analysis-note button { margin-left: 8px; padding: 2px 10px; border-radius: 6px; border: 1px solid var(--line); background: transparent; color: var(--ink); cursor: pointer; font-size: 12px; }
@media (max-width: 640px) {
  .summary-cards { grid-template-columns: repeat(2, 1fr); }
  .evidence-table { font-size: 11px; }
  .evidence-table th, .evidence-table td { padding: 4px 5px; }
}
</style>
