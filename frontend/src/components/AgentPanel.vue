<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref } from 'vue'
import MarkdownIt from 'markdown-it'
import DOMPurify from 'dompurify'
import {
  IconChevronDown, IconCopy, IconRefresh, IconSend, IconSettings,
  IconSparkles, IconSquareFilled, IconTool, IconTrash,
} from '@tabler/icons-vue'
import {
  fetchAgentAnalyze,
  describeApiError,
  AgentRequestError,
  type AgentAnalyzeResponse,
  type AgentMapAction,
  type AgentEvidence,
  type AgentTurn,
  type AgentToolEventContextResult,
  type AgentToolShipSearchResult,
  type AgentToolShipTrackResult,
  type AgentToolAnalyticsResult,
  type AgentToolResult,
} from '../api'
import { eventKind, safeNewsUrl } from '../domain/maritime'

// 智能体问答是独立异步请求：不放入 computed，由本组件管理加载/取消/超时/错误状态。
// 前端 75 秒超时覆盖后端 60 秒预算，与新闻查询的 20 秒惯例无关（见 api.ts fetchAgentAnalyze）。
// 多轮：已完成轮次保留在 turns 中，提交时携带最近 10 轮 history（契约 v4）。
const emit = defineEmits<{
  'locate-ship': [shipId: number]
  'locate-event': [eventId: string]
}>()
const props = defineProps<{
  executeMapAction: (action: AgentMapAction, signal: AbortSignal) => Promise<string>
  cancelMapAction: () => void
  playbackAt: string | null
}>()

interface AgentTurnState {
  question: string
  response: AgentAnalyzeResponse | null
  mapMessage?: string
}

const markdown = new MarkdownIt({ html: false, linkify: false, breaks: true })

function renderAnswer(value: string): string {
  return DOMPurify.sanitize(markdown.render(value), { USE_PROFILES: { html: true } })
}

const question = ref('')
const closureAt = ref('')
const endAt = ref('')
const loading = ref(false)
const turns = ref<AgentTurnState[]>([])
const error = ref('')
const errorRequestId = ref('')
const notice = ref('')
const elapsedSeconds = ref(0)
const messageFlow = ref<HTMLElement | null>(null)
const userReadingHistory = ref(false)
let request: AbortController | null = null
let mapRequest: AbortController | null = null
const mapLoadingTurn = ref<number | null>(null)
let elapsedTimer: ReturnType<typeof setInterval> | null = null

const canSubmit = computed(() => question.value.trim().length > 0 && !loading.value)

function stopClock() {
  if (elapsedTimer) clearInterval(elapsedTimer)
  elapsedTimer = null
}

async function scrollToLatest(force = false) {
  await nextTick()
  const flow = messageFlow.value
  if (flow && (force || !userReadingHistory.value)) {
    flow.scrollTop = flow.scrollHeight
    userReadingHistory.value = false
  }
}

function trackScroll() {
  const flow = messageFlow.value
  if (flow) userReadingHistory.value = flow.scrollHeight - flow.scrollTop - flow.clientHeight > 72
}

function onQuestionKeydown(event: KeyboardEvent) {
  if (event.key !== 'Enter' || event.shiftKey || event.isComposing || event.keyCode === 229) return
  event.preventDefault()
  void submit()
}

const statusMeta: Record<string, { label: string; tone: 'ok' | 'warn' | 'info' }> = {
  ok: { label: '成功', tone: 'ok' },
  partial: { label: '部分数据', tone: 'ok' },
  no_data: { label: '无可用数据', tone: 'warn' },
  needs_clarification: { label: '待澄清', tone: 'info' },
  refused: { label: '已拒绝', tone: 'warn' },
}

const toolLabels: Record<string, string> = {
  query_strait_passages: '海峡通行',
  search_ships: '船舶检索',
  get_ship_track: '单船轨迹',
  get_event_context: '新闻事件',
  get_data_health: '数据健康',
  query_ship_dwell: '停留识别',
  query_encounters: '相遇分析',
  query_event_ship_links: '事件—船舶关联',
  query_analytics: '受限分析',
  search_project_knowledge: '项目知识',
  get_database_schema: '数据库结构',
  check_sql: 'SQL 安全检查',
  execute_sql: '只读 SQL 查询',
}

function agentErrorMessage(e: unknown): string {
  if (e instanceof AgentRequestError) {
    const friendly: Record<string, string> = {
      INVALID_REQUEST: '请求参数不合法：请检查问题长度及封锁时间格式（须带时区，窗口不超过 24 小时）。',
      AGENT_UNAVAILABLE: '智能体模型未配置或暂不可用，请稍后重试。',
      AGENT_TIMEOUT: '智能体处理超时，请缩小问题范围或稍后重试。',
      AGENT_INVALID_RESPONSE: '智能体回答不符合契约，请重试。',
      DATA_QUERY_FAILED: '数据查询失败，请稍后重试。',
      AGENT_QUERY_TIMEOUT: '受限分析查询超时，请缩小范围后重新提问。',
      AGENT_QUERY_UNAVAILABLE: '受限分析的只读数据源或安全配置当前不可用。',
    }
    return friendly[e.code] ?? e.message
  }
  return describeApiError(e, '智能体请求失败')
}

