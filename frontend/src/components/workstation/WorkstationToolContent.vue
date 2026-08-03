<template>
  <ToolWindow :title="tool.title || tool.tool_type" :symbol="activeSymbol" :link-group="tool.link_group" :timeframe-link-group="timeframeLinkGroup" :timeframe="tool.tool_type === 'chart' ? activeTimeframe : ''" :active="tool.instance_key === activeWindowKey" @float="emit('float', tool.instance_key)" @maximize="emit('maximize', tool.instance_key)" @close="emit('close', tool.instance_key)" @update:link-group="emit('updateLinkGroup', tool.instance_key, $event)" @update:timeframe-link-group="setTimeframeLinkGroup" @update:timeframe="setTimeframe">
    <div v-if="tool.instance_key === 'benchmark-list'" class="benchmark-surface">
      <div class="benchmark-surface__identity" aria-label="S&P 500 benchmark identity">
        <strong>S&amp;P 500</strong>
        <span>Official series: {{ benchmarkIdentity.official_index_symbol }}</span>
        <span>Using tradable proxy: {{ benchmarkIdentity.default_tradable_proxy }}</span>
      </div>
      <VirtualWatchlistTool
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
      :python-columns="configuredPythonColumns"
      :python-condition="configuredPythonCondition"
      @select="selectSymbol($event.symbol, $event.instrumentId)"
      @compare="emit('compare', $event)"
      @row-action="handleRowAction"
      @update:visible-column-keys="emit('columns', tool.instance_key, $event)"
      @update:filter-text="emit('filter', tool.instance_key, $event)"
      @update:condition-screener-id="emit('conditionFilter', tool.instance_key, $event)"
      @update:condition-filter-mode="emit('conditionFilterMode', tool.instance_key, $event)"
      @update:pinned-boolean-keys="emit('pinnedBooleanKeys', tool.instance_key, $event)"
      @update:column-groups="emit('columnGroups', tool.instance_key, $event)"
      @update:stacked-column-keys="emit('stackedColumnKeys', tool.instance_key, $event)"
      @update:column-overrides="emit('configuration', tool.instance_key, { ...tool.configuration, column_overrides: $event })"
      @update:python-columns="emit('configuration', tool.instance_key, { ...tool.configuration, python_columns: $event })"
      @update:python-condition="emit('configuration', tool.instance_key, { ...tool.configuration, python_condition: $event })"
      />
    </div>
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
      :python-columns="configuredPythonColumns"
      :python-condition="configuredPythonCondition"
      @select="selectSymbol($event.symbol, $event.instrumentId)"
      @compare="emit('compare', $event)"
      @row-action="handleRowAction"
      @update:visible-column-keys="emit('columns', tool.instance_key, $event)"
      @update:filter-text="emit('filter', tool.instance_key, $event)"
      @update:condition-screener-id="emit('conditionFilter', tool.instance_key, $event)"
      @update:condition-filter-mode="emit('conditionFilterMode', tool.instance_key, $event)"
      @update:pinned-boolean-keys="emit('pinnedBooleanKeys', tool.instance_key, $event)"
      @update:column-groups="emit('columnGroups', tool.instance_key, $event)"
      @update:stacked-column-keys="emit('stackedColumnKeys', tool.instance_key, $event)"
      @update:column-overrides="emit('configuration', tool.instance_key, { ...tool.configuration, column_overrides: $event })"
      @update:python-columns="emit('configuration', tool.instance_key, { ...tool.configuration, python_columns: $event })"
      @update:python-condition="emit('configuration', tool.instance_key, { ...tool.configuration, python_condition: $event })"
    />
    <div v-else-if="tool.tool_type === 'watchlist' && tool.configuration.personal === true" class="personal-watchlist-tool">
      <div class="personal-watchlist-tool__controls">
        <label>WatchList
          <select :value="selectedPersonalWatchlistId == null ? '' : String(selectedPersonalWatchlistId)" aria-label="Personal watchlist" @change="selectPersonalWatchlist(($event.target as HTMLSelectElement).value)">
            <option value="">Select a personal watchlist</option>
            <option v-for="watchlist in personalWatchlists" :key="watchlist.id" :value="String(watchlist.id)">{{ watchlist.name }}{{ watchlist.is_locked ? ' · Locked' : '' }}</option>
          </select>
        </label>
        <input v-model="personalListNameDraft" aria-label="Personal watchlist name" placeholder="List name" @keydown.enter.prevent="selectedPersonalWatchlist ? renamePersonalWatchlist() : createPersonalWatchlist()" />
        <button type="button" :disabled="!personalListNameDraft.trim() || personalListBusy" @click="createPersonalWatchlist">New</button>
        <button type="button" :disabled="!selectedPersonalWatchlist || selectedPersonalWatchlist.is_locked || selectedPersonalWatchlist.is_managed || !personalListNameDraft.trim() || personalListBusy" @click="renamePersonalWatchlist">Rename</button>
        <button type="button" :disabled="!selectedPersonalWatchlist || personalListBusy" @click="copyPersonalWatchlist">Copy</button>
        <button type="button" :disabled="!selectedPersonalWatchlist || selectedPersonalWatchlist.is_locked || selectedPersonalWatchlist.is_managed || personalListBusy" @click="deletePersonalWatchlist">Delete</button>
        <input v-model="personalSymbolDraft" aria-label="Add symbol to personal watchlist" placeholder="Add symbol" :disabled="!selectedPersonalWatchlist || selectedPersonalWatchlist.is_locked" @keydown.enter.prevent="addPersonalSymbol" />
        <button type="button" :disabled="!personalSymbolDraft.trim() || !selectedPersonalWatchlist || selectedPersonalWatchlist.is_locked || personalWatchlistBusy" @click="addPersonalSymbol">{{ personalWatchlistBusy ? 'Adding…' : 'Add' }}</button>
        <span v-if="selectedPersonalWatchlist">{{ selectedPersonalWatchlist.items.length }} symbols · {{ selectedPersonalWatchlist.is_locked ? 'Locked' : 'Drag rows to reorder' }}</span>
        <span v-else-if="watchlistStore.loading">Loading watchlists…</span>
        <span v-else>No personal watchlists available.</span>
        <span v-if="personalWatchlistError" class="personal-watchlist-tool__error">{{ personalWatchlistError }}</span>
      </div>
      <VirtualWatchlistTool
        v-if="selectedPersonalWatchlist"
        :label="selectedPersonalWatchlist.name"
        :rows="personalWatchlistRows"
        :selected="activeSymbol"
        :columns="personalWatchlistColumns"
        :visible-column-keys="configuredColumnKeys"
        :filter-text="configuredFilterText"
        :condition-screener-id="configuredConditionScreenerId"
        :condition-filter-mode="configuredConditionFilterMode"
        :pinned-boolean-keys="configuredPinnedBooleanKeys"
        :column-groups="configuredColumnGroups"
        :stacked-column-keys="configuredStackedColumnKeys"
        :python-columns="configuredPythonColumns"
        :python-condition="configuredPythonCondition"
        :reorderable="!selectedPersonalWatchlist.is_locked && !selectedPersonalWatchlist.is_managed"
        :allow-remove="!selectedPersonalWatchlist.is_locked && !selectedPersonalWatchlist.is_managed"
        @select="selectSymbol($event.symbol, $event.instrumentId)"
        @reorder="emit('reorder', selectedPersonalWatchlist.id, $event)"
        @compare="emit('compare', $event)"
        @row-action="handlePersonalRowAction"
        @update:visible-column-keys="emit('columns', tool.instance_key, $event)"
        @update:filter-text="emit('filter', tool.instance_key, $event)"
        @update:condition-screener-id="emit('conditionFilter', tool.instance_key, $event)"
        @update:condition-filter-mode="emit('conditionFilterMode', tool.instance_key, $event)"
        @update:pinned-boolean-keys="emit('pinnedBooleanKeys', tool.instance_key, $event)"
        @update:column-groups="emit('columnGroups', tool.instance_key, $event)"
        @update:stacked-column-keys="emit('stackedColumnKeys', tool.instance_key, $event)"
        @update:column-overrides="emit('configuration', tool.instance_key, { ...tool.configuration, column_overrides: $event })"
        @update:python-columns="emit('configuration', tool.instance_key, { ...tool.configuration, python_columns: $event })"
        @update:python-condition="emit('configuration', tool.instance_key, { ...tool.configuration, python_condition: $event })"
      />
    </div>
    <VirtualWatchlistTool
      v-else-if="tool.tool_type === 'watchlist'"
      :label="tool.title || 'WatchList'"
      :rows="factoryWatchlistRows"
      :selected="tool.instance_key === 'industries' ? (selectedIndustry ?? '') : activeSymbol"
      :columns="factoryWatchlistColumns"
      :visible-column-keys="configuredColumnKeys"
      :filter-text="configuredFilterText"
      :condition-screener-id="configuredConditionScreenerId"
      :condition-filter-mode="configuredConditionFilterMode"
      :pinned-boolean-keys="configuredPinnedBooleanKeys"
      :column-groups="configuredColumnGroups"
      :stacked-column-keys="configuredStackedColumnKeys"
      :python-columns="configuredPythonColumns"
      :python-condition="configuredPythonCondition"
      @select="tool.instance_key === 'industries' ? emit('selectIndustry', $event.symbol) : selectSymbol($event.symbol, $event.instrumentId)"
      @compare="emit('compare', $event)"
      @row-action="handleRowAction"
      @update:visible-column-keys="emit('columns', tool.instance_key, $event)"
      @update:filter-text="emit('filter', tool.instance_key, $event)"
      @update:condition-screener-id="emit('conditionFilter', tool.instance_key, $event)"
      @update:condition-filter-mode="emit('conditionFilterMode', tool.instance_key, $event)"
      @update:pinned-boolean-keys="emit('pinnedBooleanKeys', tool.instance_key, $event)"
      @update:column-groups="emit('columnGroups', tool.instance_key, $event)"
      @update:stacked-column-keys="emit('stackedColumnKeys', tool.instance_key, $event)"
      @update:column-overrides="emit('configuration', tool.instance_key, { ...tool.configuration, column_overrides: $event })"
      @update:python-columns="emit('configuration', tool.instance_key, { ...tool.configuration, python_columns: $event })"
      @update:python-condition="emit('configuration', tool.instance_key, { ...tool.configuration, python_condition: $event })"
    />
    <div v-else-if="ratioExpression" class="analysis">
      <RatioUPlot :symbol="ratioExpression.numerator" :benchmarks="[ratioExpression.denominator]" :timeframe="activeTimeframe" :linked-timestamp="workspaceStore.timestampForLinkGroup(tool.link_group)" @cursor-timestamp="workspaceStore.publishTimestamp($event, tool.link_group, tool.instance_key)" />
    </div>
    <div v-else-if="tool.tool_type === 'chart' && tool.instance_key !== 'ratio-chart'" class="chart-tool">
      <DrawingToolbar class="chart-tool__drawing-toolbar" />
        <div class="chart-tool__surface">
        <ChartTemplateControl class="chart-tool__templates" :configuration="liveChartConfiguration" :indicator-configs="chartStore.indicators" @apply="applyChartTemplate" />
        <ChartPlotLibrary class="chart-tool__plots" :source-window-key="tool.instance_key" :link-group="tool.link_group" />
        <div class="chart-tool__compare" aria-label="Chart comparisons">
          <input v-model="comparisonDraft" aria-label="Comparison symbol" placeholder="Compare" @keydown.enter.prevent="addComparisonSymbol(comparisonDraft)" />
          <button type="button" title="Add comparison" @click="addComparisonSymbol(comparisonDraft)">＋</button>
          <button v-for="target in comparisonLegend" :key="target.symbol" type="button" class="chart-tool__compare-chip" :title="`Remove ${target.label}`" @click="removeComparisonSymbol(target.symbol)">
            <i :style="{ background: target.color }" />{{ target.symbol }} {{ target.percentChange == null ? '—' : `${target.percentChange >= 0 ? '+' : ''}${target.percentChange.toFixed(2)}%` }} ×
          </button>
        </div>
        <div v-if="chartStore.isLoading" class="tool-state">Loading {{ activeSymbol }}…</div>
        <div v-else-if="chartStore.error" class="tool-state tool-state--error">{{ chartStore.error }}</div>
        <UPlotChart
          v-else-if="chartStore.symbol"
          :chart-type="chartBarType"
          :chart-settings="liveChartConfiguration"
          :workspace-link-group="tool.link_group"
          :linked-timestamp="workspaceStore.timestampForLinkGroup(tool.link_group)"
          :comparison-series="comparisonSeries"
          @configuration="applyChartConfiguration"
        />
        <div v-else class="tool-state">Select a canonical instrument.</div>
      </div>
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
          <small>Verified ETF proxies · point-in-time holdings · {{ proxyCoverage }}</small>
          <VirtualWatchlistTool
            class="industry-list__proxy-table"
            label="Verified proxy rankings"
            :rows="proxyRows"
            :selected="selectedIndustryProxy ?? ''"
            :columns="proxyColumns"
            :visible-column-keys="configuredColumnKeys"
            :filter-text="configuredFilterText"
            :condition-screener-id="configuredConditionScreenerId"
            :condition-filter-mode="configuredConditionFilterMode"
            :pinned-boolean-keys="configuredPinnedBooleanKeys"
            :column-groups="configuredColumnGroups"
            :stacked-column-keys="configuredStackedColumnKeys"
            :python-columns="configuredPythonColumns"
            :python-condition="configuredPythonCondition"
            @select="selectProxy($event.symbol)"
            @compare="emit('compare', $event)"
            @row-action="handleRowAction"
            @update:visible-column-keys="emit('columns', tool.instance_key, $event)"
            @update:filter-text="emit('filter', tool.instance_key, $event)"
            @update:condition-screener-id="emit('conditionFilter', tool.instance_key, $event)"
            @update:condition-filter-mode="emit('conditionFilterMode', tool.instance_key, $event)"
            @update:pinned-boolean-keys="emit('pinnedBooleanKeys', tool.instance_key, $event)"
            @update:column-groups="emit('columnGroups', tool.instance_key, $event)"
            @update:stacked-column-keys="emit('stackedColumnKeys', tool.instance_key, $event)"
            @update:column-overrides="emit('configuration', tool.instance_key, { ...tool.configuration, column_overrides: $event })"
            @update:python-columns="emit('configuration', tool.instance_key, { ...tool.configuration, python_columns: $event })"
            @update:python-condition="emit('configuration', tool.instance_key, { ...tool.configuration, python_condition: $event })"
          />
          <small v-if="industryProxySnapshot?.exclusions.length" class="industry-list__proxy-warning">{{ industryProxySnapshot.exclusions.map(item => item.code).join(' · ') }}</small>
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
      :python-columns="configuredPythonColumns"
      :python-condition="configuredPythonCondition"
      @select="selectSymbol($event.symbol, $event.instrumentId)"
      @compare="emit('compare', $event)"
      @row-action="handleRowAction"
      @update:visible-column-keys="emit('columns', tool.instance_key, $event)"
      @update:filter-text="emit('filter', tool.instance_key, $event)"
      @update:condition-screener-id="emit('conditionFilter', tool.instance_key, $event)"
      @update:condition-filter-mode="emit('conditionFilterMode', tool.instance_key, $event)"
      @update:pinned-boolean-keys="emit('pinnedBooleanKeys', tool.instance_key, $event)"
      @update:column-groups="emit('columnGroups', tool.instance_key, $event)"
      @update:stacked-column-keys="emit('stackedColumnKeys', tool.instance_key, $event)"
      @update:column-overrides="emit('configuration', tool.instance_key, { ...tool.configuration, column_overrides: $event })"
      @update:python-columns="emit('configuration', tool.instance_key, { ...tool.configuration, python_columns: $event })"
      @update:python-condition="emit('configuration', tool.instance_key, { ...tool.configuration, python_condition: $event })"
    />
    <div v-else-if="tool.instance_key === 'ratio-chart'" class="analysis">
      <RatioUPlot :symbol="activeSymbol" :benchmarks="ratioBenchmarks" :timeframe="activeTimeframe" :linked-timestamp="workspaceStore.timestampForLinkGroup(tool.link_group)" @cursor-timestamp="workspaceStore.publishTimestamp($event, tool.link_group, tool.instance_key)" />
    </div>
    <div v-else-if="tool.instance_key === 'breadth-summary'" class="breadth-tool">
      <div class="metrics"><span>Above 20 MA</span><b>{{ breadthMetric('ma20') }}</b><span>Above 50 MA</span><b>{{ breadthMetric('ma50') }}</b><span>Above 200 MA</span><b>{{ breadthMetric('ma200') }}</b><span>Coverage</span><b>{{ breadthCoverage }}</b></div>
      <BreadthHistoryUPlot :history="breadthHistory" />
    </div>
    <RelativeRotationTool v-else-if="tool.instance_key === 'relative-rotation'" @select="selectSymbol($event)" />
    <div v-else-if="tool.instance_key === 'technical-summary'" class="metrics">
      <span>RSI(14)</span><b>{{ formatNumber(technical?.rsi14) }}</b>
      <span>20 / 50 / 200 MA</span><b>{{ technicalMAs }}</b>
      <span>52-week position</span><b>{{ formatPercent(technical?.position_52w) }}</b>
      <span>Volume ratio (50)</span><b>{{ formatRatio(technical?.volume_ratio_50) }}</b>
    </div>
    <CoverageSummaryTool v-else-if="tool.instance_key === 'coverage-summary'" :symbol="activeSymbol" />
    <InstrumentNoteTool v-else-if="tool.tool_type === 'notes'" :instrument-id="chartStore.instrument?.id" :symbol="activeSymbol" />
    <InstrumentAlertsTool v-else-if="tool.tool_type === 'alerts'" :instrument-id="chartStore.instrument?.id" :symbol="activeSymbol" />
    <InstrumentInfoPanel v-else-if="tool.tool_type === 'report'" class="instrument-report" :instrument="chartStore.instrument" :current-price="currentPrice" :session-high="currentSessionHigh" :session-low="currentSessionLow" @select="selectSymbol($event)" />
    <EasyScanTool v-else-if="tool.tool_type === 'scan'" />
    <MarketGaugeTool v-else-if="tool.tool_type === 'gauge'" />
    <StudyLabTool v-else-if="tool.tool_type === 'study_lab'" :active-symbol="activeSymbol" :configuration="tool.configuration" @configuration="emit('configuration', tool.instance_key, $event)" @occurrence="emit('occurrence', $event.symbol, $event.timestamp)" />
    <ResearchResultsTool v-else-if="tool.tool_type === 'research_results'" @occurrence="emit('occurrence', $event.symbol, $event.timestamp)" />
    <UnknownToolRecovery v-else :tool="tool" />
  </ToolWindow>
