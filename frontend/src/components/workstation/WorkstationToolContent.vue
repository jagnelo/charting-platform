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
      :timeframe="activeTimeframe"
      :rows="benchmarkRows"
      :selected="activeSymbol"
      :visible-column-keys="configuredColumnKeys"
      :filter-text="configuredFilterText"
      :condition-screener-id="configuredConditionScreenerId"
      :condition-filter-mode="configuredConditionFilterMode"
      :pinned-boolean-keys="configuredPinnedBooleanKeys"
      :column-groups="configuredColumnGroups"
      :stacked-column-keys="configuredStackedColumnKeys"
      :indicator-columns="configuredIndicatorColumns"
      :indicator-values="indicatorValues"
      :indicator-warnings="indicatorWarnings"
      :condition-columns="configuredConditionColumns"
      :condition-values="conditionValues"
      :drop-error="conditionDropError"
      :python-columns="configuredPythonColumns"
      :python-condition="configuredPythonCondition"
      :membership-targets="personalWatchlistTargets"
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
      @plot-drop="addPlotColumn"
      @condition-drop="addConditionColumn"
      />
    </div>
    <VirtualWatchlistTool
      v-else-if="tool.instance_key === 'sector-list'"
      label="Relative to SPY"
      :timeframe="activeTimeframe"
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
      :indicator-columns="configuredIndicatorColumns"
      :indicator-values="indicatorValues"
      :indicator-warnings="indicatorWarnings"
      :condition-columns="configuredConditionColumns"
      :condition-values="conditionValues"
      :drop-error="conditionDropError"
      :python-columns="configuredPythonColumns"
      :python-condition="configuredPythonCondition"
      :membership-targets="personalWatchlistTargets"
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
      @plot-drop="addPlotColumn"
      @condition-drop="addConditionColumn"
    />
    <div v-else-if="tool.tool_type === 'watchlist' && tool.configuration.personal === true" class="personal-watchlist-tool">
      <div class="personal-watchlist-tool__controls">
        <label>WatchList
          <select :value="flaggedItemsSelected ? 'flagged' : selectedComboKey ? `combo:${selectedComboKey}` : selectedPersonalWatchlistId == null ? '' : String(selectedPersonalWatchlistId)" aria-label="Personal watchlist" @change="selectPersonalWatchlist(($event.target as HTMLSelectElement).value)">
            <option value="flagged">Flagged Items</option>
            <option value="">Select a personal watchlist</option>
            <option v-for="watchlist in personalWatchlists" :key="watchlist.id" :value="String(watchlist.id)">{{ watchlist.name }}{{ watchlist.is_locked ? ' · Locked' : '' }}</option>
            <option v-for="combo in comboLists" :key="`combo:${combo.stable_key}`" :value="`combo:${combo.stable_key}`">Combo · {{ combo.name }}</option>
          </select>
        </label>
        <input v-model="personalListNameDraft" aria-label="Personal watchlist name" placeholder="List name" :disabled="flaggedItemsSelected || Boolean(selectedCombo)" @keydown.enter.prevent="selectedPersonalWatchlist ? renamePersonalWatchlist() : createPersonalWatchlist()" />
        <button type="button" :disabled="flaggedItemsSelected || Boolean(selectedCombo) || !personalListNameDraft.trim() || personalListBusy" @click="createPersonalWatchlist">New</button>
        <button type="button" :disabled="flaggedItemsSelected || Boolean(selectedCombo) || !selectedPersonalWatchlist || selectedPersonalWatchlist.is_locked || selectedPersonalWatchlist.is_managed || !personalListNameDraft.trim() || personalListBusy" @click="renamePersonalWatchlist">Rename</button>
        <button type="button" :disabled="flaggedItemsSelected || Boolean(selectedCombo) || !selectedPersonalWatchlist || personalListBusy" @click="copyPersonalWatchlist">Copy</button>
        <button type="button" :disabled="flaggedItemsSelected || Boolean(selectedCombo) || !selectedPersonalWatchlist || selectedPersonalWatchlist.is_locked || selectedPersonalWatchlist.is_managed || personalListBusy" @click="deletePersonalWatchlist">Delete</button>
        <input v-model="personalSymbolDraft" aria-label="Add symbol to personal watchlist" placeholder="Add symbol" :disabled="flaggedItemsSelected || Boolean(selectedCombo) || !selectedPersonalWatchlist || selectedPersonalWatchlist.is_locked" @keydown.enter.prevent="addPersonalSymbol" />
        <button type="button" :disabled="flaggedItemsSelected || Boolean(selectedCombo) || !personalSymbolDraft.trim() || !selectedPersonalWatchlist || selectedPersonalWatchlist.is_locked || personalWatchlistBusy" @click="addPersonalSymbol">{{ personalWatchlistBusy ? 'Adding…' : 'Add' }}</button>
        <span v-if="flaggedItemsSelected">{{ flaggedWatchlistRows.length }} flagged symbols · select a row to inspect its source list</span>
        <span v-else-if="selectedCombo">{{ comboWatchlistRows.length }} symbols · {{ selectedCombo.name }} · union/intersection/exclusion</span>
        <span v-else-if="selectedPersonalWatchlist">{{ selectedPersonalWatchlist.items.length }} symbols · {{ selectedPersonalWatchlist.is_locked ? 'Locked' : 'Drag rows to reorder' }}</span>
        <span v-else-if="watchlistStore.loading">Loading watchlists…</span>
        <span v-else>No personal watchlists available.</span>
        <span v-if="personalWatchlistError" class="personal-watchlist-tool__error">{{ personalWatchlistError }}</span>
        <section class="combo-editor" aria-label="Combo list editor">
          <header>Combo list</header>
          <input v-model="comboNameDraft" aria-label="Combo list name" placeholder="Name" :disabled="flaggedItemsSelected" />
          <label>Union
            <select v-model="comboUnionIds" multiple aria-label="Combo union lists" :disabled="flaggedItemsSelected">
              <option v-for="watchlist in personalWatchlists" :key="`union-${watchlist.id}`" :value="watchlist.id">{{ watchlist.name }}</option>
            </select>
          </label>
          <label>Intersection
            <select v-model="comboIntersectionIds" multiple aria-label="Combo intersection lists" :disabled="flaggedItemsSelected">
              <option v-for="watchlist in personalWatchlists" :key="`intersection-${watchlist.id}`" :value="watchlist.id">{{ watchlist.name }}</option>
            </select>
          </label>
          <label>Exclude
            <select v-model="comboExcludeIds" multiple aria-label="Combo exclusion lists" :disabled="flaggedItemsSelected">
              <option v-for="watchlist in personalWatchlists" :key="`exclude-${watchlist.id}`" :value="watchlist.id">{{ watchlist.name }}</option>
            </select>
          </label>
          <button type="button" :disabled="flaggedItemsSelected || !comboNameDraft.trim() || (!comboUnionIds.length && !comboIntersectionIds.length) || comboBusy" @click="saveComboList">{{ selectedCombo ? 'Save combo' : 'New combo' }}</button>
          <button v-if="selectedCombo" type="button" :disabled="comboBusy" @click="deleteComboList">Delete combo</button>
          <span v-if="comboError" class="personal-watchlist-tool__error">{{ comboError }}</span>
        </section>
      </div>
      <VirtualWatchlistTool
        v-if="selectedPersonalWatchlist || flaggedItemsSelected || selectedCombo"
        :timeframe="activeTimeframe"
        :label="flaggedItemsSelected ? 'Flagged Items' : selectedCombo?.name ?? selectedPersonalWatchlist?.name ?? 'WatchList'"
        :rows="flaggedItemsSelected ? flaggedWatchlistRows : selectedCombo ? comboWatchlistRows : personalWatchlistRows"
        :selected="activeSymbol"
        :columns="personalWatchlistColumns"
        :visible-column-keys="configuredColumnKeys"
        :filter-text="configuredFilterText"
        :condition-screener-id="configuredConditionScreenerId"
        :condition-filter-mode="configuredConditionFilterMode"
        :pinned-boolean-keys="configuredPinnedBooleanKeys"
        :column-groups="configuredColumnGroups"
        :stacked-column-keys="configuredStackedColumnKeys"
        :indicator-columns="configuredIndicatorColumns"
        :indicator-values="indicatorValues"
        :indicator-warnings="indicatorWarnings"
        :condition-columns="configuredConditionColumns"
        :condition-values="conditionValues"
        :drop-error="conditionDropError"
        :python-columns="configuredPythonColumns"
        :python-condition="configuredPythonCondition"
        :membership-targets="personalWatchlistTargets"
        :source-watchlist-id="selectedPersonalWatchlist?.id"
        :reorderable="Boolean(selectedPersonalWatchlist && !selectedPersonalWatchlist.is_locked && !selectedPersonalWatchlist.is_managed)"
        :allow-remove="Boolean(selectedPersonalWatchlist && !selectedPersonalWatchlist.is_locked && !selectedPersonalWatchlist.is_managed)"
        @select="selectSymbol($event.symbol, $event.instrumentId)"
        @reorder="selectedPersonalWatchlist && emit('reorder', selectedPersonalWatchlist.id, $event)"
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
        @plot-drop="addPlotColumn"
        @condition-drop="addConditionColumn"
      />
    </div>
    <VirtualWatchlistTool
      v-else-if="tool.tool_type === 'watchlist'"
      :label="tool.title || 'WatchList'"
      :timeframe="activeTimeframe"
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
      :indicator-columns="configuredIndicatorColumns"
      :indicator-values="indicatorValues"
        :indicator-warnings="indicatorWarnings"
        :condition-columns="configuredConditionColumns"
        :condition-values="conditionValues"
        :drop-error="conditionDropError"
      :python-columns="configuredPythonColumns"
      :python-condition="configuredPythonCondition"
      :membership-targets="personalWatchlistTargets"
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
        @plot-drop="addPlotColumn"
        @condition-drop="addConditionColumn"
    />
    <div v-else-if="ratioExpression" class="analysis">
      <RatioUPlot :symbol="ratioExpression.numerator" :benchmarks="[ratioExpression.denominator]" :timeframe="activeTimeframe" :as-of="typeof tool.configuration.as_of === 'string' ? tool.configuration.as_of : null" :linked-timestamp="workspaceStore.timestampForLinkGroup(tool.link_group)" @cursor-timestamp="workspaceStore.publishTimestamp($event, tool.link_group, tool.instance_key)" @configuration="emit('configuration', tool.instance_key, { ...tool.configuration, ...$event })" />
    </div>
    <div v-else-if="tool.tool_type === 'chart' && tool.instance_key !== 'ratio-chart'" class="chart-tool">
      <DrawingToolbar class="chart-tool__drawing-toolbar" />
        <div class="chart-tool__surface">
        <ChartTemplateControl class="chart-tool__templates" :configuration="liveChartConfiguration" :indicator-configs="chartStore.indicators" @apply="applyChartTemplate" />
        <ChartPlotLibrary class="chart-tool__plots" :source-window-key="tool.instance_key" :link-group="tool.link_group" :python-plots="configuredPythonPlots" @update:python-plots="updatePythonPlots" />
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
          :python-series="pythonSeries"
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
            :timeframe="activeTimeframe"
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
            :indicator-columns="configuredIndicatorColumns"
            :indicator-values="indicatorValues"
            :indicator-warnings="indicatorWarnings"
            :condition-columns="configuredConditionColumns"
            :condition-values="conditionValues"
            :drop-error="conditionDropError"
            :python-columns="configuredPythonColumns"
            :python-condition="configuredPythonCondition"
            :membership-targets="personalWatchlistTargets"
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
            @plot-drop="addPlotColumn"
            @condition-drop="addConditionColumn"
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
      :timeframe="activeTimeframe"
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
      :indicator-columns="configuredIndicatorColumns"
      :indicator-values="indicatorValues"
      :indicator-warnings="indicatorWarnings"
      :condition-columns="configuredConditionColumns"
      :condition-values="conditionValues"
      :drop-error="conditionDropError"
      :python-columns="configuredPythonColumns"
      :python-condition="configuredPythonCondition"
      :membership-targets="personalWatchlistTargets"
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
      @plot-drop="addPlotColumn"
      @condition-drop="addConditionColumn"
    />
    <div v-else-if="tool.instance_key === 'ratio-chart'" class="analysis">
      <RatioUPlot :symbol="activeSymbol" :benchmarks="ratioBenchmarks" :timeframe="activeTimeframe" :as-of="typeof tool.configuration.as_of === 'string' ? tool.configuration.as_of : null" :linked-timestamp="workspaceStore.timestampForLinkGroup(tool.link_group)" @cursor-timestamp="workspaceStore.publishTimestamp($event, tool.link_group, tool.instance_key)" @configuration="emit('configuration', tool.instance_key, { ...tool.configuration, ...$event })" />
    </div>
    <div v-else-if="tool.instance_key === 'breadth-summary' || tool.tool_type === 'breadth'" class="breadth-tool">
      <label class="breadth-tool__universe">Universe <select :value="breadthGroupKey" aria-label="Breadth universe" @change="setBreadthGroup(($event.target as HTMLSelectElement).value)"><option value="sp500-sectors">S&amp;P 500 sectors</option><option value="us-benchmarks">US benchmarks</option></select> Timeframe <select :value="breadthTimeframe" aria-label="Breadth timeframe" @change="setBreadthConfiguration({ timeframe: ($event.target as HTMLSelectElement).value })"><option value="D1">Daily</option><option value="W1">Weekly</option><option value="MN">Monthly</option></select> Lookback <input :value="breadthLookback" aria-label="Breadth new high low lookback" type="number" min="2" max="252" @change="setBreadthConfiguration({ new_high_lookback: Number(($event.target as HTMLInputElement).value) })" /> <label><input type="checkbox" :checked="breadthAdjusted" aria-label="Breadth split adjusted" @change="setBreadthConfiguration({ adjusted: ($event.target as HTMLInputElement).checked })" /> Adjusted</label></label>
      <div class="metrics">
        <template v-for="period in ['ma20', 'ma50', 'ma200']" :key="period">
          <span>Above {{ period.slice(2) }} MA</span>
          <span class="breadth-tool__actions">
            <button type="button" :class="{ 'breadth-tool__action--active': breadthDrilldown?.key === period && breadthDrilldown.state === 'above' }" @click="setBreadthDrilldown(period, 'above')">{{ breadthMetric(period) }}</button>
            <button type="button" :class="{ 'breadth-tool__action--active': breadthDrilldown?.key === period && breadthDrilldown.state === 'below' }" @click="setBreadthDrilldown(period, 'below')">Below {{ breadthBelowCount(period) }}</button>
          </span>
        </template>
        <span>Coverage</span><b>{{ breadthCoverage }}</b>
        <span>Near 52W high / low</span><span class="breadth-tool__actions"><button type="button" @click="setBreadthDrilldown('near_52w_high', 'above')">High {{ breadthMetric('near_52w_high') }}</button><button type="button" @click="setBreadthDrilldown('near_52w_low', 'above')">Low {{ breadthMetric('near_52w_low') }}</button></span>
        <span>New high / low ({{ breadthLookback }})</span><span class="breadth-tool__actions"><button type="button" @click="setBreadthDrilldown('new_high', 'above')">High {{ breadthMetric('new_high') }}</button><button type="button" @click="setBreadthDrilldown('new_low', 'above')">Low {{ breadthMetric('new_low') }}</button></span>
        <span>Uptrend / downtrend</span><span class="breadth-tool__actions"><button type="button" @click="setBreadthDrilldown('uptrend', 'above')">Up {{ breadthMetric('uptrend') }}</button><button type="button" @click="setBreadthDrilldown('downtrend', 'above')">Down {{ breadthMetric('downtrend') }}</button></span>
        <span>Avg distance from MA20 / MA50</span><b>{{ breadthAdvanced('distance_from_ma', 'ma20') }} / {{ breadthAdvanced('distance_from_ma', 'ma50') }}</b>
      </div>
      <small class="breadth-tool__coverage-detail">Metric coverage: {{ breadthMetricCoverage }}</small>
      <div v-if="breadthDrilldown" class="breadth-tool__drilldown" aria-label="Breadth member drilldown">
        <header><strong>{{ breadthDrilldown.state === 'above' ? 'Passing' : 'Failing' }} {{ breadthDrilldownLabel(breadthDrilldown.key) }} members</strong><span><button type="button" :class="{ 'breadth-tool__action--active': breadthDrilldown.state === 'above' }" @click="setBreadthDrilldown(breadthDrilldown.key, 'above')">Pass</button><button type="button" :class="{ 'breadth-tool__action--active': breadthDrilldown.state === 'below' }" @click="setBreadthDrilldown(breadthDrilldown.key, 'below')">Fail</button><button type="button" @click="breadthDrilldown = null">Close</button></span></header>
        <button v-for="row in breadthDrilldownRows" :key="row.symbol" type="button" @click="emit('select', row.symbol)"><strong>{{ row.symbol }}</strong><span>{{ row.name }}</span></button>
        <small v-if="!breadthDrilldownRows.length">No locally evaluated members are available.</small>
      </div>
      <BreadthHistoryUPlot :history="breadthHistory" />
    </div>
    <RelativeRotationTool v-else-if="tool.instance_key === 'relative-rotation' || tool.tool_type === 'relative_rotation'" :configuration="tool.configuration" @select="selectSymbol($event)" @configuration="emit('configuration', tool.instance_key, $event)" />
    <div v-else-if="tool.instance_key === 'technical-summary' || tool.tool_type === 'technical_summary'" class="metrics">
      <span>RSI(14)</span><b>{{ formatNumber(technical?.rsi14) }}</b>
      <span>20 / 50 / 200 MA</span><b>{{ technicalMAs }}</b>
      <span>52-week position</span><b>{{ formatPercent(technical?.position_52w) }}</b>
      <span>Volume ratio (50)</span><b>{{ formatRatio(technical?.volume_ratio_50) }}</b>
    </div>
    <CoverageSummaryTool v-else-if="tool.instance_key === 'coverage-summary' || tool.tool_type === 'coverage'" :symbol="activeSymbol" :configuration="tool.configuration" @configuration="emit('configuration', tool.instance_key, $event)" />
    <InstrumentNoteTool v-else-if="tool.tool_type === 'notes'" :instrument-id="chartStore.instrument?.id" :symbol="activeSymbol" />
    <InstrumentAlertsTool v-else-if="tool.tool_type === 'alerts'" :instrument-id="chartStore.instrument?.id" :symbol="activeSymbol" />
    <InstrumentInfoPanel v-else-if="tool.tool_type === 'report'" class="instrument-report" :instrument="chartStore.instrument" :current-price="currentPrice" :session-high="currentSessionHigh" :session-low="currentSessionLow" @select="selectSymbol($event)" />
    <EasyScanTool v-else-if="tool.tool_type === 'scan'" :source-window-key="tool.instance_key" />
    <MarketGaugeTool v-else-if="tool.tool_type === 'gauge'" />
    <StudyLabTool v-else-if="tool.tool_type === 'study_lab'" :active-symbol="activeSymbol" :configuration="tool.configuration" @configuration="emit('configuration', tool.instance_key, $event)" @occurrence="emit('occurrence', $event.symbol, $event.timestamp)" />
    <ResearchResultsTool v-else-if="tool.tool_type === 'research_results'" @occurrence="emit('occurrence', $event.symbol, $event.timestamp)" />
    <CodeLibraryTool v-else-if="tool.tool_type === 'code_library'" />
    <UnknownToolRecovery v-else :tool="tool" />
  </ToolWindow>