function buildHistory(): AgentTurn[] {
  const history: AgentTurn[] = []
  for (const turn of turns.value) {
    if (!turn.response) continue
    history.push({ role: 'user', content: turn.question })
    history.push({ role: 'assistant', content: turn.response.answer })
  }
  return history.slice(-10)
}

function referenceShip(): number | null {
  const response = turns.value.filter(turn => turn.response).at(-1)?.response
  if (!response) return null
  const actionIds = new Set(response.map_actions?.filter(action => action.type !== 'event').map(action => action.ship_id))
  if (actionIds.size === 1) return [...actionIds][0]!
  const ids = new Set<number>()
  for (const result of Object.values(response.results ?? {})) {
    if (result.status !== 'ok') continue
    if (result.tool_name === 'get_ship_track' && 'ship_id' in result) ids.add(result.ship_id as number)
    if (result.tool_name === 'search_ships' && 'matches' in result) {
      const search = result as AgentToolShipSearchResult
      if (search.matched_count !== 1 || search.truncated) return null
      search.matches.forEach(match => ids.add(match.ship_id))
    }
  }
  return ids.size === 1 ? [...ids][0]! : null
}

function parseTime(value: string): string | null {
  const trimmed = value.trim()
  return trimmed ? trimmed : null
}

function explicitTrackWindow(text: string): [string, string] | null {
  if (!text.includes('轨迹')) return null
  const values = text.match(/\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2})?(?:Z|[+-]\d{2}:\d{2})/g)
  if (values?.length !== 2) return null
  const start = Date.parse(values[0]!), end = Date.parse(values[1]!)
  return Number.isFinite(start) && Number.isFinite(end) && start < end && end - start <= 86400000
    ? [new Date(start).toISOString(), new Date(end).toISOString()] : null
}

async function submit() {
  if (!canSubmit.value) return
  request?.abort()
  cancelMap()
  const controller = new AbortController()
  request = controller
  const asked = question.value.trim()
  const inferredWindow = explicitTrackWindow(asked)
  const history = buildHistory()
  const targetShipId = referenceShip()
  const turnIndex = turns.value.push({ question: asked, response: null }) - 1
  question.value = ''
  loading.value = true
  error.value = ''
  errorRequestId.value = ''
  notice.value = ''
  elapsedSeconds.value = 0
  stopClock()
  elapsedTimer = setInterval(() => { elapsedSeconds.value += 1 }, 1000)
  void scrollToLatest()
  try {
    const response = await fetchAgentAnalyze(
      {
        question: asked,
        closure_at: parseTime(closureAt.value) ?? inferredWindow?.[0] ?? null,
        end_at: parseTime(endAt.value) ?? inferredWindow?.[1] ?? null,
        history,
        ...(props.playbackAt ? { map_context: { playback_at: props.playbackAt, target_ship_id: targetShipId } } : {}),
      },
      controller.signal,
    )
    if (request === controller && !controller.signal.aborted) {
      turns.value[turnIndex]!.response = response
      const automatic = response.map_actions?.find(action => action.trigger === 'automatic')
      if (automatic) void runMapAction(turnIndex, automatic)
      void scrollToLatest()
    }
  } catch (e) {
    if (request === controller && !controller.signal.aborted) {
      if (e instanceof AgentRequestError) errorRequestId.value = e.requestId
      error.value = agentErrorMessage(e)
    }
  } finally {
    if (request === controller) {
      loading.value = false
      request = null
      stopClock()
      void scrollToLatest()
    }
  }
}

async function runMapAction(turnIndex: number, action: AgentMapAction) {
  const turn = turns.value[turnIndex]
  if (!turn) return
  cancelMap()
  const controller = new AbortController()
  mapRequest = controller
  mapLoadingTurn.value = turnIndex
  turn.mapMessage = '正在地图加载并核对目标…'
  try {
    const message = await props.executeMapAction(action, controller.signal)
    if (!controller.signal.aborted) turn.mapMessage = message
  } catch (e) {
    if (!controller.signal.aborted) turn.mapMessage = describeApiError(e, '地图操作失败')
  } finally {
    if (mapRequest === controller) { mapRequest = null; mapLoadingTurn.value = null }
  }
}

function cancelMap() {
  if (!mapRequest) return
  mapRequest.abort()
  props.cancelMapAction()
  if (mapLoadingTurn.value !== null) turns.value[mapLoadingTurn.value]!.mapMessage = '地图操作已取消。'
  mapRequest = null
  mapLoadingTurn.value = null
}

