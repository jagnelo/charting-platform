<template>
  <div class="workstation" @keydown="handleKeydown">
    <header v-if="!isPopout" class="workstation__menu">
      <div class="workstation__brand">CHARTING WORKSTATION</div>
      <nav aria-label="Application menu">
        <div class="workstation__workspace-menu">
          <button type="button" title="Manage workspace layouts" :aria-expanded="workspaceMenuOpen" @click="workspaceMenuOpen = !workspaceMenuOpen">Workspace</button>
          <div v-if="workspaceMenuOpen" class="workstation__workspace-popover" aria-label="Workspace layouts" @click.stop>
            <header><strong>Layouts</strong><small>{{ workspaceStore.workspace?.name ?? 'Workspace' }}</small></header>
            <div class="workstation__workspace-actions">
              <button type="button" @click="workspaceStore.cloneActiveTab(); workspaceMenuOpen = false">Clone</button>
              <button type="button" @click="exportWorkspace">Export</button>
              <button type="button" @click="workspaceFileInput?.click()">Import</button>
              <input ref="workspaceFileInput" class="workstation__workspace-file" type="file" accept="application/json,.json" @change="importWorkspace" />
            </div>
            <div class="workstation__layout-list">
              <div v-for="tab in workspaceStore.workspace?.tabs ?? []" :key="tab.stable_key" class="workstation__layout-item" draggable="true" @dragstart="dragTabKey = tab.stable_key" @dragover.prevent @drop.prevent="dropTab(tab.stable_key)" @dragend="dragTabKey = null">
                <button type="button" class="workstation__layout-select" :class="{ active: tab.stable_key === workspaceStore.activeTabKey }" @click="workspaceStore.activeTabKey = tab.stable_key; workspaceMenuOpen = false">{{ tab.name }}</button>
                <input :aria-label="`Rename ${tab.name}`" :value="tab.name" @change="renameTab(tab.stable_key, ($event.target as HTMLInputElement).value)" />
                <button type="button" class="workstation__layout-delete" :disabled="(workspaceStore.workspace?.tabs.length ?? 0) <= 1" :aria-label="`Delete ${tab.name}`" @click="deleteTab(tab.stable_key)">×</button>
              </div>
            </div>
            <button v-if="workspaceStore.workspace?.settings.factory_id === 'us-top-down'" type="button" class="workstation__layout-reset" @click="resetFactoryWorkspace(); workspaceMenuOpen = false">Reset factory layout</button>
          </div>
        </div>
        <button type="button" title="Open Study Lab layout" @click="workspaceStore.activeTabKey = 'study-lab'">Study</button>
        <button type="button" title="Open active-symbol alerts" @click="openAlertsTool">Alerts</button>
        <button v-if="workspaceStore.workspace?.is_default" type="button" title="Reset factory workspace" @click="resetFactoryWorkspace">Reset</button>
      </nav>
      <div class="workstation__search">
        <input
          ref="symbolInput"
          v-model="symbolDraft"
          aria-label="Active symbol"
          placeholder="Symbol"
          autocomplete="off"
          role="combobox"
          :aria-expanded="searchResults.length > 0"
          aria-controls="workstation-symbol-results"
          @keydown.stop="handleSymbolInputKeydown"
        />
        <button type="button" @click="selectSymbol(symbolDraft)">Go</button>
        <div v-if="searchResults.length" id="workstation-symbol-results" class="workstation__symbol-results" role="listbox" aria-label="Symbol search results">
          <button
            v-for="(result, index) in searchResults"
            :key="`${result.symbol}:${result.exchange}`"
            type="button"
            role="option"
            :aria-selected="index === searchIndex"
            @mousedown.prevent="selectSearchResult(result.symbol)"
          ><strong>{{ result.symbol }}</strong><span>{{ result.name }}</span><small>{{ result.exchange || result.type }}</small></button>
        </div>
      </div>
      <label class="workstation__timeframe">TF
        <select :value="workspaceStore.linkedTimeframe" aria-label="Linked timeframe" @change="setLinkedTimeframe(($event.target as HTMLSelectElement).value)">
          <option value="M1">1 minute</option><option value="M5">5 minutes</option><option value="M15">15 minutes</option><option value="M30">30 minutes</option><option value="H1">1 hour</option><option value="H2">2 hours</option><option value="H4">4 hours</option><option value="H12">12 hours</option><option value="D1">Daily</option><option value="W1">Weekly</option><option value="MN">Monthly</option>
        </select>
      </label>
      <div class="workstation__status">
        <span :class="{ 'workstation__leader': workspaceStore.isPersistenceLeader }">●</span>
        {{ workspaceStore.isPersistenceLeader ? 'Leader' : 'Shared' }}
        <span :class="`workstation__data-state--${dataState.kind}`">{{ dataState.label }}</span>
        <button type="button" class="workstation__refresh" :disabled="workspaceStore.marketAnalysisRefreshing" title="Refresh top-down analysis" @click="refreshMarketData">{{ workspaceStore.marketAnalysisRefreshing ? 'Refreshing…' : 'Refresh' }}</button>
        <button type="button" class="workstation__sign-out logout-btn" title="Sign out" @click="signOut">Sign out</button>
      </div>
    </header>

    <div v-if="!isPopout" class="workstation__tabs">
      <button
        v-for="tab in workspaceStore.workspace?.tabs ?? []"
        :key="tab.stable_key"
        type="button"
        :class="{ 'workstation__tab--active': tab.stable_key === workspaceStore.activeTabKey }"
        @click="workspaceStore.activeTabKey = tab.stable_key"
      >{{ tab.name }}</button>
      <button type="button" class="workstation__tab-add" title="Clone active layout" @click="workspaceStore.cloneActiveTab()">+</button>
      <div class="workstation__tool-library">
        <button type="button" class="workstation__tab-add" title="Open a workstation tool" @click="toolLibraryOpen = !toolLibraryOpen">Add tool</button>
        <div v-if="toolLibraryOpen" class="workstation__tool-library-menu">
          <button v-for="tool in openableTools" :key="tool.instance_prefix" type="button" @click="openTool(tool)">{{ tool.title }}</button>
        </div>
      </div>
      <button v-if="workspaceStore.workspace?.settings.factory_id === 'us-top-down'" type="button" class="workstation__tab-reset" title="Reset factory workspace" @click="resetFactoryWorkspace">↺</button>
      <span class="workstation__workspace-name">{{ workspaceStore.workspace?.name ?? 'Loading workspace…' }}</span>
    </div>

    <WorkspaceLayoutHost
      v-if="!isPopout && goldenLayoutConfig"
      class="workstation__dock"
      :layout="goldenLayoutConfig"
      :render-tool="renderDockTool"
      @changed="persistGoldenLayout"
    />
    <main v-if="isPopout" class="workstation__popout">
      <WorkstationToolContent
        v-if="popoutTool"
        :tool="popoutTool"
        :active-window-key="popoutTool.instance_key"
        :factory-layout="workspaceStore.activeTabKey"
        @select="selectSymbol"
        @compare="compareSymbols"
        @reorder="reorderWatchlistItems"
        @row-action="handleRowAction"
        @occurrence="selectOccurrence"
        @select-industry="workspaceStore.selectIndustry(workspaceStore.constituentETF ?? '', $event)"
        @select-proxy="selectIndustryProxy"
        @columns="updateColumns"
        @filter="updateFilter"
        @condition-filter="updateConditionFilter"
        @condition-filter-mode="updateConditionFilterMode"
        @pinned-boolean-keys="updatePinnedBooleanKeys"
        @column-groups="updateColumnGroups"
        @stacked-column-keys="updateStackedColumnKeys"
        @configuration="updateToolConfiguration"
        @update-link-group="updateLinkGroup"
        @timeframe="setLinkedTimeframe"
        @close="closePopoutTool"
      />
      <div v-else class="workstation__missing-tool">The requested tool is unavailable. It remains in the source workspace.</div>
    </main>
    <main v-else-if="!isPopout" class="workstation__layout-state" role="status">
      <span v-if="workspaceStore.loading">Loading saved workstation…</span>
      <template v-else>
        <span>Unable to load a serializable workstation layout.</span>
        <button type="button" @click="workspaceStore.loadDefault()">Retry</button>
      </template>
    </main>

    <footer v-if="!isPopout" class="workstation__footer">
      <span>{{ activeSymbol }}</span>
      <span>{{ chartStore.timeframe }}</span>
      <span>{{ workspaceStore.error ?? 'Ready' }}</span>
      <span :class="`workstation__data-state--${dataState.kind}`">{{ dataState.label }}</span>
    </footer>
  </div>
