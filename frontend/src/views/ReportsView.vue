<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { reportApi, scenarioApi } from '../api'

const router = useRouter()
const items = ref([])
const loading = ref(false)
const titles = ref({})
const pdfBusy = ref({})
const compareMode = ref(false)
const selected = ref(new Set())

function toggleCompare(id) {
  const s = new Set(selected.value)
  if (s.has(id)) s.delete(id)
  else {
    if (s.size >= 5) {
      ElMessage.warning('最多对比 5 份报告')
      return
    }
    s.add(id)
  }
  selected.value = s
}

function goCompare() {
  if (selected.value.size < 2) {
    ElMessage.warning('请至少勾选 2 份报告')
    return
  }
  router.push({ name: 'report-compare', params: { ids: [...selected.value].join(',') } })
}

function verdict(score) {
  if (score === null || score === undefined) return { label: '—', cls: 'none' }
  if (score >= 0.6) return { label: '胜', cls: 'win' }
  if (score >= 0.4) return { label: '平', cls: 'draw' }
  return { label: '负', cls: 'lose' }
}

onMounted(async () => {
  loading.value = true
  try {
    const [r, s] = await Promise.all([reportApi.list(), scenarioApi.list()])
    items.value = r.items
    titles.value = Object.fromEntries(s.items.map((x) => [x.id, x.title]))
  } catch {
    /* 拦截器已提示 */
  } finally {
    loading.value = false
  }
})

function open(id) {
  router.push({ name: 'report-detail', params: { id } })
}

async function downloadPdf(id, ev) {
  ev.stopPropagation()
  if (pdfBusy.value[id]) return
  pdfBusy.value = { ...pdfBusy.value, [id]: true }
  try {
    await reportApi.downloadPdf(id)
  } catch (e) {
    if (e?.code === 'PDF_NOT_READY') {
      for (let i = 0; i < 10; i++) {
        await new Promise((r) => setTimeout(r, 1500))
        try {
          await reportApi.downloadPdf(id)
          return
        } catch (retryErr) {
          if (retryErr?.code !== 'PDF_NOT_READY') return
        }
      }
      ElMessage.warning('PDF 生成超时，请稍后重试')
    }
  } finally {
    pdfBusy.value = { ...pdfBusy.value, [id]: false }
  }
}
</script>

<template>
  <div class="reports">
    <div class="head">
      <p class="kicker">复盘报告</p>
      <h1>卷宗录</h1>
      <p class="sub">每一次对局，皆有迹可循</p>
    </div>
    <hr class="gold-rule" />

    <div v-if="loading" class="empty">正在誊写……</div>

    <div v-else-if="!items.length" class="empty">
      <span class="ink-char">空</span>
      <p>尚无复盘记录，去场景大厅开局</p>
      <el-button type="primary" @click="router.push({ name: 'lobby' })">返回大厅</el-button>
    </div>

    <div v-else class="list">
      <button v-for="r in items" :key="r.id" class="record" :class="{ sel: selected.has(r.id) }" @click="open(r.id)">
        <span v-if="compareMode" class="chk" :class="{ on: selected.has(r.id) }" @click.stop="toggleCompare(r.id)"></span>
        <span class="rec-no">卷</span>
        <div class="rec-main">
          <h3>{{ titles[r.scenario_id] || r.scenario_id }}</h3>
          <p>{{ r.generated_at ? new Date(r.generated_at).toLocaleString('zh-CN') : '-' }}</p>
        </div>
        <div class="rec-score">
          <span class="score-num">{{ r.total_score === null || r.total_score === undefined ? '—' : `${Math.round(r.total_score * 100)}` }}</span>
          <span class="score-bar">
            <i :style="{ width: `${Math.round((r.total_score || 0) * 100)}%` }"></i>
          </span>
        </div>
        <span class="verdict" :class="verdict(r.total_score).cls">{{ verdict(r.total_score).label }}</span>
        <span
          v-if="!compareMode"
          class="pdf-dl"
          :class="{ busy: pdfBusy[r.id] }"
          title="下载 PDF"
          @click.stop="downloadPdf(r.id, $event)"
        >▤</span>
        <span class="arrow">阅 →</span>
      </button>
    </div>

    <div class="compare-bar" v-if="items.length >= 2">
      <el-button :type="compareMode ? 'primary' : 'default'" size="small" @click="compareMode = !compareMode; selected = new Set()">
        {{ compareMode ? '退出选择' : '对比报告' }}
      </el-button>
      <el-button v-if="compareMode" type="primary" size="small" :disabled="selected.size < 2" @click="goCompare">
        对比所选（{{ selected.size }}/5）
      </el-button>
    </div>
  </div>
