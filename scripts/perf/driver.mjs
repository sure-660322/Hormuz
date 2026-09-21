// 地图回放渲染性能实测驱动（开发环境一次性测量工具）。
// 用法: node driver.mjs <baseUrl> <outJson>
// 在页面注入 longtask 观察器，并读取应用内 ?perf=1 探针(window.__hormuzPerf)的数据。
import puppeteer from 'puppeteer-core'
import { writeFileSync } from 'node:fs'

const [, , baseUrl = 'http://localhost:5174/?perf=1', outJson = 'result.json'] = process.argv
const CHROME = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

const browser = await puppeteer.launch({
  executablePath: CHROME,
  headless: true,
  args: [
    '--no-sandbox',
    '--disable-background-timer-throttling',
    '--disable-renderer-backgrounding',
    '--disable-backgrounding-occluded-windows',
    '--window-size=1600,900',
  ],
})
const page = await browser.newPage()
await page.setViewport({ width: 1600, height: 900 })
await page.evaluateOnNewDocument(() => {
  const w = window
  w.__longtasks = []
  new PerformanceObserver((list) => {
    for (const entry of list.getEntries()) {
      w.__longtasks.push({ start: entry.startTime, duration: entry.duration })
    }
  }).observe({ entryTypes: ['longtask'] })
})

await page.goto(baseUrl, { waitUntil: 'domcontentloaded', timeout: 60000 })
// 等待回放数据加载完成（地图上出现船舶 Marker，加载提示消失）
await page.waitForFunction(
  () =>
    document.querySelectorAll('.vessel-marker').length > 0 &&
    !document.querySelector('.map-data-status'),
  { timeout: 120000 },
)
await sleep(1500)

const results = { scenarios: {}, meta: { url: baseUrl, userAgent: await browser.version() } }

async function resetCounters() {
  await page.evaluate(() => {
    window.__longtasks.length = 0
    window.__hormuzPerf?.reset()
  })
}

async function collect(label, extra = {}) {
  const data = await page.evaluate(() => {
    const lt = window.__longtasks
    const durs = lt.map((t) => t.duration).sort((a, b) => a - b)
    const probe = window.__hormuzPerf ? window.__hormuzPerf.stats() : null
    return {
      longtaskCount: lt.length,
      longtaskMedianMs: durs.length ? durs[Math.floor(durs.length / 2)] : 0,
      longtaskMaxMs: durs.length ? durs[durs.length - 1] : 0,
      longtaskTotalMs: durs.reduce((a, b) => a + b, 0),
      probe,
      vesselMarkers: document.querySelectorAll('.vessel-marker').length,
      incidentMarkers: document.querySelectorAll('.incident-marker').length,
      trackPointMarkers: document.querySelectorAll('.leaflet-interactive').length,
    }
  })
  results.scenarios[label] = { ...data, ...extra }
  console.log(label, JSON.stringify(data.probe ?? {}, null, 0))
}

// —— 场景 1：普通播放 1×，未选中船舶 ——
await resetCounters()
await page.click('.play-button')
await sleep(6000)
await page.click('.play-button') // 暂停
await sleep(300)
await collect('play-1x-no-selection')

// —— 场景 2：快速拖动滑块（大跨度随机跳变，模拟快速 scrub）——
await resetCounters()
await page.evaluate(async () => {
  const slider = document.querySelector('#replay-time')
  const max = Number(slider.max)
  for (let i = 0; i < 150; i++) {
    slider.value = String(Math.floor(Math.random() * max))
    slider.dispatchEvent(new Event('input', { bubbles: true }))
    await new Promise((r) => setTimeout(r, 8))
  }
})
await sleep(800)
await collect('fast-scrub-no-selection')

// —— 场景 3：选中船舶并显示轨迹（放大到 zoom>=10 使向量线/船首向也参与）——
await page.evaluate(() => {
  document.querySelector('.leaflet-control-zoom-in')?.click()
})
await sleep(400)
await page.evaluate(() => {
  document.querySelector('.leaflet-control-zoom-in')?.click()
})
await sleep(400)
await page.evaluate(() => {
  document.querySelector('.leaflet-control-zoom-in')?.click()
})
await sleep(800)
await page.click('.vessel-marker')
await sleep(1200)
const hasTrackButton = await page.evaluate(() => {
  const btn = [...document.querySelectorAll('button')].find((b) => b.textContent.includes('查看轨迹'))
  if (btn) btn.click()
  return Boolean(btn)
})
await sleep(2500) // 等待轨迹首次构建（整轨创建，属一次性成本）
await resetCounters()
await page.click('.play-button')
await sleep(6000)
await page.click('.play-button')
await sleep(300)
await collect('play-1x-selected-track', { trackToggled: hasTrackButton })

// —— 场景 4：开启速度着色后继续播放 ——
await page.evaluate(() => {
  const btn = [...document.querySelectorAll('button')].find((b) => b.textContent.includes('速度着色'))
  if (btn) btn.click()
})
await sleep(3500) // 等待 /api/tracks 取回
await resetCounters()
await page.click('.play-button')
await sleep(6000)
await page.click('.play-button')
await sleep(300)
await collect('play-1x-speed-color')

// —— 场景 5：快速拖动（选中船 + 轨迹 + 着色状态下）——
await resetCounters()
await page.evaluate(async () => {
  const slider = document.querySelector('#replay-time')
  const max = Number(slider.max)
  for (let i = 0; i < 150; i++) {
    slider.value = String(Math.floor(Math.random() * max))
    slider.dispatchEvent(new Event('input', { bubbles: true }))
    await new Promise((r) => setTimeout(r, 8))
  }
})
await sleep(800)
await collect('fast-scrub-selected-track-color')

// —— 场景 6：2× / 4× 播放 ——
for (const speed of [2, 4]) {
  await page.select('select[aria-label="播放速度"]', String(speed))
  await resetCounters()
  await page.click('.play-button')
  await sleep(6000)
  await page.click('.play-button')
  await sleep(300)
  await collect(`play-${speed}x`)
}

await browser.close()
writeFileSync(outJson, JSON.stringify(results, null, 2))
console.log('written to', outJson)
