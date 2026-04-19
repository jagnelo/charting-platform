<template>
  <footer class="status-bar">
    <span :class="['status-pill', alertsStore.wsConnected ? 'ok' : 'bad']">
      WS {{ alertsStore.wsConnected ? 'connected' : 'offline' }}
    </span>
    <span :class="['status-pill', serverOk ? 'ok' : 'warn']">
      API {{ serverOk ? 'ok' : 'checking' }}
    </span>
    <span v-if="showChartContext && chartStore.symbol" class="status-item">
      {{ chartStore.symbol }} · {{ chartStore.timeframe }} · {{ chartStore.barType.replace('_', ' ') }}
    </span>
    <span v-if="showChartContext && lastBarTime" class="status-item">Last bar {{ lastBarTime }}</span>
    <span class="status-spacer" />
    <span class="status-item">{{ clock }}</span>
  </footer>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { useAlertsStore } from '@/stores/alerts'
import { useChartStore } from '@/stores/chart'

const alertsStore = useAlertsStore()
const chartStore = useChartStore()
const route = useRoute()

const clock = ref(formatClock())
const serverOk = ref(false)
let clockTimer: ReturnType<typeof setInterval> | null = null
let healthTimer: ReturnType<typeof setInterval> | null = null

const showChartContext = computed(() => route.path.startsWith('/chart'))

const lastBarTime = computed(() => {
  const ts = chartStore.bars[chartStore.bars.length - 1]?.ts
  if (!ts) return ''
  return new Date(ts).toLocaleString()
})

function formatClock() {
  return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

async function checkHealth() {
  try {
    const res = await fetch('/health')
    serverOk.value = res.ok
  } catch {
    serverOk.value = false
  }
}

onMounted(() => {
  clockTimer = setInterval(() => { clock.value = formatClock() }, 1000)
  checkHealth()
  healthTimer = setInterval(checkHealth, 30_000)
})

onUnmounted(() => {
  if (clockTimer) clearInterval(clockTimer)
  if (healthTimer) clearInterval(healthTimer)
})
</script>

<style scoped>
.status-bar {
  height: 24px;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 10px;
  border-top: 1px solid #171717;
  background: #0b0b0b;
  color: #666;
  font-family: 'JetBrains Mono', monospace;
  font-size: 10px;
  flex-shrink: 0;
}
.status-pill {
  padding: 2px 6px;
  border: 1px solid #2a2a2a;
  border-radius: 4px;
  color: #777;
  text-transform: uppercase;
}
.status-pill.ok { color: #26a69a; border-color: #1b4a43; }
.status-pill.warn { color: #ffb74d; border-color: #4a3718; }
.status-pill.bad { color: #ef5350; border-color: #4a1f1f; }
.status-item {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.status-spacer { flex: 1; }
</style>
