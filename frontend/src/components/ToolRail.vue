<script setup lang="ts">
defineProps<{
  layersActive: boolean
  areaActive: boolean
  agentActive: boolean
}>()
defineEmits<{
  'open-layers': []
  'start-area': []
  share: []
  print: []
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
      <svg viewBox="0 0 18 18" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <path d="M9 2 16 6 9 10 2 6Z" />
        <path d="m2.8 9.3-0.8 0.5L9 13.8l7-4-0.8-0.5" />
        <path d="m2.8 12.3-0.8 0.5L9 16.8l7-4-0.8-0.5" />
      </svg>
    </button>
    <button
      type="button"
      :class="{ active: areaActive }"
      title="半径分析"
      aria-label="半径分析"
      @click="$emit('start-area')"
    >
      <svg viewBox="0 0 18 18" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <circle cx="9" cy="9" r="6.2" />
        <circle cx="9" cy="9" r="1" fill="currentColor" stroke="none" />
        <path d="M9 1.2v1.6M9 15.2v1.6M1.2 9h1.6M15.2 9h1.6" />
      </svg>
    </button>
    <button
      type="button"
      title="分享视图"
      aria-label="分享视图"
      @click="$emit('share')"
    >
      <svg viewBox="0 0 18 18" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <circle cx="4.5" cy="9" r="2.2" />
        <circle cx="13.5" cy="4.5" r="2.2" />
        <circle cx="13.5" cy="13.5" r="2.2" />
        <path d="m6.5 8 5.2-2.7M6.5 10l5.2 2.7" />
      </svg>
    </button>
    <button
      type="button"
      title="导出 PDF"
      aria-label="导出 PDF"
      @click="$emit('print')"
    >
      <svg viewBox="0 0 18 18" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <path d="M5.5 6.5v-4h7v4" />
        <rect x="2.5" y="6.5" width="13" height="5.5" rx="1.5" />
        <path d="M5.5 10h7v5.5h-7Z" />
        <path d="M7 13h4" />
      </svg>
    </button>
    <button
      type="button"
      :class="{ active: agentActive }"
      title="智能体"
      aria-label="智能体"
      @click="$emit('open-agent')"
    >
      <svg viewBox="0 0 18 18" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <rect x="2.5" y="3" width="13" height="9.5" rx="2" />
        <path d="M6 12.5v2.7l3.4-2.7" />
        <path d="M5.8 7.8h.01M9 7.8h.01M12.2 7.8h.01" />
      </svg>
    </button>
  </nav>
</template>
