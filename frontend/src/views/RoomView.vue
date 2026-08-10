<script setup>
import { nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import * as echarts from 'echarts'
import { sessionApi, scenarioApi, reportApi } from '../api'
import { useAuthStore } from '../stores/auth'
import { useNegotiation } from '../composables/useNegotiation'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const neg = useNegotiation()

const scenario = ref(null)
const msgs = ref([])
const draft = ref('')
const chartEl = ref(null)
const chatEl = ref(null)
const metaStat = ref(null)
const finished = ref(false)
const resultRid = ref('')
const curve = ref([])
const coachOpen = ref(false)
const coachLoading = ref(false)
const coach = ref(null)
let chart = null

const TACTIC_LABEL = {
  anchoring: '锚定效应',
  concession: '让步策略',
  divide_conquer: '分而治之',
  good_cop_bad_cop: '红白脸',
  scarcity: '稀缺施压',
  silence: '沉默施压',
  carrot_stick: '胡萝卜加大棒',
  other: '试探',
}

const BOTTOM_LINE_LABEL = { ok: '底线未破', breached: '已越底线', unknown: '未知' }

function parsePrice(text) {
  const m = String(text).match(/(\d+(?:\.\d+)?)\s*(万|w|千|k)?/i)
  if (!m) return null
  let v = parseFloat(m[1])
  const unit = (m[2] || '').toLowerCase()
  if (unit === '万' || unit === 'w') v *= 10000
  else if (unit === '千' || unit === 'k') v *= 1000
  return v
}

function trackPrice(text) {
  const v = parsePrice(text)
  if (v === null) return
  curve.value = [...curve.value, { round: curve.value.length + 1, price: v }]
  updateChart()
}

function scrollBottom() {
  nextTick(() => {
    if (chatEl.value) chatEl.value.scrollTop = chatEl.value.scrollHeight
  })
}

function pushMsg(m) {
  msgs.value.push(m)
  scrollBottom()
}

function updateChart() {
  if (!chart) return
  const data = curve.value.map((p) => p.price)
  const rounds = curve.value.map((p) => p.round)
  const lastIdx = data.length - 1
  chart.setOption({
    series: [
      {
        data,
        // 最新报价点放大高亮（sticky 图表 + 当前轮强调）
        symbolSize: (value, params) => (params.dataIndex === lastIdx ? 14 : 8),
        itemStyle: {
          color: (params) => (params.dataIndex === lastIdx ? '#e8d5a0' : '#c9a86a'),
          borderColor: '#eae3d0',
          borderWidth: (params) => (params.dataIndex === lastIdx ? 2 : 1),
        },
      },
    ],
    xAxis: { data: rounds },
    // 数据点多时自动滚动窗口跟随最新点（最多显示 12 轮）
    dataZoom: data.length > 12 ? [{ type: 'inside', startValue: lastIdx - 11, endValue: lastIdx }] : [],
  })
}

function initChart() {
  if (!chartEl.value) return
  chart = echarts.init(chartEl.value)
  chart.setOption({
    backgroundColor: 'transparent',
    grid: { left: 52, right: 20, top: 20, bottom: 30 },
    tooltip: {
      trigger: 'axis',
      backgroundColor: '#1a2740',
      borderColor: '#8a7346',
      textStyle: { color: '#eae3d0', fontSize: 12 },
    },
    xAxis: {
      type: 'category',
      name: '轮',
      nameTextStyle: { color: '#8b918f' },
      data: [],
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
        data: [],
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
              { offset: 0, color: 'rgba(201,168,106,0.28)' },
              { offset: 1, color: 'rgba(201,168,106,0.02)' },
            ],
          },
        },
        markLine: {
          silent: true,
          symbol: 'none',
          lineStyle: { color: '#c2452e', type: 'dashed', width: 1 },
          data: [],
        },
      },
    ],
  })
  setBottomLineMark()
}