</template>

<script setup lang="ts">
import { computed, onMounted, provide, ref, watch } from 'vue'
import { api } from '@/lib/api'
import UPlotChart from '@/components/chart/UPlotChart.vue'
import DrawingToolbar from '@/components/chart/DrawingToolbar.vue'
import ChartTemplateControl from './ChartTemplateControl.vue'
import ChartPlotLibrary from './ChartPlotLibrary.vue'
import { usePanelStore } from '@/stores/chart'
import { useDrawingsStore } from '@/stores/drawings'
import { useAlertsStore } from '@/stores/alerts'
import { useWorkspaceStore, type LinkGroup, type WorkspaceWindowState } from '@/stores/workspace'
import { useWatchlistStore } from '@/stores/watchlist'
import type { Watchlist } from '@/types'
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
import InstrumentInfoPanel from '@/components/chart/InstrumentInfoPanel.vue'
import ResearchResultsTool from './ResearchResultsTool.vue'
import CoverageSummaryTool from './CoverageSummaryTool.vue'
import { calendarYearKeys } from '@/lib/workstation/calendarYears'
import { buildNormalizedComparisonSeries, type ComparisonTarget } from '@/lib/workstation/comparison'
import { ensureKnownInstrumentSymbol } from '@/lib/instruments'
import { INDICATOR_BY_TYPE } from '@/lib/indicators/catalog'
import { CHART_BAR_TYPES, type ChartBarType, type ChartComparisonSeries, type IndicatorConfig, type OHLCVBar, type Timeframe } from '@/types'

