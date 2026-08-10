import { onUnmounted, reactive, ref } from 'vue'

const HEARTBEAT_INTERVAL = 30000 // 心跳间隔（PRD 8.2：30s）
const RECONNECT_DELAYS = [1000, 2000, 4000, 8000, 16000, 30000] // 指数退避上限 30s（PRD 9.1）

export function useNegotiation() {
  const ws = ref(null)
  const connected = ref(false)
  const opening = ref('')
  const streaming = ref(false)
  const turnText = ref('')
  const lastMeta = ref(null)
  const simpleResult = ref(null)
  const reportId = ref(null)
  const reportSubmitted = ref(false)
  const errorMsg = ref('')
  const llmMode = ref('glm')
  let sessionId = ''
  let authToken = ''
  let handlers = {}
  let heartbeatTimer = null
  let reconnectTimer = null
  let reconnectAttempt = 0
  let closedByUser = false

  function clearTimers() {
    if (heartbeatTimer) {
      clearInterval(heartbeatTimer)
      heartbeatTimer = null
    }
    if (reconnectTimer) {
      clearTimeout(reconnectTimer)
      reconnectTimer = null
    }
  }

  function scheduleReconnect() {
    if (closedByUser) return
    const delay = RECONNECT_DELAYS[Math.min(reconnectAttempt, RECONNECT_DELAYS.length - 1)]
    reconnectAttempt += 1
    reconnectTimer = setTimeout(() => {
      connect(sessionId, authToken, handlers)
    }, delay)
  }

  function connect(sid, token, h = {}) {
    sessionId = sid
    authToken = token
    handlers = h
    clearTimers()
    const proto = location.protocol === 'https:' ? 'wss' : 'ws'
    const url = `${proto}://${location.host}/api/negotiation/${sid}?token=${encodeURIComponent(token)}`
    const sock = new WebSocket(url)
    ws.value = sock

    sock.onopen = () => {
      connected.value = true
      reconnectAttempt = 0
      handlers.onOpen?.()
      heartbeatTimer = setInterval(() => {
        if (sock.readyState === WebSocket.OPEN) {
          sock.send(JSON.stringify({ type: 'ping' }))
        }
      }, HEARTBEAT_INTERVAL)
      if (reconnectAttempt > 0) {
        // 重连成功：请求回放断线期间缓冲的轮次（PRD 9.1）
        sock.send(JSON.stringify({ type: 'resume' }))
      }
    }

    sock.onmessage = (ev) => {
      let msg
      try {
        msg = JSON.parse(ev.data)
      } catch {
        return
      }
      switch (msg.type) {
        case 'opening':
          opening.value = msg.text
          if (msg.llm_mode) llmMode.value = msg.llm_mode
          handlers.onOpening?.(msg)
          break
        case 'history':
          if (msg.llm_mode) llmMode.value = msg.llm_mode
          handlers.onHistory?.(msg)
          break
        case 'token':
          streaming.value = true
          turnText.value += msg.text
          handlers.onToken?.(msg)
          break
        case 'meta':
          streaming.value = false
          lastMeta.value = msg
          handlers.onMeta?.(msg)
          turnText.value = ''
          // 确认已收到本轮，服务端清空断线缓冲
          if (sock.readyState === WebSocket.OPEN) {
            sock.send(JSON.stringify({ type: 'ack' }))
          }
          break
        case 'replay':
          // 断线回放：逐条渲染缓冲的轮次（PRD 9.1）
          handlers.onReplay?.(msg.messages || [])
          break
        case 'coach_advice':
          handlers.onCoachAdvice?.(msg)
          break
        case 'simple_result':
          simpleResult.value = msg
          handlers.onResult?.(msg)
          break
        case 'report_ready':
          reportId.value = msg.rid
          handlers.onReport?.(msg)
          break
        case 'report_submitted':
          reportSubmitted.value = true
          handlers.onReportSubmitted?.(msg)
          break
        case 'error':
          errorMsg.value = msg.message
          handlers.onError?.(msg)
          break
        default:
          break
      }
    }

    sock.onerror = () => {
      errorMsg.value = '连接异常，正在重连…'
      handlers.onError?.()
    }

    sock.onclose = () => {
      connected.value = false
      clearTimers()
      handlers.onClose?.()
      scheduleReconnect()
    }
  }

  function send(type, payload = {}) {
    if (ws.value && ws.value.readyState === WebSocket.OPEN) {
      ws.value.send(JSON.stringify({ type, ...payload }))
    }
  }

  function close() {
    closedByUser = true
    clearTimers()
    ws.value?.close()
  }

  onUnmounted(() => close())

  return reactive({
    connected,
    opening,
    streaming,
    turnText,
    lastMeta,
    simpleResult,
    reportId,
    reportSubmitted,
    errorMsg,
    llmMode,
    connect,
    send,
    close,
  })
}
