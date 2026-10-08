// 区域活动面板（issue #41 阶段二-A）语义检查：静态断言组件契约 + 运行纯函数行为检查。
// 无测试框架：node:assert/strict；先用 tsc 把 src/domain/areaActivity.ts 编译到 CJS 再 require。
// 运行：cd frontend && node checks/area-activity.cjs（退出码 0 才算通过）
const assert = require('node:assert/strict')
const { execFileSync } = require('node:child_process')
const { mkdirSync, readFileSync, writeFileSync } = require('node:fs')
const path = require('node:path')

const root = path.resolve(__dirname, '..')
const out = path.join(root, 'node_modules/.tmp/area-activity-checks')
mkdirSync(out, { recursive: true })
execFileSync(
  process.execPath,
  [
    path.join(root, 'node_modules/typescript/bin/tsc'),
    'src/domain/areaActivity.ts',
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
    '--strict',
    '--rootDir',
    'src',
    '--outDir',
    out,
  ],
  { cwd: root, stdio: 'inherit' },
)
writeFileSync(path.join(out, 'package.json'), '{"type":"commonjs"}')

// 可选：隔离类型检查（--types）。只检查本组件 + domain + api.ts，
// 不依赖 App.vue 是否已接入，避免别的在途文件把本组件的类型错误淹没。
if (process.argv.includes('--types')) {
  const tsconfigPath = path.join(out, 'tsconfig.area.json')
  writeFileSync(tsconfigPath, JSON.stringify({
    extends: '../../../tsconfig.app.json',
    // types 留空：临时目录里解析不到 vite/client，且本组件不使用 import.meta.env。
    compilerOptions: { types: [], tsBuildInfoFile: './area.tsbuildinfo' },
    include: [
      '../../../src/components/AreaActivityPanel.vue',
      '../../../src/domain/areaActivity.ts',
      '../../../src/api.ts',
    ],
  }, null, 2))
  console.log('运行隔离 vue-tsc（AreaActivityPanel.vue + areaActivity.ts + api.ts）…')
  execFileSync(
    process.execPath,
    [path.join(root, 'node_modules/vue-tsc/bin/vue-tsc.js'), '--project', tsconfigPath, '--noEmit'],
    { cwd: root, stdio: 'inherit' },
  )
  console.log('隔离类型检查通过：0 errors')
}

const domain = require(path.join(out, 'domain/areaActivity.js'))
const componentPath = path.join(root, 'src/components/AreaActivityPanel.vue')
const domainPath = path.join(root, 'src/domain/areaActivity.ts')
const source = readFileSync(componentPath, 'utf8')
const domainSource = readFileSync(domainPath, 'utf8')

const results = []
function check(label, fn) {
  try {
    fn()
    results.push({ label, ok: true })
  } catch (error) {
    results.push({ label, ok: false, message: error instanceof Error ? error.message : String(error) })
  }
}

// —— 静态语义：组件契约 ——
check('三模式齐全（时刻在场/时段活动/两时段比较）', () => {
  for (const label of ['时刻在场', '时段活动', '两时段比较']) assert.ok(source.includes(label), `组件缺少模式标签 ${label}`)
  for (const mode of ['snapshot', 'activity', 'compare']) assert.ok(source.includes(`'${mode}'`), `组件缺少模式 ${mode}`)
  assert.deepEqual(domain.AREA_PANEL_MODES.map(item => item.value), ['snapshot', 'activity', 'compare'])
})

check('emit 名称齐全且参数形状正确', () => {
  const block = source.slice(source.indexOf('defineEmits<{'), source.indexOf('}>()', source.indexOf('defineEmits<{')))
  for (const name of ['close', "'update:bounds'", "'results-updated'", "'locate-ship'", "'focus-visit'", "'use-area-in-dialog'"])
    assert.ok(block.includes(name), `defineEmits 缺少 ${name}`)
  assert.match(block, /'locate-ship':\s*\[payload: \{ shipId: number; startAt: string; endAt: string \}\]/)
  assert.match(block, /'focus-visit':\s*\[payload: \{ shipId: number; startAt: string; endAt: string; visitKey: string \}\]/)
  assert.match(block, /'use-area-in-dialog':\s*\[payload: AreaDialogPayload\]/)
})

