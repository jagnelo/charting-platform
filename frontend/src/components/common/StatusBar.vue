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
  height: var(--tc-status-height, 21px);
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 10px;
  border-top: 1px solid var(--tc-border, #303940);
  background: var(--tc-shell-bg, #0d1013);
  color: var(--tc-text-muted, #81909a);
  font-family: var(--tc-font-family, "Segoe UI", Arial, sans-serif);
  font-size: 10px;
  flex-shrink: 0;
}
.status-pill {
  padding: 2px 6px;
  border: 1px solid var(--tc-border, #303940);
  border-radius: var(--tc-radius, 0px);
  color: var(--tc-text-muted, #81909a);
  text-transform: uppercase;
}
.status-pill.ok { color: var(--tc-positive, #63bd85); border-color: #63bd8555; }
.status-pill.warn { color: var(--tc-warning, #dfbd82); border-color: #dfbd8255; }
.status-pill.bad { color: var(--tc-negative, #ed9696); border-color: #ed969655; }
.status-item {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.status-spacer { flex: 1; }
</style>