const props = defineProps<{
  tool: WorkspaceWindowState
  activeWindowKey?: string | null
  factoryLayout?: string | null
}>()
const emit = defineEmits<{ select: [symbol: string]; compare: [symbols: string[]]; reorder: [watchlistId: number, itemIds: number[]]; rowAction: [action: 'chart' | 'compare' | 'note' | 'alert' | 'copy', row: { symbol: string; instrumentId: number | null }]; occurrence: [symbol: string, timestamp: string]; selectIndustry: [industry: string]; selectProxy: [symbol: string]; columns: [windowKey: string, keys: string[]]; filter: [windowKey: string, value: string]; conditionFilter: [windowKey: string, screenerId: number | null]; conditionFilterMode: [windowKey: string, mode: 'active' | 'inactive' | 'off']; pinnedBooleanKeys: [windowKey: string, keys: string[]]; columnGroups: [windowKey: string, groups: Record<string, string>]; stackedColumnKeys: [windowKey: string, keys: string[]]; configuration: [windowKey: string, configuration: Record<string, unknown>]; timeframe: [value: string, group: LinkGroup]; float: [windowKey: string]; maximize: [windowKey: string]; close: [windowKey: string]; updateLinkGroup: [windowKey: string, group: LinkGroup] }>()
// uPlot already consumes a panel-scoped store through injection. Give every persisted
// workstation chart its own stable store identity so red/grey/yellow charts cannot
// accidentally render the shell's blue/default data.
const chartPanelId = `workstation-${props.tool.instance_key}`
provide('panelId', chartPanelId)
const chartStore = usePanelStore(chartPanelId)
const drawingsStore = useDrawingsStore()
const alertsStore = useAlertsStore()
const workspaceStore = useWorkspaceStore()
const watchlistStore = useWatchlistStore()
const selectedPersonalWatchlistId = ref<number | null>(typeof props.tool.configuration.watchlist_id === 'number' ? props.tool.configuration.watchlist_id : null)
const personalWatchlists = computed(() => watchlistStore.watchlists.filter(watchlist => !watchlist.is_managed))
const selectedPersonalWatchlist = computed<Watchlist | null>(() => personalWatchlists.value.find(watchlist => watchlist.id === selectedPersonalWatchlistId.value) ?? null)
const personalWatchlistRows = computed(() => (selectedPersonalWatchlist.value?.items ?? []).map(item => ({
  itemId: item.id,
  instrumentId: item.instrument_id,
  symbol: item.symbol ?? `#${item.instrument_id}`,
  name: item.name ?? item.symbol ?? `Instrument ${item.instrument_id}`,
  values: {
    last: watchlistStore.priceMap[item.symbol ?? '']?.close ?? null,
    change: watchlistStore.priceMap[item.symbol ?? '']?.pct ?? null,
  },
})))
const personalWatchlistColumns: WatchlistColumn[] = [
  { key: 'symbol', label: 'Symbol', width: '72px' },
  { key: 'name', label: 'Name', width: 'minmax(130px, 1fr)' },
  { key: 'last', label: 'Last', width: '72px', format: 'number' },
  { key: 'change', label: 'Chg %', width: '68px', format: 'percent' },
]
const personalSymbolDraft = ref('')
const personalListNameDraft = ref('')
const personalListBusy = ref(false)
const personalWatchlistBusy = ref(false)
const personalWatchlistError = ref('')

