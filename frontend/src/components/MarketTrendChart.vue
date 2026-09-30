<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import * as echarts from 'echarts/core'
import { LineChart } from 'echarts/charts'
import {
  GridComponent,
  MarkAreaComponent,
  TooltipComponent,
} from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import type { ComposeOption } from 'echarts/core'
import type { LineSeriesOption } from 'echarts/charts'
import type {
  GridComponentOption,
  MarkAreaComponentOption,
  TooltipComponentOption,
} from 'echarts/components'
import {
  AIS_WINDOW,
  brentDailyPrices,
} from '../domain/brentPrices'
import { tankerPassagesUtc } from '../domain/tankerPassages'

echarts.use([
  LineChart,
  GridComponent,
  MarkAreaComponent,
  TooltipComponent,
  CanvasRenderer,
])

type ChartOption = ComposeOption<
  | LineSeriesOption
  | GridComponentOption
  | MarkAreaComponentOption
  | TooltipComponentOption
>

const PRICE_COLOR = '#E8B14E'
const TRAFFIC_COLOR = '#5AA2E8'

function dateRange(start: string, end: string): string[] {
  const days: string[] = []
  const d = new Date(`${start}T00:00:00Z`)
  const last = new Date(`${end}T00:00:00Z`)
  while (d <= last) {
    days.push(d.toISOString().slice(0, 10))
    d.setUTCDate(d.getUTCDate() + 1)
  }
  return days
}

// 连续日历日横轴：油价周末无报价显示为断点，通行量按自然日覆盖。
const categories = dateRange('2026-02-18', '2026-03-10')
const priceByDate = new Map(brentDailyPrices.map((d) => [d.date, d.price]))
const passageByDate = new Map(tankerPassagesUtc.map((d) => [d.date, d.passages]))

const showPrice = ref(true)
const showTraffic = ref(true)

const chartEl = ref<HTMLElement | null>(null)
let chart: ReturnType<typeof echarts.init> | null = null
let resizeObserver: ResizeObserver | null = null

function buildOption(): ChartOption {
  const series: LineSeriesOption[] = [
    // 常驻底图序列：不画线，只承载 AIS 回放窗口高亮带，开关切换时保持不变。
    {
      type: 'line',
      name: '回放窗口',
      data: [],
      silent: true,
      animation: false,
      showSymbol: false,
      lineStyle: { opacity: 0 },
      tooltip: { show: false },
      markArea: {
        silent: true,
        itemStyle: { color: 'rgba(232, 177, 78, 0.10)' },
        label: {
          show: true,
          position: 'insideTop',
          color: '#8B98A8',
          fontSize: 10,
          formatter: 'AIS 回放窗口',
        },
        data: [
          [
            { xAxis: AIS_WINDOW.start.slice(5) },
            { xAxis: AIS_WINDOW.end.slice(5) },
          ],
        ],
      },
    },
  ]
  if (showPrice.value) {
    series.push({
      type: 'line',
      name: 'Brent 现货价',
      yAxisIndex: 0,
      data: categories.map((d) => priceByDate.get(d) ?? null),
      smooth: false,
      symbol: 'circle',
      symbolSize: 5,
      lineStyle: { width: 2, color: PRICE_COLOR },
      itemStyle: { color: PRICE_COLOR },
    })
  }
  if (showTraffic.value) {
    series.push({
      type: 'line',
      name: '油轮通行量',
      yAxisIndex: 1,
      data: categories.map((d) => passageByDate.get(d) ?? null),
      smooth: false,
      symbol: 'diamond',
      symbolSize: 6,
      lineStyle: { width: 2, color: TRAFFIC_COLOR },
      itemStyle: { color: TRAFFIC_COLOR },
    })
  }
  return {
    // 开关重新加入序列时，用入场动画（从左描线）而不是直接弹出。
    animationDuration: 900,
    animationEasing: 'cubicOut',
    grid: { top: 28, right: 44, bottom: 28, left: 52 },
    tooltip: {
      trigger: 'axis',
      formatter: (params) => {
        const list = (Array.isArray(params) ? params : [params]) as unknown as Array<{
          marker: string
          seriesName: string
          axisValue: string
          value: number | null
        }>
        const header = list.length ? list[0].axisValue : ''
        const lines = list.map((p) => {
          const unit = p.seriesName === '油轮通行量' ? '次' : '美元/桶'
          const value = p.value == null ? '—' : `${p.value} ${unit}`
          return `${p.marker} ${p.seriesName}：<b>${value}</b>`
        })
        return [header, ...lines].join('<br/>')
      },
    },
    xAxis: {
      type: 'category',
      boundaryGap: false,
      data: categories.map((d) => d.slice(5)),
      axisLabel: { color: '#8B98A8', fontSize: 10 },
      axisLine: { lineStyle: { color: '#28323F' } },
    },
    yAxis: [
      {
        type: 'value',
        min: 65,
        axisLabel: { color: '#8B98A8', fontSize: 10 },
        splitLine: { lineStyle: { color: '#28323F' } },
      },
      {
        type: 'value',
        min: 0,
        position: 'right',
        axisLabel: { color: '#8B98A8', fontSize: 10 },
        splitLine: { show: false },
      },
    ],
    series,
  }
}

function applyOption() {
  // replaceMerge 让重新开启的序列按新实例入场，触发描线动画。
  chart?.setOption(buildOption(), { replaceMerge: ['series'] })
}

function togglePrice() {
  showPrice.value = !showPrice.value
  applyOption()
}

function toggleTraffic() {
  showTraffic.value = !showTraffic.value
  applyOption()
}

onMounted(() => {
  if (!chartEl.value) return
  chart = echarts.init(chartEl.value)
  chart.setOption(buildOption())
  resizeObserver = new ResizeObserver(() => chart?.resize())
  resizeObserver.observe(chartEl.value)
})

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  resizeObserver = null
  chart?.dispose()
  chart = null
})
</script>

<template>
  <div class="chart-toggles">
    <button
      type="button"
      class="chart-toggle"
      :class="{ active: showPrice }"
      :aria-pressed="showPrice"
      @click="togglePrice"
    >
      <i class="toggle-dot" :style="{ background: PRICE_COLOR }"></i>
      Brent 油价（左轴）
    </button>
    <button
      type="button"
      class="chart-toggle"
      :class="{ active: showTraffic }"
      :aria-pressed="showTraffic"
      @click="toggleTraffic"
    >
      <i class="toggle-dot" :style="{ background: TRAFFIC_COLOR }"></i>
      油轮通行量（右轴）
    </button>
  </div>
  <div
    ref="chartEl"
    class="market-chart"
    role="img"
    aria-label="布伦特原油现货价格与油轮通行量双轴折线图，覆盖 2026-02-18 至 2026-03-10"
  ></div>
</template>
