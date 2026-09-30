<script setup lang="ts">
import type { ApiMaritimeCase } from '../api'
defineProps<{ data: ApiMaritimeCase | null; activeStage: string; loading: boolean; error: string; active: boolean }>()
defineEmits<{ select: [id: string]; close: []; retry: []; exit: [] }>()
</script>

<template>
  <aside class="case-panel" aria-label="中海北冰洋过航案例">
    <header><div><small>典型案例 · 2026年3月27—31日</small><h2>中海北冰洋</h2><p>两次过航尝试</p></div><button @click="$emit('close')" aria-label="关闭案例面板">×</button></header>
    <p v-if="loading" role="status">正在读取案例…</p>
    <p v-if="error" role="alert">{{ error }} <button @click="$emit('retry')">重试</button></p>
    <template v-if="data">
      <p class="case-identity">MMSI {{ data.mmsi }}<br>IMO {{ data.imo }} · {{ data.supplier }}</p>
      <p v-if="!data.ready" role="status">轨迹尚未导入。可先查看报道，导入后点击阶段进入回放。</p>
      <p v-else class="case-coverage">独立单船窗口 · {{ data.position_count.toLocaleString() }} 条报位</p>
      <ol>
        <li v-for="stage in data.stages" :key="stage.id" :class="{ selected: activeStage === stage.id }">
          <button class="case-stage-button" :aria-pressed="activeStage === stage.id" @click="$emit('select', stage.id)"><time>{{ stage.id === 'waiting' ? '2026-03-28—29' : stage.date }}</time><strong>{{ stage.title }}</strong><span>{{ data.ready ? '查看阶段轨迹' : '查看报道' }}</span></button>
          <div v-if="activeStage === stage.id" class="case-stage-detail">
            <p>{{ stage.summary }}</p>
            <a v-for="article in stage.articles" :key="article.url" :href="article.url" target="_blank" rel="noopener noreferrer"><strong>{{ article.title }}</strong><small>{{ article.media }} · 发布于 {{ article.publish_date }}</small></a>
          </div>
        </li>
      </ol>
      <details><summary>数据范围与证据说明</summary><p v-for="note in data.limitations" :key="note">{{ note }}</p></details>
      <button class="case-exit" @click="$emit('exit')">退出案例，恢复原态势</button>
    </template>
  </aside>
</template>

<style scoped>
.case-panel{position:absolute;left:18px;top:14px;bottom:18px;width:340px;max-width:calc(100vw - 36px);z-index:650;background:var(--panel);color:var(--ink);border:1px solid var(--line);border-radius:12px;overflow:auto;padding:18px;box-shadow:var(--shadow-overlay)}
header{display:flex;justify-content:space-between;align-items:flex-start}header small,.case-identity,.case-coverage{color:#9cb6c8;font-size:12px;line-height:1.7}h2{font-size:24px;margin:7px 0 3px}header p{margin:0}button{cursor:pointer;color:inherit;background:transparent;border:0}header button{font-size:24px}ol{list-style:none;padding:0;margin:20px 0}li{border-left:2px solid #486170;padding:0 0 10px 14px}li.selected{border-color:#51c2cb}.case-stage-button{text-align:left;display:grid;gap:5px;width:100%;padding:10px 0}.case-stage-button time,.case-stage-button span{font-size:12px;color:#9cb6c8}.case-stage-button strong{font-size:15px}.case-stage-detail p,details p{font-size:13px;line-height:1.7}.case-stage-detail a{display:block;color:#8cd9ee;padding:10px 0;text-decoration:none;border-bottom:1px solid #486170}.case-stage-detail a strong{font-size:13px;line-height:1.5;display:block}.case-stage-detail a small{display:block;margin-top:5px;color:#9cb6c8;font-size:11px}summary{cursor:pointer;font-size:13px}.case-exit{margin-top:16px;padding:10px;border:1px solid #567083;border-radius:6px;width:100%}button:focus-visible,a:focus-visible,summary:focus-visible{outline:2px solid #51c2cb;outline-offset:3px}@media(max-width:700px){.case-panel{left:64px;width:285px;bottom:125px}}
</style>
