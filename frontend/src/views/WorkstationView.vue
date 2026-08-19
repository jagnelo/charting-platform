<template>
  <div class="workstation" tabindex="0" @keydown.capture="handleGlobalKeydownCapture" @keydown="handleKeydown" @wheel.capture="handleWheel" @pointerdown.capture="handleWorkstationPointerDown" @focusin.capture="handleWorkstationFocusIn" @change.capture="handleWorkstationChange">
    <header v-if="!isPopout" class="workstation__menu">
      <div class="workstation__brand">CHARTING WORKSTATION</div>
      <nav aria-label="Application menu">
        <div class="workstation__workspace-menu">
          <button ref="workspaceMenuTrigger" type="button" title="Manage workspace layouts" aria-haspopup="menu" :aria-expanded="workspaceMenuOpen" @click="toggleWorkspaceMenu" @keydown="handleShellTriggerKeydown('workspace', $event)">Workspace</button>
          <div v-if="workspaceMenuOpen" ref="workspaceMenuRoot" class="workstation__workspace-popover" role="menu" tabindex="-1" aria-label="Workspace layouts" :style="workspaceMenuStyle" @click.stop @keydown="handleShellMenuKeydown('workspace', $event)">
            <header><strong>Workspaces</strong><small>{{ workspaceStore.workspace?.name ?? 'Workspace' }}</small></header>
            <div class="workstation__workspace-list" role="listbox" aria-label="Saved workspaces" tabindex="0" :aria-activedescendant="workspaceStore.workspaces[workspaceOptionIndex] ? `saved-workspace-${workspaceStore.workspaces[workspaceOptionIndex].id}` : undefined" @keydown.stop="handleWorkspaceListKeydown" @focus="syncWorkspaceOptionIndex">
              <span v-if="!workspaceStore.workspaces.length" role="status">Loading workspaces…</span>
              <button v-for="(item, index) in workspaceStore.workspaces" :id="`saved-workspace-${item.id}`" :key="item.id" type="button" role="option" tabindex="-1" :aria-selected="item.id === workspaceStore.workspace?.id" @click="switchWorkspaceFromMenu(item.id)">{{ item.name }}<small v-if="item.is_default">Default</small></button>
            </div>
            <div class="workstation__workspace-actions">
              <button type="button" role="menuitem" tabindex="-1" @click="createWorkspace(); closeShellMenuToTrigger('workspace')">New</button>
              <button type="button" role="menuitem" tabindex="-1" @click="workspaceStore.cloneActiveTab(); closeShellMenuToTrigger('workspace')">Clone</button>
              <button type="button" role="menuitem" tabindex="-1" @click="cloneWorkspace(); closeShellMenuToTrigger('workspace')">Clone workspace</button>
              <button type="button" role="menuitem" tabindex="-1" @click="renameWorkspace(); closeShellMenuToTrigger('workspace')">Rename</button>
              <button type="button" role="menuitem" tabindex="-1" :disabled="workspaceStore.workspace?.is_default" @click="deleteWorkspace(); closeShellMenuToTrigger('workspace')">Delete</button>
              <button type="button" role="menuitem" tabindex="-1" @click="exportWorkspace">Export</button>
              <button type="button" role="menuitem" tabindex="-1" @click="workspaceFileInput?.click()">Import</button>
              <input ref="workspaceFileInput" class="workstation__workspace-file" type="file" accept="application/json,.json" @change="importWorkspace" />
            </div>
            <div class="workstation__layout-list">
              <div v-for="tab in workspaceStore.workspace?.tabs ?? []" :key="tab.stable_key" class="workstation__layout-item" draggable="true" @dragstart="dragTabKey = tab.stable_key" @dragover.prevent @drop.prevent="dropTab(tab.stable_key)" @dragend="dragTabKey = null">
                <button type="button" role="menuitem" tabindex="-1" class="workstation__layout-select" :class="{ active: tab.stable_key === workspaceStore.activeTabKey }" @click="selectWorkspaceTab(tab.stable_key); closeShellMenuToTrigger('workspace')">{{ tab.name }}</button>
                <input :aria-label="`Rename ${tab.name}`" :value="tab.name" @change="renameTab(tab.stable_key, ($event.target as HTMLInputElement).value)" />
                <button type="button" class="workstation__layout-delete" :disabled="(workspaceStore.workspace?.tabs.length ?? 0) <= 1" :aria-label="`Delete ${tab.name}`" @click="deleteTab(tab.stable_key)"><WorkstationGlyph kind="delete" /></button>
              </div>
            </div>
            <button v-if="workspaceStore.workspace?.settings.factory_id === 'us-top-down'" type="button" role="menuitem" tabindex="-1" class="workstation__layout-reset" @click="resetFactoryWorkspace(); closeShellMenuToTrigger('workspace')">Reset factory layout</button>
          </div>
        </div>
        <button type="button" title="Open Study Lab layout" @click="openStudyLab">Study</button>
        <button type="button" title="Open active-symbol alerts" @click="openAlertsTool">Alerts</button>
        <div class="workstation__help-menu">
          <button ref="keyboardHelpTrigger" type="button" title="Keyboard shortcuts" aria-haspopup="menu" :aria-expanded="keyboardHelpOpen" @click="toggleKeyboardHelp" @keydown="handleShellTriggerKeydown('help', $event)">Help</button>
          <div v-if="keyboardHelpOpen" ref="keyboardHelpMenuRoot" class="workstation__help-popover" role="menu" aria-label="Keyboard shortcuts" :style="keyboardHelpMenuStyle" @click.stop @keydown="handleShellMenuKeydown('help', $event)">
            <header><strong>Keyboard shortcuts</strong><button type="button" role="menuitem" tabindex="-1" aria-label="Close keyboard shortcuts" @click="closeShellMenuToTrigger('help')"><WorkstationGlyph kind="close" /></button></header>
            <dl>
              <div><dt>Type</dt><dd>Open symbol search</dd></div>
              <div><dt>Space</dt><dd>Next symbol in the focused list</dd></div>
              <div><dt>Shift+Space</dt><dd>Previous symbol in the focused list</dd></div>
              <div><dt>Ctrl+wheel</dt><dd>Traverse the active symbol universe</dd></div>
              <div><dt>F1 or ?</dt><dd>Show this help</dd></div>
              <div><dt>Escape</dt><dd>Close search and menus</dd></div>
            </dl>
            <small>Shortcuts are inactive while a text, numeric, code, or search editor owns focus.</small>
          </div>
        </div>
        <button v-if="workspaceStore.workspace?.is_default" type="button" title="Reset factory workspace" @click="resetFactoryWorkspace">Reset</button>
      </nav>
      <div class="workstation__search" @pointerdown.stop>
        <input
          ref="symbolInput"
          v-model="symbolDraft"
          aria-label="Active symbol"
          placeholder="Symbol"
          autocomplete="off"
          role="combobox"
          aria-autocomplete="list"
          :aria-expanded="searchPanelVisible"
          aria-controls="workstation-symbol-results"
          :aria-activedescendant="searchIndex >= 0 ? `workstation-symbol-option-${searchIndex}` : undefined"
          :aria-busy="searchLoading ? 'true' : 'false'"
          aria-describedby="workstation-symbol-search-state"
          @input="handleSymbolInput"
          @blur="closeSymbolSearch"
          @keydown.stop="handleSymbolInputKeydown"
        />
        <button type="button" @click="recentSymbolsOpen = false; closeSymbolSearch(); selectSymbol(symbolDraft)">Go</button>
        <button
          type="button"
          class="workstation__history-button"
          aria-label="Recent symbols"
          aria-haspopup="menu"
          :aria-expanded="recentSymbolsOpen"
          :disabled="!recentStore.recent.length"
          ref="recentSymbolsTrigger"
          @click.stop="toggleRecentSymbols"
          @keydown="handleShellTriggerKeydown('recent', $event)"
        ><WorkstationGlyph kind="chevron-down" /></button>
        <div v-if="recentSymbolsOpen && recentStore.recent.length" ref="recentSymbolsMenuRoot" class="workstation__recent-symbols" role="menu" aria-label="Recent symbols" :style="recentSymbolsMenuStyle" @click.stop @keydown="handleShellMenuKeydown('recent', $event)">
          <header><strong>Recent symbols</strong><button type="button" role="menuitem" tabindex="-1" aria-label="Clear recent symbols" @click="recentStore.clear()">Clear</button></header>
          <button v-for="item in recentStore.recent" :key="item.symbol" type="button" role="menuitem" tabindex="-1" @click="selectRecentSymbol(item.symbol)">
            <strong>{{ item.symbol }}</strong><span>{{ item.name || 'Viewed instrument' }}</span>
          </button>
        </div>
        <div v-if="searchPanelVisible" id="workstation-symbol-results" class="workstation__symbol-results" role="listbox" aria-label="Symbol search results" :aria-busy="searchLoading ? 'true' : 'false'">
          <button
            v-for="(result, index) in searchResults"
            :key="`${result.symbol}:${result.exchange}`"
            :id="`workstation-symbol-option-${index}`"
            type="button"
            role="option"
            :aria-selected="index === searchIndex"
            @mousedown.prevent="selectSearchResult(result.symbol, result.instrument_id)"
          ><strong>{{ result.symbol }}</strong><span>{{ result.name }}</span><small>{{ result.exchange || result.type }}</small></button>
          <div v-if="searchLoading" class="workstation__symbol-search-message" role="status">Searching canonical instruments…</div>
          <div v-else-if="searchError" class="workstation__symbol-search-message workstation__symbol-search-message--error" role="alert">{{ searchError }}</div>
          <div v-else-if="searchSettled && !searchResults.length" class="workstation__symbol-search-message" role="status">No canonical instruments found for “{{ symbolDraft.trim().toUpperCase() }}”.</div>
        </div>
        <span id="workstation-symbol-search-state" class="workstation__symbol-search-state" role="status" aria-live="polite" aria-atomic="true">{{ searchStateText }}</span>
      </div>
      <label class="workstation__timeframe">TF
        <select :value="workspaceStore.linkedTimeframe" aria-label="Linked timeframe" @change="setLinkedTimeframe(($event.target as HTMLSelectElement).value)">
          <option value="M1">1 minute</option><option value="M5">5 minutes</option><option value="M15">15 minutes</option><option value="M30">30 minutes</option><option value="H1">1 hour</option><option value="H2">2 hours</option><option value="H4">4 hours</option><option value="H12">12 hours</option><option value="D1">Daily</option><option value="W1">Weekly</option><option value="MN">Monthly</option>
        </select>
      </label>
      <div class="workstation__status">
        <span :class="{ 'workstation__leader': workspaceStore.isPersistenceLeader }">●</span>
        {{ workspaceStore.isPersistenceLeader ? 'Leader' : 'Shared' }}
        <span class="workstation__data-state" role="status" aria-live="polite" aria-atomic="true" :aria-label="`Market data freshness: ${dataState.label}`" :class="`workstation__data-state--${dataState.kind}`">{{ dataState.label }}</span>
        <button type="button" class="workstation__refresh" :disabled="workspaceStore.marketAnalysisRefreshing" title="Refresh top-down analysis" @click="refreshMarketData">{{ workspaceStore.marketAnalysisRefreshing ? 'Refreshing…' : 'Refresh' }}</button>
        <button type="button" class="workstation__sign-out logout-btn" title="Sign out" @click="signOut">Sign out</button>
      </div>
    </header>

    <div v-if="!isPopout" class="workstation__tabs" role="tablist" aria-label="Workspace layouts">
      <button
        v-for="tab in workspaceStore.workspace?.tabs ?? []"
        :key="tab.stable_key"
        type="button"
        role="tab"
        :data-tab-key="tab.stable_key"
        :aria-selected="tab.stable_key === workspaceStore.activeTabKey ? 'true' : 'false'"
        :tabindex="tab.stable_key === workspaceStore.activeTabKey ? 0 : -1"
        :aria-grabbed="dragTabKey === tab.stable_key ? 'true' : 'false'"
        :class="{ 'workstation__tab--active': tab.stable_key === workspaceStore.activeTabKey, 'workstation__tab--drag-over': tabDragOverKey === tab.stable_key && dragTabKey !== tab.stable_key }"
        @pointerdown="beginTabPointerDrag(tab.stable_key, $event)"
        @pointerenter="tabDragOverKey = dragTabKey ? tab.stable_key : tabDragOverKey"
        @pointermove="tabDragOverKey = dragTabKey ? tab.stable_key : tabDragOverKey"
        @pointerup="dropTab(tab.stable_key)"
        @mousedown="beginTabMouseDrag(tab.stable_key, $event)"
        @mouseenter="tabDragOverKey = dragTabKey ? tab.stable_key : tabDragOverKey"
        @mouseup="dropTab(tab.stable_key)"
        @click="selectWorkspaceTab(tab.stable_key)"
        @keydown="handleWorkspaceTabKeydown(tab.stable_key, $event)"
      >{{ tab.name }}</button>
      <button type="button" class="workstation__tab-add" title="Clone active layout" @click="workspaceStore.cloneActiveTab()">+</button>
      <div class="workstation__tool-library">
        <button ref="toolLibraryTrigger" type="button" class="workstation__tab-add" title="Open a workstation tool" aria-haspopup="menu" :aria-expanded="toolLibraryOpen" @click="toggleToolLibrary" @keydown="handleShellTriggerKeydown('tool-library', $event)">Add tool</button>
        <div v-if="toolLibraryOpen" ref="toolLibraryMenuRoot" class="workstation__tool-library-menu" role="menu" aria-label="Workstation tools" :style="toolLibraryMenuStyle" @keydown="handleShellMenuKeydown('tool-library', $event)">
          <button v-for="tool in openableTools" :key="tool.instance_prefix" type="button" role="menuitem" tabindex="-1" @click="openTool(tool)">{{ tool.title }}</button>
        </div>
      </div>
      <button v-if="workspaceStore.workspace?.settings.factory_id === 'us-top-down'" type="button" class="workstation__tab-reset" title="Reset factory workspace" @click="resetFactoryWorkspace"><WorkstationGlyph kind="reset" /></button>
      <span class="workstation__workspace-name">{{ workspaceStore.workspace?.name ?? 'Loading workspace…' }}</span>
    </div>

    <WorkspaceLayoutHost
      v-if="!isPopout && goldenLayoutConfig && !workspaceReplacementPending"
      class="workstation__dock"
      :layout="goldenLayoutConfig"
      :active-window-key="workspaceStore.activeTab?.active_window_key"
      :reload-key="workspaceReloadKey"
      :render-tool="renderDockTool"
      @changed="persistGoldenLayout"
      @active-window-changed="workspaceStore.setActiveWindow"
    />
    <main v-else-if="!isPopout && workspaceReplacementPending" class="workstation__layout-state" role="status">
      Reloading workspace…
    </main>
    <main v-if="isPopout" class="workstation__popout">
      <WorkstationToolContent
        v-if="popoutTool"
        :tool="popoutTool"
        :active-window-key="popoutTool.instance_key"
        :factory-layout="workspaceStore.activeTabKey"
        @select="(symbol, instrumentId) => selectSymbol(symbol, undefined, false, instrumentId)"
        @compare="compareSymbols"
        @ratio="openMarketMapRatio"
        @reorder="reorderWatchlistItems"
        @row-action="handleRowAction"
        @market-map="openMarketMap"
        @occurrence="selectOccurrence"
        @select-industry="selectIndustryForContext"
        @select-proxy="selectIndustryProxy"
        @columns="updateColumns"
        @filter="updateFilter"
        @condition-filter="updateConditionFilter"
        @condition-filter-mode="updateConditionFilterMode"
        @pinned-boolean-keys="updatePinnedBooleanKeys"
        @column-groups="updateColumnGroups"
        @stacked-column-keys="updateStackedColumnKeys"
        @configuration="updateToolConfiguration"
        @publish-analysis="publishMapAnalysis"
        @update-link-group="updateLinkGroup"
        @timeframe="setLinkedTimeframe"
        @close="closePopoutTool"
      />
      <div v-else class="workstation__missing-tool">The requested tool is unavailable. It remains in the source workspace.</div>
    </main>
    <main v-else-if="!isPopout && !goldenLayoutConfig" class="workstation__layout-state" role="status">
      <span v-if="workspaceStore.loading">Loading saved workstation…</span>
      <template v-else>
        <span>Unable to load a serializable workstation layout.</span>
        <button type="button" @click="workspaceStore.loadDefault()">Retry</button>
      </template>
    </main>

    <footer v-if="!isPopout" class="workstation__footer">
      <span>{{ activeSymbol }}</span>
      <span>{{ chartStore.timeframe }}</span>
      <span :title="workspaceStore.error ?? symbolProxyNotice ?? undefined">{{ footerMessage }}</span>
      <span class="workstation__data-state" role="status" aria-live="polite" aria-atomic="true" :aria-label="`Market data freshness: ${dataState.label}`" :class="`workstation__data-state--${dataState.kind}`">{{ dataState.label }}</span>
    </footer>
  </div>
