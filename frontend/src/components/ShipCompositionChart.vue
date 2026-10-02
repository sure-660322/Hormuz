<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts/core'
import { PieChart, type PieSeriesOption } from 'echarts/charts'
import { TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import type { shipComposition, ShipGroup } from '../domain/overview'

echarts.use([PieChart, TooltipComponent, CanvasRenderer])
const props = defineProps<{ groups: ReturnType<typeof shipComposition> }>()
const emit = defineEmits<{ select: [group: ShipGroup] }>()
const total = computed(() => props.groups.reduce((sum, group) => sum + group.count, 0))
const description = computed(() => props.groups.map(group => `${group.label} ${group.count} 艘，占 ${group.percent.toFixed(1)}%`).join('；'))
const chartEl = ref<HTMLElement | null>(null)
let chart: ReturnType<typeof echarts.init> | null = null
let observer: ResizeObserver | null = null
// 减少动态偏好：饼图关闭入场动画与高亮缩放（issue #31）。
const motionQuery = window.matchMedia('(prefers-reduced-motion: reduce)')
const motionAllowed = ref(!motionQuery.matches)
function onMotionPreferenceChange() {
  motionAllowed.value = !motionQuery.matches
  updateChart()
}

function updateChart() {
  const series: PieSeriesOption = {
    type: 'pie', radius: '80%', showEmptyCircle: false,
    animation: motionAllowed.value,
    label: { position: 'inside', formatter: params => `${props.groups.find(group => group.label === params.name)?.percent.toFixed(1)}%`, color: '#fff', fontSize: 13 },
    minShowLabelAngle: 12,
    itemStyle: { borderColor: '#161d25', borderWidth: 2 },
    emphasis: { scaleSize: motionAllowed.value ? 5 : 0 },
    data: props.groups.filter(group => group.count > 0).map(group => ({
      name: group.label, value: group.count, itemStyle: { color: group.color },
    })),
  }
  chart?.setOption({ tooltip: { trigger: 'item', confine: true, valueFormatter: (value: unknown) => `${value} 艘` }, series: [series] })
}
function resizeChart() {
  if (!chartEl.value?.clientWidth || !chartEl.value.clientHeight) return
  if (!chart) {
    chart = echarts.init(chartEl.value)
    chart.on('click', params => {
      const group = props.groups.find(group => group.label === params.name && group.count > 0)
      if (group) emit('select', group.key)
    })
    updateChart()
  } else chart.resize()
}
watch(() => props.groups, updateChart)
onMounted(() => {
  motionQuery.addEventListener('change', onMotionPreferenceChange)
  observer = new ResizeObserver(resizeChart)
  if (chartEl.value) observer.observe(chartEl.value)
  resizeChart()
})
onBeforeUnmount(() => { motionQuery.removeEventListener('change', onMotionPreferenceChange); observer?.disconnect(); chart?.dispose() })
</script>

<template>
  <div class="composition-visual">
    <div class="composition-pie-container">
      <div ref="chartEl" class="composition-pie" role="img" :aria-label="total ? `船舶构成饼图：${description}` : '船舶构成饼图：当前无船位快照'"></div>
      <p v-if="!total" class="composition-pie-empty">暂无船位快照</p>
    </div>
    <div class="composition-legend" aria-label="按船舶类型筛选">
      <button v-for="group in groups" :key="group.key" class="composition-row" :disabled="!group.count" @click="emit('select', group.key)">
        <i :style="{ background: group.color }"></i><span>{{ group.label }}</span><strong>{{ group.count }} 艘</strong><small>{{ group.percent.toFixed(1) }}%</small><span>›</span>
      </button>
    </div>
  </div>
  <p v-if="total" class="composition-note">点击扇区或类别，查看对应船舶。</p>
</template>
