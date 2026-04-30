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
        <div v-for="group in providerCards" :key="group.provider" class="provider-card">
          <div class="provider-card-head">
            <div class="provider-title">
              <div class="provider-title-row">
                <strong>{{ group.provider }}</strong>
                <span>{{ group.capabilities.length }} capabilities</span>
              </div>
              <p class="provider-summary-text">{{ providerSummaryText(group) }}</p>
            </div>
            <div class="provider-card-actions">
              <button
                type="button"
                class="provider-toggle"
                :aria-expanded="isPanelOpen(group.provider, 'usage')"
                @click="togglePanel(group.provider, 'usage')"
              >
                {{ isPanelOpen(group.provider, 'usage') ? 'Hide usage' : 'Show usage' }}
              </button>
              <button
                type="button"
                class="provider-toggle"
                :aria-expanded="isPanelOpen(group.provider, 'config')"
                @click="togglePanel(group.provider, 'config')"
              >
                {{ isPanelOpen(group.provider, 'config') ? 'Hide config' : 'Show config' }}
              </button>
            </div>
          </div>

          <div class="provider-summary-grid">
            <div class="provider-summary-card">
              <span>Calls</span>
              <strong>{{ group.usage ? fmtCount(group.usage.requests_24h, 'calls') : 'No traffic' }}</strong>
              <small>{{ group.usage ? `7d ${fmtCount(group.usage.requests_7d, 'calls')}` : 'No recorded requests yet' }}</small>
            </div>
            <div class="provider-summary-card">
              <span>Reliability</span>
              <strong>{{ group.usage ? fmtPct(group.usage.success_rate_24h) : 'No data' }}</strong>
              <small>{{ reliabilityDetail(group.usage) }}</small>
            </div>
            <div class="provider-summary-card">
              <span>Latency</span>
              <strong>{{ group.usage ? fmtLatency(group.usage.avg_latency_ms_24h) : 'n/a' }}</strong>
              <small>{{ group.usage ? `P95 ${fmtLatency(group.usage.p95_latency_ms_24h)}` : 'No recent timing samples' }}</small>
            </div>
            <div class="provider-summary-card">
              <span>Tracking</span>
              <strong>{{ trackingHeadline(group.usage) }}</strong>
              <small>{{ trackingDetail(group.usage) }}</small>
            </div>
            <div class="provider-summary-card">
              <span>Configuration</span>
              <strong>{{ `${group.enabledCount}/${group.capabilities.length} enabled` }}</strong>
              <small>{{ `${group.pinnedCount} pinned · ${group.autoCount} auto-weighted` }}</small>
            </div>
          </div>

          <div v-if="group.usage && isPanelOpen(group.provider, 'usage')" class="provider-panel">
            <div class="provider-panel-head">
              <strong>Usage details</strong>
              <span>{{ usagePanelIntro(group.usage) }}</span>
            </div>
            <div class="usage-meta-grid">
              <div class="usage-meta-card">
                <span>Last request</span>
                <strong>{{ formatDateTime(group.usage.last_request_at) }}</strong>
              </div>
              <div class="usage-meta-card">
                <span>Last success</span>
                <strong>{{ formatDateTime(group.usage.last_success_at) }}</strong>
              </div>
              <div class="usage-meta-card">
                <span>Last failure</span>
                <strong>{{ formatDateTime(group.usage.last_failure_at) }}</strong>
              </div>
              <div class="usage-meta-card">
                <span>Retention</span>
                <strong>{{ fmtCount(group.usage.retained_requests, 'logged calls') }}</strong>
              </div>
            </div>

            <div class="timeline-layout">
              <div class="timeline-block">
                <div class="timeline-head">
                  <strong>Last 24h</strong>
                  <span>{{ usageMetricLabel(group.usage, 'calls') }}</span>
                </div>
                <div class="timeline-bars">
                  <div v-for="bucket in group.usage.hourly_buckets" :key="`${group.provider}-${bucket.bucket_start}`" class="timeline-bar-wrap">
                    <div class="timeline-bar" :style="{ height: `${bucketHeight(group.usage.hourly_buckets, usageBucketValue(group.usage, bucket))}%` }" />
                  </div>
                </div>
              </div>

              <div class="timeline-block">
                <div class="timeline-head">
                  <strong>Last 7d</strong>
                  <span>{{ usageMetricLabel(group.usage, 'calls') }}</span>
                </div>
                <div class="timeline-bars daily">
                  <div v-for="bucket in group.usage.daily_buckets" :key="`${group.provider}-day-${bucket.bucket_start}`" class="timeline-bar-wrap">
                    <div class="timeline-bar" :style="{ height: `${bucketHeight(group.usage.daily_buckets, usageBucketValue(group.usage, bucket))}%` }" />
                  </div>
                </div>
              </div>
            </div>

            <div v-if="group.usage.top_operations.length" class="telemetry-table">
              <div class="telemetry-table-head">
                <strong>Top operations</strong>
                <span>Most active actions over the last 7 days</span>
              </div>
              <div class="telemetry-row telemetry-row--head" :class="{ 'telemetry-row--with-usage': hasDistinctUsageUnits(group.usage) }">
                <span>Operation</span>
                <span>Calls</span>
                <span v-if="hasDistinctUsageUnits(group.usage)">Usage</span>
                <span>Failures</span>
              </div>
              <div
                v-for="row in group.usage.top_operations.slice(0, 5)"
                :key="`${group.provider}-${row.operation_family}`"
                class="telemetry-row"
                :class="{ 'telemetry-row--with-usage': hasDistinctUsageUnits(group.usage) }"
              >
                <span>{{ humanizeKey(row.operation_family) }}</span>
                <span>{{ fmtCount(row.requests, 'calls') }}</span>
                <span v-if="hasDistinctUsageUnits(group.usage)">{{ fmtUnits(row.units, group.usage.usage_unit_label) }}</span>
                <span>{{ row.failures }} failed</span>
              </div>
            </div>

            <div v-if="group.usage.error_breakdown.length" class="telemetry-table">
              <div class="telemetry-table-head">
                <strong>Recent errors</strong>
                <span>Failure types seen in the same 7-day window</span>
              </div>
              <div v-for="row in group.usage.error_breakdown" :key="`${group.provider}-err-${row.error_type}`" class="telemetry-row telemetry-row--errors">
                <span>{{ row.error_type }}</span>
                <span>{{ row.count }}</span>
              </div>
            </div>
          </div>

          <div v-if="isPanelOpen(group.provider, 'config')" class="provider-panel">
            <div class="provider-panel-head">
              <strong>Capability configuration</strong>
              <span>Expand this only when you need to tune routing and freshness behavior.</span>
            </div>

            <div class="capability-list">
              <div v-for="policy in group.capabilities" :key="`${policy.provider}:${policy.capability}`" class="capability-card">
                <div class="capability-head">
                  <div class="provider-main">
                    <strong>{{ humanizeKey(policy.capability) }}</strong>
                    <small>{{ capabilitySummary(policy) }}</small>
                  </div>
                  <div class="capability-badges">
                    <span class="capability-badge" :class="policy.is_enabled ? 'ok' : 'off'">{{ policy.is_enabled ? 'Enabled' : 'Disabled' }}</span>
                    <span class="capability-badge" :class="policy.is_pinned ? 'pin' : 'muted'">{{ policy.is_pinned ? 'Pinned' : 'Fallback' }}</span>
                    <span class="capability-badge" :class="policy.auto_weight_enabled ? 'auto' : 'muted'">{{ policy.auto_weight_enabled ? 'Auto' : 'Manual' }}</span>
                  </div>
                </div>

                <div class="capability-controls">
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
                    <span>Auto-weight</span>
                  </label>
                </div>

                <div class="capability-grid">
                  <label class="provider-inline">
                    <span>Priority</span>
                    <input type="number" :value="policy.base_priority" @change="patchPolicy(policy, { base_priority: Number(inputValue($event)) })" />
                  </label>
                  <label class="provider-inline">
                    <span>Tokens / min</span>
                    <input type="number" :value="policy.tokens_per_minute" @change="patchPolicy(policy, { tokens_per_minute: Number(inputValue($event)) })" />
                  </label>
                  <label class="provider-inline">
                    <span>Burst</span>
                    <input type="number" :value="policy.burst_capacity" @change="patchPolicy(policy, { burst_capacity: Number(inputValue($event)) })" />
                  </label>
                  <label class="provider-inline">
                    <span>Freshness</span>
                    <input type="number" :value="policy.freshness_seconds" @change="patchPolicy(policy, { freshness_seconds: Number(inputValue($event)) })" />
                  </label>
                </div>

                <div class="capability-foot">
                  <span>{{ statusWindow(policy) }}</span>
                  <span v-if="policy.last_error_type">{{ `${policy.last_error_type}: ${policy.last_error_message || 'No detail'}` }}</span>
                </div>
              </div>
            </div>
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
const providerPanels = ref<Record<string, { usage: boolean; config: boolean }>>({})