</template>

<script setup lang="ts">
import { computed, h, nextTick, onBeforeUnmount, onMounted, ref, watch, type VNode } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useQuery } from '@tanstack/vue-query'
import WorkspaceLayoutHost from '@/components/workstation/WorkspaceLayoutHost.vue'
import WorkstationToolContent from '@/components/workstation/WorkstationToolContent.vue'
import { useChartStore } from '@/stores/chart'
import { useAuthStore } from '@/stores/auth'
import { OPENABLE_WORKSTATION_TOOLS, useWorkspaceStore, type LinkGroup, type OpenableToolDefinition } from '@/stores/workspace'
import type { LayoutConfig } from 'golden-layout'
import { ensureKnownInstrumentSymbol } from '@/lib/instruments'
import { autoRatioExpression } from '@/lib/workstation/ratioExpression'
import { api } from '@/lib/api'
import { useWatchlistStore } from '@/stores/watchlist'

const route = useRoute()
const router = useRouter()
const chartStore = useChartStore()
const authStore = useAuthStore()
const workspaceStore = useWorkspaceStore()
const watchlistStore = useWatchlistStore()
const symbolInput = ref<HTMLInputElement | null>(null)
const symbolDraft = ref('')
const toolLibraryOpen = ref(false)
const workspaceMenuOpen = ref(false)
const workspaceFileInput = ref<HTMLInputElement | null>(null)
const dragTabKey = ref<string | null>(null)
const searchResults = ref<Array<{ symbol: string; name: string; exchange: string; type: string }>>([])
const searchIndex = ref(-1)
let searchTimer: ReturnType<typeof setTimeout> | null = null
let searchRequest = 0
let suppressNextSearch = false
const preserveDrilldownSymbol = ref<string | null>(null)
const openableTools = OPENABLE_WORKSTATION_TOOLS
const documentVisible = ref(typeof document === 'undefined' || document.visibilityState === 'visible')
let removeVisibilityListener: (() => void) | null = null

