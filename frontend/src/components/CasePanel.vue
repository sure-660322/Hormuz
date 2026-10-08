<script setup lang="ts">
import { computed, ref } from 'vue'
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

</script>

<template>
  <aside class="case-panel" :aria-label="`${displayTitle}案例`">
    <header><div><small>{{ data?.date_label ?? (isArctic ? '2026.03.27 — 03.31' : '2026.02.25 — 03.03') }} / 北京时间</small><h2>{{ displayTitle }}</h2><p>{{ isArctic ? '两次尝试，一条过航故事' : '报道与报位的对照' }}</p></div><div class="header-actions"><button @click="$emit('close')" aria-label="收起案例面板，保留案例模式" title="收起面板">‹</button><button @click="$emit('exit')" aria-label="退出案例，恢复原态势" title="退出案例">×</button></div></header>
    <label class="case-selector">选择案例 <select :value="caseId" :disabled="loading" @change="$emit('switchCase', ($event.target as HTMLSelectElement).value as MaritimeCaseId)"><option value="arctic-ocean">中海北冰洋</option><option value="athe-nova">ATHE NOVA</option></select></label>
    <div class="case-identity" v-if="data"><span>{{ data.vessel_label ?? '集装箱船 · CSCL ARCTIC OCEAN' }}</span><details><summary>船舶与数据</summary><p>MMSI {{ data.mmsi }}<br>IMO {{ data.imo }}<br>{{ data.position_count.toLocaleString() }} 条源报位</p></details></div>
    <p v-if="loading" role="status">正在加载完整案例…</p>
    <p v-if="error" role="alert">{{ error }} <button @click="$emit('retry')">重试</button></p>
    <template v-if="data">
      <p v-if="!data.ready" role="status">{{ data.unavailable_reason ?? '轨迹尚未导入，可先阅读报道。' }}</p>
      <div class="case-view-controls">
        <button :aria-pressed="activeStage === 'overview'" :disabled="loading" @click="$emit('select', 'overview')"><strong>完整故事</strong><span>完整轨迹与全部证据</span></button>
      </div>
      <nav class="case-stages" aria-label="航行阶段">
        <button
          v-for="(item, i) in navigation"
          :key="item.id"
          :class="{ active: activeStage === item.id }"
          :aria-current="activeStage === item.id ? 'step' : undefined"
          :disabled="loading"
          @click="$emit('select', item.id)"
        >
          <span class="case-step-index" aria-hidden="true">{{ i + 1 }}</span>
          <span class="case-step-copy"><span class="case-step-date">{{ isArctic && item.id === 'waiting' ? '03.28–03.29' : item.date.slice(5).replace('-', '.') }}</span><strong>{{ item.title }}</strong></span><span class="step-arrow" aria-hidden="true">›</span>
        </button>
      </nav>
      <section class="case-detail" aria-live="polite">
        <div class="detail-heading"><span>{{ stage && stageIndex >= 0 ? `第 ${stageIndex + 1} 段 / 共 ${navigation.length} 段` : '案例概况' }}</span><span>{{ stage ? stage.date.slice(5).replace('-', '.') : (isArctic ? '03.27–31' : '02.25–03.03') }}</span></div>
        <h3>{{ stage?.title ?? (isArctic ? '从首次折返，到再次通过' : '报道、缺报与后续观测') }}</h3>
        <p>{{ stage?.summary ?? data.overview_summary ?? '沿历史航迹查看航行过程；报道与AIS分别提供证据。' }}</p>
        <div class="case-play-actions"><button class="primary" :disabled="!ready" @click="playing ? $emit('pause') : $emit('play', activeStage)">{{ playing ? '暂停回放' : stage ? '从本段开始播放' : '从故事起点播放' }}</button><button :disabled="!ready" @click="$emit('select', activeStage)">查看{{ stage ? '本段' : '完整' }}轨迹</button></div>
        <p v-if="stageStatus" class="case-stage-status" role="status">{{ stageStatus }}</p>
        <div class="case-legend"><span><i class="legend-full" />完整观测轨迹</span><span><i />{{ stage ? '本段' : '故事' }}已回放 · 航速着色</span><label><input type="checkbox" :checked="pointsVisible" @change="$emit('togglePoints')">报位点</label></div>
      </section>
      <CaseSpeedPlot v-if="period.from && period.to" :track="track" :from="period.from" :to="period.to" :at="at" :disabled="!ready" @seek="$emit('seek', $event)" />
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
        <div v-if="!articles.length" class="case-empty"><strong>这一阶段没有单独点名报道</strong><p>先看航迹和观测缺口，或回到完整故事阅读相关报道。</p><button @click="$emit('select', 'overview')">查看全部报道</button></div>
        <a class="case-article" v-for="article in articles" :key="article.url" :href="safeNewsUrl(article.url) ?? undefined" target="_blank" rel="noopener noreferrer">
          <img v-if="article.image_url && !failedImages.has(article.url)" :src="article.image_url" alt="原文配图，非船舶身份依据" loading="lazy" referrerpolicy="no-referrer" @error="imageFailed(article.url)">
          <span v-else class="case-image-placeholder" aria-label="暂无配图">报道</span>
          <span class="case-article-copy"><small>{{ article.publish_date }} · {{ article.media }}</small><strong>{{ article.title }}</strong><span class="read-source">{{ safeNewsUrl(article.url) ? '阅读原文 ↗' : '来源链接不可用' }}</span></span>
        </a>
        <small v-if="articles.some(a => a.image_url)" class="image-note">配图来自对应原文，仅作报道配图。</small>
      </section>
      <section v-if="!stage && followup" class="case-followup"><small>03.31 / 后续回应</small><h3>把后续消息放回证据链</h3><p>{{ followup.summary }}</p></section>
      <details class="case-limitations"><summary>观测缺口与证据边界</summary><p>轨迹断线表示缺报，不代表停船或消失。阶段日期是浏览窗口，不是精确事件时刻。</p><p v-for="note in data.limitations" :key="note">{{ note }}</p></details>
      <div v-if="stage && stageIndex >= 0" class="stage-pagination"><button :disabled="stageIndex <= 0 || loading" @click="$emit('select', navigation[stageIndex - 1]!.id)">‹ 上一段</button><button v-if="stageIndex < navigation.length - 1" :disabled="loading" @click="$emit('select', navigation[stageIndex + 1]!.id)">下一段 ›</button><button v-else :disabled="loading" @click="$emit('select', 'overview')">回到完整故事</button></div>
      <button class="case-exit" @click="$emit('exit')">退出案例，恢复原态势</button>
    </template>
  </aside>
