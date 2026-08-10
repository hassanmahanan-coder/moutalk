import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('./http', () => ({
  default: {
    get: vi.fn(() => Promise.resolve({})),
    post: vi.fn(() => Promise.resolve({})),
    patch: vi.fn(() => Promise.resolve({})),
  },
}))

import http from './http'
import {
  adminApi,
  authApi,
  notificationApi,
  paymentApi,
  reportApi,
  scenarioApi,
  sessionApi,
} from './index'

describe('api layer', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('authApi.register 携带 username/email/password', async () => {
    await authApi.register('mou_talker', 'a@b.com', 'password123')
    expect(http.post).toHaveBeenCalledWith('/auth/register', {
      username: 'mou_talker',
      email: 'a@b.com',
      password: 'password123',
    })
  })

  it('authApi.login 使用 account 字段', async () => {
    await authApi.login('mou_talker', 'password123')
    expect(http.post).toHaveBeenCalledWith('/auth/login', {
      account: 'mou_talker',
      password: 'password123',
    })
  })

  it('notificationApi.list 支持 type 筛选', async () => {
    await notificationApi.list(true, 'report')
    expect(http.get).toHaveBeenCalledWith('/notifications?unread=true&type=report')
    await notificationApi.list(false, null)
    expect(http.get).toHaveBeenCalledWith('/notifications')
  })

  it('paymentApi.createOrder 携带类型与 target', async () => {
    await paymentApi.createOrder('scenario', 'it_procurement')
    expect(http.post).toHaveBeenCalledWith('/payment/orders', {
      type: 'scenario',
      target_id: 'it_procurement',
    })
    await paymentApi.getOrder('abc-123')
    expect(http.get).toHaveBeenCalledWith('/payment/orders/abc-123')
  })

  it('adminApi 用户管理接口路径正确', async () => {
    await adminApi.users()
    expect(http.get).toHaveBeenCalledWith('/admin/users')
    await adminApi.updateUserRole('u-1', { role: 'pro' })
    expect(http.patch).toHaveBeenCalledWith('/admin/users/u-1', { role: 'pro' })
    await adminApi.updateUserRole('u-1', { is_admin: true })
    expect(http.patch).toHaveBeenCalledWith('/admin/users/u-1', { is_admin: true })
  })

  it('sessionApi/reportApi/scenarioApi 基础路径', async () => {
    await sessionApi.create('salary')
    expect(http.post).toHaveBeenCalledWith('/sessions', { scenario_id: 'salary' })
    await reportApi.trends()
    expect(http.get).toHaveBeenCalledWith('/reports/trends')
    await scenarioApi.detail('supplier')
    expect(http.get).toHaveBeenCalledWith('/scenarios/supplier')
  })
})
