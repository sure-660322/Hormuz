<script setup lang="ts">
import type { LayerState } from '../domain/maritime'
defineProps<{
  harbourStatus: string
  countryStatus: string
  effectiveVector: number
  realAis: boolean
}>()
const layers = defineModel<LayerState>('layers', { required: true })
const vectorMinutes = defineModel<number>('vectorMinutes', { required: true })
const vectorLinked = defineModel<boolean>('vectorLinked', { required: true })
const emit = defineEmits<{
  close: []
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
    description: '随回放时间更新的船位',
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
  {
    key: 'dwell',
    label: '停留识别（锚泊/漂航/慢速）',
    description: 'MobilityDB 派生层：低速区间的识别结果，需结合数据来源核验',
  },
  {
    key: 'encounters',
    label: '相遇分析',
    description: 'MobilityDB 派生层：船舶对时空邻近，接近不等于有交互',
  },
]
</script>
<template>
  <section class="layers-popover" role="dialog" aria-label="地图图层">
    <header class="popover-head">
      <h2>图层</h2>
      <button aria-label="关闭图层面板" @click="emit('close')">×</button>
    </header>
    <div class="popover-body">
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
      <h3 class="group-label">显示设置</h3>
      <div class="popover-settings">
        <label>速度矢量 <select v-model.number="vectorMinutes"><option :value="3">3 分钟</option><option :value="6">6 分钟</option><option :value="12">12 分钟</option></select></label>
        <label><input type="checkbox" v-model="vectorLinked" /> 随回放倍率调整（当前 {{ effectiveVector }} 分钟）</label>
        <p class="caption">实线为有效船首向；虚线为 COG/SOG 等速外推。无 ROT 与船体尺寸数据，不绘制转向旗和真尺度轮廓。{{ realAis ? '单船轨迹按时间桶抽稀；速度着色使用采样报位的航速，报位点开关只显示采样点。' : '速度着色默认与当前显示的轨迹同范围，可在船舶调查面板切换为仅最近 24 小时。' }}</p>
      </div>
      <div class="detail-section">
        <h3>底图来源</h3>
        <p class="caption">
          OpenStreetMap / OpenSeaMap<br />在线参考地图不等同于官方航海图；业务图层不用于航行决策。
        </p>
      </div>
    </div>
  </section>
</template>
