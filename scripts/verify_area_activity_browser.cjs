/**
 * Issue #41 real browser acceptance. Run from repository root after starting isolated API/Vite services:
 * node scripts/verify_area_activity_browser.cjs --base http://127.0.0.1:5178 --out browser_current_final.json
 * Requires externally available playwright (NODE_PATH if needed) and Edge; no package installation.
 * Expected data: output/acceptance/independent_recompute.json. S9 calls the real configured model once.
 * --only S7,S8 allows targeted checks without model calls. Evidence is saved after every assertion.
 */
const { chromium } = require('playwright')
const path = require('path')
const fs = require('fs')

const args = process.argv.slice(2)
const getArg = (name, dflt) => {
  const i = args.indexOf(name)
  return i >= 0 && args[i + 1] ? args[i + 1] : dflt
}
const BASE = getArg('--base', 'http://127.0.0.1:5177')
const ONLY = getArg('--only', '').split(',').map((s) => s.trim()).filter(Boolean)
const HEADFUL = args.includes('--headful')
const OUT_DIR = path.resolve('output/acceptance')
fs.mkdirSync(OUT_DIR, { recursive: true })
const RESULT_PATH = path.join(OUT_DIR, getArg('--out', 'browser_acceptance.json'))

// 独立复算期望值（面板数字必须与它一致；缺失时相关核对记 BLOCKED，不伪造通过）
let REC = null
try { REC = JSON.parse(fs.readFileSync(path.join(OUT_DIR, 'independent_recompute.json'), 'utf-8')) } catch { REC = null }

function toNum(text) {
  if (text === null || text === undefined) return null
  const m = String(text).replace(/,/g, '').match(/-?\d+(\.\d+)?/)
  return m ? parseFloat(m[0]) : null
}

function assertFactNear(stepId, facts, label, expected, tol = 0) {
  if (expected === undefined || expected === null) {
    record(stepId, `数字核对：${label}`, 'BLOCKED', '独立复算无该期望值')
    return
  }
  const got = toNum(facts[label])
  if (got === null) { record(stepId, `数字核对：${label}`, 'FAIL', `面板无该字段（期望 ${expected}）`); return }
  const ok = Math.abs(got - expected) <= tol
  record(stepId, `数字核对：${label}`, ok ? 'PASS' : 'FAIL', `面板=${got} 独立复算=${expected} tol=${tol}`)
}

function checkCompareRows(rows) {
  const exp = REC?.compare?.default_prev1d_vs_1d?.metrics
  if (!exp) { record('S4', 'A/B 指标核对', 'BLOCKED', '独立复算无 A/B 期望值'); return }
  const keys = { ships_observed: '船数', observed_entry_count: '进入', observed_exit_count: '离开', observed_ship_hours: '船时' }
  for (const m of exp) {
    const row = rows.find((cells) => String(cells[0] || '').includes(keys[m.metric]))
    if (!row) { record('S4', `A/B 指标 ${m.metric}`, 'FAIL', '表格缺少该指标行'); continue }
    const tol = m.metric === 'observed_ship_hours' ? 0.1 : 0
    const got = { A: toNum(row[2]), B: toNum(row[3]), delta: toNum(row[4]), rate: toNum(row[5]) }
    const rateOk = m.change_rate === null
      ? got.rate === null || /null|不可比|—|-/.test(String(row[5]))
      : (got.rate !== null && (Math.abs(got.rate - m.change_rate) < 0.01 ||
                               Math.abs(got.rate - m.change_rate * 100) < 0.2))
    const ok = Math.abs(got.A - m.a) <= tol && Math.abs(got.B - m.b) <= tol &&
               Math.abs(got.delta - m.delta) <= tol && rateOk
    record('S4', `A/B 指标核对：${m.metric}`, ok ? 'PASS' : 'FAIL',
      `面板 A=${got.A} B=${got.B} delta=${got.delta} rate=${got.rate} | 独立复算 A=${m.a} B=${m.b} delta=${m.delta} rate=${m.change_rate}`)
  }
}

// ---------------------------------------------------------------- 选择器
// AreaActivityPanel.vue 已落地（aside.aa-panel）；入口按钮由 App.vue 提供，落地后核对。
const SEL = {
  openPanel: ['[data-testid="tool-area"]', 'button[aria-label="区域分析"]'],
  panel: ['aside.aa-panel', '.area-panel-placement .aa-panel'],
  closePanel: ['button[aria-label="关闭区域活动分析"]'],
  modeTabs: ['.aa-modes button.aa-mode'],
  areaLabel: ['p.aa-area-name'],
  areaChip: ['.aa-section-head .aa-chip'],
  statusBar: ['.area-status-bar'],
  statusCoord: ['.area-status-bar .area-coord'],
  statusTag: ['.area-status-bar .area-tag'],
  statusNote: ['.area-status-bar .area-note'],
  restoreDefault: ['.area-status-bar button.area-btn:has-text("恢复默认区域")', 'button:has-text("恢复默认区域")'],
  reselectRect: ['.area-status-bar button.area-btn:has-text("重新圈选")', 'button:has-text("重新圈选")'],
  cancelDraw: ['.area-status-bar button.area-btn:has-text("取消绘制")'],
  drawHint: ['.area-draw-hint'],
  suggestBar: ['.area-suggest-bar'],
  openSuggested: ['[data-testid="open-area-analysis"]'],
  toast: ['.alert-toast'],
  runQuery: ['form.aa-section button[type="submit"].aa-btn-primary', 'button.aa-btn-primary'],
  cancelQuery: ['form.aa-section button.aa-btn:has-text("取消")'],
  statusLine: ['p.aa-status'],
  noticeLine: ['p.aa-notice'],
  errorBox: ['p.aa-error'],
  staleLine: ['p.aa-stale'],
  noData: ['p.aa-empty'],
  facts: ['dl.aa-facts', 'dl.aa-facts.aa-grid'],
  dailyTable: ['.aa-daily-group table.aa-table'],
  visitsWrap: ['.aa-table-wrap[aria-label^="访问明细"]'],
  visitRow: ['.aa-table-wrap[aria-label^="访问明细"] tbody tr'],
  locateBtn: ['button.aa-btn-s:has-text("地图定位")'],
  focusVisitBtn: ['button.aa-btn-s:has-text("显示区间")'],
  shipTypeBoxes: ['ul.aa-checks input[type="checkbox"]'],
  shipTypeAll: ['button.aa-btn-s:has-text("全选")'],
  shipTypeClear: ['button.aa-btn-s:has-text("清空")'],
  writeDialog: ['button:has-text("写入对话")'],
  inputs: {
    snapshotAt: '#aa-snapshot-at',
    freshness: '#aa-freshness',
    activityStart: '#aa-activity-start',
    activityEnd: '#aa-activity-end',
    visitLimit: '#aa-visit-limit',
    startA: '#aa-compare-start-a',
    endA: '#aa-compare-end-a',
    startB: '#aa-compare-start-b',
    endB: '#aa-compare-end-b',
  },
  resultChip: ['.aa-result .aa-chip'],
  map: ['.leaflet-container'],
}

