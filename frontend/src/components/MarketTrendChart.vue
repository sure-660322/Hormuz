<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts/core'
import { LineChart } from 'echarts/charts'
import {
  GridComponent,
  MarkAreaComponent,
  MarkLineComponent,
  TooltipComponent,
} from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import type { ComposeOption } from 'echarts/core'
import type { LineSeriesOption } from 'echarts/charts'
import type {
  GridComponentOption,
  MarkAreaComponentOption,
  MarkLineComponentOption,
  TooltipComponentOption,
} from 'echarts/components'
import {
  brentDailyPrices,
} from '../domain/brentPrices'
import { tankerPassagesUtc } from '../domain/tankerPassages'

echarts.use([
  LineChart,
  GridComponent,
  MarkAreaComponent,
  MarkLineComponent,
  TooltipComponent,
  CanvasRenderer,
])

type ChartOption = ComposeOption<
  | LineSeriesOption
  | GridComponentOption
  | MarkAreaComponentOption
  | MarkLineComponentOption
  | TooltipComponentOption
>

import { formatTime, zoneLabel } from '../domain/maritime'
const props = defineProps<{ time: string | null; rangeStart: string | undefined; rangeEnd: string | undefined }>()
const direction = ref<'passages' | 'inbound' | 'outbound'>('passages')
const directions = { passages: '总次数', inbound: '入湾', outbound: '出湾' }

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
const passageByDate = new Map(tankerPassagesUtc.map((d) => [d.date, d]))

const showPrice = ref(true)
const showTraffic = ref(true)

const chartEl = ref<HTMLElement | null>(null)
let chart: ReturnType<typeof echarts.init> | null = null
let resizeObserver: ResizeObserver | null = null

function buildOption(): ChartOption {
  const series: LineSeriesOption[] = [
    // 常驻底图序列：不画线，只承载 AIS 回放窗口高亮带，开关切换时保持不变。
    {
      id: 'replay-window',
      type: 'line',
      name: '回放窗口',
      data: [],
      silent: true,
      animation: false,
      showSymbol: false,
      lineStyle: { opacity: 0 },
      tooltip: { show: false },
      markLine: props.time ? {
        silent: true, symbol: 'none',
        lineStyle: { color: '#A8B6C6', type: 'dashed', width: 1 },
        label: { show: true, position: 'insideEndTop', formatter: '当前回放', color: '#A8B6C6', fontSize: 10 },
        data: [{ xAxis: Date.parse(props.time) }],
      } : undefined,
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
            { xAxis: Date.parse(props.rangeStart ?? '2026-02-24T16:00:00Z') },
            { xAxis: Date.parse(props.rangeEnd ?? '2026-03-03T15:59:59Z') },
          ],
        ],
      },
    },
  ]
  if (showPrice.value) {
    series.push({
      id: 'brent-price',
      type: 'line',
      name: 'Brent 现货价',
      yAxisIndex: 0,
      data: categories.map((d) => [Date.parse(d + 'T00:00:00Z'), priceByDate.get(d) ?? null]),
      smooth: false,
      symbol: 'circle',
      symbolSize: 5,
      lineStyle: { width: 2, color: PRICE_COLOR },
      itemStyle: { color: PRICE_COLOR },
    })
  }
  if (showTraffic.value) {
    series.push({
      id: 'tanker-traffic',
      type: 'line',
      name: `油轮${directions[direction.value]}`,
      yAxisIndex: 1,
      data: categories.map((d) => [Date.parse(d + 'T00:00:00Z'), passageByDate.get(d)?.[direction.value] ?? null]),
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
          value: [number, number | null]
        }>
        const header = list.length ? new Date(Number(list[0].axisValue)).toISOString().slice(0, 10) + ' UTC' : ''
        const lines = list.map((p) => {
          const unit = p.seriesName.startsWith('油轮') ? '次' : '美元/桶'
          const value = p.value[1] == null ? '—' : `${p.value[1]} ${unit}`
          return `${p.marker} ${p.seriesName}：<b>${value}</b>`
        })
        return [header, ...lines].join('<br/>')
      },
    },
    xAxis: {
      type: 'time',
      splitNumber: (chartEl.value?.clientWidth ?? 800) < 550 ? 4 : 10,
      min: Date.parse(categories[0]! + 'T00:00:00Z'),
      max: Date.parse(categories.at(-1)! + 'T00:00:00Z'),
      axisLabel: { color: '#8B98A8', fontSize: 10, formatter: (value: number) => new Date(value).toISOString().slice(5, 10) },
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

function applySeries(changedId: 'brent-price' | 'tanker-traffic') {
  // 稳定 id 保留未变化曲线；只让重新加入的曲线播放入场动画。
  const series = (buildOption().series as LineSeriesOption[]).map(series => ({
    ...series, animation: series.id === changedId,
  }))
  chart?.setOption({ series }, { replaceMerge: ['series'] })
}

function applyWindow() {
  const window = (buildOption().series as LineSeriesOption[])[0]!
  chart?.setOption({ series: [
    { id: 'replay-window', markLine: window.markLine, markArea: window.markArea },
    ...staticCurves(),
  ] })
}

function staticCurves(): LineSeriesOption[] {
  return [
    ...(showPrice.value ? [{ id: 'brent-price', animation: false }] : []),
    ...(showTraffic.value ? [{ id: 'tanker-traffic', animation: false }] : []),
  ]
}

function togglePrice() {
  showPrice.value = !showPrice.value
  applySeries('brent-price')
}

function toggleTraffic() {
  showTraffic.value = !showTraffic.value
  applySeries('tanker-traffic')
}

function resizeChart() {
  if (!chartEl.value || !chartEl.value.clientWidth || !chartEl.value.clientHeight) return
  if (!chart) { chart = echarts.init(chartEl.value); chart.setOption(buildOption()) }
  else {
    chart.setOption({ series: staticCurves() })
    chart.resize()
    chart.setOption({ xAxis: { splitNumber: chartEl.value.clientWidth < 550 ? 4 : 10 } })
  }
}
watch([() => props.time, () => props.rangeStart, () => props.rangeEnd], applyWindow)
watch(direction, () => applySeries('tanker-traffic'))
onMounted(() => {
  if (!chartEl.value) return
  resizeObserver = new ResizeObserver(resizeChart)
  resizeObserver.observe(chartEl.value)
  resizeChart()
})

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  resizeObserver = null
  chart?.dispose()
  chart = null
})
</script>

