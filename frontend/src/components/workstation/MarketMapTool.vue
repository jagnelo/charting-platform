<template>
  <section class="market-map-tool" aria-label="Universe market map" :aria-busy="loading ? 'true' : 'false'">
    <div class="market-map-tool__controls">
      <label>Universe
        <select v-model="sourceId" aria-label="Market Map universe" :disabled="loadingSources" @change="explicitSymbols = ''">
          <option value="">Select a universe</option>
          <option v-if="sourceId.startsWith('explicit:')" :value="sourceId">Explicit symbols · Locked</option>
          <optgroup v-for="group in sourceGroups" :key="group.key" :label="group.label">
            <option v-for="source in group.sources" :key="source.source_id" :value="source.source_id" :disabled="!isSourceSelectable(source)">
              {{ source.pinned ? '★ ' : '' }}{{ source.name }}{{ source.locked ? ' · Locked' : '' }}{{ sourceAvailabilitySuffix(source) }}
            </option>
          </optgroup>
        </select>
      </label>
      <div class="market-map-tool__source-bootstrap" aria-label="Add ETF constituent universe">
        <label>ETF universe
          <input v-model.trim="etfBootstrapSymbol" aria-label="ETF universe symbol" placeholder="e.g. QQQ" maxlength="20" @keydown.enter.prevent="bootstrapEtfSource" />
        </label>
        <button type="button" :disabled="etfBootstrapBusy || !etfBootstrapSymbol.trim()" aria-label="Load ETF constituent universe" @click="bootstrapEtfSource">{{ etfBootstrapBusy ? 'Loading…' : 'Load ETF' }}</button>
        <span v-if="etfBootstrapMessage" role="status">{{ etfBootstrapMessage }}</span>
        <span v-if="etfBootstrapError" class="market-map-tool__status--error" role="alert">{{ etfBootstrapError }}</span>
      </div>
      <label>Explicit symbols
        <input v-model.trim="explicitSymbols" aria-label="Market Map explicit symbols" placeholder="SPY, NVDA, MSFT" @keydown.enter.prevent="run" />
      </label>
      <small v-if="explicitSymbols.trim()" class="market-map-tool__explicit-hint">Canonical selection · save it as a personal watchlist for durable membership</small>
      <template v-if="explicitSymbols.trim()">
        <input v-model.trim="explicitWatchlistName" aria-label="Explicit source watchlist name" placeholder="Save watchlist as…" maxlength="80" />
        <button type="button" :disabled="explicitSaving || !explicitWatchlistName" @click="saveExplicitSource">{{ explicitSaving ? 'Saving…' : 'Save as watchlist' }}</button>
        <button type="button" :disabled="explicitSaving || !explicitWatchlistName" aria-label="Save explicit symbols as locked source" @click="saveExplicitLockedSource">{{ explicitSaving ? 'Saving…' : 'Save as locked source' }}</button>
        <span v-if="publicationMessage" role="status">{{ publicationMessage }}</span>
        <span v-if="publicationError" class="market-map-tool__status--error" role="alert">{{ publicationError }}</span>
      </template>
      <div v-if="activeSource" class="market-map-tool__source-actions" aria-label="Market Map source preferences">
        <span class="market-map-tool__source-kind">{{ sourceKindLabel(activeSource.source_kind) }} · {{ activeSource.member_count ?? '—' }} members</span>
        <span v-if="sourceAvailability(activeSource) === 'pending'" class="market-map-tool__source-state" role="status">Membership pending; this locked source remains followable</span>
        <span
          v-if="sourceIsNotCurrent(activeSource)"
          class="market-map-tool__source-state market-map-tool__source-state--warning"
          role="status"
        >
          Current holdings unavailable{{ activeSource.provenance?.failure_class ? ` · ${formatFailureClass(activeSource.provenance.failure_class)}` : '' }}{{ activeSource.provenance?.capability_reason ? `: ${activeSource.provenance.capability_reason}` : '' }}
        </span>
        <button v-if="activeSource.can_follow" type="button" :aria-pressed="sourceFollowed" :aria-label="sourceFollowed ? `Unfollow ${activeSource.name}` : `Follow ${activeSource.name}`" @click="toggleSourceFollow">{{ sourceFollowed ? 'Following' : 'Follow' }}</button>
        <button v-if="activeSource.can_clone" type="button" :aria-pressed="sourcePinned" :aria-label="sourcePinned ? `Unpin ${activeSource.name}` : `Pin ${activeSource.name}`" @click="toggleSourcePin">{{ sourcePinned ? 'Pinned' : 'Pin' }}</button>
        <button v-if="map && activeSource.can_clone" type="button" :disabled="sourceCloneBusy" :aria-label="`Clone ${activeSource.name} snapshot`" @click="cloneActiveSource">{{ sourceCloneBusy ? 'Cloning…' : 'Clone snapshot' }}</button>
        <button v-if="sourceCloneRetryIds.length" type="button" :disabled="sourceCloneBusy" aria-label="Retry failed source clone members" @click="retrySourceClone">{{ sourceCloneBusy ? 'Retrying…' : `Retry ${sourceCloneRetryIds.length} failed` }}</button>
        <span v-if="sourceCloneMessage" role="status">{{ sourceCloneMessage }}</span>
        <span v-if="sourceCloneError" class="market-map-tool__status--error" role="alert">{{ sourceCloneError }}</span>
      </div>
      <label>Group
        <select v-model="groupBy" aria-label="Market Map grouping">
          <option value="sector_industry">Sector → Industry</option>
          <option value="sector">Sector</option>
          <option value="industry">Industry</option>
          <option value="none">Ungrouped</option>
        </select>
      </label>
      <label>Sort
        <select v-model="sortBy" aria-label="Market Map sort order">
          <option value="area_desc">Largest area</option>
          <option value="color_desc">Strongest colour</option>
          <option value="symbol_asc">Symbol A–Z</option>
        </select>
      </label>
      <label>Period
        <select v-model="period" aria-label="Market Map period">
          <option v-for="value in periods" :key="value" :value="value">{{ value }}</option>
        </select>
      </label>
      <label>Timeframe
        <select v-model="timeframe" aria-label="Market Map timeframe">
          <option value="D1">Daily</option><option value="W1">Weekly</option><option value="MN">Monthly</option>
        </select>
      </label>
      <label v-if="period === 'CUSTOM'">Start
        <input v-model="startDate" aria-label="Market Map custom start date" type="date" />
      </label>
      <label v-if="period === 'CUSTOM'">End
        <input v-model="endDate" aria-label="Market Map custom end date" type="date" />
      </label>
      <label>Area
        <select v-model="areaMetric" aria-label="Market Map area metric">
          <option value="market_cap">Market cap</option><option value="weight">Source weight</option><option value="equal">Equal</option><option value="volume">Volume</option><option value="field">Provider numeric field</option><option value="python">Python numeric output</option>
        </select>
      </label>
      <label v-if="areaMetric === 'field'">Field
        <select v-model="areaField" aria-label="Market Map provider numeric area field">
          <option value="avg_volume_30d">Average volume (30D)</option>
          <option value="pe_ratio">P/E ratio</option>
          <option value="beta">Beta</option>
          <option value="dividend_yield">Dividend yield</option>
          <option value="week52_high">52-week high</option>
          <option value="week52_low">52-week low</option>
        </select>
      </label>
      <label>Colour
        <select v-model="colorMetric" aria-label="Market Map colour metric">
          <option value="return">Return</option><option value="relative_return">Relative return</option><option value="breadth">Breadth condition</option><option value="python">Python output</option><option value="rsi_14">RSI(14)</option><option value="relative_volume">Relative volume</option><option value="distance_52w_high">Distance to 52W high</option><option value="distance_52w_low">Distance to 52W low</option>
        </select>
      </label>
      <label v-if="colorMetric === 'relative_return' || referenceNeeded">Reference universe
        <select v-model="referenceSourceId" aria-label="Market Map reference universe">
          <option value="">Single symbol…</option>
          <option v-for="source in sources" :key="`reference-${source.source_id}`" :value="source.source_id">{{ source.name }}{{ source.locked ? ' · Managed' : '' }}</option>
        </select>
      </label>
      <label v-if="(colorMetric === 'relative_return' || referenceNeeded) && !referenceSourceId">Reference
        <input v-model="referenceSymbol" aria-label="Market Map relative-return reference" placeholder="SPY" maxlength="20" />
      </label>
      <label v-if="colorMetric === 'breadth' && !advancedBreadthEditor">Condition
        <select v-model="breadthConditionKind" aria-label="Market Map breadth condition">
          <option value="above_moving_average">Above moving average</option>
          <option value="within_52_week_high">Within 52-week high</option>
          <option value="new_high_low">New high/low</option>
          <option value="rsi">RSI threshold</option>
          <option value="volume_ratio">Volume ratio</option>
          <option value="event">Event occurrence</option>
          <option value="relative_strength">Relative strength</option>
        </select>
      </label>
      <label v-if="colorMetric === 'breadth'" class="market-map-tool__advanced-toggle"><input v-model="advancedBreadthEditor" type="checkbox" aria-label="Use advanced Market Map breadth condition editor" /> Advanced condition editor</label>
      <BreadthConditionTreeEditor v-if="colorMetric === 'breadth' && advancedBreadthEditor" v-model="breadthConditionTree" />
      <label v-if="colorMetric === 'breadth' && !advancedBreadthEditor && breadthConditionKind === 'above_moving_average'">Period
        <input v-model.number="breadthConditionPeriod" aria-label="Market Map breadth moving average period" type="number" min="2" max="252" />
      </label>
      <label v-if="colorMetric === 'breadth' && !advancedBreadthEditor && breadthConditionKind === 'within_52_week_high'">Within %
        <input v-model.number="breadthConditionThreshold" aria-label="Market Map breadth extreme threshold" type="number" min="0" max="1" step="0.001" />
      </label>
      <label v-if="colorMetric === 'breadth' && !advancedBreadthEditor && (breadthConditionKind === 'rsi' || breadthConditionKind === 'volume_ratio')">Threshold
        <input v-model.number="breadthConditionThreshold" aria-label="Market Map breadth threshold" type="number" step="0.01" />
      </label>
      <label v-if="colorMetric === 'breadth' && !advancedBreadthEditor && breadthConditionKind === 'event'">Event
        <select v-model="breadthEventType" aria-label="Market Map breadth event type">
          <option value="any">Any event</option><option value="earnings">Earnings</option><option value="dividend">Dividend</option><option value="ex_dividend">Ex-dividend</option><option value="split">Split</option>
        </select>
      </label>
      <label v-if="colorMetric === 'breadth' && !advancedBreadthEditor && breadthConditionKind === 'event'">Lookback days
        <input v-model.number="breadthEventLookback" aria-label="Market Map breadth event lookback" type="number" min="0" max="3660" />
      </label>
      <label v-if="colorMetric === 'python' || areaMetric === 'python'">Python output
        <select v-model="pythonCodeVersionId" aria-label="Market Map Python colour asset" :disabled="pythonAssetsLoading || pythonRunLoading">
          <option :value="null">Select a Boolean or numeric-series asset</option>
          <option v-for="asset in pythonAssets.filter(item => areaMetric !== 'python' || item.outputContract === 'series')" :key="asset.versionId" :value="asset.versionId">{{ asset.name }} · {{ asset.outputContract }}</option>
        </select>
      </label>
      <span v-if="colorMetric === 'python' && pythonRunLoading" class="market-map-tool__status">Evaluating isolated Python…</span>
      <span v-if="colorMetric === 'python' && pythonRunError" class="market-map-tool__status--error" role="alert">{{ pythonRunError }}</span>
      <button type="button" class="market-map-tool__run" :disabled="loading || (!sourceId && !explicitSymbols.trim()) || (!explicitSymbols.trim() && !!activeSource && !isSourceSelectable(activeSource))" @click="run">{{ loading ? 'Loading…' : 'Refresh' }}</button>
      <label>Snapshot
        <select v-model="snapshotSelectionId" aria-label="Market Map snapshot" :disabled="snapshotLoading">
          <option value="">Live / cached result</option>
          <option v-for="snapshot in snapshots" :key="snapshot.id" :value="String(snapshot.id)">{{ snapshot.name }}</option>
        </select>
      </label>
      <input v-model="snapshotName" aria-label="Market Map snapshot name" placeholder="Snapshot name" maxlength="160" />
      <button type="button" :disabled="snapshotLoading || !map || !snapshotName.trim()" @click="saveSnapshot">{{ snapshotLoading ? 'Saving…' : 'Save snapshot' }}</button>
      <button type="button" :disabled="!map" @click="exportCsv">Export CSV</button>
      <button v-if="snapshotSelectionId" type="button" :disabled="snapshotLoading" @click="deleteSnapshot">Delete snapshot</button>
    </div>
    <p v-if="sourcesError" class="market-map-tool__status market-map-tool__status--error" role="alert">{{ sourcesError }}</p>
    <p v-if="error" class="market-map-tool__status market-map-tool__status--error" role="alert">{{ error }}</p>
    <p v-if="snapshotError" class="market-map-tool__status market-map-tool__status--error" role="alert">{{ snapshotError }}</p>
    <p v-if="publicationMessage && !explicitSymbols.trim() && !selectedIds.length" class="market-map-tool__status" role="status">{{ publicationMessage }}</p>
    <p v-if="map?.warnings.length" class="market-map-tool__status" role="status">{{ map.warnings.map(item => item.message).join(' · ') }}</p>
    <div v-if="map" class="market-map-tool__summary">
      <span>{{ map.source.name }}</span><span>{{ map.evaluated_count }}/{{ map.requested_count }} combined covered</span><span>Colour {{ coveragePercent(map.color_coverage, map.coverage) }}%</span><span>Area {{ coveragePercent(map.area_coverage, map.coverage) }}%</span><span>{{ formatFreshness(map.freshness) }}</span><span v-if="activeSnapshotName">Snapshot · {{ activeSnapshotName }}</span><span v-else-if="map.cache_hit">Cached result · {{ map.cached_at ? new Date(map.cached_at).toLocaleTimeString() : 'saved' }}</span><span v-if="map.source.locked">Locked source · {{ map.source.membership_version }}</span>
    </div>
    <div v-if="sourceId || historyLoading || historyError" class="market-map-tool__history-status" aria-label="Market Map history readiness">
      <strong>History</strong>
      <span v-if="historyLoading">Checking local bars…</span>
      <span v-else-if="historyError" class="market-map-tool__status--error" role="alert">{{ historyError }}</span>
      <template v-else-if="historyStatus">
        <span :class="`market-map-tool__history-status--${historyStatus.overall_status}`">{{ historyStatus.overall_status }}</span>
        <span v-if="historyStatus.timeframes.length">{{ historyStatus.timeframes[0].covered_member_count }}/{{ historyStatus.timeframes[0].member_count }} {{ historyStatus.timeframes[0].timeframe }} members covered</span>
        <span v-if="historyStatus.limited">Bounded to {{ historyStatus.selected_instrument_count }} of {{ historyStatus.available_instrument_count }}</span>
        <span v-if="historyRefreshMessage" role="status">{{ historyRefreshMessage }}</span>
      </template>
      <span v-if="historyRun" class="market-map-tool__history-run" role="status">Run {{ historyRun.id }} · {{ historyRun.status }}<template v-if="historyRun.progress"> · {{ historyRunProgress }}</template></span>
      <button v-if="sourceId" type="button" aria-label="Refresh Market Map history" :disabled="historyRefreshing || historyLoading" @click="refreshHistory">{{ historyRefreshing ? 'Queueing…' : 'Refresh history' }}</button>
      <button v-if="historyRun && isHistoryRunActive" type="button" aria-label="Cancel Market Map history refresh" :disabled="historyRunLoading" @click="cancelHistoryRefresh">{{ historyRunLoading ? 'Canceling…' : 'Cancel refresh' }}</button>
      <span v-if="historyRefreshError" class="market-map-tool__status--error" role="alert">{{ historyRefreshError }}</span>
    </div>
    <div v-if="map" class="market-map-tool__source-analysis-actions" aria-label="Market Map source analysis actions">
      <span v-if="selectedIds.length">{{ selectedIds.length }} selected members will be included as context</span>
      <button type="button" aria-label="Open full source in Market Breadth" @click="publishAnalysis('breadth', 'full')">Open full source in Breadth</button>
      <button type="button" aria-label="Open full source in Study Lab" @click="publishAnalysis('study_lab', 'full')">Open full source in Study Lab</button>
    </div>
    <div v-if="map && colorMetric === 'breadth'" class="market-map-tool__definition-actions" aria-label="Market Map reusable definition actions">
      <input v-model.trim="definitionName" aria-label="Market Map breadth definition name" placeholder="Reusable breadth definition name" maxlength="160" />
      <button type="button" aria-label="Save as Study Lab definition" :disabled="definitionSaving || !definitionName" @click="saveBreadthDefinition">{{ definitionSaving ? 'Saving…' : 'Save as Study Lab definition' }}</button>
      <span v-if="definitionMessage" role="status">{{ definitionMessage }}</span>
      <span v-if="definitionError" class="market-map-tool__status--error" role="alert">{{ definitionError }}</span>
    </div>
    <div v-if="map" class="market-map-tool__nodes" aria-label="Market Map groups">
      <button v-if="selectedNode" type="button" aria-label="Market Map parent group" @click="selectNode(activeNode?.parent_id ?? null)">← Up</button>
      <button v-for="node in visibleNodes" :key="node.node_id" type="button" :class="{ active: selectedNode === node.node_id }" @click="selectNode(node.node_id)">{{ node.label }} <small>{{ node.member_count }}</small></button>
    </div>
    <nav v-if="map" class="market-map-tool__breadcrumbs" aria-label="Market Map hierarchy">
      <button type="button" :class="{ active: !selectedNode }" @click="selectNode(null)">All members</button>
      <template v-for="node in breadcrumbs" :key="node.node_id">
        <span aria-hidden="true">›</span>
        <button type="button" :class="{ active: selectedNode === node.node_id }" @click="selectNode(node.node_id)">{{ node.label }}</button>
      </template>
    </nav>
    <div v-if="map" class="market-map-tool__legend" aria-label="Market Map colour and coverage legend"><span class="market-map-tool__legend--negative">−</span><span>{{ colorLabel }}</span><span class="market-map-tool__legend--positive">+</span><span class="market-map-tool__legend__coverage">Combined {{ coveragePercent(map.coverage, 0) }}% · Colour {{ coveragePercent(map.color_coverage, map.coverage) }}% · Area {{ coveragePercent(map.area_coverage, map.coverage) }}%</span></div>
    <div v-if="map" class="market-map-tool__viewport-controls" aria-label="Market Map viewport controls">
      <button type="button" aria-label="Zoom out Market Map" :disabled="viewportZoom <= 1" @click="zoomBy(-0.25)">−</button>
      <span aria-live="polite">{{ Math.round(viewportZoom * 100) }}%</span>
      <button type="button" aria-label="Zoom in Market Map" :disabled="viewportZoom >= 4" @click="zoomBy(0.25)">+</button>
      <button type="button" aria-label="Reset Market Map viewport" :disabled="viewportZoom === 1 && !panX && !panY" @click="resetViewport">Reset</button>
      <small v-if="viewportZoom > 1">Drag empty map space or use the wheel to pan and zoom.</small>
    </div>
    <div v-if="map && useCanvasTiles" class="market-map-tool__canvas-access" aria-label="Large Market Map member selection">
      <label>Find member
        <input v-model.trim="canvasSearch" aria-label="Find Large Market Map member" placeholder="Symbol or name" @keydown.enter="selectCanvasSearch" />
      </label>
      <small v-if="canvasSearch && canvasSearchMatch">{{ canvasSearchMatch.symbol }} · press Enter to select</small>
      <small v-else-if="canvasSearch">No matching member</small>
      <small v-else>Canvas tiles remain selectable by pointer; use this field for keyboard selection.</small>
    </div>
    <div v-if="map && selectedIds.length" class="market-map-tool__selection-actions" aria-label="Market Map selection actions">
      <strong>{{ selectedIds.length }} selected</strong>
      <select v-model="publicationTargetId" aria-label="Market Map target watchlist">
        <option value="">New personal watchlist…</option>
        <option v-for="target in publicationTargets" :key="target.id" :value="String(target.id)">{{ target.name }}</option>
      </select>
      <input v-if="!publicationTargetId" v-model="newPublicationName" aria-label="Market Map new watchlist name" placeholder="Watchlist name" maxlength="80" @keydown.enter.prevent="publishSelection" />
      <button type="button" :disabled="publishing || (!publicationTargetId && !newPublicationName.trim())" @click="publishSelection">{{ publishing ? 'Saving…' : 'Save selection' }}</button>
      <input v-model.trim="lockedSourceName" aria-label="Market Map locked source name" placeholder="Locked source name" maxlength="160" />
      <button type="button" :disabled="lockedSourceSaving || !lockedSourceName || !selectedIds.length" aria-label="Save selected members as locked source" @click="saveSelectedAsLockedSource">{{ lockedSourceSaving ? 'Saving…' : 'Save as locked source' }}</button>
      <button type="button" :disabled="!selectedSymbols.length" aria-label="Open selected members in chart" @click="openSelectedInChart">Open in Chart</button>
      <button type="button" :disabled="selectedSymbols.length < 2" aria-label="Compare selected members in chart" @click="compareSelectedInChart">Compare in Chart</button>
      <button type="button" :disabled="!selectedSymbols.length" aria-label="Open selected members in relative strength" @click="openSelectedInRatio">Relative Strength</button>
      <button type="button" aria-label="Open selected members in Market Breadth" @click="publishAnalysis('breadth', 'selection')">Open selected members in Breadth</button>
      <button type="button" aria-label="Open selected members in Study Lab" @click="publishAnalysis('study_lab', 'selection')">Open selected members in Study Lab</button>
      <span v-if="publicationMessage" role="status">{{ publicationMessage }}</span>
      <span v-if="publicationError" class="market-map-tool__status--error" role="alert">{{ publicationError }}</span>
    </div>
    <div v-if="map" ref="viewportRef" class="market-map-tool__tiles" aria-label="Market Map tiles" @wheel.prevent="zoomByWheel" @pointerdown="startPan" @pointermove="movePan" @pointerup="endPan" @pointercancel="endPan">
      <div class="market-map-tool__canvas" :style="canvasStyle">
        <canvas
          v-if="useCanvasTiles"
          ref="canvasRef"
          class="market-map-tool__canvas-map"
          role="img"
          :aria-label="`${visibleLayoutCells.length} Market Map members`"
          @mousemove="handleCanvasHover"
          @mouseleave="hoveredCell = null"
          @click="selectCanvasCell"
        />
        <button v-else v-for="cell in visibleLayoutCells" :key="cell.instrument_id" type="button" class="market-map-tool__tile" :class="[tileClass(cell.color_value), { 'market-map-tool__tile--selected': selectedIds.includes(cell.instrument_id) }]" :style="tileStyle(cell)" :title="`${cell.symbol} · ${cell.name}`" @pointerdown.stop @mouseenter="hoveredCell = cell" @mouseleave="hoveredCell = null" @click="selectCell($event, cell)">
          <strong>{{ cell.symbol }}</strong><span>{{ formatMetric(cell.color_value) }}</span><small>{{ cell.group_path.join(' · ') || 'All members' }}</small>
        </button>
        <div v-if="!useCanvasTiles" v-for="group in visibleLayoutGroups" :key="`group-${group.key}`" class="market-map-tool__group-frame" :style="groupFrameStyle(group)" :data-group-level="group.level" aria-hidden="true">
          <strong>{{ group.label }}</strong><small>{{ group.member_count }} members</small>
        </div>
        <small v-if="useCanvasTiles" class="market-map-tool__canvas-hint">Large universe · canvas rendering · click a tile to select</small>
        <p v-if="!visibleCells.length" class="market-map-tool__status">No covered members match this group.</p>
        <p v-else-if="visibleLayoutCells.length < visibleCells.length" class="market-map-tool__status">{{ visibleCells.length - visibleLayoutCells.length }} member(s) have no valid area value and are excluded from tile geometry.</p>
      </div>
    </div>
    <aside v-if="hoveredCell" class="market-map-tool__hover" role="status"><strong>{{ hoveredCell.symbol }}</strong><span>{{ hoveredCell.name }}</span><span>{{ hoveredCell.group_path.join(' · ') || 'All members' }}</span><span>Combined {{ coveragePercent(hoveredCell.coverage, 0) }}% · Colour {{ coveragePercent(hoveredCell.color_coverage, hoveredCell.coverage) }}% · Area {{ coveragePercent(hoveredCell.area_coverage, hoveredCell.coverage) }}%</span><span v-if="hoveredCell.classification_provenance">Classification snapshot · {{ formatClassificationProvenance(hoveredCell.classification_provenance) }}</span><span v-if="hoveredCell.warnings.length">{{ hoveredCell.warnings.map(item => item.message).join(' · ') }}</span></aside>
    <p v-if="!map && !loading" class="market-map-tool__status">Choose a canonical universe, personal watchlist, or explicit symbols to build a map.</p>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useQueryClient } from '@tanstack/vue-query'
