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
    'src/domain/countryLabels.ts',
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
const { hasEventLocation, eventOccurredBy, eventTimeText, safeNewsUrl } = require(path.join(out, 'domain/maritime.js'))

async function main() {
  const { countryLabelPosition } = require(path.join(out, 'domain/countryLabels.js'))
  const countryData = JSON.parse(require('node:fs').readFileSync(path.join(root, 'public/data/gulf-countries.geojson'), 'utf8'))
  assert.equal(countryData.features.length, 13)
  for (const feature of countryData.features) {
    const [lat, lng] = feature.properties.label
    assert.deepEqual(countryLabelPosition(feature, { south: lat - .01, north: lat + .01, west: lng - .01, east: lng + .01 }), [lat, lng])
    assert.equal(countryLabelPosition(feature, { south: -60, north: -50, west: -120, east: -110 }), null)
  }
  const palestine = countryData.features.find(f => f.properties.code === 'PSX')
  assert.equal(palestine.geometry.type, 'MultiPolygon')
  assert.equal(palestine.geometry.coordinates.length, 2, 'Keep both Gaza and the West Bank')
  for (const [lat, lng] of [[31.45, 34.4], [32.0, 35.3]]) {
    assert.ok(countryLabelPosition(palestine, { south: lat - .001, north: lat + .001, west: lng - .001, east: lng + .001 }), 'Both Palestinian areas must have geometry')
    assert.equal(countryLabelPosition(countryData.features.find(f => f.properties.code === 'ISR'), { south: lat - .001, north: lat + .001, west: lng - .001, east: lng + .001 }), null, 'Palestinian interior points must not receive Israel fill')
  }
  const donut = { properties: { label: [5, 5] }, geometry: { type: 'Polygon', coordinates: [
    [[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]],
    [[4, 4], [6, 4], [6, 6], [4, 6], [4, 4]],
  ] } }
  const interior = countryLabelPosition(donut, { south: 0, north: 10, west: 0, east: 10 })
  assert.ok(interior && !(interior[0] > 4 && interior[0] < 6 && interior[1] > 4 && interior[1] < 6), 'Country labels must not land in polygon holes')
  const unknownEvent = api.toEventView({ title_zh: '测试', summary_zh: '摘要', event_lat: null, event_lng: null, event_datetime: null, event_time_text: null })
  assert.equal(unknownEvent.latitude, null)
  assert.equal(unknownEvent.occurred_at, null)
  assert.equal(hasEventLocation(unknownEvent), false)
  assert.equal(hasEventLocation({ latitude: 0, longitude: 0 }), true)
  assert.equal(hasEventLocation({ latitude: NaN, longitude: 50 }), false)
  assert.equal(hasEventLocation({ latitude: 26, longitude: null }), false)
  assert.equal(eventTimeText(unknownEvent), '时间未明确')
  assert.equal(eventTimeText({ event_time_text: '3月初' }), '3月初')
  const datedEvent = { occurred_at: '2026-03-01T06:27:00Z' }
  assert.equal(eventOccurredBy(datedEvent, '2026-03-01T06:26:59Z'), false, 'Future event stays hidden')
  assert.equal(eventOccurredBy(datedEvent, '2026-03-01T06:27:00Z'), true, 'Event appears at its timestamp')
  assert.equal(eventOccurredBy(datedEvent, '2026-03-02T00:00:00Z'), true, 'Past event remains visible')
  assert.equal(eventOccurredBy({ occurred_at: null }, '2026-03-02T00:00:00Z'), false, 'Unknown occurrence is not invented from report date')
  assert.equal(eventOccurredBy(datedEvent, null), false, 'No playback time means no revealed event')
  assert.equal(eventOccurredBy({ occurred_at: 'invalid' }, '2026-03-02T00:00:00Z'), false)
  assert.equal(eventKind('military').label, '军事行动与安全事件')
  assert.equal(eventKind('passage').label, '海峡通行与航运动态')
  assert.equal(eventKind('freight').label, '运费与航运保险')
  assert.equal(safeNewsUrl('javascript:alert(1)'), undefined)
  assert.equal(safeNewsUrl('https://example.com/news'), 'https://example.com/news')
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
  assert.equal(eventKind('unknown_value').label, '其他')
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
    frame_interval_seconds: 300,
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
    8,
    'An intermediate display tick holds the last report without future leakage',
  )
  playback.seek('2026-08-29T00:00:00Z')
  assert.equal(playback.index.value, 0)
  playback.seek('2026-08-31T00:00:00Z')
  assert.equal(playback.index.value, 2)
  assert.equal(playback.currentShips.value[0].speed, 12)
  const multiEnd = '2026-09-01T00:01:00Z'
  api.fetchSimulationMeta = async () => ({ start_at: first.recorded_at, end_at: multiEnd, frame_count: 578, frame_interval_seconds: 300 })
  const windows = []
  api.fetchPlaybackPositions = async (start, end) => {
    windows.push([Date.parse(start), Date.parse(end)])
    return [first, last]
  }
  await playback.load()
  assert.equal(windows.length, 3)
  assert.ok(windows.every(([start, end]) => end - start <= 86400000))
  assert.equal(windows[0][1], windows[1][0])
  assert.equal(playback.tracks.value[7].length, 2, 'Inclusive window duplicates are removed')
  assert.equal(playback.times.value.at(-1), new Date(multiEnd).toISOString())
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
