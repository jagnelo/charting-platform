<template>
  <ToolWindow :title="tool.title || tool.tool_type" :symbol="activeSymbol" :link-group="tool.link_group" :active="tool.instance_key === activeWindowKey" @float="emit('float', tool.instance_key)" @update:link-group="emit('updateLinkGroup', tool.instance_key, $event)">
    <VirtualWatchlistTool
      v-if="tool.instance_key === 'benchmark-list'"
      label="Major US benchmarks"
      :rows="benchmarkRows"
      :selected="activeSymbol"
      :visible-column-keys="configuredColumnKeys"
      @select="emit('select', $event.symbol)"
      @update:visible-column-keys="emit('columns', tool.instance_key, $event)"
    />
    <VirtualWatchlistTool
      v-else-if="tool.instance_key === 'sector-list'"
      label="Relative to SPY"
      :rows="sectorRows"
      :selected="activeSymbol"
      :columns="sectorColumns"
      :visible-column-keys="configuredColumnKeys"
      @select="emit('select', $event.symbol)"
      @update:visible-column-keys="emit('columns', tool.instance_key, $event)"
    />
    <div v-else-if="tool.tool_type === 'chart' && tool.instance_key === 'primary-chart'" class="chart-tool">
      <div v-if="chartStore.isLoading" class="tool-state">Loading {{ activeSymbol }}…</div>
      <div v-else-if="chartStore.error" class="tool-state tool-state--error">{{ chartStore.error }}</div>
      <UPlotChart v-else-if="chartStore.symbol" />
      <div v-else class="tool-state">Select a canonical instrument.</div>
    </div>
    <div v-else-if="tool.instance_key === 'industry-list' && industries.length" class="industry-list">
      <button
        v-for="item in industries"
        :key="item.industry"
        type="button"
        :class="{ 'industry-list__row--active': item.industry === selectedIndustry }"
        class="industry-list__row"
        @click="emit('selectIndustry', item.industry)"
      >
        <strong>{{ item.industry }}</strong><span>{{ item.resolved_count }}/{{ item.constituent_count }}</span>
      </button>
      <small>{{ selectedETF }} holdings · point-in-time classification</small>
    </div>
    <div v-else-if="tool.instance_key === 'industry-list'" class="tool-state">
      No mapped ETF proxy for {{ selectedETF || activeSymbol }}. Curated industry mappings require holdings and classification evidence.
    </div>
    <VirtualWatchlistTool
      v-else-if="tool.instance_key === 'constituent-list'"
      :label="constituentLabel"
      :rows="constituentRows"
      :selected="activeSymbol"
      :columns="constituentColumns"
      :visible-column-keys="configuredColumnKeys"
      @select="emit('select', $event.symbol)"
      @update:visible-column-keys="emit('columns', tool.instance_key, $event)"
    />
    <div v-else-if="tool.instance_key === 'ratio-chart'" class="analysis">
      <RatioUPlot :symbol="activeSymbol" :benchmark="ratioBenchmark" />
    </div>
    <div v-else-if="tool.instance_key === 'breadth-summary'" class="metrics">
      <span>Above 20 MA</span><b>{{ breadthMetric('ma20') }}</b>
      <span>Above 50 MA</span><b>{{ breadthMetric('ma50') }}</b>
      <span>Above 200 MA</span><b>{{ breadthMetric('ma200') }}</b>
      <span>Coverage</span><b>{{ breadthCoverage }}</b>
    </div>
    <div v-else-if="tool.instance_key === 'technical-summary'" class="metrics">
      <span>RSI(14)</span><b>{{ formatNumber(technical?.rsi14) }}</b>
      <span>20 / 50 / 200 MA</span><b>{{ technicalMAs }}</b>
      <span>52-week position</span><b>{{ formatPercent(technical?.position_52w) }}</b>
      <span>Volume ratio (50)</span><b>{{ formatRatio(technical?.volume_ratio_50) }}</b>
    </div>
    <div v-else-if="tool.instance_key === 'coverage-summary'" class="metrics">
      <span>Universe coverage</span><b>{{ breadthCoverage }}</b>
      <span>Membership</span><b>ETF-proxy labelled</b>
    </div>
    <InstrumentNoteTool v-else-if="tool.instance_key === 'notes'" :instrument-id="chartStore.instrument?.id" :symbol="activeSymbol" />
    <InstrumentAlertsTool v-else-if="tool.instance_key === 'alerts'" :instrument-id="chartStore.instrument?.id" :symbol="activeSymbol" />
    <EasyScanTool v-else-if="tool.instance_key === 'easy-scan'" />
    <div v-else class="tool-state">{{ tool.title || tool.tool_type }}</div>
  </ToolWindow>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import UPlotChart from '@/components/chart/UPlotChart.vue'