async function findFirst(page, candidates, { timeout = 4000, visible = true } = {}) {
  const state = visible ? 'visible' : 'attached'
  const combined = candidates.join(', ')
  try {
    const loc = page.locator(combined).first()
    await loc.waitFor({ state, timeout })
    return loc
  } catch { /* fall through to per-selector */ }
  for (const sel of candidates) {
    try {
      const loc = page.locator(sel).first()
      await loc.waitFor({ state, timeout: 800 })
      return loc
    } catch { /* try next */ }
  }
  return null
}

const results = []
function record(step, name, status, detail, extra) {
  const row = { step, name, status, detail, ...(extra || {}) }
  results.push(row)
  fs.writeFileSync(RESULT_PATH, JSON.stringify({ generated_at: new Date().toISOString(), base: BASE, status: "running", results }, null, 2))
  const tag = status === 'PASS' ? 'PASS' : status === 'BLOCKED' ? 'BLOCKED' : 'FAIL'
  console.log(`${tag} [${step}] ${name}${detail ? ' :: ' + detail : ''}`)
}
async function inputValueIfPresent(page, selector) {
  const input = page.locator(selector).first()
  return await input.count() ? input.inputValue() : ''
}
async function shot(page, step) {
  try { await page.screenshot({ path: path.join(OUT_DIR, `shot-${step}.png`) }) } catch { /* ignore */ }
}

function stepGuard(fn, step, name) {
  return async (ctx) => {
    if (ONLY.length && !ONLY.includes(step)) return
    try {
      await fn(ctx)
    } catch (err) {
      record(step, name, 'FAIL', err.message.split('\n')[0])
      await shot(ctx.page, step)
    }
  }
}

// ---------------------------------------------------------------- 步骤
const steps = []
const step = (id, name, fn) => steps.push({ id, name, run: stepGuard(fn, id, name) })

async function openAreaPanel(page) {
  let panel = await findFirst(page, SEL.panel, { timeout: 1500 })
  if (panel) return panel
  const opener = await findFirst(page, SEL.openPanel, { timeout: 8000 })
  if (!opener) throw new Error('找不到打开区域活动面板的入口（App.vue 未接入？SEL.openPanel 待补齐）')
  await opener.click()
  panel = await findFirst(page, SEL.panel, { timeout: 8000 })
  if (!panel) throw new Error('面板未出现（aside.aa-panel）')
  return panel
}

/** 读取所有 dl.aa-facts 的 dt->dd 文本（用于与 API/独立复算数字比对）。 */
async function readFacts(page) {
  return page.evaluate(() => {
    const out = {}
    document.querySelectorAll('dl.aa-facts > div').forEach((div) => {
      const dt = div.querySelector('dt')
      const dd = div.querySelector('dd')
      if (dt && dd) out[dt.textContent.trim()] = dd.textContent.replace(/\s+/g, ' ').trim()
    })
    return out
  })
}

async function readSummary(page) {
  const facts = await readFacts(page)
  const entries = Object.entries(facts)
  if (!entries.length) throw new Error('找不到结果摘要 dl.aa-facts')
  return entries.map(([k, v]) => `${k}=${v}`).join(' | ')
}

/** 填写 datetime-local 输入框（值形如 2026-02-28T12:00）。 */
async function setDatetime(page, selector, value) {
  const input = page.locator(selector).first()
  await input.waitFor({ state: 'visible', timeout: 5000 })
  await input.fill(value)
  await input.dispatchEvent('input')
  await input.dispatchEvent('change')
}

async function switchMode(page, label) {
  const tab = page.locator(`${SEL.modeTabs[0]}:has-text("${label}")`).first()
  await tab.waitFor({ state: 'visible', timeout: 5000 })
  await tab.click()
  await page.waitForTimeout(200)
}

async function runQuery(page, { timeoutMs = 60000 } = {}) {
  const run = await findFirst(page, SEL.runQuery)
  if (!run) throw new Error('找不到查询按钮（SEL.runQuery）')
  await run.click()
  const started = Date.now()
  while (Date.now() - started < timeoutMs) {
    const busy = await page.locator('.aa-scroll[aria-busy="true"]').count()
    if (!busy) break
    await page.waitForTimeout(200)
  }
  await page.waitForTimeout(400)
}

async function statusText(page) {
  const el = await findFirst(page, SEL.statusLine, { timeout: 2000 })
  return el ? ((await el.textContent()) || '').trim() : ''
}

/** 地图被 .aa-panel / .area-status-bar / .tool-rail 覆盖，且面板宽度在运行间会变化，
 *  因此在每次圈选前按实际几何算出「空白区」的最长对角，保证鼠标事件落在 .leaflet-container 上。 */
async function safeDragPoints(page, { horizontal = false } = {}) {
  const geo = await page.evaluate(() => {
    const r = (sel) => {
      const el = document.querySelector(sel)
      if (!el) return null
      const b = el.getBoundingClientRect()
      return { x: b.x, y: b.y, right: b.right, bottom: b.bottom, w: b.width, h: b.height }
    }
    const controls = ['.leaflet-control-attribution', '.leaflet-control-scale', '.leaflet-control-zoom',
                      '.map-top-tools', '.legend-toggle', '.map-hud', '.ais-snapshot-strip']
      .map(r).filter(Boolean)
    return { map: r('.leaflet-container'), panel: r('.aa-panel'), status: r('.area-status-bar'),
             rail: r('.tool-rail'), controls }
  })
  const m = geo.map
  if (!m) throw new Error('找不到地图容器 .leaflet-container')
  const blockers = [geo.panel, geo.status, geo.rail, ...geo.controls].filter(Boolean)
    .map((b) => ({ x: b.x - 6, y: b.y - 6, right: b.right + 6, bottom: b.bottom + 6 }))
  const free = []
  for (let fx = 0.02; fx <= 0.971; fx += 0.02) {
    for (let fy = 0.02; fy <= 0.901; fy += 0.02) {
      const px = m.x + fx * m.w, py = m.y + fy * m.h
      if (blockers.some((b) => px >= b.x && px <= b.right && py >= b.y && py <= b.bottom)) continue
      free.push({ fx, fy, px, py })
    }
  }
  if (free.length < 4) throw new Error('地图上没有可用于圈选的空白区域（被面板/控件遮挡）')

  // 按行分组并求「连续可拖拽段」（相邻采样点 fx 间距 ≤ 0.021），避免拖拽路径穿过面板/控件
  const STEP = 0.02
  const rows = new Map()
  for (const p of free) {
    const key = p.fy.toFixed(2)
    if (!rows.has(key)) rows.set(key, [])
    rows.get(key).push(p)
  }
  const rowList = [...rows.entries()].map(([key, pts]) => {
    pts.sort((a, b) => a.fx - b.fx)
    const runs = []
    let start = pts[0]
    let prev = pts[0]
    for (const p of pts.slice(1)) {
      if (p.fx - prev.fx > STEP * 1.05) { runs.push({ a: start, b: prev }); start = p }
      prev = p
    }
    runs.push({ a: start, b: prev })
    const longest = runs.reduce((best, r) => (r.b.fx - r.a.fx > best.b.fx - best.a.fx ? r : best), runs[0])
    return { fy: Number(key), longest }
  }).sort((a, b) => a.fy - b.fy)

  // 在所有行对上求「矩形空白块」；wide 模式取宽度最大，普通模式取面积最大
  let best = null
  for (let i = 0; i < rowList.length; i++) {
    let xLo = -Infinity, xHi = Infinity
    for (let j = i; j < rowList.length && rowList[j].fy - rowList[i].fy <= 0.62; j++) {
      const run = rowList[j].longest
      xLo = Math.max(xLo, run.a.fx)
      xHi = Math.min(xHi, run.b.fx)
      const width = xHi - xLo
      if (width < 0.06) break
      const height = rowList[j].fy - rowList[i].fy
      // MapView 把跨度 < 0.01° 的拖动当误触取消，因此宽高都必须有实际尺寸
      if (height < 0.08) continue
      const score = horizontal ? width : width * height
      if (!best || score > best.score) {
        best = { score, xLo, xHi, fyLo: rowList[i].fy, fyHi: rowList[j].fy, width, height }
      }
    }
  }
  if (!best) throw new Error('找不到连续可拖拽的空白矩形块')
  const px = (fx) => m.x + fx * m.w
  const py = (fy) => m.y + fy * m.h
  const insetX = Math.min(0.02, best.width * 0.06)
  const x1 = px(best.xLo + insetX), x2 = px(best.xHi - insetX)
  const y1 = py(best.fyLo), y2 = py(best.fyHi)
  return {
    x1, y1, x2, y2, mx: (x1 + x2) / 2, my: (y1 + y2) / 2,
    extent: { blockFx: Number(best.width.toFixed(2)), blockFy: Number(best.height.toFixed(2)) },
  }
}

