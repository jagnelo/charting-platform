<template>
  <div v-if="hasData" class="excursion-bars">
    <div class="excursion-bars__legend" aria-hidden="true">
      <span><i class="excursion-bars__swatch excursion-bars__swatch--mae" /> MAE</span>
      <span><i class="excursion-bars__swatch excursion-bars__swatch--mfe" /> MFE</span>
    </div>
    <div ref="hostRef" class="excursion-bars__plot" role="img" aria-label="Trade maximum adverse and favorable excursion" />
    <p class="excursion-bars__summary">
      {{ sampleSize }} trades with intratrade bars · average MAE {{ formatPercent(averageMae) }} · average MFE {{ formatPercent(averageMfe) }}
    </p>
  </div>
  <div v-else class="excursion-bars__empty">{{ emptyLabel }}</div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import uPlot from 'uplot'
import 'uplot/dist/uPlot.min.css'

export interface ExcursionRow {
  instrument_symbol?: string | null
  entry_at?: string | null
  exit_at?: string | null
  mae_pct?: number | null
  mfe_pct?: number | null
  bars_available?: number | null
}

const props = withDefaults(defineProps<{ rows: ExcursionRow[]; emptyLabel?: string }>(), {
  emptyLabel: 'No intratrade excursion data yet.',
})
const hostRef = ref<HTMLDivElement | null>(null)
const chart = ref<uPlot | null>(null)
let resizeObserver: ResizeObserver | null = null
const normalized = computed(() => props.rows.filter(row => (
  Number(row.bars_available ?? 0) > 0
  && Number.isFinite(Number(row.mae_pct))
  && Number.isFinite(Number(row.mfe_pct))
  && Number.isFinite(new Date(row.exit_at || row.entry_at || '').getTime())
)))
const hasData = computed(() => normalized.value.length > 0)
const sampleSize = computed(() => normalized.value.length)
const averageMae = computed(() => average(normalized.value.map(row => Number(row.mae_pct))))
const averageMfe = computed(() => average(normalized.value.map(row => Number(row.mfe_pct))))
function average(values: number[]) { return values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : null }
function formatPercent(value: number | null) { return value == null || !Number.isFinite(value) ? '—' : `${value >= 0 ? '+' : ''}${value.toFixed(2)}%` }
function excursionPlugin(): uPlot.Plugin {
  return { hooks: { draw: [instance => {
    const ctx = instance.ctx
    const x = (value: number) => instance.valToPos(value, 'x')
    const y = (value: number) => instance.valToPos(value, 'y')
    const width = Math.max(3, (instance.bbox.width / Math.max(normalized.value.length, 1)) * 0.28)
    normalized.value.forEach(row => {
      const center = x(new Date(row.exit_at || row.entry_at || '').getTime() / 1000)
      const mae = y(Number(row.mae_pct)); const mfe = y(Number(row.mfe_pct)); const zero = y(0)
      ctx.fillStyle = '#e77b85'; ctx.fillRect(center - width - 1, Math.min(zero, mae), width, Math.max(1, Math.abs(zero - mae)))
      ctx.fillStyle = '#6ddb95'; ctx.fillRect(center + 1, Math.min(zero, mfe), width, Math.max(1, Math.abs(zero - mfe)))
    })
  }] } }
}
function destroy() { chart.value?.destroy(); chart.value = null; resizeObserver?.disconnect(); resizeObserver = null }
async function render() {
  await nextTick(); destroy(); if (!hostRef.value || !hasData.value) return
  const timestamps = normalized.value.map(row => new Date(row.exit_at || row.entry_at || '').getTime() / 1000)
  chart.value = new uPlot({ width: Math.max(hostRef.value.clientWidth || 320, 240), height: 150, plugins: [excursionPlugin()], scales: { x: { time: true }, y: { auto: true } }, axes: [{}, { values: (_u, values) => values.map(value => `${Number(value).toFixed(1)}%`) }], series: [{}, { label: 'MAE', stroke: 'transparent' }, { label: 'MFE', stroke: 'transparent' }] }, [timestamps, normalized.value.map(row => Number(row.mae_pct)), normalized.value.map(row => Number(row.mfe_pct))], hostRef.value)
  if (typeof ResizeObserver !== 'undefined') {
    resizeObserver = new ResizeObserver(() => {
      if (chart.value && hostRef.value) {
        chart.value.setSize({ width: Math.max(hostRef.value.clientWidth, 240), height: 150 })
      }
    })
    resizeObserver.observe(hostRef.value)
  }
}
onMounted(render); watch(() => props.rows, render, { deep: true }); onBeforeUnmount(destroy)
</script>

<style scoped>
.excursion-bars { display: grid; gap: 7px; }
.excursion-bars__legend { display: flex; gap: 14px; color: #aeb7c2; font-size: 11px; }
.excursion-bars__legend span { display: inline-flex; align-items: center; gap: 5px; }
.excursion-bars__swatch { width: 9px; height: 9px; display: inline-block; border-radius: 2px; }
.excursion-bars__swatch--mae { background: #e77b85; }
.excursion-bars__swatch--mfe { background: #6ddb95; }
.excursion-bars__plot { min-height: 150px; width: 100%; }
.excursion-bars__summary { margin: 0; color: #7e8792; font-size: 11px; }
.excursion-bars__empty { color: #7e8792; font-size: 12px; padding: 12px 0; }
</style>
