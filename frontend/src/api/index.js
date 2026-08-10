import http from './http'

export const authApi = {
  register: (username, email, password) => http.post('/auth/register', { username, email, password }),
  login: (account, password) => http.post('/auth/login', { account, password }),
  verify: (email, code) => http.post('/auth/verify', { email, code }),
  refresh: (refreshToken) => http.post('/auth/refresh', { refresh_token: refreshToken }),
  me: () => http.get('/auth/me'),
}

export const scenarioApi = {
  list: () => http.get('/scenarios'),
  detail: (id) => http.get(`/scenarios/${id}`),
}

export const sessionApi = {
  create: (scenarioId) => http.post('/sessions', { scenario_id: scenarioId }),
  list: () => http.get('/sessions'),
  replay: (id) => http.get(`/sessions/${id}/replay`),
}

export const reportApi = {
  list: () => http.get('/reports'),
  detail: (id) => http.get(`/reports/${id}`),
  compare: (ids) => http.get(`/reports/compare?ids=${ids.join(',')}`),
  trends: () => http.get('/reports/trends'),
  // 下载 PDF：blob 响应（绕过统一 res.data 拦截）；未就绪抛 {code:'PDF_NOT_READY'}
  async downloadPdf(id) {
    const res = await http.get(`/reports/${id}/pdf`, { responseType: 'blob' })
    const name = `moutalk-report-${id}.pdf`
    const url = URL.createObjectURL(new Blob([res]))
    const a = document.createElement('a')
    a.href = url
    a.download = name
    a.click()
    URL.revokeObjectURL(url)
  },
}

export const paymentApi = {
  createOrder: (type, targetId = null) =>
    http.post('/payment/orders', { type, target_id: targetId }),
  getOrder: (id) => http.get(`/payment/orders/${id}`),
}

export const quotaApi = {
  me: () => http.get('/quota/me'),
}

export const notificationApi = {
  list: (unread = false, type = null) =>
    http.get(`/notifications${unread ? '?unread=true' : ''}${type ? `&type=${type}` : ''}`),
  markRead: (id) => http.patch(`/notifications/${id}`),
}

export const adminApi = {
  stats: () => http.get('/admin/stats'),
  tacticStats: () => http.get('/admin/tactic-stats'),
  connections: () => http.get('/admin/connections'),
}
