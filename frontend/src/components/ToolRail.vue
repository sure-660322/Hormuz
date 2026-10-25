<script setup lang="ts">
defineProps<{
  layersActive: boolean
  agentActive: boolean
  areaActive: boolean
  passageActive: boolean
}>()
defineEmits<{
  'open-layers': []
  'open-agent': []
  'open-area': []
  'open-passage': []
}>()
</script>

<template>
  <nav class="tool-rail" aria-label="地图工具栏">
    <button
      type="button"
      :class="{ active: layersActive }"
      title="图层"
      aria-label="图层"
      @click="$emit('open-layers')"
    >
      <img src="/icons/layers.png" alt="" width="20" height="20" aria-hidden="true" />
      <span>图层</span>
    </button>
    <button
      type="button"
      :class="{ active: areaActive }"
      title="区域分析"
      aria-label="区域分析"
      data-testid="tool-area"
      @click="$emit('open-area')"
    >
      <img src="/icons/area-query.png" alt="" width="20" height="20" aria-hidden="true" />
      <span>区域</span>
    </button>
    <button type="button" :class="{ active: passageActive }" title="通行分析" aria-label="通行分析" data-testid="tool-passage" @click="$emit('open-passage')">
      <img src="/icons/passage-analysis.png" alt="" width="20" height="20" aria-hidden="true" />
      <span>通行</span>
    </button>
    <button
      type="button"
      :class="{ active: agentActive }"
      title="智能体"
      aria-label="智能体"
      @click="$emit('open-agent')"
    >
      <img src="/icons/agent.png" alt="" width="20" height="20" aria-hidden="true" />
      <span>智能体</span>
    </button>
  </nav>
</template>