async function performDraw(page, { zoomOutSteps = 0, horizontal = false } = {}) {
  const map = page.locator('.leaflet-container').first()
  if (await map.count() === 0) throw new Error('找不到地图容器')
  const reselect = await findFirst(page, SEL.reselectRect)
  if (!reselect) throw new Error('找不到「重新圈选」按钮')
  let pts = await safeDragPoints(page, { horizontal })
  if (zoomOutSteps > 0) {
    await page.mouse.move(pts.mx, pts.my)
    for (let i = 0; i < zoomOutSteps; i++) {
      await page.mouse.wheel(0, 400)
      await page.waitForTimeout(180)
    }
    await page.waitForTimeout(500)
    pts = await safeDragPoints(page, { horizontal })
  }
  await reselect.click()
  await page.waitForTimeout(400)
  const diagBefore = await page.evaluate(() => ({
    zoom: (() => {
      const src = document.querySelector('.leaflet-tile')?.getAttribute('src') || ''
      const m = src.match(/\/(\d+)\/(\d+)\/(\d+)(?:@2x)?\.(?:png|jpg|webp)/)
      return m ? Number(m[1]) : null
    })(),
    hint: document.querySelectorAll('.area-draw-hint').length,
    ready: document.querySelectorAll('.leaflet-container.area-draw-ready').length,
  }))
  await page.mouse.move(pts.x1, pts.y1)
  await page.mouse.down()
  await page.mouse.move((pts.x1 + pts.x2) / 2, (pts.y1 + pts.y2) / 2, { steps: 8 })
  await page.mouse.move(pts.x2, pts.y2, { steps: 8 })
  await page.mouse.up()
  await page.waitForTimeout(3500)
  const diagAfter = await page.evaluate(() => {
    const note = document.querySelector('.area-status-bar .area-note')
    return { note: (note?.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 120),
             hint: document.querySelectorAll('.area-draw-hint').length }
  })
  console.log(`      [draw] zoom=${diagBefore.zoom} hint=${diagBefore.hint} ready=${diagBefore.ready} `
    + `pts=(${Math.round(pts.x1)},${Math.round(pts.y1)})->(${Math.round(pts.x2)},${Math.round(pts.y2)}) `
    + `extent=${JSON.stringify(pts.extent)} note="${diagAfter.note}"`)
  return pts
}

function parseVisitTime(text) {
  const m = String(text).match(/(\d{4})-(\d{2})-(\d{2}) (\d{2}):(\d{2}):(\d{2})/)
  return m ? Date.parse(`${m[1]}-${m[2]}-${m[3]}T${m[4]}:${m[5]}:${m[6]}Z`) : null
}

step('S0', '应用可访问 + 面板可打开 + 控制台无 error', async ({ page }) => {
  await page.goto(BASE, { waitUntil: 'domcontentloaded', timeout: 20000 })
  await page.waitForTimeout(1200)
  try {
    await openAreaPanel(page)
    record('S0', '面板可打开', 'PASS', '')
  } catch (err) {
    record('S0', '面板可打开', 'BLOCKED', err.message)
  }
  await shot(page, 'S0')
})

step('S1', '默认区域显示（状态条 + 面板名称/边界/默认标记）', async ({ page }) => {
  await openAreaPanel(page)
  const statusBar = await findFirst(page, SEL.statusBar)
  if (!statusBar) { record('S1', '默认区域状态条', 'BLOCKED', '找不到 .area-status-bar'); return }
  const statusText = ((await statusBar.textContent()) || '').replace(/\s+/g, ' ').trim()
  if (!/默认项目分析区域/.test(statusText)) throw new Error(`状态条未标记默认区域：${statusText.slice(0, 120)}`)
  record('S1', '状态条显示默认区域', 'PASS', statusText.slice(0, 120))
  const label = await findFirst(page, SEL.areaLabel)
  const labelText = label ? ((await label.textContent()) || '').trim() : ''
  const chip = await findFirst(page, SEL.areaChip)
  const chipText = chip ? ((await chip.textContent()) || '').trim() : ''
  if (!labelText) throw new Error('面板区域名称为空')
  if (!/默认/.test(chipText)) throw new Error(`面板未标记默认区域，chip="${chipText}"`)
  record('S1', '面板显示默认区域名与标记', 'PASS', `name=${labelText} chip=${chipText}`)
  // 默认区状态下不应出现「区域已变更，待查询」
  const coord = await findFirst(page, SEL.statusCoord)
  record('S1', '默认区无「待查询」标记', /区域已变更/.test(statusText) ? 'FAIL' : 'PASS',
    coord ? ((await coord.textContent()) || '').trim() : '')
  await shot(page, 'S1')
})

step('S2', '地图缩放平移不改变分析区', async ({ page }) => {
  await openAreaPanel(page)
  const coordBefore = ((await page.locator(SEL.statusCoord[0]).first().textContent().catch(() => '')) || '').trim()
  const boundsBefore = ((await page.locator('p.aa-mono.aa-muted').first().textContent().catch(() => '')) || '').trim()
  const map = page.locator('.leaflet-container').first()
  if (await map.count() === 0) throw new Error('找不到地图容器 .leaflet-container')
  const box = await map.boundingBox()
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2)
  await page.mouse.wheel(0, -600)
  await page.waitForTimeout(500)
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2)
  await page.mouse.down()
  await page.mouse.move(box.x + box.width / 2 + 140, box.y + box.height / 2 + 90, { steps: 10 })
  await page.mouse.up()
  await page.waitForTimeout(600)
  const coordAfter = ((await page.locator(SEL.statusCoord[0]).first().textContent().catch(() => '')) || '').trim()
  const boundsAfter = ((await page.locator('p.aa-mono.aa-muted').first().textContent().catch(() => '')) || '').trim()
  if (!coordBefore || !boundsBefore) { record('S2', '缩放平移不改变分析区', 'BLOCKED', '区域坐标/边界文本不可读'); return }
  if (coordBefore !== coordAfter) throw new Error(`状态条坐标在缩放/平移后改变：${coordBefore} -> ${coordAfter}`)
  if (boundsBefore !== boundsAfter) throw new Error(`面板边界在缩放/平移后改变：${boundsBefore} -> ${boundsAfter}`)
  record('S2', '缩放平移不改变分析区', 'PASS', `coord 不变 = ${coordBefore}`)
  await shot(page, 'S2')
})

