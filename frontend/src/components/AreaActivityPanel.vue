<script setup lang="ts">
// 区域船舶活动面板（issue #41 阶段二-A）：三模式（时刻在场/时段活动/两时段比较）。
// 展示层只做两件事：调用 api.ts 的 area 函数取后端结果 + 按后端字段渲染。
// 不在前端重算在场/进入/离开/时长，不自己拼 URL，不硬编码船型列表。
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts/core'
import { LineChart } from 'echarts/charts'
import { GridComponent, LegendComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import type { ComposeOption } from 'echarts/core'
import type { LineSeriesOption } from 'echarts/charts'
import type { GridComponentOption, LegendComponentOption, TooltipComponentOption } from 'echarts/components'
import {
  describeApiError,
  fetchAreaActivity,
  fetchAreaCompare,
  fetchAreaShipTypes,
  fetchAreaSnapshot,
  type ApiAreaBounds,
} from '../api'
import {
  AREA_PANEL_MODES,
  activityTruncationNote,
  allShipTypesSelected,
  areaQueryText,
  boundsEqual,
  boundsText,
  changeRateText,
  dailySeries,
  dash,
  defaultActivityWindow,
  defaultCompareWindows,
  emptyResultText,
  eventFlagLabels,
  flagLabel,
  formatAge,
  formatCount,
  formatDecimal,
  formatHours,
  formatPosition,
  formatSeconds,
  formatSigned,
  formatSpan,
  formatSpeed,
  formatUtc,
  hasChangeRate,
  isEmptyResult,
  isNoData,
  priorStateLabel,
  readActivitySummary,
  readAlgorithm,
  readAreaHint,
  readAreaInfo,
  readComparability,
  readCoverage,
  readSnapshotSummary,
  shipTypeQueryValues,
  shipTypeSelectionText,
  snapshotTruncationNote,
  statusDescription,
  statusLabel,
  statusTone,
  toAreaActivityResult,
  toAreaCompareResult,
  toAreaShipTypesResult,
  toAreaSnapshotResult,
  utcInputToIso,
  utcInputValue,
  utcRangeText,
  visitDetailId,
  visitFocusArgs,
  visitLocateArgs,
  visitStatusLabel,
  windowOrderError,
  type AreaActivityResult,
  type AreaAlgorithm,
  type AreaBounds,
  type AreaCompareResult,
  type AreaConditionHint,
  type AreaCoverage,
  type AreaFix,
  type AreaInfo,
  type AreaLimits,
  type AreaPanelMode,
  type AreaQueryDraft,
  type AreaShipTypeOption,
  type AreaSnapshotResult,
} from '../domain/areaActivity'

// pendingAction 为不可信外部输入（unknown），只在 readAreaHint 里做运行时收窄。
const props = defineProps<{
  open: boolean
  bounds: ApiAreaBounds
  defaultBounds: ApiAreaBounds
  areaLabel: string
  areaIsDefault: boolean
  agentContext?: { shipTypes?: string[] | null; at?: string | null; start?: string | null; end?: string | null } | null
  pendingAction?: unknown | null
}>()

type AreaDialogPayload = AreaQueryDraft & { text: string }

const emit = defineEmits<{
  close: []
  'update:bounds': []
  // 成功得到一组新结果时 emit 一次（失败/取消不发）：父组件据此推进「结果版本」。
  'results-updated': []
  'locate-ship': [payload: { shipId: number; startAt: string; endAt: string }]
  'focus-visit': [payload: { shipId: number; startAt: string; endAt: string; visitKey: string }]
  'use-area-in-dialog': [payload: AreaDialogPayload]
}>()

echarts.use([LineChart, GridComponent, LegendComponent, TooltipComponent, CanvasRenderer])

// —— 表单状态 ——
const mode = ref<AreaPanelMode>('snapshot')
const snapshotAt = ref(utcInputValue(new Date()))
const activityStart = ref(defaultActivityWindow().start)
const activityEnd = ref(defaultActivityWindow().end)
const compareWindows = ref(defaultCompareWindows())
const freshnessSeconds = ref('')
const visitLimit = ref('')

// —— 船型筛选（默认全选；来源为后端 ship-types 接口，不在前端硬编码） ——
const shipTypeOptions = ref<AreaShipTypeOption[]>([])
const shipTypeSource = ref<string | null>(null)
const shipTypeTotal = ref<number | null>(null)
const shipTypeLimitations = ref<string[]>([])
const shipTypeError = ref('')
const shipTypesLoading = ref(false)
const selectedShipTypes = ref<string[]>([])
const shipTypeHintIgnored = ref(false)

const allShipTypeValues = computed(() => shipTypeOptions.value.map(option => option.value))
const allShipTypesChecked = computed(() => allShipTypesSelected(selectedShipTypes.value, allShipTypeValues.value))
const shipTypeFilter = computed(() => shipTypeQueryValues(selectedShipTypes.value, allShipTypeValues.value))
const shipTypeText = computed(() => shipTypeSelectionText(selectedShipTypes.value, shipTypeOptions.value))
// 后端语义：空船型 = 全部。因此「清空」后必须显式提示并阻止提交，避免静默变成全选。
const shipTypeFilterReady = computed(() => shipTypeOptions.value.length === 0 || selectedShipTypes.value.length > 0)
const shipTypeStatusText = computed(() => {
  if (shipTypesLoading.value) return '加载中…'
  if (shipTypeError.value) return '加载失败'
  if (!shipTypeOptions.value.length) return '未加载'
  return `共 ${shipTypeOptions.value.length} 项`
})

// —— 结果状态 ——
const loading = ref(false)
const error = ref('')
const notice = ref('')
const snapshotResult = ref<AreaSnapshotResult | null>(null)
const activityResult = ref<AreaActivityResult | null>(null)
const compareResult = ref<AreaCompareResult | null>(null)

interface ResultContext {
  bounds: AreaBounds
  label: string
  conditions: string
  at: string
}

const resultContexts = ref<Record<AreaPanelMode, ResultContext | null>>({ snapshot: null, activity: null, compare: null })
const currentContext = computed(() => resultContexts.value[mode.value])
const staleText = computed(() => {
  const context = currentContext.value
  if (!context || boundsEqual(context.bounds, props.bounds)) return ''
  return `区域已变更，待查询：以下结果属于 ${context.label}（${boundsText(context.bounds)}）。`
})
const resultContextText = computed(() => {
  const context = currentContext.value
  if (!context) return ''
  return `结果所属区域：${context.label}（${boundsText(context.bounds)}）；条件：${context.conditions}。`
})
const expandedVisits = ref<Record<string, boolean>>({})
const queuedHint = ref<AreaConditionHint | null>(null)

// 空值视图对象：让模板始终有确定类型，是否渲染由 hasXxx 控制。
const snapshotView = computed<AreaSnapshotResult>(() => snapshotResult.value ?? {
  status: '',
  area: readAreaInfo(null),
  algorithm: readAlgorithm(null),
  coverage: readCoverage(null),
  summary: readSnapshotSummary(null),
  ships: [],
  limits: {},
  limitations: [],
  query: null,
})
const activityView = computed<AreaActivityResult>(() => activityResult.value ?? {
  status: '',
  area: readAreaInfo(null),
  algorithm: readAlgorithm(null),
  coverage: readCoverage(null),
  summary: readActivitySummary(null),
  daily: [],
  visits: [],
  limits: {},
  limitations: [],
  query: null,
})
const compareView = computed<AreaCompareResult>(() => compareResult.value ?? {
  status: '',
  area: readAreaInfo(null),
  algorithm: readAlgorithm(null),
  windows: { a: { start: null, end: null, days: null, length_hours: null, length_days: null }, b: { start: null, end: null, days: null, length_hours: null, length_days: null } },
  metrics: [],
  comparability: readComparability(null),
  a: { status: '', summary: readActivitySummary(null), coverage: readCoverage(null), daily: [] },
  b: { status: '', summary: readActivitySummary(null), coverage: readCoverage(null), daily: [] },
  limitations: [],
})

const hasSnapshot = computed(() => snapshotResult.value !== null)
const hasActivity = computed(() => activityResult.value !== null)
const hasCompare = computed(() => compareResult.value !== null)
const hasResult = computed(() => {
  if (mode.value === 'snapshot') return hasSnapshot.value
  if (mode.value === 'activity') return hasActivity.value
  return hasCompare.value
})

interface ResultMeta {
  status: string
  area: AreaInfo
  algorithm: AreaAlgorithm
  coverage: AreaCoverage | null
  limits: AreaLimits
  limitations: string[]
}

const resultMeta = computed<ResultMeta>(() => {
  if (mode.value === 'snapshot') {
    const result = snapshotView.value
    return { status: result.status, area: result.area, algorithm: result.algorithm, coverage: result.coverage, limits: result.limits, limitations: result.limitations }
  }
  if (mode.value === 'activity') {
    const result = activityView.value
    return { status: result.status, area: result.area, algorithm: result.algorithm, coverage: result.coverage, limits: result.limits, limitations: result.limitations }
  }
  const result = compareView.value
  return { status: result.status, area: result.area, algorithm: result.algorithm, coverage: null, limits: {}, limitations: result.limitations }
})

const coverageSummaryText = computed(() => {
  const coverage = resultMeta.value.coverage
  if (!coverage) return ''
  const batches = coverage.batch_ids.length ? coverage.batch_ids.join('、') : '—'
  const days = coverage.batch_days.length ? `（${coverage.batch_days.join('、')}）` : ''
  const parts = [
    `来源 ${dash(coverage.source)}`,
    `批次 ${batches}${days}`,
    `扫描报位 ${formatCount(coverage.scoped_fix_count)}`,
    `区域内报位 ${formatCount(coverage.region_fix_count)}`,
  ]
  if (coverage.window_region_fix_count !== null) parts.push(`窗口内区域内报位 ${formatCount(coverage.window_region_fix_count)}`)
  return parts.join('；')
})
const coverageWindowText = computed(() => {
  const coverage = resultMeta.value.coverage
  if (!coverage || (!coverage.scope_start && !coverage.scope_end)) return ''
  return `${formatUtc(coverage.scope_start)} → ${formatUtc(coverage.scope_end)}（UTC）`
})
const coverageNoteText = computed(() => resultMeta.value.coverage?.note ?? '')
const areaBasisText = computed(() => resultMeta.value.area.basis ?? '')

// compare 的 coverage 在 a/b 两期各自返回，不聚合到顶层。
function periodCoverageText(coverage: AreaCoverage): string {
  const batches = coverage.batch_ids.length ? coverage.batch_ids.join('、') : '—'
  const parts = [
    `来源 ${dash(coverage.source)}`,
    `批次 ${batches}`,
    `扫描报位 ${formatCount(coverage.scoped_fix_count)}`,
    `区域内报位 ${formatCount(coverage.region_fix_count)}`,
  ]
  if (coverage.scope_start || coverage.scope_end) parts.push(`覆盖时间 ${formatUtc(coverage.scope_start)} → ${formatUtc(coverage.scope_end)}（UTC）`)
  return parts.join('；')
}

const snapshotTruncation = computed(() => snapshotTruncationNote(snapshotView.value.limits))
const activityTruncation = computed(() => activityTruncationNote(activityView.value.limits))

// 每日统计块：activity 一组，compare 分 A/B 两组。
const dailyTables = computed(() => {
  if (mode.value === 'activity' && hasActivity.value) {
    return [{ key: 'activity', label: '全窗每日统计', rows: activityView.value.daily, status: activityView.value.status }]
  }
  if (mode.value === 'compare' && hasCompare.value) {
    return [
      { key: 'a', label: 'A 期每日统计', rows: compareView.value.a.daily, status: compareView.value.a.status },
      { key: 'b', label: 'B 期每日统计', rows: compareView.value.b.daily, status: compareView.value.b.status },
    ]
  }
  return []
})
const chartVisible = computed(() => mode.value === 'activity' && hasActivity.value && activityView.value.daily.length > 0)
const chartLabel = computed(() => {
  const count = activityView.value.daily.length
  return count ? `每日活动趋势图：共 ${count} 个 UTC 自然日的去重船数、观测进入与观测离开` : '每日活动趋势图（暂无数据）'
})

const statusLine = computed(() => {
  if (loading.value) return '查询中…（可取消）'
  if (error.value) return '查询失败，见下方错误信息'
  if (mode.value === 'snapshot') return hasSnapshot.value ? `时刻在场结果：${statusLabel(snapshotView.value.status)}` : '尚未查询'
  if (mode.value === 'activity') return hasActivity.value ? `时段活动结果：${statusLabel(activityView.value.status)}` : '尚未查询'
  return hasCompare.value ? `两时段比较结果：${statusLabel(compareView.value.status)}` : '尚未查询'
})
const currentModeHint = computed(() => AREA_PANEL_MODES.find(item => item.value === mode.value)?.hint ?? '')

// —— 请求版本守卫 + AbortController：切模式、改条件、连续查询、区域变更都会作废旧响应 ——
let requestSeq = 0
let controller: AbortController | null = null

function abortInFlight() {
  if (controller) {
    controller.abort()
    controller = null
  }
  requestSeq += 1
  loading.value = false
}

function isAbortError(value: unknown): boolean {
  return typeof value === 'object' && value !== null && 'name' in value && (value as { name?: unknown }).name === 'AbortError'
}

function setMode(next: AreaPanelMode) {
  if (next === mode.value) return
  mode.value = next
  abortInFlight()
  error.value = ''
  notice.value = ''
  expandedVisits.value = {}
}

watch(() => props.bounds, () => {
  // 区域变了：作废在途请求，旧结果由 staleText 标记为「区域已变更，待查询」。
  abortInFlight()
  notice.value = ''
})

// —— 查询计划 ——
type QueryPlan =
  | { ok: false; message: string }
  | { ok: true; conditions: string; execute: (signal: AbortSignal) => Promise<unknown> }

function parseOptionalInt(text: string): { value: number | null; error: string | null } {
  const trimmed = text.trim()
  if (!trimmed) return { value: null, error: null }
  if (!/^\d+$/.test(trimmed)) return { value: null, error: '请输入正整数或留空' }
  const value = Number(trimmed)
  if (!Number.isFinite(value) || value < 1) return { value: null, error: '请输入不小于 1 的整数或留空' }
  return { value, error: null }
}

function planQuery(): QueryPlan {
  if (!shipTypeFilterReady.value) return { ok: false, message: '请至少选择一个船型再查询（后端把空船型解释为全部，清空后请点「全选」）。' }
  const shipTypes = shipTypeFilter.value
  // 默认区域传 null（后端按默认区返回 area_id=hormuz_core_v1/is_default=true）；
  // 只有自选矩形才传四个边界，否则后端按契约回显 area_id=custom，丢掉默认区身份。
  const bounds = props.areaIsDefault ? null : { ...props.bounds }
  if (mode.value === 'snapshot') {
    const at = utcInputToIso(snapshotAt.value)
    if (!at) return { ok: false, message: '请填写有效的时刻（UTC，格式 YYYY-MM-DDTHH:mm）。' }
    const freshness = parseOptionalInt(freshnessSeconds.value)
    if (freshness.error) return { ok: false, message: `新鲜度阈值：${freshness.error}` }
    return {
      ok: true,
      conditions: `时刻 ${formatUtc(at)} UTC；新鲜度阈值 ${freshness.value === null ? '后端默认' : `${freshness.value} 秒`}；船型 ${shipTypeText.value}`,
      execute: signal => fetchAreaSnapshot({
        at,
        bounds,
        ship_types: shipTypes,
        ...(freshness.value === null ? {} : { freshness_seconds: freshness.value }),
      }, signal),
    }
  }
  const visitLimitValue = parseOptionalInt(visitLimit.value)
  if (visitLimitValue.error) return { ok: false, message: `明细上限：${visitLimitValue.error}` }
  if (mode.value === 'activity') {
    const start = utcInputToIso(activityStart.value)
    const end = utcInputToIso(activityEnd.value)
    const orderError = windowOrderError(start, end)
    if (orderError) return { ok: false, message: orderError }
    return {
      ok: true,
      conditions: `窗口 ${utcRangeText(start, end)}；船型 ${shipTypeText.value}${visitLimitValue.value === null ? '' : `；visit_limit=${visitLimitValue.value}`}`,
      execute: signal => fetchAreaActivity({
        start: start as string,
        end: end as string,
        bounds,
        ship_types: shipTypes,
        ...(visitLimitValue.value === null ? {} : { visit_limit: visitLimitValue.value }),
      }, signal),
    }
  }
  const startA = utcInputToIso(compareWindows.value.startA)
  const endA = utcInputToIso(compareWindows.value.endA)
  const startB = utcInputToIso(compareWindows.value.startB)
  const endB = utcInputToIso(compareWindows.value.endB)
  const errorA = windowOrderError(startA, endA)
  if (errorA) return { ok: false, message: `A 期：${errorA}` }
  const errorB = windowOrderError(startB, endB)
  if (errorB) return { ok: false, message: `B 期：${errorB}` }
  return {
    ok: true,
    conditions: `A ${utcRangeText(startA, endA)}；B ${utcRangeText(startB, endB)}；船型 ${shipTypeText.value}${visitLimitValue.value === null ? '' : `；visit_limit=${visitLimitValue.value}`}`,
    execute: signal => fetchAreaCompare({
      start_a: startA as string,
      end_a: endA as string,
      start_b: startB as string,
      end_b: endB as string,
      bounds,
      ship_types: shipTypes,
      ...(visitLimitValue.value === null ? {} : { visit_limit: visitLimitValue.value }),
    }, signal),
  }
}

async function runQuery() {
  const plan = planQuery()
  if (!plan.ok) {
    error.value = plan.message
    notice.value = ''
    return
  }
  if (controller) controller.abort()
  controller = new AbortController()
  requestSeq += 1
  const seq = requestSeq
  const queryMode = mode.value
  loading.value = true
  error.value = ''
  notice.value = ''
  try {
    const payload = await plan.execute(controller.signal)
    if (seq !== requestSeq) return
    if (queryMode === 'snapshot') {
      snapshotResult.value = toAreaSnapshotResult(payload)
      activityResult.value = null
      compareResult.value = null
    } else if (queryMode === 'activity') {
      activityResult.value = toAreaActivityResult(payload)
      snapshotResult.value = null
      compareResult.value = null
    } else {
      compareResult.value = toAreaCompareResult(payload)
      snapshotResult.value = null
      activityResult.value = null
    }
    expandedVisits.value = {}
    resultContexts.value[queryMode] = {
      bounds: { ...props.bounds },
      label: props.areaLabel,
      conditions: plan.conditions,
      at: new Date().toISOString(),
    }
    // 只在成功写入新结果时通知父组件推进「结果版本」；失败与取消不发。
    emit('results-updated')
  } catch (cause) {
    if (seq !== requestSeq) return
    if (isAbortError(cause)) {
      notice.value = '查询已取消。'
      return
    }
    error.value = describeApiError(cause, '区域分析请求失败')
  } finally {
    if (seq === requestSeq) loading.value = false
  }
}

function cancelQuery() {
  if (!loading.value) return
  abortInFlight()
  notice.value = '查询已取消。'
}

// —— 船型列表 ——
function applyShipTypeSelection(hint: string[] | null | undefined) {
  const values = allShipTypeValues.value
  if (!values.length) {
    selectedShipTypes.value = []
    shipTypeHintIgnored.value = false
    return
  }
  if (hint && hint.length) {
    const matched = values.filter(value => hint.includes(value))
    shipTypeHintIgnored.value = matched.length === 0
    selectedShipTypes.value = matched.length ? matched : [...values]
    return
  }
  shipTypeHintIgnored.value = false
  selectedShipTypes.value = [...values]
}

async function loadShipTypes(hint: string[] | null) {
  if (shipTypesLoading.value) return
  shipTypesLoading.value = true
  shipTypeError.value = ''
  try {
    const payload = await fetchAreaShipTypes()
    const data = toAreaShipTypesResult(payload)
    shipTypeOptions.value = data.options
    shipTypeSource.value = data.source
    shipTypeTotal.value = data.total_ships
    shipTypeLimitations.value = data.limitations
    applyShipTypeSelection(hint)
  } catch (cause) {
    shipTypeError.value = describeApiError(cause, '船型列表加载失败')
    // 列表不可用时不做前端兜底枚举：按「全部船型」提交并如实提示。
    shipTypeOptions.value = []
    selectedShipTypes.value = []
  } finally {
    shipTypesLoading.value = false
  }
}

function selectAllShipTypes() {
  selectedShipTypes.value = [...allShipTypeValues.value]
  shipTypeHintIgnored.value = false
}

function clearShipTypes() {
  selectedShipTypes.value = []
}

function toggleShipType(value: string) {
  if (selectedShipTypes.value.includes(value)) selectedShipTypes.value = selectedShipTypes.value.filter(item => item !== value)
  else selectedShipTypes.value = [...selectedShipTypes.value, value]
}

// —— 上下文（对话）联动 ——
function applyHint(hint: AreaConditionHint, autoQuery: boolean) {
  if (hint.mode) setMode(hint.mode)
  else if (hint.startA || hint.endA || hint.startB || hint.endB) setMode('compare')
  else if (hint.start || hint.end) setMode('activity')
  else if (hint.at) setMode('snapshot')
  if (hint.at) snapshotAt.value = utcInputValue(hint.at) || snapshotAt.value
  if (hint.start) activityStart.value = utcInputValue(hint.start) || activityStart.value
  if (hint.end) activityEnd.value = utcInputValue(hint.end) || activityEnd.value
  if (hint.startA) compareWindows.value.startA = utcInputValue(hint.startA) || compareWindows.value.startA
  if (hint.endA) compareWindows.value.endA = utcInputValue(hint.endA) || compareWindows.value.endA
  if (hint.startB) compareWindows.value.startB = utcInputValue(hint.startB) || compareWindows.value.startB
  if (hint.endB) compareWindows.value.endB = utcInputValue(hint.endB) || compareWindows.value.endB
  if (hint.shipTypes) applyShipTypeSelection(hint.shipTypes)
  if (autoQuery) void runQuery()
  else notice.value = '已按对话上下文预填条件，确认后点击「查询」。'
}

async function applyHintWithQuery(hint: AreaConditionHint) {
  if (!shipTypeOptions.value.length && !shipTypesLoading.value) {
    await loadShipTypes(hint.shipTypes)
    applyHint(hint, true)
    return
  }
  applyHint(hint, true)
}

function bootstrapOnOpen() {
  const pending = readAreaHint(props.pendingAction) ?? queuedHint.value
  if (pending) {
    queuedHint.value = null
    void applyHintWithQuery(pending)
    return
  }
  const context = readAreaHint(props.agentContext)
  if (!shipTypeOptions.value.length && !shipTypesLoading.value) void loadShipTypes(context?.shipTypes ?? null)
  if (context) applyHint(context, false)
}

watch(() => props.open, (open, wasOpen) => {
  if (open && !wasOpen) bootstrapOnOpen()
  if (!open) abortInFlight()
  // immediate：面板 v-if 首次挂载时 open 已为 true，变化监听不会触发，首帧 bootstrap 会丢失。
}, { immediate: true })

watch(() => props.pendingAction, value => {
  const hint = readAreaHint(value)
  if (!hint) return
  if (!props.open) {
    queuedHint.value = hint
    return
  }
  void applyHintWithQuery(hint)
}, { deep: true })

// —— 访问明细展开 ——
function toggleVisit(visitKey: string) {
  expandedVisits.value[visitKey] = !expandedVisits.value[visitKey]
}

function fixText(fix: AreaFix | null | undefined): string {
  if (!fix) return '—'
  const id = fix.id === null || fix.id === undefined ? '—' : `#${fix.id}`
  return `${id} · ${formatUtc(fix.recorded_at)} UTC · ${formatPosition(fix.latitude, fix.longitude)}`
}

function bracketText(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || !Number.isFinite(seconds)) return '—'
  return `${formatSeconds(seconds)}（外侧相邻报位 → 区内首/末点）`
}