function setBottomLineMark() {
  if (!chart) return
  const priceDims = (scenario.value?.dimensions || []).filter((d) => d.type === 'price')
  const marks = []
  for (const d of priceDims) {
    const v = parsePrice(String(d.bottom_line)) ?? Number(d.bottom_line)
    if (v === null || Number.isNaN(v)) continue
    marks.push({ yAxis: v, label: { formatter: '底线', color: '#e0603f', fontSize: 11 } })
  }
  chart.setOption({ series: [{ markLine: { data: marks } }] })
}

onMounted(async () => {
  initChart()
  try {
    const list = await sessionApi.list()
    const row = list.sessions.find((s) => s.id === route.params.id)
    if (row && row.scenario_id) {
      scenario.value = await scenarioApi.detail(row.scenario_id)
    }
  } catch {
    /* 拦截器已提示 */
  }

  neg.connect(route.params.id, auth.accessToken, {
    onOpening(msg) {
      pushMsg({ role: 'opponent', text: msg.text, streaming: false, tactic: '', bottom_line: 'unknown', intent: '' })
      setBottomLineMark()
    },
    onHistory(msg) {
      for (const m of msg.messages || []) {
        msgs.value.push({
          role: m.role === 'assistant' ? 'opponent' : 'user',
          text: m.content,
          streaming: false,
          tactic: '',
          bottom_line: 'unknown',
          intent: '',
        })
      }
      curve.value = (msg.offers || []).map((o, i) => ({ round: i + 1, price: o.numbers }))
      metaStat.value = { round: msg.round, tactic: '', bottom_line: 'unknown' }
      updateChart()
      setBottomLineMark()
      scrollBottom()
    },
    onToken() {
      scrollBottom()
    },
    onMeta(msg) {
      metaStat.value = msg
      const last = msgs.value[msgs.value.length - 1]
      if (last && last.role === 'opponent' && last.streaming) {
        last.streaming = false
        last.text = neg.turnText
        last.tactic = msg.tactic
        last.bottom_line = msg.bottom_line
        last.intent = msg.intent
        trackPrice(last.text)
        scrollBottom()
      }
    },
    onReplay(messages) {
      // 断线重连回放（PRD 9.1）：渲染断线期间缓冲的轮次
      for (const m of messages || []) {
        if (m.user_text) pushMsg({ role: 'user', text: m.user_text, streaming: false, tactic: '', bottom_line: 'unknown', intent: '' })
        if (m.reply) {
          pushMsg({ role: 'opponent', text: m.reply, streaming: false, tactic: m.meta?.tactic || '', bottom_line: m.meta?.bottom_line || 'unknown', intent: m.meta?.intent || '' })
          trackPrice(m.reply)
        }
      }
      if (messages?.length) {
        ElMessage.success('已恢复断线期间的对话')
      }
    },
    onCoachAdvice(msg) {
      coachLoading.value = false
      coach.value = { analysis: msg.analysis, strategy: msg.strategy, options: msg.options || [] }
    },
    onResult(msg) {
      finished.value = true
      metaStat.value = null
      ElMessage.success('谈判结束')
    },
    onReport(msg) {
      resultRid.value = msg.rid
    },
    onReportSubmitted() {
      finished.value = true
      metaStat.value = null
      ElMessage.info('谈判已结束，复盘报告异步生成中……')
      pollReport(route.params.id)
    },
    onError() {
      finished.value = true
    },
    onClose() {
      if (!finished.value && msgs.value.length) {
        ElMessage.info('连接已断开')
      }
    },
  })
})

function send() {
  const text = draft.value.trim()
  if (!text || !neg.connected || finished.value || neg.streaming) return
  draft.value = ''
  pushMsg({ role: 'user', text })
  pushMsg({ role: 'opponent', text: '', streaming: true, tactic: '', bottom_line: 'unknown', intent: '' })
  trackPrice(text)
  neg.send('user_msg', { text })
}

// ---- 谈判教练：请求建议 + 点选话术直接发送 ----
function askCoach() {
  if (coachLoading.value || !neg.connected || finished.value) return
  coachLoading.value = true
  coach.value = null
  coachOpen.value = true
  neg.send('coach')
}