import { api } from '@/lib/api'
import { formatSourceFailureClass as formatFailureClass, sourceAvailability, sourceAvailabilitySuffix, sourceIsNotCurrent } from '@/lib/workstation/sourceCapability'
import { useWatchlistStore } from '@/stores/watchlist'
import { useUserSettingsStore } from '@/stores/userSettings'
import { invalidateCodeAssets } from '@/lib/workstation/libraryQueries'
import { resolveCanonicalSymbols } from '@/lib/instruments'
import BreadthConditionTreeEditor, { type BreadthConditionNode } from './BreadthConditionTreeEditor.vue'
import { marketMapPythonUniverse } from '@/lib/workstation/marketMapPublication'
import { cancelWatchlistHistoryRefreshRun, deleteMarketMapSnapshot, fetchMarketMap, fetchMarketMapSnapshot, fetchMarketMapSnapshots, fetchWatchlistHistoryRefreshRun, fetchWatchlistSourceHistoryStatus, layoutMarketMapCells, layoutMarketMapGroupsFromLayout, refreshWatchlistSourceHistory, saveMarketMapSnapshot, type MarketMapLayoutCell, type MarketMapLayoutGroup, type WatchlistHistoryRefreshRun, type WatchlistSourceHistoryStatus } from '@/lib/workstation/marketMap'
import type { MarketMap, MarketMapAreaMetric, MarketMapCell, MarketMapColorMetric, MarketMapGroupBy, MarketMapNumericAreaField, MarketMapSnapshotSummary, Timeframe, WatchlistSource, WatchlistSourceKind } from '@/types'