</template>

<script setup lang="ts">
import { computed, h, nextTick, onBeforeUnmount, onMounted, ref, watch, type VNode } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useQuery } from '@tanstack/vue-query'
import WorkspaceLayoutHost from '@/components/workstation/WorkspaceLayoutHost.vue'
import WorkstationToolContent from '@/components/workstation/WorkstationToolContent.vue'
import WorkstationGlyph from '@/components/workstation/WorkstationGlyph.vue'
import { useChartStore } from '@/stores/chart'
import { useAuthStore } from '@/stores/auth'
import { OPENABLE_WORKSTATION_TOOLS, useWorkspaceStore, type LinkGroup, type OpenableToolDefinition } from '@/stores/workspace'
import type { LayoutConfig } from 'golden-layout'
import { resolveKnownInstrument } from '@/lib/instruments'
import { autoRatioExpression } from '@/lib/workstation/ratioExpression'
import { api } from '@/lib/api'
import { useQueryClient } from '@tanstack/vue-query'
import { useWatchlistStore } from '@/stores/watchlist'
import { useRecentInstrumentsStore } from '@/stores/recentInstruments'
import { workstationFreshness } from '@/lib/workstation/freshness'
import { capturePopoutGeometry, popoutWindowFeatures, readPopoutGeometry, recoverPopoutGeometry, type PopoutScreen } from '@/lib/workstation/popoutGeometry'
import { resolveMarketMapAnalysisSource } from '@/lib/workstation/marketMapPublication'

const route = useRoute()
const router = useRouter()
const chartStore = useChartStore()
const authStore = useAuthStore()
const workspaceStore = useWorkspaceStore()
const watchlistStore = useWatchlistStore()
const recentStore = useRecentInstrumentsStore()
const queryClient = useQueryClient()
const symbolInput = ref<HTMLInputElement | null>(null)
const workspaceMenuTrigger = ref<HTMLButtonElement | null>(null)
const workspaceMenuRoot = ref<HTMLElement | null>(null)
const toolLibraryTrigger = ref<HTMLButtonElement | null>(null)
const toolLibraryMenuRoot = ref<HTMLElement | null>(null)
const keyboardHelpTrigger = ref<HTMLButtonElement | null>(null)
const keyboardHelpMenuRoot = ref<HTMLElement | null>(null)
const recentSymbolsTrigger = ref<HTMLButtonElement | null>(null)
const recentSymbolsMenuRoot = ref<HTMLElement | null>(null)
const workspaceMenuStyle = ref<Record<string, string>>({})
const keyboardHelpMenuStyle = ref<Record<string, string>>({})
const toolLibraryMenuStyle = ref<Record<string, string>>({})
const recentSymbolsMenuStyle = ref<Record<string, string>>({})
// Deep links must be immediately usable while the versioned workspace snapshot
// hydrates. The route is already the user's explicit symbol intent, so expose it
// in the shell synchronously and let the canonical selection path validate/load
// it in the background. This also keeps the default workstation benchmark
// visible instead of showing an empty editor during Golden Layout startup.
const routeSymbol = typeof route.params.symbol === 'string' && route.params.symbol.trim()
  ? decodeURIComponent(route.params.symbol).trim().toUpperCase()
  : 'SPY'
const symbolDraft = ref(routeSymbol)
const toolLibraryOpen = ref(false)
const workspaceMenuOpen = ref(false)
const workspaceOptionIndex = ref(0)
const keyboardHelpOpen = ref(false)
const recentSymbolsOpen = ref(false)
const workspaceFileInput = ref<HTMLInputElement | null>(null)
// Golden Layout virtual roots capture their tool object when created. Advance
// this token only after an import/reset replaces the complete workspace object
// so those roots are recreated from the new serializable tool state.
const workspaceReloadKey = ref(0)
const workspaceReplacementPending = ref(false)
// Shell controls render before the async workspace snapshot has necessarily
// hydrated. Keep tool-opening commands queued behind that first load instead
// of allowing an early click to mutate a stale/null tab and then be overwritten
// by the snapshot response.
const workspaceReady = ref(false)
let workspaceLoadPromise: Promise<void> | null = null
let resolveWorkspaceReady: (() => void) | null = null
const workspaceReadyPromise = new Promise<void>(resolve => {
  resolveWorkspaceReady = resolve
})
const dragTabKey = ref<string | null>(null)
const tabDragOverKey = ref<string | null>(null)
const tabDragCommitted = ref(false)
const searchResults = ref<Array<{ symbol: string; name: string; exchange: string; type: string; instrument_id?: number | null }>>([])
const searchIndex = ref(-1)
const searchLoading = ref(false)
const searchSettled = ref(false)
const searchError = ref('')
let searchTimer: ReturnType<typeof setTimeout> | null = null
let searchRequest = 0
const symbolSearchEnabled = ref(false)
const searchPanelVisible = computed(() => symbolSearchEnabled.value && Boolean(symbolDraft.value.trim()))
const searchStateText = computed(() => {
  if (!searchPanelVisible.value) return ''
  if (searchLoading.value) return 'Searching canonical instruments'
  if (searchError.value) return `Symbol search error: ${searchError.value}`
  if (searchSettled.value && !searchResults.value.length) return `No canonical instruments found for ${symbolDraft.value.trim().toUpperCase()}`
  return ''
})
const handledWheelEvents = new WeakSet<Event>()
// Some browser/OS combinations omit ctrlKey from a wheel event even while the
// Control key is physically held. Track the modifier at window scope so the
// desktop traversal gesture remains reliable without requiring a synthetic
// event or changing editor shortcut ownership.
const ctrlWheelHeld = ref(false)
// Initial route loading and fast list traversal can overlap. The latest symbol
// intent wins so a late initial SPY request cannot restore an older selection.
let symbolSelectionGeneration = 0
let drilldownSelectionGeneration = 0
const preserveDrilldownSymbol = ref<string | null>(null)
// SPX is a logical benchmark identity. When an official SPX series is not
// entitled or cannot be resolved, keep the requested workflow usable through
// the canonical, explicitly-labelled SPY tradable proxy instead of leaving the
// workstation on a dead symbol.
const symbolProxyNotice = ref<string | null>(null)
const openableTools = OPENABLE_WORKSTATION_TOOLS
const documentVisible = ref(typeof document === 'undefined' || document.visibilityState === 'visible')
let removeVisibilityListener: (() => void) | null = null
const popoutGeometryPollers = new Map<string, ReturnType<typeof window.setInterval>>()

function closeSymbolSearch() {
  symbolSearchEnabled.value = false
  if (searchTimer) {
    clearTimeout(searchTimer)
    searchTimer = null
  }
  searchRequest += 1
  searchResults.value = []
  searchIndex.value = -1
  searchLoading.value = false
  searchSettled.value = false
  searchError.value = ''
}

function handleSymbolInput() {
  // A user edit is a newer symbol intent than the initial route hydration. In
  // particular, invalidate an in-flight SPY selection before its async
  // metadata/bar loads can write SPY back into the field between keystrokes.
  // Programmatic linked-symbol updates do not emit DOM input events and keep
  // their existing watcher-backed synchronization semantics.
  symbolSelectionGeneration += 1
  drilldownSelectionGeneration += 1
  symbolSearchEnabled.value = true
  if (symbolDraft.value.trim()) {
    searchLoading.value = true
    searchSettled.value = false
    searchError.value = ''
  }
}

type ShellMenu = 'workspace' | 'tool-library' | 'help' | 'recent'

/**
 * The desktop shell has one transient menu layer at a time. Keeping this
 * invariant in one place prevents a newly opened popover from leaving an
 * older fixed-position menu over the dock or stealing the next pointer event.
 * The search wrapper is the one deliberate exception: its listbox and recent
 * symbols menu may remain open while the symbol editor owns focus.
 */
function closeShellMenus(except?: ShellMenu) {
  if (except !== 'workspace') workspaceMenuOpen.value = false
  if (except !== 'tool-library') toolLibraryOpen.value = false
  if (except !== 'help') keyboardHelpOpen.value = false
  if (except !== 'recent') recentSymbolsOpen.value = false
  syncShellMenuListeners()
}