<template>
  <p class="chart-window-note">完整历史窗口 · 日统计按 UTC 归日<span>当前回放 {{ formatTime(time, true) }} {{ zoneLabel() }}</span></p>
  <div class="chart-toggles">
    <button
      type="button"
      class="chart-toggle"
      :class="{ active: showPrice }"
      role="switch"
      aria-label="Brent 油价（左轴）"
      :aria-checked="showPrice"
      @click="togglePrice"
    >
      <i class="toggle-dot" :style="{ background: PRICE_COLOR }"></i>
      Brent 油价（左轴）
      <span class="toggle-state">{{ showPrice ? '显示' : '隐藏' }}</span>
      <span class="toggle-track" aria-hidden="true"><span></span></span>
    </button>
    <button
      type="button"
      class="chart-toggle"
      :class="{ active: showTraffic }"
      role="switch"
      aria-label="油轮通行量（右轴）"
      :aria-checked="showTraffic"
      @click="toggleTraffic"
    >
      <i class="toggle-dot" :style="{ background: TRAFFIC_COLOR }"></i>
      油轮通行量（右轴）
      <span class="toggle-state">{{ showTraffic ? '显示' : '隐藏' }}</span>
      <span class="toggle-track" aria-hidden="true"><span></span></span>
    </button>
  </div>
  <div class="traffic-direction" role="group" aria-label="油轮通行方向">
    <button v-for="(label, key) in directions" :key="key" :aria-pressed="direction === key" :class="{ active: direction === key }" @click="direction = key">{{ label }}</button>
  </div>
  <div
    ref="chartEl"
    class="market-chart"
    role="img"
    aria-label="布伦特原油现货价格与油轮通行量双轴折线图，覆盖 2026-02-18 至 2026-03-10"
  ></div>
</template>