type MarketMapSort = 'area_desc' | 'color_desc' | 'symbol_asc'
type MarketMapSource = WatchlistSource & { pinned: boolean }

const props = withDefaults(defineProps<{ configuration?: Record<string, unknown> }>(), { configuration: () => ({}) })
const emit = defineEmits<{
  configuration: [value: Record<string, unknown>]
  select: [symbol: string, instrumentId: number]
  compare: [symbols: string[]]
  ratio: [symbols: string[]]
  publishAnalysis: [payload: { target: 'breadth' | 'study_lab'; sourceId: string; selectedIds: number[]; selectedSymbols: string[]; scope: 'full' | 'selection' }]
}>()
const watchlistStore = useWatchlistStore()
const userSettingsStore = useUserSettingsStore()
const queryClient = useQueryClient()
const sources = computed(() => [...watchlistStore.watchlistSources]
  .map(source => ({ ...source, pinned: userSettingsStore.pinnedSourceIds.includes(source.source_id) }))
  .sort((left, right) => Number(right.pinned) - Number(left.pinned) || left.name.localeCompare(right.name)))
const sourceGroupOrder: WatchlistSourceKind[] = ['index_membership', 'etf_holdings', 'market_group', 'personal', 'screener_managed', 'combo', 'explicit']
const sourceGroups = computed(() => {
  const grouped = new Map<WatchlistSourceKind, MarketMapSource[]>()
  for (const source of sources.value) {
    const bucket = grouped.get(source.source_kind) ?? []
    bucket.push(source)
    grouped.set(source.source_kind, bucket)
  }
  return sourceGroupOrder
    .filter(key => grouped.has(key))
    .map(key => ({ key, label: sourceKindLabel(key), sources: grouped.get(key) ?? [] }))
})
const sourceId = ref(String(props.configuration.source_id ?? ''))
const explicitSymbols = ref(String(props.configuration.explicit_symbols ?? ''))
const groupBy = ref<MarketMapGroupBy>((props.configuration.group_by as MarketMapGroupBy) ?? 'sector_industry')
const sortBy = ref<MarketMapSort>((props.configuration.sort_by as MarketMapSort) ?? 'area_desc')
const period = ref(String(props.configuration.period ?? '1D'))
const configuredTimeframe = String(props.configuration.timeframe ?? 'D1').toUpperCase()
const timeframe = ref<Timeframe>((['D1', 'W1', 'MN'] as string[]).includes(configuredTimeframe) ? configuredTimeframe as Timeframe : 'D1')
const areaMetric = ref<MarketMapAreaMetric>((props.configuration.area_metric as MarketMapAreaMetric) ?? 'market_cap')
const areaField = ref<MarketMapNumericAreaField>((props.configuration.area_field as MarketMapNumericAreaField) ?? 'avg_volume_30d')
const colorMetric = ref<MarketMapColorMetric>((props.configuration.color_metric as MarketMapColorMetric) ?? 'return')
const referenceSymbol = ref(String(props.configuration.reference_symbol ?? ''))
const referenceSourceId = ref(String(props.configuration.reference_source_id ?? ''))
const breadthConditionKind = ref(String(props.configuration.breadth_condition_kind ?? 'above_moving_average'))
const breadthConditionPeriod = ref(Number(props.configuration.breadth_condition_period ?? 200))
const breadthConditionThreshold = ref(Number(props.configuration.breadth_condition_threshold ?? 0.01))
const breadthEventType = ref(String(props.configuration.breadth_event_type ?? 'any'))
const breadthEventLookback = ref(Number(props.configuration.breadth_event_lookback ?? 0))
const advancedBreadthEditor = ref(Boolean(props.configuration.advanced_breadth_editor ?? false))
const breadthConditionTree = ref<BreadthConditionNode>((props.configuration.condition as BreadthConditionNode | undefined) ?? { kind: 'above_moving_average', params: { period: 200, average: 'sma', comparator: 'above' } })
const pythonCodeVersionId = ref<number | null>(Number(props.configuration.python_code_version_id ?? 0) || null)
const pythonRunId = ref<number | null>(Number(props.configuration.python_run_id ?? 0) || null)
const pythonAssets = ref<Array<{ versionId: number; name: string; outputContract: 'boolean' | 'series' }>>([])
const pythonAssetsLoading = ref(false)
const pythonRunLoading = ref(false)
const pythonRunError = ref('')
const periods = ['1D', '1W', 'MTD', 'YTD', '1M', '3M', '6M', '1Y', 'CUSTOM']
const startDate = ref(String(props.configuration.start_date ?? ''))
const endDate = ref(String(props.configuration.end_date ?? ''))
const loading = ref(false)
const error = ref('')
const map = ref<MarketMap | null>(null)
const selectedNode = ref<string | null>(null)
const selectedIds = ref<number[]>([])
const hoveredCell = ref<MarketMapCell | null>(null)
const viewportRef = ref<HTMLElement | null>(null)
const canvasRef = ref<HTMLCanvasElement | null>(null)
const viewportZoom = ref(1)
const panX = ref(0)
const panY = ref(0)
const panStart = ref<{ pointerX: number; pointerY: number; x: number; y: number } | null>(null)
const panMoved = ref(false)
const canvasSearch = ref('')
const publicationTargetId = ref('')
const newPublicationName = ref('')
const publishing = ref(false)
const publicationMessage = ref('')
const publicationError = ref('')
const sourceCloneBusy = ref(false)
const sourceCloneMessage = ref('')
const sourceCloneError = ref('')
const sourceCloneRetryIds = ref<number[]>([])
const sourceCloneRetryTargetId = ref<number | null>(null)
const sourceCloneRetryTotal = ref(0)
const etfBootstrapSymbol = ref('')
const etfBootstrapBusy = ref(false)
const etfBootstrapMessage = ref('')
const etfBootstrapError = ref('')
const explicitWatchlistName = ref('')
const explicitSaving = ref(false)
const lockedSourceName = ref('')
const lockedSourceSaving = ref(false)
const snapshots = ref<MarketMapSnapshotSummary[]>([])
const snapshotSelectionId = ref('')
const snapshotName = ref('')
const activeSnapshotName = ref('')
const snapshotLoading = ref(false)
const snapshotError = ref('')
const historyStatus = ref<WatchlistSourceHistoryStatus | null>(null)
const historyLoading = ref(false)
const historyError = ref('')
const historyRefreshing = ref(false)
const historyRefreshMessage = ref('')
const historyRefreshError = ref('')
const historyRun = ref<WatchlistHistoryRefreshRun | null>(null)
const historyRunLoading = ref(false)
let historyPollTimer: ReturnType<typeof setTimeout> | null = null
// Source changes can overlap while Golden Layout is opening/closing repeated
// Market Map tools.  Fence each request so a slower response from the prior
// universe cannot clear or replace the currently selected map.
let runGeneration = 0
let componentMounted = false
const definitionName = ref(String(props.configuration.definition_name ?? ''))
const definitionSaving = ref(false)
const definitionMessage = ref('')
const definitionError = ref('')
const skipNextSourceRun = ref(false)
const loadingSources = computed(() => watchlistStore.watchlistSourcesLoading)
const sourcesError = computed(() => watchlistStore.watchlistSourcesError)
const publicationTargets = computed(() => watchlistStore.watchlists.filter(watchlist => !watchlist.is_managed && !watchlist.is_locked))
const activeSource = computed(() => sources.value.find(source => source.source_id === sourceId.value) ?? null)
const sourceFollowed = computed(() => Boolean(activeSource.value && userSettingsStore.followedSourceIds.includes(activeSource.value.source_id)))
const sourcePinned = computed(() => Boolean(activeSource.value && userSettingsStore.pinnedSourceIds.includes(activeSource.value.source_id)))
const LARGE_MAP_CANVAS_THRESHOLD = 1500

