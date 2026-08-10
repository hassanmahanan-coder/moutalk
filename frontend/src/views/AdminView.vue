<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import * as echarts from 'echarts'
import { adminApi } from '../api'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const meId = auth.user?.id

const stats = ref(null)
const tactics = ref({})
const tacticTotal = ref(0)
const online = ref(0)
const users = ref([])
const scenarios = ref([])
const tab = ref('overview')
const forbidden = ref(false)
const loading = ref(true)
const chartEl = ref(null)
let chart = null

const ROLE_LABELS = { free: '免费', pro: 'Pro', enterprise: '企业' }

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

async function loadUsers() {
  try {
    users.value = (await adminApi.users()).items
  } catch (e) {
    if (e?.code === 'FORBIDDEN') forbidden.value = true
  }
}

async function changeRole(u, role) {
  try {
    const updated = await adminApi.updateUserRole(u.id, { role })
    u.role = updated.role
    ElMessage.success(`已将 ${u.email} 调整为 ${ROLE_LABELS[role] || role}`)
  } catch {
    /* 拦截器已提示 */
  }
}

async function toggleAdmin(u) {
  try {
    const updated = await adminApi.updateUserRole(u.id, { is_admin: !u.is_admin })
    u.is_admin = updated.is_admin
    ElMessage.success(`${u.email} ${u.is_admin ? '已设为' : '已取消'}管理员`)
  } catch {
    /* 拦截器已提示 */
  }
}

async function loadScenarios() {
  try {
    scenarios.value = (await adminApi.scenarios()).items
  } catch (e) {
    if (e?.code === 'FORBIDDEN') forbidden.value = true
  }
}

async function toggleOnSale(s) {
  try {
    const updated = await adminApi.updateScenario(s.id, { on_sale: !s.on_sale })
    s.on_sale = updated.on_sale
    ElMessage.success(`「${s.title}」已${s.on_sale ? '上架' : '下架'}`)
  } catch {
    /* 拦截器已提示 */
  }
}

async function changePrice(s) {
  const price = prompt(`设置「${s.title}」价格（元，0 表示免费）`, s.price ?? 0)
  if (price === null) return
  const num = Number(price)
  if (Number.isNaN(num) || num < 0) {
    ElMessage.error('价格不合法')
    return
  }
  try {
    const updated = await adminApi.updateScenario(s.id, { price: num })
    s.price = updated.price
    ElMessage.success('价格已更新')
  } catch {
    /* 拦截器已提示 */
  }
}

function switchTab(t) {
  tab.value = t
  if (t === 'users' && !users.value.length) loadUsers()
  if (t === 'scenarios' && !scenarios.value.length) loadScenarios()
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
      <div class="tabs">
        <button class="tab" :class="{ on: tab === 'overview' }" @click="switchTab('overview')">运营概览</button>
        <button class="tab" :class="{ on: tab === 'users' }" @click="switchTab('users')">用户管理</button>
        <button class="tab" :class="{ on: tab === 'scenarios' }" @click="switchTab('scenarios')">场景管理</button>
      </div>

      <div v-if="tab === 'overview'">
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
      </div>

      <section v-else-if="tab === 'users'" class="panel-sec">
        <h2>用户管理 <span class="dim">共 {{ users.length }} 人</span></h2>
        <div v-if="!users.length" class="empty small">暂无用户</div>
        <table v-else class="user-table">
          <thead>
            <tr>
              <th>邮箱</th>
              <th>用户名</th>
              <th>角色</th>
              <th>管理员</th>
              <th>到期时间</th>
              <th>注册时间</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="u in users" :key="u.id">
              <td>{{ u.email }}</td>
              <td>{{ u.username || '—' }}</td>
              <td><span class="role-pill" :class="u.role">{{ ROLE_LABELS[u.role] || u.role }}</span></td>
              <td>
                <span v-if="u.is_admin" class="role-pill enterprise">管理员</span>
                <span v-else class="dim">—</span>
              </td>
              <td>{{ u.expire_at ? new Date(u.expire_at).toLocaleDateString('zh-CN') : '—' }}</td>
              <td>{{ u.created_at ? new Date(u.created_at).toLocaleDateString('zh-CN') : '—' }}</td>
              <td class="ops">
                <el-select v-if="!u.is_admin || u.id !== meId" :model-value="u.role" size="small" @change="(v) => changeRole(u, v)">
                  <el-option label="免费" value="free" />
                  <el-option label="Pro" value="pro" />
                  <el-option label="企业" value="enterprise" />
                </el-select>
                <el-button v-if="u.id !== meId" size="small" plain :type="u.is_admin ? 'danger' : 'primary'" @click="toggleAdmin(u)">
                  {{ u.is_admin ? '取消管理员' : '设为管理员' }}
                </el-button>
              </td>
            </tr>
          </tbody>
        </table>
      </section>

      <section v-else class="panel-sec">
        <h2>场景管理 <span class="dim">共 {{ scenarios.length }} 个</span></h2>
        <div v-if="!scenarios.length" class="empty small">暂无场景包</div>
        <table v-else class="user-table">
          <thead>
            <tr>
              <th>场景</th>
              <th>类型</th>
              <th>价格</th>
              <th>状态</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="s in scenarios" :key="s.id">
              <td>{{ s.title }}</td>
              <td>{{ s.domain }}</td>
              <td>{{ s.is_free ? '免费' : s.price != null ? `¥ ${Number(s.price).toFixed(2)}` : '—' }}</td>
              <td><span class="role-pill" :class="s.on_sale ? 'pro' : ''">{{ s.on_sale ? '在售' : '已下架' }}</span></td>
              <td class="ops">
                <el-button size="small" plain @click="changePrice(s)">定价</el-button>
                <el-button size="small" :type="s.on_sale ? 'danger' : 'primary'" plain @click="toggleOnSale(s)">
                  {{ s.on_sale ? '下架' : '上架' }}
                </el-button>
              </td>
            </tr>
          </tbody>
        </table>
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

.tabs {
  display: flex;
  gap: 10px;
  margin: 24px 0 16px;
}

.tab {
  font-family: var(--font-body);
  font-size: 13px;
  letter-spacing: 0.18em;
  color: var(--paper-dim);
  background: none;
  border: 1px solid var(--ink-600);
  border-radius: 3px;
  padding: 7px 18px;
  cursor: pointer;
  transition: all 0.2s;
}

.tab:hover {
  color: var(--paper);
  border-color: var(--gold-dim);
}

.tab.on {
  color: var(--gold);
  border-color: var(--gold-dim);
  background: rgba(201, 168, 106, 0.08);
}

.user-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12.5px;
}

.user-table th {
  text-align: left;
  padding: 10px 12px;
  color: var(--paper-faint);
  font-weight: 400;
  letter-spacing: 0.12em;
  border-bottom: 1px solid var(--border);
}

.user-table td {
  padding: 10px 12px;
  color: var(--paper-dim);
  border-bottom: 1px solid rgba(38, 55, 90, 0.5);
}

.role-pill {
  font-size: 11px;
  letter-spacing: 0.14em;
  padding: 2px 8px;
  border-radius: 2px;
  border: 1px solid var(--ink-600);
  color: var(--paper-dim);
}

.role-pill.pro {
  color: var(--gold);
  border-color: var(--gold-dim);
}

.role-pill.enterprise {
  color: var(--seal-bright);
  border-color: var(--seal);
}

.dim {
  color: var(--paper-faint);
}
</style>
