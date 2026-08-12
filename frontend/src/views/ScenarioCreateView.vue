<script setup>
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { scenarioApi } from '../api'

const router = useRouter()
const mode = ref('form') // form | json
const loading = ref(false)
const jsonText = ref('')

const form = reactive({
  title: '',
  briefing: '',
  rules: '',
  opponent_role: '',
  opening_line: '',
  safe_fallback: '',
  dimensions: [
    { key: 'price', label: '总价', direction: 'min', first_offer: 100, bottom_line: 80, keywords: '报价,价格,万' },
  ],
})

const DIM_HINT = [
  { key: 'price', label: '总价', first: 235, bottom: 180 },
  { key: 'payment_cycle', label: '付款周期', first: 30, bottom: 90 },
  { key: 'warranty', label: '保修年限', first: 1, bottom: 2 },
  { key: 'delivery', label: '交期', first: 15, bottom: 45 },
]

function addDimension() {
  form.dimensions.push({ key: '', label: '', direction: 'min', first_offer: null, bottom_line: null, keywords: '' })
}

function removeDimension(i) {
  form.dimensions.splice(i, 1)
}

function buildConfig() {
  const dims = form.dimensions.map((d) => ({
    key: d.key.trim(),
    label: d.label.trim(),
    direction: d.direction,
    first_offer: Number(d.first_offer),
    bottom_line: Number(d.bottom_line),
    keywords: d.keywords.split(/[,，]/).map((k) => k.trim()).filter(Boolean),
  }))
  const weights = {}
  const w = 1 / Math.max(1, dims.length)
  dims.forEach((d) => { weights[d.key] = Number(w.toFixed(2)) })
  // 修正浮点误差：最后一个补足 1
  const sum = Object.values(weights).reduce((a, b) => a + b, 0)
  if (dims.length) weights[dims[dims.length - 1].key] = Number((weights[dims[dims.length - 1].key] + (1 - sum)).toFixed(2))
  return {
    title: form.title.trim(),
    briefing: form.briefing.trim(),
    rules: form.rules.trim() || '在多个维度上争取最有利条件。',
    opponent_role: form.opponent_role.trim() || '你是经验丰富的谈判对手。',
    opening_line: form.opening_line.trim(),
    safe_fallback: form.safe_fallback
      .split('\n')
      .map((s) => s.trim())
      .filter(Boolean),
    dimensions: dims,
    weights,
  }
}

