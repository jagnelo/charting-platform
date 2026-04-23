<template>
  <div class="options-panel">
    <div class="options-toolbar">
      <div class="options-title-wrap">
        <strong class="options-title">{{ titleText }}</strong>
        <span v-if="snapshotMeta" class="options-meta" :title="snapshotTitle">
          {{ snapshotMeta.provider || 'provider' }} · {{ snapshotTime }}
        </span>
      </div>
      <div class="options-actions" v-if="symbol">
        <select
          v-if="response?.available_expirations?.length"
          :value="selectedExpiration"
          class="options-select"
          @change="onExpirationChange"
        >
          <option v-for="item in response.available_expirations" :key="item" :value="item">{{ item }}</option>
        </select>
        <button class="options-refresh" @click="load(true)">Refresh</button>
      </div>
    </div>

    <div v-if="!symbol" class="options-state">Choose an instrument</div>
    <div v-else-if="loading" class="options-state">Loading options...</div>
    <div v-else-if="error" class="options-state error">{{ error }}</div>
    <div v-else-if="!rows.length" class="options-state">No options available</div>
    <div v-else class="options-table-wrap">
      <table class="options-table" :class="{ compact }">
        <thead>
          <tr>
            <th>Contract</th>
            <th>Bid</th>
            <th>Ask</th>
            <th>Mark</th>
            <th>Last</th>
            <th>Vol</th>
            <th>OI</th>
            <th>IV</th>
            <th>Delta</th>
            <th>Gamma</th>
            <th>Theta</th>
            <th>Vega</th>
            <th>Rho</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="row in rows"
            :key="row.instrument_id"
            class="options-row"
            @click="$emit('open-symbol', row.symbol)"
          >
            <td class="contract-col">
              <div class="contract-main">{{ row.right.toUpperCase().slice(0, 1) }} {{ fmt(row.strike, 2) }}</div>
              <div class="contract-sub">{{ row.expiry_date }}</div>
            </td>
            <td>{{ fmt(row.bid) }}</td>
            <td>{{ fmt(row.ask) }}</td>
            <td>{{ fmt(row.mark) }}</td>
            <td>{{ fmt(row.last) }}</td>
            <td>{{ fmtInt(row.volume) }}</td>
            <td>{{ fmtInt(row.open_interest) }}</td>
            <td>{{ fmtPct(row.implied_vol) }}</td>
            <td>{{ fmtSigned(row.delta) }}</td>
            <td>{{ fmtSigned(row.gamma) }}</td>
            <td>{{ fmtSigned(row.theta) }}</td>
            <td>{{ fmtSigned(row.vega) }}</td>
            <td>{{ fmtSigned(row.rho) }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { api } from '@/lib/api'
import type { OptionChainResponse, OptionChainRow } from '@/types'

const props = withDefaults(defineProps<{
  symbol?: string | null
  title?: string
  compact?: boolean
}>(), {
  title: 'Options Chain',
  compact: false,
})

defineEmits<{
  'open-symbol': [symbol: string]
}>()

const loading = ref(false)
const error = ref<string | null>(null)
const response = ref<OptionChainResponse | null>(null)
const selectedExpiration = ref('')
let refreshSeq = 0

const rows = computed<OptionChainRow[]>(() => response.value?.rows ?? [])
const snapshotMeta = computed(() => response.value?.snapshot ?? null)
const snapshotTime = computed(() =>
  snapshotMeta.value?.observed_at ? new Date(snapshotMeta.value.observed_at).toLocaleString() : ''
)
const snapshotTitle = computed(() => {
  const snapshot = snapshotMeta.value
  if (!snapshot) return ''
  return [
    `Source: ${snapshot.provider || 'unknown'}`,
    `Observed: ${new Date(snapshot.observed_at).toLocaleString()}`,
    `Fetched: ${new Date(snapshot.fetched_at).toLocaleString()}`,
    `Contracts: ${snapshot.contract_count}`,
  ].join('\n')
})
const titleText = computed(() => props.title || 'Options Chain')

async function load(force = false) {
  const symbol = props.symbol?.trim().toUpperCase()
  const seq = ++refreshSeq
  if (!symbol) {
    response.value = null
    error.value = null
    loading.value = false
    return
  }
  loading.value = true
  error.value = null
  try {
    const loaded = await api.get<OptionChainResponse>(
      `/instruments/${encodeURIComponent(symbol)}/options/chain`,
      {
        expiration: selectedExpiration.value || undefined,
        refresh: force || undefined,
      },
    )
    if (seq !== refreshSeq) return
    response.value = loaded
    selectedExpiration.value = loaded.expiration ?? loaded.available_expirations[0] ?? ''
  } catch (e: any) {
    if (seq === refreshSeq) error.value = e?.message ?? 'Options unavailable'
  } finally {
    if (seq === refreshSeq) loading.value = false
  }
}

function onExpirationChange(event: Event) {
  selectedExpiration.value = (event.target as HTMLSelectElement).value
  load(false)
}

function fmt(value?: number | null, digits = 2) {
  if (value == null || !Number.isFinite(value)) return '—'
  return Number(value).toLocaleString(undefined, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })
}

function fmtInt(value?: number | null) {
  if (value == null || !Number.isFinite(value)) return '—'
  return Math.round(value).toLocaleString()
}

function fmtPct(value?: number | null) {
  if (value == null || !Number.isFinite(value)) return '—'
  return `${(value * 100).toFixed(2)}%`
}

function fmtSigned(value?: number | null) {
  if (value == null || !Number.isFinite(value)) return '—'
  return `${value >= 0 ? '+' : ''}${value.toFixed(4)}`
}

watch(() => props.symbol, () => {
  selectedExpiration.value = ''
  load(false)
})
onMounted(() => load(false))
</script>

<style scoped>
.options-panel {
  height: 100%;
  display: flex;
  flex-direction: column;
  min-height: 0;
  color: #c7c7c7;
}

.options-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 8px 10px;
  border-bottom: 1px solid #191919;
  background: #101010;
}

.options-title-wrap {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.options-title {
  font-size: 11px;
  color: #f2f2f2;
}

.options-meta {
  font-size: 10px;
  color: #6d6d6d;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.options-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.options-select,
.options-refresh {
  background: #151515;
  border: 1px solid #2b2b2b;
  color: #c7c7c7;
  border-radius: 4px;
  font: inherit;
  font-size: 11px;
  padding: 5px 8px;
}

.options-refresh {
  cursor: pointer;
}

.options-table-wrap {
  flex: 1;
  min-height: 0;
  overflow: auto;
}

.options-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 11px;
}

.options-table.compact {
  font-size: 10px;
}

.options-table th,
.options-table td {
  padding: 7px 8px;
  border-bottom: 1px solid #161616;
  text-align: right;
  white-space: nowrap;
}

.options-table th:first-child,
.options-table td:first-child {
  text-align: left;
}

.options-table thead th {
  position: sticky;
  top: 0;
  z-index: 1;
  background: #111;
  color: #6d6d6d;
  font-weight: 600;
}

.options-row {
  cursor: pointer;
}

.options-row:hover {
  background: #121a23;
}

.contract-col {
  min-width: 98px;
}

.contract-main {
  color: #f0f0f0;
  font-weight: 600;
}

.contract-sub {
  color: #666;
  font-size: 10px;
}

.options-state {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #565656;
  font-size: 12px;
  padding: 12px;
  text-align: center;
}

.options-state.error {
  color: #ef5350;
}
</style>
