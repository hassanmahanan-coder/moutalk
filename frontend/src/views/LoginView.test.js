import { describe, expect, it, vi } from 'vitest'
import { defineComponent, h } from 'vue'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn() }),
}))

vi.mock('../stores/auth', () => ({
  useAuthStore: () => ({
    login: vi.fn().mockResolvedValue(undefined),
    isLoggedIn: false,
  }),
}))

const { ElMessage } = vi.hoisted(() => ({
  ElMessage: { success: vi.fn(), warning: vi.fn(), error: vi.fn() },
}))
vi.mock('element-plus', () => ({ ElMessage }))

const ElInput = defineComponent({
  props: ['modelValue', 'type'],
  emits: ['update:modelValue'],
  setup(_, { emit, attrs }) {
    return () =>
      h('input', {
        value: attrs.modelValue ?? undefined,
        onInput: (e) => emit('update:modelValue', e.target.value),
      })
  },
})
const ElButton = defineComponent({
  props: ['type', 'loading'],
  emits: ['click'],
  setup(_, { emit, slots }) {
    return () => h('button', { class: 'el-btn', onClick: () => emit('click') }, slots.default?.())
  },
})
const ElForm = defineComponent({
  setup(_, { slots, attrs }) {
    return () => h('form', attrs, slots.default?.())
  },
})
const ElFormItem = defineComponent({
  props: ['label'],
  setup(props, { slots }) {
    return () => h('div', [h('label', props.label), slots.default?.()])
  },
})

import LoginView from './LoginView.vue'

function mountLogin() {
  setActivePinia(createPinia())
  return mount(LoginView, {
    global: {
      components: { ElInput, ElButton, ElForm, ElFormItem },
      stubs: { 'router-link': true },
    },
  })
}

describe('LoginView', () => {
  it('渲染标题与账号输入框', () => {
    const wrapper = mountLogin()
    expect(wrapper.find('h1').text()).toBe('谋谈')
    expect(wrapper.text()).toContain('邮箱或用户名')
  })

  it('空表单提交提示输入账号与密码', async () => {
    const wrapper = mountLogin()
    await wrapper.find('.submit-btn').trigger('click')
    expect(ElMessage.warning).toHaveBeenCalledWith('请输入账号与密码')
  })

  it('填入账号密码后提交调用登录', async () => {
    const wrapper = mountLogin()
    const inputs = wrapper.findAll('input')
    await inputs[0].setValue('mou_talker')
    await inputs[1].setValue('password123')
    await wrapper.find('.submit-btn').trigger('click')
    await wrapper.vm.$nextTick()
    await wrapper.vm.$nextTick()
    expect(ElMessage.success).toHaveBeenCalledWith('登录成功，入局')
  })
})
