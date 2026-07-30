<template>
  <div class="workstation" @keydown="handleKeydown">
    <header v-if="!isPopout" class="workstation__menu">
      <div class="workstation__brand">CHARTING WORKSTATION</div>
      <nav aria-label="Application menu">
        <button type="button" title="Clone active workspace layout" @click="workspaceStore.cloneActiveTab()">Workspace</button>
        <button type="button" title="Open Study Lab layout" @click="workspaceStore.activeTabKey = 'study-lab'">Study</button>
        <button v-if="workspaceStore.workspace?.is_default" type="button" title="Reset factory workspace" @click="resetFactoryWorkspace">Reset</button>
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
      <label class="workstation__timeframe">TF
        <select :value="workspaceStore.linkedTimeframe" aria-label="Linked timeframe" @change="setLinkedTimeframe(($event.target as HTMLSelectElement).value)">
          <option value="M15">15 minute</option><option value="D1">Daily</option><option value="W1">Weekly</option><option value="MN">Monthly</option>
        </select>
      </label>
      <div class="workstation__status">
        <span :class="{ 'workstation__leader': workspaceStore.isPersistenceLeader }">●</span>
        {{ workspaceStore.isPersistenceLeader ? 'Leader' : 'Shared' }}
        <span :class="`workstation__data-state--${dataState.kind}`">{{ dataState.label }}</span>
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
        @select="selectSymbol"
        @occurrence="selectOccurrence"
        @select-industry="workspaceStore.selectIndustry(workspaceStore.constituentETF ?? '', $event)"
        @columns="updateColumns"
        @filter="updateFilter"
        @condition-filter="updateConditionFilter"
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
import WorkspaceLayoutHost from '@/components/workstation/WorkspaceLayoutHost.vue'
import WorkstationToolContent from '@/components/workstation/WorkstationToolContent.vue'
import { useChartStore } from '@/stores/chart'
import { useAuthStore } from '@/stores/auth'
import { OPENABLE_WORKSTATION_TOOLS, useWorkspaceStore, type LinkGroup, type OpenableToolDefinition } from '@/stores/workspace'
import type { LayoutConfig } from 'golden-layout'
import { ensureKnownInstrumentSymbol } from '@/lib/instruments'

const route = useRoute()
const router = useRouter()
const chartStore = useChartStore()
const authStore = useAuthStore()
const workspaceStore = useWorkspaceStore()
const symbolInput = ref<HTMLInputElement | null>(null)
const symbolDraft = ref('')
const toolLibraryOpen = ref(false)
const preserveDrilldownSymbol = ref<string | null>(null)
const openableTools = OPENABLE_WORKSTATION_TOOLS

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
  let symbol: string
  try {
    symbol = await ensureKnownInstrumentSymbol(requested, 'Workstation symbol')
  } catch (cause: any) {
    workspaceStore.error = cause?.message ?? 'Unable to resolve symbol'
    return
  }
  symbolDraft.value = symbol
  workspaceStore.publishSymbol({ symbol, timestamp, group: 'blue', sourceWindowKey: 'workstation' })
  await Promise.all([
    chartStore.loadBars(symbol, chartStore.timeframe, chartStore.barType, true),
    workspaceStore.loadETFHoldings(symbol),
    workspaceStore.loadETFIndustries(symbol),
    workspaceStore.loadTechnical(symbol),
  ])
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
  workspaceStore.selectIndustryProxy(symbol)
  symbolDraft.value = symbol
  preserveDrilldownSymbol.value = symbol
}

function openTool(tool: OpenableToolDefinition) {
  workspaceStore.openTool(tool)
  toolLibraryOpen.value = false
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
    onSelect: (symbol: string) => void selectSymbol(symbol),
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
  const preserveDrilldown = preserveDrilldownSymbol.value === symbol
  if (preserveDrilldown) preserveDrilldownSymbol.value = null
  if (chartStore.symbol === symbol) return
  void Promise.all([
    chartStore.loadBars(symbol, chartStore.timeframe, chartStore.barType, true),
    ...(preserveDrilldown ? [] : [workspaceStore.loadETFHoldings(symbol), workspaceStore.loadETFIndustries(symbol)]),
    workspaceStore.loadTechnical(symbol),
  ])
})
watch(() => workspaceStore.linkedTimeframe, timeframe => {
  if (timeframe === chartStore.timeframe) return
  void chartStore.loadBars(activeSymbol.value, timeframe as typeof chartStore.timeframe, chartStore.barType, true)
})

