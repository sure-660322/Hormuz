// 每日油轮观测通行统计（UTC 归日），单位：次/日。
// 来源: docs/daily_tanker_passages_2026-09-30.md（本机 aisdb 只读统计，独立 SQL 复核一致，2026-09-30）。
// 口径：query_strait_passages 虚拟门线（56.2°E–56.7°E 侧别变化）观测，非官方航道或目的港判断；
// 2026-02-24 与 2026-03-03 为部分日窗（UTC 16:00 边界），03-03 的 0 表示“无确定通行”，不证明实际零通行。
export interface TankerPassageDay {
  /** ISO 日期（UTC 归日） */
  date: string
  /** 当日确定通行次数 */
  passages: number
  inbound: number
  outbound: number
}

export const tankerPassagesUtc: TankerPassageDay[] = [
  { date: '2026-02-24', passages: 16, inbound: 13, outbound: 3 },
  { date: '2026-02-25', passages: 53, inbound: 24, outbound: 29 },
  { date: '2026-02-26', passages: 68, inbound: 46, outbound: 22 },
  { date: '2026-02-27', passages: 65, inbound: 32, outbound: 33 },
  { date: '2026-02-28', passages: 43, inbound: 17, outbound: 26 },
  { date: '2026-03-01', passages: 7, inbound: 0, outbound: 7 },
  { date: '2026-03-02', passages: 1, inbound: 0, outbound: 1 },
  { date: '2026-03-03', passages: 0, inbound: 0, outbound: 0 },
]
