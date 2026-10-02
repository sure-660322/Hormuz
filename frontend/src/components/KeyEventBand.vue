<script setup lang="ts">
import { computed } from 'vue'
import type { ApiEvent } from '../api'
import { eventKind } from '../domain/maritime'
import { keyEvents } from '../domain/overview'
const props = defineProps<{ events: ApiEvent[]; start: string | undefined; end: string | undefined; loading: boolean }>()
const emit = defineEmits<{ select: [event: ApiEvent] }>()
const groups = computed(() => {
  const byDay = new Map<string, ApiEvent[]>()
  for (const event of keyEvents(props.events, props.start, props.end)) {
    const day = event.occurred_at!.slice(0, 10)
    if (!byDay.has(day)) byDay.set(day, [])
    byDay.get(day)!.push(event)
  }
  return [...byDay].map(([day, events]) => ({ day, events }))
})
const groupElements = new Map<string, HTMLDetailsElement>()
function jumpToGroup(day: string) {
  const element = groupElements.get(day)
  if (element) element.open = true
}
</script>
<template>
  <section class="key-event-band" aria-label="关键事件带">
    <header><h4>关键事件对照</h4><span>完整 AIS 历史窗口 · 按报道数选取最多 6 条</span></header>
    <p class="chart-note">包含当前回放时刻之后的历史事件；标记为来源发生日期，仅作时间对照，不推断因果。</p>
    <p v-if="loading" class="empty compact" role="status">正在加载事件…</p>
    <template v-else>
      <nav v-if="groups.length" class="event-date-navigation" aria-label="按事件发生日期跳转">
        <span>按发生日期跳转</span>
        <a v-for="group in groups" :key="group.day" :href="`#key-event-${group.day}`" @click="jumpToGroup(group.day)"><time>{{ group.day.slice(5).replace('-', '/') }}</time><span>{{ group.events.length }} 条</span><span>跳转 ↓</span></a>
      </nav>
      <div class="key-event-groups">
        <details v-for="group in groups" :id="`key-event-${group.day}`" :key="group.day" :ref="element => { if (element) groupElements.set(group.day, element as HTMLDetailsElement); else groupElements.delete(group.day) }" open>
          <summary><time>{{ group.day }}</time><span>{{ group.events.length }} 条</span></summary>
          <button v-for="event in group.events" :key="event.event_id" class="key-event-card" @click="emit('select', event)">
            <span :style="{ color: eventKind(event.event_type).color }">{{ eventKind(event.event_type).label }}</span>
            <strong>{{ event.title }}</strong>
            <small>{{ event.coverage_count }} 篇报道 · 首次报道 {{ event.publish_date_min || '日期未提供' }} · 查看详情 ›</small>
          </button>
        </details>
      </div>
      <p v-if="!groups.length" class="empty compact">此历史窗口暂无发生日期明确的新闻事件。</p>
    </template>
  </section>
</template>
