<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import type { ApiMapShip, ApiShipPosition, ApiEvent, ApiTrackWindow } from '../api'
import { formatTime, shipType, eventKind, shipShape, shipStatus, sampleAge, zoneLabel } from '../domain/maritime'
const props = defineProps<{
  ship: ApiMapShip | null
  ships: ApiMapShip[]
  track: ApiShipPosition[]
  trackVisible: boolean
  trackAvailable: boolean
  realAis: boolean
  realTrack: ApiTrackWindow | null
  realTrackLoading: boolean
  realTrackError: string
  realTrackHours: 1 | 6 | 24
  realPointsVisible: boolean
  trackRecent24h: boolean
  speedColor: boolean
  speedColorRecent24h: boolean
  isolated: boolean
  nearbyEvents: (ApiEvent & { distance: number })[]
  eventsError: string
  eventsLoading: boolean
  time: string | null
}>()
const emit = defineEmits<{
  select: [ship: ApiMapShip]
  clear: []
  track: []
  'speed-color': []
  'real-points': []
  'update:speedColorRecent24h': [value: boolean]
  'update:trackRecent24h': [value: boolean]
  'update:realTrackHours': [value: 1 | 6 | 24]
  isolate: []
  event: [event: ApiEvent]
  locate: []
}>()
const section = ref<'track' | 'events' | 'news'>('track')
const compact = ref(true)
const sortedShips = computed(() => [...props.ships].sort((a, b) => shipStatus(b, props.time).rank - shipStatus(a, props.time).rank || (a.name ?? a.mmsi).localeCompare(b.name ?? b.mmsi, 'zh-CN')))
const directoryLimit = ref(100)
const panel = ref<HTMLElement | null>(null)
watch(
  () => props.ship?.id,
  async () => {
    section.value = 'track'
    await nextTick()
    if (panel.value) panel.value.scrollTop = 0
  },
)
const peak = computed(() => Math.max(1, ...props.track.map((p) => p.speed)))
const average = computed(() =>
  props.track.length
    ? (
        props.track.reduce((s, p) => s + p.speed, 0) / props.track.length
      ).toFixed(1)
    : '—',
)
const points = computed(() => {
  const start = Date.parse(props.track[0]?.recorded_at ?? ''),
    end = Date.parse(props.track.at(-1)?.recorded_at ?? '')
  return props.track
    .map(
      (p) =>
        `${30 + ((Date.parse(p.recorded_at) - start) / Math.max(1, end - start)) * 270},${100 - (p.speed / peak.value) * 70}`,
    )
    .join(' ')
})
</script>
<template>
  <section ref="panel" class="panel-content ship-inspector">
    <template v-if="ship">
      <header class="panel-heading">
        <div class="section-title">
          <span>船舶调查</span><button @click="emit('clear')">取消选中</button>
        </div>
        <h2>{{ ship.name ?? ship.mmsi }}</h2>
        <p>
          {{ shipType(ship.ship_type) }} <span>{{ ship.flag ?? '未提供' }}</span>
        </p>
      </header>
      <div class="vessel-readings">
        <div>
          <strong>{{ ship.speed.toFixed(1) }}<small>kn</small></strong
          ><span>当前航速</span>
        </div>
        <div>
          <strong
            >{{ ship.course.toFixed(0).padStart(3, '0')
            }}<small>°</small></strong
          ><span>对地航向</span>
        </div>
      </div>
      <dl class="facts identity">
        <div>
          <dt>MMSI</dt>
          <dd>{{ ship.mmsi }}</dd>
        </div>
        <div>
          <dt>IMO</dt>
          <dd>{{ ship.imo ?? '未提供' }}</dd>
        </div>
        <div>
          <dt>呼号</dt>
          <dd>{{ ship.callsign ?? '未提供' }}</dd>
        </div>
        <div>
          <dt>经纬度</dt>
          <dd>
            {{ ship.latitude.toFixed(4) }}° N<br />{{
              ship.longitude.toFixed(4)
            }}° E
          </dd>
        </div>
        <div>
          <dt>船首向</dt>
          <dd>
            {{
              ship.heading === null ? '未提供' : `${ship.heading.toFixed(0)}°`
            }}
          </dd>
        </div>
        <div>
          <dt>位置时间</dt>
          <dd>{{ formatTime(ship.recorded_at, true) }} {{ zoneLabel() }}<br />{{ sampleAge(ship, time).toFixed(0) }} 分钟前（相对回放）</dd>
        </div>
      </dl>
      <div class="ship-actions">
        <button
          v-if="trackAvailable"
          class="primary"
          :aria-pressed="trackVisible"
          @click="emit('track')"
        >
          {{ trackVisible ? '隐藏轨迹' : '查看轨迹' }}</button
        ><button v-if="trackAvailable" :aria-pressed="speedColor" @click="emit('speed-color')">
          {{ speedColor ? '关闭着色' : '速度着色' }}</button
        ><button v-if="realAis" :aria-pressed="realPointsVisible" @click="emit('real-points')">
          {{ realPointsVisible ? '隐藏报位点' : '显示报位点' }}</button
        ><button
          v-if="speedColor && !realAis"
          :aria-pressed="speedColorRecent24h"
          @click="emit('update:speedColorRecent24h', !speedColorRecent24h)"
        >
          {{ speedColorRecent24h ? '着色：全部范围' : '着色：仅最近 24h' }}</button
        ><button :aria-pressed="isolated" @click="emit('isolate')">
          {{ isolated ? '恢复全部' : '仅看此船' }}</button
        ><button @click="emit('locate')">定位</button>
      </div>
      <p v-if="speedColor" class="speed-legend">
        {{ realAis ? '抽稀轨迹按线段起点的实测航速着色，无速度插值：' : '派生层着色（数据库插值结果）：' }}<span style="color: #8a97a3">■</span> &lt;3 kn
        <span style="color: #2e9e5b">■</span> 3–8
        <span style="color: #e6a23c">■</span> 8–12
        <span style="color: #d64f4f">■</span> &gt;12 kn<span v-if="!realAis"> ·
        {{ speedColorRecent24h ? '仅回放时刻前 24 小时' : '范围与当前显示的轨迹一致' }}</span>
      </p>
      <nav class="detail-tabs" aria-label="船舶详情分类">
        <button
          :class="{ active: section === 'track' }"
          @click="section = 'track'"
        >
          航行记录</button
        ><button
          :class="{ active: section === 'events' }"
          @click="section = 'events'"
        >
          周边事件 {{ nearbyEvents.length }}</button
        ><button
          :class="{ active: section === 'news' }"
          @click="section = 'news'"
        >
          附近新闻
        </button>
      </nav>
      <section v-if="section === 'track'" class="detail-section">
        <p v-if="!trackAvailable" class="empty compact">当前为单时刻船位快照。单船轨迹将在下一阶段接入。</p>
        <div v-else-if="realAis" class="real-track-details">
          <div class="section-title"><h3>单船历史轨迹</h3><span>最长 24 小时</span></div>
          <div class="track-range" role="group" aria-label="轨迹时间范围">
            <button v-for="hours in ([1, 6, 24] as const)" :key="hours" :aria-pressed="realTrackHours === hours" @click="emit('update:realTrackHours', hours)">最近 {{ hours }} 小时</button>
          </div>
          <p v-if="realTrackLoading" class="caption" role="status">正在读取并抽稀该船报位…</p>
          <p v-else-if="realTrackError" class="empty compact" role="alert">{{ realTrackError }}</p>
          <template v-else-if="realTrack">
            <p class="caption">窗口内原始报位 {{ realTrack.source_count }} 条，地图采样 {{ realTrack.point_count }} 点、{{ realTrack.segments.length }} 段。相邻报位超过 {{ realTrack.gap_minutes }} 分钟即断开；各段首尾保留，段间不连线。</p>
            <p class="caption">“显示报位点”仅显示返回的采样点；线段着色使用起点报位的航速。原始报位仍保存在数据库中。</p>
            <p v-if="realTrack.gaps.length" class="track-note">发现 {{ realTrack.gaps.length }} 处断档，最长 {{ Math.max(...realTrack.gaps.map(g => g.minutes)).toFixed(1) }} 分钟。断档并不代表船舶停止航行。</p>
            <p v-if="!realTrack.source_count" class="empty compact">此时段没有该船报位，可调整时间轴或时间范围。</p>
          </template>
          <p v-else class="caption">点击“查看轨迹”后按所选时段加载。</p>
        </div>
        <template v-else>
        <div class="section-title">
          <h3>航速变化</h3>
          <span>{{ track.length }} 个采样</span>
        </div>
        <svg
          v-if="track.length > 1"
          class="speed-chart"
          viewBox="0 0 320 125"
          role="img"
          :aria-label="`截至当前时刻的航速曲线，平均 ${average} 节，最高 ${peak.toFixed(1)} 节`"
        >
          <path
            d="M30 30H300M30 65H300M30 100H300"
            stroke="#e0e5e8"
            fill="none"
          />
          <text x="0" y="34">{{ peak.toFixed(1) }}</text>
          <text x="8" y="104">0</text>
          <text x="30" y="120">{{ formatTime(track[0]?.recorded_at) }}</text>
          <text x="264" y="120">
            {{ formatTime(track.at(-1)?.recorded_at) }}
          </text>
          <polyline
            :points="points"
            fill="none"
            stroke="#386d99"
            stroke-width="2"
            stroke-linejoin="round"
          />
        </svg>
        <p v-else class="empty compact">向后移动时间轴，查看航速变化。</p>
        <p class="caption">
          平均 {{ average }} kn · 最高
          {{
            peak.toFixed(1)
          }}
          kn<br />仅统计已回放的船位采样，不推断异常或航行状态。
        </p>
        <p class="track-note">
          {{
            trackVisible
              ? trackRecent24h
                ? '地图仅显示回放时刻前 24 小时的轨迹。'
                : '地图已显示全部已航行轨迹。悬停采样点查看时间、位置与航速。'
              : '点击“查看轨迹”在地图上显示历史采样。'
          }}
        </p>
        <label v-if="trackVisible" class="track-scope"
          ><input
            type="checkbox"
            :checked="trackRecent24h"
            @change="emit('update:trackRecent24h', ($event.target as HTMLInputElement).checked)"
          />只看最近 24h 轨迹</label
        >
        <details class="sample-records"><summary>船位记录（{{ track.length }} 条）</summary><table><thead><tr><th>时间</th><th>纬度 / 经度</th><th>kn</th></tr></thead><tbody><tr v-for="p in [...track].reverse()" :key="p.id"><td>{{ formatTime(p.recorded_at) }}</td><td>{{ p.latitude.toFixed(3) }} / {{ p.longitude.toFixed(3) }}</td><td>{{ p.speed.toFixed(1) }}</td></tr></tbody></table></details>
        </template>
      </section>
      <section v-else-if="section === 'events'" class="detail-section">
        <h3>船舶事件关联</h3>
        <p class="caption">
          新闻事件与船舶身份需分别核验；时空接近不能证明真实关联。
        </p>
        <p v-if="eventsLoading || eventsError" class="empty">
          {{ eventsError || '正在加载事件…' }}
        </p>
        <p v-else-if="!nearbyEvents.length" class="empty">
          关联功能暂未适配，请在“事件”面板独立查看新闻。
        </p>
        <button
          v-for="event in nearbyEvents"
          :key="event.id"
          class="context-result"
          @click="emit('event', event)"
        >
          <strong
            >{{ eventKind(event.event_type).label }}
            <span>{{ event.distance.toFixed(1) }} NM</span></strong
          ><small
            >{{ formatTime(event.occurred_at) }} · {{ event.title }}</small
          >
        </button>
      </section>
      <section v-else class="detail-section empty">
        <h3>船舶新闻关联暂不可用</h3>
        <p v-if="!trackAvailable">当前仅展示历史 AIS 船位快照；尚未核验该船与报道的身份对应关系。</p>
        <p v-else>船舶与报道的身份对应关系尚未核验。</p>
        <p>已采集新闻可在事件详情中查看；船舶与新闻的身份和因果关系需独立核验。</p>
      </section>
    </template>
    <template v-else
      ><header class="panel-heading">
        <h2>船舶目录</h2>
        <p>按采样陈旧程度排序；暂无真实船舶风险评级。</p>
      </header>
      <div class="directory-toolbar"><span>{{ ships.length }} 艘船舶</span><button @click="compact = !compact" :aria-pressed="compact">{{ compact ? '紧凑' : '舒适' }}</button></div>
      <table class="ship-table" :class="{ compact }"><thead><tr><th>船舶 / MMSI</th><th>kn</th><th>采样</th></tr></thead><tbody>
        <tr v-for="item in sortedShips.slice(0, directoryLimit)" :key="item.id"><td><button @click="emit('select', item)" :aria-label="`查看 ${item.name ?? item.mmsi}`"><span class="status-dot" :style="{ background: shipStatus(item, time).color }" :title="shipStatus(item, time).label"></span><span class="ship-name">{{ shipShape(item.ship_type) }} {{ item.name ?? item.mmsi }}<small>{{ item.mmsi }}</small></span></button></td><td>{{ item.speed.toFixed(1) }}</td><td><span :title="shipStatus(item, time).label">{{ sampleAge(item, time).toFixed(0) }} 分前</span></td></tr>
      </tbody></table>
      <button v-if="directoryLimit < ships.length" class="overview-more" @click="directoryLimit += 100">再显示 100 艘（已显示 {{ Math.min(directoryLimit, ships.length) }} / {{ ships.length }}）</button>
      <p v-if="!ships.length" class="empty">
        当前时刻没有可用船位，请检查回放数据状态。
      </p></template
    >
  </section>
</template>