</template>

<script setup lang="ts">
import { computed, onMounted, provide, ref, watch } from 'vue'
import { useQueryClient } from '@tanstack/vue-query'
import { api } from '@/lib/api'
import UPlotChart from '@/components/chart/UPlotChart.vue'
import DrawingToolbar from '@/components/chart/DrawingToolbar.vue'
import ChartTemplateControl from './ChartTemplateControl.vue'
import ChartPlotLibrary from './ChartPlotLibrary.vue'
import { usePanelStore } from '@/stores/chart'
import { useDrawingsStore } from '@/stores/drawings'
import { useAlertsStore } from '@/stores/alerts'
import { useWorkspaceStore, type GroupSnapshotRow, type LinkGroup, type WorkspaceWindowState } from '@/stores/workspace'
import { useWatchlistStore } from '@/stores/watchlist'
import type { Watchlist } from '@/types'
import ToolWindow from './ToolWindow.vue'
import VirtualWatchlistTool, { type WatchlistColumn, type WatchlistRow } from './VirtualWatchlistTool.vue'
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
import CodeLibraryTool from './CodeLibraryTool.vue'
import CoverageSummaryTool from './CoverageSummaryTool.vue'
import { calendarYearKeys } from '@/lib/workstation/calendarYears'
import { buildNormalizedComparisonSeries, type ComparisonTarget } from '@/lib/workstation/comparison'
import { ensureKnownInstrumentSymbol } from '@/lib/instruments'
import { INDICATOR_BY_TYPE } from '@/lib/indicators/catalog'
import { buildFlaggedWatchlistRows } from '@/lib/workstation/flagged-watchlist'
import { buildComboWatchlistRows, type ComboListDefinition } from '@/lib/workstation/combo-lists'
import { indicatorColumnFromPlot, type ChartPlotDragPayload, type TechnicalConditionDragPayload } from '@/lib/workstation/plotDrag'
import { CHART_BAR_TYPES, type ChartBarType, type ChartComparisonSeries, type ChartPythonSeries, type IndicatorConfig, type OHLCVBar, type Timeframe } from '@/types'

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
const queryClient = useQueryClient()
const configuredWatchlistId = props.tool.configuration.watchlist_id
const flaggedItemsSelected = ref(configuredWatchlistId === 'flagged')
const configuredComboKey = typeof configuredWatchlistId === 'string' && configuredWatchlistId.startsWith('combo:') ? configuredWatchlistId.slice(6) : null
const selectedComboKey = ref<string | null>(configuredComboKey)
const selectedPersonalWatchlistId = ref<number | null>(typeof configuredWatchlistId === 'number' ? configuredWatchlistId : null)
const personalWatchlists = computed(() => watchlistStore.watchlists.filter(watchlist => !watchlist.is_managed))
const comboLists = ref<ComboListDefinition[]>([])
const comboNameDraft = ref('')
const comboUnionIds = ref<number[]>([])
const comboIntersectionIds = ref<number[]>([])
const comboExcludeIds = ref<number[]>([])
const comboBusy = ref(false)
const comboError = ref('')
const selectedCombo = computed(() => comboLists.value.find(combo => combo.stable_key === selectedComboKey.value) ?? null)
const personalWatchlistTargets = computed(() => personalWatchlists.value.map(watchlist => ({
  id: watchlist.id,
  name: watchlist.name,
  locked: watchlist.is_locked,
  instrumentIds: watchlist.items.map(item => item.instrument_id),
})))
const selectedPersonalWatchlist = computed<Watchlist | null>(() => personalWatchlists.value.find(watchlist => watchlist.id === selectedPersonalWatchlistId.value) ?? null)
const personalWatchlistRows = computed(() => (selectedPersonalWatchlist.value?.items ?? []).map(item => ({
  itemId: item.id,
  sourceWatchlistId: selectedPersonalWatchlist.value?.id,
  instrumentId: item.instrument_id,
  symbol: item.symbol ?? `#${item.instrument_id}`,
  name: item.name ?? item.symbol ?? `Instrument ${item.instrument_id}`,
  flagged: item.flagged === true,
  values: {
    last: watchlistStore.priceMap[item.symbol ?? '']?.close ?? null,
    change: watchlistStore.priceMap[item.symbol ?? '']?.pct ?? null,
  },
})))
const flaggedWatchlistRows = computed(() => buildFlaggedWatchlistRows(personalWatchlists.value, watchlistStore.priceMap))
const comboWatchlistRows = computed(() => selectedCombo.value
  ? buildComboWatchlistRows(watchlistStore.watchlists, selectedCombo.value, watchlistStore.priceMap)
  : [])
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
  flaggedItemsSelected.value = raw === 'flagged'
  selectedComboKey.value = raw.startsWith('combo:') ? raw.slice(6) : null
  const id = Number(raw)
  selectedPersonalWatchlistId.value = Number.isInteger(id) && id > 0 ? id : null
  personalListNameDraft.value = selectedPersonalWatchlist.value?.name ?? ''
  comboError.value = ''
  hydrateSelectedCombo()
  emit('configuration', props.tool.instance_key, { ...props.tool.configuration, watchlist_id: flaggedItemsSelected.value ? 'flagged' : selectedComboKey.value ? `combo:${selectedComboKey.value}` : selectedPersonalWatchlistId.value })
}