const providerCards = computed(() => {
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
    enabledCount: capabilities.filter((policy) => policy.is_enabled).length,
    pinnedCount: capabilities.filter((policy) => policy.is_pinned).length,
    autoCount: capabilities.filter((policy) => policy.auto_weight_enabled).length,
  }))
})

function hasDistinctUsageUnits(usage: ProviderUsageSummary | null) {
  return !!usage && usage.usage_unit_label.trim().toLowerCase() !== 'requests'
}

function usageMetricLabel(usage: ProviderUsageSummary | null, fallbackLabel = 'calls') {
  return hasDistinctUsageUnits(usage) ? usage!.usage_unit_label : fallbackLabel
}

function humanizeKey(value: string) {
  return value
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (char) => char.toUpperCase())
}

function fmtCount(value: number | null | undefined, label = 'calls') {
  return `${Math.round(value ?? 0).toLocaleString()} ${label}`
}

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

function formatDateTime(value: string | null | undefined) {
  if (!value) return 'Not seen yet'
  return new Date(value).toLocaleString()
}

function quotaLabel(usage: ProviderUsageSummary) {
  const limit = usage.quota_limit ?? usage.estimated_quota_limit
  if (limit == null) return 'Quota window'
  const kind = usage.limit_kind === 'estimated' ? 'Est.' : 'Quota'
  return `${kind} ${limit} ${usage.usage_unit_label}`
}

