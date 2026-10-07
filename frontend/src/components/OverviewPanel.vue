<script setup lang="ts">
import { computed, ref } from 'vue'
import type { AgentAnalysisAction, AgentMapAction, ApiEvent, ApiMapShip } from '../api'
import { eventKind, formatTime, zoneLabel } from '../domain/maritime'
import { BRENT_SOURCE_URL } from '../domain/brentPrices'
import KeyEventBand from './KeyEventBand.vue'
import { shipComposition, type ShipGroup } from '../domain/overview'
import MarketTrendChart from './MarketTrendChart.vue'
import PassageAnalysisPanel from './PassageAnalysisPanel.vue'
import ShipCompositionChart from './ShipCompositionChart.vue'
const props = defineProps<{
  time: string | null
  viewShips: ApiMapShip[]
  viewEvents: ApiEvent[]
  events: ApiEvent[]
  allEvents: ApiEvent[]
  rangeStart: string | undefined
  rangeEnd: string | undefined
  totalShips: number
  totalEvents: number
  averageSpeed: string
  eventsLoading: boolean
  executeMapAction: (action: AgentMapAction, signal: AbortSignal) => Promise<{ message: string; outcome: 'ok' | 'error' | 'cancelled' }>
  analysisRestore: AgentAnalysisAction | null
}>()
const emit = defineEmits<{
  selectEvent: [event: ApiEvent]
  openEvents: []
  openShips: []
  openShipGroup: [group: ShipGroup]
  selectKeyEvent: [event: ApiEvent]
}>()
// 热点事件：报道数 coverage_count 降序，并列时按首次报道日期新的在前。
const hotEvents = computed(() =>
  [...props.events]
    .sort(
      (a, b) =>
        b.coverage_count - a.coverage_count ||
        (b.publish_date_min ?? '').localeCompare(a.publish_date_min ?? ''),
    )
    .slice(0, 5),
)
const composition = computed(() => shipComposition(props.viewShips))
// issue #40：「通行分析」动态查询面板（默认折叠，保持总览克制的工作区风格）。
const analysisOpen = ref(false)
</script>
<template>
  <section class="panel-content overview-panel">
    <header class="panel-heading">
      <p>
        {{ totalShips }} 艘船舶 · {{ totalEvents }} 条新闻事件 · 快照
        {{ formatTime(time, true) }}
      </p>
      <p>历史快照 · 非实时数据；新闻与船位来源独立，不因时空接近建立关联。</p>
    </header>
    <div class="overview-chips">
      <span
        ><strong>{{ viewShips.length }}</strong> 快照船舶</span
      ><span
        ><strong>{{ viewEvents.length }}</strong> 可定位新闻</span
      ><span
        >平均航速 <strong>{{ averageSpeed }}</strong> kn</span
      >
    </div>
    <section class="overview-section overview-chart" aria-label="油价与油轮通行量">
      <div class="section-title">
        <h3>油价 · 油轮通行量</h3>
        <span>完整历史窗口 · 双轴折线</span>
        <button type="button" class="analysis-toggle" :aria-expanded="analysisOpen" @click="analysisOpen = !analysisOpen">
          {{ analysisOpen ? '收起通行分析' : '通行分析' }}
        </button>
      </div>
      <MarketTrendChart :time="time" :range-start="rangeStart" :range-end="rangeEnd" />
      <p class="chart-source">
        数据来源：<a :href="BRENT_SOURCE_URL" target="_blank" rel="noopener noreferrer">EIA · Europe Brent Spot Price FOB (Daily)</a>
        · 油轮通行量为历史独立复核对照（UTC 归日，虚拟门线口径，固定批次，非动态查询结果）
      </p>
      <p class="chart-source chart-note">注：Brent 现货价仅工作日发布，周末无报价显示为断点；通行量 02-24 与 03-03 为部分日窗，03-03 的 0 表示“无确定通行”，不证明实际零通行。</p>
      <KeyEventBand :events="allEvents" :start="rangeStart" :end="rangeEnd" :loading="eventsLoading" @select="emit('selectKeyEvent', $event)" />
      <PassageAnalysisPanel
        v-if="analysisOpen"
        :execute-map-action="executeMapAction"
        :restore="analysisRestore"
      />
    </section>
    <section class="overview-section" aria-label="热点事件">
      <div class="section-title">
        <h3>热点事件</h3>
        <span>按报道数排序</span>
      </div>
      <p v-if="eventsLoading" class="empty compact" role="status">正在加载事件…</p>
      <template v-else>
        <button
          v-for="event in hotEvents"
          :key="event.event_id"
          class="overview-row"
          @click="emit('selectEvent', event)"
        >
          <time>{{ event.publish_date_min?.slice(5) || '—' }}</time>
          <span class="event-dot" :style="{ color: eventKind(event.event_type).color }"><img :src="eventKind(event.event_type).icon" alt=""></span>
          <span class="overview-row-title">{{ event.title }}</span>
          <small>{{ event.coverage_count }} 篇</small>
        </button>
        <p v-if="!hotEvents.length" class="empty compact">暂无新闻事件。</p>
        <button class="overview-more" @click="emit('openEvents')">
          查看全部 {{ totalEvents }} 条 ›
        </button>
      </template>
    </section>
    <section class="overview-section composition-section" aria-label="当前快照船舶构成">
      <div class="section-title"><h3>当前快照船舶构成</h3><span>{{ viewShips.length }} 艘 · 全部快照</span></div>
      <p class="composition-time">{{ formatTime(time, true) }} {{ zoneLabel() }} · 不随地图视野筛选</p>
      <ShipCompositionChart :groups="composition" @select="emit('openShipGroup', $event)" />
      <p v-if="!viewShips.length" class="empty compact">当前时刻暂无船位快照。</p>
      <p class="composition-note">货船含集装箱与散货船；缺失或未识别船型归为类型未知。</p>
      <button class="overview-more" @click="emit('openShips')">查看全部船舶 ›</button>
    </section>
  </section>
</template>
