<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import * as echarts from 'echarts'
import { reportApi, scenarioApi } from '../api'

const route = useRoute()
const router = useRouter()
const reports = ref([])
const titles = ref({})
const barEl = ref(null)
const curveEl = ref(null)
let barChart = null
let curveChart = null

const DIM_LABEL = {
  price_attainment: '价格达成',
  concession_margin: '让步幅度',
  bottom_line_hold: '底线坚守',
  time_efficiency: '时间效率',
  naturalness: '自然度',
  strategy_diversity: '策略多样性',
  emotion_control: '情绪控制',
  logic_consistency: '逻辑一致性',
}

const PALETTE = ['#c9a86a', '#6fae93', '#c2452e', '#7d8fbb', '#b07d9e']

function shortId(id) {
  return id ? id.slice(0, 8) : ''
}

function fmtDate(iso) {
  if (!iso) return '-'
  const d = new Date(iso)
  return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

function initBarChart() {
  if (!barEl.value || !reports.value.length) return
  barChart = echarts.init(barEl.value)
  barChart.setOption({
    backgroundColor: 'transparent',
    grid: { left: 56, right: 30, top: 30, bottom: 40 },
    tooltip: {
      trigger: 'axis',
      backgroundColor: '#1a2740',
      borderColor: '#8a7346',
      textStyle: { color: '#eae3d0', fontSize: 12 },
      formatter: (ps) => {
        const p = ps[0]
        return `${p.name}<br/>综合得分：${Math.round(p.value * 100)}`
      },
    },
    xAxis: {
      type: 'category',
      data: reports.value.map((r) => `${shortId(r.id)} ${fmtDate(r.generated_at)}`),
      axisLine: { lineStyle: { color: '#26375a' } },
      axisLabel: { color: '#8b918f', fontSize: 11, interval: 0, rotate: 18 },
    },
    yAxis: {
      type: 'value',
      max: 1,
      name: '综合得分',
      nameTextStyle: { color: '#8b918f' },
      splitLine: { lineStyle: { color: 'rgba(38,55,90,0.5)' } },
      axisLabel: { color: '#8b918f', formatter: (v) => Math.round(v * 100) },
    },
    series: [
      {
        type: 'bar',
        data: reports.value.map((r, i) => ({
          value: r.total_score || 0,
          itemStyle: { color: PALETTE[i % PALETTE.length] },
        })),
        barWidth: 46,
        label: { show: true, position: 'top', color: '#eae3d0', formatter: (p) => Math.round(p.value * 100) },
      },
    ],
  })
}

function initCurveChart() {
  if (!curveEl.value || !reports.value.length) return
  curveChart = echarts.init(curveEl.value)
  const maxRounds = Math.max(...reports.value.map((r) => (r.concession_curve || []).length), 1)
  curveChart.setOption({
    backgroundColor: 'transparent',
    grid: { left: 60, right: 24, top: 30, bottom: 34 },
    tooltip: {
      trigger: 'axis',
      backgroundColor: '#1a2740',
      borderColor: '#8a7346',
      textStyle: { color: '#eae3d0', fontSize: 12 },
      formatter: (ps) => {
        const p = ps[0]
        return `第 ${p.data[0]} 轮<br/>${p.seriesName}：${p.data[1] >= 10000 ? (p.data[1] / 10000).toFixed(1) + ' 万' : p.data[1]}`
      },
    },
    legend: {
      textStyle: { color: '#8b918f', fontSize: 11 },
      top: 0,
    },
    xAxis: {
      type: 'category',
      name: '轮',
      nameTextStyle: { color: '#8b918f' },
      data: Array.from({ length: maxRounds }, (_, i) => i + 1),
      axisLine: { lineStyle: { color: '#26375a' } },
      axisLabel: { color: '#8b918f' },
    },
    yAxis: {
      type: 'value',
      name: '报价',
      nameTextStyle: { color: '#8b918f' },
      splitLine: { lineStyle: { color: 'rgba(38,55,90,0.5)' } },
      axisLabel: { color: '#8b918f', formatter: (v) => (v >= 10000 ? `${(v / 10000).toFixed(1)}万` : v) },
    },
    series: reports.value.map((r, i) => ({
      name: shortId(r.id),
      type: 'line',
      smooth: true,
      symbol: 'circle',
      symbolSize: 6,
      lineStyle: { color: PALETTE[i % PALETTE.length], width: 2 },
      itemStyle: { color: PALETTE[i % PALETTE.length] },
      data: (r.concession_curve || []).map((p) => [p.round, p.price]),
    })),
  })
}

function dimKeys() {
  const keys = new Set()
  for (const r of reports.value) {
    for (const k of Object.keys(r.objective_json?.dimensions || {})) keys.add(k)
    for (const k of Object.keys(r.subjective_json?.dimensions || {})) keys.add(k)
  }
  return [...keys].filter((k) => DIM_LABEL[k])
}

function dimValue(report, key) {
  const v = report.objective_json?.dimensions?.[key]
  if (v !== undefined && v !== null) return { val: v, kind: 'objective' }
  const sv = report.subjective_json?.dimensions?.[key]
  if (sv !== undefined && sv !== null) return { val: sv, kind: 'subjective' }
  return null
}

function verdict(score) {
  if (score >= 0.6) return { label: '胜', cls: 'win' }
  if (score >= 0.4) return { label: '平', cls: 'draw' }
  return { label: '负', cls: 'lose' }
}

onMounted(async () => {
  const ids = route.params.ids.split(',')
  try {
    const [cmp, scenarios] = await Promise.all([reportApi.compare(ids), scenarioApi.list()])
    reports.value = cmp.reports
    titles.value = Object.fromEntries(scenarios.items.map((x) => [x.id, x.title]))
  } catch {
    router.push({ name: 'reports' })
    return
  }
  await new Promise((r) => setTimeout(r, 50))
  initBarChart()
  initCurveChart()
  window.addEventListener('resize', resize)
})

function resize() {
  barChart?.resize()
  curveChart?.resize()
}

onBeforeUnmount(() => {
  window.removeEventListener('resize', resize)
  barChart?.dispose()
  curveChart?.dispose()
})
</script>

<template>
  <div class="compare">
    <div class="head">
      <p class="kicker">复盘报告 · 对比</p>
      <h1>卷宗对照</h1>
      <p class="sub">对比 {{ reports.length }} 份对局，洞察进步曲线</p>
    </div>
    <hr class="gold-rule" />

    <template v-if="reports.length">
      <section class="sec">
        <h2>综合得分</h2>
        <div ref="barEl" class="chart bar"></div>
      </section>

      <section class="sec">
        <h2>让步曲线叠加</h2>
        <div ref="curveEl" class="chart curve"></div>
      </section>

      <section class="sec">
        <h2>维度对比</h2>
        <div class="tbl-wrap">
          <table class="cmp-tbl">
            <thead>
              <tr>
                <th class="dim-col">维度</th>
                <th v-for="r in reports" :key="r.id" class="rep-col">
                  <span class="rep-name">{{ titles[r.scenario_id] || r.scenario_id }}</span>
                  <span class="rep-id">#{{ shortId(r.id) }} · {{ fmtDate(r.generated_at) }}</span>
                  <span class="rep-score" :class="verdict(r.total_score).cls">
                    {{ Math.round((r.total_score || 0) * 100) }} · {{ verdict(r.total_score).label }}
                  </span>
                </th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="k in dimKeys()" :key="k">
                <td class="dim-col">{{ DIM_LABEL[k] }}</td>
                <td v-for="r in reports" :key="r.id">
                  <template v-if="dimValue(r, k)">
                    <span v-if="dimValue(r, k).kind === 'objective'" class="dim-bar">
                      <i :style="{ width: `${Math.round(dimValue(r, k).val * 100)}%` }"></i>
                    </span>
                    <span v-else class="stars">
                      <i v-for="n in 5" :key="n" :class="{ on: n <= Math.round(dimValue(r, k).val) }"></i>
                    </span>
                    <span class="dim-val">{{ dimValue(r, k).kind === 'objective' ? Math.round(dimValue(r, k).val * 100) : dimValue(r, k).val.toFixed(1) }}</span>
                  </template>
                  <span v-else class="na">—</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <div class="foot-nav">
        <el-button plain @click="router.push({ name: 'reports' })">返回卷宗录</el-button>
      </div>
    </template>

    <div v-else class="empty">加载中……</div>
  </div>
</template>

<style scoped>
.compare {
  max-width: 980px;
  width: 100%;
  margin: 0 auto;
  padding: 48px 40px 70px;
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
  font-size: 34px;
  letter-spacing: 0.5em;
  text-indent: 0.5em;
}

.head .sub {
  margin: 10px 0 0;
  font-size: 13px;
  letter-spacing: 0.24em;
  color: var(--paper-faint);
}

.sec {
  margin-bottom: 36px;
}

.sec h2 {
  font-size: 17px;
  letter-spacing: 0.34em;
  color: var(--paper-dim);
  padding-bottom: 10px;
  border-bottom: 1px solid var(--border);
  margin: 0 0 18px;
}

.chart.bar {
  height: 260px;
}

.chart.curve {
  height: 300px;
}

.tbl-wrap {
  overflow-x: auto;
  border: 1px solid var(--border);
  border-radius: 6px;
}

.cmp-tbl {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.cmp-tbl th,
.cmp-tbl td {
  padding: 12px 14px;
  border-bottom: 1px solid rgba(38, 55, 90, 0.5);
  text-align: center;
}

.cmp-tbl thead th {
  background: rgba(22, 34, 58, 0.6);
}

.cmp-tbl tr:last-child td {
  border-bottom: none;
}

.dim-col {
  width: 110px;
  text-align: left !important;
  color: var(--paper-dim);
  letter-spacing: 0.1em;
  white-space: nowrap;
}

.rep-col {
  min-width: 160px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  align-items: center;
}

.rep-name {
  color: var(--paper);
  font-size: 13px;
  letter-spacing: 0.06em;
}

.rep-id {
  color: var(--paper-faint);
  font-size: 11px;
}

.rep-score {
  font-family: var(--font-display);
  font-size: 15px;
}

.rep-score.win {
  color: var(--gold);
}

.rep-score.draw {
  color: var(--jade);
}

.rep-score.lose {
  color: var(--seal-bright);
}

.dim-bar {
  display: inline-block;
  width: 90px;
  height: 7px;
  background: var(--ink-700);
  border-radius: 4px;
  overflow: hidden;
  vertical-align: middle;
}

.dim-bar i {
  display: block;
  height: 100%;
  background: linear-gradient(90deg, var(--gold-dim), var(--gold));
}

.stars i {
  display: inline-block;
  width: 10px;
  height: 10px;
  transform: rotate(45deg);
  border: 1px solid var(--ink-600);
  border-radius: 2px;
  margin: 0 2px;
}

.stars i.on {
  background: var(--gold-dim);
  border-color: var(--gold-dim);
}

.dim-val {
  margin-left: 8px;
  font-family: var(--font-display);
  color: var(--gold);
  font-size: 14px;
}

.na {
  color: var(--paper-faint);
}

.foot-nav {
  display: flex;
  justify-content: center;
  margin-top: 34px;
}

.empty {
  padding: 60px 0;
  text-align: center;
  color: var(--paper-faint);
  letter-spacing: 0.2em;
}
</style>
