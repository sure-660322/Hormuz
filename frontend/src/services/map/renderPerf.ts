// 渲染性能探针：仅在 URL 携带 ?perf=1 时启用，记录每次地图渲染任务的耗时，
// 并通过 window.__hormuzPerf 暴露统计接口，供性能验证脚本读取（中位数 / 最大值 / 样本数）。
// 默认完全关闭，对生产渲染零开销。
const enabled =
  typeof window !== 'undefined' &&
  new URLSearchParams(window.location.search).has('perf')

const MAX_SAMPLES = 2000
const buffers = new Map<string, number[]>()

export function recordRender(name: string, ms: number) {
  if (!enabled) return
  let buffer = buffers.get(name)
  if (!buffer) {
    buffer = []
    buffers.set(name, buffer)
  }
  buffer.push(ms)
  if (buffer.length > MAX_SAMPLES) buffer.splice(0, buffer.length - MAX_SAMPLES)
}

interface RenderStats {
  count: number
  medianMs: number
  maxMs: number
  p95Ms: number
}

function summarize(buffer: number[]): RenderStats {
  const sorted = [...buffer].sort((a, b) => a - b)
  const at = (fraction: number) =>
    sorted.length ? sorted[Math.min(sorted.length - 1, Math.floor(sorted.length * fraction))]! : 0
  return {
    count: buffer.length,
    medianMs: at(0.5),
    maxMs: sorted.length ? sorted[sorted.length - 1]! : 0,
    p95Ms: at(0.95),
  }
}

declare global {
  interface Window {
    __hormuzPerf?: {
      stats: () => Record<string, RenderStats>
      reset: () => void
    }
  }
}

if (enabled && typeof window !== 'undefined') {
  window.__hormuzPerf = {
    stats: () =>
      Object.fromEntries(
        [...buffers.entries()].map(([name, buffer]) => [name, summarize(buffer)]),
      ),
    reset: () => buffers.clear(),
  }
}
