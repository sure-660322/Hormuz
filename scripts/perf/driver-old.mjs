// 旧代码（全量重建版）对照测量：同步渲染阻塞主线程，减少 scrub 次数防止超时。
import puppeteer from 'puppeteer-core'
import { writeFileSync } from 'node:fs'

const CHROME = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

const browser = await puppeteer.launch({
  executablePath: CHROME,
  headless: true,
  args: ['--no-sandbox', '--disable-background-timer-throttling', '--disable-renderer-backgrounding', '--window-size=1600,900'],
})
const page = await browser.newPage()
await page.setViewport({ width: 1600, height: 900 })
await page.evaluateOnNewDocument(() => {
  const w = window
  w.__longtasks = []
  new PerformanceObserver((list) => {
    for (const entry of list.getEntries()) w.__longtasks.push(entry.duration)
  }).observe({ entryTypes: ['longtask'] })
})
await page.goto('http://localhost:5174/', { waitUntil: 'domcontentloaded', timeout: 60000 })
await page.waitForFunction(
  () => document.querySelectorAll('.vessel-marker').length > 0 && !document.querySelector('.map-data-status'),
  { timeout: 120000 },
)
await sleep(1500)

const results = {}
async function measure(label, ms) {
  await page.evaluate(() => { window.__longtasks.length = 0 })
  await sleep(ms)
  const s = await page.evaluate(() => {
    const d = [...window.__longtasks].sort((a, b) => a - b)
    return {
      longtaskCount: d.length,
      medianMs: d.length ? d[Math.floor(d.length / 2)] : 0,
      maxMs: d.length ? d[d.length - 1] : 0,
      totalMs: d.reduce((a, b) => a + b, 0),
      vesselMarkers: document.querySelectorAll('.vessel-marker').length,
      incidentMarkers: document.querySelectorAll('.incident-marker').length,
    }
  })
  results[label] = s
  console.log(label, JSON.stringify(s))
}

// 旧代码：普通播放 1×
await page.click('.play-button')
await measure('OLD play-1x 6s', 6000)
await page.click('.play-button')

// 旧代码：快速拖动（40 次随机跳变；每次同步渲染 ~0.5s，需 ~20s）
await page.evaluate(async () => {
  const slider = document.querySelector('#replay-time')
  const max = Number(slider.max)
  for (let i = 0; i < 40; i++) {
    slider.value = String(Math.floor(Math.random() * max))
    slider.dispatchEvent(new Event('input', { bubbles: true }))
    await new Promise((r) => setTimeout(r, 5))
  }
})
await measure('OLD fast-scrub 40 jumps + 1s settle', 1000)

// 旧代码：选中船 + 轨迹 + 播放
await page.evaluate(() => { document.querySelector('.leaflet-control-zoom-in')?.click() })
await sleep(500)
await page.evaluate(() => { document.querySelector('.leaflet-control-zoom-in')?.click() })
await sleep(500)
await page.evaluate(() => { document.querySelector('.leaflet-control-zoom-in')?.click() })
await sleep(1000)
await page.click('.vessel-marker')
await sleep(1500)
await page.evaluate(() => {
  const btn = [...document.querySelectorAll('button')].find((b) => b.textContent.includes('查看轨迹'))
  if (btn) btn.click()
})
await sleep(4000)
await page.click('.play-button')
await measure('OLD play-1x selected+track 6s', 6000)
await page.click('.play-button')

await browser.close()
writeFileSync('result-old.json', JSON.stringify(results, null, 2))
console.log('written to result-old.json')
