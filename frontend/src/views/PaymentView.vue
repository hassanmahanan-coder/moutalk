<script setup>
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { paymentApi, scenarioApi } from '../api'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const paidScenarios = ref([])
const loading = ref(false)
const paying = ref('')

async function mockNotify(order) {
  const fd = new FormData()
  fd.append('out_trade_no', order.out_trade_no)
  fd.append('trade_no', `mock_${Date.now()}`)
  fd.append('amount', String(order.amount))
  const res = await fetch('/api/payment/notify', { method: 'POST', body: fd })
  return res.text()
}

async function quickPay(type, targetId = null, label = '') {
  // 一键直付：不下发支付宝，下单后直接触发支付回调秒成功（演示/内测用）
  paying.value = label
  loading.value = true
  try {
    const order = await paymentApi.createOrder(type, targetId)
    const ok = await mockNotify(order)
    if (ok === 'success') {
      ElMessage.success('支付成功')
      await auth.fetchMe()
    } else {
      ElMessage.error('回调处理失败，请联系支持')
    }
  } catch {
    /* 拦截器已提示 */
  } finally {
    loading.value = false
    paying.value = ''
  }
}

async function pollOrder(orderId, timeoutMs = 60000) {
  const intervalMs = 2000
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    await new Promise((r) => setTimeout(r, intervalMs))
    const order = await paymentApi.getOrder(orderId)
    if (order.status === 'paid') return true
  }
  return false
}

async function buy(type, targetId = null, label = '') {
  paying.value = label
  loading.value = true
  try {
    const order = await paymentApi.createOrder(type, targetId)
    if (order.pay_url) {
      // 真实支付宝沙箱支付：新窗口打开收银台，轮询订单状态确认到账
      window.open(order.pay_url, '_blank')
      ElMessage.info('请在打开的支付宝页面完成支付……')
      const ok = await pollOrder(order.id)
      if (ok) {
        ElMessage.success('支付成功')
        await auth.fetchMe()
      } else {
        ElMessage.warning('支付确认超时，若已完成支付请稍后在个人中心查看')
      }
    } else {
      // 未配置支付宝密钥：模拟回调兜底（MVP）
      const ok = await mockNotify(order)
      if (ok === 'success') {
        ElMessage.success('支付成功（模拟回调）')
        await auth.fetchMe()
      } else {
        ElMessage.error('回调处理失败，请联系支持')
      }
    }
  } catch {
    /* 拦截器已提示 */
  } finally {
    loading.value = false
    paying.value = ''
  }
}

onMounted(async () => {
  try {
    const s = await scenarioApi.list()
    paidScenarios.value = s.items.filter((x) => x.price !== null && x.price > 0 && !x.is_free)
  } catch {
    /* 拦截器已提示 */
  }
})
</script>

<template>
  <div class="payment">
    <div class="head">
      <p class="kicker">升级 Pro</p>
      <h1>开通席位</h1>
      <p class="sub">解除限制，尽享完整谈判体验</p>
    </div>
    <hr class="gold-rule" />

    <div class="plans">
      <section class="plan free">
        <h3>免费席</h3>
        <p class="price">¥0</p>
        <ul>
          <li>每月每场景 5 次谈判</li>
          <li>基础复盘报告</li>
          <li>全部免费内置场景</li>
        </ul>
        <span class="current" v-if="!auth.isPro">当前席位</span>
        <el-button v-else plain disabled>已可继续</el-button>
      </section>

      <section class="plan pro">
        <span class="ribbon">推荐</span>
        <h3>Pro 席位</h3>
        <p class="price">¥199<span>/ 30 天</span></p>
        <ul>
          <li>不限次谈判</li>
          <li>解锁付费场景包</li>
          <li>完整复盘报告与建议</li>
        </ul>
        <div v-if="!auth.isPro" class="pay-actions">
          <el-button
            type="primary"
            size="large"
            :loading="paying === 'subscribe-alipay' && loading"
            @click="buy('subscribe', null, 'subscribe-alipay')"
          >
            支付宝支付
          </el-button>
          <el-button
            plain
            size="large"
            :loading="paying === 'subscribe-quick' && loading"
            @click="quickPay('subscribe', null, 'subscribe-quick')"
          >
            一键直付
          </el-button>
        </div>
        <span v-else class="current">Pro 生效中</span>
      </section>
    </div>

    <hr class="gold-rule" />

    <section v-if="paidScenarios.length" class="scen-sec">
      <h2>付费场景包</h2>
      <div class="scen-list">
        <div v-for="s in paidScenarios" :key="s.id" class="scen">
          <h3>{{ s.title }}</h3>
          <p>{{ s.briefing }}</p>
          <div class="scen-foot">
            <span class="price">¥ {{ Number(s.price).toFixed(2) }}</span>
            <div class="scen-btns">
              <el-button type="primary" :loading="paying === `a-${s.id}` && loading" @click="buy('scenario', s.id, `a-${s.id}`)">
                支付宝支付
              </el-button>
              <el-button plain :loading="paying === `q-${s.id}` && loading" @click="quickPay('scenario', s.id, `q-${s.id}`)">
                一键直付
              </el-button>
            </div>
          </div>
        </div>
      </div>
    </section>

    <p class="note">支付二选一：支付宝沙箱跳转（配置密钥后可用），或一键直付（演示/内测，点击即成功，PRD 7.5 / 9.12）。</p>
  </div>
