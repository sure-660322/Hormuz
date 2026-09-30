// EIA Europe Brent Spot Price FOB（日度，美元/桶）。
// 来源: https://www.eia.gov/dnav/pet/hist/RBRTED.htm
// 数值于 2026-09-30 对照 EIA 页面核对；范围取 AIS 回放窗口（见 AIS_WINDOW）前后各一周。
export const BRENT_SOURCE_URL = 'https://www.eia.gov/dnav/pet/hist/RBRTED.htm'

export interface BrentDailyPrice {
  /** ISO 日期（交易日） */
  date: string
  /** 美元/桶 */
  price: number
}

// 2026-02-18 至 2026-03-10，仅含交易日（周末无现货报价）。
export const brentDailyPrices: BrentDailyPrice[] = [
  { date: '2026-02-18', price: 71.78 },
  { date: '2026-02-19', price: 73.17 },
  { date: '2026-02-20', price: 72.75 },
  { date: '2026-02-23', price: 71.9 },
  { date: '2026-02-24', price: 71.21 },
  { date: '2026-02-25', price: 70.69 },
  { date: '2026-02-26', price: 71.66 },
  { date: '2026-02-27', price: 71.32 },
  { date: '2026-03-02', price: 77.24 },
  { date: '2026-03-03', price: 83.28 },
  { date: '2026-03-04', price: 81.56 },
  { date: '2026-03-05', price: 88.59 },
  { date: '2026-03-06', price: 95.74 },
  { date: '2026-03-09', price: 94.35 },
  { date: '2026-03-10', price: 89.84 },
]

/** 库内真实 AIS 回放窗口（态势总览地图数据范围）。 */
export const AIS_WINDOW = { start: '2026-02-25', end: '2026-03-03' }
