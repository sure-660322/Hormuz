import { computed, ref } from 'vue'
import {
  fetchMapShips,
  fetchPlaybackPositions,
  fetchSimulationMeta,
  describeApiError,
  type ApiShipPosition,
  type ApiMapShip,
} from '../api'

export function usePlayback() {
  const ships = ref<ApiMapShip[]>([])
  const frames = ref<{ time: string; positions: ApiShipPosition[] }[]>([])
  const tracks = ref<Record<number, ApiShipPosition[]>>({})
  const index = ref(0)
  const loading = ref(true)
  const error = ref('')
  const time = computed(() => frames.value[index.value]?.time ?? null)
  const times = computed(() => frames.value.map((frame) => frame.time))
  const currentShips = computed(() => {
    if (!time.value) return []
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
  async function load() {
    loading.value = true
    error.value = ''
    try {
      const [meta, identities] = await Promise.all([
        fetchSimulationMeta(),
        fetchMapShips(),
      ])
      if (!meta.start_at || !meta.end_at || !meta.frame_count)
        throw new Error('暂无可回放的船位数据')
      const start = Date.parse(meta.start_at)
      const end = Date.parse(meta.end_at)
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
      const step = Math.max(1, meta.frame_interval_seconds) * 1000
      const displayTimes: number[] = []
      for (let at = start; at < end; at += step) displayTimes.push(at)
      displayTimes.push(end)
      // Display ticks do not resample or interpolate the underlying reports.
      frames.value = displayTimes.map((at) => ({ time: new Date(at).toISOString(), positions: [] }))
      index.value = 0
    } catch (e) {
      ships.value = []
      frames.value = []
      tracks.value = {}
      index.value = 0
      error.value = describeApiError(e, '回放数据加载失败')
    } finally {
      loading.value = false
    }
  }
  function seek(at: string) {
    const target = frames.value.findIndex(
      (frame) => Date.parse(frame.time) >= Date.parse(at),
    )
    index.value = target < 0 ? Math.max(0, frames.value.length - 1) : target
  }
  return {
    ships,
    frames,
    tracks,
    index,
    loading,
    error,
    time,
    times,
    currentShips,
    load,
    seek,
  }
}
