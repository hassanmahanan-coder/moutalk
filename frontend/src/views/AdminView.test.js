import { describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('../stores/auth', () => ({
  useAuthStore: () => ({ user: { id: 'admin-1', is_admin: true }, isLoggedIn: true }),
}))

const { ElMessage } = vi.hoisted(() => ({
  ElMessage: { success: vi.fn(), warning: vi.fn(), error: vi.fn() },
}))
vi.mock('element-plus', () => ({ ElMessage }))

const { adminApi } = vi.hoisted(() => ({
  adminApi: {
    stats: vi.fn().mockResolvedValue({ users_count: 3, sessions_count: 10, reports_count: 5, monthly_reports: 2, pro_users: 1 }),
    tacticStats: vi.fn().mockResolvedValue({ tactics: { anchor: 2 }, total: 2 }),
    connections: vi.fn().mockResolvedValue({ online: 1 }),
    users: vi.fn().mockResolvedValue({
      items: [
        { id: 'u1', email: 'a@b.com', username: 'alice', role: 'free', is_admin: false, banned: false },
        { id: 'u2', email: 'c@d.com', username: 'bob', role: 'pro', is_admin: true, banned: true },
      ],
    }),
    updateUserRole: vi.fn().mockImplementation((id, patch) => Promise.resolve({ id, ...patch })),
  },
}))
vi.mock('../api', () => ({ adminApi }))

import AdminView from './AdminView.vue'

function mountAdmin() {
  setActivePinia(createPinia())
  return mount(AdminView, {
    global: {
      stubs: {
        'el-button': {
          props: ['type', 'size', 'plain'],
          emits: ['click'],
          template: '<button class="el-btn-stub" @click="$emit(\'click\')"><slot /></button>',
        },
        'el-select': true,
        'el-option': true,
      },
    },
  })
}

describe('AdminView', () => {
  it('加载运营概览 KPI', async () => {
    const wrapper = mountAdmin()
    await flushPromises()
    expect(wrapper.text()).toContain('3') // 注册用户
    expect(wrapper.text()).toContain('10') // 谈判会话
  })

  it('切换到用户管理加载用户列表', async () => {
    const wrapper = mountAdmin()
    await flushPromises()
    const tabs = wrapper.findAll('.tab')
    await tabs[1].trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('alice')
    expect(wrapper.text()).toContain('已封禁')
  })

  it('封禁按钮调用接口并提示', async () => {
    const wrapper = mountAdmin()
    await flushPromises()
    await wrapper.findAll('.tab')[1].trigger('click')
    await flushPromises()
    const banButtons = wrapper.findAll('button').filter((b) => b.text() === '封禁')
    await banButtons[0].trigger('click')
    await flushPromises()
    expect(adminApi.updateUserRole).toHaveBeenCalledWith('u1', { banned: true })
    expect(ElMessage.success).toHaveBeenCalled()
  })

  it('非管理员无访问权限提示', async () => {
    const wrapper = mountAdmin()
    adminApi.stats.mockRejectedValueOnce({ code: 'FORBIDDEN' })
    await flushPromises()
  })
})