function isSourceSelectable(source: WatchlistSource): boolean {
  return sourceAvailability(source) !== 'unavailable'
}

function sourceKindLabel(kind: WatchlistSourceKind): string {
  return ({
    index_membership: 'Index and managed universes',
    etf_holdings: 'ETF holdings',
    market_group: 'Market groups',
    personal: 'Personal watchlists',
    screener_managed: 'Managed scans',
    combo: 'Combo watchlists',
    explicit: 'Explicit selections',
  } satisfies Record<WatchlistSourceKind, string>)[kind]
}

function toggleSourceFollow() {
  if (activeSource.value?.can_follow) userSettingsStore.toggleFollowedSource(activeSource.value.source_id)
}

function toggleSourcePin() {
  if (activeSource.value?.can_clone) userSettingsStore.togglePinnedSource(activeSource.value.source_id)
}

function sourceSnapshotName(source: WatchlistSource): string {
  const versionParts = source.membership_version?.split(':') ?? []
  const date = source.composition_date ?? versionParts[versionParts.length - 1] ?? 'current'
  return `${source.name} snapshot ${date}`.slice(0, 80)
}

function sourceSnapshotDescription(source: WatchlistSource): string {
  const provenanceSource = source.source ?? source.provenance?.source_provider ?? 'canonical local source'
  return [
    `Cloned from ${source.source_id}`,
    `membership_version=${source.membership_version ?? 'unknown'}`,
    `effective_at=${source.effective_at ?? 'unknown'}`,
    `known_at=${source.known_at ?? 'unknown'}`,
    `composition_date=${source.composition_date ?? 'unknown'}`,
    `source=${provenanceSource}`,
  ].join('; ')
}

async function cloneActiveSource() {
  const source = activeSource.value
  if (!source || !map.value || sourceCloneBusy.value) return
  sourceCloneBusy.value = true
  sourceCloneMessage.value = ''
  sourceCloneError.value = ''
  sourceCloneRetryIds.value = []
  sourceCloneRetryTargetId.value = null
  sourceCloneRetryTotal.value = 0
  try {
    const asOf = source.composition_date ? `${source.composition_date}T23:59:59Z` : null
    const resolved = await watchlistStore.resolveWatchlistSource(source.source_id, asOf)
    const memberIds = [...new Set((resolved?.members ?? []).map(member => member.instrument_id).filter(id => Number.isInteger(id) && id > 0))]
    if (!memberIds.length) throw new Error('The selected source has no canonical members available to clone.')
    const descriptor = resolved?.source ?? source
    const created = await watchlistStore.createWatchlist(sourceSnapshotName(descriptor), sourceSnapshotDescription(descriptor))
    if (!created) throw new Error('Unable to create the cloned watchlist.')
    const existingIds = new Set((created.items ?? []).map(item => item.instrument_id))
    const pendingIds = memberIds.filter(instrumentId => !existingIds.has(instrumentId))
    const result = await addCloneMembers(created.id, pendingIds)
    sourceCloneRetryTargetId.value = result.failed.length ? created.id : null
    sourceCloneRetryIds.value = result.failed
    sourceCloneRetryTotal.value = memberIds.length
    sourceCloneMessage.value = `${result.added + existingIds.size}/${memberIds.length} members cloned as ${created.name} · ${descriptor.membership_version ?? 'current snapshot'}${result.failed.length ? ` · ${result.failed.length} pending (${result.failed.join(', ')})` : ''}`
  } catch (cause) {
    sourceCloneError.value = cause instanceof Error ? cause.message : 'Unable to clone the selected source'
  } finally {
    sourceCloneBusy.value = false
  }
}

async function addCloneMembers(targetId: number, memberIds: number[]) {
  const failed: number[] = []
  let added = 0
  for (const instrumentId of memberIds) {
    const result = await watchlistStore.addItem(targetId, instrumentId)
    if (result) added += 1
    else failed.push(instrumentId)
  }
  return { added, failed }
}

async function retrySourceClone() {
  const targetId = sourceCloneRetryTargetId.value
  const retryIds = [...sourceCloneRetryIds.value]
  if (!targetId || !retryIds.length || sourceCloneBusy.value) return
  sourceCloneBusy.value = true
  sourceCloneMessage.value = ''
  sourceCloneError.value = ''
  try {
    const result = await addCloneMembers(targetId, retryIds)
    sourceCloneRetryIds.value = result.failed
    sourceCloneRetryTargetId.value = result.failed.length ? targetId : null
    const completed = sourceCloneRetryTotal.value - result.failed.length
    sourceCloneMessage.value = `${completed}/${sourceCloneRetryTotal.value} members cloned${result.failed.length ? ` · ${result.failed.length} still pending (${result.failed.join(', ')})` : ' · retry complete'}`
  } catch (cause) {
    sourceCloneError.value = cause instanceof Error ? cause.message : 'Unable to retry failed source clone members'
  } finally {
    sourceCloneBusy.value = false
  }
}

function clearHistoryPoll() {
  if (historyPollTimer) clearTimeout(historyPollTimer)
  historyPollTimer = null
}

function scheduleHistoryPoll() {
  clearHistoryPoll()
  const sourcePending = historyStatus.value && ['pending', 'fetching'].includes(historyStatus.value.overall_status)
  if (!sourcePending && !isHistoryRunActive.value) return
  historyPollTimer = setTimeout(() => { void loadHistoryStatus(true) }, 1500)
}

const isHistoryRunActive = computed(() => Boolean(historyRun.value && ['queued', 'running'].includes(historyRun.value.status)))
const historyRunProgress = computed(() => {
  if (!historyRun.value) return ''
  const progress = historyRun.value.progress || {}
  const done = Number(progress.complete ?? 0) + Number(progress.canceled ?? 0)
  const total = historyRun.value.selected_instrument_count
  if (Number.isFinite(total) && total > 0 && Number.isFinite(done)) return `${done}/${total}`
  return `${historyRun.value.queued_count + historyRun.value.already_queued_count} queued`
})

async function loadHistoryRun(schedulePoll = false) {
  if (!historyRun.value) return
  try {
    historyRun.value = await fetchWatchlistHistoryRefreshRun(historyRun.value.id)
    if (schedulePoll) scheduleHistoryPoll()
  } catch (cause) {
    historyRefreshError.value = cause instanceof Error ? cause.message : 'Unable to read history refresh progress'
  }
}

async function loadHistoryStatus(schedulePoll = false) {
  if (!sourceId.value) {
    clearHistoryPoll()
    historyStatus.value = null
    return
  }
  historyLoading.value = true
  historyError.value = ''
  try {
    const result = await fetchWatchlistSourceHistoryStatus(sourceId.value, [timeframe.value])
    historyStatus.value = result && !Array.isArray(result) ? result : null
    await loadHistoryRun()
    if (schedulePoll) scheduleHistoryPoll()
  } catch (cause) {
    historyStatus.value = null
    historyError.value = cause instanceof Error ? cause.message : 'Unable to read local history readiness'
  } finally {
    historyLoading.value = false
  }
}

async function refreshHistory() {
  if (!sourceId.value || historyRefreshing.value) return
  historyRefreshing.value = true
  historyRefreshMessage.value = ''
  historyRefreshError.value = ''
  try {
    const result = await refreshWatchlistSourceHistory(sourceId.value, [timeframe.value])
    historyRun.value = result.run_id ? await fetchWatchlistHistoryRefreshRun(result.run_id) : null
    const jobs = result.queued + result.already_queued
    historyRefreshMessage.value = result.queue_unavailable
      ? 'History queue unavailable; cached bars were not changed.'
      : `${jobs} history job${jobs === 1 ? '' : 's'} queued`
    await loadHistoryStatus(true)
  } catch (cause) {
    historyRefreshError.value = cause instanceof Error ? cause.message : 'Unable to queue history refresh'
  } finally {
    historyRefreshing.value = false
  }
}

async function bootstrapEtfSource() {
  const symbol = etfBootstrapSymbol.value.trim().toUpperCase()
  if (etfBootstrapBusy.value || !symbol) return
  if (!/^[A-Z][A-Z0-9./-]{0,19}$/.test(symbol)) {
    etfBootstrapError.value = 'Enter one canonical ETF symbol.'
    etfBootstrapMessage.value = ''
    return
  }
  etfBootstrapBusy.value = true
  etfBootstrapMessage.value = ''
  etfBootstrapError.value = ''
  try {
    const result = await api.post<{ latest_snapshot?: unknown; refresh_succeeded?: boolean; message?: string | null }>(
      `/etf-holdings/${encodeURIComponent(symbol)}/bootstrap`,
      {},
    )
    // This is an explicit, user-triggered bootstrap. It does not turn ordinary
    // source reads into provider fan-out; the canonical source catalog remains
    // the only map input after this action completes.
    await watchlistStore.loadWatchlistSources()
    const source = watchlistStore.watchlistSources.find(item => item.source_id === `etf-holdings:${symbol}`)
    if (!source) throw new Error(`${symbol} was registered but is not available as a canonical ETF source.`)
    sourceId.value = source.source_id
    explicitSymbols.value = ''
    etfBootstrapMessage.value = result.latest_snapshot
      ? `${symbol} holdings source loaded.`
      : `${symbol} source registered; membership is pending hydration.`
    if (result.message && !result.latest_snapshot) etfBootstrapMessage.value += ` ${result.message}`
  } catch (cause) {
    etfBootstrapError.value = cause instanceof Error ? cause.message : 'Unable to load ETF constituent universe'
  } finally {
    etfBootstrapBusy.value = false
  }
}