function hydrateSelectedCombo() {
  const payload = selectedCombo.value?.payload ?? {}
  comboNameDraft.value = selectedCombo.value?.name ?? ''
  comboUnionIds.value = [...(payload.union_watchlist_ids ?? [])]
  comboIntersectionIds.value = [...(payload.intersection_watchlist_ids ?? [])]
  comboExcludeIds.value = [...(payload.exclude_watchlist_ids ?? [])]
}

async function loadComboLists() {
  try {
    comboLists.value = await api.get<ComboListDefinition[]>('/workspaces/library/items', { kind: 'combo_list' })
    hydrateSelectedCombo()
  } catch (cause: any) {
    comboError.value = cause?.message ?? 'Unable to load combo lists'
  }
}

async function saveComboList() {
  const name = comboNameDraft.value.trim()
  const union = comboUnionIds.value.filter(id => Number.isInteger(id) && id > 0)
  const intersection = comboIntersectionIds.value.filter(id => Number.isInteger(id) && id > 0)
  const exclude = comboExcludeIds.value.filter(id => Number.isInteger(id) && id > 0)
  if (!name || (!union.length && !intersection.length) || comboBusy.value) return
  comboBusy.value = true
  comboError.value = ''
  try {
    const stableKey = selectedComboKey.value ?? `${name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'combo'}-${Date.now()}`
    const saved = await api.put<ComboListDefinition>(`/workspaces/library/items/combo_list/${encodeURIComponent(stableKey)}`, {
      kind: 'combo_list', stable_key: stableKey, name,
      payload: { union_watchlist_ids: union, intersection_watchlist_ids: intersection, exclude_watchlist_ids: exclude },
      dependency_metadata: { watchlist_ids: [...new Set([...union, ...intersection, ...exclude])] },
    })
    const index = comboLists.value.findIndex(item => item.stable_key === stableKey)
    if (index >= 0) comboLists.value[index] = saved
    else comboLists.value.push(saved)
    selectedComboKey.value = stableKey
    flaggedItemsSelected.value = false
    selectedPersonalWatchlistId.value = null
    emit('configuration', props.tool.instance_key, { ...props.tool.configuration, watchlist_id: `combo:${stableKey}` })
  } catch (cause: any) {
    comboError.value = cause?.message ?? 'Unable to save combo list'
  } finally {
    comboBusy.value = false
  }
}

