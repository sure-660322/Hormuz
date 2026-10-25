<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import type { ApiMaritimeCase, ApiTrackWindow, MaritimeCaseId } from '../api'
import { safeNewsUrl } from '../domain/maritime'
import CaseSpeedPlot from './CaseSpeedPlot.vue'
const props = defineProps<{ caseId: MaritimeCaseId; data: ApiMaritimeCase | null; activeStage: string; loading: boolean; error: string; active: boolean; pointsVisible: boolean; stageStatus?: string; track: ApiTrackWindow | null; at: string | null; playing: boolean; playbackStageId?: string | null; playbackFinished?: boolean }>()
const emit = defineEmits<{ switchCase: [id: MaritimeCaseId]; select: [id: string]; close: []; retry: []; exit: []; togglePoints: []; play: [id: string]; pause: []; seek: [at: string]; locate: [at: string] }>()
const failedImages = ref(new Set<string>())
const navigation = computed(() => props.data?.stages.filter(s => s.id !== 'confirmation') ?? [])
const stage = computed(() => props.data?.stages.find(s => s.id === props.activeStage))
const followup = computed(() => props.data?.stages.find(s => s.id === 'confirmation'))
function imageFailed(url: string) { failedImages.value = new Set([...failedImages.value, url]) }
const isArctic = computed(() => props.caseId === 'arctic-ocean')
const displayTitle = computed(() => props.data?.display_title ?? (isArctic.value ? '中海北冰洋' : 'ATHE NOVA'))
const stageIndex = computed(() => navigation.value.findIndex(s => s.id === props.activeStage))
const playbackStage = computed(() => navigation.value.find(s => s.id === props.playbackStageId))
const period = computed(() => ({ from: stage.value?.start_at ?? props.data?.start_at, to: stage.value?.end_at ?? props.data?.end_at }))
const ready = computed(() => props.active && !!props.track && !props.loading && !props.error)
function stageDate(id: string, date: string) {
  return isArctic.value && id === 'waiting' ? '03.28–03.29' : date.slice(5).replace('-', '.')
}

// issue #55：「过程 / 证据」只是阅读视图。切换页签不改案例、阶段、时间、播放状态或地图选择，
// 两个视图各自保留滚动位置。
type CaseView = 'process' | 'evidence'
const view = ref<CaseView>('process')
const contentEl = ref<HTMLElement | null>(null)
const tabProcessEl = ref<HTMLElement | null>(null)
const tabEvidenceEl = ref<HTMLElement | null>(null)
const scrollTops: Record<CaseView, number> = { process: 0, evidence: 0 }
function setView(next: CaseView) {
  if (view.value === next) return
  scrollTops[view.value] = contentEl.value?.scrollTop ?? 0
  view.value = next
}
watch(view, async next => {
  await nextTick()
  if (contentEl.value) contentEl.value.scrollTop = scrollTops[next]
})
const VIEW_ORDER: CaseView[] = ['process', 'evidence']
function onTabKeydown(event: KeyboardEvent) {
  const index = VIEW_ORDER.indexOf(view.value)
  let next = -1
  if (event.key === 'ArrowRight') next = (index + 1) % VIEW_ORDER.length
  else if (event.key === 'ArrowLeft') next = (index + VIEW_ORDER.length - 1) % VIEW_ORDER.length
  if (next < 0) return
  event.preventDefault()
  setView(VIEW_ORDER[next])
  ;(VIEW_ORDER[next] === 'process' ? tabProcessEl : tabEvidenceEl).value?.focus()
}
// 长摘要默认收起（约三行）并提供「展开摘要」，不用 CSS 截断制造不可读内容。
const SUMMARY_LIMIT = 66
const summaryExpanded = ref(false)
const summaryText = computed(() => stage.value?.summary ?? props.data?.overview_summary ?? '沿历史航迹查看航行过程；报道与AIS分别提供证据。')
const summaryLong = computed(() => summaryText.value.length > SUMMARY_LIMIT)
const summaryShown = computed(() => (!summaryLong.value || summaryExpanded.value) ? summaryText.value : summaryText.value.slice(0, SUMMARY_LIMIT) + '…')
// 切阶段后摘要回到阅读位置（过程视图内容区顶部），收起上一阶段的摘要展开状态与定位反馈。
watch(() => props.activeStage, async () => {
  summaryExpanded.value = false
  locatedKey.value = null
  await nextTick()
  if (view.value === 'process' && contentEl.value) contentEl.value.scrollTop = 0
})
// 切换案例：回到新案例的过程视图与全程概况，清空本地阅读状态；旧案例的响应已由 App 侧版本号拦截。
watch(() => props.caseId, async () => {
  view.value = 'process'
  summaryExpanded.value = false
  scopeChoice.value = 'auto'
  locatedKey.value = null
  scrollTops.process = 0
  scrollTops.evidence = 0
  await nextTick()
  if (contentEl.value) contentEl.value.scrollTop = 0
})