import { useChartStore } from '@/stores/chart'
import { useWorkspaceStore, type LinkGroup, type WorkspaceWindowState } from '@/stores/workspace'
import ToolWindow from './ToolWindow.vue'
import VirtualWatchlistTool, { type WatchlistColumn } from './VirtualWatchlistTool.vue'
import RatioUPlot from './RatioUPlot.vue'
import InstrumentNoteTool from './InstrumentNoteTool.vue'
import InstrumentAlertsTool from './InstrumentAlertsTool.vue'
import EasyScanTool from './EasyScanTool.vue'

const props = defineProps<{
  tool: WorkspaceWindowState
  activeWindowKey?: string | null
}>()
const emit = defineEmits<{ select: [symbol: string]; selectIndustry: [industry: string]; columns: [windowKey: string, keys: string[]]; float: [windowKey: string]; updateLinkGroup: [windowKey: string, group: LinkGroup] }>()
const chartStore = useChartStore()
const workspaceStore = useWorkspaceStore()
const activeSymbol = computed(() => workspaceStore.linkedSymbol || 'SPY')
const benchmarks = computed(() => workspaceStore.marketGroups['us-benchmarks']?.members.map(member => member.instrument.symbol) ?? [])
const sectors = computed(() => workspaceStore.marketGroups['sp500-sectors']?.members.map(member => member.instrument.symbol) ?? [])
const sectorPerformance = computed(() => Object.fromEntries(
  (workspaceStore.groupSnapshots['sp500-sectors']?.rows ?? []).map(row => [row.symbol, row.performance['1M']?.value ?? null]),
))
const breadth = computed(() => workspaceStore.breadth['sp500-sectors'])
const technical = computed(() => workspaceStore.technicals[activeSymbol.value])
const selectedETF = computed(() => workspaceStore.constituentETF ?? '')
const ratioBenchmark = computed(() => selectedETF.value && selectedETF.value !== activeSymbol.value ? selectedETF.value : 'SPY')
const holdings = computed(() => selectedETF.value ? workspaceStore.etfHoldings[selectedETF.value] : null)
const industries = computed(() => selectedETF.value ? workspaceStore.etfIndustries[selectedETF.value]?.industries ?? [] : [])
const selectedIndustry = computed(() => workspaceStore.selectedIndustry)
const constituents = computed(() => {
  if (selectedETF.value && selectedIndustry.value) {
    return workspaceStore.industryConstituents[`${selectedETF.value}:${selectedIndustry.value}`]?.constituents.map(row => row.symbol) ?? []
  }
  return holdings.value?.holdings.filter(row => row.is_resolved && Boolean(row.constituent_symbol)).map(row => row.constituent_symbol as string) ?? []
})
const constituentLabel = computed(() => {
  if (!holdings.value) return 'No point-in-time ETF holdings snapshot'
  return `${holdings.value.snapshot.etf_symbol} holdings · ${holdings.value.snapshot.composition_date}`
})
const benchmarkRows = computed(() => (workspaceStore.marketGroups['us-benchmarks']?.members ?? []).map(member => ({
  instrumentId: member.instrument.id, symbol: member.instrument.symbol, name: member.instrument.name,
})))
const sectorRows = computed(() => (workspaceStore.marketGroups['sp500-sectors']?.members ?? []).map(member => ({
  instrumentId: member.instrument.id,
  symbol: member.instrument.symbol,
  name: member.instrument.name,
  values: { relative_1m: workspaceStore.groupSnapshots['sp500-sectors']?.rows.find(row => row.instrument_id === member.instrument.id)?.performance['1M']?.value ?? null },
})))
const constituentRows = computed(() => {
  const source = selectedETF.value && selectedIndustry.value
    ? workspaceStore.industryConstituents[`${selectedETF.value}:${selectedIndustry.value}`]?.constituents ?? []
    : holdings.value?.holdings.filter(row => row.is_resolved && row.constituent_instrument_id && row.constituent_symbol).map(row => ({
        id: row.constituent_instrument_id as number, symbol: row.constituent_symbol as string, name: row.constituent_name ?? row.reported_name ?? row.constituent_symbol as string,
        weight: row.weight,
      })) ?? []
  return source.map(row => ({ instrumentId: row.id, symbol: row.symbol, name: row.name, values: { weight: 'weight' in row ? row.weight ?? null : null } }))
})
const sectorColumns: WatchlistColumn[] = [
  { key: 'symbol', label: 'Symbol', width: '54px' }, { key: 'name', label: 'Sector', width: 'minmax(90px, 1fr)' }, { key: 'relative_1m', label: '1M / SPY', width: '70px' },
]
const constituentColumns: WatchlistColumn[] = [
  { key: 'symbol', label: 'Symbol', width: '60px' }, { key: 'name', label: 'Constituent', width: 'minmax(100px, 1fr)' }, { key: 'weight', label: 'Weight', width: '62px' },
]
const configuredColumnKeys = computed(() => {
  const keys = props.tool.configuration.column_keys
  return Array.isArray(keys) && keys.every(key => typeof key === 'string') ? keys as string[] : []
})
const descriptions: Record<string, string> = {
  SPY: 'S&P 500 proxy', RSP: 'S&P 500 equal weight', QQQ: 'Nasdaq-100 proxy', DIA: 'Dow Jones proxy', IWM: 'Russell 2000 proxy',
  XLK: 'Technology', XLY: 'Consumer Discretionary', XLC: 'Communication Services', XLF: 'Financials', XLV: 'Health Care', XLI: 'Industrials', XLP: 'Consumer Staples', XLE: 'Energy', XLU: 'Utilities', XLRE: 'Real Estate', XLB: 'Materials',
  NVDA: 'NVIDIA', MSFT: 'Microsoft', AAPL: 'Apple', AVGO: 'Broadcom', CRM: 'Salesforce', ORCL: 'Oracle', AMD: 'AMD', ADBE: 'Adobe',
}
const breadthCoverage = computed(() => breadth.value ? `${(breadth.value.coverage * 100).toFixed(0)}% · ${breadth.value.evaluated_count} symbols` : 'Unavailable')
const technicalMAs = computed(() => [technical.value?.sma20, technical.value?.sma50, technical.value?.sma200]
  .map(value => formatNumber(value)).join(' / '))