const activeSymbol = computed(() => workspaceStore.linkedSymbol || 'SPY')
const dataState = computed(() => {
  if (chartStore.isLoading) return { kind: 'fetching', label: 'Fetching' }
  if (chartStore.isFetchingHistory) return { kind: 'fetching', label: 'Backfilling history' }
  if (chartStore.error) return { kind: 'unavailable', label: 'Unavailable' }
  const latest = chartStore.bars.length ? chartStore.bars[chartStore.bars.length - 1] : null
  if (!latest) return { kind: 'unavailable', label: 'No local observations' }
  return { kind: 'cached', label: `Cached ${new Date(latest.ts).toLocaleString()}` }
})
const isPopout = computed(() => route.path.startsWith('/popout/'))

// The shell is the coordinator for the shared top-down inputs. Keep this in the
// same Vue Query cache as the explicit Refresh action so docked and floated
// windows cannot create independent five-minute timers or duplicate the six
// canonical requests. Vue Query automatically pauses the interval while the
// document is hidden; the explicit visibility gate also prevents a queued
// refresh from starting while hidden.
const marketAnalysisQuery = useQuery({
  queryKey: ['workstation', 'market-analysis'],
  queryFn: async () => {
    await workspaceStore.refreshMarketAnalysis()
    return true
  },
  enabled: computed(() => !isPopout.value && documentVisible.value && Boolean(workspaceStore.workspace)),
  staleTime: 60_000,
  refetchInterval: 5 * 60 * 1000,
  refetchIntervalInBackground: false,
})

async function refreshMarketData() {
  if (isPopout.value || !documentVisible.value) return
  await marketAnalysisQuery.refetch()
}
const popoutTool = computed(() => {
  const key = String(route.params.windowKey ?? '')
  const requestedTab = typeof route.query.tab === 'string' ? route.query.tab : null
  const preferredTab = requestedTab
    ? workspaceStore.workspace?.tabs.find(tab => tab.stable_key === requestedTab)
    : workspaceStore.activeTab
  return preferredTab?.windows.find(window => window.instance_key === key)
    ?? workspaceStore.workspace?.tabs.flatMap(tab => tab.windows).find(window => window.instance_key === key)
    ?? null
})
const allSymbols = computed(() => [
  ...(workspaceStore.marketGroups['us-benchmarks']?.members ?? []),
  ...(workspaceStore.marketGroups['sp500-sectors']?.members ?? []),
].map(member => member.instrument.symbol))
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
async function selectSymbol(raw: string, timestamp?: string) {
  const requested = raw.trim()
  if (!requested) return
  suppressNextSearch = true
  searchResults.value = []
  searchIndex.value = -1
  let symbol: string
  try {
    symbol = await ensureKnownInstrumentSymbol(requested, 'Workstation symbol')
  } catch (cause: any) {
    workspaceStore.error = cause?.message ?? 'Unable to resolve symbol'
    return
  }
  symbolDraft.value = symbol
  // Capture the drill-down ETF before loading the newly selected symbol. A stock
  // selection from a constituent list may itself have no holdings endpoint, but
  // its relevant ratio denominator is still the list's active ETF.
  const comparisonETF = workspaceStore.constituentETF
  workspaceStore.publishSymbol({ symbol, timestamp, group: 'blue', sourceWindowKey: 'workstation' })
  await loadSymbolData(symbol, comparisonETF, true)
}

async function loadSymbolData(symbol: string, comparisonETF = workspaceStore.constituentETF, updateRatio = true) {
  symbolDraft.value = symbol
  await Promise.all([
    chartStore.loadBars(symbol, chartStore.timeframe, chartStore.barType, true),
    workspaceStore.loadETFHoldings(symbol),
    workspaceStore.loadETFIndustries(symbol),
    workspaceStore.loadTechnical(symbol),
  ])
  if (updateRatio) updateAutoRatioExpression(symbol, comparisonETF)
}