function eventWindowText(inWindow: boolean): string {
  return inWindow ? '事件时间落在本窗口内，计入汇总' : '事件时间不在本窗口内，不计入汇总'
}

// —— 写入对话 ——
function useAreaInDialog() {
  const draft: AreaQueryDraft = {
    mode: mode.value,
    bounds: { ...props.bounds },
    areaLabel: props.areaLabel,
    areaIsDefault: props.areaIsDefault,
    shipTypes: shipTypeFilter.value,
    at: mode.value === 'snapshot' ? utcInputToIso(snapshotAt.value) : null,
    start: mode.value === 'activity' ? utcInputToIso(activityStart.value) : null,
    end: mode.value === 'activity' ? utcInputToIso(activityEnd.value) : null,
    startA: mode.value === 'compare' ? utcInputToIso(compareWindows.value.startA) : null,
    endA: mode.value === 'compare' ? utcInputToIso(compareWindows.value.endA) : null,
    startB: mode.value === 'compare' ? utcInputToIso(compareWindows.value.startB) : null,
    endB: mode.value === 'compare' ? utcInputToIso(compareWindows.value.endB) : null,
  }
  emit('use-area-in-dialog', { ...draft, text: areaQueryText(draft) })
  notice.value = '已把当前区域与条件写入对话输入框。'
}

