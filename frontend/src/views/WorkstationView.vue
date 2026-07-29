<template>
  <div class="workstation" @keydown="handleKeydown">
    <header class="workstation__menu">
      <div class="workstation__brand">CHARTING WORKSTATION</div>
      <nav aria-label="Application menu">
        <button v-for="item in ['File', 'Edit', 'Chart', 'Watchlist', 'Tools', 'Help']" :key="item" type="button" @click="item === 'Tools' && router.push('/study-lab')">{{ item }}</button>
      </nav>
      <div class="workstation__search">
        <input
          ref="symbolInput"
          v-model="symbolDraft"
          aria-label="Active symbol"
          placeholder="Symbol"
          @keydown.enter="selectSymbol(symbolDraft)"
        />
        <button type="button" @click="selectSymbol(symbolDraft)">Go</button>
      </div>
      <div class="workstation__status">
        <span :class="{ 'workstation__leader': workspaceStore.isPersistenceLeader }">●</span>
        {{ workspaceStore.isPersistenceLeader ? 'Leader' : 'Shared' }}
        <span>Polling</span>
      </div>
    </header>

    <div class="workstation__tabs">
      <button
        v-for="tab in workspaceStore.workspace?.tabs ?? []"
        :key="tab.stable_key"
        type="button"
        :class="{ 'workstation__tab--active': tab.stable_key === workspaceStore.activeTabKey }"
        @click="workspaceStore.activeTabKey = tab.stable_key"
      >{{ tab.name }}</button>
      <button type="button" class="workstation__tab-add" title="New workspace tab">+</button>
      <span class="workstation__workspace-name">{{ workspaceStore.workspace?.name ?? 'Loading workspace…' }}</span>
    </div>

    <WorkspaceLayoutHost
      v-if="goldenLayoutConfig"
      class="workstation__dock"
      :layout="goldenLayoutConfig"
      :render-tool="renderDockTool"
      @changed="persistGoldenLayout"
    />
    <main v-else class="workstation__grid" :class="{ 'workstation__grid--loading': workspaceStore.loading }">
      <ToolWindow title="Benchmarks" :symbol="activeSymbol" active @update:link-group="updateLinkGroup('benchmark-list', $event)">
        <SymbolListTool label="Major US benchmarks" :symbols="benchmarks" :selected="activeSymbol" :descriptions="descriptions" @select="selectSymbol" />
      </ToolWindow>

      <ToolWindow title="S&P 500 Sectors" :symbol="activeSymbol" @update:link-group="updateLinkGroup('sector-list', $event)">
        <SymbolListTool label="Relative to SPY" :symbols="sectors" :selected="activeSymbol" comparison="SPY" :descriptions="descriptions" :metrics="sectorPerformance" @select="selectSymbol" />
      </ToolWindow>

      <ToolWindow title="Chart" :symbol="activeSymbol" @update:link-group="updateLinkGroup('primary-chart', $event)">
        <div class="workstation__chart">
          <div v-if="chartStore.isLoading" class="workstation__chart-state">Loading {{ activeSymbol }}…</div>
          <div v-else-if="chartStore.error" class="workstation__chart-state workstation__chart-state--error">{{ chartStore.error }}</div>
          <UPlotChart v-else-if="chartStore.symbol" />
          <div v-else class="workstation__chart-state">Select a canonical instrument.</div>
        </div>
      </ToolWindow>

      <ToolWindow title="Industries / Proxies" :symbol="activeSymbol" @update:link-group="updateLinkGroup('industry-list', $event)">
        <SymbolListTool label="Selected-sector proxies" :symbols="industryProxies" :selected="activeSymbol" comparison="XLK" :descriptions="descriptions" @select="selectSymbol" />
      </ToolWindow>

      <ToolWindow title="Constituents" :symbol="activeSymbol" @update:link-group="updateLinkGroup('constituent-list', $event)">
        <SymbolListTool label="Selected group" :symbols="constituents" :selected="activeSymbol" comparison="XLK" :descriptions="descriptions" @select="selectSymbol" />
      </ToolWindow>

      <ToolWindow title="Relative Strength" :symbol="activeSymbol" @update:link-group="updateLinkGroup('ratio-chart', $event)">
        <div class="workstation__analysis">
          <strong>{{ activeSymbol }}/SPY</strong>
          <strong v-if="activeSymbol !== 'XLK'">{{ activeSymbol }}/XLK</strong>
          <p>Ratio views are resolved through canonical synthetic instruments. Missing or misaligned bars remain explicitly excluded.</p>
        </div>
      </ToolWindow>

      <ToolWindow title="Technicals" :symbol="activeSymbol">
        <div class="workstation__metrics">
          <span>RSI</span><b>Coverage pending</b>
          <span>20/50/200 MA</span><b>Canonical batch API</b>
          <span>52-week position</span><b>Source-labelled</b>
          <span>Volume ratio</span><b>Freshness-aware</b>
        </div>
      </ToolWindow>

      <ToolWindow title="Breadth & Coverage" :symbol="activeSymbol">
        <div class="workstation__metrics">
          <span>Above 20 MA</span><b>{{ breadthMetric('ma20') }}</b>
          <span>Above 50 MA</span><b>{{ breadthMetric('ma50') }}</b>
          <span>Above 200 MA</span><b>{{ breadthMetric('ma200') }}</b>
          <span>Coverage</span><b>{{ breadthCoverage }}</b>
        </div>
      </ToolWindow>
    </main>

    <footer class="workstation__footer">
      <span>{{ activeSymbol }}</span>
      <span>{{ chartStore.timeframe }}</span>
      <span>{{ workspaceStore.error ?? 'Ready' }}</span>
      <span>Current / delayed / stale states remain provider-derived</span>
    </footer>
  </div>