// ---------------------------------------------------------------------------
// issue #56：证据视图。每条证据有稳定 key、明确类型与适用范围；
// 报道由各阶段文章按 url 去重合成，同一报道不因多个阶段引用而重复铺开。
type EvidenceKind = 'ais_observation' | 'report' | 'boundary' | 'identity'
interface EvidenceRow {
  key: string; kind: EvidenceKind; title: string; summary: string
  observation: string; boundary: string; at: string | null
  url: string | undefined; stageIds: string[]
  article: ApiMaritimeCase['stages'][number]['articles'][number] | null
}
const KIND_ORDER: EvidenceKind[] = ['ais_observation', 'report', 'boundary', 'identity']
const KIND_LABEL: Record<EvidenceKind, string> = { ais_observation: 'AIS观测', report: '报道', boundary: '结论边界', identity: '身份与数据资料' }
const evidenceRows = computed<EvidenceRow[]>(() => {
  if (!props.data) return []
  const rows: EvidenceRow[] = (props.data.evidence ?? []).map(item => ({
    key: item.id, kind: item.kind, title: item.title,
    summary: item.summary || item.observation,
    observation: item.observation, boundary: item.boundary,
    at: item.at, url: safeNewsUrl(item.url ?? ''), stageIds: [...item.stage_ids], article: null,
  }))
  const byUrl = new Map<string, EvidenceRow>()
  for (const item of props.data.stages) {
    for (const article of item.articles) {
      const existing = byUrl.get(article.url)
      if (existing) {
        if (!existing.stageIds.includes(item.id)) existing.stageIds.push(item.id)
        continue
      }
      const row: EvidenceRow = {
        key: `article:${article.url}`, kind: 'report', title: article.title,
        summary: article.summary || article.media,
        observation: article.summary || article.title,
        boundary: '报道提供事件叙述，发布日期不是精确事件时刻；不与AIS观测自动互证。',
        at: null, url: safeNewsUrl(article.url), stageIds: [item.id], article,
      }
      byUrl.set(article.url, row)
      rows.push(row)
    }
  }
  return rows
})
// 范围：默认跟随当前阶段（全程概况 → 全部）；用户手动切换后保持选择，直到换案例或再次从「查看相关证据」进入。
type ScopeChoice = 'auto' | 'stage' | 'all'
const scopeChoice = ref<ScopeChoice>('auto')
const scope = computed<'stage' | 'all'>(() => scopeChoice.value === 'auto' ? (stage.value ? 'stage' : 'all') : scopeChoice.value)
const scopeLabel = computed(() => scope.value === 'all'
  ? (stage.value ? '全部阶段' : '案例全部')
  : `当前阶段 · ${stage.value?.title ?? ''}`)
const scopedRows = computed(() => {
  if (scope.value === 'all' || !stage.value) return evidenceRows.value
  const id = stage.value.id
  return evidenceRows.value.filter(row => row.stageIds.length === 0 || row.stageIds.includes(id))
})
const groupedRows = computed(() =>
  KIND_ORDER.map(kind => ({ kind, label: KIND_LABEL[kind], rows: scopedRows.value.filter(row => row.kind === kind) }))
    .filter(group => group.rows.length))
