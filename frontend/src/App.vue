<script setup>
import { onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from './stores/auth'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()

onMounted(() => {
  if (auth.isLoggedIn && !auth.user) {
    auth.fetchMe().catch(() => {})
  }
})

function logout() {
  auth.logout()
  router.push({ name: 'login' })
}
</script>

<template>
  <div class="shell">
    <header v-if="auth.isLoggedIn" class="topbar">
      <router-link class="brand" to="/">
        <span class="seal-mark">谋</span>
        <span class="brand-text">谋谈<em>MouTalk</em></span>
      </router-link>
      <nav class="nav">
        <router-link to="/" :class="{ active: route.name === 'lobby' }">场景大厅</router-link>
        <router-link to="/reports" :class="{ active: route.name === 'reports' || route.name === 'report-detail' }">复盘报告</router-link>
        <router-link to="/trends" :class="{ active: route.name === 'trends' }">进步曲线</router-link>
        <router-link to="/profile" :class="{ active: route.name === 'profile' }">个人中心</router-link>
        <router-link to="/payment" :class="{ active: route.name === 'payment' }">升级 Pro</router-link>
        <router-link v-if="auth.user?.is_admin" to="/admin" :class="{ active: route.name === 'admin' }">管理后台</router-link>
      </nav>
      <div class="user">
        <span class="role-badge" :class="auth.isPro ? 'pro' : 'free'">
          {{ auth.isPro ? 'PRO' : 'FREE' }}
        </span>
        <span class="email">{{ auth.user?.email }}</span>
        <button class="ghost-btn" @click="logout">退 出</button>
      </div>
    </header>

    <main class="main">
      <router-view v-slot="{ Component }">
        <transition name="page" mode="out-in">
          <component :is="Component" />
        </transition>
      </router-view>
    </main>

    <footer v-if="auth.isLoggedIn" class="foot">
      <span>谋定而后动 · 知止而有得</span>
    </footer>
  </div>
</template>

<style scoped>
.shell {
  position: relative;
  z-index: 2;
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}

.topbar {
  display: flex;
  align-items: center;
  gap: 36px;
  padding: 14px 40px;
  border-bottom: 1px solid var(--border);
  background: rgba(11, 18, 32, 0.78);
  backdrop-filter: blur(10px);
  position: sticky;
  top: 0;
  z-index: 10;
}

.brand {
  display: flex;
  align-items: center;
  gap: 12px;
}

.brand-text {
  font-family: var(--font-display);
  font-size: 21px;
  font-weight: 700;
  letter-spacing: 0.3em;
  color: var(--paper);
}

.brand-text em {
  font-style: normal;
  font-family: var(--font-body);
  font-size: 11px;
  font-weight: 400;
  letter-spacing: 0.22em;
  color: var(--gold-dim);
  margin-left: 8px;
  text-transform: uppercase;
}

.nav {
  display: flex;
  gap: 30px;
  margin-left: 12px;
}

.nav a {
  position: relative;
  font-size: 14px;
  letter-spacing: 0.22em;
  color: var(--paper-dim);
  padding: 6px 2px;
  transition: color 0.2s;
}

.nav a:hover {
  color: var(--paper);
}

.nav a.active {
  color: var(--paper);
}

.nav a.active::after {
  content: '';
  position: absolute;
  left: 0;
  right: 0;
  bottom: -2px;
  height: 1px;
  background: var(--seal);
}

.user {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 14px;
}

.role-badge {
  font-size: 10px;
  letter-spacing: 0.24em;
  padding: 3px 9px;
  border-radius: 2px;
  border: 1px solid;
}

.role-badge.free {
  color: var(--paper-dim);
  border-color: var(--ink-600);
}

.role-badge.pro {
  color: var(--gold);
  border-color: var(--gold-dim);
}

.email {
  font-size: 13px;
  color: var(--paper-dim);
  max-width: 220px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ghost-btn {
  font-family: var(--font-body);
  font-size: 12px;
  letter-spacing: 0.22em;
  color: var(--paper-faint);
  background: none;
  border: 1px solid var(--ink-600);
  border-radius: 2px;
  padding: 5px 14px;
  cursor: pointer;
  transition: all 0.2s;
}

.ghost-btn:hover {
  color: var(--seal-bright);
  border-color: var(--seal);
}

.main {
  flex: 1;
  display: flex;
  flex-direction: column;
}

.foot {
  padding: 22px 0 30px;
  text-align: center;
  font-family: var(--font-display);
  font-size: 12px;
  letter-spacing: 0.5em;
  color: var(--paper-faint);
  border-top: 1px solid var(--border);
  opacity: 0.8;
}
</style>