function shellMenuPosition(trigger: HTMLButtonElement | null, width: number, maxHeight: number, align: 'left' | 'right' = 'left'): Record<string, string> {
  const rect = trigger?.getBoundingClientRect()
  if (!rect) return { position: 'fixed', left: '8px', top: '8px', width: `${width}px`, maxHeight: `${maxHeight}px` }
  const gutter = 8
  // A dense workstation intentionally keeps a larger internal minimum width;
  // use the actual document/visual viewport for fixed overlays instead of the
  // overflowed layout viewport reported by window.innerWidth.
  const viewportWidth = Math.min(window.innerWidth, document.documentElement.clientWidth || window.innerWidth, window.visualViewport?.width || window.innerWidth)
  const viewportHeight = Math.min(window.innerHeight, document.documentElement.clientHeight || window.innerHeight, window.visualViewport?.height || window.innerHeight)
  const boundedWidth = Math.min(width, Math.max(150, viewportWidth - gutter * 2))
  const height = Math.min(maxHeight, Math.max(96, viewportHeight - gutter * 2))
  const preferredLeft = align === 'right' ? rect.right - boundedWidth : rect.left
  const left = Math.max(gutter, Math.min(preferredLeft, viewportWidth - boundedWidth - gutter))
  const below = rect.bottom + 1
  const above = rect.top - height - 1
  const top = below + height <= viewportHeight - gutter ? below : Math.max(gutter, above)
  return { position: 'fixed', left: `${Math.round(left)}px`, top: `${Math.round(top)}px`, width: `${Math.round(boundedWidth)}px`, maxHeight: `${Math.round(height)}px` }
}

function positionShellMenus() {
  if (workspaceMenuOpen.value) workspaceMenuStyle.value = shellMenuPosition(workspaceMenuTrigger.value, 292, 360)
  if (keyboardHelpOpen.value) keyboardHelpMenuStyle.value = shellMenuPosition(keyboardHelpTrigger.value, 286, 320)
  if (toolLibraryOpen.value) toolLibraryMenuStyle.value = shellMenuPosition(toolLibraryTrigger.value, 190, 360)
  if (recentSymbolsOpen.value) recentSymbolsMenuStyle.value = shellMenuPosition(recentSymbolsTrigger.value, 280, 320, 'right')
}

function addShellMenuListeners() {
  window.addEventListener('resize', positionShellMenus)
  window.addEventListener('scroll', positionShellMenus, true)
}

function removeShellMenuListeners() {
  window.removeEventListener('resize', positionShellMenus)
  window.removeEventListener('scroll', positionShellMenus, true)
}

function syncShellMenuListeners() {
  const open = workspaceMenuOpen.value || toolLibraryOpen.value || keyboardHelpOpen.value || recentSymbolsOpen.value
  if (!open) return removeShellMenuListeners()
  void nextTick(() => { positionShellMenus(); addShellMenuListeners() })
}

function toggleWorkspaceMenu() {
  const open = !workspaceMenuOpen.value
  closeShellMenus(open ? 'workspace' : undefined)
  workspaceMenuOpen.value = open
  if (open) {
    const selectedIndex = (workspaceStore.workspaces ?? []).findIndex(item => item.id === workspaceStore.workspace?.id)
    workspaceOptionIndex.value = selectedIndex >= 0 ? selectedIndex : 0
    void focusShellMenu('workspace')
    // The fixed overlay is mounted one render after the trigger key event in
    // some Chromium/GLayout combinations. One bounded retry covers that DOM
    // attachment boundary without introducing polling or stealing later focus.
    window.setTimeout(() => {
      if (workspaceMenuOpen.value) void focusShellMenu('workspace')
    }, 50)
    // Startup hydration already supplies the current workspace. Only fetch the
    // list on a genuinely cold menu; refreshing a warm list would replace the
    // focused listbox and create a keyboard race.
    if (!(workspaceStore.workspaces ?? []).length) {
      void (async () => {
        try { await workspaceStore.refreshWorkspaces?.() } catch { /* retain the hydrated workspace list */ }
        syncWorkspaceOptionIndex()
        await focusShellMenu('workspace')
      })()
    }
  }
  if (open) closeSymbolSearch()
  else workspaceMenuTrigger.value?.focus()
  syncShellMenuListeners()
}

function syncWorkspaceOptionIndex() {
  const workspaces = workspaceStore.workspaces ?? []
  const selectedIndex = workspaces.findIndex(item => item.id === workspaceStore.workspace?.id)
  workspaceOptionIndex.value = selectedIndex >= 0 ? selectedIndex : Math.min(workspaceOptionIndex.value, Math.max(0, workspaces.length - 1))
}

function focusWorkspaceOption(index: number) {
  const options = workspaceStore.workspaces ?? []
  if (!options.length) return
  workspaceOptionIndex.value = Math.max(0, Math.min(index, options.length - 1))
  void nextTick(() => workspaceMenuRoot.value?.querySelector<HTMLElement>('[role="listbox"]')?.focus())
}

function switchWorkspaceFromMenu(id: number) {
  void workspaceStore.switchWorkspace(id)
  closeShellMenuToTrigger('workspace')
}

function handleWorkspaceListKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') {
    event.preventDefault()
    event.stopPropagation()
    closeShellMenuToTrigger('workspace')
    return
  }
  const options = workspaceStore.workspaces ?? []
  if (!options.length) return
  if (event.key === 'ArrowDown' || event.key === 'ArrowRight') {
    event.preventDefault()
    focusWorkspaceOption((workspaceOptionIndex.value + 1) % options.length)
  } else if (event.key === 'ArrowUp' || event.key === 'ArrowLeft') {
    event.preventDefault()
    focusWorkspaceOption((workspaceOptionIndex.value - 1 + options.length) % options.length)
  } else if (event.key === 'Home') {
    event.preventDefault()
    focusWorkspaceOption(0)
  } else if (event.key === 'End') {
    event.preventDefault()
    focusWorkspaceOption(options.length - 1)
  } else if (event.key === 'Enter' || event.key === ' ') {
    event.preventDefault()
    const selected = options[workspaceOptionIndex.value]
    if (selected) switchWorkspaceFromMenu(selected.id)
  }
}

watch(() => workspaceStore.workspaces?.length ?? 0, () => {
  if (!workspaceMenuOpen.value || !(workspaceStore.workspaces ?? []).length) return
  syncWorkspaceOptionIndex()
  void nextTick(() => {
    const active = document.activeElement
    const menuRoot = workspaceMenuRoot.value
    if (active === workspaceMenuTrigger.value || (menuRoot && menuRoot.contains(active))) {
      menuRoot?.querySelector<HTMLElement>('[role="listbox"]')?.focus()
    }
  })
})

function toggleToolLibrary() {
  const open = !toolLibraryOpen.value
  closeShellMenus(open ? 'tool-library' : undefined)
  toolLibraryOpen.value = open
  if (open) closeSymbolSearch()
  if (open) void focusShellMenu('tool-library')
  else toolLibraryTrigger.value?.focus()
  syncShellMenuListeners()
}

function toggleKeyboardHelp() {
  const open = !keyboardHelpOpen.value
  closeShellMenus(open ? 'help' : undefined)
  keyboardHelpOpen.value = open
  if (open) closeSymbolSearch()
  if (open) void focusShellMenu('help')
  else keyboardHelpTrigger.value?.focus()
  syncShellMenuListeners()
}

function toggleRecentSymbols() {
  const open = !recentSymbolsOpen.value
  closeShellMenus(open ? 'recent' : undefined)
  recentSymbolsOpen.value = open
  if (open) closeSymbolSearch()
  if (open) void focusShellMenu('recent')
  else recentSymbolsTrigger.value?.focus()
  syncShellMenuListeners()
}

type ShellMenuRoot = 'workspace' | 'tool-library' | 'help' | 'recent'
const shellMenuRoots: Record<ShellMenuRoot, ReturnType<typeof ref<HTMLElement | null>>> = {
  workspace: workspaceMenuRoot,
  'tool-library': toolLibraryMenuRoot,
  help: keyboardHelpMenuRoot,
  recent: recentSymbolsMenuRoot,
}
const shellMenuTriggers: Record<ShellMenuRoot, ReturnType<typeof ref<HTMLButtonElement | null>>> = {
  workspace: workspaceMenuTrigger,
  'tool-library': toolLibraryTrigger,
  help: keyboardHelpTrigger,
  recent: recentSymbolsTrigger,
}
function shellMenuItems(menu: ShellMenuRoot) {
  return Array.from(shellMenuRoots[menu].value?.querySelectorAll<HTMLButtonElement>('[role="menuitem"]:not(:disabled)') ?? [])
}
async function focusShellMenu(menu: ShellMenuRoot) {
  await nextTick()
  if (menu === 'workspace') {
    const list = workspaceMenuRoot.value?.querySelector<HTMLElement>('[role="listbox"]')
    list?.focus()
    return
  }
  shellMenuItems(menu)[0]?.focus()
}
function closeShellMenuToTrigger(menu: ShellMenuRoot) {
  closeShellMenus()
  void nextTick(() => shellMenuTriggers[menu].value?.focus())
}
function handleShellTriggerKeydown(menu: ShellMenuRoot, event: KeyboardEvent) {
  if (!['Enter', ' ', 'ArrowDown', 'ArrowUp'].includes(event.key)) return
  event.preventDefault()
  // Opening a conditional menu during this key event mounts its root before
  // the browser finishes bubbling the original event. Stop that event at the
  // trigger boundary so the newly mounted menu cannot interpret ArrowDown as
  // a request to focus its first action (the workspace listbox owns focus).
  event.stopPropagation()
  if (menu === 'workspace' && !workspaceMenuOpen.value) return toggleWorkspaceMenu()
  if (menu === 'tool-library' && !toolLibraryOpen.value) return toggleToolLibrary()
  if (menu === 'help' && !keyboardHelpOpen.value) return toggleKeyboardHelp()
  if (menu === 'recent' && !recentSymbolsOpen.value) return toggleRecentSymbols()
  void focusShellMenu(menu)
}
function handleShellMenuKeydown(menu: ShellMenuRoot, event: KeyboardEvent) {
  if (event.key === 'Escape') {
    event.preventDefault()
    event.stopPropagation()
    closeShellMenuToTrigger(menu)
    return
  }
  const items = shellMenuItems(menu)
  if (!items.length) return
  const current = items.indexOf(document.activeElement as HTMLButtonElement)
  let next: number | null = null
  if (event.key === 'ArrowDown' || event.key === 'ArrowRight') next = (current + 1 + items.length) % items.length
  else if (event.key === 'ArrowUp' || event.key === 'ArrowLeft') next = (current - 1 + items.length) % items.length
  else if (event.key === 'Home') next = 0
  else if (event.key === 'End') next = items.length - 1
  if (next === null) return
  event.preventDefault()
  items[next].focus()
}

function preserveActiveUserSymbolDraft(symbol: string) {
  return symbolSearchEnabled.value
    && symbolInput.value === document.activeElement
    && symbolDraft.value.trim().toUpperCase() !== symbol.toUpperCase()
}

// A focused symbol input can keep its listbox above the dock surface. Close it
// during the pointer-down capture/bubble sequence for every tool click so the
// overlay cannot intercept the later click event. Pointer events inside the
// search control are stopped at the wrapper and retain normal list interaction.
function handleWorkstationPointerDown(event: PointerEvent) {
  const target = event.target
  const insideSearch = target instanceof Element && target.closest('.workstation__search')
  if (insideSearch) {
    // Search controls retain their own listbox/history state, but any other
    // shell menu must still close when focus moves into the editor.
    closeShellMenus('recent')
    return
  }
  if (!(target instanceof Element && target.closest('.workstation__workspace-menu'))) workspaceMenuOpen.value = false
  if (!(target instanceof Element && target.closest('.workstation__tool-library'))) toolLibraryOpen.value = false
  if (!(target instanceof Element && target.closest('.workstation__help-menu'))) keyboardHelpOpen.value = false
  recentSymbolsOpen.value = false
  syncShellMenuListeners()
  closeSymbolSearch()
}

function handleWorkstationFocusIn(event: FocusEvent) {
  const target = event.target
  if (target instanceof Element && target.closest('.workstation__search')) {
    // Global menus must not remain over an editor after focus moves into the
    // symbol control. The editor owns subsequent keyboard events, so dismiss
    // the shell help surface at the same focus boundary.
    keyboardHelpOpen.value = false
    syncShellMenuListeners()
    return
  }
  const inWorkspaceMenu = target instanceof Element && target.closest('.workstation__workspace-menu')
  const inToolLibrary = target instanceof Element && target.closest('.workstation__tool-library')
  const inHelpMenu = target instanceof Element && target.closest('.workstation__help-menu')
  const inRecentMenu = target instanceof Element && target.closest('.workstation__search')
  if (!inWorkspaceMenu) workspaceMenuOpen.value = false
  if (!inToolLibrary) toolLibraryOpen.value = false
  if (!inHelpMenu) keyboardHelpOpen.value = false
  if (!inRecentMenu) recentSymbolsOpen.value = false
  syncShellMenuListeners()
  closeSymbolSearch()
}

function handleWorkstationChange(event: Event) {
  const target = event.target
  if (target instanceof Element && target.closest('.workstation__search')) return
  recentSymbolsOpen.value = false
  syncShellMenuListeners()
  closeSymbolSearch()
}