function usageBucketValue(usage: ProviderUsageSummary, bucket: ProviderUsageBucket) {
  return hasDistinctUsageUnits(usage) ? bucket.units : bucket.requests
}

function bucketHeight(buckets: ProviderUsageBucket[], value: number) {
  const max = Math.max(...buckets.map((bucket) => Math.max(bucket.units || 0, bucket.requests || 0)), 0)
  if (max <= 0 || value <= 0) return 8
  return Math.max(8, Math.min(100, (value / max) * 100))
}

function failureCount(usage: ProviderUsageSummary | null) {
  if (!usage) return 0
  return Math.round(((usage.failure_rate_24h || 0) / 100) * usage.requests_24h)
}

function timeoutCount(usage: ProviderUsageSummary | null) {
  if (!usage) return 0
  return Math.round(((usage.timeout_rate_24h || 0) / 100) * usage.requests_24h)
}

function reliabilityDetail(usage: ProviderUsageSummary | null) {
  if (!usage || usage.requests_24h === 0) return 'No recent failures recorded'
  return `${failureCount(usage)} failed · ${timeoutCount(usage)} timed out`
}

function trackingHeadline(usage: ProviderUsageSummary | null) {
  if (!usage) return 'Policy only'
  if (usage.limit_kind !== 'unknown' && usage.current_window_units != null) return quotaLabel(usage)
  return hasDistinctUsageUnits(usage) ? `Tracked in ${usage.usage_unit_label}` : 'Observed calls only'
}

