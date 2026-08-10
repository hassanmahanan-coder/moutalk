<script setup>
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const auth = useAuthStore()
const step = ref(1)
const username = ref('')
const email = ref('')
const loading = ref(false)
const devCode = ref('')
const form = reactive({ password: '', confirm: '' })
const code = ref('')
const agreed = ref(false)

const USERNAME_RE = /^[A-Za-z][A-Za-z0-9_]{2,19}$/

async function register() {
  if (!username.value || !email.value || !form.password) {
    ElMessage.warning('请填写用户名、邮箱与密码')
    return
  }
  if (!USERNAME_RE.test(username.value)) {
    ElMessage.warning('用户名需 3-20 位，字母开头，可含数字与下划线')
    return
  }
  if (form.password !== form.confirm) {
    ElMessage.warning('两次输入的密码不一致')
    return
  }
  if (!agreed.value) {
    ElMessage.warning('请先阅读并同意《用户协议》与《隐私政策》')
    return
  }
  loading.value = true
  try {
    const data = await auth.register(username.value, email.value, form.password)
    devCode.value = data.code
    step.value = 2
    ElMessage.success('注册成功，请验证邮箱')
  } catch {
    /* 拦截器已提示 */
  } finally {
    loading.value = false
  }
}

async function verify() {
  if (code.value.length !== 6) {
    ElMessage.warning('请输入 6 位验证码')
    return
  }
  loading.value = true
  try {
    await auth.verify(email.value, code.value)
    ElMessage.success('验证通过，请登录')
    router.push({ name: 'login' })
  } catch {
    /* 拦截器已提示 */
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="auth-page">
    <div class="auth-card">
      <div class="auth-head">
        <span class="seal-mark large">谋</span>
        <h1>注册</h1>
        <p>开辟一方谈判席</p>
      </div>
      <hr class="gold-rule" />

      <el-form v-if="step === 1" label-position="top" @submit.prevent="register">
        <el-form-item label="用户名">
          <el-input v-model="username" placeholder="3-20 位，字母开头，可含数字与下划线" size="large" />
        </el-form-item>
        <el-form-item label="邮箱">
          <el-input v-model="email" type="email" placeholder="you@example.com" size="large" />
        </el-form-item>
        <el-form-item label="密码">
          <el-input v-model="form.password" type="password" show-password placeholder="至少 8 位" size="large" />
        </el-form-item>
        <el-form-item label="确认密码">
          <el-input v-model="form.confirm" type="password" show-password placeholder="再次输入密码" size="large" @keyup.enter="register" />
        </el-form-item>
        <div class="agree-row">
          <el-checkbox v-model="agreed">
            我已阅读并同意
            <router-link to="/terms">《用户协议》</router-link>
            与
            <router-link to="/terms/privacy">《隐私政策》</router-link>
          </el-checkbox>
        </div>
        <el-button class="submit-btn" type="primary" size="large" :loading="loading" @click="register">
          注册
        </el-button>
      </el-form>

      <div v-else class="verify-step">
        <p class="verify-tip">
          验证码已发送至 <b>{{ email }}</b>（开发环境直接显示于下方）
        </p>
        <div v-if="devCode" class="dev-code">{{ devCode }}</div>
        <el-form label-position="top" @submit.prevent="verify">
          <el-form-item label="6 位验证码">
            <el-input v-model="code" maxlength="6" placeholder="000000" size="large" class="code-input" @keyup.enter="verify" />
          </el-form-item>
          <el-button class="submit-btn" type="primary" size="large" :loading="loading" @click="verify">
            验 证
          </el-button>
        </el-form>
        <button class="back-link" @click="step = 1">返回修改邮箱</button>
      </div>

      <p class="auth-foot">
        已有账号？
        <router-link to="/login">直接登录</router-link>
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
  width: 420px;
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

.agree-row {
  margin: 4px 0 12px;
  font-size: 12.5px;
  color: var(--paper-dim);
}

.agree-row a {
  color: var(--gold-dim);
  text-decoration: underline;
  margin: 0 2px;
}

.verify-tip {
  font-size: 13px;
  color: var(--paper-dim);
  line-height: 1.8;
}

.verify-tip b {
  color: var(--paper);
  font-weight: 600;
}

.dev-code {
  margin: 14px 0 22px;
  padding: 12px;
  text-align: center;
  font-family: ui-monospace, Consolas, monospace;
  font-size: 26px;
  letter-spacing: 0.5em;
  color: var(--gold);
  background: rgba(201, 168, 106, 0.08);
  border: 1px dashed var(--gold-dim);
  border-radius: 4px;
}

.code-input :deep(.el-input__inner) {
  text-align: center;
  font-size: 22px;
  letter-spacing: 0.4em;
}

.back-link {
  display: block;
  margin: 20px auto 0;
  font-family: var(--font-body);
  font-size: 12px;
  color: var(--paper-faint);
  background: none;
  border: none;
  cursor: pointer;
  letter-spacing: 0.14em;
}

.back-link:hover {
  color: var(--gold);
}

.auth-foot {
  margin: 26px 0 0;
  text-align: center;
  font-size: 13px;
  color: var(--paper-faint);
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