</template>

<script setup lang="ts">
import { computed, h, nextTick, onBeforeUnmount, onMounted, ref, watch, type VNode } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import ToolWindow from '@/components/workstation/ToolWindow.vue'
import WorkspaceLayoutHost from '@/components/workstation/WorkspaceLayoutHost.vue'
import WorkstationToolContent from '@/components/workstation/WorkstationToolContent.vue'
import SymbolListTool from '@/components/workstation/SymbolListTool.vue'
import UPlotChart from '@/components/chart/UPlotChart.vue'
import { useChartStore } from '@/stores/chart'
import { useWorkspaceStore, type LinkGroup } from '@/stores/workspace'
import type { LayoutConfig } from 'golden-layout'

const route = useRoute()
const router = useRouter()
const chartStore = useChartStore()
const workspaceStore = useWorkspaceStore()
const symbolInput = ref<HTMLInputElement | null>(null)
const symbolDraft = ref('')

const benchmarks = computed(() => workspaceStore.marketGroups['us-benchmarks']?.members.map(member => member.instrument.symbol) ?? [])
const sectors = computed(() => workspaceStore.marketGroups['sp500-sectors']?.members.map(member => member.instrument.symbol) ?? [])
const industryProxies = ['SMH', 'IGV', 'SOXX', 'HACK', 'SKYY']
const constituents = ['NVDA', 'MSFT', 'AAPL', 'AVGO', 'CRM', 'ORCL', 'AMD', 'ADBE']
const descriptions: Record<string, string> = {
  SPY: 'S&P 500 proxy', RSP: 'S&P 500 equal weight', QQQ: 'Nasdaq-100 proxy', DIA: 'Dow Jones proxy', IWM: 'Russell 2000 proxy',
  XLK: 'Technology', XLY: 'Consumer Discretionary', XLC: 'Communication Services', XLF: 'Financials', XLV: 'Health Care',
  XLI: 'Industrials', XLP: 'Consumer Staples', XLE: 'Energy', XLU: 'Utilities', XLRE: 'Real Estate', XLB: 'Materials',
  NVDA: 'NVIDIA', MSFT: 'Microsoft', AAPL: 'Apple', AVGO: 'Broadcom', CRM: 'Salesforce', ORCL: 'Oracle', AMD: 'AMD', ADBE: 'Adobe',
}

