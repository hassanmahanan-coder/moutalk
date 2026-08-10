<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'

const props = defineProps({
  rounds: { type: Array, default: () => [] },
})
const emit = defineEmits(['close'])

const playing = ref(false)
const speed = ref(1)
const cursor = ref(0)
let timer = null

const SPEEDS = [1, 2, 4]

const currentRound = computed(() => props.rounds[cursor.value] || null)

watch(playing, (v) => {
  if (v) start()
  else stop()
})

function start() {
  stop()
  timer = setInterval(() => {
    cursor.value += 1
    if (cursor.value >= props.rounds.length) {
      stop()
      playing.value = false
      cursor.value = 0
    }
  }, 1800 / speed.value)
}

function stop() {
  if (timer) {
    clearInterval(timer)
    timer = null
  }
}

function toggle() {
  playing.value = !playing.value
}

function jump(i) {
  cursor.value = i
}

onBeforeUnmount(stop)
</script>

<template>
  <div class="replay">
    <div class="rp-head">
      <span class="rp-title">谈判回放</span>
      <div class="rp-controls">
        <button v-for="s in SPEEDS" :key="s" class="spd" :class="{ on: speed === s }" @click="speed = s">{{ s }}x</button>
        <button class="play" @click="toggle">{{ playing ? '⏸ 暂停' : '▶ 播放' }}</button>
        <button class="close" @click="emit('close')">✕</button>
      </div>
    </div>

    <div class="rp-body">
      <div class="rp-progress">
        <div v-for="(r, i) in rounds" :key="i" class="dot" :class="{ active: i === cursor, done: i < cursor }" @click="jump(i)">
          <span class="dot-num">{{ i + 1 }}</span>
        </div>
      </div>

      <div v-if="currentRound" class="rp-round" :key="cursor">
        <div class="rp-bubble user">
          <span class="b-lbl">你</span>
          <p>{{ currentRound.user_text || '（无发言）' }}</p>
        </div>
        <div class="rp-bubble ai">
          <span class="b-lbl">对手</span>
          <p>{{ currentRound.reply || '（无回复）' }}</p>
          <div class="rp-meta">
            <span v-if="currentRound.tactic" class="tag">{{ currentRound.tactic }}</span>
            <span v-if="currentRound.offer !== null && currentRound.offer !== undefined" class="tag offer">报价 {{ currentRound.offer }}</span>
          </div>
        </div>
      </div>
      <div v-else class="rp-empty">回放结束</div>
    </div>
  </div>
</template>

<style scoped>
.replay {
  border: 1px solid var(--gold-dim);
  border-radius: 6px;
  background: rgba(17, 28, 49, 0.85);
  overflow: hidden;
  margin-top: 18px;
}

.rp-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 16px;
  border-bottom: 1px solid var(--border);
  background: rgba(22, 34, 58, 0.6);
}

.rp-title {
  font-family: var(--font-display);
  font-size: 13px;
  letter-spacing: 0.3em;
  color: var(--gold);
}

.rp-controls {
  display: flex;
  gap: 8px;
  align-items: center;
}

.spd,
.play,
.close {
  font-family: var(--font-body);
  font-size: 11px;
  letter-spacing: 0.1em;
  color: var(--paper-dim);
  background: none;
  border: 1px solid var(--ink-600);
  border-radius: 2px;
  padding: 3px 10px;
  cursor: pointer;
  transition: all 0.2s;
}

.spd.on {
  color: var(--gold);
  border-color: var(--gold-dim);
}

.play {
  color: var(--seal-bright);
  border-color: rgba(83, 152, 127, 0.4);
}

.close:hover {
  color: var(--seal-bright);
}

.rp-body {
  padding: 18px 20px;
}

.rp-progress {
  display: flex;
  gap: 10px;
  margin-bottom: 18px;
}

.dot {
  width: 26px;
  height: 26px;
  display: grid;
  place-items: center;
  border-radius: 50%;
  border: 1px solid var(--ink-600);
  cursor: pointer;
  transition: all 0.2s;
}

.dot-num {
  font-size: 11px;
  color: var(--paper-faint);
}

.dot.active {
  border-color: var(--gold);
  background: rgba(201, 168, 106, 0.15);
}

.dot.active .dot-num {
  color: var(--gold);
}

.dot.done {
  border-color: var(--seal);
}

.rp-round {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.rp-bubble {
  max-width: 82%;
  padding: 10px 14px;
  border-radius: 4px;
  font-size: 13.5px;
  line-height: 1.8;
}

.rp-bubble.user {
  align-self: flex-end;
  background: rgba(194, 69, 46, 0.14);
  border: 1px solid rgba(194, 69, 46, 0.3);
}

.rp-bubble.ai {
  align-self: flex-start;
  background: rgba(26, 40, 66, 0.7);
  border: 1px solid var(--border);
}

.b-lbl {
  font-size: 10px;
  letter-spacing: 0.2em;
  color: var(--paper-faint);
  margin-right: 8px;
}

.rp-bubble p {
  margin: 4px 0 0;
  white-space: pre-wrap;
}

.rp-meta {
  display: flex;
  gap: 8px;
  margin-top: 8px;
}

.tag {
  font-size: 10px;
  letter-spacing: 0.12em;
  color: var(--gold);
  border: 1px solid rgba(201, 168, 106, 0.3);
  border-radius: 2px;
  padding: 1px 8px;
}

.tag.offer {
  color: var(--jade);
  border-color: rgba(111, 174, 147, 0.4);
}

.rp-empty {
  padding: 20px;
  text-align: center;
  color: var(--paper-faint);
  letter-spacing: 0.2em;
}
</style>
