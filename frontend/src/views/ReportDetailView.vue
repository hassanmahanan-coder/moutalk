<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import * as echarts from 'echarts'
import { reportApi, scenarioApi, sessionApi } from '../api'
import ReplayTimeline from '../components/ReplayTimeline.vue'

const route = useRoute()
const router = useRouter()
const report = ref(null)
const scenarioTitle = ref('')
const chartEl = ref(null)
const replayOpen = ref(false)
const replayRounds = ref([])
let chart = null

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

function verdict(score) {
  if (score >= 0.6) return { label: '完胜', cls: 'win' }
  if (score >= 0.4) return { label: '势均', cls: 'draw' }
  return { label: '落败', cls: 'lose' }
}

function initChart() {
  if (!chartEl.value || !report.value) return
  const curve = report.value.concession_curve || []
  chart = echarts.init(chartEl.value)
  chart.setOption({
    backgroundColor: 'transparent',
    grid: { left: 60, right: 24, top: 28, bottom: 34 },
    tooltip: {
      trigger: 'axis',
      backgroundColor: '#1a2740',
      borderColor: '#8a7346',
      textStyle: { color: '#eae3d0', fontSize: 12 },
      formatter: (ps) => {
        const p = ps[0]
        return `第 ${p.data[0]} 轮<br/>报价：${p.data[1] >= 10000 ? (p.data[1] / 10000).toFixed(2) + ' 万' : p.data[1]}`
      },
    },
    xAxis: {
      type: 'category',
      name: '轮',
      nameTextStyle: { color: '#8b918f' },
      data: curve.map((p) => p.round),
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
    series: [
      {
        type: 'line',
        data: curve.map((p) => [p.round, p.price]),
        smooth: true,
        symbol: 'circle',
        symbolSize: 8,
        lineStyle: { color: '#c9a86a', width: 2 },
        itemStyle: { color: '#c9a86a', borderColor: '#eae3d0', borderWidth: 1 },
        areaStyle: {
          color: {
            type: 'linear',
            x: 0,
            y: 0,
            x2: 0,
            y2: 1,
            colorStops: [
              { offset: 0, color: 'rgba(201,168,106,0.3)' },
              { offset: 1, color: 'rgba(201,168,106,0.02)' },
            ],
          },
        },
      },
    ],
  })
}

function dimValues(map) {
  if (!map) return []
  return Object.entries(DIM_LABEL)
    .filter(([k]) => map[k] !== undefined && map[k] !== null)
    .map(([k, label]) => ({ key: k, label, value: map[k] }))
}

onMounted(async () => {
  try {
    const r = await reportApi.detail(route.params.id)
    report.value = r
    const s = await scenarioApi.detail(r.scenario_id)
    scenarioTitle.value = s.title
  } catch {
    router.push({ name: 'reports' })
    return
  }
  await new Promise((r) => setTimeout(r, 50))
  initChart()
  window.addEventListener('resize', resize)
})

function resize() {
  chart?.resize()
}

// ---- PDF 下载（PRD 9.10）：首次触发导出返回 PDF_NOT_READY，轮询重试 ----
const pdfLoading = ref(false)

async function downloadPdf() {
  if (pdfLoading.value) return
  pdfLoading.value = true
  try {
    await reportApi.downloadPdf(route.params.id)
  } catch (e) {
    if (e?.code === 'PDF_NOT_READY') {
      // 导出中：最多轮询 10 次（每 1.5s）
      for (let i = 0; i < 10; i++) {
        await new Promise((r) => setTimeout(r, 1500))
        try {
          await reportApi.downloadPdf(route.params.id)
          return
        } catch (retryErr) {
          if (retryErr?.code !== 'PDF_NOT_READY') return
        }
      }
      ElMessage.warning('PDF 生成超时，请稍后在列表重试')
    }
  } finally {
    pdfLoading.value = false
  }
}

// ---- 谈判回放（PRD 9.17 / 故事 10）：时间轴逐轮播放 ----
const replayLoading = ref(false)

async function openReplay() {
  if (replayLoading.value) return
  replayLoading.value = true
  try {
    const sid = report.value.session_id
    const data = await sessionApi.replay(sid)
    replayRounds.value = data.rounds
    replayOpen.value = true
  } catch {
    ElMessage.warning('回放数据加载失败')
  } finally {
    replayLoading.value = false
  }
}

onBeforeUnmount(() => {
  window.removeEventListener('resize', resize)
  chart?.dispose()
})
</script>

<template>
  <div v-if="report" class="detail">
    <div class="head">
      <p class="kicker">复盘报告</p>
      <h1>{{ scenarioTitle }}</h1>
      <p class="sub">{{ report.ended_at ? new Date(report.ended_at).toLocaleString('zh-CN') : '' }}</p>
    </div>

    <div class="verdict-banner" :class="verdict(report.total_score).cls">
      <div class="vb-score">
        <span class="vb-num">{{ Math.round(report.total_score * 100) }}</span>
        <span class="vb-max">/ 100</span>
      </div>
      <div class="vb-meta">
        <span class="vb-verdict">{{ verdict(report.total_score).label }}</span>
        <span class="vb-total">综合得分 · 客观 {{ Math.round((report.objective_json?.total || 0) * 100) }}% + 主观 {{ Math.round((report.subjective_json?.normalized || 0) * 100) }}%</span>
      </div>
    </div>

    <section class="sec">
      <h2>让步曲线</h2>
      <div ref="chartEl" class="chart"></div>
    </section>

    <section class="sec">
      <h2>客观维度</h2>
      <div class="dims">
        <div v-for="d in dimValues(report.objective_json?.dimensions)" :key="d.key" class="dim-row">
          <span class="dim-label">{{ d.label }}</span>
          <div class="dim-bar">
            <i :style="{ width: `${Math.round(d.value * 100)}%` }" :class="d.key"></i>
          </div>
          <span class="dim-val">{{ Math.round(d.value * 100) }}</span>
        </div>
      </div>
    </section>

    <section class="sec">
      <h2>主观评估</h2>
      <div class="dims">
        <div v-for="d in dimValues(report.subjective_json?.dimensions)" :key="d.key" class="dim-row">
          <span class="dim-label">{{ d.label }}</span>
          <div class="subj-stars">
            <i v-for="n in 5" :key="n" :class="{ on: n <= Math.round(d.value) }"></i>
          </div>
          <span class="dim-val">{{ d.value.toFixed(1) }}</span>
        </div>
      </div>
    </section>

    <section class="sec">
      <h2>弱点与建议</h2>
      <ul class="weak">
        <li v-for="(w, i) in report.weak_points" :key="i">· {{ w }}</li>
        <li v-if="!report.weak_points?.length">· 无显著弱点</li>
      </ul>
      <blockquote class="advice">{{ report.advice }}</blockquote>
    </section>

    <div class="foot-nav">
      <el-button plain @click="router.push({ name: 'reports' })">返回卷宗录</el-button>
      <el-button :loading="replayLoading" @click="openReplay">回放谈判</el-button>
      <el-button :loading="pdfLoading" @click="downloadPdf">
        <span class="pdf-icon">▤</span> 下载 PDF
      </el-button>
      <el-button type="primary" @click="router.push({ name: 'lobby' })">再战一局</el-button>
    </div>

    <ReplayTimeline v-if="replayOpen" :rounds="replayRounds" @close="replayOpen = false" />
  </div>
</template>

<style scoped>
.detail {
  max-width: 920px;
  width: 100%;
  margin: 0 auto;
  padding: 48px 40px 70px;
}

.head {
  text-align: center;
  margin-bottom: 28px;
}

.kicker {
  margin: 0 0 8px;
  font-size: 11px;
  letter-spacing: 0.6em;
  color: var(--seal-bright);
}

.head h1 {
  margin: 0;
  font-size: 32px;
  letter-spacing: 0.3em;
}

.head .sub {
  margin: 10px 0 0;
  font-size: 12px;
  color: var(--paper-faint);
  letter-spacing: 0.12em;
}

.verdict-banner {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 26px;
  padding: 26px 32px;
  border-radius: 6px;
  border: 1px solid;
  margin-bottom: 34px;
  background: linear-gradient(180deg, rgba(22, 34, 58, 0.5), rgba(13, 22, 38, 0.7));
  animation: banner-in 0.5s ease both;
}

@keyframes banner-in {
  from {
    opacity: 0;
    transform: translateY(10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.verdict-banner.win {
  border-color: rgba(201, 168, 106, 0.5);
}

.verdict-banner.draw {
  border-color: rgba(111, 174, 147, 0.5);
}

.verdict-banner.lose {
  border-color: rgba(194, 69, 46, 0.5);
}

.vb-score {
  display: flex;
  align-items: baseline;
}

.vb-num {
  font-family: var(--font-display);
  font-size: 56px;
  line-height: 1;
  color: var(--gold);
}

.vb-max {
  font-size: 13px;
  color: var(--paper-faint);
  margin-left: 6px;
}

.vb-meta {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.vb-verdict {
  font-family: var(--font-display);
  font-size: 22px;
  letter-spacing: 0.3em;
}

.verdict-banner.win .vb-verdict {
  color: var(--gold);
}

.verdict-banner.draw .vb-verdict {
  color: var(--jade);
}

.verdict-banner.lose .vb-verdict {
  color: var(--seal-bright);
}

.vb-total {
  font-size: 12px;
  color: var(--paper-faint);
  letter-spacing: 0.08em;
}

.sec {
  margin-bottom: 34px;
}

.sec h2 {
  font-size: 17px;
  letter-spacing: 0.34em;
  color: var(--paper-dim);
  padding-bottom: 10px;
  border-bottom: 1px solid var(--border);
  margin: 0 0 18px;
}

.chart {
  height: 300px;
}

.dims {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.dim-row {
  display: flex;
  align-items: center;
  gap: 14px;
}

.dim-label {
  width: 90px;
  font-size: 13px;
  color: var(--paper-dim);
  letter-spacing: 0.1em;
  flex-shrink: 0;
}

.dim-bar {
  flex: 1;
  height: 8px;
  background: var(--ink-700);
  border-radius: 4px;
  overflow: hidden;
}

.dim-bar i {
  display: block;
  height: 100%;
  border-radius: 4px;
  background: linear-gradient(90deg, var(--gold-dim), var(--gold));
  transition: width 0.8s ease;
}

.dim-bar i.bottom_line_hold,
.dim-bar i.time_efficiency {
  background: linear-gradient(90deg, #4f7d6c, var(--jade));
}

.dim-val {
  width: 30px;
  text-align: right;
  font-family: var(--font-display);
  font-size: 15px;
  color: var(--gold);
  flex-shrink: 0;
}

.subj-stars {
  flex: 1;
  display: flex;
  gap: 8px;
}

.subj-stars i {
  width: 14px;
  height: 14px;
  transform: rotate(45deg);
  border: 1px solid var(--ink-600);
  border-radius: 2px;
}

.subj-stars i.on {
  background: var(--gold-dim);
  border-color: var(--gold-dim);
}

.weak {
  margin: 0 0 16px;
  padding: 0;
  list-style: none;
}

.weak li {
  font-size: 13.5px;
  color: var(--paper-dim);
  line-height: 2;
  letter-spacing: 0.04em;
}

.advice {
  margin: 0;
  padding: 16px 20px;
  border-left: 3px solid var(--gold-dim);
  background: rgba(201, 168, 106, 0.06);
  border-radius: 0 4px 4px 0;
  font-family: var(--font-display);
  font-size: 14.5px;
  line-height: 2;
  color: var(--paper);
}

.foot-nav {
  display: flex;
  justify-content: center;
  gap: 14px;
  margin-top: 40px;
}

.pdf-icon {
  display: inline-block;
  margin-right: 4px;
  font-size: 13px;
}
</style>
