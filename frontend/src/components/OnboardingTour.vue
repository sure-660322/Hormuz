<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

const emit = defineEmits<{ step: [index: number]; close: [completed: boolean] }>()
const steps = [
  {
    title: '从这里开始了解海峡态势',
    text: '用几步认识霍尔木兹海事态势分析系统：查看历史船位、浏览新闻，再按时间和区域展开调查。',
    hint: '引导中只介绍功能，不会发起分析。随时可以跳过，稍后从顶栏「使用引导」重新打开。',
  },
  {
    title: '先看态势总览', target: '[data-tour="overview"]',
    text: '在「态势总览」查看船舶构成、历史通行趋势与关键新闻。点击感兴趣的船型或事件，可以继续进入地图调查。',
    hint: '顶部三个入口分别用于查看总览、探索地图和阅读典型案例。',
  },
  {
    title: '查找新闻与船舶', target: '[data-tour="explorer"]', maxHeight: 170,
    text: '在左侧切换「新闻事件」和「船舶」。新闻可按类型筛选；船舶可按船名、MMSI 或 IMO 搜索，选中后查看详情。',
    hint: '窄屏时用顶栏「查找」展开列表。船舶列表随当前回放时刻更新。',
  },
  {
    title: '在地图上查看位置与轨迹', target: '[data-tour="map"]',
    text: '拖动、缩放地图，点击船舶查看详情和轨迹；点击新闻标记阅读摘要，再打开详情查看报道来源。',
    hint: '船位来自历史 AIS，新闻来自独立报道。两者在地图上接近，不代表存在真实关联。',
  },
  {
    title: '沿时间回看海峡动态', target: '[data-tour="timeline"]',
    text: '拖动时间滑杆选择时刻，或使用播放与步进按钮回看船位变化。新闻会按已知事件日期逐步出现。',
    hint: '留意当前时区；日期级新闻只表达日期顺序，不代表精确发生时刻。',
  },
  {
    title: '按区域查看船舶活动', target: '[data-tour="tools"] [data-testid="tool-area"]',
    text: '点击「区域」打开分析面板，使用默认区域或在地图拖拽圈选矩形，查询时刻在场、时段活动，或比较两个时段。',
    hint: '旁边的「图层」调整地图显示，「通行」统计或比较过航。工具在右侧展开，左边小三角可重新打开新闻栏。结果以已有 AIS 观测和覆盖范围为限。',
  },
  {
    title: '跟着典型案例阅读证据', target: '[data-tour="cases"]',
    text: '在「典型案例」点击一条中文新闻，查看相关船舶的轨迹，再从证据页访问报道原文。虚线仅示意缺报区间。退出案例后可返回原来的探索状态。',
    hint: '案例区分报道内容与 AIS 观测，缺报不代表沉没或主动关闭 AIS。',
  },
  {
    title: '让智能体协助调查', target: '[data-tour="tools"] [aria-label="智能体"]',
    text: '点击「智能体」，用自然语言提出问题。尽量给出船名、时间或区域，例如「这艘船在这个时段有哪些报位？」',
    hint: '结合工具结果和来源核对结论。现在可以开始探索，顶栏「使用引导」随时为你保留。',
  },
]
const index = ref(0)
const step = computed(() => steps[index.value]!)
const dialog = ref<HTMLElement | null>(null)
const nextButton = ref<HTMLButtonElement | null>(null)
const rect = ref<{ left: number; top: number; width: number; height: number } | null>(null)
const cardPosition = ref({ left: '12px', top: '12px' })
let observer: ResizeObserver | undefined
let frame = 0

function place() {
  const width = window.innerWidth
  const height = window.innerHeight
  const target = step.value.target ? document.querySelector<HTMLElement>(step.value.target) : null
  const bounds = target?.getBoundingClientRect()
  if (bounds && bounds.width > 0 && bounds.height > 0) {
    const left = Math.max(6, bounds.left - 5)
    const top = Math.max(6, bounds.top - 5)
    const right = Math.min(width - 6, bounds.right + 5)
    const bottom = Math.min(height - 6, bounds.top + Math.min(bounds.height, step.value.maxHeight ?? bounds.height) + 5)
    rect.value = right > left && bottom > top ? { left, top, width: right - left, height: bottom - top } : null
  } else rect.value = null
  const card = dialog.value?.getBoundingClientRect()
  if (!card) return
  const gap = 18
  const r = rect.value
  let left = (width - card.width) / 2
  let top = (height - card.height) / 2
  if (r) {
    const candidates = [
      { left: r.left + r.width + gap, top: r.top },
      { left: r.left - card.width - gap, top: r.top },
      { left: r.left + (r.width - card.width) / 2, top: r.top + r.height + gap },
      { left: r.left + (r.width - card.width) / 2, top: r.top - card.height - gap },
    ]
    const fit = candidates.find(p => p.left >= 12 && p.left + card.width <= width - 12 && p.top >= 12 && p.top + card.height <= height - 12)
    if (fit) ({ left, top } = fit)
    else {
      left = width > 760 ? r.left + 24 : 12
      top = r.top + r.height / 2 < height / 2 ? height - card.height - 18 : 18
    }
  }
  cardPosition.value = {
    left: `${Math.max(12, Math.min(left, width - card.width - 12))}px`,
    top: `${Math.max(12, Math.min(top, height - card.height - 12))}px`,
  }
}
function schedulePlace() {
  cancelAnimationFrame(frame)
  frame = requestAnimationFrame(place)
}
async function showStep() {
  emit('step', index.value)
  await nextTick()
  observer?.disconnect()
  if (dialog.value) observer?.observe(dialog.value)
  const target = step.value.target ? document.querySelector(step.value.target) : null
  if (target) observer?.observe(target)
  place()
  nextButton.value?.focus({ preventScroll: true })
}
function keyboard(event: KeyboardEvent) {
  // Capture before workbench and timeline shortcuts can change the underlying view.
  event.stopImmediatePropagation()
  if (event.key === 'Escape') { event.preventDefault(); emit('close', false) }
  else if (event.key === 'Tab') {
    const buttons = [...(dialog.value?.querySelectorAll<HTMLButtonElement>('button:not(:disabled)') ?? [])]
    const first = buttons[0]
    const last = buttons.at(-1)
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus() }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus() }
  } else if (event.key === 'ArrowRight') {
    event.preventDefault()
    if (index.value < steps.length - 1) index.value++
  } else if (event.key === 'ArrowLeft') {
    event.preventDefault()
    if (index.value > 0) index.value--
  }
}
watch(index, showStep)
onMounted(() => {
  observer = new ResizeObserver(schedulePlace)
  window.addEventListener('resize', schedulePlace)
  window.addEventListener('scroll', schedulePlace, true)
  window.addEventListener('keydown', keyboard, true)
  void showStep()
})
onBeforeUnmount(() => {
  observer?.disconnect()
  cancelAnimationFrame(frame)
  window.removeEventListener('resize', schedulePlace)
  window.removeEventListener('scroll', schedulePlace, true)
  window.removeEventListener('keydown', keyboard, true)
})
</script>