function useCoachOption(text) {
  coachOpen.value = false
  coach.value = null
  draft.value = text
  send()
}

function endNegotiation() {
  if (!neg.connected || finished.value) return
  ElMessage.info('正在终结谈判并生成复盘……')
  neg.send('end_negotiation')
}

function gotoReport() {
  if (resultRid.value) router.push({ name: 'report-detail', params: { id: resultRid.value } })
}

function pollReport(sessionId, attempts = 0) {
  if (!sessionId || attempts >= 15) return
  reportApi
    .list()
    .then((res) => {
      const hit = (res.items || []).find((it) => it.session_id === sessionId)
      if (hit) resultRid.value = hit.id
      else setTimeout(() => pollReport(sessionId, attempts + 1), 1500)
    })
    .catch(() => setTimeout(() => pollReport(sessionId, attempts + 1), 1500))
}

function leave() {
  router.push({ name: 'lobby' })
}

onBeforeUnmount(() => {
  chart?.dispose()
})
</script>

<template>
  <div class="room">
    <aside class="panel dossier">
      <div class="dossier-head">
        <span class="opponent-avatar">对</span>
        <div>
          <h3>{{ scenario?.opponent_role || '谈判对手' }}</h3>
          <p>{{ scenario?.title || '谈判中' }}</p>
        </div>
      </div>
      <dl class="stats">
        <div>
          <dt>对手风格</dt>
          <dd>{{ scenario?.opponent_style || '-' }}</dd>
        </div>
        <div>
          <dt>当前战术</dt>
          <dd class="tactic">
            <span v-if="metaStat">{{ TACTIC_LABEL[metaStat.tactic] || metaStat.tactic }}</span>
            <span v-else class="muted">试探中</span>
          </dd>
        </div>
        <div>
          <dt>底线状态</dt>
          <dd>
            <span class="line" :class="metaStat?.bottom_line || 'unknown'">
              {{ BOTTOM_LINE_LABEL[metaStat?.bottom_line || 'unknown'] }}
            </span>
          </dd>
        </div>
        <div>
          <dt>轮次</dt>
          <dd>{{ metaStat?.round ?? 0 }}</dd>
        </div>
      </dl>
      <hr class="gold-rule" />
      <p class="brief">{{ scenario?.briefing }}</p>
    </aside>

    <section class="table">
      <div ref="chatEl" class="chat">
        <div v-if="!msgs.length" class="waiting">
          <span class="ink-char">谈</span>
          <p>正与对手落座……</p>
        </div>
        <div v-for="(m, i) in msgs" :key="i" class="bubble-row" :class="m.role">
          <div class="bubble" :class="{ streaming: m.streaming }">
            <p>{{ m.streaming ? neg.turnText : m.text }}<span v-if="m.streaming" class="caret"></span></p>
            <div v-if="m.role === 'opponent' && !m.streaming && (m.tactic || m.bottom_line !== 'unknown')" class="meta-tags">
              <span v-if="m.tactic" class="mt">{{ TACTIC_LABEL[m.tactic] || m.tactic }}</span>
              <span class="mt line" :class="m.bottom_line">{{ BOTTOM_LINE_LABEL[m.bottom_line] }}</span>
            </div>
          </div>
        </div>
      </div>
      <div class="composer">
        <textarea
          v-model="draft"
          :disabled="!neg.connected || finished"
          :placeholder="finished ? '谈判已结束' : neg.connected ? '陈述您的立场或报价……' : '连接中……'"
          @keydown.enter.exact.prevent="send"
        ></textarea>
        <div class="composer-actions">
          <span class="hint">Enter 发送</span>
          <el-button size="small" :disabled="!neg.connected || finished || neg.streaming" :loading="coachLoading" @click="askCoach">
            教练
          </el-button>
          <el-button size="small" @click="endNegotiation" :disabled="!neg.connected || finished">结束谈判</el-button>
          <el-button
            type="primary"
            size="small"
            :loading="neg.streaming"
            :disabled="!neg.connected || finished || neg.streaming || !draft.trim()"
            @click="send"
          >
            出 牌
          </el-button>
        </div>
      </div>

      <transition name="coach">
        <div v-if="coachOpen" class="coach-panel">
          <div class="cp-head">
            <span class="cp-title">谈判教练</span>
            <button class="cp-close" @click="coachOpen = false">✕</button>
          </div>
          <div v-if="coachLoading" class="cp-loading">正在研判局势……</div>
          <div v-else-if="coach" class="cp-body">
            <p class="cp-analysis">{{ coach.analysis }}</p>
            <p class="cp-strategy">策略 · {{ coach.strategy }}</p>
            <div class="cp-options">
              <button v-for="(opt, i) in coach.options" :key="i" class="cp-opt" @click="useCoachOption(opt)">
                {{ opt }}
              </button>
            </div>
          </div>
          <div v-else class="cp-loading">建议生成中……</div>
        </div>
      </transition>
    </section>

    <aside class="panel board">
      <div class="chart-wrap">
        <div class="board-head">
          <h3>报价看板</h3>
          <span class="head-tags">
            <span v-if="neg.llmMode === 'mock'" class="demo-tag" title="未配置 LLM_API_KEY，当前为规则引擎演示模式">演示</span>
            <span class="conn" :class="{ on: neg.connected }">{{ neg.connected ? '连线中' : '已断开' }}</span>
          </span>
        </div>
        <div ref="chartEl" class="chart"></div>
      </div>
      <hr class="gold-rule" />

      <div v-if="!finished" class="board-note">
        <p>双方每轮报价将实时绘制于曲线上方。</p>
        <p class="dim">谈判要点：先摸底、再出价、控节奏。</p>
      </div>

      <div v-else class="result-box">
        <h4>本局已终</h4>
        <p class="summary">{{ neg.simpleResult?.summary || '谈判已结束，详细复盘报告生成中' }}</p>
        <p class="stat-line">共 {{ neg.simpleResult?.rounds ?? 0 }} 轮 · 报价 {{ neg.simpleResult?.offers_count ?? 0 }} 次</p>
        <el-button type="primary" :disabled="!resultRid" @click="gotoReport">查看复盘报告</el-button>
        <el-button plain class="back" @click="leave">返回大厅</el-button>
      </div>
    </aside>
  </div>
