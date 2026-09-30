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

const chartEl = ref<HTMLElement | null>(null)
let chart: ReturnType<typeof echarts.init> | null = null
let resizeObserver: ResizeObserver | null = null

onMounted(() => {
  if (!chartEl.value) return
  chart = echarts.init(chartEl.value)
  const option: ChartOption = {
    grid: { top: 28, right: 18, bottom: 28, left: 52 },
    tooltip: {
      trigger: 'axis',
      valueFormatter: (value) => `${Number(value).toFixed(2)} 美元/桶`,
    },
    xAxis: {
      type: 'category',
      boundaryGap: false,
      data: brentDailyPrices.map((d) => d.date.slice(5)),
      axisLabel: { color: '#8B98A8', fontSize: 10 },
      axisLine: { lineStyle: { color: '#28323F' } },
    },
    yAxis: {
      type: 'value',
      min: 65,
      axisLabel: { color: '#8B98A8', fontSize: 10, formatter: '{value}' },
      splitLine: { lineStyle: { color: '#28323F' } },
    },
    series: [
      {
        type: 'line',
        name: 'Brent 现货价',
        data: brentDailyPrices.map((d) => d.price),
        smooth: false,
        symbol: 'circle',
        symbolSize: 5,
        lineStyle: { width: 2, color: '#E8B14E' },
        itemStyle: { color: '#E8B14E' },
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
    ],
  }
  chart.setOption(option)
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
  <div
    ref="chartEl"
    class="brent-chart"
    role="img"
    aria-label="布伦特原油现货价格折线图，覆盖 2026-02-18 至 2026-03-10"
  ></div>
</template>