async function cancelHistoryRefresh() {
  if (!historyRun.value || !isHistoryRunActive.value || historyRunLoading.value) return
  historyRunLoading.value = true
  historyRefreshError.value = ''
  try {
    historyRun.value = await cancelWatchlistHistoryRefreshRun(historyRun.value.id)
    historyRefreshMessage.value = 'History refresh canceled; cached bars were retained.'
    clearHistoryPoll()
    await loadHistoryStatus()
  } catch (cause) {
    historyRefreshError.value = cause instanceof Error ? cause.message : 'Unable to cancel history refresh'
  } finally {
    historyRunLoading.value = false
  }
}

function formatFreshness(value: string) { return value.replace(/_/g, ' ') }
function coveragePercent(value: number | null | undefined, fallback: number) {
  const resolved = value ?? fallback
  return Math.round(Math.max(0, Math.min(1, resolved)) * 100)
}
function formatMetric(value: number | null | undefined) {
  if (value == null || !Number.isFinite(value)) return '—'
  if (colorMetric.value === 'rsi_14') return value.toFixed(1)
  return `${(value * 100).toFixed(2)}%`
}
function formatClassificationProvenance(value: Record<string, unknown>) {
  const provider = typeof value.provider_name === 'string' && value.provider_name.trim()
    ? value.provider_name
    : 'local snapshot'
  const observed = typeof value.observed_at === 'string' ? value.observed_at.slice(0, 10) : null
  return observed ? `${provider} · observed ${observed}` : provider
}
function tileClass(value: number | null | undefined) {
  if (value == null) return 'market-map-tool__tile--unknown'
  return value >= 0 ? 'market-map-tool__tile--positive' : 'market-map-tool__tile--negative'
}
function tileStyle(cell: MarketMapLayoutCell) {
  return { left: `${cell.x}%`, top: `${cell.y}%`, width: `${cell.width}%`, height: `${cell.height}%` }
}
function groupFrameStyle(group: MarketMapLayoutGroup) {
  return { left: `${group.x}%`, top: `${group.y}%`, width: `${group.width}%`, height: `${group.height}%`, zIndex: 3 + group.level }
}
function selectCell(event: MouseEvent, cell: MarketMapCell) {
  const additive = event.shiftKey || event.ctrlKey || event.metaKey
  selectedIds.value = additive
    ? (selectedIds.value.includes(cell.instrument_id) ? selectedIds.value.filter(id => id !== cell.instrument_id) : [...selectedIds.value, cell.instrument_id])
    : [cell.instrument_id]
  emit('select', cell.symbol, cell.instrument_id)
}
const activeNode = computed(() => map.value?.nodes.find(node => node.node_id === selectedNode.value) ?? null)
const visibleNodes = computed(() => {
  const parentId = selectedNode.value ?? 'root'
  return (map.value?.nodes ?? []).filter(node => node.node_id !== 'root' && (node.parent_id ?? 'root') === parentId)
})
const breadcrumbs = computed(() => {
  if (!activeNode.value || !map.value) return []
  return activeNode.value.group_path
    .map((_, index) => activeNode.value?.group_path.slice(0, index + 1) ?? [])
    .map(path => map.value?.nodes.find(node => node.group_path.length === path.length && node.group_path.every((part, index) => part === path[index])))
    .filter((node): node is NonNullable<typeof node> => Boolean(node))
})
const visibleCells = computed(() => {
  if (!map.value) return []
  const path = activeNode.value?.group_path ?? []
  const cells = path.length
    ? map.value.cells.filter(cell => path.every((part, index) => cell.group_path[index] === part))
    : map.value.cells
  return [...cells].sort((left, right) => {
    if (sortBy.value === 'symbol_asc') return left.symbol.localeCompare(right.symbol)
    const leftValue = sortBy.value === 'color_desc' ? left.color_value : left.area_value
    const rightValue = sortBy.value === 'color_desc' ? right.color_value : right.area_value
    if (leftValue == null && rightValue == null) return left.symbol.localeCompare(right.symbol)
    if (leftValue == null) return 1
    if (rightValue == null) return -1
    return rightValue - leftValue || left.symbol.localeCompare(right.symbol)
  })
})
const visibleLayoutCells = computed<MarketMapLayoutCell[]>(() => layoutMarketMapCells(visibleCells.value))
const visibleLayoutGroups = computed<MarketMapLayoutGroup[]>(() => layoutMarketMapGroupsFromLayout(visibleLayoutCells.value))
const useCanvasTiles = computed(() => visibleLayoutCells.value.length > LARGE_MAP_CANVAS_THRESHOLD)
const canvasSearchMatch = computed(() => {
  const query = canvasSearch.value.trim().toLowerCase()
  if (!query) return null
  return visibleCells.value.find(cell => cell.symbol.toLowerCase().includes(query) || cell.name.toLowerCase().includes(query)) ?? null
})

let canvasDrawFrame: number | null = null
function canvasFill(value: number | null | undefined) {
  if (value == null || !Number.isFinite(value)) return '#3c4652'
  return value >= 0 ? '#207d56' : '#843f50'
}
function drawCanvas() {
  canvasDrawFrame = null
  const canvas = canvasRef.value
  const viewport = viewportRef.value
  if (!canvas || !viewport || !useCanvasTiles.value) return
  const width = Math.max(1, viewport.clientWidth)
  const height = Math.max(1, viewport.clientHeight)
  const dpr = Math.min(2, Math.max(1, window.devicePixelRatio || 1))
  canvas.width = Math.round(width * dpr)
  canvas.height = Math.round(height * dpr)
  const context = (() => {
    try { return canvas.getContext('2d') } catch { return null }
  })()
  if (!context) return
  context.setTransform(dpr, 0, 0, dpr, 0, 0)
  context.clearRect(0, 0, width, height)
  context.font = '600 11px Segoe UI, Arial, sans-serif'
  context.textAlign = 'center'
  context.textBaseline = 'middle'
  for (const cell of visibleLayoutCells.value) {
    const x = (cell.x / 100) * width
    const y = (cell.y / 100) * height
    const tileWidth = (cell.width / 100) * width
    const tileHeight = (cell.height / 100) * height
    context.fillStyle = canvasFill(cell.color_value)
    context.fillRect(x, y, tileWidth, tileHeight)
    if (selectedIds.value.includes(cell.instrument_id)) {
      context.strokeStyle = '#f7d87b'
      context.lineWidth = 2
      context.strokeRect(x + 1, y + 1, Math.max(0, tileWidth - 2), Math.max(0, tileHeight - 2))
    }
    // At very small scales the symbol text would become unreadable and would
    // dominate paint time. The hover card remains the authoritative detail.
    if (tileWidth < 28 || tileHeight < 20) continue
    context.fillStyle = '#ffffff'
    context.font = `${tileWidth >= 54 && tileHeight >= 34 ? '600 13px' : '600 10px'} Segoe UI, Arial, sans-serif`
    context.fillText(cell.symbol, x + tileWidth / 2, y + tileHeight / 2 - (tileHeight >= 34 ? 6 : 0), Math.max(10, tileWidth - 4))
    if (tileWidth >= 54 && tileHeight >= 34) {
      context.font = '10px Segoe UI, Arial, sans-serif'
      context.fillText(formatMetric(cell.color_value), x + tileWidth / 2, y + tileHeight / 2 + 8, Math.max(10, tileWidth - 4))
    }
  }
  // Paint hierarchy after member fills/text so group boundaries and labels
  // remain visible in the large-universe canvas. The exact V25 treatment
  // remains a visual reference gap; this is a low-cost, deterministic oracle.
  for (const group of visibleLayoutGroups.value) {
    const x = (group.x / 100) * width
    const y = (group.y / 100) * height
    const groupWidth = (group.width / 100) * width
    const groupHeight = (group.height / 100) * height
    context.strokeStyle = '#90a2b5'
    context.lineWidth = 1
    context.strokeRect(x + 0.5, y + 0.5, Math.max(0, groupWidth - 1), Math.max(0, groupHeight - 1))
    if (groupWidth >= 48 && groupHeight >= 18) {
      context.fillStyle = '#d4d9e2'
      context.font = `${group.level === 0 ? '600 11px' : '600 10px'} Segoe UI, Arial, sans-serif`
      context.textAlign = 'left'
      context.textBaseline = 'top'
      context.fillText(`${group.label} · ${group.member_count}`, x + 5, y + 4, Math.max(20, groupWidth - 10))
      context.textAlign = 'center'
      context.textBaseline = 'middle'
    }
  }
}
function scheduleCanvasDraw() {
  if (!useCanvasTiles.value || canvasDrawFrame != null) return
  canvasDrawFrame = window.requestAnimationFrame(drawCanvas)
}
function canvasCellAt(event: MouseEvent): MarketMapLayoutCell | null {
  const canvas = event.currentTarget instanceof HTMLCanvasElement ? event.currentTarget : null
  if (!canvas) return null
  const bounds = canvas.getBoundingClientRect()
  if (!bounds.width || !bounds.height) return null
  const x = ((event.clientX - bounds.left) / bounds.width) * 100
  const y = ((event.clientY - bounds.top) / bounds.height) * 100
  return visibleLayoutCells.value.find(cell => x >= cell.x && x <= cell.x + cell.width && y >= cell.y && y <= cell.y + cell.height) ?? null
}
function handleCanvasHover(event: MouseEvent) {
  hoveredCell.value = canvasCellAt(event)
}
function selectCanvasCell(event: MouseEvent) {
  if (panMoved.value) {
    panMoved.value = false
    return
  }
  const cell = canvasCellAt(event)
  if (cell) selectCell(event, cell)
}
function selectCanvasSearch(event: KeyboardEvent) {
  if (event.key !== 'Enter') return
  const cell = canvasSearchMatch.value
  if (!cell) return
  selectedIds.value = [cell.instrument_id]
  hoveredCell.value = cell
  emit('select', cell.symbol, cell.instrument_id)
}

