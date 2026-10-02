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
const left = (day: string) => (Date.parse(day + 'T00:00:00Z') - Date.parse('2026-02-18T00:00:00Z')) / (20 * 86400000) * 100
</script>
<template>
  <section class="key-event-band" aria-label="关键事件带">
    <header><h4>关键事件对照</h4><span>完整 AIS 历史窗口 · 按报道数选取最多 6 条</span></header>
    <p class="chart-note">包含当前回放时刻之后的历史事件；标记为来源发生日期，仅作时间对照，不推断因果。</p>
    <p v-if="loading" class="empty compact" role="status">正在加载事件…</p>
    <template v-else>
      <div v-if="groups.length" class="event-date-track" aria-label="与图表 UTC 日期对应的事件标记">
        <a v-for="group in groups" :key="group.day" :href="`#key-event-${group.day}`" :style="{ left: left(group.day) + '%' }" :title="`${group.day} · ${group.events.length} 条`" :aria-label="`${group.day} 来源发生日期，${group.events.length} 条关键事件`">●</a>
      </div>
      <div class="key-event-groups">
        <details v-for="group in groups" :id="`key-event-${group.day}`" :key="group.day" open>
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
