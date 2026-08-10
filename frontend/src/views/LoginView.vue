<script setup>
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { authApi } from '../api'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const auth = useAuthStore()
const form = reactive({ account: '', password: '' })
const loading = ref(false)
const forgotOpen = ref(false)
const forgotEmail = ref('')
const forgotStep = ref(1) // 1=输邮箱 2=输验证码+新密码
const forgotCode = ref('')
const forgotPwd = ref('')
const forgotLoading = ref(false)

async function submit() {
  if (!form.account || !form.password) {
    ElMessage.warning('请输入账号与密码')
    return
  }
  loading.value = true
  try {
    await auth.login(form.account, form.password)
    ElMessage.success('登录成功，入局')
    router.push({ name: 'lobby' })
  } catch {
    /* 拦截器已提示 */
  } finally {
    loading.value = false
  }
}

async function sendForgotCode() {
  if (!forgotEmail.value) {
    ElMessage.warning('请输入注册邮箱')
    return
  }
  forgotLoading.value = true
  try {
    await authApi.forgotPassword(forgotEmail.value)
    forgotStep.value = 2
    ElMessage.success('验证码已发送至邮箱')
  } catch {
    /* 拦截器已提示 */
  } finally {
    forgotLoading.value = false
  }
}

async function resetPassword() {
  if (forgotCode.value.length !== 6) {
    ElMessage.warning('请输入 6 位验证码')
    return
  }
  if (forgotPwd.value.length < 8) {
    ElMessage.warning('新密码至少 8 位')
    return
  }
  forgotLoading.value = true
  try {
    await authApi.resetPassword(forgotEmail.value, forgotCode.value, forgotPwd.value)
    ElMessage.success('密码已重置，请用新密码登录')
    forgotOpen.value = false
    forgotStep.value = 1
  } catch {
    /* 拦截器已提示 */
  } finally {
    forgotLoading.value = false
  }
}
</script>

<template>
  <div class="auth-page">
    <div class="auth-card">
      <div class="auth-head">
        <span class="seal-mark large">谋</span>
        <h1>谋谈</h1>
        <p>多轮深度谈判模拟 · 与 AI 对弈，知己知彼</p>
      </div>
      <hr class="gold-rule" />
      <el-form label-position="top" @submit.prevent="submit">
        <el-form-item label="邮箱或用户名">
          <el-input v-model="form.account" placeholder="you@example.com 或用户名" size="large" />
        </el-form-item>
        <el-form-item label="密码">
          <el-input v-model="form.password" type="password" show-password placeholder="至少 8 位" size="large" @keyup.enter="submit" />
        </el-form-item>
        <el-button class="submit-btn" type="primary" size="large" :loading="loading" @click="submit">
          入 局
        </el-button>
        <div class="form-foot">
          <span class="forgot" @click="forgotOpen = !forgotOpen">忘记密码</span>
        </div>
      </el-form>

      <div v-if="forgotOpen" class="forgot-box">
        <template v-if="forgotStep === 1">
          <p class="forgot-title">找回密码</p>
          <el-input v-model="forgotEmail" placeholder="注册邮箱" size="large" />
          <el-button class="submit-btn" type="primary" size="large" :loading="forgotLoading" @click="sendForgotCode">
            发送验证码
          </el-button>
        </template>
        <template v-else>
          <p class="forgot-title">重置密码</p>
          <el-input v-model="forgotCode" placeholder="6 位验证码" size="large" />
          <el-input v-model="forgotPwd" type="password" show-password placeholder="新密码（至少 8 位）" size="large" />
          <el-button class="submit-btn" type="primary" size="large" :loading="forgotLoading" @click="resetPassword">
            重置密码
          </el-button>
        </template>
      </div>
      <p class="auth-foot">
        尚无席位？
        <router-link to="/register">注册账号</router-link>
      </p>
    </div>
  </div>
</template>

<style scoped>
.auth-page {
  min-height: 100vh;
  display: grid;
  place-items: center;
  padding: 40px 20px;
}

.auth-card {
  width: 400px;
  max-width: 100%;
  background: linear-gradient(180deg, rgba(22, 34, 58, 0.55), rgba(13, 22, 38, 0.75));
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 42px 44px 32px;
  box-shadow: var(--shadow-float);
  backdrop-filter: blur(8px);
  animation: rise 0.5s ease both;
}

@keyframes rise {
  from {
    opacity: 0;
    transform: translateY(16px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.auth-head {
  text-align: center;
  margin-bottom: 26px;
}

.seal-mark.large {
  width: 52px;
  height: 52px;
  font-size: 28px;
  border-radius: 8px;
}

.auth-head h1 {
  margin: 16px 0 6px;
  font-size: 30px;
  letter-spacing: 0.6em;
  text-indent: 0.6em;
}

.auth-head p {
  margin: 0;
  font-size: 12.5px;
  letter-spacing: 0.14em;
  color: var(--paper-faint);
}

.submit-btn {
  width: 100%;
  margin-top: 8px;
  letter-spacing: 0.5em;
  text-indent: 0.5em;
  font-family: var(--font-display);
}

.auth-foot {
  margin: 26px 0 0;
  text-align: center;
  font-size: 13px;
  color: var(--paper-faint);
}

.form-foot {
  margin-top: 10px;
  text-align: right;
}

.forgot {
  font-size: 12px;
  color: var(--paper-faint);
  cursor: pointer;
  letter-spacing: 0.08em;
  transition: color 0.2s;
}

.forgot:hover {
  color: var(--seal-bright);
}

.forgot-box {
  margin-top: 20px;
  border-top: 1px dashed var(--ink-600);
  padding-top: 18px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.forgot-title {
  margin: 0;
  font-family: var(--font-display);
  font-size: 15px;
  letter-spacing: 0.3em;
  color: var(--gold);
}

.auth-foot a {
  color: var(--gold);
  letter-spacing: 0.1em;
  margin-left: 6px;
}

.auth-foot a:hover {
  color: var(--seal-bright);
}
</style>
