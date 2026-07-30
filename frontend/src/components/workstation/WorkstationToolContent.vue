<template>
  <ToolWindow :title="tool.title || tool.tool_type" :symbol="activeSymbol" :link-group="tool.link_group" :active="tool.instance_key === activeWindowKey" @float="emit('float', tool.instance_key)" @maximize="emit('maximize', tool.instance_key)" @update:link-group="emit('updateLinkGroup', tool.instance_key, $event)">
    <VirtualWatchlistTool
      v-if="tool.instance_key === 'benchmark-list'"
      label="Major US benchmarks"
      :rows="benchmarkRows"
      :selected="activeSymbol"
      :visible-column-keys="configuredColumnKeys"
      :filter-text="configuredFilterText"
      :condition-screener-id="configuredConditionScreenerId"
      :condition-filter-mode="configuredConditionFilterMode"
      :pinned-boolean-keys="configuredPinnedBooleanKeys"
      :column-groups="configuredColumnGroups"
      :stacked-column-keys="configuredStackedColumnKeys"
      @select="emit('select', $event.symbol)"
      @update:visible-column-keys="emit('columns', tool.instance_key, $event)"
      @update:filter-text="emit('filter', tool.instance_key, $event)"
      @update:condition-screener-id="emit('conditionFilter', tool.instance_key, $event)"
      @update:condition-filter-mode="emit('conditionFilterMode', tool.instance_key, $event)"
      @update:pinned-boolean-keys="emit('pinnedBooleanKeys', tool.instance_key, $event)"
      @update:column-groups="emit('columnGroups', tool.instance_key, $event)"
      @update:stacked-column-keys="emit('stackedColumnKeys', tool.instance_key, $event)"
    />
    <VirtualWatchlistTool
      v-else-if="tool.instance_key === 'sector-list'"
      label="Relative to SPY"
      :rows="sectorRows"
      :selected="activeSymbol"
      :columns="sectorColumns"
      :visible-column-keys="configuredColumnKeys"
      :filter-text="configuredFilterText"
      :condition-screener-id="configuredConditionScreenerId"
      :condition-filter-mode="configuredConditionFilterMode"
      :pinned-boolean-keys="configuredPinnedBooleanKeys"
      :column-groups="configuredColumnGroups"
      :stacked-column-keys="configuredStackedColumnKeys"
      @select="emit('select', $event.symbol)"
      @update:visible-column-keys="emit('columns', tool.instance_key, $event)"
      @update:filter-text="emit('filter', tool.instance_key, $event)"
      @update:condition-screener-id="emit('conditionFilter', tool.instance_key, $event)"
      @update:condition-filter-mode="emit('conditionFilterMode', tool.instance_key, $event)"
      @update:pinned-boolean-keys="emit('pinnedBooleanKeys', tool.instance_key, $event)"
      @update:column-groups="emit('columnGroups', tool.instance_key, $event)"
      @update:stacked-column-keys="emit('stackedColumnKeys', tool.instance_key, $event)"
    />
    <div v-else-if="tool.tool_type === 'chart' && tool.instance_key !== 'ratio-chart'" class="chart-tool">
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
      <div v-if="selectedIndustry" class="industry-list__proxies">
        <small v-if="!industryProxyState">Checking curated ETF proxies…</small>
        <small v-else-if="!industryProxyState.proxies.length">No mapped ETF proxy · holdings/classification evidence required</small>
        <template v-else>
          <small>Verified ETF proxies · point-in-time holdings</small>
          <button
            v-for="proxy in industryProxyState.proxies"
            :key="proxy.symbol"
            type="button"
            class="industry-list__proxy"
            :class="{ 'industry-list__proxy--active': proxy.symbol === selectedIndustryProxy }"
            @click="emit('selectProxy', proxy.symbol)"
          >
            <strong>{{ proxy.symbol }}</strong><span>{{ proxy.classification_coverage * 100 }}% classified</span>
          </button>
        </template>
      </div>
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
      :filter-text="configuredFilterText"
      :condition-screener-id="configuredConditionScreenerId"
      :condition-filter-mode="configuredConditionFilterMode"
      :pinned-boolean-keys="configuredPinnedBooleanKeys"
      :column-groups="configuredColumnGroups"
      :stacked-column-keys="configuredStackedColumnKeys"
      @select="emit('select', $event.symbol)"
      @update:visible-column-keys="emit('columns', tool.instance_key, $event)"
      @update:filter-text="emit('filter', tool.instance_key, $event)"
      @update:condition-screener-id="emit('conditionFilter', tool.instance_key, $event)"
      @update:condition-filter-mode="emit('conditionFilterMode', tool.instance_key, $event)"
      @update:pinned-boolean-keys="emit('pinnedBooleanKeys', tool.instance_key, $event)"
      @update:column-groups="emit('columnGroups', tool.instance_key, $event)"
      @update:stacked-column-keys="emit('stackedColumnKeys', tool.instance_key, $event)"
    />
    <div v-else-if="tool.instance_key === 'ratio-chart'" class="analysis">
      <RatioUPlot :symbol="activeSymbol" :benchmarks="ratioBenchmarks" />
    </div>
    <div v-else-if="tool.instance_key === 'breadth-summary'" class="breadth-tool">
      <div class="metrics"><span>Above 20 MA</span><b>{{ breadthMetric('ma20') }}</b><span>Above 50 MA</span><b>{{ breadthMetric('ma50') }}</b><span>Above 200 MA</span><b>{{ breadthMetric('ma200') }}</b><span>Coverage</span><b>{{ breadthCoverage }}</b></div>
      <BreadthHistoryUPlot :history="breadthHistory" />
    </div>
    <RelativeRotationTool v-else-if="tool.instance_key === 'relative-rotation'" @select="emit('select', $event)" />
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
    <InstrumentNoteTool v-else-if="tool.tool_type === 'notes'" :instrument-id="chartStore.instrument?.id" :symbol="activeSymbol" />
    <InstrumentAlertsTool v-else-if="tool.tool_type === 'alerts'" :instrument-id="chartStore.instrument?.id" :symbol="activeSymbol" />
    <EasyScanTool v-else-if="tool.tool_type === 'scan'" />
    <MarketGaugeTool v-else-if="tool.tool_type === 'gauge'" />
    <StudyLabTool v-else-if="tool.tool_type === 'study_lab'" :active-symbol="activeSymbol" @occurrence="emit('occurrence', $event.symbol, $event.timestamp)" />
    <UnknownToolRecovery v-else :tool="tool" />
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
import MarketGaugeTool from './MarketGaugeTool.vue'
import StudyLabTool from './StudyLabTool.vue'
import UnknownToolRecovery from './UnknownToolRecovery.vue'
import BreadthHistoryUPlot from './BreadthHistoryUPlot.vue'
import RelativeRotationTool from './RelativeRotationTool.vue'

