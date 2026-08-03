<template>
  <section class="chart-plots" aria-label="Chart plot library">
    <button type="button" aria-label="Chart plot library" @click="open = !open">Plots {{ chartStore.indicators.length }}</button>
    <div v-if="open" class="chart-plots__menu">
      <header><b>Chart plots</b><button type="button" aria-label="Close chart plot library" @click="open = false">×</button></header>
      <select aria-label="Add indicator plot" :value="''" @change="add(($event.target as HTMLSelectElement).value)">
        <option value="" disabled>Add indicator plot…</option>
        <option v-for="item in catalog" :key="item.type" :value="item.type">{{ item.pickerLabel }}</option>
      </select>
      <label class="chart-plots__target">Copy target
        <select v-model="selectedCopyTarget" aria-label="Copy plot target">
          <option value="linked">Linked charts ({{ linkedChartCount }})</option>
          <option v-for="target in chartTargets" :key="target.instance_key" :value="target.instance_key">{{ target.title || target.instance_key }} · {{ target.tool_type }}{{ target.link_group === linkGroup ? ' · linked' : '' }}</option>
        </select>
      </label>
      <label class="chart-plots__target">Promote plot
        <select v-model="selectedPromotionIndex" aria-label="Promotion plot">
          <option value="">Select a plot…</option>
          <option v-for="(indicator, index) in chartStore.indicators" :key="`promotion-${index}`" :value="String(index)">{{ label(indicator) }}</option>
        </select>
      </label>
      <div v-if="selectedPromotionIndex !== ''" class="chart-plots__promotion">
        <select v-model="promotionTarget" aria-label="Plot promotion target"><option value="condition">Condition</option><option value="scan">EasyScan</option><option value="filter">Watchlist filter</option><option value="alert">Indicator alert</option></select>
        <select v-if="promotionTarget === 'filter'" v-model="selectedFilterTarget" aria-label="Plot promotion watchlist"><option value="" disabled>Select watchlist…</option><option v-for="target in watchlistTargets" :key="target.instance_key" :value="target.instance_key">{{ target.title || target.instance_key }}</option></select>
        <select v-model="promotionOperator" aria-label="Plot promotion operator"><option value="gt">&gt;</option><option value="gte">≥</option><option value="lt">&lt;</option><option value="lte">≤</option></select>
        <input v-model.number="promotionThreshold" aria-label="Plot promotion threshold" type="number" step="any" />
        <input v-model.trim="promotionName" aria-label="Plot promotion name" placeholder="Name" />
        <button type="button" :disabled="promotionBusy || !promotionName || !Number.isFinite(promotionThreshold) || (promotionTarget === 'filter' && !selectedFilterTarget)" @click="promoteSelected">{{ promotionBusy ? 'Saving…' : 'Copy' }}</button>
      </div>
      <p v-if="promotionStatus" class="chart-plots__promotion-status" role="status">{{ promotionStatus }}</p>
      <p>Price history <small>active</small></p>
      <p v-if="!chartStore.indicators.length">No indicator plots.</p>
      <ol v-else><li v-for="(indicator, index) in chartStore.indicators" :key="`${indicator.type}:${index}`" :class="{ muted: indicator.hidden }">
        <input :value="indicator.style.color" :aria-label="`${label(indicator)} color`" type="color" @input="style(index, 'color', ($event.target as HTMLInputElement).value)" /><span>{{ label(indicator) }}</span>
        <input :value="indicator.style.lineWidth" :aria-label="`${label(indicator)} line width`" type="number" min="0.25" max="5" step="0.25" @change="style(index, 'lineWidth', Number(($event.target as HTMLInputElement).value))" />
        <button type="button" :aria-label="`${indicator.hidden ? 'Show' : 'Hide'} ${label(indicator)}`" @click="toggle(index)">{{ indicator.hidden ? '○' : '●' }}</button><button type="button" :aria-label="`Move ${label(indicator)} up`" :disabled="index === 0" @click="move(index, -1)">↑</button><button type="button" :aria-label="`Move ${label(indicator)} down`" :disabled="index === chartStore.indicators.length - 1" @click="move(index, 1)">↓</button><button type="button" :aria-label="`Duplicate ${label(indicator)}`" @click="duplicate(index)">⧉</button><button type="button" :aria-label="`Copy ${label(indicator)} to linked charts`" :disabled="!linkedTargets" @click="copy(index, 'linked')">⇉</button><button type="button" :aria-label="`Copy ${label(indicator)} to selected chart target`" :disabled="!copyTargetAvailable" @click="copy(index, selectedCopyTarget)">→</button><button type="button" :aria-label="`Promote ${label(indicator)}`" @click="selectPromotion(index)">⇧</button><button type="button" :aria-label="`Delete ${label(indicator)}`" @click="chartStore.removeIndicator(index)">×</button>
      </li></ol>
    </div>
  </section>