step('S3', '手动矩形圈选：拖拽 / ESC 取消 / 超大矩形被拒 / 恢复默认', async ({ page }) => {
  await openAreaPanel(page)
  const pts = await performDraw(page)
  const statusText = ((await page.locator(SEL.statusBar[0]).first().textContent()) || '').replace(/\s+/g, ' ').trim()
  if (!/自选矩形/.test(statusText)) throw new Error(`圈选后状态条未变为自选矩形：${statusText.slice(0, 140)}（拖动点 ${JSON.stringify(pts.extent)}）`)
  record('S3', '拖拽圈选应用为自定义矩形', 'PASS', `${statusText.slice(0, 120)}；空白区范围 ${JSON.stringify(pts.extent)}`)
  await shot(page, 'S3-rect-drag')

  // 2) ESC 取消：区域不变
  const coordCustom = ((await page.locator(SEL.statusCoord[0]).first().textContent()) || '').trim()
  const escPts = await safeDragPoints(page)
  const reselect = await findFirst(page, SEL.reselectRect)
  await reselect.click()
  await page.waitForTimeout(300)
  await page.mouse.move(escPts.x1, escPts.y1)
  await page.mouse.down()
  await page.mouse.move((escPts.x1 + escPts.x2) / 2, (escPts.y1 + escPts.y2) / 2, { steps: 8 })
  await page.keyboard.press('Escape')
  await page.mouse.up()
  await page.waitForTimeout(1500)
  const coordAfterEsc = ((await page.locator(SEL.statusCoord[0]).first().textContent()) || '').trim()
  const hintGone = await page.locator(SEL.drawHint[0]).count()
  if (coordAfterEsc !== coordCustom) throw new Error(`ESC 取消后区域被改变：${coordCustom} -> ${coordAfterEsc}`)
  record('S3', 'ESC 取消圈选不改变区域', hintGone === 0 ? 'PASS' : 'FAIL',
    `coord 不变；draw-hint 残留=${hintGone}`)

  // 3) 超大矩形：逐次缩放到 >10° 视野后水平拖满，直到后端拒绝；并核对失败回滚
  const coordBeforeOversize = ((await page.locator(SEL.statusCoord[0]).first().textContent()) || '').trim()
  let rejected = false
  let oversizeDetail = ''
  for (let attempt = 1; attempt <= 4 && !rejected; attempt++) {
    await performDraw(page, { zoomOutSteps: attempt * 3, horizontal: true })
    const noteEl = await findFirst(page, SEL.statusNote, { timeout: 3000 })
    const noteText = noteEl ? ((await noteEl.textContent()) || '').replace(/\s+/g, ' ').trim() : ''
    if (/不能超过|校验失败|无效|拒绝/.test(noteText)) {
      rejected = true
      oversizeDetail = `第 ${attempt} 次（缩放 ${attempt * 3} 步）被拒：${noteText.slice(0, 120)}`
    } else {
      oversizeDetail = `第 ${attempt} 次（缩放 ${attempt * 3} 步）仍被接受：${noteText.slice(0, 100)}`
    }
  }
  if (!rejected) throw new Error(`未能构造超大矩形被拒的场景（4 次尝试均被接受）：${oversizeDetail}`)
  const coordAfterOversize = ((await page.locator(SEL.statusCoord[0]).first().textContent()) || '').trim()
  if (coordAfterOversize !== coordBeforeOversize) {
    record('S3', '超大矩形被拒绝并回滚原区域', 'FAIL',
      `拒绝后区域未回滚：${coordBeforeOversize} -> ${coordAfterOversize}；${oversizeDetail}`)
  } else {
    record('S3', '超大矩形被拒绝并回滚原区域', 'PASS', oversizeDetail)
  }
  await shot(page, 'S3-oversize-rejected')

  // 4) 恢复默认区域：边界必须回到默认矩形，且状态必须恢复为「默认项目分析区域」
  const restore = await findFirst(page, SEL.restoreDefault)
  if (!restore) { record('S3', '恢复默认区域', 'BLOCKED', '找不到「恢复默认区域」按钮'); return }
  await restore.click()
  await page.waitForTimeout(3000)
  const statusRestored = ((await page.locator(SEL.statusBar[0]).first().textContent()) || '').replace(/\s+/g, ' ').trim()
  const coordRestored = ((await page.locator(SEL.statusCoord[0]).first().textContent()) || '').trim()
  const boundsOk = /25\.800–27\.100.*55\.800–57\.100/.test(coordRestored)
  const tagOk = /默认项目分析区域/.test(statusRestored)
  if (boundsOk && tagOk) {
    record('S3', '恢复默认区域', 'PASS', `${coordRestored}；${statusRestored.slice(0, 60)}`)
  } else {
    record('S3', '恢复默认区域', 'FAIL',
      `边界回到默认=${boundsOk}（${coordRestored}），但默认标记未恢复=${!tagOk}；状态条="${statusRestored.slice(0, 120)}"。`
      + '最小复现：POST /api/area-activity/resolve-area {"west":55.8,"south":25.8,"east":57.1,"north":27.1} '
      + '→ area_id=custom, is_default=false（带 area_id=hormuz_core_v1 亦为 false）；App.vue:821 传入 areaId:null 经 ?? "custom" 落到自定义分支')
  }
  await shot(page, 'S3-restored-default')
})