const reportCountInScope = computed(() => scopedRows.value.filter(row => row.kind === 'report').length)
function stageName(id: string) {
  const item = props.data?.stages.find(s => s.id === id)
  return item ? `${stageDate(item.id, item.date)} ${item.title}` : id
}
function metaLabel(row: EvidenceRow) {
  if (row.kind === 'ais_observation' && row.at) return atLabel(row.at)
  if (row.kind === 'report' && row.article) return `${row.article.publish_date} · ${row.article.media}`
  return row.stageIds.length ? row.stageIds.map(stageName).join('；') : '适用于整个案例'
}
function atLabel(at: string) {
  // 观测时刻是 UTC 事实（如 2026-03-02T08:16:26Z），固定显示为 03.02 08:16 UTC。
  return `${at.slice(5, 10).replace('-', '.')} ${at.slice(11, 16)} UTC`
}
// AIS 证据定位：只有具备明确观测时刻且落在可定位范围内才提供「定位地图」；
// 缺报、范围外、轨迹未加载都给具体原因，不用相邻点冒充定位成功。
function locateInfo(row: EvidenceRow): { ok: boolean; reason: string } {
  if (row.kind !== 'ais_observation' || !row.at) return { ok: false, reason: '' }
  if (!props.data?.ready) return { ok: false, reason: '轨迹尚未导入，无法定位。' }
  if (props.error) return { ok: false, reason: `轨迹加载失败：${props.error}` }
  if (props.loading) return { ok: false, reason: '轨迹加载中，请稍后重试。' }
  if (!props.track) return { ok: false, reason: '轨迹未加载，先在过程视图查看轨迹。' }
  const at = Date.parse(row.at), from = Date.parse(props.track.from), to = Date.parse(props.track.to)
  if (!Number.isFinite(at) || at < from || at > to) return { ok: false, reason: '该观测时刻超出本案例轨迹覆盖范围。' }
  const gap = props.track.gaps.find(item => Date.parse(item.from) < at && at < Date.parse(item.to))
  if (gap) return { ok: false, reason: `该时刻处于缺报区间（约${Math.round(gap.minutes / 60)}小时），无法定位。` }
  return { ok: true, reason: '' }
}
const locatedKey = ref<string | null>(null)
function locate(row: EvidenceRow) {
  if (!locateInfo(row).ok || !row.at) return
  locatedKey.value = row.key
  // 执行时暂停当前播放；App 侧版本号保证快速连续点击时最后一次选择生效。
  emit('pause')
  emit('locate', row.at)
}
// 过程视图 → 证据视图：切到证据视图、按当前阶段筛选并把证据列表带到阅读位置。
function showStageEvidence() {
  scopeChoice.value = 'auto'
  scrollTops.evidence = 0
  setView('evidence')
}
</script>

