<script setup lang="ts">
import { computed, ref } from 'vue'
import type { ApiMaritimeCase } from '../api'
const props = defineProps<{ data: ApiMaritimeCase | null; activeStage: string; loading: boolean; error: string; active: boolean; pointsVisible: boolean; stageStatus?: string }>()
defineEmits<{ select: [id: string]; close: []; retry: []; exit: []; togglePoints: [] }>()
const failedImages = ref(new Set<string>())
const navigation = computed(() => props.data?.stages.filter(s => s.id !== 'confirmation') ?? [])
const stage = computed(() => props.data?.stages.find(s => s.id === props.activeStage))
const articles = computed(() => stage.value ? stage.value.articles : props.data?.stages.flatMap(s => s.articles) ?? [])
const followup = computed(() => props.data?.stages.find(s => s.id === 'confirmation'))
function imageFailed(url: string) { failedImages.value = new Set([...failedImages.value, url]) }
const stageNames = ['首次尝试', '等待', '再次通过']
function stageName(item: { id: string }, index: number) { return stageNames[index] ?? item.id }
</script>

<template>
  <aside class="case-panel" aria-label="中海北冰洋过航案例">
    <header><div><small>2026年3月27—31日 · 典型案例</small><h2>中海北冰洋</h2><p>从首次折返到再次通过</p></div><button @click="$emit('close')" aria-label="关闭案例面板，保留案例模式">×</button></header>
    <p class="case-identity" v-if="data">MMSI {{ data.mmsi }} · IMO {{ data.imo }}<br>{{ data.position_count.toLocaleString() }} 条报位</p>
    <p v-if="loading" role="status">正在加载完整案例…</p>
    <p v-if="error" role="alert">{{ error }} <button @click="$emit('retry')">重试</button></p>
    <template v-if="data">
      <p v-if="!data.ready" role="status">轨迹尚未导入，可先阅读报道。</p>
      <div class="case-view-controls">
        <button :aria-pressed="activeStage === 'overview'" @click="$emit('select', 'overview')">案例概况 · 完整轨迹</button>
        <label><input type="checkbox" :checked="pointsVisible" @change="$emit('togglePoints')">显示报位点</label>
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
          <span class="case-step-date">{{ item.id === 'waiting' ? '03.28–03.29' : item.date.slice(5).replace('-', '.') }}</span>
          <strong>{{ stageName(item, i) }}</strong>
        </button>
      </nav>
      <p v-if="stageStatus" class="case-stage-status" role="status">{{ stageStatus }}</p>
      <section class="case-detail" aria-live="polite">
        <h3>{{ stage?.title ?? '两次尝试，一条航行轨迹' }}</h3>
        <p>{{ stage?.summary ?? '沿完整轨迹查看首次尝试、两次尝试之间的等待与再次通过。点击阶段定位时间和视野，完整航迹仍保留在地图中。' }}</p>
        <small class="case-legend">淡线：完整观测轨迹 · 亮线：当前阶段已播放部分</small>
      </section>
      <section class="case-report-section">
        <h3>{{ stage ? '阶段相关报道' : '相关报道与后续回应' }}</h3>
        <p v-if="!articles.length" class="case-empty">此阶段没有单独点名报道，可返回概况查看完整报道。</p>
        <a class="case-article" v-for="article in articles" :key="article.url" :href="article.url" target="_blank" rel="noopener noreferrer">
          <img v-if="article.image_url && !failedImages.has(article.url)" :src="article.image_url" alt="原文配图" loading="lazy" referrerpolicy="no-referrer" @error="imageFailed(article.url)">
          <span v-else class="case-image-placeholder" aria-label="暂无配图">报道</span>
          <span class="case-article-copy"><strong>{{ article.title }}</strong><small>{{ article.media }}<br>发布于 {{ article.publish_date }}</small></span>
        </a>
        <small v-if="articles.some(a => a.image_url)" class="image-note">配图来自对应原文，仅作报道配图。</small>
      </section>
      <section v-if="!stage && followup" class="case-followup"><h3>3月31日 · 后续回应</h3><p>{{ followup.summary }}</p></section>
      <details><summary>数据范围与证据说明</summary><p v-for="note in data.limitations" :key="note">{{ note }}</p></details>
      <button class="case-exit" @click="$emit('exit')">退出案例，恢复原态势</button>
    </template>
  </aside>