step('S4', '三模式各一次成功查询（数字与独立复算一致）', async ({ page }) => {
  await openAreaPanel(page)
  const tabs = await findFirst(page, SEL.modeTabs)
  if (!tabs) { record('S4', '三模式查询', 'BLOCKED', 'SEL.modeTabs 待补齐'); return }
  const n = await page.locator(SEL.modeTabs[0]).count()
  if (n < 3) throw new Error(`模式页签少于 3 个（实测 ${n}）`)

  // 时刻在场：2026-02-28T12:00Z
  await switchMode(page, '时刻在场')
  await setDatetime(page, SEL.inputs.snapshotAt, '2026-02-28T12:00')
  await runQuery(page)
  let facts = await readFacts(page)
  record('S4', '快照查询成功', Object.keys(facts).length ? 'PASS' : 'FAIL', JSON.stringify(facts).slice(0, 200))
  await assertFactNear('S4', facts, '在场船数', REC?.scenarios?.['snapshot_default_2026-02-28T12:00Z']?.summary?.in_area_count)
  // 默认区域身份回显：面板自身标记「默认区域」，结果区应回显 hormuz_core_v1 / is_default=true
  const areaIdShown = String(facts['area_id'] ?? '').trim()
  const areaNameShown = String(facts['区域'] ?? '').trim()
  if (areaIdShown === 'hormuz_core_v1') {
    record('S4', '默认区结果回显 area_id=hormuz_core_v1', 'PASS', `${areaNameShown}`)
  } else {
    record('S4', '默认区结果回显 area_id=hormuz_core_v1', 'FAIL',
      `面板区域标记为「默认区域」，但结果区显示 area_id=${areaIdShown}、区域名称=${areaNameShown}；期望 hormuz_core_v1/is_default=true（GET 无 bounds 时实测为该值）`)
  }
  await shot(page, 'S4-mode1-snapshot')

  // 时段活动：2026-02-28 → 2026-03-01
  await switchMode(page, '时段活动')
  await setDatetime(page, SEL.inputs.activityStart, '2026-02-28T00:00')
  await setDatetime(page, SEL.inputs.activityEnd, '2026-03-01T00:00')
  await runQuery(page)
  facts = await readFacts(page)
  record('S4', '时段活动查询成功', Object.keys(facts).length ? 'PASS' : 'FAIL', JSON.stringify(facts).slice(0, 240))
  const expAct = REC?.scenarios?.['activity_default_1d_2026-02-28']?.summary
  await assertFactNear('S4', facts, '去重出现船数', expAct?.ships_observed)
  await assertFactNear('S4', facts, '观测进入次数', expAct?.observed_entry_count)
  await assertFactNear('S4', facts, '观测离开次数', expAct?.observed_exit_count)
  await assertFactNear('S4', facts, '累计船时', expAct?.observed_ship_hours, 0.1)
  await shot(page, 'S4-mode2-activity')

  // 两时段比较：A 02-27→02-28，B 02-28→03-01
  await switchMode(page, '两时段比较')
  await setDatetime(page, SEL.inputs.startA, '2026-02-27T00:00')
  await setDatetime(page, SEL.inputs.endA, '2026-02-28T00:00')
  await setDatetime(page, SEL.inputs.startB, '2026-02-28T00:00')
  await setDatetime(page, SEL.inputs.endB, '2026-03-01T00:00')
  await runQuery(page)
  const rows = await page.$$eval('.aa-table-wrap[aria-label^="两期指标对比表"] tbody tr',
    (trs) => trs.map((tr) => Array.from(tr.children).map((td) => (td.textContent || '').replace(/\s+/g, ' ').trim())))
  record('S4', '两时段比较查询成功', rows.length ? 'PASS' : 'FAIL', `${rows.length} 行`)
  checkCompareRows(rows)
  await shot(page, 'S4-mode3-compare')
})

step('S5', '空结果与参数错误（ok+零结果 / 422）', async ({ page }) => {
  await openAreaPanel(page)
  // 有效零结果：快照时刻选在数据覆盖结束之后（最新报位已过期）→ ok + 0 在场
  await switchMode(page, '时刻在场')
  await setDatetime(page, SEL.inputs.snapshotAt, '2026-03-05T00:00')
  await runQuery(page)
  const facts = await readFacts(page)
  const inArea = toNum(facts['在场船数'])
  if (inArea === null) { record('S5', '有效零结果', 'BLOCKED', '读不到「在场船数」'); return }
  if (inArea !== 0) throw new Error(`期望有效零结果，实际在场船数=${inArea}`)
  const emptyHint = await page.locator('p.aa-empty').count()
  record('S5', '有效零结果（ok + 0 在场）', 'PASS', `在场船数=0，提示元素=${emptyHint}`)
  await shot(page, 'S5-empty-result')

  // 参数错误：start >= end
  await switchMode(page, '时段活动')
  await setDatetime(page, SEL.inputs.activityStart, '2026-03-01T00:00')
  await setDatetime(page, SEL.inputs.activityEnd, '2026-02-28T00:00')
  await runQuery(page)
  const err = await findFirst(page, SEL.errorBox, { timeout: 5000 })
  const errText = err ? ((await err.textContent()) || '').trim() : ''
  if (!errText) throw new Error('start >= end 未产生错误提示')
  record('S5', '参数错误（start >= end）被拒', 'PASS', errText.slice(0, 120))
  await shot(page, 'S5-param-error')
})

step('S6', '加载/取消/旧响应不覆盖新条件', async ({ page }) => {
  await openAreaPanel(page)
  // 1) 长查询（7 天默认区）→ 取消：加载态必须结束，且不写出错误结果
  await switchMode(page, '时段活动')
  await setDatetime(page, SEL.inputs.activityStart, '2026-02-24T16:00')
  await setDatetime(page, SEL.inputs.activityEnd, '2026-03-03T15:59')
  const run = await findFirst(page, SEL.runQuery)
  if (!run) { record('S6', '取消查询', 'BLOCKED', '找不到查询按钮'); return }
  await run.click()
  await page.waitForTimeout(400)
  const cancel = await findFirst(page, SEL.cancelQuery, { timeout: 3000 })
  if (!cancel) { record('S6', '取消按钮出现', 'FAIL', '加载中没有出现「取消」按钮'); return }
  await cancel.click()
  let busyLeft = true
  for (let i = 0; i < 100; i++) {
    if (await page.locator('.aa-scroll[aria-busy="true"]').count() === 0) { busyLeft = false; break }
    await page.waitForTimeout(200)
  }
  if (busyLeft) throw new Error('点击取消后 20 s 内加载态未结束')
  const afterCancelStatus = await statusText(page)
  record('S6', '取消后加载态结束', 'PASS', afterCancelStatus.slice(0, 80))
  await shot(page, 'S6-cancelled')

  // 2) 旧响应不覆盖新条件：发起 7 天查询后立刻切到快照模式改条件
  await switchMode(page, '时段活动')
  await run.click()
  await page.waitForTimeout(250)
  await switchMode(page, '时刻在场')
  await setDatetime(page, SEL.inputs.snapshotAt, '2026-02-28T12:00')
  await page.getByRole('button', { name: '查询', exact: true }).first().click({timeout: 2000}).catch(() => {})
  await page.waitForTimeout(12000)
  const activityHeading = await page.locator('h4:has-text("全窗汇总")').count()
  const snapshotFacts = await readFacts(page).catch(() => ({}))
  if (activityHeading > 0) throw new Error('已切到快照模式，却显示了时段活动的旧结果')
  const inArea = toNum(snapshotFacts['在场船数'])
  const expected = REC?.scenarios?.['snapshot_default_2026-02-28T12:00Z']?.summary?.in_area_count
  if (inArea === null) record('S6', '旧响应不覆盖新条件', 'FAIL', '切换条件后未渲染新条件结果')
  else if (expected !== undefined && inArea !== expected) {
    record('S6', '旧响应不覆盖新条件', 'FAIL', `新条件结果=${inArea}，独立复算期望=${expected}`)
  } else record('S6', '旧响应不覆盖新条件', 'PASS', `快照在场船数=${inArea}`)
  await shot(page, 'S6-stale-guard')

  // 3) 查询成功后变更区域 → 旧结果必须标「区域已变更，待查询」
  const reselect = await findFirst(page, SEL.reselectRect)
  if (!reselect) { record('S6', '区域变更后旧结果标记', 'BLOCKED', '找不到「重新圈选」'); return }
  await performDraw(page)
  const statusAfter = ((await page.locator(SEL.statusBar[0]).first().textContent()) || '').replace(/\s+/g, ' ').trim()
  const panelStale = await page.locator('.aa-stale').count()
  if (!/区域已变更，待查询/.test(statusAfter) && panelStale === 0) {
    throw new Error(`区域变更后未标记待查询：状态条="${statusAfter.slice(0, 140)}" panelStale=${panelStale}`)
  }
  record('S6', '区域变更后旧结果标「区域已变更，待查询」', 'PASS',
    `状态条标记=${/区域已变更/.test(statusAfter)} 面板标记=${panelStale}`)
  await shot(page, 'S6-area-changed-stale')
})

