<script setup>
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { authApi, notificationApi, quotaApi } from '../api'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const auth = useAuthStore()
const quota = ref(null)
const notifications = ref([])
const notifLoading = ref(false)
const filterType = ref('all')
const pwdOpen = ref(false)
const pwdLoading = ref(false)
const pwdForm = reactive({ oldPassword: '', newPassword: '', confirm: '' })

const TYPE_LABEL = { report: '复盘报告', payment: '支付', system: '系统' }

async function changePassword() {
  if (!pwdForm.oldPassword || !pwdForm.newPassword) {
    ElMessage.warning('请填写当前密码与新密码')
    return
  }
  if (pwdForm.newPassword.length < 8) {
    ElMessage.warning('新密码至少 8 位')
    return
  }
  if (pwdForm.newPassword !== pwdForm.confirm) {
    ElMessage.warning('两次输入的新密码不一致')
    return
  }
  pwdLoading.value = true
  try {
    await authApi.changePassword(pwdForm.oldPassword, pwdForm.newPassword)
    ElMessage.success('密码已修改，下次登录请使用新密码')
    pwdOpen.value = false
    pwdForm.oldPassword = ''
    pwdForm.newPassword = ''
    pwdForm.confirm = ''
  } catch {
    /* 拦截器已提示 */
  } finally {
    pwdLoading.value = false
  }
}

async function loadNotifications() {
  notifLoading.value = true
  try {
    const n = await notificationApi.list(true, filterType.value === 'all' ? null : filterType.value)
    notifications.value = n.items
  } catch {
    /* 拦截器已提示 */
  } finally {
    notifLoading.value = false
  }
}

onMounted(async () => {
  try {
    quota.value = await quotaApi.me()
  } catch {
    /* 拦截器已提示 */
  }
  await loadNotifications()
})

function switchFilter(t) {
  filterType.value = t
  loadNotifications()
}

async function markRead(n) {
  try {
    await notificationApi.markRead(n.id)
    notifications.value = notifications.value.filter((x) => x.id !== n.id)
  } catch {
    /* 拦截器已提示 */
  }
}

function openReport(n) {
  const rid = n.payload?.report_id
  if (rid) router.push({ name: 'report-detail', params: { id: rid } })
}

function logout() {
  auth.logout()
  router.push({ name: 'login' })
}

function expireHint() {
  const exp = quota.value?.expire_at
  if (!exp) return ''
  const days = Math.ceil((new Date(exp) - Date.now()) / 86400000)
  if (days <= 0) return '订阅已到期，请续费'
  if (days <= 7) return `订阅将于 ${days} 天后到期，请及时续费`
  return `订阅有效期至 ${new Date(exp).toLocaleDateString('zh-CN')}`
}
</script>

<template>
  <div class="profile">
    <div class="head">
      <p class="kicker">个人中心</p>
      <h1>案卷 · 名册</h1>
      <p class="sub">{{ auth.user?.email }}</p>
    </div>
    <hr class="gold-rule" />

    <div v-if="quota" class="grid">
      <section class="sec">
        <h2>账号与订阅</h2>
        <div class="card">
          <div class="row">
            <span class="lbl">角色</span>
            <span class="val role" :class="quota.role">{{ quota.role === 'free' ? '免费用户' : quota.role === 'pro' ? 'Pro 订阅' : '企业版' }}</span>
          </div>
          <div class="row">
            <span class="lbl">次数</span>
            <span class="val">{{ quota.limit ? `每场景 ${quota.limit} 次/月` : '无限次数' }}</span>
          </div>
          <div v-if="quota.expire_at" class="row">
            <span class="lbl">订阅</span>
            <span class="val">{{ expireHint() }}</span>
          </div>
          <div class="actions">
            <el-button v-if="quota.role === 'free'" type="primary" size="small" @click="router.push({ name: 'payment' })">升级 Pro</el-button>
            <el-button v-else plain size="small" @click="router.push({ name: 'payment' })">续费</el-button>
            <el-button plain size="small" @click="router.push({ name: 'reports' })">谈判历史</el-button>
            <el-button plain size="small" @click="pwdOpen = !pwdOpen">修改密码</el-button>
            <el-button plain size="small" @click="logout">退出登录</el-button>
          </div>
        </div>
      </section>

      <section class="sec">
        <h2>本月额度</h2>
        <div class="quota-list">
          <div v-for="s in quota.scenarios" :key="s.scenario_id" class="quota-row">
            <span class="q-name">{{ s.title }}</span>
            <div class="q-bar">
              <i :style="{ width: `${s.limit ? Math.min(100, (s.used / s.limit) * 100) : 0}%` }"></i>
            </div>
            <span class="q-num">{{ s.limit ? `${s.used}/${s.limit}` : '∞' }}</span>
          </div>
        </div>
      </section>

      <section v-if="pwdOpen" class="sec">
        <h2>修改密码</h2>
        <div class="card">
          <el-input v-model="pwdForm.oldPassword" type="password" show-password placeholder="当前密码" size="large" />
          <el-input v-model="pwdForm.newPassword" type="password" show-password placeholder="新密码（至少 8 位）" size="large" />
          <el-input v-model="pwdForm.confirm" type="password" show-password placeholder="确认新密码" size="large" />
          <div class="pwd-actions">
            <el-button type="primary" :loading="pwdLoading" @click="changePassword">确认修改</el-button>
            <el-button plain @click="pwdOpen = false">取消</el-button>
          </div>
        </div>
      </section>
    </div>

    <section class="sec">
      <h2>通知 <span v-if="notifications.length" class="badge">{{ notifications.length }}</span></h2>
      <div class="filter-row">
        <button v-for="t in ['all', 'report', 'payment', 'system']" :key="t" class="f-tab" :class="{ on: filterType === t }" @click="switchFilter(t)">
          {{ t === 'all' ? '全部' : TYPE_LABEL[t] || t }}
        </button>
      </div>
      <div v-if="notifLoading" class="empty">加载中……</div>
      <div v-else-if="!notifications.length" class="empty">暂无未读通知</div>
      <div v-else class="notif-list">
        <div v-for="n in notifications" :key="n.id" class="notif" @click="n.payload?.report_id ? openReport(n) : markRead(n)">
          <span class="n-type" :class="n.type">{{ TYPE_LABEL[n.type] || n.type }}</span>
          <span class="n-title">{{ n.title }}</span>
          <span class="n-time">{{ n.created_at ? new Date(n.created_at).toLocaleString('zh-CN') : '' }}</span>
          <button class="n-read" @click.stop="markRead(n)">标已读</button>
        </div>
      </div>
    </section>
  </div>