function scheduleSymbolSearch(value: string) {
  if (suppressNextSearch) {
    suppressNextSearch = false
    return
  }
  if (searchTimer) clearTimeout(searchTimer)
  const query = value.trim()
  if (!query) {
    searchResults.value = []
    searchIndex.value = -1
    return
  }
  const requestId = ++searchRequest
  searchTimer = setTimeout(async () => {
    try {
      const results = await api.get<Array<{ symbol: string; name: string; exchange: string; type: string }>>('/instruments/search', { q: query })
      if (requestId !== searchRequest || symbolDraft.value.trim() !== query) return
      searchResults.value = results
      searchIndex.value = results.length ? 0 : -1
    } catch {
      if (requestId === searchRequest) {
        searchResults.value = []
        searchIndex.value = -1
      }
    }
  }, 120)
}

function selectSearchResult(symbol: string) {
  symbolDraft.value = symbol
  searchResults.value = []
  searchIndex.value = -1
  void selectSymbol(symbol)
}

function handleSymbolInputKeydown(event: KeyboardEvent) {
  if (event.key === 'ArrowDown' && searchResults.value.length) {
    event.preventDefault()
    searchIndex.value = (searchIndex.value + 1) % searchResults.value.length
  } else if (event.key === 'ArrowUp' && searchResults.value.length) {
    event.preventDefault()
    searchIndex.value = (searchIndex.value - 1 + searchResults.value.length) % searchResults.value.length
  } else if (event.key === 'Enter') {
    event.preventDefault()
    const result = searchResults.value[searchIndex.value]
    void selectSymbol(result?.symbol ?? symbolDraft.value)
  } else if (event.key === 'Escape') {
    searchResults.value = []
    searchIndex.value = -1
  }
}

function updateAutoRatioExpression(symbol: string, comparisonETF = workspaceStore.constituentETF) {
  const ratio = workspaceStore.activeTab?.windows.find(window => window.instance_key === 'ratio-chart')
  if (!ratio || (ratio.configuration.auto_ratio !== true && ratio.configuration.expression !== '=SPY/RSP')) return
  const sectorSymbols = (workspaceStore.marketGroups['sp500-sectors']?.members ?? []).map(member => member.instrument.symbol)
  updateToolConfiguration(ratio.instance_key, {
    ...ratio.configuration,
    expression: autoRatioExpression(symbol, sectorSymbols, comparisonETF),
    auto_ratio: true,
  })
}

function selectOccurrence(symbol: string, timestamp: string) {
  void selectSymbol(symbol, timestamp)
}

function setLinkedTimeframe(timeframe: string, group: LinkGroup = 'blue') {
  workspaceStore.publishTimeframe(timeframe, group, 'workstation')
}

async function signOut() {
  await authStore.logout()
}

async function selectIndustryProxy(symbol: string) {
  const normalized = await ensureKnownInstrumentSymbol(symbol, 'Industry ETF proxy')
  const comparisonETF = workspaceStore.constituentETF
  workspaceStore.selectIndustryProxy(normalized)
  symbolDraft.value = normalized
  // A proxy is a drill-down target, not a new taxonomy root. Publish it to the
  // linked charts and load its price/technicals while preserving the selected
  // sector/industry context. The watcher uses this marker to avoid replacing
  // the sector holdings tree with the proxy's own holdings.
  preserveDrilldownSymbol.value = normalized
  workspaceStore.publishSymbol({ symbol: normalized, group: 'blue', sourceWindowKey: 'workstation' })
  await Promise.all([
    chartStore.loadBars(normalized, chartStore.timeframe, chartStore.barType, true),
    workspaceStore.loadTechnical(normalized),
  ])
  updateAutoRatioExpression(normalized, comparisonETF)
}

function openTool(tool: OpenableToolDefinition) {
  workspaceStore.openTool(tool)
  toolLibraryOpen.value = false
}

function renameTab(stableKey: string, name: string) {
  workspaceStore.renameTab(stableKey, name)
}

function deleteTab(stableKey: string) {
  if (!window.confirm('Delete this personal layout?')) return
  workspaceStore.deleteTab(stableKey)
}

function dropTab(targetStableKey: string) {
  const source = dragTabKey.value
  dragTabKey.value = null
  if (source) workspaceStore.reorderTabs(source, targetStableKey)
}

function exportWorkspace() {
  const snapshot = workspaceStore.exportWorkspaceSnapshot()
  if (!snapshot) return
  const blob = new Blob([snapshot], { type: 'application/json' })
  const href = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = href
  anchor.download = `${(workspaceStore.workspace?.name ?? 'workspace').replace(/[^a-z0-9]+/gi, '-').toLowerCase()}.json`
  anchor.click()
  URL.revokeObjectURL(href)
}

async function importWorkspace(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  try {
    const payload = JSON.parse(await file.text()) as unknown
    if (workspaceStore.importWorkspaceSnapshot(payload)) workspaceMenuOpen.value = false
  } catch {
    workspaceStore.error = 'The workspace file is not valid JSON.'
  }
}

function openAlertsTool() {
  const alerts = OPENABLE_WORKSTATION_TOOLS.find(tool => tool.tool_type === 'alerts')
  if (alerts) openTool(alerts)
}

function updateLinkGroup(windowKey: string, group: LinkGroup) {
  workspaceStore.updateToolLinkGroup(windowKey, group)
}