</template>

<style scoped>
.reports {
  max-width: 960px;
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

.empty {
  padding: 60px 0;
  text-align: center;
  color: var(--paper-faint);
  letter-spacing: 0.2em;
}

.empty p {
  margin: 10px 0 18px;
  font-size: 13px;
}

.ink-char {
  font-family: var(--font-display);
  font-size: 60px;
  color: transparent;
  -webkit-text-stroke: 1px rgba(201, 168, 106, 0.25);
}

.list {
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding-top: 26px;
}

.record {
  display: flex;
  align-items: center;
  gap: 18px;
  width: 100%;
  text-align: left;
  background: linear-gradient(180deg, rgba(22, 34, 58, 0.5), rgba(13, 22, 38, 0.7));
  border: 1px solid var(--border);
  border-radius: 5px;
  padding: 18px 24px;
  cursor: pointer;
  transition: all 0.22s;
  color: var(--paper);
  font-family: var(--font-body);
}

.record:hover {
  border-color: var(--border-strong);
  transform: translateY(-2px);
  box-shadow: var(--shadow-float);
}

.rec-no {
  font-family: var(--font-display);
  font-size: 15px;
  color: var(--gold-dim);
  border: 1px solid var(--gold-dim);
  border-radius: 3px;
  padding: 3px 7px;
  flex-shrink: 0;
}

.rec-main {
  flex: 1;
  min-width: 0;
}

.rec-main h3 {
  margin: 0 0 4px;
  font-size: 16px;
  letter-spacing: 0.06em;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.rec-main p {
  margin: 0;
  font-size: 12px;
  color: var(--paper-faint);
}

.rec-score {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 6px;
  width: 150px;
}

.score-num {
  font-family: var(--font-display);
  font-size: 24px;
  color: var(--gold);
  line-height: 1;
}

.score-bar {
  width: 120px;
  height: 4px;
  background: var(--ink-600);
  border-radius: 2px;
  overflow: hidden;
}

.score-bar i {
  display: block;
  height: 100%;
  background: linear-gradient(90deg, var(--gold-dim), var(--gold));
  border-radius: 2px;
}

.verdict {
  font-family: var(--font-display);
  font-size: 15px;
  width: 34px;
  height: 34px;
  display: grid;
  place-items: center;
  border-radius: 50%;
  border: 1px solid;
  flex-shrink: 0;
}

.verdict.win {
  color: var(--gold);
  border-color: rgba(201, 168, 106, 0.5);
}

.verdict.draw {
  color: var(--jade);
  border-color: rgba(111, 174, 147, 0.5);
}

.verdict.lose {
  color: var(--seal-bright);
  border-color: rgba(194, 69, 46, 0.5);
}

.verdict.none {
  color: var(--paper-faint);
  border-color: var(--ink-600);
}

.arrow {
  font-size: 12px;
  color: var(--paper-faint);
  letter-spacing: 0.2em;
  flex-shrink: 0;
}

.pdf-dl {
  font-size: 15px;
  color: var(--gold-dim);
  padding: 4px 8px;
  border: 1px solid rgba(201, 168, 106, 0.25);
  border-radius: 3px;
  cursor: pointer;
  transition: all 0.2s;
  flex-shrink: 0;
}

.pdf-dl:hover {
  color: var(--gold);
  border-color: var(--gold-dim);
  background: rgba(201, 168, 106, 0.08);
}

.pdf-dl.busy {
  opacity: 0.4;
  pointer-events: none;
}

.chk {
  width: 18px;
  height: 18px;
  border: 1px solid var(--ink-600);
  border-radius: 3px;
  flex-shrink: 0;
  transition: all 0.2s;
  background: var(--ink-800);
}

.chk.on {
  background: var(--gold-dim);
  border-color: var(--gold-dim);
  box-shadow: inset 0 0 0 3px var(--ink-850);
}

.record.sel {
  border-color: var(--gold-dim);
  background: rgba(201, 168, 106, 0.06);
}

.compare-bar {
  display: flex;
  justify-content: center;
  gap: 12px;
  margin-top: 26px;
  padding-top: 18px;
  border-top: 1px solid var(--border);
}
</style>