const activeSymbol = computed(() => workspaceStore.linkedSymbol || 'SPY')
const dataState = computed(() => {
  if (chartStore.error) return { kind: 'unavailable', label: 'Unavailable' }
  const technical = workspaceStore.technicals?.[activeSymbol.value]
  return workstationFreshness({
    freshness: technical?.freshness,
    freshness_detail: technical?.freshness_detail,
    isLoading: chartStore.isLoading,
    isFetchingHistory: chartStore.isFetchingHistory,
    hasBars: chartStore.bars.length > 0,
  })
})
const footerMessage = computed(() => symbolProxyNotice.value ?? humanizeWorkspaceError(workspaceStore.error))
const isPopout = computed(() => route.path.startsWith('/popout/'))

/** Keep raw transport diagnostics out of the dense workstation status bar.
 * Detailed errors remain available as the native tooltip and in browser/backend
 * diagnostics, while users get a concise recovery-oriented message in the shell.
 */
function humanizeWorkspaceError(error: string | null | undefined): string {
  if (!error) return 'Ready'
  const normalized = error.trim()
  // Conflict recovery has already produced a user-safe message in the store.
  // Keep the recovery name and the explicit preservation wording visible in the
  // footer instead of collapsing it to the generic HTTP 409 label.
  if (/local changes were preserved/i.test(normalized)) return normalized
  const status = normalized.match(/^API\s+(?:GET|POST|PUT|PATCH|DELETE)\s+[^→]+→\s*(\d{3})/i)?.[1]
  if (status === '401' || status === '403') return 'Session or permission required'
  if (status === '404') return 'Some market data is unavailable'
  if (status === '409') return 'Workspace changed elsewhere; recovery is available'
  if (status && Number(status) >= 500) return 'Market service unavailable; cached data retained'
  if (/^API\s+/i.test(normalized)) return 'Market data request could not be completed'
  return normalized
}

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
  enabled: computed(() => !isPopout.value && documentVisible.value && Boolean(workspaceStore.workspace) && workspaceStore.isPersistenceLeader),
  staleTime: 60_000,
  refetchInterval: 5 * 60 * 1000,
  refetchIntervalInBackground: false,
})