function selectPersonalWatchlist(raw: string) {
  const id = Number(raw)
  selectedPersonalWatchlistId.value = Number.isInteger(id) && id > 0 ? id : null
  personalListNameDraft.value = selectedPersonalWatchlist.value?.name ?? ''
  emit('configuration', props.tool.instance_key, { ...props.tool.configuration, watchlist_id: selectedPersonalWatchlistId.value })
}

async function createPersonalWatchlist() {
  const name = personalListNameDraft.value.trim()
  if (!name || personalListBusy.value) return
  personalListBusy.value = true
  personalWatchlistError.value = ''
  try {
    const created = await watchlistStore.createWatchlist(name)
    if (!created) throw new Error('Unable to create personal watchlist')
    selectedPersonalWatchlistId.value = created.id
    personalListNameDraft.value = created.name
    emit('configuration', props.tool.instance_key, { ...props.tool.configuration, watchlist_id: created.id })
  } catch (cause: any) {
    personalWatchlistError.value = cause?.message ?? 'Unable to create personal watchlist'
  } finally {
    personalListBusy.value = false
  }
}

async function renamePersonalWatchlist() {
  const watchlist = selectedPersonalWatchlist.value
  const name = personalListNameDraft.value.trim()
  if (!watchlist || watchlist.is_locked || watchlist.is_managed || !name || personalListBusy.value) return
  personalListBusy.value = true
  personalWatchlistError.value = ''
  try {
    const renamed = await watchlistStore.renameWatchlist(watchlist.id, name)
    if (!renamed) throw new Error('Unable to rename personal watchlist')
    personalListNameDraft.value = renamed.name
  } catch (cause: any) {
    personalWatchlistError.value = cause?.status === 409 ? 'Another window changed this watchlist; reload it before renaming.' : (cause?.message ?? 'Unable to rename personal watchlist')
  } finally {
    personalListBusy.value = false
  }
}

async function copyPersonalWatchlist() {
  const watchlist = selectedPersonalWatchlist.value
  if (!watchlist || personalListBusy.value) return
  personalListBusy.value = true
  personalWatchlistError.value = ''
  try {
    const copy = await watchlistStore.copyWatchlist(watchlist.id)
    if (!copy) throw new Error('Unable to copy personal watchlist')
    selectedPersonalWatchlistId.value = copy.id
    personalListNameDraft.value = copy.name
    emit('configuration', props.tool.instance_key, { ...props.tool.configuration, watchlist_id: copy.id })
  } catch (cause: any) {
    personalWatchlistError.value = cause?.message ?? 'Unable to copy personal watchlist'
  } finally {
    personalListBusy.value = false
  }
}

async function deletePersonalWatchlist() {
  const watchlist = selectedPersonalWatchlist.value
  if (!watchlist || watchlist.is_locked || watchlist.is_managed || personalListBusy.value) return
  if (!window.confirm(`Delete personal watchlist “${watchlist.name}”?`)) return
  personalListBusy.value = true
  personalWatchlistError.value = ''
  try {
    await watchlistStore.deleteWatchlist(watchlist.id)
    const next = personalWatchlists.value[0] ?? null
    selectedPersonalWatchlistId.value = next?.id ?? null
    personalListNameDraft.value = next?.name ?? ''
    emit('configuration', props.tool.instance_key, { ...props.tool.configuration, watchlist_id: selectedPersonalWatchlistId.value })
  } catch (cause: any) {
    personalWatchlistError.value = cause?.message ?? 'Unable to delete personal watchlist'
  } finally {
    personalListBusy.value = false
  }
}

async function addPersonalSymbol() {
  const watchlist = selectedPersonalWatchlist.value
  const raw = personalSymbolDraft.value.trim()
  if (!watchlist || watchlist.is_locked || watchlist.is_managed || !raw || personalWatchlistBusy.value) return
  personalWatchlistBusy.value = true
  personalWatchlistError.value = ''
  try {
    const item = await watchlistStore.addBySymbol(watchlist.id, raw)
    if (!item) throw new Error(`${raw.toUpperCase()} could not be added (it may already be in the list).`)
    personalSymbolDraft.value = ''
  } catch (cause: any) {
    personalWatchlistError.value = cause?.message ?? 'Unable to add symbol'
  } finally {
    personalWatchlistBusy.value = false
  }
}

function handlePersonalRowAction(action: 'chart' | 'compare' | 'note' | 'alert' | 'copy' | 'remove', row: { symbol: string; instrumentId: number | null; itemId?: number }) {
  if (action === 'remove' && selectedPersonalWatchlist.value && row.itemId != null) {
    void watchlistStore.removeItem(selectedPersonalWatchlist.value.id, row.itemId)
    return
  }
  if (action !== 'remove') handleRowAction(action, row)
}

