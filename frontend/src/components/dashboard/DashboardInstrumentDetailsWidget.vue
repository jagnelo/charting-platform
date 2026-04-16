<template>
  <div class="details-widget">
    <div v-if="loading" class="widget-state">Loading {{ symbol }}...</div>
    <div v-else-if="!symbol" class="widget-state">Choose an instrument</div>
    <div v-else-if="error" class="widget-state error">{{ error }}</div>
    <template v-else-if="instrument">
      <div class="details-main">
        <div class="details-symbol">{{ instrument.symbol }}</div>
        <router-link class="details-open" :to="`/chart/${encodeURIComponent(instrument.symbol)}`">Open</router-link>
      </div>
      <div class="details-name">{{ instrument.name || instrument.description }}</div>
      <div class="details-grid">
        <div v-for="row in rows" :key="row.label" class="detail-row">
          <span>{{ row.label }}</span>
          <b>{{ row.value || '-' }}</b>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { api } from '@/lib/api'
import type { Instrument } from '@/types'

const props = defineProps<{ config: Record<string, any> }>()

const loading = ref(false)
const error = ref<string | null>(null)
const instrument = ref<Instrument | null>(null)
const symbol = computed(() => String(props.config.symbol ?? '').trim().toUpperCase())
const EXPR_RE = /^[A-Z0-9.^]+(\s*[+\-*/]\s*[A-Z0-9.^]+)+$/i
let refreshSeq = 0

const rows = computed(() => {
  const detail = instrument.value?.equity_detail
  const stats = instrument.value?.stats
  return [
    { label: 'Currency', value: instrument.value?.currency },
    { label: 'Sector', value: detail?.sector },
    { label: 'Industry', value: detail?.industry },
    { label: 'Country', value: detail?.country },
    { label: 'Market Cap', value: formatLarge(stats?.market_cap) },
    { label: 'P/E', value: stats?.pe_ratio?.toFixed(2) },
    { label: 'Beta', value: stats?.beta?.toFixed(2) },
    { label: '52W High', value: formatNumber(stats?.week52_high) },
    { label: '52W Low', value: formatNumber(stats?.week52_low) },
  ]
})

function formatNumber(value?: number) {
  if (value == null) return ''
  return value.toLocaleString(undefined, { maximumFractionDigits: 2 })
}

function formatLarge(value?: number) {
  if (value == null) return ''
  if (value >= 1e12) return `${(value / 1e12).toFixed(2)}T`
  if (value >= 1e9) return `${(value / 1e9).toFixed(2)}B`
  if (value >= 1e6) return `${(value / 1e6).toFixed(2)}M`
  return formatNumber(value)
}

async function refresh() {
  const seq = ++refreshSeq
  if (!symbol.value) {
    instrument.value = null
    error.value = null
    loading.value = false
    return
  }
  loading.value = true
  error.value = null
  try {
    const target = await resolveTarget(symbol.value)
    if (seq !== refreshSeq) return
    instrument.value = await api.get<Instrument>(`/instruments/${encodeURIComponent(target)}`)
    if (
      !instrument.value.is_synthetic
      && (!instrument.value.stats?.week52_high || !instrument.value.stats?.week52_low)
    ) {
      await api.get(`/ohlcv/${encodeURIComponent(target)}/D1`, { limit: 260 })
      if (seq !== refreshSeq) return
      instrument.value = await api.get<Instrument>(`/instruments/${encodeURIComponent(target)}`)
    }
  } catch (e: any) {
    if (seq === refreshSeq) error.value = e?.message ?? 'Instrument unavailable'
  } finally {
    if (seq === refreshSeq) loading.value = false
  }
}

async function resolveTarget(target: string) {
  if (!EXPR_RE.test(target)) return target
  const instrument = await api.post<{ symbol: string }>('/instruments/resolve-expression', {
    expression: target,
  })
  return instrument.symbol
}

watch(symbol, refresh)
onMounted(refresh)
</script>

<style scoped>
.details-widget {
  height: 100%;
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-width: 0;
}
.details-main {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  align-items: center;
}
.details-symbol { color: #fff; font-size: 17px; font-weight: 800; }
.details-open {
  color: #64b5f6;
  text-decoration: none;
  border: 1px solid #242424;
  border-radius: 4px;
  padding: 3px 6px;
  font-size: 10px;
}
.details-name { color: #888; font-size: 11px; line-height: 1.35; }
.details-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 5px 10px;
  overflow: auto;
  min-height: 0;
}
.detail-row {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  color: #777;
  font-size: 10px;
  border-bottom: 1px solid #181818;
  padding-bottom: 4px;
}
.detail-row b {
  color: #ccc;
  font-weight: 500;
  text-align: right;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.widget-state {
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #555;
  font-size: 12px;
  text-align: center;
  padding: 12px;
}
.widget-state.error { color: #ef5350; font-size: 10px; }
</style>
