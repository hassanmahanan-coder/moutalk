import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('../api', () => ({
  authApi: {
    register: vi.fn(),
    login: vi.fn(),
    verify: vi.fn(),
    me: vi.fn(),
  },
}))

import { authApi } from '../api'
import { useAuthStore } from './auth'

describe('auth store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    vi.clearAllMocks()
  })

  it('login 保存 token 并缓存用户', async () => {
    authApi.login.mockResolvedValue({
      access_token: 'at-1',
      refresh_token: 'rt-1',
      user: { id: 'u1', email: 'a@b.com', username: 'mou', role: 'free' },
    })
    const store = useAuthStore()
    await store.login('mou', 'password123')
    expect(authApi.login).toHaveBeenCalledWith('mou', 'password123')
    expect(store.accessToken).toBe('at-1')
    expect(localStorage.getItem('mt_access')).toBe('at-1')
    expect(store.user.username).toBe('mou')
  })

  it('register 转发 username/email/password', async () => {
    authApi.register.mockResolvedValue({ code: '123456' })
    const store = useAuthStore()
    const data = await store.register('mou', 'a@b.com', 'password123')
    expect(authApi.register).toHaveBeenCalledWith('mou', 'a@b.com', 'password123')
    expect(data.code).toBe('123456')
  })

  it('isPro 判断角色', async () => {
    const store = useAuthStore()
    store.user = { role: 'pro' }
    expect(store.isPro).toBe(true)
    store.user = { role: 'free' }
    expect(store.isPro).toBe(false)
  })

  it('logout 清空 token 与用户', () => {
    const store = useAuthStore()
    store.setTokens('at', 'rt')
    store.user = { role: 'free' }
    store.logout()
    expect(store.accessToken).toBe('')
    expect(store.user).toBeNull()
    expect(localStorage.getItem('mt_access')).toBeNull()
  })
})