onMounted(async () => {
  if (props.tool.tool_type !== 'watchlist' || props.tool.configuration.personal !== true) return
  if (!watchlistStore.watchlists.length) await watchlistStore.loadWatchlists()
  if (selectedPersonalWatchlistId.value == null) {
    selectedPersonalWatchlistId.value = personalWatchlists.value[0]?.id ?? null
    personalListNameDraft.value = personalWatchlists.value[0]?.name ?? ''
    if (selectedPersonalWatchlistId.value != null) {
      emit('configuration', props.tool.instance_key, { ...props.tool.configuration, watchlist_id: selectedPersonalWatchlistId.value })
    }
  }
  const symbols = personalWatchlistRows.value.map(row => row.symbol).filter(symbol => !symbol.startsWith('#'))
  if (symbols.length) await watchlistStore.fetchPrices(symbols)
})

watch(() => props.tool.configuration.watchlist_id, value => {
  selectedPersonalWatchlistId.value = typeof value === 'number' ? value : null
})

watch(() => selectedPersonalWatchlist.value?.items.map(item => item.symbol).join(','), value => {
  const symbols = (value ?? '').split(',').filter(Boolean)
  if (symbols.length) void watchlistStore.fetchPrices(symbols)
})
// A Golden Layout virtual component is mounted independently from its host render
// cycle. Keep the latest serializable chart configuration locally so template changes
// update its uPlot instance immediately, while the same object is persisted by the
// parent workspace snapshot.
const liveChartConfiguration = ref<Record<string, unknown>>(props.tool.configuration)
const activeSymbol = computed(() => workspaceStore.symbolForLinkGroup(
  props.tool.link_group,
  typeof props.tool.configuration.symbol === 'string' ? props.tool.configuration.symbol : null,
))
const activeTimeframe = computed(() => workspaceStore.timeframeForLinkGroup(
  timeframeLinkGroup.value,
  typeof props.tool.configuration.timeframe === 'string' ? props.tool.configuration.timeframe : null,
))
const timeframeLinkGroup = computed(() => workspaceStore.timeframeLinkGroupForTool(props.tool))
const ratioExpression = computed(() => {
  const expression = typeof props.tool.configuration.expression === 'string'
    ? props.tool.configuration.expression.trim().toUpperCase()
    : ''
  const match = expression.match(/^=([A-Z0-9.:-]+)\/([A-Z0-9.:-]+)$/)
  return match ? { numerator: match[1], denominator: match[2] } : null
})
const syntheticExpression = computed(() => {
  const expression = typeof props.tool.configuration.expression === 'string'
    ? props.tool.configuration.expression.trim()
    : ''
  return expression.startsWith('=') && !ratioExpression.value ? expression : null
})
const chartBarType = computed<ChartBarType>(() => {
  const requested = liveChartConfiguration.value.bar_type
  return typeof requested === 'string' && CHART_BAR_TYPES.some(type => type.value === requested)
    ? requested as ChartBarType
    : 'candles'
})
const comparisonDraft = ref('')
const comparisonTargets = ref<ComparisonTarget[]>([])
let comparisonRequestSequence = 0
const comparisonColors = ['#ffb74d', '#64b5f6', '#81c784', '#ba68c8', '#f06292', '#4dd0e1']
const configuredComparisonSymbols = computed(() => {
  const symbols = props.tool.configuration.comparison_symbols
  return Array.isArray(symbols)
    ? symbols.filter((symbol): symbol is string => typeof symbol === 'string' && Boolean(symbol.trim())).map(symbol => symbol.trim().toUpperCase())
    : []
})
const comparisonSeries = computed<ChartComparisonSeries[]>(() => {
  return buildNormalizedComparisonSeries(chartStore.bars, comparisonTargets.value)
})
const comparisonLegend = computed(() => comparisonSeries.value.map(series => ({
  symbol: series.symbol,
  label: series.label,
  color: series.color,
  percentChange: series.percentChange,
})))

function selectSymbol(symbol: string, instrumentId?: number | null) {
  workspaceStore.selectToolSymbol(props.tool.instance_key, symbol, instrumentId)
  // The shell owns canonical data loading and auto-ratio orchestration. Publish
  // row selections through it as well as the local link-group mutation so every
  // watchlist interaction follows the same top-down path as symbol entry.
  emit('select', symbol)
}

function setTimeframe(timeframe: string) {
  workspaceStore.updateToolTimeframe(props.tool.instance_key, timeframe)
}

function setTimeframeLinkGroup(group: LinkGroup) {
  workspaceStore.updateToolTimeframeLinkGroup(props.tool.instance_key, group)
}

function applyChartTemplate(configuration: Record<string, unknown>) {
  const indicators = templateIndicators(configuration.indicators)
  const identity = Object.fromEntries(Object.entries(props.tool.configuration)
    .filter(([key]) => ['symbol', 'instrument_id', 'expression', 'comparison_symbols'].includes(key)))
  const applied = { ...configuration, ...identity }
  if (indicators) {
    chartStore.setIndicators(indicators)
    // Chart store persistence is per canonical instrument, which keeps a template's
    // plot stack available when the window is restored or floated later.
    void chartStore.saveIndicatorsForInstrument()
  }
  liveChartConfiguration.value = applied
  emit('configuration', props.tool.instance_key, applied)
}

function persistComparisonSymbols() {
  emit('configuration', props.tool.instance_key, {
    ...liveChartConfiguration.value,
    comparison_symbols: comparisonTargets.value.map(target => target.symbol),
  })
}

async function loadComparisonBars() {
  const symbols = comparisonTargets.value.map(target => target.symbol)
  if (!symbols.length || !chartStore.symbol) return
  const sequence = ++comparisonRequestSequence
  const timeframe = activeTimeframe.value
  const loaded = await Promise.all(symbols.map(async symbol => {
    try {
      const raw = await api.get<any[]>(`/ohlcv/${encodeURIComponent(symbol)}/${timeframe}`, { limit: Math.max(chartStore.bars.length, 500) })
      return { symbol, bars: raw.map(bar => ({
        ...bar,
        ts: Number(bar.ts ?? bar.timestamp),
        open: Number(bar.open), high: Number(bar.high), low: Number(bar.low), close: Number(bar.close),
        volume: bar.volume == null ? undefined : Number(bar.volume),
        vwap: bar.vwap == null ? undefined : Number(bar.vwap),
      })) as OHLCVBar[] }
    } catch {
      return { symbol, bars: [] as OHLCVBar[] }
    }
  }))
  if (sequence !== comparisonRequestSequence) return
  comparisonTargets.value = comparisonTargets.value.map(target => ({ ...target, bars: loaded.find(item => item.symbol === target.symbol)?.bars ?? [] }))
}

async function addComparisonSymbol(raw: string) {
  const symbol = raw.trim().toUpperCase()
  if (!symbol || symbol === chartStore.symbol || comparisonTargets.value.some(target => target.symbol === symbol)) {
    comparisonDraft.value = ''
    return
  }
  try {
    const canonical = await ensureKnownInstrumentSymbol(symbol, 'Comparison symbol')
    comparisonTargets.value.push({ symbol: canonical, label: canonical, color: comparisonColors[comparisonTargets.value.length % comparisonColors.length], bars: [] })
    comparisonDraft.value = ''
    persistComparisonSymbols()
    await loadComparisonBars()
  } catch (cause: any) {
    chartStore.error = cause?.message ?? 'Unable to resolve comparison symbol'
  }
}

