<script setup>
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const auth = useAuthStore()
const form = reactive({ account: '', password: '' })
const loading = ref(false)

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
      </el-form>
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

.auth-foot a {
  color: var(--gold);
  letter-spacing: 0.1em;
  margin-left: 6px;
}

.auth-foot a:hover {
  color: var(--seal-bright);
}
</style>
