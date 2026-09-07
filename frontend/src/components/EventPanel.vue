<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'
import type { ApiEvent } from '../api'
import { eventKind, eventKinds, formatTime } from '../domain/maritime'
const props = defineProps<{
  events: ApiEvent[]
  totalCount: number
  occurredCount: number
  eventType: string
  sort: 'asc' | 'desc'
  occurredOnly: boolean
  selected: ApiEvent | null
  time: string | null
  loading: boolean
  error: string
}>()
const emit = defineEmits<{
  select: [event: ApiEvent]
  typeChange: [type: string]
  sortChange: [sort: 'asc' | 'desc']
  occurredChange: [value: boolean]
  clear: []
  retry: []
}>()
const panel = ref<HTMLElement | null>(null)
const occurred = (event: ApiEvent) =>
  props.time !== null && Date.parse(event.occurred_at) <= Date.parse(props.time)
watch(
  () => props.selected?.id,
  async (id) => {
    await nextTick()
    if (id && panel.value) panel.value.scrollTop = 0
  },
)
</script>
<template>
  <section ref="panel" class="panel-content event-panel">
    <header class="panel-heading">
      <h2>事件流</h2>
      <p>
        已发生 {{ occurredCount }} / {{ totalCount }} 条
        <span>点击事件定位并回放</span>
      </p>
    </header>
    <div class="event-filters">
      <select
        aria-label="事件类型"
        :value="eventType"
        @change="emit('typeChange', ($event.target as HTMLSelectElement).value)"
      >
        <option value="all">全部类型</option>
        <option v-for="(kind, key) in eventKinds" :key="key" :value="key">
          {{ kind.label }}
        </option></select
      ><select
        aria-label="时间顺序"
        :value="sort"
        @change="
          emit(
            'sortChange',
            ($event.target as HTMLSelectElement).value as 'asc' | 'desc',
          )
        "
      >
        <option value="asc">时间正序</option>
        <option value="desc">最新在前</option>
      </select>
    </div>
    <label class="check-line occurred-filter"
      ><input
        type="checkbox"
        :checked="occurredOnly"
        @change="
          emit('occurredChange', ($event.target as HTMLInputElement).checked)
        "
      />仅显示当前时刻已发生事件</label
    >
    <div v-if="loading" class="empty" role="status">正在加载事件…</div>
    <div v-else-if="error" class="empty error" role="alert">
      {{ error }}<button @click="emit('retry')">重新加载</button>
    </div>
    <template v-else>
      <section
        v-if="selected"
        class="event-detail"
        :style="{ '--event-color': eventKind(selected.event_type).color }"
      >
        <div class="section-title">
          <span>{{ eventKind(selected.event_type).label }}</span
          ><button aria-label="关闭事件详情" @click="emit('clear')">×</button>
        </div>
        <h3>{{ selected.title }}</h3>
        <p>{{ selected.description }}</p>
        <dl class="facts">
          <div>
            <dt>发生时间</dt>
            <dd>{{ formatTime(selected.occurred_at, true) }}</dd>
          </div>
          <div>
            <dt>经纬度</dt>
            <dd>
              {{ selected.latitude.toFixed(4) }},
              {{ selected.longitude.toFixed(4) }}
            </dd>
          </div>
          <div>
            <dt>来源</dt>
            <dd>{{ selected.source_name || '教学模拟数据' }}</dd>
          </div>
        </dl>
        <p class="caption">
          蓝色船位为事件周边 10 NM 内的船舶，空间邻近不代表事件关联。
        </p>
      </section>
      <p v-if="!events.length" class="empty">
        此筛选条件下暂无事件。可取消“仅显示已发生”或调整回放时间。
      </p>
      <ul v-else class="event-list">
        <li v-for="event in events" :key="event.id">
          <button
            class="event-row"
            :class="{
              selected: selected?.id === event.id,
              future: !occurred(event),
            }"
            :data-event-id="event.id"
            @click="emit('select', event)"
          >
            <time>{{ formatTime(event.occurred_at) }}</time
            ><span
              class="event-dot"
              :style="{ color: eventKind(event.event_type).color }"
              >{{ eventKind(event.event_type).symbol }}</span
            ><span class="event-row-body"
              ><span class="event-row-title"
                ><strong>{{ eventKind(event.event_type).label }}</strong
                ><small>{{
                  occurred(event) ? '已发生' : '待回放'
                }}</small></span
              ><span>{{ event.title }}</span
              ><small
                >{{ event.latitude.toFixed(2) }}° N /
                {{ event.longitude.toFixed(2) }}° E</small
              ></span
            >
          </button>
        </li>
      </ul>
    </template>
  </section>
</template>