function trackingDetail(usage: ProviderUsageSummary | null) {
  if (!usage) return 'No usage summary available yet'
  if (usage.limit_kind !== 'unknown' && usage.current_window_units != null) {
    const parts = [fmtUnits(usage.current_window_units, usage.usage_unit_label)]
    if (usage.current_window_requests != null) parts.push(fmtCount(usage.current_window_requests))
    if (usage.current_window_utilization_pct != null) parts.push(`${fmtPct(usage.current_window_utilization_pct)} used`)
    return parts.join(' · ')
  }
  return 'No hard quota documented for this provider'
}

function providerSummaryText(group: { usage: ProviderUsageSummary | null; enabledCount: number; capabilities: ProviderPolicyStatus[] }) {
  if (!group.usage) return `${group.enabledCount} of ${group.capabilities.length} capabilities enabled.`
  return `${fmtCount(group.usage.requests_24h)} in the last 24h with ${fmtPct(group.usage.success_rate_24h)} success.`
}

function usagePanelIntro(usage: ProviderUsageSummary) {
  return hasDistinctUsageUnits(usage)
    ? `Calls and ${usage.usage_unit_label} are tracked separately.`
    : 'Traffic is tracked by call count.'
}

function capabilitySummary(policy: ProviderPolicyStatus) {
  return `Priority ${policy.base_priority} · score ${policy.effective_score.toFixed(2)} · latency ${policy.ewma_latency_ms.toFixed(0)}ms`
}

function statusWindow(policy: ProviderPolicyStatus) {
  if (policy.circuit_open_until) return `Circuit open until ${formatDateTime(policy.circuit_open_until)}`
  if (policy.last_failure_at) return `Last failure ${formatDateTime(policy.last_failure_at)} · streak ${policy.failure_streak}`
  if (policy.last_success_at) return `Last success ${formatDateTime(policy.last_success_at)}`
  return 'No recent execution history'
}

function isPanelOpen(provider: string, panel: 'usage' | 'config') {
  return providerPanels.value[provider]?.[panel] ?? false
}

function togglePanel(provider: string, panel: 'usage' | 'config') {
  const current = providerPanels.value[provider] ?? { usage: false, config: false }
  providerPanels.value = {
    ...providerPanels.value,
    [provider]: { ...current, [panel]: !current[panel] },
  }
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
  gap: 16px;
}

.provider-card {
  border: 1px solid #212121;
  border-radius: 10px;
  padding: 14px;
  background:
    radial-gradient(circle at top right, rgba(100, 181, 246, 0.08), transparent 28%),
    linear-gradient(180deg, rgba(15, 15, 15, 0.98), rgba(11, 11, 11, 0.98));
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.03);
}

.provider-card-head {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
  margin-bottom: 14px;
  color: #d7d7d7;
  font-size: 12px;
  flex-wrap: wrap;
}

.provider-title {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
}

.provider-title-row {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 8px;
}

.provider-title-row strong {
  color: #f0f0f0;
  font-size: 17px;
  letter-spacing: 0.01em;
}

.provider-summary-text {
  margin: 0;
  color: #8f8f8f;
  font-size: 11px;
  line-height: 1.45;
}

.provider-title-row span {
  color: #666;
  font-size: 11px;
}

.provider-card-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.provider-toggle {
  background: #121b24;
  border: 1px solid #27384c;
  color: #9dc4f5;
  border-radius: 999px;
  padding: 7px 12px;
  cursor: pointer;
  font-size: 11px;
  font-family: inherit;
}

.provider-toggle:hover {
  border-color: #4e81b6;
  color: #d3e7ff;
}

.provider-summary-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 10px;
}

.provider-summary-card,
.usage-meta-card {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 12px;
  border: 1px solid #1f1f1f;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.015);
}

.provider-summary-card span,
.usage-meta-card span {
  color: #727272;
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
}