function updateColumns(windowKey: string, columnKeys: string[]) {
  const windowState = workspaceStore.activeTab?.windows.find(window => window.instance_key === windowKey)
  if (!windowState) return
  windowState.configuration = { ...windowState.configuration, column_keys: columnKeys }
  workspaceStore.scheduleSnapshot()
}
function updateFilter(windowKey: string, filterText: string) {
  const windowState = workspaceStore.activeTab?.windows.find(window => window.instance_key === windowKey)
  if (!windowState) return
  windowState.configuration = { ...windowState.configuration, filter_text: filterText }
  workspaceStore.scheduleSnapshot()
}
function updateConditionFilter(windowKey: string, screenerId: number | null) {
  const windowState = workspaceStore.activeTab?.windows.find(window => window.instance_key === windowKey)
  if (!windowState) return
  windowState.configuration = { ...windowState.configuration, condition_screener_id: screenerId }
  workspaceStore.scheduleSnapshot()
}
function updateConditionFilterMode(windowKey: string, mode: 'active' | 'inactive' | 'off') {
  const windowState = workspaceStore.activeTab?.windows.find(window => window.instance_key === windowKey)
  if (!windowState) return
  windowState.configuration = { ...windowState.configuration, condition_filter_mode: mode }
  workspaceStore.scheduleSnapshot()
}
function updatePinnedBooleanKeys(windowKey: string, keys: string[]) {
  const windowState = workspaceStore.activeTab?.windows.find(window => window.instance_key === windowKey)
  if (!windowState) return
  windowState.configuration = { ...windowState.configuration, pinned_boolean_keys: keys }
  workspaceStore.scheduleSnapshot()
}
function updateColumnGroups(windowKey: string, groups: Record<string, string>) {
  const windowState = workspaceStore.activeTab?.windows.find(window => window.instance_key === windowKey)
  if (!windowState) return
  windowState.configuration = { ...windowState.configuration, column_groups: groups }
  workspaceStore.scheduleSnapshot()
}
function updateStackedColumnKeys(windowKey: string, keys: string[]) {
  const windowState = workspaceStore.activeTab?.windows.find(window => window.instance_key === windowKey)
  if (!windowState) return
  windowState.configuration = { ...windowState.configuration, stacked_column_keys: keys }
  workspaceStore.scheduleSnapshot()
}
function updateToolConfiguration(windowKey: string, configuration: Record<string, unknown>) {
  const windowState = workspaceStore.activeTab?.windows.find(window => window.instance_key === windowKey)
  if (!windowState) return
  // Golden Layout mounts virtual Vue tool components once. Preserve this reactive
  // configuration object so a template applies to the live tool immediately instead
  // of waiting for a dock remount or workspace reload.
  for (const key of Object.keys(windowState.configuration)) delete windowState.configuration[key]
  Object.assign(windowState.configuration, configuration)
  workspaceStore.scheduleSnapshot()
}

function reorderWatchlistItems(watchlistId: number, itemIds: number[]) {
  void watchlistStore.reorderItems(watchlistId, itemIds)
}

function compareSymbols(symbols: string[]) {
  const normalized = [...new Set(symbols.map(symbol => symbol.trim().toUpperCase()).filter(Boolean))]
  const active = activeSymbol.value.toUpperCase()
  const chart = workspaceStore.activeTab?.windows.find(window => window.tool_type === 'chart' && window.instance_key !== 'ratio-chart')
  if (!chart) {
    workspaceStore.error = 'Open a chart tool to compare selected symbols.'
    return
  }
  updateToolConfiguration(chart.instance_key, {
    ...chart.configuration,
    comparison_symbols: normalized.filter(symbol => symbol !== active).slice(0, 6),
  })
}

async function handleRowAction(action: 'chart' | 'compare' | 'note' | 'alert' | 'copy', row: { symbol: string; instrumentId: number | null }) {
  if (action === 'copy') {
    try {
      await navigator.clipboard?.writeText(row.symbol)
      workspaceStore.error = `Copied ${row.symbol}`
    } catch {
      workspaceStore.error = `Unable to copy ${row.symbol}`
    }
    return
  }
  if (action === 'compare') {
    compareSymbols([activeSymbol.value, row.symbol])
    return
  }
  await selectSymbol(row.symbol)
  if (action === 'chart') {
    const chart = OPENABLE_WORKSTATION_TOOLS.find(tool => tool.tool_type === 'chart')
    if (chart) openTool(chart)
    return
  }
  const toolType = action === 'note' ? 'notes' : action === 'alert' ? 'alerts' : action
  const tool = OPENABLE_WORKSTATION_TOOLS.find(candidate => candidate.tool_type === toolType)
  if (tool) openTool(tool)
}

