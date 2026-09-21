import { recordRender } from './renderPerf'

// 统一渲染调度：回放时间快速变化时，同一浏览器帧内对同一渲染任务只保留最新一次，
// 过时的中间状态直接丢弃（latest-state-wins），避免回放积压旧渲染任务挤占主线程。
// 滑块等 UI 状态由 Vue 同步维护，地图渲染按浏览器帧率（requestAnimationFrame）批量更新。
export class RenderScheduler {
  private pending = new Map<string, () => void>()
  private frameHandle: number | null = null

  schedule(name: string, task: () => void) {
    this.pending.set(name, task)
    if (this.frameHandle === null) {
      this.frameHandle = requestAnimationFrame(() => this.flush())
    }
  }

  /** 立即执行当前所有待处理任务（用于组件卸载前收尾）。 */
  flushNow() {
    if (this.frameHandle !== null) {
      cancelAnimationFrame(this.frameHandle)
      this.frameHandle = null
    }
    this.flush()
  }

  cancel() {
    if (this.frameHandle !== null) {
      cancelAnimationFrame(this.frameHandle)
      this.frameHandle = null
    }
    this.pending.clear()
  }

  private flush() {
    this.frameHandle = null
    if (!this.pending.size) return
    const tasks = [...this.pending.entries()]
    this.pending.clear()
    for (const [name, task] of tasks) {
      const start = performance.now()
      task()
      recordRender(name, performance.now() - start)
    }
  }
}
