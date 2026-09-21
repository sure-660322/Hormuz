// 纯环境对照：about:blank 与简单静态页，验证 ~1Hz 长任务是否来自 Chrome headless 自身
import puppeteer from 'puppeteer-core'

const CHROME = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

const browser = await puppeteer.launch({
  executablePath: CHROME,
  headless: true,
  args: ['--no-sandbox', '--window-size=1600,900'],
})

for (const [label, url] of [['blank', 'about:blank'], ['static', 'http://localhost:5174/favicon.svg']]) {
  const page = await browser.newPage()
  await page.setViewport({ width: 1600, height: 900 })
  await page.evaluateOnNewDocument(() => {
    const w = window
    w.__longtasks = []
    new PerformanceObserver((list) => {
      for (const entry of list.getEntries()) w.__longtasks.push(entry.duration)
    }).observe({ entryTypes: ['longtask'] })
  })
  await page.goto(url, { waitUntil: 'domcontentloaded' }).catch(() => {})
  await sleep(2000)
  await page.evaluate(() => { window.__longtasks.length = 0 })
  await sleep(8000)
  const s = await page.evaluate(() => {
    const d = [...window.__longtasks].sort((a, b) => a - b)
    return { count: d.length, medianMs: d.length ? d[Math.floor(d.length / 2)] : 0, maxMs: d.length ? d[d.length - 1] : 0 }
  })
  console.log(label, JSON.stringify(s))
  await page.close()
}
await browser.close()
