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
        throw new Error('暂无可回放的模拟位置数据')
      const positions = await fetchPlaybackPositions(meta.start_at, meta.end_at)
      const byTime = new Map<string, ApiShipPosition[]>()
      const byShip: Record<number, ApiShipPosition[]> = {}
      for (const p of positions) {
        const key = new Date(p.recorded_at).toISOString()
        if (!byTime.has(key)) byTime.set(key, [])
        byTime.get(key)!.push(p)
        ;(byShip[p.ship_id] ??= []).push(p)
      }
      Object.values(byShip).forEach((track) =>
        track.sort(
          (a, b) => Date.parse(a.recorded_at) - Date.parse(b.recorded_at),
        ),
      )
      ships.value = identities
      tracks.value = byShip
      frames.value = [...byTime]
        .sort(([a], [b]) => Date.parse(a) - Date.parse(b))
        .map(([time, positions]) => ({ time, positions }))
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
