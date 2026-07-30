<template>
  <section class="rotation-tool">
    <header><strong>Relative Rotation · SPY</strong><small>Trend: ratio return over 20 bars · Momentum: change in that trend</small></header>
    <p v-if="loading" class="rotation-tool__state">Calculating aligned local ratios…</p>
    <p v-else-if="error" class="rotation-tool__state rotation-tool__state--error">{{ error }}</p>
    <p v-else-if="!rows.length" class="rotation-tool__state">No sector rotation rows are available.</p>
    <div v-else class="rotation-tool__table"><div class="rotation-tool__head"><span>Sector</span><span>State</span><span>Trend</span><span>Momentum</span><span>Coverage</span><span>Tail</span></div><button v-for="row in rows" :key="row.instrument_id" type="button" class="rotation-tool__row" @click="emit('select', row.symbol)"><strong>{{ row.symbol }}</strong><span :class="`rotation-tool__state-${row.state}`">{{ row.state ?? 'Unavailable' }}</span><span>{{ percent(row.trend) }}</span><span>{{ percent(row.momentum) }}</span><span>{{ percent(row.coverage) }}</span><span>{{ row.tail.length }}</span></button></div>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '@/lib/api'
interface Row { instrument_id: number; symbol: string; state: string | null; trend: number | null; momentum: number | null; coverage: number; tail: unknown[] }
const emit = defineEmits<{ select: [symbol: string] }>()
const rows = ref<Row[]>([]), loading = ref(true), error = ref('')
function percent(value: number | null) { return value == null ? '—' : `${(value * 100).toFixed(2)}%` }
onMounted(async () => { try { const payload = await api.get<{ rows: Row[] }>('/analysis/groups/sp500-sectors/relative-rotation', { benchmark: 'SPY', lookback: 20, tail_length: 10 }); rows.value = payload.rows } catch (cause: any) { error.value = cause?.message ?? 'Relative rotation is unavailable.' } finally { loading.value = false } })
</script>

<style scoped>.rotation-tool{display:grid;height:100%;min-height:0;grid-template-rows:auto minmax(0,1fr);background:#11161b;color:#cad4db;font:10px "Segoe UI",Arial,sans-serif}.rotation-tool header{display:grid;gap:2px;padding:7px;border-bottom:1px solid #2d3841}.rotation-tool header small{color:#82929d}.rotation-tool__state{display:grid;place-items:center;color:#8596a1}.rotation-tool__state--error{color:#e28c8c}.rotation-tool__table{overflow:auto}.rotation-tool__head,.rotation-tool__row{display:grid;grid-template-columns:54px 78px 1fr 1fr 64px 38px;align-items:center;gap:5px;padding:5px 7px}.rotation-tool__head{position:sticky;top:0;background:#20282f;color:#9baab5;font-weight:600;text-transform:uppercase}.rotation-tool__row{width:100%;border:0;border-bottom:1px solid #20282f;background:transparent;color:inherit;text-align:left;cursor:pointer}.rotation-tool__row:hover{background:#1d4057}.rotation-tool__state-leading{color:#61c58c}.rotation-tool__state-weakening{color:#e7bc68}.rotation-tool__state-improving{color:#6dbbe6}.rotation-tool__state-lagging{color:#df8181}</style>