</template>

<style scoped>
.profile {
  max-width: 960px;
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
  letter-spacing: 0.1em;
  color: var(--paper-faint);
}

.grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 26px;
  margin-bottom: 30px;
}

.sec {
  margin-bottom: 30px;
}

.sec h2 {
  font-size: 17px;
  letter-spacing: 0.34em;
  color: var(--paper-dim);
  padding-bottom: 10px;
  border-bottom: 1px solid var(--border);
  margin: 0 0 16px;
}

.badge {
  display: inline-block;
  min-width: 18px;
  text-align: center;
  font-size: 11px;
  color: var(--seal-bright);
  border: 1px solid var(--seal);
  border-radius: 9px;
  padding: 0 6px;
  vertical-align: middle;
}

.card {
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 18px 20px;
  background: rgba(17, 28, 49, 0.5);
}

.row {
  display: flex;
  justify-content: space-between;
  padding: 9px 0;
  border-bottom: 1px solid rgba(38, 55, 90, 0.5);
}

.row:last-of-type {
  border-bottom: none;
}

.lbl {
  font-size: 12px;
  color: var(--paper-faint);
  letter-spacing: 0.2em;
}

.val {
  font-size: 13px;
  color: var(--paper);
}

.val.role.pro {
  color: var(--gold);
}

.actions {
  display: flex;
  gap: 10px;
  margin-top: 16px;
  flex-wrap: wrap;
}

.quota-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.quota-row {
  display: flex;
  align-items: center;
  gap: 14px;
}

.q-name {
  width: 130px;
  font-size: 13px;
  color: var(--paper-dim);
  letter-spacing: 0.06em;
  flex-shrink: 0;
}

.q-bar {
  flex: 1;
  height: 8px;
  background: var(--ink-700);
  border-radius: 4px;
  overflow: hidden;
}

.q-bar i {
  display: block;
  height: 100%;
  background: linear-gradient(90deg, var(--gold-dim), var(--gold));
}

.q-num {
  width: 52px;
  text-align: right;
  font-family: var(--font-display);
  font-size: 14px;
  color: var(--gold);
}

.notif-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.filter-row {
  display: flex;
  gap: 8px;
  margin-bottom: 14px;
}

.f-tab {
  font-family: var(--font-body);
  font-size: 12px;
  letter-spacing: 0.14em;
  color: var(--paper-dim);
  background: none;
  border: 1px solid var(--ink-600);
  border-radius: 3px;
  padding: 5px 14px;
  cursor: pointer;
  transition: all 0.2s;
}

.f-tab:hover {
  color: var(--paper);
  border-color: var(--gold-dim);
}

.f-tab.on {
  color: var(--gold);
  border-color: var(--gold-dim);
  background: rgba(201, 168, 106, 0.08);
}

.notif {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  border: 1px solid var(--border);
  border-radius: 4px;
  cursor: pointer;
  transition: border-color 0.2s;
}

.notif:hover {
  border-color: var(--gold-dim);
}

.n-type {
  font-size: 10px;
  letter-spacing: 0.14em;
  padding: 2px 8px;
  border-radius: 2px;
  border: 1px solid;
  flex-shrink: 0;
}

.n-type.report {
  color: var(--gold);
  border-color: rgba(201, 168, 106, 0.4);
}

.n-type.payment {
  color: var(--jade);
  border-color: rgba(111, 174, 147, 0.4);
}

.n-type.system {
  color: var(--paper-faint);
  border-color: var(--ink-600);
}

.n-title {
  flex: 1;
  font-size: 13px;
  color: var(--paper);
}

.n-time {
  font-size: 11px;
  color: var(--paper-faint);
}

.n-read {
  font-family: var(--font-body);
  font-size: 11px;
  letter-spacing: 0.1em;
  color: var(--seal-bright);
  background: none;
  border: 1px solid rgba(83, 152, 127, 0.4);
  border-radius: 2px;
  padding: 3px 10px;
  cursor: pointer;
}

.empty {
  padding: 30px 0;
  text-align: center;
  color: var(--paper-faint);
  letter-spacing: 0.2em;
  font-size: 13px;
}
</style>
