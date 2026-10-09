<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import type { ApiMaritimeCase, ApiTrackWindow, MaritimeCaseId } from '../api'
import { safeNewsUrl } from '../domain/maritime'
import CaseSpeedPlot from './CaseSpeedPlot.vue'
const props = defineProps<{ caseId: MaritimeCaseId; data: ApiMaritimeCase | null; activeStage: string; loading: boolean; error: string; active: boolean; pointsVisible: boolean; stageStatus?: string; track: ApiTrackWindow | null; at: string | null; playing: boolean }>()
defineEmits<{ switchCase: [id: MaritimeCaseId]; select: [id: string]; close: []; retry: []; exit: []; togglePoints: []; play: [id: string]; pause: []; seek: [at: string] }>()
const failedImages = ref(new Set<string>())
const navigation = computed(() => props.data?.stages.filter(s => s.id !== 'confirmation') ?? [])
const stage = computed(() => props.data?.stages.find(s => s.id === props.activeStage))
const articles = computed(() => stage.value ? stage.value.articles : props.data?.stages.flatMap(s => s.articles) ?? [])
const followup = computed(() => props.data?.stages.find(s => s.id === 'confirmation'))
function imageFailed(url: string) { failedImages.value = new Set([...failedImages.value, url]) }
const isArctic = computed(() => props.caseId === 'arctic-ocean')
const displayTitle = computed(() => props.data?.display_title ?? (isArctic.value ? '中海北冰洋' : 'ATHE NOVA'))
const stageIndex = computed(() => navigation.value.findIndex(s => s.id === props.activeStage))
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
// 切阶段后摘要回到阅读位置（过程视图内容区顶部），收起上一阶段的摘要展开状态。
watch(() => props.activeStage, async () => {
  summaryExpanded.value = false
  await nextTick()
  if (view.value === 'process' && contentEl.value) contentEl.value.scrollTop = 0
})
// 切换案例：回到新案例的过程视图与全程概况，清空本地阅读状态；旧案例的响应已由 App 侧版本号拦截。
watch(() => props.caseId, async () => {
  view.value = 'process'
  summaryExpanded.value = false
  scrollTops.process = 0
  scrollTops.evidence = 0
  await nextTick()
  if (contentEl.value) contentEl.value.scrollTop = 0
})
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
              :class="{ active: activeStage === item.id }"
              :aria-current="activeStage === item.id ? 'step' : undefined"
              :disabled="loading"
              @click="$emit('select', item.id)"
            >
              <span class="case-step-copy"><span class="case-step-date">{{ stageDate(item.id, item.date) }}</span><strong>{{ item.title }}</strong></span><span class="step-arrow" aria-hidden="true">›</span>
            </button>
          </nav>
          <section class="case-detail" aria-live="polite">
            <div class="detail-heading"><span>{{ stage && stageIndex >= 0 ? `第 ${stageIndex + 1} 段 / 共 ${navigation.length} 段` : '案例概况' }}</span><span>{{ stage ? stageDate(stage.id, stage.date) : (isArctic ? '03.27–31' : '02.25–03.03') }}</span></div>
            <h3>{{ stage?.title ?? (isArctic ? '首次折返与再次通过' : '报道、缺报与后续观测') }}</h3>
            <p class="case-summary">{{ summaryShown }}<button v-if="summaryLong" type="button" class="summary-toggle" @click="summaryExpanded = !summaryExpanded">{{ summaryExpanded ? '收起摘要' : '展开摘要' }}</button></p>
            <p class="case-note">断线表示缺报，不代表停船或消失；阶段日期是浏览窗口。</p>
            <div class="case-play-actions"><button class="primary" :disabled="!ready" @click="playing ? $emit('pause') : $emit('play', activeStage)">{{ playing ? '暂停回放' : stage ? '从本段开始播放' : '从故事起点播放' }}</button><button :disabled="!ready" @click="$emit('select', activeStage)">查看{{ stage ? '本段' : '完整' }}轨迹</button></div>
            <p v-if="stageStatus" class="case-stage-status" role="status">{{ stageStatus }}</p>
            <div class="case-legend"><span><i class="legend-full" />完整观测轨迹</span><span><i />{{ stage ? '本段' : '故事' }}已回放 · 航速着色</span><label><input type="checkbox" :checked="pointsVisible" @change="$emit('togglePoints')">报位点</label></div>
          </section>
          <details v-if="period.from && period.to" class="case-speed">
            <summary>航速与观测<span>曲线与采样说明按需展开</span></summary>
            <CaseSpeedPlot :track="track" :from="period.from" :to="period.to" :at="at" :disabled="!ready" @seek="$emit('seek', $event)" />
          </details>
        </div>
        <div v-show="view === 'evidence'" id="case-view-evidence" role="tabpanel" aria-labelledby="case-tab-evidence">
          <p class="evidence-scope">本视图汇集当前案例的全部证据与报道，尚未按阶段关联；完成阶段映射前不把证据标注为「本段证据」。</p>
          <section v-if="data.evidence?.length" class="case-evidence">
            <h3>报道 / AIS / 不能确认</h3>
            <article v-for="item in data.evidence" :key="item.title">
              <strong>{{ item.title }}</strong><p v-if="item.at">{{ item.at.replace('T', ' ').replace('+00:00', ' UTC').replace('Z', ' UTC') }}</p><p>{{ item.observation }}</p><p class="evidence-label">{{ item.boundary }}</p>
              <button v-if="item.at" :disabled="!ready" @click="$emit('seek', item.at)">定位观测时间</button>
              <a v-if="item.url && safeNewsUrl(item.url)" :href="safeNewsUrl(item.url)!" target="_blank" rel="noopener noreferrer">阅读证据来源 ↗</a>
            </article>
          </section>
          <section class="case-report-section">
            <div class="report-heading"><h3>{{ stage ? '这一阶段的报道' : '报道与后续回应' }}</h3><span>{{ articles.length }} 篇</span></div>
            <p class="evidence-label">报道提供事件叙述，航迹提供位置观测；两者不自动证明因果。</p>
            <div v-if="!articles.length" class="case-empty"><strong>这一阶段没有单独点名报道</strong><p>先看航迹和观测缺口，或回到全程阅读相关报道。</p><button @click="$emit('select', 'overview')">查看全部报道</button></div>
            <a class="case-article" v-for="article in articles" :key="article.url" :href="safeNewsUrl(article.url) ?? undefined" target="_blank" rel="noopener noreferrer">
              <img v-if="article.image_url && !failedImages.has(article.url)" :src="article.image_url" alt="原文配图，非船舶身份依据" loading="lazy" referrerpolicy="no-referrer" @error="imageFailed(article.url)">
              <span v-else class="case-image-placeholder" aria-label="暂无配图">报道</span>
              <span class="case-article-copy"><small>{{ article.publish_date }} · {{ article.media }}</small><strong>{{ article.title }}</strong><span class="read-source">{{ safeNewsUrl(article.url) ? '阅读原文 ↗' : '来源链接不可用' }}</span></span>
            </a>
            <small v-if="articles.some(a => a.image_url)" class="image-note">配图来自对应原文，仅作报道配图。</small>
          </section>
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
.case-play-actions { display: flex; gap: 7px; margin: 12px 0 0 }.case-play-actions button { font-size: 12px; padding: 8px 9px }.case-play-actions .primary { flex: 1; background: #59c7bd; border-color: #59c7bd; color: #102724; font-weight: 600 }.case-detail .case-stage-status { font-size: 11px; color: var(--muted); margin: 8px 0 0 }
.case-legend { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 9px; margin-top: 10px; color: var(--muted); font-size: 11px }.case-legend span { display: flex; align-items: center; gap: 4px }.case-legend i { width: 12px; height: 2px; background: linear-gradient(90deg, #66b99a, #dca653, #db6363) }.case-legend i.legend-full { background: #7a91a5; opacity: .6 }.case-legend label { display: flex; align-items: center; gap: 3px; margin-left: auto }
.case-speed summary { cursor: pointer; padding: 12px 0 0; font-size: 13px; display: flex; justify-content: space-between; gap: 8px; align-items: baseline }.case-speed summary span { color: var(--muted); font-size: 11px }
.evidence-scope { margin: 12px 0 0; padding: 9px 10px; border: 1px solid var(--line); border-radius: var(--radius-s); color: var(--muted); font-size: 12px; line-height: 1.7 }
.case-evidence article { border-bottom: 1px solid var(--line); padding: 10px 0; font-size: 12px }.case-evidence p { line-height: 1.8 }.case-evidence h3 { margin: 12px 0 2px }.case-evidence button, .case-evidence a { font-size: 11px; margin-right: 8px }
.case-report-section { padding-top: 14px }.report-heading { display: flex; align-items: baseline; justify-content: space-between }.report-heading h3 { font-size: 14px; margin: 0 }.report-heading span, .evidence-label { font-size: 11px; color: var(--muted) }.evidence-label { line-height: 1.7; margin: 6px 0 8px }.case-article { display: flex; gap: 10px; align-items: flex-start; padding: 14px 0; border-bottom: 1px solid var(--line); text-decoration: none; color: var(--ink) }.case-article img, .case-image-placeholder { width: 65px; height: 70px; flex: none; border-radius: 4px; object-fit: cover; background: var(--wash) }.case-image-placeholder { display: grid; place-items: center; color: var(--muted); font-size: 12px }.case-article-copy { min-width: 0 }.case-article strong { font-size: 12px; line-height: 1.6; display: block; font-weight: 500; margin: 5px 0 }.case-article small { color: var(--muted); font-size: 11px; display: block }.read-source { font-size: 11px; color: #59c7bd }.case-article:hover strong { text-decoration: underline; text-underline-offset: 3px }.image-note { color: var(--muted); font-size: 11px; line-height: 1.7; display: block; margin: 8px 0 }.case-empty { font-size: 12px; color: var(--muted); line-height: 1.8 }.case-empty strong { font-size: 12px; font-weight: 500 }.case-empty button { font-size: 11px }
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
}
@media (max-width: 760px) {
  .case-panel { position: absolute; left: 10px; right: 10px; top: auto; bottom: 10px; width: auto; height: auto; max-height: 56%; border: 1px solid var(--line); border-radius: var(--radius-l); border-right: 1px solid var(--line); box-shadow: var(--shadow-overlay) }
  .case-content { padding: 0 14px 14px }
}
@media (prefers-reduced-motion: reduce) { .case-stages button { transition: none } }
</style>
