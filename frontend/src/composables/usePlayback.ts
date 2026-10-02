import { computed, getCurrentInstance, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import {
  fetchMapShips,
  fetchPlaybackPositions,
  fetchShipSnapshot,
  fetchShipSnapshotWindow,
  fetchSimulationMeta,
  describeApiError,
  type ApiShipPosition,
  type ApiMapShip,
} from '../api'

export function usePlayback() {
  const scopeShipId = ref<number | null>(null)
  const ships = ref<ApiMapShip[]>([])
  const snapshotShips = ref<ApiMapShip[]>([])
  const snapshotAt = ref<string | null>(null)
  const isRealAis = ref(false)
  const hasEvents = ref(true)
  const hasDerived = ref(true)
  const snapshotLoading = ref(false)
  const snapshotError = ref('')
  const frames = ref<{ time: string; positions: ApiShipPosition[] }[]>([])
  const tracks = ref<Record<number, ApiShipPosition[]>>({})
  const index = ref(0)
  const loading = ref(true)
  const error = ref('')
  const requestedTime = computed(() => frames.value[index.value]?.time ?? null)
  const time = computed(() => isRealAis.value ? snapshotAt.value : requestedTime.value)
  const times = computed(() => frames.value.map((frame) => frame.time))
  const frameReady = computed(() => !isRealAis.value || (
    snapshotAt.value === requestedTime.value && !snapshotLoading.value && !snapshotError.value
  ))
  const currentShips = computed(() => {
    if (!time.value) return []
    if (isRealAis.value) return snapshotShips.value
    const at = Date.parse(time.value)
    return ships.value.flatMap((ship) => {
      const samples = tracks.value[ship.id] ?? []
      let low = 0, high = samples.length
      while (low < high) {
        const middle = Math.floor((low + high) / 2)
        if (Date.parse(samples[middle]!.recorded_at) <= at) low = middle + 1
        else high = middle
      }
      const position = samples[low - 1]
      return position ? [{ ...ship, ...position, id: ship.id }] : []
    })
  })
  let snapshotRequest: AbortController | null = null
  let snapshotTimer: ReturnType<typeof setTimeout> | undefined
  let requestVersion = 0
  let loadVersion = 0
  const snapshotCache = new Map<string, ApiMapShip[]>()
  let windowRequest: { times: string[]; controller: AbortController; promise: Promise<void> } | null = null
  function remember(at: string, shipsAt: ApiMapShip[]) {
    snapshotCache.delete(at)
    snapshotCache.set(at, shipsAt)
    while (snapshotCache.size > 12) snapshotCache.delete(snapshotCache.keys().next().value!)
  }
  function commit(at: string, shipsAt: ApiMapShip[]) {
    snapshotShips.value = scopeShipId.value === null ? shipsAt : shipsAt.filter(s => s.id === scopeShipId.value)
    snapshotAt.value = at
    snapshotLoading.value = false
    snapshotError.value = ''
  }
  function fetchWindow(startIndex: number) {
    const windowTimes = times.value.slice(startIndex, startIndex + 4)
    const controller = new AbortController()
    const promise = fetchShipSnapshotWindow(windowTimes, controller.signal)
      .then((result) => {
        for (const frame of result.frames) remember(new Date(frame.at).toISOString(), frame.ships)
      })
      .finally(() => {
        if (windowRequest?.controller === controller) windowRequest = null
      })
    windowRequest = { times: windowTimes, controller, promise }
    return promise
  }
  function prefetchAfter(position: number) {
    const next = position + 2
    const nextAt = times.value[next]
    if (!nextAt || snapshotCache.has(nextAt) || windowRequest) return
    void fetchWindow(next).catch(() => { /* Selected-frame requests retry failed prefetches. */ })
  }
  async function loadSelectedFrame(at: string, position: number) {
    const version = ++requestVersion
    snapshotLoading.value = true
    snapshotError.value = ''
    try {
      let cached = snapshotCache.get(at)
      if (!cached) {
        if (windowRequest && !windowRequest.times.includes(at)) {
          windowRequest.controller.abort()
          windowRequest = null
        }
        if (windowRequest) await windowRequest.promise
        else await fetchWindow(position)
        cached = snapshotCache.get(at)
      }
      if (version !== requestVersion) return
      if (!cached) throw new Error('快照窗口未返回所选时刻')
      commit(at, cached)
      prefetchAfter(position)
    } catch (e) {
      if (version !== requestVersion) return
      snapshotLoading.value = false
      snapshotError.value = describeApiError(e, '船位快照加载失败')
    }
  }
  async function loadSnapshot(at: string) {
    snapshotRequest?.abort()
    const request = new AbortController()
    snapshotRequest = request
    const version = ++requestVersion
    snapshotLoading.value = true
    snapshotError.value = ''
    try {
      const result = await fetchShipSnapshot(at, request.signal)
      if (version !== requestVersion) return
      remember(at, result)
      commit(at, result)
    } catch (e) {
      if (version !== requestVersion || request.signal.aborted) return
      snapshotShips.value = []
      snapshotAt.value = at
      snapshotError.value = describeApiError(e, '船位快照加载失败')
    } finally {
      if (version === requestVersion) snapshotLoading.value = false
    }
  }
  watch(requestedTime, (at) => {
    clearTimeout(snapshotTimer)
    if (!isRealAis.value || !at) return
    snapshotRequest?.abort()
    ++requestVersion
    snapshotLoading.value = true
    snapshotError.value = ''
    const position = index.value
    const cached = snapshotCache.get(at)
    if (cached) {
      commit(at, cached)
      prefetchAfter(position)
    } else {
      snapshotTimer = setTimeout(() => { void loadSelectedFrame(at, position) }, 120)
    }
  })
  if (getCurrentInstance()) onBeforeUnmount(() => {
    clearTimeout(snapshotTimer)
    snapshotRequest?.abort()
    windowRequest?.controller.abort()
  })
  async function load(scope?: { start_at: string; end_at: string; ship_id: number }) {
    const version = ++loadVersion
    scopeShipId.value = scope?.ship_id ?? null
    loading.value = true
    error.value = ''
    clearTimeout(snapshotTimer)
    snapshotRequest?.abort()
    windowRequest?.controller.abort()
    windowRequest = null
    snapshotCache.clear()
    ++requestVersion
    try {
      const meta = await fetchSimulationMeta()
      if (version !== loadVersion) return
      if (!scope && (!meta.start_at || !meta.end_at || !meta.frame_count))
        throw new Error('暂无可回放的船位数据')
      const start = Date.parse(scope?.start_at ?? meta.start_at!)
      const end = Date.parse(scope?.end_at ?? meta.end_at!)
      if (!Number.isFinite(start) || !Number.isFinite(end) || start >= end) throw new Error('回放窗口无效')
      isRealAis.value = !!scope || meta.is_simulated === false
      hasEvents.value = meta.has_events !== false
      hasDerived.value = meta.has_derived !== false
      const step = Math.max(1, meta.frame_interval_seconds) * 1000
      const displayTimes: number[] = []
      for (let at = start; at < end; at += step) displayTimes.push(at)
      displayTimes.push(end)
      if (isRealAis.value) {
        ships.value = []
        tracks.value = {}
        snapshotShips.value = []
        snapshotAt.value = null
        frames.value = displayTimes.map((at) => ({ time: new Date(at).toISOString(), positions: [] }))
        index.value = 0
        await nextTick()
        clearTimeout(snapshotTimer)
        await loadSnapshot(requestedTime.value!)
        return
      }
      const identities = await fetchMapShips()
      const positionsById = new Map<number, ApiShipPosition>()
      // The API accepts at most 24 hours. Inclusive boundaries can repeat a point.
      let cursor = start
      do {
        const until = Math.min(end, cursor + 24 * 60 * 60 * 1000)
        const chunk = await fetchPlaybackPositions(new Date(cursor).toISOString(), new Date(until).toISOString())
        chunk.forEach((position) => positionsById.set(position.id, position))
        cursor = until
      } while (cursor < end)
      const byShip: Record<number, ApiShipPosition[]> = {}
      for (const p of positionsById.values()) {
        ;(byShip[p.ship_id] ??= []).push(p)
      }
      Object.values(byShip).forEach((track) =>
        track.sort(
          (a, b) => Date.parse(a.recorded_at) - Date.parse(b.recorded_at),
        ),
      )
      ships.value = identities
      tracks.value = byShip
      // Display ticks do not resample or interpolate the underlying reports.
      frames.value = displayTimes.map((at) => ({ time: new Date(at).toISOString(), positions: [] }))
      index.value = 0
    } catch (e) {
      if (version !== loadVersion) return
      ships.value = []
      frames.value = []
      tracks.value = {}
      snapshotShips.value = []
      snapshotAt.value = null
      index.value = 0
      error.value = describeApiError(e, '回放数据加载失败')
    } finally {
      if (version === loadVersion) loading.value = false
    }
  }
  function seek(at: string) {
    const target = frames.value.findIndex(
      (frame) => Date.parse(frame.time) >= Date.parse(at),
    )
    index.value = target < 0 ? Math.max(0, frames.value.length - 1) : target
  }
  function retrySnapshot() {
    if (isRealAis.value && requestedTime.value) {
      void loadSelectedFrame(requestedTime.value, index.value)
    }
  }
  return {
    ships,
    frames,
    tracks,
    index,
    loading,
    error,
    time,
    requestedTime,
    times,
    currentShips,
    frameReady,
    isRealAis,
    hasEvents,
    hasDerived,
    snapshotLoading,
    snapshotError,
    load,
    seek,
    retrySnapshot,
    scopeShipId,
  }
}