function removeComparisonSymbol(symbol: string) {
  comparisonTargets.value = comparisonTargets.value.filter(target => target.symbol !== symbol)
  persistComparisonSymbols()
}

function templateIndicators(value: unknown): IndicatorConfig[] | null {
  if (!Array.isArray(value)) return null
  const valid = value.filter((candidate): candidate is IndicatorConfig => {
    if (!candidate || typeof candidate !== 'object') return false
    const record = candidate as Record<string, unknown>
    return typeof record.type === 'string' && Boolean(INDICATOR_BY_TYPE[record.type as keyof typeof INDICATOR_BY_TYPE])
      && Boolean(record.params && typeof record.params === 'object' && !Array.isArray(record.params))
      && Boolean(record.style && typeof record.style === 'object' && !Array.isArray(record.style))
  })
  return valid.map(indicator => ({
    ...indicator,
    params: { ...indicator.params },
    style: { ...indicator.style },
    lockedTimeframes: indicator.lockedTimeframes ? [...indicator.lockedTimeframes] : indicator.lockedTimeframes,
  }))
}

function applyChartConfiguration(changes: Record<string, unknown>) {
  applyChartTemplate({ ...liveChartConfiguration.value, ...changes })
}

function selectProxy(symbol: string) {
  selectSymbol(symbol)
  emit('selectProxy', symbol)
}

function handleRowAction(action: 'chart' | 'compare' | 'note' | 'alert' | 'copy' | 'remove', row: { symbol: string; instrumentId: number | null }) {
  if (action === 'remove') return
  emit('rowAction', action, row)
}

watch([activeSymbol, activeTimeframe, syntheticExpression, chartBarType], async ([symbol, timeframe, expression, barType]) => {
  if (props.tool.tool_type !== 'chart' || (!symbol && !expression)) return
  let targetSymbol = symbol
  if (expression) {
    try {
      targetSymbol = await ensureKnownInstrumentSymbol(expression, 'Workstation expression')
    } catch (cause: any) {
      chartStore.error = cause?.message ?? 'Unable to resolve expression'
      return
    }
  }
  if (chartStore.symbol === targetSymbol && chartStore.timeframe === timeframe && chartStore.barType === barType) return
  void chartStore.loadBars(
    targetSymbol,
    timeframe as Timeframe,
    barType,
    true,
  )
}, { immediate: true })

watch(() => props.tool.configuration, configuration => {
  liveChartConfiguration.value = configuration
}, { deep: true })

watch([configuredComparisonSymbols, activeTimeframe, () => chartStore.symbol], async ([symbols, timeframe, symbol], previous) => {
  if (props.tool.tool_type !== 'chart') return
  const current = new Set(comparisonTargets.value.map(target => target.symbol))
  const requested = symbols.filter(candidate => candidate !== symbol)
  comparisonTargets.value = requested.map((symbol, index) => {
    const existing = comparisonTargets.value.find(target => target.symbol === symbol)
    return existing ?? { symbol, label: symbol, color: comparisonColors[index % comparisonColors.length], bars: [] }
  })
  const timeframeChanged = previous?.[1] !== timeframe || previous?.[2] !== symbol
  if (requested.length && (timeframeChanged || !current.size || requested.some(candidate => !current.has(candidate)))) await loadComparisonBars()
}, { immediate: true })

watch(() => props.tool.configuration.indicators, configured => {
  const indicators = templateIndicators(configured)
  if (indicators) chartStore.setIndicators(indicators)
}, { deep: true })

// The shared drawing and alert overlay stores are deliberately hydrated whenever a
// workstation chart resolves a canonical instrument. This gives docked/popped-out
// uPlot charts the same persisted drawing and alert-line mechanics as the legacy
// chart panel, rather than rendering a cosmetic toolbar with no backing state.
watch(() => [chartStore.instrument?.id, activeTimeframe.value] as const, ([instrumentId, timeframe]) => {
  if (props.tool.tool_type !== 'chart' || !instrumentId) return
  void drawingsStore.loadDrawings(instrumentId, timeframe as any)
  void alertsStore.loadAlerts(instrumentId)
}, { immediate: true })
const benchmarks = computed(() => workspaceStore.marketGroups['us-benchmarks']?.members.map(member => member.instrument.symbol) ?? [])
const sectors = computed(() => workspaceStore.marketGroups['sp500-sectors']?.members.map(member => member.instrument.symbol) ?? [])
const benchmarkIdentity = computed(() => {
  const identity = workspaceStore.marketGroups['us-benchmarks']?.provenance?.benchmark_identities
  const sp500 = identity && typeof identity === 'object' ? (identity as Record<string, unknown>).sp500 : null
  const details = sp500 && typeof sp500 === 'object' ? sp500 as Record<string, unknown> : {}
  return {
    official_index_symbol: typeof details.official_index_symbol === 'string' ? details.official_index_symbol : 'SPX',
    default_tradable_proxy: typeof details.default_tradable_proxy === 'string' ? details.default_tradable_proxy : 'SPY',
  }
})
const benchmarkSnapshot = computed(() => workspaceStore.groupSnapshots['us-benchmarks'])
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
const industryProxySnapshot = computed(() => selectedETF.value && selectedIndustry.value
  ? workspaceStore.industryProxySnapshots[`${selectedETF.value}:${selectedIndustry.value}`]
  : null)