const activeSymbol = computed(() => workspaceStore.linkedSymbol || 'SPY')
const allSymbols = computed(() => [...benchmarks.value, ...sectors.value, ...industryProxies, ...constituents])
const goldenLayoutConfig = computed(() => {
  const layout = workspaceStore.activeTab?.layout_config
  if (layout?.root) return layout as LayoutConfig
  const windows = workspaceStore.activeTab?.windows ?? []
  if (!windows.length) return null
  return {
    root: {
      type: 'row',
      content: windows.map(window => ({
        type: 'component', componentType: 'workstation-tool', title: window.title ?? window.tool_type,
        componentState: { instance_key: window.instance_key, tool_type: window.tool_type, title: window.title ?? window.tool_type },
      })),
    },
  } as unknown as LayoutConfig
})
const sectorPerformance = computed(() => Object.fromEntries(
  (workspaceStore.groupSnapshots['sp500-sectors']?.rows ?? []).map(row => [row.symbol, row.performance['1M']?.value ?? null]),
))
const sectorBreadth = computed(() => workspaceStore.breadth['sp500-sectors'])
const breadthCoverage = computed(() => sectorBreadth.value ? `${(sectorBreadth.value.coverage * 100).toFixed(0)}% · ${sectorBreadth.value.evaluated_count} symbols` : 'Unavailable')
function breadthMetric(key: string) {
  const value = sectorBreadth.value?.above_ma[key]
  return value == null ? 'Unavailable' : `${(value * 100).toFixed(1)}%`
}

async function selectSymbol(raw: string) {
  const symbol = raw.trim().toUpperCase()
  if (!symbol) return
  symbolDraft.value = symbol
  workspaceStore.publishSymbol({ symbol, group: 'blue', sourceWindowKey: 'workstation' })
  await Promise.all([
    chartStore.loadBars(symbol, chartStore.timeframe, chartStore.barType, true),
    workspaceStore.loadETFHoldings(symbol),
    workspaceStore.loadETFIndustries(symbol),
  ])
}

function updateLinkGroup(windowKey: string, group: LinkGroup) {
  const windowState = workspaceStore.activeTab?.windows.find(window => window.instance_key === windowKey)
  if (windowState) windowState.link_group = group
}

function renderDockTool(dockTool: { instance_key: string; title: string; tool_type: string }): VNode {
  const tool = workspaceStore.activeTab?.windows.find(window => window.instance_key === dockTool.instance_key)
  if (!tool) return h('div', { class: 'workstation__missing-tool' }, `Missing persisted tool: ${dockTool.instance_key}`)
  return h(WorkstationToolContent, {
    tool,
    activeWindowKey: workspaceStore.activeTab?.active_window_key,
    onSelect: (symbol: string) => void selectSymbol(symbol),
    onSelectIndustry: (industry: string) => void workspaceStore.selectIndustry(workspaceStore.constituentETF ?? '', industry),
    onUpdateLinkGroup: (windowKey: string, group: LinkGroup) => updateLinkGroup(windowKey, group),
  })
}

function persistGoldenLayout(layout: Record<string, unknown>) {
  if (workspaceStore.activeTab) {
    workspaceStore.activeTab.layout_config = layout
    workspaceStore.scheduleSnapshot()
  }
}

function handleKeydown(event: KeyboardEvent) {
  if (workspaceStore.isEditorTarget(event.target)) return
  if (/^[a-z0-9.=]$/i.test(event.key) && !event.ctrlKey && !event.metaKey && !event.altKey) {
    event.preventDefault()
    symbolInput.value?.focus()
    symbolDraft.value = event.key.toUpperCase()
    return
  }
  if (event.key !== ' ' || event.ctrlKey || event.metaKey || event.altKey) return
  event.preventDefault()
  if (!allSymbols.value.length) return
  const currentIndex = allSymbols.value.indexOf(activeSymbol.value)
  const nextIndex = (currentIndex + (event.shiftKey ? -1 : 1) + allSymbols.value.length) % allSymbols.value.length
  void selectSymbol(allSymbols.value[nextIndex])
}

watch(activeSymbol, symbol => {
  if (!symbol || chartStore.symbol === symbol) return
  void Promise.all([
    chartStore.loadBars(symbol, chartStore.timeframe, chartStore.barType, true),
    workspaceStore.loadETFHoldings(symbol),
    workspaceStore.loadETFIndustries(symbol),
  ])
})

onMounted(async () => {
  workspaceStore.connect()
  await workspaceStore.loadDefault()
  await Promise.all([
    workspaceStore.loadMarketGroup('us-benchmarks'),
    workspaceStore.loadMarketGroup('sp500-sectors'),
    workspaceStore.loadGroupSnapshot('sp500-sectors', 'SPY'),
    workspaceStore.loadBreadth('sp500-sectors'),
  ])
  const requested = String(route.params.symbol ?? route.query.symbol ?? 'SPY')
  await selectSymbol(requested)
  await nextTick()
})

onBeforeUnmount(() => workspaceStore.disconnect())
</script>