async function refreshMarketData() {
  if (isPopout.value || !documentVisible.value) return
  if (workspaceStore.isPersistenceLeader) {
    await marketAnalysisQuery.refetch()
  } else {
    // Followers still hydrate once when they open. Subsequent periodic refreshes are
    // leader-owned and arrive through the cross-window refresh event.
    await workspaceStore.refreshMarketAnalysis()
  }
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

function selectWorkspaceTab(stableKey: string) {
  if (workspaceStore.activeTabKey === stableKey) return
  // A layout switch can occur while the previous layout's trailing snapshot is
  // still in flight. Advance the snapshot generation so that stale server
  // responses cannot reinstall the previous layout over the newly selected tab.
  workspaceStore.activeTabKey = stableKey
  workspaceStore.scheduleSnapshot()
}

async function replaceDockAfterWorkspaceChange() {
  if (isPopout.value) return
  workspaceReplacementPending.value = true
  await nextTick()
  workspaceReloadKey.value += 1
  await nextTick()
  workspaceReplacementPending.value = false
  await nextTick()
}

function focusWorkspaceTab(stableKey: string, source?: EventTarget | null) {
  const sourceElement = source instanceof HTMLElement ? source : null
  const tabList = sourceElement?.closest('[role="tablist"]')
  const tab = Array.from((tabList ?? document).querySelectorAll<HTMLElement>('[data-tab-key]'))
    .find(element => element.dataset.tabKey === stableKey)
  tab?.focus()
}

function handleWorkspaceTabKeydown(stableKey: string, event: KeyboardEvent) {
  const tabs = workspaceStore.workspace?.tabs ?? []
  const currentIndex = tabs.findIndex(tab => tab.stable_key === stableKey)
  if (currentIndex < 0 || !tabs.length) return

  if (event.key === 'Enter' || event.key === ' ') {
    event.preventDefault()
    selectWorkspaceTab(stableKey)
    return
  }

  let nextIndex: number | null = null
  if (event.key === 'ArrowRight' || event.key === 'ArrowDown') nextIndex = (currentIndex + 1) % tabs.length
  else if (event.key === 'ArrowLeft' || event.key === 'ArrowUp') nextIndex = (currentIndex - 1 + tabs.length) % tabs.length
  else if (event.key === 'Home') nextIndex = 0
  else if (event.key === 'End') nextIndex = tabs.length - 1
  if (nextIndex === null) return

  event.preventDefault()
  focusWorkspaceTab(tabs[nextIndex].stable_key, event.currentTarget)
}
const allSymbols = computed(() => {
  const loaded = [
    ...(workspaceStore.marketGroups['us-benchmarks']?.members ?? []),
    ...(workspaceStore.marketGroups['sp500-sectors']?.members ?? []),
  ].map(member => member.instrument.symbol)
  // Keep the canonical fallback symbols available even when a partially hydrated
  // group contains only one member. This preserves Ctrl+wheel traversal during
  // cross-test/window hydration without inventing instruments or bypassing the
  // normal freshness/coverage state.
  return [...new Set([...loaded, 'SPY', 'QQQ', 'DIA', 'IWM'])]
})
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

function sp500TradableProxy(): string {
  const identities = workspaceStore.marketGroups['us-benchmarks']?.provenance?.benchmark_identities
  if (identities && typeof identities === 'object') {
    const sp500 = (identities as Record<string, unknown>).sp500
    if (sp500 && typeof sp500 === 'object') {
      const configuredProxy = (sp500 as Record<string, unknown>).default_tradable_proxy
      if (typeof configuredProxy === 'string' && configuredProxy.trim()) return configuredProxy.trim().toUpperCase()
    }
  }
  return 'SPY'
}

async function selectSymbol(raw: string, timestamp?: string, allowNavigationFallback = false, instrumentId?: number | null) {
  const requested = raw.trim()
  if (!requested) return
  const generation = ++symbolSelectionGeneration
  symbolProxyNotice.value = null
  // A normal symbol selection supersedes any still-running proxy drill-down
  // handler that was started by an earlier row click.
  drilldownSelectionGeneration += 1
  // Invalidate an in-flight autocomplete request as soon as an explicit symbol
  // selection starts and close any stale options before the next interaction.
  closeSymbolSearch()
  let symbol: string
  let resolvedInstrumentId: number | null = null
  const navigationFallbacks = new Set(['SPY', 'QQQ', 'DIA', 'IWM'])
  // Keyboard/list traversal is an interaction command, not an instrument
  // search. Resolve the small canonical benchmark universe synchronously so a
  // slow or unavailable metadata provider cannot make Ctrl+wheel appear to do
  // nothing. Normal typed/search selections still require canonical identity
  // resolution below.
  const knownWorkstationSymbols = new Set([
    ...allSymbols.value.map(value => value.trim().toUpperCase()),
    ...(workspaceStore.marketGroups['sp500-sectors']?.members ?? [])
      .map(member => member.instrument.symbol.trim().toUpperCase()),
  ])
  if (knownWorkstationSymbols.has(requested.toUpperCase())) {
    // These symbols are already canonical members of a loaded workstation
    // universe. Publish them synchronously so an in-flight initial request
    // cannot leave the Industries pane bound to the previous ETF.
    symbol = requested.toUpperCase()
  } else if (allowNavigationFallback && navigationFallbacks.has(requested.toUpperCase())) {
    symbol = requested.toUpperCase()
  } else {
    try {
      const resolved = await resolveKnownInstrument(requested, 'Workstation symbol', { canonicalOnly: true })
      symbol = resolved.symbol
      resolvedInstrumentId = resolved.id
    } catch (cause: any) {
      if (generation !== symbolSelectionGeneration) return
      if (allowNavigationFallback && navigationFallbacks.has(requested.toUpperCase())) {
        symbol = requested.toUpperCase()
      } else if (requested.toUpperCase() === 'SPX') {
        // The canonical database may not contain the official index series
        // under the current free-source entitlements. Resolve the configured
        // tradable proxy through the normal instrument endpoint so this is
        // still a canonical, provenance-backed selection rather than a fake
        // ticker alias. Keep the limitation visible in the shell status bar.
        const proxy = sp500TradableProxy()
        try {
          const resolved = await resolveKnownInstrument(proxy, 'S&P 500 tradable proxy', { canonicalOnly: true })
          symbol = resolved.symbol
          resolvedInstrumentId = resolved.id
          if (generation !== symbolSelectionGeneration) return
          symbolProxyNotice.value = `SPX official series unavailable; using tradable proxy ${symbol}`
        } catch (proxyCause: any) {
          if (generation !== symbolSelectionGeneration) return
          workspaceStore.error = proxyCause?.message ?? cause?.message ?? 'Unable to resolve S&P 500 benchmark'
          return
        }
      } else {
        workspaceStore.error = cause?.message ?? 'Unable to resolve symbol'
        return
      }
    }
  }
  if (generation !== symbolSelectionGeneration) return
  let canonicalInstrumentId = typeof instrumentId === 'number' ? instrumentId : resolvedInstrumentId
  if (canonicalInstrumentId == null) {
    const knownMember = [
      ...(workspaceStore.marketGroups['us-benchmarks']?.members ?? []),
      ...(workspaceStore.marketGroups['sp500-sectors']?.members ?? []),
    ].find(member => member.instrument.symbol.trim().toUpperCase() === symbol)
    canonicalInstrumentId = knownMember?.instrument.id ?? null
  }
  // Crossing to a different sector starts a new industry context immediately,
  // before any old ETF-holdings requests can complete. Stock/proxy selections
  // intentionally retain the sector context for ratio and constituent drilldown.
  const sectorSymbols = new Set(
    (workspaceStore.marketGroups['sp500-sectors']?.members ?? [])
      .map(member => member.instrument.symbol.trim().toUpperCase()),
  )
  if (sectorSymbols.has(symbol)) workspaceStore.setConstituentETF(symbol)
  symbolDraft.value = symbol
  recentStore.add(symbol)
  // Capture the drill-down ETF before loading the newly selected symbol. A stock
  // selection from a constituent list may itself have no holdings endpoint, but
  // its relevant ratio denominator is still the list's active ETF.
  const comparisonETF = workspaceStore.constituentETF
  workspaceStore.publishSymbol({
    symbol,
    ...(typeof canonicalInstrumentId === 'number' ? { instrumentId: canonicalInstrumentId } : {}),
    timestamp,
    group: 'blue',
    sourceWindowKey: 'workstation',
  })
  // Update linked ratio state at publish time. Data hydration can take much
  // longer than the user's next click and must not delay the visible target.
  updateAutoRatioExpression(symbol, comparisonETF)
  await loadSymbolData(symbol, comparisonETF, false)
  if (generation !== symbolSelectionGeneration) return
}

async function loadSymbolData(symbol: string, comparisonETF = workspaceStore.constituentETF, updateRatio = true) {
  if (!preserveActiveUserSymbolDraft(symbol)) symbolDraft.value = symbol
  if (!documentVisible.value) return
  await Promise.all([
    chartStore.loadBars(symbol, chartStore.timeframe, chartStore.barType, true),
    workspaceStore.loadETFHoldings(symbol),
    workspaceStore.loadETFIndustries(symbol),
    workspaceStore.loadTechnical(symbol),
  ])
  if (updateRatio) updateAutoRatioExpression(symbol, comparisonETF)
}

function scheduleSymbolSearch(value: string) {
  if (!symbolSearchEnabled.value) return
  if (searchTimer) clearTimeout(searchTimer)
  const query = value.trim()
  if (!query) {
    searchResults.value = []
    searchIndex.value = -1
    searchLoading.value = false
    searchSettled.value = false
    searchError.value = ''
    return
  }
  searchLoading.value = true
  searchSettled.value = false
  searchError.value = ''
  const requestId = ++searchRequest
  searchTimer = setTimeout(async () => {
    try {
      const results = await queryClient.fetchQuery<Array<{ symbol: string; name: string; exchange: string; type: string }>>({
        queryKey: ['workstation', 'instrument-search', query.toUpperCase()],
      queryFn: () => api.get<Array<{ symbol: string; name: string; exchange: string; type: string; instrument_id?: number | null }>>('/instruments/search', { q: query, canonical_only: true }),
        staleTime: 30_000,
      })
      if (requestId !== searchRequest || symbolDraft.value.trim() !== query) return
      searchResults.value = results
      searchIndex.value = results.length ? 0 : -1
      searchLoading.value = false
      searchSettled.value = true
    } catch {
      if (requestId === searchRequest) {
        searchResults.value = []
        searchIndex.value = -1
        searchLoading.value = false
        searchSettled.value = true
        searchError.value = 'Unable to search canonical instruments. Try again.'
      }
    }
  }, 120)
}

function selectSearchResult(symbol: string, instrumentId?: number | null) {
  // Close before changing the draft. The input remains focused while an option
  // is selected with the mouse, so relying on blur leaves the listbox mounted
  // above the workstation and can intercept the next tool click.
  closeSymbolSearch()
  symbolDraft.value = symbol
  void selectSymbol(symbol, undefined, false, instrumentId)
}

function selectRecentSymbol(symbol: string) {
  recentSymbolsOpen.value = false
  closeSymbolSearch()
  symbolDraft.value = symbol
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
    closeSymbolSearch()
    void selectSymbol(result?.symbol ?? symbolDraft.value, undefined, false, result?.instrument_id)
  } else if (event.key === 'Escape') {
    closeSymbolSearch()
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

function selectOccurrence(symbol: string, timestamp: string, instrumentId?: number | null) {
  void selectSymbol(symbol, timestamp, false, instrumentId)
}

function selectIndustryForContext(industry: string, etf?: string) {
  const contextETF = etf?.trim().toUpperCase() || workspaceStore.constituentETF || ''
  void workspaceStore.selectIndustry(contextETF, industry)
}

function setLinkedTimeframe(timeframe: string, group: LinkGroup = 'blue') {
  workspaceStore.publishTimeframe(timeframe, group, 'workstation')
}

async function signOut() {
  await authStore.logout()
}

async function selectIndustryProxy(symbol: string, instrumentId?: number | null) {
  const generation = ++drilldownSelectionGeneration
  // Proxy rows normally carry their canonical identity, but keep direct or
  // keyboard-triggered proxy navigation identity-safe as well. This avoids
  // publishing a ticker-only link when a valid local instrument exists.
  const resolved = await resolveKnownInstrument(symbol, 'Industry ETF proxy', { canonicalOnly: true })
  const normalized = resolved.symbol
  if (generation !== drilldownSelectionGeneration) return
  const resolvedInstrumentId = typeof instrumentId === 'number' ? instrumentId : resolved.id
  const comparisonETF = workspaceStore.constituentETF
  workspaceStore.selectIndustryProxy(normalized)
  symbolDraft.value = normalized
  recentStore.add(normalized)
  // A proxy is a drill-down target, not a new taxonomy root. Publish it to the
  // linked charts and load its price/technicals while preserving the selected
  // sector/industry context. The watcher uses this marker to avoid replacing
  // the sector holdings tree with the proxy's own holdings.
  preserveDrilldownSymbol.value = normalized
  workspaceStore.publishSymbol({
    symbol: normalized,
    ...(typeof resolvedInstrumentId === 'number' ? { instrumentId: resolvedInstrumentId } : {}),
    group: 'blue',
    sourceWindowKey: 'workstation',
  })
  updateAutoRatioExpression(normalized, comparisonETF)
  await Promise.all([
    chartStore.loadBars(normalized, chartStore.timeframe, chartStore.barType, true),
    workspaceStore.loadTechnical(normalized),
  ])
}

async function openTool(tool: OpenableToolDefinition, configurationOverride: Record<string, unknown> = {}) {
  // The dock can already expose a fully usable active tab while the initial
  // workspace promise is still settling (notably after Golden Layout restores
  // a persisted snapshot). Do not strand an Add-tool click behind that promise
  // when the concrete tab needed for the mutation is already present. Only
  // wait for readiness when there is no active tab to mutate at all.
  if (!workspaceReady.value && !workspaceStore.activeTab) {
    if (workspaceLoadPromise) await workspaceLoadPromise
    // The click can arrive in the same turn as component mount, before the
    // onMounted callback has assigned its load promise. Wait on the explicit
    // readiness signal instead of silently dropping the user's command after
    // an arbitrary polling budget while the canonical workspace is still
    // hydrating.
    if (!workspaceReady.value && !workspaceStore.activeTab) await workspaceReadyPromise
  }
  if (!workspaceStore.activeTab) {
    workspaceStore.error = 'The workstation layout is not available yet; please retry the tool action.'
    return
  }
  const opened = workspaceStore.openTool(tool, configurationOverride)
  toolLibraryOpen.value = false
  if (!opened) return
  await nextTick()
  // Golden Layout can finish creating the tab after its virtual component has
  // mounted. Clicking the concrete tab element is the same interaction as a
  // user selecting it and guarantees the newly opened tool is foregrounded.
  // Installing a component can produce a late Golden Layout state restore. In
  // that window a click may activate the tab successfully and then be followed
  // by the restore selecting the previous tab. Keep applying the same real tab
  // interaction until the DOM confirms the requested tab is active; this is
  // bounded and exits immediately once the user-visible state is correct.
  for (let attempt = 0; attempt < 40; attempt += 1) {
    const toolRoot = [...document.querySelectorAll<HTMLElement>('[data-tool-key]')]
      .find(candidate => candidate.dataset.toolKey === opened.instance_key)
    // Do not fall back to a same-titled tab while the new virtual component is
    // still mounting. A persisted Notes/Chart/etc. tab can already be visible;
    // treating that tab as success would leave the newly opened component hidden.
    if (!toolRoot) {
      await new Promise(resolve => setTimeout(resolve, 25))
      continue
    }
    const stack = toolRoot?.closest<HTMLElement>('.lm_stack')
    const stackItems = stack ? [...stack.querySelectorAll<HTMLElement>('.lm_items > div')] : []
    const itemIndex = toolRoot
      ? stackItems.findIndex(item => item.contains(toolRoot))
      : -1
    const stackTabs = stack
      ? [...stack.querySelectorAll<HTMLElement>('.lm_header .lm_tabs > .lm_tab')]
      : []
    let tab = itemIndex >= 0 ? stackTabs[itemIndex] : null
    if (!tab && itemIndex >= stackTabs.length) {
      // Golden Layout moves overflowed tabs into its tab-dropdown list. Open
      // that list and address the corresponding overflow index; selecting a
      // same-titled visible tab would activate an older instance instead.
      const dropdownList = stack?.querySelector<HTMLElement>('.lm_tabdropdown_list')
      if (dropdownList && getComputedStyle(dropdownList).display === 'none') {
        stack?.querySelector<HTMLElement>('.lm_tabdropdown')?.click()
        await new Promise(resolve => setTimeout(resolve, 25))
        continue
      }
      const overflowTabs = dropdownList
        ? [...dropdownList.querySelectorAll<HTMLElement>('.lm_tab')]
        : []
      const matchingOverflowTabs = overflowTabs
        .filter(candidate => candidate.textContent?.trim() === opened.title)
      tab = overflowTabs[itemIndex - stackTabs.length]
        ?? matchingOverflowTabs[matchingOverflowTabs.length - 1]
        ?? null
    }
    if (tab) {
      if (tab.classList.contains('lm_active')) return
      tab.click()
    }
    await new Promise(resolve => setTimeout(resolve, 25))
  }
  return opened
}

async function openMarketMap(sourceId: string) {
  const normalized = sourceId.trim()
  if (!normalized) return
  const definition = OPENABLE_WORKSTATION_TOOLS.find(tool => tool.tool_type === 'market_map')
  if (!definition) return
  await openTool(definition, { source_id: normalized })
}

async function openStudyLab() {
  const studyLayout = workspaceStore.workspace?.tabs.find(tab => tab.stable_key === 'study-lab')
  if (studyLayout) selectWorkspaceTab(studyLayout.stable_key)
  const currentTab = workspaceStore.activeTab
  const studyWindow = currentTab?.windows.find(window => window.tool_type === 'study_lab')
  if (studyWindow) {
    // A persisted Study Lab window may exist in the layout without being the
    // active Golden Layout component. Merely switching to the layout tab leaves
    // the tool mounted but hidden behind another stack tab, making the global
    // Study action appear to do nothing after hydration.
    workspaceStore.setActiveWindow(studyWindow.instance_key)
    return
  }
  const studyDefinition = OPENABLE_WORKSTATION_TOOLS.find(tool => tool.tool_type === 'study_lab')
  if (studyDefinition) await openTool(studyDefinition)
}

function renameTab(stableKey: string, name: string) {
  workspaceStore.renameTab(stableKey, name)
}

function deleteTab(stableKey: string) {
  if (!window.confirm('Delete this personal layout?')) return
  workspaceStore.deleteTab(stableKey)
}

function dropTab(targetStableKey: string, event?: DragEvent) {
  const source = dragTabKey.value || event?.dataTransfer?.getData('text/plain') || null
  commitTabDrag(source, targetStableKey)
  endTabDrag()
}

function beginTabDrag(stableKey: string, event?: DragEvent) {
  dragTabKey.value = stableKey
  tabDragOverKey.value = stableKey
  tabDragCommitted.value = false
  if (event?.dataTransfer) {
    event.dataTransfer.effectAllowed = 'move'
    event.dataTransfer.setData('text/plain', stableKey)
  }
}

function beginTabPointerDrag(stableKey: string, event: PointerEvent) {
  // Native drag events are not emitted consistently by every browser test
  // driver. Track the same intent through pointer events as a durable fallback;
  // the native path remains enabled for OS-level dragging.
  if (event.button !== 0) return
  beginTabDrag(stableKey)
  window.addEventListener('pointermove', handleTabPointerMove, true)
  window.addEventListener('pointerup', handleTabPointerUp, true)
}

function beginTabMouseDrag(stableKey: string, event: MouseEvent) {
  if (event.button !== 0) return
  beginTabDrag(stableKey)
  window.addEventListener('mousemove', handleTabMouseMove, true)
  window.addEventListener('mouseup', handleTabMouseUp, true)
}

function handleTabMouseMove(event: MouseEvent) {
  if (!dragTabKey.value) return
  const target = document.elementFromPoint(event.clientX, event.clientY)?.closest<HTMLElement>('[data-tab-key]')
  if (target?.dataset.tabKey) tabDragOverKey.value = target.dataset.tabKey
}

function handleTabMouseUp(event: MouseEvent) {
  if (!dragTabKey.value) return
  const target = document.elementFromPoint(event.clientX, event.clientY)?.closest<HTMLElement>('[data-tab-key]')
  commitTabDrag(dragTabKey.value, target?.dataset.tabKey ?? tabDragOverKey.value)
  endTabDrag()
}

function handleTabPointerMove(event: PointerEvent) {
  if (!dragTabKey.value) return
  const target = document.elementFromPoint(event.clientX, event.clientY)?.closest<HTMLElement>('[data-tab-key]')
  if (target?.dataset.tabKey) tabDragOverKey.value = target.dataset.tabKey
}

function handleTabPointerUp(event: PointerEvent) {
  if (!dragTabKey.value) return
  const target = document.elementFromPoint(event.clientX, event.clientY)?.closest<HTMLElement>('[data-tab-key]')
  commitTabDrag(dragTabKey.value, target?.dataset.tabKey ?? tabDragOverKey.value)
  endTabDrag()
}

function commitTabDrag(source: string | null, target: string | null) {
  if (!source || !target || source === target || tabDragCommitted.value) return
  tabDragCommitted.value = true
  workspaceStore.reorderTabs(source, target)
}

function endTabDrag(event?: DragEvent) {
  const source = dragTabKey.value
  const elementTarget = event && document.elementFromPoint(event.clientX, event.clientY)?.closest<HTMLElement>('[data-tab-key]')
  const target = elementTarget?.dataset.tabKey ?? tabDragOverKey.value
  // Some Chromium/macOS drag paths emit dragend without a corresponding drop.
  // Commit the last visible target as a guarded fallback so the primary tab
  // strip remains a reliable reorder surface rather than a visual-only affordance.
  if (!tabDragCommitted.value) commitTabDrag(source, target)
  dragTabKey.value = null
  tabDragOverKey.value = null
  tabDragCommitted.value = false
  window.removeEventListener('pointermove', handleTabPointerMove, true)
  window.removeEventListener('pointerup', handleTabPointerUp, true)
  window.removeEventListener('mousemove', handleTabMouseMove, true)
  window.removeEventListener('mouseup', handleTabMouseUp, true)
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
  workspaceReplacementPending.value = true
  await nextTick()
  try {
    const payload = JSON.parse(await file.text()) as unknown
    if (workspaceStore.importWorkspaceSnapshot(payload)) {
      workspaceReloadKey.value += 1
      workspaceMenuOpen.value = false
      await nextTick()
    }
  } catch {
    workspaceStore.error = 'The workspace file is not valid JSON.'
  } finally {
    workspaceReplacementPending.value = false
    await nextTick()
  }
}

function openAlertsTool() {
  const alerts = OPENABLE_WORKSTATION_TOOLS.find(tool => tool.tool_type === 'alerts')
  if (alerts) openTool(alerts)
}

type MapAnalysisPublication = {
  target: 'breadth' | 'study_lab'
  sourceId: string
  selectedIds: number[]
  selectedSymbols: string[]
  scope: 'full' | 'selection'
}

async function publishMapAnalysis(publication: MapAnalysisPublication) {
  if (!publication.sourceId) return
  // Let the source tool's selection/layout event settle before switching the
  // destination. This avoids applying the publication to a stale Golden Layout
  // root when the handoff follows a selection click in the same turn.
  await nextTick()
  const analysisSource = resolveMarketMapAnalysisSource({
    sourceId: publication.sourceId,
    scope: publication.scope,
    selectedIds: publication.selectedIds,
  })
  if (analysisSource.error) {
    workspaceStore.error = analysisSource.error
    return
  }
  const analysisSourceId = analysisSource.sourceId
  const selectedConfiguration = {
    source_id: publication.sourceId,
    analysis_source_id: analysisSourceId,
    analysis_scope: analysisSource.scope,
    selected_member_ids: [...publication.selectedIds],
    selected_member_symbols: [...publication.selectedSymbols],
    publication_origin: 'market_map',
  }
  if (publication.target === 'breadth') {
    // The factory breadth surface predates the generic tool registry and is keyed as
    // `breadth-summary` while its rendered component still uses the breadth contract.
    // Treat both identities as the same destination so Market Map publication cannot
    // silently update a hidden generic instance while the visible factory surface stays
    // on its previous group universe.
    const breadthCandidates = (workspaceStore.workspace?.tabs ?? []).flatMap(tab => tab.windows
      .filter(window => window.tool_type === 'breadth' || window.instance_key === 'breadth-summary' || window.instance_key.startsWith('breadth-'))
      .map(window => ({ tab, window })))
    const existing = breadthCandidates.find(candidate => candidate.tab.stable_key === workspaceStore.activeTabKey) ?? breadthCandidates[0]
    if (existing) {
      if (workspaceStore.activeTabKey !== existing.tab.stable_key) selectWorkspaceTab(existing.tab.stable_key)
      workspaceStore.setActiveWindow(existing.window.instance_key)
      await nextTick()
      const mountedConfiguration = existing.window.configuration
      const publishedConfiguration = {
        ...existing.window.configuration,
        custom_universe_kind: 'watchlist',
        custom_universe_watchlist_id: analysisSourceId,
        ...selectedConfiguration,
      }
      updateToolConfiguration(existing.window.instance_key, publishedConfiguration)
      await workspaceStore.saveSnapshot()
      // saveSnapshot replaces the canonical workspace object with the server
      // response. Golden Layout may still hold the pre-save tool object, so
      // mirror the accepted configuration into that mounted object as well.
      for (const key of Object.keys(mountedConfiguration)) delete mountedConfiguration[key]
      Object.assign(mountedConfiguration, publishedConfiguration)
      // A snapshot replacement can leave Golden Layout's virtual root bound
      // to the pre-save object. Reinstall this completed layout from the
      // server-confirmed workspace so the visible breadth controls and the
      // persisted configuration cannot diverge.
      workspaceReloadKey.value += 1
      await nextTick()
      return
    }
    const definition = OPENABLE_WORKSTATION_TOOLS.find(tool => tool.tool_type === 'breadth')
    if (!definition) return
    const opened = await openTool(definition, {
      custom_universe_kind: 'watchlist',
      custom_universe_watchlist_id: analysisSourceId,
      ...selectedConfiguration,
    })
    if (!opened) return
    return
  }

  const studyCandidates = (workspaceStore.workspace?.tabs ?? []).flatMap(tab => tab.windows
    .filter(window => window.tool_type === 'study_lab')
    .map(window => ({ tab, window })))
  const existing = studyCandidates.find(candidate => candidate.tab.stable_key === workspaceStore.activeTabKey) ?? studyCandidates[0]
  if (existing) {
    if (workspaceStore.activeTabKey !== existing.tab.stable_key) selectWorkspaceTab(existing.tab.stable_key)
    workspaceStore.setActiveWindow(existing.window.instance_key)
    updateToolConfiguration(existing.window.instance_key, {
      ...existing.window.configuration,
      source_id: publication.sourceId,
      universe_source_id: analysisSourceId,
      selected_member_ids: [...publication.selectedIds],
      selected_member_symbols: [...publication.selectedSymbols],
      analysis_source_id: analysisSourceId,
      analysis_scope: analysisSource.scope,
      publication_origin: 'market_map',
    })
    return
  }
  const definition = OPENABLE_WORKSTATION_TOOLS.find(tool => tool.tool_type === 'study_lab')
  if (!definition) return
  const opened = await openTool(definition, {
    source_id: publication.sourceId,
    universe_source_id: analysisSourceId,
    selected_member_ids: [...publication.selectedIds],
    selected_member_symbols: [...publication.selectedSymbols],
    analysis_source_id: analysisSourceId,
    analysis_scope: analysisSource.scope,
    publication_origin: 'market_map',
  })
  if (!opened) return
}

function updateLinkGroup(windowKey: string, group: LinkGroup, displayedSymbol?: string) {
  workspaceStore.updateToolLinkGroup(windowKey, group, displayedSymbol)
}

function patchToolConfiguration(windowKey: string, patch: Record<string, unknown>) {
  const windowState = workspaceStore.activeTab?.windows.find(window => window.instance_key === windowKey)
  if (!windowState) return
  // Golden Layout keeps the mounted virtual tool alive while workspace state
  // changes. Mutating the existing reactive configuration preserves the object
  // identity observed by that tool; replacing it would persist the setting but
  // leave the visible editor/render tree on the previous configuration.
  Object.assign(windowState.configuration, patch)
  workspaceStore.scheduleSnapshot()
}

function updateColumns(windowKey: string, columnKeys: string[]) {
  patchToolConfiguration(windowKey, { column_keys: columnKeys })
}
function updateFilter(windowKey: string, filterText: string) {
  patchToolConfiguration(windowKey, { filter_text: filterText })
}
function updateConditionFilter(windowKey: string, screenerId: number | null) {
  patchToolConfiguration(windowKey, { condition_screener_id: screenerId })
}
function updateConditionFilterMode(windowKey: string, mode: 'active' | 'inactive' | 'off') {
  patchToolConfiguration(windowKey, { condition_filter_mode: mode })
}
function updatePinnedBooleanKeys(windowKey: string, keys: string[]) {
  patchToolConfiguration(windowKey, { pinned_boolean_keys: keys })
}
function updateColumnGroups(windowKey: string, groups: Record<string, string>) {
  patchToolConfiguration(windowKey, { column_groups: groups })
}
function updateStackedColumnKeys(windowKey: string, keys: string[]) {
  patchToolConfiguration(windowKey, { stacked_column_keys: keys })
}
function updateToolConfiguration(windowKey: string, configuration: Record<string, unknown>) {
  // Publication/open actions may switch tabs immediately before applying a
  // configuration. Golden Layout can update the active-tab pointer on the next
  // reactive turn, so searching only activeTab can silently patch nothing (or
  // leave the visible tool on its previous universe). Window instance keys are
  // globally unique within a workspace; resolve the canonical record across
  // all tabs and preserve its reactive configuration object for the mounted
  // virtual tool.
  const windowState = workspaceStore.workspace?.tabs
    .flatMap(tab => tab.windows)
    .find(window => window.instance_key === windowKey)
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

async function openMarketMapRatio(symbols: string[]) {
  const normalized = [...new Set(symbols.map(symbol => symbol.trim().toUpperCase()).filter(Boolean))].slice(0, 2)
  const numerator = normalized[0]
  const denominator = normalized[1] ?? activeSymbol.value.trim().toUpperCase()
  if (!numerator || !denominator || numerator === denominator) {
    workspaceStore.error = 'Select a different member or two members to create a relative-strength ratio.'
    return
  }
  const ratio = workspaceStore.activeTab?.windows.find(window => window.instance_key === 'ratio-chart')
  if (!ratio) {
    workspaceStore.error = 'Open a Relative Strength tool to create a ratio.'
    return
  }
  // Activate the canonical ratio window before publishing its configuration.
  // Golden Layout can emit a trailing layout snapshot during activation; doing
  // this first prevents that observational snapshot from restoring the old
  // expression over the user-requested ratio.
  workspaceStore.setActiveWindow(ratio.instance_key)
  await nextTick()
  const mountedConfiguration = ratio.configuration
  const publishedConfiguration = {
    ...ratio.configuration,
    expression: `=${numerator}/${denominator}`,
    auto_ratio: false,
  }
  updateToolConfiguration(ratio.instance_key, publishedConfiguration)
  await workspaceStore.saveSnapshot()
  for (const key of Object.keys(mountedConfiguration)) delete mountedConfiguration[key]
  Object.assign(mountedConfiguration, publishedConfiguration)
}

async function handleRowAction(action: 'chart' | 'compare' | 'ratio' | 'note' | 'alert' | 'copy', row: { symbol: string; instrumentId: number | null }) {
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
  if (action === 'ratio') {
    const numerator = row.symbol.trim().toUpperCase()
    const denominator = activeSymbol.value.trim().toUpperCase()
    if (!numerator || !denominator || numerator === denominator) {
      workspaceStore.error = 'Choose a different symbol to create a relative-strength ratio.'
      return
    }
    const ratio = workspaceStore.activeTab?.windows.find(window => window.instance_key === 'ratio-chart')
    if (!ratio) {
      workspaceStore.error = 'Open a Relative Strength tool to create a ratio.'
      return
    }
    workspaceStore.setActiveWindow(ratio.instance_key)
    await nextTick()
    const mountedConfiguration = ratio.configuration
    const publishedConfiguration = {
      ...ratio.configuration,
      expression: `=${numerator}/${denominator}`,
      auto_ratio: false,
    }
    updateToolConfiguration(ratio.instance_key, publishedConfiguration)
    await workspaceStore.saveSnapshot()
    for (const key of Object.keys(mountedConfiguration)) delete mountedConfiguration[key]
    Object.assign(mountedConfiguration, publishedConfiguration)
    return
  }
  await selectSymbol(row.symbol, undefined, false, row.instrumentId)
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
  const tool = workspaceStore.workspace?.tabs.flatMap(item => item.windows).find(item => item.instance_key === windowKey)
  const popup = window.open(href, `workstation-${windowKey}`, popoutWindowFeatures(readPopoutGeometry(tool?.style, window.screen as Screen & { availLeft?: number; availTop?: number })))
  if (!popup) {
    workspaceStore.error = 'Browser blocked the pop-out. The tool remains docked.'
    return
  }
  // Record the requested geometry immediately. The browser-reported outer
  // bounds may not be readable until the popup has painted, and the debounced
  // poll below is intentionally only a refinement of this deterministic
  // initial placement.
  const initialGeometry = readPopoutGeometry(tool?.style, window.screen as Screen & { availLeft?: number; availTop?: number })
  const persisted = workspaceStore.updateToolStyle(windowKey, { popout: initialGeometry })
  // Popup creation must remain synchronous to survive browser popup blocking.
  // Once the child exists, use the optional Window Management API to recover a
  // saved placement whose monitor has disappeared. If permission/API support is
  // absent, leave persisted coordinates untouched so valid secondary-monitor
  // placements are never moved based on a single-screen guess.
  void reconcilePopoutPlacement(windowKey, popup, initialGeometry)
  // Do not leave the first pop-out placement behind the normal debounce: the
  // popup immediately performs its own workspace read and may otherwise race
  // the pending snapshot, especially when several windows are being opened.
  void (async () => {
    for (let attempt = 0; attempt < 3; attempt += 1) {
      if (attempt > 0 || !persisted) {
        // A concurrent cross-window revision can replace the local workspace
        // between the button click and this handler. Rehydrate, then apply the
        // geometry against the current canonical window record.
        await workspaceStore.loadDefault()
        workspaceStore.updateToolStyle(windowKey, { popout: initialGeometry })
      }
      await workspaceStore.saveSnapshot()
      const savedTool = workspaceStore.workspace?.tabs
        .flatMap(tab => tab.windows)
        .find(candidate => candidate.instance_key === windowKey)
      const savedGeometry = savedTool?.style?.popout
      if (savedGeometry && typeof savedGeometry === 'object') return
    }
  })()
  const previous = popoutGeometryPollers.get(windowKey)
  if (previous) window.clearInterval(previous)
  const poll = window.setInterval(() => {
    try {
      if (popup.closed) {
        window.clearInterval(poll)
        popoutGeometryPollers.delete(windowKey)
        return
      }
      const geometry = capturePopoutGeometry(popup)
      if (geometry) workspaceStore.updateToolStyle(windowKey, { popout: geometry })
    } catch {
      window.clearInterval(poll)
      popoutGeometryPollers.delete(windowKey)
    }
  }, 1000)
  popoutGeometryPollers.set(windowKey, poll)
}

async function reconcilePopoutPlacement(windowKey: string, popup: Window, initialGeometry: ReturnType<typeof readPopoutGeometry>) {
  const host = window as Window & {
    getScreenDetails?: () => Promise<{ screens?: Array<PopoutScreen> }>
  }
  const screenState = window.screen as Screen & { isExtended?: boolean }
  if (screenState.isExtended !== true || typeof host.getScreenDetails !== 'function') return
  try {
    const details = await host.getScreenDetails()
    const screens = Array.isArray(details?.screens) ? details.screens : []
    const fallbackScreen = screenState as unknown as PopoutScreen
    const recovered = recoverPopoutGeometry({ popout: initialGeometry }, screens, fallbackScreen)
    if (recovered.left === initialGeometry.left
      && recovered.top === initialGeometry.top
      && recovered.width === initialGeometry.width
      && recovered.height === initialGeometry.height) return
    if (popup.closed) return
    popup.moveTo(recovered.left, recovered.top)
    popup.resizeTo(recovered.width, recovered.height)
    workspaceStore.updateToolStyle(windowKey, { popout: recovered })
    await workspaceStore.saveSnapshot()
  } catch {
    // Window Management permission is optional and browser support is uneven.
    // The persisted geometry and normal bounds poll remain the recovery path.
  }
}

function renderDockTool(dockTool: { instance_key: string; title: string; tool_type: string }, actions: { toggleMaximize: () => void; close: () => void }): VNode {
  const tool = workspaceStore.activeTab?.windows.find(window => window.instance_key === dockTool.instance_key)
  if (!tool) return h('div', { class: 'workstation__missing-tool' }, `Missing persisted tool: ${dockTool.instance_key}`)
  return h(WorkstationToolContent, {
    tool,
    activeWindowKey: workspaceStore.activeTab?.active_window_key,
    factoryLayout: workspaceStore.activeTabKey,
    onSelect: (symbol: string, instrumentId?: number | null) => void selectSymbol(symbol, undefined, false, instrumentId),
    onCompare: (symbols: string[]) => compareSymbols(symbols),
    onRatio: (symbols: string[]) => void openMarketMapRatio(symbols),
    onReorder: (watchlistId: number, itemIds: number[]) => reorderWatchlistItems(watchlistId, itemIds),
    onRowAction: (action: 'chart' | 'compare' | 'ratio' | 'note' | 'alert' | 'copy', row: { symbol: string; instrumentId: number | null }) => void handleRowAction(action, row),
    onMarketMap: (sourceId: string) => void openMarketMap(sourceId),
    onOccurrence: (symbol: string, timestamp: string, instrumentId?: number | null) => void selectSymbol(symbol, timestamp, false, instrumentId),
    onSelectIndustry: (industry: string, etf: string) => selectIndustryForContext(industry, etf),
    onSelectProxy: (symbol: string, instrumentId?: number | null) => void selectIndustryProxy(symbol, instrumentId),
    onColumns: (windowKey: string, keys: string[]) => updateColumns(windowKey, keys),
    onFilter: (windowKey: string, value: string) => updateFilter(windowKey, value),
    onConditionFilter: (windowKey: string, screenerId: number | null) => updateConditionFilter(windowKey, screenerId),
    onConditionFilterMode: (windowKey: string, mode: 'active' | 'inactive' | 'off') => updateConditionFilterMode(windowKey, mode),
    onPinnedBooleanKeys: (windowKey: string, keys: string[]) => updatePinnedBooleanKeys(windowKey, keys),
    onColumnGroups: (windowKey: string, groups: Record<string, string>) => updateColumnGroups(windowKey, groups),
    onStackedColumnKeys: (windowKey: string, keys: string[]) => updateStackedColumnKeys(windowKey, keys),
    onConfiguration: (windowKey: string, configuration: Record<string, unknown>) => updateToolConfiguration(windowKey, configuration),
    onPublishAnalysis: (publication: MapAnalysisPublication) => void publishMapAnalysis(publication),
    onTimeframe: (timeframe: string, group: LinkGroup) => setLinkedTimeframe(timeframe, group),
    onFloat: (windowKey: string) => floatTool(windowKey),
    onMaximize: () => actions.toggleMaximize(),
    onClose: () => {
      // The layout host removes the component through a filtered serializable
      // tree and tears down Golden Layout before emitting the new layout. That
      // avoids the library's live-stack resize race while keeping the store's
      // close guard (a workspace must retain one tool) authoritative.
      if (workspaceStore.closeTool(dockTool.instance_key)) actions.close()
    },
    onUpdateLinkGroup: (windowKey: string, group: LinkGroup, displayedSymbol?: string) => updateLinkGroup(windowKey, group, displayedSymbol),
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
  workspaceReplacementPending.value = true
  // Golden Layout owns detached Vue roots. Flush the withdrawal before the
  // server reset so a fast response cannot batch the pending=true and
  // reload=false transitions into one render and leave an old root alive.
  await nextTick()
  try {
    if (await workspaceStore.resetFactoryWorkspace()) {
      workspaceReloadKey.value += 1
      // Let the host recreate its virtual roots from the replacement snapshot
      // before exposing the workstation to the next interaction.
      await nextTick()
    }
  } finally {
    workspaceReplacementPending.value = false
    await nextTick()
  }
}

async function createWorkspace() { await workspaceStore.createWorkspace('New Workspace') }
async function cloneWorkspace() { await workspaceStore.cloneWorkspace() }
async function renameWorkspace() {
  const current = workspaceStore.workspace
  if (!current) return
  const name = window.prompt('Workspace name', current.name)
  if (name != null) await workspaceStore.renameWorkspace(name)
}
async function deleteWorkspace() {
  const current = workspaceStore.workspace
  if (!current || current.is_default) return
  if (window.confirm(`Delete workspace “${current.name}”?`)) await workspaceStore.deleteCurrentWorkspace()
}

function handleKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') {
    closeSymbolSearch()
    recentSymbolsOpen.value = false
    workspaceMenuOpen.value = false
    toolLibraryOpen.value = false
    keyboardHelpOpen.value = false
    syncShellMenuListeners()
    return
  }
  if (workspaceStore.isEditorTarget(event.target)) return
  if (event.key === 'F1' || event.key === '?') {
    event.preventDefault()
    closeShellMenus('help')
    closeSymbolSearch()
    keyboardHelpOpen.value = true
    return
  }
  if (/^[a-z0-9.=]$/i.test(event.key) && !event.ctrlKey && !event.metaKey && !event.altKey) {
    event.preventDefault()
    symbolInput.value?.focus()
    symbolSearchEnabled.value = true
    symbolDraft.value = event.key.toUpperCase()
    return
  }
  if (event.key !== ' ' || event.ctrlKey || event.metaKey || event.altKey) return
  event.preventDefault()
  if (!allSymbols.value.length) return
  // Explicit shell actions publish the draft synchronously, while the shared
  // blue-link store can briefly lag during initial workspace hydration. The
  // draft is therefore the authoritative traversal anchor when it names a
  // loaded symbol; falling back to the link keeps linked-window selections
  // traversable when no shell draft is available.
  const draftSymbol = symbolDraft.value.trim().toUpperCase()
  const currentSymbol = allSymbols.value.includes(draftSymbol) ? draftSymbol : activeSymbol.value
  const currentIndex = allSymbols.value.indexOf(currentSymbol)
  const nextIndex = (currentIndex + (event.shiftKey ? -1 : 1) + allSymbols.value.length) % allSymbols.value.length
  void selectSymbol(allSymbols.value[nextIndex], undefined, true)
}

// Escape is a workstation-wide command. Handle it during capture so nested
// listboxes, editors, and menu roots cannot stop propagation before transient
// shell surfaces are dismissed. The focused child still receives the normal
// focus recovery scheduled by closeShellMenuToTrigger where applicable.
function handleGlobalKeydownCapture(event: KeyboardEvent) {
  if (event.key !== 'Escape') return
  const hasTransientShell = recentSymbolsOpen.value || workspaceMenuOpen.value
    || toolLibraryOpen.value || keyboardHelpOpen.value
  if (!hasTransientShell) return
  event.preventDefault()
  event.stopPropagation()
  const active = document.activeElement
  const activeMenu = active instanceof Element
    ? (Object.entries(shellMenuRoots).find(([, root]) => root.value?.contains(active))?.[0] as ShellMenuRoot | undefined)
    : undefined
  const openMenu: ShellMenuRoot | undefined = activeMenu
    ?? (workspaceMenuOpen.value ? 'workspace' : toolLibraryOpen.value ? 'tool-library' : keyboardHelpOpen.value ? 'help' : recentSymbolsOpen.value ? 'recent' : undefined)
  closeSymbolSearch()
  recentSymbolsOpen.value = false
  workspaceMenuOpen.value = false
  toolLibraryOpen.value = false
  keyboardHelpOpen.value = false
  syncShellMenuListeners()
  if (openMenu) void nextTick(() => shellMenuTriggers[openMenu].value?.focus())
}

function handleWheel(event: WheelEvent) {
  if (handledWheelEvents.has(event)) return
  handledWheelEvents.add(event)
  // Ctrl+wheel is an explicit symbol-traversal gesture; unlike typed shortcuts
  // it remains usable while the active-symbol control retains focus after Go.
  const controlPressed = event.ctrlKey || ctrlWheelHeld.value || event.getModifierState?.('Control') === true
  if (!controlPressed || event.metaKey || event.altKey) return
  event.preventDefault()
  if (!allSymbols.value.length) return
  // The shell input is updated synchronously by an explicit Go action while
  // the canonical store publication completes asynchronously. Use the draft
  // as a short-lived fallback so an immediate wheel gesture cannot select SPY
  // again simply because the store has not hydrated the same symbol yet.
  const currentSymbol = activeSymbol.value || symbolDraft.value.trim().toUpperCase()
  const currentIndex = allSymbols.value.indexOf(currentSymbol)
  const direction = event.deltaY > 0 ? 1 : -1
  let nextIndex = (currentIndex + direction + allSymbols.value.length) % allSymbols.value.length
  // A partially hydrated symbol can temporarily be absent from the list. Do
  // not turn a traversal gesture into a no-op in that case; advance once more
  // through the canonical fallback universe.
  if (allSymbols.value.length > 1 && allSymbols.value[nextIndex] === activeSymbol.value) {
    nextIndex = (nextIndex + direction + allSymbols.value.length) % allSymbols.value.length
  }
  void selectSymbol(allSymbols.value[nextIndex], undefined, true)
}

watch(activeSymbol, symbol => {
  if (!symbol) return
  recentStore.add(symbol)
  // Linked row selections can arrive through the workspace bus before the shell's
  // async symbol handler resumes. Keep the auto-ratio tool tied to the newest
  // published symbol at this boundary as well as in the explicit selection path.
  updateAutoRatioExpression(symbol)
  // Selections made by linked watchlists, pop-outs, or another browser window
  // publish through the workspace bus rather than through the shell input.
  // Keep the active-symbol entry authoritative for those paths too, while
  // suppressing the search request that is only intended for user typing.
  const preserveDraft = preserveActiveUserSymbolDraft(symbol)
  // A late route/linked-symbol publication must not tear down a newer user
  // search intent. Keep the combobox, debounce, and results alive while the
  // user is editing a different symbol; only synchronize the shell for a
  // publication that is not competing with an active draft.
  if (!preserveDraft) {
    closeSymbolSearch()
    symbolDraft.value = symbol
  }
  const preserveDrilldown = preserveDrilldownSymbol.value === symbol
  if (preserveDrilldown) preserveDrilldownSymbol.value = null
  if (chartStore.symbol === symbol) return
  if (!documentVisible.value) return
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
watch(() => workspaceStore.workspace?.id, (workspaceId, previousWorkspaceId) => {
  if (workspaceId && previousWorkspaceId && workspaceId !== previousWorkspaceId) {
    void replaceDockAfterWorkspaceChange()
  }
})

onMounted(async () => {
  const mountSelectionGeneration = symbolSelectionGeneration
  // Capture before chart/uPlot gesture handlers can stop propagation. The
  // workstation-level Ctrl+wheel traversal is a shell command and must remain
  // available even when the pointer is over a chart canvas.
  window.addEventListener('wheel', handleWheel, { passive: false, capture: true })
  const handleModifierKeydown = (event: KeyboardEvent) => {
    if (event.key === 'Control') ctrlWheelHeld.value = true
  }
  const handleModifierKeyup = (event: KeyboardEvent) => {
    if (event.key === 'Control') ctrlWheelHeld.value = false
  }
  window.addEventListener('keydown', handleModifierKeydown)
  window.addEventListener('keyup', handleModifierKeyup)
  const handleVisibilityChange = () => {
    documentVisible.value = document.visibilityState === 'visible'
    if (documentVisible.value && !isPopout.value) {
      void marketAnalysisQuery.refetch()
      void loadSymbolData(activeSymbol.value, workspaceStore.constituentETF, false)
    }
  }
  document.addEventListener('visibilitychange', handleVisibilityChange)
  removeVisibilityListener = () => {
    document.removeEventListener('visibilitychange', handleVisibilityChange)
    window.removeEventListener('keydown', handleModifierKeydown)
    window.removeEventListener('keyup', handleModifierKeyup)
  }
  workspaceStore.connect()
  workspaceLoadPromise = workspaceStore.loadDefault()
  try {
    await workspaceLoadPromise
  } finally {
    workspaceReady.value = true
    resolveWorkspaceReady?.()
    resolveWorkspaceReady = null
  }
  // A user can interact with the shell while the first snapshot is loading.
  // loadDefault hydrates the persisted blue link, so replay the newer explicit
  // shell selection once hydration completes instead of silently reverting it.
  // Search-only typing is intentionally excluded: an unsubmitted editor draft
  // must never publish a symbol merely because the workspace finished loading.
  if (symbolSelectionGeneration !== mountSelectionGeneration && !symbolSearchEnabled.value) {
    const explicitSymbol = symbolDraft.value.trim().toUpperCase()
    if (explicitSymbol && explicitSymbol !== activeSymbol.value) {
      await selectSymbol(explicitSymbol, undefined, true)
    }
  }
  const requestedTab = typeof route.query.tab === 'string' ? route.query.tab : null
  if (requestedTab && workspaceStore.workspace?.tabs.some(tab => tab.stable_key === requestedTab)) {
    workspaceStore.activeTabKey = requestedTab
  }
  // A second browser pop-out can start while the first window is announcing a
  // revisioned workspace snapshot. If that narrow race returns a stale snapshot
  // without the requested tool, retry the canonical read once before rendering
  // the honest unavailable-tool recovery state.
  if (isPopout.value && !popoutTool.value) {
    // A source window may still be settling a revisioned snapshot when the
    // browser popup starts. Retry the canonical read for a bounded interval so
    // a transient stale snapshot does not leave a black, empty pop-out.
    for (let attempt = 0; attempt < 5 && !popoutTool.value; attempt += 1) {
      await new Promise(resolve => window.setTimeout(resolve, 200))
      await workspaceStore.loadDefault()
      if (requestedTab && workspaceStore.workspace?.tabs.some(tab => tab.stable_key === requestedTab)) {
        workspaceStore.activeTabKey = requestedTab
      }
    }
  }
  await refreshMarketData()
  if (isPopout.value && popoutTool.value) {
    const tool = popoutTool.value
    const configuredSymbol = typeof tool.configuration.symbol === 'string' ? tool.configuration.symbol : null
    const linked = workspaceStore.symbolForLinkGroup(tool.link_group, configuredSymbol)
    await loadSymbolData(linked, workspaceStore.constituentETF, false)
  } else {
    const explicitRouteSymbol = route.params.symbol ?? route.query.symbol
    // A plain /chart navigation restores the persisted workstation symbol; it
    // must not silently reset a user who is already drilled into a sector while
    // the layout/data refresh is completing. Explicit deep-links still win.
    const requested = String(explicitRouteSymbol ?? activeSymbol.value ?? 'SPY')
    // Route hydration can take long enough for the user to type/press Go or
    // traverse with Ctrl+wheel first. Never let that late initial selection
    // overwrite a newer user intent.
    if (symbolSelectionGeneration === mountSelectionGeneration) {
      // Route deep-links for the canonical benchmark universe must remain
      // usable even when metadata/search is temporarily unavailable. The
      // navigation fallback keeps the visible symbol deterministic while the
      // chart and technical tools report their honest freshness/error state.
      await selectSymbol(requested, undefined, true)
    }
  }
  await nextTick()
  if (!isPopout.value) await refreshMarketData()

})

onBeforeUnmount(() => {
  endTabDrag()
  window.removeEventListener('wheel', handleWheel, { capture: true })
  ctrlWheelHeld.value = false
  for (const poll of popoutGeometryPollers.values()) window.clearInterval(poll)
  popoutGeometryPollers.clear()
  removeVisibilityListener?.()
  removeVisibilityListener = null
  if (searchTimer) clearTimeout(searchTimer)
  workspaceStore.disconnect()
  removeShellMenuListeners()
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
.workstation__workspace-popover { position: fixed; z-index: 150; padding: 5px; border: 1px solid #4d5a63; background: #151d23; box-shadow: 0 7px 18px #000b; color: #cbd6dc; overflow: auto; }
.workstation__help-menu { position: relative; display: flex; align-items: stretch; }
.workstation__help-popover { position: fixed; z-index: 150; padding: 5px; border: 1px solid #4d5a63; background: #151d23; box-shadow: 0 7px 18px #000b; color: #cbd6dc; overflow: auto; }
.workstation__help-popover header { display: flex; justify-content: space-between; align-items: center; padding: 3px 4px 5px; border-bottom: 1px solid #29343b; font-size: 11px; }
.workstation__help-popover header button { border: 0; color: #aebbc4; background: transparent; cursor: pointer; font: 13px/1 "Segoe UI",Arial,sans-serif; padding: 0 2px; }
.workstation__help-popover dl { display: grid; gap: 3px; margin: 5px 0; }
.workstation__help-popover dl div { display: grid; grid-template-columns: 82px minmax(0,1fr); gap: 7px; padding: 2px 3px; }
.workstation__help-popover dt { color: #e4f1f7; font-weight: 700; }
.workstation__help-popover dd { margin: 0; color: #aebbc4; }
.workstation__help-popover > small { display: block; padding: 4px 3px 2px; border-top: 1px solid #29343b; color: #81909a; line-height: 1.35; }
.workstation__workspace-popover header { display: flex; justify-content: space-between; align-items: baseline; padding: 3px 4px 5px; border-bottom: 1px solid #29343b; font-size: 11px; }.workstation__workspace-popover header small { color: #81909a; font-size: 9px; }
.workstation__workspace-list { display: grid; gap: 2px; max-height: 112px; overflow: auto; padding: 4px 0; border-bottom: 1px solid #29343b; }.workstation__workspace-list button { display: flex; justify-content: space-between; gap: 8px; border: 1px solid transparent; background: transparent; color: #aebbc4; padding: 3px 4px; text-align: left; font: 10px "Segoe UI",Arial,sans-serif; cursor: pointer; }.workstation__workspace-list button:hover,.workstation__workspace-list button[aria-selected="true"] { border-color: #3e505c; background: #202b32; color: #f1f7fa; }.workstation__workspace-list small { color: #81909a; font-size: 9px; }
.workstation__workspace-actions { display: flex; gap: 3px; padding: 5px 2px; border-bottom: 1px solid #29343b; }.workstation__workspace-actions button,.workstation__layout-reset { border: 1px solid #42505a; background: #202b32; color: #cbd6dc; padding: 3px 6px; font: 10px "Segoe UI",Arial,sans-serif; cursor: pointer; }.workstation__workspace-actions button:hover,.workstation__layout-reset:hover { background: #31424d; color: #fff; }.workstation__workspace-file { display: none; }
.workstation__layout-list { display: grid; gap: 2px; max-height: 250px; overflow: auto; padding: 4px 0; }.workstation__layout-item { display: grid; grid-template-columns: minmax(72px, 1fr) 112px 20px; gap: 3px; align-items: center; padding: 2px; border: 1px solid transparent; }.workstation__layout-item:hover { border-color: #3e505c; }.workstation__layout-select { overflow: hidden; border: 0; background: transparent; color: #aebbc4; text-align: left; text-overflow: ellipsis; white-space: nowrap; cursor: pointer; font: 10px "Segoe UI",Arial,sans-serif; }.workstation__layout-select.active { color: #eaf2f6; font-weight: 700; }.workstation__layout-item input { min-width: 0; border: 1px solid #3b4850; background: #11161a; color: #bfcbd3; padding: 2px 3px; font: 10px "Segoe UI",Arial,sans-serif; }.workstation__layout-delete { border: 0; background: transparent; color: #d78989; cursor: pointer; }.workstation__layout-delete:disabled { color: #5e686e; cursor: not-allowed; }.workstation__layout-reset { width: 100%; margin-top: 2px; }
.workstation__menu nav button, .workstation__tab-add, .workstation__tab-reset { border: 0; background: transparent; color: #d4d9dd; padding: 0 8px; font: 11px "Segoe UI", Arial, sans-serif; cursor: pointer; }
.workstation__menu nav button:hover, .workstation__tab-add:hover, .workstation__tab-reset:hover { background: #3a444d; color: #fff; }
.workstation__search { position: relative; display: flex; height: 21px; margin-left: 10px; }
.workstation__search input { width: 88px; padding: 0 5px; border: 1px solid #4d5a63; background: #11161a; color: #f1f5f7; font: 11px "Segoe UI", Arial, sans-serif; text-transform: uppercase; }
.workstation__search button { border: 1px solid #4d5a63; border-left: 0; background: #26333d; color: #dce9f2; padding: 0 7px; font-size: 10px; cursor: pointer; }
.workstation__search button:disabled { color: #62717a; background: #1b2329; cursor: not-allowed; }
.workstation__history-button { min-width: 20px; padding: 0 4px!important; }
.workstation__recent-symbols { position: fixed; z-index: 140; display: grid; min-width: 220px; max-width: 280px; overflow: auto; border: 1px solid #4d5a63; background: #151d23; box-shadow: 0 6px 16px #000b; }
.workstation__recent-symbols header { display: flex; align-items: center; justify-content: space-between; padding: 4px 6px; border-bottom: 1px solid #29343b; color: #aebbc4; font: 10px "Segoe UI", Arial, sans-serif; }
.workstation__recent-symbols header button { border: 0; padding: 1px 3px; color: #9fb5c2; background: transparent; font: inherit; cursor: pointer; }
.workstation__recent-symbols > button { display: grid; grid-template-columns: 52px minmax(0, 1fr); gap: 6px; min-height: 24px; padding: 3px 6px; border: 0; border-bottom: 1px solid #29343b; background: transparent; color: #bfcbd3; font: 10px "Segoe UI", Arial, sans-serif; text-align: left; cursor: pointer; }
.workstation__recent-symbols > button:hover, .workstation__recent-symbols > button:focus-visible { background: #2c4554; color: #fff; outline: none; }
.workstation__recent-symbols > button strong { color: #e4f1f7; }.workstation__recent-symbols > button span { overflow: hidden; color: #8799a5; text-overflow: ellipsis; white-space: nowrap; }
.workstation__symbol-results { position: absolute; z-index: 130; top: 23px; left: 0; display: grid; min-width: 270px; max-height: 250px; overflow: auto; border: 1px solid #4d5a63; background: #151d23; box-shadow: 0 6px 16px #000b; }
.workstation__symbol-results button { display: grid; grid-template-columns: 55px minmax(0, 1fr) 48px; gap: 6px; align-items: center; min-height: 25px; padding: 3px 6px; border: 0; border-bottom: 1px solid #29343b; background: transparent; color: #bfcbd3; font: 10px "Segoe UI", Arial, sans-serif; text-align: left; }
.workstation__symbol-results button:hover, .workstation__symbol-results button[aria-selected="true"] { background: #2c4554; color: #fff; }
.workstation__symbol-results strong { color: #e4f1f7; }.workstation__symbol-results span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }.workstation__symbol-results small { color: #8799a5; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.workstation__symbol-search-message { min-width: 270px; padding: 7px 8px; border-top: 1px solid #29343b; color: #93a5af; font: 10px "Segoe UI", Arial, sans-serif; }
.workstation__symbol-search-message--error { color: #e4a0a0; }
.workstation__symbol-search-state { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); clip-path: inset(50%); white-space: nowrap; }
.workstation__status { margin-left: auto; display: flex; align-items: center; gap: 8px; color: #81909a; font-size: 10px; }
.workstation__refresh,.workstation__sign-out { border: 1px solid #47545d; background: #20282e; color: #bdc9d1; padding: 2px 6px; font: inherit; cursor: pointer; }
.workstation__refresh:disabled { cursor: wait; opacity: .65; }
.workstation__refresh:hover:not(:disabled),
.workstation__sign-out:hover { border-color: #6d8290; color: #fff; background: #33414a; }
.workstation__leader { color: #63bd85; }
.workstation__data-state--fetching { color:#80bce8; }.workstation__data-state--unavailable { color:#ed9696; }.workstation__data-state--current { color:#91d5a7; }.workstation__data-state--delayed,.workstation__data-state--stale { color:#e8c06b; }.workstation__data-state--partial,.workstation__data-state--coverage-limited { color:#e8b879; }
.workstation__tabs { display: flex; align-items: stretch; background: var(--tc-panel-bg); border-bottom: 1px solid var(--tc-border); }
.workstation__tool-library { position: relative; display: flex; }
.workstation__tool-library-menu { position: fixed; z-index: 60; display: grid; min-width: 118px; padding: 2px; border: 1px solid #42505a; background: #1b2228; box-shadow: 0 3px 10px #000a; overflow: auto; }
.workstation__tool-library-menu button { border: 0; background: transparent; color: #cbd6dc; padding: 5px 8px; font: 11px "Segoe UI", Arial, sans-serif; text-align: left; cursor: pointer; }
.workstation__tool-library-menu button:hover { background: #31424d; color: #fff; }
.workstation__tabs > button:not(.workstation__tab-add) { min-width: 112px; padding: 0 11px; border: 0; border-right: 1px solid #303940; background: #1b2126; color: #9facb5; font: 11px "Segoe UI", Arial, sans-serif; cursor: grab; }
.workstation__tabs > button:not(.workstation__tab-add):active { cursor: grabbing; }
.workstation__tabs > button.workstation__tab--active { background: #28333b; color: #eaf2f6; box-shadow: inset 0 2px #68b6e9; }
.workstation__tabs > button.workstation__tab--drag-over { box-shadow: inset 2px 0 #f0c66d, inset -2px 0 #f0c66d; }
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