const proxyRows = computed(() => (industryProxySnapshot.value?.rows ?? []).map(row => {
  const evidence = industryProxyState.value?.proxies.find(proxy => proxy.symbol === row.symbol)
  return {
  instrumentId: null,
  symbol: row.symbol,
  name: row.name,
  values: {
    performance_1m: row.performance['1M']?.value ?? null,
    relative_sector: row.relative_to_benchmark?.value ?? null,
    relative_spy: row.relative_to_market?.value ?? null,
    rsi14: row.technical.rsi14?.value ?? null,
    source: evidence?.source_provider ?? 'Unavailable',
    as_of: evidence?.composition_date ?? 'Unavailable',
    known_at: evidence?.known_at ? new Date(evidence.known_at).toLocaleDateString() : 'Unknown',
  },
}}))
const constituents = computed(() => {
  if (selectedETF.value && selectedIndustry.value) {
    return workspaceStore.industryConstituents[`${selectedETF.value}:${selectedIndustry.value}`]?.constituents.map(row => row.symbol) ?? []
  }
  return holdings.value?.holdings.filter(row => row.is_resolved && Boolean(row.constituent_symbol)).map(row => row.constituent_symbol as string) ?? []
})
const industryRows = computed(() => industries.value.map(item => ({
  instrumentId: null,
  symbol: item.industry,
  name: `${item.resolved_count}/${item.constituent_count}`,
  values: { proxy_count: workspaceStore.industryProxies[`${selectedETF.value}:${item.industry}`]?.proxies.length ?? null },
})))
const constituentLabel = computed(() => {
  if (!holdings.value) return 'No point-in-time ETF holdings snapshot'
  return `${holdings.value.snapshot.etf_symbol} holdings · ${holdings.value.snapshot.composition_date}`
})
const benchmarkRows = computed(() => (workspaceStore.marketGroups['us-benchmarks']?.members ?? []).map(member => ({
  instrumentId: member.instrument.id,
  symbol: member.instrument.symbol,
  name: member.instrument.name,
  values: (() => {
    const row = benchmarkSnapshot.value?.rows.find(item => item.instrument_id === member.instrument.id)
    return {
      performance_1d: row?.performance['1D']?.value ?? null,
      performance_1w: row?.performance['1W']?.value ?? null,
      performance_1m: row?.performance['1M']?.value ?? null,
      performance_3m: row?.performance['3M']?.value ?? null,
      performance_ytd: row?.performance.YTD?.value ?? null,
      performance_1y: row?.performance['1Y']?.value ?? null,
      relative_ratio: row?.relative_to_benchmark?.value == null ? null : row.relative_to_benchmark.value.toFixed(4),
      rsi14: row?.technical?.rsi14?.value ?? null,
      position_52w: row?.technical?.position_52w?.value ?? null,
      volume_ratio_50: row?.technical?.volume_ratio_50?.value == null ? null : row.technical.volume_ratio_50.value.toFixed(2),
    }
  })(),
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
      ...Object.fromEntries(Object.entries(row?.calendar_year_performance ?? {}).map(([year, cell]) => [`calendar_${year}`, cell.value])),
    }
  })(),
})))
const sectorByYearYears = computed(() => {
  return calendarYearKeys(workspaceStore.groupSnapshots['sp500-sectors']?.rows ?? [])
})
const factoryWatchlistRows = computed(() => {
  const title = (props.tool.title ?? '').toLowerCase()
  const factoryLayout = typeof props.tool.configuration.factory_layout === 'string' ? props.tool.configuration.factory_layout : ''
  if (props.factoryLayout === 'sector-by-year' || factoryLayout === 'sector-by-year' || title.includes('sector by year')) return sectorRows.value
  if (title.includes('sector')) return sectorRows.value
  if (title.includes('industry')) return industryRows.value
  if (title.includes('component') || title.includes('constituent')) return constituentRows.value
  return benchmarkRows.value
})
const factoryWatchlistColumns = computed<WatchlistColumn[]>(() => {
  const title = (props.tool.title ?? '').toLowerCase()
  const factoryLayout = typeof props.tool.configuration.factory_layout === 'string' ? props.tool.configuration.factory_layout : ''
  if (props.factoryLayout === 'sector-by-year' || factoryLayout === 'sector-by-year' || title.includes('sector by year')) return sectorByYearColumns.value
  if (title.includes('sector')) return sectorColumns
  if (title.includes('industry')) return industryColumns
  if (title.includes('component') || title.includes('constituent')) return constituentColumns
  return benchmarkColumns
})
const latestChartBar = computed(() => chartStore.bars.length ? chartStore.bars[chartStore.bars.length - 1] : null)
const currentPrice = computed(() => latestChartBar.value?.close ?? null)
const currentSessionHigh = computed(() => latestChartBar.value?.high ?? null)
const currentSessionLow = computed(() => latestChartBar.value?.low ?? null)
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
const sectorByYearColumns = computed<WatchlistColumn[]>(() => [
  { key: 'symbol', label: 'Symbol', width: '54px' },
  { key: 'name', label: 'Sector', width: 'minmax(90px, 1fr)' },
  ...sectorByYearYears.value.map(year => ({ key: `calendar_${year}`, label: String(year), width: '62px', format: 'percent' as const })),
  { key: 'relative_ratio', label: '/ SPY', width: '64px' },
  { key: 'rsi14', label: 'RSI', width: '54px', format: 'number' as const },
  { key: 'position_52w', label: '52W Pos', width: '64px' },
])
const benchmarkColumns: WatchlistColumn[] = [
  { key: 'symbol', label: 'Symbol', width: '58px' },
  { key: 'name', label: 'Benchmark', width: 'minmax(100px, 1fr)' },
  { key: 'performance_1d', label: '1D', width: '52px' },
  { key: 'performance_1w', label: '1W', width: '52px' },
  { key: 'performance_1m', label: '1M', width: '52px' },
  { key: 'performance_3m', label: '3M', width: '52px' },
  { key: 'performance_ytd', label: 'YTD', width: '52px' },
  { key: 'performance_1y', label: '1Y', width: '52px' },
  { key: 'relative_ratio', label: '/ SPY', width: '64px' },
  { key: 'rsi14', label: 'RSI', width: '52px', format: 'number' },
  { key: 'position_52w', label: '52W Pos', width: '64px' },
  { key: 'volume_ratio_50', label: 'Vol x50', width: '62px' },
]
const industryColumns: WatchlistColumn[] = [
  { key: 'symbol', label: 'Industry', width: 'minmax(120px, 1fr)' },
  { key: 'name', label: 'Coverage', width: '78px' },
  { key: 'proxy_count', label: 'Proxies', width: '58px' },
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
const proxyColumns: WatchlistColumn[] = [
  { key: 'symbol', label: 'Proxy', width: '56px' },
  { key: 'name', label: 'Name', width: 'minmax(92px, 1fr)' },
  { key: 'performance_1m', label: '1M', width: '54px' },
  { key: 'relative_sector', label: `/ ${selectedETF.value || 'Sector'}`, width: '62px', format: 'number' },
  { key: 'relative_spy', label: '/ SPY', width: '58px', format: 'number' },
  { key: 'rsi14', label: 'RSI', width: '48px', format: 'number' },
  { key: 'as_of', label: 'Holdings', width: '78px', format: 'number' },
  { key: 'known_at', label: 'Known', width: '72px', format: 'number' },
  { key: 'source', label: 'Source', width: '72px', format: 'number' },
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
const configuredColumnOverrides = computed(() => {
  const overrides = props.tool.configuration.column_overrides
  if (!overrides || typeof overrides !== 'object' || Array.isArray(overrides)) return {}
  return Object.fromEntries(Object.entries(overrides).flatMap(([key, value]) => {
    if (!value || typeof value !== 'object' || Array.isArray(value)) return []
    const candidate = value as Record<string, unknown>
    const label = typeof candidate.label === 'string' ? candidate.label.trim() : ''
    const width = typeof candidate.width === 'string' ? candidate.width.trim() : ''
    return label || width ? [[key, { ...(label ? { label } : {}), ...(width ? { width } : {}) }]] : []
  })) as Record<string, { label?: string; width?: string }>
})
const configuredPythonColumns = computed(() => Array.isArray(props.tool.configuration.python_columns)
  ? props.tool.configuration.python_columns.filter((column): column is { code_version_id: number; name: string } => Boolean(column) && typeof column === 'object' && Number.isInteger((column as Record<string, unknown>).code_version_id) && typeof (column as Record<string, unknown>).name === 'string')
  : [])
const configuredPythonCondition = computed(() => {
  const condition = props.tool.configuration.python_condition
  if (!condition || typeof condition !== 'object' || Array.isArray(condition)) return null
  const value = condition as Record<string, unknown>
  return Number.isInteger(value.code_version_id) && typeof value.name === 'string' && ['active', 'inactive', 'off'].includes(String(value.mode))
    ? { code_version_id: value.code_version_id as number, name: value.name, mode: value.mode as 'active' | 'inactive' | 'off' }
    : null
})
const descriptions: Record<string, string> = {
  SPY: 'S&P 500 proxy', RSP: 'S&P 500 equal weight', QQQ: 'Nasdaq-100 proxy', DIA: 'Dow Jones proxy', IWM: 'Russell 2000 proxy',
  XLK: 'Technology', XLY: 'Consumer Discretionary', XLC: 'Communication Services', XLF: 'Financials', XLV: 'Health Care', XLI: 'Industrials', XLP: 'Consumer Staples', XLE: 'Energy', XLU: 'Utilities', XLRE: 'Real Estate', XLB: 'Materials',
  NVDA: 'NVIDIA', MSFT: 'Microsoft', AAPL: 'Apple', AVGO: 'Broadcom', CRM: 'Salesforce', ORCL: 'Oracle', AMD: 'AMD', ADBE: 'Adobe',
}
const freshnessLabel = (value?: string) => value ? ` · ${value}` : ''
const breadthCoverage = computed(() => breadth.value ? `${(breadth.value.coverage * 100).toFixed(0)}% · ${breadth.value.evaluated_count} symbols${freshnessLabel(breadth.value.freshness)}` : 'Unavailable')
const technicalMAs = computed(() => [technical.value?.sma20, technical.value?.sma50, technical.value?.sma200]
  .map(value => formatNumber(value)).join(' / '))
function breadthMetric(key: string) {
  const value = breadth.value?.above_ma[key]
  return value == null ? 'Unavailable' : `${(value * 100).toFixed(1)}%`
}
function formatNumber(value: number | null | undefined) { return value == null ? 'Unavailable' : value.toFixed(2) }
function formatPercent(value: number | null | undefined) { return value == null ? 'Unavailable' : `${(value * 100).toFixed(1)}%` }
function formatRatio(value: number | null | undefined) { return value == null ? 'Unavailable' : `${value.toFixed(2)}×` }
const proxyCoverage = computed(() => industryProxySnapshot.value
  ? `${(industryProxySnapshot.value.coverage * 100).toFixed(0)}% local-bar coverage${freshnessLabel(industryProxySnapshot.value.freshness)}`
  : 'local-bar coverage pending')
</script>

<style scoped>
.chart-tool { display: flex; height: 100%; min-height: 0; background: #101419; }
.chart-tool__drawing-toolbar { flex: 0 0 auto; }
.chart-tool__surface { position: relative; min-width: 0; min-height: 0; flex: 1 1 auto; }
.chart-tool__templates { position: absolute; top: 3px; right: 4px; z-index: 12; }
.chart-tool__compare { position: absolute; top: 3px; left: 4px; z-index: 12; display: flex; align-items: center; gap: 3px; max-width: calc(100% - 120px); overflow: hidden; }
.chart-tool__compare input { width: 72px; border: 1px solid #42515c; background: #11161b; color: #dce9f2; padding: 2px 4px; font: 10px "Segoe UI", Arial, sans-serif; }
.chart-tool__compare > button { border: 1px solid #42515c; background: #1b252d; color: #b9c9d3; padding: 1px 4px; font: 10px "Segoe UI", Arial, sans-serif; cursor: pointer; white-space: nowrap; }
.chart-tool__compare-chip { overflow: hidden; text-overflow: ellipsis; }
.chart-tool__compare-chip i { display: inline-block; width: 7px; height: 7px; margin-right: 3px; border-radius: 50%; }
.tool-state { display: grid; place-items: center; height: 100%; padding: 12px; color: #98a7b2; font: 11px "Segoe UI", Arial, sans-serif; text-align: center; }
.tool-state--error { color: #ec8f8f; }
.benchmark-surface { display: grid; grid-template-rows: auto minmax(0, 1fr); height: 100%; min-height: 0; }
.benchmark-surface__identity { display: flex; align-items: baseline; gap: 9px; padding: 5px 7px; border-bottom: 1px solid #28343c; background: #121920; color: #91a2ad; font: 10px "Segoe UI", Arial, sans-serif; }
.benchmark-surface__identity strong { color: #d7e4eb; font-size: 11px; }
.benchmark-surface__identity span:first-of-type { color: #d2bc7a; }
.personal-watchlist-tool { display: grid; grid-template-rows: auto minmax(0, 1fr); height: 100%; min-height: 0; background: #11161b; }
.personal-watchlist-tool__controls { display: flex; align-items: center; gap: 8px; min-height: 28px; padding: 3px 7px; border-bottom: 1px solid #28343c; background: #121920; color: #91a2ad; font: 10px "Segoe UI", Arial, sans-serif; }
.personal-watchlist-tool__controls label { display: flex; align-items: center; gap: 5px; color: #d7e4eb; }
.personal-watchlist-tool__controls select { max-width: 210px; border: 1px solid #42515c; background: #11161b; color: #dce9f2; font: inherit; }
.personal-watchlist-tool__controls input, .personal-watchlist-tool__controls button { border: 1px solid #42515c; background: #11161b; color: #dce9f2; font: inherit; padding: 2px 5px; }
.personal-watchlist-tool__controls input { width: 84px; }
.personal-watchlist-tool__controls button { background: #1b303d; cursor: pointer; }
.personal-watchlist-tool__controls button:disabled { cursor: default; opacity: .5; }
.personal-watchlist-tool__controls span { color: #8498a6; }
.personal-watchlist-tool__controls .personal-watchlist-tool__error { color: #e49a9a; }
.analysis { height: 100%; min-height: 0; }
.breadth-tool { display:grid; grid-template-rows:auto minmax(0,1fr); height:100%; min-height:0; }.metrics { display: grid; grid-template-columns: 1fr auto; gap: 5px 10px; padding: 9px; color: #99a8b1; font: 10px "Segoe UI", Arial, sans-serif; }
.metrics b { color: #d2dce3; font-weight: 500; text-align: right; }
.industry-list { height: 100%; overflow: auto; background: #11161b; font: 11px "Segoe UI", Arial, sans-serif; }
.industry-list__row { display: flex; width: 100%; justify-content: space-between; gap: 8px; padding: 7px; border: 0; border-bottom: 1px solid #20282f; background: transparent; color: #c7d0d8; text-align: left; cursor: pointer; }
.industry-list__row:hover, .industry-list__row--active { background: #1d4057; }
.industry-list__proxies { display: grid; gap: 3px; padding: 6px 7px; border-bottom: 1px solid #20282f; color: #8998a3; }
.industry-list__proxy-table { height: 170px; border: 1px solid #34434e; }
.instrument-report { height: 100%; overflow: auto; background: #11161b; }
.industry-list__row strong { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.industry-list__row span, .industry-list small { color: #7d9db0; }
.industry-list small { display: block; padding: 7px; line-height: 1.3; }
</style>
