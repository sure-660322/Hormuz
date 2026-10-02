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
    'src/domain/casePlayback.ts',
    'src/domain/trackArrows.ts',
    'src/domain/overview.ts',
    'src/domain/tankerPassages.ts',
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
const { nextTick } = require('vue')
const { hasEventLocation, eventOccurredBy, eventTimeText, safeNewsUrl } = require(path.join(out, 'domain/maritime.js'))

async function main() {
  const { shipComposition, shipGroup, keyEvents, eventSeekTime } = require(path.join(out, 'domain/overview.js'))
  const { tankerPassagesUtc } = require(path.join(out, 'domain/tankerPassages.js'))
  assert.deepEqual(tankerPassagesUtc.map(d => [d.inbound, d.outbound]), [[13,3],[24,29],[46,22],[32,33],[17,26],[0,7],[0,1],[0,0]], 'Audited UTC direction counts')
  assert.ok(tankerPassagesUtc.every(d => d.passages === d.inbound + d.outbound))
  assert.equal(shipGroup('集装箱'), 'cargo')
  assert.equal(shipGroup('油轮'), 'tanker')
  assert.equal(shipGroup('拖引'), 'other')
  assert.equal(shipGroup('unrecognized'), 'unknown')
  assert.equal(shipGroup(null), 'unknown')
  const composition = shipComposition(['油轮','货船','集装箱','拖轮',null,'未知'].map(ship_type => ({ship_type})))
  assert.deepEqual(composition.map(g => g.count), [1,2,1,2])
  assert.equal(composition.reduce((n,g) => n + g.count,0), 6)
  assert.ok(shipComposition([]).every(g => g.percent === 0))
  const story = (id, day, count) => ({event_id: id, occurred_at: day, coverage_count: count})
  const stories = Array.from({length:8}, (_,i) => story(String(i),'2026-02-28T00:00:00Z',i))
  const selected = keyEvents([...stories,story('undated',null,100),story('bad','2026-02-30T00:00:00Z',100),story('out','2026-04-01T00:00:00Z',100)],'2026-02-24T16:00:00Z','2026-03-03T15:59:59Z')
  assert.equal(selected.length,6)
  assert.deepEqual(selected.map(e => e.event_id),['2','3','4','5','6','7'])
  assert.equal(eventSeekTime(stories[0],'2026-02-24T16:00:00Z','Asia/Shanghai'),'2026-02-27T16:00:00.000Z')
  assert.equal(eventSeekTime(stories[0],'2026-02-24T16:00:00Z','UTC'),'2026-02-28T00:00:00.000Z')
  assert.equal(eventSeekTime(story('first','2026-02-24T00:00:00Z',1),'2026-02-24T16:00:00Z','UTC'),'2026-02-24T16:00:00.000Z')

  const { sparseTrackArrows } = require(path.join(out, 'domain/trackArrows.js'))
  const east = Array.from({ length: 100 }, (_, i) => ({ x: i * 10, y: 50, speed: 10 }))
  const arrows = sparseTrackArrows([east], 1000, 200)
  assert.ok(arrows.length > 0 && arrows.length < 15, 'Directions must be sparse')
  assert.ok(arrows.every(a => a.angle === 90), 'Arrow follows chronological direction')
  assert.equal(sparseTrackArrows([[east[0]], [east[99]]], 1000, 200).length, 0, 'No arrow across observation gaps')
  assert.equal(sparseTrackArrows([[{ x: 20, y: 20, speed: 0 }, { x: 20.1, y: 20.1, speed: 0 }]], 1000, 200).length, 0, 'No direction for stationary jitter')
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
  displayZone.value = 'UTC'
  assert.equal(eventOccurredBy(datedEvent, '2026-02-28T23:59:59Z'), false, 'Future calendar day stays hidden')
  assert.equal(eventOccurredBy(datedEvent, '2026-03-01T00:00:00Z'), true, 'Day-level event appears at day start')
  assert.equal(eventOccurredBy(datedEvent, '2026-03-02T00:00:00Z'), true, 'Past event remains visible')
  displayZone.value = 'Asia/Shanghai'
  assert.equal(eventOccurredBy(datedEvent, '2026-02-28T15:59:59Z'), false, 'UTC+8 day has not begun')
  assert.equal(eventOccurredBy(datedEvent, '2026-02-28T16:00:00Z'), true, 'UTC+8 midnight reveals the source day')
  displayZone.value = 'UTC'
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
  api.fetchSimulationMeta = async () => ({
    start_at: first.recorded_at, end_at: last.recorded_at,
    frame_count: 3, frame_interval_seconds: 300,
    is_simulated: false, has_events: false, has_derived: false,
  })
  api.fetchShipSnapshot = async () => [{ ...ship, speed: 8, recorded_at: first.recorded_at }]
  let resolveWindow
  api.fetchShipSnapshotWindow = async () => new Promise((resolve) => { resolveWindow = resolve })
  const realPlayback = usePlayback()
  await realPlayback.load()
  assert.equal(realPlayback.isRealAis.value, true)
  assert.equal(realPlayback.frameReady.value, true)
  assert.equal(realPlayback.index.value, 0, 'Real AIS opens at the start of the playback range')
  assert.equal(realPlayback.time.value, new Date(first.recorded_at).toISOString())
  assert.equal(realPlayback.currentShips.value[0].speed, 8)
  realPlayback.index.value = 2
  await nextTick()
  assert.equal(realPlayback.frameReady.value, false)
  assert.equal(realPlayback.time.value, new Date(first.recorded_at).toISOString(), 'Keep displayed time while the target frame loads')
  assert.equal(realPlayback.currentShips.value[0].speed, 8, 'Keep the previous map snapshot during loading')
  await new Promise((resolve) => setTimeout(resolve, 150))
  resolveWindow({
    frames: [
      { at: first.recorded_at, ships: [{ ...ship, speed: 8, recorded_at: first.recorded_at }] },
      { at: '2026-08-30T00:05:00Z', ships: [{ ...ship, speed: 10, recorded_at: '2026-08-30T00:05:00Z' }] },
      { at: last.recorded_at, ships: [{ ...ship, speed: 12, recorded_at: last.recorded_at }] },
    ],
    max_age_seconds: 3600,
  })
  await new Promise((resolve) => setTimeout(resolve, 0))
  assert.equal(realPlayback.frameReady.value, true)
  assert.equal(realPlayback.time.value, new Date(last.recorded_at).toISOString())
  assert.equal(realPlayback.currentShips.value[0].speed, 12)
  realPlayback.index.value = 1
  await nextTick()
  assert.equal(realPlayback.frameReady.value, true, 'Adjacent cached frame is ready without a new request')
  assert.equal(realPlayback.currentShips.value[0].speed, 10)
  const { caseTrackChunks, mergeCaseTracks, clipCaseTracks } = require(path.join(out, 'domain/casePlayback.js'))
  const chunks = caseTrackChunks('2026-03-27T16:00:00Z','2026-03-29T15:59:59Z')
  assert.equal(chunks.length,2)
  assert.ok(chunks.every(([a,b]) => Date.parse(b)-Date.parse(a) <= 86400000))
  const point = (id, at) => ({id,recorded_at:at,latitude:26,longitude:56,speed:10})
  const window = (points) => ({ship_id:1,from:points[0].recorded_at,to:points.at(-1).recorded_at,bucket_seconds:120,gap_minutes:90,source_count:points.length,point_count:points.length,segments:[{segment_no:0,points}],gaps:[]})
  const a = point(1,'2026-03-28T15:55:00Z'), b = point(2,'2026-03-28T16:00:00Z'), c = point(3,'2026-03-28T20:00:00Z')
  const merged = mergeCaseTracks([window([a,b]),window([b,c])])
  assert.equal(merged.point_count,3,'Repeated chunk endpoint must be deduplicated')
  assert.equal(merged.segments.length,2,'Gap across chunk boundary must not be connected')
  assert.equal(merged.gaps.length,1)
  const clipped = clipCaseTracks(merged, a.recorded_at, b.recorded_at)
  assert.deepEqual(clipped.flatMap(s => s.points.map(p => p.id)), [1,2], 'No future point in playback highlight')
  assert.equal(clipCaseTracks(merged, a.recorded_at, c.recorded_at).length, 2, 'Clipping must preserve gaps')
  assert.equal(caseTrackChunks('2026-03-26T16:01:33Z','2026-03-31T15:59:51Z').length, 5, 'Full case uses five bounded requests')
  api.fetchShipSnapshot = async () => [{...ship,id:1},{...ship,id:2}]
  await realPlayback.load({start_at:'2026-03-30T00:00:00Z',end_at:'2026-03-30T00:10:00Z',ship_id:2})
  assert.deepEqual(realPlayback.currentShips.value.map(s => s.id),[2],'Case snapshot must contain only its vessel')
  assert.equal(realPlayback.times.value[0],'2026-03-30T00:00:00.000Z')
  console.log(
    'PASS: spatial distance, temporal filtering, search, identity, replay ordering/seeking, bounded real AIS snapshots, empty/error/retry states',
  )
}
main().catch((error) => {
  console.error(error)
  process.exitCode = 1
})
