<script setup lang="ts">
import type { ApiCaseNewsEntry, MaritimeCaseId } from '../api'
defineProps<{ entries: ApiCaseNewsEntry[]; loading: boolean; error: string }>()
defineEmits<{ select: [id: MaritimeCaseId]; retry: []; close: []; exit: [] }>()
</script>

<template>
  <aside class="case-panel case-news-index" aria-label="典型新闻事件">
    <header class="news-head">
      <div><span>新闻与航迹</span><h2>典型新闻事件</h2></div>
      <div class="news-actions"><button @click="$emit('close')">收起</button><button @click="$emit('exit')">退出案例</button></div>
    </header>
    <p class="news-intro">从一条新闻开始，对照相关船舶的历史 AIS 轨迹。</p>
    <p v-if="loading" role="status">正在加载典型新闻…</p>
    <p v-else-if="error" role="alert">{{ error }} <button @click="$emit('retry')">重试</button></p>
    <div v-else class="news-entry-list">
      <button v-for="entry in entries" :key="entry.case_id" class="case-news-entry" :data-case-id="entry.case_id" :disabled="!entry.available" @click="$emit('select', entry.case_id)">
        <span class="entry-meta"><time>{{ entry.event_day }}</time><span>{{ entry.articles.length }} 篇来源</span></span>
        <strong>{{ entry.title_zh }}</strong>
        <span class="entry-summary">{{ entry.summary_zh }}</span>
        <span class="entry-vessel">{{ entry.vessel_name }} · MMSI {{ entry.mmsi }}</span>
        <span class="entry-action">{{ entry.available ? '查看相关船舶轨迹 →' : '新闻证据尚未导入' }}</span>
      </button>
    </div>
    <p class="news-boundary">精选案例已人工核对；报道描述与 AIS 观测分别提供证据。</p>
  </aside>
</template>

<style scoped>
.case-news-index { position: relative; display: flex; flex-direction: column; height: 100%; flex: none; z-index: 1050; width: 340px; box-sizing: border-box; overflow: auto; padding: 18px 16px; background: var(--panel); color: var(--ink); border-right: 1px solid var(--line) }
.news-head { display: flex; justify-content: space-between; align-items: center; gap: 10px }.news-head span { color: var(--muted); font-size: 11px }h2 { margin: 4px 0 0; font-size: 17px; font-weight: 600 }.news-actions { display: flex; gap: 5px }
button { cursor: pointer; color: var(--ink); background: transparent; border: 1px solid var(--line); border-radius: 6px; padding: 6px; font: inherit; font-size: 11px }button:focus-visible { outline: 2px solid #59c7bd; outline-offset: 3px }button:disabled { opacity: .55; cursor: default }
.news-intro,.news-boundary { font-size: 12px; color: var(--muted); line-height: 1.7; margin: 14px 0 }.news-boundary { font-size: 11px; border-top: 1px solid var(--line); padding-top: 12px }
.news-entry-list { display: grid; gap: 0 }.case-news-entry { display: flex; flex-direction: column; align-items: stretch; gap: 9px; text-align: left; border: 0; border-bottom: 1px solid var(--line); border-radius: 0; padding: 18px 0 }.case-news-entry:hover:not(:disabled) strong,.entry-action { color: #59c7bd }.entry-meta { display: flex; justify-content: space-between; color: var(--muted); font-size: 11px }.case-news-entry strong { font-size: 15px; font-weight: 550; line-height: 1.65 }.entry-summary { font-size: 12px; line-height: 1.8 }.entry-vessel { color: var(--muted); font-size: 10px; overflow-wrap: anywhere }.entry-action { font-size: 11px }
@media (max-width: 760px) { .case-news-index { position: absolute; inset: auto 10px 10px; height: auto; width: auto; max-height: 64%; border: 1px solid var(--line); border-radius: 12px; padding: 14px }.news-entry-list { gap: 0 } }
</style>
