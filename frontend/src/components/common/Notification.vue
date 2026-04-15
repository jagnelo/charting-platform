<template>
  <Teleport to="body">
    <div class="notification-stack">
      <TransitionGroup name="notif">
        <div
          v-for="n in notifications"
          :key="n.id"
          :class="['notification', `notification--${n.type}`]"
          @click="remove(n.id)"
        >
          <span class="notif-icon">{{ icons[n.type] }}</span>
          <div class="notif-body">
            <div class="notif-title">{{ n.title }}</div>
            <div class="notif-msg">{{ n.message }}</div>
          </div>
          <button class="notif-close">✕</button>
        </div>
      </TransitionGroup>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'

interface Notification { id: number; type: 'alert' | 'info' | 'error'; title: string; message: string }

const notifications = ref<Notification[]>([])
let nextId = 1

const icons = { alert: '🔔', info: 'ℹ️', error: '⚠️' }

function add(notif: Omit<Notification, 'id'>, duration = 6000) {
  const id = nextId++
  notifications.value.push({ ...notif, id })
  setTimeout(() => remove(id), duration)
}

function remove(id: number) {
  notifications.value = notifications.value.filter(n => n.id !== id)
}

function handleAlertEvent(e: Event) {
  const detail = (e as CustomEvent).detail
  const title = `${detail.symbol} alert`
  const message = `${detail.condition?.replace(/_/g, ' ')} ${detail.threshold ?? ''} — current: ${detail.current_price?.toFixed?.(4) ?? detail.value_a?.toFixed?.(4) ?? 'n/a'}`
  add({
    type: 'alert',
    title,
    message,
  })
  playAlertSound()
  showDesktopNotification(title, message)
}

async function showDesktopNotification(title: string, body: string) {
  if (!('Notification' in window)) return
  try {
    let permission = Notification.permission
    if (permission === 'default') permission = await Notification.requestPermission()
    if (permission === 'granted') {
      new Notification(title, { body, silent: true })
    }
  } catch {
    /* Browser denied or blocked notification access. */
  }
}

function playAlertSound() {
  try {
    const AudioCtx = window.AudioContext || (window as any).webkitAudioContext
    if (!AudioCtx) return
    const ctx = new AudioCtx()
    const osc = ctx.createOscillator()
    const gain = ctx.createGain()
    osc.type = 'sine'
    osc.frequency.value = 880
    gain.gain.value = 0.001
    osc.connect(gain)
    gain.connect(ctx.destination)
    osc.start()
    gain.gain.exponentialRampToValueAtTime(0.08, ctx.currentTime + 0.02)
    gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.22)
    osc.stop(ctx.currentTime + 0.24)
  } catch {
    /* Autoplay policies can block audio until the user interacts with the page. */
  }
}

onMounted(() => window.addEventListener('chart:alert-triggered', handleAlertEvent))
onUnmounted(() => window.removeEventListener('chart:alert-triggered', handleAlertEvent))
</script>

<style scoped>
.notification-stack {
  position: fixed;
  bottom: 20px;
  right: 20px;
  z-index: 9999;
  display: flex;
  flex-direction: column;
  gap: 8px;
  pointer-events: none;
}

.notification {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  background: #1a1a1a;
  border-radius: 6px;
  padding: 12px 16px;
  min-width: 280px;
  max-width: 360px;
  box-shadow: 0 4px 20px rgba(0,0,0,0.5);
  pointer-events: all;
  cursor: pointer;
  border-left: 3px solid #64b5f6;
}

.notification--alert { border-left-color: #ffb74d; }
.notification--error  { border-left-color: #ef5350; }

.notif-icon { font-size: 18px; flex-shrink: 0; margin-top: 1px; }

.notif-body { flex: 1; }
.notif-title { font-weight: 600; color: #eee; font-size: 13px; margin-bottom: 2px; }
.notif-msg   { font-size: 11px; color: #888; font-family: monospace; }

.notif-close { background: none; border: none; color: #555; cursor: pointer; font-size: 12px; padding: 0; }
.notif-close:hover { color: #aaa; }

.notif-enter-active, .notif-leave-active { transition: all 0.3s ease; }
.notif-enter-from { transform: translateX(40px); opacity: 0; }
.notif-leave-to   { transform: translateX(40px); opacity: 0; }
</style>
