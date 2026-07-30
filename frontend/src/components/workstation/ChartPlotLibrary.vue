<template>
  <section class="chart-plots" aria-label="Chart plot library">
    <button type="button" aria-label="Chart plot library" @click="open = !open">Plots {{ chartStore.indicators.length }}</button>
    <div v-if="open" class="chart-plots__menu">
      <header><b>Chart plots</b><button type="button" aria-label="Close chart plot library" @click="open = false">×</button></header>
      <select aria-label="Add indicator plot" :value="''" @change="add(($event.target as HTMLSelectElement).value)">
        <option value="" disabled>Add indicator plot…</option>
        <option v-for="item in catalog" :key="item.type" :value="item.type">{{ item.pickerLabel }}</option>
      </select>
      <p>Price history <small>active</small></p>
      <p v-if="!chartStore.indicators.length">No indicator plots.</p>
      <ol v-else><li v-for="(indicator, index) in chartStore.indicators" :key="`${indicator.type}:${index}`" :class="{ muted: indicator.hidden }">
        <input :value="indicator.style.color" :aria-label="`${label(indicator)} color`" type="color" @input="style(index, 'color', ($event.target as HTMLInputElement).value)" /><span>{{ label(indicator) }}</span>
        <input :value="indicator.style.lineWidth" :aria-label="`${label(indicator)} line width`" type="number" min="0.25" max="5" step="0.25" @change="style(index, 'lineWidth', Number(($event.target as HTMLInputElement).value))" />
        <button type="button" :aria-label="`${indicator.hidden ? 'Show' : 'Hide'} ${label(indicator)}`" @click="toggle(index)">{{ indicator.hidden ? '○' : '●' }}</button><button type="button" :aria-label="`Move ${label(indicator)} up`" :disabled="index === 0" @click="move(index, -1)">↑</button><button type="button" :aria-label="`Move ${label(indicator)} down`" :disabled="index === chartStore.indicators.length - 1" @click="move(index, 1)">↓</button><button type="button" :aria-label="`Duplicate ${label(indicator)}`" @click="duplicate(index)">⧉</button><button type="button" :aria-label="`Delete ${label(indicator)}`" @click="chartStore.removeIndicator(index)">×</button>
      </li></ol>
    </div>
  </section>
</template>
<script setup lang="ts">
import { inject, ref } from 'vue'
import { usePanelStore } from '@/stores/chart'
import { cloneDefaultIndicator, INDICATOR_CATALOG, indicatorDisplayName } from '@/lib/indicators/catalog'
import type { IndicatorConfig, IndicatorType } from '@/types'
const chartStore = usePanelStore(inject<string>('panelId', 'chart')); const open = ref(false); const catalog = INDICATOR_CATALOG
function label(indicator: IndicatorConfig) { return indicatorDisplayName(indicator) }
function add(value: string) { if (INDICATOR_CATALOG.some(item => item.type === value)) chartStore.addIndicator(cloneDefaultIndicator(value as IndicatorType)) }
function style(index: number, key: 'color' | 'lineWidth', value: string | number) { const item = chartStore.indicators[index]; if (item && (key !== 'lineWidth' || (Number.isFinite(value) && Number(value) > 0))) chartStore.updateIndicator(index, { ...item, style: { ...item.style, [key]: value } }) }
function toggle(index: number) { const item = chartStore.indicators[index]; if (item) chartStore.updateIndicator(index, { ...item, hidden: !item.hidden }) }
function duplicate(index: number) { const item = chartStore.indicators[index]; if (item) chartStore.indicators.splice(index + 1, 0, { ...item, params: { ...item.params }, style: { ...item.style }, lockedTimeframes: item.lockedTimeframes ? [...item.lockedTimeframes] : item.lockedTimeframes }) }
function move(index: number, delta: number) { const target = index + delta; if (target < 0 || target >= chartStore.indicators.length) return; const next = [...chartStore.indicators]; const [item] = next.splice(index, 1); next.splice(target, 0, item); chartStore.reorderIndicators(next) }
</script>
<style scoped>
.chart-plots{position:relative}.chart-plots button,.chart-plots select,.chart-plots input{border:1px solid #3a4954;background:#172027;color:#dce6ed;font:10px "Segoe UI",Arial,sans-serif}.chart-plots>button{height:18px;padding:0 5px;cursor:pointer}.chart-plots__menu{position:absolute;z-index:121;right:0;top:22px;display:grid;gap:4px;width:300px;max-height:340px;padding:6px;border:1px solid #4a5b67;background:#131a20;box-shadow:0 6px 16px #000b}.chart-plots__menu header{display:flex;align-items:center}.chart-plots__menu header button{margin-left:auto}.chart-plots select{min-width:0;padding:2px}.chart-plots p{margin:0;padding:3px 4px;color:#b4c3cd;border-top:1px solid #2d3942}.chart-plots p small{color:#8196a4}.chart-plots ol{display:grid;gap:2px;max-height:204px;margin:0;padding:0;overflow:auto;list-style:none}.chart-plots li{display:grid;grid-template-columns:18px minmax(0,1fr) 36px repeat(5,18px);align-items:center;gap:3px;padding:2px;border-top:1px solid #27323a}.chart-plots li span{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.chart-plots li input[type=color]{width:17px;height:16px;padding:0}.chart-plots li input[type=number]{min-width:0;padding:1px}.chart-plots li button{height:17px;padding:0;cursor:pointer}.chart-plots li button:disabled{opacity:.35}.muted{opacity:.5}
</style>
