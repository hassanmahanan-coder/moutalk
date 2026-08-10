<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'
import * as echarts from 'echarts'
import { adminApi } from '../api'

const stats = ref(null)
const tactics = ref({})
const tacticTotal = ref(0)
const online = ref(0)
const forbidden = ref(false)
const loading = ref(true)
const chartEl = ref(null)
let chart = null

const TACTIC_LABELS = {
  anchor: '锚定报价',
  concession_bait: '让步诱饵',
  urgency: '时间压迫',
  false_bottom: '虚假底线',
  divide_conquer: '分化瓦解',
  package_deal: '打包成交',
  silence: '沉默施压',
  good_cop_bad_cop: '红脸白脸',
  deadlock_break: '破局缓和',
  neutral: '中性',
}

async function load() {
  loading.value = true
  try {
    const [s, t, c] = await Promise.all([adminApi.stats(), adminApi.tacticStats(), adminApi.connections()])
    stats.value = s
    tactics.value = t.tactics || {}
    tacticTotal.value = t.total || 0
    online.value = c.online
    renderChart()
  } catch (e) {
    if (e?.code === 'FORBIDDEN' || e?.code === 'INVALID_CREDENTIALS') forbidden.value = true
  } finally {
    loading.value = false
  }
}

function renderChart() {
  if (!chartEl.value) return
  if (!chart) chart = echarts.init(chartEl.value)
  const entries = Object.entries(tactics.value).sort((a, b) => b[1] - a[1])
  chart.setOption({
    backgroundColor: 'transparent',
    grid: { left: 96, right: 32, top: 16, bottom: 28 },
    xAxis: { type: 'value', axisLabel: { color: '#8b918f' }, splitLine: { lineStyle: { color: 'rgba(38,55,90,0.5)' } } },
    yAxis: {
      type: 'category',
      data: entries.map(([k]) => TACTIC_LABELS[k] || k),
      axisLine: { lineStyle: { color: '#26375a' } },
      axisLabel: { color: '#8b918f' },
    },
    series: [
      {
        type: 'bar',
        data: entries.map(([, v]) => v),
        itemStyle: { color: '#c9a86a', borderRadius: [0, 3, 3, 0] },
        barWidth: 16,
      },
    ],
  })
}

function onResize() {
  chart?.resize()
}

onMounted(() => {
  window.addEventListener('resize', onResize)
  load()
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', onResize)
  chart?.dispose()
})
</script>

<template>
  <div class="admin">
    <div class="head">
      <p class="kicker">Console</p>
      <h1>管理后台</h1>
      <p class="sub">平台运营概览 · 仅管理员可见</p>
    </div>
    <hr class="gold-rule" />

    <div v-if="forbidden" class="empty">
      <p class="empty-title">无访问权限</p>
      <p>当前账号不是管理员。</p>
    </div>
    <div v-else-if="loading" class="empty">加载中……</div>
    <template v-else>
      <div class="kpis">
        <div class="kpi">
          <span class="num">{{ stats?.users_count ?? 0 }}</span>
          <span class="label">注册用户</span>
        </div>
        <div class="kpi">
          <span class="num">{{ stats?.sessions_count ?? 0 }}</span>
          <span class="label">谈判会话</span>
        </div>
        <div class="kpi">
          <span class="num">{{ stats?.reports_count ?? 0 }}</span>
          <span class="label">复盘报告</span>
        </div>
        <div class="kpi">
          <span class="num">{{ stats?.monthly_reports ?? 0 }}</span>
          <span class="label">本月报告</span>
        </div>
        <div class="kpi">
          <span class="num">{{ stats?.pro_users ?? 0 }}</span>
          <span class="label">Pro 用户</span>
        </div>
        <div class="kpi">
          <span class="num">{{ online }}</span>
          <span class="label">在线连接</span>
        </div>
      </div>

      <section class="panel-sec">
        <h2>战术命中分布 <span class="dim">共 {{ tacticTotal }} 次</span></h2>
        <div v-if="tacticTotal === 0" class="empty small">暂无已结束谈判的战术数据</div>
        <div v-else ref="chartEl" class="chart"></div>
      </section>
    </template>
  </div>
</template>

<style scoped>
.admin {
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

.kpis {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 14px;
  margin: 24px 0;
}

.kpi {
  background: linear-gradient(180deg, rgba(22, 34, 58, 0.5), rgba(13, 22, 38, 0.7));
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 20px 24px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.kpi .num {
  font-family: var(--font-display);
  font-size: 30px;
  color: var(--gold);
}

.kpi .label {
  font-size: 12px;
  letter-spacing: 0.24em;
  color: var(--paper-faint);
}

.panel-sec {
  background: rgba(13, 22, 38, 0.6);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 24px;
}

.panel-sec h2 {
  margin: 0 0 16px;
  font-size: 15px;
  letter-spacing: 0.28em;
  color: var(--paper-dim);
}

.panel-sec h2 .dim {
  font-size: 12px;
  color: var(--paper-faint);
  margin-left: 10px;
  letter-spacing: 0.1em;
}

.chart {
  height: 320px;
}

.empty {
  padding: 60px 20px;
  text-align: center;
  border: 1px dashed var(--ink-600);
  border-radius: 6px;
}

.empty.small {
  padding: 32px 20px;
}

.empty-title {
  font-family: var(--font-display);
  font-size: 16px;
  letter-spacing: 0.3em;
  color: var(--gold);
  margin: 0 0 10px;
}

.empty p:not(.empty-title) {
  font-size: 13px;
  color: var(--paper-faint);
  margin: 0;
}
</style>