watch([visibleLayoutCells, selectedIds, useCanvasTiles], scheduleCanvasDraw, { deep: true })
watch([viewportZoom, panX, panY], scheduleCanvasDraw)
const breadthCondition = computed<Record<string, unknown> | null>(() => {
  if (colorMetric.value !== 'breadth') return null
  if (advancedBreadthEditor.value) return breadthConditionTree.value
  if (breadthConditionKind.value === 'above_moving_average') return { kind: 'above_moving_average', params: { period: breadthConditionPeriod.value, average: 'sma', comparator: 'above' } }
  if (breadthConditionKind.value === 'within_52_week_high') return { kind: 'within_52_week_high', params: { lookback: 252, threshold: breadthConditionThreshold.value, direction: 'high' } }
  if (breadthConditionKind.value === 'new_high_low') return { kind: 'new_high_low', params: { lookback: breadthConditionPeriod.value, direction: 'high' } }
  if (breadthConditionKind.value === 'rsi') return { kind: 'rsi', params: { period: 14, operator: 'gte', threshold: breadthConditionThreshold.value } }
  if (breadthConditionKind.value === 'volume_ratio') return { kind: 'volume_ratio', params: { period: 50, operator: 'gte', threshold: breadthConditionThreshold.value } }
  if (breadthConditionKind.value === 'event') return { kind: 'event', params: { event_type: breadthEventType.value, lookback_days: breadthEventLookback.value, include_estimates: false } }
  return { kind: 'relative_strength', params: { lookback: breadthConditionPeriod.value, operator: 'gte', threshold: 0 } }
})
function conditionNeedsReference(node: BreadthConditionNode | null): boolean {
  if (!node) return false
  if (node.kind === 'relative_strength' || node.kind === 'series_comparison') return true
  const children = node.params?.conditions
  return Array.isArray(children) && children.some(child => conditionNeedsReference(child as BreadthConditionNode))
}
const referenceNeeded = computed(() => colorMetric.value === 'breadth' && conditionNeedsReference(breadthConditionTree.value))
const colorLabel = computed(() => colorMetric.value.replace(/_/g, ' '))
const canvasStyle = computed(() => ({ transform: `translate(${panX.value}%, ${panY.value}%) scale(${viewportZoom.value})` }))

function pythonUniverse() {
  return marketMapPythonUniverse(sourceId.value)
}

async function loadPythonAssets() {
  pythonAssetsLoading.value = true
  try {
    const assets = await api.get<Array<{ kind: string; name: string; versions: Array<{ id?: number; version_number: number; output_contract?: string }> }>>('/code/assets')
    pythonAssets.value = (assets ?? []).filter(asset => asset.kind === 'condition').flatMap(asset => {
      const version = asset.versions.slice(-1)[0]
      if (version?.id == null || (version.output_contract !== 'boolean' && version.output_contract !== 'series')) return []
      return [{ versionId: version.id, name: `${asset.name} v${version.version_number}`, outputContract: version.output_contract }]
    })
  } catch (cause) {
    pythonRunError.value = cause instanceof Error ? cause.message : 'Unable to load Python code assets'
  } finally {
    pythonAssetsLoading.value = false
  }
}

async function resolvePythonRun() {
  pythonRunError.value = ''
  if (pythonCodeVersionId.value == null) throw new Error('Select a Boolean or numeric-series Python asset first.')
  const selected = pythonAssets.value.find(asset => asset.versionId === pythonCodeVersionId.value)
  if (!selected) throw new Error('The selected Python asset is unavailable or no longer active.')
  const queued = await api.post<{ run_id: number }>('/analysis/breadth/python', {
    code_version_id: selected.versionId,
    universe: pythonUniverse(),
    output_contract: selected.outputContract,
    series_target: selected.outputContract === 'series' ? { operator: 'gte', threshold: 0 } : null,
    timeframe: timeframe.value,
    adjusted: true,
    history: false,
  })
  pythonRunLoading.value = true
  try {
    for (let attempt = 0; attempt < 240; attempt += 1) {
      const result = await api.get<{ status: string }>(`/analysis/breadth/python/runs/${queued.run_id}`)
      if (result.status === 'completed') {
        pythonRunId.value = queued.run_id
        return
      }
      if (result.status === 'failed' || result.status === 'canceled') throw new Error(`Python colour run ${result.status}.`)
      await new Promise(resolve => setTimeout(resolve, 250))
    }
    throw new Error('Python colour run did not finish within 60 seconds; its run remains available for retry.')
  } finally {
    pythonRunLoading.value = false
  }
}

function selectNode(nodeId: string | null) {
  selectedNode.value = nodeId
  selectedIds.value = []
  resetViewport()
}
function clampPan(value: number) {
  const limit = (viewportZoom.value - 1) * 100
  return Math.max(-limit, Math.min(0, value))
}
function resetViewport() {
  viewportZoom.value = 1
  panX.value = 0
  panY.value = 0
  panStart.value = null
  panMoved.value = false
}
function zoomBy(delta: number) {
  const next = Math.max(1, Math.min(4, Number((viewportZoom.value + delta).toFixed(2))))
  viewportZoom.value = next
  panX.value = clampPan(panX.value)
  panY.value = clampPan(panY.value)
}
function zoomByWheel(event: WheelEvent) {
  zoomBy(event.deltaY > 0 ? -0.25 : 0.25)
}
function startPan(event: PointerEvent) {
  if (viewportZoom.value <= 1 || (event.target instanceof Element && event.target.closest('button'))) return
  const element = event.currentTarget
  if (!(element instanceof HTMLElement)) return
  panMoved.value = false
  panStart.value = { pointerX: event.clientX, pointerY: event.clientY, x: panX.value, y: panY.value }
  element.setPointerCapture(event.pointerId)
}
function movePan(event: PointerEvent) {
  if (!panStart.value || !viewportRef.value) return
  if (Math.abs(event.clientX - panStart.value.pointerX) + Math.abs(event.clientY - panStart.value.pointerY) > 2) panMoved.value = true
  const bounds = viewportRef.value.getBoundingClientRect()
  panX.value = clampPan(panStart.value.x + ((event.clientX - panStart.value.pointerX) / Math.max(bounds.width, 1)) * 100)
  panY.value = clampPan(panStart.value.y + ((event.clientY - panStart.value.pointerY) / Math.max(bounds.height, 1)) * 100)
}
function endPan(event: PointerEvent) {
  const element = event.currentTarget
  if (element instanceof HTMLElement && element.hasPointerCapture(event.pointerId)) element.releasePointerCapture(event.pointerId)
  panStart.value = null
}
async function publishSelection() {
  if (!selectedIds.value.length || publishing.value) return
  publishing.value = true
  publicationMessage.value = ''
  publicationError.value = ''
  try {
    let targetId = Number(publicationTargetId.value)
    if (!Number.isInteger(targetId) || targetId <= 0) {
      const name = newPublicationName.value.trim()
      if (!name) return
      const created = await watchlistStore.createWatchlist(name)
      if (!created) throw new Error('Unable to create personal watchlist')
      targetId = created.id
      publicationTargetId.value = String(targetId)
    }
    const results = await Promise.all(selectedIds.value.map(instrumentId => watchlistStore.addItem(targetId, instrumentId)))
    const added = results.filter(Boolean).length
    publicationMessage.value = `${added} selected member${added === 1 ? '' : 's'} saved`
  } catch (cause) {
    publicationError.value = cause instanceof Error ? cause.message : 'Unable to save selected members'
  } finally {
    publishing.value = false
  }
}

function explicitSourceMemberIds(): number[] {
  const raw = map.value?.source.provenance?.instrument_ids
  return Array.isArray(raw)
    ? [...new Set(raw.filter((value): value is number => typeof value === 'number' && Number.isInteger(value) && value > 0))]
    : sourceId.value.startsWith('explicit:')
      ? [...new Set(sourceId.value.slice('explicit:'.length).split(',').map(Number).filter(value => Number.isInteger(value) && value > 0))]
      : []
}

async function saveExplicitSource() {
  const memberIds = explicitSourceMemberIds()
  const name = explicitWatchlistName.value.trim()
  if (!memberIds.length || !name || explicitSaving.value) return
  explicitSaving.value = true
  publicationMessage.value = ''
  publicationError.value = ''
  try {
    const created = await watchlistStore.createWatchlist(name)
    if (!created) throw new Error('Unable to create personal watchlist')
    const results = await Promise.all(memberIds.map(instrumentId => watchlistStore.addItem(created.id, instrumentId)))
    const added = results.filter(Boolean).length
    publicationMessage.value = `${added} canonical member${added === 1 ? '' : 's'} saved as ${created.name}`
    explicitWatchlistName.value = ''
  } catch (cause) {
    publicationError.value = cause instanceof Error ? cause.message : 'Unable to save explicit source'
  } finally {
    explicitSaving.value = false
  }
}

async function saveLockedSource(memberIds: number[], name: string) {
  const normalizedIds = [...new Set(memberIds.filter(id => Number.isInteger(id) && id > 0))]
  const normalizedName = name.trim()
  if (!normalizedIds.length || !normalizedName || lockedSourceSaving.value) return
  lockedSourceSaving.value = true
  publicationMessage.value = ''
  publicationError.value = ''
  try {
    const saved = await api.post<WatchlistSource>('/watchlists/sources/explicit', {
      name: normalizedName,
      instrument_ids: normalizedIds,
      parent_source_id: sourceId.value || null,
      parent_membership_version: map.value?.membership_version ?? map.value?.source.membership_version ?? activeSource.value?.membership_version ?? null,
    })
    await watchlistStore.loadWatchlistSources()
    skipNextSourceRun.value = true
    sourceId.value = saved.source_id
    explicitSymbols.value = ''
    selectedIds.value = []
    lockedSourceName.value = ''
    explicitWatchlistName.value = ''
    publicationMessage.value = normalizedIds.length + ' canonical member' + (normalizedIds.length === 1 ? '' : 's') + ' saved as locked source ' + saved.name
    await run()
  } catch (cause) {
    publicationError.value = cause instanceof Error ? cause.message : 'Unable to save locked explicit source'
  } finally {
    lockedSourceSaving.value = false
  }
}

async function saveSelectedAsLockedSource() {
  await saveLockedSource(selectedIds.value, lockedSourceName.value)
}

async function saveExplicitLockedSource() {
  await run()
  await saveLockedSource(explicitSourceMemberIds(), explicitWatchlistName.value)
}

function publishAnalysis(target: 'breadth' | 'study_lab', scope: 'full' | 'selection' = 'full') {
  if (!sourceId.value) return
  const selectedSymbols = selectedIds.value
    .map(instrumentId => map.value?.cells.find(cell => cell.instrument_id === instrumentId)?.symbol)
    .filter((symbol): symbol is string => Boolean(symbol))
  emit('publishAnalysis', {
    target,
    sourceId: sourceId.value,
    selectedIds: [...selectedIds.value],
    selectedSymbols,
    scope,
  })
}

const selectedMembers = computed(() => selectedIds.value
  .map(instrumentId => map.value?.cells.find(cell => cell.instrument_id === instrumentId))
  .filter((cell): cell is NonNullable<typeof cell> => Boolean(cell)))
const selectedSymbols = computed(() => selectedMembers.value.map(cell => cell.symbol))

function openSelectedInChart() {
  const member = selectedMembers.value[0]
  if (member) emit('select', member.symbol, member.instrument_id)
}

function compareSelectedInChart() {
  if (selectedSymbols.value.length >= 2) emit('compare', selectedSymbols.value.slice(0, 6))
}

