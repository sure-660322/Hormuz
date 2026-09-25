<script setup lang="ts">
import type { ApiMapShip, ApiEvent } from '../api'
import type { AreaResult, GeoPoint } from '../domain/maritime'
import { formatTime } from '../domain/maritime'
defineProps<{
  center: GeoPoint | null
  result: AreaResult | null
  viewShips: ApiMapShip[]
  viewEventCount: number
  time: string | null
  picking: boolean
  loading: boolean
  error: string
}>()
const radius = defineModel<number>('radius', { required: true })
const emit = defineEmits<{
  pick: []
  clear: []
  selectShip: [ship: ApiMapShip]
  selectEvent: [event: ApiEvent]
}>()
</script>
<template>
  <section class="panel-content">
    <header class="panel-heading">
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
        在地图上选择中心，按当前回放时刻计算范围内的船舶。新闻事件空间查询尚未适配。
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
        {{ error || '等待船位快照加载…' }}
      </p>
    </div>
    <section v-if="result && !error && !loading" class="detail-section">
      <div class="section-title">
        <h3>范围内结果</h3>
        <span>{{ radius }} NM</span>
      </div>
      <p class="analysis-total">
        船舶 <strong>{{ result.ships.length }}</strong>
      </p>
      <p class="caption">
        本地船位快照计算 · 非后端空间查询<br />新闻事件未参与半径统计。
      </p>
      <p v-if="!result.ships.length && !result.events.length" class="empty">
        范围内暂无船舶。可扩大半径或更换时间。
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
        后续以同一空间范围比较两个时段的船位与航速；双地图、密度或通航量对比尚未实现。
      </p>
    </details>
  </section>
</template>
