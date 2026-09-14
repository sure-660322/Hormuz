<script setup lang="ts">
import { nextTick, ref, watch, onBeforeUnmount } from 'vue'
import { fetchEventNews, describeApiError, type ApiEvent, type ApiEventNews } from '../api'
import { eventKind, eventKinds, eventTimeText, eventCoordinates, eventLocationLabel, hasEventLocation, safeNewsUrl } from '../domain/maritime'
const props = defineProps<{
  events: ApiEvent[]
  totalCount: number
  eventType: string
  sort: 'asc' | 'desc'
  selected: ApiEvent | null
  loading: boolean
  error: string
}>()
const emit = defineEmits<{
  select: [event: ApiEvent]
  typeChange: [type: string]
  sortChange: [sort: 'asc' | 'desc']
  clear: []
  retry: []
}>()
const panel = ref<HTMLElement | null>(null)
const news = ref<ApiEventNews[]>([])
const newsLoading = ref(false)
const newsError = ref('')
let request: AbortController | null = null
async function loadNews() {
  request?.abort()
  const controller = new AbortController()
  request = controller
  news.value = []
  newsError.value = ''
  newsLoading.value = false
  const event = props.selected
  if (!event) return
  newsLoading.value = true
  try {
    const items = await fetchEventNews(event.event_id, controller.signal)
    if (request === controller && !controller.signal.aborted) news.value = items
  } catch (error) {
    if (request === controller && !controller.signal.aborted)
      newsError.value = describeApiError(error, '关联新闻加载失败')
  } finally {
    if (request === controller) newsLoading.value = false
  }
}
watch(() => props.selected?.event_id, async () => {
  void loadNews()
  await nextTick()
  if (panel.value) panel.value.scrollTop = 0
}, { immediate: true })
onBeforeUnmount(() => request?.abort())
</script>
<template>
  <section ref="panel" class="panel-content event-panel">
    <header class="panel-heading">
      <h2>新闻事件</h2>
      <p>显示 {{ events.length }} / {{ totalCount }} 条 · 按首次报道日期排序</p>
      <p>独立浏览历史新闻，不改变模拟船舶回放。</p>
    </header>
    <div class="event-filters">
      <select aria-label="事件类型" :value="eventType" @change="emit('typeChange', ($event.target as HTMLSelectElement).value)">
        <option value="all">全部类型</option>
        <option v-for="(kind, key) in eventKinds" :key="key" :value="key">{{ kind.label }}</option>
      </select>
      <select aria-label="报道日期顺序" :value="sort" @change="emit('sortChange', ($event.target as HTMLSelectElement).value as 'asc' | 'desc')">
        <option value="asc">报道日期正序</option><option value="desc">最新报道在前</option>
      </select>
    </div>
    <div v-if="loading" class="empty" role="status">正在加载事件…</div>
    <div v-else-if="error" class="empty error" role="alert">{{ error }}<button @click="emit('retry')">重新加载</button></div>
    <template v-else>
      <section v-if="selected" class="event-detail" :style="{ '--event-color': eventKind(selected.event_type).color }">
        <div class="section-title"><span>{{ eventKind(selected.event_type).label }} · {{ selected.event_id }}</span><button aria-label="关闭事件详情" @click="emit('clear')">×</button></div>
        <h3>{{ selected.title }}</h3>
        <p>{{ selected.description }}</p>
        <dl class="facts">
          <div><dt>事件时间</dt><dd>{{ eventTimeText(selected) }}</dd></div>
          <div><dt>报道日期</dt><dd>{{ selected.publish_date_min || '未明确' }} — {{ selected.publish_date_max || '未明确' }}</dd></div>
          <div><dt>地点</dt><dd>{{ selected.event_location_text || selected.event_region || '地点未明确' }}</dd></div>
          <div><dt>代表点</dt><dd>{{ eventCoordinates(selected) }}<br />{{ eventLocationLabel(selected) }}</dd></div>
          <div><dt>定位说明</dt><dd>{{ selected.geo_note || '暂无定位说明' }}</dd></div>
          <div><dt>报道视角</dt><dd>{{ selected.perspectives.join('、') || '未标注' }}</dd></div>
          <div v-if="selected.mentioned_vessels.length"><dt>提及船名</dt><dd>{{ selected.mentioned_vessels.join('、') }}（原文提及，未关联模拟船舶）</dd></div>
        </dl>
        <p class="caption">{{ hasEventLocation(selected) ? '地图仅展示代表点，地名或区域中心不等于精确事发位置；多点展示待适配。' : '此事件没有可定位坐标，保留文字详情，不移动地图。' }}</p>
        <section class="event-news">
          <h3>关联新闻 · {{ selected.coverage_count }} 篇</h3>
          <p v-if="newsLoading" role="status">正在加载关联新闻…</p>
          <p v-else-if="newsError" role="alert">{{ newsError }} <button @click="loadNews">重试新闻</button></p>
          <p v-else-if="!news.length">暂无关联新闻。</p>
          <ul v-else class="news-list">
            <li v-for="item in news" :key="item.story_id">
              <a v-if="safeNewsUrl(item.canonical_url)" :href="safeNewsUrl(item.canonical_url)" target="_blank" rel="noopener noreferrer">{{ item.title_zh || item.title }} ↗</a>
              <strong v-else>{{ item.title_zh || item.title }}</strong>
              <p>{{ item.media_name }} · {{ item.publish_date }} · {{ item.perspective }}</p>
              <details v-if="item.summary_zh"><summary>报道摘要</summary><p>{{ item.summary_zh }}</p></details>
            </li>
          </ul>
        </section>
      </section>
      <p v-if="!events.length" class="empty">此分类暂无事件，可切换到全部类型。</p>
      <ul v-else class="event-list">
        <li v-for="event in events" :key="event.event_id">
          <button class="event-row" :class="{ selected: selected?.event_id === event.event_id }" :data-event-id="event.event_id" @click="emit('select', event)">
            <time>{{ event.publish_date_min?.slice(5) || '—' }}</time>
            <span class="event-dot" :style="{ color: eventKind(event.event_type).color }">{{ eventKind(event.event_type).symbol }}</span>
            <span class="event-row-body"><span class="event-row-title"><strong>{{ eventKind(event.event_type).label }}</strong><small>{{ event.coverage_count }} 篇报道</small></span>
              <span>{{ event.title }}</span><small>{{ hasEventLocation(event) ? '代表点可定位' : '暂无坐标 · 可查看详情' }}</small>
            </span>
          </button>
        </li>
      </ul>
    </template>
  </section>
</template>
<style scoped>
.news-list { list-style: none; padding: 0; }
.news-list li { padding: 12px 0; border-bottom: 1px solid var(--line, #68768150); overflow-wrap: anywhere; }
.news-list a { color: var(--ink); text-decoration: underline; text-underline-offset: 3px; }
.news-list p, .news-list summary { font-size: 12px; line-height: 1.6; }
.facts dd { overflow-wrap: anywhere; }
</style>