<template>
  <aside class="case-panel" :aria-label="`${displayTitle}案例`">
    <header class="case-head">
      <div class="case-head-row">
        <select class="case-switch" :value="caseId" :disabled="loading" aria-label="切换案例" @change="$emit('switchCase', ($event.target as HTMLSelectElement).value as MaritimeCaseId)">
          <option value="arctic-ocean">中海北冰洋</option>
          <option value="athe-nova">ATHE NOVA</option>
        </select>
        <div class="case-head-actions">
          <button type="button" class="case-dock-toggle" @click="$emit('close')">收起</button>
          <button type="button" class="case-exit" @click="$emit('exit')">退出案例</button>
        </div>
      </div>
      <div class="case-sub-row">
        <small class="case-dates">{{ data?.date_label ?? (isArctic ? '2026.03.27 — 03.31' : '2026.02.25 — 03.03') }} / 北京时间</small>
        <details v-if="data" class="case-vessel">
          <summary>船舶资料</summary>
          <p>{{ data.vessel_label ?? (isArctic ? '集装箱船 · CSCL ARCTIC OCEAN' : '沥青船（平台分类） · ATHE NOVA') }}</p>
          <p>MMSI {{ data.mmsi }} · IMO {{ data.imo }}</p>
          <p>船型来源：{{ data.data_source }}；{{ data.supplier }}</p>
          <p>{{ data.position_count.toLocaleString() }} 条源报位<template v-if="data.start_at && data.end_at"> · {{ data.start_at.slice(0, 10) }} 至 {{ data.end_at.slice(0, 10) }}</template></p>
        </details>
      </div>
    </header>
    <div class="case-tabs" role="tablist" aria-label="案例阅读视图">
      <button
        ref="tabProcessEl"
        type="button"
        role="tab"
        id="case-tab-process"
        aria-controls="case-view-process"
        :aria-selected="view === 'process'"
        :tabindex="view === 'process' ? 0 : -1"
        @click="setView('process')"
        @keydown="onTabKeydown"
      >过程</button>
      <button
        ref="tabEvidenceEl"
        type="button"
        role="tab"
        id="case-tab-evidence"
        aria-controls="case-view-evidence"
        :aria-selected="view === 'evidence'"
        :tabindex="view === 'evidence' ? 0 : -1"
        @click="setView('evidence')"
        @keydown="onTabKeydown"
      >证据</button>
    </div>
    <div ref="contentEl" class="case-content">
      <p v-if="loading" role="status">正在加载完整案例…</p>
      <p v-if="error" role="alert">{{ error }} <button @click="$emit('retry')">重试</button></p>
      <template v-if="data">
        <p v-if="!data.ready" role="status">{{ data.unavailable_reason ?? '轨迹尚未导入，可先阅读报道。' }}</p>
        <div v-show="view === 'process'" id="case-view-process" role="tabpanel" aria-labelledby="case-tab-process">
          <div class="case-view-controls">
            <button :class="{ active: activeStage === 'overview' }" :aria-pressed="activeStage === 'overview'" :disabled="loading" @click="$emit('select', 'overview')"><strong>全程</strong><span>完整轨迹与全部阶段</span></button>
          </div>
          <nav class="case-stages" aria-label="航行阶段">
            <button
              v-for="item in navigation"
              :key="item.id"
              :class="{ active: activeStage === item.id, 'playback-current': playbackStageId === item.id }"
              :aria-current="playbackStageId === item.id || activeStage === item.id ? 'step' : undefined"
              :disabled="loading"
              @click="$emit('select', item.id)"
            >
              <span class="case-step-copy"><span class="case-step-date">{{ stageDate(item.id, item.date) }}<span v-if="playbackStageId === item.id" class="case-step-progress">{{ playing ? '正在经过' : '播放至此' }}</span></span><strong>{{ item.title }}</strong></span><span class="step-arrow" aria-hidden="true">›</span>
            </button>
          </nav>
          <p v-if="playbackFinished" class="case-playback-complete" role="status"><strong>播放完成</strong><span>点击上方阶段可细看对应过程与证据。</span></p>
          <p v-else-if="playbackStage" class="case-playback-caption" role="status">{{ playing ? '正在经过' : '已暂停于' }}：{{ playbackStage.title }}</p>
          <section class="case-detail" aria-live="polite">
            <div class="detail-heading"><span>{{ stage && stageIndex >= 0 ? `第 ${stageIndex + 1} 段 / 共 ${navigation.length} 段` : '案例概况' }}</span><span>{{ stage ? stageDate(stage.id, stage.date) : (isArctic ? '03.27–31' : '02.25–03.03') }}</span></div>
            <h3>{{ stage?.title ?? (isArctic ? '首次折返与再次通过' : '报道、缺报与后续观测') }}</h3>
            <p class="case-summary">{{ summaryShown }}<button v-if="summaryLong" type="button" class="summary-toggle" @click="summaryExpanded = !summaryExpanded">{{ summaryExpanded ? '收起摘要' : '展开摘要' }}</button></p>
            <p class="case-note">断线表示缺报，不代表停船或消失；阶段日期是浏览窗口。</p>
            <div class="case-play-actions"><button class="primary" :disabled="!ready" @click="playing ? $emit('pause') : $emit('play', activeStage)">{{ playing ? '暂停回放' : stage ? '从本段开始播放' : '从故事起点播放' }}</button><button :disabled="!ready" @click="$emit('select', activeStage)">查看{{ stage ? '本段' : '完整' }}轨迹</button><button @click="showStageEvidence">查看相关证据</button></div>
            <p v-if="stageStatus" class="case-stage-status" role="status">{{ stageStatus }}</p>
            <div class="case-legend"><span><i class="legend-full" />完整观测轨迹</span><span><i />{{ stage ? '本段' : '故事' }}已回放 · 航速着色</span><label><input type="checkbox" :checked="pointsVisible" @change="$emit('togglePoints')">报位点</label></div>
          </section>
          <details v-if="period.from && period.to" class="case-speed">
            <summary>航速与观测<span>曲线与采样说明按需展开</span></summary>
            <CaseSpeedPlot :track="track" :from="period.from" :to="period.to" :at="at" :disabled="!ready" @seek="$emit('seek', $event)" />
          </details>
        </div>
        <div v-show="view === 'evidence'" id="case-view-evidence" role="tabpanel" aria-labelledby="case-tab-evidence">
          <div class="evidence-toolbar">
            <div class="evidence-scope-row">
              <span class="evidence-scope-label">范围：{{ scopeLabel }}</span>
              <button type="button" class="evidence-back" @click="setView('process')">返回过程</button>
            </div>
            <div class="evidence-scope-switch" role="group" aria-label="证据范围">
              <button type="button" :class="{ active: scope === 'stage' }" :aria-pressed="scope === 'stage'" :disabled="!stage" @click="scopeChoice = 'stage'">当前阶段</button>
              <button type="button" :class="{ active: scope === 'all' }" :aria-pressed="scope === 'all'" @click="scopeChoice = 'all'">全部</button>
            </div>
            <p v-if="scope === 'stage'" class="evidence-scope-note">同时列出案例级证据（适用于整个案例）。</p>
          </div>
          <p v-if="!data.ready" role="status" class="case-note">{{ data.unavailable_reason ?? '轨迹尚未导入，可先阅读报道；AIS证据定位不可用。' }}</p>
          <p v-if="!scopedRows.length" class="case-empty" role="status"><strong>这个范围没有登记的证据</strong><span>可切换到「全部」查看案例级资料与全部报道。</span></p>
          <section v-for="group in groupedRows" :key="group.kind" class="evidence-group">
            <h3>{{ group.label }}<span>{{ group.rows.length }}</span></h3>
            <article v-for="row in group.rows" :key="row.key" class="evidence-row" :class="{ locating: locatedKey === row.key }">
              <div class="evidence-row-head"><strong>{{ row.title }}</strong><span v-if="!row.stageIds.length" class="evidence-case-tag">适用于整个案例</span><span v-else-if="locatedKey === row.key" class="evidence-located-tag" role="status">已定位</span></div>
              <p class="evidence-row-meta">{{ metaLabel(row) }}</p>
              <p class="evidence-row-summary">{{ row.summary }}</p>
              <div class="evidence-row-actions">
                <template v-if="row.kind === 'ais_observation' && row.at">
                  <button v-if="locateInfo(row).ok" type="button" class="locate-btn" @click="locate(row)">定位地图</button>
                  <span v-else class="evidence-cant" role="status">{{ locateInfo(row).reason }}</span>
                </template>
                <a v-if="row.url" :href="row.url" target="_blank" rel="noopener noreferrer">阅读原文 ↗</a>
                <span v-else-if="row.kind === 'report'" class="evidence-cant">来源链接不可用</span>
                <details class="evidence-detail">
                  <summary>展开详情</summary>
                  <p class="evidence-detail-text">{{ row.observation }}</p>
                  <p v-if="row.boundary" class="evidence-boundary">{{ row.boundary }}</p>
                  <p class="evidence-stages">{{ row.stageIds.length ? `适用阶段：${row.stageIds.map(stageName).join('；')}` : '适用阶段：整个案例' }}</p>
                  <template v-if="row.article">
                    <img v-if="row.article.image_url && !failedImages.has(row.article.url)" :src="row.article.image_url" alt="原文配图，非船舶身份依据" loading="lazy" referrerpolicy="no-referrer" @error="imageFailed(row.article.url)">
                    <p v-if="row.article.image_url" class="image-note">配图来自对应原文，仅作报道配图，非船舶身份依据；加载失败时不影响阅读。</p>
                  </template>
                </details>
              </div>
            </article>
          </section>
          <p v-if="scope === 'stage' && !reportCountInScope" class="case-empty"><strong>本阶段无单独报道</strong><span>可查看AIS观测或切换到「全部」证据。</span></p>
          <section v-if="!stage && followup" class="case-followup"><small>03.31 / 后续回应</small><h3>后续报道</h3><p>{{ followup.summary }}</p></section>
          <details class="case-limitations" open>
            <summary>观测缺口与证据边界</summary>
            <p>轨迹断线表示缺报，不代表停船或消失。阶段日期是浏览窗口，不是精确事件时刻。</p>
            <p v-for="note in data.limitations" :key="note">{{ note }}</p>
          </details>
        </div>
      </template>
    </div>
  </aside>