</template>

<style scoped>
.payment {
  max-width: 920px;
  width: 100%;
  margin: 0 auto;
  padding: 52px 40px 60px;
}

.head {
  text-align: center;
  margin-bottom: 26px;
}

.kicker {
  margin: 0 0 8px;
  font-size: 11px;
  letter-spacing: 0.6em;
  color: var(--seal-bright);
}

.head h1 {
  margin: 0;
  font-size: 36px;
  letter-spacing: 0.5em;
  text-indent: 0.5em;
}

.head .sub {
  margin: 10px 0 0;
  font-size: 13px;
  letter-spacing: 0.24em;
  color: var(--paper-faint);
}

.plans {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 24px;
  padding: 30px 0;
}

.plan {
  position: relative;
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 30px 34px;
  background: linear-gradient(180deg, rgba(22, 34, 58, 0.5), rgba(13, 22, 38, 0.7));
  display: flex;
  flex-direction: column;
}

.plan.pro {
  border-color: rgba(194, 69, 46, 0.55);
  box-shadow: 0 0 0 1px rgba(194, 69, 46, 0.2), var(--shadow-float);
}

.ribbon {
  position: absolute;
  top: -1px;
  right: 24px;
  font-size: 11px;
  letter-spacing: 0.3em;
  color: #f4efe2;
  background: linear-gradient(150deg, var(--seal-bright), var(--seal-deep));
  padding: 4px 12px;
  border-radius: 0 0 4px 4px;
}

.plan h3 {
  margin: 0 0 8px;
  font-size: 17px;
  letter-spacing: 0.3em;
}

.plan .price {
  margin: 0 0 18px;
  font-family: var(--font-display);
  font-size: 40px;
  color: var(--gold);
  letter-spacing: 0.04em;
}

.plan.free .price {
  color: var(--paper-dim);
}

.plan .price span {
  font-size: 13px;
  color: var(--paper-faint);
  font-family: var(--font-body);
}

.plan ul {
  margin: 0 0 22px;
  padding: 0;
  list-style: none;
  flex: 1;
}

.plan li {
  font-size: 13px;
  color: var(--paper-dim);
  line-height: 2.2;
  letter-spacing: 0.06em;
}

.plan li::before {
  content: '·';
  color: var(--seal);
  margin-right: 10px;
}

.current {
  font-size: 12px;
  letter-spacing: 0.2em;
  color: var(--jade);
  padding: 9px 0;
  text-align: center;
  border: 1px dashed rgba(111, 174, 147, 0.45);
  border-radius: 4px;
}

.scen-sec {
  padding: 26px 0 10px;
}

.scen-sec h2 {
  font-size: 17px;
  letter-spacing: 0.34em;
  color: var(--paper-dim);
  padding-bottom: 10px;
  border-bottom: 1px solid var(--border);
  margin: 0 0 18px;
}

.scen-list {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.scen {
  border: 1px solid var(--border);
  border-radius: 5px;
  padding: 18px 24px;
  background: rgba(13, 22, 38, 0.6);
}

.scen h3 {
  margin: 0 0 6px;
  font-size: 15px;
  letter-spacing: 0.08em;
}

.scen p {
  margin: 0;
  font-size: 12.5px;
  line-height: 1.9;
  color: var(--paper-faint);
}

.scen-foot {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 14px;
}

.scen-btns {
  display: flex;
  gap: 10px;
}

.pay-actions {
  display: flex;
  gap: 12px;
}

.pay-actions .el-button {
  flex: 1;
}

.scen-foot .price {
  font-family: var(--font-display);
  font-size: 18px;
  color: var(--gold);
}

.note {
  margin: 30px 0 0;
  text-align: center;
  font-size: 11.5px;
  color: var(--paper-faint);
  letter-spacing: 0.08em;
}
</style>
