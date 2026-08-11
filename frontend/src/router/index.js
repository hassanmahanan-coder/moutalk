import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const routes = [
  { path: '/login', name: 'login', component: () => import('../views/LoginView.vue'), meta: { guest: true, title: '登录' } },
  { path: '/register', name: 'register', component: () => import('../views/RegisterView.vue'), meta: { guest: true, title: '注册' } },
  { path: '/terms/:kind?', name: 'terms', component: () => import('../views/TermsView.vue'), meta: { guest: true, title: '用户协议' } },
  { path: '/', name: 'lobby', component: () => import('../views/LobbyView.vue'), meta: { title: '场景大厅' } },
  { path: '/scenario/create', name: 'scenario-create', component: () => import('../views/ScenarioCreateView.vue'), meta: { title: '自定义场景' } },
  { path: '/room/:id', name: 'room', component: () => import('../views/RoomView.vue'), meta: { title: '谈判室' } },
  { path: '/reports', name: 'reports', component: () => import('../views/ReportsView.vue'), meta: { title: '复盘报告' } },
  { path: '/reports/compare/:ids', name: 'report-compare', component: () => import('../views/ReportCompareView.vue'), meta: { title: '报告对比' } },
  { path: '/reports/:id', name: 'report-detail', component: () => import('../views/ReportDetailView.vue'), meta: { title: '报告详情' } },
  { path: '/trends', name: 'trends', component: () => import('../views/TrendsView.vue'), meta: { title: '进步曲线' } },
  { path: '/admin', name: 'admin', component: () => import('../views/AdminView.vue'), meta: { title: '管理后台' } },
  { path: '/payment', name: 'payment', component: () => import('../views/PaymentView.vue'), meta: { title: '升级 Pro' } },
  { path: '/profile', name: 'profile', component: () => import('../views/ProfileView.vue'), meta: { title: '个人中心' } },
  { path: '/:pathMatch(.*)*', redirect: '/' },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to) => {
  const auth = useAuthStore()
  if (to.meta.guest && auth.isLoggedIn) return { name: 'lobby' }
  if (!to.meta.guest && !auth.isLoggedIn) return { name: 'login' }
  document.title = to.meta.title ? `${to.meta.title} · 谋谈 MouTalk` : '谋谈 MouTalk'
  return true
})

export default router