// —— ECharts 每日趋势（按需引入，尊重 prefers-reduced-motion，窄屏减少刻度） ——
type AreaChartOption = ComposeOption<LineSeriesOption | GridComponentOption | LegendComponentOption | TooltipComponentOption>

const chartEl = ref<HTMLElement | null>(null)
let chart: ReturnType<typeof echarts.init> | null = null
let chartObserver: ResizeObserver | null = null
const narrow = ref(false)
const motionQuery = window.matchMedia('(prefers-reduced-motion: reduce)')
const narrowQuery = window.matchMedia('(max-width: 640px)')
const motionAllowed = ref(!motionQuery.matches)

function onMotionChange() {
  motionAllowed.value = !motionQuery.matches
}
function onNarrowChange() {
  narrow.value = narrowQuery.matches
}

function disposeChart() {
  chartObserver?.disconnect()
  chartObserver = null
  chart?.dispose()
  chart = null
}

function renderDailyChart() {
  const series = dailySeries(activityView.value.daily)
  if (!chartEl.value || !series.dates.length) {
    chart?.clear()
    return
  }
  if (!chart) {
    chart = echarts.init(chartEl.value)
    chartObserver = new ResizeObserver(() => chart?.resize())
    chartObserver.observe(chartEl.value)
  }
  chart.setOption(buildDailyOption(series), true)
}

