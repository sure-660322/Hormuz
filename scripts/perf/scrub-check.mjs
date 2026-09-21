import puppeteer from 'puppeteer-core'
const CHROME = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
const browser = await puppeteer.launch({ executablePath: CHROME, headless: true, args: ['--no-sandbox', '--disable-background-timer-throttling'] })
const page = await browser.newPage()
await page.setViewport({ width: 1600, height: 900 })
await page.evaluateOnNewDocument(() => {
  const w = window
  w.__longtasks = []
  new PerformanceObserver((list) => {
    for (const entry of list.getEntries()) w.__longtasks.push({ start: entry.startTime, dur: entry.duration })
  }).observe({ entryTypes: ['longtask'] })
})
await page.goto('http://localhost:5174/', { waitUntil: 'domcontentloaded', timeout: 60000 })
await page.waitForFunction(() => document.querySelectorAll('.vessel-marker').length > 0 && !document.querySelector('.map-data-status'), { timeout: 120000 })
await sleep(1000)
const r = await page.evaluate(async () => {
  const t0 = performance.now()
  const slider = document.querySelector('#replay-time')
  const max = Number(slider.max)
  window.__longtasks.length = 0
  for (let i = 0; i < 20; i++) {
    slider.value = String(Math.floor(Math.random() * max))
    slider.dispatchEvent(new Event('input', { bubbles: true }))
    await new Promise((r2) => setTimeout(r2, 5))
  }
  const loopMs = performance.now() - t0
  await new Promise((r2) => setTimeout(r2, 500))
  const lt = window.__longtasks
  return {
    loopMs,
    longtaskCount: lt.length,
    durs: lt.map((t) => Math.round(t.dur)),
    sliderNow: slider.value,
  }
})
console.log(JSON.stringify(r, null, 1))
await browser.close()