function floatTool(windowKey: string) {
  const tab = workspaceStore.activeTabKey
  const href = router.resolve({ path: `/popout/${encodeURIComponent(windowKey)}`, query: { tab } }).href
  const popup = window.open(href, `workstation-${windowKey}`, 'popup=yes,width=1100,height=760,resizable=yes,scrollbars=no')
  if (!popup) workspaceStore.error = 'Browser blocked the pop-out. The tool remains docked.'
}

function renderDockTool(dockTool: { instance_key: string; title: string; tool_type: string }, actions: { toggleMaximize: () => void; close: () => void }): VNode {
  const tool = workspaceStore.activeTab?.windows.find(window => window.instance_key === dockTool.instance_key)
  if (!tool) return h('div', { class: 'workstation__missing-tool' }, `Missing persisted tool: ${dockTool.instance_key}`)
  return h(WorkstationToolContent, {
    tool,
    activeWindowKey: workspaceStore.activeTab?.active_window_key,
    factoryLayout: workspaceStore.activeTabKey,
    onSelect: (symbol: string) => void selectSymbol(symbol),
    onCompare: (symbols: string[]) => compareSymbols(symbols),
    onReorder: (watchlistId: number, itemIds: number[]) => reorderWatchlistItems(watchlistId, itemIds),
    onRowAction: (action: 'chart' | 'compare' | 'note' | 'alert' | 'copy', row: { symbol: string; instrumentId: number | null }) => void handleRowAction(action, row),
    onOccurrence: (symbol: string, timestamp: string) => void selectSymbol(symbol, timestamp),
    onSelectIndustry: (industry: string) => void workspaceStore.selectIndustry(workspaceStore.constituentETF ?? '', industry),
    onSelectProxy: (symbol: string) => void selectIndustryProxy(symbol),
    onColumns: (windowKey: string, keys: string[]) => updateColumns(windowKey, keys),
    onFilter: (windowKey: string, value: string) => updateFilter(windowKey, value),
    onConditionFilter: (windowKey: string, screenerId: number | null) => updateConditionFilter(windowKey, screenerId),
    onConditionFilterMode: (windowKey: string, mode: 'active' | 'inactive' | 'off') => updateConditionFilterMode(windowKey, mode),
    onPinnedBooleanKeys: (windowKey: string, keys: string[]) => updatePinnedBooleanKeys(windowKey, keys),
    onColumnGroups: (windowKey: string, groups: Record<string, string>) => updateColumnGroups(windowKey, groups),
    onStackedColumnKeys: (windowKey: string, keys: string[]) => updateStackedColumnKeys(windowKey, keys),
    onConfiguration: (windowKey: string, configuration: Record<string, unknown>) => updateToolConfiguration(windowKey, configuration),
    onTimeframe: (timeframe: string, group: LinkGroup) => setLinkedTimeframe(timeframe, group),
    onFloat: (windowKey: string) => floatTool(windowKey),
    onMaximize: () => actions.toggleMaximize(),
    onClose: () => {
      if (workspaceStore.closeTool(dockTool.instance_key)) actions.close()
    },
    onUpdateLinkGroup: (windowKey: string, group: LinkGroup) => updateLinkGroup(windowKey, group),
  })
}

function closePopoutTool(windowKey: string) {
  const tab = workspaceStore.activeTab
  if (!tab?.windows.some(window => window.instance_key === windowKey)) return
  // A browser pop-out is a second view of the persisted docked tool. Closing it must
  // restore the source layout, never delete the tool and its serializable state.
  window.close()
}

function persistGoldenLayout(layout: Record<string, unknown>, visibleToolKeys: string[]) {
  workspaceStore.applyActiveLayout(layout, visibleToolKeys)
}

async function resetFactoryWorkspace() {
  if (!window.confirm('Reset this factory workspace? Your current layout changes will be replaced.')) return
  await workspaceStore.resetFactoryWorkspace()
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
  if (!symbol) return
  // Selections made by linked watchlists, pop-outs, or another browser window
  // publish through the workspace bus rather than through the shell input.
  // Keep the active-symbol entry authoritative for those paths too, while
  // suppressing the search request that is only intended for user typing.
  suppressNextSearch = true
  symbolDraft.value = symbol
  const preserveDrilldown = preserveDrilldownSymbol.value === symbol
  if (preserveDrilldown) preserveDrilldownSymbol.value = null
  if (chartStore.symbol === symbol) return
  void Promise.all([
    chartStore.loadBars(symbol, chartStore.timeframe, chartStore.barType, true),
    ...(preserveDrilldown ? [] : [workspaceStore.loadETFHoldings(symbol), workspaceStore.loadETFIndustries(symbol)]),
    workspaceStore.loadTechnical(symbol),
  ])
})
watch(symbolDraft, scheduleSymbolSearch)
watch(() => workspaceStore.linkedTimeframe, timeframe => {
  if (timeframe === chartStore.timeframe) return
  void chartStore.loadBars(activeSymbol.value, timeframe as typeof chartStore.timeframe, chartStore.barType, true)
})