</template>

<style scoped>
.case-panel { display: flex; flex-direction: column; height: 100%; width: 340px; flex: none; background: var(--panel); color: var(--ink); border-right: 1px solid var(--line); z-index: 1050; scrollbar-width: thin; scrollbar-color: var(--subtle) transparent }
.case-head { flex: none; padding: 14px 16px 10px; border-bottom: 1px solid var(--line) }
.case-head-row { display: flex; align-items: center; gap: 8px }
.case-switch { flex: 1; min-width: 0; font-size: 15px; font-weight: 650; background: var(--wash); color: var(--ink); padding: 7px 9px }
.case-head-actions { display: flex; gap: 6px; flex: none }
.case-head-actions button { font-size: 12px; padding: 6px 9px }
.case-sub-row { display: flex; align-items: baseline; justify-content: space-between; gap: 10px; margin-top: 8px }
.case-dates { font-size: 11px; color: var(--muted); letter-spacing: .3px; flex: none }
.case-vessel { color: var(--muted); font-size: 12px; text-align: right }
.case-vessel summary { cursor: pointer; font-size: 12px }
.case-vessel p { margin: 7px 0 0; line-height: 1.7; font-size: 12px; text-align: left }
.case-tabs { flex: none; display: flex; border-bottom: 1px solid var(--line) }
.case-tabs button { flex: 1; border: 0; border-radius: 0; border-bottom: 2px solid transparent; padding: 9px 10px; background: transparent; color: var(--muted); font-size: 13px }
.case-tabs button:hover { background: var(--wash) }
.case-tabs button[aria-selected='true'] { color: var(--ink); border-bottom-color: #59c7bd; background: var(--wash) }
.case-content { flex: 1; min-height: 0; overflow-y: auto; padding: 0 16px 16px; scrollbar-width: thin; scrollbar-color: var(--subtle) transparent }
.case-view-controls { margin: 12px 0 6px }.case-view-controls button { width: 100%; display: flex; justify-content: space-between; align-items: center; gap: 8px; padding: 9px 10px; border-color: transparent; background: transparent }.case-view-controls button.active { border-color: var(--line); color: var(--ink); background: var(--wash) }.case-view-controls strong { font-size: 13px }.case-view-controls span { color: var(--muted); font-size: 11px }
.case-stages { display: flex; flex-direction: column; gap: 3px; border-bottom: 1px solid var(--line); padding-bottom: 12px }.case-stages button { display: flex; align-items: center; gap: 10px; padding: 8px 10px; border-color: transparent; background: transparent; text-align: left; transition: border-color var(--dur-feedback) var(--ease-out), background var(--dur-feedback) var(--ease-out) }.case-stages button.active { border-color: var(--line); background: var(--wash) }.case-step-copy { display: flex; align-items: baseline; gap: 8px; min-width: 0 }.case-step-date { font-size: 11px; color: var(--muted); flex: none }.case-stages strong { font-size: 13px; font-weight: 500; overflow-wrap: anywhere }.step-arrow { margin-left: auto; color: var(--muted); font-size: 18px; flex: none }.case-stages button.active .step-arrow { color: #59c7bd }
.case-detail { padding: 13px 0 12px; border-bottom: 1px solid var(--line) }
.detail-heading { display: flex; justify-content: space-between; color: var(--muted); font-size: 11px }
h3 { font-size: 15px; line-height: 1.6; margin: 6px 0 }
.case-summary { font-size: 13px; line-height: 1.7 }
.summary-toggle { border: 0; padding: 0 0 0 6px; font-size: 12px; color: #59c7bd; text-decoration: underline; text-underline-offset: 3px }
.summary-toggle:hover { background: transparent; border-color: transparent }
.case-note { margin-top: 6px; font-size: 11px; line-height: 1.6; color: var(--muted) }
.case-play-actions { display: flex; flex-wrap: wrap; gap: 7px; margin: 12px 0 0 }.case-play-actions button { font-size: 12px; padding: 8px 9px }.case-play-actions .primary { flex: 1; background: #59c7bd; border-color: #59c7bd; color: #102724; font-weight: 600 }.case-detail .case-stage-status { font-size: 11px; color: var(--muted); margin: 8px 0 0 }
.case-legend { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 9px; margin-top: 10px; color: var(--muted); font-size: 11px }.case-legend span { display: flex; align-items: center; gap: 4px }.case-legend i { width: 12px; height: 2px; background: linear-gradient(90deg, #66b99a, #dca653, #db6363) }.case-legend i.legend-full { background: #7a91a5; opacity: .6 }.case-legend label { display: flex; align-items: center; gap: 3px; margin-left: auto }
.case-speed summary { cursor: pointer; padding: 12px 0 0; font-size: 13px; display: flex; justify-content: space-between; gap: 8px; align-items: baseline }.case-speed summary span { color: var(--muted); font-size: 11px }
.evidence-toolbar { margin: 12px 0 4px; padding-bottom: 10px; border-bottom: 1px solid var(--line) }
.evidence-scope-row { display: flex; align-items: center; justify-content: space-between; gap: 8px }
.evidence-scope-label { font-size: 12px; color: var(--ink); font-weight: 600; min-width: 0; overflow-wrap: anywhere }
.evidence-back { font-size: 11px; padding: 5px 8px; flex: none }
.evidence-scope-switch { display: flex; gap: 6px; margin-top: 8px }
.evidence-scope-switch button { flex: 1; font-size: 12px; padding: 6px 8px }
.evidence-scope-switch button.active { background: var(--wash); border-color: var(--line); color: var(--ink); font-weight: 600 }
.evidence-scope-note { margin: 6px 0 0; font-size: 11px; color: var(--muted); line-height: 1.6 }
.evidence-group { border-bottom: 1px solid var(--line); padding-bottom: 4px }
.evidence-group h3 { display: flex; align-items: baseline; justify-content: space-between; font-size: 13px; margin: 12px 0 2px }
.evidence-group h3 span { font-size: 11px; color: var(--muted); font-weight: 400 }
.evidence-row { padding: 10px 0; border-bottom: 1px solid var(--line); font-size: 12px }
.evidence-row:last-child { border-bottom: 0 }
.evidence-row.locating { background: var(--wash) }
.evidence-row-head { display: flex; align-items: baseline; gap: 8px }
.evidence-row-head strong { font-size: 12.5px; font-weight: 600; min-width: 0; overflow-wrap: anywhere }
.evidence-case-tag, .evidence-located-tag { flex: none; font-size: 10.5px; color: var(--muted); border: 1px solid var(--line); border-radius: var(--radius-s); padding: 1px 6px }
.evidence-located-tag { color: #59c7bd; border-color: #59c7bd }
.evidence-row-meta { margin: 4px 0 0; font-size: 11px; color: var(--muted); line-height: 1.6; overflow-wrap: anywhere }
.evidence-row-summary { margin: 5px 0 0; line-height: 1.75 }
.evidence-row-actions { display: flex; flex-wrap: wrap; align-items: center; gap: 4px 10px; margin-top: 7px }
.evidence-row-actions a, .evidence-row-actions .locate-btn { font-size: 11px }
.evidence-cant { font-size: 11px; color: var(--muted); line-height: 1.6 }
.evidence-detail { width: 100%; margin-top: 4px }
.evidence-detail summary { cursor: pointer; font-size: 11px; color: #59c7bd; width: fit-content }
.evidence-detail-text { margin: 7px 0 0; line-height: 1.8; color: var(--ink); overflow-wrap: anywhere }
.evidence-boundary { margin: 6px 0 0; line-height: 1.8; color: var(--muted) }
.evidence-stages { margin: 6px 0 0; font-size: 11px; color: var(--muted); line-height: 1.7 }
.evidence-detail img { display: block; margin-top: 8px; max-width: 100%; border-radius: var(--radius-s) }
.image-note { margin: 6px 0 0; font-size: 11px; color: var(--muted); line-height: 1.7 }
.case-empty { display: flex; flex-direction: column; gap: 3px; margin: 12px 0; font-size: 12px; color: var(--muted); line-height: 1.8 }
.case-empty strong { font-weight: 500; color: var(--ink) }
.case-followup { margin: 18px 0; padding-left: 12px; border-left: 2px solid #59c7bd }.case-followup small { font-size: 11px; color: var(--muted) }.case-followup h3 { font-size: 13px }.case-followup p { font-size: 12px; line-height: 1.8 }
.case-limitations { margin-top: 16px; color: var(--muted) }.case-limitations summary { cursor: pointer; font-size: 12px }.case-limitations p { font-size: 12px; line-height: 1.8 }
button:disabled { opacity: .45; cursor: not-allowed }button:focus-visible, a:focus-visible, summary:focus-visible, input:focus-visible, select:focus-visible { outline: 2px solid var(--blue); outline-offset: 2px }
@media (max-height: 800px) {
  .case-head { padding: 9px 16px 7px }
  .case-switch { font-size: 14px; padding: 5px 8px }
  .case-sub-row { margin-top: 5px }
  .case-tabs button { padding: 6px 10px }
  .case-content { padding-bottom: 8px }
  .case-view-controls { margin: 5px 0 3px }
  .case-view-controls button { padding: 6px 10px }
  .case-stages { gap: 2px; padding-bottom: 8px }
  .case-stages button { padding: 3px 10px }
  .case-detail { padding: 6px 0 8px }
  h3 { margin: 3px 0; font-size: 14px }
  .case-summary { line-height: 1.65 }
  .case-note { margin-top: 4px }
  .case-play-actions { margin-top: 8px }
  .case-play-actions button { padding: 7px 9px }
  .case-legend { margin-top: 6px }
  .case-speed summary { padding-top: 4px; font-size: 12px }
  .case-speed summary span { font-size: 10px }
  .evidence-toolbar { margin-top: 8px; padding-bottom: 6px }
  .evidence-row { padding: 7px 0 }
}
@media (max-width: 760px) {
  .case-panel { position: absolute; left: 10px; right: 10px; top: auto; bottom: 10px; width: auto; height: auto; max-height: 56%; border: 1px solid var(--line); border-radius: var(--radius-l); border-right: 1px solid var(--line); box-shadow: var(--shadow-overlay) }
  .case-content { padding: 0 14px 14px }
}
@media (prefers-reduced-motion: reduce) { .case-stages button { transition: none } }
</style>