check('results-updated 只在成功写入新结果时 emit（失败/取消不发）', () => {
  const emitted = source.match(/emit\('results-updated'\)/g) ?? []
  assert.equal(emitted.length, 1, 'results-updated 应只在一处 emit')
  const emitIndex = source.indexOf("emit('results-updated')")
  const writeIndex = source.indexOf('resultContexts.value[queryMode] = {')
  const catchIndex = source.indexOf('} catch (cause) {')
  assert.ok(writeIndex > 0 && catchIndex > writeIndex, '未找到结果写入/异常分支')
  assert.ok(emitIndex > writeIndex, 'emit 必须在结果写入之后')
  assert.ok(emitIndex < catchIndex, 'emit 必须在 try 的成功路径内，不能在 catch 里')
  const catchBlock = source.slice(catchIndex, source.indexOf('function cancelQuery'))
  assert.ok(!catchBlock.includes("emit('results-updated')"), '失败/取消路径不得 emit')
})

check('请求版本守卫 + AbortController', () => {
  assert.match(source, /requestSeq/, '缺少请求版本号')
  assert.match(source, /seq !== requestSeq/, '缺少旧响应丢弃判断')
  assert.match(source, /new AbortController\(\)/, '缺少 AbortController')
  assert.match(source, /controller\.abort\(\)/, '缺少取消在途请求')
  assert.match(source, /function isAbortError/, '缺少取消异常识别')
  assert.match(source, /watch\(\(\) => props\.bounds,/, '区域变更未作废在途请求')
  assert.match(source, /区域已变更，待查询/, '缺少区域变更后的旧结果标注')
})

check('船型筛选来自接口、默认全选、不在前端硬编码', () => {
  assert.match(source, /fetchAreaShipTypes\(\)/, '未调用船型接口')
  assert.match(source, /toAreaShipTypesResult\(/, '未归一化船型响应')
  assert.match(source, /selectedShipTypes\.value = \[\.\.\.values\]/, '默认全选逻辑缺失')
  for (const literal of ['__missing__', '__unknown__', '油轮', '货船', '集装箱', '拖轮'])
    assert.ok(!source.includes(literal), `组件硬编码了船型值 ${literal}`)
  for (const literal of ['油轮', '货船', '集装箱'])
    assert.ok(!domainSource.includes(literal), `domain 硬编码了船型值 ${literal}`)
})

check('清空船型时不提交（后端空船型=全部）', () => {
  assert.match(source, /shipTypeFilterReady/, '缺少船型就绪判断')
  assert.match(source, /已清空船型/, '缺少清空船型的提示')
})

check('no_data 与有效零结果分开渲染', () => {
  assert.match(source, /isNoData\(/, '缺少 no_data 分支')
  assert.match(source, /emptyResultText\(/, '缺少有效零结果分支')
  assert.match(source, /statusDescription\('no_data'\)/, 'no_data 未使用专门的说明文案')
  assert.match(domainSource, /不能解释为「零船」/, 'domain 未说明 no_data 不代表零船')
})

check('change_rate 为 null 时显示说明而不是 0', () => {
  assert.match(source, /hasChangeRate\(metric\.change_rate\)/, '缺少 change_rate 空值判断')
  assert.match(source, /changeRateText\(metric\.change_rate\)/, '缺少变化率文案函数')
  assert.ok(!/change_rate\s*\?\?\s*0/.test(source), '组件用 0 代替了 null change_rate')
})

check('截断提示读后端 limits 标志', () => {
  assert.match(source, /snapshotTruncationNote\(/, '缺少列表截断提示')
  assert.match(source, /activityTruncationNote\(/, '缺少明细截断提示')
  assert.match(domainSource, /list_truncated/, 'domain 未读 list_truncated')
  assert.match(domainSource, /detail_truncated/, 'domain 未读 detail_truncated')
  assert.match(source, /visit_limit/, '组件未暴露/提示 visit_limit')
})

check('结果区展示区域名称/版本/默认标记、算法版本、coverage、limitations 全文', () => {
  assert.match(source, /resultMeta\.area\.name/, '缺少结果区域名称')
  assert.match(source, /resultMeta\.area\.version/, '缺少区域版本')
  assert.match(source, /resultMeta\.area\.is_default/, '缺少默认区域标记')
  assert.match(source, /resultMeta\.algorithm\.version/, '缺少算法版本')
  assert.match(source, /coverageSummaryText/, '缺少 coverage 覆盖信息')
  assert.match(source, /v-for="\(item, index\) in resultMeta\.limitations"/, 'limitations 未逐条全文渲染')
})

check('compare 展示可比性 warnings，且不渲染访问明细', () => {
  assert.match(source, /compareView\.comparability\.warnings/, '缺少可比性提示')
  assert.match(source, /A 期每日统计/, '缺少 A 期每日分组')
  assert.match(source, /B 期每日统计/, '缺少 B 期每日分组')
  assert.match(source, /mode === 'activity' && hasActivity && !isNoData\(activityView\.status\)/, '访问明细应只在时段活动模式渲染')
})

check('证据联动：地图定位/显示区间 + segment 起止与报位 id', () => {
  assert.match(source, /emit\('locate-ship', visitLocateArgs\(visit\)\)/, '缺少 locate-ship 联动')
  assert.match(source, /emit\('focus-visit', visitFocusArgs\(visit\)\)/, '缺少 focus-visit 联动')
  assert.match(domainSource, /first_inside_at/, 'locate 参数未使用 first_inside_at')
  assert.match(domainSource, /last_inside_at/, 'locate 参数未使用 last_inside_at')
  assert.match(source, /segment\.start_fix_id/, 'segment 未显示起始报位 id')
  assert.match(source, /segment\.end_fix_id/, 'segment 未显示结束报位 id')
  assert.match(source, /formatUtc\(segment\.start_at\)/, 'segment 未显示起始时刻')
})

check('不自己拼 URL、不新增依赖、只调用 api.ts 函数', () => {
  assert.ok(!source.includes('fetch('), '组件不应直接使用 fetch')
  assert.ok(!source.includes('/api/area-activity'), '组件不应拼接区域接口 URL')
  for (const fn of ['fetchAreaSnapshot(', 'fetchAreaActivity(', 'fetchAreaCompare(', 'fetchAreaShipTypes('])
    assert.ok(source.includes(fn), `缺少 api.ts 调用 ${fn}`)
})

check('无障碍与窄屏：label/aria-live/表格 caption+scope/横向滚动', () => {
  assert.match(source, /aria-live="polite"/, '缺少 aria-live 状态区')
  assert.match(source, /role="alert"/, '缺少错误 alert')
  assert.match(source, /aria-busy/, '缺少 aria-busy')
  assert.match(source, /:aria-expanded=/, '展开按钮缺少 aria-expanded')
  assert.match(source, /:aria-controls=/, '展开按钮缺少 aria-controls')
  assert.match(source, /<caption>/, '表格缺少 caption')
  assert.match(source, /scope="col"/, '表头缺少 scope=col')
  assert.match(source, /scope="row"/, '行首缺少 scope=row')
  assert.match(source, /:for="`aa-ship-type-\$\{index\}`"/, '船型复选缺少 label/for 关联')
  assert.match(source, /overflow-x: auto/, '缺少窄屏横向滚动')
  assert.match(source, /@media \(max-width: 640px\)/, '缺少窄屏媒体查询')
})

check('ECharts 按需引入并尊重 prefers-reduced-motion、窄屏减少刻度', () => {
  assert.match(source, /from 'echarts\/core'/, '未按需引入 echarts/core')
  assert.match(source, /from 'echarts\/charts'/, '未按需引入 echarts/charts')
  assert.match(source, /prefers-reduced-motion/, '未尊重减少动态偏好')
  assert.match(source, /animation: motionAllowed\.value/, '图表动画未受偏好控制')
  assert.match(source, /const interval = narrow\.value/, '窄屏未减少横轴刻度')
})

// —— 纯函数行为 ——
check('UTC 时间输入/输出互转（不随本机时区漂移）', () => {
  assert.equal(domain.utcInputToIso('2026-02-25T00:00'), '2026-02-25T00:00:00Z')
  assert.equal(domain.utcInputToIso('2026-02-25T08:30:15'), '2026-02-25T08:30:15Z')
  assert.equal(domain.utcInputToIso('2026-02-30T00:00'), null, '非法日期必须被拒绝')
  assert.equal(domain.utcInputToIso('2026/02/25 00:00'), null)
  assert.equal(domain.utcInputToIso(''), null)
  assert.equal(domain.utcInputValue('2026-02-25T08:30:00Z'), '2026-02-25T08:30')
  assert.equal(domain.utcInputValue('2026-02-25T08:30:00+08:00'), '2026-02-25T00:30')
  assert.equal(domain.utcInputValue(null), '')
})

check('默认时段为 UTC 自然日半开区间，跨月边界正确', () => {
  const window = domain.defaultActivityWindow(new Date('2026-02-25T13:45:00Z'))
  assert.deepEqual(window, { start: '2026-02-25T00:00', end: '2026-02-26T00:00' })
  const compare = domain.defaultCompareWindows(new Date('2026-03-01T00:10:00Z'))
  assert.deepEqual(compare, {
    startA: '2026-02-28T00:00',
    endA: '2026-03-01T00:00',
    startB: '2026-03-01T00:00',
    endB: '2026-03-02T00:00',
  })
  assert.equal(domain.shiftUtcDay('2026-02-28', 1), '2026-03-01')
  assert.equal(domain.utcDayStartIso('2026-02-28'), '2026-02-28T00:00:00Z')
  assert.equal(domain.utcDayEndIso('2026-02-28'), '2026-03-01T00:00:00Z')
})

check('半开区间表单校验：只拦必填与顺序', () => {
  assert.equal(domain.windowOrderError('2026-02-25T00:00:00Z', '2026-02-26T00:00:00Z'), null)
  assert.ok(domain.windowOrderError('2026-02-26T00:00:00Z', '2026-02-25T00:00:00Z'))
  assert.ok(domain.windowOrderError('2026-02-25T00:00:00Z', '2026-02-25T00:00:00Z'))
  assert.ok(domain.windowOrderError(null, '2026-02-25T00:00:00Z'))
})

check('区域归一化：兼容后端嵌套 bounds（含 version=null / custom）', () => {
  const result = domain.toAreaSnapshotResult({
    status: 'partial',
    area: {
      area_id: 'custom',
      name: '自定义分析矩形',
      version: null,
      is_default: false,
      basis: '调用方显式提供的矩形（未做权威性核验）',
      bounds: { south: 25.8, west: 55.8, north: 27.1, east: 57.1 },
      span_deg: { lat: 1.3, lon: 1.3 },
      containment: 'west <= longitude < east 且 south <= latitude < north（半开矩形）',
    },
    query: { mode: 'snapshot' },
    algorithm: { name: 'area_activity', version: '1.0.1', params: {} },
    coverage: {
      source: 'nnu_ais',
      batch_ids: [1, 2],
      batch_days: ['2026-02-25', '2026-02-26'],
      scope_start: '2026-02-24T16:00:00Z',
      scope_end: '2026-03-03T15:59:59Z',
      scoped_fix_count: 1000,
      region_fix_count: 120,
      window_region_fix_count: 40,
      first_fix_at: null,
      last_fix_at: null,
      note: '说明',
    },
    summary: { in_area_count: 7, out_of_area_fresh_count: 3, stale_fix_count: 5, evaluated_ship_count: 4462, freshness_seconds: 3600 },
    ships: [{ ship_id: 1, name: 'A', mmsi: '1', ship_type: null, latitude: 26.4, longitude: 56.6, speed: 12.3, recorded_at: '2026-02-25T08:00:00Z', age_seconds: 120, fresh: true, inside: true }],
    limits: { max_snapshot_ships: 5000, evaluated_ship_count: 4462, returned_ship_count: 1, list_truncated: false },
    limitations: ['限制一'],
  })
  assert.equal(result.status, 'partial')
  assert.equal(result.area.area_id, 'custom')
  assert.equal(result.area.version, null)
  assert.equal(result.area.is_default, false)
  assert.deepEqual(result.area.bounds, { west: 55.8, south: 25.8, east: 57.1, north: 27.1 })
  assert.equal(result.area.span_deg.lat, 1.3)
  assert.equal(result.algorithm.version, '1.0.1')
  assert.equal(result.coverage.batch_ids.length, 2)
  assert.equal(result.summary.in_area_count, 7)
  assert.equal(result.summary.evaluated_ship_count, 4462)
  assert.equal(result.ships.length, 1)
  assert.deepEqual(result.limitations, ['限制一'])
})

check('区域归一化：兼容扁平 west/south/east/north，缺失字段记 null 不回填 0', () => {
  const bounds = domain.readBounds({ west: 1, south: 2, east: 3, north: 4 })
  assert.deepEqual(bounds, { west: 1, south: 2, east: 3, north: 4 })
  assert.equal(domain.readBounds({ west: 1, south: 2 }), null)
  const result = domain.toAreaActivityResult({ status: 'ok', area: { west: 1, south: 2, east: 3, north: 4 } })
  assert.deepEqual(result.area.bounds, { west: 1, south: 2, east: 3, north: 4 })
  assert.equal(result.summary.ships_observed, null)
  assert.equal(domain.formatCount(result.summary.ships_observed), '—')
  assert.equal(domain.readAreaInfo(null).version, null)
})

check('no_data 与有效零结果的语义分开', () => {
  assert.equal(domain.isNoData('no_data'), true)
  assert.equal(domain.isNoData('ok'), false)
  assert.equal(domain.isEmptyResult('no_data', 0), false, 'no_data 不能被当成零结果')
  assert.equal(domain.isEmptyResult('ok', 0), true)
  assert.equal(domain.isEmptyResult('partial', 0), true)
  assert.ok(domain.statusDescription('no_data').includes('不能解释为「零船」'))
  assert.ok(domain.emptyResultText('snapshot').includes('有效零结果'))
  assert.ok(domain.emptyResultText('activity').includes('有效零结果'))
  assert.notEqual(domain.emptyResultText('snapshot'), domain.emptyResultText('activity'))
  assert.equal(domain.statusLabel('partial'), '部分结果')
  assert.equal(domain.statusTone('no_data'), 'empty')
})

check('change_rate 空值显示说明，数值带符号百分比', () => {
  assert.equal(domain.hasChangeRate(null), false)
  assert.equal(domain.hasChangeRate(undefined), false)
  assert.equal(domain.hasChangeRate(Number.NaN), false)
  assert.equal(domain.changeRateText(null), '基期为 0，无法计算变化率')
  assert.ok(!domain.changeRateText(null).includes('0%'))
  assert.equal(domain.changeRateText(0.1234), '+12.3%')
  assert.equal(domain.changeRateText(-0.5), '-50.0%')
  assert.equal(domain.formatSigned(-3.2), '-3.2')
  assert.equal(domain.formatSigned(3.2), '+3.2')
})

check('截断提示由后端标志驱动，未截断时不提示', () => {
  assert.equal(domain.snapshotTruncationNote({ list_truncated: false }), null)
  assert.equal(domain.snapshotTruncationNote({}), null)
  const snapshotNote = domain.snapshotTruncationNote({
    list_truncated: true,
    returned_ship_count: 500,
    max_snapshot_ships: 500,
    evaluated_ship_count: 4462,
  })
  assert.ok(snapshotNote.includes('截断') && snapshotNote.includes('500') && snapshotNote.includes('4,462'), snapshotNote)
  assert.equal(domain.activityTruncationNote({ detail_truncated: false }), null)
  const activityNote = domain.activityTruncationNote({
    detail_truncated: true,
    returned_visit_count: 200,
    visit_limit: 500,
    max_visit_rows: 2000,
    candidate_ship_count: 3000,
  })
  assert.ok(activityNote.includes('截断') && activityNote.includes('visit_limit=500') && activityNote.includes('3,000'), activityNote)
})

check('船型多选：全部=null、部分=数组、列表为空=null', () => {
  assert.equal(domain.shipTypeQueryValues(['a', 'b'], ['a', 'b']), null, '全选应等价于不带筛选')
  assert.deepEqual(domain.shipTypeQueryValues(['a'], ['a', 'b']), ['a'])
  assert.equal(domain.shipTypeQueryValues([], []), null, '列表未加载时不加筛选')
  assert.equal(domain.shipTypeQueryValues([], ['a', 'b']), null, '空选择由后端解释为全部')
  assert.equal(domain.allShipTypesSelected(['a', 'b'], ['a', 'b']), true)
  assert.equal(domain.allShipTypesSelected(['a'], ['a', 'b']), false)
  assert.equal(domain.allShipTypesSelected([], []), true)
})

check('保留船型值来自后端 reserved，合并去重且不硬编码', () => {
  const options = domain.mergeShipTypeOptions(
    [{ value: '油轮', label: '油轮', count: 25, count_scope: 'all' }],
    [{ value: '__missing__', label: '缺失' }, { value: '__unknown__', label: '未知' }],
  )
  assert.deepEqual(options.map(option => option.value), ['油轮', '__missing__', '__unknown__'])
  assert.equal(options[0].count, 25)
  assert.equal(options[1].count, null)
  assert.equal(options[2].label, '未知')
  const deduped = domain.mergeShipTypeOptions([{ value: 'a', label: 'a', count: 1, count_scope: 'x' }], [{ value: 'a', label: '重复' }])
  assert.equal(deduped.length, 1)
  assert.equal(domain.shipTypeSelectionText(['a'], options).length > 0, true)
  assert.equal(domain.shipTypeSelectionText([], []), '全部船型（船型列表未加载）')
})

check('每日序列与 compare windows/metrics 归一化', () => {
  const series = domain.dailySeries([
    { date: '2026-02-25', ships_observed: 3, observed_entry_count: 4, observed_exit_count: 2, observed_ship_hours: 8.5 },
    { date: '2026-02-26', ships_observed: 5, observed_entry_count: 6, observed_exit_count: 7, observed_ship_hours: 9.25 },
  ])
  assert.deepEqual(series.dates, ['2026-02-25', '2026-02-26'])
  assert.deepEqual(series.shipsObserved, [3, 5])
  assert.deepEqual(series.exits, [2, 7])
  assert.deepEqual(domain.dailySeries(null).dates, [])

  const compare = domain.toAreaCompareResult({
    status: 'ok',
    area: { area_id: 'hormuz_core_v1', name: '核心区', version: '1.0.0', is_default: true, bounds: { west: 55.8, south: 25.8, east: 57.1, north: 27.1 } },
    algorithm: { name: 'area_activity', version: '1.0.1', params: {} },
    windows: { a: { start: '2026-02-25T00:00:00Z', end: '2026-02-26T00:00:00Z', days: 1, length_hours: 24 }, b: { start: '2026-02-26T00:00:00Z', end: '2026-02-27T00:00:00Z', days: 1, length_hours: 24 } },
    metrics: [
      { key: 'ships_observed', label: '出现去重船数', unit: '艘', a: 0, b: 6, delta: 6, change_rate: null },
      { key: 'ships_observed_per_day', label: '出现去重船数日均', unit: '艘/日', a: 4, b: 6, delta: 2, change_rate: 0.5 },
    ],
    comparability: { same_area: true, same_filters: true, same_algorithm: true, equal_length: true, window_days_a: 1, window_days_b: 1, window_length_days_a: 1, window_length_days_b: 1, per_day_denominator: '窗口实际长度', warnings: ['提示'] },
    a: { status: 'ok', summary: { ships_observed: 0 }, coverage: {}, daily: [] },
    b: { status: 'ok', summary: { ships_observed: 6 }, coverage: {}, daily: [] },
    limitations: [],
  })
  assert.equal(compare.windows.a.length_hours, 24)
  assert.equal(compare.metrics.length, 2)
  assert.equal(compare.metrics[0].change_rate, null)
  assert.equal(domain.changeRateText(compare.metrics[0].change_rate), '基期为 0，无法计算变化率')
  assert.equal(compare.metrics[1].unit, '艘/日')
  assert.deepEqual(compare.comparability.warnings, ['提示'])
  assert.equal(compare.a.summary.ships_observed, 0)
  assert.equal(compare.a.daily.length, 0)
})

check('访问 emit 参数：locate 用 first/last inside，focus 带 visitKey', () => {
  const visit = {
    visit_key: 's1234:f987654',
    ship_id: 1234,
    first_inside_at: '2026-02-25T01:00:00Z',
    last_inside_at: '2026-02-25T02:30:00Z',
  }
  assert.deepEqual(domain.visitLocateArgs(visit), { shipId: 1234, startAt: '2026-02-25T01:00:00Z', endAt: '2026-02-25T02:30:00Z' })
  assert.deepEqual(domain.visitFocusArgs(visit), {
    shipId: 1234,
    startAt: '2026-02-25T01:00:00Z',
    endAt: '2026-02-25T02:30:00Z',
    visitKey: 's1234:f987654',
  })
  assert.equal(domain.visitDetailId('s1234:f987654'), 'aa-visit-s1234-f987654')
  assert.equal(domain.visitStatusLabel('truncated_end').includes('未观测到离开'), true)
  assert.equal(domain.flagLabel('gap_interrupted') !== 'gap_interrupted', true)
  assert.equal(domain.flagLabel('未知标记'), '未知标记')
  assert.equal(domain.priorStateLabel('unknown').includes('前置状态未知'), true)
  assert.equal(domain.eventFlagLabels({ near_boundary: true, wide_bracket: false, in_window: true }).length, 1)
  assert.equal(domain.eventFlagLabels(null).length, 0)
})

check('格式化：时长/数量/坐标/龄期/单位', () => {
  assert.equal(domain.formatSeconds(5400), '01:30:00')
  assert.equal(domain.formatSeconds(90000), '1 天 01:00:00')
  assert.equal(domain.formatSeconds(null), '—')
  assert.equal(domain.formatCount(4462), '4,462')
  assert.equal(domain.formatCount(0), '0')
  assert.equal(domain.formatCount(null), '—')
  assert.equal(domain.formatHours(88.25), '88.3 h')
  assert.equal(domain.formatAge(45), '45 秒')
  assert.equal(domain.formatAge(7200), '2.0 小时')
  assert.equal(domain.formatSpeed(12.34), '12.3 kn')
  assert.equal(domain.formatSpeed(null), '—')
  assert.equal(domain.formatLatitude(25.8), '25.8000°N')
  assert.equal(domain.formatLongitude(-56.1), '56.1000°W')
  assert.equal(domain.formatPosition(26.4, 56.6), '26.4000°N 56.6000°E')
  assert.equal(domain.formatSpan({ lat: 1.3, lon: 1.3 }), '1.30° × 1.30°')
  assert.equal(domain.formatUtc('2026-02-25T08:30:00Z'), '2026-02-25 08:30:00')
  assert.equal(domain.formatUtc('bad'), '—')
  assert.equal(domain.dash(null), '—')
})

check('区域比较与边界文本', () => {
  const a = { west: 55.8, south: 25.8, east: 57.1, north: 27.1 }
  assert.equal(domain.boundsEqual(a, { ...a }), true)
  assert.equal(domain.boundsEqual(a, { ...a, north: 27.2 }), false)
  assert.equal(domain.boundsEqual(a, null), false)
  assert.equal(domain.boundsEqual(null, null), true)
  assert.ok(domain.boundsText(a).includes('25.8000°N') && domain.boundsText(a).includes('57.1000°E'))
  assert.equal(domain.boundsText(null), '—')
})

check('对话联动：读取 agentContext/pendingAction 与生成提示词', () => {
  const hint = domain.readAreaHint({ mode: 'activity', start: '2026-02-25T00:00:00Z', end: '2026-02-26T00:00:00Z', shipTypes: ['油轮', ''] })
  assert.equal(hint.mode, 'activity')
  assert.deepEqual(hint.shipTypes, ['油轮'])
  assert.equal(domain.readAreaHint(null), null)
  assert.equal(domain.readAreaHint('2026-02-25'), null)
  assert.equal(domain.readAreaHint({ mode: 'unknown-mode' }), null, '无可识别字段应返回 null')
  assert.equal(domain.readAreaHint({ mode: 'unknown-mode', at: '2026-02-25T00:00:00Z' }).mode, null, '未知模式不采纳但仍读取其它字段')
  assert.equal(domain.readAreaHint({ mode: 'snapshot', at: '2026-02-25T00:00:00Z' }).at, '2026-02-25T00:00:00Z')

  const text = domain.areaQueryText({
    mode: 'activity',
    bounds: { west: 55.8, south: 25.8, east: 57.1, north: 27.1 },
    areaLabel: '霍尔木兹海峡核心通行区',
    areaIsDefault: true,
    shipTypes: null,
    at: null,
    start: '2026-02-25T00:00:00Z',
    end: '2026-02-26T00:00:00Z',
    startA: null,
    endA: null,
    startB: null,
    endB: null,
  })
  assert.ok(text.includes('霍尔木兹海峡核心通行区'))
  assert.ok(text.includes('2026-02-25 00:00:00'))
  assert.ok(text.includes('全部'))
  assert.ok(text.includes('半开区间'))
  assert.ok(domain.utcRangeText('2026-02-25T00:00:00Z', '2026-02-26T00:00:00Z').includes('终点不含'))
})

// —— 输出 ——
for (const [index, item] of results.entries()) {
  const label = `${String(index + 1).padStart(2, '0')} - ${item.label}`
  if (item.ok) console.log(`ok   ${label}`)
  else console.log(`FAIL ${label}\n       ${item.message}`)
}
const failed = results.filter(item => !item.ok)
console.log(`\n${results.length - failed.length}/${results.length} checks passed`)
if (failed.length) {
  console.log(`\n失败项：`)
  for (const item of failed) console.log(`- ${item.label}：${item.message}`)
  process.exitCode = 1
} else {
  console.log('area-activity 前端语义检查通过（退出码 0）')
}
