import puppeteer from 'puppeteer-core'
const CHROME = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'
const browser = await puppeteer.launch({ executablePath: CHROME, headless: true, args: ['--no-sandbox'] })
const page = await browser.newPage()
await page.goto('http://localhost:5174/', { waitUntil: 'domcontentloaded', timeout: 60000 })
await page.waitForFunction(() => document.querySelectorAll('.vessel-marker').length > 0 && !document.querySelector('.map-data-status'), { timeout: 120000 })
const check = await page.evaluate(() => ({
  hasRotor: Boolean(document.querySelector('g.vessel-rotor')),
  markerHtml: document.querySelector('.vessel-marker svg g')?.outerHTML?.slice(0, 120) ?? null,
}))
console.log(JSON.stringify(check, null, 1))
await browser.close()
