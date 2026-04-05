<template>
  <div class="settings-view">
    <h2 class="page-title">Settings</h2>

    <section class="settings-section">
      <h3>OneSignal Push Notifications</h3>
      <p class="hint">
        To receive push notifications when alerts trigger, you need a free OneSignal account.
        Enter your App ID below — the browser will ask for notification permission.
      </p>
      <div class="form-row">
        <label>OneSignal App ID</label>
        <input v-model="oneSignalAppId" type="text" class="settings-input" placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx" />
      </div>
      <button class="settings-btn" @click="initOneSignal">Enable Push Notifications</button>
      <div v-if="pushStatus" class="push-status" :class="pushStatus.ok ? 'ok' : 'err'">{{ pushStatus.msg }}</div>
    </section>

    <section class="settings-section">
      <h3>Backend Connection</h3>
      <div class="form-row">
        <label>API Base URL</label>
        <input v-model="apiBase" type="text" class="settings-input" placeholder="http://your-nas-ip:8000" />
      </div>
      <button class="settings-btn" @click="testConnection">Test Connection</button>
      <div v-if="connStatus" class="push-status" :class="connStatus.ok ? 'ok' : 'err'">{{ connStatus.msg }}</div>
    </section>

    <section class="settings-section">
      <h3>Indicator Presets</h3>
      <div v-for="preset in presetsStore.presets" :key="preset.id" class="preset-row">
        <span class="preset-name">{{ preset.name }}</span>
        <span class="preset-default" v-if="preset.is_default">★ default</span>
        <span class="preset-count">{{ preset.indicators.length }} indicators</span>
        <button @click="presetsStore.updatePreset(preset.id, { is_default: true })">Set Default</button>
        <button @click="presetsStore.deletePreset(preset.id)" class="btn-danger">Delete</button>
      </div>
      <div v-if="!presetsStore.presets.length" class="empty-hint">No presets saved yet. Create them from the chart view.</div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { usePresetsStore } from '@/stores/presets'

const presetsStore = usePresetsStore()
const oneSignalAppId = ref(localStorage.getItem('onesignal_app_id') ?? '')
const apiBase = ref(localStorage.getItem('api_base') ?? '')
const pushStatus = ref<{ ok: boolean; msg: string } | null>(null)
const connStatus = ref<{ ok: boolean; msg: string } | null>(null)

async function initOneSignal() {
  if (!oneSignalAppId.value) { pushStatus.value = { ok: false, msg: 'Please enter an App ID' }; return }
  localStorage.setItem('onesignal_app_id', oneSignalAppId.value)
  try {
    // @ts-ignore
    window.OneSignalDeferred = window.OneSignalDeferred || []
    // @ts-ignore
    window.OneSignalDeferred.push(async (OneSignal: any) => {
      await OneSignal.init({ appId: oneSignalAppId.value, notifyButton: { enable: false } })
      await OneSignal.Notifications.requestPermission()
      pushStatus.value = { ok: true, msg: 'Push notifications enabled!' }
    })
  } catch (e: any) {
    pushStatus.value = { ok: false, msg: `Failed: ${e.message}` }
  }
}

async function testConnection() {
  try {
    const url = `${apiBase.value || ''}/health`
    const res = await fetch(url)
    const data = await res.json()
    connStatus.value = { ok: true, msg: `Connected ✓ — ${JSON.stringify(data)}` }
    if (apiBase.value) localStorage.setItem('api_base', apiBase.value)
  } catch (e: any) {
    connStatus.value = { ok: false, msg: `Failed: ${e.message}` }
  }
}

onMounted(() => presetsStore.loadPresets())
</script>

<style scoped>
.settings-view { padding: 24px; color: #ccc; height: 100%; overflow-y: auto; box-sizing: border-box; }
.page-title     { color: #fff; font-size: 20px; margin-bottom: 24px; }

.settings-section { margin-bottom: 32px; }
.settings-section h3 { color: #eee; font-size: 14px; margin-bottom: 12px; border-bottom: 1px solid #222; padding-bottom: 6px; }

.hint { font-size: 12px; color: #666; margin-bottom: 12px; line-height: 1.5; }

.form-row { display: flex; flex-direction: column; gap: 4px; margin-bottom: 10px; }
.form-row label { font-size: 11px; color: #666; }

.settings-input {
  background: #1a1a1a;
  border: 1px solid #333;
  color: #ccc;
  border-radius: 3px;
  padding: 6px 10px;
  font-size: 13px;
  font-family: monospace;
  width: 100%;
}

.settings-btn {
  background: #1a3a5c;
  border: 1px solid #64b5f6;
  color: #64b5f6;
  border-radius: 3px;
  padding: 6px 16px;
  cursor: pointer;
  font-size: 12px;
}

.push-status { margin-top: 8px; font-size: 12px; }
.push-status.ok  { color: #66bb6a; }
.push-status.err { color: #ef5350; }

.preset-row { display: flex; align-items: center; gap: 10px; padding: 6px 0; font-size: 12px; }
.preset-name { font-weight: 600; color: #ddd; min-width: 120px; }
.preset-default { color: #ffd54f; font-size: 10px; }
.preset-count { color: #555; margin-right: auto; }

.preset-row button { background: #1a1a1a; border: 1px solid #333; color: #888; border-radius: 3px; padding: 3px 10px; cursor: pointer; font-size: 11px; }
.preset-row button:hover { color: #ccc; }
.preset-row .btn-danger:hover { border-color: #ef5350; color: #ef5350; }

.empty-hint { color: #444; font-size: 12px; font-style: italic; }
</style>