</template>

<style scoped>
.case-selector { display: flex; gap: 10px; align-items: center; font-size: 12px; margin-top: 12px }.case-selector select { flex: 1; min-width: 0; background: var(--wash); color: var(--ink); padding: 6px }.case-evidence article { border-bottom: 1px solid var(--line); padding: 10px 0; font-size: 12px }.case-evidence p { line-height: 1.8 }.case-evidence button, .case-evidence a { font-size: 11px; margin-right: 8px }
.case-panel { position: absolute; left: 18px; top: 14px; bottom: 18px; width: 340px; max-width: calc(100vw - 36px); z-index: 1050; background: var(--panel); color: var(--ink); border: 1px solid var(--line); border-radius: var(--radius-l); overflow: auto; padding: 0 20px 18px; scrollbar-width: thin; scrollbar-color: var(--subtle) transparent }
header { display: flex; justify-content: space-between; align-items: flex-start; padding-top: 22px }header small { font-size: 10px; color: var(--muted); letter-spacing: .3px }h2 { font-size: 27px; font-weight: 650; letter-spacing: .8px; line-height: 1.25; margin: 9px 0 6px }header p { margin: 0; color: var(--muted) }.header-actions { display: flex; gap: 2px }.header-actions button { padding: 2px 5px; border: 0; color: var(--muted); font-size: 18px }
.case-identity { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 6px; color: var(--muted); font-size: 10px; line-height: 1.7; margin-top: 12px; padding-bottom: 14px; border-bottom: 1px solid var(--line) }.case-identity details { margin: 0 }.case-identity p { margin: 8px 0; font-size: 11px }
.case-view-controls { margin: 14px 0 6px }.case-view-controls button { width: 100%; display: flex; justify-content: space-between; align-items: center; gap: 8px; padding: 9px 10px; border-color: transparent; background: transparent }.case-view-controls button[aria-pressed=true] { border-color: var(--line); color: var(--ink); background: var(--wash) }.case-view-controls span { color: var(--muted); font-size: 10px }
.case-stages { display: flex; flex-direction: column; gap: 3px; border-bottom: 1px solid var(--line); padding-bottom: 14px }.case-stages button { display: flex; align-items: center; gap: 11px; padding: 9px 10px; border-color: transparent; background: transparent; text-align: left; transition: border-color var(--dur-feedback) var(--ease-out), background var(--dur-feedback) var(--ease-out) }.case-stages button.active { border-color: var(--line); background: var(--wash) }.case-step-index { display: grid; place-items: center; width: 23px; height: 23px; flex-shrink: 0; border: 1px solid var(--line); border-radius: 50%; color: var(--muted); font-size: 11px }.case-stages button.active .case-step-index { border-color: #59c7bd; color: var(--ink); background: #59c7bd20 }.case-step-copy { display: flex; flex-direction: column; gap: 2px }.case-step-date { font-size: 10px; color: var(--muted) }.case-stages strong { font-size: 12px; font-weight: 500 }.step-arrow { margin-left: auto; color: var(--muted); font-size: 20px }.active .step-arrow { color: #59c7bd }
.detail-heading { display: flex; justify-content: space-between; color: var(--muted); font-size: 10px }.case-detail { padding: 16px 0 14px; border-bottom: 1px solid var(--line) }h3 { font-size: 16px; line-height: 1.6; margin: 7px 0 }.case-detail p, .case-followup p, details p { font-size: 12px; line-height: 1.8 }.case-play-actions { display: flex; gap: 7px; margin: 13px 0 }.case-play-actions button { font-size: 11px; padding: 8px 9px }.case-play-actions .primary { flex: 1; background: #59c7bd; border-color: #59c7bd; color: #102724; font-weight: 600 }.case-detail .case-stage-status { font-size: 10px; color: var(--muted); margin: 7px 0 12px }
.case-legend { display: flex; flex-wrap: wrap; align-items: center; gap: 7px 9px; color: var(--muted); font-size: 10px }.case-legend span { display: flex; align-items: center; gap: 4px }.case-legend i { width: 12px; height: 2px; background: linear-gradient(90deg, #66b99a, #dca653, #db6363) }.case-legend i.legend-full { background: #7a91a5; opacity: .6 }.case-legend label { display: flex; align-items: center; gap: 3px; margin-left: auto }
.case-report-section { padding-top: 16px }.report-heading { display: flex; align-items: baseline; justify-content: space-between }.report-heading h3 { font-size: 14px; margin: 0 }.report-heading span, .evidence-label { font-size: 10px; color: var(--muted) }.evidence-label { line-height: 1.7; margin: 6px 0 8px }.case-article { display: flex; gap: 10px; align-items: flex-start; padding: 14px 0; border-bottom: 1px solid var(--line); text-decoration: none; color: var(--ink) }.case-article img, .case-image-placeholder { width: 65px; height: 70px; flex: none; border-radius: 4px; object-fit: cover; background: var(--wash) }.case-image-placeholder { display: grid; place-items: center; color: var(--muted); font-size: 12px }.case-article-copy { min-width: 0 }.case-article strong { font-size: 12px; line-height: 1.6; display: block; font-weight: 500; margin: 5px 0 }.case-article small { color: var(--muted); font-size: 10px; display: block }.read-source { font-size: 10px; color: #59c7bd }.case-article:hover strong { text-decoration: underline; text-underline-offset: 3px }.image-note { color: var(--muted); font-size: 11px; line-height: 1.7; display: block; margin: 8px 0 }.case-empty { font-size: 12px; color: var(--muted); line-height: 1.8 }.case-empty strong { font-size: 12px; font-weight: 500 }.case-empty button { font-size: 11px }
.case-followup { margin: 18px 0; padding-left: 12px; border-left: 2px solid #59c7bd }.case-followup small { font-size: 10px; color: var(--muted) }.case-followup h3 { font-size: 13px }details { margin-top: 18px }summary { cursor: pointer; font-size: 12px }.case-limitations { color: var(--muted) }.stage-pagination { display: flex; gap: 8px; justify-content: space-between; padding-top: 18px }.stage-pagination button { font-size: 11px }.case-exit { margin-top: 16px; width: 100%; padding: 9px; font-size: 11px; color: var(--muted) }
button:disabled { opacity: .45; cursor: not-allowed }button:focus-visible, a:focus-visible, summary:focus-visible, input:focus-visible { outline: 2px solid var(--blue); outline-offset: 2px }
@media (max-height: 800px), (max-width: 760px) { header { padding-top: 14px }h2 { margin: 5px 0; font-size: 24px }header p { font-size: 11px }.case-identity { margin-top: 8px; padding-bottom: 8px }.case-view-controls { margin-top: 9px }.case-detail { padding-top: 8px }.case-step-index { display: none } .case-stages { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 5px }.case-stages button { align-items: flex-start; gap: 6px; padding: 8px 5px }.case-step-index { width: 18px; height: 18px; font-size: 10px; margin-top: 3px }.case-stages strong { font-size: 11px }.step-arrow { display: none } }
@media (max-width: 760px) { .case-panel { left: 10px; right: 10px; top: auto; bottom: 10px; max-height: 48%; width: auto; padding: 0 16px 16px }header { padding-top: 16px }h2 { font-size: 23px } }
@media (prefers-reduced-motion: reduce) { .case-stages button { transition: none } }
</style>
