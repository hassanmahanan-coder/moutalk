import { describe, expect, it, vi } from 'vitest'
import { defineComponent, h } from 'vue'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn() }),
}))

const { ElMessage } = vi.hoisted(() => ({
  ElMessage: { success: vi.fn(), warning: vi.fn(), error: vi.fn() },
}))
vi.mock('element-plus', () => ({ ElMessage }))

vi.mock('../stores/auth', () => ({
  useAuthStore: () => ({ isLoggedIn: false }),
}))

vi.mock('../api', () => ({
  authApi: { register: vi.fn().mockResolvedValue({ code: '123456' }) },
}))

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
const ElCheckbox = defineComponent({
  props: ['modelValue'],
  emits: ['update:modelValue'],
  setup(_, { emit, slots }) {
    return () => h('input', { type: 'checkbox', onChange: (e) => emit('update:modelValue', e.target.checked) }, slots.default?.())
  },
})

import RegisterView from './RegisterView.vue'

function mountRegister() {
  setActivePinia(createPinia())
  return mount(RegisterView, {
    global: {
      components: { ElInput, ElButton, ElForm, ElFormItem, ElCheckbox },
      stubs: { 'router-link': true },
    },
  })
}

describe('RegisterView', () => {
  it('渲染用户名输入框', () => {
    const wrapper = mountRegister()
    expect(wrapper.text()).toContain('用户名')
  })

  it('非法用户名提交时提示格式错误', async () => {
    const wrapper = mountRegister()
    const inputs = wrapper.findAll('input')
    await inputs[0].setValue('1bad') // 数字开头
    await inputs[1].setValue('a@b.com')
    await inputs[2].setValue('password123')
    await inputs[3].setValue('password123')
    // 勾选协议
    const cb = wrapper.findAll('input[type="checkbox"]')[0]
    await cb.setValue(true)
    await wrapper.find('.submit-btn').trigger('click')
    expect(ElMessage.warning).toHaveBeenCalledWith('用户名需 3-20 位，字母开头，可含数字与下划线')
  })

  it('空表单提交提示填写', async () => {
    const wrapper = mountRegister()
    await wrapper.find('.submit-btn').trigger('click')
    expect(ElMessage.warning).toHaveBeenCalledWith('请填写用户名、邮箱与密码')
  })

  it('密码不一致提示', async () => {
    const wrapper = mountRegister()
    const inputs = wrapper.findAll('input')
    await inputs[0].setValue('mou_talker')
    await inputs[1].setValue('a@b.com')
    await inputs[2].setValue('password123')
    await inputs[3].setValue('different456')
    await wrapper.find('.submit-btn').trigger('click')
    expect(ElMessage.warning).toHaveBeenCalledWith('两次输入的密码不一致')
  })
})
