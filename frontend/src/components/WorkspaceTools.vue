<script setup lang="ts">
import type { ApiMapShip, ApiEvent } from '../api'
import type { AreaResult, GeoPoint, LayerState } from '../domain/maritime'
import { formatTime } from '../domain/maritime'
defineProps<{
  panel: 'layers' | 'analysis'
  center: GeoPoint | null
  result: AreaResult | null
  viewShips: ApiMapShip[]
  viewEventCount: number
  time: string | null
  picking: boolean
  harbourStatus: string
  countryStatus: string
  loading: boolean
  error: string
}>()
const layers = defineModel<LayerState>('layers', { required: true })
const radius = defineModel<number>('radius', { required: true })
const emit = defineEmits<{
  pick: []
  clear: []
  selectShip: [ship: ApiMapShip]
  selectEvent: [event: ApiEvent]
}>()
const layerOptions: {
  key: keyof LayerState
  label: string
  description: string
}[] = [
  { key: 'countries', label: '国界与中文国名', description: '伊朗与以色列橙红高亮 · 其他国家低饱和多色填充 · 随缩放显示中文国名' },
  {
    key: 'ships',
    label: '船舶当前位置',
    description: '随历史时间更新的模拟船位',
  },
  {
    key: 'tracks',
    label: '选中船舶轨迹',
    description: '在船舶详情中选择“查看轨迹”',
  },
  {
    key: 'events',
    label: '海事事件',
    description: '符合筛选且有代表点的新闻事件，不随船位回放过滤',
  },
  {
    key: 'seamarks',
    label: '航标与海事参考',
    description: 'OpenSeaMap 在线海事图层',
  },
  { key: 'harbours', label: '港口', description: 'OpenSeaMap 在线港口服务' },
]
</script>
<template>
  <section class="panel-content">
    <template v-if="panel === 'layers'">
      <header class="panel-heading">
        <h2>地图图层</h2>
        <p>控制地图信息，保持分析焦点。</p>
      </header>
      <h3 class="group-label">业务与参考图层</h3>
      <label v-for="item in layerOptions" :key="item.key" class="layer-row"
        ><input
          type="checkbox"
          :aria-label="item.label"
          :checked="layers[item.key]"
          @change="
            layers = {
              ...layers,
              [item.key]: ($event.target as HTMLInputElement).checked,
            }
          "
        /><span
          ><strong>{{ item.label }}</strong
          ><small>{{ item.description }}</small
          ><small v-if="item.key === 'countries' && layers.countries" role="status">{{ countryStatus }}</small>
          <small
            v-if="item.key === 'harbours' && layers.harbours"
            role="status"
            >{{ harbourStatus }}</small
          ></span
        ></label
      >
      <p class="caption layer-note">
        单船隔离时，事件和港口临时隐藏；恢复全部后沿用这里的设置。
      </p>
      <h3 class="group-label">待接入数据</h3>
      <div
        v-for="name in ['航道边界', '风险区域', 'AIS 密度']"
        :key="name"
        class="layer-row unavailable"
      >
        <input type="checkbox" disabled :aria-label="name + '尚未接入'" /><span
          ><strong>{{ name }}</strong
          ><small>尚未接入 · 无可用数据</small></span
        >
      </div>
      <div class="detail-section">
        <h3>底图来源</h3>
        <p class="caption">
          OpenStreetMap / OpenSeaMap<br />在线参考地图不等同于官方航海图；模拟业务图层不代表真实航运态势。
        </p>
      </div>
    </template>
    <template v-else>
      <header class="panel-heading">
        <h2>区域分析</h2>
        <p>观察当前快照中的空间分布。</p>
      </header>
      <div class="detail-section">
        <div class="section-title">
          <h3>当前视野</h3>
          <span>{{ formatTime(time) }}</span>
        </div>
        <p class="analysis-total">
          <strong>{{ viewShips.length }}</strong> 艘船舶
          <strong>{{ viewEventCount }}</strong> 条新闻事件（独立历史资料）
        </p>
        <p class="caption">统计当前视野内全部快照数据，不受图层显隐影响。</p>
      </div>
      <div class="detail-section">
        <h3>圆形半径查询</h3>
        <p class="caption">
          在地图上选择中心，按当前回放时刻计算范围内的模拟船舶。新闻事件空间查询尚未适配。
        </p>
        <label class="radius-control"
          >半径
          <input
            v-model.number="radius"
            type="range"
            min="1"
            max="50"
            step="1"
            aria-label="分析半径"
          /><output>{{ radius }} NM</output></label
        >
        <div class="ship-actions">
          <button
            class="primary"
            :disabled="loading || !!error"
            @click="emit('pick')"
          >
            {{
              picking
                ? '取消选点'
                : center
                  ? '重新选择中心'
                  : '在地图上选择中心'
            }}</button
          ><button v-if="center" @click="emit('clear')">清除区域</button>
        </div>
        <p v-if="center" class="caption">
          中心 {{ center.latitude.toFixed(4) }}° N /
          {{ center.longitude.toFixed(4) }}° E
        </p>
        <p v-if="loading || error" class="empty">
          {{ error || '等待模拟快照加载…' }}
        </p>
      </div>
      <section v-if="result && !error && !loading" class="detail-section">
        <div class="section-title">
          <h3>范围内结果</h3>
          <span>{{ radius }} NM</span>
        </div>
        <p class="analysis-total">
          模拟船舶 <strong>{{ result.ships.length }}</strong>
        </p>
        <p class="caption">
          本地模拟快照计算 · 非后端空间查询<br />新闻事件未参与半径统计。
        </p>
        <p v-if="!result.ships.length && !result.events.length" class="empty">
          范围内暂无模拟船舶。可扩大半径或更换时间。
        </p>
        <button
          v-for="ship in result.ships"
          :key="ship.id"
          class="context-result"
          @click="emit('selectShip', ship)"
        >
          <strong
            >{{ ship.name }}<span>{{ ship.speed.toFixed(1) }} kn</span></strong
          ><small>MMSI {{ ship.mmsi }}</small></button
        ><button
          v-for="event in result.events"
          :key="event.id"
          class="context-result"
          @click="emit('selectEvent', event)"
        >
          <strong>{{ event.title }}</strong
          ><small>{{ formatTime(event.occurred_at) }}</small>
        </button>
      </section>
      <details class="future-capability">
        <summary>前后时段对比 <span>规划中</span></summary>
        <p>
          后续以同一空间范围比较两个时段的船位与航速。当前只有单日模拟回放，尚未实现双地图、密度或通航量对比。
        </p>
      </details>
    </template>
  </section>
</template>