const props = defineProps<{
  tool: WorkspaceWindowState
  activeWindowKey?: string | null
}>()
const emit = defineEmits<{ select: [symbol: string]; occurrence: [symbol: string, timestamp: string]; selectIndustry: [industry: string]; selectProxy: [symbol: string]; columns: [windowKey: string, keys: string[]]; filter: [windowKey: string, value: string]; conditionFilter: [windowKey: string, screenerId: number | null]; conditionFilterMode: [windowKey: string, mode: 'active' | 'inactive' | 'off']; pinnedBooleanKeys: [windowKey: string, keys: string[]]; columnGroups: [windowKey: string, groups: Record<string, string>]; stackedColumnKeys: [windowKey: string, keys: string[]]; float: [windowKey: string]; maximize: [windowKey: string]; updateLinkGroup: [windowKey: string, group: LinkGroup] }>()
const chartStore = useChartStore()
const workspaceStore = useWorkspaceStore()
const activeSymbol = computed(() => workspaceStore.linkedSymbol || 'SPY')
const benchmarks = computed(() => workspaceStore.marketGroups['us-benchmarks']?.members.map(member => member.instrument.symbol) ?? [])
const sectors = computed(() => workspaceStore.marketGroups['sp500-sectors']?.members.map(member => member.instrument.symbol) ?? [])
const sectorPerformance = computed(() => Object.fromEntries(
  (workspaceStore.groupSnapshots['sp500-sectors']?.rows ?? []).map(row => [row.symbol, row.performance['1M']?.value ?? null]),
))
const breadth = computed(() => workspaceStore.breadth['sp500-sectors'])
const breadthHistory = computed(() => workspaceStore.breadthHistory['sp500-sectors'])
const technical = computed(() => workspaceStore.technicals[activeSymbol.value])
const selectedETF = computed(() => workspaceStore.constituentETF ?? '')
const ratioBenchmarks = computed(() => [...new Set([
  selectedETF.value && selectedETF.value !== activeSymbol.value ? selectedETF.value : 'SPY',
  'SPY',
])])
const holdings = computed(() => selectedETF.value ? workspaceStore.etfHoldings[selectedETF.value] : null)
const constituentSnapshot = computed(() => selectedETF.value ? workspaceStore.etfConstituentSnapshots[selectedETF.value] : null)
const industries = computed(() => selectedETF.value ? workspaceStore.etfIndustries[selectedETF.value]?.industries ?? [] : [])
const selectedIndustry = computed(() => workspaceStore.selectedIndustry)
const selectedIndustryProxy = computed(() => workspaceStore.selectedIndustryProxy)
const industryProxyState = computed(() => selectedETF.value && selectedIndustry.value
  ? workspaceStore.industryProxies[`${selectedETF.value}:${selectedIndustry.value}`]
  : null)
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
  values: (() => {
    const row = workspaceStore.groupSnapshots['sp500-sectors']?.rows.find(item => item.instrument_id === member.instrument.id)
    return {
      performance_1d: row?.performance['1D']?.value ?? null,
      performance_1w: row?.performance['1W']?.value ?? null,
      performance_1m: row?.performance['1M']?.value ?? null,
      performance_3m: row?.performance['3M']?.value ?? null,
      performance_6m: row?.performance['6M']?.value ?? null,
      performance_ytd: row?.performance.YTD?.value ?? null,
      performance_1y: row?.performance['1Y']?.value ?? null,
      relative_ratio: row?.relative_to_benchmark?.value == null ? null : row.relative_to_benchmark.value.toFixed(4),
      rsi14: row?.technical?.rsi14?.value ?? null,
      above_ma20: row?.technical?.above_ma20?.value ?? null,
      above_ma50: row?.technical?.above_ma50?.value ?? null,
      above_ma200: row?.technical?.above_ma200?.value ?? null,
      position_52w: row?.technical?.position_52w?.value ?? null,
      volume_ratio_50: row?.technical?.volume_ratio_50?.value == null ? null : row.technical.volume_ratio_50.value.toFixed(2),
    }
  })(),
})))
const constituentRows = computed(() => {
  const source = selectedETF.value && selectedIndustry.value
    ? workspaceStore.industryConstituents[`${selectedETF.value}:${selectedIndustry.value}`]?.constituents ?? []
    : holdings.value?.holdings.filter(row => row.is_resolved && row.constituent_instrument_id && row.constituent_symbol).map(row => ({
        id: row.constituent_instrument_id as number, symbol: row.constituent_symbol as string, name: row.constituent_name ?? row.reported_name ?? row.constituent_symbol as string,
        weight: row.weight,
      })) ?? []
  return source.map(row => {
    const analysis = constituentSnapshot.value?.rows.find(item => item.instrument_id === row.id)
    return {
      instrumentId: row.id, symbol: row.symbol, name: row.name,
      values: {
        weight: 'weight' in row ? row.weight ?? null : null,
        performance_1m: analysis?.performance['1M']?.value ?? null,
        relative_ratio: analysis?.relative_to_benchmark?.value == null ? null : analysis.relative_to_benchmark.value.toFixed(4),
        rsi14: analysis?.technical?.rsi14?.value ?? null,
        above_ma50: analysis?.technical?.above_ma50?.value ?? null,
        position_52w: analysis?.technical?.position_52w?.value ?? null,
      },
    }
  })
})
const sectorColumns: WatchlistColumn[] = [
  { key: 'symbol', label: 'Symbol', width: '54px' },
  { key: 'name', label: 'Sector', width: 'minmax(90px, 1fr)' },
  { key: 'performance_1d', label: '1D', width: '58px' },
  { key: 'performance_1w', label: '1W', width: '58px' },
  { key: 'performance_1m', label: '1M', width: '58px' },
  { key: 'performance_3m', label: '3M', width: '58px' },
  { key: 'performance_6m', label: '6M', width: '58px' },
  { key: 'performance_ytd', label: 'YTD', width: '58px' },
  { key: 'performance_1y', label: '1Y', width: '58px' },
  { key: 'relative_ratio', label: '/ SPY', width: '64px' },
  { key: 'rsi14', label: 'RSI', width: '54px', format: 'number' },
  { key: 'above_ma20', label: '>20', width: '54px', kind: 'boolean' },
  { key: 'above_ma50', label: '>50', width: '54px', kind: 'boolean' },
  { key: 'above_ma200', label: '>200', width: '58px', kind: 'boolean' },
  { key: 'position_52w', label: '52W Pos', width: '64px' },
  { key: 'volume_ratio_50', label: 'Vol x50', width: '62px' },
]
const constituentColumns: WatchlistColumn[] = [
  { key: 'symbol', label: 'Symbol', width: '60px' },
  { key: 'name', label: 'Constituent', width: 'minmax(100px, 1fr)' },
  { key: 'weight', label: 'Weight', width: '62px' },
  { key: 'performance_1m', label: '1M', width: '58px' },
  { key: 'relative_ratio', label: `/ ${selectedETF.value || 'ETF'}`, width: '64px', format: 'number' },
  { key: 'rsi14', label: 'RSI', width: '54px', format: 'number' },
  { key: 'above_ma50', label: '>50', width: '54px' },
  { key: 'position_52w', label: '52W Pos', width: '64px' },
]
const configuredColumnKeys = computed(() => {
  const keys = props.tool.configuration.column_keys
  return Array.isArray(keys) && keys.every(key => typeof key === 'string') ? keys as string[] : []
})
const configuredFilterText = computed(() => typeof props.tool.configuration.filter_text === 'string' ? props.tool.configuration.filter_text : '')
const configuredConditionScreenerId = computed(() => Number.isInteger(props.tool.configuration.condition_screener_id) ? props.tool.configuration.condition_screener_id as number : null)
const configuredConditionFilterMode = computed(() => ['active', 'inactive', 'off'].includes(String(props.tool.configuration.condition_filter_mode)) ? props.tool.configuration.condition_filter_mode as 'active' | 'inactive' | 'off' : 'off')
const configuredPinnedBooleanKeys = computed(() => Array.isArray(props.tool.configuration.pinned_boolean_keys) ? props.tool.configuration.pinned_boolean_keys.filter((key): key is string => typeof key === 'string') : [])
const configuredColumnGroups = computed(() => {
  const groups = props.tool.configuration.column_groups
  if (!groups || typeof groups !== 'object' || Array.isArray(groups)) return {}
  return Object.fromEntries(Object.entries(groups).filter(([key, value]) => typeof key === 'string' && typeof value === 'string'))
})
const configuredStackedColumnKeys = computed(() => Array.isArray(props.tool.configuration.stacked_column_keys)
  ? props.tool.configuration.stacked_column_keys.filter((key): key is string => typeof key === 'string') : [])
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
.breadth-tool { display:grid; grid-template-rows:auto minmax(0,1fr); height:100%; min-height:0; }.metrics { display: grid; grid-template-columns: 1fr auto; gap: 5px 10px; padding: 9px; color: #99a8b1; font: 10px "Segoe UI", Arial, sans-serif; }
.metrics b { color: #d2dce3; font-weight: 500; text-align: right; }
.industry-list { height: 100%; overflow: auto; background: #11161b; font: 11px "Segoe UI", Arial, sans-serif; }
.industry-list__row { display: flex; width: 100%; justify-content: space-between; gap: 8px; padding: 7px; border: 0; border-bottom: 1px solid #20282f; background: transparent; color: #c7d0d8; text-align: left; cursor: pointer; }
.industry-list__row:hover, .industry-list__row--active { background: #1d4057; }
.industry-list__proxies { display: grid; gap: 3px; padding: 6px 7px; border-bottom: 1px solid #20282f; color: #8998a3; }
.industry-list__proxy { display: flex; justify-content: space-between; gap: 8px; border: 1px solid #34434e; background: #162029; color: #c7d0d8; padding: 4px 5px; font: 10px "Segoe UI", Arial, sans-serif; text-align: left; cursor: pointer; }
.industry-list__proxy:hover, .industry-list__proxy--active { border-color: #5faed7; background: #1d4057; }
.industry-list__row strong { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.industry-list__row span, .industry-list small { color: #7d9db0; }
.industry-list small { display: block; padding: 7px; line-height: 1.3; }
</style>
