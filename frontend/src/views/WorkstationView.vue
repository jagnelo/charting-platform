<template>
  <div class="workstation" tabindex="0" @keydown.capture="handleGlobalKeydownCapture" @keydown="handleKeydown" @wheel.capture="handleWheel" @pointerdown.capture="handleWorkstationPointerDown" @focusin.capture="handleWorkstationFocusIn" @change.capture="handleWorkstationChange">
    <header v-if="!isPopout" class="workstation__menu">
      <div class="workstation__application-navigation">
        <button
          ref="applicationMenuTrigger"
          class="workstation__brand"
          type="button"
          title="Open application navigation"
          aria-label="Open application navigation"
          aria-haspopup="menu"
          :aria-expanded="applicationMenuOpen"
          :aria-controls="applicationMenuId"
          @click="toggleApplicationMenu()"
          @keydown="handleShellTriggerKeydown('application', $event)"
        >CHARTING WORKSTATION</button>
        <div
          v-if="applicationMenuOpen"
          :id="applicationMenuId"
          ref="applicationMenuRoot"
          class="workstation__application-menu"
          role="menu"
          aria-label="Application navigation"
          :style="applicationMenuStyle"
          @click.stop
          @keydown="handleShellMenuKeydown('application', $event)"
        >
          <router-link
            v-for="item in applicationNavigation"
            :key="item.path"
            :to="item.path"
            :data-navigation-key="item.key"
            role="menuitem"
            tabindex="-1"
            :aria-current="isApplicationNavigationItemActive(item) ? 'page' : undefined"
          >
            <span aria-hidden="true">{{ item.icon }}</span>
            <span>{{ item.label }}</span>
          </router-link>
        </div>
      </div>
      <nav aria-label="Application menu">
        <div class="workstation__workspace-menu">
          <button ref="workspaceMenuTrigger" type="button" title="Manage workspace layouts" aria-haspopup="menu" :aria-expanded="workspaceMenuOpen" :aria-controls="workspaceMenuId" @click="toggleWorkspaceMenu" @keydown="handleShellTriggerKeydown('workspace', $event)">Workspace</button>
          <div v-if="workspaceMenuOpen" :id="workspaceMenuId" ref="workspaceMenuRoot" class="workstation__workspace-popover" role="menu" tabindex="-1" aria-label="Workspace layouts" :style="workspaceMenuStyle" @click.stop @keydown.capture="handleShellMenuKeydown('workspace', $event)">
            <header><strong>Workspaces</strong><small>{{ workspaceStore.workspace?.name ?? 'Workspace' }}</small></header>
            <div class="workstation__workspace-list" role="listbox" aria-label="Saved workspaces" tabindex="0" :aria-activedescendant="workspaceStore.workspaces[workspaceOptionIndex] ? `saved-workspace-${workspaceStore.workspaces[workspaceOptionIndex].id}` : undefined" @keydown.stop="handleWorkspaceListKeydown" @focus="syncWorkspaceOptionIndex">
              <span v-if="!workspaceStore.workspaces.length" role="status">Loading workspaces…</span>
              <button v-for="(item, index) in workspaceStore.workspaces" :id="`saved-workspace-${item.id}`" :key="item.id" type="button" role="option" tabindex="-1" :aria-selected="item.id === workspaceStore.workspace?.id" @click="switchWorkspaceFromMenu(item.id)">{{ item.name }}<small v-if="item.is_default">Default</small></button>
            </div>
            <div class="workstation__workspace-actions">
              <button type="button" role="menuitem" tabindex="-1" @click="createWorkspace(); closeShellMenuToTrigger('workspace')">New workspace</button>
              <button type="button" role="menuitem" tabindex="-1" @click="workspaceStore.cloneActiveTab(); closeShellMenuToTrigger('workspace')">Duplicate active layout</button>
              <button type="button" role="menuitem" tabindex="-1" @click="cloneWorkspace(); closeShellMenuToTrigger('workspace')">Duplicate workspace</button>
              <button type="button" role="menuitem" tabindex="-1" @click="renameWorkspace(); closeShellMenuToTrigger('workspace')">Rename workspace</button>
              <button type="button" role="menuitem" tabindex="-1" title="Factory workspaces cannot be deleted" :disabled="workspaceStore.workspace?.is_default" @click="deleteWorkspace(); closeShellMenuToTrigger('workspace')">Delete workspace</button>
              <button type="button" role="menuitem" tabindex="-1" @click="exportWorkspace">Export workspace</button>
              <button type="button" role="menuitem" tabindex="-1" @click="workspaceFileInput?.click()">Import workspace</button>
              <input ref="workspaceFileInput" class="workstation__workspace-file" type="file" accept="application/json,.json" @change="importWorkspace" />
            </div>
            <div
              v-if="deletedLayoutRecovery && workspaceStore.workspace?.id === deletedLayoutRecovery.workspace_id"
              class="workstation__layout-recovery"
              role="status"
              aria-live="polite"
            >
              <span v-if="deletedLayoutRecoveryStatus === 'saving'">Restoring layout “{{ deletedLayoutRecovery.tab.name }}” and saving…</span>
              <span v-else-if="deletedLayoutRecoveryStatus === 'error'">Layout “{{ deletedLayoutRecovery.tab.name }}” is restored here but was not saved. Retry to keep it after reload.</span>
              <span v-else>Deleted layout “{{ deletedLayoutRecovery.tab.name }}”.</span>
              <button type="button" role="menuitem" tabindex="-1" :disabled="deletedLayoutRecoveryStatus === 'saving'" @click="undoDeletedLayout">
                {{ deletedLayoutRecoveryStatus === 'saving' ? 'Saving…' : deletedLayoutRecoveryStatus === 'error' ? 'Retry save' : 'Undo' }}
              </button>
            </div>
            <small id="workspace-delete-help" class="workstation__workspace-delete-help">
              {{ workspaceStore.workspace?.is_default ? 'This factory workspace is protected; remove extra layouts from the list below.' : 'Deleting a workspace removes its saved layouts. Export it first if you need a backup.' }}
            </small>
            <div class="workstation__layout-list">
              <div v-for="tab in workspaceStore.workspace?.tabs ?? []" :key="tab.stable_key" class="workstation__layout-item" draggable="true" @dragstart="dragTabKey = tab.stable_key" @dragover.prevent @drop.prevent="dropTab(tab.stable_key)" @dragend="dragTabKey = null">
                <button type="button" role="menuitem" tabindex="-1" class="workstation__layout-select" :class="{ active: tab.stable_key === workspaceStore.activeTabKey }" @click="selectWorkspaceTab(tab.stable_key); closeShellMenuToTrigger('workspace')">{{ tab.name }}</button>
                <input
                  aria-label="Rename layout"
                  :value="layoutRenameDrafts[tab.stable_key] ?? tab.name"
                  @input="updateLayoutRenameDraft(tab.stable_key, $event)"
                  @change="commitLayoutRenameDraft(tab.stable_key, $event)"
                />
                <button type="button" class="workstation__layout-delete" :disabled="(workspaceStore.workspace?.tabs.length ?? 0) <= 1" :aria-label="`Delete layout ${tab.name}`" :title="`Delete layout ${tab.name}`" @click="deleteTab(tab.stable_key, tab.name)"><WorkstationGlyph kind="delete" /><span>Delete</span></button>
              </div>
            </div>
            <button v-if="workspaceStore.workspace?.settings.factory_id === 'us-top-down'" type="button" role="menuitem" tabindex="-1" class="workstation__layout-reset" @click="resetFactoryWorkspace(); closeShellMenuToTrigger('workspace')">Reset factory layout</button>
          </div>
        </div>
        <button type="button" title="Open Study Lab layout" @click="openStudyLab">Study</button>
        <button type="button" title="Open active-symbol alerts" @click="openAlertsTool">Alerts</button>
        <div class="workstation__help-menu">
          <button ref="keyboardHelpTrigger" type="button" title="Keyboard shortcuts" aria-haspopup="dialog" :aria-expanded="keyboardHelpOpen" :aria-controls="keyboardHelpMenuId" @click="toggleKeyboardHelp()" @keydown="handleShellTriggerKeydown('help', $event)">Help</button>
          <div v-if="keyboardHelpOpen" :id="keyboardHelpMenuId" ref="keyboardHelpMenuRoot" class="workstation__help-popover" role="dialog" aria-modal="false" aria-labelledby="keyboard-help-title" tabindex="0" :style="keyboardHelpMenuStyle" @click.stop @keydown="handleShellMenuKeydown('help', $event)">
            <header><strong id="keyboard-help-title">Keyboard shortcuts</strong><button type="button" aria-label="Close keyboard shortcuts" @click="closeShellMenuToTrigger('help')"><WorkstationGlyph kind="close" /></button></header>
            <dl>
              <div><dt>Type</dt><dd>Open symbol search</dd></div>
              <div><dt>Space</dt><dd>Next symbol in the focused list</dd></div>
              <div><dt>Ctrl+Space</dt><dd>Previous symbol in the focused list</dd></div>
              <div><dt>Backspace</dt><dd>Previous symbol in viewed history</dd></div>
              <div><dt>Shift+L</dt><dd>Toggle maximize for the selected window</dd></div>
              <div><dt>Shift+F</dt><dd>Flag or unflag selected WatchList symbols</dd></div>
              <div><dt>Shift+V</dt><dd>Add selected WatchList symbols to My Favorites</dd></div>
              <div><dt>Ctrl+M</dt><dd>Choose an explicit personal WatchList membership action for the selected symbols</dd></div>
              <div><dt>Shift+drag divider</dt><dd>Resize panes above the divider evenly</dd></div>
              <div><dt>Ctrl+drag divider</dt><dd>Resize panes below the divider evenly</dd></div>
              <div><dt>Shift+N</dt><dd>Write a note for the active symbol</dd></div>
              <div><dt>Shift+D</dt><dd>Toggle Trend Line drawing on the active chart</dd></div>
              <div><dt>Ctrl+B</dt><dd>Cycle HLC and OHLC bars, candles, and line style on the active chart</dd></div>
              <div><dt>Ctrl+1</dt><dd>Set the active chart to 1-minute bars</dd></div>
              <div><dt>Ctrl+3</dt><dd>Set the active chart to 5-minute bars</dd></div>
              <div><dt>Ctrl+4</dt><dd>Set the active chart to 15-minute bars</dd></div>
              <div><dt>Ctrl+5</dt><dd>Set the active chart to 30-minute bars</dd></div>
              <div><dt>Ctrl+6</dt><dd>Set the active chart to hourly bars</dd></div>
              <div><dt>1</dt><dd>Set the active chart to daily bars</dd></div>
              <div><dt>5</dt><dd>Set the active chart to weekly bars</dd></div>
              <div><dt>.</dt><dd>Cycle the active chart date pointer off, on, and on with data values</dd></div>
              <div><dt>/</dt><dd>Open the active chart's plot library and search indicators</dd></div>
              <div><dt>[ / ]</dt><dd>Move the active chart backward or forward one bar; Shift moves five bars</dd></div>
              <div><dt>Shift+wheel</dt><dd>Pan chart history</dd></div>
              <div><dt>Ctrl+wheel</dt><dd>Over a chart: change timeframe; over a WatchList: move through symbols</dd></div>
              <div><dt>= / -</dt><dd>Over the active chart: change timeframe</dd></div>
              <div><dt>F1–F12</dt><dd>Load the chart template assigned to that key</dd></div>
              <div><dt>?</dt><dd>Show this help</dd></div>
              <div><dt>Escape</dt><dd>Close search and menus</dd></div>
            </dl>
            <small>Shortcuts are inactive while a text, numeric, code, or search editor owns focus.</small>
          </div>
        </div>
        <button v-if="workspaceStore.workspace?.is_default" type="button" title="Reset factory workspace" @click="resetFactoryWorkspace">Reset</button>
      </nav>
      <div class="workstation__search" @pointerdown.stop @focusout="handleSymbolSearchFocusout" @keydown.esc.capture.prevent="closeSymbolSearch">
        <input
          ref="symbolInput"
          v-model="symbolDraft"
          aria-label="Active symbol"
          placeholder="Symbol"
          autocomplete="off"
          role="combobox"
          aria-autocomplete="list"
          :aria-expanded="searchPanelVisible"
          :aria-controls="symbolResultsId"
          :aria-activedescendant="searchIndex >= 0 ? symbolOptionId(searchIndex) : undefined"
          :aria-busy="searchLoading ? 'true' : 'false'"
          :aria-describedby="symbolSearchStateId"
          @input="handleSymbolInput"
          @keydown.stop="handleSymbolInputKeydown"
        />
        <button type="button" @click="goToSymbolDraft">Go</button>
        <button
          type="button"
          class="workstation__history-button"
          aria-label="Recent symbols"
          aria-haspopup="menu"
          :aria-expanded="recentSymbolsOpen"
          :aria-controls="recentSymbolsMenuId"
          :disabled="!recentStore.recent.length"
          ref="recentSymbolsTrigger"
          @click.stop="toggleRecentSymbols()"
          @keydown="handleShellTriggerKeydown('recent', $event)"
        ><WorkstationGlyph kind="chevron-down" /></button>
        <div v-if="recentSymbolsOpen && recentStore.recent.length" :id="recentSymbolsMenuId" ref="recentSymbolsMenuRoot" class="workstation__recent-symbols" role="menu" aria-label="Recent symbols" :style="recentSymbolsMenuStyle" @click.stop @keydown="handleShellMenuKeydown('recent', $event)">
          <header><strong>Recent symbols</strong><button type="button" role="menuitem" tabindex="-1" aria-label="Clear recent symbols" @click="recentStore.clear()">Clear</button></header>
          <button v-for="item in recentStore.recent" :key="item.symbol" type="button" role="menuitem" tabindex="-1" @click="selectRecentSymbol(item.symbol)">
            <strong>{{ item.symbol }}</strong><span>{{ item.name || 'Viewed instrument' }}</span>
          </button>
        </div>
        <div v-if="searchPanelVisible" class="workstation__symbol-results">
          <div :id="symbolResultsId" class="workstation__canonical-symbol-options" role="listbox" aria-label="Symbol search results" :aria-busy="searchLoading ? 'true' : 'false'">
            <div v-if="searchLoading" class="workstation__symbol-search-message" role="status">Searching canonical instruments…</div>
            <div v-else-if="searchError" class="workstation__symbol-search-message workstation__symbol-search-message--error" role="alert">{{ searchError }}</div>
            <div v-else-if="searchSettled && !searchResults.length && sourceDiscoveryLoading" class="workstation__symbol-search-message" role="status">No local match. Checking ticker availability…</div>
            <div v-else-if="searchSettled && sourceDiscoverySettled && sourceDiscoveryTerminalNoMatch" class="workstation__symbol-search-message" role="status">No matching ticker is available for “{{ symbolDraft.trim().toUpperCase() }}”.</div>
            <button
              v-for="(result, index) in searchResults"
              :key="`${result.symbol}:${result.exchange}`"
              :id="symbolOptionId(index)"
              type="button"
              role="option"
              :aria-selected="index === searchIndex"
              @mousedown.prevent="selectSearchResult(result.symbol, result.instrument_id, result.type)"
            ><strong>{{ result.symbol }}</strong><span>{{ result.name }}</span><small>{{ result.exchange || result.type }}</small></button>
          </div>
          <div v-if="sourceDiscoveryMessage" class="workstation__symbol-search-message" role="status" aria-live="polite">{{ sourceDiscoveryMessage }}</div>
          <div v-if="sourceDiscoveryError" class="workstation__symbol-search-message workstation__symbol-search-message--error" role="alert">{{ sourceDiscoveryError }}</div>
          <div v-if="sourceCandidates.length" class="workstation__source-actions" role="group" aria-label="Matching ticker listings">
            <button
              v-for="candidate in sourceCandidates"
              :key="`${candidate.provider}:${candidate.symbol}:${candidate.exchange}`"
              class="workstation__source-option"
              type="button"
              :disabled="sourceResolving"
              @mousedown.prevent
              @click="resolveSourceCandidate(candidate)"
            >Use {{ candidate.symbol }} · {{ candidate.exchange || candidate.type }} <span>{{ candidate.name }}</span></button>
          </div>
        </div>
        <span :id="symbolSearchStateId" class="workstation__symbol-search-state" role="status" aria-live="polite" aria-atomic="true">{{ searchStateText }}</span>
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
        <CompactStatusNotice
          v-if="selectionHistoryMessage"
          class="workstation__selection-acquisition"
          :summary="preparationMessageSummary(selectionHistoryMessage, 'History')"
          :detail="selectionHistoryMessage"
        />
        <CompactStatusNotice
          v-if="selectionHistoryError"
          class="workstation__selection-acquisition workstation__selection-acquisition--error"
          kind="alert"
          summary="History update failed"
          :detail="selectionHistoryError"
        />
        <CompactStatusNotice
          v-if="selectionHoldingsMessage"
          class="workstation__selection-acquisition"
          :summary="preparationMessageSummary(selectionHoldingsMessage, 'Holdings')"
          :detail="selectionHoldingsMessage"
        />
        <CompactStatusNotice
          v-if="selectionHoldingsError"
          class="workstation__selection-acquisition workstation__selection-acquisition--error"
          kind="alert"
          summary="Holdings update failed"
          :detail="selectionHoldingsError"
        />
        <span
          v-if="selectedHoldingLineage"
          class="workstation__selection-acquisition"
          data-testid="active-holding-lineage"
          role="status"
          :aria-label="selectedHoldingLineage"
          :title="selectedHoldingLineage"
        >{{ selectedHoldingCaption }}</span>
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
      <button type="button" class="workstation__tab-add" title="Duplicate layout" aria-label="Duplicate layout" @click="workspaceStore.cloneActiveTab()">+</button>
      <div class="workstation__tool-library">
          <button ref="toolLibraryTrigger" type="button" class="workstation__tab-add" title="Open a workstation tool" aria-haspopup="menu" :aria-expanded="toolLibraryOpen" :aria-controls="toolLibraryMenuId" @click="toggleToolLibrary()" @keydown="handleShellTriggerKeydown('tool-library', $event)">Add tool</button>
        <div v-if="toolLibraryOpen" :id="toolLibraryMenuId" ref="toolLibraryMenuRoot" class="workstation__tool-library-menu" role="menu" aria-label="Workstation tools" :style="toolLibraryMenuStyle" @keydown="handleShellMenuKeydown('tool-library', $event)">
          <p v-if="workspaceStore.toolCatalogueLoading" role="status">{{ openableTools.length ? 'Refreshing available tools…' : 'Loading available tools…' }}</p>
          <p v-else-if="workspaceStore.toolCatalogueError" role="status">{{ openableTools.length ? 'Using the last verified tool list. ' : '' }}{{ workspaceStore.toolCatalogueError }}</p>
          <p v-else-if="!openableTools.length" role="status">No workstation tools are currently available.</p>
          <button v-for="tool in openableTools" :key="tool.key" type="button" role="menuitem" tabindex="-1" @click="openTool(tool)">{{ tool.title }}</button>
        </div>
      </div>
      <button v-if="workspaceStore.workspace?.settings.factory_id === 'us-top-down'" type="button" class="workstation__tab-reset" title="Reset factory workspace" aria-label="Reset factory workspace" @click="resetFactoryWorkspace"><WorkstationGlyph kind="reset" /></button>
      <span class="workstation__workspace-name">{{ workspaceStore.workspace?.name ?? 'Loading workspace…' }}</span>
    </div>

    <WorkspaceLayoutHost
      v-if="!isPopout && goldenLayoutConfig && !workspaceDockPending"
      class="workstation__dock"
      :layout="goldenLayoutConfig"
      :tab-key="workspaceStore.activeTabKey"
      :active-window-key="workspaceStore.activeTab?.active_window_key"
      :reload-key="workspaceReloadKey"
      :persist-layout="persistMaximizedLayout"
      :render-tool="renderDockTool"
      @changed="persistGoldenLayout"
      @active-window-changed="(windowKey, sourceTabKey) => { if (!sourceTabKey || sourceTabKey === workspaceStore.activeTabKey) workspaceStore.setActiveWindow(windowKey) }"
    />
    <main v-else-if="!isPopout && workspaceDockPending" class="workstation__layout-state" role="status">
      Reloading workspace…
    </main>
    <main v-if="isPopout" ref="popoutRoot" class="workstation__popout" tabindex="-1" :aria-label="popoutLabel" :aria-describedby="popoutContextId">
      <WorkstationToolContent
        v-if="popoutTool"
        :tool="popoutTool"
        :active-window-key="popoutTool.instance_key"
        :factory-layout="workspaceStore.activeTabKey"
        @select="(symbol, instrumentId, preserveETFContext) => selectSymbol(symbol, undefined, false, instrumentId, true, Boolean(preserveETFContext), '', true)"
        @holding-select="selectHoldingInDashboard"
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
        @open-study="openStudyDefinition"
        @update-link-group="updateLinkGroup"
        @timeframe="setLinkedTimeframe"
        @close="closePopoutTool"
      />
      <div v-else class="workstation__missing-tool" role="alert" aria-live="assertive">The requested tool is unavailable. It remains in the source workspace.</div>
      <span :id="popoutContextId" class="sr-only">This is a browser-managed pop-out window. Placement across monitors and window controls are controlled by the browser and operating system.</span>
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
      <span role="status" aria-live="polite" aria-atomic="true" :title="footerError ?? symbolProxyNotice ?? undefined">{{ footerMessage }}</span>
      <span class="workstation__data-state" role="status" aria-live="polite" aria-atomic="true" :aria-label="`Market data freshness: ${dataState.label}`" :class="`workstation__data-state--${dataState.kind}`">{{ dataState.label }}</span>
      <span class="workstation__snapshot-save-state" role="status" aria-live="polite" aria-atomic="true" aria-label="Workspace save status" :title="workspaceStore.snapshotSaveError ?? undefined" :data-state="workspaceSaveStatus">
        {{ workspaceSaveStatusText }}
      </span>
      <button v-if="workspaceSaveStatus === 'error'" type="button" class="workstation__snapshot-save-retry" @click="retryWorkspaceSave">Retry save</button>
    </footer>
  </div>