function buildDailyOption(series: ReturnType<typeof dailySeries>): AreaChartOption {
  // 窄屏减少横轴刻度（约 4 个），宽屏显示全部日期。
  const interval = narrow.value ? Math.max(0, Math.ceil(series.dates.length / 4) - 1) : 0
  return {
    animation: motionAllowed.value,
    animationDuration: motionAllowed.value ? 500 : 0,
    grid: { top: 30, right: 14, bottom: 24, left: 44 },
    legend: { top: 0, textStyle: { color: '#8B98A8', fontSize: 10 }, itemWidth: 12, itemHeight: 8 },
    tooltip: { trigger: 'axis', confine: true },
    xAxis: {
      type: 'category',
      data: series.dates.map(date => date.slice(5)),
      axisLabel: { color: '#8B98A8', fontSize: 10, interval, hideOverlap: true },
      axisLine: { lineStyle: { color: '#28323F' } },
      axisTick: { show: false },
    },
    yAxis: {
      type: 'value',
      minInterval: 1,
      axisLabel: { color: '#8B98A8', fontSize: 10 },
      splitLine: { lineStyle: { color: '#28323F' } },
    },
    series: [
      { name: '去重船数', type: 'line', data: series.shipsObserved, symbolSize: 5, lineStyle: { width: 2, color: '#3B9EFF' }, itemStyle: { color: '#3B9EFF' } },
      { name: '观测进入', type: 'line', data: series.entries, symbolSize: 4, lineStyle: { width: 1.5, color: '#3FB950' }, itemStyle: { color: '#3FB950' } },
      { name: '观测离开', type: 'line', data: series.exits, symbolSize: 4, lineStyle: { width: 1.5, color: '#D29922' }, itemStyle: { color: '#D29922' } },
    ],
  }
}

watch(chartEl, (element, previous) => {
  if (previous && !element) disposeChart()
  if (element) void nextTick().then(renderDailyChart)
})
watch([() => activityResult.value, narrow, motionAllowed], () => { void nextTick().then(renderDailyChart) })

onMounted(() => {
  motionQuery.addEventListener('change', onMotionChange)
  narrowQuery.addEventListener('change', onNarrowChange)
  onNarrowChange()
  if (props.open) bootstrapOnOpen()
})

onBeforeUnmount(() => {
  abortInFlight()
  motionQuery.removeEventListener('change', onMotionChange)
  narrowQuery.removeEventListener('change', onNarrowChange)
  disposeChart()
})
</script>