<style scoped>
.workstation { --tc-border: #303940; --tc-window: #15191e; width: 100%; height: 100%; min-width: 980px; display: grid; grid-template-rows: 29px 28px minmax(0, 1fr) 21px; overflow: hidden; color: #d5dde4; background: #0d1013; font-family: "Segoe UI", Arial, sans-serif; }
.workstation__menu { display: flex; align-items: center; gap: 12px; padding: 0 7px; background: linear-gradient(#2c3339, #1c2227); border-bottom: 1px solid #090b0d; }
.workstation__brand { color: #8fc7ea; font-size: 10px; font-weight: 700; letter-spacing: .06em; white-space: nowrap; }
.workstation__menu nav { display: flex; align-self: stretch; }
.workstation__menu nav button, .workstation__tab-add { border: 0; background: transparent; color: #d4d9dd; padding: 0 8px; font: 11px "Segoe UI", Arial, sans-serif; cursor: pointer; }
.workstation__menu nav button:hover, .workstation__tab-add:hover { background: #3a444d; color: #fff; }
.workstation__search { display: flex; height: 21px; margin-left: 10px; }
.workstation__search input { width: 88px; padding: 0 5px; border: 1px solid #4d5a63; background: #11161a; color: #f1f5f7; font: 11px "Segoe UI", Arial, sans-serif; text-transform: uppercase; }
.workstation__search button { border: 1px solid #4d5a63; border-left: 0; background: #26333d; color: #dce9f2; padding: 0 7px; font-size: 10px; cursor: pointer; }
.workstation__status { margin-left: auto; display: flex; gap: 8px; color: #81909a; font-size: 10px; }
.workstation__leader { color: #63bd85; }
.workstation__tabs { display: flex; align-items: stretch; background: #151a1f; border-bottom: 1px solid #303940; }
.workstation__tabs > button:not(.workstation__tab-add) { min-width: 112px; padding: 0 11px; border: 0; border-right: 1px solid #303940; background: #1b2126; color: #9facb5; font: 11px "Segoe UI", Arial, sans-serif; cursor: pointer; }
.workstation__tabs > button.workstation__tab--active { background: #28333b; color: #eaf2f6; box-shadow: inset 0 2px #68b6e9; }
.workstation__workspace-name { margin-left: auto; padding: 7px 9px; color: #697782; font-size: 10px; }
.workstation__grid { min-width: 0; min-height: 0; display: grid; grid-template-columns: minmax(180px, 18%) minmax(190px, 19%) minmax(420px, 1fr); grid-template-rows: minmax(150px, 1fr) minmax(160px, 1fr) minmax(110px, .65fr); gap: 3px; padding: 3px; background: #090c0f; }
.workstation__grid > :nth-child(1) { grid-column: 1; grid-row: 1; }
.workstation__grid > :nth-child(2) { grid-column: 2; grid-row: 1; }
.workstation__grid > :nth-child(3) { grid-column: 3; grid-row: 1 / span 2; }
.workstation__grid > :nth-child(4) { grid-column: 1; grid-row: 2; }
.workstation__grid > :nth-child(5) { grid-column: 2; grid-row: 2; }
.workstation__grid > :nth-child(6) { grid-column: 1; grid-row: 3; }
.workstation__grid > :nth-child(7) { grid-column: 2; grid-row: 3; }
.workstation__grid > :nth-child(8) { grid-column: 3; grid-row: 3; }
.workstation__grid--loading { opacity: .7; }
.workstation__chart { height: 100%; min-height: 0; position: relative; background: #101419; }
.workstation__chart-state { display: grid; height: 100%; place-items: center; color: #98a7b2; font-size: 12px; }
.workstation__chart-state--error { color: #ec8f8f; }
.workstation__analysis { display: grid; gap: 8px; padding: 10px; color: #aebbc4; font-size: 11px; }
.workstation__analysis strong { color: #71c3f5; font-size: 14px; }
.workstation__analysis p { color: #84929c; line-height: 1.45; }
.workstation__metrics { display: grid; grid-template-columns: 1fr auto; gap: 5px 10px; padding: 9px; color: #99a8b1; font-size: 10px; }
.workstation__metrics b { color: #d2dce3; font-weight: 500; text-align: right; }
.workstation__footer { display: flex; gap: 16px; align-items: center; padding: 0 7px; border-top: 1px solid #2f3941; color: #84939d; background: #151a1f; font-size: 10px; }
.workstation__footer span:first-child { color: #d4e7f4; font-weight: 700; }
</style>
