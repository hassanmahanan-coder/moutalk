<script setup>
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'

const route = useRoute()
const router = useRouter()
const kind = computed(() => (route.params.kind === 'privacy' ? 'privacy' : 'terms'))
</script>

<template>
  <div class="terms">
    <div class="head">
      <p class="kicker">合规文件</p>
      <h1>{{ kind === 'terms' ? '用户协议' : '隐私政策' }}</h1>
    </div>
    <hr class="gold-rule" />

    <div class="doc">
      <template v-if="kind === 'terms'">
        <h2>一、服务说明</h2>
        <p>谋谈（MouTalk）提供基于人工智能的谈判模拟训练服务。本系统用于谈判技巧训练，所有战术均为模拟对抗设定，应用于真实场景时请遵循商业道德与法律。</p>

        <h2>二、账号与使用</h2>
        <p>用户须以真实邮箱注册，并对账号下的所有行为负责。免费用户每月每场景可进行 5 次谈判，Pro 订阅用户不限次数。</p>

        <h2>三、内容与合规</h2>
        <p>谈判过程中 AI 对手可能使用"虚假底线""信息不对称"等战术，均属<strong>模拟场景内的设定信息</strong>，不构成真实商业承诺，亦不诱导用户刺探他人真实机密。</p>
        <p>用户谈判内容<strong>不作为训练语料</strong>、不向第三方共享。</p>

        <h2>四、免责声明</h2>
        <p>系统输出仅供训练参考，不构成法律、商业或投资建议。因使用本系统产生的决策后果由用户自行承担。</p>
      </template>

      <template v-else>
        <h2>一、数据收集</h2>
        <p>我们收集：注册邮箱、密码哈希、谈判对话内容、报价记录、复盘报告、支付订单信息。密码以 bcrypt 哈希存储，不保留明文。</p>

        <h2>二、数据使用</h2>
        <p>数据仅用于：提供服务、生成复盘报告、优化战术规则（聚合统计，不含个人身份）。用户谈判内容不作为训练语料、不向第三方共享。</p>

        <h2>三、数据存储与安全</h2>
        <p>数据存储于加密保护的服务器；支付信息由支付宝托管。用户可随时请求删除账号及相关数据。</p>

        <h2>四、企业版说明</h2>
        <p>企业版支持数据本地化部署选项（规划中），届时企业数据不离开客户指定环境。</p>
      </template>
    </div>

    <div class="foot-nav">
      <el-button plain @click="router.push({ name: 'register' })">返回注册</el-button>
    </div>
  </div>
</template>

<style scoped>
.terms {
  max-width: 760px;
  width: 100%;
  margin: 0 auto;
  padding: 48px 40px 70px;
}

.head {
  text-align: center;
  margin-bottom: 24px;
}

.kicker {
  margin: 0 0 8px;
  font-size: 11px;
  letter-spacing: 0.6em;
  color: var(--seal-bright);
}

.head h1 {
  margin: 0;
  font-size: 30px;
  letter-spacing: 0.4em;
  text-indent: 0.4em;
}

.doc {
  padding: 26px 30px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: rgba(17, 28, 49, 0.4);
}

.doc h2 {
  font-size: 15px;
  letter-spacing: 0.2em;
  color: var(--gold);
  margin: 22px 0 10px;
}

.doc h2:first-child {
  margin-top: 0;
}

.doc p {
  font-size: 13.5px;
  line-height: 2;
  color: var(--paper-dim);
  margin: 0 0 10px;
}

.doc strong {
  color: var(--paper);
}

.foot-nav {
  display: flex;
  justify-content: center;
  margin-top: 30px;
}
</style>
