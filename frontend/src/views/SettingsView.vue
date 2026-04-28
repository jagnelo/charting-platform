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
      <p class="hint">Capability routing, fallback health, and observed provider usage over time.</p>
      <div v-if="providersLoading" class="empty-hint">Loading provider policies...</div>
      <div v-else-if="providerError" class="push-status err">{{ providerError }}</div>
      <div v-else class="provider-list">
        <div v-for="group in groupedPolicies" :key="group.provider" class="provider-card">
          <div class="provider-card-head">
            <div class="provider-title">
              <strong>{{ group.provider }}</strong>
              <span>{{ group.capabilities.length }} capabilities</span>
            </div>
            <small v-if="group.usage">{{ group.usage.requests_24h }} req / 24h</small>
          </div>

          <div v-if="group.usage" class="provider-telemetry">
            <div class="telemetry-grid">
              <div class="telemetry-stat">
                <span>24h</span>
                <strong>{{ group.usage.requests_24h }} req</strong>
                <small>{{ fmtUnits(group.usage.units_24h, group.usage.usage_unit_label) }}</small>
              </div>
              <div class="telemetry-stat">
                <span>7d</span>
                <strong>{{ group.usage.requests_7d }} req</strong>
                <small>{{ fmtUnits(group.usage.units_7d, group.usage.usage_unit_label) }}</small>
              </div>
              <div class="telemetry-stat">
                <span>Failures</span>
                <strong>{{ fmtPct(group.usage.failure_rate_24h) }}</strong>
                <small>Timeout {{ fmtPct(group.usage.timeout_rate_24h) }}</small>
              </div>
              <div class="telemetry-stat">
                <span>Latency</span>
                <strong>{{ fmtLatency(group.usage.avg_latency_ms_24h) }}</strong>
                <small>P95 {{ fmtLatency(group.usage.p95_latency_ms_24h) }}</small>
              </div>
            </div>

            <div class="telemetry-window">
              <template v-if="group.usage.limit_kind !== 'unknown' && group.usage.current_window_units != null">
                <strong>{{ quotaLabel(group.usage) }}</strong>
                <span>
                  {{ fmtUnits(group.usage.current_window_units, group.usage.usage_unit_label) }}
                  <template v-if="group.usage.current_window_requests != null">
                    · {{ group.usage.current_window_requests }} req
                  </template>
                  <template v-if="group.usage.current_window_utilization_pct != null">
                    · {{ fmtPct(group.usage.current_window_utilization_pct) }} used
                  </template>
                </span>
              </template>
              <template v-else>
                <strong>Observed usage only</strong>
                <span>No documented hard quota configured for this provider.</span>
              </template>
            </div>

            <div class="timeline-block">
              <div class="timeline-head">
                <strong>Last 24h</strong>
                <span>{{ group.usage.usage_unit_label }}</span>
              </div>
              <div class="timeline-bars">
                <div v-for="bucket in group.usage.hourly_buckets" :key="`${group.provider}-${bucket.bucket_start}`" class="timeline-bar-wrap">
                  <div class="timeline-bar" :style="{ height: `${bucketHeight(group.usage.hourly_buckets, bucket.units)}%` }" />
                </div>
              </div>
            </div>

            <div class="timeline-block">
              <div class="timeline-head">
                <strong>Last 7d</strong>
                <span>{{ group.usage.usage_unit_label }}</span>
              </div>
              <div class="timeline-bars daily">
                <div v-for="bucket in group.usage.daily_buckets" :key="`${group.provider}-day-${bucket.bucket_start}`" class="timeline-bar-wrap">
                  <div class="timeline-bar" :style="{ height: `${bucketHeight(group.usage.daily_buckets, bucket.units)}%` }" />
                </div>
              </div>
            </div>

            <div v-if="group.usage.top_operations.length" class="telemetry-table">
              <div class="telemetry-table-head">
                <strong>Top operations</strong>
              </div>
              <div v-for="row in group.usage.top_operations.slice(0, 5)" :key="`${group.provider}-${row.operation_family}`" class="telemetry-row">
                <span>{{ row.operation_family }}</span>
                <span>{{ row.requests }} req</span>
                <span>{{ fmtUnits(row.units, group.usage.usage_unit_label) }}</span>
                <span>{{ row.failures }} fail</span>
              </div>
            </div>

            <div v-if="group.usage.error_breakdown.length" class="telemetry-table">
              <div class="telemetry-table-head">
                <strong>Recent errors</strong>
              </div>
              <div v-for="row in group.usage.error_breakdown" :key="`${group.provider}-err-${row.error_type}`" class="telemetry-row">
                <span>{{ row.error_type }}</span>
                <span>{{ row.count }}</span>
              </div>
            </div>
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
import type { ProviderPolicyStatus, ProviderUsageBucket, ProviderUsageSummary } from '@/types'

