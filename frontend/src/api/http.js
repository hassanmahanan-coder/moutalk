import axios from 'axios'
import { ElMessage } from 'element-plus'

const http = axios.create({ baseURL: '/api', timeout: 20000 })

http.interceptors.request.use((config) => {
  const token = localStorage.getItem('mt_access')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

http.interceptors.response.use(
  (res) => res.data,
  (err) => {
    const detail = err.response?.data?.detail
    const message = detail?.message || err.message || '请求失败'
    if (err.response?.status === 401 && !location.pathname.startsWith('/login')) {
      localStorage.removeItem('mt_access')
      localStorage.removeItem('mt_refresh')
      location.href = '/login'
    } else {
      ElMessage.error(message)
    }
    return Promise.reject({ ...err, code: detail?.code || 'REQUEST_FAILED', message })
  }
)

export default http