async function deleteComboList() {
  const combo = selectedCombo.value
  if (!combo || comboBusy.value) return
  comboBusy.value = true
  comboError.value = ''
  try {
    await api.delete(`/workspaces/library/items/combo_list/${encodeURIComponent(combo.stable_key)}`)
    comboLists.value = comboLists.value.filter(item => item.stable_key !== combo.stable_key)
    selectedComboKey.value = null
    comboNameDraft.value = ''
    comboUnionIds.value = []
    comboIntersectionIds.value = []
    comboExcludeIds.value = []
    selectedPersonalWatchlistId.value = personalWatchlists.value[0]?.id ?? null
    emit('configuration', props.tool.instance_key, { ...props.tool.configuration, watchlist_id: selectedPersonalWatchlistId.value })
  } catch (cause: any) {
    comboError.value = cause?.message ?? 'Unable to delete combo list'
  } finally {
    comboBusy.value = false
  }
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
    const deleted = await watchlistStore.deleteWatchlist(watchlist.id)
    if (!deleted) throw new Error('Unable to delete personal watchlist')
    const next = personalWatchlists.value[0] ?? null
    flaggedItemsSelected.value = false
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

async function handleMembershipAction(action: 'copy-to-watchlist' | 'move-to-watchlist', row: { symbol: string; instrumentId: number | null; itemId?: number }, targetWatchlistId?: number) {
  if (row.instrumentId == null || targetWatchlistId == null) return
  const target = personalWatchlists.value.find(watchlist => watchlist.id === targetWatchlistId)
  if (!target || target.is_locked || target.is_managed) {
    personalWatchlistError.value = 'Choose an unlocked personal watchlist as the destination.'
    return
  }
  if (action === 'move-to-watchlist' && (!selectedPersonalWatchlist.value || selectedPersonalWatchlist.value.is_locked || selectedPersonalWatchlist.value.is_managed || selectedPersonalWatchlist.value.id === target.id)) return
  personalWatchlistError.value = ''
  const added = await watchlistStore.addItem(target.id, row.instrumentId)
  if (!added) {
    personalWatchlistError.value = `${row.symbol} is already in ${target.name}, or the destination rejected the change.`
    return
  }
  if (action === 'move-to-watchlist' && selectedPersonalWatchlist.value && row.itemId != null) {
    await watchlistStore.removeItem(selectedPersonalWatchlist.value.id, row.itemId)
  }
}

function handlePersonalRowAction(action: 'chart' | 'compare' | 'note' | 'alert' | 'copy' | 'copy-to-watchlist' | 'move-to-watchlist' | 'flag' | 'remove', row: { symbol: string; instrumentId: number | null; itemId?: number; sourceWatchlistId?: number; flagged?: boolean }, targetWatchlistId?: number) {
  if (action === 'flag' && row.itemId != null) {
    const sourceWatchlistId = row.sourceWatchlistId ?? selectedPersonalWatchlist.value?.id
    if (sourceWatchlistId == null) return
    void watchlistStore.setItemFlag(sourceWatchlistId, row.itemId, !row.flagged)
    return
  }
  if (action === 'copy-to-watchlist' || action === 'move-to-watchlist') {
    void handleMembershipAction(action, row, targetWatchlistId)
    return
  }
  if (action === 'remove' && selectedPersonalWatchlist.value && row.itemId != null) {
    void watchlistStore.removeItem(selectedPersonalWatchlist.value.id, row.itemId)
    return
  }
  if (action !== 'remove') handleRowAction(action, row)
}

onMounted(async () => {
  if (!watchlistStore.watchlists.length && !watchlistStore.loading) await watchlistStore.loadWatchlists()
  if (props.tool.tool_type !== 'watchlist' || props.tool.configuration.personal !== true) return
  await loadComboLists()
  if (selectedPersonalWatchlistId.value == null && !flaggedItemsSelected.value) {
    selectedPersonalWatchlistId.value = personalWatchlists.value[0]?.id ?? null
    personalListNameDraft.value = personalWatchlists.value[0]?.name ?? ''
    if (selectedPersonalWatchlistId.value != null) {
      emit('configuration', props.tool.instance_key, { ...props.tool.configuration, watchlist_id: selectedPersonalWatchlistId.value })
    }
  }
  const symbols = personalWatchlistRows.value.map(row => row.symbol).filter(symbol => !symbol.startsWith('#'))
  if (symbols.length) await watchlistStore.fetchPrices(symbols)
  void loadIndicatorColumns([
    ...personalWatchlistRows.value,
    ...flaggedWatchlistRows.value,
    ...comboWatchlistRows.value,
    ...benchmarkRows.value,
    ...sectorRows.value,
    ...factoryWatchlistRows.value,
    ...proxyRows.value,
    ...constituentRows.value,
  ])
  void loadConditionColumns([
    ...personalWatchlistRows.value,
    ...flaggedWatchlistRows.value,
    ...comboWatchlistRows.value,
    ...benchmarkRows.value,
    ...sectorRows.value,
    ...factoryWatchlistRows.value,
    ...proxyRows.value,
    ...constituentRows.value,
  ])
})

watch(() => props.tool.configuration.watchlist_id, value => {
  flaggedItemsSelected.value = value === 'flagged'
  selectedComboKey.value = typeof value === 'string' && value.startsWith('combo:') ? value.slice(6) : null
  selectedPersonalWatchlistId.value = typeof value === 'number' ? value : null
  hydrateSelectedCombo()
})

watch(() => selectedPersonalWatchlist.value?.items.map(item => item.symbol).join(','), value => {
  const symbols = (value ?? '').split(',').filter(Boolean)
  if (symbols.length) void watchlistStore.fetchPrices(symbols)
})
watch(() => flaggedWatchlistRows.value.map(row => row.symbol).join(','), value => {
  const symbols = (value ?? '').split(',').filter(Boolean)
  if (symbols.length) void watchlistStore.fetchPrices(symbols)
})
watch(() => comboWatchlistRows.value.map(row => row.symbol).join(','), value => {
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
let chartSelectionSequence = 0
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
const configuredPythonPlots = computed(() => {
  const plots = props.tool.configuration.python_plots
  if (!Array.isArray(plots)) return []
  return plots.filter((plot): plot is { code_version_id: number; name: string; color?: string; timeframe?: string } => Boolean(plot) && typeof plot === 'object' && Number.isInteger((plot as Record<string, unknown>).code_version_id) && typeof (plot as Record<string, unknown>).name === 'string' && (typeof (plot as Record<string, unknown>).color === 'undefined' || typeof (plot as Record<string, unknown>).color === 'string') && (typeof (plot as Record<string, unknown>).timeframe === 'undefined' || typeof (plot as Record<string, unknown>).timeframe === 'string'))
})
const pythonSeries = ref<ChartPythonSeries[]>([])
let pythonPlotRequestSequence = 0
const pythonPlotRunIds = new Set<number>()
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

function updatePythonPlots(plots: Array<{ code_version_id: number; name: string; color?: string; timeframe?: string }>) {
  emit('configuration', props.tool.instance_key, { ...props.tool.configuration, python_plots: plots })
}

async function loadPythonPlots() {
  const plots = configuredPythonPlots.value
  for (const runId of pythonPlotRunIds) void api.post(`/research/runs/${runId}/cancel`, {})
  pythonPlotRunIds.clear()
  if (props.tool.tool_type !== 'chart' || !plots.length || !activeSymbol.value) { pythonSeries.value = []; return }
  const sequence = ++pythonPlotRequestSequence
  const loaded = await Promise.all(plots.map(async plot => {
    const timeframe = plot.timeframe ?? activeTimeframe.value
    let runId: number | null = null
    try {
      const queued = await api.post<{ id: number }>('/research/runs', { code_version_id: plot.code_version_id, run_config: { symbol: activeSymbol.value, timeframe }, dataset_manifest: { source: 'canonical_database', timeframe } })
      runId = queued.id
      pythonPlotRunIds.add(queued.id)
      for (let attempt = 0; attempt < 30; attempt += 1) {
        const result = await queryClient.fetchQuery({
          queryKey: ['workstation', 'research-run', queued.id],
          queryFn: () => api.get<{ status: string; artifacts?: Array<{ name: string; artifact_type: string; payload: Record<string, unknown> }> }>(`/research/runs/${queued.id}`),
          staleTime: 0,
        })
        if (result.status === 'completed' || result.status === 'failed' || result.status === 'canceled') {
          const artifact = result.artifacts?.find(item => item.artifact_type === 'series')
          const value = artifact?.payload?.value
          if (!value || typeof value !== 'object' || Array.isArray(value)) return null
          const candidate = value as { timestamps?: unknown; values?: unknown }
          if (!Array.isArray(candidate.timestamps) || !candidate.timestamps.every(item => typeof item === 'string') || !Array.isArray(candidate.values) || candidate.timestamps.length !== candidate.values.length || !candidate.values.every(item => item == null || typeof item === 'number')) return null
          return { codeVersionId: plot.code_version_id, label: plot.name, color: plot.color ?? '#ffb74d', timestamps: candidate.timestamps, values: candidate.values } satisfies ChartPythonSeries
        }
        await new Promise(resolve => window.setTimeout(resolve, 250))
      }
    } catch { return null }
    finally { if (runId != null) pythonPlotRunIds.delete(runId) }
    return null
  }))
  if (sequence === pythonPlotRequestSequence) pythonSeries.value = loaded.filter((item): item is ChartPythonSeries => item != null)
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

function handleRowAction(action: 'chart' | 'compare' | 'note' | 'alert' | 'copy' | 'copy-to-watchlist' | 'move-to-watchlist' | 'flag' | 'remove', row: { symbol: string; instrumentId: number | null; flagged?: boolean }, targetWatchlistId?: number) {
  if (action === 'flag') return
  if (action === 'copy-to-watchlist' || action === 'move-to-watchlist') {
    void handleMembershipAction(action, row, targetWatchlistId)
    return
  }
  if (action === 'remove') return
  emit('rowAction', action, row)
}

watch([activeSymbol, activeTimeframe, syntheticExpression, chartBarType], async ([symbol, timeframe, expression, barType]) => {
  if (props.tool.tool_type !== 'chart' || (!symbol && !expression)) return
  const sequence = ++chartSelectionSequence
  let targetSymbol = symbol
  if (expression) {
    try {
      targetSymbol = await ensureKnownInstrumentSymbol(expression, 'Workstation expression')
    } catch (cause: any) {
      if (sequence === chartSelectionSequence) chartStore.error = cause?.message ?? 'Unable to resolve expression'
      return
    }
  }
  if (sequence !== chartSelectionSequence) return
  if (chartStore.symbol === targetSymbol && chartStore.timeframe === timeframe && chartStore.barType === barType) return
  void chartStore.loadBars(
    targetSymbol,
    timeframe as Timeframe,
    barType,
    true,
  )
}, { immediate: true })

watch([configuredPythonPlots, activeSymbol, activeTimeframe], () => { void loadPythonPlots() }, { deep: true, immediate: true })

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
function cellWarning(cell: { warning?: { message: string } | null } | null | undefined) {
  return cell?.warning?.message ?? null
}
function snapshotWarnings(row: GroupSnapshotRow | undefined) {
  if (!row) return {}
  const warnings: Record<string, string> = {}
  for (const [period, cell] of Object.entries(row.performance)) {
    if (cell.warning?.message) warnings[`performance_${period.toLowerCase()}`] = cell.warning.message
  }
  for (const [year, cell] of Object.entries(row.calendar_year_performance ?? {})) {
    if (cell.warning?.message) warnings[`calendar_${year}`] = cell.warning.message
  }
  if (row.relative_to_benchmark?.warning?.message) warnings.relative_ratio = row.relative_to_benchmark.warning.message
  if (row.relative_to_market?.warning?.message) warnings.relative_spy = row.relative_to_market.warning.message
  for (const [key, cell] of Object.entries(row.technical ?? {})) {
    if (cell.warning?.message) warnings[key] = cell.warning.message
  }
  return warnings
}
function snapshotLineage(snapshot: { coverage?: number; freshness?: string; data_provenance?: string } | null | undefined) {
  return {
    coverage: snapshot?.coverage ?? null,
    freshness: snapshot?.freshness ?? 'unavailable',
    provenance: snapshot?.data_provenance ?? 'unavailable',
  }
}
const sectorPerformance = computed(() => Object.fromEntries(
  (workspaceStore.groupSnapshots['sp500-sectors']?.rows ?? []).map(row => [row.symbol, row.performance['1M']?.value ?? null]),
))
const breadthGroupKey = computed(() => typeof props.tool.configuration.group_key === 'string' && props.tool.configuration.group_key.trim() ? props.tool.configuration.group_key.trim() : 'sp500-sectors')
const breadthTimeframe = computed(() => ['D1', 'W1', 'MN'].includes(String(props.tool.configuration.timeframe)) ? String(props.tool.configuration.timeframe) : 'D1')
const breadthAdjusted = computed(() => props.tool.configuration.adjusted !== false)
const breadthLookback = computed(() => Math.min(252, Math.max(2, Number(props.tool.configuration.new_high_lookback ?? 20) || 20)))
const breadth = computed(() => workspaceStore.breadth[breadthGroupKey.value])
const breadthHistory = computed(() => workspaceStore.breadthHistory[breadthGroupKey.value])
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
    ...snapshotLineage(industryProxySnapshot.value),
  },
  warnings: {
    performance_1m: cellWarning(row.performance['1M']),
    relative_sector: cellWarning(row.relative_to_benchmark),
    relative_spy: cellWarning(row.relative_to_market),
    rsi14: cellWarning(row.technical.rsi14),
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
      ...snapshotLineage(benchmarkSnapshot.value),
    }
  })(),
  warnings: snapshotWarnings(benchmarkSnapshot.value?.rows.find(item => item.instrument_id === member.instrument.id)),
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
      ...snapshotLineage(workspaceStore.groupSnapshots['sp500-sectors']),
      ...Object.fromEntries(Object.entries(row?.calendar_year_performance ?? {}).map(([year, cell]) => [`calendar_${year}`, cell.value])),
    }
  })(),
  warnings: snapshotWarnings(workspaceStore.groupSnapshots['sp500-sectors']?.rows.find(item => item.instrument_id === member.instrument.id)),
})))
const breadthRows = computed<WatchlistRow[]>(() => {
  const snapshot = workspaceStore.groupSnapshots[breadthGroupKey.value]
  return (workspaceStore.marketGroups[breadthGroupKey.value]?.members ?? []).map(member => {
    const row = snapshot?.rows.find(item => item.instrument_id === member.instrument.id)
    const metrics = breadth.value?.member_metrics?.[String(member.instrument.id)] ?? {}
    return {
      instrumentId: member.instrument.id,
      symbol: member.instrument.symbol,
      name: member.instrument.name,
      values: {
        above_ma20: row?.technical?.above_ma20?.value ?? null,
        above_ma50: row?.technical?.above_ma50?.value ?? null,
        above_ma200: row?.technical?.above_ma200?.value ?? null,
        near_52w_high: metrics.near_52w_high ?? null,
        near_52w_low: metrics.near_52w_low ?? null,
        new_high: metrics.new_high ?? null,
        new_low: metrics.new_low ?? null,
        uptrend: metrics.uptrend ?? null,
        downtrend: metrics.downtrend ?? null,
      },
      warnings: snapshotWarnings(row),
    }
  })
})
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
        relative_spy: analysis?.relative_to_market?.value == null ? null : analysis.relative_to_market.value.toFixed(4),
        rsi14: analysis?.technical?.rsi14?.value ?? null,
        above_ma50: analysis?.technical?.above_ma50?.value ?? null,
      position_52w: analysis?.technical?.position_52w?.value ?? null,
      ...snapshotLineage(constituentSnapshot.value),
      },
      warnings: snapshotWarnings(analysis),
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
  { key: 'coverage', label: 'Coverage', width: '68px' },
  { key: 'freshness', label: 'Freshness', width: '74px' },
  { key: 'provenance', label: 'Provenance', width: '92px' },
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
  { key: 'coverage', label: 'Coverage', width: '68px' },
  { key: 'freshness', label: 'Freshness', width: '74px' },
  { key: 'provenance', label: 'Provenance', width: '92px' },
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
  { key: 'relative_spy', label: '/ SPY', width: '58px', format: 'number' },
  { key: 'rsi14', label: 'RSI', width: '54px', format: 'number' },
  { key: 'above_ma50', label: '>50', width: '54px' },
  { key: 'position_52w', label: '52W Pos', width: '64px' },
  { key: 'coverage', label: 'Coverage', width: '68px' },
  { key: 'freshness', label: 'Freshness', width: '74px' },
  { key: 'provenance', label: 'Provenance', width: '92px' },
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
  { key: 'coverage', label: 'Coverage', width: '68px' },
  { key: 'freshness', label: 'Freshness', width: '74px' },
  { key: 'provenance', label: 'Provenance', width: '92px' },
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
    const format = candidate.format === 'number' || candidate.format === 'percent' ? candidate.format : undefined
    const decimals = Number.isInteger(candidate.decimals) ? Math.min(6, Math.max(0, Number(candidate.decimals))) : undefined
    return label || width || format || decimals != null
      ? [[key, { ...(label ? { label } : {}), ...(width ? { width } : {}), ...(format ? { format } : {}), ...(decimals != null ? { decimals } : {}) }]]
      : []
  })) as Record<string, { label?: string; width?: string; format?: 'percent' | 'number'; decimals?: number }>
})
const configuredPythonColumns = computed(() => Array.isArray(props.tool.configuration.python_columns)
  ? props.tool.configuration.python_columns.filter((column): column is { code_version_id: number; name: string; timeframe?: string } => Boolean(column) && typeof column === 'object' && Number.isInteger((column as Record<string, unknown>).code_version_id) && typeof (column as Record<string, unknown>).name === 'string' && (typeof (column as Record<string, unknown>).timeframe === 'undefined' || typeof (column as Record<string, unknown>).timeframe === 'string'))
  : [])