function openSelectedInRatio() {
  if (selectedSymbols.value.length) emit('ratio', selectedSymbols.value.slice(0, 2))
}

function pythonLiteral(value: unknown): string {
  if (value === null) return 'None'
  if (value === true) return 'True'
  if (value === false) return 'False'
  if (typeof value === 'number' && Number.isFinite(value)) return String(value)
  if (typeof value === 'string') return JSON.stringify(value)
  if (Array.isArray(value)) return `[${value.map(item => pythonLiteral(item)).join(', ')}]`
  if (value && typeof value === 'object') {
    return `{${Object.entries(value as Record<string, unknown>).map(([key, item]) => `${JSON.stringify(key)}: ${pythonLiteral(item)}`).join(', ')}}`
  }
  return 'None'
}

function definitionStableKey(name: string) {
  const slug = name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 54) || 'breadth'
  return `market-map-${slug}-${Date.now().toString(36)}`.slice(0, 80)
}

async function saveBreadthDefinition() {
  if (definitionSaving.value || colorMetric.value !== 'breadth' || !definitionName.value || !breadthCondition.value) return
  definitionSaving.value = true
  definitionMessage.value = ''
  definitionError.value = ''
  try {
    const source = [
      `condition = parameters.get('condition', ${pythonLiteral(breadthCondition.value)})`,
      "snapshot = research.breadth_condition(dataset, condition)",
      "history = research.breadth_condition(dataset, condition, True)",
      "output.scalar('current_percentage', snapshot['percentage'] if snapshot['percentage'] is not None else 0)",
      "output.scalar('current_pass_count', snapshot['pass_count'])",
      "output.scalar('current_eligible_count', snapshot['eligible_count'])",
      "output.series('percentage_history', [point['percentage'] for point in history['points']])",
      "output.table('breadth_members', snapshot['rows'])",
      "output.table('breadth_exclusions', snapshot['exclusions'])",
      "output.table('historical_breadth', history['points'])",
    ].join('\n')
    await api.post('/code/assets', {
      stable_key: definitionStableKey(definitionName.value),
      name: definitionName.value,
      kind: 'study',
      initial_version: {
        source,
        output_contract: 'study',
        parameter_schema: {
          properties: {
            condition: { type: 'object' },
            source_id: { type: 'string' },
            period: { type: 'string' },
            timeframe: { type: 'string' },
            adjustment: { type: 'string' },
          },
          required: ['condition', 'source_id'],
        },
        default_parameters: {
          condition: breadthCondition.value,
          source_id: sourceId.value,
          period: period.value,
          timeframe: timeframe.value,
          adjustment: 'split_adjusted',
        },
      },
    })
    await invalidateCodeAssets(queryClient)
    definitionMessage.value = 'Saved immutable Study Lab definition.'
  } catch (cause) {
    definitionError.value = cause instanceof Error ? cause.message : 'Unable to save reusable breadth definition'
  } finally {
    definitionSaving.value = false
  }
}

async function loadSnapshot() {
  const snapshotId = Number(snapshotSelectionId.value)
  if (!Number.isInteger(snapshotId) || snapshotId <= 0) {
    activeSnapshotName.value = ''
    return
  }
  snapshotLoading.value = true
  snapshotError.value = ''
  try {
    const snapshot = await fetchMarketMapSnapshot(snapshotId)
    skipNextSourceRun.value = true
    sourceId.value = snapshot.source_id
    map.value = snapshot.map
    if (['D1', 'W1', 'MN'].includes(snapshot.map.timeframe)) timeframe.value = snapshot.map.timeframe as Timeframe
    areaMetric.value = snapshot.map.area_metric
    areaField.value = snapshot.map.area_field ?? 'avg_volume_30d'
    colorMetric.value = snapshot.map.color_metric
    if (snapshot.map.period_start) startDate.value = snapshot.map.period_start.slice(0, 10)
    if (snapshot.map.period_end) endDate.value = snapshot.map.period_end.slice(0, 10)
    if (snapshot.map.condition) {
      breadthConditionTree.value = snapshot.map.condition as unknown as BreadthConditionNode
      advancedBreadthEditor.value = true
    }
    pythonRunId.value = snapshot.map.python_run_id ?? null
    activeSnapshotName.value = snapshot.name
    snapshotName.value = snapshot.name
    selectedNode.value = null
    selectedIds.value = []
    resetViewport()
  } catch (cause) {
    snapshotError.value = cause instanceof Error ? cause.message : 'Unable to load Market Map snapshot'
  } finally {
    snapshotLoading.value = false
  }
}

async function saveSnapshot() {
  if (!map.value || !snapshotName.value.trim() || snapshotLoading.value) return
  snapshotLoading.value = true
  snapshotError.value = ''
  try {
    const snapshot = await saveMarketMapSnapshot(snapshotName.value.trim(), map.value.cache_key)
    snapshots.value = [snapshot, ...snapshots.value.filter(item => item.id !== snapshot.id)]
    snapshotSelectionId.value = String(snapshot.id)
    activeSnapshotName.value = snapshot.name
    snapshotName.value = snapshot.name
  } catch (cause) {
    snapshotError.value = cause instanceof Error ? cause.message : 'Unable to save Market Map snapshot'
  } finally {
    snapshotLoading.value = false
  }
}

async function deleteSnapshot() {
  const snapshotId = Number(snapshotSelectionId.value)
  if (!Number.isInteger(snapshotId) || snapshotId <= 0 || snapshotLoading.value) return
  snapshotLoading.value = true
  snapshotError.value = ''
  try {
    await deleteMarketMapSnapshot(snapshotId)
    snapshots.value = snapshots.value.filter(item => item.id !== snapshotId)
    snapshotSelectionId.value = ''
    activeSnapshotName.value = ''
    snapshotName.value = ''
  } catch (cause) {
    snapshotError.value = cause instanceof Error ? cause.message : 'Unable to delete Market Map snapshot'
  } finally {
    snapshotLoading.value = false
  }
}

function csvCell(value: unknown): string {
  const text = value == null ? '' : String(value)
  return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text
}

function exportCsv() {
  if (!map.value) return
  const header = ['symbol', 'name', 'sector', 'industry', 'group_path', 'area_value', 'color_value', 'return_value', 'coverage', 'color_coverage', 'area_coverage', 'observation_time', 'warnings']
  const rows = map.value.cells.map(cell => [
    cell.symbol,
    cell.name,
    cell.sector,
    cell.industry,
    cell.group_path.join(' / '),
    cell.area_value,
    cell.color_value,
    cell.return_value,
    cell.coverage,
    cell.color_coverage,
    cell.area_coverage,
    cell.observation_time,
    cell.warnings.map(warning => warning.code).join('|'),
  ])
  const csv = [header, ...rows].map(row => row.map(csvCell).join(',')).join('\n')
  const url = URL.createObjectURL(new Blob([`${csv}\n`], { type: 'text/csv;charset=utf-8' }))
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = `market-map-${map.value.source.source_id.replace(/[^a-z0-9_-]+/gi, '-') || 'universe'}.csv`
  anchor.click()
  URL.revokeObjectURL(url)
}

async function run() {
  if (!componentMounted || (!sourceId.value && !explicitSymbols.value.trim())) return
  if (!explicitSymbols.value.trim() && sourceId.value) {
    const selectedSource = sources.value.find(source => source.source_id === sourceId.value)
    if (selectedSource && !isSourceSelectable(selectedSource)) {
      error.value = `${selectedSource.name} is not current and cannot be used for Market Map analysis.`
      return
    }
  }
  const generation = ++runGeneration
  loading.value = true
  error.value = ''
  map.value = null
  try {
    let requestSourceId = sourceId.value
    if (explicitSymbols.value.trim()) {
      const symbols = [...new Set(explicitSymbols.value.split(/[\s,]+/).map(item => item.trim().toUpperCase()).filter(Boolean))]
      if (symbols.length > 500) throw new Error('Explicit Market Map selections are limited to 500 symbols; save a larger universe as a watchlist.')
      const resolved = await resolveCanonicalSymbols(symbols, 'Explicit symbol')
      const ids = resolved.map(item => item.id)
      if (ids.some(id => id == null)) throw new Error('Every explicit symbol must resolve to a canonical instrument.')
      requestSourceId = `explicit:${ids.join(',')}`
      if (sourceId.value !== requestSourceId) {
        skipNextSourceRun.value = true
        sourceId.value = requestSourceId
      }
    }
    if (!componentMounted || generation !== runGeneration) return
    if (colorMetric.value === 'python' || areaMetric.value === 'python') await resolvePythonRun()
    const nextMap = await fetchMarketMap({ source_id: requestSourceId, group_by: groupBy.value, period: period.value, start: period.value === 'CUSTOM' && startDate.value ? startDate.value : null, end: period.value === 'CUSTOM' && endDate.value ? `${endDate.value}T23:59:59Z` : null, area_metric: areaMetric.value, area_field: areaMetric.value === 'field' ? areaField.value : null, color_metric: colorMetric.value, condition: colorMetric.value === 'breadth' ? breadthCondition.value : null, python_run_id: colorMetric.value === 'python' || areaMetric.value === 'python' ? pythonRunId.value : null, reference_symbol: (colorMetric.value === 'relative_return' || referenceNeeded.value) && !referenceSourceId.value ? referenceSymbol.value.toUpperCase() : null, reference_source_id: (colorMetric.value === 'relative_return' || referenceNeeded.value) && referenceSourceId.value ? referenceSourceId.value : null, timeframe: timeframe.value, adjusted: true })
    if (!componentMounted || generation !== runGeneration) return
    map.value = nextMap
    snapshotSelectionId.value = ''
    activeSnapshotName.value = ''
    selectedNode.value = null
    selectedIds.value = []
    resetViewport()
  } catch (cause) {
    if (!componentMounted || generation !== runGeneration) return
    error.value = cause instanceof Error ? cause.message : 'Unable to load Market Map'
  } finally {
    if (generation === runGeneration) loading.value = false
  }
}
function persist() {
  if (!componentMounted) return
  emit('configuration', { ...props.configuration, source_id: sourceId.value, explicit_symbols: explicitSymbols.value || null, group_by: groupBy.value, sort_by: sortBy.value, period: period.value, timeframe: timeframe.value, start_date: period.value === 'CUSTOM' ? startDate.value : null, end_date: period.value === 'CUSTOM' ? endDate.value : null, area_metric: areaMetric.value, area_field: areaMetric.value === 'field' ? areaField.value : null, color_metric: colorMetric.value, condition: colorMetric.value === 'breadth' ? breadthCondition.value : null, advanced_breadth_editor: advancedBreadthEditor.value, python_code_version_id: pythonCodeVersionId.value, python_run_id: pythonRunId.value, breadth_condition_kind: breadthConditionKind.value, breadth_condition_period: breadthConditionPeriod.value, breadth_condition_threshold: breadthConditionThreshold.value, breadth_event_type: breadthEventType.value, breadth_event_lookback: breadthEventLookback.value, reference_symbol: referenceSymbol.value, reference_source_id: referenceSourceId.value, definition_name: definitionName.value })
}
watch([sourceId, explicitSymbols, groupBy, sortBy, period, timeframe, startDate, endDate, areaMetric, areaField, colorMetric, referenceSymbol, referenceSourceId, pythonCodeVersionId, pythonRunId, breadthConditionKind, breadthConditionPeriod, breadthConditionThreshold, breadthEventType, breadthEventLookback, advancedBreadthEditor, breadthConditionTree, definitionName], persist, { deep: true })
watch(timeframe, () => {
  clearHistoryPoll()
  historyStatus.value = null
  historyRun.value = null
  historyRefreshMessage.value = ''
  historyError.value = ''
  if (sourceId.value) void loadHistoryStatus()
})
watch(sourceId, () => {
  clearHistoryPoll()
  historyStatus.value = null
  historyRun.value = null
  historyRefreshMessage.value = ''
  historyError.value = ''
  if (skipNextSourceRun.value) {
    skipNextSourceRun.value = false
    if (sourceId.value) void loadHistoryStatus()
    return
  }
  if (sourceId.value) {
    void run()
    void loadHistoryStatus()
  }
})
watch(snapshotSelectionId, () => { void loadSnapshot() })
onMounted(async () => {
  componentMounted = true
  window.addEventListener('resize', scheduleCanvasDraw)
  await userSettingsStore.loadSettings()
  if (!componentMounted) return
  if (!sources.value.length) await watchlistStore.loadWatchlistSources()
  if (!componentMounted) return
  if (!watchlistStore.watchlists.length) await watchlistStore.loadWatchlists()
  if (!componentMounted) return
  await loadPythonAssets()
  if (!componentMounted) return
  try {
    snapshots.value = await fetchMarketMapSnapshots()
  } catch (cause) {
    if (!componentMounted) return
    snapshotError.value = cause instanceof Error ? cause.message : 'Unable to load Market Map snapshots'
  }
  if (!componentMounted) return
  if (!sourceId.value && !explicitSymbols.value.trim()) {
    const preferred = sources.value.find((item: WatchlistSource) => isSourceSelectable(item) && (item.source_kind === 'index_membership' || item.source_kind === 'etf_holdings'))
      ?? sources.value.find((item: WatchlistSource) => isSourceSelectable(item))
    if (preferred) sourceId.value = preferred.source_id
  }
  if (!componentMounted) return
  if (sourceId.value || explicitSymbols.value.trim()) await run()
  if (!componentMounted) return
  if (sourceId.value) await loadHistoryStatus()
})
onUnmounted(() => {
  componentMounted = false
  runGeneration += 1
  clearHistoryPoll()
  window.removeEventListener('resize', scheduleCanvasDraw)
  if (canvasDrawFrame != null) window.cancelAnimationFrame(canvasDrawFrame)
  canvasDrawFrame = null
})
</script>

