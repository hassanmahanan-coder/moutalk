<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { scenarioApi, sessionApi } from '../api'

const router = useRouter()
const scenarios = ref([])
const recent = ref([])
const loading = ref(false)
const starting = ref('')

const DOMAIN_LABEL = {
  it_procurement: 'IT 采购',
  salary: '薪资谈判',
  supplier: '供应商管理',
}

const DIFFICULTY_LABEL = {
  easy: '入门',
  medium: '进阶',
  hard: '高阶',
}

onMounted(async () => {
  loading.value = true
  try {
    const [sData, rData] = await Promise.all([scenarioApi.list(), sessionApi.list()])
    scenarios.value = sData.items
    recent.value = rData.sessions
  } catch {
    /* 拦截器已提示 */
  } finally {
    loading.value = false
  }
})

async function start(scenario) {
  starting.value = scenario.id
  try {
    const s = await sessionApi.create(scenario.id)
    ElMessage.success('谈判席位已就绪')
    router.push({ name: 'room', params: { id: s.id } })
  } catch (err) {
    if (err.code === 'FREE_QUOTA_EXCEEDED') {
      ElMessage.warning('本月免费额度已用完，请升级 Pro')
      router.push({ name: 'payment' })
    }
  } finally {
    starting.value = ''
  }
}

async function removeCustom(scenario) {
  try {
    await scenarioApi.deleteCustom(scenario.id)
    scenarios.value = scenarios.value.filter((s) => s.id !== scenario.id)
    ElMessage.success('自定义场景已删除')
  } catch {
    /* 拦截器已提示 */
  }
}
</script>