</template>
<script setup lang="ts">
import { computed, inject, ref } from 'vue'
import { usePanelStore } from '@/stores/chart'
import { useWorkspaceStore } from '@/stores/workspace'
import { cloneDefaultIndicator, INDICATOR_CATALOG, indicatorDisplayName } from '@/lib/indicators/catalog'
import { api } from '@/lib/api'
import type { IndicatorConfig, IndicatorType } from '@/types'
const props = defineProps<{ sourceWindowKey: string; linkGroup: string }>()
const chartStore = usePanelStore(inject<string>('panelId', 'chart')); const open = ref(false); const catalog = INDICATOR_CATALOG; const workspaceStore = useWorkspaceStore()
const selectedCopyTarget = ref('linked')
const chartTargets = computed(() => (workspaceStore.activeTab?.windows ?? []).filter(window => ['chart', 'watchlist'].includes(window.tool_type) && window.instance_key !== props.sourceWindowKey))
const watchlistTargets = computed(() => chartTargets.value.filter(window => window.tool_type === 'watchlist'))
const linkedChartCount = computed(() => chartTargets.value.filter(window => window.tool_type === 'chart' && window.link_group === props.linkGroup).length)
const linkedTargets = computed(() => linkedChartCount.value > 0)
const copyTargetAvailable = computed(() => selectedCopyTarget.value === 'linked' ? linkedTargets.value : chartTargets.value.some(window => window.instance_key === selectedCopyTarget.value))
const selectedPromotionIndex = ref('')
const promotionTarget = ref<'condition' | 'scan' | 'filter' | 'alert'>('condition')
const selectedFilterTarget = ref('')
const promotionOperator = ref('gt')
const promotionThreshold = ref(0)
const promotionName = ref('')
const promotionBusy = ref(false)
const promotionStatus = ref('')
function label(indicator: IndicatorConfig) { return indicatorDisplayName(indicator) }
function add(value: string) { if (INDICATOR_CATALOG.some(item => item.type === value)) chartStore.addIndicator(cloneDefaultIndicator(value as IndicatorType)) }
function style(index: number, key: 'color' | 'lineWidth', value: string | number) { const item = chartStore.indicators[index]; if (item && (key !== 'lineWidth' || (Number.isFinite(value) && Number(value) > 0))) chartStore.updateIndicator(index, { ...item, style: { ...item.style, [key]: value } }) }
function toggle(index: number) { const item = chartStore.indicators[index]; if (item) chartStore.updateIndicator(index, { ...item, hidden: !item.hidden }) }
function duplicate(index: number) { const item = chartStore.indicators[index]; if (item) chartStore.indicators.splice(index + 1, 0, { ...item, params: { ...item.params }, style: { ...item.style }, lockedTimeframes: item.lockedTimeframes ? [...item.lockedTimeframes] : item.lockedTimeframes }) }
function move(index: number, delta: number) { const target = index + delta; if (target < 0 || target >= chartStore.indicators.length) return; const next = [...chartStore.indicators]; const [item] = next.splice(index, 1); next.splice(target, 0, item); chartStore.reorderIndicators(next) }
function copy(index: number, target: string) {
  const item = chartStore.indicators[index]
  if (!item) return
  for (const window of workspaceStore.activeTab?.windows ?? []) {
    if (window.instance_key === props.sourceWindowKey) continue
    if (target === 'linked' ? window.tool_type !== 'chart' || window.link_group !== props.linkGroup : window.instance_key !== target) continue
    if (window.tool_type === 'watchlist') {
      const columns = Array.isArray(window.configuration.indicator_columns) ? window.configuration.indicator_columns : []
      const key = `indicator:${item.type}:${JSON.stringify(item.params)}`
      if (!columns.some((column: any) => column?.key === key)) window.configuration.indicator_columns = [...columns, { key, name: label(item), indicator: item.type, params: { ...item.params }, timeframe: chartStore.timeframe, output: 'value' }]
    } else {
      const plots = Array.isArray(window.configuration.indicators) ? window.configuration.indicators : []
      window.configuration.indicators = [...plots, { ...item, params: { ...item.params }, style: { ...item.style }, lockedTimeframes: item.lockedTimeframes ? [...item.lockedTimeframes] : item.lockedTimeframes }]
    }
  }
  workspaceStore.scheduleSnapshot()
}
function selectPromotion(index: number) {
  selectedPromotionIndex.value = String(index)
  promotionName.value = `${label(chartStore.indicators[index])} condition`
  selectedFilterTarget.value = watchlistTargets.value[0]?.instance_key ?? ''
  promotionStatus.value = ''
}
function promotionCondition(item: IndicatorConfig) {
  return { operator: 'AND', conditions: [{ type: 'indicator_threshold', indicator: item.type, params: { ...item.params }, output: 'value', op: promotionOperator.value, value: promotionThreshold.value }] }
}
function promotionKey(name: string) {
  return name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 72) || 'chart-plot-condition'
}
async function promoteSelected() {
  const item = chartStore.indicators[Number(selectedPromotionIndex.value)]
  if (!item || !promotionName.value || !Number.isFinite(promotionThreshold.value) || promotionBusy.value) return
  promotionBusy.value = true; promotionStatus.value = ''
  try {
    const key = promotionKey(promotionName.value)
    await api.put(`/workspaces/library/conditions/${encodeURIComponent(key)}`, {
      name: promotionName.value, condition: promotionCondition(item),
      dependency_metadata: { source: 'chart-plot-library', indicator_type: item.type, timeframe: chartStore.timeframe },
    })
    if (promotionTarget.value === 'scan' || promotionTarget.value === 'filter') {
      const scan = await api.post<{ id: number }>(`/screeners/from-condition/${encodeURIComponent(key)}`, { name: `${promotionName.value} Scan`, universe_type: 'all', timeframe: chartStore.timeframe })
      if (promotionTarget.value === 'filter') {
        const target = watchlistTargets.value.find(window => window.instance_key === selectedFilterTarget.value)
        if (!target) throw new Error('Select a watchlist window before applying a filter')
        target.configuration = { ...target.configuration, condition_screener_id: scan.id, condition_filter_mode: 'active' }
        workspaceStore.scheduleSnapshot()
        promotionStatus.value = `Copied ${label(item)} to ${target.title || target.instance_key} filter`
        return
      }
      promotionStatus.value = `Copied ${label(item)} to condition and EasyScan`
    } else if (promotionTarget.value === 'alert') {
      const instrumentId = chartStore.instrument?.id
      if (!instrumentId) throw new Error('Select a canonical instrument before creating an indicator alert')
      await api.post('/alerts/indicator', { instrument_id: instrumentId, timeframe: chartStore.timeframe, indicator_a_type: item.type, indicator_a_params: { ...item.params }, condition: promotionOperator.value, threshold_value: promotionThreshold.value, repeat: true, notes: promotionName.value })
      promotionStatus.value = `Copied ${label(item)} to condition and indicator alert`
    } else promotionStatus.value = `Copied ${label(item)} to reusable condition`
  } catch (cause: any) {
    promotionStatus.value = cause?.message ?? 'Unable to promote plot'
  } finally { promotionBusy.value = false }
}
</script>
<style scoped>
.chart-plots{position:relative}.chart-plots button,.chart-plots select,.chart-plots input{border:1px solid #3a4954;background:#172027;color:#dce6ed;font:10px "Segoe UI",Arial,sans-serif}.chart-plots>button{height:18px;padding:0 5px;cursor:pointer}.chart-plots__menu{position:absolute;z-index:121;right:0;top:22px;display:grid;gap:4px;width:300px;max-height:340px;padding:6px;border:1px solid #4a5b67;background:#131a20;box-shadow:0 6px 16px #000b}.chart-plots__menu header{display:flex;align-items:center}.chart-plots__menu header button{margin-left:auto}.chart-plots select{min-width:0;padding:2px}.chart-plots p{margin:0;padding:3px 4px;color:#b4c3cd;border-top:1px solid #2d3942}.chart-plots p small{color:#8196a4}.chart-plots ol{display:grid;gap:2px;max-height:204px;margin:0;padding:0;overflow:auto;list-style:none}.chart-plots li{display:grid;grid-template-columns:18px minmax(0,1fr) 36px repeat(6,18px);align-items:center;gap:3px;padding:2px;border-top:1px solid #27323a}.chart-plots li span{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.chart-plots li input[type=color]{width:17px;height:16px;padding:0}.chart-plots li input[type=number]{min-width:0;padding:1px}.chart-plots li button{height:17px;padding:0;cursor:pointer}.chart-plots li button:disabled{opacity:.35}.muted{opacity:.5}
.chart-plots__promotion{display:grid;grid-template-columns:72px 34px 62px minmax(60px,1fr) 36px;gap:3px}.chart-plots__promotion input,.chart-plots__promotion select{min-width:0}.chart-plots__promotion-status{margin:0;padding:2px 4px;color:#9ec6a0}
</style>