onMounted(async () => {
  workspaceStore.connect()
  await workspaceStore.loadDefault()
  const requestedTab = typeof route.query.tab === 'string' ? route.query.tab : null
  if (requestedTab && workspaceStore.workspace?.tabs.some(tab => tab.stable_key === requestedTab)) {
    workspaceStore.activeTabKey = requestedTab
  }
  await Promise.all([
    workspaceStore.loadMarketGroup('us-benchmarks'),
    workspaceStore.loadMarketGroup('sp500-sectors'),
    workspaceStore.loadGroupSnapshot('sp500-sectors', 'SPY'),
    workspaceStore.loadBreadth('sp500-sectors'),
    workspaceStore.loadBreadthHistory('sp500-sectors'),
  ])
  const requested = String(route.params.symbol ?? route.query.symbol ?? 'SPY')
  await selectSymbol(requested)
  await nextTick()
})

onBeforeUnmount(() => workspaceStore.disconnect())
</script>

<style scoped>
.workstation { --tc-border: #303940; --tc-window: #15191e; width: 100%; height: 100%; min-width: 980px; display: grid; grid-template-rows: 29px 28px minmax(0, 1fr) 21px; overflow: hidden; color: #d5dde4; background: #0d1013; font-family: "Segoe UI", Arial, sans-serif; }
.workstation:has(.workstation__popout) { min-width: 320px; grid-template-rows: minmax(0, 1fr); }
.workstation__popout { min-width: 0; min-height: 0; padding: 2px; background: #090c0f; }
.workstation__menu { display: flex; align-items: center; gap: 12px; padding: 0 7px; background: linear-gradient(#2c3339, #1c2227); border-bottom: 1px solid #090b0d; }
.workstation__brand { color: #8fc7ea; font-size: 10px; font-weight: 700; letter-spacing: .06em; white-space: nowrap; }
.workstation__menu nav { display: flex; align-self: stretch; }
.workstation__menu nav button, .workstation__tab-add, .workstation__tab-reset { border: 0; background: transparent; color: #d4d9dd; padding: 0 8px; font: 11px "Segoe UI", Arial, sans-serif; cursor: pointer; }
.workstation__menu nav button:hover, .workstation__tab-add:hover, .workstation__tab-reset:hover { background: #3a444d; color: #fff; }
.workstation__search { display: flex; height: 21px; margin-left: 10px; }
.workstation__search input { width: 88px; padding: 0 5px; border: 1px solid #4d5a63; background: #11161a; color: #f1f5f7; font: 11px "Segoe UI", Arial, sans-serif; text-transform: uppercase; }
.workstation__search button { border: 1px solid #4d5a63; border-left: 0; background: #26333d; color: #dce9f2; padding: 0 7px; font-size: 10px; cursor: pointer; }
.workstation__status { margin-left: auto; display: flex; align-items: center; gap: 8px; color: #81909a; font-size: 10px; }
.workstation__sign-out { border: 1px solid #47545d; background: #20282e; color: #bdc9d1; padding: 2px 6px; font: inherit; cursor: pointer; }
.workstation__sign-out:hover { border-color: #6d8290; color: #fff; background: #33414a; }
.workstation__leader { color: #63bd85; }
.workstation__data-state--fetching { color:#80bce8; }.workstation__data-state--unavailable { color:#ed9696; }.workstation__data-state--cached { color:#aebbc4; }
.workstation__tabs { display: flex; align-items: stretch; background: #151a1f; border-bottom: 1px solid #303940; }
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
.workstation__footer { display: flex; gap: 16px; align-items: center; padding: 0 7px; border-top: 1px solid #2f3941; color: #84939d; background: #151a1f; font-size: 10px; }
.workstation__footer span:first-child { color: #d4e7f4; font-weight: 700; }
</style>
