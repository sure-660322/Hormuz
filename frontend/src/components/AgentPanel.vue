<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue'
import {
  fetchAgentAnalyze,
  describeApiError,
  AgentRequestError,
  type AgentAnalyzeResponse,
  type AgentEvidence,
  type AgentTurn,
  type AgentToolEventContextResult,
  type AgentToolShipSearchResult,
  type AgentToolShipTrackResult,
  type AgentToolAnalyticsResult,
} from '../api'
import { eventKind } from '../domain/maritime'

// 智能体问答是独立异步请求：不放入 computed，由本组件管理加载/取消/超时/错误状态。
// 前端 75 秒超时覆盖后端 60 秒预算，与新闻查询的 20 秒惯例无关（见 api.ts fetchAgentAnalyze）。
// 多轮：已完成轮次保留在 turns 中，提交时携带最近 10 轮 history（契约 v4）。
const emit = defineEmits<{
  'locate-ship': [shipId: number]
  'locate-event': [eventId: string]
}>()

interface AgentTurnState {
  question: string
  response: AgentAnalyzeResponse | null
}

const question = ref('')
const closureAt = ref('')
const endAt = ref('')
const loading = ref(false)
const turns = ref<AgentTurnState[]>([])
const error = ref('')
const errorRequestId = ref('')
const notice = ref('')
let request: AbortController | null = null

const canSubmit = computed(() => question.value.trim().length > 0 && !loading.value)

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

function parseTime(value: string): string | null {
  const trimmed = value.trim()
  return trimmed ? trimmed : null
}

async function submit() {
  if (!canSubmit.value) return
  request?.abort()
  const controller = new AbortController()
  request = controller
  loading.value = true
  error.value = ''
  errorRequestId.value = ''
  notice.value = ''
  const asked = question.value.trim()
  try {
    const response = await fetchAgentAnalyze(
      {
        question: asked,
        closure_at: parseTime(closureAt.value),
        end_at: parseTime(endAt.value),
        history: buildHistory(),
      },
      controller.signal,
    )
    if (request === controller && !controller.signal.aborted) {
      turns.value.push({ question: asked, response })
      question.value = ''
    }
  } catch (e) {
    if (request === controller && !controller.signal.aborted) {
      if (e instanceof AgentRequestError) errorRequestId.value = e.requestId
      error.value = agentErrorMessage(e)
    }
  } finally {
    if (request === controller) loading.value = false
  }
}

function cancel() {
  request?.abort()
  loading.value = false
  notice.value = '已取消本次智能体请求。'
}

function reset() {
  request?.abort()
  loading.value = false
  turns.value = []
  error.value = ''
  errorRequestId.value = ''
  notice.value = ''
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

onBeforeUnmount(() => request?.abort())
</script>

<template>
  <section class="panel-content agent-panel">
    <header class="panel-heading">
      <p>向智能体提问海峡通行、模拟船轨迹或新闻事件；回答附带船只、证据或报道来源。</p>
      <p class="caption">船位为教学模拟数据，非真实 AIS；新闻事件为真实报道聚合，两者相互独立。</p>
    </header>

    <form class="agent-form" @submit.prevent="submit">
      <label class="question-label">
        问题（必填）
        <textarea
          v-model="question"
          rows="3"
          maxlength="2000"
          placeholder="例如：封锁后有哪些船还通过了海峡？"
          aria-label="智能体问题"
        ></textarea>
      </label>
      <details class="advanced">
        <summary>高级：封锁窗口（可留空，留空用后端默认）</summary>
        <label>
          封锁开始时间
          <input v-model="closureAt" type="text" placeholder="默认 2026-02-28T15:00:00Z" aria-label="封锁开始时间" />
        </label>
        <label>
          封锁结束时间
          <input v-model="endAt" type="text" placeholder="默认 2026-03-01T15:00:00Z" aria-label="封锁结束时间" />
        </label>
        <p class="caption">时间须带时区（如 2026-03-01T00:00:00Z），窗口不超过 24 小时。</p>
      </details>
      <div class="actions">
        <button type="submit" class="primary" :disabled="!canSubmit">
          {{ loading ? '智能体分析中…' : turns.length ? '继续提问' : '提问' }}
        </button>
        <button v-if="loading" type="button" @click="cancel">取消</button>
        <button v-if="turns.length || error" type="button" @click="reset">清空对话</button>
      </div>
    </form>

    <p v-if="notice" class="empty" role="status">{{ notice }}</p>
    <div v-if="loading" class="empty" role="status">正在等待智能体回答（最长约 75 秒）…</div>
    <div v-else-if="error" class="empty error" role="alert">
      {{ error }}<span v-if="errorRequestId" class="request-id">请求标识：{{ errorRequestId }}</span>
    </div>

    <article v-for="(turn, turnIndex) in turns" :key="turnIndex" class="agent-result">
      <p class="turn-question">{{ turn.question }}</p>
      <template v-if="turn.response">
        <div class="result-head">
          <span class="status-badge" :data-tone="statusMeta[turn.response.status]?.tone ?? 'info'">
            {{ statusMeta[turn.response.status]?.label ?? turn.response.status }}
          </span>
          <span v-for="tool in turn.response.tools_used" :key="tool" class="tool-chip">
            {{ toolLabels[tool] ?? tool }}
          </span>
          <span class="request-id">请求标识：{{ turn.response.request_id }}</span>
        </div>

        <p v-if="turn.response.status === 'needs_clarification' && turn.response.clarification" class="clarification">
          {{ turn.response.clarification }}
        </p>
        <section v-if="turn.response.answer" class="answer-block">
          <h3>回答</h3>
          <p class="answer-text">{{ turn.response.answer }}</p>
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

        <section class="facts-block">
          <h3>查询上下文</h3>
          <dl class="facts">
            <div><dt>批次</dt><dd>{{ turn.response.context.batch }}</dd></div>
            <div><dt>封锁窗口</dt><dd>{{ formatUtc(turn.response.context.closure_at) }} — {{ formatUtc(turn.response.context.end_at) }}</dd></div>
            <div><dt>封锁时间来源</dt><dd>{{ turn.response.context.closure_source }}</dd></div>
            <div><dt>船位来源</dt><dd>{{ turn.response.context.ship_data_source }}</dd></div>
            <div><dt>通行规则</dt><dd>{{ turn.response.context.passage_rule }}</dd></div>
          </dl>
        </section>

        <section v-if="turn.response.query_summary" class="facts-block">
          <h3>查询统计</h3>
          <p class="summary-line">
            报位 {{ turn.response.query_summary.position_count }} 条 · 匹配船只 {{ turn.response.query_summary.matched_ship_count }} 艘 ·
            通行 {{ turn.response.query_summary.passage_count }} 次 · 不确定候选 {{ turn.response.query_summary.uncertain_candidate_count }} 个
            <template v-if="turn.response.query_summary.coverage_start && turn.response.query_summary.coverage_end">
              · 覆盖 {{ formatUtc(turn.response.query_summary.coverage_start) }} — {{ formatUtc(turn.response.query_summary.coverage_end) }}
            </template>
            <template v-if="turn.response.query_summary.truncated"> · 结果已截断</template>
          </p>
        </section>

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
          <p class="caption">新闻事件为真实报道聚合，与模拟船相互独立。</p>
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
                  <a :href="story.url" target="_blank" rel="noopener">{{ story.title_zh }}</a>
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
      </template>
    </article>
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
</style>