onMounted(async () => {
  const handleVisibilityChange = () => {
    documentVisible.value = document.visibilityState === 'visible'
    if (documentVisible.value && !isPopout.value) void marketAnalysisQuery.refetch()
  }
  document.addEventListener('visibilitychange', handleVisibilityChange)
  removeVisibilityListener = () => document.removeEventListener('visibilitychange', handleVisibilityChange)
  workspaceStore.connect()
  await workspaceStore.loadDefault()
  const requestedTab = typeof route.query.tab === 'string' ? route.query.tab : null
  if (requestedTab && workspaceStore.workspace?.tabs.some(tab => tab.stable_key === requestedTab)) {
    workspaceStore.activeTabKey = requestedTab
  }
  await refreshMarketData()
  if (isPopout.value && popoutTool.value) {
    const tool = popoutTool.value
    const configuredSymbol = typeof tool.configuration.symbol === 'string' ? tool.configuration.symbol : null
    const linked = workspaceStore.symbolForLinkGroup(tool.link_group, configuredSymbol)
    await loadSymbolData(linked, workspaceStore.constituentETF, false)
  } else {
    const requested = String(route.params.symbol ?? route.query.symbol ?? 'SPY')
    await selectSymbol(requested)
  }
  await nextTick()
  if (!isPopout.value) await refreshMarketData()

})

onBeforeUnmount(() => {
  removeVisibilityListener?.()
  removeVisibilityListener = null
  if (searchTimer) clearTimeout(searchTimer)
  workspaceStore.disconnect()
})
</script>