step('S7', '证据联动：访问行「地图定位」→ 轨迹时段与访问一致', async ({ page }) => {
  await openAreaPanel(page)
  await switchMode(page, '时段活动')
  await setDatetime(page, SEL.inputs.activityStart, '2026-02-28T00:00')
  await setDatetime(page, SEL.inputs.activityEnd, '2026-03-01T00:00')
  await runQuery(page)
  const rows = await findFirst(page, SEL.visitRow)
  if (!rows) { record('S7', '访问记录联动', 'BLOCKED', '访问明细表未出现'); return }
  const all = await page.$$eval(SEL.visitRow[0], (trs) =>
    trs.map((tr) => Array.from(tr.children).map((td) => (td.textContent || '').replace(/\s+/g, ' ').trim())))
  const parsed = all.map((cells, index) => {
    const from = parseVisitTime(cells[2])
    const to = parseVisitTime(cells[3])
    return {
      index, cells,
      shipId: (String(cells[0]).match(/#(\d+)/) || [])[1] || null,
      from, to, spanMs: from !== null && to !== null ? to - from : null,
    }
  })
  const good = parsed.find((v) => v.spanMs !== null && v.spanMs > 0 && v.spanMs <= 86400000)
  const bad = parsed.find((v) => v.spanMs !== null && (v.spanMs <= 0 || v.spanMs > 86400000))
  record('S7', '访问明细行可解析', parsed.length ? 'PASS' : 'FAIL',
    `共 ${parsed.length} 行；0<跨度≤24h ${parsed.filter((v) => v.spanMs > 0 && v.spanMs <= 86400000).length} 行；跨度>24h 或为 0 ${parsed.filter((v) => v.spanMs <= 0 || v.spanMs > 86400000).length} 行`)

  // (b) 正常时长访问（0<跨度≤24h）先测：轨迹请求必须与访问时段一致，且地图出现轨迹
  const goodCandidates = parsed.filter((v) => v.spanMs !== null && v.spanMs > 0 && v.spanMs <= 86400000).slice(0, 6)
  if (!goodCandidates.length) {
    record('S7', '正常时长访问联动', 'BLOCKED', '本轮访问明细里没有 0<跨度≤24h 的访问行')
  }
  const trackRequests = []
  page.on('request', (r) => {
    if (/\/ships\/\d+\/track-window/.test(r.url())) trackRequests.push(r.url())
  })
  let goodDone = false
  for (const cand of goodCandidates) {
    const row = page.locator(SEL.visitRow[0]).nth(cand.index)
    const locate = row.locator(SEL.locateBtn[0]).first()
    if (await locate.count() === 0) continue
    await locate.scrollIntoViewIfNeeded().catch(() => {})
    const before = await page.locator('.leaflet-container svg path, .track-direction-arrow').count()
    trackRequests.length = 0
    try {
      await locate.click({ timeout: 12000 })
    } catch (err) {
      record('S7', `候选访问行 ${cand.index} 点击失败`, 'BLOCKED', String(err.message).split('\n')[0])
      continue
    }
    await page.waitForTimeout(8000)
    const after = await page.locator('.leaflet-container svg path, .track-direction-arrow').count()
    const matches = trackRequests.filter((u) => {
      const q = new URL(u).searchParams
      return Math.abs(Date.parse(q.get('from')) - cand.from) < 1000 && Math.abs(Date.parse(q.get('to')) - cand.to) < 1000
    })
    if (!matches.length) continue
    const reqUrl = new URL(matches[0])
    const reqShip = (matches[0].match(/\/ships\/(\d+)\//) || [])[1]
    const shipOk = cand.shipId === null || reqShip === cand.shipId
    if (!shipOk) { record('S7', '轨迹请求船号一致', 'FAIL', `${reqShip} vs ${cand.shipId}`); continue }
    const toast = await page.locator('.alert-toast').first().textContent().catch(() => '')
    const detail = `访问 ${cand.cells[0]} ${cand.cells[2]}~${cand.cells[3]}；请求 ${reqUrl.searchParams.get('from')}~${reqUrl.searchParams.get('to')}；`
      + `图形 ${before}->${after}；toast=${(toast || '').trim().slice(0, 40)}`
    if (after <= before) {
      record('S7', '轨迹请求时段与访问一致', 'PASS', detail)
      record('S7', '地图出现轨迹图形', 'FAIL', `图形数未增加（${before} -> ${after}）`)
    } else {
      record('S7', '访问行「地图定位」轨迹与访问时段一致', 'PASS', detail)
    }
    goodDone = true
    break
  }
  if (!goodDone && goodCandidates.length) {
    record('S7', '正常时长访问联动', 'FAIL', '候选行都未能触发与访问时段一致的轨迹请求')
  }
  await shot(page, 'S7-track')

  // (a) 超 24h / 零长度访问：修复后超 24h 应按「末次区内报位向前 24h」裁剪；0 长度仍应明确拒绝
  const longCandidates = parsed.filter((v) => v.spanMs !== null && v.spanMs > 86400000).slice(0, 4)
  const zeroCandidates = parsed.filter((v) => v.spanMs !== null && v.spanMs <= 0).slice(0, 2)
  const longRequests = []
  page.on('request', (r) => {
    if (/\/ships\/\d+\/track-window/.test(r.url())) longRequests.push(r.url())
  })
  const clearToast = async () => {
    for (let i = 0; i < 10; i++) {
      if (await page.locator('.alert-toast').count() === 0) return
      await page.locator('button[aria-label="关闭提醒"]').first().click({timeout: 2000}).catch(() => {})
      await page.waitForTimeout(250)
    }
  }
  let longOk = false
  let longDetail = ''
  for (const cand of longCandidates) {
    await clearToast()
    const row = page.locator(SEL.visitRow[0]).nth(cand.index)
    const btn = row.locator(SEL.locateBtn[0]).first()
    if (await btn.count() === 0) continue
    await btn.scrollIntoViewIfNeeded().catch(() => {})
    const shapesBefore = await page.locator('.leaflet-container svg path, .track-direction-arrow').count()
    longRequests.length = 0
    try { await btn.click({ timeout: 12000 }) } catch {
      // 真实点击失败必须作为可达性失败记录，不能用 DOM click 绕过遮挡
      record('S7', '长访问按钮真实点击可达', 'FAIL', '按钮被遮挡或不可点击'); continue
    }
    await page.waitForTimeout(6000)
    const toastText = ((await page.locator('.alert-toast').first().textContent().catch(() => '')) || '').replace(/\s+/g, ' ').trim()
    const shapesAfter = await page.locator('.leaflet-container svg path, .track-direction-arrow').count()
    const req = longRequests.map((u) => new URL(u)).find((q) => Math.abs(Date.parse(q.searchParams.get('to')) - cand.to) < 1000)
    const durH = req ? (Date.parse(req.searchParams.get('to')) - Date.parse(req.searchParams.get('from'))) / 3600000 : null
    longDetail = `访问键=${cand.cells[0]} ${cand.cells[2]}~${cand.cells[3]}（跨度 ${(cand.spanMs / 3600000).toFixed(2)}h） → `
      + `请求 ${req ? `${req.searchParams.get('from')}~${req.searchParams.get('to')}（${durH.toFixed(2)}h）` : '无'}；`
      + `图形 ${shapesBefore}->${shapesAfter}；toast="${toastText.slice(0, 60)}"`
    if (req && durH !== null && durH <= 24.001 && durH > 23.0 && shapesAfter > shapesBefore) { longOk = true; break }
  }
  if (longCandidates.length) {
    record('S7', '跨度 >24h 的访问按 24h 裁剪并显示轨迹', longOk ? 'PASS' : 'FAIL', longDetail)
  }
  if (zeroCandidates.length) {
    const cand = zeroCandidates[0]
    await clearToast()
    const row = page.locator(SEL.visitRow[0]).nth(cand.index)
    const btn = row.locator(SEL.locateBtn[0]).first()
    await btn.scrollIntoViewIfNeeded().catch(() => {})
    const before = await page.locator('.leaflet-container svg path, .track-direction-arrow').count()
    await btn.click({ timeout: 12000 })
    await page.waitForTimeout(3000)
    const toastText = ((await page.locator('.alert-toast').first().textContent().catch(() => '')) || '').replace(/\s+/g, ' ').trim()
    const after = await page.locator('.leaflet-container svg path, .track-direction-arrow').count()
    const rejected = /无效|超出|最多 24 小时|无法/.test(toastText)
    record('S7', '零长度访问「地图定位」被明确拒绝', rejected ? 'PASS' : 'FAIL',
      `访问键=${cand.cells[0]} ${cand.cells[2]}~${cand.cells[3]} → toast="${toastText.slice(0, 80)}"；图形 ${before}->${after}`)
  }
  await shot(page, 'S7-long-visit')
})

step('S8', '桌面 1440 / 窄屏 390 无横向溢出；prefers-reduced-motion 无报错', async ({ page, context }) => {
  await openAreaPanel(page)
  await switchMode(page, '时段活动')
  await setDatetime(page, SEL.inputs.activityStart, '2026-02-28T00:00')
  await setDatetime(page, SEL.inputs.activityEnd, '2026-03-01T00:00')
  await runQuery(page)
  for (const [w, h, tag] of [[1440, 900, 'desktop-1440'], [390, 844, 'narrow-390']]) {
    await page.setViewportSize({ width: w, height: h })
    await page.waitForTimeout(900)
    const overflow = await page.evaluate(() => ({
      docScrollW: document.documentElement.scrollWidth,
      clientW: document.documentElement.clientWidth,
      bodyScrollW: document.body.scrollWidth,
      panelScrollW: document.querySelector('.aa-panel')?.scrollWidth ?? null,
      panelW: document.querySelector('.aa-panel')?.clientWidth ?? null,
    }))
    const bad = overflow.docScrollW > overflow.clientW + 1 || overflow.bodyScrollW > overflow.clientW + 1
    if (bad) throw new Error(`${tag} 横向溢出：${JSON.stringify(overflow)}`)
    record('S8', `${tag} 无横向溢出`, 'PASS', JSON.stringify(overflow))
    await shot(page, `S8-${tag}`)
  }
  // prefers-reduced-motion：本 context 已用 reducedMotion: 'reduce' 创建，检查图表/动画分支不报错
  const motion = await page.evaluate(() => window.matchMedia('(prefers-reduced-motion: reduce)').matches)
  record('S8', 'prefers-reduced-motion 生效且无报错', motion ? 'PASS' : 'FAIL', `matchMedia(reduce)=${motion}`)
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.waitForTimeout(500)
  await shot(page, 'S8-reduced-motion')
})

step('S9', '智能体 analysis_actions →「查看区域分析」回填面板（1 次真实模型调用）', async ({ page }) => {
  // 捕获 /agent/analyze 响应，用于核对 analysis_actions.query 的区域身份（F5 复测）
  let agentPayload = null
  page.on('response', async (r) => {
    if (r.url().includes('/agent/analyze') && r.status() === 200) {
      try { agentPayload = await r.json() } catch { /* ignore */ }
    }
  })
  // 打开智能体面板
  const agentBtn = page.locator('button[aria-label="智能体"]').first()
  await agentBtn.waitFor({ state: 'visible', timeout: 8000 })
  await agentBtn.click()
  const input = page.locator('textarea[aria-label="智能体问题"]').first()
  await input.waitFor({ state: 'visible', timeout: 8000 })
  const question = '2026-02-28T11:59Z 到 2026-02-28T12:01Z 之间，霍尔木兹核心通行区有多少艘船在航？'
  await input.fill(question)
  await page.locator('button[aria-label="发送提问"]').first().click()
  const result = page.locator('.agent-result').first()
  await result.waitFor({ state: 'visible', timeout: 120000 })
  const answer = ((await result.textContent()) || '').replace(/\s+/g, ' ').trim()
  record('S9', '智能体回答渲染', 'PASS', answer.slice(0, 120))
  const action = (agentPayload?.analysis_actions || []).find((a) => a?.type === 'area_activity')
  if (action) {
    const q = action.query || {}
    const identityOk = q.area_id === 'hormuz_core_v1' && q.area_is_default === true
    record('S9', 'analysis_actions.query 区域身份（F5 复测）', identityOk ? 'PASS' : 'FAIL',
      `area_id=${q.area_id} area_is_default=${q.area_is_default} mode=${action.mode} at=${q.at ?? ''} `
      + `bounds=${q.west}/${q.south}/${q.east}/${q.north} status=${agentPayload?.status} tools=${JSON.stringify(agentPayload?.tools_used)}`)
  } else {
    record('S9', 'analysis_actions.query 区域身份（F5 复测）', 'FAIL',
      `响应无 area_activity 动作；status=${agentPayload?.status} tools=${JSON.stringify(agentPayload?.tools_used)}`)
  }
  const suggest = await findFirst(page, SEL.suggestBar, { timeout: 15000 })
  if (!suggest) { record('S9', '出现「查看区域分析」建议条', 'FAIL', '未出现 .area-suggest-bar'); return }
  const suggestText = ((await suggest.textContent()) || '').replace(/\s+/g, ' ').trim()
  record('S9', '出现「查看区域分析」建议条', 'PASS', suggestText.slice(0, 120))
  await shot(page, 'S9-agent-answer')

  const open = await findFirst(page, SEL.openSuggested, { timeout: 5000 })
  if (!open) { record('S9', '建议条按钮可点', 'FAIL', '找不到 [data-testid=open-area-analysis]'); return }
  await open.click()
  const panel = await findFirst(page, SEL.panel, { timeout: 8000 })
  if (!panel) { record('S9', '点击后打开区域面板', 'FAIL', '面板未出现'); return }
  await page.waitForTimeout(1500)
  const activeMode = ((await page.locator('.aa-mode.active').first().textContent().catch(() => '')) || '').trim()
  const atValue = await page.locator(SEL.inputs.snapshotAt).first().inputValue().catch(() => '')
  const startValue = await page.locator(SEL.inputs.activityStart).first().inputValue().catch(() => '')
  const endValue = await page.locator(SEL.inputs.activityEnd).first().inputValue().catch(() => '')
  const areaLabel = ((await page.locator(SEL.areaLabel[0]).first().textContent().catch(() => '')) || '').trim()
  const chip = ((await page.locator(SEL.areaChip[0]).first().textContent().catch(() => '')) || '').trim()
  const modes = ['时刻在场', '时段活动', '两时段比较']
  const modeOk = modes.some((m) => activeMode.includes(m))
  const timeOk = activeMode.includes('时刻在场')
    ? atValue.startsWith('2026-02-28T12:00') || atValue.startsWith('2026-02-28T11:5')
    : (startValue.length > 0 && endValue.length > 0)
  record('S9', '打开面板并回填模式/时刻', modeOk && timeOk ? 'PASS' : 'FAIL',
    `mode=${activeMode} at=${atValue} start=${startValue} end=${endValue} area=${areaLabel} chip=${chip}`)
  await shot(page, 'S9-restored-panel')
})

step('S10', '「写入对话」：区域条件带入智能体输入框且无 ReferenceError', async ({ page }) => {
  await openAreaPanel(page)
  await switchMode(page, '时刻在场')
  await setDatetime(page, SEL.inputs.snapshotAt, '2026-02-28T12:00')
  await runQuery(page)
  const write = await findFirst(page, SEL.writeDialog, { timeout: 5000 })
  if (!write) { record('S10', '「写入对话」按钮', 'FAIL', '找不到按钮'); return }
  await write.click()
  await page.waitForTimeout(1500)
  const input = page.locator('textarea[aria-label="智能体问题"]').first()
  const visible = await input.isVisible().catch(() => false)
  if (!visible) { record('S10', '「写入对话」后智能体输入框可见', 'FAIL', '输入框不可见'); return }
  const value = await input.inputValue()
  record('S10', '「写入对话」带入区域条件', value.trim().length > 20 ? 'PASS' : 'FAIL',
    `提示词长度=${value.trim().length}；前 80 字="${value.trim().slice(0, 80)}"`)
  await shot(page, 'S10-write-to-dialog')
})

// ---------------------------------------------------------------- 主流程
async function main() {
  const accessErrors = []
  const browser = await chromium.launch({ channel: 'msedge', headless: !HEADFUL })
  let consoleErrors = []
  let httpErrors = []
  const newPage = async (opts) => {
    const context = await browser.newContext(opts)
    const page = await context.newPage()
    page.on('console', (m) => { if (m.type() === 'error') consoleErrors.push(m.text()) })
    page.on('pageerror', (e) => consoleErrors.push(String(e)))
    page.on('response', (r) => { if (r.status() >= 400) httpErrors.push(`HTTP ${r.status()} ${r.url()}`) })
    return { context, page }
  }

  // 可达性预检
  const pre = await newPage({ viewport: { width: 1440, height: 900 } })
  try {
    const resp = await pre.page.goto(BASE, { waitUntil: 'domcontentloaded', timeout: 15000 })
    console.log(`INFO: ${BASE} -> HTTP ${resp ? resp.status() : 'n/a'}`)
  } catch (err) {
    console.log(`BLOCKED: 无法访问 ${BASE}（${err.message.split('\n')[0]}）——前端 dev server 未启动？`)
    await pre.context.close(); await browser.close()
    fs.writeFileSync(RESULT_PATH, JSON.stringify({
      generated_at: new Date().toISOString(), base: BASE,
      status: 'blocked', reason: `前端不可访问：${err.message.split('\n')[0]}`, results,
    }, null, 2), 'utf-8')
    process.exit(2)
  }
  await pre.context.close()

  for (const s of steps) {
    if (ONLY.length && !ONLY.includes(s.id)) { console.log(`SKIP  [${s.id}] ${s.name}`); continue }
    consoleErrors = []
    httpErrors = []
    const { context, page } = await newPage({ viewport: { width: 1440, height: 900 }, reducedMotion: 'reduce' })
    try {
      await page.goto(BASE, { waitUntil: 'domcontentloaded', timeout: 20000 })
      await page.waitForTimeout(1200)
      await s.run({ page, context })
    } finally {
      // 已知环境项（非本功能）：
      //  (1) 工作树缺 news_raw_data（events.py 取 PROJECT_ROOT.parent/"news_raw_data"）→ /events/*/cover 404；
      //  (2) node_modules 是指向主仓库的 Junction → Vite @fs 白名单拒绝 Leaflet 默认图标（403）。
      //      两者在主仓库（5174）分别为 200/200，已单独取证。单独记录、不计入控制台错误。
      const knownEnvPattern = /\/events\/[^/]+\/cover/
      const knownEnvLeaflet = /\/@fs\/.*node_modules\/leaflet\/dist\/images\/marker-(?:icon|shadow)\.png/
      const expectedPattern = /resolve-area$/
      const knownHttp = httpErrors.filter((u) => knownEnvPattern.test(u) || knownEnvLeaflet.test(u))
      const expectedSeen = httpErrors.filter((u) => expectedPattern.test(u))
      const realHttp = httpErrors.filter((u) => !knownEnvPattern.test(u) && !knownEnvLeaflet.test(u) && !expectedPattern.test(u))
      const resourceFailures = consoleErrors.filter((e) => /Failed to load resource/i.test(e))
      const otherConsole = consoleErrors.filter((e) => !/Failed to load resource/i.test(e) && !/favicon/i.test(e))
      const expectedCount = expectedSeen.length
      const realConsole = [...otherConsole]
      if (realHttp.length) realConsole.push(...realHttp)
      else if (resourceFailures.length) {
        const unexplained = Math.max(0, resourceFailures.length - knownHttp.length - expectedCount)
        if (unexplained > 0) realConsole.push(...resourceFailures.slice(0, unexplained))
      }
      if (knownHttp.length) {
        const cover = knownHttp.filter((u) => knownEnvPattern.test(u)).length
        const leaflet = knownHttp.filter((u) => knownEnvLeaflet.test(u)).length
        record(s.id, '已知环境项（非本功能）', 'PASS',
          `新闻封面 404 ×${cover}；leaflet 默认图标 403 ×${leaflet}（工作树路径/Junction 导致，主仓库为 200）`)
      }
      if (expectedSeen.length) {
        record(s.id, '预期 4xx（负向用例）', 'PASS', expectedSeen.map((u) => u.slice(0, 60)).join(' | '))
      }
      if (realConsole.length) record(s.id, '控制台 0 error', 'FAIL', JSON.stringify(realConsole.slice(0, 3)))
      else record(s.id, '控制台 0 error', 'PASS', '')
      await context.close()
    }
  }
  await browser.close()

  const counts = results.reduce((acc, r) => { acc[r.status] = (acc[r.status] || 0) + 1; return acc }, {})
  const payload = {
    generated_at: new Date().toISOString(), base: BASE,
    counts, results,
    console_errors: consoleErrors,
  }
  fs.writeFileSync(RESULT_PATH, JSON.stringify(payload, null, 2), 'utf-8')
  console.log(`\nSUMMARY: ${JSON.stringify(counts)} -> ${RESULT_PATH}`)
  process.exit(Object.keys(counts).some((k) => k === 'FAIL' || k === 'BLOCKED') ? 1 : 0)
}

main().catch((err) => { console.error('FAIL:', err.message); process.exit(1) })