</template>

<script setup lang="ts">
import { computed, defineComponent, h, nextTick, onBeforeUnmount, onMounted, ref, useId, watch, type PropType, type Ref, type VNode } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useQuery } from '@tanstack/vue-query'
import WorkspaceLayoutHost from '@/components/workstation/WorkspaceLayoutHost.vue'
import WorkstationToolContent from '@/components/workstation/WorkstationToolContent.vue'
import WorkstationGlyph from '@/components/workstation/WorkstationGlyph.vue'
import { refreshMountedWorkstationChartPanels, useChartStore } from '@/stores/chart'
import { useAuthStore } from '@/stores/auth'
import { useWorkspaceStore, type LinkGroup, type OpenableToolDefinition, type WorkspaceTabRecovery, type WorkspaceWindowState } from '@/stores/workspace'
import type { LayoutConfig } from 'golden-layout'
import { resolveKnownInstrument } from '@/lib/instruments'
import { createKnownTemporaryRetryLifecycle, isConfirmedInstrumentSelection, isCurrentETFHoldingsCapability, isEligibleETFHoldingsInstrumentType, readETFHoldingsCapability, resolveExistingInstrument, type InstrumentDiscoveryResponse } from '@/lib/onDemandAcquisition'
import { scheduleTickerDiscovery, shouldDiscoverTicker, tickerDiscoveryMessage } from '@/lib/workstationSymbolSearch'
import { autoRatioExpression } from '@/lib/workstation/ratioExpression'
import { api } from '@/lib/api'
import { discoverInstruments, resolveDiscoveredInstrument, type InstrumentAcquireResponse, type InstrumentDiscoveryCandidate } from '@/lib/onDemandAcquisition'
import { useQueryClient } from '@tanstack/vue-query'
import { useWatchlistStore } from '@/stores/watchlist'
import { useRecentInstrumentsStore } from '@/stores/recentInstruments'
import { useDrawingsStore } from '@/stores/drawings'
import { workstationFreshness } from '@/lib/workstation/freshness'
import { isInteractiveTarget } from '@/lib/workstation/keyboard'
import { capturePopoutGeometry, popoutWindowFeatures, readPopoutGeometry, recoverPopoutGeometry, type PopoutScreen } from '@/lib/workstation/popoutGeometry'
import { resolveMarketMapAnalysisSource } from '@/lib/workstation/marketMapPublication'
import { isActiveVirtualToolRoot } from '@/lib/workstation/toolActivation'
import {
  isConfirmedETFHoldingIdentity,
  isSameETFHoldingDrilldownContext,
  holdingDrilldownRouteQuery,
  parseETFHoldingDrilldownRouteQuery,
  type ETFHoldingDrilldownContext,
} from '@/lib/etfHoldingDrilldown'
import { isSharedNavigationItemActive, sharedShellNavigation } from '@/router'
import CompactStatusNotice from '@/components/common/CompactStatusNotice.vue'
import type { Timeframe } from '@/types'
import { dataPreparationCoordinator, historyPreparationStatusMessage, instrumentHistoryPreparationRequest, PreparationProgressRefreshQueue, preparationMessageSummary, preparationStatusMessage, type DataEnsureRequest, type DataEnsureResponse, type PreparationDataset, type PreparationStatus } from '@/lib/dataPreparation'

const BLOCKED_POPOUT_ERROR = 'Browser blocked the pop-out. The tool remains docked.'
const CHART_TIMEFRAME_ORDER: readonly Timeframe[] = ['M1', 'M5', 'M15', 'M30', 'H1', 'H2', 'H4', 'H12', 'D1', 'W1', 'MN']
const DIRECT_CHART_TIMEFRAME_SHORTCUTS: Readonly<Record<string, Timeframe>> = {
  '1': 'M1',
  '3': 'M5',
  '4': 'M15',
  '5': 'M30',
  '6': 'H1',
}
const DIRECT_CHART_PERIOD_SHORTCUTS: Readonly<Record<string, Timeframe>> = {
  '1': 'D1',
  '5': 'W1',
}
const STANDARD_CHART_STYLES = ['hlc', 'ohlc', 'candles', 'line'] as const

/** Prefer the selected instrument's requested dataset outcome over an aggregate
 * partial status that may be caused by an unrelated dependency. */
function selectedDatasetPreparationResponse(
  response: DataEnsureResponse,
  dataset: PreparationDataset,
  instrumentId: number,
  symbol: string,
): DataEnsureResponse {
  const normalizedSymbol = symbol.trim().toUpperCase()
  const dependencies = response.dependencies.filter(dependency => dependency.dataset === dataset
    && dependency.instrument_id === instrumentId
    && (dependency.symbol === null || dependency.symbol.trim().toUpperCase() === normalizedSymbol))
  if (!dependencies.length) return response

  const statusOrder: PreparationStatus[] = ['failed', 'unavailable', 'waiting', 'partial', 'running', 'queued', 'ready']
  const status = statusOrder.find(candidate => dependencies.some(dependency => dependency.status === candidate)) ?? response.status
  const completed = dependencies.filter(dependency => dependency.status === 'ready').length
  const hasPendingWork = dependencies.some(dependency => ['queued', 'running', 'partial', 'waiting'].includes(dependency.status))
  return { ...response, status, completed, total: dependencies.length, has_pending_work: hasPendingWork, dependencies }
}

