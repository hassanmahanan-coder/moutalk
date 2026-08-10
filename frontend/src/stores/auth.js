import { defineStore } from 'pinia'
import { authApi } from '../api'

const ACCESS_KEY = 'mt_access'
const REFRESH_KEY = 'mt_refresh'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    accessToken: localStorage.getItem(ACCESS_KEY) || '',
    refreshToken: localStorage.getItem(REFRESH_KEY) || '',
    user: null,
  }),
  getters: {
    isLoggedIn: (s) => !!s.accessToken,
    isPro: (s) => s.user?.role === 'pro' || s.user?.role === 'enterprise',
  },
  actions: {
    setTokens(access, refresh) {
      this.accessToken = access
      this.refreshToken = refresh
      localStorage.setItem(ACCESS_KEY, access)
      localStorage.setItem(REFRESH_KEY, refresh)
    },
    async login(account, password) {
      const data = await authApi.login(account, password)
      this.setTokens(data.access_token, data.refresh_token)
      this.user = data.user
    },
    async register(username, email, password) {
      return authApi.register(username, email, password)
    },
    async verify(email, code) {
      await authApi.verify(email, code)
    },
    async fetchMe() {
      this.user = await authApi.me()
    },
    async refresh() {
      const data = await authApi.refresh(this.refreshToken)
      this.setTokens(data.access_token, data.refresh_token || data.access_token)
    },
    logout() {
      this.accessToken = ''
      this.refreshToken = ''
      this.user = null
      localStorage.removeItem(ACCESS_KEY)
      localStorage.removeItem(REFRESH_KEY)
    },
  },
})