const configuredIndicatorColumns = computed(() => Array.isArray(props.tool.configuration.indicator_columns)
  ? props.tool.configuration.indicator_columns.filter((column): column is { key: string; name: string; indicator: string; params: Record<string, unknown>; timeframe: string; output?: string } => Boolean(column) && typeof column === 'object' && typeof (column as Record<string, unknown>).key === 'string' && typeof (column as Record<string, unknown>).name === 'string' && typeof (column as Record<string, unknown>).indicator === 'string' && typeof (column as Record<string, unknown>).params === 'object' && typeof (column as Record<string, unknown>).timeframe === 'string')
  : [])
const configuredConditionColumns = computed(() => Array.isArray(props.tool.configuration.condition_columns)
  ? props.tool.configuration.condition_columns.filter((column): column is { key: string; name: string; screener_id: number; timeframe: string } => Boolean(column) && typeof column === 'object' && typeof (column as Record<string, unknown>).key === 'string' && typeof (column as Record<string, unknown>).name === 'string' && Number.isInteger((column as Record<string, unknown>).screener_id) && typeof (column as Record<string, unknown>).timeframe === 'string')
  : [])

function addPlotColumn(payload: ChartPlotDragPayload) {
  const column = indicatorColumnFromPlot(payload)
  const columns = Array.isArray(props.tool.configuration.indicator_columns) ? props.tool.configuration.indicator_columns : []
  if (columns.some(candidate => Boolean(candidate) && typeof candidate === 'object' && (candidate as Record<string, unknown>).key === column.key)) return
  emit('configuration', props.tool.instance_key, { ...props.tool.configuration, indicator_columns: [...columns, column] })
}
const conditionValues = ref<Record<string, Record<string, boolean | null>>>({})
const conditionDropError = ref('')
let conditionRequestGeneration = 0
async function loadConditionColumns(rows: Array<{ symbol: string; instrumentId?: number | null }>) {
  const columns = configuredConditionColumns.value
  if (!columns.length) { conditionValues.value = {}; return }
  const generation = ++conditionRequestGeneration
  const next: Record<string, Record<string, boolean | null>> = {}
  await Promise.all(columns.map(async column => {
    try {
      const results = await queryClient.fetchQuery({
        queryKey: ['workstation', 'condition-column', column.screener_id],
        queryFn: () => api.get<Array<{ matched_ids?: number[] }>>(`/screeners/${column.screener_id}/results`, { limit: 1 }),
        staleTime: 30_000,
      })
      const matched = new Set(results[0]?.matched_ids ?? [])
      next[column.key] = Object.fromEntries(rows.map(row => [row.symbol, row.instrumentId == null ? null : matched.has(row.instrumentId)]))
    } catch {
      next[column.key] = Object.fromEntries(rows.map(row => [row.symbol, null]))
    }
  }))
  if (generation === conditionRequestGeneration) conditionValues.value = next
}
async function addConditionColumn(payload: TechnicalConditionDragPayload) {
  conditionDropError.value = ''
  const name = payload.label.trim() || 'Technical condition'
  const stableKey = `drag-${name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 54) || 'technical-condition'}-${payload.timeframe.toLowerCase()}`
  const key = `condition:${stableKey}`
  if (configuredConditionColumns.value.some(column => column.key === key)) return
  try {
    await api.put(`/workspaces/library/conditions/${encodeURIComponent(stableKey)}`, {
      name, condition: payload.condition,
      dependency_metadata: { source: 'technical-condition-drag', timeframe: payload.timeframe },
    })
    let scan: { id: number }
    try {
      scan = await api.post<{ id: number }>(`/screeners/from-condition/${encodeURIComponent(stableKey)}`, {
        name: `${name} Boolean`, universe_type: 'all', timeframe: payload.timeframe,
      })
    } catch (cause: any) {
      if (!String(cause?.message ?? '').includes('→ 409:')) throw cause
      const existing = await api.get<Array<{ id: number; name: string }>>('/screeners')
      const found = existing.find(item => item.name.toLowerCase() === `${name} boolean`.toLowerCase())
      if (!found) throw cause
      scan = found
    }
    await api.post(`/screeners/${scan.id}/run`, {})
    const columns = Array.isArray(props.tool.configuration.condition_columns) ? props.tool.configuration.condition_columns : []
    emit('configuration', props.tool.instance_key, { ...props.tool.configuration, condition_columns: [...columns, { key, name, screener_id: scan.id, timeframe: payload.timeframe }] })
    void loadConditionColumns([...personalWatchlistRows.value, ...flaggedWatchlistRows.value, ...comboWatchlistRows.value, ...benchmarkRows.value, ...sectorRows.value, ...factoryWatchlistRows.value, ...proxyRows.value, ...constituentRows.value])
  } catch (cause: any) {
    conditionDropError.value = `Unable to create ${name} Boolean column: ${cause?.message ?? 'unknown error'}`
  }
}
const indicatorValues = ref<Record<string, Record<string, number | null>>>({})
const indicatorWarnings = ref<Record<string, Record<string, string | null>>>({})
let indicatorRequestGeneration = 0
async function loadIndicatorColumns(rows: Array<{ symbol: string }>) {
  const columns = configuredIndicatorColumns.value
  if (!columns.length) { indicatorValues.value = {}; indicatorWarnings.value = {}; return }
  const generation = ++indicatorRequestGeneration
  await queryClient.cancelQueries({ queryKey: ['workstation', 'indicator-batch'] })
  const symbols = [...new Set(rows.map(row => row.symbol).filter(symbol => symbol && !symbol.startsWith('#')))]
  if (!symbols.length) { indicatorValues.value = {}; indicatorWarnings.value = {}; return }
  const next: Record<string, Record<string, number | null>> = {}
  const nextWarnings: Record<string, Record<string, string | null>> = {}
  await Promise.all(columns.map(async column => {
    try {
      const params = { ...column.params, ...(column.output ? { output: column.output } : {}) }
      const requestSymbols = [...symbols].sort()
      const response = await queryClient.fetchQuery({
        queryKey: ['workstation', 'indicator-batch', requestSymbols, column.indicator, params, column.timeframe, true],
        queryFn: ({ signal }) => api.post<{ values: Record<string, { value?: number | null; warning?: { code?: string } | null }> }>('/analysis/indicator-batch', {
          symbols: requestSymbols, indicator: column.indicator, params, timeframe: column.timeframe, adjusted: true,
        }, { signal }),
        staleTime: 30_000,
      })
      next[column.key] = Object.fromEntries(Object.entries(response.values ?? {}).map(([symbol, cell]) => [symbol, cell?.value ?? null]))
      nextWarnings[column.key] = Object.fromEntries(Object.entries(response.values ?? {}).map(([symbol, cell]) => [symbol, cell?.warning?.code ?? null]))
    } catch {
      next[column.key] = Object.fromEntries(symbols.map(symbol => [symbol, null]))
      nextWarnings[column.key] = Object.fromEntries(symbols.map(symbol => [symbol, 'unavailable']))
    }
  }))
  if (generation === indicatorRequestGeneration) {
    indicatorValues.value = next
    indicatorWarnings.value = nextWarnings
  }
}