</template>

<style scoped>
.room {
  flex: 1;
  display: grid;
  grid-template-columns: 260px minmax(0, 1fr) 340px;
  gap: 1px;
  background: var(--ink-600);
  min-height: calc(100vh - 64px);
}

.panel {
  background: var(--ink-850);
  padding: 22px 20px;
  overflow-y: auto;
}

.dossier-head {
  display: flex;
  gap: 12px;
  align-items: center;
  margin-bottom: 20px;
}

.opponent-avatar {
  width: 46px;
  height: 46px;
  border-radius: 5px;
  display: grid;
  place-items: center;
  font-family: var(--font-display);
  font-size: 20px;
  color: var(--paper);
  background: linear-gradient(150deg, var(--ink-600), var(--ink-700));
  border: 1px solid var(--border-strong);
}

.dossier-head h3 {
  margin: 0;
  font-size: 15px;
  letter-spacing: 0.08em;
}

.dossier-head p {
  margin: 4px 0 0;
  font-size: 12px;
  color: var(--paper-faint);
  letter-spacing: 0.04em;
}

.stats {
  margin: 0;
}

.stats > div {
  padding: 9px 0;
  border-bottom: 1px solid rgba(38, 55, 90, 0.6);
}

.stats dt {
  font-size: 11px;
  color: var(--paper-faint);
  letter-spacing: 0.24em;
  margin-bottom: 4px;
}

.stats dd {
  margin: 0;
  font-size: 13px;
  color: var(--paper);
}

