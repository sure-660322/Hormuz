<script setup lang="ts">
defineProps<{
  layersActive: boolean
  agentActive: boolean
}>()
defineEmits<{
  'open-layers': []
  'open-agent': []
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
