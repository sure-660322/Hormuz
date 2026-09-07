<script setup lang="ts">
import { computed, ref, onMounted, onBeforeUnmount } from 'vue'
import type { ApiMapShip, ApiEvent } from '../api'
import { localWorkbench } from '../services/workbench'
import { shipType, formatTime } from '../domain/maritime'
const props = defineProps<{ ships: ApiMapShip[]; loading: boolean; events: ApiEvent[] }>()
const emit = defineEmits<{ select: [ship: ApiMapShip]; selectEvent: [event: ApiEvent] }>()
const input = ref<HTMLInputElement | null>(null)
const eventResults = computed(() => query.value.trim() ? props.events.filter(e => `${e.title} ${e.description}`.toLowerCase().includes(query.value.trim().toLowerCase())).slice(0, 15) : [])
function chooseEvent(event: ApiEvent) { emit('selectEvent', event); open.value = false; query.value = '' }
function shortcut(event: KeyboardEvent) { if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') { event.preventDefault(); input.value?.focus(); open.value = true } }
onMounted(() => window.addEventListener('keydown', shortcut))
onBeforeUnmount(() => window.removeEventListener('keydown', shortcut))
const query = ref('')
const open = ref(false)
const results = computed(() =>
  localWorkbench.searchShips(query.value, props.ships),
)
function choose(ship: ApiMapShip) {
  emit('select', ship)
  open.value = false
  query.value = ''
}
</script>
<template>
  <div
    class="ship-search"
    @focusout="
      (event) => {
        if (
          !(event.currentTarget as HTMLElement).contains(
            event.relatedTarget as Node,
          )
        )
          open = false
      }
    "
    @keydown.esc.stop="open = false"
  >
    <div class="search-input">
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <circle cx="10" cy="10" r="6" />
        <path d="m15 15 5 5" /></svg
      ><input
        ref="input"
        v-model="query"
        aria-label="搜索船名、IMO、MMSI 或事件"
        placeholder="船名 / 编号 / 事件 · Ctrl K"
        :aria-expanded="open"
        aria-controls="ship-search-results"
        @focus="open = true"
        @input="open = true"
        @keydown.enter.prevent="results[0] ? choose(results[0]) : eventResults[0] && chooseEvent(eventResults[0])"
      /><button v-if="query" aria-label="清空搜索" @click="query = ''">
        ×
      </button>
    </div>
    <div v-if="open" id="ship-search-results" class="search-results">
      <p class="search-summary">
        {{ loading ? '正在载入船舶…' : `当前时刻 · ${results.length} 个匹配` }}
      </p>
      <button
        v-for="ship in results.slice(0, 30)"
        :key="ship.id"
        class="ship-result"
        @click="choose(ship)"
      >
        <strong>{{ ship.name }}</strong
        ><span>{{ shipType(ship.ship_type) }} · MMSI {{ ship.mmsi }}</span
        ><small v-if="ship.imo">IMO {{ ship.imo }}</small>
      </button>
      <button v-for="event in eventResults" :key="`event-${event.id}`" class="ship-result" @click="chooseEvent(event)"><strong>{{ event.title }}</strong><small>模拟事件 · {{ formatTime(event.occurred_at, true) }}</small></button>
      <p v-if="!loading && !results.length && !eventResults.length" class="empty">
        没有匹配船舶。请尝试船名片段或完整编号。
      </p>
      <p v-if="results.length > 30" class="search-summary">
        显示前 30 项，请输入关键词缩小范围
      </p>
    </div>
  </div>
</template>