<style scoped>
.workstation { width: 100%; height: 100%; min-width: 980px; display: grid; grid-template-rows: var(--tc-toolbar-height) var(--tc-tab-height) minmax(0, 1fr) var(--tc-status-height); overflow: hidden; color: var(--tc-text); background: var(--tc-shell-bg); font-family: var(--tc-font-family); }
.workstation:has(.workstation__popout) { min-width: 320px; grid-template-rows: minmax(0, 1fr); }
.workstation__popout { min-width: 0; min-height: 0; padding: 2px; background: #090c0f; }
.workstation__menu { display: flex; align-items: center; gap: 12px; padding: 0 7px; background: linear-gradient(var(--tc-header-top), var(--tc-header-bottom)); border-bottom: 1px solid #090b0d; }
.workstation__brand { color: var(--tc-accent-soft); font-size: 10px; font-weight: 700; letter-spacing: .06em; white-space: nowrap; }
.workstation__menu nav { display: flex; align-self: stretch; }
.workstation__workspace-menu { position: relative; display: flex; align-items: stretch; }
.workstation__workspace-popover { position: absolute; z-index: 150; top: calc(100% + 1px); left: 0; width: 292px; padding: 5px; border: 1px solid #4d5a63; background: #151d23; box-shadow: 0 7px 18px #000b; color: #cbd6dc; }
.workstation__workspace-popover header { display: flex; justify-content: space-between; align-items: baseline; padding: 3px 4px 5px; border-bottom: 1px solid #29343b; font-size: 11px; }.workstation__workspace-popover header small { color: #81909a; font-size: 9px; }
.workstation__workspace-actions { display: flex; gap: 3px; padding: 5px 2px; border-bottom: 1px solid #29343b; }.workstation__workspace-actions button,.workstation__layout-reset { border: 1px solid #42505a; background: #202b32; color: #cbd6dc; padding: 3px 6px; font: 10px "Segoe UI",Arial,sans-serif; cursor: pointer; }.workstation__workspace-actions button:hover,.workstation__layout-reset:hover { background: #31424d; color: #fff; }.workstation__workspace-file { display: none; }
.workstation__layout-list { display: grid; gap: 2px; max-height: 250px; overflow: auto; padding: 4px 0; }.workstation__layout-item { display: grid; grid-template-columns: minmax(72px, 1fr) 112px 20px; gap: 3px; align-items: center; padding: 2px; border: 1px solid transparent; }.workstation__layout-item:hover { border-color: #3e505c; }.workstation__layout-select { overflow: hidden; border: 0; background: transparent; color: #aebbc4; text-align: left; text-overflow: ellipsis; white-space: nowrap; cursor: pointer; font: 10px "Segoe UI",Arial,sans-serif; }.workstation__layout-select.active { color: #eaf2f6; font-weight: 700; }.workstation__layout-item input { min-width: 0; border: 1px solid #3b4850; background: #11161a; color: #bfcbd3; padding: 2px 3px; font: 10px "Segoe UI",Arial,sans-serif; }.workstation__layout-delete { border: 0; background: transparent; color: #d78989; cursor: pointer; }.workstation__layout-delete:disabled { color: #5e686e; cursor: not-allowed; }.workstation__layout-reset { width: 100%; margin-top: 2px; }
.workstation__menu nav button, .workstation__tab-add, .workstation__tab-reset { border: 0; background: transparent; color: #d4d9dd; padding: 0 8px; font: 11px "Segoe UI", Arial, sans-serif; cursor: pointer; }
.workstation__menu nav button:hover, .workstation__tab-add:hover, .workstation__tab-reset:hover { background: #3a444d; color: #fff; }
.workstation__search { position: relative; display: flex; height: 21px; margin-left: 10px; }
.workstation__search input { width: 88px; padding: 0 5px; border: 1px solid #4d5a63; background: #11161a; color: #f1f5f7; font: 11px "Segoe UI", Arial, sans-serif; text-transform: uppercase; }
.workstation__search button { border: 1px solid #4d5a63; border-left: 0; background: #26333d; color: #dce9f2; padding: 0 7px; font-size: 10px; cursor: pointer; }
.workstation__symbol-results { position: absolute; z-index: 130; top: 23px; left: 0; display: grid; min-width: 270px; max-height: 250px; overflow: auto; border: 1px solid #4d5a63; background: #151d23; box-shadow: 0 6px 16px #000b; }
.workstation__symbol-results button { display: grid; grid-template-columns: 55px minmax(0, 1fr) 48px; gap: 6px; align-items: center; min-height: 25px; padding: 3px 6px; border: 0; border-bottom: 1px solid #29343b; background: transparent; color: #bfcbd3; font: 10px "Segoe UI", Arial, sans-serif; text-align: left; }
.workstation__symbol-results button:hover, .workstation__symbol-results button[aria-selected="true"] { background: #2c4554; color: #fff; }
.workstation__symbol-results strong { color: #e4f1f7; }.workstation__symbol-results span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }.workstation__symbol-results small { color: #8799a5; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.workstation__status { margin-left: auto; display: flex; align-items: center; gap: 8px; color: #81909a; font-size: 10px; }
.workstation__refresh,.workstation__sign-out { border: 1px solid #47545d; background: #20282e; color: #bdc9d1; padding: 2px 6px; font: inherit; cursor: pointer; }
.workstation__refresh:disabled { cursor: wait; opacity: .65; }
.workstation__refresh:hover:not(:disabled),
.workstation__sign-out:hover { border-color: #6d8290; color: #fff; background: #33414a; }
.workstation__leader { color: #63bd85; }
.workstation__data-state--fetching { color:#80bce8; }.workstation__data-state--unavailable { color:#ed9696; }.workstation__data-state--cached { color:#aebbc4; }
.workstation__tabs { display: flex; align-items: stretch; background: var(--tc-panel-bg); border-bottom: 1px solid var(--tc-border); }
.workstation__tool-library { position: relative; display: flex; }
.workstation__tool-library-menu { position: absolute; z-index: 60; top: 28px; left: 0; display: grid; min-width: 118px; padding: 2px; border: 1px solid #42505a; background: #1b2228; box-shadow: 0 3px 10px #000a; }
.workstation__tool-library-menu button { border: 0; background: transparent; color: #cbd6dc; padding: 5px 8px; font: 11px "Segoe UI", Arial, sans-serif; text-align: left; cursor: pointer; }
.workstation__tool-library-menu button:hover { background: #31424d; color: #fff; }
.workstation__tabs > button:not(.workstation__tab-add) { min-width: 112px; padding: 0 11px; border: 0; border-right: 1px solid #303940; background: #1b2126; color: #9facb5; font: 11px "Segoe UI", Arial, sans-serif; cursor: pointer; }
.workstation__tabs > button.workstation__tab--active { background: #28333b; color: #eaf2f6; box-shadow: inset 0 2px #68b6e9; }
.workstation__workspace-name { margin-left: auto; padding: 7px 9px; color: #697782; font-size: 10px; }
.workstation__layout-state { display: grid; min-height: 0; place-content: center; gap: 9px; padding: 20px; background: #090c0f; color: #9baab4; font: 12px "Segoe UI", Arial, sans-serif; text-align: center; }
.workstation__layout-state button { justify-self: center; border: 1px solid #43525d; background: #1a242c; color: #c5d8e4; cursor: pointer; font: inherit; padding: 4px 10px; }
.workstation__chart { height: 100%; min-height: 0; position: relative; background: #101419; }
.workstation__chart-state { display: grid; height: 100%; place-items: center; color: #98a7b2; font-size: 12px; }
.workstation__chart-state--error { color: #ec8f8f; }
.workstation__analysis { display: grid; gap: 8px; padding: 10px; color: #aebbc4; font-size: 11px; }
.workstation__analysis strong { color: #71c3f5; font-size: 14px; }
.workstation__analysis p { color: #84929c; line-height: 1.45; }
.workstation__metrics { display: grid; grid-template-columns: 1fr auto; gap: 5px 10px; padding: 9px; color: #99a8b1; font-size: 10px; }
.workstation__metrics b { color: #d2dce3; font-weight: 500; text-align: right; }
.workstation__footer { display: flex; gap: 16px; align-items: center; padding: 0 7px; border-top: 1px solid var(--tc-border); color: var(--tc-text-muted); background: var(--tc-panel-bg); font-size: 10px; }
.workstation__footer span:first-child { color: #d4e7f4; font-weight: 700; }
</style>
