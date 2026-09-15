<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue'
import {
  fetchAgentAnalyze,
  describeApiError,
  AgentRequestError,
  type AgentAnalyzeResponse,
  type AgentEvidence,
} from '../api'

// 智能体问答是独立异步请求：不放入 computed，由本组件管理加载/取消/超时/错误状态。
// 前端 75 秒超时覆盖后端 60 秒预算，与新闻查询的 20 秒惯例无关（见 api.ts fetchAgentAnalyze）。
const question = ref('')
const closureAt = ref('')
const endAt = ref('')
const loading = ref(false)
const result = ref<AgentAnalyzeResponse | null>(null)
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
}

function agentErrorMessage(e: unknown): string {
  if (e instanceof AgentRequestError) {
    const friendly: Record<string, string> = {
      INVALID_REQUEST: '请求参数不合法：请检查问题长度及封锁时间格式（须带时区，窗口不超过 24 小时）。',
      AGENT_UNAVAILABLE: '智能体模型未配置或暂不可用，请稍后重试。',
      AGENT_TIMEOUT: '智能体处理超时，请缩小问题范围或稍后重试。',
      AGENT_INVALID_RESPONSE: '智能体回答不符合契约，请重试。',
      DATA_QUERY_FAILED: '数据查询失败，请稍后重试。',
    }
    return friendly[e.code] ?? e.message
  }
  return describeApiError(e, '智能体请求失败')
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
  result.value = null
  try {
    const response = await fetchAgentAnalyze(
      {
        question: question.value.trim(),
        closure_at: parseTime(closureAt.value),
        end_at: parseTime(endAt.value),
      },
      controller.signal,
    )
    if (request === controller && !controller.signal.aborted) result.value = response
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
  result.value = null
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

onBeforeUnmount(() => request?.abort())
</script>

<template>
  <section class="panel-content agent-panel">
    <header class="panel-heading">
      <h2>智能体问答</h2>
      <p>向智能体提问封锁窗口内的海峡通行情况；回答附带船只与证据编号。</p>
      <p class="caption">船位为教学模拟数据，非真实 AIS；结论不代表真实船舶动态。</p>
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
          {{ loading ? '智能体分析中…' : '提问' }}
        </button>
        <button v-if="loading" type="button" @click="cancel">取消</button>
        <button v-if="result || error" type="button" @click="reset">清空结果</button>
      </div>
    </form>

    <p v-if="notice" class="empty" role="status">{{ notice }}</p>
    <div v-if="loading" class="empty" role="status">正在等待智能体回答（最长约 75 秒）…</div>
    <div v-else-if="error" class="empty error" role="alert">
      {{ error }}<span v-if="errorRequestId" class="request-id">请求标识：{{ errorRequestId }}</span>
    </div>

    <article v-if="result" class="agent-result">
      <div class="result-head">
        <span class="status-badge" :data-tone="statusMeta[result.status]?.tone ?? 'info'">
          {{ statusMeta[result.status]?.label ?? result.status }}
        </span>
        <span class="request-id">请求标识：{{ result.request_id }}</span>
      </div>

      <p v-if="result.status === 'needs_clarification' && result.clarification" class="clarification">
        {{ result.clarification }}
      </p>
      <section v-if="result.answer" class="answer-block">
        <h3>回答</h3>
        <p class="answer-text">{{ result.answer }}</p>
      </section>

      <section class="facts-block">
        <h3>查询上下文</h3>
        <dl class="facts">
          <div><dt>批次</dt><dd>{{ result.context.batch }}</dd></div>
          <div><dt>封锁窗口</dt><dd>{{ formatUtc(result.context.closure_at) }} — {{ formatUtc(result.context.end_at) }}</dd></div>
          <div><dt>封锁时间来源</dt><dd>{{ result.context.closure_source }}</dd></div>
          <div><dt>船位来源</dt><dd>{{ result.context.ship_data_source }}</dd></div>
          <div><dt>通行规则</dt><dd>{{ result.context.passage_rule }}</dd></div>
        </dl>
      </section>

      <section v-if="result.query_summary" class="facts-block">
        <h3>查询统计</h3>
        <p class="summary-line">
          报位 {{ result.query_summary.position_count }} 条 · 匹配船只 {{ result.query_summary.matched_ship_count }} 艘 ·
          通行 {{ result.query_summary.passage_count }} 次 · 不确定候选 {{ result.query_summary.uncertain_candidate_count }} 个
          <template v-if="result.query_summary.coverage_start && result.query_summary.coverage_end">
            · 覆盖 {{ formatUtc(result.query_summary.coverage_start) }} — {{ formatUtc(result.query_summary.coverage_end) }}
          </template>
          <template v-if="result.query_summary.truncated"> · 结果已截断</template>
        </p>
      </section>

      <section v-if="result.ships.length" class="facts-block">
        <h3>船只（{{ result.ships.length }}）</h3>
        <ul class="ship-list">
          <li v-for="ship in result.ships" :key="ship.ship_id">
            <strong>{{ ship.name }}</strong>
            <span>ID {{ ship.ship_id }} · 通行 {{ ship.passage_count }} 次</span>
          </li>
        </ul>
      </section>

      <section v-if="result.evidence.length" class="facts-block">
        <h3>通行证据（{{ result.evidence.length }}）</h3>
        <ul class="evidence-list">
          <li v-for="item in result.evidence" :key="item.evidence_id">
            <strong>[{{ item.evidence_id }}]</strong> 船 ID {{ item.ship_id }} · 方向 {{ directionLabel(item.direction) }}
            · 观测完成 {{ formatUtc(item.observed_completion_at) }}
            <span class="fix-line">起始侧报位：{{ fixText(item.start_fix) }}</span>
            <span class="fix-line">完成侧报位：{{ fixText(item.completion_fix) }}</span>
          </li>
        </ul>
      </section>

      <section v-if="result.limitations.length" class="facts-block">
        <h3>限制说明</h3>
        <ul class="limitation-list">
          <li v-for="(item, index) in result.limitations" :key="index">{{ item }}</li>
        </ul>
      </section>
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
  padding-top: 12px;
}
.agent-result h3 {
  font-size: 14px;
  font-weight: 650;
  padding-bottom: 4px;
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
.limitation-list {
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
  gap: 10px;
  flex-wrap: wrap;
}
.ship-list span {
  color: var(--muted, #9fc2e0);
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