</template>

<style scoped>
.case-panel { position: absolute; left: 18px; top: 14px; bottom: 18px; width: 340px; max-width: calc(100vw - 36px); z-index: 650; background: var(--panel); color: var(--ink); border: 1px solid var(--line); border-radius: var(--radius-l); overflow: auto; padding: 18px; box-shadow: var(--shadow-overlay) }
header { display: flex; justify-content: space-between; align-items: flex-start }
header small, .case-identity, .case-legend, .image-note { color: var(--muted); font-size: 11px; line-height: 1.7 }
h2 { font-size: 24px; margin: 6px 0 3px }
header p { font-size: 13px }
header button { font-size: 23px; border: 0; padding: 0 5px }
.case-identity { margin: 12px 0 }
.case-view-controls { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; margin: 15px 0 }
.case-view-controls button { font-size: 12px }
.case-view-controls label { font-size: 11px; color: var(--muted) }
button[aria-pressed=true] { color: #8cd9ee; border-color: #51c2cb; background: var(--wash) }
/* 阶段步骤导航：编号 + 日期 + 名称，当前阶段持续可见 */
.case-stages { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 5px }
.case-stages button { position: relative; display: grid; gap: 4px; justify-items: start; text-align: left; padding: 9px 6px; transition: border-color var(--dur-feedback) var(--ease-out), background var(--dur-feedback) var(--ease-out) }
.case-step-index { display: grid; place-items: center; width: 18px; height: 18px; border-radius: 50%; border: 1px solid var(--line); color: var(--muted); font-size: 11px; line-height: 1 }
.case-stages button.active { border-color: var(--accent, #51c2cb); background: var(--wash) }
.case-stages button.active .case-step-index { border-color: var(--accent, #51c2cb); color: var(--accent, #8cd9ee) }
.case-step-date { font-size: 10px; color: var(--muted) }
.case-stages strong { font-size: 12px }
.case-stage-status { margin: 9px 0 0; padding: 7px 10px; border: 1px dashed var(--line); border-radius: var(--radius-s); color: var(--muted); font-size: 11px; line-height: 1.6 }
.case-detail { min-height: 140px; padding: 16px 0 14px; border-bottom: 1px solid var(--line) }
h3 { font-size: 14px; margin-bottom: 10px }
.case-detail p, .case-followup p, details p { font-size: 12px; line-height: 1.8 }
.case-legend { display: block; margin-top: 10px }
.case-report-section { padding-top: 16px }
.case-article { display: flex; gap: 10px; align-items: flex-start; padding: 12px 0; border-bottom: 1px solid var(--line); text-decoration: none; color: var(--ink) }
.case-article img, .case-image-placeholder { width: 78px; height: 60px; flex: none; border-radius: 5px; object-fit: cover; background: var(--wash) }
.case-image-placeholder { display: grid; place-items: center; color: var(--muted); font-size: 12px }
.case-article-copy { min-width: 0 }
.case-article strong { font-size: 12px; line-height: 1.6; display: block }
.case-article small { color: var(--muted); font-size: 10px; display: block; margin-top: 5px }
.case-article:hover strong { color: #8cd9ee }
.image-note { display: block; margin: 8px 0 }
.case-empty { font-size: 12px; color: var(--muted); line-height: 1.8 }
.case-followup { margin: 18px 0 }
details { margin-top: 18px }
summary { cursor: pointer; font-size: 12px }
.case-exit { margin-top: 16px; width: 100%; padding: 9px }
button:focus-visible, a:focus-visible, summary:focus-visible, input:focus-visible { outline: 2px solid var(--blue); outline-offset: 2px }
@media (max-width: 760px) {
  .case-panel { left: 10px; right: 10px; top: 10px; bottom: auto; max-height: 62%; width: auto }
}
@media (prefers-reduced-motion: reduce) {
  .case-stages button { transition: none; }
}
</style>
