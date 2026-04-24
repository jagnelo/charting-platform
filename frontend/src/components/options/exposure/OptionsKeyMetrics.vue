<template>
  <div class="key-metrics">
    <div class="metric">
      <span class="metric-label">Spot</span>
      <span class="metric-value">{{ fmt(data.spot) }}</span>
    </div>
    <div class="metric">
      <span class="metric-label">Call Wall</span>
      <span class="metric-value bullish">{{ fmt(data.key_levels.call_wall) }}</span>
    </div>
    <div class="metric">
      <span class="metric-label">Put Wall</span>
      <span class="metric-value bearish">{{ fmt(data.key_levels.put_wall) }}</span>
    </div>
    <div class="metric">
      <span class="metric-label">Gamma Flip</span>
      <span class="metric-value" :class="gammaFlipClass">{{ fmt(data.key_levels.gamma_flip) }}</span>
    </div>
    <div class="metric">
      <span class="metric-label">Max Pain</span>
      <span class="metric-value">{{ fmt(data.key_levels.max_pain) }}</span>
    </div>
    <div class="metric">
      <span class="metric-label">PCR (OI)</span>
      <span class="metric-value" :class="pcrClass">{{ fmtRatio(data.pcr_oi) }}</span>
    </div>
    <div class="metric">
      <span class="metric-label">PCR (Vol)</span>
      <span class="metric-value">{{ fmtRatio(data.pcr_volume) }}</span>
    </div>
    <div class="metric">
      <span class="metric-label">Implied Move</span>
      <span class="metric-value">{{ fmtPct(data.implied_move_pct) }}</span>
    </div>
    <div class="metric">
      <span class="metric-label">Total GEX</span>
      <span class="metric-value" :class="totalGexClass">{{ fmtGex(data.total_gex) }}</span>
    </div>
    <div v-if="data.greeks_estimated" class="metric est-badge" title="Some Greeks were estimated via Black-Scholes">
      <span class="metric-label">Greeks</span>
      <span class="metric-value est">~est</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { OptionsExposureResponse } from '@/types'

const props = defineProps<{ data: OptionsExposureResponse }>()

function fmt(v: number | null | undefined) {
  if (v == null) return '—'
  return v.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtRatio(v: number | null | undefined) {
  if (v == null) return '—'
  return v.toFixed(2)
}

function fmtPct(v: number | null | undefined) {
  if (v == null) return '—'
  return (v * 100).toFixed(2) + '%'
}

function fmtGex(v: number) {
  const abs = Math.abs(v)
  const sign = v < 0 ? '-' : '+'
  if (abs >= 1e9) return `${sign}${(abs / 1e9).toFixed(2)}B`
  if (abs >= 1e6) return `${sign}${(abs / 1e6).toFixed(2)}M`
  return `${sign}${abs.toFixed(0)}`
}

const gammaFlipClass = computed(() => {
  const flip = props.data.key_levels.gamma_flip
  const spot = props.data.spot
  if (flip == null || spot == null) return ''
  return spot > flip ? 'bullish' : 'bearish'
})

const pcrClass = computed(() => {
  const pcr = props.data.pcr_oi
  if (pcr == null) return ''
  return pcr > 1.2 ? 'bearish' : pcr < 0.8 ? 'bullish' : ''
})

const totalGexClass = computed(() => {
  return props.data.total_gex >= 0 ? 'bullish' : 'bearish'
})
</script>

<style scoped>
.key-metrics {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 12px;
  padding: 8px 10px;
  border-bottom: 1px solid #222;
}
.metric {
  display: flex;
  flex-direction: column;
  min-width: 72px;
}
.metric-label {
  font-size: 10px;
  color: #888;
  letter-spacing: 0.03em;
  text-transform: uppercase;
}
.metric-value {
  font-size: 12px;
  font-family: 'JetBrains Mono', monospace;
  color: #ccc;
  margin-top: 2px;
}
.bullish { color: #26a69a; }
.bearish { color: #ef5350; }
.est-badge .metric-label { color: #666; }
.metric-value.est { color: #888; font-style: italic; }
</style>