<style scoped>
.market-map-tool { display: flex; flex-direction: column; gap: 8px; min-height: 100%; background: #11161d; color: #d4d9e2; font-size: 12px; }
.market-map-tool__controls { display: flex; flex-wrap: wrap; gap: 6px; align-items: end; padding: 8px; background: #1b222c; border-bottom: 1px solid #303a48; }
.market-map-tool__source-bootstrap { display: flex; flex-wrap: wrap; gap: 4px; align-items: end; padding: 2px 4px; border: 1px solid #34434e; background: #141b20; }
.market-map-tool__source-bootstrap label { display: flex; flex-direction: column; gap: 3px; color: #8e9bad; font-size: 10px; text-transform: uppercase; letter-spacing: .04em; }
.market-map-tool__source-bootstrap input { width: 74px; }
.market-map-tool__source-bootstrap span { max-width: 260px; }
.market-map-tool__controls label { display: flex; flex-direction: column; gap: 3px; color: #8e9bad; font-size: 10px; text-transform: uppercase; letter-spacing: .04em; }
.market-map-tool__explicit-hint { align-self: end; max-width: 260px; padding-bottom: 6px; color: #f7d87b; font-size: 10px; }
.market-map-tool select, .market-map-tool input, .market-map-tool button { border: 1px solid #3c4858; background: #151c25; color: #d4d9e2; border-radius: 2px; padding: 5px 7px; font: inherit; }
.market-map-tool__source-actions { display: flex; gap: 4px; align-items: end; padding-bottom: 0; }
.market-map-tool__source-kind { margin-right: auto; color: #80909d; font-size: 10px; }
.market-map-tool__source-state { color: #f7d87b; font-size: 10px; }
.market-map-tool__source-state--warning { max-width: 420px; color: #ff9a9a; }
.market-map-tool__source-actions button { cursor: pointer; min-width: 58px; }
.market-map-tool__source-actions button[aria-pressed="true"] { border-color: #f7d87b; color: #f7d87b; }
.market-map-tool__run { background: #2d8cff !important; border-color: #2d8cff !important; color: white !important; cursor: pointer; }
.market-map-tool__run:disabled { opacity: .55; cursor: default; }
.market-map-tool__status { margin: 0; padding: 6px 9px; color: #aeb8c7; }
.market-map-tool__status--error { color: #ff9898; }
.market-map-tool__summary, .market-map-tool__nodes, .market-map-tool__breadcrumbs, .market-map-tool__viewport-controls, .market-map-tool__source-analysis-actions { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; padding: 0 8px; color: #9eabbb; }
.market-map-tool__history-status { display: flex; gap: 7px; align-items: center; flex-wrap: wrap; padding: 3px 8px; color: #9eabbb; border-top: 1px solid #303a48; border-bottom: 1px solid #303a48; background: #151c25; }
.market-map-tool__history-status strong { color: #dce5ee; }
.market-map-tool__history-status button { cursor: pointer; }
.market-map-tool__history-status button:disabled { cursor: default; opacity: .55; }
.market-map-tool__history-status--ready { color: #82e2ac; }.market-map-tool__history-status--partial,.market-map-tool__history-status--pending { color: #f7d87b; }.market-map-tool__history-status--fetching { color: #70b4ff; }.market-map-tool__history-status--failed,.market-map-tool__history-status--unavailable { color: #ff9a9a; }
.market-map-tool__source-analysis-actions { padding-top: 2px; padding-bottom: 2px; }
.market-map-tool__source-analysis-actions button, .market-map-tool__definition-actions button { cursor: pointer; }
.market-map-tool__definition-actions { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; padding: 2px 8px; }
.market-map-tool__summary span:first-child { color: #f1f4f8; font-weight: 700; }
.market-map-tool__nodes button { cursor: pointer; }
.market-map-tool__nodes button.active { border-color: #70b4ff; color: #fff; }
.market-map-tool__nodes small { color: #8e9bad; }
.market-map-tool__breadcrumbs { gap: 5px; color: #8e9bad; }
.market-map-tool__breadcrumbs button { padding: 3px 5px; cursor: pointer; }
.market-map-tool__breadcrumbs button.active { border-color: #70b4ff; color: #fff; }
.market-map-tool__viewport-controls { justify-content: flex-end; }
.market-map-tool__viewport-controls button { min-width: 26px; padding: 3px 6px; cursor: pointer; }
.market-map-tool__viewport-controls button:disabled { cursor: default; opacity: .5; }
.market-map-tool__viewport-controls small { margin-left: auto; color: #7d8a9b; }
.market-map-tool__canvas-access { display: flex; gap: 8px; align-items: end; flex-wrap: wrap; padding: 3px 8px; color: #8e9bad; }
.market-map-tool__canvas-access label { display: flex; flex-direction: column; gap: 3px; font-size: 10px; text-transform: uppercase; letter-spacing: .04em; }
.market-map-tool__canvas-access input { min-width: 180px; }
.market-map-tool__canvas-access small { padding-bottom: 6px; }
.market-map-tool__selection-actions { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; padding: 4px 8px; border-top: 1px solid #303a48; border-bottom: 1px solid #303a48; background: #18212c; }
.market-map-tool__selection-actions strong { color: #f7d87b; }
.market-map-tool__selection-actions button { cursor: pointer; }
.market-map-tool__selection-actions button:disabled { cursor: default; opacity: .55; }
.market-map-tool__selection-actions span[role="status"] { color: #82e2ac; }
.market-map-tool__legend { display: flex; gap: 8px; align-items: center; padding: 2px 8px; color: #aeb8c7; text-transform: capitalize; }
.market-map-tool__legend--negative { color: #ff9a9a; font-weight: 800; }.market-map-tool__legend--positive { color: #82e2ac; font-weight: 800; }.market-map-tool__legend__coverage { margin-left: auto; text-transform: none; }
.market-map-tool__tiles { position: relative; min-height: 300px; margin: 0 8px 8px; overflow: hidden; border: 1px solid #303a48; background: #0d1218; cursor: grab; touch-action: none; }
.market-map-tool__tiles:active { cursor: grabbing; }
.market-map-tool__canvas { position: absolute; inset: 0; transform-origin: top left; transition: transform 120ms ease-out; }
.market-map-tool__group-frame { position: absolute; z-index: 3; box-sizing: border-box; display: flex; align-items: flex-start; gap: 5px; padding: 4px 5px; overflow: hidden; border: 1px solid #90a2b5aa; color: #d4d9e2; font-size: 10px; pointer-events: none; }
.market-map-tool__group-frame[data-group-level="1"] { border-color: #90a2b577; color: #c2ccd8; }
.market-map-tool__group-frame strong { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.market-map-tool__group-frame small { flex: 0 0 auto; color: #aeb8c7; }
.market-map-tool__canvas-map { position: absolute; inset: 0; z-index: 0; display: block; width: 100%; height: 100%; cursor: pointer; }
.market-map-tool__canvas-hint { position: absolute; right: 6px; bottom: 5px; z-index: 1; padding: 2px 4px; color: #d4d9e2; background: #11161dcc; pointer-events: none; }
.market-map-tool__tile { position: absolute; z-index: 2; display: flex; min-width: 28px; min-height: 28px; flex-direction: column; justify-content: center; align-items: center; gap: 3px; cursor: pointer; color: #fff !important; overflow: hidden; border-radius: 0 !important; }
.market-map-tool__tile strong { font-size: 16px; }
.market-map-tool__tile small { max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; opacity: .75; }
.market-map-tool__tile--positive { background: #207d56 !important; }
.market-map-tool__tile--negative { background: #843f50 !important; }
.market-map-tool__tile--unknown { background: #3c4652 !important; }
.market-map-tool__tile--selected { outline: 2px solid #f7d87b; outline-offset: -2px; z-index: 2; }
.market-map-tool__hover { position: absolute; right: 12px; bottom: 12px; z-index: 5; display: flex; flex-direction: column; gap: 2px; max-width: 300px; padding: 8px 10px; border: 1px solid #60758d; background: #18222e; box-shadow: 0 4px 18px #0008; }
</style>
