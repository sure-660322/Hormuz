// 决定性对照：拦截所有瓦片请求（无底图），测量回放渲染的 longtask。
// 若 longtask 消失，则此前观察到的 ~400ms 任务是瓦片下载/解码/滤镜合成的环境噪音。
import puppeteer from 'puppeteer-core'

const CHROME = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

const browser = await puppeteer.launch({
  executablePath: CHROME,
  headless: true,
  args: ['--no-sandbox', '--disable-background-timer-throttling', '--disable-renderer-backgrounding', '--window-size=1600,900'],
})
const page = await browser.newPage()
await page.setViewport({ width: 1600, height: 900 })
let tileRequests = 0
await page.setRequestInterception(true)
page.on('request', (req) => {
  const url = req.url()
  if (/tile\.openstreetmap\.org|openseamap\.org/.test(url)) {
    tileRequests++
    req.abort()
  } else req.continue()
})
await page.evaluateOnNewDocument(() => {
  const w = window
  w.__longtasks = []
  new PerformanceObserver((list) => {
    for (const entry of list.getEntries()) w.__longtasks.push(entry.duration)
  }).observe({ entryTypes: ['longtask'] })
})
await page.goto('http://localhost:5174/?perf=1', { waitUntil: 'domcontentloaded', timeout: 60000 })
await page.waitForFunction(
  () => document.querySelectorAll('.vessel-marker').length > 0 && !document.querySelector('.map-data-status'),
  { timeout: 120000 },
)

async function measure(label, ms) {
  await page.evaluate(() => { window.__longtasks.length = 0 })
  await sleep(ms)
  const s = await page.evaluate(() => {
    const d = [...window.__longtasks].sort((a, b) => a - b)
    return {
      count: d.length,
      medianMs: d.length ? d[Math.floor(d.length / 2)] : 0,
      maxMs: d.length ? d[d.length - 1] : 0,
      probe: window.__hormuzPerf?.stats() ?? null,
    }
  })
  console.log(label, JSON.stringify(s))
}

// 等瓦片请求全部结束（都被 abort），消除加载期影响
await sleep(3000)
console.log('tileRequests(aborted):', tileRequests)

await page.click('.play-button')
await measure('NO-TILES play-1x 6s', 6000)
await page.click('.play-button')

await page.evaluate(async () => {
  const slider = document.querySelector('#replay-time')
  const max = Number(slider.max)
  for (let i = 0; i < 150; i++) {
    slider.value = String(Math.floor(Math.random() * max))
    slider.dispatchEvent(new Event('input', { bubbles: true }))
    await new Promise((r) => setTimeout(r, 8))
  }
})
await measure('NO-TILES fast-scrub 1.2s-after', 1200)
await browser.close()
