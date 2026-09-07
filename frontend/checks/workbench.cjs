// Focused regression checks for time/identity/spatial semantics. No test framework.
const assert = require('node:assert/strict')
const { execFileSync } = require('node:child_process')
const { mkdirSync, writeFileSync } = require('node:fs')
const path = require('node:path')
const root = path.resolve(__dirname, '..')
const out = path.join(root, 'node_modules/.tmp/workbench-checks')
mkdirSync(out, { recursive: true })
execFileSync(
  process.execPath,
  [
    path.join(root, 'node_modules/typescript/bin/tsc'),
    'src/domain/maritime.ts',
    'src/services/workbench.ts',
    'src/composables/usePlayback.ts',
    '--ignoreConfig',
    '--target',
    'ES2022',
    '--module',
    'commonjs',
    '--moduleResolution',
    'node',
    '--ignoreDeprecations',
    '6.0',
    '--skipLibCheck',
    '--outDir',
    out,
  ],
  { cwd: root, stdio: 'inherit' },
)
writeFileSync(path.join(out, 'package.json'), '{"type":"commonjs"}')
const { distanceNm, inBounds, eventKind, shipType, projectPosition, sampleAge, shipStatus, displayZone, formatTime } = require(
  path.join(out, 'domain/maritime.js'),
)
const { localWorkbench } = require(path.join(out, 'services/workbench.js'))
const api = require(path.join(out, 'api.js'))
const { usePlayback } = require(path.join(out, 'composables/usePlayback.js'))

async function main() {
  assert.match(api.describeApiError(new TypeError('Failed to fetch'), '失败'), /无法连接数据服务/)
  assert.match(api.describeApiError(new DOMException('timeout', 'TimeoutError'), '失败'), /请求超时/)
  const center = { latitude: 0, longitude: 0 }
  assert.equal(distanceNm(center, center), 0)
  assert.ok(
    Math.abs(distanceNm(center, { latitude: 1, longitude: 0 }) - 60.04) < 0.1,
  )
  assert.equal(
    inBounds(
      { latitude: 1, longitude: 1 },
      { south: 0, north: 1, west: 0, east: 1 },
    ),
    true,
  )
  assert.equal(
    inBounds(
      { latitude: 1.01, longitude: 1 },
      { south: 0, north: 1, west: 0, east: 1 },
    ),
    false,
  )
  const ship = {
    id: 7,
    name: '模拟集装箱船 007',
    mmsi: '900000007',
    imo: null,
    callsign: null,
    flag: '模拟旗',
    ship_type: '集装箱船',
    ...center,
    speed: 10,
    course: 90,
    heading: null,
    recorded_at: '2026-08-30T00:10:00Z',
  }
  const oldEvent = {
    id: 1,
    title: '模拟事件',
    description: '',
    event_type: 'navigation_control',
    ...center,
    occurred_at: '2026-08-30T00:00:00Z',
    source_name: null,
    source_url: null,
  }
  const projected = projectPosition(center, 90, 1)
  assert.ok(Math.abs(distanceNm(center, projected) - 1) < 0.00001, '10 kn for 6 minutes is exactly 1 NM')
  assert.ok(projected.longitude > 0 && Math.abs(projected.latitude) < 0.00001, 'COG 90 projects east')
  assert.deepEqual(projectPosition(center, 0, 0), center, 'Stopped ship has zero vector')
  assert.equal(sampleAge(ship, '2026-08-30T00:20:00Z'), 10)
  assert.equal(shipStatus(ship, '2026-08-30T00:41:00Z').rank, 1, 'Staleness uses replay time, not wall clock')
  displayZone.value = 'UTC'
  assert.match(formatTime('2026-08-30T00:10:00Z'), /00:10/)
  displayZone.value = 'Asia/Shanghai'
  assert.match(formatTime('2026-08-30T00:10:00Z'), /08:10/)
  displayZone.value = 'UTC'
  const futureEvent = {
    ...oldEvent,
    id: 2,
    occurred_at: '2026-08-30T00:10:00Z',
  }
  const distantEvent = { ...oldEvent, id: 3, latitude: 1 }
  const result = localWorkbench.queryArea(
    { center, radiusNm: 10, at: '2026-08-30T00:05:00Z' },
    [ship, { ...ship, id: 8, latitude: 1 }],
    [oldEvent, futureEvent, distantEvent],
  )
  assert.deepEqual(
    result.ships.map((s) => s.id),
    [7],
  )
  assert.deepEqual(
    result.events.map((e) => e.id),
    [1],
    'Exclude future events and distant events',
  )
  assert.equal(result.source, 'local-simulation')
  assert.equal(localWorkbench.searchShips(' 900000007 ', [ship]).length, 1)
  assert.equal(localWorkbench.searchShips('集装箱', [ship]).length, 1)
  assert.equal(localWorkbench.searchShips('missing', [ship]).length, 0)
  assert.equal(
    localWorkbench.searchShips('9695157', [{ ...ship, imo: '9695157' }]).length,
    1,
  )
  assert.equal(shipType('集装箱船'), '集装箱船')
  assert.equal(shipType('container_ship'), '集装箱船')
  assert.equal(eventKind('unknown_value').label, '其他事件')
  const first = {
    id: 700,
    ship_id: 7,
    latitude: 0,
    longitude: 0,
    speed: 8,
    course: 90,
    heading: null,
    recorded_at: '2026-08-30T00:00:00Z',
  }
  const last = {
    ...first,
    id: 701,
    longitude: 1,
    speed: 12,
    recorded_at: '2026-08-30T00:10:00Z',
  }
  api.fetchSimulationMeta = async () => ({
    start_at: first.recorded_at,
    end_at: last.recorded_at,
    frame_count: 2,
  })
  api.fetchMapShips = async () => [ship]
  api.fetchPlaybackPositions = async () => [last, first]
  const playback = usePlayback()
  await playback.load()
  assert.equal(
    playback.currentShips.value[0].id,
    7,
    'Position id must not replace ship identity',
  )
  assert.equal(
    playback.currentShips.value[0].speed,
    8,
    'Initial snapshot must not leak latest ship position',
  )
  assert.equal(
    playback.tracks.value[7][0].id,
    700,
    'Tracks sort chronologically',
  )
  playback.seek('2026-08-30T00:05:00Z')
  assert.equal(
    playback.currentShips.value[0].speed,
    12,
    'Seek selects first frame at or after event time',
  )
  playback.seek('2026-08-29T00:00:00Z')
  assert.equal(playback.index.value, 0)
  playback.seek('2026-08-31T00:00:00Z')
  assert.equal(playback.index.value, 1)
  api.fetchPlaybackPositions = async () => {
    throw new Error('模拟接口失败')
  }
  await playback.load()
  assert.equal(playback.loading.value, false)
  assert.equal(playback.error.value, '模拟接口失败')
  assert.equal(
    playback.currentShips.value.length,
    0,
    'Failure clears stale snapshots',
  )
  api.fetchPlaybackPositions = async () => [first, last]
  await playback.load()
  assert.equal(playback.error.value, '')
  assert.equal(playback.currentShips.value.length, 1, 'Retry recovers')
  api.fetchSimulationMeta = async () => ({
    start_at: null,
    end_at: null,
    frame_count: 0,
  })
  await playback.load()
  assert.match(playback.error.value, /暂无可回放/)
  assert.equal(playback.currentShips.value.length, 0)
  console.log(
    'PASS: spatial distance, temporal filtering, search, identity, replay ordering/seeking, empty/error/retry states',
  )
}
main().catch((error) => {
  console.error(error)
  process.exitCode = 1
})