watch(
  () => [
    ...personalWatchlistRows.value,
    ...flaggedWatchlistRows.value,
    ...comboWatchlistRows.value,
    ...benchmarkRows.value,
    ...sectorRows.value,
    ...factoryWatchlistRows.value,
    ...proxyRows.value,
    ...constituentRows.value,
  ].map(row => row.symbol).join(',') + JSON.stringify(configuredIndicatorColumns.value) + JSON.stringify(configuredConditionColumns.value),
  () => {
    void loadIndicatorColumns([
      ...personalWatchlistRows.value,
      ...flaggedWatchlistRows.value,
      ...comboWatchlistRows.value,
      ...benchmarkRows.value,
      ...sectorRows.value,
      ...factoryWatchlistRows.value,
      ...proxyRows.value,
      ...constituentRows.value,
    ])
    void loadConditionColumns([
      ...personalWatchlistRows.value,
      ...flaggedWatchlistRows.value,
      ...comboWatchlistRows.value,
      ...benchmarkRows.value,
      ...sectorRows.value,
      ...factoryWatchlistRows.value,
      ...proxyRows.value,
      ...constituentRows.value,
    ])
  },
  { immediate: true },
)
const configuredPythonCondition = computed(() => {
  const condition = props.tool.configuration.python_condition
  if (!condition || typeof condition !== 'object' || Array.isArray(condition)) return null
  const value = condition as Record<string, unknown>
  return Number.isInteger(value.code_version_id) && typeof value.name === 'string' && ['active', 'inactive', 'off'].includes(String(value.mode)) && (value.timeframe === undefined || typeof value.timeframe === 'string')
    ? { code_version_id: value.code_version_id as number, name: value.name, mode: value.mode as 'active' | 'inactive' | 'off', ...(typeof value.timeframe === 'string' ? { timeframe: value.timeframe } : {}) }
    : null
})
const descriptions: Record<string, string> = {
  SPY: 'S&P 500 proxy', RSP: 'S&P 500 equal weight', QQQ: 'Nasdaq-100 proxy', DIA: 'Dow Jones proxy', IWM: 'Russell 2000 proxy',
  XLK: 'Technology', XLY: 'Consumer Discretionary', XLC: 'Communication Services', XLF: 'Financials', XLV: 'Health Care', XLI: 'Industrials', XLP: 'Consumer Staples', XLE: 'Energy', XLU: 'Utilities', XLRE: 'Real Estate', XLB: 'Materials',
  NVDA: 'NVIDIA', MSFT: 'Microsoft', AAPL: 'Apple', AVGO: 'Broadcom', CRM: 'Salesforce', ORCL: 'Oracle', AMD: 'AMD', ADBE: 'Adobe',
}
const freshnessLabel = (value?: string) => value ? ` · ${value}` : ''
const breadthCoverage = computed(() => breadth.value ? `${(breadth.value.coverage * 100).toFixed(0)}% · ${breadth.value.evaluated_count} symbols${freshnessLabel(breadth.value.freshness)}` : 'Unavailable')
const breadthMetricCoverage = computed(() => {
  const detail = breadth.value?.coverage_detail
  if (!detail) return 'Unavailable'
  return Object.entries(detail).map(([key, value]) => `${key} ${(value * 100).toFixed(0)}%`).join(' · ')
})
const breadthDrilldown = ref<{ key: string; state: 'above' | 'below' } | null>(null)
const breadthDrilldownRows = computed(() => {
  if (!breadthDrilldown.value) return []
  const expected = breadthDrilldown.value.state === 'above' ? 1 : 0
  return breadthRows.value.filter(row => row.values?.[breadthDrilldown.value!.key] === expected)
})
const technicalMAs = computed(() => [technical.value?.sma20, technical.value?.sma50, technical.value?.sma200]
  .map(value => formatNumber(value)).join(' / '))