.tactic {
  color: var(--gold) !important;
}

.line {
  padding: 1px 8px;
  border-radius: 2px;
  font-size: 11px !important;
  letter-spacing: 0.1em;
  border: 1px solid;
}

.line.ok {
  color: var(--jade);
  border-color: rgba(111, 174, 147, 0.4);
}

.line.breached {
  color: var(--seal-bright);
  border-color: rgba(194, 69, 46, 0.5);
}

.line.unknown {
  color: var(--paper-faint);
  border-color: var(--ink-600);
}

.muted {
  color: var(--paper-faint);
}

.brief {
  margin: 16px 0 0;
  font-size: 12px;
  line-height: 1.9;
  color: var(--paper-dim);
}

.table {
  display: flex;
  flex-direction: column;
  background:
    radial-gradient(900px 400px at 50% 0%, rgba(194, 69, 46, 0.06), transparent 60%),
    var(--ink-900);
}

.chat {
  flex: 1;
  overflow-y: auto;
  padding: 28px 36px;
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.waiting {
  margin: auto;
  text-align: center;
}

.ink-char {
  font-family: var(--font-display);
  font-size: 64px;
  color: transparent;
  -webkit-text-stroke: 1px rgba(201, 168, 106, 0.25);
}

.waiting p {
  color: var(--paper-faint);
  letter-spacing: 0.3em;
  font-size: 13px;
}

.bubble-row {
  display: flex;
}

.bubble-row.user {
  justify-content: flex-end;
}

.bubble-row.opponent {
  justify-content: flex-start;
}

.bubble {
  max-width: 68%;
  padding: 14px 18px;
  border-radius: 4px;
  font-size: 14px;
  line-height: 1.9;
  animation: bubble-in 0.3s ease both;
}

@keyframes bubble-in {
  from {
    opacity: 0;
    transform: translateY(6px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.bubble p {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
}

.bubble-row.opponent .bubble {
  background: linear-gradient(180deg, rgba(26, 40, 66, 0.85), rgba(17, 28, 49, 0.9));
  border: 1px solid var(--border);
  border-left: 2px solid var(--gold-dim);
}

.bubble-row.user .bubble {
  background: linear-gradient(180deg, rgba(143, 47, 31, 0.32), rgba(194, 69, 46, 0.16));
  border: 1px solid rgba(194, 69, 46, 0.35);
}

.caret {
  display: inline-block;
  width: 2px;
  height: 1em;
  vertical-align: -0.18em;
  margin-left: 3px;
  background: var(--gold);
  animation: blink 0.9s steps(1) infinite;
}

@keyframes blink {
  50% {
    opacity: 0;
  }
}

.meta-tags {
  display: flex;
  gap: 8px;
  margin-top: 10px;
}

.mt {
  font-size: 11px;
  letter-spacing: 0.14em;
  color: var(--gold);
  border: 1px solid rgba(201, 168, 106, 0.3);
  border-radius: 2px;
  padding: 1px 8px;
}

.mt.line {
  color: var(--jade);
  border-color: rgba(111, 174, 147, 0.4);
}

.mt.line.breached {
  color: var(--seal-bright);
  border-color: rgba(194, 69, 46, 0.5);
}

.mt.line.unknown {
  color: var(--paper-faint);
  border-color: var(--ink-600);
}

.composer {
  border-top: 1px solid var(--border);
  padding: 16px 36px 20px;
  background: rgba(11, 18, 32, 0.9);
}

.composer textarea {
  width: 100%;
  min-height: 74px;
  resize: none;
  background: var(--ink-800);
  border: 1px solid var(--ink-600);
  border-radius: 4px;
  color: var(--paper);
  font-family: var(--font-body);
  font-size: 14px;
  line-height: 1.8;
  padding: 10px 14px;
  outline: none;
  transition: border-color 0.2s;
}

.composer textarea:focus {
  border-color: var(--gold-dim);
}

.composer textarea:disabled {
  opacity: 0.55;
}

.composer-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 12px;
}

.hint {
  margin-right: auto;
  font-size: 11px;
  color: var(--paper-faint);
  letter-spacing: 0.16em;
}

.coach-panel {
  position: fixed;
  right: 24px;
  bottom: 110px;
  width: 340px;
  max-height: 60vh;
  overflow-y: auto;
  background: rgba(11, 18, 32, 0.96);
  border: 1px solid var(--gold-dim);
  border-radius: 8px;
  box-shadow: 0 12px 40px rgba(0, 0, 0, 0.5);
  z-index: 30;
}

.cp-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border);
  background: rgba(22, 34, 58, 0.7);
}

.cp-title {
  font-family: var(--font-display);
  font-size: 13px;
  letter-spacing: 0.3em;
  color: var(--gold);
}

.cp-close {
  font-size: 12px;
  color: var(--paper-faint);
  background: none;
  border: none;
  cursor: pointer;
}

.cp-loading {
  padding: 28px 20px;
  text-align: center;
  color: var(--paper-faint);
  letter-spacing: 0.2em;
  font-size: 13px;
}

.cp-body {
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.cp-analysis {
  margin: 0;
  font-size: 13.5px;
  line-height: 1.9;
  color: var(--paper);
}

.cp-strategy {
  margin: 0;
  font-size: 12.5px;
  line-height: 1.8;
  color: var(--gold);
  letter-spacing: 0.04em;
}

.cp-options {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 4px;
}

.cp-opt {
  text-align: left;
  font-family: var(--font-body);
  font-size: 13px;
  line-height: 1.7;
  color: var(--paper-dim);
  background: rgba(26, 40, 66, 0.6);
  border: 1px solid var(--ink-600);
  border-radius: 4px;
  padding: 9px 12px;
  cursor: pointer;
  transition: all 0.2s;
}

.cp-opt:hover {
  color: var(--paper);
  border-color: var(--gold-dim);
  background: rgba(201, 168, 106, 0.08);
}

.coach-enter-active,
.coach-leave-active {
  transition: opacity 0.25s, transform 0.25s;
}

.coach-enter-from,
.coach-leave-to {
  opacity: 0;
  transform: translateY(12px);
}

.board {
  display: flex;
  flex-direction: column;
}

.board-head {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
}

.board-head h3 {
  margin: 0;
  font-size: 15px;
  letter-spacing: 0.24em;
}

.head-tags {
  display: inline-flex;
  align-items: baseline;
  gap: 10px;
}

.demo-tag {
  font-size: 10px;
  letter-spacing: 0.14em;
  color: var(--paper-faint);
  border: 1px solid var(--gold-dim);
  border-radius: 2px;
  padding: 1px 7px;
  cursor: help;
}

.conn {
  font-size: 11px;
  letter-spacing: 0.1em;
  color: var(--paper-faint);
}

.conn.on {
  color: var(--jade);
}

.chart-wrap {
  position: sticky;
  top: 0;
  z-index: 5;
  background: var(--ink-850);
  padding-bottom: 4px;
}

.chart {
  height: 260px;
  margin: 14px 0 4px;
}

.board-note p {
  margin: 8px 0;
  font-size: 12.5px;
  color: var(--paper-dim);
  line-height: 1.9;
}

.board-note .dim {
  color: var(--paper-faint);
  font-family: var(--font-display);
  letter-spacing: 0.08em;
}

.result-box {
  text-align: center;
  padding: 18px 0 6px;
}

.result-box h4 {
  margin: 0 0 10px;
  font-family: var(--font-display);
  font-size: 17px;
  letter-spacing: 0.3em;
  color: var(--gold);
}

.result-box .summary {
  margin: 0;
  font-size: 13px;
  color: var(--paper-dim);
  line-height: 1.9;
}

.result-box .stat-line {
  margin: 10px 0 18px;
  font-size: 12px;
  color: var(--paper-faint);
  letter-spacing: 0.12em;
}

.result-box .back {
  margin-left: 10px;
}
</style>