function cancel() {
  cancelMap()
  request?.abort()
  request = null
  loading.value = false
  stopClock()
  notice.value = '已取消本次智能体请求。'
  void scrollToLatest()
}

function reset() {
  cancelMap()
  request?.abort()
  request = null
  loading.value = false
  stopClock()
  turns.value = []
  error.value = ''
  errorRequestId.value = ''
  notice.value = ''
  userReadingHistory.value = false
}

function retry() {
  const last = turns.value.at(-1)
  if (!last || last.response || loading.value) return
  question.value = last.question
  turns.value.pop()
  void submit()
}

async function copyAnswer(answer: string) {
  try {
    await navigator.clipboard.writeText(answer)
    notice.value = '回答已复制。'
  } catch {
    notice.value = '复制失败，请选中文本复制。'
  }
}

function toolEntries(response: AgentAnalyzeResponse): [string, AgentToolResult][] {
  return Object.entries(response.results ?? {})
}

function toolDetail(result: AgentToolResult): string {
  const record = result as Record<string, unknown>
  const parts: string[] = []
  if (typeof record.keyword === 'string') parts.push(`关键词：${record.keyword}`)
  if (typeof record.ship_id === 'number') parts.push(`船 ID：${record.ship_id}`)
  if (typeof record.event_id === 'string') parts.push(`事件 ID：${record.event_id}`)
  if (typeof record.direction === 'string') parts.push(`方向：${record.direction}`)
  if (typeof record.kind === 'string') parts.push(`类别：${record.kind}`)
  if (typeof record.returned_count === 'number') parts.push(`返回 ${record.returned_count} 条`)
  if (typeof record.matched_count === 'number') parts.push(`匹配 ${record.matched_count} 条`)
  if (typeof record.returned_event_count === 'number') parts.push(`返回 ${record.returned_event_count} 个事件`)
  if (typeof record.fix_count === 'number') parts.push(`报位 ${record.fix_count} 条`)
  if (typeof record.returned_row_count === 'number') parts.push(`结果 ${record.returned_row_count} 行`)
  if (record.truncated === true) parts.push('已截断')
  return parts.join(' · ') || '服务端未返回可展示的参数或计数'
}

function directionLabel(direction: string): string {
  if (direction === 'west_to_east') return '西向东'
  if (direction === 'east_to_west') return '东向西'
  return direction
}

function fixText(fix: AgentEvidence['start_fix']): string {
  return `${fix.recorded_at.replace('T', ' ').replace('Z', ' UTC')}，${fix.longitude.toFixed(4)}°E / ${fix.latitude.toFixed(4)}°N`
}

function formatUtc(value: string): string {
  return value.replace('T', ' ').replace('Z', ' UTC')
}

function toolResult(response: AgentAnalyzeResponse, toolName: string) {
  return Object.values(response.results ?? {}).find((item) => item.tool_name === toolName)
}

function eventResult(response: AgentAnalyzeResponse): AgentToolEventContextResult | null {
  const result = toolResult(response, 'get_event_context')
  return result && 'events' in result ? (result as AgentToolEventContextResult) : null
}

function searchResult(response: AgentAnalyzeResponse): AgentToolShipSearchResult | null {
  const result = toolResult(response, 'search_ships')
  return result && 'matches' in result ? (result as AgentToolShipSearchResult) : null
}

function trackResult(response: AgentAnalyzeResponse): AgentToolShipTrackResult | null {
  const result = toolResult(response, 'get_ship_track')
  return result && 'fix_count' in result ? (result as AgentToolShipTrackResult) : null
}

function analyticsResult(response: AgentAnalyzeResponse): AgentToolAnalyticsResult | null {
  const result = toolResult(response, 'query_analytics')
  return result && 'columns' in result ? (result as AgentToolAnalyticsResult) : null
}