<template>
  <div class="lobby">
    <div class="lobby-hero">
      <span class="water-char">谋</span>
      <p class="kicker">多轮深度谈判模拟</p>
      <h1>场景大厅</h1>
      <p class="subtitle">择一卷案牍，与 AI 对手席上论高下</p>
    </div>

    <hr class="gold-rule" />

    <div class="lobby-toolbar">
      <el-button type="primary" plain @click="router.push({ name: 'scenario-create' })">
        ＋ 自定义场景
      </el-button>
    </div>

    <div class="grid">
      <article v-for="(s, i) in scenarios" :key="s.id" class="card" :style="{ '--i': i }">
        <header class="card-head">
          <span class="case-no">案卷 {{ String(i + 1).padStart(2, '0') }}</span>
          <span class="domain">{{ DOMAIN_LABEL[s.domain] || s.domain }}</span>
          <span v-if="s.is_custom" class="tag custom">自定义</span>
        </header>
        <h2 class="card-title">{{ s.title }}</h2>
        <div class="tags">
          <span class="tag diff" :class="s.difficulty">{{ DIFFICULTY_LABEL[s.difficulty] || s.difficulty }}</span>
          <span class="tag" v-if="s.opponent_style">对手 · {{ s.opponent_style }}</span>
        </div>
        <p class="briefing">{{ s.briefing }}</p>
        <footer class="card-foot">
          <span class="price" :class="{ free: s.is_free }">
            {{ s.is_free || s.price === null || s.price === 0 ? '内置免费' : `¥ ${Number(s.price).toFixed(2)}` }}
          </span>
          <div class="card-actions">
            <el-button v-if="s.is_custom" plain size="small" @click.stop="removeCustom(s)">
              删除
            </el-button>
            <el-button
              type="primary"
              :loading="starting === s.id"
              @click="start(s)"
            >
              展开谈判
            </el-button>
          </div>
        </footer>
      </article>
    </div>

    <hr class="gold-rule" />

    <section class="recent">
      <h3>近案 · 最近会话</h3>
      <el-table v-if="recent.length" :data="recent" class="recent-table">
        <el-table-column prop="scenario_title" label="场景" min-width="160" />
        <el-table-column label="状态" width="110">
          <template #default="{ row }">
            <span class="status" :class="row.status">{{ row.status === 'active' ? '进行中' : '已结束' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="开始时间" min-width="180">
          <template #default="{ row }">
            {{ row.started_at ? new Date(row.started_at).toLocaleString('zh-CN') : '-' }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="140">
          <template #default="{ row }">
            <router-link v-if="row.status === 'active'" class="resume" :to="{ name: 'room', params: { id: row.id } }">继续谈判</router-link>
            <span v-else class="muted">—</span>
          </template>
        </el-table-column>
      </el-table>
      <p v-else class="empty">尚无谈判记录，从上方选择场景开局</p>
    </section>
  </div>
</template>

<style scoped>
.lobby {
  position: relative;
  padding: 56px 56px 40px;
  max-width: 1240px;
  margin: 0 auto;
  width: 100%;
}

.lobby-hero {
  position: relative;
  text-align: center;
  padding: 18px 0 30px;
}

.water-char {
  position: absolute;
  top: -34px;
  left: 50%;
  transform: translateX(-50%);
  font-family: var(--font-display);
  font-size: 220px;
  line-height: 1;
  color: transparent;
  -webkit-text-stroke: 1px rgba(201, 168, 106, 0.1);
  user-select: none;
  pointer-events: none;
}

.kicker {
  margin: 0 0 10px;
  font-size: 11px;
  letter-spacing: 0.6em;
  color: var(--seal-bright);
  text-indent: 0.6em;
}

.lobby-hero h1 {
  margin: 0;
  font-size: 42px;
  letter-spacing: 0.42em;
  text-indent: 0.42em;
}

.subtitle {
  margin: 12px 0 0;
  font-size: 13px;
  letter-spacing: 0.3em;
  color: var(--paper-faint);
}

.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(330px, 1fr));
  gap: 24px;
  padding: 34px 0;
}

.card {
  background: linear-gradient(180deg, rgba(22, 34, 58, 0.5), rgba(13, 22, 38, 0.68));
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 26px 28px 22px;
  display: flex;
  flex-direction: column;
  transition: transform 0.25s ease, border-color 0.25s ease, box-shadow 0.25s ease;
  animation: card-in 0.5s ease both;
  animation-delay: calc(var(--i) * 0.07s);
}

@keyframes card-in {
  from {
    opacity: 0;
    transform: translateY(14px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.card:hover {
  transform: translateY(-4px);
  border-color: var(--border-strong);
  box-shadow: var(--shadow-float);
}

.card-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.case-no {
  font-size: 11px;
  letter-spacing: 0.28em;
  color: var(--gold-dim);
  font-family: var(--font-display);
}

.domain {
  font-size: 11px;
  letter-spacing: 0.2em;
  color: var(--paper-faint);
  border: 1px solid var(--ink-600);
  border-radius: 2px;
  padding: 2px 8px;
}

.card-title {
  margin: 16px 0 10px;
  font-size: 21px;
  letter-spacing: 0.1em;
}

.tags {
  display: flex;
  gap: 8px;
  margin-bottom: 14px;
}

.tag {
  font-size: 11px;
  letter-spacing: 0.12em;
  color: var(--paper-dim);
  padding: 2px 10px;
  border-radius: 2px;
  background: rgba(201, 168, 106, 0.07);
  border: 1px solid rgba(201, 168, 106, 0.18);
}

.tag.diff.easy {
  color: var(--jade);
  border-color: rgba(111, 174, 147, 0.35);
}

.tag.diff.medium {
  color: var(--gold);
  border-color: rgba(201, 168, 106, 0.35);
}

.tag.diff.hard {
  color: var(--seal-bright);
  border-color: rgba(194, 69, 46, 0.4);
}

.briefing {
  margin: 0;
  font-size: 13px;
  line-height: 1.9;
  color: var(--paper-dim);
  flex: 1;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.card-foot {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 20px;
  padding-top: 16px;
  border-top: 1px solid rgba(201, 168, 106, 0.12);
}

.price {
  font-family: var(--font-display);
  font-size: 15px;
  color: var(--gold);
  letter-spacing: 0.08em;
}

.price.free {
  color: var(--jade);
}

.recent {
  padding: 8px 0 10px;
}

.recent h3 {
  margin: 0 0 16px;
  font-size: 17px;
  letter-spacing: 0.3em;
  color: var(--paper-dim);
}

.recent-table {
  --el-table-border-color: var(--ink-700);
  --el-table-header-bg-color: transparent;
  --el-table-tr-bg-color: transparent;
  --el-table-row-hover-bg-color: rgba(26, 40, 66, 0.55);
  background: transparent;
}

.status {
  font-size: 12px;
  letter-spacing: 0.14em;
  padding: 2px 10px;
  border-radius: 2px;
  border: 1px solid;
}

.status.active {
  color: var(--jade);
  border-color: rgba(111, 174, 147, 0.4);
}

.status.ended {
  color: var(--paper-faint);
  border-color: var(--ink-600);
}

.resume {
  color: var(--gold);
  font-size: 13px;
  letter-spacing: 0.14em;
}

.resume:hover {
  color: var(--seal-bright);
}

.muted {
  color: var(--paper-faint);
}

.empty {
  margin: 0;
  padding: 18px 0;
  font-size: 13px;
  color: var(--paper-faint);
  letter-spacing: 0.14em;
}
</style>
