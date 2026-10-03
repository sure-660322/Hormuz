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
// 减少动态偏好：覆盖图表入场/退出动画（issue #31）。
const motionQuery = window.matchMedia('(prefers-reduced-motion: reduce)')
const motionAllowed = ref(!motionQuery.matches)
function onMotionPreferenceChange() { motionAllowed.value = !motionQuery.matches }
type CurveId = 'brent-price' | 'tanker-traffic'
const exits = new Map<CurveId, { frame: number; started: number; opacity: number }>()
const EXIT_DURATION = 400

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
  if (showPrice.value || exits.has('brent-price')) {
    series.push({
      id: 'brent-price',
      type: 'line',
      name: 'Brent 现货价',
      yAxisIndex: 0,
      data: categories.map((d) => [Date.parse(d + 'T00:00:00Z'), priceByDate.get(d) ?? null]),
      smooth: false,
      symbol: 'circle',
      symbolSize: 5,
      lineStyle: { width: 2, color: PRICE_COLOR, opacity: exits.get('brent-price')?.opacity ?? 1 },
      itemStyle: { color: PRICE_COLOR, opacity: exits.get('brent-price')?.opacity ?? 1 },
      emphasis: { lineStyle: { width: 3.5 } },
    })
  }
  if (showTraffic.value || exits.has('tanker-traffic')) {
    series.push({
      id: 'tanker-traffic',
      type: 'line',
      name: `油轮${directions[direction.value]}`,
      yAxisIndex: 1,
      data: categories.map((d) => [Date.parse(d + 'T00:00:00Z'), passageByDate.get(d)?.[direction.value] ?? null]),
      smooth: false,
      symbol: 'diamond',
      symbolSize: 6,
      lineStyle: { width: 2, color: TRAFFIC_COLOR, opacity: exits.get('tanker-traffic')?.opacity ?? 1 },
      itemStyle: { color: TRAFFIC_COLOR, opacity: exits.get('tanker-traffic')?.opacity ?? 1 },
      emphasis: { lineStyle: { width: 3.5 } },
    })
  }
  return {
    // 开关重新加入序列时，用入场动画（从左描线）而不是直接弹出。
    animation: motionAllowed.value,
    animationDuration: motionAllowed.value ? 900 : 0,
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

function applySeries(changedId: CurveId) {
  // 稳定 id 保留未变化曲线；只让重新加入的曲线播放入场动画。
  const series = (buildOption().series as LineSeriesOption[]).map(series => ({
    ...series, animation: series.id === changedId && !exits.has(changedId),
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
    ...(showPrice.value || exits.has('brent-price') ? [{ id: 'brent-price', animation: false }] : []),
    ...(showTraffic.value || exits.has('tanker-traffic') ? [{ id: 'tanker-traffic', animation: false }] : []),
  ]
}

function transitionCurve(id: CurveId, visible: boolean) {
  const previousExit = exits.get(id)
  if (previousExit) cancelAnimationFrame(previousExit.frame)
  exits.delete(id)
  if (visible || !chart || !motionAllowed.value) { applySeries(id); return }
  const exit = { frame: 0, started: performance.now(), opacity: 1 }
  exits.set(id, exit)
  applySeries(id)
  const fade = (now: number) => {
    if (exits.get(id) !== exit || !chart) return
    const progress = Math.min((now - exit.started) / EXIT_DURATION, 1)
    exit.opacity = (1 - progress) ** 2
    // 两条序列使用独立固定颜色，只改变目标线与符号的透明度。
    const color = id === 'brent-price' ? PRICE_COLOR : TRAFFIC_COLOR
    for (const element of chart.getZr().storage.getDisplayList()) {
      const style = element.style as { stroke?: string; fill?: string }
      if (style.stroke === color || style.fill === color) {
        element.style.opacity = exit.opacity
        element.dirty()
      }
    }
    if (progress < 1) exit.frame = requestAnimationFrame(fade)
    else { exits.delete(id); applySeries(id) }
  }
  exit.frame = requestAnimationFrame(fade)
}

function togglePrice() {
  showPrice.value = !showPrice.value
  transitionCurve('brent-price', showPrice.value)
}

function toggleTraffic() {
  showTraffic.value = !showTraffic.value
  transitionCurve('tanker-traffic', showTraffic.value)
}

// 图例悬停/聚焦强调对应曲线（issue #34）；颜色之外用线宽变化传达。
function hoverCurve(id: CurveId, on: boolean) {
  if (!chart || !motionAllowed.value) return
  chart.dispatchAction({ type: on ? 'highlight' : 'downplay', seriesId: id })
}
watch(motionAllowed, allowed => {
  chart?.setOption({ animation: allowed, animationDuration: allowed ? 900 : 0 })
})

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
  motionQuery.addEventListener('change', onMotionPreferenceChange)
  resizeObserver = new ResizeObserver(resizeChart)
  resizeObserver.observe(chartEl.value)
  resizeChart()
})

onBeforeUnmount(() => {
  motionQuery.removeEventListener('change', onMotionPreferenceChange)
  for (const exit of exits.values()) cancelAnimationFrame(exit.frame)
  exits.clear()
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
      @mouseenter="hoverCurve('brent-price', true)"
      @mouseleave="hoverCurve('brent-price', false)"
      @focus="hoverCurve('brent-price', true)"
      @blur="hoverCurve('brent-price', false)"
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
      @mouseenter="hoverCurve('tanker-traffic', true)"
      @mouseleave="hoverCurve('tanker-traffic', false)"
      @focus="hoverCurve('tanker-traffic', true)"
      @blur="hoverCurve('tanker-traffic', false)"
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