function cellText(value: unknown): string {
  if (value === null) return 'null'
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

onBeforeUnmount(() => { request?.abort(); cancelMap(); stopClock() })
</script>

<template>
  <section class="panel-content agent-panel">
    <header class="chat-heading">
      <div><strong>智能体问答</strong><span>船位观测与新闻报道分别呈现</span></div>
      <button v-if="turns.length || error" type="button" class="icon-button" aria-label="清空对话" title="清空对话" @click="reset"><IconTrash :size="17" aria-hidden="true" /></button>
    </header>
    <div ref="messageFlow" class="message-flow" @scroll.passive="trackScroll">
      <div v-if="!turns.length && !loading" class="chat-empty">
        <IconSparkles :size="22" aria-hidden="true" />
        <strong>从一个问题开始</strong>
        <p>可询问海峡通行、船舶轨迹或新闻事件。回答会附上可用证据和来源。</p>
      </div>
      <article v-for="(turn, turnIndex) in turns" :key="turnIndex" class="chat-turn">
        <p class="turn-question">{{ turn.question }}</p>
        <div v-if="turn.response" class="agent-result">
        <div class="result-head">
          <span class="status-badge" :data-tone="statusMeta[turn.response.status]?.tone ?? 'info'">
            {{ statusMeta[turn.response.status]?.label ?? turn.response.status }}
          </span>
          <span v-for="tool in turn.response.tools_used" :key="tool" class="tool-chip">{{ toolLabels[tool] ?? tool }}</span>
          <button type="button" class="icon-button copy-button" aria-label="复制回答" title="复制回答" @click="copyAnswer(turn.response.answer)"><IconCopy :size="16" aria-hidden="true" /></button>
        </div>

        <details v-if="toolEntries(turn.response).length || turn.response.tools_used.length" class="tool-process">
          <summary><IconTool :size="15" aria-hidden="true" /> 使用了 {{ turn.response.tools_used.map(tool => toolLabels[tool] ?? tool).join(' / ') || '工具' }}<IconChevronDown class="chevron" :size="14" aria-hidden="true" /></summary>
          <ol v-if="toolEntries(turn.response).length">
            <li v-for="[callId, result] in toolEntries(turn.response)" :key="callId">
              <strong>{{ toolLabels[String(result.tool_name ?? '')] ?? result.tool_name ?? '工具调用' }}</strong>
              <span class="tool-status">{{ result.status ?? '状态未提供' }}</span>
              <span class="request-id">{{ callId }}</span>
              <small>{{ toolDetail(result) }}</small>
            </li>
          </ol>
          <p v-else class="caption">服务端只返回工具名，未提供逐次调用结果。</p>
        </details>

        <p v-if="turn.response.status === 'needs_clarification' && turn.response.clarification" class="clarification">
          {{ turn.response.clarification }}
        </p>
        <section v-if="turn.response.answer" class="answer-block">
          <div class="answer-text" v-html="renderAnswer(turn.response.answer)"></div>
        </section>
        <section v-if="turn.response.map_actions?.length" class="facts-block">
          <h3>地图操作</h3>
          <button v-for="(action, actionIndex) in turn.response.map_actions" :key="actionIndex" type="button" class="locate-btn" @click="runMapAction(turnIndex, action)">
            {{ action.type === 'ship_track' ? '在地图显示轨迹' : action.type === 'ship_position' ? '在地图定位船位' : '在地图显示事件' }}
          </button>
          <p v-for="(action, actionIndex) in turn.response.map_actions.filter(item => item.type !== 'event')" :key="`window-${actionIndex}`" class="caption">{{ `${action.start_at} — ${action.end_at} · ${action.window_source || '工具核实时间窗'} · ${action.source}` }}</p>
          <button v-if="mapLoadingTurn === turnIndex" type="button" class="locate-btn" @click="cancelMap">取消地图操作</button>
          <p v-if="turn.mapMessage" role="status" class="caption">{{ turn.mapMessage }}</p>
        </section>

        <section v-if="analyticsResult(turn.response)" class="facts-block analytics-block">
          <h3>受限分析结果</h3>
          <p class="summary-line">
            {{ analyticsResult(turn.response)!.returned_row_count }} 行
            · catalog {{ analyticsResult(turn.response)!.source.catalog_version }}
            · 视图 {{ analyticsResult(turn.response)!.source.views.join('、') }}
            <template v-if="analyticsResult(turn.response)!.truncated"> · 结果已截断</template>
          </p>
          <div v-if="analyticsResult(turn.response)!.rows.length" class="analytics-table-wrap">
            <table class="analytics-table">
              <thead><tr><th v-for="column in analyticsResult(turn.response)!.columns" :key="column">{{ column }}</th></tr></thead>
              <tbody>
                <tr v-for="(row, rowIndex) in analyticsResult(turn.response)!.rows" :key="rowIndex">
                  <td v-for="(cell, cellIndex) in row" :key="cellIndex">{{ cellText(cell) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <p v-else class="caption">查询成功，明确范围内返回 0 行。</p>
          <p class="request-id">查询标识：{{ analyticsResult(turn.response)!.query_id }}</p>
        </section>

        <details class="facts-block collapsible-facts">
          <summary>查询上下文</summary>
          <dl class="facts">
            <div><dt>批次</dt><dd>{{ turn.response.context.batch }}</dd></div>
            <div><dt>封锁窗口</dt><dd>{{ formatUtc(turn.response.context.closure_at) }} — {{ formatUtc(turn.response.context.end_at) }}</dd></div>
            <div><dt>封锁时间来源</dt><dd>{{ turn.response.context.closure_source }}</dd></div>
            <div><dt>船位来源</dt><dd>{{ turn.response.context.ship_data_source }}</dd></div>
            <div><dt>通行规则</dt><dd>{{ turn.response.context.passage_rule }}</dd></div>
          </dl>
        </details>

        <details v-if="turn.response.query_summary" class="facts-block collapsible-facts">
          <summary>查询统计</summary>
          <p class="summary-line">
            报位 {{ turn.response.query_summary.position_count }} 条 · 匹配船只 {{ turn.response.query_summary.matched_ship_count }} 艘 ·
            通行 {{ turn.response.query_summary.passage_count }} 次 · 不确定候选 {{ turn.response.query_summary.uncertain_candidate_count }} 个
            <template v-if="turn.response.query_summary.coverage_start && turn.response.query_summary.coverage_end">
              · 覆盖 {{ formatUtc(turn.response.query_summary.coverage_start) }} — {{ formatUtc(turn.response.query_summary.coverage_end) }}
            </template>
            <template v-if="turn.response.query_summary.truncated"> · 结果已截断</template>
          </p>
        </details>

        <section v-if="trackResult(turn.response)" class="facts-block">
          <h3>轨迹查询结果</h3>
          <p class="summary-line">
            {{ trackResult(turn.response)!.ship_name }}（ID {{ trackResult(turn.response)!.ship_id }}）
            · 报位 {{ trackResult(turn.response)!.fix_count }} 条
            <template v-if="trackResult(turn.response)!.coverage_start && trackResult(turn.response)!.coverage_end">
              · 覆盖 {{ formatUtc(trackResult(turn.response)!.coverage_start!) }} — {{ formatUtc(trackResult(turn.response)!.coverage_end!) }}
            </template>
          </p>
        </section>

        <section v-if="turn.response.ships.length" class="facts-block">
          <h3>船只（{{ turn.response.ships.length }}）</h3>
          <ul class="ship-list">
            <li v-for="ship in turn.response.ships" :key="ship.ship_id">
              <span class="ship-line">
                <strong>{{ ship.name }}</strong>
                <span>ID {{ ship.ship_id }} · 通行 {{ ship.passage_count }} 次</span>
              </span>
              <button type="button" class="locate-btn" @click="emit('locate-ship', ship.ship_id)">地图定位</button>
            </li>
          </ul>
        </section>

        <section v-if="searchResult(turn.response)?.matches.length" class="facts-block">
          <h3>检索到的船（{{ searchResult(turn.response)!.returned_count }}）</h3>
          <ul class="ship-list">
            <li v-for="match in searchResult(turn.response)!.matches" :key="match.ship_id">
              <span class="ship-line">
                <strong>{{ match.name }}</strong>
                <span>ID {{ match.ship_id }} · {{ match.ship_type }} · MMSI {{ match.mmsi }}</span>
              </span>
              <button type="button" class="locate-btn" @click="emit('locate-ship', match.ship_id)">地图定位</button>
            </li>
          </ul>
          <p v-if="searchResult(turn.response)!.truncated" class="caption">
            命中 {{ searchResult(turn.response)!.matched_count }} 条，仅返回前 {{ searchResult(turn.response)!.returned_count }} 条。
          </p>
        </section>

        <section v-if="eventResult(turn.response)?.events.length" class="facts-block">
          <h3>事件（{{ eventResult(turn.response)!.returned_event_count }}）</h3>
          <p class="caption">新闻事件为已采集报道的聚合，与船位数据相互独立。</p>
          <ul class="event-list">
            <li v-for="event in eventResult(turn.response)!.events" :key="event.event_id">
              <div class="event-head">
                <strong>[{{ event.event_id }}] {{ event.title_zh }}</strong>
                <button type="button" class="locate-btn" @click="emit('locate-event', event.event_id)">地图定位</button>
              </div>
              <p class="summary-line">
                类型 {{ eventKind(event.event_type).label }}
                · 时间 {{ event.event_datetime ? formatUtc(event.event_datetime) : (event.event_time_text ?? '未知') }}
                <template v-if="event.event_location_text"> · 位置 {{ event.event_location_text }}</template>
              </p>
              <p class="event-summary">{{ event.summary_zh }}</p>
              <ul v-if="event.news.length" class="news-list">
                <li v-for="story in event.news" :key="story.story_id">
                  <a v-if="safeNewsUrl(story.url)" :href="safeNewsUrl(story.url)" target="_blank" rel="noopener noreferrer">{{ story.title_zh }}</a>
                  <span v-else>{{ story.title_zh }}</span>
                  <span class="summary-line">
                    {{ story.media_name }} · {{ story.publish_date ?? '日期未知' }} · 视角 {{ story.perspective }}
                  </span>
                </li>
              </ul>
            </li>
          </ul>
          <p v-if="eventResult(turn.response)!.truncated" class="caption">
            命中事件超过上限，仅返回前 {{ eventResult(turn.response)!.returned_event_count }} 个。
          </p>
        </section>

        <section v-if="turn.response.evidence.length" class="facts-block">
          <h3>通行证据（{{ turn.response.evidence.length }}）</h3>
          <ul class="evidence-list">
            <li v-for="item in turn.response.evidence" :key="item.evidence_id">
              <div class="event-head">
                <strong>[{{ item.evidence_id }}]</strong> 船 ID {{ item.ship_id }} · 方向 {{ directionLabel(item.direction) }}
                · 观测完成 {{ formatUtc(item.observed_completion_at) }}
                <button type="button" class="locate-btn" @click="emit('locate-ship', item.ship_id)">地图定位</button>
              </div>
              <span class="fix-line">起始侧报位：{{ fixText(item.start_fix) }}</span>
              <span class="fix-line">完成侧报位：{{ fixText(item.completion_fix) }}</span>
            </li>
          </ul>
        </section>

        <section v-if="turn.response.limitations.length" class="facts-block">
          <h3>限制说明</h3>
          <ul class="limitation-list">
            <li v-for="(item, index) in turn.response.limitations" :key="index">{{ item }}</li>
          </ul>
        </section>
        <span class="request-id">请求标识：{{ turn.response.request_id }}</span>
        </div>
      </article>
      <div v-if="loading" class="waiting-bubble" role="status">
        <span class="typing-dots" aria-hidden="true"><i></i><i></i><i></i></span>
        <span>正在分析…已等待 {{ elapsedSeconds }} 秒</span>
        <button type="button" @click="cancel">停止</button>
      </div>
      <div v-else-if="error" class="chat-alert error" role="alert">
        <span>{{ error }}</span><span v-if="errorRequestId" class="request-id">请求标识：{{ errorRequestId }}</span>
        <button type="button" @click="retry"><IconRefresh :size="15" aria-hidden="true" /> 重试</button>
      </div>
      <p v-if="notice" class="chat-notice" role="status">{{ notice }}</p>
    </div>
    <form class="agent-form" @submit.prevent="submit">
      <details class="advanced">
        <summary><IconSettings :size="17" aria-hidden="true" /> 高级设置：封锁窗口（可留空）<IconChevronDown class="chevron" :size="14" aria-hidden="true" /></summary>
        <label>封锁开始时间<input v-model="closureAt" type="text" placeholder="例如 2026-02-28T14:00:00Z" aria-label="封锁开始时间" /></label>
        <label>封锁结束时间<input v-model="endAt" type="text" placeholder="例如 2026-02-28T15:00:00Z" aria-label="封锁结束时间" /></label>
        <p class="caption">时间须带时区，窗口不超过 24 小时。船位/轨迹问题留空时按地图回放时刻附近窗口查询，实际起止以结果为准。</p>
      </details>
      <div class="composer">
        <textarea v-model="question" rows="2" maxlength="2000" placeholder="询问海峡通行、船舶轨迹或新闻事件…" aria-label="智能体问题" @keydown="onQuestionKeydown"></textarea>
        <button v-if="loading" type="button" class="send-button" aria-label="停止生成" title="停止生成" @click="cancel"><IconSquareFilled :size="14" aria-hidden="true" /></button>
        <button v-else type="submit" class="send-button" :disabled="!canSubmit" aria-label="发送提问" title="发送提问"><IconSend :size="19" aria-hidden="true" /></button>
      </div>
      <p class="composer-hint">Enter 发送 · Shift+Enter 换行</p>
    </form>
  </section>
</template>

<style scoped>
.agent-form {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--line, #68768150);
}
.agent-form label {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 12px;
  color: var(--muted, #9fc2e0);
}
.agent-form textarea,
.agent-form input {
  font: inherit;
  color: var(--ink);
  background: var(--panel, #12263a);
  border: 1px solid var(--line, #26405a);
  border-radius: 3px;
  padding: 6px 8px;
  resize: vertical;
}
.agent-form textarea:focus-visible,
.agent-form input:focus-visible {
  outline: 2px solid var(--blue, #38bdf8);
  outline-offset: 2px;
}
.advanced summary {
  cursor: pointer;
  font-size: 12px;
  color: var(--muted, #9fc2e0);
  padding: 4px 0;
}
.advanced {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.actions {
  display: flex;
  gap: 8px;
}
.result-head {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.status-badge {
  padding: 2px 8px;
  border-radius: 10px;
  font-size: 12px;
  border: 1px solid var(--line, #26405a);
}
.tool-chip {
  padding: 1px 6px;
  border-radius: 8px;
  font-size: 11px;
  border: 1px solid var(--line, #26405a);
  color: var(--muted, #9fc2e0);
}
.status-badge[data-tone='ok'] {
  color: #7ee2a8;
  border-color: #2f7d52;
}
.status-badge[data-tone='warn'] {
  color: #f2c14e;
  border-color: #8a6d1f;
}
.status-badge[data-tone='info'] {
  color: var(--blue, #38bdf8);
  border-color: #2b6a8a;
}
:root[data-theme='light'] .status-badge[data-tone='ok'] {
  color: #1d7a43;
  border-color: #1d7a43;
}
:root[data-theme='light'] .status-badge[data-tone='warn'] {
  color: #8a6d1f;
  border-color: #8a6d1f;
}
:root[data-theme='light'] .status-badge[data-tone='info'] {
  color: #1c6ea0;
  border-color: #1c6ea0;
}
.agent-result {
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 12px 0;
  border-bottom: 1px solid var(--line, #68768150);
}
.turn-question {
  font-weight: 650;
  overflow-wrap: anywhere;
}
.agent-result h3 {
  font-size: 14px;
  font-weight: 650;
  padding-bottom: 4px;
}
.analytics-table-wrap {
  overflow-x: auto;
  margin-top: 8px;
}
.analytics-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}
.analytics-table th,
.analytics-table td {
  padding: 5px 7px;
  border: 1px solid var(--line, #26405a);
  text-align: left;
  white-space: nowrap;
}
.analytics-table th {
  color: var(--muted, #9fc2e0);
  font-weight: 650;
}
.answer-text {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  line-height: 1.7;
}
.clarification {
  padding: 8px 10px;
  border: 1px solid var(--line, #26405a);
  border-radius: 3px;
  background: var(--wash, #16324a);
}
.summary-line {
  font-size: 12px;
  line-height: 1.7;
  color: var(--muted, #9fc2e0);
}
.ship-list,
.evidence-list,
.limitation-list,
.event-list,
.news-list {
  list-style: none;
  padding: 0;
  margin: 0;
}
.ship-list li,
.evidence-list li,
.limitation-list li {
  padding: 8px 0;
  border-bottom: 1px solid var(--line, #68768150);
  font-size: 12px;
  line-height: 1.7;
  overflow-wrap: anywhere;
}
.ship-list li {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.ship-line {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.ship-list span {
  color: var(--muted, #9fc2e0);
}
.locate-btn {
  font: inherit;
  font-size: 11px;
  padding: 2px 8px;
  border: 1px solid var(--line, #26405a);
  border-radius: 3px;
  background: transparent;
  color: var(--blue, #38bdf8);
  cursor: pointer;
  white-space: nowrap;
}
.locate-btn:hover {
  border-color: var(--blue, #38bdf8);
}
.event-list > li {
  padding: 10px 0;
  border-bottom: 1px solid var(--line, #68768150);
  font-size: 12px;
  line-height: 1.7;
}
.event-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.event-summary {
  margin: 4px 0;
  overflow-wrap: anywhere;
}
.news-list li {
  padding: 4px 0;
}
.news-list a {
  color: var(--blue, #38bdf8);
  overflow-wrap: anywhere;
}
.fix-line {
  display: block;
  color: var(--muted, #9fc2e0);
}
.request-id {
  font-size: 11px;
  color: var(--subtle, #7a8fa6);
  display: block;
}
.result-head .request-id {
  display: inline;
}
.facts dd {
  overflow-wrap: anywhere;
}
.agent-panel {
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--panel);
}
.chat-heading {
  flex: none;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  padding: 11px 16px;
  border-bottom: 1px solid var(--line);
}
.chat-heading div { display: flex; flex-direction: column; gap: 3px; }
.chat-heading strong { font-size: 13px; }
.chat-heading span, .composer-hint { color: var(--muted); font-size: 11px; }
.icon-button {
  display: grid;
  place-items: center;
  width: 28px;
  height: 28px;
  border: 1px solid transparent;
  border-radius: 7px;
  color: var(--muted);
  background: transparent;
  cursor: pointer;
}
.icon-button:hover, .icon-button:focus-visible { color: var(--ink); background: var(--wash); border-color: var(--line); }
.message-flow {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  overscroll-behavior: contain;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 13px;
}
.chat-empty { margin: auto; max-width: 260px; display: grid; gap: 10px; justify-items: center; text-align: center; color: var(--muted); line-height: 1.6; }
.chat-empty strong { color: var(--ink); font-size: 14px; }
.chat-empty p { font-size: 12px; }
.chat-turn { display: flex; flex-direction: column; align-items: stretch; gap: 12px; }
.turn-question {
  align-self: flex-end;
  max-width: 88%;
  padding: 9px 12px;
  border-radius: 14px 14px 4px 14px;
  border: 1px solid var(--line);
  background: var(--wash);
  font-size: 12px;
  line-height: 1.6;
  white-space: pre-wrap;
}
.agent-result {
  gap: 12px;
  padding: 14px;
  border: 1px solid var(--line);
  border-radius: 14px 14px 14px 4px;
  background: var(--panel);
  box-shadow: 0 4px 16px rgb(0 0 0 / .08);
}
.copy-button { margin-left: auto; }
.tool-process, .collapsible-facts { border: 1px solid var(--line); border-radius: 8px; padding: 8px 10px; }
.tool-process summary, .collapsible-facts summary, .advanced summary { cursor: pointer; list-style: none; display: flex; align-items: center; gap: 7px; color: var(--muted); font-size: 12px; }
.tool-process summary::-webkit-details-marker, .collapsible-facts summary::-webkit-details-marker, .advanced summary::-webkit-details-marker { display: none; }
.tool-process .chevron, .advanced .chevron { margin-left: auto; transition: transform .18s ease; }
.tool-process[open] .chevron, .advanced[open] .chevron { transform: rotate(180deg); }
.tool-process ol { margin: 9px 0 0; padding-left: 19px; display: grid; gap: 8px; }
.tool-process li { font-size: 11px; overflow-wrap: anywhere; }
.tool-process li strong { margin-right: 7px; }
.tool-process li small { display: block; margin-top: 3px; color: var(--muted); font-size: 11px; }
.tool-status { padding: 1px 5px; border-radius: 5px; background: var(--wash); }
.collapsible-facts { margin: 0; }
.collapsible-facts .facts, .collapsible-facts .summary-line { margin-top: 9px; }
.answer-block { min-width: 0; }
.answer-text { white-space: normal; font-size: 13px; line-height: 1.7; }
.answer-text :deep(p) { margin: 0 0 9px; }
.answer-text :deep(p:last-child) { margin-bottom: 0; }
.answer-text :deep(ul), .answer-text :deep(ol) { padding-left: 20px; margin: 6px 0 10px; }
.answer-text :deep(strong) { color: var(--ink); }
.answer-text :deep(a) { color: var(--blue); text-decoration: underline; text-underline-offset: 2px; }
.answer-text :deep(pre) { overflow-x: auto; padding: 9px; border-radius: 6px; background: var(--wash); }
.answer-text :deep(code) { font-family: ui-monospace, Consolas, monospace; font-size: .92em; }
.answer-text :deep(table) { display: block; max-width: 100%; overflow-x: auto; border-collapse: collapse; font-size: 12px; }
.answer-text :deep(th), .answer-text :deep(td) { padding: 5px 7px; border: 1px solid var(--line); text-align: left; }
.answer-text :deep(blockquote) { margin: 8px 0; padding-left: 10px; border-left: 2px solid var(--blue); color: var(--muted); }
.waiting-bubble, .chat-alert, .chat-notice {
  align-self: flex-start;
  padding: 10px 12px;
  border: 1px solid var(--line);
  border-radius: 12px 12px 12px 4px;
  font-size: 12px;
  line-height: 1.5;
}
.waiting-bubble { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.waiting-bubble button, .chat-alert button { background: transparent; border: 1px solid var(--line); border-radius: 6px; color: var(--ink); cursor: pointer; padding: 3px 7px; }
.chat-alert button { display: inline-flex; align-items: center; gap: 4px; margin-top: 6px; }
.typing-dots { display: inline-flex; gap: 3px; align-items: center; height: 14px; }
.typing-dots i { width: 5px; height: 5px; border-radius: 50%; background: var(--blue); animation: typing-bounce .75s infinite alternate; }
.typing-dots i:nth-child(2) { animation-delay: .15s; }
.typing-dots i:nth-child(3) { animation-delay: .3s; }
@keyframes typing-bounce { to { transform: translateY(-4px); opacity: .35; } }
.agent-form { flex: none; padding: 10px 12px 8px; border-top: 1px solid var(--line); border-bottom: 0; background: var(--panel); }
.advanced { display: block; }
.advanced[open] { display: grid; }
.advanced label { margin-top: 5px; }
.composer { display: flex; align-items: flex-end; gap: 6px; padding: 5px; border: 1px solid var(--line); border-radius: 11px; background: var(--wash); }
.agent-form .composer textarea { flex: 1; min-height: 43px; max-height: 130px; resize: vertical; border: 0; background: transparent; padding: 8px; font-size: 12px; line-height: 1.5; }
.agent-form .composer textarea:focus-visible { outline: 0; }
.composer:focus-within { outline: 2px solid var(--blue); outline-offset: 1px; }
.send-button { flex: none; display: grid; place-items: center; width: 34px; height: 34px; border: 0; border-radius: 8px; background: var(--blue); color: #062032; cursor: pointer; }
.send-button:disabled { opacity: .45; cursor: not-allowed; }
.composer-hint { margin: 0; text-align: right; }
@media (prefers-reduced-motion: reduce) { .typing-dots i { animation: none; } .chevron { transition: none; } }
</style>