function breadthMetric(key: string) {
  const value = breadth.value?.above_ma[key]
  return value == null ? 'Unavailable' : `${(value * 100).toFixed(1)}%`
}
function formatNumber(value: number | null | undefined) { return value == null ? 'Unavailable' : value.toFixed(2) }
function formatPercent(value: number | null | undefined) { return value == null ? 'Unavailable' : `${(value * 100).toFixed(1)}%` }
function formatRatio(value: number | null | undefined) { return value == null ? 'Unavailable' : `${value.toFixed(2)}×` }
</script>

<style scoped>
.chart-tool { height: 100%; min-height: 0; background: #101419; }
.tool-state { display: grid; place-items: center; height: 100%; padding: 12px; color: #98a7b2; font: 11px "Segoe UI", Arial, sans-serif; text-align: center; }
.tool-state--error { color: #ec8f8f; }
.analysis { height: 100%; min-height: 0; }
.metrics { display: grid; grid-template-columns: 1fr auto; gap: 5px 10px; padding: 9px; color: #99a8b1; font: 10px "Segoe UI", Arial, sans-serif; }
.metrics b { color: #d2dce3; font-weight: 500; text-align: right; }
.industry-list { height: 100%; overflow: auto; background: #11161b; font: 11px "Segoe UI", Arial, sans-serif; }
.industry-list__row { display: flex; width: 100%; justify-content: space-between; gap: 8px; padding: 7px; border: 0; border-bottom: 1px solid #20282f; background: transparent; color: #c7d0d8; text-align: left; cursor: pointer; }
.industry-list__row:hover, .industry-list__row--active { background: #1d4057; }
.industry-list__row strong { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.industry-list__row span, .industry-list small { color: #7d9db0; }
.industry-list small { display: block; padding: 7px; line-height: 1.3; }
</style>