const presetsStore = usePresetsStore()
const oneSignalAppId = ref(localStorage.getItem('onesignal_app_id') ?? '')
const apiBase = ref(localStorage.getItem('api_base') ?? '')
const pushStatus = ref<{ ok: boolean; msg: string } | null>(null)
const connStatus = ref<{ ok: boolean; msg: string } | null>(null)
const providerPolicies = ref<ProviderPolicyStatus[]>([])
const providerUsage = ref<ProviderUsageSummary[]>([])
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
    usage: providerUsage.value.find((row) => row.provider === provider) ?? null,
    capabilities: capabilities.sort((a, b) => a.base_priority - b.base_priority || a.capability.localeCompare(b.capability)),
  }))
})

function fmtUnits(value: number | null | undefined, unitLabel: string) {
  if (value == null) return `0 ${unitLabel}`
  return `${value.toFixed(value >= 10 ? 0 : 1)} ${unitLabel}`
}

function fmtPct(value: number | null | undefined) {
  if (value == null) return '0%'
  return `${value.toFixed(1)}%`
}

function fmtLatency(value: number | null | undefined) {
  if (value == null) return 'n/a'
  return `${Math.round(value)}ms`
}

function quotaLabel(usage: ProviderUsageSummary) {
  const limit = usage.quota_limit ?? usage.estimated_quota_limit
  if (limit == null) return 'Quota window'
  const kind = usage.limit_kind === 'estimated' ? 'Est.' : 'Quota'
  return `${kind} ${limit} ${usage.usage_unit_label}`
}

function bucketHeight(buckets: ProviderUsageBucket[], value: number) {
  const max = Math.max(...buckets.map((bucket) => bucket.units || 0), 0)
  if (max <= 0 || value <= 0) return 8
  return Math.max(8, Math.min(100, (value / max) * 100))
}

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
    const [policies, usage] = await Promise.all([
      api.get<ProviderPolicyStatus[]>('/providers/policies'),
      api.get<ProviderUsageSummary[]>('/providers/usage'),
    ])
    providerPolicies.value = policies
    providerUsage.value = usage
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

.provider-title {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.provider-card-head span {
  color: #666;
  font-size: 11px;
}

.provider-card-head small {
  color: #7aaef8;
  font-size: 11px;
}

.provider-telemetry {
  display: grid;
  gap: 10px;
  margin-bottom: 8px;
  padding-bottom: 10px;
  border-bottom: 1px solid #1a1a1a;
}

.telemetry-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
  gap: 8px;
}

.telemetry-stat {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.telemetry-stat span,
.timeline-head span,
.telemetry-window span {
  color: #6f6f6f;
  font-size: 10px;
}

.telemetry-stat strong,
.telemetry-window strong,
.timeline-head strong,
.telemetry-table-head strong {
  color: #e8e8e8;
  font-size: 12px;
}

.telemetry-stat small {
  color: #8e8e8e;
  font-size: 10px;
}

.telemetry-window {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}

.timeline-block {
  display: grid;
  gap: 6px;
}

.timeline-head {
  display: flex;
  justify-content: space-between;
  gap: 8px;
}

.timeline-bars {
  display: grid;
  grid-template-columns: repeat(24, minmax(0, 1fr));
  gap: 4px;
  align-items: end;
  min-height: 54px;
}

.timeline-bars.daily {
  grid-template-columns: repeat(7, minmax(0, 1fr));
}

.timeline-bar-wrap {
  height: 54px;
  display: flex;
  align-items: end;
}

.timeline-bar {
  width: 100%;
  min-height: 4px;
  border-radius: 4px;
  background: #64b5f6;
  opacity: 0.9;
}

.telemetry-table {
  display: grid;
  gap: 4px;
}

.telemetry-table-head {
  display: flex;
  align-items: center;
}

.telemetry-row {
  display: grid;
  grid-template-columns: minmax(0, 1.8fr) repeat(3, minmax(0, 0.8fr));
  gap: 8px;
  color: #8e8e8e;
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