function breadthMetric(key: string) {
  const value = key.startsWith('ma')
    ? breadth.value?.above_ma[key]
    : key === 'near_52w_high' ? breadth.value?.near_52w?.high
      : key === 'near_52w_low' ? breadth.value?.near_52w?.low
        : key === 'new_high' ? breadth.value?.new_highs?.lookback
          : key === 'new_low' ? breadth.value?.new_lows?.lookback
            : key === 'uptrend' ? breadth.value?.trend?.uptrend
              : key === 'downtrend' ? breadth.value?.trend?.downtrend
                : null
  return value == null ? 'Unavailable' : `${(value * 100).toFixed(1)}%`
}
function breadthDrilldownLabel(key: string) {
  return ({
    ma20: '20-day MA', ma50: '50-day MA', ma200: '200-day MA',
    near_52w_high: 'near 52-week high', near_52w_low: 'near 52-week low',
    new_high: `new high (${breadthLookback.value})`, new_low: `new low (${breadthLookback.value})`,
    uptrend: 'uptrend', downtrend: 'downtrend',
  } as Record<string, string>)[key] ?? key
}
function breadthAdvanced(bucket: 'near_52w' | 'new_highs' | 'new_lows' | 'trend' | 'distance_from_ma', key: string) {
  const value = breadth.value?.[bucket]?.[key]
  return value == null ? '—' : `${(value * 100).toFixed(1)}%`
}
function breadthBelowCount(key: string) {
  return breadthRows.value.filter(row => row.values?.[key] === 0).length
}
function setBreadthDrilldown(key: string, state: 'above' | 'below') {
  breadthDrilldown.value = breadthDrilldown.value?.key === key && breadthDrilldown.value.state === state
    ? null
    : { key, state }
}
function setBreadthGroup(groupKey: string) {
  const normalized = groupKey === 'us-benchmarks' ? 'us-benchmarks' : 'sp500-sectors'
  setBreadthConfiguration({ group_key: normalized })
}
function setBreadthConfiguration(configuration: Record<string, unknown>) {
  emit('configuration', props.tool.instance_key, { ...props.tool.configuration, ...configuration })
}
async function loadBreadthUniverse(groupKey: string, timeframe = breadthTimeframe.value, adjusted = breadthAdjusted.value, lookback = breadthLookback.value) {
  const options = { ...(timeframe !== 'D1' ? { timeframe } : {}), ...(adjusted !== true ? { adjusted } : {}), ...(lookback !== 20 ? { new_high_lookback: lookback } : {}) }
  await Promise.all([
    workspaceStore.loadMarketGroup(groupKey),
    workspaceStore.loadGroupSnapshot(groupKey, 'SPY', options),
    workspaceStore.loadBreadth(groupKey, options),
    workspaceStore.loadBreadthHistory(groupKey, options),
  ])
}
watch([breadthGroupKey, breadthTimeframe, breadthAdjusted, breadthLookback], ([groupKey, timeframe, adjusted, lookback]) => {
  if (props.tool.instance_key === 'breadth-summary' || props.tool.tool_type === 'breadth') void loadBreadthUniverse(groupKey, timeframe, adjusted, lookback)
}, { immediate: true })
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
.combo-editor { display: flex; align-items: center; gap: 4px; padding-left: 4px; border-left: 1px solid #34434d; }
.combo-editor header { color: #d7e4eb; }
.combo-editor label { display: flex; align-items: center; gap: 2px; color: #8498a6; }
.combo-editor select { width: 82px; min-height: 22px; }
.combo-editor select[multiple] { height: 34px; }
.combo-editor input { width: 78px; }
.analysis { height: 100%; min-height: 0; }
.breadth-tool { display:grid; grid-template-rows:auto auto auto auto minmax(0,1fr); height:100%; min-height:0; }.breadth-tool__universe { display:flex; gap:5px; align-items:center; padding:5px 7px 0; color:#9aabb6; font:10px "Segoe UI",Arial,sans-serif; }.breadth-tool__universe select,.breadth-tool__universe input { border:1px solid #34434e; background:#172027; color:#d2dce3; font:inherit; }.breadth-tool__universe input { width:42px; }.metrics { display: grid; grid-template-columns: 1fr auto; gap: 5px 10px; padding: 9px; color: #99aabb; font: 10px "Segoe UI", Arial, sans-serif; }.breadth-tool__coverage-detail { padding:0 7px 4px; color:#778994; font:9px "Segoe UI",Arial,sans-serif; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }.breadth-tool__actions { display:flex; gap:3px; justify-content:flex-end; }.breadth-tool__actions button,.breadth-tool__drilldown header button { border:1px solid #34434e; background:#172027; color:#b9c8d1; font:inherit; padding:1px 4px; cursor:pointer; }.breadth-tool__actions button:hover,.breadth-tool__action--active { background:#1d4057; color:#e5f1f7; }.breadth-tool__drilldown { min-height:0; max-height:150px; overflow:auto; border-top:1px solid #2b3841; border-bottom:1px solid #2b3841; background:#131a20; font:10px "Segoe UI",Arial,sans-serif; }.breadth-tool__drilldown header { display:flex; justify-content:space-between; align-items:center; padding:4px 7px; color:#9aabb6; position:sticky; top:0; background:#20282f; }.breadth-tool__drilldown > button { display:flex; gap:8px; width:100%; border:0; border-bottom:1px solid #20282f; background:transparent; color:#cad4db; padding:4px 7px; text-align:left; cursor:pointer; }.breadth-tool__drilldown > button:hover { background:#1d4057; }.breadth-tool__drilldown > button span { color:#81929e; }.breadth-tool__drilldown > small { display:block; padding:7px; color:#8497a4; }
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
