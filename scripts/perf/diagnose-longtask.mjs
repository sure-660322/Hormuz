// longtask 归因对照实验：
// 1) 静止对照（页面加载后不动，测环境噪音：瓦片解码/CSS 滤镜）
// 2) light 主题播放对照（去掉 dark-map 滤镜）
// 3) 记录 longtask attribution
import puppeteer from 'puppeteer-core'

const CHROME = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

const browser = await puppeteer.launch({
  executablePath: CHROME,
  headless: true,
  args: ['--no-sandbox', '--disable-background-timer-throttling', '--disable-renderer-backgrounding', '--window-size=1600,900'],
})

async function newInstrumentedPage(url) {
  const page = await browser.newPage()
  await page.setViewport({ width: 1600, height: 900 })
  await page.evaluateOnNewDocument(() => {
    const w = window
    w.__longtasks = []
    new PerformanceObserver((list) => {
      for (const entry of list.getEntries()) {
        w.__longtasks.push({
          start: entry.startTime,
          duration: entry.duration,
          attribution: entry.attribution?.map((a) => ({
            containerType: a.containerType,
            containerName: a.containerName,
            containerSrc: a.containerSrc?.slice(0, 80),
          })) ?? [],
        })
      }
    }).observe({ entryTypes: ['longtask'] })
  })
  await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 60000 })
  await page.waitForFunction(
    () => document.querySelectorAll('.vessel-marker').length > 0 && !document.querySelector('.map-data-status'),
    { timeout: 120000 },
  )
  return page
}

async function measure(page, label, idleMs) {
  await page.evaluate(() => { window.__longtasks.length = 0 })
  await sleep(idleMs)
  const stats = await page.evaluate(() => {
    const durs = window.__longtasks.map((t) => t.duration).sort((a, b) => a - b)
    const byContainer = {}
    for (const t of window.__longtasks) {
      const key = t.attribution?.length ? `${t.attribution[0].containerType}:${t.attribution[0].containerName || t.attribution[0].containerSrc || '?'}` : 'unknown'
      byContainer[key] = (byContainer[key] ?? 0) + 1
    }
    return {
      count: durs.length,
      medianMs: durs.length ? durs[Math.floor(durs.length / 2)] : 0,
      maxMs: durs.length ? durs[durs.length - 1] : 0,
      byContainer,
      samples: window.__longtasks.slice(0, 5),
    }
  })
  console.log(label, JSON.stringify(stats, null, 1))
  return stats
}

// A. 深色主题 + 静止 8s（瓦片仍在加载/解码）
const p1 = await newInstrumentedPage('http://localhost:5174/')
await sleep(2000)
await measure(p1, 'A.dark-idle-8s', 8000)

// B. 深色主题 + 播放 6s
await measure(p1, 'B.dark-play-6s', 1000)
await p1.click('.play-button')
await measure(p1, 'B.dark-play-6s-active', 6000)
await p1.click('.play-button')

// C. 浅色主题 + 播放 6s
await p1.evaluate(() => {
  const btn = [...document.querySelectorAll('button')].find((b) => b.textContent === '浅色')
  btn?.click()
})
await sleep(1500)
await p1.click('.play-button')
await measure(p1, 'C.light-play-6s', 6000)
await p1.click('.play-button')

// D. 浅色 + 静止 8s
await measure(p1, 'D.light-idle-8s', 8000)
await p1.close()

// E. 深色 + 关闭底图滤镜变量？无法直接关；改测：深色但地图移出视野不可行。
// 改为：深色 + 播放 + 隐藏 marker-pane（验证 DOM 更新归因）
const p2 = await newInstrumentedPage('http://localhost:5174/')
await sleep(2000)
await p2.click('.play-button')
await measure(p2, 'E.dark-play-baseline', 6000)
await p2.click('.play-button')
await p2.close()

await browser.close()
