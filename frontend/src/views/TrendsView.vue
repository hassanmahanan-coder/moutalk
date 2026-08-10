<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'
import * as echarts from 'echarts'
import { reportApi } from '../api'

const chartEl = ref(null)
const loading = ref(true)
const insufficient = ref(false)
let chart = null

function render(points) {
  if (!chartEl.value) return
  if (!chart) chart = echarts.init(chartEl.value)
  chart.setOption({
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis' },
    legend: { data: ['总分', '客观分', '主观分'], textStyle: { color: '#8b918f' } },
    grid: { left: 48, right: 24, top: 48, bottom: 36 },
    xAxis: {
      type: 'category',
      name: '月份',
      nameTextStyle: { color: '#8b918f' },
      data: points.map((p) => p.month),
      axisLine: { lineStyle: { color: '#26375a' } },
      axisLabel: { color: '#8b918f' },
    },
    yAxis: {
      type: 'value',
      name: '得分',
      min: 0,
      max: 1,
      nameTextStyle: { color: '#8b918f' },
      splitLine: { lineStyle: { color: 'rgba(38,55,90,0.5)' } },
      axisLabel: { color: '#8b918f' },
    },
    series: [
      { name: '总分', type: 'line', smooth: true, data: points.map((p) => p.total), lineStyle: { color: '#c9a86a', width: 2 }, itemStyle: { color: '#c9a86a' } },
      { name: '客观分', type: 'line', smooth: true, data: points.map((p) => p.objective), lineStyle: { color: '#6fae93', width: 2 }, itemStyle: { color: '#6fae93' } },
      { name: '主观分', type: 'line', smooth: true, data: points.map((p) => p.subjective), lineStyle: { color: '#5b7fb8', width: 2 }, itemStyle: { color: '#5b7fb8' } },
    ],
  })
}

function onResize() {
  chart?.resize()
}

onMounted(async () => {
  window.addEventListener('resize', onResize)
  try {
    const data = await reportApi.trends()
    insufficient.value = data.insufficient
    if (!data.insufficient) render(data.points)
  } catch {
    /* 拦截器已提示 */
  } finally {
    loading.value = false
  }
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', onResize)
  chart?.dispose()
})
</script>

<template>
  <div class="trends">
    <div class="head">
      <p class="kicker">Progress</p>
      <h1>进步曲线</h1>
      <p class="sub">每月总分与双轨得分走势 · 免费席可见近 3 个月，Pro 可见全部</p>
    </div>
    <hr class="gold-rule" />

    <div v-if="loading" class="empty">加载中……</div>
    <div v-else-if="insufficient" class="empty">
      <p class="empty-title">谈判样本不足</p>
      <p>完成至少 2 局谈判后，这里将呈现你的进步轨迹。</p>
      <router-link to="/" class="go">去开局</router-link>
    </div>
    <div v-else class="chart-wrap">
      <div ref="chartEl" class="chart"></div>
    </div>
  </div>
</template>

<style scoped>
.trends {
  max-width: 920px;
  width: 100%;
  margin: 0 auto;
  padding: 52px 40px 60px;
}

.head {
  text-align: center;
  margin-bottom: 26px;
}

.kicker {
  margin: 0 0 8px;
  font-size: 11px;
  letter-spacing: 0.6em;
  color: var(--seal-bright);
}

.head h1 {
  margin: 0;
  font-size: 36px;
  letter-spacing: 0.5em;
  text-indent: 0.5em;
}

.head .sub {
  margin: 10px 0 0;
  font-size: 13px;
  letter-spacing: 0.24em;
  color: var(--paper-faint);
}

.chart-wrap {
  background: rgba(13, 22, 38, 0.6);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 24px;
}

.chart {
  height: 380px;
}

.empty {
  padding: 80px 20px;
  text-align: center;
  border: 1px dashed var(--ink-600);
  border-radius: 6px;
}

.empty-title {
  font-family: var(--font-display);
  font-size: 17px;
  letter-spacing: 0.3em;
  color: var(--gold);
  margin: 0 0 12px;
}

.empty p:not(.empty-title) {
  font-size: 13px;
  color: var(--paper-faint);
  margin: 0 0 18px;
}

.go {
  font-size: 13px;
  letter-spacing: 0.2em;
  color: var(--seal-bright);
  border: 1px solid var(--seal);
  border-radius: 3px;
  padding: 8px 22px;
  transition: all 0.2s;
}

.go:hover {
  color: var(--paper);
  background: rgba(111, 174, 147, 0.08);
}
</style>