async function submit() {
  loading.value = true
  try {
    let config
    if (mode.value === 'json') {
      config = JSON.parse(jsonText.value)
    } else {
      if (!form.title.trim() || !form.opening_line.trim() || !form.briefing.trim()) {
        ElMessage.warning('请填写标题、背景与开场白')
        return
      }
      config = buildConfig()
    }
    const created = await scenarioApi.createCustom(config)
    ElMessage.success(`场景「${created.title}」创建成功`)
    router.push({ name: 'lobby' })
  } catch (e) {
    if (e.code === 'SCENARIO_INVALID') {
      ElMessage.error(`场景配置不合法：${e.message || ''}`)
    } else if (e instanceof SyntaxError) {
      ElMessage.error('JSON 格式错误，请检查语法')
    }
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="create">
    <div class="head">
      <p class="kicker">Custom</p>
      <h1>自定义场景</h1>
      <p class="sub">打造你自己的谈判案卷 · 仅自己可见</p>
    </div>
    <hr class="gold-rule" />

    <div class="mode-row">
      <button class="mode" :class="{ on: mode === 'form' }" @click="mode = 'form'">表单模式</button>
      <button class="mode" :class="{ on: mode === 'json' }" @click="mode = 'json'">JSON 导入</button>
    </div>

    <template v-if="mode === 'form'">
      <el-form label-position="top">
        <el-form-item label="场景标题" required>
          <el-input v-model="form.title" placeholder="如：办公室租赁谈判" size="large" />
        </el-form-item>
        <el-form-item label="背景简报" required>
          <el-input v-model="form.briefing" type="textarea" :rows="2" placeholder="您是谁、对方是谁、谈判目标……" />
        </el-form-item>
        <el-form-item label="谈判规则">
          <el-input v-model="form.rules" type="textarea" :rows="2" placeholder="您的立场与目标（可选）" />
        </el-form-item>
        <el-form-item label="对手角色设定">
          <el-input v-model="form.opponent_role" placeholder="如：你是写字楼招商经理，善于利用地段优势" />
        </el-form-item>
        <el-form-item label="对手开场白" required>
          <el-input v-model="form.opening_line" type="textarea" :rows="2" placeholder="对方说的第一句话（需含首个报价）" />
        </el-form-item>
        <el-form-item label="安全话术（每行一条，对手无法让步时使用）">
          <el-input v-model="form.safe_fallback" type="textarea" :rows="2" placeholder="如：这个条件我无法答应，但我们可以再谈谈其他条款。" />
        </el-form-item>

        <div class="dims-head">
          <h3>谈判维度</h3>
          <el-button size="small" plain @click="addDimension">＋ 添加维度</el-button>
        </div>
        <div v-for="(d, i) in form.dimensions" :key="i" class="dim-card">
          <div class="dim-row">
            <el-input v-model="d.key" placeholder="key（price）" class="w-key" />
            <el-input v-model="d.label" placeholder="名称（总价）" class="w-label" />
            <el-select v-model="d.direction" class="w-dir">
              <el-option label="越低越好" value="min" />
              <el-option label="越高越好" value="max" />
            </el-select>
            <el-button size="small" plain type="danger" @click="removeDimension(i)">移除</el-button>
          </div>
          <div class="dim-row">
            <el-input v-model.number="d.first_offer" placeholder="对手首次报价" class="w-num" type="number" />
            <el-input v-model.number="d.bottom_line" placeholder="对手底线（不可突破）" class="w-num" type="number" />
            <el-input v-model="d.keywords" placeholder="触发关键词（报价,价格,万）" />
          </div>
          <div class="dim-hint">
            ⚠️ 首报价=对手开价（如 3 万填 3）；底线=对手能接受的最差条件（如 2 万填 2）；
            关键词用于识别对方话术（如"报价""万"），不要填具体数字。
            方向"越低越好"=你希望压低（买方视角）；"越高越好"=你希望抬高（卖方视角）。
            参考：{{ DIM_HINT.find((h) => h.key === d.key)?.label || '自定义' }}
            （首报 {{ DIM_HINT.find((h) => h.key === d.key)?.first ?? '—' }} / 底线 {{ DIM_HINT.find((h) => h.key === d.key)?.bottom ?? '—' }}）
          </div>
        </div>
      </el-form>
    </template>

    <template v-else>
      <p class="json-tip">粘贴完整场景 JSON（对齐官方场景包结构：title/briefing/rules/opponent_role/opening_line/safe_fallback/dimensions/weights）</p>
      <el-input v-model="jsonText" type="textarea" :rows="16" class="json-input" placeholder="{ &quot;title&quot;: &quot;...&quot;, ... }" />
      <el-button size="small" plain @click="jsonText = JSON.stringify({
        title: '示例场景', briefing: '背景…', rules: '目标…', opponent_role: '你是…', opening_line: '您好，报价…',
        safe_fallback: ['这个条件我无法答应。'],
        dimensions: [{ key: 'price', label: '总价', direction: 'min', first_offer: 100, bottom_line: 80, keywords: ['报价'] }],
        weights: { price: 1.0 },
      }, null, 2)">填入示例</el-button>
    </template>

    <div class="submit-row">
      <el-button type="primary" size="large" :loading="loading" @click="submit">创建场景</el-button>
      <el-button plain size="large" @click="router.push({ name: 'lobby' })">返回大厅</el-button>
    </div>
  </div>
</template>

<style scoped>
.create {
  max-width: 760px;
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

.mode-row {
  display: flex;
  gap: 10px;
  margin: 20px 0;
}

.mode {
  font-family: var(--font-body);
  font-size: 13px;
  letter-spacing: 0.18em;
  color: var(--paper-dim);
  background: none;
  border: 1px solid var(--ink-600);
  border-radius: 3px;
  padding: 7px 18px;
  cursor: pointer;
  transition: all 0.2s;
}

.mode:hover {
  color: var(--paper);
  border-color: var(--gold-dim);
}

.mode.on {
  color: var(--gold);
  border-color: var(--gold-dim);
  background: rgba(201, 168, 106, 0.08);
}

.dims-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin: 18px 0 10px;
}

.dims-head h3 {
  margin: 0;
  font-size: 15px;
  letter-spacing: 0.24em;
  color: var(--paper-dim);
}

.dim-card {
  border: 1px solid var(--border);
  border-radius: 5px;
  padding: 14px 16px;
  margin-bottom: 12px;
  background: rgba(13, 22, 38, 0.5);
}

.dim-row {
  display: flex;
  gap: 10px;
  margin-bottom: 10px;
}

.w-key { flex: 1; }
.w-label { flex: 1.4; }
.w-dir { flex: 0.9; }
.w-num { flex: 1; }

.dim-hint {
  font-size: 11px;
  color: var(--paper-faint);
}

.json-tip {
  font-size: 12.5px;
  color: var(--paper-faint);
  line-height: 1.9;
  margin: 4px 0 12px;
}

.json-input {
  font-family: Consolas, monospace;
  font-size: 12px;
  margin-bottom: 12px;
}

.submit-row {
  display: flex;
  gap: 12px;
  margin-top: 24px;
}
</style>
