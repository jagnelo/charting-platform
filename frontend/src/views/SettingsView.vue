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

    <section class="settings-section">
      <h3>Providers</h3>
      <p class="hint">Capability routing, fallback health, and rate limits.</p>
      <div v-if="providersLoading" class="empty-hint">Loading provider policies...</div>
      <div v-else-if="providerError" class="push-status err">{{ providerError }}</div>
      <div v-else class="provider-list">
        <div v-for="group in groupedPolicies" :key="group.provider" class="provider-card">
          <div class="provider-card-head">
            <strong>{{ group.provider }}</strong>
            <span>{{ group.capabilities.length }} capabilities</span>
          </div>
          <div v-for="policy in group.capabilities" :key="`${policy.provider}:${policy.capability}`" class="provider-row">
            <div class="provider-main">
              <strong>{{ policy.capability }}</strong>
              <small>
                score {{ policy.effective_score.toFixed(2) }} · latency {{ policy.ewma_latency_ms.toFixed(0) }}ms · failures {{ policy.failure_streak }}
              </small>
            </div>
            <label class="provider-check">
              <input type="checkbox" :checked="policy.is_enabled" @change="patchPolicy(policy, { is_enabled: checkboxValue($event) })" />
              <span>Enabled</span>
            </label>
            <label class="provider-check">
              <input type="checkbox" :checked="policy.is_pinned" @change="patchPolicy(policy, { is_pinned: checkboxValue($event) })" />
              <span>Pinned</span>
            </label>
            <label class="provider-check">
              <input type="checkbox" :checked="policy.auto_weight_enabled" @change="patchPolicy(policy, { auto_weight_enabled: checkboxValue($event) })" />
              <span>Auto</span>
            </label>
            <label class="provider-inline">
              <span>Priority</span>
              <input type="number" :value="policy.base_priority" @change="patchPolicy(policy, { base_priority: Number(inputValue($event)) })" />
            </label>
            <label class="provider-inline">
              <span>TPM</span>
              <input type="number" :value="policy.tokens_per_minute" @change="patchPolicy(policy, { tokens_per_minute: Number(inputValue($event)) })" />
            </label>
            <label class="provider-inline">
              <span>Burst</span>
              <input type="number" :value="policy.burst_capacity" @change="patchPolicy(policy, { burst_capacity: Number(inputValue($event)) })" />
            </label>
            <label class="provider-inline">
              <span>Fresh</span>
              <input type="number" :value="policy.freshness_seconds" @change="patchPolicy(policy, { freshness_seconds: Number(inputValue($event)) })" />
            </label>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { api } from '@/lib/api'
import { usePresetsStore } from '@/stores/presets'
import type { ProviderPolicyStatus } from '@/types'

const presetsStore = usePresetsStore()
const oneSignalAppId = ref(localStorage.getItem('onesignal_app_id') ?? '')
const apiBase = ref(localStorage.getItem('api_base') ?? '')
const pushStatus = ref<{ ok: boolean; msg: string } | null>(null)
const connStatus = ref<{ ok: boolean; msg: string } | null>(null)
const providerPolicies = ref<ProviderPolicyStatus[]>([])
const providersLoading = ref(false)
const providerError = ref<string | null>(null)

const groupedPolicies = computed(() => {
  const groups = new Map<string, ProviderPolicyStatus[]>()
  for (const policy of providerPolicies.value) {
    const current = groups.get(policy.provider) ?? []
    current.push(policy)
    groups.set(policy.provider, current)
  }
  return [...groups.entries()].map(([provider, capabilities]) => ({
    provider,
    capabilities: capabilities.sort((a, b) => a.base_priority - b.base_priority || a.capability.localeCompare(b.capability)),
  }))
})

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

function inputValue(event: Event) {
  return (event.target as HTMLInputElement).value
}

function checkboxValue(event: Event) {
  return (event.target as HTMLInputElement).checked
}

async function loadProviderPolicies() {
  providersLoading.value = true
  providerError.value = null
  try {
    providerPolicies.value = await api.get<ProviderPolicyStatus[]>('/providers/policies')
  } catch (e: any) {
    providerError.value = e?.message ?? 'Failed to load providers'
  } finally {
    providersLoading.value = false
  }
}

async function patchPolicy(policy: ProviderPolicyStatus, patch: Record<string, unknown>) {
  try {
    await api.patch(`/providers/policies/${encodeURIComponent(policy.provider)}/${encodeURIComponent(policy.capability)}`, patch)
    await loadProviderPolicies()
  } catch (e: any) {
    providerError.value = e?.message ?? 'Failed to update provider policy'
  }
}

onMounted(async () => {
  presetsStore.loadPresets()
  await loadProviderPolicies()
})
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

.provider-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.provider-card {
  border: 1px solid #202020;
  border-radius: 6px;
  padding: 10px;
  background: #101010;
}

.provider-card-head {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  align-items: center;
  margin-bottom: 8px;
  color: #d7d7d7;
  font-size: 12px;
}

.provider-card-head span {
  color: #666;
  font-size: 11px;
}

.provider-row {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
  padding: 8px 0;
  border-top: 1px solid #1a1a1a;
}

.provider-main {
  min-width: 200px;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.provider-main strong {
  color: #efefef;
  font-size: 12px;
}

.provider-main small {
  color: #666;
  font-size: 10px;
}

.provider-check,
.provider-inline {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  color: #8a8a8a;
}

.provider-inline input {
  width: 72px;
  background: #181818;
  border: 1px solid #313131;
  color: #d4d4d4;
  border-radius: 4px;
  padding: 4px 6px;
  font: inherit;
}
</style>
