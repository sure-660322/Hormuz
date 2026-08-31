<template>
  <section
    class="timeline-controls"
    aria-label="船舶轨迹回放时间轴"
  >
    <div class="timeline-toolbar">
      <button type="button" disabled>
        ▶ 播放
      </button>

      <span class="current-time">
        当前时间：尚未加载
      </span>

      <label class="speed-control">
        播放速度

        <select disabled>
          <option>0.5×</option>
          <option selected>1×</option>
          <option>2×</option>
          <option>4×</option>
        </select>
      </label>
    </div>

    <div class="slider-row">
      <span>开始</span>

      <input
        type="range"
        min="0"
        max="95"
        value="0"
        disabled
        aria-label="回放时间"
      >

      <span>结束</span>
    </div>
  </section>
</template>

<style scoped>
.timeline-controls {
  box-sizing: border-box;
  height: 96px;
  padding: 14px 20px;
  border-top: 1px solid #cbd5e1;
  background-color: #f8fafc;
  color: #0f172a;
}

.timeline-toolbar {
  display: flex;
  align-items: center;
  gap: 18px;
}

.timeline-toolbar button {
  padding: 8px 16px;
  border: 0;
  border-radius: 6px;
  background-color: #64748b;
  color: #ffffff;
  font: inherit;
  cursor: not-allowed;
}

.current-time {
  flex: 1;
  font-size: 14px;
  font-weight: 600;
}

.speed-control {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
}

.speed-control select {
  padding: 5px 8px;
}

.slider-row {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 12px;
  margin-top: 12px;
  color: #64748b;
  font-size: 12px;
}

.slider-row input {
  width: 100%;
}
</style>