.provider-summary-card strong,
.usage-meta-card strong {
  color: #f1f1f1;
  font-size: 15px;
}

.provider-summary-card small,
.usage-meta-card small {
  color: #8a8a8a;
  font-size: 10px;
}

.provider-panel {
  display: flex;
  flex-direction: column;
  gap: 14px;
  margin-top: 14px;
  padding-top: 14px;
  border-top: 1px solid #1a1a1a;
}

.provider-panel-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: baseline;
  flex-wrap: wrap;
}

.provider-panel-head strong,
.timeline-head strong,
.telemetry-table-head strong {
  color: #ececec;
  font-size: 12px;
}

.provider-panel-head span,
.timeline-head span,
.telemetry-table-head span {
  color: #8e8e8e;
  font-size: 10px;
}

.usage-meta-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 10px;
}

.timeline-layout {
  display: grid;
  gap: 12px;
}

.timeline-block {
  display: grid;
  gap: 6px;
  padding: 12px;
  border: 1px solid #1f1f1f;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.015);
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
  gap: 6px;
  padding: 12px;
  border: 1px solid #1f1f1f;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.015);
}

.telemetry-table-head {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  align-items: baseline;
  flex-wrap: wrap;
}

.telemetry-row {
  display: grid;
  grid-template-columns: minmax(0, 1.7fr) minmax(96px, 0.8fr) minmax(96px, 0.8fr);
  gap: 8px;
  color: #8e8e8e;
  font-size: 11px;
  align-items: baseline;
  padding: 4px 0;
  border-top: 1px solid #171717;
}

.telemetry-row--head {
  color: #6f6f6f;
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
}

.telemetry-row--with-usage {
  grid-template-columns: minmax(0, 1.7fr) repeat(3, minmax(96px, 0.8fr));
}

.telemetry-row--errors {
  grid-template-columns: minmax(0, 1.8fr) minmax(60px, 0.5fr);
}

.capability-list {
  display: grid;
  gap: 12px;
}

.capability-card {
  display: grid;
  gap: 12px;
  padding: 12px;
  border: 1px solid #1f1f1f;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.015);
}

.capability-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
  flex-wrap: wrap;
}

.capability-badges {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.capability-badge {
  display: inline-flex;
  align-items: center;
  border-radius: 999px;
  padding: 3px 8px;
  font-size: 10px;
  border: 1px solid #2c2c2c;
}

.capability-badge.ok { color: #84d28d; border-color: rgba(132, 210, 141, 0.3); }
.capability-badge.off { color: #b58a8a; border-color: rgba(181, 138, 138, 0.28); }
.capability-badge.pin { color: #f3c97e; border-color: rgba(243, 201, 126, 0.28); }
.capability-badge.auto { color: #9dc4f5; border-color: rgba(157, 196, 245, 0.28); }
.capability-badge.muted { color: #7c7c7c; }

.capability-controls {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}

.capability-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 10px;
}

.capability-foot {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  flex-wrap: wrap;
  color: #787878;
  font-size: 10px;
}

.provider-main {
  min-width: 220px;
  display: flex;
  flex-direction: column;
  gap: 4px;
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
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 11px;
  color: #8a8a8a;
}

.provider-check {
  flex-direction: row;
  align-items: center;
}

.provider-inline input {
  width: 100%;
  background: #181818;
  border: 1px solid #313131;
  color: #d4d4d4;
  border-radius: 4px;
  padding: 4px 6px;
  font: inherit;
}

@media (max-width: 760px) {
  .settings-view { padding: 18px; }
  .provider-card { padding: 12px; }
  .provider-card-actions { width: 100%; }
  .provider-toggle { flex: 1 1 140px; justify-content: center; }
  .telemetry-row,
  .telemetry-row--with-usage,
  .telemetry-row--errors {
    grid-template-columns: 1fr;
    gap: 4px;
  }
  .capability-foot {
    flex-direction: column;
  }
}
</style>