<template>
  <aside v-if="open" class="aa-panel" aria-label="区域船舶活动分析">
    <header class="aa-head">
      <h2>区域活动分析</h2>
      <span class="aa-head-note">UTC · 判定与汇总由后端算法给出</span>
      <button type="button" class="aa-icon-btn" aria-label="关闭区域活动分析" @click="emit('close')">✕</button>
    </header>

    <div class="aa-scroll" :aria-busy="loading">
      <!-- 分析区域 -->
      <section class="aa-section" aria-labelledby="aa-area-heading">
        <div class="aa-section-head">
          <h3 id="aa-area-heading">分析区域</h3>
          <span class="aa-chip" :class="props.areaIsDefault ? 'aa-chip-ok' : 'aa-chip-warn'">{{ props.areaIsDefault ? '默认区域' : '自定义矩形' }}</span>
        </div>
        <p class="aa-area-name">{{ dash(props.areaLabel) }}</p>
        <p class="aa-mono aa-muted">{{ boundsText(props.bounds) }}</p>
        <p class="aa-muted">包含规则（半开矩形）：west ≤ 经度 &lt; east，south ≤ 纬度 &lt; north；区域不是官方航道边界。</p>
        <div class="aa-row">
          <button type="button" class="aa-btn" @click="emit('update:bounds')">重新圈选</button>
          <span class="aa-muted">圈选后由主界面更新区域；旧结果会标记「区域已变更，待查询」。</span>
        </div>
      </section>

      <!-- 分析模式 -->
      <section class="aa-section" aria-labelledby="aa-mode-heading">
        <h3 id="aa-mode-heading">分析模式</h3>
        <div class="aa-modes" role="group" aria-label="分析模式">
          <button
            v-for="item in AREA_PANEL_MODES"
            :key="item.value"
            type="button"
            class="aa-mode"
            :class="{ active: mode === item.value }"
            :aria-pressed="mode === item.value"
            :title="item.hint"
            @click="setMode(item.value)"
          >{{ item.label }}</button>
        </div>
        <p class="aa-muted">{{ currentModeHint }}</p>
      </section>

      <!-- 船型筛选 -->
      <section class="aa-section" aria-labelledby="aa-ship-type-heading">
        <div class="aa-section-head">
          <h3 id="aa-ship-type-heading">船型筛选</h3>
          <span class="aa-muted">{{ shipTypeStatusText }}</span>
        </div>
        <div class="aa-row">
          <button type="button" class="aa-btn aa-btn-s" :aria-pressed="allShipTypesChecked" :disabled="!shipTypeOptions.length" @click="selectAllShipTypes">全选</button>
          <button type="button" class="aa-btn aa-btn-s" :disabled="!shipTypeOptions.length" @click="clearShipTypes">清空</button>
          <span class="aa-muted">当前：{{ shipTypeText }}</span>
        </div>
        <p v-if="shipTypeError" class="aa-warn" role="status">{{ shipTypeError }}。本次查询按「全部船型」提交。</p>
        <p v-else-if="!shipTypeOptions.length && !shipTypesLoading" class="aa-muted">船型列表为空（或未加载），本次查询按「全部船型」提交。</p>
        <ul v-if="shipTypeOptions.length" class="aa-checks">
          <li v-for="(option, index) in shipTypeOptions" :key="option.value">
            <label :for="`aa-ship-type-${index}`">
              <input
                :id="`aa-ship-type-${index}`"
                type="checkbox"
                :value="option.value"
                :checked="selectedShipTypes.includes(option.value)"
                @change="toggleShipType(option.value)"
              >
              <span>{{ option.label }}</span>
            </label>
            <small v-if="option.count !== null" :title="option.count_scope ?? ''">{{ formatCount(option.count) }} 艘</small>
          </li>
        </ul>
        <p v-if="shipTypeHintIgnored" class="aa-warn" role="status">对话上下文给出的船型不在当前列表中，已回退为全选。</p>
        <p v-if="shipTypeSource || shipTypeTotal !== null" class="aa-muted">列表来源：{{ dash(shipTypeSource) }}；船舶总数 {{ formatCount(shipTypeTotal) }}。计数口径见各船型标注，保留值（缺失/未知）来自后端 reserved。</p>
        <ul v-if="shipTypeLimitations.length" class="aa-limits">
          <li v-for="(item, index) in shipTypeLimitations" :key="index">{{ item }}</li>
        </ul>
      </section>

      <!-- 查询条件 -->
      <form class="aa-section" aria-labelledby="aa-cond-heading" @submit.prevent="runQuery">
        <h3 id="aa-cond-heading">查询条件</h3>
        <p class="aa-muted">时间一律按 UTC 输入与显示，界面不做本地时区换算。</p>

        <template v-if="mode === 'snapshot'">
          <div class="aa-field">
            <label for="aa-snapshot-at">时刻（UTC）</label>
            <input id="aa-snapshot-at" v-model="snapshotAt" type="datetime-local" step="60">
          </div>
          <p class="aa-muted">取该时刻之前每艘船的最新报位；龄期超过新鲜度阈值的报位记为过期，不计入在场，也不回退到更早的区内报位。</p>
          <details class="aa-advanced">
            <summary>高级参数（可选）</summary>
            <div class="aa-field">
              <label for="aa-freshness">新鲜度阈值（秒，1–86400）</label>
              <input id="aa-freshness" v-model="freshnessSeconds" type="number" min="1" max="86400" inputmode="numeric" placeholder="留空用后端默认 3600">
            </div>
          </details>
        </template>

        <template v-else-if="mode === 'activity'">
          <div class="aa-field">
            <label for="aa-activity-start">开始时刻（UTC，含）</label>
            <input id="aa-activity-start" v-model="activityStart" type="datetime-local" step="60">
          </div>
          <div class="aa-field">
            <label for="aa-activity-end">结束时刻（UTC，不含）</label>
            <input id="aa-activity-end" v-model="activityEnd" type="datetime-local" step="60">
          </div>
          <p class="aa-muted">半开区间 [start, end)：结束时刻本身不计入；单窗最长 7 天（后端校验）。默认按 UTC 自然日。</p>
          <details class="aa-advanced">
            <summary>高级参数（可选）</summary>
            <div class="aa-field">
              <label for="aa-visit-limit">访问明细上限 visit_limit（1–2000）</label>
              <input id="aa-visit-limit" v-model="visitLimit" type="number" min="1" max="2000" inputmode="numeric" placeholder="留空用后端默认 500">
            </div>
          </details>
        </template>

        <template v-else>
          <div class="aa-field">
            <label for="aa-compare-start-a">A 期开始（UTC，含）</label>
            <input id="aa-compare-start-a" v-model="compareWindows.startA" type="datetime-local" step="60">
          </div>
          <div class="aa-field">
            <label for="aa-compare-end-a">A 期结束（UTC，不含）</label>
            <input id="aa-compare-end-a" v-model="compareWindows.endA" type="datetime-local" step="60">
          </div>
          <div class="aa-field">
            <label for="aa-compare-start-b">B 期开始（UTC，含）</label>
            <input id="aa-compare-start-b" v-model="compareWindows.startB" type="datetime-local" step="60">
          </div>
          <div class="aa-field">
            <label for="aa-compare-end-b">B 期结束（UTC，不含）</label>
            <input id="aa-compare-end-b" v-model="compareWindows.endB" type="datetime-local" step="60">
          </div>
          <p class="aa-muted">两期使用同一区域、同一船型筛选与同一算法版本，允许不等长；比较模式不返回访问明细。</p>
          <details class="aa-advanced">
            <summary>高级参数（可选）</summary>
            <div class="aa-field">
              <label for="aa-compare-visit-limit">访问明细上限 visit_limit（1–2000）</label>
              <input id="aa-compare-visit-limit" v-model="visitLimit" type="number" min="1" max="2000" inputmode="numeric" placeholder="留空用后端默认 500">
            </div>
          </details>
        </template>

        <div class="aa-row aa-row-end">
          <button type="button" class="aa-btn" @click="useAreaInDialog">写入对话</button>
          <button type="submit" class="aa-btn aa-btn-primary" :disabled="loading || !shipTypeFilterReady">查询</button>
          <button v-if="loading" type="button" class="aa-btn" @click="cancelQuery">取消</button>
        </div>
        <p v-if="!shipTypeFilterReady" class="aa-warn" role="status">已清空船型：后端把「空船型」解释为全部，请先勾选船型或点「全选」再查询。</p>
      </form>

      <!-- 状态 -->
      <p class="aa-status" role="status" aria-live="polite">{{ statusLine }}</p>
      <p v-if="notice" class="aa-notice" role="status" aria-live="polite">{{ notice }}</p>
      <p v-if="error" class="aa-error" role="alert">{{ error }}</p>

      <!-- 结果归属 -->
      <p v-if="staleText" class="aa-stale" role="status">{{ staleText }}</p>
      <p v-else-if="resultContextText" class="aa-muted">{{ resultContextText }}</p>

      <!-- 结果概览（三种模式共用） -->
      <section v-if="hasResult" class="aa-section aa-result" aria-labelledby="aa-meta-heading">
        <div class="aa-section-head">
          <h3 id="aa-meta-heading">结果概览</h3>
          <span class="aa-chip" :class="`aa-chip-${statusTone(resultMeta.status)}`">{{ statusLabel(resultMeta.status) }}</span>
        </div>
        <p class="aa-muted">{{ statusDescription(resultMeta.status) }}</p>
        <dl class="aa-facts">
          <div>
            <dt>区域</dt>
            <dd>{{ dash(resultMeta.area.name) }}<span v-if="resultMeta.area.version"> · v{{ resultMeta.area.version }}</span>
              <span class="aa-chip aa-chip-s">{{ resultMeta.area.is_default ? '默认区域' : '自定义矩形' }}</span>
            </dd>
          </div>
          <div><dt>区域边界</dt><dd class="aa-mono">{{ boundsText(resultMeta.area.bounds) }}<span v-if="resultMeta.area.span_deg">（跨度 {{ formatSpan(resultMeta.area.span_deg) }}）</span></dd></div>
          <div><dt>area_id</dt><dd class="aa-mono">{{ dash(resultMeta.area.area_id) }}</dd></div>
          <div><dt>算法版本</dt><dd>{{ dash(resultMeta.algorithm.name) }}<span v-if="resultMeta.algorithm.version"> v{{ resultMeta.algorithm.version }}</span></dd></div>
          <div v-if="coverageSummaryText"><dt>覆盖</dt><dd>{{ coverageSummaryText }}</dd></div>
          <div v-if="coverageWindowText"><dt>覆盖时间</dt><dd class="aa-mono">{{ coverageWindowText }}</dd></div>
          <div v-if="coverageNoteText"><dt>覆盖说明</dt><dd>{{ coverageNoteText }}</dd></div>
          <div v-if="areaBasisText"><dt>区域依据</dt><dd>{{ areaBasisText }}</dd></div>
        </dl>
        <div v-if="resultMeta.limitations.length" class="aa-block">
          <h4>限制说明（后端原文，需随结果一起表述）</h4>
          <ul class="aa-limits">
            <li v-for="(item, index) in resultMeta.limitations" :key="index">{{ item }}</li>
          </ul>
        </div>
      </section>

      <!-- 时刻在场结果 -->
      <section v-if="mode === 'snapshot' && hasSnapshot" class="aa-section aa-result" aria-labelledby="aa-snapshot-heading">
        <h3 id="aa-snapshot-heading">时刻在场</h3>
        <p v-if="isNoData(snapshotView.status)" class="aa-empty" role="status">无数据（no_data）：{{ statusDescription('no_data') }}</p>
        <template v-else>
          <p v-if="isEmptyResult(snapshotView.status, snapshotView.summary.in_area_count)" class="aa-empty" role="status">{{ emptyResultText('snapshot') }}</p>
          <dl class="aa-facts aa-grid">
            <div><dt>在场船数</dt><dd>{{ formatCount(snapshotView.summary.in_area_count) }}</dd></div>
            <div><dt>区域外新鲜报位</dt><dd>{{ formatCount(snapshotView.summary.out_of_area_fresh_count) }}</dd></div>
            <div><dt>过期报位（不计入在场）</dt><dd>{{ formatCount(snapshotView.summary.stale_fix_count) }}</dd></div>
            <div><dt>参与判定船舶</dt><dd>{{ formatCount(snapshotView.summary.evaluated_ship_count) }}</dd></div>
            <div><dt>新鲜度阈值</dt><dd>{{ formatSeconds(snapshotView.summary.freshness_seconds) }}</dd></div>
          </dl>
          <p v-if="snapshotTruncation" class="aa-warn" role="status">{{ snapshotTruncation }}</p>
          <div v-if="snapshotView.ships.length" class="aa-table-wrap" tabindex="0" role="region" aria-label="时刻在场船舶列表（窄屏可横向滚动）">
            <table class="aa-table">
              <caption>时刻在场船舶（{{ snapshotView.ships.length }} 艘；报位时间与龄期按 UTC）</caption>
              <thead>
                <tr>
                  <th scope="col">船名</th>
                  <th scope="col">MMSI</th>
                  <th scope="col">船型</th>
                  <th scope="col">位置</th>
                  <th scope="col">航速</th>
                  <th scope="col">报位时间</th>
                  <th scope="col">龄期</th>
                  <th scope="col">新鲜度</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="ship in snapshotView.ships" :key="ship.ship_id">
                  <th scope="row">{{ dash(ship.name) }}<small>#{{ ship.ship_id }}<template v-if="ship.flag"> · {{ ship.flag }}</template></small></th>
                  <td class="aa-mono">{{ dash(ship.mmsi) }}</td>
                  <td>{{ dash(ship.ship_type) }}</td>
                  <td class="aa-mono">{{ formatPosition(ship.latitude, ship.longitude) }}</td>
                  <td>{{ formatSpeed(ship.speed) }}</td>
                  <td class="aa-mono" :title="ship.recorded_at">{{ formatUtc(ship.recorded_at) }}</td>
                  <td>{{ formatAge(ship.age_seconds) }}</td>
                  <td>
                    <span class="aa-chip" :class="ship.fresh ? 'aa-chip-ok' : 'aa-chip-warn'">{{ ship.fresh ? '新鲜' : '过期' }}</span>
                    <span class="aa-chip" :class="ship.inside ? 'aa-chip-ok' : 'aa-chip-empty'">{{ ship.inside ? '区内' : '区外' }}</span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <p v-else class="aa-muted">列表为空。</p>
        </template>
      </section>

      <!-- 时段活动结果 -->
      <section v-else-if="mode === 'activity' && hasActivity" class="aa-section aa-result" aria-labelledby="aa-activity-heading">
        <h3 id="aa-activity-heading">时段活动</h3>
        <p v-if="isNoData(activityView.status)" class="aa-empty" role="status">无数据（no_data）：{{ statusDescription('no_data') }}</p>
        <template v-else>
          <p v-if="isEmptyResult(activityView.status, activityView.summary.ships_observed)" class="aa-empty" role="status">{{ emptyResultText('activity') }}</p>
          <h4>全窗汇总</h4>
          <dl class="aa-facts aa-grid">
            <div><dt>去重出现船数</dt><dd>{{ formatCount(activityView.summary.ships_observed) }}</dd></div>
            <div><dt>观测进入次数</dt><dd>{{ formatCount(activityView.summary.observed_entry_count) }}</dd></div>
            <div><dt>观测离开次数</dt><dd>{{ formatCount(activityView.summary.observed_exit_count) }}</dd></div>
            <div><dt>累计船时</dt><dd>{{ formatHours(activityView.summary.observed_ship_hours) }}<small>{{ formatSeconds(activityView.summary.observed_ship_seconds) }}</small></dd></div>
            <div><dt>访问数</dt><dd>{{ formatCount(activityView.summary.visit_count) }}</dd></div>
            <div><dt>未观测间隔合计</dt><dd>{{ formatSeconds(activityView.summary.unobserved_gap_seconds) }}</dd></div>
          </dl>
          <h4>访问状态计数</h4>
          <dl class="aa-facts aa-grid">
            <div><dt>完整</dt><dd>{{ formatCount(activityView.summary.complete_visit_count) }}</dd></div>
            <div><dt>起点截断</dt><dd>{{ formatCount(activityView.summary.truncated_start_visit_count) }}</dd></div>
            <div><dt>终点截断</dt><dd>{{ formatCount(activityView.summary.truncated_end_visit_count) }}</dd></div>
            <div><dt>缺报中断</dt><dd>{{ formatCount(activityView.summary.interrupted_visit_count) }}</dd></div>
            <div><dt>含质量标记</dt><dd>{{ formatCount(activityView.summary.uncertain_visit_count) }}</dd></div>
            <div><dt>前置状态未知</dt><dd>{{ formatCount(activityView.summary.prior_state_unknown_visit_count) }}</dd></div>
            <div><dt>边界近邻事件</dt><dd>{{ formatCount(activityView.summary.near_boundary_event_count) }}</dd></div>
          </dl>
          <p class="aa-muted">出现船数按各自范围去重，每日数字不可相加当作全窗去重；进入次数不要求等于离开次数（窗外进入、窗内离开、缺报都会造成差额）。</p>
          <p v-if="activityTruncation" class="aa-warn" role="status">{{ activityTruncation }}</p>
        </template>
      </section>

      <!-- 两时段比较结果 -->
      <section v-else-if="mode === 'compare' && hasCompare" class="aa-section aa-result" aria-labelledby="aa-compare-heading">
        <h3 id="aa-compare-heading">两时段比较</h3>
        <p v-if="isNoData(compareView.status)" class="aa-empty" role="status">无数据（no_data）：{{ statusDescription('no_data') }}</p>
        <template v-else>
          <dl class="aa-facts aa-grid">
            <div><dt>A 期窗口</dt><dd class="aa-mono">{{ utcRangeText(compareView.windows.a.start, compareView.windows.a.end) }}<small v-if="compareView.windows.a.days !== null">覆盖 {{ compareView.windows.a.days }} 个 UTC 自然日 · 实际长度 {{ formatDecimal(compareView.windows.a.length_hours, 1) }} 小时</small></dd></div>
            <div><dt>B 期窗口</dt><dd class="aa-mono">{{ utcRangeText(compareView.windows.b.start, compareView.windows.b.end) }}<small v-if="compareView.windows.b.days !== null">覆盖 {{ compareView.windows.b.days }} 个 UTC 自然日 · 实际长度 {{ formatDecimal(compareView.windows.b.length_hours, 1) }} 小时</small></dd></div>
          </dl>
          <h4>两期覆盖</h4>
          <dl class="aa-facts">
            <div><dt>A 期覆盖</dt><dd>{{ periodCoverageText(compareView.a.coverage) }}</dd></div>
            <div><dt>B 期覆盖</dt><dd>{{ periodCoverageText(compareView.b.coverage) }}</dd></div>
          </dl>
          <h4>可比性</h4>
          <ul class="aa-chips">
            <li><span class="aa-chip" :class="compareView.comparability.same_area ? 'aa-chip-ok' : 'aa-chip-warn'">同一区域</span></li>
            <li><span class="aa-chip" :class="compareView.comparability.same_filters ? 'aa-chip-ok' : 'aa-chip-warn'">同一筛选</span></li>
            <li><span class="aa-chip" :class="compareView.comparability.same_algorithm ? 'aa-chip-ok' : 'aa-chip-warn'">同一算法版本</span></li>
            <li><span class="aa-chip" :class="compareView.comparability.equal_length ? 'aa-chip-ok' : 'aa-chip-warn'">等长窗口</span></li>
            <li><span class="aa-chip aa-chip-s">自然日 A/B：{{ formatCount(compareView.comparability.window_days_a) }} / {{ formatCount(compareView.comparability.window_days_b) }}</span></li>
            <li><span class="aa-chip aa-chip-s">实际天数 A/B：{{ formatDecimal(compareView.comparability.window_length_days_a, 3) }} / {{ formatDecimal(compareView.comparability.window_length_days_b, 3) }}</span></li>
          </ul>
          <div v-if="compareView.comparability.warnings.length" class="aa-block">
            <h5>可比性提示（后端原文）</h5>
            <ul class="aa-limits">
              <li v-for="(warning, index) in compareView.comparability.warnings" :key="index">{{ warning }}</li>
            </ul>
          </div>
          <h4>指标对比</h4>
          <div class="aa-table-wrap" tabindex="0" role="region" aria-label="两期指标对比表（窄屏可横向滚动）">
            <table class="aa-table">
              <caption>两期指标（delta = B − A；基期为 0 时后端返回 change_rate=null，不用 0 代替；日均分母为窗口实际长度）</caption>
              <thead>
                <tr>
                  <th scope="col">指标</th>
                  <th scope="col">单位</th>
                  <th scope="col">A</th>
                  <th scope="col">B</th>
                  <th scope="col">delta</th>
                  <th scope="col">change_rate</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="metric in compareView.metrics" :key="metric.key">
                  <th scope="row">{{ metric.label }}</th>
                  <td>{{ dash(metric.unit) }}</td>
                  <td>{{ formatDecimal(metric.a, 2) }}</td>
                  <td>{{ formatDecimal(metric.b, 2) }}</td>
                  <td>{{ formatSigned(metric.delta, 2) }}</td>
                  <td>
                    <template v-if="hasChangeRate(metric.change_rate)">{{ changeRateText(metric.change_rate) }}</template>
                    <span v-else class="aa-muted" title="后端在基期 A=0 时返回 change_rate=null，不显示为 0">{{ changeRateText(metric.change_rate) }}</span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <p class="aa-muted">比较模式只返回两期的 summary、coverage 与 daily，不含访问明细；不输出无条件的「活动增减」结论。</p>
        </template>
      </section>

      <!-- 每日统计 + 趋势图（activity 与 compare 共用） -->
      <section v-if="dailyTables.length" class="aa-section aa-result" aria-labelledby="aa-daily-heading">
        <h3 id="aa-daily-heading">每日统计</h3>
        <div v-for="table in dailyTables" :key="table.key" class="aa-daily-group">
          <h4>{{ table.label }}（{{ table.rows.length }} 天，UTC 归日，status={{ statusLabel(table.status) }}）</h4>
          <p v-if="!table.rows.length" class="aa-muted">该范围没有每日数据。</p>
          <div v-else class="aa-table-wrap" tabindex="0" role="region" :aria-label="`${table.label}表格（窄屏可横向滚动）`">
            <table class="aa-table">
              <caption>{{ table.label }}：每日去重船数、进入/离开次数、累计船时与访问状态计数</caption>
              <thead>
                <tr>
                  <th scope="col">日期</th>
                  <th scope="col">去重船数</th>
                  <th scope="col">进入</th>
                  <th scope="col">离开</th>
                  <th scope="col">累计船时</th>
                  <th scope="col">涉及访问</th>
                  <th scope="col">完整</th>
                  <th scope="col">截断</th>
                  <th scope="col">中断</th>
                  <th scope="col">不确定</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="row in table.rows" :key="row.date">
                  <th scope="row" class="aa-mono">{{ row.date }}</th>
                  <td>{{ formatCount(row.ships_observed) }}</td>
                  <td>{{ formatCount(row.observed_entry_count) }}</td>
                  <td>{{ formatCount(row.observed_exit_count) }}</td>
                  <td>{{ formatHours(row.observed_ship_hours) }}</td>
                  <td>{{ formatCount(row.visits_touching_day) }}</td>
                  <td>{{ formatCount(row.complete_visit_count) }}</td>
                  <td>{{ formatCount(row.truncated_visit_count) }}</td>
                  <td>{{ formatCount(row.interrupted_visit_count) }}</td>
                  <td>{{ formatCount(row.uncertain_visit_count) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
        <div v-if="chartVisible" class="aa-chart-block">
          <h4>每日趋势</h4>
          <div ref="chartEl" class="aa-chart" role="img" :aria-label="chartLabel"></div>
          <p class="aa-muted">纵轴为每日去重船数（船）与观测进入/离开次数（次）；累计船时见上表。窄屏自动减少横轴刻度，趋势图不替代表格数字。</p>
        </div>
      </section>

      <!-- 访问明细（仅时段活动） -->
      <section v-if="mode === 'activity' && hasActivity && !isNoData(activityView.status)" class="aa-section aa-result" aria-labelledby="aa-visits-heading">
        <h3 id="aa-visits-heading">访问明细</h3>
        <p class="aa-muted">访问 = 序列中一段极大连续的区域内报位；证据报位 id 为源表 id。表内时间为 UTC。</p>
        <p v-if="activityTruncation" class="aa-warn" role="status">{{ activityTruncation }}</p>
        <div v-if="activityView.visits.length" class="aa-table-wrap" tabindex="0" role="region" aria-label="访问明细表（窄屏可横向滚动）">
          <table class="aa-table">
            <caption>区域内访问明细（{{ activityView.visits.length }} 条；展开行含进入/离开证据报位与分段）</caption>
            <thead>
              <tr>
                <th scope="col">船舶</th>
                <th scope="col">访问状态</th>
                <th scope="col">首次入区</th>
                <th scope="col">最后入区</th>
                <th scope="col">观测时长</th>
                <th scope="col">窗口内时长</th>
                <th scope="col">分段 / 报位</th>
                <th scope="col">质量标记</th>
                <th scope="col">操作</th>
              </tr>
            </thead>
            <tbody>
              <template v-for="visit in activityView.visits" :key="visit.visit_key">
                <tr>
                  <th scope="row">
                    <span>{{ dash(visit.ship_name) }}</span>
                    <small>#{{ visit.ship_id }}<template v-if="visit.mmsi"> · {{ visit.mmsi }}</template><template v-if="visit.ship_type"> · {{ visit.ship_type }}</template></small>
                    <small class="aa-mono">{{ visit.visit_key }}</small>
                  </th>
                  <td>
                    {{ visitStatusLabel(visit.status) }}
                    <small v-if="visit.started_before_window">窗口前已在区内</small>
                    <small v-else-if="visit.touches_window">与本窗口有交集</small>
                  </td>
                  <td class="aa-mono">{{ formatUtc(visit.first_inside_at) }}</td>
                  <td class="aa-mono">{{ formatUtc(visit.last_inside_at) }}</td>
                  <td>{{ formatSeconds(visit.observed_seconds) }}</td>
                  <td>{{ formatSeconds(visit.window_seconds) }}</td>
                  <td>{{ visit.segment_count }} 段 / {{ visit.fix_count }} 报位<small>未观测 {{ formatSeconds(visit.unobserved_gap_seconds) }}</small></td>
                  <td>
                    <template v-if="visit.flags.length">
                      <span v-for="flag in visit.flags" :key="flag" class="aa-chip aa-chip-warn">{{ flagLabel(flag) }}</span>
                    </template>
                    <span v-else class="aa-muted">无</span>
                  </td>
                  <td class="aa-actions-cell">
                    <button type="button" class="aa-btn aa-btn-s" @click="emit('locate-ship', visitLocateArgs(visit))">地图定位</button>
                    <button type="button" class="aa-btn aa-btn-s" @click="emit('focus-visit', visitFocusArgs(visit))">显示区间</button>
                    <button
                      type="button"
                      class="aa-btn aa-btn-s"
                      :aria-expanded="!!expandedVisits[visit.visit_key]"
                      :aria-controls="visitDetailId(visit.visit_key)"
                      @click="toggleVisit(visit.visit_key)"
                    >{{ expandedVisits[visit.visit_key] ? '收起明细' : '展开明细' }}</button>
                  </td>
                </tr>
                <tr v-if="expandedVisits[visit.visit_key]" :id="visitDetailId(visit.visit_key)" class="aa-detail-row">
                  <td colspan="9">
                    <div class="aa-detail">
                      <div class="aa-detail-grid">
                        <section aria-label="进入证据">
                          <h5>进入证据</h5>
                          <dl class="aa-facts">
                            <div><dt>是否观测到进入</dt><dd>{{ visit.entry.observed ? '是' : '否（不计入进入次数）' }}</dd></div>
                            <div><dt>事件时间</dt><dd class="aa-mono">{{ formatUtc(visit.entry.observed_at) }}<small>{{ eventWindowText(visit.entry.in_window) }}</small></dd></div>
                            <div><dt>证据括号</dt><dd>{{ bracketText(visit.entry.bracket_seconds) }}</dd></div>
                            <div><dt>区内报位（首点）</dt><dd class="aa-mono">{{ fixText(visit.entry.inside_fix) }}</dd></div>
                            <div><dt>区外报位（前一点）</dt><dd class="aa-mono">{{ fixText(visit.entry.outside_fix) }}</dd></div>
                            <div v-if="eventFlagLabels(visit.entry).length"><dt>证据标记</dt><dd><span v-for="label in eventFlagLabels(visit.entry)" :key="label" class="aa-chip aa-chip-warn">{{ label }}</span></dd></div>
                          </dl>
                        </section>
                        <section aria-label="离开证据">
                          <h5>离开证据</h5>
                          <dl class="aa-facts">
                            <div><dt>是否观测到离开</dt><dd>{{ visit.exit.observed ? '是' : '否（不计入离开次数）' }}</dd></div>
                            <div><dt>事件时间</dt><dd class="aa-mono">{{ formatUtc(visit.exit.observed_at) }}<small>{{ eventWindowText(visit.exit.in_window) }}</small></dd></div>
                            <div><dt>证据括号</dt><dd>{{ bracketText(visit.exit.bracket_seconds) }}</dd></div>
                            <div><dt>区内报位（末点）</dt><dd class="aa-mono">{{ fixText(visit.exit.inside_fix) }}</dd></div>
                            <div><dt>区外报位（后一点）</dt><dd class="aa-mono">{{ fixText(visit.exit.outside_fix) }}</dd></div>
                            <div v-if="eventFlagLabels(visit.exit).length"><dt>证据标记</dt><dd><span v-for="label in eventFlagLabels(visit.exit)" :key="label" class="aa-chip aa-chip-warn">{{ label }}</span></dd></div>
                          </dl>
                        </section>
                      </div>
                      <h5>轨迹分段（{{ visit.segments.length }} 段；gap/跳点区间不计入时长）</h5>
                      <table class="aa-table">
                        <caption>访问 {{ visit.visit_key }} 的分段起止与报位 id</caption>
                        <thead>
                          <tr>
                            <th scope="col">段</th>
                            <th scope="col">开始</th>
                            <th scope="col">结束</th>
                            <th scope="col">起始报位</th>
                            <th scope="col">结束报位</th>
                            <th scope="col">段时长</th>
                            <th scope="col">窗口内</th>
                            <th scope="col">报位数</th>
                          </tr>
                        </thead>
                        <tbody>
                          <tr v-for="segment in visit.segments" :key="segment.segment_no">
                            <th scope="row">{{ segment.segment_no }}</th>
                            <td class="aa-mono">{{ formatUtc(segment.start_at) }}</td>
                            <td class="aa-mono">{{ formatUtc(segment.end_at) }}</td>
                            <td class="aa-mono">#{{ dash(segment.start_fix_id) }}</td>
                            <td class="aa-mono">#{{ dash(segment.end_fix_id) }}</td>
                            <td>{{ formatSeconds(segment.seconds) }}</td>
                            <td>{{ formatSeconds(segment.in_window_seconds) }}</td>
                            <td>{{ segment.fix_count }}</td>
                          </tr>
                        </tbody>
                      </table>
                      <dl class="aa-facts">
                        <div><dt>前置状态</dt><dd>{{ priorStateLabel(visit.prior_state) }}</dd></div>
                        <div><dt>访问状态</dt><dd>{{ visitStatusLabel(visit.status) }}</dd></div>
                        <div><dt>质量标记</dt><dd>{{ visit.flags.length ? visit.flags.map(flagLabel).join('；') : '无' }}</dd></div>
                      </dl>
                    </div>
                  </td>
                </tr>
              </template>
            </tbody>
          </table>
        </div>
        <p v-else class="aa-muted">明细为空（可能未产生访问，或窗口内没有区域内报位）。</p>
      </section>
    </div>
  </aside>
</template>

<style scoped>
.aa-panel {
  display: flex;
  flex-direction: column;
  width: 100%;
  height: 100%;
  min-width: 0;
  min-height: 0;
  background: var(--panel);
  color: var(--ink);
  border-left: 1px solid var(--line);
}
.aa-head { display: flex; align-items: center; gap: 8px; flex: 0 0 auto; height: 48px; padding: 0 14px; border-bottom: 1px solid var(--line); }
.aa-head h2 { margin: 0; font-size: 13px; font-weight: 600; }
.aa-head-note { flex: 1; color: var(--muted); font-size: 10px; }
.aa-icon-btn { border: 1px solid var(--line); background: transparent; color: var(--muted); border-radius: var(--radius-s); width: 24px; height: 24px; cursor: pointer; }
.aa-icon-btn:hover, .aa-icon-btn:focus-visible { color: var(--ink); border-color: var(--accent); outline: 0; }
.aa-scroll { flex: 1 1 auto; min-height: 0; overflow-y: auto; overflow-x: hidden; padding: 10px 14px 28px; }
.aa-section { padding: 12px 0; border-bottom: 1px dashed var(--line); }
.aa-section:last-child { border-bottom: 0; }
.aa-section h3 { margin: 0 0 8px; font-size: 12px; font-weight: 600; }
.aa-section h4 { margin: 12px 0 6px; font-size: 11px; font-weight: 600; color: var(--ink); }
.aa-section h5 { margin: 10px 0 4px; font-size: 11px; font-weight: 600; color: var(--muted); }
.aa-section-head { display: flex; align-items: center; gap: 8px; }
.aa-section-head h3 { flex: 1; }
.aa-area-name { margin: 0 0 2px; font-size: 12px; }
.aa-muted { margin: 4px 0; color: var(--muted); font-size: 10px; line-height: 1.6; overflow-wrap: anywhere; }
.aa-mono { font-family: Consolas, 'Courier New', monospace; font-variant-numeric: tabular-nums; }
.aa-row { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; margin-top: 8px; }
.aa-row-end { justify-content: flex-end; }
.aa-modes { display: flex; flex-wrap: wrap; gap: 6px; }
.aa-mode, .aa-btn {
  border: 1px solid var(--line);
  background: transparent;
  color: var(--ink);
  border-radius: var(--radius-s);
  padding: 5px 10px;
  font-size: 11px;
  cursor: pointer;
}
.aa-btn-s { padding: 3px 8px; font-size: 10px; }
.aa-mode:hover, .aa-btn:hover:not(:disabled) { border-color: var(--accent); }
.aa-mode.active { border-color: var(--accent); color: var(--accent); background: color-mix(in srgb, var(--accent) 12%, transparent); }
.aa-mode:focus-visible, .aa-btn:focus-visible, .aa-check input:focus-visible { outline: 1px solid var(--accent); outline-offset: 1px; }
.aa-btn:disabled { opacity: .45; cursor: not-allowed; }
.aa-btn-primary { border-color: var(--accent); color: var(--accent); }
.aa-checks { list-style: none; margin: 8px 0 0; padding: 0; display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 2px 10px; }
.aa-checks li { display: flex; align-items: center; justify-content: space-between; gap: 6px; font-size: 11px; }
.aa-checks label { display: flex; align-items: center; gap: 6px; cursor: pointer; min-width: 0; }
.aa-checks span { overflow-wrap: anywhere; }
.aa-checks small { color: var(--muted); font-size: 10px; white-space: nowrap; }
.aa-field { display: flex; flex-direction: column; gap: 3px; margin: 8px 0; }
.aa-field label { color: var(--muted); font-size: 10px; }
.aa-field input {
  background: var(--page);
  border: 1px solid var(--line);
  border-radius: var(--radius-s);
  color: var(--ink);
  padding: 5px 7px;
  font-size: 11px;
  font-family: inherit;
  width: 100%;
  min-width: 0;
}
.aa-field input:focus-visible { outline: 1px solid var(--accent); outline-offset: 0; }
.aa-advanced { margin-top: 8px; }
.aa-advanced summary { color: var(--muted); font-size: 10px; cursor: pointer; }
.aa-status { margin: 10px 0 4px; color: var(--muted); font-size: 11px; }
.aa-notice { margin: 4px 0; color: var(--accent); font-size: 10px; }
.aa-error { margin: 4px 0; color: var(--danger); font-size: 11px; overflow-wrap: anywhere; }
.aa-warn { margin: 6px 0; color: var(--warn); font-size: 10px; line-height: 1.6; }
.aa-stale { margin: 6px 0; padding: 6px 8px; border: 1px solid var(--warn); border-radius: var(--radius-s); color: var(--warn); font-size: 10px; line-height: 1.6; }
.aa-empty { margin: 6px 0; padding: 8px; background: var(--wash); border-radius: var(--radius-s); color: var(--ink); font-size: 11px; line-height: 1.6; }
.aa-chip { display: inline-block; margin: 0 3px 2px 0; padding: 1px 6px; border: 1px solid var(--line); border-radius: 999px; font-size: 9px; color: var(--muted); white-space: nowrap; }
.aa-chip-ok { border-color: var(--ok); color: var(--ok); }
.aa-chip-warn { border-color: var(--warn); color: var(--warn); }
.aa-chip-empty { border-color: var(--line); color: var(--subtle); }
.aa-chip-s { font-size: 9px; }
.aa-chips { list-style: none; display: flex; flex-wrap: wrap; gap: 4px; margin: 6px 0; padding: 0; }
.aa-facts { margin: 6px 0; display: flex; flex-direction: column; gap: 4px; }
.aa-facts > div { display: flex; gap: 8px; font-size: 10px; }
.aa-facts dt { flex: 0 0 96px; color: var(--muted); }
.aa-facts dd { flex: 1; margin: 0; min-width: 0; overflow-wrap: anywhere; }
.aa-facts dd small { display: block; color: var(--muted); }
.aa-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(170px, 1fr)); gap: 4px 12px; }
.aa-grid > div { display: flex; gap: 6px; font-size: 11px; }
.aa-grid dt { flex: 0 0 auto; }
.aa-grid dd { font-variant-numeric: tabular-nums; font-weight: 600; }
.aa-block { margin-top: 8px; }
.aa-limits { margin: 4px 0 0; padding-left: 16px; color: var(--muted); font-size: 10px; line-height: 1.6; }
.aa-limits li { overflow-wrap: anywhere; }
.aa-table-wrap { max-width: 100%; overflow-x: auto; margin-top: 6px; border: 1px solid var(--line); border-radius: var(--radius-s); }
.aa-table-wrap:focus-visible { outline: 1px solid var(--accent); outline-offset: 1px; }
.aa-table { width: 100%; min-width: max-content; border-collapse: collapse; font-size: 10px; font-variant-numeric: tabular-nums; }
.aa-table caption { padding: 6px 8px; text-align: left; color: var(--muted); font-size: 10px; }
.aa-table th, .aa-table td { padding: 5px 8px; border-bottom: 1px solid var(--line); text-align: left; vertical-align: top; white-space: nowrap; }
.aa-table thead th { position: sticky; top: 0; background: var(--wash); color: var(--muted); z-index: 1; }
.aa-table tbody th { font-weight: 600; }
.aa-table tbody th small { display: block; color: var(--muted); font-weight: 400; }
.aa-table tbody tr:hover { background: var(--wash); }
.aa-actions-cell { display: flex; flex-wrap: wrap; gap: 4px; }
.aa-detail-row td { background: var(--page); white-space: normal; }
.aa-detail { padding: 6px 2px; }
.aa-detail-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 8px 16px; }
.aa-daily-group { margin-top: 8px; }
.aa-chart-block { margin-top: 10px; }
.aa-chart { width: 100%; height: 200px; }
@media (max-width: 640px) {
  .aa-scroll { padding: 8px 10px 24px; }
  .aa-facts dt { flex-basis: 80px; }
  .aa-grid { grid-template-columns: 1fr; }
  .aa-chart { height: 170px; }
}
@media (prefers-reduced-motion: reduce) {
  .aa-panel * { transition: none !important; animation: none !important; }
}
</style>