<template>
  <Teleport to="body">
    <div class="tour-overlay" :class="{ 'tour-centered': !rect }" data-testid="onboarding">
      <div v-if="rect" class="tour-spotlight" :style="{ left: `${rect.left}px`, top: `${rect.top}px`, width: `${rect.width}px`, height: `${rect.height}px` }" aria-hidden="true"></div>
      <section ref="dialog" class="tour-card" :style="cardPosition" role="dialog" aria-modal="true" aria-labelledby="tour-title" aria-describedby="tour-description tour-hint">
        <div class="tour-meta"><span>使用引导</span><span aria-live="polite">{{ index + 1 }} / {{ steps.length }}</span></div>
        <div class="tour-progress" aria-hidden="true"><span v-for="(_, i) in steps" :key="i" :class="{ reached: i <= index }"></span></div>
        <h2 id="tour-title">{{ step.title }}</h2>
        <p id="tour-description">{{ step.text }}</p>
        <p id="tour-hint" class="tour-hint">{{ step.hint }}</p>
        <footer class="tour-actions">
          <button type="button" class="tour-skip" @click="emit('close', false)">跳过引导</button>
          <button v-if="index > 0" type="button" @click="index--">上一步</button>
          <button ref="nextButton" type="button" class="tour-next" @click="index === steps.length - 1 ? emit('close', true) : index++">{{ index === steps.length - 1 ? '开始使用' : index === 0 ? '开始了解' : '下一步' }}</button>
        </footer>
      </section>
    </div>
  </Teleport>
</template>

<style scoped>
.tour-overlay { position: fixed; inset: 0; z-index: 10000; isolation: isolate; --tour-blue: #216bc4; }
.tour-centered { background: rgb(40 72 99 / .26); }
.tour-spotlight { position: absolute; border: 2px solid #4398ed; border-radius: 8px; box-shadow: 0 0 0 100vmax rgb(40 72 99 / .26); pointer-events: none; }
.tour-card { position: absolute; width: min(410px, calc(100vw - 24px)); max-height: calc(100dvh - 24px); overflow-y: auto; padding: 24px; border: 1px solid #bed5e8; border-radius: 16px; background: #e8f2fa; color: #20394c; color-scheme: light; box-shadow: 0 18px 64px rgb(28 61 89 / .22); }
.tour-meta { display: flex; align-items: center; justify-content: space-between; color: #52718a; font-size: 12px; }
.tour-meta span:last-child { padding: 2px 9px; border-radius: 12px; background: #d4e7f7; color: var(--tour-blue); }
.tour-progress { display: flex; gap: 5px; margin: 12px 0 22px; }
.tour-progress span { flex: 1; height: 3px; background: #c5dced; border-radius: 2px; }
.tour-progress .reached { background: #428cde; }
.tour-card h2 { font-size: 22px; line-height: 1.45; margin-bottom: 14px; }
.tour-card p { line-height: 1.85; font-size: 14px; }
.tour-card .tour-hint { margin-top: 16px; padding: 11px 13px; border: 1px solid #c5ddeb; border-radius: 8px; background: #d9eaf7; color: #45647d; font-size: 12px; }
.tour-actions { display: flex; align-items: center; gap: 8px; margin-top: 24px; }
.tour-actions button { padding: 8px 12px; border-color: #b4cfe4; background: #f0f7fc; color: #304f67; white-space: nowrap; }
.tour-actions button:hover { background: #edf5fd; border-color: #91bce5; }
.tour-actions button:focus-visible { outline-color: var(--tour-blue); }
.tour-actions .tour-skip { margin-right: auto; border-color: transparent; padding-inline: 0; color: #5f7485; }
.tour-actions .tour-next { background: var(--tour-blue); border-color: var(--tour-blue); color: #ffffff; font-weight: 650; }
.tour-actions .tour-next:hover { background: #195ba9; border-color: #195ba9; }
@media (max-width: 760px) {
  .tour-card { padding: 20px; }
  .tour-card h2 { font-size: 20px; }
  .tour-progress { margin-bottom: 16px; }
  .tour-actions { margin-top: 20px; }
}
</style>