const route = useRoute()
const router = useRouter()
const chartStore = useChartStore()
const authStore = useAuthStore()
const workspaceStore = useWorkspaceStore()
const watchlistStore = useWatchlistStore()
const recentStore = useRecentInstrumentsStore()
const drawingsStore = useDrawingsStore()
const queryClient = useQueryClient()
const workstationInstanceId = useId()
const symbolResultsId = `${workstationInstanceId}-symbol-results`
const symbolSearchStateId = `${workstationInstanceId}-symbol-search-state`
const symbolOptionId = (index: number) => `${workstationInstanceId}-symbol-option-${index}`
const workspaceMenuId = `${workstationInstanceId}-workspace-menu`
const keyboardHelpMenuId = `${workstationInstanceId}-keyboard-help-menu`
const recentSymbolsMenuId = `${workstationInstanceId}-recent-symbols-menu`
const toolLibraryMenuId = `${workstationInstanceId}-tool-library-menu`
const applicationMenuId = `${workstationInstanceId}-application-menu`
const popoutContextId = `${workstationInstanceId}-popout-context`
const symbolInput = ref<HTMLInputElement | null>(null)
const workspaceMenuTrigger = ref<HTMLButtonElement | null>(null)
const workspaceMenuRoot = ref<HTMLElement | null>(null)
const applicationMenuTrigger = ref<HTMLButtonElement | null>(null)
const applicationMenuRoot = ref<HTMLElement | null>(null)
const toolLibraryTrigger = ref<HTMLButtonElement | null>(null)
const toolLibraryMenuRoot = ref<HTMLElement | null>(null)
const keyboardHelpTrigger = ref<HTMLButtonElement | null>(null)
const keyboardHelpMenuRoot = ref<HTMLElement | null>(null)
const recentSymbolsTrigger = ref<HTMLButtonElement | null>(null)
const recentSymbolsMenuRoot = ref<HTMLElement | null>(null)
const popoutRoot = ref<HTMLElement | null>(null)
const workspaceMenuStyle = ref<Record<string, string>>({})
const applicationMenuStyle = ref<Record<string, string>>({})
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
const initialHoldingRouteContext = (() => {
  const requestedSymbol = route.params.symbol ?? route.query.symbol
  if (typeof requestedSymbol !== 'string' || route.query.holding_history_intent !== 'selected') return null
  return parseETFHoldingDrilldownRouteQuery(route.query as Record<string, unknown>, requestedSymbol)
})()
const holdingRouteHydrationPending = ref(initialHoldingRouteContext !== null)
const symbolDraft = ref(routeSymbol)
const toolLibraryOpen = ref(false)
const workspaceMenuOpen = ref(false)
const applicationMenuOpen = ref(false)
const workspaceOptionIndex = ref(0)
const keyboardHelpOpen = ref(false)
const recentSymbolsOpen = ref(false)
let historyNavigationTarget: string | null = null
let suppressSymbolDraftWatch: string | null = null
const workspaceFileInput = ref<HTMLInputElement | null>(null)
// Golden Layout virtual roots capture their tool object when created. Advance
// this token only after an import/reset replaces the complete workspace object
// so those roots are recreated from the new serializable tool state.
const workspaceReloadKey = ref(0)
const workspaceReplacementPending = ref(false)
const workspaceTabSwitchPending = ref(false)
const deletedLayoutRecovery = ref<WorkspaceTabRecovery | null>(null)
const deletedLayoutRecoveryStatus = ref<'ready' | 'saving' | 'error'>('ready')
const workspaceDockPending = computed(() => workspaceReplacementPending.value || workspaceTabSwitchPending.value)
// Shell controls render before the async workspace snapshot has necessarily
// hydrated. Keep tool-opening commands queued behind that first load instead
// of allowing an early click to mutate a stale/null tab and then be overwritten
// by the snapshot response.
const workspaceReady = ref(false)
const pendingTimeframeSelections = new Map<LinkGroup, string>()
let workspaceLoadPromise: Promise<void> | null = null
let initialWorkspaceHydrationPending = false
let pendingInitialWorkspaceSymbolIntent: {
  generation: number
  symbol: string
  instrumentId: number | null
  timestamp?: string
  holdingContext: ETFHoldingDrilldownContext | null
  selectedHolding: boolean
} | null = null
let resolveWorkspaceReady: (() => void) | null = null
const workspaceReadyPromise = new Promise<void>(resolve => {
  resolveWorkspaceReady = resolve
})
const dragTabKey = ref<string | null>(null)
const tabDragOverKey = ref<string | null>(null)
const tabDragCommitted = ref(false)
const searchResults = ref<Array<{ symbol: string; name: string; exchange: string; type: string; instrument_id?: number | null }>>([])
const searchIndex = ref(-1)
const searchOptionExplicitlyNavigatedFor = ref('')
const userSymbolDraftActive = ref(false)
const searchLoading = ref(false)
const searchSettled = ref(false)
const searchError = ref('')
const sourceCandidates = ref<InstrumentDiscoveryCandidate[]>([])
const sourceDiscoveryLoading = ref(false)
const sourceDiscoverySettled = ref(false)
const sourceDiscoveryTerminalNoMatch = ref(false)
const sourceResolving = ref(false)
const sourceDiscoveryMessage = ref('')
const sourceDiscoveryError = ref('')
const selectionHistoryMessage = ref('')
const selectionHistoryError = ref('')
const selectionHoldingsMessage = ref('')
const selectionHoldingsError = ref('')
const activeHoldingContext = ref<{ symbol: string; context: ETFHoldingDrilldownContext; restoredFromRoute?: boolean } | null>(null)
const selectedHoldingDetails = computed(() => {
  const selection = activeHoldingContext.value
  const fund = selection?.restoredFromRoute ? selection.context.etfSymbol : workspaceStore.constituentETF
  if (!selection || !fund || selection.symbol !== workspaceStore.linkedSymbol.trim().toUpperCase()) return ''
  const context = selection.context
  const origin = selection.restoredFromRoute ? 'dated holdings' : 'holdings'
  return [
    `${selection.symbol} from ${fund} ${origin}`,
    `instrument ${context.instrumentId}`,
    `snapshot ${context.snapshotId}`,
    `row ${context.holdingRowId}`,
    context.sourceRowId ? `source row ${context.sourceRowId}` : '',
    `reported ${context.reportedSymbol}`,
    context.reportedName ? `reported name ${context.reportedName}` : '',
    context.holdingType ? `type ${context.holdingType}` : '',
    `composition ${context.compositionDate}`,
    `known ${context.knownAt || 'not reported'}`,
    `${context.sourceProvider} / ${context.provenance}`,
    'This dated context does not establish current ETF analysis eligibility',
  ].filter(Boolean).join(' · ')
})
const selectedHoldingCaption = computed(() => {
  const selection = activeHoldingContext.value
  const fund = selection?.restoredFromRoute ? selection.context.etfSymbol : workspaceStore.constituentETF
  if (!selection || !fund || selection.symbol !== workspaceStore.linkedSymbol.trim().toUpperCase()) return ''
  return selection.restoredFromRoute
    ? `${selection.symbol} from ${fund} dated holdings · ${selection.context.compositionDate}`
    : `${selection.symbol} from ${fund} holdings · ${selection.context.compositionDate}`
})
const selectedHoldingLineage = selectedHoldingDetails
let searchTimer: ReturnType<typeof setTimeout> | null = null
let discoveryTimer: ReturnType<typeof setTimeout> | null = null
let discoveryRetryAbortController: AbortController | null = null
let candidateResolutionAbortController: AbortController | null = null
let candidateResolutionSequence = 0
let searchRequest = 0
let pendingSymbolSearch: { requestId: number; query: string; promise: Promise<void>; resolve: () => void } | null = null
let symbolSubmissionInFlight: { query: string; requestId: number } | null = null
let lastSymbolSelectionError: string | null = null
let lastDiscoveryQuery = ''
const symbolSearchEnabled = ref(false)
const layoutRenameDrafts = ref<Record<string, string>>({})
const searchPanelVisible = computed(() => symbolSearchEnabled.value && Boolean(symbolDraft.value.trim()))
const searchStateText = computed(() => {
  if (!searchPanelVisible.value) return ''
  if (searchLoading.value) return 'Searching canonical instruments'
  if (sourceDiscoveryLoading.value) return 'Checking ticker availability'
  if (searchError.value) return `Symbol search error: ${searchError.value}`
  if (sourceDiscoveryError.value) return `Ticker lookup error: ${sourceDiscoveryError.value}`
  if (searchSettled.value && sourceDiscoverySettled.value && sourceDiscoveryTerminalNoMatch.value) return `No matching ticker is available for ${symbolDraft.value.trim().toUpperCase()}`
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
let selectedAcquisitionAbortController: AbortController | null = null
let linkedTimeframePreparationGeneration = 0
let linkedTimeframePreparationAbortController: AbortController | null = null
let drilldownSelectionGeneration = 0
let componentMounted = false
let resolveComponentMountSettled: (() => void) | null = null
const componentMountSettled = new Promise<void>(resolve => {
  resolveComponentMountSettled = resolve
})
const preserveDrilldownSymbol = ref<string | null>(null)
// SPX is a logical benchmark identity. When an official SPX series is not
// entitled or cannot be resolved, keep the requested workflow usable through
// the canonical, explicitly-labelled SPY tradable proxy instead of leaving the
// workstation on a dead symbol.
const symbolProxyNotice = ref<string | null>(null)
const openableTools = computed(() => workspaceStore.toolCatalogue ?? [])
const applicationNavigation = sharedShellNavigation
const isApplicationNavigationItemActive = (item: typeof applicationNavigation[number]) =>
  isSharedNavigationItemActive(route.path, item.match)
// Keep RouterLink mounted until its own navigation handler has committed the
// destination. Closing the v-if menu during pointerdown/click can detach the
// link before Vue Router processes the ordinary activation.
watch(() => route.fullPath, () => closeShellMenus())
const documentVisible = ref(typeof document === 'undefined' || document.visibilityState === 'visible')
let removeVisibilityListener: (() => void) | null = null
const popoutGeometryPollers = new Map<string, ReturnType<typeof window.setInterval>>()

function closeSymbolSearch() {
  symbolSearchEnabled.value = false
  searchOptionExplicitlyNavigatedFor.value = ''
  userSymbolDraftActive.value = false
  discoveryRetryAbortController?.abort()
  discoveryRetryAbortController = null
  candidateResolutionAbortController?.abort()
  candidateResolutionAbortController = null
  candidateResolutionSequence += 1
  if (searchTimer) {
    clearTimeout(searchTimer)
    searchTimer = null
  }
  if (discoveryTimer) {
    clearTimeout(discoveryTimer)
    discoveryTimer = null
  }
  searchRequest += 1
  finishPendingSymbolSearch()
  searchResults.value = []
  searchIndex.value = -1
  searchLoading.value = false
  searchSettled.value = false
  searchError.value = ''
  sourceDiscoveryLoading.value = false
  sourceDiscoveryMessage.value = ''
  sourceDiscoveryTerminalNoMatch.value = false
}

function handleSymbolSearchFocusout(event: FocusEvent) {
  const root = event.currentTarget
  const next = event.relatedTarget
  if (root instanceof HTMLElement && next instanceof Node && root.contains(next)) return
  closeSymbolSearch()
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
  userSymbolDraftActive.value = true
  const inputValue = symbolInput.value?.value ?? symbolDraft.value
  if (symbolDraft.value !== inputValue) symbolDraft.value = inputValue
  // Schedule from the actual DOM event as well as the ref watcher. This also
  // handles a deliberate edit/paste of an already hydrated ticker, where the
  // input event fires but Vue sees no ref-value change.
  suppressSymbolDraftWatch = inputValue
  scheduleSymbolSearch(inputValue)
  queueMicrotask(() => {
    if (suppressSymbolDraftWatch === inputValue) suppressSymbolDraftWatch = null
  })
  if (symbolDraft.value.trim()) {
    searchLoading.value = true
    searchSettled.value = false
    searchError.value = ''
  }
}

type ShellMenu = 'application' | 'workspace' | 'tool-library' | 'help' | 'recent'

/**
 * The desktop shell has one transient menu layer at a time. Keeping this
 * invariant in one place prevents a newly opened popover from leaving an
 * older fixed-position menu over the dock or stealing the next pointer event.
 * The search wrapper is the one deliberate exception: its listbox and recent
 * symbols menu may remain open while the symbol editor owns focus.
 */
function closeShellMenus(except?: ShellMenu) {
  if (except !== 'application') applicationMenuOpen.value = false
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
  if (applicationMenuOpen.value) applicationMenuStyle.value = shellMenuPosition(applicationMenuTrigger.value, 236, 360)
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

function scheduleShellMenuPosition() {
  void nextTick(positionShellMenus)
}

function syncShellMenuListeners() {
  const open = applicationMenuOpen.value || workspaceMenuOpen.value || toolLibraryOpen.value || keyboardHelpOpen.value || recentSymbolsOpen.value
  if (!open) return removeShellMenuListeners()
  addShellMenuListeners()
}

function toggleWorkspaceMenu() {
  const open = !workspaceMenuOpen.value
  closeShellMenus(open ? 'workspace' : undefined)
  workspaceMenuOpen.value = open
  if (open) {
    scheduleShellMenuPosition()
    const selectedIndex = (workspaceStore.workspaces ?? []).findIndex(item => item.id === workspaceStore.workspace?.id)
    workspaceOptionIndex.value = selectedIndex >= 0 ? selectedIndex : 0
    void focusShellMenu('workspace')
    // The fixed overlay is mounted one render after the trigger key event in
    // some Chromium/GLayout combinations. One bounded retry covers that DOM
    // attachment boundary without introducing polling or stealing later focus.
    window.setTimeout(() => {
      const menuRoot = workspaceMenuRoot.value
      const active = document.activeElement
      if (workspaceMenuOpen.value && menuRoot && !menuRoot.contains(active)) {
        void focusShellMenu('workspace')
      }
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

function toggleApplicationMenu(focusLast = false) {
  const open = !applicationMenuOpen.value
  closeShellMenus(open ? 'application' : undefined)
  applicationMenuOpen.value = open
  if (open) {
    closeSymbolSearch()
    scheduleShellMenuPosition()
    void focusShellMenu('application', focusLast ? -1 : 0)
  } else {
    applicationMenuTrigger.value?.focus()
  }
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

function toggleToolLibrary(focusLast = false) {
  const open = !toolLibraryOpen.value
  closeShellMenus(open ? 'tool-library' : undefined)
  toolLibraryOpen.value = open
  if (open) {
    closeSymbolSearch()
    scheduleShellMenuPosition()
  }
  if (open) void focusShellMenu('tool-library', focusLast ? -1 : 0)
  else toolLibraryTrigger.value?.focus()
  syncShellMenuListeners()
}

function toggleKeyboardHelp(focusLast = false) {
  const open = !keyboardHelpOpen.value
  closeShellMenus(open ? 'help' : undefined)
  keyboardHelpOpen.value = open
  if (open) {
    closeSymbolSearch()
    scheduleShellMenuPosition()
  }
  if (open) void focusShellMenu('help', focusLast ? -1 : 0)
  else keyboardHelpTrigger.value?.focus()
  syncShellMenuListeners()
}

function toggleRecentSymbols(focusLast = false) {
  const open = !recentSymbolsOpen.value
  closeShellMenus(open ? 'recent' : undefined)
  recentSymbolsOpen.value = open
  if (open) {
    closeSymbolSearch()
    scheduleShellMenuPosition()
  }
  if (open) void focusShellMenu('recent', focusLast ? -1 : 0)
  else recentSymbolsTrigger.value?.focus()
  syncShellMenuListeners()
}

type ShellMenuRoot = 'application' | 'workspace' | 'tool-library' | 'help' | 'recent'
const shellMenuRoots: Record<ShellMenuRoot, ReturnType<typeof ref<HTMLElement | null>>> = {
  application: applicationMenuRoot,
  workspace: workspaceMenuRoot,
  'tool-library': toolLibraryMenuRoot,
  help: keyboardHelpMenuRoot,
  recent: recentSymbolsMenuRoot,
}
const shellMenuTriggers: Record<ShellMenuRoot, ReturnType<typeof ref<HTMLButtonElement | null>>> = {
  application: applicationMenuTrigger,
  workspace: workspaceMenuTrigger,
  'tool-library': toolLibraryTrigger,
  help: keyboardHelpTrigger,
  recent: recentSymbolsTrigger,
}
function shellMenuItems(menu: ShellMenuRoot) {
  return Array.from(shellMenuRoots[menu].value?.querySelectorAll<HTMLElement>('[role="menuitem"]:not(:disabled):not([aria-disabled="true"])') ?? [])
}
async function focusShellMenu(menu: ShellMenuRoot, focusIndex = 0) {
  await nextTick()
  if (menu === 'workspace') {
    const list = workspaceMenuRoot.value?.querySelector<HTMLElement>('[role="listbox"]')
    list?.focus()
    return
  }
  const items = shellMenuItems(menu)
  if (menu === 'help') {
    keyboardHelpMenuRoot.value?.focus()
    return
  }
  if (!items.length) return
  const index = focusIndex < 0 ? items.length - 1 : Math.min(focusIndex, items.length - 1)
  items[Math.max(0, index)]?.focus()
}
function closeShellMenuToTrigger(menu: ShellMenuRoot) {
  closeShellMenus()
  void nextTick(() => shellMenuTriggers[menu].value?.focus())
}
function handleShellTriggerKeydown(menu: ShellMenuRoot, event: KeyboardEvent) {
  if (!['Enter', ' ', 'ArrowDown', 'ArrowUp'].includes(event.key)) return
  event.preventDefault()
  const focusIndex = event.key === 'ArrowUp' ? -1 : 0
  // Opening a conditional menu during this key event mounts its root before
  // the browser finishes bubbling the original event. Stop that event at the
  // trigger boundary so the newly mounted menu cannot interpret ArrowDown as
  // a request to focus its first action (the workspace listbox owns focus).
  event.stopPropagation()
  if (menu === 'workspace' && !workspaceMenuOpen.value) return toggleWorkspaceMenu()
  if (menu === 'application' && !applicationMenuOpen.value) return toggleApplicationMenu(focusIndex < 0)
  if (menu === 'tool-library' && !toolLibraryOpen.value) return toggleToolLibrary(focusIndex < 0)
  if (menu === 'help' && !keyboardHelpOpen.value) return toggleKeyboardHelp(focusIndex < 0)
  if (menu === 'recent' && !recentSymbolsOpen.value) return toggleRecentSymbols(focusIndex < 0)
  void focusShellMenu(menu, focusIndex)
}
function handleShellMenuKeydown(menu: ShellMenuRoot, event: KeyboardEvent) {
  if (event.key === 'Escape') {
    event.preventDefault()
    event.stopPropagation()
    closeShellMenuToTrigger(menu)
    return
  }
  if (menu === 'help' && event.key === 'Home') {
    event.preventDefault()
    if (keyboardHelpMenuRoot.value) keyboardHelpMenuRoot.value.scrollTop = 0
    return
  }
  // The workspace menu owns a nested listbox.  Its handler deliberately stops
  // bubbling so End/Home change the active descendant instead of moving focus
  // to an action.  When Playwright (or an assistive technology) addresses the
  // menu root directly, capture the event at the root; otherwise a browser can
  // leave focus on the listbox and silently ignore the root-level command.
  if (menu === 'workspace' && event.target instanceof Element
    && event.target.closest('[role="listbox"]')) return
  const items = shellMenuItems(menu)
  if (!items.length) return
  const current = items.indexOf(document.activeElement as HTMLElement)
  let next: number | null = null
  if (event.key === 'ArrowDown' || event.key === 'ArrowRight') next = (current + 1 + items.length) % items.length
  else if (event.key === 'ArrowUp' || event.key === 'ArrowLeft') next = (current - 1 + items.length) % items.length
  else if (event.key === 'Home') next = 0
  else if (event.key === 'End') next = items.length - 1
  if (next === null) return
  event.preventDefault()
  event.stopPropagation()
  items[next].focus()
}

function preserveActiveUserSymbolDraft(symbol: string) {
  return symbolSearchEnabled.value
    && userSymbolDraftActive.value
    && symbolDraft.value.trim().toUpperCase() !== symbol.toUpperCase()
}

// A focused symbol input can keep its listbox above the dock surface. Close it
// during the pointer-down capture/bubble sequence for every tool click so the
// overlay cannot intercept the later click event. Pointer events inside the
// search control are stopped at the wrapper and retain normal list interaction.
function handleWorkstationPointerDown(event: PointerEvent) {
  const target = event.target
  const clickedTool = target instanceof Element
    ? target.closest<HTMLElement>('.tool-window[data-window-key]')
    : null
  const clickedWindowKey = clickedTool?.dataset.windowKey
  if (!isPopout.value && clickedWindowKey
    && workspaceStore.activeTab?.active_window_key !== clickedWindowKey) {
    workspaceStore.setActiveWindow(clickedWindowKey)
  }
  const insideSearch = target instanceof Element && target.closest('.workstation__search')
  if (insideSearch) {
    // Search controls retain their own listbox/history state, but any other
    // shell menu must still close when focus moves into the editor.
    closeShellMenus('recent')
    return
  }
  if (!(target instanceof Element && target.closest('.workstation__workspace-menu'))) workspaceMenuOpen.value = false
  if (!(target instanceof Element && target.closest('.workstation__application-navigation'))) applicationMenuOpen.value = false
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
    applicationMenuOpen.value = false
    syncShellMenuListeners()
    return
  }
  const inWorkspaceMenu = target instanceof Element && target.closest('.workstation__workspace-menu')
  const inApplicationMenu = target instanceof Element && target.closest('.workstation__application-navigation')
  const inToolLibrary = target instanceof Element && target.closest('.workstation__tool-library')
  const inHelpMenu = target instanceof Element && target.closest('.workstation__help-menu')
  const inRecentMenu = target instanceof Element && target.closest('.workstation__search')
  if (!inWorkspaceMenu) workspaceMenuOpen.value = false
  if (!inApplicationMenu) applicationMenuOpen.value = false
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
const footerError = computed(() => {
  const selectedETF = workspaceStore.constituentETF
  return (selectedETF ? workspaceStore.etfConstituentSnapshotErrors[selectedETF] : null) ?? workspaceStore.error
})
const footerMessage = computed(() => symbolProxyNotice.value ?? humanizeWorkspaceError(footerError.value))
const workspaceSaveStatus = computed(() => workspaceStore.snapshotSaveStatus ?? 'saved')
const workspaceSaveStatusText = computed(() => {
  if (workspaceSaveStatus.value === 'saving') return 'Saving layout…'
  if (workspaceSaveStatus.value === 'error') return 'Workspace save failed'
  return 'Workspace saved'
})
const isPopout = computed(() => route.path.startsWith('/popout/'))
const popoutLabel = computed(() => {
  const title = popoutTool.value?.title?.trim() || 'workstation tool'
  return `TC2000 ${title} pop-out`
})

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
  // The visibility handler below is the single refresh owner. Vue Query also
  // observes document visibility as window focus; disabling its parallel
  // focus refetch prevents two shell refreshes for the same foreground return.
  refetchOnWindowFocus: false,
  refetchInterval: 5 * 60 * 1000,
  refetchIntervalInBackground: false,
})

function hasSharedMarketAnalysis() {
  const groups = workspaceStore.marketGroups ?? {}
  const snapshots = workspaceStore.groupSnapshots ?? {}
  const breadth = workspaceStore.breadth ?? {}
  const breadthHistory = workspaceStore.breadthHistory ?? {}
  return ['us-benchmarks', 'sp500-sectors'].every(key => Boolean(groups[key] && snapshots[key]))
    && Boolean(breadth['sp500-sectors'])
    && Boolean(breadthHistory['sp500-sectors'])
}

async function refreshMarketData() {
  if (!documentVisible.value) return
  // A pop-out does not own the periodic refresh timer, but it can be opened
  // after the leader has already announced its refresh. In that case the
  // BroadcastChannel event has already been missed and the local store is
  // empty, so hydrate the shared analysis once before rendering the tool.
  // Once the six canonical inputs exist, the pop-out remains a follower and
  // does not fan out duplicate requests on every mount.
  if (isPopout.value) {
    // Only market-analysis surfaces need the shared top-down payload. A chart
    // pop-out must remain display-only here; hydrating unrelated watchlists on
    // its first paint changes the canonical readiness/status state behind the
    // visual workstation oracle without helping the chart itself.
    if (popoutTool.value?.tool_type === 'watchlist' && !hasSharedMarketAnalysis()) {
      await workspaceStore.refreshMarketAnalysis('high')
    }
    return
  }
  if (workspaceStore.isPersistenceLeader) {
    // Mounting a visible analysis surface is user-visible work. If the shell's
    // interval refresh already queued these same reads, the store promotes the
    // existing requests rather than issuing duplicates.
    void workspaceStore.refreshMarketAnalysis('high')
    await marketAnalysisQuery.refetch()
  } else {
    // Followers still hydrate once when they open. Subsequent periodic refreshes are
    // leader-owned and arrive through the cross-window refresh event.
    await workspaceStore.refreshMarketAnalysis('high')
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
  // Remove the old Golden Layout host before exposing the new tab. Its final
  // bootstrap/stateChanged event can otherwise remain visible for one turn and
  // make a caller observe the previous tab as if it were the newly selected
  // layout. Mount the replacement host on the following Vue turn.
  workspaceTabSwitchPending.value = true
  // A layout switch can occur while the previous layout's trailing snapshot is
  // still in flight. Advance the snapshot generation so that stale server
  // responses cannot reinstall the previous layout over the newly selected tab.
  workspaceStore.activeTabKey = stableKey
  workspaceStore.scheduleSnapshot()
  void workspaceStore.saveSnapshot()
  void nextTick(() => {
    workspaceTabSwitchPending.value = false
  })
}

async function replaceDockAfterWorkspaceChange() {
  if (isPopout.value) return
  const alreadyReplacingWorkspace = workspaceReplacementPending.value
  workspaceReplacementPending.value = true
  await nextTick()
  workspaceReloadKey.value += 1
  await nextTick()
  workspaceReplacementPending.value = alreadyReplacingWorkspace
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

function isPrivateBasketToken(value: string): boolean {
  const match = value.trim().match(/^BASKET:(\d+)$/i)
  return Boolean(match && Number(match[1]) > 0)
}

function consumeHoldingSelectionHandoff(context: ETFHoldingDrilldownContext | null): {
  selected: boolean
  confirmedIdentity?: InstrumentAcquireResponse
} {
  const state = window.history.state as Record<string, unknown> | null
  if (!state || (!Object.prototype.hasOwnProperty.call(state, 'tcHoldingSelectionHandoff')
    && !Object.prototype.hasOwnProperty.call(state, 'tcHoldingIdentityHandoff'))) return { selected: false }
  const nextState = { ...state }
  const rawSelection = nextState.tcHoldingSelectionHandoff
  const rawIdentity = nextState.tcHoldingIdentityHandoff
  delete nextState.tcHoldingSelectionHandoff
  delete nextState.tcHoldingIdentityHandoff
  window.history.replaceState(nextState, '', window.location.href)
  if (!context || typeof rawSelection !== 'string') return { selected: false }
  try {
    const selectedContext = JSON.parse(rawSelection) as ETFHoldingDrilldownContext
    if (!isSameETFHoldingDrilldownContext(selectedContext, context)) return { selected: false }
    if (typeof rawIdentity !== 'string') return { selected: true }
    const candidate = JSON.parse(rawIdentity) as InstrumentAcquireResponse
    return {
      selected: true,
      confirmedIdentity: isConfirmedETFHoldingIdentity(candidate, context) ? candidate : undefined,
    }
  } catch {
    return { selected: false }
  }
}

function selectHoldingInDashboard(
  symbol: string,
  context: ETFHoldingDrilldownContext,
  confirmedIdentity?: InstrumentAcquireResponse,
) {
  const canonical = symbol.trim().toUpperCase()
  if (!canonical || canonical !== context.canonicalSymbol.trim().toUpperCase()
    || !Number.isSafeInteger(context.instrumentId) || context.instrumentId <= 0) return
  // A holding row is a dashboard selection, not a legacy chart navigation.
  // Keep the parent ETF context active so the same snapshot/row remains the
  // provenance source while linked dashboard panels follow the selected equity.
  void selectSymbol(canonical, undefined, false, context.instrumentId, true, true,
    confirmedIdentity?.instrument?.instrument_type ?? '', true, confirmedIdentity, context)
}

let pendingChartRouteSync: string | null = null
function syncChartRouteToSelection(
  rawSymbol: string,
  instrumentId?: number | null,
  candidateContext?: ETFHoldingDrilldownContext | null,
  markHoldingSelection = false,
) {
  if (isPopout.value || !/^\/chart(?:\/|$)/.test(route.path)) return
  const symbol = rawSymbol.trim().toUpperCase()
  if (!symbol) return
  // A requested SPX that resolved to its labelled tradable proxy keeps the
  // user's SPX URL; rewriting it would present the proxy as the request.
  const requestedRouteSymbol = typeof route.params.symbol === 'string' ? route.params.symbol.trim().toUpperCase() : ''
  if (requestedRouteSymbol === 'SPX' && symbolProxyNotice.value === `SPX official series unavailable; using tradable proxy ${symbol}`) return
  const candidateHoldingContext = candidateContext
    ?? (!isPrivateBasketToken(symbol) && activeHoldingContext.value?.symbol === symbol
      ? activeHoldingContext.value.context
      : null)
  const context = candidateHoldingContext
    && candidateHoldingContext.canonicalSymbol.trim().toUpperCase() === symbol
    && (instrumentId == null || candidateHoldingContext.instrumentId === instrumentId)
    ? candidateHoldingContext
    : null
  const nextQuery: Record<string, unknown> = { ...route.query }
  for (const key of Object.keys(nextQuery)) {
    if (key.startsWith('holding_')) delete nextQuery[key]
  }
  if (typeof nextQuery.symbol === 'string' && nextQuery.symbol.trim().toUpperCase() !== symbol) {
    delete nextQuery.symbol
  }
  if (context) {
    Object.assign(nextQuery, holdingDrilldownRouteQuery(context))
    if (markHoldingSelection || route.query.holding_history_intent === 'selected') {
      nextQuery.holding_history_intent = 'selected'
    }
  }
  const path = `/chart/${encodeURIComponent(symbol)}`
  if (route.path === path && JSON.stringify(nextQuery) === JSON.stringify(route.query)) return
  const requestKey = JSON.stringify({ path, query: nextQuery })
  if (pendingChartRouteSync === requestKey) return
  pendingChartRouteSync = requestKey
  void router.replace({ path, query: nextQuery as typeof route.query }).then(failure => {
      if (failure && pendingChartRouteSync === requestKey) {
      pendingChartRouteSync = null
      setSymbolSelectionError(`Selected ${symbol}, but the chart URL could not be updated; a reload may restore a different symbol.`)
    }
  }).catch(() => {
    if (pendingChartRouteSync === requestKey) {
      pendingChartRouteSync = null
      setSymbolSelectionError(`Selected ${symbol}, but the chart URL could not be updated; a reload may restore a different symbol.`)
    }
  }).finally(() => {
    if (pendingChartRouteSync === requestKey) pendingChartRouteSync = null
  })
}

function restoredWorkspaceBlueSymbol(): string {
  const workspace = workspaceStore.workspace
  const linkedSymbols = workspace?.settings?.linked_symbols
  if (linkedSymbols && typeof linkedSymbols === 'object' && !Array.isArray(linkedSymbols)) {
    const blue = (linkedSymbols as Record<string, unknown>).blue
    if (blue && typeof blue === 'object' && !Array.isArray(blue)) {
      const symbol = (blue as Record<string, unknown>).symbol
      if (typeof symbol === 'string' && symbol.trim()) return symbol.trim().toUpperCase()
    }
  }
  const configured = workspace?.tabs.flatMap(tab => tab.windows)
    .find(tool => tool.link_group !== 'grey' && typeof tool.configuration.symbol === 'string')
    ?.configuration.symbol
  return typeof configured === 'string' && configured.trim() ? configured.trim().toUpperCase() : 'SPY'
}

async function selectSymbol(
  raw: string,
  timestamp?: string,
  allowNavigationFallback = false,
  instrumentId?: number | null,
  recordHistory = true,
  preserveETFContext = false,
  instrumentType = '',
  acquisitionIntent = false,
  confirmedIdentity?: InstrumentAcquireResponse,
  holdingContext?: ETFHoldingDrilldownContext,
  restoredHoldingContext?: ETFHoldingDrilldownContext,
) {
  const requested = raw.trim()
  if (!requested) return
  const privateBasketSelection = isPrivateBasketToken(requested)
  clearSupersededSymbolSelectionError()
  linkedTimeframePreparationGeneration += 1
  linkedTimeframePreparationAbortController?.abort()
  linkedTimeframePreparationAbortController = null
  selectedAcquisitionAbortController?.abort()
  const acquisitionController = new AbortController()
  selectedAcquisitionAbortController = acquisitionController
  const generation = ++symbolSelectionGeneration
  let resolvedInstrumentType = confirmedIdentity?.instrument?.instrument_type?.trim() || instrumentType
  if (!preserveETFContext) {
    const requestedSymbol = requested.toUpperCase()
    const sectorSymbols = new Set(
      (workspaceStore.marketGroups['sp500-sectors']?.members ?? [])
        .map(member => member.instrument.symbol.trim().toUpperCase()),
    )
    const selectedType = confirmedIdentity?.instrument?.instrument_type ?? instrumentType
    const selectedETF = sectorSymbols.has(requestedSymbol) || isEligibleETFHoldingsInstrumentType(selectedType)
    workspaceStore.setConstituentETF(null)
    if (selectedETF) workspaceStore.setConstituentETF(requestedSymbol)
  } else preserveDrilldownSymbol.value = requested.toUpperCase()
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
  if (privateBasketSelection) {
    // Basket IDs are authenticated, user-owned chart contexts, not instruments.
    // The chart store validates the private basket endpoint and prepares its
    // exact member IDs through the shared coordinator.
    symbol = requested.toUpperCase()
  } else if (holdingContext
    && holdingContext.canonicalSymbol.trim().toUpperCase() === requested.toUpperCase()
    && Number.isSafeInteger(instrumentId) && instrumentId === holdingContext.instrumentId) {
    // A verified holding handoff already carries the canonical instrument ID.
    // Do not resolve the reported ticker again and risk attaching the lineage to
    // a different listing.
    symbol = holdingContext.canonicalSymbol.trim().toUpperCase()
    resolvedInstrumentId = holdingContext.instrumentId
  } else if (confirmedIdentity) {
    if (!isConfirmedInstrumentSelection(confirmedIdentity, requested, instrumentId)) {
      setSymbolSelectionError('Ticker confirmation did not match the selected listing. No chart was opened.')
      return
    }
    const confirmedInstrument = confirmedIdentity.instrument!
    // Candidate confirmation already returned the exact canonical identity.
    // Re-resolving it adds a second metadata dependency after successful
    // confirmation and can leave the user's selection/URL stuck behind a
    // queued request. Trust only the matching resolved symbol and positive ID.
    symbol = confirmedInstrument.symbol.trim().toUpperCase()
    resolvedInstrumentId = confirmedInstrument.instrument_id
    resolvedInstrumentType = confirmedInstrument.instrument_type?.trim() || resolvedInstrumentType
  } else if (knownWorkstationSymbols.has(requested.toUpperCase())) {
    // These symbols are already canonical members of a loaded workstation
    // universe. Publish them synchronously so an in-flight initial request
    // cannot leave the Industries pane bound to the previous ETF.
    symbol = requested.toUpperCase()
  } else if (allowNavigationFallback && navigationFallbacks.has(requested.toUpperCase())) {
    symbol = requested.toUpperCase()
  } else {
    try {
      const resolved = await resolveKnownInstrument(requested, 'Workstation symbol', {
        canonicalOnly: true,
        priority: 'high',
        foreground: true,
        signal: acquisitionController.signal,
      })
      symbol = resolved.symbol
      resolvedInstrumentId = resolved.id
      // The local picker may have an older or coarse security classification.
      // Use the canonical metadata returned by this already-needed lookup to
      // update dataset-specific panels without re-acquiring the identity.
      resolvedInstrumentType = resolved.instrumentType || resolvedInstrumentType
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
          const resolved = await resolveKnownInstrument(proxy, 'S&P 500 tradable proxy', {
            canonicalOnly: true,
            priority: 'high',
            foreground: true,
            signal: acquisitionController.signal,
          })
          symbol = resolved.symbol
          resolvedInstrumentId = resolved.id
          if (generation !== symbolSelectionGeneration) return
          symbolProxyNotice.value = `SPX official series unavailable; using tradable proxy ${symbol}`
        } catch (proxyCause: any) {
          if (generation !== symbolSelectionGeneration) return
          setSymbolSelectionError(proxyCause?.message ?? cause?.message ?? 'Unable to resolve S&P 500 benchmark')
          return
        }
      } else {
        setSymbolSelectionError(cause?.message ?? 'Unable to resolve symbol')
        return
      }
    }
  }
  if (generation !== symbolSelectionGeneration) return
  selectionHistoryMessage.value = ''
  selectionHistoryError.value = ''
  selectionHoldingsMessage.value = ''
  selectionHoldingsError.value = ''
  let canonicalInstrumentId = typeof instrumentId === 'number' ? instrumentId : resolvedInstrumentId
  if (canonicalInstrumentId == null) {
    const knownMember = [
      ...(workspaceStore.marketGroups['us-benchmarks']?.members ?? []),
      ...(workspaceStore.marketGroups['sp500-sectors']?.members ?? []),
    ].find(member => member.instrument.symbol.trim().toUpperCase() === symbol)
    canonicalInstrumentId = knownMember?.instrument.id ?? null
  }
  const displayContext = holdingContext ?? restoredHoldingContext
  const contextMatchesResolvedIdentity = displayContext
    && displayContext.canonicalSymbol.trim().toUpperCase() === symbol.trim().toUpperCase()
    && Number.isSafeInteger(canonicalInstrumentId)
    && canonicalInstrumentId === displayContext.instrumentId
  activeHoldingContext.value = contextMatchesResolvedIdentity
    ? { symbol: symbol.trim().toUpperCase(), context: displayContext, restoredFromRoute: !holdingContext }
    : null
  // A direct selection begins a new holdings context immediately. A constituent
  // row is the explicit exception: its parent ETF remains the source for the
  // linked constituent/ratio panels while the selected equity chart changes.
  const sectorSymbols = new Set(
    (workspaceStore.marketGroups['sp500-sectors']?.members ?? [])
      .map(member => member.instrument.symbol.trim().toUpperCase()),
  )
  const selectedType = resolvedInstrumentType
  const isETF = sectorSymbols.has(symbol) || isEligibleETFHoldingsInstrumentType(selectedType)
  if (!preserveETFContext) {
    // The click boundary already reset ETF context; re-setting the same ETF
    // here would erase an industry the user picked while this load ran.
    if (isETF) {
      if (workspaceStore.constituentETF !== symbol) workspaceStore.setConstituentETF(symbol)
    } else if (workspaceStore.constituentETF !== null) workspaceStore.setConstituentETF(null)
  } else {
    preserveDrilldownSymbol.value = symbol
  }
  symbolDraft.value = symbol
  if (!privateBasketSelection) recentStore.add(symbol, undefined, recordHistory)
  // Capture the drill-down ETF before loading the newly selected symbol. A stock
  // selection from a constituent list may itself have no holdings endpoint, but
  // its relevant ratio denominator is still the list's active ETF.
  const comparisonETF = workspaceStore.constituentETF
  if (initialWorkspaceHydrationPending) {
    pendingInitialWorkspaceSymbolIntent = {
      generation,
      symbol,
      instrumentId: canonicalInstrumentId,
      timestamp,
      holdingContext: contextMatchesResolvedIdentity ? displayContext : null,
      selectedHolding: Boolean(holdingContext),
    }
  }
  const explicitTimestampToken = workspaceStore.publishSymbol({
    symbol,
    ...(typeof canonicalInstrumentId === 'number' ? { instrumentId: canonicalInstrumentId } : {}),
    timestamp,
    group: 'blue',
    sourceWindowKey: 'workstation',
  })
  syncChartRouteToSelection(
    symbol,
    canonicalInstrumentId,
    contextMatchesResolvedIdentity ? displayContext : null,
    Boolean(holdingContext),
  )
  // Update linked ratio state at publish time. Data hydration can take much
  // longer than the user's next click and must not delay the visible target.
  if (!privateBasketSelection) updateAutoRatioExpression(symbol, comparisonETF)
  try {
    let localHoldingsReady: Promise<unknown> = Promise.resolve(null)
    const localDataReady = loadSymbolData(symbol, comparisonETF, false, preserveETFContext, promise => {
      localHoldingsReady = promise
    })
    const selectedAcquisition = acquisitionIntent
      ? acquireSelectedTickerData(symbol, generation, localHoldingsReady, confirmedIdentity, acquisitionController.signal, canonicalInstrumentId, resolvedInstrumentType)
      : Promise.resolve()
    await Promise.all([localDataReady, selectedAcquisition])
    if (generation !== symbolSelectionGeneration) return
    if (timestamp) {
      // The store holds this explicit intent against stale cursor publications
      // while the chart is rebuilding. Republish after the bars and renderer
      // have settled, then release the hold so normal chart navigation resumes.
      await nextTick()
      await new Promise<void>(resolve => window.requestAnimationFrame(() => window.requestAnimationFrame(() => resolve())))
      if (generation === symbolSelectionGeneration) {
        workspaceStore.publishTimestamp(timestamp, 'blue', 'workstation')
      }
    }
  } finally {
    if (timestamp && explicitTimestampToken != null) {
      workspaceStore.clearExplicitLinkedTimestamp(timestamp, explicitTimestampToken, 'blue')
    }
  }
}

async function acquireSelectedTickerData(
  symbol: string,
  generation: number,
  localHoldingsReady: Promise<unknown>,
  confirmedIdentity?: InstrumentAcquireResponse,
  signal?: AbortSignal,
  knownInstrumentId?: number | null,
  resolvedInstrumentType = '',
) {
  const timeframe = chartStore.timeframe
  const normalizedSymbol = symbol.trim().toUpperCase()
  const isCurrent = () => generation === symbolSelectionGeneration && !signal?.aborted
    && chartStore.timeframe === timeframe
  const target = Number.isSafeInteger(confirmedIdentity?.instrument?.instrument_id)
    && Number(confirmedIdentity?.instrument?.instrument_id) > 0
    ? { kind: 'instrument' as const, instrument_id: Number(confirmedIdentity!.instrument!.instrument_id) }
    : Number.isSafeInteger(knownInstrumentId) && Number(knownInstrumentId) > 0
      ? { kind: 'instrument' as const, instrument_id: Number(knownInstrumentId) }
      : { kind: 'instrument' as const, symbol: normalizedSymbol }
  const targetInstrumentId = 'instrument_id' in target && Number.isSafeInteger(target.instrument_id)
    ? Number(target.instrument_id)
    : null
  let resolveIdentity!: (value: InstrumentAcquireResponse | null) => void
  let identityResolved = false
  const identityPromise = new Promise<InstrumentAcquireResponse | null>(resolve => { resolveIdentity = resolve })
  const finishIdentity = (value: InstrumentAcquireResponse | null) => {
    if (identityResolved) return
    identityResolved = true
    resolveIdentity(value)
  }
  const makeResolvedIdentity = (instrumentId: number, instrumentType = ''): InstrumentAcquireResponse => ({
    request_id: confirmedIdentity?.request_id ?? `preparation-${generation}`,
    status: 'resolved',
    instrument: {
      instrument_id: instrumentId,
      symbol: normalizedSymbol,
      identity_status: 'resolved',
      ...(instrumentType ? { instrument_type: instrumentType } : {}),
    },
    source_outcomes: [],
  })
  if (confirmedIdentity?.status === 'resolved' && confirmedIdentity.instrument?.symbol.trim().toUpperCase() === normalizedSymbol) {
    finishIdentity(confirmedIdentity)
  } else if (targetInstrumentId !== null) {
      finishIdentity(makeResolvedIdentity(targetInstrumentId, confirmedIdentity?.instrument?.instrument_type ?? resolvedInstrumentType))
  }

  const refreshQueue = new PreparationProgressRefreshQueue()
  const refreshVisibleSelection = async () => {
    if (!isCurrent()) return
    await Promise.allSettled([
      chartStore.refreshLocalBars(),
      refreshMountedWorkstationChartPanels(symbol, timeframe, isCurrent),
      workspaceStore.loadTechnical(symbol, 'high'),
    ])
  }
  const publishIdentityFromProgress = (result: DataEnsureResponse) => {
    if (identityResolved) return
    const identityDependency = result.dependencies.find(dependency => dependency.dataset === 'identity'
      && dependency.status === 'ready'
      && Number.isSafeInteger(dependency.instrument_id)
      && Number(dependency.instrument_id) > 0
      && (!dependency.symbol || dependency.symbol.trim().toUpperCase() === normalizedSymbol))
    if (identityDependency?.instrument_id) {
      finishIdentity(makeResolvedIdentity(identityDependency.instrument_id, confirmedIdentity?.instrument?.instrument_type ?? ''))
      return
    }
    const matching = result.dependencies.find(dependency => dependency.instrument_id
      && dependency.symbol?.trim().toUpperCase() === normalizedSymbol
      && ['profile', 'history', 'holdings', 'fundamentals'].includes(dependency.dataset))
    if (matching?.instrument_id) finishIdentity(makeResolvedIdentity(matching.instrument_id, confirmedIdentity?.instrument?.instrument_type ?? ''))
    else if (result.has_pending_work === false && result.dependencies.some(dependency => dependency.dataset === 'identity'
      && ['unavailable', 'failed'].includes(dependency.status))) finishIdentity(null)
  }
  const preparation = dataPreparationCoordinator.ensure(
    instrumentHistoryPreparationRequest(target, timeframe, true),
    {
      signal,
      priority: 'high',
      onProgress: ({ response, completed, total }) => {
        if (!isCurrent()) return
        publishIdentityFromProgress(response)
        const historyDependencies = response.dependencies.filter(dependency => dependency.dataset === 'history')
        const hasHistoryOutput = historyDependencies.some(dependency => dependency.covered_ranges.length > 0
          || (dependency.covered_start !== null && dependency.covered_end !== null))
        selectionHistoryMessage.value = response.status === 'ready'
          ? `Refreshing the available ${timeframe} history for ${symbol}…`
          : historyPreparationStatusMessage(response, symbol, timeframe, completed, total)
        if (hasHistoryOutput) {
          void refreshQueue.request(response, refreshVisibleSelection).catch(() => {
            if (isCurrent()) selectionHistoryError.value = `Available ${timeframe} history for ${symbol} could not be refreshed; saved bars remain visible.`
          })
        }
      },
    },
  )
  const historyTask = (async () => {
    try {
      const result = await preparation
      if (!isCurrent()) return
      publishIdentityFromProgress(result)
      if (!identityResolved) finishIdentity(null)
      if (result.status === 'ready') {
        selectionHistoryError.value = ''
        selectionHistoryMessage.value = `The admitted ${timeframe} history for ${symbol} is available locally.`
      } else {
        selectionHistoryMessage.value = historyPreparationStatusMessage(result, symbol, timeframe, result.completed, result.total)
      }
      const hasHistoryOutput = result.dependencies.some(dependency => dependency.dataset === 'history'
        && (dependency.covered_ranges.length > 0 || (dependency.covered_start !== null && dependency.covered_end !== null)))
      if (hasHistoryOutput) await refreshQueue.request(result, refreshVisibleSelection)
    } catch (error: any) {
      if (!identityResolved) finishIdentity(null)
      if (isCurrent() && error?.name !== 'AbortError') {
        selectionHistoryError.value = `History for ${symbol} could not be prepared; the current chart remains available.`
      }
    }
  })()

  const holdingsTask = (async () => {
    try {
      const identity = await identityPromise
      if (!isCurrent()) return
      if (!identity || identity.status !== 'resolved' || !identity.instrument
        || identity.instrument.symbol.trim().toUpperCase() !== normalizedSymbol
        || !Number.isSafeInteger(identity.instrument.instrument_id) || identity.instrument.instrument_id <= 0) {
        selectionHoldingsMessage.value = `The ticker identity for ${symbol} could not be confirmed; no holdings request was made.`
        return
      }

      const instrumentId = identity.instrument.instrument_id
      let resolvedType = identity.instrument.instrument_type?.trim() ?? ''
      if (!resolvedType) {
        const localOptions = await queryClient.fetchQuery<Array<{ symbol: string; type: string; instrument_id?: number | null }>>({
          queryKey: ['workstation', 'instrument-search', normalizedSymbol, instrumentId],
          queryFn: () => api.get('/instruments/search', { q: normalizedSymbol, canonical_only: true }, { priority: 'high', signal }),
          staleTime: 0,
        })
        if (!isCurrent()) return
        resolvedType = localOptions.find(option => option.symbol.trim().toUpperCase() === normalizedSymbol
          && option.instrument_id === instrumentId)?.type ?? ''
      }
      if (!isEligibleETFHoldingsInstrumentType(resolvedType)) {
        if (workspaceStore.constituentETF === normalizedSymbol) workspaceStore.setConstituentETF(null)
        return
      }
      if (!isCurrent()) return
      if (workspaceStore.constituentETF !== normalizedSymbol) workspaceStore.setConstituentETF(symbol)
      let stored = workspaceStore.etfHoldings[normalizedSymbol]
      const capability = await readETFHoldingsCapability(symbol, { priority: 'high', signal })
      if (!isCurrent()) return
      if (isCurrentETFHoldingsCapability(capability)) {
        // Only the selected fund's saved holdings read is required to describe
        // this current snapshot. Chart bars, technicals, and industry analysis
        // hydrate independently and must not hold that status behind them.
        await localHoldingsReady
        if (!isCurrent()) return
        stored = workspaceStore.etfHoldings[normalizedSymbol]
        const latest = stored?.snapshot
        selectionHoldingsMessage.value = latest
          ? `Current holdings for ${symbol} are available locally.`
            : `Holdings for ${symbol} are current, but no saved snapshot was returned.`
        return
      }

      const hasLastKnown = Boolean(stored?.snapshot ?? workspaceStore.etfHoldings[normalizedSymbol]?.snapshot)
      selectionHoldingsMessage.value = hasLastKnown
        ? `Showing last-known holdings for ${symbol}; preparing a current local update…`
        : `Preparing holdings for ${symbol}…`
      const holdingsRefreshQueue = new PreparationProgressRefreshQueue()
      const refreshHoldings = () => Promise.allSettled([
        workspaceStore.loadETFHoldings(symbol, 'high'),
        workspaceStore.loadETFIndustries(symbol, 'high'),
      ]).then(() => undefined)
      const holdingsResult = await dataPreparationCoordinator.ensure({
        target: { kind: 'instrument', instrument_id: instrumentId },
        datasets: ['holdings'],
        timeframe,
        adjusted: true,
      }, {
        signal,
        priority: 'high',
        onProgress: progress => {
          if (!isCurrent()) return
          const datasetProgress = selectedDatasetPreparationResponse(progress.response, 'holdings', instrumentId, symbol)
          const dependency = datasetProgress.dependencies.find(item => item.dataset === 'holdings'
            && item.instrument_id === instrumentId)
          if (dependency && (dependency.status === 'ready' || dependency.covered_ranges.length > 0)) {
            void holdingsRefreshQueue.request(progress.response, refreshHoldings)
          }
          if (datasetProgress.status === 'waiting' || datasetProgress.status === 'unavailable'
            || datasetProgress.status === 'failed') {
            selectionHoldingsMessage.value = `Holdings for ${symbol}: ${preparationStatusMessage(datasetProgress)}`
          } else if (datasetProgress.has_pending_work !== false) {
            selectionHoldingsMessage.value = `Preparing holdings for ${symbol} (${datasetProgress.completed}/${datasetProgress.total})…`
          }
        },
      })
      if (!isCurrent()) return
      await holdingsRefreshQueue.request(holdingsResult, refreshHoldings)
      if (!isCurrent()) return
      const page = workspaceStore.etfHoldings[normalizedSymbol]
      const finalSnapshot = page?.snapshot
      const selectedHoldingsResult = selectedDatasetPreparationResponse(holdingsResult, 'holdings', instrumentId, symbol)
      if (selectedHoldingsResult.status === 'ready' && finalSnapshot) {
        selectionHoldingsMessage.value = `Current holdings for ${symbol} are available locally.`
      } else if (selectedHoldingsResult.status === 'partial' || selectedHoldingsResult.status === 'waiting'
        || selectedHoldingsResult.status === 'unavailable' || selectedHoldingsResult.status === 'failed') {
        const detail = `Holdings for ${symbol}: ${preparationStatusMessage(selectedHoldingsResult)}`
        selectionHoldingsMessage.value = finalSnapshot
          ? `Last-known holdings for ${symbol} remain visible. ${detail}`
          : detail
      } else if (finalSnapshot) {
        selectionHoldingsMessage.value = `Saved holdings for ${symbol} are available locally.`
      } else {
        selectionHoldingsMessage.value = `No holdings snapshot is available for ${symbol}.`
      }
    } catch (error: any) {
      if (isCurrent() && error?.name !== 'AbortError') {
        const hasLastKnown = Boolean(workspaceStore.etfHoldings[normalizedSymbol]?.snapshot)
        selectionHoldingsError.value = hasLastKnown
          ? `Holdings for ${symbol} could not be checked; last-known holdings remain visible.`
          : `Holdings for ${symbol} could not be checked; no saved snapshot is available.`
      }
    }
  })()

  await Promise.all([historyTask, holdingsTask])
}

async function loadSymbolData(
  symbol: string,
  comparisonETF = workspaceStore.constituentETF,
  updateRatio = true,
  preserveETFContext = false,
  onHoldingsRead?: (promise: Promise<unknown>) => void,
) {
  if (!preserveActiveUserSymbolDraft(symbol)) symbolDraft.value = symbol
  if (!documentVisible.value) return
  const privateBasketSelection = isPrivateBasketToken(symbol)
  const holdingsRead = preserveETFContext || privateBasketSelection
    ? Promise.resolve(null)
    : workspaceStore.loadETFHoldings(symbol, 'high')
  onHoldingsRead?.(holdingsRead)
  await Promise.all([
    chartStore.loadBars(symbol, chartStore.timeframe, chartStore.barType, true),
    holdingsRead,
    ...(preserveETFContext || privateBasketSelection ? [] : [workspaceStore.loadETFIndustries(symbol, 'high')]),
    ...(!privateBasketSelection ? [workspaceStore.loadTechnical(symbol, 'high')] : []),
  ])
  if (updateRatio && !privateBasketSelection) updateAutoRatioExpression(symbol, comparisonETF)
}

function scheduleSymbolSearch(value: string) {
  if (!symbolSearchEnabled.value) return
  discoveryRetryAbortController?.abort()
  discoveryRetryAbortController = null
  candidateResolutionAbortController?.abort()
  candidateResolutionAbortController = null
  candidateResolutionSequence += 1
  searchOptionExplicitlyNavigatedFor.value = ''
  finishPendingSymbolSearch()
  if (searchTimer) clearTimeout(searchTimer)
  if (discoveryTimer) clearTimeout(discoveryTimer)
  const requestId = ++searchRequest
  const query = value.trim()
  let resolvePending!: () => void
  const promise = new Promise<void>(resolve => { resolvePending = resolve })
  pendingSymbolSearch = { requestId, query, promise, resolve: resolvePending }
  sourceDiscoveryLoading.value = false
  sourceResolving.value = false
  sourceDiscoverySettled.value = false
  sourceDiscoveryTerminalNoMatch.value = false
  sourceCandidates.value = []
  if (!query) {
    searchResults.value = []
    searchIndex.value = -1
    searchLoading.value = false
    searchSettled.value = false
    searchError.value = ''
    sourceDiscoverySettled.value = false
    lastDiscoveryQuery = ''
    finishSymbolSearch(requestId)
    return
  }
  searchLoading.value = true
  searchSettled.value = false
  searchError.value = ''
  // Do not leave options from the previous query selectable while this
  // debounced request is pending.
  searchResults.value = []
  sourceCandidates.value = []
  sourceDiscoveryMessage.value = ''
  sourceDiscoveryError.value = ''
  sourceDiscoverySettled.value = false
  lastDiscoveryQuery = ''
  searchTimer = setTimeout(async () => {
    try {
      const results = await queryClient.fetchQuery<Array<{ symbol: string; name: string; exchange: string; type: string }>>({
        queryKey: ['workstation', 'instrument-search', query.toUpperCase()],
      queryFn: () => api.get<Array<{ symbol: string; name: string; exchange: string; type: string; instrument_id?: number | null }>>(
        '/instruments/search',
        { q: query, canonical_only: true },
        { priority: 'high' },
      ),
        staleTime: 30_000,
      })
      if (!componentMounted || requestId !== searchRequest || symbolDraft.value.trim() !== query) return
      searchResults.value = results
      searchIndex.value = results.length ? 0 : -1
      searchLoading.value = false
      searchSettled.value = true
      // Wait for the local canonical lookup, then debounce discovery only when
      // no exact ticker exists. New input cancels this request before it starts.
      if (shouldDiscoverTicker(query, results)) {
        discoveryTimer = scheduleTickerDiscovery(() => {
          if (requestId === searchRequest && symbolDraft.value.trim() === query) {
            void discoverSymbolDraft(query, requestId).finally(() => finishSymbolSearch(requestId))
          } else {
            finishSymbolSearch(requestId)
          }
        })
      } else {
        sourceDiscoverySettled.value = true
        finishSymbolSearch(requestId)
      }
    } catch {
      if (componentMounted && requestId === searchRequest) {
        searchResults.value = []
        searchIndex.value = -1
        searchLoading.value = false
        searchSettled.value = true
        searchError.value = 'Unable to search canonical instruments. Try again.'
      }
      finishSymbolSearch(requestId)
    }
  }, 120)
}

function finishSymbolSearch(requestId?: number) {
  if (!pendingSymbolSearch || (requestId != null && pendingSymbolSearch.requestId !== requestId)) return
  const pending = pendingSymbolSearch
  pendingSymbolSearch = null
  pending.resolve()
}

function finishPendingSymbolSearch() {
  finishSymbolSearch()
}

function setSymbolSelectionError(message: string) {
  lastSymbolSelectionError = message
  workspaceStore.error = message
}

function clearSupersededSymbolSelectionError() {
  if (lastSymbolSelectionError && workspaceStore.error === lastSymbolSelectionError) {
    workspaceStore.error = null
  }
  lastSymbolSelectionError = null
}

async function discoverSymbolDraft(rawQuery = symbolDraft.value, requestGeneration = searchRequest) {
  const query = rawQuery.trim()
  if (!query || sourceDiscoveryLoading.value || sourceResolving.value) return
  const queryKey = query.toUpperCase()
  if (lastDiscoveryQuery === queryKey) return
  lastDiscoveryQuery = queryKey
  discoveryRetryAbortController?.abort()
  const controller = new AbortController()
  discoveryRetryAbortController = controller
  const isCurrent = () => componentMounted
    && !controller.signal.aborted
    && requestGeneration === searchRequest
    && symbolDraft.value.trim().toUpperCase() === queryKey
  const retryLifecycle = createKnownTemporaryRetryLifecycle(
    isCurrent,
    retryAt => {
      sourceDiscoveryLoading.value = false
      sourceDiscoveryMessage.value = `Ticker lookup is temporarily waiting to retry after ${new Date(retryAt).toLocaleTimeString()}.`
    },
    controller.signal,
  )
  sourceDiscoveryLoading.value = true
  sourceDiscoverySettled.value = false
  sourceDiscoveryError.value = ''
  sourceDiscoveryMessage.value = ''
  sourceCandidates.value = []
  try {
    while (isCurrent()) {
      sourceDiscoveryLoading.value = true
      sourceDiscoveryMessage.value = ''
      const result = await discoverInstruments(query, [], 10, { priority: 'high', signal: controller.signal })
      if (!isCurrent()) return
      const retryAt = result.retry_at
        ?? result.source_outcomes.find(outcome => outcome.status === 'held' && outcome.retry_at)?.retry_at
      const hasHeldSource = result.source_outcomes.some(outcome => outcome.status === 'held')
      const shouldWait = (result.status === 'held' || result.status === 'unavailable' || hasHeldSource) && Boolean(retryAt)
      if (shouldWait && await retryLifecycle.wait(retryAt) === 'ready') continue
      sourceCandidates.value = Array.isArray(result.candidates) ? result.candidates : []
      sourceDiscoveryTerminalNoMatch.value = result.status === 'no_match' && sourceCandidates.value.length === 0
      sourceDiscoveryMessage.value = sourceDiscoveryTerminalNoMatch.value
        ? ''
        : tickerDiscoveryMessage(result.status, sourceCandidates.value.length)
      if ((result.status === 'held' || result.status === 'unavailable' || hasHeldSource) && !sourceCandidates.value.length) {
        sourceDiscoveryMessage.value = 'Ticker lookup is unavailable. You can try again manually.'
      }
      return
    }
  } catch {
    if (isCurrent()) {
      sourceDiscoveryError.value = 'Ticker lookup failed. Local search and cached charts remain available.'
    }
  } finally {
    if (isCurrent()) {
      sourceDiscoveryLoading.value = false
      sourceDiscoverySettled.value = true
    }
    if (discoveryRetryAbortController === controller) discoveryRetryAbortController = null
  }
}

async function resolveSourceCandidate(candidate: InstrumentDiscoveryCandidate) {
  if (sourceResolving.value) return
  const queryKey = symbolDraft.value.trim().toUpperCase()
  const requestGeneration = searchRequest
  candidateResolutionAbortController?.abort()
  const controller = new AbortController()
  candidateResolutionAbortController = controller
  const resolutionId = ++candidateResolutionSequence
  const isCurrent = () => componentMounted
    && !controller.signal.aborted
    && resolutionId === candidateResolutionSequence
    && requestGeneration === searchRequest
    && symbolDraft.value.trim().toUpperCase() === queryKey
  const retryLifecycle = createKnownTemporaryRetryLifecycle(
    isCurrent,
    retryAt => {
      sourceResolving.value = false
      sourceDiscoveryMessage.value = `Ticker confirmation is temporarily waiting to retry after ${new Date(retryAt).toLocaleTimeString()}.`
    },
    controller.signal,
  )
  sourceResolving.value = true
  sourceDiscoveryError.value = ''
  try {
    let result: InstrumentAcquireResponse | null = null
    while (isCurrent()) {
      sourceResolving.value = true
      sourceDiscoveryMessage.value = ''
      result = await resolveDiscoveredInstrument(candidate, { priority: 'high', signal: controller.signal })
      if (!isCurrent()) return
      const retryAt = result.retry_at
        ?? result.source_outcomes.find(outcome => outcome.status === 'held' && outcome.retry_at)?.retry_at
      if (result.status === 'held' && await retryLifecycle.wait(retryAt) === 'ready') continue
      break
    }
    if (!isCurrent() || !result) return
    if (result.status !== 'resolved' || !result.instrument
      || !Number.isSafeInteger(result.instrument.instrument_id) || result.instrument.instrument_id <= 0) {
      sourceDiscoveryMessage.value = result.status === 'identity_conflict'
        ? 'This ticker listing could not be confirmed. No chart was opened.'
        : result.status === 'held'
          ? 'Ticker confirmation is currently unavailable.'
          : result.status === 'no_match'
            ? 'No matching ticker was found.'
            : result.status === 'failed'
              ? 'Ticker confirmation failed.'
              : 'This ticker listing is not available.'
      return
    }
    selectSearchResult(result.instrument.symbol, result.instrument.instrument_id, candidate.type, result)
  } catch {
    if (isCurrent()) {
      sourceDiscoveryError.value = 'Ticker confirmation failed. No chart was opened.'
    }
  } finally {
    if (isCurrent()) sourceResolving.value = false
    if (candidateResolutionAbortController === controller) candidateResolutionAbortController = null
  }
}

function selectSearchResult(
  symbol: string,
  instrumentId?: number | null,
  instrumentType = '',
  confirmedIdentity?: InstrumentAcquireResponse,
) {
  // Close before changing the draft. The input remains focused while an option
  // is selected with the mouse, so relying on blur leaves the listbox mounted
  // above the workstation and can intercept the next tool click.
  closeSymbolSearch()
  symbolDraft.value = symbol
  void selectSymbol(symbol, undefined, false, instrumentId, true, false, instrumentType, true, confirmedIdentity)
}

async function goToSymbolDraft() {
  await submitSymbolDraft()
}

async function submitSymbolDraft() {
  const symbol = symbolDraft.value.trim()
  if (!symbol) return
  const requestId = searchRequest
  const submission = { query: symbol.toUpperCase(), requestId }
  if (symbolSubmissionInFlight?.query === submission.query
    && symbolSubmissionInFlight.requestId === submission.requestId) return
  // A newer query is a newer selection intent. It must be allowed to finish
  // even while an older Go action is still waiting for its own search result.
  symbolSubmissionInFlight = submission
  const explicitlyNavigatedCurrentQuery = searchOptionExplicitlyNavigatedFor.value === symbol.toUpperCase()
  try {
    const immediateLocal = explicitlyNavigatedCurrentQuery
      ? searchResults.value[searchIndex.value]
      : searchResults.value.find(result => result.symbol.trim().toUpperCase() === symbol.toUpperCase())
    if (immediateLocal) {
      recentSymbolsOpen.value = false
      selectSearchResult(immediateLocal.symbol, immediateLocal.instrument_id, immediateLocal.type)
      return
    }
    const pending = pendingSymbolSearch
    if (pending && pending.requestId === requestId && pending.query === symbol) {
      await pending.promise
    }
    if (requestId !== searchRequest || symbolDraft.value.trim() !== symbol) return

    const navigatedLocal = explicitlyNavigatedCurrentQuery ? searchResults.value[searchIndex.value] : undefined
    // A canonical exact result may arrive while Go is waiting for the current
    // debounced lookup. Use that newly confirmed row before considering any
    // provisional prefix candidate; only an explicit arrow choice overrides it.
    const local = navigatedLocal ?? searchResults.value.find(result =>
      result.symbol.trim().toUpperCase() === symbol.toUpperCase(),
    )
    if (local) {
      recentSymbolsOpen.value = false
      selectSearchResult(local.symbol, local.instrument_id, local.type)
      return
    }

    if (!explicitlyNavigatedCurrentQuery) {
      const exactCandidates = sourceCandidates.value.filter(candidate =>
        candidate.symbol.trim().toUpperCase() === symbol.toUpperCase(),
      )
      if (exactCandidates.length === 1) {
        recentSymbolsOpen.value = false
        void resolveSourceCandidate(exactCandidates[0])
        return
      }
      if (exactCandidates.length > 1) {
        sourceDiscoveryMessage.value = `More than one listing matches ${symbol.toUpperCase()}. Choose the correct exchange listing.`
        return
      }
    }

    recentSymbolsOpen.value = false
    closeSymbolSearch()
    void selectSymbol(symbol, undefined, false, undefined, true, false, '', true)
  } finally {
    if (symbolSubmissionInFlight === submission) symbolSubmissionInFlight = null
  }
}

function selectRecentSymbol(symbol: string) {
  recentSymbolsOpen.value = false
  closeSymbolSearch()
  symbolDraft.value = symbol
  void selectSymbol(symbol, undefined, false, undefined, true, false, '', true)
}

function handleSymbolInputKeydown(event: KeyboardEvent) {
  if (event.key === 'ArrowDown' && searchResults.value.length) {
    event.preventDefault()
    searchOptionExplicitlyNavigatedFor.value = symbolDraft.value.trim().toUpperCase()
    searchIndex.value = (searchIndex.value + 1) % searchResults.value.length
  } else if (event.key === 'ArrowUp' && searchResults.value.length) {
    event.preventDefault()
    searchOptionExplicitlyNavigatedFor.value = symbolDraft.value.trim().toUpperCase()
    searchIndex.value = (searchIndex.value - 1 + searchResults.value.length) % searchResults.value.length
  } else if (event.key === 'Enter') {
    event.preventDefault()
    void submitSymbolDraft()
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
  void selectSymbol(symbol, timestamp, false, instrumentId, true, false, '', true)
}

function selectIndustryForContext(industry: string, etf?: string) {
  const contextETF = etf?.trim().toUpperCase() || workspaceStore.constituentETF || ''
  void workspaceStore.selectIndustry(contextETF, industry)
}

function setLinkedTimeframe(timeframe: string, group: LinkGroup = 'blue') {
  // As with shell symbol selection, preserve an explicit choice made while
  // the first saved snapshot is in flight. The snapshot can replace the
  // linked timeframe before the initial workspace load settles.
  if (!workspaceReady.value) pendingTimeframeSelections.set(group, timeframe)
  workspaceStore.publishTimeframe(timeframe, group, 'workstation')
}

function cancelLinkedTimeframePreparation() {
  linkedTimeframePreparationGeneration += 1
  linkedTimeframePreparationAbortController?.abort()
  linkedTimeframePreparationAbortController = null
}

async function prepareLinkedTimeframeHistory(symbol: string, timeframe: Timeframe) {
  cancelLinkedTimeframePreparation()
  const generation = linkedTimeframePreparationGeneration
  const controller = new AbortController()
  linkedTimeframePreparationAbortController = controller
  const isCurrent = () => componentMounted
    && generation === linkedTimeframePreparationGeneration
    && !controller.signal.aborted
    && activeSymbol.value.trim().toUpperCase() === symbol
    && workspaceStore.linkedTimeframe === timeframe
    && chartStore.symbol.trim().toUpperCase() === symbol
    && chartStore.timeframe === timeframe

  selectionHistoryError.value = ''
  selectionHistoryMessage.value = `Checking saved ${timeframe} history for ${symbol}…`

  try {
    const linkedInstrument = workspaceStore.linkedSymbols?.blue
    const currentChartInstrument = chartStore.instrument
    const holding = activeHoldingContext.value
    const candidates = [
      holding?.symbol === symbol ? holding.context.instrumentId : null,
      linkedInstrument?.symbol.trim().toUpperCase() === symbol ? linkedInstrument.instrumentId : null,
      currentChartInstrument?.symbol.trim().toUpperCase() === symbol ? currentChartInstrument.id : null,
    ]
    let instrumentId = candidates.find(candidate => Number.isSafeInteger(candidate) && Number(candidate) > 0) ?? null

    if (instrumentId === null) {
      const resolved = await resolveKnownInstrument(symbol, 'Workstation timeframe history', {
        canonicalOnly: true,
        priority: 'high',
        foreground: true,
        signal: controller.signal,
      })
      if (!isCurrent()) return
      if (resolved.symbol.trim().toUpperCase() !== symbol || typeof resolved.id !== 'number'
        || !Number.isSafeInteger(resolved.id) || resolved.id <= 0) {
        selectionHistoryError.value = `The canonical identity for ${symbol} could not be confirmed; ${timeframe} history was not requested.`
        return
      }
      instrumentId = resolved.id
    }

    const request: DataEnsureRequest = {
      target: { kind: 'instrument', instrument_id: instrumentId },
      datasets: ['history'],
      timeframe,
      adjusted: true,
    }
    const refreshQueue = new PreparationProgressRefreshQueue()
    const refreshCurrentChart = async () => {
      if (!isCurrent()) return
      await Promise.allSettled([
        chartStore.refreshLocalBars(),
        refreshMountedWorkstationChartPanels(symbol, timeframe, isCurrent),
      ])
    }
    const historyResult = (response: DataEnsureResponse) => selectedDatasetPreparationResponse(response, 'history', instrumentId!, symbol)
    const hasHistoryOutput = (response: DataEnsureResponse) => response.dependencies.some(dependency =>
      dependency.dataset === 'history'
      && dependency.instrument_id === instrumentId
      && (dependency.symbol === null || dependency.symbol.trim().toUpperCase() === symbol)
      && (dependency.status === 'ready' || dependency.covered_ranges.length > 0
        || (dependency.covered_start !== null && dependency.covered_end !== null)),
    )
    const result = await dataPreparationCoordinator.ensure(request, {
      signal: controller.signal,
      priority: 'high',
      onProgress: ({ response, completed, total }) => {
        if (!isCurrent()) return
        const scoped = historyResult(response)
        selectionHistoryMessage.value = historyPreparationStatusMessage(scoped, symbol, timeframe, completed, total)
        if (hasHistoryOutput(scoped)) {
          void refreshQueue.request(response, refreshCurrentChart).catch(() => {
            if (isCurrent()) selectionHistoryError.value = `Available ${timeframe} history for ${symbol} could not be refreshed; saved bars remain visible.`
          })
        }
      },
    })
    if (!isCurrent()) return
    const scoped = historyResult(result)
    selectionHistoryMessage.value = historyPreparationStatusMessage(scoped, symbol, timeframe, result.completed, result.total)
    if (hasHistoryOutput(scoped)) await refreshQueue.request(result, refreshCurrentChart)
  } catch (error: any) {
    if (isCurrent() && error?.name !== 'AbortError') {
      selectionHistoryError.value = `History for ${symbol} could not be prepared; the current ${timeframe} chart remains available.`
    }
  } finally {
    if (linkedTimeframePreparationAbortController === controller) linkedTimeframePreparationAbortController = null
  }
}

async function signOut() {
  await authStore.logout()
}

async function selectIndustryProxy(symbol: string, instrumentId?: number | null) {
  const generation = ++drilldownSelectionGeneration
  // Proxy rows normally carry their canonical identity, but keep direct or
  // keyboard-triggered proxy navigation identity-safe as well. This avoids
  // publishing a ticker-only link when a valid local instrument exists.
  const resolved = await resolveKnownInstrument(symbol, 'Industry ETF proxy', { canonicalOnly: true, priority: 'high' })
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
  // Acknowledge the accepted command before hydration can suspend it. Keeping
  // the menu open makes a queued ordinary click indistinguishable from a lost
  // click and invites a second activation of the same command.
  toolLibraryOpen.value = false
  // A shell click can arrive before the asynchronous onMounted hook marks the
  // component live. Wait for that lifecycle boundary instead of yielding one
  // render turn and accidentally dropping the first Add-tool action on a cold
  // /chart navigation. Unmount resolves the same signal so teardown still
  // cancels the command.
  if (!componentMounted) {
    await componentMountSettled
    if (!componentMounted) return
  }
  // The dock can already expose a fully usable active tab while the initial
  // workspace promise is still settling (notably after Golden Layout restores
  // a persisted snapshot). Do not strand an Add-tool click behind that promise
  // when the concrete tab needed for the mutation is already present. Only
  // wait for readiness when there is no active tab to mutate at all.
  if (!workspaceReady.value && !workspaceStore.activeTab) {
    if (workspaceLoadPromise) {
      await workspaceLoadPromise
      if (!componentMounted) return
    }
    if (!componentMounted) return
    // The click can arrive in the same turn as component mount, before the
    // onMounted callback has assigned its load promise. Wait on the explicit
    // readiness signal instead of silently dropping the user's command after
    // an arbitrary polling budget while the canonical workspace is still
    // hydrating.
    if (!workspaceReady.value && !workspaceStore.activeTab) {
      await workspaceReadyPromise
      if (!componentMounted) return
    }
  }
  // The user may have left this workstation while its snapshot was loading.
  // The old view must never apply a pending command to the shared store after
  // teardown (including a tab now owned by the replacement view).
  if (!componentMounted) return
  if (!workspaceStore.activeTab) {
    workspaceStore.error = 'The workstation layout is not available yet; please retry the tool action.'
    return
  }
  const opened = workspaceStore.openTool(tool, configurationOverride)
  if (!opened) return
  await nextTick()
  if (!componentMounted) return
  // Golden Layout can finish creating the tab after its virtual component has
  // mounted. Clicking the concrete tab element is the same interaction as a
  // user selecting it and guarantees the newly opened tool is foregrounded.
  // Installing a component can produce a late Golden Layout state restore. In
  // that window a click may activate the tab successfully and then be followed
  // by the restore selecting the previous tab. Keep applying the same real tab
  // interaction until the DOM confirms the requested tab is active; this is
  // bounded and exits immediately once the user-visible state is correct.
  // A cold Golden Layout reinstall can take longer than a single second when
  // the browser is already carrying the workstation's chart/watchlist work.
  // Keep the activation bounded, but give the newly installed component enough
  // time to acquire its real stack/header before treating the open action as
  // complete.
  // Bound by elapsed time rather than attempts: on a busy machine the layout
  // reinstall alone can exceed a fixed attempt budget.
  const activationDeadline = Date.now() + 15_000
  while (Date.now() < activationDeadline) {
    if (!componentMounted) return
    const toolRoot = [...document.querySelectorAll<HTMLElement>('[data-tool-key]')]
      .find(candidate => candidate.dataset.toolKey === opened.instance_key)
    // Do not fall back to a same-titled tab while the new virtual component is
    // still mounting. A persisted Notes/Chart/etc. tab can already be visible;
    // treating that tab as success would leave the newly opened component hidden.
    if (!toolRoot) {
      await new Promise(resolve => setTimeout(resolve, 25))
      if (!componentMounted) return
      continue
    }
    // Virtual component roots are rendered outside Golden Layout's stack DOM.
    // The host contract already applies active_window_key through its layout
    // watcher, so waiting for or clicking a nonexistent `.lm_tab` only adds a
    // multi-second delay to ordinary Add-tool and Market Map actions.
    if (isActiveVirtualToolRoot(toolRoot, opened.instance_key, workspaceStore.activeTab?.active_window_key)) {
      // Opening a tool mutates both the active tab's window list and its
      // active-window selection. Flush that exact active-layout snapshot once
      // the user-visible tool is active so a fast sign-out/reload cannot leave
      // the panel in memory but restore an older workspace context.
      const persisted = await workspaceStore.saveSnapshot()
      if (!componentMounted) return
      if (!persisted && workspaceStore.snapshotSaveStatus === 'error') {
        workspaceStore.error = workspaceStore.snapshotSaveError ?? 'The tool opened, but its workspace selection could not be saved.'
      }
      return opened
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
        if (!componentMounted) return
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

async function catalogueTool(key: string) {
  const current = workspaceStore.toolDefinition(key)
  if (current) return current
  return (await workspaceStore.loadToolCatalogue()).find(tool => tool.key === key) ?? null
}

async function openMarketMap(sourceId: string) {
  const normalized = sourceId.trim()
  if (!normalized) return
  const definition = await catalogueTool('market-map')
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
  const studyDefinition = await catalogueTool('study-lab')
  if (studyDefinition) await openTool(studyDefinition)
}

function renameTab(stableKey: string, name: string) {
  workspaceStore.renameTab(stableKey, name)
}

function updateLayoutRenameDraft(stableKey: string, event: Event) {
  const value = (event.target as HTMLInputElement).value
  layoutRenameDrafts.value = { ...layoutRenameDrafts.value, [stableKey]: value }
  // Commit the local name while the field is edited so an older in-flight
  // snapshot cannot replace it before the browser emits change on blur.
  renameTab(stableKey, value)
}

function commitLayoutRenameDraft(stableKey: string, event: Event) {
  const value = (event.target as HTMLInputElement).value
  renameTab(stableKey, value)
  const next = { ...layoutRenameDrafts.value }
  delete next[stableKey]
  layoutRenameDrafts.value = next
}

function deleteTab(stableKey: string, name: string) {
  if (!window.confirm(`Delete layout “${name}”?`)) return
  const recovery = workspaceStore.captureTabRecovery(stableKey)
  if (!recovery || !workspaceStore.deleteTab(stableKey)) return
  deletedLayoutRecoveryStatus.value = 'ready'
  deletedLayoutRecovery.value = recovery
}

async function undoDeletedLayout() {
  const recovery = deletedLayoutRecovery.value
  if (!recovery || deletedLayoutRecoveryStatus.value === 'saving') return
  if (deletedLayoutRecoveryStatus.value !== 'error' && !workspaceStore.restoreDeletedTab(recovery)) return
  deletedLayoutRecoveryStatus.value = 'saving'
  // Keep the recovery affordance visible until the latest restored layout is
  // acknowledged by the server. A failed write remains retryable instead of
  // hiding the only indication that the restored layout is local-only.
  const saved = await workspaceStore.saveSnapshot()
  if (!saved) {
    deletedLayoutRecoveryStatus.value = 'error'
    return
  }
  await replaceDockAfterWorkspaceChange()
  deletedLayoutRecovery.value = null
  deletedLayoutRecoveryStatus.value = 'ready'
}

function retryWorkspaceSave() {
  void workspaceStore.saveSnapshot()
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
  const alreadyReplacingWorkspace = workspaceReplacementPending.value
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
    workspaceReplacementPending.value = alreadyReplacingWorkspace
    await nextTick()
  }
}

async function openAlertsTool() {
  const alerts = await catalogueTool('alerts')
  if (alerts) openTool(alerts)
}

type MapAnalysisPublication = {
  target: 'breadth' | 'study_lab'
  sourceId: string
  selectedIds: number[]
  selectedSymbols: string[]
  scope: 'full' | 'selection'
}

async function saveWorkspaceSnapshotIfSupported() {
  const saveSnapshot = (workspaceStore as unknown as { saveSnapshot?: () => Promise<void> }).saveSnapshot
  if (typeof saveSnapshot === 'function') await saveSnapshot.call(workspaceStore)
}

async function remountDockAfterSnapshot(
  mountedConfiguration: Record<string, unknown>,
  publishedConfiguration: Record<string, unknown>,
) {
  // saveSnapshot replaces the canonical workspace object with the server
  // response. Golden Layout may still hold the pre-save tool object, so mirror
  // the accepted configuration into that mounted object and then reinstall the
  // completed layout from the server-confirmed workspace.
  for (const key of Object.keys(mountedConfiguration)) delete mountedConfiguration[key]
  Object.assign(mountedConfiguration, publishedConfiguration)
  // A virtual root can emit one final layout callback as it is destroyed.
  // Keep the host out of the DOM until that callback is fenced, then mount it
  // from the server-confirmed workspace snapshot and configuration.
  const wasReplacing = workspaceReplacementPending.value
  workspaceReplacementPending.value = true
  try {
    await nextTick()
    workspaceReloadKey.value += 1
    await nextTick()
  } finally {
    workspaceReplacementPending.value = wasReplacing
    await nextTick()
  }
}

async function saveToolConfigurationAndRemount(
  windowKey: string,
  mountedConfiguration: Record<string, unknown>,
  publishedConfiguration: Record<string, unknown>,
) {
  // Fence virtual-root layout callbacks for the entire publish/save/remount
  // transaction. A callback from the old root must not replace an accepted
  // selected-member source with the factory's previous group configuration.
  const wasReplacing = workspaceReplacementPending.value
  workspaceReplacementPending.value = true
  await nextTick()
  try {
    updateToolConfiguration(windowKey, publishedConfiguration)
    await saveWorkspaceSnapshotIfSupported()
    // Saving can replace the canonical workspace object with the API response.
    // Keep the just-accepted semantic source on that current object before the
    // dock remounts, even if a delayed stateChanged event raced the response.
    const savedWindow = workspaceStore.workspace?.tabs
      .flatMap(tab => tab.windows)
      .find(window => window.instance_key === windowKey)
    if (savedWindow) {
      for (const key of Object.keys(savedWindow.configuration)) delete savedWindow.configuration[key]
      Object.assign(savedWindow.configuration, publishedConfiguration)
    }
    await remountDockAfterSnapshot(mountedConfiguration, publishedConfiguration)
  } finally {
    workspaceReplacementPending.value = wasReplacing
    await nextTick()
  }
}

type StudyDefinitionOpen = {
  name: string
  versionId: number
  source: string
  outputContract: string
  parameterSchema: Record<string, unknown>
  defaultParameters: Record<string, unknown>
}

async function openStudyDefinition(definition: StudyDefinitionOpen) {
  const studyDefinition = await catalogueTool('study-lab')
  if (!studyDefinition || !Number.isInteger(definition.versionId) || !definition.source.trim()) return
  const defaults = definition.defaultParameters ?? {}
  const configuration: Record<string, unknown> = {
    study_asset_version_id: definition.versionId,
    study_name: definition.name,
    study_source: definition.source,
    study_output_contract: definition.outputContract,
    parameter_schema: JSON.stringify(definition.parameterSchema ?? {}),
    study_default_parameters: defaults,
  }
  const stringDefaults = ['symbol', 'universe_source_id', 'symbols', 'timeframe', 'benchmark', 'adjustment', 'session', 'start_date', 'end_date', 'as_of']
  for (const key of stringDefaults) {
    if (typeof defaults[key] === 'string' && defaults[key].trim()) configuration[key] = defaults[key]
  }
  await openTool(studyDefinition, configuration)
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
      await saveToolConfigurationAndRemount(existing.window.instance_key, mountedConfiguration, publishedConfiguration)
      return
    }
    const definition = await catalogueTool('breadth')
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
  const definition = await catalogueTool('study-lab')
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
  await saveWorkspaceSnapshotIfSupported()
  await remountDockAfterSnapshot(mountedConfiguration, publishedConfiguration)
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
    await saveWorkspaceSnapshotIfSupported()
    await remountDockAfterSnapshot(mountedConfiguration, publishedConfiguration)
    return
  }
  await selectSymbol(row.symbol, undefined, false, row.instrumentId, true, false, '', true)
  if (action === 'chart') {
    const chart = await catalogueTool('chart')
    if (chart) openTool(chart)
    return
  }
  const toolType = action === 'note' ? 'notes' : action === 'alert' ? 'alerts' : action
  const tools = workspaceStore.toolCatalogue.length ? workspaceStore.toolCatalogue : await workspaceStore.loadToolCatalogue()
  const tool = tools.find(candidate => candidate.tool_type === toolType) ?? null
  if (tool) openTool(tool)
}

function floatTool(windowKey: string) {
  const tab = workspaceStore.activeTabKey
  const href = router.resolve({ path: `/popout/${encodeURIComponent(windowKey)}`, query: { tab } }).href
  const tool = workspaceStore.workspace?.tabs.flatMap(item => item.windows).find(item => item.instance_key === windowKey)
  const popup = window.open(href, `workstation-${windowKey}`, popoutWindowFeatures(readPopoutGeometry(tool?.style, window.screen as Screen & { availLeft?: number; availTop?: number })))
  if (!popup) {
    workspaceStore.error = BLOCKED_POPOUT_ERROR
    return
  }
  // A blocked first attempt is recoverable by retrying after the user grants
  // the browser gesture permission. Clear only this transient status so a
  // successful retry does not leave stale recovery guidance in the footer.
  if (workspaceStore.error === BLOCKED_POPOUT_ERROR) workspaceStore.error = null
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

type DockToolDescriptor = { instance_key: string; title: string; tool_type: string }
type DockToolRenderActions = { toggleMaximize: () => Promise<void>; maximized: Readonly<Ref<boolean>>; maximizing: Readonly<Ref<boolean>>; close: () => void }

// Golden Layout renders each virtual tool once into a detached root. Every
// acknowledged snapshot replaces the store's window records, so binding the
// mount-time record would strand later configuration edits on an object the
// mounted tool never reads. Re-resolve the live record on each reactive render.
const DockToolBinding = defineComponent({
  name: 'DockToolBinding',
  props: {
    dockTool: { type: Object as PropType<DockToolDescriptor>, required: true },
    actions: { type: Object as PropType<DockToolRenderActions>, required: true },
  },
  setup(bindingProps) {
    let lastTool: WorkspaceWindowState | undefined
    return () => {
      const key = bindingProps.dockTool.instance_key
      const tool = workspaceStore.activeTab?.windows.find(window => window.instance_key === key)
        ?? workspaceStore.workspace?.tabs.flatMap(tab => tab.windows).find(window => window.instance_key === key)
        ?? lastTool
      if (tool) lastTool = tool
      return renderDockToolContent(tool, bindingProps.dockTool, bindingProps.actions)
    }
  },
})

function renderDockTool(dockTool: DockToolDescriptor, actions: DockToolRenderActions): VNode {
  return h(DockToolBinding, { dockTool, actions })
}

function renderDockToolContent(tool: WorkspaceWindowState | undefined, dockTool: DockToolDescriptor, actions: DockToolRenderActions): VNode {
  if (!tool) return h('div', { class: 'workstation__missing-tool' }, `Missing persisted tool: ${dockTool.instance_key}`)
  return h(WorkstationToolContent, {
    tool,
    maximizedState: actions.maximized,
    maximizingState: actions.maximizing,
    activeWindowKey: workspaceStore.activeTab?.active_window_key,
    factoryLayout: workspaceStore.activeTabKey,
    onActivate: () => workspaceStore.setActiveWindow(dockTool.instance_key),
    onSelect: (symbol: string, instrumentId?: number | null, preserveETFContext?: boolean) => void selectSymbol(symbol, undefined, false, instrumentId, true, Boolean(preserveETFContext), '', true),
    onHoldingSelect: (symbol: string, context: ETFHoldingDrilldownContext, identity?: InstrumentAcquireResponse) => selectHoldingInDashboard(symbol, context, identity),
    onCompare: (symbols: string[]) => compareSymbols(symbols),
    onRatio: (symbols: string[]) => void openMarketMapRatio(symbols),
    onReorder: (watchlistId: number, itemIds: number[]) => reorderWatchlistItems(watchlistId, itemIds),
    onRowAction: (action: 'chart' | 'compare' | 'ratio' | 'note' | 'alert' | 'copy', row: { symbol: string; instrumentId: number | null }) => void handleRowAction(action, row),
    onMarketMap: (sourceId: string) => void openMarketMap(sourceId),
    onOccurrence: (symbol: string, timestamp: string, instrumentId?: number | null) => void selectSymbol(symbol, timestamp, false, instrumentId, true, false, '', true),
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
    onOpenStudy: (definition: StudyDefinitionOpen) => void openStudyDefinition(definition),
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

function persistGoldenLayout(layout: Record<string, unknown>, visibleToolKeys: string[], sourceTabKey?: string | null) {
  // Golden Layout may report one last state change from the previous tab while
  // Vue is switching the active tab. Never write that old tree into the newly
  // selected tab; the host will emit a fresh snapshot after its replacement
  // install completes.
  if (workspaceReplacementPending.value || (sourceTabKey && sourceTabKey !== workspaceStore.activeTabKey)) return
  workspaceStore.applyActiveLayout(layout, visibleToolKeys)
}

function persistMaximizedLayout() {
  // Maximize/restore is an explicit workspace action. Flush the layout emitted
  // by Golden Layout before its toolbar reports the new state, so an immediate
  // reload cannot interrupt the snapshot debounce or its conflict merge.
  return workspaceStore.saveSnapshot()
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
  if (workspaceStore.isEditorTarget(event.target) || isInteractiveTarget(event.target)) return
  if (event.key.toLowerCase() === 'n' && event.shiftKey && !event.ctrlKey && !event.metaKey && !event.altKey) {
    event.preventDefault()
    void catalogueTool('notes').then(notes => { if (notes) return openTool(notes) })
    return
  }
  if (event.key.toLowerCase() === 'l' && event.shiftKey && !event.ctrlKey && !event.metaKey && !event.altKey) {
    const activeTab = workspaceStore.activeTab
    const activeWindowKey = isPopout.value
      ? String(route.params.windowKey ?? '')
      : activeTab?.active_window_key
    if (!activeWindowKey) return
    const activeTool = Array.from(document.querySelectorAll<HTMLElement>('.tool-window[data-window-key]'))
      .find(tool => tool.dataset.windowKey === activeWindowKey)
    // A maximized tool exposes "Restore tool" instead, and Shift+L must toggle back.
    const maximizeButton = activeTool?.querySelector<HTMLButtonElement>('[aria-label="Maximize tool"], [aria-label="Restore tool"]')
    if (!maximizeButton) return
    event.preventDefault()
    maximizeButton.click()
    return
  }
  if (event.key.toLowerCase() === 'd' && event.shiftKey && !event.ctrlKey && !event.metaKey && !event.altKey) {
    const activeTab = workspaceStore.activeTab
    const activeWindowKey = isPopout.value
      ? String(route.params.windowKey ?? '')
      : activeTab?.active_window_key
    const activeWindow = activeTab?.windows.find(window => window.instance_key === activeWindowKey)
    if (activeWindow?.tool_type !== 'chart') return
    event.preventDefault()
    drawingsStore.setActiveTool(drawingsStore.activeToolType === 'trendline' ? null : 'trendline')
    return
  }
  if (event.key === '/' && !event.ctrlKey && !event.metaKey && !event.altKey && !event.shiftKey) {
    const activeTab = workspaceStore.activeTab
    const activeWindowKey = isPopout.value
      ? String(route.params.windowKey ?? '')
      : activeTab?.active_window_key
    const activeWindow = activeTab?.windows.find(window => window.instance_key === activeWindowKey)
    if (activeWindow?.tool_type !== 'chart' || !activeWindowKey) return
    const toolWindow = Array.from(document.querySelectorAll<HTMLElement>('.tool-window[data-window-key]'))
      .find(tool => tool.dataset.windowKey === activeWindowKey)
    const plotLibraryTrigger = toolWindow?.querySelector<HTMLButtonElement>('button[aria-label="Chart plot library"]')
    if (!plotLibraryTrigger) return
    event.preventDefault()
    plotLibraryTrigger.click()
    return
  }
  if (event.ctrlKey && !event.metaKey && !event.altKey && !event.shiftKey) {
    if (event.key.toLowerCase() === 'b') {
      const activeTab = workspaceStore.activeTab
      const activeWindowKey = isPopout.value
        ? String(route.params.windowKey ?? '')
        : activeTab?.active_window_key
      const activeWindow = activeTab?.windows.find(window => window.instance_key === activeWindowKey)
      if (activeWindow?.tool_type === 'chart' && activeWindowKey) {
        const configuredStyle = activeWindow.configuration.bar_type
        const currentStyle = configuredStyle == null
          ? 'candles'
          : STANDARD_CHART_STYLES.includes(configuredStyle as typeof STANDARD_CHART_STYLES[number])
            ? configuredStyle as typeof STANDARD_CHART_STYLES[number]
            : undefined
        const currentIndex = currentStyle ? STANDARD_CHART_STYLES.indexOf(currentStyle) : -1
        const nextStyle = STANDARD_CHART_STYLES[(currentIndex + 1) % STANDARD_CHART_STYLES.length]
        updateToolConfiguration(activeWindowKey, { ...activeWindow.configuration, bar_type: nextStyle })
        event.preventDefault()
        return
      }
    }
    const timeframe = DIRECT_CHART_TIMEFRAME_SHORTCUTS[event.key]
    if (timeframe) {
      const activeTab = workspaceStore.activeTab
      const activeWindowKey = isPopout.value
        ? String(route.params.windowKey ?? '')
        : activeTab?.active_window_key
      const activeWindow = activeTab?.windows.find(window => window.instance_key === activeWindowKey)
      if (activeWindow?.tool_type === 'chart' && activeWindowKey
        && workspaceStore.updateToolTimeframe(activeWindowKey, timeframe)) {
        event.preventDefault()
        return
      }
    }
  }
  if (!event.ctrlKey && !event.metaKey && !event.altKey && !event.shiftKey && (event.key === '=' || event.key === '-')) {
    const activeTab = workspaceStore.activeTab
    const activeWindowKey = isPopout.value
      ? String(route.params.windowKey ?? '')
      : activeTab?.active_window_key
    const activeWindow = activeTab?.windows.find(window => window.instance_key === activeWindowKey)
    const direction = event.key === '=' ? 1 : -1
    if (activeWindow?.tool_type === 'chart' && activeWindowKey && cycleChartTimeframe(activeWindowKey, direction)) {
      event.preventDefault()
      return
    }
  }
  if (/^F(?:[1-9]|1[0-2])$/.test(event.key) && !event.ctrlKey && !event.metaKey && !event.altKey && !event.shiftKey) {
    const activeTab = workspaceStore.activeTab
    const activeWindowKey = isPopout.value
      ? String(route.params.windowKey ?? '')
      : activeTab?.active_window_key
    const activeWindow = activeTab?.windows.find(window => window.instance_key === activeWindowKey)
    if (activeWindow?.tool_type === 'chart' && activeWindowKey) {
      event.preventDefault()
      window.dispatchEvent(new CustomEvent('tc2000:chart-template-key', {
        detail: { windowKey: activeWindowKey, functionKey: event.key },
      }))
      return
    }
  }
  if (event.key === 'F1' || event.key === '?') {
    event.preventDefault()
    closeShellMenus('help')
    closeSymbolSearch()
    keyboardHelpOpen.value = true
    scheduleShellMenuPosition()
    syncShellMenuListeners()
    return
  }
  if (event.key === 'Backspace' && !event.ctrlKey && !event.metaKey && !event.altKey && !event.shiftKey) {
    // Backspace is owned even at the oldest entry; never let it fall through
    // to the browser's page-navigation behavior.
    event.preventDefault()
    const previous = recentStore.previous()
    if (!previous) return
    historyNavigationTarget = previous
    void selectSymbol(previous, undefined, true, undefined, false, false, '', true).finally(() => {
      if (historyNavigationTarget === previous) historyNavigationTarget = null
    })
    return
  }
  if (!event.ctrlKey && !event.metaKey && !event.altKey && !event.shiftKey) {
    const timeframe = DIRECT_CHART_PERIOD_SHORTCUTS[event.key]
    if (timeframe) {
      const activeTab = workspaceStore.activeTab
      const activeWindowKey = isPopout.value
        ? String(route.params.windowKey ?? '')
        : activeTab?.active_window_key
      const activeWindow = activeTab?.windows.find(window => window.instance_key === activeWindowKey)
      if (activeWindow?.tool_type === 'chart' && activeWindowKey
        && workspaceStore.updateToolTimeframe(activeWindowKey, timeframe)) {
        event.preventDefault()
        return
      }
    }
  }
  if (event.key === '.' && !event.ctrlKey && !event.metaKey && !event.altKey && !event.shiftKey) {
    const activeTab = workspaceStore.activeTab
    const activeWindowKey = isPopout.value
      ? String(route.params.windowKey ?? '')
      : activeTab?.active_window_key
    if (activeTab?.windows.some(window => window.instance_key === activeWindowKey && window.tool_type === 'chart')) return
  }
  if (/^[a-z0-9.=]$/i.test(event.key) && !event.ctrlKey && !event.metaKey && !event.altKey && !event.shiftKey) {
    event.preventDefault()
    const seed = event.key.toUpperCase()
    // Write the DOM value synchronously: v-model only patches the input on
    // the next render, so a fast following keystroke would otherwise be
    // appended to the previous symbol (for example "SPY" + "p").
    if (symbolInput.value) symbolInput.value.value = seed
    symbolInput.value?.focus()
    symbolSearchEnabled.value = true
    symbolDraft.value = seed
    return
  }
  if (event.key !== ' ' || event.metaKey || event.altKey) return
  // Match TC2000 V25: plain Space advances and Ctrl+Space reverses. Shift+Space
  // is not a traversal command; editor targets have already been excluded.
  if (event.shiftKey) return
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
  const nextIndex = (currentIndex + (event.ctrlKey ? -1 : 1) + allSymbols.value.length) % allSymbols.value.length
  void selectSymbol(allSymbols.value[nextIndex], undefined, true, undefined, true, false, '', true)
}

// Escape is a workstation-wide command. Handle it during capture so nested
// listboxes, editors, and menu roots cannot stop propagation before transient
// shell surfaces are dismissed. The focused child still receives the normal
// focus recovery scheduled by closeShellMenuToTrigger where applicable.
function handleGlobalKeydownCapture(event: KeyboardEvent) {
  if (event.key !== 'Escape') return
  const hasTransientShell = applicationMenuOpen.value || recentSymbolsOpen.value || workspaceMenuOpen.value
    || toolLibraryOpen.value || keyboardHelpOpen.value
  if (!hasTransientShell) return
  event.preventDefault()
  event.stopPropagation()
  const active = document.activeElement
  const activeMenu = active instanceof Element
    ? (Object.entries(shellMenuRoots).find(([, root]) => root.value?.contains(active))?.[0] as ShellMenuRoot | undefined)
    : undefined
  const openMenu: ShellMenuRoot | undefined = activeMenu
    ?? (applicationMenuOpen.value ? 'application' : workspaceMenuOpen.value ? 'workspace' : toolLibraryOpen.value ? 'tool-library' : keyboardHelpOpen.value ? 'help' : recentSymbolsOpen.value ? 'recent' : undefined)
  closeSymbolSearch()
  recentSymbolsOpen.value = false
  applicationMenuOpen.value = false
  workspaceMenuOpen.value = false
  toolLibraryOpen.value = false
  keyboardHelpOpen.value = false
  syncShellMenuListeners()
  if (openMenu) void nextTick(() => shellMenuTriggers[openMenu].value?.focus())
}

function handleWheel(event: WheelEvent) {
  if (handledWheelEvents.has(event)) return
  handledWheelEvents.add(event)
  const controlPressed = !event.shiftKey && (event.ctrlKey || ctrlWheelHeld.value || event.getModifierState?.('Control') === true)
  if (!controlPressed || event.metaKey || event.altKey || event.deltaY === 0) return
  const target = event.target
  if (!(target instanceof Element)) return
  // Ctrl+wheel belongs to a chart only when the pointer is over its plot.
  // WatchLists keep their own row-scoped handler; every other shell surface
  // leaves the gesture untouched.
  const plot = target.closest('.uplot')
  const toolWindow = plot?.closest<HTMLElement>('.tool-window[data-window-key]')
  const windowKey = toolWindow?.dataset.windowKey
  if (!plot || !windowKey) return
  const tool = workspaceStore.activeTab?.windows.find(window => window.instance_key === windowKey)
  if (!tool || tool.tool_type !== 'chart') return
  // The V25 help defines the chart gesture but not its direction. Follow the
  // selector's ascending interval order: wheel down moves to a longer interval.
  const direction = event.deltaY > 0 ? 1 : -1
  if (!cycleChartTimeframe(windowKey, direction)) return
  // Window capture runs before uPlot and its subpane handlers; consume the
  // modifier gesture here so the same wheel event cannot also pinch-zoom or
  // redispatch through another chart layer.
  event.preventDefault()
  event.stopPropagation()
}

function cycleChartTimeframe(windowKey: string, direction: 1 | -1) {
  const currentTimeframe = workspaceStore.timeframeForTool(windowKey)
  const currentIndex = CHART_TIMEFRAME_ORDER.indexOf(currentTimeframe as Timeframe)
  if (currentIndex < 0) return false
  // The V25 help lists `=` / `-` but does not specify direction. Follow the
  // selector's ascending interval order: `=` moves longer, `-` moves shorter.
  const nextIndex = (currentIndex + direction + CHART_TIMEFRAME_ORDER.length) % CHART_TIMEFRAME_ORDER.length
  const nextTimeframe = CHART_TIMEFRAME_ORDER[nextIndex]
  return nextTimeframe ? workspaceStore.updateToolTimeframe(windowKey, nextTimeframe) : false
}

watch(activeSymbol, symbol => {
  if (!symbol) return
  const pendingSelection = pendingInitialWorkspaceSymbolIntent
  if (initialWorkspaceHydrationPending && pendingSelection
    && pendingSelection.generation === symbolSelectionGeneration
    && symbol !== pendingSelection.symbol) {
    if (symbol === restoredWorkspaceBlueSymbol()) {
      // The initial workspace response can arrive after the user has already
      // selected a verified instrument. Do not let that stale persisted blue
      // symbol replace the newer chart, route, or search-field context.
      return
    }
    // A different linked selection arrived after the persisted restore; treat
    // that newer publication as current rather than replaying the shell choice.
    pendingInitialWorkspaceSymbolIntent = null
  }
  cancelLinkedTimeframePreparation()
  const privateBasketSelection = isPrivateBasketToken(symbol)
  const activeRouteContext = activeHoldingContext.value?.symbol === symbol
    ? activeHoldingContext.value.context
    : null
  const preservingInitialHoldingRoute = holdingRouteHydrationPending.value
    && initialHoldingRouteContext?.canonicalSymbol === routeSymbol
  if (!preservingInitialHoldingRoute) {
    syncChartRouteToSelection(symbol, activeRouteContext?.instrumentId, activeRouteContext)
  }
  const isHistoryNavigation = historyNavigationTarget === symbol
  if (!privateBasketSelection) recentStore.add(symbol, undefined, !isHistoryNavigation)
  if (isHistoryNavigation) historyNavigationTarget = null
  // Linked row selections can arrive through the workspace bus before the shell's
  // async symbol handler resumes. Keep the auto-ratio tool tied to the newest
  // published symbol at this boundary as well as in the explicit selection path.
  if (!privateBasketSelection) updateAutoRatioExpression(symbol)
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
    ...(preserveDrilldown || privateBasketSelection ? [] : [workspaceStore.loadETFHoldings(symbol, 'high'), workspaceStore.loadETFIndustries(symbol, 'high')]),
    ...(!privateBasketSelection ? [workspaceStore.loadTechnical(symbol)] : []),
  ])
})
watch(symbolDraft, value => {
  if (suppressSymbolDraftWatch === value) {
    suppressSymbolDraftWatch = null
    return
  }
  scheduleSymbolSearch(value)
})
watch(() => workspaceStore.linkedTimeframe, timeframe => {
  cancelLinkedTimeframePreparation()
  selectedAcquisitionAbortController?.abort()
  selectedAcquisitionAbortController = null
  const symbol = activeSymbol.value.trim().toUpperCase()
  void chartStore.loadBars(symbol, timeframe as typeof chartStore.timeframe, chartStore.barType, true)
  if (symbol && !isPrivateBasketToken(symbol)) {
    void prepareLinkedTimeframeHistory(symbol, timeframe as Timeframe)
  }
})
watch(() => chartStore.timeframe, () => {
  selectedAcquisitionAbortController?.abort()
  selectedAcquisitionAbortController = null
}, { flush: 'sync' })
watch(() => workspaceStore.workspace?.id, (workspaceId, previousWorkspaceId) => {
  if (workspaceId && previousWorkspaceId && workspaceId !== previousWorkspaceId) {
    void replaceDockAfterWorkspaceChange()
  }
})

onMounted(async () => {
  void workspaceStore.loadToolCatalogue()
  componentMounted = true
  if (isPopout.value) {
    // Establish keyboard and assistive-technology focus before workspace
    // hydration or market-data requests can delay the pop-out's first focus.
    popoutRoot.value?.focus({ preventScroll: true })
  }
  const resolveMount = resolveComponentMountSettled
  resolveComponentMountSettled = null
  resolveMount?.()
  const mountSelectionGeneration = symbolSelectionGeneration
  // Capture before chart/uPlot gesture handlers can stop propagation. A chart
  // owns Ctrl+wheel for timeframe navigation; non-chart targets pass through
  // so WatchLists can traverse their own rows.
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
  initialWorkspaceHydrationPending = true
  workspaceLoadPromise = workspaceStore.loadDefault()
  try {
    await workspaceLoadPromise
  } finally {
    const resolveReady = resolveWorkspaceReady
    resolveWorkspaceReady = null
    if (componentMounted) {
      workspaceReady.value = true
      resolveReady?.()
    }
  }
  // Let reactive watchers consume the workspace response while the intent
  // guard is still active, then restore the latest committed selection once.
  await nextTick()
  initialWorkspaceHydrationPending = false
  if (!componentMounted) return
  // The initial snapshot restores persisted linked timeframes. Replay any
  // newer shell choices made while it loaded so hydration cannot discard
  // what the user just selected.
  for (const [group, timeframe] of pendingTimeframeSelections) {
    workspaceStore.publishTimeframe(timeframe, group, 'workstation')
  }
  pendingTimeframeSelections.clear()
  if (symbolSelectionGeneration !== mountSelectionGeneration) {
    // A newer explicit selection already synchronized the route while the
    // workspace loaded, so initial-route protection is no longer needed.
    holdingRouteHydrationPending.value = false
  }
  const pendingSelection = pendingInitialWorkspaceSymbolIntent
  if (pendingSelection && pendingSelection.generation === symbolSelectionGeneration) {
    pendingInitialWorkspaceSymbolIntent = null
    symbolDraft.value = pendingSelection.symbol
    if (activeSymbol.value !== pendingSelection.symbol) {
      workspaceStore.publishSymbol({
        symbol: pendingSelection.symbol,
        ...(typeof pendingSelection.instrumentId === 'number' ? { instrumentId: pendingSelection.instrumentId } : {}),
        ...(pendingSelection.timestamp ? { timestamp: pendingSelection.timestamp } : {}),
        group: 'blue',
        sourceWindowKey: 'workstation',
      })
    }
    syncChartRouteToSelection(
      pendingSelection.symbol,
      pendingSelection.instrumentId,
      pendingSelection.holdingContext,
      pendingSelection.selectedHolding,
    )
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
  // A browser pop-out can start while the source window is still persisting a
  // revisioned workspace snapshot. Keep retrying the canonical read for a short,
  // bounded recovery window so transient stale reads do not strand a valid tool
  // in the source workspace.
  if (isPopout.value && !popoutTool.value) {
    // A source window may still be settling a revisioned snapshot when the
    // browser popup starts. Retry for up to roughly five seconds so a transient
    // stale read does not leave an empty pop-out during normal persistence load.
    for (let attempt = 0; attempt < 20 && !popoutTool.value; attempt += 1) {
      if (!componentMounted) return
      await new Promise(resolve => window.setTimeout(resolve, 250))
      if (!componentMounted) return
      await workspaceStore.loadDefault()
      if (requestedTab && workspaceStore.workspace?.tabs.some(tab => tab.stable_key === requestedTab)) {
        workspaceStore.activeTabKey = requestedTab
      }
    }
  }
  // Start shared panel refresh concurrently. It must not gate the selected
  // chart's local-first hydration on first use or a route restore.
  let initialMarketRefresh: Promise<void> | null = null
  if (isPopout.value) await refreshMarketData()
  else initialMarketRefresh = refreshMarketData()
  if (!componentMounted) return
  if (isPopout.value && popoutTool.value) {
    const tool = popoutTool.value
    const configuredSymbol = typeof tool.configuration.symbol === 'string' ? tool.configuration.symbol : null
    const linked = workspaceStore.symbolForLinkGroup(tool.link_group, configuredSymbol)
    await loadSymbolData(linked, workspaceStore.constituentETF, false)
    if (!componentMounted) return
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
      // A plain /chart restore preserves a parent fund only when one is
      // actually bound. On a fresh workstation there is no parent context yet;
      // let the normal local holdings/industry reads hydrate the active ETF.
      // The shared chart store renders its local cache first; visible canonical
      // chart hydration below also starts the shared preparation lifecycle.
      const preserveParentETFContext = explicitRouteSymbol == null && workspaceStore.constituentETF != null
      const routeHoldingContext = explicitRouteSymbol == null || isPrivateBasketToken(requested)
        ? null
        : parseETFHoldingDrilldownRouteQuery(route.query as Record<string, unknown>, requested)
      const holdingHandoff = consumeHoldingSelectionHandoff(routeHoldingContext)
      const selectedHoldingRoute = route.query.holding_history_intent === 'selected'
        && routeHoldingContext !== null && holdingHandoff.selected
      // The route consumer is now taking over. From this point on, ordinary
      // linked selections must synchronize their own URL and clear unrelated
      // holding provenance through the normal identity-checked selection path.
      holdingRouteHydrationPending.value = false
      if (selectedHoldingRoute && routeHoldingContext) {
        // The one-use same-tab handoff is written only after the holdings view
        // validates the exact current row/identity. A bare replayed query keeps
        // no acquisition intent and cannot turn dated provenance into current
        // membership.
        if (routeHoldingContext.etfSymbol) workspaceStore.setConstituentETF(routeHoldingContext.etfSymbol)
        await selectSymbol(
          requested,
          undefined,
          true,
          routeHoldingContext.instrumentId,
          true,
          true,
          holdingHandoff.confirmedIdentity?.instrument?.instrument_type ?? routeHoldingContext.holdingType,
          true,
          holdingHandoff.confirmedIdentity,
          routeHoldingContext,
        )
      } else {
        // A visible canonical chart is a first-use intent: hydrate local bars
        // immediately, then let the shared coordinator prepare admitted history
        // in the background. Private baskets use their own authenticated member
        // preparation path and are not ticker identities.
        await selectSymbol(
          requested,
          undefined,
          true,
          undefined,
          true,
          preserveParentETFContext,
          '',
          !isPrivateBasketToken(requested),
          undefined,
          undefined,
          routeHoldingContext ?? undefined,
        )
      }
      if (!componentMounted) return
    }
  }
  await nextTick()
  if (!componentMounted) return
  // Finish the startup refresh that already began above. Starting another
  // refetch here duplicated all shared group/snapshot reads after the chart
  // had hydrated, and repeated mounts could keep the list surfaces busy.
  if (initialMarketRefresh) await initialMarketRefresh
  if (!componentMounted) return
})

onBeforeUnmount(() => {
  componentMounted = false
  initialWorkspaceHydrationPending = false
  pendingInitialWorkspaceSymbolIntent = null
  const resolveMount = resolveComponentMountSettled
  resolveComponentMountSettled = null
  resolveMount?.()
  symbolSelectionGeneration += 1
  cancelLinkedTimeframePreparation()
  selectedAcquisitionAbortController?.abort()
  selectedAcquisitionAbortController = null
  drilldownSelectionGeneration += 1
  searchRequest += 1
  finishPendingSymbolSearch()
  resolveWorkspaceReady?.()
  resolveWorkspaceReady = null
  endTabDrag()
  window.removeEventListener('wheel', handleWheel, { capture: true })
  ctrlWheelHeld.value = false
  for (const poll of popoutGeometryPollers.values()) window.clearInterval(poll)
  popoutGeometryPollers.clear()
  removeVisibilityListener?.()
  removeVisibilityListener = null
  if (searchTimer) clearTimeout(searchTimer)
  if (discoveryTimer) clearTimeout(discoveryTimer)
  discoveryRetryAbortController?.abort()
  candidateResolutionAbortController?.abort()
  workspaceStore.disconnect()
  removeShellMenuListeners()
})
</script>

<style scoped>
.workstation { width: 100%; height: 100%; min-width: 980px; display: grid; grid-template-rows: var(--tc-toolbar-height) var(--tc-tab-height) minmax(0, 1fr) var(--tc-status-height); overflow: hidden; color: var(--tc-text); background: var(--tc-shell-bg); font-family: var(--tc-font-family); }
.workstation:has(.workstation__popout) { min-width: 320px; grid-template-rows: minmax(0, 1fr); }
.workstation__popout { min-width: 0; min-height: 0; padding: 2px; background: #090c0f; }
.workstation__menu { display: flex; align-items: center; gap: 12px; padding: 0 7px; background: linear-gradient(var(--tc-header-top), var(--tc-header-bottom)); border-bottom: 1px solid #090b0d; }
.workstation__application-navigation { position: relative; display: flex; align-items: center; flex: 0 0 auto; }
.workstation__brand { appearance: none; display: block; padding: 0; border: 0; background: transparent; color: var(--tc-accent-soft); font-family: inherit; font-size: 10px; font-weight: 700; letter-spacing: .06em; line-height: normal; text-align: left; white-space: nowrap; cursor: pointer; }
.workstation__brand:hover { color: var(--tc-text); text-decoration: underline; text-decoration-color: var(--tc-accent); text-underline-offset: 3px; }
.workstation__brand:focus-visible { outline: 2px solid var(--tc-accent); outline-offset: 3px; }
.workstation__application-menu { position: fixed; z-index: 151; display: grid; min-width: 0; padding: 3px; border: 1px solid var(--tc-border-strong); border-radius: var(--tc-radius); background: var(--tc-panel-bg); box-shadow: 0 7px 18px #000b; color: var(--tc-text); overflow: auto; overscroll-behavior: contain; }
.workstation__application-menu a { display: flex; align-items: center; gap: 8px; min-width: 0; min-height: 28px; padding: 4px 7px; border: 1px solid transparent; border-radius: calc(var(--tc-radius) - 2px); color: var(--tc-text-muted); font-size: 11px; line-height: 1.25; text-decoration: none; white-space: nowrap; }
.workstation__application-menu a:hover,
.workstation__application-menu a:focus-visible { border-color: var(--tc-border); background: var(--tc-control-bg); color: var(--tc-text); outline: none; }
.workstation__application-menu a[aria-current="page"] { border-color: color-mix(in srgb, var(--tc-accent) 28%, transparent); background: color-mix(in srgb, var(--tc-accent) 12%, transparent); color: var(--tc-accent-soft); }
.workstation__menu nav { display: flex; align-self: stretch; }
.workstation__workspace-menu { position: relative; display: flex; align-items: stretch; }
.workstation__workspace-popover { position: fixed; z-index: 150; padding: 5px; border: 1px solid #4d5a63; background: #151d23; box-shadow: 0 7px 18px #000b; color: #cbd6dc; overflow: auto; }
.workstation__help-menu { position: relative; display: flex; align-items: stretch; }
.workstation__help-popover { position: fixed; z-index: 150; padding: 5px; border: 1px solid #4d5a63; background: #151d23; box-shadow: 0 7px 18px #000b; color: #cbd6dc; overflow: auto; }
.workstation__help-popover header { display: flex; justify-content: space-between; align-items: center; padding: 3px 4px 5px; border-bottom: 1px solid #29343b; font-size: 11px; }
.workstation__help-popover header button { border: 0; color: #aebbc4; background: transparent; cursor: pointer; font: 13px/1 "Segoe UI",Arial,sans-serif; padding: 0 2px; }
.workstation__help-popover dl { display: grid; gap: 3px; margin: 5px 0; }
.workstation__help-popover dl div { display: grid; grid-template-columns: 112px minmax(0,1fr); gap: 7px; padding: 2px 3px; }
.workstation__help-popover dt { color: #e4f1f7; font-weight: 700; }
.workstation__help-popover dd { margin: 0; color: #aebbc4; }
.workstation__help-popover > small { display: block; padding: 4px 3px 2px; border-top: 1px solid #29343b; color: #81909a; line-height: 1.35; }
.workstation__workspace-popover header { display: flex; justify-content: space-between; align-items: baseline; padding: 3px 4px 5px; border-bottom: 1px solid #29343b; font-size: 11px; }.workstation__workspace-popover header small { color: #81909a; font-size: 9px; }
.workstation__workspace-list { display: grid; gap: 2px; max-height: 112px; overflow: auto; padding: 4px 0; border-bottom: 1px solid #29343b; }.workstation__workspace-list button { display: flex; justify-content: space-between; gap: 8px; border: 1px solid transparent; background: transparent; color: #aebbc4; padding: 3px 4px; text-align: left; font: 10px "Segoe UI",Arial,sans-serif; cursor: pointer; }.workstation__workspace-list button:hover,.workstation__workspace-list button[aria-selected="true"] { border-color: #3e505c; background: #202b32; color: #f1f7fa; }.workstation__workspace-list small { color: #81909a; font-size: 9px; }
.workstation__workspace-actions { display: grid; grid-template-columns: repeat(3,minmax(0,1fr)); gap: 4px; padding: 5px 2px; border-bottom: 1px solid #29343b; }.workstation__workspace-actions button,.workstation__layout-reset { min-width: 0; min-height: 28px; border: 1px solid #42505a; background: #202b32; color: #cbd6dc; padding: 4px 5px; font: 10px/1.2 "Segoe UI",Arial,sans-serif; cursor: pointer; white-space: normal; }.workstation__workspace-actions button:hover,.workstation__layout-reset:hover { background: #31424d; color: #fff; }.workstation__workspace-actions button:disabled { color: #68767e; border-color: #354149; background: #182026; cursor: not-allowed; }.workstation__workspace-file { display: none; }
.workstation__layout-recovery { display: flex; align-items: center; justify-content: space-between; gap: 8px; padding: 6px 5px; border: 1px solid var(--tc-accent); border-radius: var(--tc-radius); color: var(--tc-text); font-size: 10px; }
.workstation__layout-recovery button { flex: none; border: 1px solid var(--tc-border-strong); border-radius: var(--tc-radius); background: var(--tc-control-bg); color: var(--tc-text); padding: 3px 8px; cursor: pointer; }
.workstation__workspace-delete-help { display: block; padding: 4px 4px 2px; border-bottom: 1px solid #29343b; color: #91a0a9; font-size: 9px; line-height: 1.35; }
.workstation__layout-list { display: grid; gap: 2px; max-height: 250px; overflow: auto; padding: 4px 0; }.workstation__layout-item { display: grid; grid-template-columns: minmax(72px, 1fr) 98px 58px; gap: 3px; align-items: center; padding: 2px; border: 1px solid transparent; }.workstation__layout-item:hover { border-color: #3e505c; }.workstation__layout-select { overflow: hidden; border: 0; background: transparent; color: #aebbc4; text-align: left; text-overflow: ellipsis; white-space: nowrap; cursor: pointer; font: 10px "Segoe UI",Arial,sans-serif; }.workstation__layout-select.active { color: #eaf2f6; font-weight: 700; }.workstation__layout-item input { min-width: 0; border: 1px solid #3b4850; background: #11161a; color: #bfcbd3; padding: 2px 3px; font: 10px "Segoe UI",Arial,sans-serif; }.workstation__layout-delete { display: flex; align-items: center; justify-content: center; gap: 2px; min-height: 22px; padding: 2px 3px; border: 1px solid #4d4242; border-radius: var(--tc-radius); background: #2a2020; color: #e4a4a4; font: 9px/1.1 "Segoe UI",Arial,sans-serif; cursor: pointer; white-space: nowrap; }.workstation__layout-delete:hover:not(:disabled) { border-color: #d78989; background: #3b2626; color: #fff; }.workstation__layout-delete:disabled { color: #68767e; border-color: #354149; background: #182026; cursor: not-allowed; }.workstation__layout-reset { width: 100%; margin-top: 2px; }
.workstation__menu nav button, .workstation__tab-add, .workstation__tab-reset { border: 0; background: transparent; color: #d4d9dd; padding: 0 8px; font: 11px "Segoe UI", Arial, sans-serif; cursor: pointer; }
.workstation__menu nav .workstation__workspace-actions button { border: 1px solid #42505a; border-radius: var(--tc-radius); background: #202b32; color: #cbd6dc; padding: 4px 5px; font: 10px/1.2 "Segoe UI",Arial,sans-serif; white-space: normal; }
.workstation__menu nav .workstation__workspace-actions button:hover:not(:disabled) { background: #31424d; color: #fff; }
.workstation__menu nav .workstation__workspace-actions button:disabled { color: #68767e; border-color: #354149; background: #182026; cursor: not-allowed; }
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
.workstation__canonical-symbol-options { display: grid; }
.workstation__symbol-results button { display: grid; grid-template-columns: 55px minmax(0, 1fr) 48px; gap: 6px; align-items: center; min-height: 25px; padding: 3px 6px; border: 0; border-bottom: 1px solid #29343b; background: transparent; color: #bfcbd3; font: 10px "Segoe UI", Arial, sans-serif; text-align: left; }
.workstation__symbol-results button:hover, .workstation__symbol-results button:focus-visible, .workstation__symbol-results button[aria-selected="true"] { background: #2c4554; color: #fff; outline-color: #80bce8; }
.workstation__symbol-results strong { color: #e4f1f7; }.workstation__symbol-results span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }.workstation__symbol-results small { color: #8799a5; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.workstation__source-actions { display: grid; gap: 2px; padding: 4px; border-top: 1px solid #29343b; }
.workstation__source-actions .workstation__source-option { display: block; min-height: 28px; padding: 5px 6px; border: 1px solid #42505a; background: #202b32; color: #dce9f2; font: 10px "Segoe UI", Arial, sans-serif; text-align: left; white-space: normal; cursor: pointer; }
.workstation__source-actions .workstation__source-option:hover:not(:disabled), .workstation__source-actions .workstation__source-option:focus-visible { background: #31424d; color: #fff; outline: 2px solid #80bce8; outline-offset: -2px; }
.workstation__source-actions .workstation__source-option:disabled { color: #87939a; background: #1b2329; cursor: wait; }
.workstation__symbol-search-message { min-width: 270px; padding: 7px 8px; border-top: 1px solid #29343b; color: #93a5af; font: 10px "Segoe UI", Arial, sans-serif; }
.workstation__symbol-search-message--error { color: #e4a0a0; }
.workstation__symbol-search-state { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); clip-path: inset(50%); white-space: nowrap; }
.workstation__status { margin-left: auto; display: flex; align-items: center; gap: 6px; min-width: 0; max-width: 62%; overflow: visible; color: #81909a; font-size: 10px; }
.workstation__selection-acquisition { flex: 0 1 clamp(92px, 11vw, 150px); }
.workstation__selection-acquisition--error { color: var(--tc-danger, #ed9696); }
.workstation__refresh,.workstation__sign-out { border: 1px solid #47545d; background: #20282e; color: #bdc9d1; padding: 2px 6px; font: inherit; cursor: pointer; }
.workstation__refresh:disabled { cursor: wait; opacity: .65; }
.workstation__refresh:hover:not(:disabled),
.workstation__sign-out:hover { border-color: #6d8290; color: #fff; background: #33414a; }
.workstation__leader { color: #63bd85; }
.workstation__data-state--fetching { color:#80bce8; }.workstation__data-state--unavailable { color:#ed9696; }.workstation__data-state--current { color:#91d5a7; }.workstation__data-state--delayed,.workstation__data-state--stale { color:#e8c06b; }.workstation__data-state--partial,.workstation__data-state--coverage-limited { color:#e8b879; }
@media (max-width: 1100px) {
  .workstation { min-width: 0; grid-template-rows: auto var(--tc-tab-height) minmax(0, 1fr) var(--tc-status-height); }
  .workstation:has(.workstation__popout) { min-width: 320px; grid-template-rows: minmax(0, 1fr); }
  .workstation__menu {
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto minmax(0, 2fr);
    grid-template-areas: "application navigation navigation" "search timeframe status";
    align-content: center;
    align-items: center;
    gap: 4px 8px;
    min-width: 0;
    padding: 5px;
  }
  .workstation__application-navigation { grid-area: application; }
  .workstation__menu > nav { grid-area: navigation; min-width: 0; overflow-x: auto; overflow-y: hidden; }
  .workstation__menu nav button { flex: 0 0 auto; }
  .workstation__search { grid-area: search; width: max-content; max-width: 100%; }
  .workstation__timeframe { grid-area: timeframe; }
  .workstation__status { grid-area: status; width: 100%; max-width: none; min-width: 0; flex-wrap: wrap; }
  .workstation__menu nav button { padding-inline: 5px; font-size: 10px; }
  .workstation__search { margin-left: 0; }
  .workstation__search input { width: 72px; }
  .workstation__timeframe { flex: 0 0 auto; }
  .workstation__status { flex: 0 1 auto; max-width: 46%; gap: 4px; }
  .workstation__selection-acquisition { flex-basis: 78px; min-width: 0; }
  .workstation__selection-acquisition[data-testid="active-holding-lineage"] { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .workstation__data-state { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .workstation__refresh, .workstation__sign-out { flex: 0 0 auto; padding-inline: 4px; white-space: nowrap; }
}
.workstation__tabs { display: flex; align-items: stretch; background: var(--tc-panel-bg); border-bottom: 1px solid var(--tc-border); }
.workstation__tabs { min-width: 0; overflow-x: auto; overflow-y: hidden; scrollbar-width: thin; }
.workstation__tool-library { position: relative; display: flex; }
.workstation__tool-library-menu { position: fixed; z-index: 60; display: grid; min-width: 118px; padding: 2px; border: 1px solid #42505a; background: #1b2228; box-shadow: 0 3px 10px #000a; overflow: auto; }
.workstation__tool-library-menu button { border: 0; background: transparent; color: #cbd6dc; padding: 5px 8px; font: 11px "Segoe UI", Arial, sans-serif; text-align: left; cursor: pointer; }
.workstation__tool-library-menu button:hover { background: #31424d; color: #fff; }
.workstation__tabs > button:not(.workstation__tab-add) { flex: 0 0 auto; min-width: 112px; padding: 0 11px; border: 0; border-right: 1px solid #303940; background: #1b2126; color: #9facb5; font: 11px "Segoe UI", Arial, sans-serif; cursor: grab; }
.workstation__tabs > button:not(.workstation__tab-add):active { cursor: grabbing; }
.workstation__tabs > button.workstation__tab--active { background: #28333b; color: #eaf2f6; box-shadow: inset 0 2px #68b6e9; }
.workstation__tabs > button.workstation__tab--drag-over { box-shadow: inset 2px 0 #f0c66d, inset -2px 0 #f0c66d; }
.workstation__tabs > button[role="tab"]:focus-visible { position: relative; z-index: 1; outline: 2px solid #eef3fb; outline-offset: -3px; }
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
.workstation__snapshot-save-state { white-space: nowrap; }
.workstation__snapshot-save-state[data-state="saving"] { color: var(--tc-accent); }
.workstation__snapshot-save-state[data-state="error"] { color: var(--tc-negative); }
.workstation__snapshot-save-retry { border: 1px solid var(--tc-border); border-radius: 3px; padding: 1px 5px; background: var(--tc-control-bg); color: var(--tc-text); font: inherit; cursor: pointer; }
.workstation__snapshot-save-retry:focus-visible { outline: 2px solid var(--tc-accent); outline-offset: 2px; }
.sr-only { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; border: 0; }
</style>
