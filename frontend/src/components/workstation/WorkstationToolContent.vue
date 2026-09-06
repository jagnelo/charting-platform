<template>
  <ToolWindow :window-key="tool.instance_key" :title="tool.title || tool.tool_type" :symbol="activeSymbol" :link-group="localLinkGroup" :timeframe-link-group="timeframeLinkGroup" :timeframe="tool.tool_type === 'chart' ? activeTimeframe : ''" :active="tool.instance_key === activeWindowKey" @float="emit('float', tool.instance_key)" @maximize="emit('maximize', tool.instance_key)" @close="emit('close', tool.instance_key)" @update:link-group="handleLinkGroupChange" @update:timeframe-link-group="setTimeframeLinkGroup" @update:timeframe="setTimeframe">
    <div v-if="tool.instance_key === 'benchmark-list'" class="benchmark-surface">
      <div class="benchmark-surface__family-controls" aria-label="Benchmark family selector">
        <label>Family
          <select :value="benchmarkFamilyKey" aria-label="Benchmark family" @change="setBenchmarkFamily(($event.target as HTMLSelectElement).value)">
            <option value="">Major US benchmarks</option>
            <option v-for="family in benchmarkFamilyOptions" :key="family.logicalKey" :value="family.logicalKey">{{ family.name }}</option>
          </select>
        </label>
        <label v-if="benchmarkFamilyKey">Map role
          <select :value="activeBenchmarkMapRole" aria-label="Benchmark family Map role" @change="setBenchmarkFamilyMapRole(($event.target as HTMLSelectElement).value)">
            <option v-for="role in benchmarkFamilyMapRoleOptions" :key="role.role" :value="role.role" :disabled="!role.available">{{ familyRoleLabel(role.role) }}{{ role.available ? '' : ' · unavailable' }}</option>
          </select>
        </label>
        <span v-if="benchmarkFamilyKey" class="benchmark-surface__family-state">{{ activeBenchmarkLabel }} · locked family legs</span>
        <span v-if="benchmarkFamilyReadinessLoading" role="status">Checking all-family readiness…</span>
        <span v-else-if="benchmarkFamilyReadinessError" class="benchmark-surface__family-error" role="alert">Readiness unavailable: {{ benchmarkFamilyReadinessError }}</span>
        <span v-else-if="benchmarkFamilyReadiness" class="benchmark-surface__family-readiness" aria-label="Benchmark family readiness">All-family readiness: {{ benchmarkFamilyReadiness.readiness_status }} · {{ benchmarkFamilyReadiness.ready_role_count }}/{{ benchmarkFamilyReadiness.role_count }} roles · {{ benchmarkFamilyReadiness.ready_family_count }}/{{ benchmarkFamilyReadiness.family_count }} families ready</span>
        <span v-if="benchmarkFamilyReadiness" class="sr-only" aria-label="Benchmark provider probe evidence">{{ benchmarkFamilyProviderProbeLabel(benchmarkFamilyReadiness) }}</span>
        <span v-if="benchmarkFamilyReadiness" class="sr-only" aria-label="Benchmark family universe provenance">{{ benchmarkFamilyUniverseProvenanceLabel(benchmarkFamilyReadiness) }}</span>
        <span v-if="benchmarkFamilyLoading" role="status">Loading family legs…</span>
        <span v-else-if="benchmarkFamilyError" class="benchmark-surface__family-error" role="alert">{{ benchmarkFamilyError }}</span>
      </div>
      <div v-if="benchmarkFamilyKey && benchmarkFamilyOverview" class="benchmark-surface__family-roles" aria-label="Selected benchmark family roles">
        <span v-for="mapping in benchmarkFamilyOverview.mappings" :key="mapping.role"><b>{{ familyRoleLabel(mapping.role) }}</b> {{ mapping.symbol ?? mapping.label }} · {{ familyMappingState(mapping) }}</span>
      </div>
      <div class="benchmark-surface__identity" :aria-label="`${activeBenchmarkLabel} benchmark identity`">
        <strong>{{ activeBenchmarkLabel }}</strong>
        <span>Official series: {{ activeBenchmarkIdentity.official_index_symbol }}</span>
        <span>Using tradable proxy: {{ activeBenchmarkIdentity.default_tradable_proxy }}</span>
      </div>
      <VirtualWatchlistTool
      :label="activeBenchmarkListLabel"
      :timeframe="activeTimeframe"
      :rows="activeBenchmarkRows"
      :loading="workspaceStore.marketAnalysisRefreshing || benchmarkFamilyLoading"
      loading-label="Refreshing benchmark analysis…"
      :error-message="activeBenchmarkDataError"
      :columns="benchmarkColumns"
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
      :market-map-source-id="activeBenchmarkMarketMapSourceId"
      :market-map-source-for-row="benchmarkFamilyKey ? benchmarkFamilyMarketMapSourceForRow : undefined"
      @select="selectSymbol($event.symbol, $event.instrumentId)"
      @compare="emit('compare', $event)"
      @market-map="emit('marketMap', $event)"
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
      :loading="workspaceStore.marketAnalysisRefreshing"
      loading-label="Refreshing sector analysis…"
      :error-message="sectorDataError"
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
      market-map-source-id="market-group:sp500-sectors"
      @select="selectSymbol($event.symbol, $event.instrumentId)"
      @compare="emit('compare', $event)"
      @market-map="emit('marketMap', $event)"
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
    <section v-else-if="tool.tool_type === 'watchlist' && tool.configuration.personal === true" class="personal-watchlist-tool" role="region" aria-label="Personal watchlists" :aria-busy="((watchlistStore.loading && !selectedPersonalWatchlist && !flaggedItemsSelected && !selectedCombo) || personalListBusy || personalWatchlistBusy) ? 'true' : 'false'">
      <div class="personal-watchlist-tool__controls">
        <label>WatchList
            <select :value="flaggedItemsSelected ? 'flagged' : selectedComboKey ? `combo:${selectedComboKey}` : effectiveSelectedPersonalWatchlistId == null ? '' : String(effectiveSelectedPersonalWatchlistId)" aria-label="Personal watchlist" @change="selectPersonalWatchlist(($event.target as HTMLSelectElement).value)">
            <option value="flagged">Flagged Items</option>
            <option value="">Select a personal watchlist</option>
            <option v-for="watchlist in personalWatchlists" :key="watchlist.id" :value="String(watchlist.id)">{{ watchlist.name }}{{ watchlist.is_locked ? ' · Locked' : '' }}</option>
            <option v-for="combo in comboLists" :key="`combo:${combo.stable_key}`" :value="`combo:${combo.stable_key}`">Combo · {{ combo.name }}</option>
          </select>
        </label>
        <input v-model="personalListNameDraft" aria-label="Personal watchlist name" placeholder="List name" :disabled="flaggedItemsSelected || Boolean(selectedCombo)" @input="markPersonalListNameEdited" @keydown.enter.prevent="selectedPersonalWatchlist ? renamePersonalWatchlist() : createPersonalWatchlist($event)" />
        <button type="button" :disabled="flaggedItemsSelected || Boolean(selectedCombo)" @click="createPersonalWatchlist">New</button>
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
        <span v-if="watchlistStore.loadError" class="personal-watchlist-tool__error" role="alert" aria-live="assertive" aria-atomic="true">{{ watchlistStore.loadError }}</span>
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
        :market-map-source-id="personalMarketMapSourceId"
        :reorderable="Boolean(selectedPersonalWatchlist && !selectedPersonalWatchlist.is_locked && !selectedPersonalWatchlist.is_managed)"
        :allow-remove="Boolean(selectedPersonalWatchlist && !selectedPersonalWatchlist.is_locked && !selectedPersonalWatchlist.is_managed)"
        @select="selectSymbol($event.symbol, $event.instrumentId)"
        @reorder="selectedPersonalWatchlist && emit('reorder', selectedPersonalWatchlist.id, $event)"
        @compare="emit('compare', $event)"
        @market-map="emit('marketMap', $event)"
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
    </section>
    <VirtualWatchlistTool
      v-else-if="tool.tool_type === 'watchlist' && !isIndustryTool"
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
      :market-map-source-id="factoryWatchlistSourceId"
      @select="tool.instance_key === 'industries' ? emit('selectIndustry', $event.symbol, industryETFContext) : selectSymbol($event.symbol, $event.instrumentId)"
      @compare="emit('compare', $event)"
      @market-map="emit('marketMap', $event)"
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
      <RatioUPlot :symbol="ratioChartExpression?.numerator ?? activeSymbol" :benchmarks="ratioChartExpression ? [ratioChartExpression.denominator] : ratioBenchmarks" editable-benchmarks :timeframe="activeTimeframe" :as-of="typeof tool.configuration.as_of === 'string' ? tool.configuration.as_of : null" :linked-timestamp="workspaceStore.timestampForLinkGroup(localLinkGroup)" @cursor-timestamp="workspaceStore.publishTimestamp($event, localLinkGroup, tool.instance_key)" @configuration="emit('configuration', tool.instance_key, { ...tool.configuration, ...$event, auto_ratio: false })" />
    </div>
    <div v-else-if="ratioExpression" class="analysis">
      <RatioUPlot :symbol="ratioExpression.numerator" :benchmarks="[ratioExpression.denominator]" :timeframe="activeTimeframe" :as-of="typeof tool.configuration.as_of === 'string' ? tool.configuration.as_of : null" :linked-timestamp="workspaceStore.timestampForLinkGroup(localLinkGroup)" @cursor-timestamp="workspaceStore.publishTimestamp($event, localLinkGroup, tool.instance_key)" @configuration="emit('configuration', tool.instance_key, { ...tool.configuration, ...$event })" />
    </div>
    <div v-else-if="tool.tool_type === 'chart' && tool.instance_key !== 'ratio-chart'" class="chart-tool">
      <DrawingToolbar class="chart-tool__drawing-toolbar" />
        <div class="chart-tool__surface">
        <ChartTemplateControl class="chart-tool__templates" :configuration="chartTemplateConfiguration" :indicator-configs="chartStore.indicators" @apply="applyChartTemplate" />
        <!-- Use the literal kebab-case event contract so the virtual component
             listener and typed emitter remain identical after template
             compilation. -->
        <ChartPlotLibrary class="chart-tool__plots" :source-window-key="tool.instance_key" :link-group="localLinkGroup" :python-plots="configuredPythonPlots" :scan-plots="configuredScanPlots" @update:python-plots="updatePythonPlots" @update:scan-plots="updateScanPlots" />
        <div class="chart-tool__compare" aria-label="Chart comparisons">
          <input v-model="comparisonDraft" aria-label="Comparison symbol" placeholder="Compare" @keydown.enter.prevent="addComparisonSymbol(comparisonDraft)" />
          <button type="button" title="Add comparison" @click="addComparisonSymbol(comparisonDraft)">＋</button>
          <button v-for="target in comparisonLegend" :key="target.symbol" type="button" class="chart-tool__compare-chip" :title="`Remove ${target.label}`" @click="removeComparisonSymbol(target.symbol)">
            <i :style="{ background: target.color }" />{{ target.symbol }} {{ target.percentChange == null ? '—' : `${target.percentChange >= 0 ? '+' : ''}${target.percentChange.toFixed(2)}%` }} ×
          </button>
        </div>
        <UPlotChart
          v-if="chartStore.symbol && !chartStore.error"
          :chart-type="chartBarType"
          :chart-settings="liveChartConfiguration"
          :workspace-link-group="localLinkGroup"
          :linked-timestamp="workspaceStore.timestampForLinkGroup(localLinkGroup)"
          :comparison-series="comparisonSeries"
          :python-series="numericSeries"
          @configuration="applyChartConfiguration"
        />
        <div v-if="chartStore.isLoading" class="tool-state chart-tool__status" role="status" aria-live="polite" aria-atomic="true">Loading {{ activeSymbol }}…</div>
        <div v-else-if="chartStore.error" class="tool-state tool-state--error chart-tool__status" role="alert" aria-live="assertive" aria-atomic="true">{{ chartStore.error }}</div>
        <div v-if="!chartStore.symbol" class="tool-state" role="status" aria-live="polite" aria-atomic="true">Select a canonical instrument.</div>
      </div>
    </div>
    <div v-else-if="isIndustryTool && industries.length" class="industry-list">
      <div class="industry-list__header" aria-label="Industry ranking columns">
        <span>Industry</span><span>Coverage</span><span>Proxies</span>
        <span v-for="column in industryRankingColumns" :key="column.key">{{ column.label }}</span>
      </div>
      <button
        v-for="item in industryRows"
        :key="item.industry"
        type="button"
        :class="{ 'industry-list__row--active': item.industry === selectedIndustry }"
        class="industry-list__row"
        @click="emit('selectIndustry', item.industry, industryETFContext)"
      >
        <strong>{{ item.industry }}</strong><span>{{ item.resolved_count }}/{{ item.constituent_count }}</span>
        <span v-for="column in industryRankingColumns" :key="column.key" class="industry-list__metric" :title="item.warnings[column.key] ?? undefined">{{ displayIndustryValue(item, column.key) }}</span>
        <small
          class="industry-list__classification"
          :title="item.classificationDetail"
          :aria-label="`${item.industry} classification provenance`"
        >{{ item.classificationLabel }}</small>
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
            :market-map-source-id="proxyMarketMapSourceId"
            @select="selectProxy($event.symbol, $event.instrumentId)"
            @compare="emit('compare', $event)"
            @market-map="emit('marketMap', $event)"
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
      <small class="industry-list__provenance">
        {{ selectedETF }} holdings · {{ industryClassificationSummary }}
        <template v-if="industryComposition?.exclusions.length"> · {{ industryComposition.exclusions.length }} excluded</template>
      </small>
    </div>
    <div v-else-if="isIndustryTool" class="tool-state">
      <template v-if="!selectedETF">
        Select a sector to inspect its industries and verified ETF proxies.
      </template>
      <template v-else>
        No mapped ETF proxy for {{ selectedETF }}. Curated industry mappings require holdings and classification evidence.
      </template>
    </div>
    <div v-else-if="tool.instance_key === 'constituent-list'" class="constituent-tool">
      <VirtualWatchlistTool
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
        :market-map-source-id="constituentMarketMapSourceId"
        @select="selectSymbol($event.symbol, $event.instrumentId)"
        @compare="emit('compare', $event)"
        @market-map="emit('marketMap', $event)"
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
      <small
        v-if="constituentExclusionSummary"
        class="constituent-tool__provenance"
        role="status"
        aria-live="polite"
        aria-atomic="true"
        :title="constituentExclusionCodes.join(', ')"
      >{{ constituentExclusionSummary }}</small>
    </div>
    <div v-else-if="tool.instance_key === 'breadth-summary' || tool.tool_type === 'breadth'" class="breadth-tool" role="region" :aria-label="`Breadth analysis for ${breadthGroupKey}`" :aria-busy="breadthBusy ? 'true' : 'false'">
      <div class="breadth-tool__universe">
        <span>Universe</span>
        <select :value="breadthGroupKey" aria-label="Breadth universe" @change="setBreadthGroup(($event.target as HTMLSelectElement).value)">
          <option value="sp500-sectors">S&amp;P 500 sectors</option>
          <option value="us-benchmarks">US benchmark index proxies</option>
          <optgroup label="Benchmark families">
            <option v-for="family in benchmarkFamilyOptions" :key="family.logicalKey" :value="family.logicalKey">{{ family.name }}</option>
          </optgroup>
        </select>
        <span>Timeframe</span>
        <select :value="breadthTimeframe" aria-label="Breadth timeframe" @change="setBreadthConfiguration({ timeframe: ($event.target as HTMLSelectElement).value })"><option value="D1">Daily</option><option value="W1">Weekly</option><option value="MN">Monthly</option></select>
        <span>Lookback</span>
        <input :value="breadthLookback" aria-label="Breadth new high low lookback" type="number" min="2" max="252" @input="setBreadthNumber('new_high_lookback', $event)" @change="setBreadthNumber('new_high_lookback', $event)" />
        <label><input type="checkbox" :checked="breadthAdjusted" aria-label="Breadth split adjusted" @change="setBreadthConfiguration({ adjusted: ($event.target as HTMLInputElement).checked })" /> Adjusted</label>
      </div>
      <div class="breadth-tool__custom" aria-label="Condition-driven breadth study">
        <strong>Custom condition</strong>
        <select :value="breadthCustomUniverseKind" aria-label="Custom breadth universe" @change="setBreadthConfiguration({ custom_universe_kind: ($event.target as HTMLSelectElement).value })">
          <option value="group">Current group</option>
          <option v-if="isBenchmarkFamily" value="benchmark_family">Selected family leg</option>
          <option value="etf_holdings">SPY holdings proxy</option>
          <option value="watchlist">Watchlist source</option>
        </select>
        <select
          v-if="breadthCustomUniverseKind === 'watchlist'"
          :value="breadthWatchlistSourceId"
          aria-label="Custom breadth watchlist source"
          @change="setBreadthConfiguration({ custom_universe_watchlist_id: ($event.target as HTMLSelectElement).value })"
        >
          <option value="">Select a watchlist source…</option>
          <option v-for="source in breadthWatchlistSources" :key="source.source_id" :value="source.source_id">
            {{ source.name }}{{ source.locked ? ' · Locked' : '' }}
          </option>
        </select>
        <small v-if="breadthCustomUniverseKind === 'watchlist' && watchlistStore.watchlistSourcesLoading" role="status">Loading watchlist sources…</small>
        <small v-if="breadthCustomUniverseKind === 'watchlist' && watchlistStore.watchlistSourcesError" role="alert">{{ watchlistStore.watchlistSourcesError }}</small>
        <select :value="breadthComposition" aria-label="Breadth condition composition" @change="setBreadthConfiguration({ breadth_condition_composition: ($event.target as HTMLSelectElement).value })">
          <option value="single">Single condition</option>
          <option value="all">All conditions</option>
          <option value="any">Any condition</option>
          <option value="not">Not condition</option>
          <option value="tree">Nested condition tree</option>
        </select>
        <select :value="breadthReferenceTarget" aria-label="Breadth reference target" @change="setBreadthConfiguration({ breadth_reference_target: ($event.target as HTMLSelectElement).value })">
          <option value="symbol">Reference symbol</option>
          <option value="group">Equal-weight group aggregate</option>
        </select>
        <label v-if="breadthReferenceTarget === 'symbol'">Benchmark <input :value="breadthBenchmark" aria-label="Breadth benchmark" maxlength="12" @change="setBreadthConfiguration({ breadth_benchmark: ($event.target as HTMLInputElement).value.toUpperCase() })" /></label>
        <label v-else>Reference group <input :value="breadthReferenceGroup" aria-label="Breadth reference group" maxlength="160" @change="setBreadthConfiguration({ breadth_reference_group: ($event.target as HTMLInputElement).value.trim() })" /></label>
        <BreadthConditionTreeEditor
          v-if="breadthComposition === 'tree'"
          :model-value="breadthTreeCondition"
          :python-series-assets="breadthPythonSeriesAssets"
          :python-series-assets-loading="breadthPythonSeriesAssetsLoading"
          @update:model-value="setBreadthTreeCondition"
        />
        <template v-else>
        <select :value="breadthConditionKind" aria-label="Breadth condition" @change="setBreadthConfiguration({ breadth_condition: ($event.target as HTMLSelectElement).value })">
          <option value="above_moving_average">Above moving average</option>
          <option value="within_52_week_high">Within distance of 52-week high/low</option>
          <option value="new_high_low">New high/low versus prior window</option>
          <option value="prior_high_low">Compare with prior high/low</option>
          <option value="trend">Trend state</option>
          <option value="rsi">RSI threshold</option>
          <option value="volume_ratio">Volume ratio threshold</option>
          <option value="relative_strength">Relative strength threshold</option>
          <option value="series_comparison">Member versus reference series</option>
          <option value="event">Event occurred in trailing window</option>
          <option value="comparison">Compare a measured field</option>
          <option value="range">Measured field within a range</option>
          <option value="percentile">Measured field percentile</option>
          <option value="cross_sectional_statistic">Cross-sectional group statistic</option>
          <option v-if="breadthComposition === 'single'" value="python_series">Python numeric series target</option>
        </select>
        <template v-if="breadthConditionKind === 'python_series'">
          <select :value="breadthPythonSeriesCodeVersionId ?? ''" aria-label="Breadth Python series condition asset" @change="setBreadthConfiguration({ breadth_python_series_code_version_id: Number(($event.target as HTMLSelectElement).value) || null })">
            <option value="">Select numeric series…</option>
            <option v-for="asset in breadthPythonSeriesAssets" :key="asset.versionId" :value="asset.versionId">{{ asset.name }}</option>
          </select>
          <select :value="breadthPythonSeriesOperator" aria-label="Breadth Python series operator" @change="setBreadthConfiguration({ breadth_python_series_operator: ($event.target as HTMLSelectElement).value })">
            <option value="gte">At or above</option><option value="gt">Above</option><option value="lte">At or below</option><option value="lt">Below</option><option value="eq">Equal to</option><option value="ne">Not equal</option>
          </select>
          <select :value="breadthPythonSeriesScope" aria-label="Breadth Python series target scope" @change="setBreadthConfiguration({ breadth_python_series_scope: ($event.target as HTMLSelectElement).value })"><option value="member">Member value</option><option value="cross_sectional">Cross-sectional group</option></select>
          <select v-if="breadthPythonSeriesScope === 'cross_sectional'" :value="breadthPythonSeriesStatistic" aria-label="Breadth Python series group statistic" @change="setBreadthConfiguration({ breadth_python_series_statistic: ($event.target as HTMLSelectElement).value })"><option value="mean">Mean</option><option value="median">Median</option><option value="min">Minimum</option><option value="max">Maximum</option><option value="std">Standard deviation</option></select>
          <label>Threshold <input :value="breadthPythonSeriesThreshold" aria-label="Breadth Python series threshold" type="number" step="0.001" @input="setBreadthNumber('breadth_python_series_threshold', $event)" @change="setBreadthNumber('breadth_python_series_threshold', $event)" /></label>
          <small v-if="breadthPythonSeriesAssetsLoading" role="status">Loading Python assets…</small>
          <small v-else-if="!breadthPythonSeriesAssets.length" class="breadth-tool__status--error">No numeric-series condition assets available.</small>
        </template>
        <template v-if="breadthConditionKind === 'above_moving_average'">
          <label>Period <input :value="breadthConditionPeriod" aria-label="Breadth condition moving average period" type="number" min="2" max="252" @input="setBreadthNumber('breadth_condition_period', $event)" @change="setBreadthNumber('breadth_condition_period', $event)" /></label>
          <select :value="breadthConditionAverage" aria-label="Breadth condition average" @change="setBreadthConfiguration({ breadth_condition_average: ($event.target as HTMLSelectElement).value })"><option value="sma">SMA</option><option value="ema">EMA</option></select>
        </template>
        <template v-else-if="breadthConditionKind === 'within_52_week_high'">
          <select :value="breadthHighLowDirection" aria-label="Breadth 52-week direction" @change="setBreadthConfiguration({ breadth_condition_high_low_direction: ($event.target as HTMLSelectElement).value })"><option value="high">Near 52-week high</option><option value="low">Near 52-week low</option></select>
          <label>Threshold <input :value="breadthConditionThreshold" aria-label="Breadth condition high threshold" type="number" min="0.001" max="0.5" step="0.001" @input="setBreadthNumber('breadth_condition_threshold', $event)" @change="setBreadthNumber('breadth_condition_threshold', $event)" /></label>
          <label>Lookback <input :value="breadthConditionLookback" aria-label="Breadth condition high lookback" type="number" min="2" max="504" @input="setBreadthNumber('breadth_condition_lookback', $event)" @change="setBreadthNumber('breadth_condition_lookback', $event)" /></label>
        </template>
        <template v-else-if="breadthConditionKind === 'new_high_low'">
          <select :value="breadthHighLowDirection" aria-label="Breadth new high low direction" @change="setBreadthConfiguration({ breadth_condition_high_low_direction: ($event.target as HTMLSelectElement).value })"><option value="high">New high</option><option value="low">New low</option></select>
          <label>Lookback <input :value="breadthConditionLookback" aria-label="Breadth condition new high low lookback" type="number" min="2" max="252" @input="setBreadthNumber('breadth_condition_lookback', $event)" @change="setBreadthNumber('breadth_condition_lookback', $event)" /></label>
        </template>
        <template v-else-if="breadthConditionKind === 'prior_high_low'">
          <select :value="breadthHighLowDirection" aria-label="Breadth prior high low direction" @change="setBreadthConfiguration({ breadth_condition_high_low_direction: ($event.target as HTMLSelectElement).value })"><option value="high">Prior high</option><option value="low">Prior low</option></select>
          <label>Lookback <input :value="breadthConditionLookback" aria-label="Breadth prior high low lookback" type="number" min="2" max="5000" @input="setBreadthNumber('breadth_condition_lookback', $event)" @change="setBreadthNumber('breadth_condition_lookback', $event)" /></label>
          <select :value="breadthComparisonOperator" aria-label="Breadth prior high low operator" @change="setBreadthConfiguration({ breadth_comparison_operator: ($event.target as HTMLSelectElement).value })"><option value="gte">At or above</option><option value="lte">At or below</option><option value="gt">Above</option><option value="lt">Below</option><option value="eq">Equal</option></select>
          <label>Distance <input :value="breadthComparisonThreshold" aria-label="Breadth prior high low threshold" type="number" step="0.001" @input="setBreadthNumber('breadth_comparison_threshold', $event)" @change="setBreadthNumber('breadth_comparison_threshold', $event)" /></label>
        </template>
        <template v-else-if="breadthConditionKind === 'trend'">
          <label>Fast <input :value="breadthConditionFastPeriod" aria-label="Breadth trend fast period" type="number" min="2" max="100" @input="setBreadthNumber('breadth_condition_fast_period', $event)" @change="setBreadthNumber('breadth_condition_fast_period', $event)" /></label>
          <label>Slow <input :value="breadthConditionSlowPeriod" aria-label="Breadth trend slow period" type="number" min="3" max="252" @input="setBreadthNumber('breadth_condition_slow_period', $event)" @change="setBreadthNumber('breadth_condition_slow_period', $event)" /></label>
          <select :value="breadthConditionDirection" aria-label="Breadth trend direction" @change="setBreadthConfiguration({ breadth_condition_direction: ($event.target as HTMLSelectElement).value })"><option value="up">Uptrend</option><option value="down">Downtrend</option></select>
        </template>
        <template v-else-if="breadthConditionKind === 'rsi'">
          <label>Period <input :value="breadthConditionRsiPeriod" aria-label="Breadth RSI period" type="number" min="2" max="252" @input="setBreadthNumber('breadth_condition_rsi_period', $event)" @change="setBreadthNumber('breadth_condition_rsi_period', $event)" /></label>
          <select :value="breadthComparisonOperator" aria-label="Breadth RSI operator" @change="setBreadthConfiguration({ breadth_comparison_operator: ($event.target as HTMLSelectElement).value })"><option value="gte">At or above</option><option value="lte">At or below</option><option value="gt">Above</option><option value="lt">Below</option></select>
          <label>Target <input :value="breadthComparisonThreshold" aria-label="Breadth RSI target" type="number" min="0" max="100" step="0.1" @input="setBreadthNumber('breadth_comparison_threshold', $event)" @change="setBreadthNumber('breadth_comparison_threshold', $event)" /></label>
        </template>
        <template v-else-if="breadthConditionKind === 'volume_ratio'">
          <label>Period <input :value="breadthConditionVolumePeriod" aria-label="Breadth volume ratio period" type="number" min="2" max="252" @input="setBreadthNumber('breadth_condition_volume_period', $event)" @change="setBreadthNumber('breadth_condition_volume_period', $event)" /></label>
          <select :value="breadthComparisonOperator" aria-label="Breadth volume ratio operator" @change="setBreadthConfiguration({ breadth_comparison_operator: ($event.target as HTMLSelectElement).value })"><option value="gte">At or above</option><option value="lte">At or below</option><option value="gt">Above</option><option value="lt">Below</option></select>
          <label>Target <input :value="breadthComparisonThreshold" aria-label="Breadth volume ratio target" type="number" min="0" step="0.1" @input="setBreadthNumber('breadth_comparison_threshold', $event)" @change="setBreadthNumber('breadth_comparison_threshold', $event)" /></label>
        </template>
        <template v-else-if="breadthConditionKind === 'relative_strength'">
          <label>Lookback <input :value="breadthConditionLookback" aria-label="Breadth relative strength lookback" type="number" min="2" max="252" @input="setBreadthNumber('breadth_condition_lookback', $event)" @change="setBreadthNumber('breadth_condition_lookback', $event)" /></label>
          <select :value="breadthComparisonOperator" aria-label="Breadth relative strength operator" @change="setBreadthConfiguration({ breadth_comparison_operator: ($event.target as HTMLSelectElement).value })"><option value="gte">At or above</option><option value="lte">At or below</option><option value="gt">Above</option><option value="lt">Below</option></select>
          <label>Target <input :value="breadthComparisonThreshold" aria-label="Breadth relative strength target" type="number" step="0.001" @input="setBreadthNumber('breadth_comparison_threshold', $event)" @change="setBreadthNumber('breadth_comparison_threshold', $event)" /></label>
        </template>
        <template v-if="breadthConditionKind === 'comparison'">
          <select :value="breadthComparisonField" aria-label="Breadth measured field" @change="setBreadthConfiguration({ breadth_comparison_field: ($event.target as HTMLSelectElement).value })">
            <option value="close">Close</option>
            <option value="return">One-period return</option>
            <option value="volume">Volume</option>
            <option value="rsi">RSI</option>
            <option value="distance_to_52w_high">Distance to 52-week high</option>
            <option value="distance_to_52w_low">Distance to 52-week low</option>
            <option value="relative_strength">Relative strength</option>
          </select>
          <select :value="breadthComparisonOperator" aria-label="Breadth target operator" @change="setBreadthConfiguration({ breadth_comparison_operator: ($event.target as HTMLSelectElement).value })">
            <option value="gte">At or above</option>
            <option value="lte">At or below</option>
            <option value="gt">Above</option>
            <option value="lt">Below</option>
            <option value="eq">Equal to</option>
          </select>
          <label>Target <input :value="breadthComparisonThreshold" aria-label="Breadth target threshold" type="number" step="0.001" @input="setBreadthNumber('breadth_comparison_threshold', $event)" @change="setBreadthNumber('breadth_comparison_threshold', $event)" /></label>
        </template>
        <template v-else-if="breadthConditionKind === 'series_comparison'">
          <select :value="breadthSeriesMemberField" aria-label="Breadth series member field" @change="setBreadthConfiguration({ breadth_series_member_field: ($event.target as HTMLSelectElement).value })">
            <option value="close">Member close</option>
            <option value="return">Member return</option>
            <option value="volume">Member volume</option>
            <option value="rsi">Member RSI</option>
            <option value="distance_to_52w_high">Member distance to 52-week high</option>
            <option value="distance_to_52w_low">Member distance to 52-week low</option>
          </select>
          <select :value="breadthSeriesReferenceField" aria-label="Breadth series reference field" @change="setBreadthConfiguration({ breadth_series_reference_field: ($event.target as HTMLSelectElement).value })">
            <option value="close">Reference close</option>
            <option value="return">Reference return</option>
            <option value="volume">Reference volume</option>
            <option value="rsi">Reference RSI</option>
            <option value="distance_to_52w_high">Reference distance to 52-week high</option>
            <option value="distance_to_52w_low">Reference distance to 52-week low</option>
          </select>
          <select :value="breadthSeriesRelation" aria-label="Breadth series relation" @change="setBreadthConfiguration({ breadth_series_relation: ($event.target as HTMLSelectElement).value })"><option value="difference">Difference</option><option value="ratio">Ratio minus one</option></select>
          <select :value="breadthComparisonOperator" aria-label="Breadth series operator" @change="setBreadthConfiguration({ breadth_comparison_operator: ($event.target as HTMLSelectElement).value })"><option value="gte">At or above</option><option value="lte">At or below</option><option value="gt">Above</option><option value="lt">Below</option><option value="eq">Equal to</option></select>
          <label>Threshold <input :value="breadthComparisonThreshold" aria-label="Breadth series threshold" type="number" step="0.001" @input="setBreadthNumber('breadth_comparison_threshold', $event)" @change="setBreadthNumber('breadth_comparison_threshold', $event)" /></label>
        </template>
        <template v-else-if="breadthConditionKind === 'event'">
          <select :value="breadthEventType" aria-label="Breadth event type" @change="setBreadthConfiguration({ breadth_event_type: ($event.target as HTMLSelectElement).value })">
            <option value="any">Any event</option>
            <option value="earnings">Earnings</option>
            <option value="dividend">Dividend</option>
            <option value="ex_dividend">Ex-dividend</option>
            <option value="split">Split</option>
          </select>
          <label>Lookback days <input :value="breadthEventLookbackDays" aria-label="Breadth event lookback days" type="number" min="0" max="3660" @input="setBreadthNumber('breadth_event_lookback_days', $event)" @change="setBreadthNumber('breadth_event_lookback_days', $event)" /></label>
          <label><input type="checkbox" :checked="breadthEventIncludeEstimates" aria-label="Breadth include event estimates" @change="setBreadthConfiguration({ breadth_event_include_estimates: ($event.target as HTMLInputElement).checked })" /> Include estimates</label>
          <select :value="breadthComparisonOperator" aria-label="Breadth event operator" @change="setBreadthConfiguration({ breadth_comparison_operator: ($event.target as HTMLSelectElement).value })"><option value="gte">Occurred</option><option value="lt">Did not occur</option></select>
        </template>
        <template v-else-if="breadthConditionKind === 'range'">
          <select :value="breadthRangeField" aria-label="Breadth range measured field" @change="setBreadthConfiguration({ breadth_range_field: ($event.target as HTMLSelectElement).value })">
            <option value="close">Close</option>
            <option value="return">One-period return</option>
            <option value="volume">Volume</option>
            <option value="distance_to_52w_high">Distance to 52-week high</option>
          </select>
          <label>Min <input :value="breadthRangeLower" aria-label="Breadth range lower bound" type="number" step="0.001" @input="setBreadthNumber('breadth_range_lower', $event)" @change="setBreadthNumber('breadth_range_lower', $event)" /></label>
          <label>Max <input :value="breadthRangeUpper" aria-label="Breadth range upper bound" type="number" step="0.001" @input="setBreadthNumber('breadth_range_upper', $event)" @change="setBreadthNumber('breadth_range_upper', $event)" /></label>
        </template>
        <template v-else-if="breadthConditionKind === 'percentile'">
          <select :value="breadthPercentileScope" aria-label="Breadth percentile target scope" @change="setBreadthConfiguration({ breadth_percentile_scope: ($event.target as HTMLSelectElement).value })">
            <option value="member">Member rolling percentile</option>
            <option value="cross_sectional">Cross-sectional rank percentile</option>
          </select>
          <select :value="breadthPercentileField" aria-label="Breadth percentile measured field" @change="setBreadthConfiguration({ breadth_percentile_field: ($event.target as HTMLSelectElement).value })">
            <option value="close">Close</option>
            <option value="return">One-period return</option>
            <option value="volume">Volume</option>
            <option value="moving_average_distance">Moving-average distance</option>
          </select>
          <label>Window <input :value="breadthPercentilePeriod" aria-label="Breadth percentile rolling window" type="number" min="2" max="5000" @input="setBreadthNumber('breadth_percentile_period', $event)" @change="setBreadthNumber('breadth_percentile_period', $event)" /></label>
          <select :value="breadthComparisonOperator" aria-label="Breadth percentile operator" @change="setBreadthConfiguration({ breadth_comparison_operator: ($event.target as HTMLSelectElement).value })"><option value="gte">At or above</option><option value="lte">At or below</option><option value="gt">Above</option><option value="lt">Below</option></select>
          <label>Percentile <input :value="breadthPercentileTarget" aria-label="Breadth percentile target" type="number" min="0" max="1" step="0.01" @input="setBreadthNumber('breadth_percentile_target', $event)" @change="setBreadthNumber('breadth_percentile_target', $event)" /></label>
        </template>
        <template v-else-if="breadthConditionKind === 'cross_sectional_statistic'">
          <select value="cross_sectional" aria-label="Breadth group statistic target scope" disabled><option value="cross_sectional">Cross-sectional group</option></select>
          <select :value="breadthComparisonField" aria-label="Breadth group statistic measured field" @change="setBreadthConfiguration({ breadth_comparison_field: ($event.target as HTMLSelectElement).value })">
            <option value="close">Close</option>
            <option value="return">One-period return</option>
            <option value="volume">Volume</option>
            <option value="moving_average_distance">Moving-average distance</option>
          </select>
          <select :value="String(breadthConfigurationValue('breadth_cross_sectional_statistic', 'mean'))" aria-label="Breadth group statistic function" @change="setBreadthConfiguration({ breadth_cross_sectional_statistic: ($event.target as HTMLSelectElement).value })"><option value="mean">Mean</option><option value="median">Median</option><option value="min">Minimum</option><option value="max">Maximum</option><option value="std">Standard deviation</option></select>
          <select :value="breadthComparisonOperator" aria-label="Breadth group statistic operator" @change="setBreadthConfiguration({ breadth_comparison_operator: ($event.target as HTMLSelectElement).value })"><option value="gte">At or above</option><option value="lte">At or below</option><option value="gt">Above</option><option value="lt">Below</option><option value="eq">Equal</option></select>
          <label>Difference <input :value="breadthComparisonThreshold" aria-label="Breadth group statistic difference" type="number" step="0.001" @input="setBreadthNumber('breadth_comparison_threshold', $event)" @change="setBreadthNumber('breadth_comparison_threshold', $event)" /></label>
        </template>
        <template v-if="breadthComposition === 'all' || breadthComposition === 'any'">
          <span class="breadth-tool__composition-note">+ measured-field target</span>
          <select :value="breadthSecondaryField" aria-label="Breadth second measured field" @change="setBreadthConfiguration({ breadth_secondary_field: ($event.target as HTMLSelectElement).value })">
            <option value="return">Return</option>
            <option value="close">Close</option>
            <option value="volume">Volume</option>
            <option value="rsi">RSI</option>
            <option value="volume_ratio">Volume ratio</option>
            <option value="distance_to_52w_high">Distance to 52-week high</option>
            <option value="relative_strength">Relative strength</option>
          </select>
          <label>Target <input :value="breadthSecondaryThreshold" aria-label="Breadth second target threshold" type="number" step="0.001" @change="setBreadthConfiguration({ breadth_secondary_threshold: Number(($event.target as HTMLInputElement).value) })" /></label>
        </template>
        </template>
        <button type="button" :disabled="(breadthConditionKind === 'python_series' && breadthPythonSeriesCodeVersionId == null) || (breadthComposition === 'tree' && breadthTreePythonSeriesLeaf !== null && pythonLeafAnchorId(breadthTreePythonSeriesLeaf) == null)" @click="runGenericBreadth">Evaluate</button>
        <span v-if="genericBreadthLoading" role="status" aria-live="polite">Evaluating…</span>
        <span v-else-if="genericBreadthError" class="breadth-tool__status--error" role="alert">{{ genericBreadthError }}</span>
        <span v-else-if="genericBreadth" class="breadth-tool__custom-result"><b>{{ genericBreadthPercentage }}</b> · {{ genericBreadth.pass_count }}/{{ genericBreadth.eligible_count }} eligible · {{ genericBreadthCoverage }} coverage<span v-if="genericBreadth.group_value != null"> · group {{ genericBreadth.group_value.toFixed(4) }}</span></span>
        <div v-if="genericBreadth && !breadthUsesPython" class="breadth-tool__definition-actions" aria-label="Reusable breadth definition">
          <input v-model.trim="genericBreadthDefinitionName" aria-label="Breadth reusable definition name" placeholder="Definition name" maxlength="160" />
          <button type="button" :disabled="genericBreadthDefinitionSaving || !genericBreadthDefinitionName" @click="saveGenericBreadthDefinition">{{ genericBreadthDefinitionSaving ? 'Saving…' : 'Save as Study Lab definition' }}</button>
          <span v-if="genericBreadthDefinitionMessage" role="status">{{ genericBreadthDefinitionMessage }}</span>
          <span v-if="genericBreadthDefinitionError" class="breadth-tool__status--error" role="alert">{{ genericBreadthDefinitionError }}</span>
        </div>
      </div>
      <div v-if="isBenchmarkFamily" class="breadth-tool__family-ratios" aria-label="Benchmark family relative strength">
        <strong>Family relative strength</strong>
        <select :value="familyRatioRole" aria-label="Family ratio leg" @change="setBreadthConfiguration({ family_ratio_role: ($event.target as HTMLSelectElement).value })">
          <option value="equal_weight">Equal weight</option>
          <option value="value">Value</option>
          <option value="growth">Growth</option>
          <option value="cap_weight">Cap weight</option>
        </select>
        <label>Market <input :value="familyRatioMarket" aria-label="Family ratio market benchmark" maxlength="12" @change="setBreadthConfiguration({ family_ratio_market: ($event.target as HTMLInputElement).value.toUpperCase() })" /></label>
        <label>Rank period <select :value="familyRankPeriod" aria-label="Family ranking period" @change="setBreadthConfiguration({ family_rank_period: ($event.target as HTMLSelectElement).value })">
          <option v-for="period in familyRankPeriods" :key="period" :value="period">{{ period }}</option>
        </select></label>
        <span v-if="familyRatioLoading" role="status">Loading…</span>
        <span v-else-if="familyRatioError" class="breadth-tool__status--error" role="alert">{{ familyRatioError }}</span>
        <template v-else-if="familyRatios?.ratios?.length">
          <span v-for="ratio in familyRatios.ratios" :key="`${ratio.benchmark_role}:${ratio.benchmark}`" class="breadth-tool__family-ratio">
            <span>{{ ratio.symbol }}/{{ ratio.benchmark }}</span>
            <b>{{ latestFamilyRatio(ratio) }}</b>
            <small>{{ ratio.points.length }} points · {{ (ratio.coverage * 100).toFixed(0) }}%</small>
          </span>
        </template>
          <span v-else class="breadth-tool__status">No aligned family ratio data.</span>
          <BenchmarkFamilyRatioHistoryUPlot v-if="familyRatios" :ratios="familyRatios" />
        </div>
      <div v-if="isBenchmarkFamily" class="breadth-tool__family-technicals" aria-label="Benchmark family technicals">
        <strong>Family technicals</strong>
        <span v-if="familyTechnicalsLoading" role="status">Loading…</span>
        <span v-else-if="familyTechnicalError" class="breadth-tool__status--error" role="alert">{{ familyTechnicalError }}</span>
        <template v-else-if="familyTechnicals">
          <span v-for="role in familyTechnicals.roles" :key="role.role" class="breadth-tool__family-technical">
            <b>{{ familyRoleLabel(role.role) }}</b> {{ role.symbol ?? role.label }} · {{ familyTechnicalValue(role.last) }} · RSI {{ familyTechnicalValue(role.rsi14) }} · SMA50 {{ familyTechnicalValue(role.sma50) }}
          </span>
        </template>
        <span v-else class="breadth-tool__status">Family technicals unavailable.</span>
      </div>
      <div v-if="isBenchmarkFamily" class="breadth-tool__family-breadth" aria-label="Benchmark family participation">
        <strong>Role participation</strong>
        <span v-if="familyBreadthLoading" role="status">Loading…</span>
        <span v-else-if="familyBreadthError" class="breadth-tool__status--error" role="alert">{{ familyBreadthError }}</span>
        <template v-else-if="familyBreadth">
          <span v-for="role in familyBreadth.roles" :key="role.role" class="breadth-tool__family-breadth-role">
            <b>{{ familyRoleLabel(role.role) }}</b> {{ role.symbol ?? role.label }} · >20 {{ familyBreadthPercentage(role.above_ma.ma20) }} · near 52w {{ familyBreadthPercentage(role.near_52w_high) }} · trend {{ familyBreadthPercentage(role.trend_up) }}
          </span>
        </template>
        <span v-else class="breadth-tool__status">Role participation unavailable.</span>
        <span v-if="familyBreadthHistory" class="breadth-tool__family-breadth-history">History · {{ familyBreadthHistoryPointCount }} aligned points · {{ familyBreadthHistoryReadinessLabel }}</span>
        <BenchmarkFamilyBreadthHistoryUPlot v-if="familyBreadthHistory" :history="familyBreadthHistory" />
      </div>
      <div v-if="isBenchmarkFamily" class="breadth-tool__family-ranking" aria-label="Benchmark family role ranking">
        <strong>Role ranking · {{ familyRanking?.rank_period ?? '1M' }}</strong>
        <span v-if="familyRankingLoading" role="status">Loading…</span>
        <span v-else-if="familyRankingError" class="breadth-tool__status--error" role="alert">{{ familyRankingError }}</span>
        <template v-else-if="familyRanking">
          <span v-for="role in familyRanking.roles" :key="role.role" class="breadth-tool__family-ranking-role">
            <b>#{{ role.rank ?? '—' }}</b> {{ familyRoleLabel(role.role) }} {{ role.symbol ?? role.label }} · {{ familyBreadthPercentage({ percentage: role.performance[familyRankPeriod] }) }} · Δ {{ familyBreadthPercentage({ percentage: role.relative_performance[familyRankPeriod] }) }}
          </span>
        </template>
        <span v-else class="breadth-tool__status">Role ranking unavailable.</span>
      </div>
      <div v-if="isBenchmarkFamily" class="breadth-tool__family-concentration" aria-label="Benchmark family concentration">
        <strong>Leadership concentration · top {{ familyConcentration?.top_n ?? 10 }} · {{ familyConcentration?.rank_period ?? '1M' }} dispersion</strong>
        <span v-if="familyConcentrationLoading" role="status">Loading…</span>
        <span v-else-if="familyConcentrationError" class="breadth-tool__status--error" role="alert">{{ familyConcentrationError }}</span>
        <template v-else-if="familyConcentration">
          <span v-for="role in familyConcentration.roles.filter(item => item.available)" :key="role.role" class="breadth-tool__family-concentration-role">
            <b>{{ familyRoleLabel(role.role) }}</b> {{ role.symbol ?? role.label }} · top {{ formatPercent(role.top_n_weight) }} · HHI {{ formatNumber(role.hhi) }} · effective {{ formatNumber(role.effective_constituents) }} · σ {{ formatPercent(role.dispersion) }} · {{ formatPercent(role.coverage) }} covered
          </span>
          <span v-if="!familyConcentration.roles.some(item => item.available)" class="breadth-tool__status">No concentration data available.</span>
        </template>
        <span v-else class="breadth-tool__status">Concentration unavailable.</span>
        <span v-if="familyConcentrationHistoryLoading" role="status">Loading history…</span>
        <span v-else-if="familyConcentrationHistoryError" class="breadth-tool__status--error" role="alert">{{ familyConcentrationHistoryError }}</span>
        <span v-else-if="familyConcentrationHistory" class="breadth-tool__family-concentration-history">History · {{ familyConcentrationHistoryPointCount }} points · {{ familyConcentrationHistoryMode }}</span>
        <BenchmarkFamilyConcentrationHistoryUPlot v-if="familyConcentrationHistory" :history="familyConcentrationHistory" />
        <BenchmarkFamilyConcentrationMetricsHistoryUPlot v-if="familyConcentrationHistory" :history="familyConcentrationHistory" />
      </div>
      <div v-if="isBenchmarkFamily" class="breadth-tool__cross-family-ranking" aria-label="Cross-family ranking">
        <strong>US family ranking · {{ crossFamilyRanking?.rank_period ?? '1M' }}</strong>
        <span v-if="crossFamilyRankingLoading" role="status">Loading…</span>
        <span v-else-if="crossFamilyRankingError" class="breadth-tool__status--error" role="alert">{{ crossFamilyRankingError }}</span>
        <template v-else-if="crossFamilyRanking">
          <span v-for="row in crossFamilyRanking.rows.filter(item => item.available).slice(0, 4)" :key="row.family_key" class="breadth-tool__cross-family-ranking-row">
            <b>#{{ row.rank ?? '—' }}</b> {{ row.family_name }} {{ row.symbol ?? row.label }} · {{ familyBreadthPercentage({ percentage: row.performance[familyRankPeriod] }) }}
          </span>
        </template>
        <span v-else class="breadth-tool__status">Cross-family ranking unavailable.</span>
        <span v-if="crossFamilyRankingHistoryLoading" role="status">Loading history…</span>
        <span v-else-if="crossFamilyRankingHistoryError" class="breadth-tool__status--error" role="alert">{{ crossFamilyRankingHistoryError }}</span>
        <span v-if="crossFamilyRankingHistory" class="breadth-tool__cross-family-ranking-history">History · {{ crossFamilyRankingHistoryPointCount }} points</span>
        <CrossFamilyRankingHistoryUPlot v-if="crossFamilyRankingHistory" :history="crossFamilyRankingHistory" />
        <CrossFamilyRankHistoryUPlot v-if="crossFamilyRankingHistory" :history="crossFamilyRankingHistory" />
      </div>
      <section v-if="isBenchmarkFamily" class="breadth-tool__family-overview" aria-label="Benchmark family analysis">
        <header class="breadth-tool__family-overview-header">
          <strong>{{ familyOverview?.name ?? breadthGroupKey }} · {{ familyOverview?.official_index_symbol ?? 'official index' }}</strong>
          <span v-if="familyOverview">{{ familyOverview.coverage == null ? 'Coverage unavailable' : `${(familyOverview.coverage * 100).toFixed(0)}% covered` }} · {{ familyOverview.freshness ?? 'unavailable' }}</span>
          <span v-else-if="familyOverviewLoading" role="status">Loading family evidence…</span>
          <span v-else-if="familyOverviewError" class="breadth-tool__status--error" role="alert">{{ familyOverviewError }}</span>
          <span v-else>Family evidence unavailable.</span>
        </header>
        <div v-if="familyOverview" class="breadth-tool__family-legs">
          <article v-for="mapping in familyOverview.mappings" :key="mapping.role" class="breadth-tool__family-leg" :class="{ 'breadth-tool__family-leg--selected': mapping.role === familyRatioRole }">
            <div><b>{{ familyRoleLabel(mapping.role) }}</b><span>{{ mapping.symbol ?? mapping.label }}</span></div>
            <small>{{ familyMappingState(mapping) }}</small>
            <button type="button" :disabled="!mapping.holdings_available" :aria-label="`Load ${familyRoleLabel(mapping.role)} constituents`" @click="setBreadthConfiguration({ family_ratio_role: mapping.role })">Constituents</button>
          </article>
        </div>
        <div v-if="familyCoverage" class="breadth-tool__family-coverage" aria-label="Benchmark family historical coverage">
          <strong>Dated holdings coverage</strong>
          <span>{{ familyCoverage.coverage == null ? 'Unavailable' : `${(familyCoverage.coverage * 100).toFixed(0)}% of roles` }} · {{ familyCoverage.as_of ? `known at ${familyCoverage.as_of}` : 'latest available disclosures' }}</span>
          <label>As of <select :value="familyAsOf" aria-label="Family analysis as of" @change="setBreadthConfiguration({ as_of: (($event.target as HTMLSelectElement).value || null) })"><option value="">Latest</option><option v-for="date in familyCoverageDates" :key="date" :value="familyAsOfValue(date)">{{ date }}</option></select></label>
          <div class="breadth-tool__family-coverage-roles">
            <span v-for="role in familyCoverage.roles" :key="role.role">
          <b>{{ familyRoleLabel(role.role) }}</b> {{ role.symbol ?? role.label }} · {{ role.status }} · {{ role.snapshots.length }} date{{ role.snapshots.length === 1 ? '' : 's' }} · {{ familyContinuityLabel(role) }} · {{ familyLatestDisclosureLabel(role) }} · bars {{ familyMemberBarHistoryLabel(role) }} · readiness {{ role.composite_readiness_status ?? 'unknown' }}{{ familyReadinessReasonsLabel(role) }} · route {{ familyRouteLabel(role) }} · entitlement {{ familyEntitlementLabel(role) }} · refresh {{ familyRefreshLabel(role) }} · weights {{ role.weights_status ?? 'unknown' }} · classification {{ role.classification_status ?? 'unknown' }}{{ role.placeholder_member_count ? ` · placeholders ${role.placeholder_member_count}` : '' }}
            </span>
          </div>
          <span class="sr-only" aria-label="Benchmark family canonical role evidence">{{ familyCanonicalRoleEvidenceLabel(familyCoverage) }}</span>
        </div>
        <p v-else-if="familyCoverageError" class="breadth-tool__status breadth-tool__status--error" role="alert">{{ familyCoverageError }}</p>
        <div v-if="familyConstituents" class="breadth-tool__family-constituents">
          <div class="breadth-tool__family-constituents-header">
            <strong>{{ familyRoleLabel(familyRatioRole) }} constituents · {{ familyConstituents.etf_symbol }}</strong>
            <span>{{ familyConstituents.composition_date }} · {{ familyConstituents.source_provider }} · {{ familyConstituents.rows.length }} rows</span>
          </div>
          <button v-for="row in familyConstituents.rows.slice(0, 100)" :key="row.instrument_id" type="button" @click="emit('select', row.symbol, row.instrument_id)">
            <strong>{{ row.symbol }}</strong><span>{{ row.name }}</span><small v-if="row.weight != null">{{ Number(row.weight).toFixed(2) }}%</small>
          </button>
          <small v-if="!familyConstituents.rows.length">No resolved constituent rows are available.</small>
        </div>
        <p v-else-if="familyConstituentError" class="breadth-tool__status breadth-tool__status--error" role="alert">{{ familyConstituentError }}</p>
      </section>
      <section v-if="genericBreadthDiagnostics.length" class="breadth-tool__generic-diagnostics" aria-label="Generic breadth clause diagnostics">
        <header><strong>Clause diagnostics</strong><span>{{ genericBreadthDiagnostics.length }} clauses</span></header>
        <div v-for="(diagnostic, index) in genericBreadthDiagnostics" :key="`${diagnostic.path}-${index}`">{{ genericBreadthDiagnosticLabel(diagnostic) }}</div>
      </section>
      <div v-if="genericBreadth" class="breadth-tool__generic-drilldown" aria-label="Generic breadth member drilldown">
        <header>
          <strong>{{ genericBreadthMemberState === 'pass' ? 'Passing' : 'Failing' }} members</strong>
          <span class="breadth-tool__actions">
            <button type="button" :class="{ 'breadth-tool__action--active': genericBreadthMemberState === 'pass' }" @click="genericBreadthMemberState = 'pass'">Pass {{ genericBreadth.pass_count }}</button>
            <button type="button" :class="{ 'breadth-tool__action--active': genericBreadthMemberState === 'fail' }" @click="genericBreadthMemberState = 'fail'">Fail {{ genericBreadth.eligible_count - genericBreadth.pass_count }}</button>
          </span>
        </header>
        <button v-for="member in genericBreadthMembers.slice(0, 100)" :key="member.instrument_id" type="button" @click="emit('select', member.symbol, member.instrument_id)"><strong>{{ member.symbol }}</strong><span>{{ member.name }}</span><small v-if="member.metric != null">{{ member.metric.toFixed(3) }}</small><small v-if="member.diagnostics?.length" class="breadth-tool__member-diagnostics" :title="member.diagnostics.map(genericBreadthDiagnosticLabel).join(' · ')">{{ member.diagnostics.map(genericBreadthDiagnosticLabel).join(' · ') }}</small></button>
        <small v-if="!genericBreadthMembers.length">No {{ genericBreadthMemberState === 'pass' ? 'passing' : 'failing' }} members are eligible.</small>
      </div>
      <GenericBreadthHistoryUPlot :history="genericBreadthHistory ?? undefined" />
      <section v-if="genericBreadthHistory" class="breadth-tool__generic-history-events" aria-label="Generic breadth historical occurrences">
        <header>
          <strong>Member state changes</strong>
          <span>{{ genericBreadthHistoryOccurrences.length }} shown · click to publish</span>
        </header>
        <button v-for="occurrence in genericBreadthHistoryOccurrences" :key="occurrence.occurrence_id" type="button" :aria-label="`${occurrence.symbol} ${genericBreadthOccurrenceLabel(occurrence)} ${occurrence.timestamp}`" @click="emit('occurrence', occurrence.symbol, occurrence.timestamp, occurrence.instrument_id)">
          <strong>{{ occurrence.symbol }}</strong>
          <span>{{ genericBreadthOccurrenceLabel(occurrence) }} · {{ occurrence.timestamp }}</span>
          <small v-if="occurrence.percentage != null">{{ (occurrence.percentage * 100).toFixed(1) }}%</small>
        </button>
        <small v-if="!genericBreadthHistoryOccurrences.length">No member state changes were recorded for this history.</small>
      </section>
      <p v-if="breadthBusy" class="breadth-tool__status" role="status" aria-live="polite" aria-atomic="true">Loading breadth analysis…</p>
      <p v-else-if="breadthError" class="breadth-tool__status breadth-tool__status--error" role="alert" aria-live="assertive" aria-atomic="true">{{ breadthError }}</p>
      <p v-else-if="!breadth" class="breadth-tool__status" role="status" aria-live="polite" aria-atomic="true">Breadth analysis is unavailable.</p>
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
        <button v-for="row in breadthDrilldownRows" :key="row.symbol" type="button" @click="emit('select', row.symbol, row.instrumentId)"><strong>{{ row.symbol }}</strong><span>{{ row.name }}</span></button>
        <small v-if="!breadthDrilldownRows.length">No locally evaluated members are available.</small>
      </div>
      <BreadthHistoryUPlot :history="breadthHistory" />
    </div>
    <RelativeRotationTool v-else-if="tool.instance_key === 'relative-rotation' || tool.tool_type === 'relative_rotation'" :configuration="tool.configuration" @select="selectRotationSymbol" @configuration="emit('configuration', tool.instance_key, $event)" />
    <MarketMapTool v-else-if="tool.tool_type === 'market_map'" :configuration="tool.configuration" @configuration="emit('configuration', tool.instance_key, $event)" @select="(symbol, instrumentId) => selectSymbol(symbol, instrumentId)" @compare="emit('compare', $event)" @ratio="emit('ratio', $event)" @publish-analysis="emit('publishAnalysis', $event)" />
    <div v-else-if="tool.instance_key === 'technical-summary' || tool.tool_type === 'technical_summary'" class="metrics">
      <span>RSI(14)</span><b>{{ formatNumber(technical?.rsi14) }}</b>
      <span>20 / 50 / 200 MA</span><b>{{ technicalMAs }}</b>
      <span>52-week position</span><b>{{ formatPercent(technical?.position_52w) }}</b>
      <span>Volume ratio (50)</span><b>{{ formatRatio(technical?.volume_ratio_50) }}</b>
    </div>
    <CoverageSummaryTool v-else-if="tool.instance_key === 'coverage-summary' || tool.tool_type === 'coverage'" :symbol="activeSymbol" :configuration="tool.configuration" @configuration="emit('configuration', tool.instance_key, $event)" />
    <InstrumentNoteTool v-else-if="tool.tool_type === 'notes'" :instrument-id="toolInstrument?.id ?? chartStore.instrument?.id" :symbol="activeSymbol" />
    <InstrumentAlertsTool v-else-if="tool.tool_type === 'alerts'" :instrument-id="toolInstrument?.id ?? chartStore.instrument?.id" :symbol="activeSymbol" :timeframe="activeTimeframe" />
    <InstrumentInfoPanel v-else-if="tool.tool_type === 'report'" class="instrument-report" :instrument="toolInstrument ?? chartStore.instrument" :current-price="currentPrice" :session-high="currentSessionHigh" :session-low="currentSessionLow" @select="(symbol, instrumentId) => selectSymbol(symbol, instrumentId)" />
    <EasyScanTool v-else-if="tool.tool_type === 'scan'" :source-window-key="tool.instance_key" />
    <MarketGaugeTool v-else-if="tool.tool_type === 'gauge'" />
    <StudyLabTool v-else-if="tool.tool_type === 'study_lab'" :tool-key="tool.instance_key" :active-symbol="activeSymbol" :configuration="tool.configuration" @configuration="emit('configuration', tool.instance_key, $event)" @occurrence="emit('occurrence', $event.symbol, $event.timestamp)" />
    <ResearchResultsTool v-else-if="tool.tool_type === 'research_results'" @occurrence="emit('occurrence', $event.symbol, $event.timestamp, $event.instrument_id)" />
    <CodeLibraryTool v-else-if="tool.tool_type === 'code_library'" />
    <UnknownToolRecovery v-else :tool="tool" />
  </ToolWindow>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, provide, ref, watch } from 'vue'
import { useQueryClient } from '@tanstack/vue-query'
import { api } from '@/lib/api'
import { fetchCanonicalInstrument } from '@/lib/workstation/instrumentQueries'
import { dedupeOhlcvRequest } from '@/lib/workstation/ohlcvRequests'
import UPlotChart from '@/components/chart/UPlotChart.vue'
import DrawingToolbar from '@/components/chart/DrawingToolbar.vue'
import ChartTemplateControl from './ChartTemplateControl.vue'
import ChartPlotLibrary from './ChartPlotLibrary.vue'
import { usePanelStore } from '@/stores/chart'
import { useDrawingsStore } from '@/stores/drawings'
import { useAlertsStore } from '@/stores/alerts'
import { useWorkspaceStore, type BenchmarkFamilyReadinessState, type GenericBreadthHistoryState, type GenericBreadthState, type GroupSnapshotRow, type LinkGroup, type WorkspaceWindowState } from '@/stores/workspace'
import { useWatchlistStore } from '@/stores/watchlist'
import type { Instrument, Watchlist, WatchlistSource } from '@/types'
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
import BenchmarkFamilyBreadthHistoryUPlot from './BenchmarkFamilyBreadthHistoryUPlot.vue'
import BenchmarkFamilyRatioHistoryUPlot from './BenchmarkFamilyRatioHistoryUPlot.vue'
import BenchmarkFamilyConcentrationHistoryUPlot from './BenchmarkFamilyConcentrationHistoryUPlot.vue'
import BenchmarkFamilyConcentrationMetricsHistoryUPlot from './BenchmarkFamilyConcentrationMetricsHistoryUPlot.vue'
import CrossFamilyRankingHistoryUPlot from './CrossFamilyRankingHistoryUPlot.vue'
import CrossFamilyRankHistoryUPlot from './CrossFamilyRankHistoryUPlot.vue'
import GenericBreadthHistoryUPlot from './GenericBreadthHistoryUPlot.vue'
import RelativeRotationTool from './RelativeRotationTool.vue'
import MarketMapTool from './MarketMapTool.vue'
import InstrumentInfoPanel from '@/components/chart/InstrumentInfoPanel.vue'
import ResearchResultsTool from './ResearchResultsTool.vue'
import CodeLibraryTool from './CodeLibraryTool.vue'
import CoverageSummaryTool from './CoverageSummaryTool.vue'
import BreadthConditionTreeEditor from './BreadthConditionTreeEditor.vue'
import { fetchCodeAssets, type CodeAssetSummary } from '@/lib/workstation/libraryQueries'
import { calendarYearKeys } from '@/lib/workstation/calendarYears'
import { buildNormalizedComparisonSeries, type ComparisonTarget } from '@/lib/workstation/comparison'
import { normalizeNumericSeries } from '@/lib/workstation/numericSeries'
import { ensureKnownInstrumentSymbol } from '@/lib/instruments'
import { INDICATOR_BY_TYPE } from '@/lib/indicators/catalog'
import { buildFlaggedWatchlistRows } from '@/lib/workstation/flagged-watchlist'
import { buildComboWatchlistRows, type ComboListDefinition } from '@/lib/workstation/combo-lists'
import { autoRatioBenchmarks, autoRatioExpression } from '@/lib/workstation/ratioExpression'
import { indicatorColumnFromPlot, pythonColumnFromPlot, type ChartAnalysisDragPayload, type ChartPlotDragPayload, type TechnicalConditionDragPayload } from '@/lib/workstation/plotDrag'
import { formatWorkstationFreshness } from '@/lib/workstation/freshness'
import { benchmarkFamilyConstituentSourceId } from '@/lib/workstation/benchmarkFamilySources'
import { buildBreadthStudyAssetPayload, type BreadthDefinition } from '@/lib/workstation/breadthDefinitions'
import { CHART_BAR_TYPES, type ChartBarType, type ChartComparisonSeries, type ChartPythonSeries, type IndicatorConfig, type OHLCVBar, type Timeframe } from '@/types'

// Golden Layout can temporarily retain multiple virtual roots for one tool.
// Keep the latest name-editor owner module-wide so a stale root cannot replay
// an older draft after a newer visible root has received the user's input.
let latestPersonalListDraft = ''
const latestCreatedPersonalWatchlistId = ref<number | null>(null)
let latestCreatedPersonalWatchlistTimer: ReturnType<typeof setTimeout> | null = null
const pendingPersonalWatchlistSelections = new Map<string, number | string | null>()
const pendingPersonalWatchlistSelectionTimers = new Map<string, ReturnType<typeof setTimeout>>()

function fenceLatestPersonalWatchlistSelection(id: number | null) {
  latestCreatedPersonalWatchlistId.value = id
  if (latestCreatedPersonalWatchlistTimer !== null) clearTimeout(latestCreatedPersonalWatchlistTimer)
  latestCreatedPersonalWatchlistTimer = id == null ? null : setTimeout(() => {
    latestCreatedPersonalWatchlistId.value = null
    latestCreatedPersonalWatchlistTimer = null
  }, 30_000)
}

const props = defineProps<{
  tool: WorkspaceWindowState
  activeWindowKey?: string | null
  factoryLayout?: string | null
}>()
const emit = defineEmits<{ select: [symbol: string, instrumentId?: number | null]; compare: [symbols: string[]]; ratio: [symbols: string[]]; marketMap: [sourceId: string]; reorder: [watchlistId: number, itemIds: number[]]; rowAction: [action: 'chart' | 'compare' | 'ratio' | 'note' | 'alert' | 'copy', row: { symbol: string; instrumentId: number | null }]; occurrence: [symbol: string, timestamp: string, instrumentId?: number | null]; selectIndustry: [industry: string, etf: string]; selectProxy: [symbol: string, instrumentId?: number | null]; columns: [windowKey: string, keys: string[]]; filter: [windowKey: string, value: string]; conditionFilter: [windowKey: string, screenerId: number | null]; conditionFilterMode: [windowKey: string, mode: 'active' | 'inactive' | 'off']; pinnedBooleanKeys: [windowKey: string, keys: string[]]; columnGroups: [windowKey: string, groups: Record<string, string>]; stackedColumnKeys: [windowKey: string, keys: string[]]; configuration: [windowKey: string, configuration: Record<string, unknown>]; publishAnalysis: [payload: { target: 'breadth' | 'study_lab'; sourceId: string; selectedIds: number[]; selectedSymbols: string[]; scope: 'full' | 'selection' }]; timeframe: [value: string, group: LinkGroup]; float: [windowKey: string]; maximize: [windowKey: string]; close: [windowKey: string]; updateLinkGroup: [windowKey: string, group: LinkGroup, displayedSymbol?: string] }>()
// Inputs in dense breadth authoring can emit several configuration updates before
// Golden Layout delivers the parent prop patch. Keep a local draft so a rapid
// select/edit/evaluate sequence cannot serialize a stale sibling value.
const breadthDraftConfiguration = ref<Record<string, unknown>>({})
// Configuration edits are emitted through a debounced, revisioned workspace
// snapshot. Keep the local draft authoritative while the mounted virtual tool
// is still backed by the same configuration object: an older snapshot response
// must not restore a shared-control default (for example percentile period
// 252) over a value the user just entered. A factory reset/workspace reload
// replaces the configuration object, which is the safe boundary for clearing
// this draft.
let breadthDraftOwner = props.tool.configuration
function breadthConfigurationValue(key: string, fallback?: unknown) {
  if (Object.prototype.hasOwnProperty.call(breadthDraftConfiguration.value, key)) {
    return breadthDraftConfiguration.value[key]
  }
  return props.tool.configuration[key] ?? fallback
}
watch(() => props.tool.configuration, nextConfiguration => {
  // WorkstationToolContent mutates the live configuration object for normal
  // edits. Remote hydration/reset replaces that object; discard a draft only
  // at that explicit identity boundary, never merely because one snapshot
  // happened to echo a value back.
  if (nextConfiguration !== breadthDraftOwner) {
    breadthDraftOwner = nextConfiguration
    breadthDraftConfiguration.value = {}
  }
}, { deep: true })
// uPlot already consumes a panel-scoped store through injection. Give every persisted
// workstation chart its own stable store identity so red/grey/yellow charts cannot
// accidentally render the shell's blue/default data.
const chartPanelId = `workstation-${props.tool.instance_key}`
const localLinkGroup = ref<LinkGroup>(props.tool.link_group)
watch(() => props.tool.link_group, group => { localLinkGroup.value = group })
function handleLinkGroupChange(group: LinkGroup) {
  localLinkGroup.value = group
  emit('updateLinkGroup', props.tool.instance_key, group, activeSymbol.value)
}
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
const effectiveSelectedPersonalWatchlistId = computed(() => latestCreatedPersonalWatchlistId.value ?? selectedPersonalWatchlistId.value)
const selectedPersonalWatchlist = computed<Watchlist | null>(() => personalWatchlists.value.find(watchlist => watchlist.id === effectiveSelectedPersonalWatchlistId.value) ?? null)
function explicitMarketMapSourceId(rows: Array<{ instrumentId: number | null }>): string | null {
  const ids = [...new Set(rows.map(row => row.instrumentId).filter(id => id != null && Number.isInteger(id) && id > 0))] as number[]
  return ids.length ? `explicit:${ids.join(',')}` : null
}
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
const personalMarketMapSourceId = computed(() => {
  if (selectedCombo.value) return `combo:${selectedCombo.value.stable_key}`
  if (selectedPersonalWatchlist.value) return `watchlist:${selectedPersonalWatchlist.value.id}`
  if (flaggedItemsSelected.value) return explicitMarketMapSourceId(flaggedWatchlistRows.value)
  return null
})
const personalWatchlistColumns: WatchlistColumn[] = [
  { key: 'symbol', label: 'Symbol', width: '72px' },
  { key: 'name', label: 'Name', width: 'minmax(130px, 1fr)' },
  { key: 'last', label: 'Last', width: '72px', format: 'number' },
  { key: 'change', label: 'Chg %', width: '68px', format: 'percent' },
]
const personalSymbolDraft = ref('')
const personalListNameDraft = ref('')
// A user-entered name must win over a stale virtual-tool snapshot. Without an
// edit fence, selecting/creating a list in one Golden Layout root could replay
// an older selection into another root between the input and its New click.
const personalListNameEditing = ref(false)
const personalListBusy = ref(false)
const personalWatchlistBusy = ref(false)
const personalWatchlistError = ref('')
// Workspace snapshots can echo an older watchlist_id while a local selection
// is still being persisted. Keep that stale echo from snapping the visible
// list back to a different tab during membership actions.
let pendingWatchlistConfiguration: number | string | null | undefined
let pendingWatchlistConfigurationTimer: ReturnType<typeof setTimeout> | null = null

function markPersonalListNameEdited(event: Event) {
  personalListNameEditing.value = true
  const value = event.target instanceof HTMLInputElement ? event.target.value : personalListNameDraft.value
  latestPersonalListDraft = value
}

function publishWatchlistConfiguration(watchlistId: number | string | null) {
  if (pendingWatchlistConfigurationTimer !== null) clearTimeout(pendingWatchlistConfigurationTimer)
  pendingWatchlistConfigurationTimer = null
  pendingWatchlistConfiguration = watchlistId
  const toolKey = props.tool.instance_key
  const previousTimer = pendingPersonalWatchlistSelectionTimers.get(toolKey)
  if (previousTimer) clearTimeout(previousTimer)
  pendingPersonalWatchlistSelections.set(toolKey, watchlistId)
  pendingPersonalWatchlistSelectionTimers.set(toolKey, setTimeout(() => {
    pendingPersonalWatchlistSelections.delete(toolKey)
    pendingPersonalWatchlistSelectionTimers.delete(toolKey)
  }, 30_000))
  emit('configuration', props.tool.instance_key, { ...props.tool.configuration, watchlist_id: watchlistId })
}

function selectPersonalWatchlist(raw: string) {
  // An explicit user selection supersedes the create-intent fence.
  flaggedItemsSelected.value = raw === 'flagged'
  selectedComboKey.value = raw.startsWith('combo:') ? raw.slice(6) : null
  const id = Number(raw)
  selectedPersonalWatchlistId.value = Number.isInteger(id) && id > 0 ? id : null
  // Persisted workspace snapshots can arrive after the native select event,
  // especially while a Golden Layout root is being activated. Keep the
  // explicitly selected list authoritative for the same bounded window used
  // after creation; the shared pending-selection map below protects sibling
  // virtual roots from replaying the older configuration.
  fenceLatestPersonalWatchlistSelection(selectedPersonalWatchlistId.value)
  personalListNameEditing.value = false
  personalListNameDraft.value = selectedPersonalWatchlist.value?.name ?? ''
  comboError.value = ''
  hydrateSelectedCombo()
  publishWatchlistConfiguration(flaggedItemsSelected.value ? 'flagged' : selectedComboKey.value ? `combo:${selectedComboKey.value}` : selectedPersonalWatchlistId.value)
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
    comboLists.value = await queryClient.fetchQuery<ComboListDefinition[]>({
      queryKey: ['workstation', 'library-items', 'combo_list'],
      queryFn: async () => (await api.get<ComboListDefinition[]>('/workspaces/library/items', { kind: 'combo_list' })) ?? [],
      staleTime: 30_000,
    })
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
    await queryClient.invalidateQueries({ queryKey: ['workstation', 'library-items', 'combo_list'] })
    const index = comboLists.value.findIndex(item => item.stable_key === stableKey)
    if (index >= 0) comboLists.value[index] = saved
    else comboLists.value.push(saved)
    // A newly-created personal-list selection fence must not keep the combo
    // view pinned to that list after the combo is saved and selected.
    fenceLatestPersonalWatchlistSelection(null)
    selectedComboKey.value = stableKey
    flaggedItemsSelected.value = false
    selectedPersonalWatchlistId.value = null
    publishWatchlistConfiguration(`combo:${stableKey}`)
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
    await queryClient.invalidateQueries({ queryKey: ['workstation', 'library-items', 'combo_list'] })
    comboLists.value = comboLists.value.filter(item => item.stable_key !== combo.stable_key)
    selectedComboKey.value = null
    comboNameDraft.value = ''
    comboUnionIds.value = []
    comboIntersectionIds.value = []
    comboExcludeIds.value = []
    selectedPersonalWatchlistId.value = personalWatchlists.value[0]?.id ?? null
    publishWatchlistConfiguration(selectedPersonalWatchlistId.value)
  } catch (cause: any) {
    comboError.value = cause?.message ?? 'Unable to delete combo list'
  } finally {
    comboBusy.value = false
  }
}

async function createPersonalWatchlist(event?: Event) {
  // Do not gate the click on a virtual-root-local busy/ref snapshot. A stale
  // root may retain that flag while its visible successor owns the current
  // draft; the store's name-keyed request deduplication remains the operation
  // guard, and the live input value below is authoritative.
  personalListBusy.value = true
  // A click can arrive in the same task as the input's final v-model update
  // when a virtual tool root is being activated. Read the committed draft,
  // not the previous render's value, before issuing the create request.
  await nextTick()
  // Read the live control as well as the component ref. During a Golden Layout
  // virtual-root handoff, the DOM button can outlive the closure that received
  // it; the input value is still the user's current draft and must win over a
  // stale closure snapshot.
  const button = event?.currentTarget instanceof HTMLElement ? event.currentTarget : null
  const liveInput = button?.closest('.personal-watchlist-tool')?.querySelector<HTMLInputElement>('input[aria-label="Personal watchlist name"]')
  const name = (latestPersonalListDraft || liveInput?.value || personalListNameDraft.value).trim()
  if (!name) {
    personalListBusy.value = false
    return
  }
  // Golden Layout may briefly leave a stale virtual root alive while a new
  // watchlist tab is being activated. The module-wide draft above is the
  // authoritative intent; any duplicate roots therefore submit the same
  // name-keyed operation, which the store deduplicates safely.
  personalWatchlistError.value = ''
  try {
    const created = await watchlistStore.createWatchlist(name)
    if (!created) throw new Error('Unable to create personal watchlist')
    // A stale virtual root can replay the same create after the first root has
    // already committed it. Selecting the canonical returned row is safe even
    // when it was found through the store's idempotent 409 recovery, and keeps
    // every duplicate root converged on the same current draft.
    fenceLatestPersonalWatchlistSelection(created.id)
    selectedPersonalWatchlistId.value = created.id
    personalListNameEditing.value = false
    personalListNameDraft.value = created.name
    publishWatchlistConfiguration(created.id)
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
    personalListNameEditing.value = false
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
    personalListNameEditing.value = false
    publishWatchlistConfiguration(copy.id)
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
    publishWatchlistConfiguration(selectedPersonalWatchlistId.value)
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
    const item = await watchlistStore.addBySymbol(watchlist.id, raw, true)
    if (!item) throw new Error(`${raw.toUpperCase()} could not be added (it may already be in the list).`)
    // A concurrent Golden Layout root can echo an older workspace selection
    // while the item request is in flight. Reassert the list that accepted the
    // mutation so the visible tool renders the newly added row immediately.
    selectedPersonalWatchlistId.value = watchlist.id
    flaggedItemsSelected.value = false
    selectedComboKey.value = null
    personalListNameDraft.value = watchlist.name
    publishWatchlistConfiguration(watchlist.id)
    personalSymbolDraft.value = ''
  } catch (cause: any) {
    personalWatchlistError.value = cause?.message ?? 'Unable to add symbol'
  } finally {
    personalWatchlistBusy.value = false
  }
}

async function handleMembershipAction(action: 'copy-to-watchlist' | 'move-to-watchlist', row: { symbol: string; instrumentId: number | null; itemId?: number; sourceWatchlistId?: number }, targetWatchlistId?: number, selectedRows: Array<{ symbol: string; instrumentId: number | null; itemId?: number; sourceWatchlistId?: number }> = [row]) {
  if (row.instrumentId == null || targetWatchlistId == null) return
  const target = personalWatchlists.value.find(watchlist => watchlist.id === targetWatchlistId)
  if (!target || target.is_locked || target.is_managed) {
    personalWatchlistError.value = 'Choose an unlocked personal watchlist as the destination.'
    return
  }
  const selected = selectedPersonalWatchlist.value
  const sourceIds = selectedRows.map(item => item.sourceWatchlistId ?? selected?.id).filter((id): id is number => id != null)
  const sourceId = sourceIds[0]
  if (sourceIds.some(id => id !== sourceId)) {
    personalWatchlistError.value = 'Selected rows must come from the same source watchlist.'
    return
  }
  const source = sourceId == null ? null : personalWatchlists.value.find(watchlist => watchlist.id === sourceId)
  if (action === 'move-to-watchlist' && (!source || source.is_locked || source.is_managed || source.id === target.id)) return
  personalWatchlistError.value = ''
  const itemIds = selectedRows.map(item => item.itemId).filter((id): id is number => id != null)
  if (sourceId == null || itemIds.length !== selectedRows.length) {
    personalWatchlistError.value = 'The source watchlist item is no longer available; reload the list and try again.'
    return
  }
  const transferred = await watchlistStore.transferItems(
    sourceId,
    itemIds,
    target.id,
    action === 'move-to-watchlist' ? 'move' : 'copy',
  )
  if (transferred.length !== itemIds.length) {
    personalWatchlistError.value = `${selectedRows.length} selected row${selectedRows.length === 1 ? '' : 's'} could not be ${action === 'move-to-watchlist' ? 'moved' : 'copied'} to ${target.name}.`
  }
}

function handlePersonalRowAction(action: 'chart' | 'compare' | 'ratio' | 'note' | 'alert' | 'copy' | 'copy-to-watchlist' | 'move-to-watchlist' | 'flag' | 'remove', row: { symbol: string; instrumentId: number | null; itemId?: number; sourceWatchlistId?: number; flagged?: boolean }, targetWatchlistId?: number, selectedRows?: Array<{ symbol: string; instrumentId: number | null; itemId?: number; sourceWatchlistId?: number; flagged?: boolean }>) {
  if (action === 'flag' && row.itemId != null) {
    const sourceWatchlistId = row.sourceWatchlistId ?? selectedPersonalWatchlist.value?.id
    if (sourceWatchlistId == null) return
    void watchlistStore.setItemFlag(sourceWatchlistId, row.itemId, !row.flagged)
    return
  }
  if (action === 'copy-to-watchlist' || action === 'move-to-watchlist') {
    void handleMembershipAction(action, row, targetWatchlistId, selectedRows?.length ? selectedRows : [row])
    return
  }
  if (action === 'remove' && selectedPersonalWatchlist.value && row.itemId != null) {
    void watchlistStore.removeItem(selectedPersonalWatchlist.value.id, row.itemId)
    return
  }
  if (action !== 'remove') handleRowAction(action, row)
}

onMounted(async () => {
  void loadBreadthPythonSeriesAssets()
  if ((props.tool.instance_key === 'breadth-summary' || props.tool.tool_type === 'breadth') && !watchlistStore.watchlistSources.length && !watchlistStore.watchlistSourcesLoading) {
    await watchlistStore.loadWatchlistSources()
  }
  if (!watchlistStore.watchlists.length && !watchlistStore.loading) await watchlistStore.loadWatchlists()
  if (props.tool.tool_type !== 'watchlist' || props.tool.configuration.personal !== true) return
  await loadComboLists()
  if (selectedPersonalWatchlistId.value == null && !flaggedItemsSelected.value) {
    selectedPersonalWatchlistId.value = personalWatchlists.value[0]?.id ?? null
    personalListNameDraft.value = personalWatchlists.value[0]?.name ?? ''
    if (selectedPersonalWatchlistId.value != null) {
      publishWatchlistConfiguration(selectedPersonalWatchlistId.value)
    }
  }
  const symbols = personalWatchlistRows.value.map(row => row.symbol).filter(symbol => !symbol.startsWith('#'))
  if (symbols.length) await watchlistStore.fetchPrices(symbols, false, true)
  void loadIndicatorColumns([
    ...personalWatchlistRows.value,
    ...flaggedWatchlistRows.value,
    ...comboWatchlistRows.value,
    ...activeBenchmarkRows.value,
    ...sectorRows.value,
    ...factoryWatchlistRows.value,
    ...proxyRows.value,
    ...constituentRows.value,
  ])
  void loadConditionColumns([
    ...personalWatchlistRows.value,
    ...flaggedWatchlistRows.value,
    ...comboWatchlistRows.value,
    ...activeBenchmarkRows.value,
    ...sectorRows.value,
    ...factoryWatchlistRows.value,
    ...proxyRows.value,
    ...constituentRows.value,
  ])
})

watch(() => props.tool.configuration.watchlist_id, value => {
  if (latestCreatedPersonalWatchlistId.value != null && value !== latestCreatedPersonalWatchlistId.value) return
  const sharedPendingSelection = pendingPersonalWatchlistSelections.get(props.tool.instance_key)
  if (sharedPendingSelection !== undefined && value !== sharedPendingSelection) return
  if (pendingWatchlistConfiguration !== undefined) {
    if (value !== pendingWatchlistConfiguration) return
    // A workspace snapshot can acknowledge the latest local selection and then
    // deliver an older in-flight snapshot. Keep the acknowledgement fence alive
    // briefly so rapid list traversal cannot snap the visible rows back to that
    // stale value. Keep the fence longer than a rapid multi-create sequence;
    // snapshot acknowledgement and persistence can involve several queued
    // writes and must not revert the latest local selection mid-operation.
    if (pendingWatchlistConfigurationTimer === null) {
      pendingWatchlistConfigurationTimer = setTimeout(() => {
        pendingWatchlistConfiguration = undefined
        pendingWatchlistConfigurationTimer = null
      }, 30_000)
    }
  }
  flaggedItemsSelected.value = value === 'flagged'
  selectedComboKey.value = typeof value === 'string' && value.startsWith('combo:') ? value.slice(6) : null
  selectedPersonalWatchlistId.value = typeof value === 'number' ? value : null
  hydrateSelectedCombo()
})

watch(() => selectedPersonalWatchlist.value?.items.map(item => item.symbol).join(','), value => {
  const symbols = (value ?? '').split(',').filter(Boolean)
  if (symbols.length) void watchlistStore.fetchPrices(symbols, false, true)
})
watch(() => flaggedWatchlistRows.value.map(row => row.symbol).join(','), value => {
  const symbols = (value ?? '').split(',').filter(Boolean)
  if (symbols.length) void watchlistStore.fetchPrices(symbols, false, true)
})
watch(() => comboWatchlistRows.value.map(row => row.symbol).join(','), value => {
  const symbols = (value ?? '').split(',').filter(Boolean)
  if (symbols.length) void watchlistStore.fetchPrices(symbols, false, true)
})
// A Golden Layout virtual component is mounted independently from its host render
// cycle. Keep the latest serializable chart configuration locally so template changes
// update its uPlot instance immediately, while the same object is persisted by the
// parent workspace snapshot.
const liveChartConfiguration = ref<Record<string, unknown>>(props.tool.configuration)
const pendingTemplateConfiguration = ref<Record<string, unknown> | null>(null)
const optimisticComparisonSymbols = ref<string[] | null>(null)
const chartTemplateConfiguration = computed(() => ({
  ...liveChartConfiguration.value,
  comparison_symbols: optimisticComparisonSymbols.value ?? comparisonTargets.value.map(target => target.symbol),
}))
const activeSymbol = computed(() => workspaceStore.symbolForLinkGroup(
  localLinkGroup.value,
  typeof props.tool.configuration.symbol === 'string' ? props.tool.configuration.symbol : null,
))
// Non-chart tools have their own panel-scoped chart store and therefore cannot
// rely on a chart window having loaded the canonical instrument first. Resolve
// identity directly for notes, alerts, and reports so active-symbol actions work
// even when those tools are opened in isolation or in a pop-out.
const toolInstrument = ref<Instrument | null>(null)
let instrumentRequestSequence = 0
watch(activeSymbol, async symbol => {
  const sequence = ++instrumentRequestSequence
  toolInstrument.value = null
  if (!symbol || props.tool.tool_type === 'chart') return
  try {
    const loaded = await fetchCanonicalInstrument(queryClient, symbol)
    if (sequence === instrumentRequestSequence) toolInstrument.value = loaded
  } catch {
    if (sequence === instrumentRequestSequence) toolInstrument.value = null
  }
}, { immediate: true })
// Older persisted workspaces used the shorter `industries` instance key. Keep
// that serialized state behavior-compatible while new factory layouts use the
// explicit `industry-list` key.
const isIndustryTool = computed(() => {
  const instanceKey = props.tool.instance_key.toLowerCase()
  const title = (props.tool.title ?? '').toLowerCase()
  const marketGroup = typeof props.tool.configuration.market_group === 'string'
    ? props.tool.configuration.market_group.toLowerCase()
    : ''
  return instanceKey === 'industry-list'
    || instanceKey === 'industries'
    || title.includes('industr')
    || marketGroup === 'selected-sector-industries'
})
const activeTimeframe = computed(() => workspaceStore.timeframeForLinkGroup(
  timeframeLinkGroup.value,
  typeof props.tool.configuration.timeframe === 'string' ? props.tool.configuration.timeframe : null,
))
const timeframeLinkGroup = computed(() => workspaceStore.timeframeLinkGroupForTool(props.tool))
const ratioExpression = computed(() => {
  const configuredExpression = typeof props.tool.configuration.expression === 'string'
    ? props.tool.configuration.expression.trim().toUpperCase()
    : ''
  const expression = props.tool.configuration.auto_ratio === true
    ? autoRatioExpression(
      activeSymbol.value,
      (workspaceStore.marketGroups['sp500-sectors']?.members ?? []).map(member => member.instrument.symbol),
      workspaceStore.constituentETF,
    )
    : configuredExpression
  const match = expression.match(/^=([A-Z0-9.:-]+)\/([A-Z0-9.:-]+)$/)
  return match ? { numerator: match[1], denominator: match[2] } : null
})
const ratioChartExpression = computed(() => {
  if (props.tool.instance_key !== 'ratio-chart' || props.tool.configuration.auto_ratio === true) return null
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
const chartTransformParams = computed(() => {
  // Template/settings changes are applied optimistically to the local
  // serialisable configuration before the parent workspace snapshot round-trip
  // completes. Read the same live object as chartBarType so a newly applied
  // Renko/Kagi/Point & Figure template cannot request stale transform fields.
  const configuration = liveChartConfiguration.value
  const number = (key: string) => typeof configuration[key] === 'number' && Number.isFinite(configuration[key]) ? configuration[key] as number : undefined
  return { brick_size: number('brick_size'), reversal_pct: number('reversal_pct'), box_size: number('box_size'), reversal: number('reversal') }
})
const comparisonDraft = ref('')
const comparisonTargets = ref<ComparisonTarget[]>([])
let comparisonRequestSequence = 0
let chartSelectionSequence = 0
const comparisonColors = ['#ffb74d', '#64b5f6', '#81c784', '#ba68c8', '#f06292', '#4dd0e1']
const configuredComparisonSymbols = computed(() => {
  const symbols = optimisticComparisonSymbols.value ?? liveChartConfiguration.value.comparison_symbols
  return Array.isArray(symbols)
    ? symbols.filter((symbol): symbol is string => typeof symbol === 'string' && Boolean(symbol.trim())).map(symbol => symbol.trim().toUpperCase())
    : []
})
const comparisonSeries = computed<ChartComparisonSeries[]>(() => {
  return buildNormalizedComparisonSeries(chartStore.bars, comparisonTargets.value)
})
type ConfiguredPythonPlot = { code_version_id: number; name: string; color?: string; timeframe?: string; hidden?: boolean; instance_key?: string; universe_source_id?: string; symbols?: string[] }
type ConfiguredScanPlot = { screener_id: number; name: string; metric: 'count' | 'percentage'; color?: string; hidden?: boolean; instance_key?: string }
function parseConfiguredPythonPlots(value: unknown): ConfiguredPythonPlot[] {
  if (!Array.isArray(value)) return []
  return value.filter((plot): plot is ConfiguredPythonPlot => Boolean(plot) && typeof plot === 'object' && Number.isInteger((plot as Record<string, unknown>).code_version_id) && typeof (plot as Record<string, unknown>).name === 'string' && (typeof (plot as Record<string, unknown>).color === 'undefined' || typeof (plot as Record<string, unknown>).color === 'string') && (typeof (plot as Record<string, unknown>).timeframe === 'undefined' || typeof (plot as Record<string, unknown>).timeframe === 'string') && (typeof (plot as Record<string, unknown>).hidden === 'undefined' || typeof (plot as Record<string, unknown>).hidden === 'boolean') && (typeof (plot as Record<string, unknown>).instance_key === 'undefined' || typeof (plot as Record<string, unknown>).instance_key === 'string') && (typeof (plot as Record<string, unknown>).universe_source_id === 'undefined' || typeof (plot as Record<string, unknown>).universe_source_id === 'string') && (typeof (plot as Record<string, unknown>).symbols === 'undefined' || (Array.isArray((plot as Record<string, unknown>).symbols) && ((plot as Record<string, unknown>).symbols as unknown[]).every((symbol: unknown) => typeof symbol === 'string'))))
}
function parseConfiguredScanPlots(value: unknown): ConfiguredScanPlot[] {
  if (!Array.isArray(value)) return []
  return value.filter((plot): plot is ConfiguredScanPlot => Boolean(plot) && typeof plot === 'object' && Number.isInteger((plot as Record<string, unknown>).screener_id) && typeof (plot as Record<string, unknown>).name === 'string' && ((plot as Record<string, unknown>).metric === 'count' || (plot as Record<string, unknown>).metric === 'percentage') && (typeof (plot as Record<string, unknown>).color === 'undefined' || typeof (plot as Record<string, unknown>).color === 'string') && (typeof (plot as Record<string, unknown>).hidden === 'undefined' || typeof (plot as Record<string, unknown>).hidden === 'boolean') && (typeof (plot as Record<string, unknown>).instance_key === 'undefined' || typeof (plot as Record<string, unknown>).instance_key === 'string'))
}
// Golden Layout keeps virtual tool instances mounted while the parent snapshot
// is being persisted. Keep an optimistic serializable copy so a just-added
// Python plot is visible immediately even if the parent emits a snapshot or
// conflict response before Vue has delivered the mutated configuration prop.
const localPythonPlots = ref<ConfiguredPythonPlot[]>(parseConfiguredPythonPlots(props.tool.configuration.python_plots))
const configuredPythonPlots = computed(() => localPythonPlots.value)
const pythonSeries = ref<ChartPythonSeries[]>([])
const localScanPlots = ref<ConfiguredScanPlot[]>(parseConfiguredScanPlots(props.tool.configuration.scan_plots))
const configuredScanPlots = computed(() => localScanPlots.value)
const scanSeries = ref<ChartPythonSeries[]>([])
const numericSeries = computed(() => [...pythonSeries.value, ...scanSeries.value])
let pythonPlotRequestSequence = 0
let scanPlotRequestSequence = 0
const pythonPlotRunIds = new Set<number>()
const comparisonLegend = computed(() => configuredComparisonSymbols.value.map((symbol, index) => {
  const target = comparisonTargets.value.find(candidate => candidate.symbol === symbol)
  const series = comparisonSeries.value.find(candidate => candidate.symbol === symbol)
  return {
    symbol,
    label: target?.label ?? symbol,
    color: target?.color ?? comparisonColors[index % comparisonColors.length],
    percentChange: series?.percentChange ?? null,
  }
}))

function selectSymbol(symbol: string, instrumentId?: number | null) {
  workspaceStore.selectToolSymbol(props.tool.instance_key, symbol, instrumentId)
  // The shell owns canonical data loading and auto-ratio orchestration. Publish
  // row selections through it as well as the local link-group mutation so every
  // watchlist interaction follows the same top-down path as symbol entry.
  emit('select', symbol, instrumentId)
}

function selectRotationSymbol(symbol: string, instrumentId?: number | null) {
  selectSymbol(symbol, instrumentId)
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
    // A template may intentionally restore its comparison set. Only the active
    // instrument identity is protected from template application.
    .filter(([key]) => ['symbol', 'instrument_id', 'expression'].includes(key)))
  const applied = { ...configuration, ...identity }
  if (indicators) {
    chartStore.setIndicators(indicators)
    // Chart store persistence is per canonical instrument, which keeps a template's
    // plot stack available when the window is restored or floated later.
    void chartStore.saveIndicatorsForInstrument()
  }
  liveChartConfiguration.value = applied
  pendingTemplateConfiguration.value = applied
  const templateComparisons = Array.isArray(applied.comparison_symbols)
    ? applied.comparison_symbols.filter((symbol): symbol is string => typeof symbol === 'string' && Boolean(symbol.trim())).map(symbol => symbol.trim().toUpperCase())
    : []
  optimisticComparisonSymbols.value = templateComparisons
  liveChartConfiguration.value = { ...applied, comparison_symbols: templateComparisons }
  comparisonTargets.value = templateComparisons.map((symbol, index) => ({
    symbol,
    label: symbol,
    color: comparisonColors[index % comparisonColors.length],
    bars: comparisonTargets.value.find(target => target.symbol === symbol)?.bars ?? [],
  }))
  if (templateComparisons.length) void loadComparisonBars()
  emit('configuration', props.tool.instance_key, applied)
}

function persistComparisonSymbols() {
  const configuration = {
    ...liveChartConfiguration.value,
    comparison_symbols: comparisonTargets.value.map(target => target.symbol),
  }
  // Keep the optimistic chart configuration in sync with the parent snapshot.
  // Template saves read this object, so a comparison added immediately before
  // saving must be included even while Golden Layout persistence is in flight.
  liveChartConfiguration.value = configuration
  optimisticComparisonSymbols.value = configuration.comparison_symbols as string[]
  emit('configuration', props.tool.instance_key, configuration)
}

function updatePythonPlots(plots: ConfiguredPythonPlot[]) {
  localPythonPlots.value = parseConfiguredPythonPlots(plots)
  emit('configuration', props.tool.instance_key, { ...props.tool.configuration, python_plots: plots })
}

function updateScanPlots(plots: ConfiguredScanPlot[]) {
  localScanPlots.value = parseConfiguredScanPlots(plots)
  emit('configuration', props.tool.instance_key, { ...props.tool.configuration, scan_plots: plots })
}

async function loadPythonPlots() {
  const plots = configuredPythonPlots.value.filter(plot => !plot.hidden)
  for (const runId of pythonPlotRunIds) void api.post(`/research/runs/${runId}/cancel`, {})
  pythonPlotRunIds.clear()
  if (props.tool.tool_type !== 'chart' || !plots.length || !activeSymbol.value) { pythonSeries.value = []; return }
  const sequence = ++pythonPlotRequestSequence
  const loaded = await Promise.all(plots.map(async plot => {
    const timeframe = plot.timeframe ?? activeTimeframe.value
    let runId: number | null = null
    try {
      const runConfig = {
        timeframe,
        ...(plot.universe_source_id ? { universe_source_id: plot.universe_source_id } : plot.symbols?.length ? { symbols: plot.symbols } : { symbol: activeSymbol.value }),
      }
      const queued = await api.post<{ id: number }>('/research/runs', { code_version_id: plot.code_version_id, run_config: runConfig, dataset_manifest: { source: 'canonical_database', timeframe } })
      runId = queued.id
      pythonPlotRunIds.add(queued.id)
      for (let attempt = 0; attempt < 30; attempt += 1) {
        const result = await queryClient.fetchQuery({
          queryKey: ['workstation', 'research-run', queued.id],
          queryFn: async () => {
            const refreshed = await api.get<{ status: string; artifacts?: Array<{ name: string; artifact_type: string; payload: Record<string, unknown> }> }>(`/research/runs/${queued.id}`)
            if (!refreshed) throw new Error('Research plot refresh returned no data')
            return refreshed
          },
          staleTime: 0,
        })
        if (result.status === 'completed' || result.status === 'failed' || result.status === 'canceled') {
          const artifact = result.artifacts?.find(item => item.artifact_type === 'series')
          const value = artifact?.payload?.value
          if (!value || typeof value !== 'object' || Array.isArray(value)) return null
          const candidate = value as { timestamps?: unknown; values?: unknown }
          const series = normalizeNumericSeries(candidate.timestamps, candidate.values)
          if (!series) return null
          return { codeVersionId: plot.code_version_id, label: plot.name, color: plot.color ?? '#ffb74d', ...series } satisfies ChartPythonSeries
        }
        await new Promise(resolve => window.setTimeout(resolve, 250))
      }
    } catch { return null }
    finally { if (runId != null) pythonPlotRunIds.delete(runId) }
    return null
  }))
  if (sequence === pythonPlotRequestSequence) pythonSeries.value = loaded.filter((item): item is ChartPythonSeries => item != null)
}

async function loadScanPlots() {
  const sequence = ++scanPlotRequestSequence
  const loaded = await Promise.all(configuredScanPlots.value.filter(plot => !plot.hidden).map(async plot => {
    try {
      const response = await api.get<{ points?: Array<{ timestamp: string; value?: number | null }> }>(`/screeners/${plot.screener_id}/plot`, { metric: plot.metric })
      const points = response?.points ?? []
      const series = normalizeNumericSeries(points.map(point => point.timestamp), points.map(point => point.value))
      if (!series) return null
      return { codeVersionId: -plot.screener_id, label: `${plot.name} · ${plot.metric}`, color: plot.color ?? '#4dd0e1', ...series, source: 'scan' as const } satisfies ChartPythonSeries
    } catch {
      return null
    }
  }))
  if (sequence === scanPlotRequestSequence) scanSeries.value = loaded.filter(item => item != null) as ChartPythonSeries[]
}

async function loadComparisonBars() {
  const symbols = comparisonTargets.value.map(target => target.symbol)
  if (!symbols.length || !chartStore.symbol) return
  const sequence = ++comparisonRequestSequence
  const timeframe = activeTimeframe.value
  const loaded = await Promise.all(symbols.map(async symbol => {
    try {
      const limit = Math.max(chartStore.bars.length, 500)
      const raw = await dedupeOhlcvRequest(`raw:local:${symbol.toUpperCase()}:${timeframe}:adjusted:${limit}`, () => api.get<any[]>(`/ohlcv/local/${encodeURIComponent(symbol)}/${timeframe}`, { limit }))
      return { symbol, bars: raw.map(bar => ({
        ...bar,
        ts: String(bar.ts ?? bar.timestamp ?? ''),
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
    const canonical = await ensureKnownInstrumentSymbol(symbol, 'Comparison symbol', { canonicalOnly: true })
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

function selectProxy(symbol: string, instrumentId?: number | null) {
  // A verified industry proxy is a comparison/drill-down target, not a new
  // taxonomy root. Let the shell publish/load its price data while retaining
  // the sector and industry context that owns the constituent list.
  emit('selectProxy', symbol, instrumentId)
}

function handleRowAction(action: 'chart' | 'compare' | 'ratio' | 'note' | 'alert' | 'copy' | 'copy-to-watchlist' | 'move-to-watchlist' | 'flag' | 'remove', row: { symbol: string; instrumentId: number | null; flagged?: boolean }, targetWatchlistId?: number) {
  if (action === 'flag') return
  if (action === 'copy-to-watchlist' || action === 'move-to-watchlist') {
    void handleMembershipAction(action, row, targetWatchlistId)
    return
  }
  if (action === 'remove') return
  emit('rowAction', action, row)
}

watch([activeSymbol, activeTimeframe, syntheticExpression, chartBarType, chartTransformParams], async ([symbol, timeframe, expression, barType, transformParams]) => {
  if (props.tool.tool_type !== 'chart' || (!symbol && !expression)) return
  const sequence = ++chartSelectionSequence
  let targetSymbol = symbol
  if (expression) {
    try {
      targetSymbol = await ensureKnownInstrumentSymbol(expression, 'Workstation expression', { canonicalOnly: true })
    } catch (cause: any) {
      if (sequence === chartSelectionSequence) chartStore.error = cause?.message ?? 'Unable to resolve expression'
      return
    }
  }
  if (sequence !== chartSelectionSequence) return
  const requestedTransformKey = JSON.stringify(transformParams ?? {})
  const loadedTransformKey = JSON.stringify(chartStore.transformParams ?? {})
  if (chartStore.symbol === targetSymbol
    && chartStore.timeframe === timeframe
    && chartStore.barType === barType
    && loadedTransformKey === requestedTransformKey) return
  void chartStore.loadBars(
    targetSymbol,
    timeframe as Timeframe,
    barType,
    true,
    transformParams,
  )
}, { immediate: true, deep: true })

watch([configuredPythonPlots, activeSymbol, activeTimeframe], () => { void loadPythonPlots() }, { deep: true, immediate: true })
watch([configuredScanPlots, activeTimeframe], () => { void loadScanPlots() }, { deep: true, immediate: true })

onBeforeUnmount(() => {
  if (pendingWatchlistConfigurationTimer !== null) clearTimeout(pendingWatchlistConfigurationTimer)
  pendingWatchlistConfigurationTimer = null
  pendingWatchlistConfiguration = undefined
  // A chart tool can own several isolated Python plot runs. Cancel known runs
  // when its dock/pop-out closes and invalidate both chart and plot generations
  // so late research responses cannot update a destroyed uPlot surface.
  chartSelectionSequence += 1
  pythonPlotRequestSequence += 1
  scanPlotRequestSequence += 1
  for (const runId of pythonPlotRunIds) void api.post(`/research/runs/${runId}/cancel`, {})
  pythonPlotRunIds.clear()
})

watch(() => props.tool.configuration, configuration => {
  const pending = pendingTemplateConfiguration.value
  if (pending && Object.prototype.hasOwnProperty.call(pending, 'comparison_symbols')) {
    const incoming = Array.isArray(configuration.comparison_symbols) ? configuration.comparison_symbols : []
    const expected = Array.isArray(pending.comparison_symbols) ? pending.comparison_symbols : []
    if (JSON.stringify(incoming) === JSON.stringify(expected)) {
      pendingTemplateConfiguration.value = null
      optimisticComparisonSymbols.value = null
    }
    else {
      liveChartConfiguration.value = { ...configuration, comparison_symbols: expected }
      return
    }
  } else if (pending) {
    pendingTemplateConfiguration.value = null
  }
  liveChartConfiguration.value = configuration
}, { deep: true })

watch(() => props.tool.configuration.python_plots, value => {
  localPythonPlots.value = parseConfiguredPythonPlots(value)
}, { deep: true })

watch(() => props.tool.configuration.scan_plots, value => {
  localScanPlots.value = parseConfiguredScanPlots(value)
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
const benchmarkFamilyOptions = computed(() => {
  const raw = workspaceStore.marketGroups['us-benchmarks']?.provenance?.benchmark_families
  if (!Array.isArray(raw)) return []
  return raw.flatMap(item => {
    if (!item || typeof item !== 'object') return []
    const family = item as Record<string, unknown>
    const logicalKey = typeof family.logical_key === 'string' ? family.logical_key.trim() : ''
    const name = typeof family.name === 'string' ? family.name.trim() : logicalKey
    return logicalKey && name ? [{ logicalKey, name }] : []
  })
})
const benchmarkFamilyKey = ref(typeof props.tool.configuration.benchmark_family_key === 'string' ? props.tool.configuration.benchmark_family_key.trim() : '')
watch(() => props.tool.configuration.benchmark_family_key, value => {
  benchmarkFamilyKey.value = typeof value === 'string' ? value.trim() : ''
})
type BenchmarkFamilyMapRole = 'cap_weight' | 'equal_weight' | 'value' | 'growth'
const benchmarkFamilyMapRoles: BenchmarkFamilyMapRole[] = ['cap_weight', 'equal_weight', 'value', 'growth']
const benchmarkFamilyMapRole = ref<BenchmarkFamilyMapRole>(
  benchmarkFamilyMapRoles.includes(props.tool.configuration.benchmark_family_map_role as BenchmarkFamilyMapRole)
    ? props.tool.configuration.benchmark_family_map_role as BenchmarkFamilyMapRole
    : 'cap_weight',
)
watch(() => props.tool.configuration.benchmark_family_map_role, value => {
  benchmarkFamilyMapRole.value = benchmarkFamilyMapRoles.includes(value as BenchmarkFamilyMapRole) ? value as BenchmarkFamilyMapRole : 'cap_weight'
})
const activeBenchmarkFamily = computed(() => benchmarkFamilyOptions.value.find(family => family.logicalKey === benchmarkFamilyKey.value) ?? null)
const benchmarkFamilyRecord = computed<Record<string, unknown> | null>(() => {
  if (!benchmarkFamilyKey.value) return null
  const raw = workspaceStore.marketGroups['us-benchmarks']?.provenance?.benchmark_families
  if (!Array.isArray(raw)) return null
  const found = raw.find(item => item && typeof item === 'object' && (item as Record<string, unknown>).logical_key === benchmarkFamilyKey.value)
  return found && typeof found === 'object' ? found as Record<string, unknown> : null
})
const benchmarkFamilyCapProxy = computed(() => {
  const mapping = benchmarkFamilyRecord.value?.cap_weight
  if (!mapping || typeof mapping !== 'object') return undefined
  const symbol = (mapping as Record<string, unknown>).symbol
  return typeof symbol === 'string' && symbol.trim() ? symbol.trim().toUpperCase() : undefined
})
const benchmarkFamilySnapshot = computed(() => benchmarkFamilyKey.value ? workspaceStore.groupSnapshots[benchmarkFamilyKey.value] : null)
const benchmarkFamilyOverviewKey = computed(() => `${benchmarkFamilyKey.value}:${activeTimeframe.value}:adj:latest`)
const benchmarkFamilyOverview = computed(() => benchmarkFamilyKey.value ? workspaceStore.benchmarkFamilyOverviews[benchmarkFamilyOverviewKey.value] : null)
const benchmarkFamilyOverviewError = computed(() => benchmarkFamilyKey.value ? workspaceStore.benchmarkFamilyOverviewErrors[benchmarkFamilyOverviewKey.value] ?? '' : '')
const benchmarkFamilyMapRoleOptions = computed(() => benchmarkFamilyMapRoles.map(role => {
  const mapping = benchmarkFamilyOverview.value?.mappings.find(item => item.role === role)
  return {
    role,
    available: Boolean(mapping?.symbol && mapping.holdings_available && mapping.available !== false),
  }
}))
const activeBenchmarkMapRole = computed<BenchmarkFamilyMapRole>(() => {
  const selected = benchmarkFamilyMapRoleOptions.value.find(item => item.role === benchmarkFamilyMapRole.value && item.available)
  return selected?.role ?? 'cap_weight'
})
const benchmarkFamilyLoading = ref(false)
const benchmarkFamilyReadiness = computed(() => workspaceStore.benchmarkFamilyReadiness)
const benchmarkFamilyReadinessError = computed(() => workspaceStore.benchmarkFamilyReadinessError)
const benchmarkFamilyReadinessLoading = ref(false)
function benchmarkFamilyProviderProbeLabel(readiness: BenchmarkFamilyReadinessState) {
  const evidence = readiness.provider_probe_evidence ?? []
  if (!evidence.length) return 'Provider probes: none recorded'
  const successful = evidence.filter(item => item.success).length
  const recovered = evidence.filter(item => item.recovered).length
  const latestObservedAt = [...evidence]
    .map(item => item.observed_at)
    .filter(Boolean)
    .sort()
  const latest = latestObservedAt.length ? latestObservedAt[latestObservedAt.length - 1] : undefined
  return `Provider probes: ${successful}/${evidence.length} passed${recovered ? ` · ${recovered} recovered` : ''}${latest ? ` · latest ${latest.slice(0, 10)}` : ''}`
}
function benchmarkFamilyUniverseProvenanceLabel(readiness: BenchmarkFamilyReadinessState) {
  const provenance = readiness.universe_provenance ?? {}
  const registry = typeof provenance.registry === 'string' && provenance.registry.trim()
    ? provenance.registry.trim()
    : 'unavailable'
  const familyKeys = Array.isArray(provenance.family_keys) ? provenance.family_keys : []
  const missingFamilies = Array.isArray(provenance.missing_families) ? provenance.missing_families : []
  const pointInTime = provenance.point_in_time === true ? 'point-in-time' : 'latest'
  const providerCalls = provenance.provider_calls === false ? 'none' : provenance.provider_calls === true ? 'recorded' : 'not reported'
  return `Universe: ${registry} · ${familyKeys.length || readiness.family_count} families · ${pointInTime} · missing ${missingFamilies.length} · provider calls ${providerCalls}`
}
const benchmarkFamilyError = computed(() => {
  if (!benchmarkFamilyKey.value) return ''
  return workspaceStore.marketGroupErrors[benchmarkFamilyKey.value] ?? workspaceStore.groupSnapshotErrors[benchmarkFamilyKey.value] ?? benchmarkFamilyOverviewError.value
})
const activeBenchmarkLabel = computed(() => activeBenchmarkFamily.value?.name ?? 'S&P 500')
const activeBenchmarkIdentity = computed(() => {
  const details = benchmarkFamilyRecord.value
  const official = details?.official_index_symbol
  const capMapping = details?.cap_weight
  return {
    official_index_symbol: typeof official === 'string' && official ? official : benchmarkIdentity.value.official_index_symbol,
    default_tradable_proxy: capMapping && typeof capMapping === 'object' && typeof (capMapping as Record<string, unknown>).symbol === 'string'
      ? String((capMapping as Record<string, unknown>).symbol)
      : benchmarkIdentity.value.default_tradable_proxy,
  }
})
const activeBenchmarkListLabel = computed(() => benchmarkFamilyKey.value ? `${activeBenchmarkLabel.value} legs` : 'Major US benchmarks')
const activeBenchmarkMarketMapSourceId = computed(() => benchmarkFamilyKey.value
  ? benchmarkFamilyConstituentSourceId(benchmarkFamilyKey.value, activeBenchmarkMapRole.value)
  : 'market-group:us-benchmarks')
const isBenchmarkFamily = computed(() => benchmarkFamilyOptions.value.some(family => family.logicalKey === breadthGroupKey.value))
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
    freshness: formatWorkstationFreshness(snapshot?.freshness),
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
const breadthBusy = computed(() => workspaceStore.breadthLoading[breadthGroupKey.value] === true || workspaceStore.breadthHistoryLoading[breadthGroupKey.value] === true)
const breadthError = computed(() => workspaceStore.breadthErrors[breadthGroupKey.value] ?? workspaceStore.breadthHistoryErrors[breadthGroupKey.value] ?? null)
const breadthCustomUniverseKind = computed(() => {
  const candidate = breadthConfigurationValue('custom_universe_kind')
  return candidate === 'etf_holdings' || candidate === 'benchmark_family' || candidate === 'watchlist' ? candidate : 'group'
})
const breadthWatchlistSources = computed<WatchlistSource[]>(() => {
  const sources = [...watchlistStore.watchlistSources]
  const configured = String(breadthConfigurationValue('custom_universe_watchlist_id', ''))
  if (configured.startsWith('explicit:') && !sources.some(source => source.source_id === configured)) {
    const ids = configured.slice('explicit:'.length).split(',').map(Number).filter(id => Number.isInteger(id) && id > 0)
    sources.unshift({
      source_id: configured,
      source_kind: 'explicit',
      name: `Selected members · ${ids.length}`,
      description: 'Ephemeral canonical selection published from Market Map',
      locked: true,
      can_follow: false,
      can_clone: true,
      can_edit_membership: false,
      member_count: ids.length,
      membership_version: `explicit:${ids.join(',')}`,
      provenance: { availability: 'available', membership_semantics: 'explicit_canonical_selection', instrument_ids: ids },
    })
  }
  return sources
})
const breadthWatchlistSourceId = computed(() => {
  const configured = String(breadthConfigurationValue('custom_universe_watchlist_id', ''))
  if (configured && breadthWatchlistSources.value.some(source => source.source_id === configured)) return configured
  return breadthWatchlistSources.value[0]?.source_id ?? ''
})
const breadthComposition = computed(() => {
  const candidate = String(breadthConfigurationValue('breadth_condition_composition', 'single'))
  return ['all', 'any', 'not', 'tree'].includes(candidate) ? candidate : 'single'
})
const breadthConditionKind = computed(() => {
  const candidate = String(breadthConfigurationValue('breadth_condition', 'above_moving_average'))
  return ['above_moving_average', 'within_52_week_high', 'new_high_low', 'prior_high_low', 'trend', 'rsi', 'volume_ratio', 'relative_strength', 'series_comparison', 'event', 'comparison', 'range', 'percentile', 'cross_sectional_statistic', 'python_series'].includes(candidate) && (candidate !== 'python_series' || breadthComposition.value === 'single') ? candidate : 'above_moving_average'
})
const breadthConditionPeriod = computed(() => Math.min(252, Math.max(2, Number(breadthConfigurationValue('breadth_condition_period', 200)) || 200)))
const breadthConditionAverage = computed(() => breadthConfigurationValue('breadth_condition_average') === 'ema' ? 'ema' : 'sma')
const breadthConditionThreshold = computed(() => Math.min(0.5, Math.max(0.001, Number(breadthConfigurationValue('breadth_condition_threshold', 0.01)) || 0.01)))
const breadthConditionLookback = computed(() => Math.min(504, Math.max(2, Number(breadthConfigurationValue('breadth_condition_lookback', 252)) || 252)))
const breadthConditionRsiPeriod = computed(() => Math.min(252, Math.max(2, Number(breadthConfigurationValue('breadth_condition_rsi_period', 14)) || 14)))
const breadthConditionVolumePeriod = computed(() => Math.min(252, Math.max(2, Number(breadthConfigurationValue('breadth_condition_volume_period', 20)) || 20)))
const breadthConditionFastPeriod = computed(() => Math.min(100, Math.max(2, Number(breadthConfigurationValue('breadth_condition_fast_period', 20)) || 20)))
const breadthConditionSlowPeriod = computed(() => Math.min(252, Math.max(3, Number(breadthConfigurationValue('breadth_condition_slow_period', 50)) || 50)))
const breadthConditionDirection = computed(() => breadthConfigurationValue('breadth_condition_direction') === 'down' ? 'down' : 'up')
const breadthHighLowDirection = computed(() => breadthConfigurationValue('breadth_condition_high_low_direction') === 'low' ? 'low' : 'high')
const breadthComparisonField = computed(() => {
  const candidate = String(breadthConfigurationValue('breadth_comparison_field', 'close'))
  return ['close', 'return', 'volume', 'rsi', 'distance_to_52w_high', 'distance_to_52w_low', 'relative_strength'].includes(candidate) ? candidate : 'close'
})
const breadthComparisonOperator = computed(() => {
  const candidate = String(breadthConfigurationValue('breadth_comparison_operator', 'gte'))
  return ['gte', 'lte', 'gt', 'lt', 'eq'].includes(candidate) ? candidate : 'gte'
})
const breadthComparisonThreshold = computed(() => Number.isFinite(Number(breadthConfigurationValue('breadth_comparison_threshold'))) ? Number(breadthConfigurationValue('breadth_comparison_threshold')) : 0)
const breadthSeriesMemberField = computed(() => {
  const candidate = String(breadthConfigurationValue('breadth_series_member_field', 'return'))
  return ['close', 'return', 'volume', 'rsi', 'distance_to_52w_high', 'distance_to_52w_low'].includes(candidate) ? candidate : 'return'
})
const breadthSeriesReferenceField = computed(() => {
  const candidate = String(breadthConfigurationValue('breadth_series_reference_field', 'return'))
  return ['close', 'return', 'volume', 'rsi', 'distance_to_52w_high', 'distance_to_52w_low'].includes(candidate) ? candidate : 'return'
})
const breadthSeriesRelation = computed(() => breadthConfigurationValue('breadth_series_relation') === 'ratio' ? 'ratio' : 'difference')
const breadthEventType = computed(() => {
  const candidate = String(breadthConfigurationValue('breadth_event_type', 'any'))
  return ['any', 'earnings', 'dividend', 'ex_dividend', 'split'].includes(candidate) ? candidate : 'any'
})
const breadthEventLookbackDays = computed(() => Math.min(3660, Math.max(0, Number(breadthConfigurationValue('breadth_event_lookback_days', 0)) || 0)))
const breadthEventIncludeEstimates = computed(() => breadthConfigurationValue('breadth_event_include_estimates') === true)
const breadthRangeField = computed(() => {
  const candidate = String(breadthConfigurationValue('breadth_range_field', 'close'))
  return ['close', 'return', 'volume', 'distance_to_52w_high'].includes(candidate) ? candidate : 'close'
})
const breadthRangeLower = computed(() => Number.isFinite(Number(breadthConfigurationValue('breadth_range_lower'))) ? Number(breadthConfigurationValue('breadth_range_lower')) : 0)
const breadthRangeUpper = computed(() => Number.isFinite(Number(breadthConfigurationValue('breadth_range_upper'))) ? Number(breadthConfigurationValue('breadth_range_upper')) : 1)
const breadthPercentileField = computed(() => {
  const candidate = String(breadthConfigurationValue('breadth_percentile_field', 'close'))
  return ['close', 'return', 'volume', 'moving_average_distance'].includes(candidate) ? candidate : 'close'
})
const breadthPercentileScope = computed(() => breadthConfigurationValue('breadth_percentile_scope') === 'cross_sectional' ? 'cross_sectional' : 'member')
const breadthPercentilePeriod = computed(() => Math.min(5000, Math.max(2, Number(breadthConfigurationValue('breadth_percentile_period', 252)) || 252)))
const breadthPercentileTarget = computed(() => Math.min(1, Math.max(0, Number(breadthConfigurationValue('breadth_percentile_target', 0.8)) || 0.8)))
const breadthSecondaryField = computed(() => {
  const candidate = String(breadthConfigurationValue('breadth_secondary_field', 'return'))
  return ['close', 'return', 'volume', 'rsi', 'volume_ratio', 'distance_to_52w_high', 'relative_strength'].includes(candidate) ? candidate : 'return'
})
const breadthSecondaryThreshold = computed(() => Number.isFinite(Number(breadthConfigurationValue('breadth_secondary_threshold'))) ? Number(breadthConfigurationValue('breadth_secondary_threshold')) : 0)
const breadthBenchmark = computed(() => {
  const candidate = String(breadthConfigurationValue('breadth_benchmark', 'SPY')).trim().toUpperCase()
  return candidate || 'SPY'
})
const breadthReferenceTarget = computed(() => breadthConfigurationValue('breadth_reference_target') === 'group' ? 'group' : 'symbol')
const breadthReferenceGroup = computed(() => {
  const candidate = String(breadthConfigurationValue('breadth_reference_group', 'sp500-sectors')).trim()
  return candidate || 'sp500-sectors'
})
type BreadthPythonSeriesAsset = { versionId: number; name: string }
const breadthPythonSeriesAssets = ref<BreadthPythonSeriesAsset[]>([])
const breadthPythonSeriesAssetsLoading = ref(false)
const breadthPythonSeriesCodeVersionId = computed(() => {
  const value = Number(breadthConfigurationValue('breadth_python_series_code_version_id'))
  return Number.isInteger(value) && value > 0 ? value : null
})
const breadthPythonSeriesOperator = computed(() => {
  const candidate = String(breadthConfigurationValue('breadth_python_series_operator', 'gte'))
  return ['gt', 'gte', 'lt', 'lte', 'eq', 'ne'].includes(candidate) ? candidate : 'gte'
})
const breadthPythonSeriesScope = computed(() => breadthConfigurationValue('breadth_python_series_scope') === 'cross_sectional' ? 'cross_sectional' : 'member')
const breadthPythonSeriesStatistic = computed(() => {
  const candidate = String(breadthConfigurationValue('breadth_python_series_statistic', 'mean'))
  return ['mean', 'median', 'min', 'max', 'std'].includes(candidate) ? candidate : 'mean'
})
const breadthPythonSeriesThreshold = computed(() => {
  const value = Number(breadthConfigurationValue('breadth_python_series_threshold', 0))
  return Number.isFinite(value) ? value : 0
})
const breadthPythonSeriesUniverse = computed(() => ({
  kind: breadthCustomUniverseKind.value,
  ...(breadthCustomUniverseKind.value === 'group'
    ? { key: breadthGroupKey.value }
    : breadthCustomUniverseKind.value === 'benchmark_family'
      ? { key: breadthGroupKey.value, role: String(breadthConfigurationValue('family_ratio_role', 'equal_weight')) }
      : breadthCustomUniverseKind.value === 'watchlist'
        ? { key: breadthWatchlistSourceId.value }
        : { key: 'SPY' }),
  point_in_time: true,
}))
const breadthPythonSeriesRequest = computed<Record<string, unknown>>(() => ({
  code_version_id: breadthPythonSeriesCodeVersionId.value ?? 0,
  universe: breadthPythonSeriesUniverse.value,
  parameters: {},
  output_contract: 'series',
  series_target: {
    operator: breadthPythonSeriesOperator.value,
    threshold: breadthPythonSeriesThreshold.value,
    scope: breadthPythonSeriesScope.value,
    ...(breadthPythonSeriesScope.value === 'cross_sectional' ? { statistic: breadthPythonSeriesStatistic.value } : {}),
  },
  timeframe: breadthTimeframe.value,
  adjusted: breadthAdjusted.value,
  session: 'regular',
  ...(typeof breadthConfigurationValue('as_of') === 'string' && breadthConfigurationValue('as_of') ? { as_of: breadthConfigurationValue('as_of') } : {}),
  ...(breadthReferenceTarget.value === 'symbol' ? { benchmark: breadthBenchmark.value } : {}),
  history: true,
  history_limit: 500,
}))
function findPythonSeriesLeaf(node: BreadthTreeNode): BreadthTreeNode | null {
  if (node.kind === 'python_series' || node.kind === 'python_series_comparison') return node
  const children = Array.isArray(node.params?.conditions) ? node.params.conditions : []
  for (const child of children) {
    if (isBreadthTreeNode(child)) {
      const found = findPythonSeriesLeaf(child)
      if (found) return found
    }
  }
  return null
}
function pythonLeafAnchorId(node: BreadthTreeNode | null): number | null {
  if (!node) return null
  const raw = node.kind === 'python_series_comparison' ? node.params.left_code_version_id : node.params.code_version_id
  const value = Number(raw)
  return Number.isInteger(value) && value > 0 ? value : null
}
const breadthTreePythonSeriesLeaf = computed(() => breadthComposition.value === 'tree' ? findPythonSeriesLeaf(breadthTreeCondition.value) : null)
const breadthUsesPython = computed(() => breadthConditionKind.value === 'python_series' || breadthTreePythonSeriesLeaf.value !== null)
const breadthPythonRequest = computed<Record<string, unknown>>(() => {
  const leaf = breadthTreePythonSeriesLeaf.value
  if (!leaf) return breadthPythonSeriesRequest.value
  const codeVersionId = pythonLeafAnchorId(leaf)
  return {
    code_version_id: codeVersionId ?? 0,
    universe: breadthPythonSeriesUniverse.value,
    parameters: {},
    output_contract: 'boolean',
    condition_tree: breadthTreeCondition.value,
    timeframe: breadthTimeframe.value,
    adjusted: breadthAdjusted.value,
    session: 'regular',
    ...(typeof breadthConfigurationValue('as_of') === 'string' && breadthConfigurationValue('as_of') ? { as_of: breadthConfigurationValue('as_of') } : {}),
    ...(breadthReferenceTarget.value === 'symbol' ? { benchmark: breadthBenchmark.value } : {}),
    history: true,
    history_limit: 500,
  }
})
const breadthPythonRequestKey = computed(() => JSON.stringify(breadthPythonRequest.value))
const breadthPythonSeriesState = computed(() => workspaceStore.pythonBreadth[breadthPythonRequestKey.value] ?? null)
const breadthPythonSeriesLoading = computed(() => workspaceStore.pythonBreadthLoading[breadthPythonRequestKey.value] === true)
const breadthPythonSeriesError = computed(() => workspaceStore.pythonBreadthErrors[breadthPythonRequestKey.value] ?? null)
const breadthPythonSeriesStatus = computed(() => breadthPythonSeriesState.value?.status ?? null)

function asGenericBreadthState(state: NonNullable<typeof breadthPythonSeriesState.value>): GenericBreadthState {
  const current = state.current
  return {
    definition_version: 1,
    definition_hash: state.definition_hash,
    universe: state.universe,
    condition: state.condition,
    timeframe: String(state.dataset_manifest.timeframe ?? breadthTimeframe.value),
    adjustment: String(state.dataset_manifest.adjustment ?? (breadthAdjusted.value ? 'split_adjusted' : 'raw')),
    as_of: typeof state.dataset_manifest.as_of === 'string' ? state.dataset_manifest.as_of : null,
    requested_count: current?.requested_count ?? 0,
    eligible_count: current?.eligible_count ?? 0,
    pass_count: current?.pass_count ?? 0,
    excluded_count: current?.excluded_count ?? 0,
    percentage: current?.percentage ?? null,
    coverage: current?.coverage ?? 0,
    group_value: current?.group_value ?? null,
    members: current?.members ?? [],
    exclusions: current?.exclusions ?? [],
    freshness: 'coverage_limited',
  }
}

function asGenericBreadthHistory(state: NonNullable<typeof breadthPythonSeriesState.value>): GenericBreadthHistoryState {
  return {
    definition_version: 1,
    definition_hash: state.definition_hash,
    universe: state.universe,
    condition: state.condition,
    timeframe: String(state.dataset_manifest.timeframe ?? breadthTimeframe.value),
    adjustment: String(state.dataset_manifest.adjustment ?? (breadthAdjusted.value ? 'split_adjusted' : 'raw')),
    as_of: typeof state.dataset_manifest.as_of === 'string' ? state.dataset_manifest.as_of : null,
    points: state.points.filter((point): point is typeof point & { timestamp: string } => typeof point.timestamp === 'string'),
    occurrences: state.occurrences ?? [],
    exclusions: state.points.flatMap(point => point.exclusions),
    freshness: 'coverage_limited',
  }
}
type BreadthTreeNode = {
  kind: 'all' | 'any' | 'not' | 'above_moving_average' | 'within_52_week_high' | 'new_high_low' | 'prior_high_low' | 'trend' | 'rsi' | 'volume_ratio' | 'relative_strength' | 'series_comparison' | 'python_series' | 'python_series_comparison' | 'event' | 'comparison' | 'range' | 'percentile' | 'cross_sectional_statistic'
  target_scope?: 'member' | 'cross_sectional'
  params: Record<string, unknown>
}
function isBreadthTreeNode(value: unknown): value is BreadthTreeNode {
  if (!value || typeof value !== 'object') return false
  const candidate = value as Record<string, unknown>
  return typeof candidate.kind === 'string' && Boolean(candidate.params && typeof candidate.params === 'object')
}
const breadthTreeCondition = computed<BreadthTreeNode>(() => {
  const configured = breadthConfigurationValue('breadth_condition_tree')
  if (isBreadthTreeNode(configured)) return configured
  return { kind: 'all', params: { conditions: [primaryBreadthCondition()] } }
})
function setBreadthTreeCondition(value: BreadthTreeNode) {
  setBreadthConfiguration({ breadth_condition_tree: value })
}
const familyRatioRole = computed(() => {
  const candidate = String(props.tool.configuration.family_ratio_role ?? 'equal_weight')
  return ['cap_weight', 'equal_weight', 'value', 'growth'].includes(candidate) ? candidate as 'cap_weight' | 'equal_weight' | 'value' | 'growth' : 'equal_weight'
})
const familyRankPeriods = ['1D', '1W', '1M', '3M', '6M', 'YTD', '1Y'] as const
const familyRankPeriod = computed<typeof familyRankPeriods[number]>(() => {
  const candidate = String(props.tool.configuration.family_rank_period ?? '1M')
  return familyRankPeriods.includes(candidate as typeof familyRankPeriods[number]) ? candidate as typeof familyRankPeriods[number] : '1M'
})
const familyRatioMarket = computed(() => {
  const candidate = String(props.tool.configuration.family_ratio_market ?? 'SPY').trim().toUpperCase()
  return candidate || 'SPY'
})
const familyRatioRoles = ['cap_weight', 'equal_weight', 'value', 'growth'] as const
const familyRatioRoleKey = familyRatioRoles.join(',')
const familyRatioKey = computed(() => `${breadthGroupKey.value}:${familyRatioRoleKey}:${familyRatioMarket.value}:${breadthTimeframe.value}:${breadthAdjusted.value ? 'adj' : 'raw'}${familyAsOf.value ? `:${familyAsOf.value}` : ''}`)
const familyRatios = computed(() => workspaceStore.benchmarkFamilyRatios[familyRatioKey.value])
const familyRatioError = computed(() => workspaceStore.benchmarkFamilyRatioErrors[familyRatioKey.value] ?? null)
const familyRatioLoading = ref(false)
const familyTechnicalKey = computed(() => `${breadthGroupKey.value}:${breadthTimeframe.value}:${breadthAdjusted.value ? 'adj' : 'raw'}:${familyAsOf.value || 'latest'}`)
const familyTechnicals = computed(() => workspaceStore.benchmarkFamilyTechnicals[familyTechnicalKey.value])
const familyTechnicalError = computed(() => workspaceStore.benchmarkFamilyTechnicalErrors[familyTechnicalKey.value] ?? null)
const familyTechnicalsLoading = ref(false)
const familyBreadthKey = computed(() => `${breadthGroupKey.value}:${breadthTimeframe.value}:${breadthAdjusted.value ? 'adj' : 'raw'}:${familyAsOf.value || 'latest'}:0.01:20`)
const familyBreadth = computed(() => workspaceStore.benchmarkFamilyBreadths[familyBreadthKey.value])
const familyBreadthError = computed(() => workspaceStore.benchmarkFamilyBreadthErrors[familyBreadthKey.value] ?? null)
const familyBreadthLoading = ref(false)
const familyBreadthHistoryKey = computed(() => `${breadthGroupKey.value}:${breadthTimeframe.value}:${breadthAdjusted.value ? 'adj' : 'raw'}:${familyAsOf.value || 'latest'}:500`)
const familyBreadthHistory = computed(() => workspaceStore.benchmarkFamilyBreadthHistories[familyBreadthHistoryKey.value])
const familyBreadthHistoryPointCount = computed(() => Math.max(0, ...((familyBreadthHistory.value?.roles ?? []).map(role => role.points.length))))
const familyBreadthHistoryReadinessLabel = computed(() => {
  const roles = (familyBreadthHistory.value?.roles ?? []).filter(role => role.available)
  if (!roles.length) return 'readiness unavailable'
  const ready = roles.filter(role => role.analysis_ready_status === 'ready').length
  const partial = roles.filter(role => role.analysis_ready_status === 'partial').length
  const pending = roles.filter(role => role.analysis_ready_status === 'pending').length
  return `analysis-ready ${ready}/${roles.length}${partial ? ` · partial ${partial}` : ''}${pending ? ` · pending ${pending}` : ''}`
})
const familyRankingKey = computed(() => `${breadthGroupKey.value}:${breadthTimeframe.value}:${breadthAdjusted.value ? 'adj' : 'raw'}:${familyAsOf.value || 'latest'}:${familyRankPeriod.value}`)
const familyRanking = computed(() => workspaceStore.benchmarkFamilyRankings[familyRankingKey.value])
const familyRankingError = computed(() => workspaceStore.benchmarkFamilyRankingErrors[familyRankingKey.value] ?? null)
const familyRankingLoading = ref(false)
const familyConcentrationKey = computed(() => `${breadthGroupKey.value}:${breadthTimeframe.value}:${breadthAdjusted.value ? 'adj' : 'raw'}:${familyAsOf.value || 'latest'}:${familyRankPeriod.value}:10`)
const familyConcentration = computed(() => workspaceStore.benchmarkFamilyConcentrations[familyConcentrationKey.value])
const familyConcentrationError = computed(() => workspaceStore.benchmarkFamilyConcentrationErrors[familyConcentrationKey.value] ?? null)
const familyConcentrationLoading = ref(false)
const familyConcentrationHistoryKey = computed(() => `${breadthGroupKey.value}:${breadthTimeframe.value}:${breadthAdjusted.value ? 'adj' : 'raw'}:${familyAsOf.value || 'latest'}:${familyRankPeriod.value}:10:500`)
const familyConcentrationHistory = computed(() => workspaceStore.benchmarkFamilyConcentrationHistories[familyConcentrationHistoryKey.value])
const familyConcentrationHistoryError = computed(() => workspaceStore.benchmarkFamilyConcentrationHistoryErrors[familyConcentrationHistoryKey.value] ?? null)
const familyConcentrationHistoryPointCount = computed(() => Math.max(0, ...((familyConcentrationHistory.value?.roles ?? []).map(role => role.points.length))))
const familyConcentrationHistoryMode = computed(() => familyConcentrationHistory.value?.roles.some(role => role.membership_semantics === 'point_in_time_group_membership') ? 'point-in-time member membership' : 'point-in-time snapshots')
const familyConcentrationHistoryLoading = ref(false)
const crossFamilyRankingKey = computed(() => `${breadthTimeframe.value}:${breadthAdjusted.value ? 'adj' : 'raw'}:${familyAsOf.value || 'latest'}:${familyRankPeriod.value}::`)
const crossFamilyRanking = computed(() => workspaceStore.crossFamilyRankings[crossFamilyRankingKey.value])
const crossFamilyRankingError = computed(() => workspaceStore.crossFamilyRankingErrors[crossFamilyRankingKey.value] ?? null)
const crossFamilyRankingLoading = ref(false)
const crossFamilyRankingHistoryKey = computed(() => `${breadthTimeframe.value}:${breadthAdjusted.value ? 'adj' : 'raw'}:${familyAsOf.value || 'latest'}:${familyRankPeriod.value}:::500`)
const crossFamilyRankingHistory = computed(() => workspaceStore.crossFamilyRankingHistories[crossFamilyRankingHistoryKey.value])
const crossFamilyRankingHistoryPointCount = computed(() => Math.max(0, ...((crossFamilyRankingHistory.value?.rows ?? []).map(row => row.points.length))))
const crossFamilyRankingHistoryError = computed(() => workspaceStore.crossFamilyRankingHistoryErrors[crossFamilyRankingHistoryKey.value] ?? null)
const crossFamilyRankingHistoryLoading = ref(false)
const familyOverviewKey = computed(() => `${breadthGroupKey.value}:${breadthTimeframe.value}:${breadthAdjusted.value ? 'adj' : 'raw'}:${familyAsOf.value || 'latest'}`)
const familyOverview = computed(() => workspaceStore.benchmarkFamilyOverviews[familyOverviewKey.value])
const familyOverviewError = computed(() => workspaceStore.benchmarkFamilyOverviewErrors[familyOverviewKey.value] ?? null)
const familyOverviewLoading = ref(false)
const familyAsOf = computed(() => typeof props.tool.configuration.as_of === 'string' ? props.tool.configuration.as_of : '')
const familyCoverageKey = computed(() => `${breadthGroupKey.value}:${familyAsOf.value || 'latest'}:256`)
const familyCoverage = computed(() => workspaceStore.benchmarkFamilyCoverages[familyCoverageKey.value])
const familyCoverageError = computed(() => workspaceStore.benchmarkFamilyCoverageErrors[familyCoverageKey.value] ?? null)
const familyCoverageDates = computed(() => [...new Set((familyCoverage.value?.roles ?? []).flatMap(role => role.snapshots.map(snapshot => snapshot.composition_date)))].sort().reverse())
function familyAsOfValue(date: string) { return `${date}T23:59:59Z` }
const familyConstituentKey = computed(() => `${breadthGroupKey.value}:${familyRatioRole.value}:${breadthTimeframe.value}:${breadthAdjusted.value ? 'adj' : 'raw'}:${familyAsOf.value || 'latest'}:${familyRatioMarket.value}`)
const familyConstituents = computed(() => workspaceStore.benchmarkFamilyConstituents[familyConstituentKey.value])
const familyConstituentError = computed(() => workspaceStore.benchmarkFamilyConstituentErrors[familyConstituentKey.value] ?? null)
function familyRoleLabel(role: 'cap_weight' | 'equal_weight' | 'value' | 'growth') {
  return ({ cap_weight: 'Cap weight', equal_weight: 'Equal weight', value: 'Value', growth: 'Growth' } as const)[role]
}
function familyMappingState(mapping: { symbol: string | null; label: string; verification_state: string; holdings_available: boolean; holdings_completeness_status?: string | null }) {
  if (!mapping.symbol) return 'No verified mapped proxy'
  if (!mapping.holdings_available) return `${mapping.verification_state} · holdings unavailable`
  return `${mapping.holdings_completeness_status ?? 'holdings available'} · ${mapping.verification_state}`
}
function familyContinuityLabel(role: { continuity_status?: string; continuity_gap_count?: number; continuity_max_interval_days?: number | null; continuity_snapshot_limit_reached?: boolean; snapshots: unknown[] }) {
  const status = role.continuity_status ?? (role.snapshots.length > 1 ? 'observed_continuity' : role.snapshots.length === 1 ? 'single_snapshot' : 'no_snapshot')
  const labels: Record<string, string> = {
    not_applicable: 'continuity n/a',
    no_snapshot: 'no continuity evidence',
    single_snapshot: 'single disclosure',
    observed_continuity: 'observed continuity',
    gapped: `gapped${role.continuity_gap_count ? ` · ${role.continuity_gap_count} gap${role.continuity_gap_count === 1 ? '' : 's'}` : ''}${role.continuity_max_interval_days ? ` · max ${role.continuity_max_interval_days}d` : ''}`,
  }
  const label = labels[status] ?? status
  return role.continuity_snapshot_limit_reached ? `${label} · window capped` : label
}
function familyLatestDisclosureLabel(role: { snapshots?: Array<{ composition_date?: string | null; as_of_date?: string | null; known_at?: string | null; source_provider?: string | null; row_count?: number | null; resolved_count?: number | null; unresolved_count?: number | null }> }) {
  const snapshot = [...(role.snapshots ?? [])]
    .sort((left, right) => String(right.composition_date ?? '').localeCompare(String(left.composition_date ?? '')))[0]
  if (!snapshot) return 'no latest disclosure'
  const rowCount = Number(snapshot.row_count)
  const resolvedCount = Number(snapshot.resolved_count)
  const unresolvedCount = Number(snapshot.unresolved_count)
  const counts = Number.isFinite(rowCount) && Number.isFinite(resolvedCount)
    ? `${resolvedCount}/${rowCount} resolved${Number.isFinite(unresolvedCount) && unresolvedCount > 0 ? ` · ${unresolvedCount} unresolved` : ''}`
    : 'resolution unavailable'
  const asOf = snapshot.as_of_date ? ` · as of ${snapshot.as_of_date}` : ''
  const knownAt = snapshot.known_at ? ` · known ${snapshot.known_at}` : ''
  return `latest ${snapshot.composition_date ?? 'date unavailable'}${asOf}${knownAt} · ${counts} · ${snapshot.source_provider?.trim() || 'source unavailable'}`
}
function familyMemberBarHistoryLabel(role: { member_bar_history?: { status?: string; placeholder_member_count?: number; timeframes?: Array<{ timeframe: string; required_bar_count?: number; covered_member_count: number; member_count: number; analysis_ready_member_count: number }> } }) {
  const history = role.member_bar_history
  if (!history || history.status === 'no_snapshot') return 'no member bars'
  if (!history.timeframes?.length) return history.status
  const timeframeLabels = ['D1', 'W1', 'MN'].map(timeframe => {
    const item = history.timeframes?.find(candidate => candidate.timeframe === timeframe)
    if (!item) return `${timeframe} unavailable`
    const floor = Number(item.required_bar_count)
    return `${timeframe} ${item.analysis_ready_member_count}/${item.member_count} ready${Number.isFinite(floor) && floor > 0 ? ` · floor ${floor}` : ''} · ${item.covered_member_count}/${item.member_count} covered`
  })
  const placeholders = history.placeholder_member_count ? ` · placeholders ${history.placeholder_member_count}` : ''
  return `${history.status} · ${timeframeLabels.join(' · ')}${placeholders}`
}
function familyReadinessReasonsLabel(role: { composite_readiness_reasons?: string[] }) {
  const reasons = (role.composite_readiness_reasons ?? []).filter(reason => reason.trim())
  return reasons.length ? ` · reasons ${reasons.join(' · ')}` : ''
}
function familyRouteLabel(role: { holdings_route_status?: string; holdings_route_provider?: string | null; holdings_route_adapter_key?: string | null }) {
  const status = role.holdings_route_status?.replace(/_/g, ' ') ?? 'not configured'
  const provider = role.holdings_route_provider?.trim()
  const adapter = role.holdings_route_adapter_key?.trim()
  return `${status}${provider ? ` · ${provider}` : ''}${adapter ? ` · adapter ${adapter}` : ''}`
}
function familyEntitlementLabel(role: { entitlement_status?: string; entitlement_provider?: string | null; entitlement_live_probe_status?: string | null; entitlement_revision?: number | null; entitlement_effective_at?: string | null; entitlement_review_due_at?: string | null }) {
  const status = role.entitlement_status ?? 'unknown'
  const provider = role.entitlement_provider?.trim()
  const probe = role.entitlement_live_probe_status?.trim()
  const revision = role.entitlement_revision == null ? null : `rev ${role.entitlement_revision}`
  const effective = role.entitlement_effective_at?.slice(0, 10)
  const reviewDue = role.entitlement_review_due_at?.slice(0, 10)
  return `${status}${provider ? ` · ${provider}` : ''}${probe ? ` · probe ${probe.replace(/_/g, ' ')}` : ''}${revision ? ` · ${revision}` : ''}${effective ? ` · effective ${effective}` : ''}${reviewDue ? ` · review due ${reviewDue}` : ''}`
}
function familyRefreshLabel(role: { holdings_refresh_status?: string; holdings_refresh_provider?: string | null; holdings_refresh_last_checked_at?: string | null; holdings_refresh_last_success_at?: string | null; holdings_refresh_last_failure_at?: string | null; holdings_refresh_failure_reason?: string | null; holdings_refresh_composition_date?: string | null }) {
  const status = role.holdings_refresh_status ?? 'not_attempted'
  const provider = role.holdings_refresh_provider?.trim()
  const checked = role.holdings_refresh_last_checked_at?.slice(0, 10)
  const success = role.holdings_refresh_last_success_at?.slice(0, 10)
  const failure = role.holdings_refresh_last_failure_at?.slice(0, 10)
  const composition = role.holdings_refresh_composition_date?.slice(0, 10)
  const reason = role.holdings_refresh_failure_reason?.trim()
  return `${status}${provider ? ` · ${provider}` : ''}${reason ? ` · reason ${reason}` : ''}${checked ? ` · checked ${checked}` : ''}${success ? ` · success ${success}` : ''}${failure ? ` · failed ${failure}` : ''}${composition ? ` · composition ${composition}` : ''}`
}
function familyCanonicalRoleEvidenceLabel(coverage: { roles?: Array<{ role: 'cap_weight' | 'equal_weight' | 'value' | 'growth'; symbol?: string | null; label: string; verification_state?: string; adapter_key?: string | null; adapter_status?: string | null; adapter_confidence?: number | string | null; point_in_time_supported?: boolean; member_count?: number; placeholder_member_count?: number; weighted_member_count?: number; weights_status?: string; classified_member_count?: number; classification_status?: string; history_ready?: boolean; composite_readiness_status?: string; entitlement_capabilities?: Record<string, string>; continuity_status?: string | null; continuity_gap_count?: number; continuity_max_interval_days?: number | null; continuity_gaps?: Array<{ from_date: string; to_date: string; interval_days: number }>; continuity_snapshot_limit_reached?: boolean; snapshots?: Array<{ composition_date?: string | null; as_of_date?: string | null; known_at?: string | null; provenance?: string | null; source_quality?: string | null; completeness_status?: string | null; row_count?: number; resolved_count?: number; unresolved_count?: number }> }> }) {
  const roles = coverage.roles ?? []
  if (!roles.length) return 'Canonical role evidence: unavailable'
  return `Canonical role evidence: ${roles.map(role => {
    const name = `${familyRoleLabel(role.role)} ${role.symbol ?? role.label}`
    const verification = role.verification_state?.trim() || 'not reported'
    const adapter = role.adapter_key?.trim() || 'unmapped'
    const adapterStatus = role.adapter_status?.trim()
    const confidence = role.adapter_confidence == null ? null : `confidence ${role.adapter_confidence}`
    const members = Number.isFinite(role.member_count) ? `members ${role.member_count}` : 'members unavailable'
    const placeholders = role.placeholder_member_count ? ` · placeholders ${role.placeholder_member_count}` : ''
    const weighted = Number.isFinite(role.weighted_member_count) ? `weighted ${role.weighted_member_count} (${role.weights_status ?? 'unknown'})` : 'weighted unavailable'
    const classified = Number.isFinite(role.classified_member_count) ? `classified ${role.classified_member_count} (${role.classification_status ?? 'unknown'})` : 'classified unavailable'
    const pointInTime = role.point_in_time_supported === true ? 'point-in-time supported' : role.point_in_time_supported === false ? 'point-in-time unavailable' : 'point-in-time not reported'
    const history = role.history_ready === true ? 'history ready' : role.history_ready === false ? 'history incomplete' : 'history not reported'
    const snapshot = [...(role.snapshots ?? [])].sort((left, right) => String(right.composition_date ?? '').localeCompare(String(left.composition_date ?? '')))[0]
    const snapshotEvidence = snapshot
      ? ` · snapshot ${snapshot.composition_date?.slice(0, 10) || 'date not reported'}${snapshot.as_of_date ? ` · as-of ${snapshot.as_of_date.slice(0, 10)}` : ''}${snapshot.known_at ? ` · known ${snapshot.known_at.slice(0, 10)}` : ''} · provenance ${snapshot.provenance?.trim() || 'not reported'} · source quality ${snapshot.source_quality?.trim() || 'not reported'} · completeness ${snapshot.completeness_status?.trim() || 'not reported'} · rows ${Number.isFinite(snapshot.row_count) ? snapshot.row_count : 'not reported'} · resolved ${Number.isFinite(snapshot.resolved_count) ? snapshot.resolved_count : 'not reported'} · unresolved ${Number.isFinite(snapshot.unresolved_count) ? snapshot.unresolved_count : 'not reported'}`
      : ' · snapshot evidence unavailable'
    const continuityStatus = role.continuity_status?.trim()?.replace(/_/g, ' ') || 'not reported'
    const continuityGaps = (role.continuity_gaps ?? []).map(gap => `${gap.from_date.slice(0, 10)} to ${gap.to_date.slice(0, 10)} (${gap.interval_days}d)`).join(', ')
    const continuityEvidence = ` · continuity ${continuityStatus}${role.continuity_gap_count ? ` · ${role.continuity_gap_count} gap${role.continuity_gap_count === 1 ? '' : 's'}` : ''}${role.continuity_max_interval_days ? ` · max ${role.continuity_max_interval_days}d` : ''}${continuityGaps ? ` · intervals ${continuityGaps}` : ''}${role.continuity_snapshot_limit_reached ? ' · snapshot window capped' : ''}`
    const entitlementCapabilities = Object.entries(role.entitlement_capabilities ?? {}).sort(([left], [right]) => left.localeCompare(right)).map(([key, value]) => `${key.replace(/_/g, ' ')}=${String(value).replace(/_/g, ' ')}`).join(', ') || 'not reported'
    return `${name} · verification ${verification} · adapter ${adapter}${adapterStatus ? ` (${adapterStatus})` : ''}${confidence ? ` · ${confidence}` : ''} · ${members}${placeholders} · ${weighted} · ${classified} · ${pointInTime} · ${history} · readiness ${role.composite_readiness_status ?? 'unknown'}${snapshotEvidence}${continuityEvidence} · capabilities ${entitlementCapabilities}`
  }).join('; ')}`
}
function latestFamilyRatio(ratio: { points: Array<{ value: number }> }) {
  const value = ratio.points.length ? ratio.points[ratio.points.length - 1]?.value : undefined
  return value == null || !Number.isFinite(value) ? 'Unavailable' : value.toFixed(3)
}
function familyTechnicalValue(value: number | null | undefined) {
  return value == null || !Number.isFinite(value) ? 'Unavailable' : value.toFixed(2)
}
function familyBreadthPercentage(metric: { percentage: number | null } | null | undefined) {
  return metric?.percentage == null || !Number.isFinite(metric.percentage) ? 'Unavailable' : `${(metric.percentage * 100).toFixed(0)}%`
}
function comparisonCondition(field: string, operator: string, threshold: number) {
  return { kind: 'comparison', params: { field, operator, threshold } }
}
function primaryBreadthCondition() {
  if (breadthConditionKind.value === 'series_comparison') {
    return { kind: 'series_comparison', params: { field: breadthSeriesMemberField.value, target_field: breadthSeriesReferenceField.value, relation: breadthSeriesRelation.value, operator: breadthComparisonOperator.value, threshold: breadthComparisonThreshold.value } }
  }
  if (breadthConditionKind.value === 'event') {
    return { kind: 'event', params: { event_type: breadthEventType.value, lookback_days: breadthEventLookbackDays.value, include_estimates: breadthEventIncludeEstimates.value, operator: breadthComparisonOperator.value, threshold: 1 } }
  }
  if (breadthConditionKind.value === 'comparison') {
    return comparisonCondition(breadthComparisonField.value, breadthComparisonOperator.value, breadthComparisonThreshold.value)
  }
  if (breadthConditionKind.value === 'range') {
    return { kind: 'range', params: { field: breadthRangeField.value, lower: breadthRangeLower.value, upper: breadthRangeUpper.value, inclusive: true } }
  }
  if (breadthConditionKind.value === 'percentile') {
    return { kind: 'percentile', target_scope: breadthPercentileScope.value, params: { field: breadthPercentileField.value, period: breadthPercentilePeriod.value, percentile: breadthPercentileTarget.value, operator: breadthComparisonOperator.value } }
  }
  if (breadthConditionKind.value === 'cross_sectional_statistic') {
    const statistic = String(breadthConfigurationValue('breadth_cross_sectional_statistic', 'mean'))
    const selectedStatistic = ['mean', 'median', 'min', 'max', 'std'].includes(statistic) ? statistic : 'mean'
    return { kind: 'cross_sectional_statistic', target_scope: 'cross_sectional', params: { field: breadthComparisonField.value, statistic: selectedStatistic, operator: breadthComparisonOperator.value, threshold: breadthComparisonThreshold.value } }
  }
  if (breadthConditionKind.value === 'within_52_week_high') {
    return { kind: 'within_52_week_high', params: { lookback: breadthConditionLookback.value, threshold: breadthConditionThreshold.value, direction: breadthHighLowDirection.value } }
  }
  if (breadthConditionKind.value === 'new_high_low') {
    return { kind: 'new_high_low', params: { lookback: breadthConditionLookback.value, direction: breadthHighLowDirection.value } }
  }
  if (breadthConditionKind.value === 'prior_high_low') {
    return { kind: 'prior_high_low', params: { lookback: breadthConditionLookback.value, direction: breadthHighLowDirection.value, operator: breadthComparisonOperator.value, threshold: breadthComparisonThreshold.value } }
  }
  if (breadthConditionKind.value === 'trend') {
    return { kind: 'trend', params: { fast_period: breadthConditionFastPeriod.value, slow_period: breadthConditionSlowPeriod.value, direction: breadthConditionDirection.value } }
  }
  if (breadthConditionKind.value === 'rsi') {
    return { kind: 'rsi', params: { period: breadthConditionRsiPeriod.value, operator: breadthComparisonOperator.value, threshold: breadthComparisonThreshold.value } }
  }
  if (breadthConditionKind.value === 'volume_ratio') {
    return { kind: 'volume_ratio', params: { period: breadthConditionVolumePeriod.value, operator: breadthComparisonOperator.value, threshold: breadthComparisonThreshold.value } }
  }
  if (breadthConditionKind.value === 'relative_strength') {
    return { kind: 'relative_strength', params: { lookback: breadthConditionLookback.value, operator: breadthComparisonOperator.value, threshold: breadthComparisonThreshold.value } }
  }
  return { kind: 'above_moving_average', params: { period: breadthConditionPeriod.value, average: breadthConditionAverage.value, comparator: 'above' } }
}
const genericBreadthDefinition = computed(() => ({
  version: 1,
  universe: {
    kind: breadthCustomUniverseKind.value,
    ...(breadthCustomUniverseKind.value === 'group'
      ? { key: breadthGroupKey.value }
      : breadthCustomUniverseKind.value === 'benchmark_family'
        ? { key: breadthGroupKey.value, role: familyRatioRole.value }
        : breadthCustomUniverseKind.value === 'watchlist'
          ? { key: breadthWatchlistSourceId.value }
          : { key: 'SPY' }),
    point_in_time: true,
  },
  condition: breadthComposition.value === 'tree'
    ? breadthTreeCondition.value
    : breadthComposition.value === 'all' || breadthComposition.value === 'any'
    ? { kind: breadthComposition.value, params: { conditions: [primaryBreadthCondition(), comparisonCondition(breadthSecondaryField.value, 'gte', breadthSecondaryThreshold.value)] } }
    : breadthComposition.value === 'not'
      ? { kind: 'not', params: { conditions: [primaryBreadthCondition()] } }
      : primaryBreadthCondition(),
  timeframe: breadthTimeframe.value,
  adjusted: breadthAdjusted.value,
  ...(familyAsOf.value ? { as_of: familyAsOf.value } : {}),
  ...(breadthReferenceTarget.value === 'group'
    ? { reference_universe: { kind: 'group', key: breadthReferenceGroup.value, point_in_time: true } }
    : { benchmark: breadthBenchmark.value }),
}))
const genericBreadthKey = computed(() => breadthUsesPython.value ? breadthPythonRequestKey.value : JSON.stringify(genericBreadthDefinition.value))
const genericBreadth = computed<GenericBreadthState | null>(() => {
  if (breadthUsesPython.value) {
    return breadthPythonSeriesState.value?.current ? asGenericBreadthState(breadthPythonSeriesState.value) : null
  }
  return workspaceStore.genericBreadth[genericBreadthKey.value] ?? null
})
const genericBreadthHistory = computed<GenericBreadthHistoryState | null>(() => {
  if (breadthUsesPython.value) {
    return breadthPythonSeriesState.value ? asGenericBreadthHistory(breadthPythonSeriesState.value) : null
  }
  return workspaceStore.genericBreadthHistory[genericBreadthKey.value] ?? null
})
const genericBreadthLoading = computed(() => breadthUsesPython.value
  ? breadthPythonSeriesLoading.value
  : workspaceStore.genericBreadthLoading[genericBreadthKey.value] === true || workspaceStore.genericBreadthHistoryLoading[genericBreadthKey.value] === true)
const genericBreadthError = computed(() => {
  if (breadthUsesPython.value) {
    if (breadthPythonSeriesError.value) return breadthPythonSeriesError.value
    if (breadthPythonSeriesStatus.value === 'failed') return 'The isolated Python breadth run failed.'
    if (breadthPythonSeriesStatus.value === 'canceled') return 'The isolated Python breadth run was canceled.'
    return null
  }
  return workspaceStore.genericBreadthErrors[genericBreadthKey.value] ?? workspaceStore.genericBreadthHistoryErrors[genericBreadthKey.value] ?? null
})
const genericBreadthPercentage = computed(() => genericBreadth.value?.percentage == null ? 'Unavailable' : `${(genericBreadth.value.percentage * 100).toFixed(1)}%`)
const genericBreadthCoverage = computed(() => genericBreadth.value == null ? 'Unavailable' : `${(genericBreadth.value.coverage * 100).toFixed(1)}%`)
const genericBreadthMemberState = ref<'pass' | 'fail'>('pass')
const genericBreadthDefinitionName = ref('')
const genericBreadthDefinitionSaving = ref(false)
const genericBreadthDefinitionMessage = ref('')
const genericBreadthDefinitionError = ref('')
const genericBreadthMembers = computed(() => (genericBreadth.value?.members ?? []).filter(member => member.value === (genericBreadthMemberState.value === 'pass')))
const genericBreadthDiagnostics = computed(() => (genericBreadth.value?.members ?? []).flatMap(member => member.diagnostics ?? []).slice(0, 100))
const genericBreadthHistoryOccurrences = computed(() => [...(genericBreadthHistory.value?.occurrences ?? [])].reverse().slice(0, 100))

function genericBreadthOccurrenceLabel(occurrence: { kind: 'member_entered' | 'member_exited' }) {
  return occurrence.kind === 'member_entered' ? 'Entered condition' : 'Exited condition'
}

function genericBreadthDiagnosticLabel(diagnostic: { path: string; kind: string; status: string; code?: string | null }) {
  const state = diagnostic.status === 'excluded' ? 'excluded' : diagnostic.status
  return `${diagnostic.path} ${diagnostic.kind} ${state}${diagnostic.code ? ` (${diagnostic.code})` : ''}`
}
async function runGenericBreadth() {
  if (breadthUsesPython.value) {
    const anchor = breadthTreePythonSeriesLeaf.value
    if (anchor && pythonLeafAnchorId(anchor) == null) return
    if (!anchor && breadthPythonSeriesCodeVersionId.value == null) return
    await workspaceStore.loadPythonBreadth(breadthPythonRequest.value, breadthPythonRequestKey.value)
    return
  }
  await Promise.all([
    workspaceStore.loadGenericBreadth(genericBreadthDefinition.value, genericBreadthKey.value),
    workspaceStore.loadGenericBreadthHistory(genericBreadthDefinition.value, genericBreadthKey.value),
  ])
}
async function saveGenericBreadthDefinition() {
  if (genericBreadthDefinitionSaving.value || breadthUsesPython.value || !genericBreadthDefinitionName.value || !genericBreadthDefinition.value) return
  genericBreadthDefinitionSaving.value = true
  genericBreadthDefinitionMessage.value = ''
  genericBreadthDefinitionError.value = ''
  try {
    const definition = genericBreadthDefinition.value as BreadthDefinition
    await api.post('/code/assets', buildBreadthStudyAssetPayload(genericBreadthDefinitionName.value, definition))
    await queryClient.invalidateQueries({ queryKey: ['workstation', 'library-items'] })
    genericBreadthDefinitionMessage.value = 'Saved immutable Study Lab definition.'
  } catch (cause) {
    genericBreadthDefinitionError.value = cause instanceof Error ? cause.message : 'Unable to save reusable breadth definition'
  } finally {
    genericBreadthDefinitionSaving.value = false
  }
}
const technical = computed(() => workspaceStore.technicals[activeSymbol.value])
const selectedETF = computed(() => workspaceStore.constituentETF ?? '')
const sectorSymbols = computed(() => new Set(
  (workspaceStore.marketGroups['sp500-sectors']?.members ?? [])
    .map(member => member.instrument.symbol.trim().toUpperCase())
    .filter(Boolean),
))
// During ETF hydration, the shared constituentETF can briefly describe the
// previous symbol while the visible Industries tool already follows the newly
// linked sector. Prefer that explicit sector link for row clicks; once the
// active symbol is a stock/proxy, retain the selected ETF context.
const industryETFContext = computed(() => {
  const linked = activeSymbol.value.trim().toUpperCase()
  return sectorSymbols.value.has(linked) ? linked : selectedETF.value
})
const ratioBenchmarks = computed(() => {
  const configured = props.tool.configuration.ratio_benchmarks
  if (Array.isArray(configured)) {
    const normalized = [...new Set(configured.filter(value => typeof value === 'string').map(value => value.trim().toUpperCase()).filter(Boolean))]
      .filter(value => value !== activeSymbol.value.trim().toUpperCase())
    if (normalized.length) return normalized
  }
  return autoRatioBenchmarks(
    activeSymbol.value,
    (workspaceStore.marketGroups['sp500-sectors']?.members ?? []).map(member => member.instrument.symbol),
    selectedETF.value,
  )
})
const holdings = computed(() => selectedETF.value ? workspaceStore.etfHoldings[selectedETF.value] : null)
const constituentSnapshot = computed(() => selectedETF.value ? workspaceStore.etfConstituentSnapshots[selectedETF.value] : null)
const industryComposition = computed(() => selectedETF.value ? workspaceStore.etfIndustries[selectedETF.value] : null)
const industries = computed(() => industryComposition.value?.industries ?? [])
const industrySnapshot = computed(() => selectedETF.value ? workspaceStore.industrySnapshots[selectedETF.value] : null)
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
  instrumentId: row.instrument_id,
  symbol: row.symbol,
  name: row.name,
  values: {
    performance_1d: row.performance['1D']?.value ?? null,
    performance_1w: row.performance['1W']?.value ?? null,
    performance_1m: row.performance['1M']?.value ?? null,
    performance_3m: row.performance['3M']?.value ?? null,
    performance_6m: row.performance['6M']?.value ?? null,
    performance_ytd: row.performance.YTD?.value ?? null,
    performance_1y: row.performance['1Y']?.value ?? null,
    relative_sector: row.relative_to_benchmark?.value ?? null,
    relative_spy: row.relative_to_market?.value ?? null,
    rsi14: row.technical.rsi14?.value ?? null,
    source: evidence?.source_provider ?? 'Unavailable',
    as_of: evidence?.composition_date ?? 'Unavailable',
    known_at: evidence?.known_at ? new Date(evidence.known_at).toLocaleDateString() : 'Unknown',
    ...snapshotLineage(industryProxySnapshot.value),
  },
  warnings: {
    performance_1d: cellWarning(row.performance['1D']),
    performance_1w: cellWarning(row.performance['1W']),
    performance_1m: cellWarning(row.performance['1M']),
    performance_3m: cellWarning(row.performance['3M']),
    performance_6m: cellWarning(row.performance['6M']),
    performance_ytd: cellWarning(row.performance.YTD),
    performance_1y: cellWarning(row.performance['1Y']),
    relative_sector: cellWarning(row.relative_to_benchmark),
    relative_spy: cellWarning(row.relative_to_market),
    rsi14: cellWarning(row.technical.rsi14),
  },
}}))
const proxyMarketMapSourceId = computed(() => explicitMarketMapSourceId(proxyRows.value))
const constituents = computed(() => {
  if (selectedETF.value && selectedIndustry.value) {
    return workspaceStore.industryConstituents[`${selectedETF.value}:${selectedIndustry.value}`]?.constituents.map(row => row.symbol) ?? []
  }
  return holdings.value?.holdings.filter(row => row.is_resolved && Boolean(row.constituent_symbol)).map(row => row.constituent_symbol as string) ?? []
})
const industryRows = computed(() => industries.value.map(item => ({
  instrumentId: null,
  industry: item.industry,
  resolved_count: item.resolved_count,
  constituent_count: item.constituent_count,
  symbol: item.industry,
  name: `${item.resolved_count}/${item.constituent_count}`,
  classificationLabel: classificationLabel(item.classification_systems),
  classificationDetail: classificationDetail(item.classification_systems),
  warnings: (() => {
    const analysis = industrySnapshot.value?.rows.find(row => row.industry === item.industry)
    const warnings: Record<string, string> = {}
    for (const [period, cell] of Object.entries(analysis?.performance ?? {})) if (cell.warning?.message) warnings[`performance_${period.toLowerCase()}`] = cell.warning.message
    if (analysis?.relative_to_benchmark?.warning?.message) warnings.relative_ratio = analysis.relative_to_benchmark.warning.message
    if (analysis?.relative_to_market?.warning?.message) warnings.relative_spy = analysis.relative_to_market.warning.message
    for (const [key, cell] of Object.entries(analysis?.technical ?? {})) if (cell.warning?.message) warnings[key] = cell.warning.message
    return warnings
  })(),
  values: {
    proxy_count: workspaceStore.industryProxies[`${selectedETF.value}:${item.industry}`]?.proxies.length ?? null,
    coverage: item.constituent_count ? item.resolved_count / item.constituent_count : null,
    as_of: holdings.value?.snapshot?.composition_date ?? 'unavailable',
    provenance: holdings.value?.snapshot?.source_provider ?? 'ETF holdings classification',
    ...(() => {
      const analysis = industrySnapshot.value?.rows.find(row => row.industry === item.industry)
      return {
        performance_1d: analysis?.performance['1D']?.value ?? null,
        performance_1w: analysis?.performance['1W']?.value ?? null,
        performance_1m: analysis?.performance['1M']?.value ?? null,
        performance_3m: analysis?.performance['3M']?.value ?? null,
        performance_6m: analysis?.performance['6M']?.value ?? null,
        performance_ytd: analysis?.performance.YTD?.value ?? null,
        performance_1y: analysis?.performance['1Y']?.value ?? null,
        relative_ratio: analysis?.relative_to_benchmark?.value ?? null,
        relative_spy: analysis?.relative_to_market?.value ?? null,
        rsi14: analysis?.technical?.rsi14?.value ?? null,
        position_52w: analysis?.technical?.position_52w?.value ?? null,
      }
    })(),
  },
})))
const industryRankingColumns: WatchlistColumn[] = [
  { key: 'performance_1d', label: '1D', width: '52px' },
  { key: 'performance_1w', label: '1W', width: '52px' },
  { key: 'performance_1m', label: '1M', width: '52px' },
  { key: 'performance_3m', label: '3M', width: '52px' },
  { key: 'performance_6m', label: '6M', width: '52px' },
  { key: 'performance_ytd', label: 'YTD', width: '52px' },
  { key: 'performance_1y', label: '1Y', width: '52px' },
  { key: 'relative_ratio', label: '/ Sector', width: '68px', format: 'number' },
  { key: 'relative_spy', label: '/ SPY', width: '58px', format: 'number' },
  { key: 'rsi14', label: 'RSI', width: '52px', format: 'number' },
  { key: 'position_52w', label: '52W Pos', width: '68px' },
]
function displayIndustryValue(item: { values: Record<string, string | number | null> }, key: string) {
  const value = item.values[key]
  if (value == null) return '—'
  if (typeof value !== 'number') return value
  return key === 'rsi14' || key === 'position_52w' || key === 'relative_ratio' || key === 'relative_spy'
    ? value.toFixed(2)
    : `${(value * 100).toFixed(2)}%`
}
function classificationLabel(systems?: string[]) {
  const values = [...new Set((systems ?? []).filter(Boolean))]
  if (!values.length) return 'Unclassified'
  if (values.length === 1 && values[0] === 'unknown') return 'Unknown source'
  if (values.length === 1) return values[0]
  return 'Mixed sources'
}
function classificationDetail(systems?: string[]) {
  const values = [...new Set((systems ?? []).filter(Boolean))]
  return values.length ? `Classification source: ${values.join(', ')}` : 'No source-labelled classification evidence'
}
const industryClassificationSummary = computed(() => {
  const composition = industryComposition.value
  if (!composition) return 'classification provenance unavailable'
  const systems = [...new Set((composition.classification_systems ?? []).filter(Boolean))]
  const coverage = composition.classification_coverage
  const coverageLabel = coverage == null ? 'coverage unavailable' : `${(coverage * 100).toFixed(0)}% classified`
  return `${systems.length ? systems.join(' + ') : 'unclassified'} · ${coverageLabel}`
})
const constituentLabel = computed(() => {
  const industrySnapshot = selectedETF.value && selectedIndustry.value
    ? workspaceStore.industryConstituents[`${selectedETF.value}:${selectedIndustry.value}`]
    : null
  if (industrySnapshot) {
    const systems = (industrySnapshot.classification_systems ?? []).join(' + ') || 'unknown source'
    const coverage = industrySnapshot.classification_coverage == null
      ? 'coverage unavailable'
      : `${(industrySnapshot.classification_coverage * 100).toFixed(0)}% classified`
    const excluded = industrySnapshot.exclusions?.length ? ` · ${industrySnapshot.exclusions.length} excluded` : ''
    return `${industrySnapshot.etf_symbol} · ${industrySnapshot.industry} constituents · ${industrySnapshot.composition_date} · ${industrySnapshot.source_provider} · ${systems} · ${coverage}${excluded}`
  }
  if (!holdings.value) return 'No point-in-time ETF holdings snapshot'
  return `${holdings.value.snapshot.etf_symbol} holdings · ${holdings.value.snapshot.composition_date} · ${holdings.value.snapshot.source_provider}`
})
const constituentExclusionCodes = computed(() => {
  const industrySnapshot = selectedETF.value && selectedIndustry.value
    ? workspaceStore.industryConstituents[`${selectedETF.value}:${selectedIndustry.value}`]
    : null
  return [...new Set(industrySnapshot?.exclusions ?? [])]
})
const constituentExclusionSummary = computed(() => {
  if (!constituentExclusionCodes.value.length) return ''
  return `Excluded from constituent view: ${constituentExclusionCodes.value.join(' · ')}`
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
const benchmarkFamilyRows = computed(() => {
  const key = benchmarkFamilyKey.value
  if (!key) return []
  const snapshot = benchmarkFamilySnapshot.value
  return (workspaceStore.marketGroups[key]?.members ?? []).map(member => {
    const row = snapshot?.rows.find(item => item.instrument_id === member.instrument.id)
    return {
      instrumentId: member.instrument.id,
      symbol: member.instrument.symbol,
      name: member.instrument.name,
      values: {
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
        ...snapshotLineage(snapshot),
      },
      warnings: snapshotWarnings(row),
    }
  })
})
const activeBenchmarkRows = computed(() => benchmarkFamilyKey.value ? benchmarkFamilyRows.value : benchmarkRows.value)
function benchmarkFamilyMarketMapSourceForRow(row: WatchlistRow): string | null {
  const familyKey = benchmarkFamilyKey.value
  const overview = benchmarkFamilyOverview.value
  if (!familyKey || !overview) return null
  const mapping = overview.mappings.find(item => item.symbol?.toUpperCase() === row.symbol.toUpperCase())
  if (!mapping || !mapping.symbol || !mapping.holdings_available || mapping.available === false) return null
  return benchmarkFamilyConstituentSourceId(familyKey, mapping.role)
}
const activeBenchmarkDataError = computed(() => benchmarkFamilyKey.value ? benchmarkFamilyError.value : benchmarkDataError.value)
const benchmarkDataError = computed(() => workspaceStore.marketGroupErrors['us-benchmarks'] ?? workspaceStore.groupSnapshotErrors['us-benchmarks'] ?? '')
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
const sectorDataError = computed(() => workspaceStore.marketGroupErrors['sp500-sectors'] ?? workspaceStore.groupSnapshotErrors['sp500-sectors'] ?? '')
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
  if (title.includes('industry') || title.includes('industries')) return industryRows.value
  if (title.includes('component') || title.includes('constituent')) return constituentRows.value
  return benchmarkRows.value
})
const factoryWatchlistSourceId = computed(() => {
  const title = (props.tool.title ?? '').toLowerCase()
  const factoryLayout = typeof props.tool.configuration.factory_layout === 'string' ? props.tool.configuration.factory_layout : ''
  if (props.factoryLayout === 'sector-by-year' || factoryLayout === 'sector-by-year' || title.includes('sector')) return 'market-group:sp500-sectors'
  if (title.includes('industry') || title.includes('industries')) return null
  if (title.includes('component') || title.includes('constituent')) return constituentMarketMapSourceId.value
  return 'market-group:us-benchmarks'
})
const factoryWatchlistColumns = computed<WatchlistColumn[]>(() => {
  const title = (props.tool.title ?? '').toLowerCase()
  const factoryLayout = typeof props.tool.configuration.factory_layout === 'string' ? props.tool.configuration.factory_layout : ''
  if (props.factoryLayout === 'sector-by-year' || factoryLayout === 'sector-by-year' || title.includes('sector by year')) return sectorByYearColumns.value
  if (title.includes('sector')) return sectorColumns
  if (title.includes('industry') || title.includes('industries')) return industryColumns
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
        performance_1d: analysis?.performance['1D']?.value ?? null,
        performance_1w: analysis?.performance['1W']?.value ?? null,
        performance_1m: analysis?.performance['1M']?.value ?? null,
        performance_3m: analysis?.performance['3M']?.value ?? null,
        performance_6m: analysis?.performance['6M']?.value ?? null,
        performance_ytd: analysis?.performance.YTD?.value ?? null,
        performance_1y: analysis?.performance['1Y']?.value ?? null,
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
const constituentMarketMapSourceId = computed(() => {
  if (selectedETF.value && !selectedIndustry.value) return `etf-holdings:${selectedETF.value}`
  return explicitMarketMapSourceId(constituentRows.value)
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
  { key: 'coverage', label: 'Coverage', width: '68px' },
  { key: 'freshness', label: 'Freshness', width: '74px' },
  { key: 'provenance', label: 'Provenance', width: '92px' },
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
  ...industryRankingColumns,
  { key: 'coverage', label: 'Coverage %', width: '72px', format: 'percent' },
  { key: 'as_of', label: 'As of', width: '74px' },
  { key: 'provenance', label: 'Provenance', width: '110px' },
]
const constituentColumns: WatchlistColumn[] = [
  { key: 'symbol', label: 'Symbol', width: '60px' },
  { key: 'name', label: 'Constituent', width: 'minmax(100px, 1fr)' },
  { key: 'weight', label: 'Weight', width: '62px' },
  { key: 'performance_1d', label: '1D', width: '52px' },
  { key: 'performance_1w', label: '1W', width: '52px' },
  { key: 'performance_1m', label: '1M', width: '58px' },
  { key: 'performance_3m', label: '3M', width: '52px' },
  { key: 'performance_6m', label: '6M', width: '52px' },
  { key: 'performance_ytd', label: 'YTD', width: '52px' },
  { key: 'performance_1y', label: '1Y', width: '52px' },
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
  { key: 'performance_1d', label: '1D', width: '52px' },
  { key: 'performance_1w', label: '1W', width: '52px' },
  { key: 'performance_1m', label: '1M', width: '54px' },
  { key: 'performance_3m', label: '3M', width: '52px' },
  { key: 'performance_6m', label: '6M', width: '52px' },
  { key: 'performance_ytd', label: 'YTD', width: '52px' },
  { key: 'performance_1y', label: '1Y', width: '52px' },
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
type IndicatorColumnConfiguration = { key: string; name: string; indicator: string; params: Record<string, unknown>; timeframe: string; output?: string }
const pendingIndicatorColumns = ref<IndicatorColumnConfiguration[]>([])
const configuredIndicatorColumns = computed<IndicatorColumnConfiguration[]>(() => {
  const persisted = Array.isArray(props.tool.configuration.indicator_columns)
    ? props.tool.configuration.indicator_columns.filter((column): column is IndicatorColumnConfiguration => Boolean(column) && typeof column === 'object' && typeof (column as Record<string, unknown>).key === 'string' && typeof (column as Record<string, unknown>).name === 'string' && typeof (column as Record<string, unknown>).indicator === 'string' && typeof (column as Record<string, unknown>).params === 'object' && typeof (column as Record<string, unknown>).timeframe === 'string')
    : []
  const persistedKeys = new Set(persisted.map(column => column.key))
  return [...persisted, ...pendingIndicatorColumns.value.filter(column => !persistedKeys.has(column.key))]
})
type ConditionColumnConfiguration = { key: string; name: string; screener_id: number; timeframe: string }
// Keep a just-created condition column visible while the debounced workspace
// snapshot crosses the parent/Golden Layout boundary.
const pendingConditionColumns = ref<ConditionColumnConfiguration[]>([])
const configuredConditionColumns = computed<ConditionColumnConfiguration[]>(() => {
  const persisted = Array.isArray(props.tool.configuration.condition_columns)
    ? props.tool.configuration.condition_columns.filter((column): column is ConditionColumnConfiguration => Boolean(column) && typeof column === 'object' && typeof (column as Record<string, unknown>).key === 'string' && typeof (column as Record<string, unknown>).name === 'string' && Number.isInteger((column as Record<string, unknown>).screener_id) && typeof (column as Record<string, unknown>).timeframe === 'string')
    : []
  const persistedKeys = new Set(persisted.map(column => column.key))
  return [...persisted, ...pendingConditionColumns.value.filter(column => !persistedKeys.has(column.key))]
})

function addPlotColumn(payload: ChartAnalysisDragPayload) {
  if (payload.kind === 'python-plot') {
    const column = pythonColumnFromPlot(payload)
    const columns = Array.isArray(props.tool.configuration.python_columns) ? props.tool.configuration.python_columns : []
    const hasColumn = columns.some(candidate => Boolean(candidate) && typeof candidate === 'object' && Number(candidate.code_version_id) === column.code_version_id)
    const key = `python:${column.code_version_id}`
    const configuredKeys = Array.isArray(props.tool.configuration.column_keys)
      ? props.tool.configuration.column_keys.filter((candidate): candidate is string => typeof candidate === 'string')
      : []
    const nextKeys = configuredKeys.includes(key) ? configuredKeys : [...configuredKeys, key]
    if (hasColumn && nextKeys.length === configuredKeys.length) return
    emit('configuration', props.tool.instance_key, {
      ...props.tool.configuration,
      column_keys: nextKeys,
      python_columns: hasColumn ? columns : [...columns, column],
    })
    return
  }
  if (payload.kind !== 'chart-plot') return
  const column = indicatorColumnFromPlot(payload)
  const columns = Array.isArray(props.tool.configuration.indicator_columns) ? props.tool.configuration.indicator_columns : []
  const hasColumn = columns.some(candidate => Boolean(candidate) && typeof candidate === 'object' && (candidate as Record<string, unknown>).key === column.key)
  const configuredKeys = Array.isArray(props.tool.configuration.column_keys)
    ? props.tool.configuration.column_keys.filter((key): key is string => typeof key === 'string')
    : []
  // A configured column list is authoritative for a customized watchlist. A
  // dropped plot must therefore both register the definition and make it
  // visible; otherwise the definition exists but is silently hidden.
  const nextKeys = configuredKeys.includes(column.key) ? configuredKeys : [...configuredKeys, column.key]
  pendingIndicatorColumns.value = [...pendingIndicatorColumns.value.filter(existing => existing.key !== column.key), column]
  emit('configuration', props.tool.instance_key, {
    ...props.tool.configuration,
    column_keys: nextKeys,
    indicator_columns: hasColumn ? columns : [...columns, column],
  })
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
        queryFn: async () => (await api.get<Array<{ matched_ids?: number[] }>>(`/screeners/${column.screener_id}/results`, { limit: 1 })) ?? [],
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
    const screenerName = `${name} Boolean`
    const existing = await queryClient.fetchQuery<Array<{ id: number; name: string }>>({
      queryKey: ['workstation', 'screeners'],
      queryFn: async () => (await api.get<Array<{ id: number; name: string }>>('/screeners')) ?? [],
      staleTime: 30_000,
    })
    let scan: { id: number } = existing.find(item => item.name.toLowerCase() === screenerName.toLowerCase()) ?? { id: 0 }
    if (!scan.id) {
      scan = await api.post<{ id: number }>(`/screeners/from-condition/${encodeURIComponent(stableKey)}`, {
        name: screenerName, universe_type: 'all', timeframe: payload.timeframe,
      })
    }
    await api.post(`/screeners/${scan.id}/run`, {})
    await queryClient.invalidateQueries({ queryKey: ['workstation', 'screeners'] })
    const column: ConditionColumnConfiguration = { key, name, screener_id: scan.id, timeframe: payload.timeframe }
    pendingConditionColumns.value = [...pendingConditionColumns.value.filter(existing => existing.key !== key), column]
    const columns = Array.isArray(props.tool.configuration.condition_columns) ? props.tool.configuration.condition_columns : []
    const configuredKeys = Array.isArray(props.tool.configuration.column_keys)
      ? props.tool.configuration.column_keys.filter((candidate): candidate is string => typeof candidate === 'string')
      : []
    // A customized watchlist treats column_keys as the visible-column
    // allow-list. Register the dropped condition there as well as in the
    // column definition, otherwise the successful drag is persisted but the
    // new Boolean header remains hidden until the user edits Columns.
    const nextKeys = configuredKeys.includes(column.key) ? configuredKeys : [...configuredKeys, column.key]
    emit('configuration', props.tool.instance_key, { ...props.tool.configuration, column_keys: nextKeys, condition_columns: [...columns, column] })
    void loadConditionColumns([...personalWatchlistRows.value, ...flaggedWatchlistRows.value, ...comboWatchlistRows.value, ...activeBenchmarkRows.value, ...sectorRows.value, ...factoryWatchlistRows.value, ...proxyRows.value, ...constituentRows.value])
  } catch (cause: any) {
    pendingConditionColumns.value = pendingConditionColumns.value.filter(column => column.key !== key)
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
        queryFn: async ({ signal }) => {
          const result = await api.post<{ values: Record<string, { value?: number | null; warning?: { code?: string } | null }> }>('/analysis/indicator-batch', {
            symbols: requestSymbols, indicator: column.indicator, params, timeframe: column.timeframe, adjusted: true,
          }, { signal })
          if (!result) throw new Error('Indicator batch returned no data')
          return result
        },
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
    ...activeBenchmarkRows.value,
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
      ...activeBenchmarkRows.value,
      ...sectorRows.value,
      ...factoryWatchlistRows.value,
      ...proxyRows.value,
      ...constituentRows.value,
    ])
    void loadConditionColumns([
      ...personalWatchlistRows.value,
      ...flaggedWatchlistRows.value,
      ...comboWatchlistRows.value,
      ...activeBenchmarkRows.value,
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
const freshnessLabel = (value?: string) => value ? ` · ${formatWorkstationFreshness(value)}` : ''
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
  const normalized = groupKey === 'us-benchmarks' || groupKey === 'sp500-sectors' || benchmarkFamilyOptions.value.some(family => family.logicalKey === groupKey)
    ? groupKey
    : 'sp500-sectors'
  setBreadthConfiguration({ group_key: normalized })
}
function setBenchmarkFamily(familyKey: string) {
  const normalized = benchmarkFamilyOptions.value.some(family => family.logicalKey === familyKey) ? familyKey : ''
  benchmarkFamilyKey.value = normalized
  benchmarkFamilyMapRole.value = 'cap_weight'
  emit('configuration', props.tool.instance_key, {
    ...props.tool.configuration,
    benchmark_family_key: normalized || null,
    benchmark_family_map_role: normalized ? 'cap_weight' : null,
  })
}
function setBenchmarkFamilyMapRole(role: string) {
  const normalized = benchmarkFamilyMapRoles.includes(role as BenchmarkFamilyMapRole) ? role as BenchmarkFamilyMapRole : 'cap_weight'
  const available = benchmarkFamilyMapRoleOptions.value.find(item => item.role === normalized)?.available ?? false
  if (!available) return
  benchmarkFamilyMapRole.value = normalized
  emit('configuration', props.tool.instance_key, { ...props.tool.configuration, benchmark_family_map_role: normalized })
}
function setBreadthConfiguration(configuration: Record<string, unknown>) {
  let nextConfiguration = configuration
  // The compact breadth editor reuses a small set of controls across several
  // condition kinds.  A value entered for one kind must not silently become
  // the default for the next kind (for example, a volume-ratio target of 1.5
  // becoming a prior-high distance).  Seed the shared control with the
  // documented default whenever the condition selector changes; the user can
  // then explicitly edit the new field.
  if (typeof configuration.breadth_condition === 'string') {
    const defaults: Record<string, number> = {
      rsi: 50,
      volume_ratio: 1,
      prior_high_low: 0.01,
      relative_strength: 0,
      comparison: 0,
      series_comparison: 0,
      cross_sectional_statistic: 0,
      event: 1,
    }
    const defaultThreshold = defaults[configuration.breadth_condition]
    if (defaultThreshold !== undefined) {
      nextConfiguration = { ...configuration, breadth_comparison_threshold: defaultThreshold }
    }
  }
  breadthDraftConfiguration.value = { ...breadthDraftConfiguration.value, ...nextConfiguration }
  emit('configuration', props.tool.instance_key, { ...props.tool.configuration, ...breadthDraftConfiguration.value })
}
function setBreadthNumber(key: string, event: Event) {
  const raw = (event.target as HTMLInputElement | null)?.value ?? ''
  const value = Number(raw)
  // Keep the last valid draft while a user is midway through typing a numeric
  // value (for example the transient '-' in a negative range). The blur/change
  // event still validates the final value through the same handler.
  if (!Number.isFinite(value)) return
  setBreadthConfiguration({ [key]: value })
}
async function loadBreadthPythonSeriesAssets() {
  if (props.tool.instance_key !== 'breadth-summary' && props.tool.tool_type !== 'breadth') return
  breadthPythonSeriesAssetsLoading.value = true
  try {
    const assets = await fetchCodeAssets(queryClient)
    breadthPythonSeriesAssets.value = assets
      .filter((asset: CodeAssetSummary) => asset.kind === 'condition')
      .flatMap((asset: CodeAssetSummary) => {
        const version = asset.versions[asset.versions.length - 1]
        return version?.id != null && version.output_contract === 'series'
          ? [{ versionId: version.id, name: `${asset.name} v${version.version_number}` }]
          : []
      })
  } catch {
    breadthPythonSeriesAssets.value = []
  } finally {
    breadthPythonSeriesAssetsLoading.value = false
  }
}
async function loadBreadthUniverse(groupKey: string, timeframe = breadthTimeframe.value, adjusted = breadthAdjusted.value, lookback = breadthLookback.value) {
  const options = { ...(timeframe !== 'D1' ? { timeframe } : {}), ...(adjusted !== true ? { adjusted } : {}), ...(lookback !== 20 ? { new_high_lookback: lookback } : {}), ...(familyAsOf.value ? { as_of: familyAsOf.value } : {}) }
  const registry = workspaceStore.marketGroups['us-benchmarks']?.provenance?.benchmark_families
  const familyRecord = Array.isArray(registry)
    ? registry.find(item => item && typeof item === 'object' && (item as Record<string, unknown>).logical_key === groupKey) as Record<string, unknown> | undefined
    : undefined
  const capMapping = familyRecord?.cap_weight && typeof familyRecord.cap_weight === 'object' ? familyRecord.cap_weight as Record<string, unknown> : null
  const familyBenchmark = typeof capMapping?.symbol === 'string' && capMapping.symbol.trim() ? capMapping.symbol.trim().toUpperCase() : undefined
  // Family roots must never borrow SPY when their own cap mapping is absent. The
  // generic sector/benchmark groups retain their established SPY comparison.
  const snapshotBenchmark = familyRecord ? familyBenchmark : 'SPY'
  await Promise.all([
    workspaceStore.loadMarketGroup(groupKey),
    workspaceStore.loadGroupSnapshot(groupKey, snapshotBenchmark, options),
    workspaceStore.loadBreadth(groupKey, options),
    workspaceStore.loadBreadthHistory(groupKey, options),
  ])
}
let benchmarkFamilyLoadSequence = 0
watch([benchmarkFamilyKey, benchmarkFamilyCapProxy, activeTimeframe], async ([familyKey, _capProxy, timeframe]) => {
  if (props.tool.instance_key !== 'benchmark-list' || !familyKey) return
  const sequence = ++benchmarkFamilyLoadSequence
  benchmarkFamilyLoading.value = true
  try {
    await Promise.all([
      workspaceStore.loadMarketGroup(familyKey),
      workspaceStore.loadGroupSnapshot(familyKey, benchmarkFamilyCapProxy.value, {
        ...(timeframe !== 'D1' ? { timeframe } : {}),
      }),
      workspaceStore.loadBenchmarkFamilyOverview(familyKey, {
        ...(timeframe !== 'D1' ? { timeframe } : {}),
      }),
    ])
  } finally {
    if (sequence === benchmarkFamilyLoadSequence) benchmarkFamilyLoading.value = false
  }
}, { immediate: true })
watch(() => props.tool.instance_key, async instanceKey => {
  if (instanceKey !== 'benchmark-list') return
  benchmarkFamilyReadinessLoading.value = true
  try {
    await workspaceStore.loadBenchmarkFamilyReadiness()
  } finally {
    benchmarkFamilyReadinessLoading.value = false
  }
}, { immediate: true })
watch([breadthGroupKey, breadthTimeframe, breadthAdjusted, breadthLookback, familyAsOf], ([groupKey, timeframe, adjusted, lookback]) => {
  if (props.tool.instance_key === 'breadth-summary' || props.tool.tool_type === 'breadth') void loadBreadthUniverse(groupKey, timeframe, adjusted, lookback)
}, { immediate: true })
watch([breadthGroupKey, breadthTimeframe, breadthAdjusted, familyRatioMarket, familyAsOf, familyRankPeriod], async ([groupKey, timeframe, adjusted, market]) => {
  if (!isBenchmarkFamily.value || !(props.tool.instance_key === 'breadth-summary' || props.tool.tool_type === 'breadth')) return
  familyRatioLoading.value = true
  familyTechnicalsLoading.value = true
  familyBreadthLoading.value = true
  familyRankingLoading.value = true
  familyConcentrationLoading.value = true
  familyConcentrationHistoryLoading.value = true
  crossFamilyRankingLoading.value = true
  crossFamilyRankingHistoryLoading.value = true
  try {
    await Promise.all([
      workspaceStore.loadBenchmarkFamilyRatios(groupKey, familyRatioRole.value, market, { timeframe, adjusted, as_of: familyAsOf.value || undefined, roles: [...familyRatioRoles] }),
      workspaceStore.loadBenchmarkFamilyTechnicals(groupKey, { timeframe, adjusted, as_of: familyAsOf.value || undefined }),
      workspaceStore.loadBenchmarkFamilyBreadth(groupKey, { timeframe, adjusted, as_of: familyAsOf.value || undefined, near_threshold: 0.01, new_high_lookback: 20 }),
      workspaceStore.loadBenchmarkFamilyBreadthHistory(groupKey, { timeframe, adjusted, as_of: familyAsOf.value || undefined, limit: 500 }),
      workspaceStore.loadBenchmarkFamilyRanking(groupKey, { timeframe, adjusted, as_of: familyAsOf.value || undefined, rank_period: familyRankPeriod.value }),
      workspaceStore.loadBenchmarkFamilyConcentration(groupKey, { timeframe, adjusted, as_of: familyAsOf.value || undefined, rank_period: familyRankPeriod.value, top_n: 10 }),
      workspaceStore.loadBenchmarkFamilyConcentrationHistory(groupKey, { timeframe, adjusted, as_of: familyAsOf.value || undefined, rank_period: familyRankPeriod.value, top_n: 10, limit: 500 }),
      workspaceStore.loadCrossFamilyRanking({ timeframe, adjusted, as_of: familyAsOf.value || undefined, rank_period: familyRankPeriod.value }),
      workspaceStore.loadCrossFamilyRankingHistory({ timeframe, adjusted, as_of: familyAsOf.value || undefined, rank_period: familyRankPeriod.value, limit: 500 }),
    ])
  } finally {
    familyRatioLoading.value = false
    familyTechnicalsLoading.value = false
    familyBreadthLoading.value = false
    familyRankingLoading.value = false
    familyConcentrationLoading.value = false
    familyConcentrationHistoryLoading.value = false
    crossFamilyRankingLoading.value = false
    crossFamilyRankingHistoryLoading.value = false
  }
}, { immediate: true })
watch([breadthGroupKey, breadthTimeframe, breadthAdjusted, familyRatioRole, familyRatioMarket, familyAsOf], async ([groupKey, timeframe, adjusted, role, market]) => {
  if (!isBenchmarkFamily.value || !(props.tool.instance_key === 'breadth-summary' || props.tool.tool_type === 'breadth')) return
  familyOverviewLoading.value = true
  try {
    await Promise.all([
      workspaceStore.loadBenchmarkFamilyOverview(groupKey, { timeframe, adjusted, as_of: familyAsOf.value || undefined }),
      workspaceStore.loadBenchmarkFamilyCoverage(groupKey, { as_of: familyAsOf.value || undefined }),
      workspaceStore.loadBenchmarkFamilyConstituents(groupKey, role, { timeframe, adjusted, as_of: familyAsOf.value || undefined, market_benchmark: market }),
    ])
  } finally {
    familyOverviewLoading.value = false
  }
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
.chart-tool__drawing-toolbar { flex: 0 0 40px; max-height: 100%; box-sizing: border-box; overflow-x: hidden; overflow-y: auto; }
.chart-tool__surface { position: relative; z-index: 2; min-width: 0; min-height: 0; flex: 1 1 auto; padding-top: 24px; box-sizing: border-box; }
.chart-tool__status { position: absolute; inset: 24px 0 0; z-index: 4; background: rgba(7, 12, 16, 0.72); pointer-events: none; }
.chart-tool__templates { position: absolute; top: 3px; right: 4px; z-index: 12; }
.chart-tool__plots { position: absolute; top: 3px; left: 150px; z-index: 13; }
.chart-tool__compare { position: absolute; top: 3px; left: 4px; z-index: 12; display: flex; align-items: center; gap: 3px; max-width: calc(100% - 290px); overflow: hidden; }
.chart-tool__compare input { width: 72px; border: 1px solid #42515c; background: #11161b; color: #dce9f2; padding: 2px 4px; font: 10px "Segoe UI", Arial, sans-serif; }
.chart-tool__compare > button { border: 1px solid #42515c; background: #1b252d; color: #b9c9d3; padding: 1px 4px; font: 10px "Segoe UI", Arial, sans-serif; cursor: pointer; white-space: nowrap; }
.chart-tool__compare-chip { overflow: hidden; text-overflow: ellipsis; }
.chart-tool__compare-chip i { display: inline-block; width: 7px; height: 7px; margin-right: 3px; border-radius: 50%; }
@media (max-width: 520px) {
  .chart-tool__surface { padding-top: 46px; }
  .chart-tool__compare { top: 3px; left: 4px; right: 4px; max-width: none; }
  .chart-tool__plots { top: 25px; left: 4px; }
  .chart-tool__templates { top: 25px; right: 4px; }
}
.tool-state { display: grid; place-items: center; height: 100%; padding: 12px; color: #98a7b2; font: 11px "Segoe UI", Arial, sans-serif; text-align: center; }
.tool-state--error { color: #ec8f8f; }
.benchmark-surface { display: grid; grid-template-rows: auto auto auto minmax(0, 1fr); height: 100%; min-height: 0; }
.benchmark-surface__family-controls { display: flex; align-items: center; gap: 8px; min-height: 25px; padding: 3px 7px; border-bottom: 1px solid #28343c; background: #172027; color: #9aabb6; font: 10px "Segoe UI", Arial, sans-serif; }
.benchmark-surface__family-controls label { display: inline-flex; align-items: center; gap: 5px; }
.benchmark-surface__family-controls select { min-width: 180px; border: 1px solid #34434e; background: #11181d; color: #c7d6df; padding: 2px 4px; font: inherit; }
.benchmark-surface__family-state { color: #9bb6c3; }
.benchmark-surface__family-error { color: #ff9b8a; }
.benchmark-surface__family-roles { display: flex; flex-wrap: wrap; gap: 3px 8px; padding: 3px 7px; border-bottom: 1px solid #28343c; background: #121920; color: #80909d; font: 9px "Segoe UI", Arial, sans-serif; }
.benchmark-surface__family-roles span { padding-left: 6px; border-left: 1px solid #34434e; white-space: nowrap; }
.benchmark-surface__family-roles b { color: #c7d6df; }
.benchmark-surface__identity { display: flex; align-items: baseline; gap: 9px; padding: 5px 7px; border-bottom: 1px solid #28343c; background: #121920; color: #91a2ad; font: 10px "Segoe UI", Arial, sans-serif; }
.benchmark-surface__identity strong { color: #d7e4eb; font-size: 11px; }
.benchmark-surface__identity span:first-of-type { color: #d2bc7a; }
.personal-watchlist-tool { display: grid; grid-template-columns: minmax(0, 1fr); grid-template-rows: auto minmax(0, 1fr); height: 100%; min-height: 0; background: #11161b; }
.personal-watchlist-tool__controls { display: flex; flex-wrap: wrap; align-content: flex-start; align-items: center; width: 100%; min-width: 0; max-width: 100%; min-height: 28px; max-height: 84px; overflow: auto; gap: 8px; padding: 3px 7px; border-bottom: 1px solid #28343c; background: #121920; color: #91a2ad; font: 10px "Segoe UI", Arial, sans-serif; }
.personal-watchlist-tool__controls label { display: flex; align-items: center; gap: 5px; color: #d7e4eb; }
.personal-watchlist-tool__controls select { max-width: 210px; border: 1px solid #42515c; background: #11161b; color: #dce9f2; font: inherit; }
.personal-watchlist-tool__controls input, .personal-watchlist-tool__controls button { border: 1px solid #42515c; background: #11161b; color: #dce9f2; font: inherit; padding: 2px 5px; }
.personal-watchlist-tool__controls input { width: 84px; }
.personal-watchlist-tool__controls button { background: #1b303d; cursor: pointer; }
.personal-watchlist-tool__controls button:disabled { cursor: default; opacity: .5; }
.personal-watchlist-tool__controls span { color: #8498a6; }
.personal-watchlist-tool__controls .personal-watchlist-tool__error { color: #e49a9a; }
.combo-editor { display: flex; flex: 1 0 100%; align-items: center; min-width: max-content; gap: 4px; padding: 3px 0 2px 4px; border-left: 1px solid #34434d; border-top: 1px solid #28343c; }
.combo-editor header { color: #d7e4eb; }
.combo-editor label { display: flex; align-items: center; gap: 2px; color: #8498a6; }
.combo-editor select { width: 82px; min-height: 22px; }
.combo-editor select[multiple] { height: 34px; }
.combo-editor input { width: 78px; }
.breadth-tool__family-coverage { display:flex; flex-wrap:wrap; align-items:center; gap:4px 8px; padding:4px 7px; border-top:1px solid #2b3841; color:#9aabb6; }.breadth-tool__family-coverage > span { color:#778994; }.breadth-tool__family-coverage-roles { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); flex:1 0 100%; gap:3px; }.breadth-tool__family-coverage-roles span { min-width:0; padding:3px 4px; border:1px solid #2b3841; color:#8497a4; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }.breadth-tool__family-coverage-roles b { color:#cad4db; }.analysis { height: 100%; min-height: 0; }
.breadth-tool { display:flex; flex-direction:column; height:100%; min-height:0; overflow:auto; container-type:inline-size; }.breadth-tool__universe { display:flex; flex-wrap:wrap; gap:5px; align-items:center; padding:5px 7px 0; color:#9aabb6; font:10px "Segoe UI",Arial,sans-serif; min-width:0; }.breadth-tool__universe span { flex:0 0 auto; }.breadth-tool__universe select,.breadth-tool__universe input { border:1px solid #34434e; background:#172027; color:#d2dce3; font:inherit; min-width:0; max-width:100%; }.breadth-tool__universe select { flex:1 1 100px; }.breadth-tool__universe input { width:42px; flex:0 1 42px; }.breadth-tool__universe label { display:flex; flex:0 0 auto; align-items:center; gap:3px; white-space:nowrap; }.breadth-tool__custom { display:flex; flex-wrap:wrap; align-items:center; gap:4px; padding:5px 7px; border-top:1px solid #2b3841; color:#9aabb6; font:10px "Segoe UI",Arial,sans-serif; }.breadth-tool__custom select,.breadth-tool__custom input,.breadth-tool__custom button { border:1px solid #34434e; background:#172027; color:#d2dce3; font:inherit; min-width:0; }.breadth-tool__custom input { width:44px; }.breadth-tool__custom label { display:flex; align-items:center; gap:3px; }.breadth-tool__custom button { padding:2px 6px; cursor:pointer; }.breadth-tool__custom-result { color:#c3d2dc; white-space:nowrap; }.breadth-tool__composition-note { color:#74858f; }.breadth-tool__family-ratios { display:flex; flex-wrap:wrap; align-items:center; gap:4px; padding:5px 7px; border-top:1px solid #2b3841; color:#9aabb6; font:10px "Segoe UI",Arial,sans-serif; }.breadth-tool__family-ratios select,.breadth-tool__family-ratios input { border:1px solid #34434e; background:#172027; color:#d2dce3; font:inherit; min-width:0; }.breadth-tool__family-ratios input { width:44px; }.breadth-tool__family-ratio { display:inline-flex; align-items:center; gap:4px; padding-left:4px; border-left:1px solid #34434e; }.breadth-tool__family-ratio b { color:#d7e8f0; }.breadth-tool__family-ratio small { color:#778994; }.breadth-tool__family-overview { min-height:0; max-height:230px; overflow:auto; border-top:1px solid #2b3841; border-bottom:1px solid #2b3841; background:#131a20; color:#9aabb6; font:10px "Segoe UI",Arial,sans-serif; }.breadth-tool__family-overview-header,.breadth-tool__family-constituents-header { display:flex; justify-content:space-between; gap:8px; align-items:center; padding:4px 7px; position:sticky; top:0; z-index:1; background:#20282f; }.breadth-tool__family-overview-header span,.breadth-tool__family-constituents-header span { color:#778994; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }.breadth-tool__family-legs { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:3px; padding:4px 6px; }.breadth-tool__family-leg { min-width:0; padding:4px; border:1px solid #2b3841; background:#172027; }.breadth-tool__family-leg--selected { border-color:#5d9ab6; background:#1b3340; }.breadth-tool__family-leg div { display:flex; justify-content:space-between; gap:4px; }.breadth-tool__family-leg div span,.breadth-tool__family-leg small { display:block; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; color:#778994; }.breadth-tool__family-leg button { margin-top:3px; padding:1px 4px; border:1px solid #34434e; background:#11181d; color:#c7d6df; font:inherit; cursor:pointer; }.breadth-tool__family-leg button:disabled { cursor:not-allowed; opacity:.55; }.breadth-tool__family-constituents { border-top:1px solid #2b3841; }.breadth-tool__family-constituents > button { display:flex; gap:8px; width:100%; border:0; border-bottom:1px solid #20282f; background:transparent; color:#cad4db; padding:3px 7px; text-align:left; cursor:pointer; }.breadth-tool__family-constituents > button:hover { background:#1d4057; }.breadth-tool__family-constituents > button span { color:#81929e; }.breadth-tool__family-constituents > button small { margin-left:auto; color:#9bb6c3; }.breadth-tool__status { margin:0; padding:5px 7px; color:#9aabb6; font:10px "Segoe UI",Arial,sans-serif; }.breadth-tool__status--error { color:#ff9b8a; }.metrics { display: grid; grid-template-columns: 1fr auto; gap: 5px 10px; padding: 9px; color: #99aabb; font: 10px "Segoe UI", Arial, sans-serif; }.breadth-tool__coverage-detail { padding:0 7px 4px; color:#778994; font:9px "Segoe UI",Arial,sans-serif; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }.breadth-tool__actions { display:flex; gap:3px; justify-content:flex-end; }.breadth-tool__actions button,.breadth-tool__drilldown header button,.breadth-tool__generic-drilldown header button { border:1px solid #34434e; background:#172027; color:#b9c8d1; font:inherit; padding:1px 4px; cursor:pointer; }.breadth-tool__actions button:hover,.breadth-tool__action--active { background:#1d4057; color:#e5f1f7; }.breadth-tool__drilldown,.breadth-tool__generic-drilldown { min-height:0; max-height:150px; overflow:auto; border-top:1px solid #2b3841; border-bottom:1px solid #2b3841; background:#131a20; font:10px "Segoe UI",Arial,sans-serif; }.breadth-tool__drilldown header,.breadth-tool__generic-drilldown header,.breadth-tool__generic-history-events header { display:flex; justify-content:space-between; align-items:center; padding:4px 7px; color:#9aabb6; position:sticky; top:0; background:#20282f; }.breadth-tool__drilldown > button,.breadth-tool__generic-drilldown > button,.breadth-tool__generic-history-events > button { display:flex; gap:8px; width:100%; border:0; border-bottom:1px solid #20282f; background:transparent; color:#cad4db; padding:4px 7px; text-align:left; cursor:pointer; }.breadth-tool__drilldown > button:hover,.breadth-tool__generic-drilldown > button:hover,.breadth-tool__generic-history-events > button:hover { background:#1d4057; }.breadth-tool__drilldown > button span,.breadth-tool__generic-drilldown > button span,.breadth-tool__generic-history-events > button span { color:#81929e; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }.breadth-tool__generic-drilldown > button small,.breadth-tool__generic-history-events > button small { margin-left:auto; color:#9bb6c3; }.breadth-tool__drilldown > small,.breadth-tool__generic-drilldown > small,.breadth-tool__generic-history-events > small { display:block; padding:7px; color:#8497a4; }.breadth-tool__generic-history-events { min-height:0; max-height:150px; overflow:auto; border-top:1px solid #2b3841; border-bottom:1px solid #2b3841; background:#131a20; font:10px "Segoe UI",Arial,sans-serif; }.breadth-tool__generic-history-events header span { color:#778994; }
.breadth-tool__generic-history-events { position: relative; z-index: 2; }
.breadth-tool__member-diagnostics { flex:1 1 100%; margin-left:0 !important; color:#d0a66a !important; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.breadth-tool__generic-diagnostics { max-height:110px; overflow:auto; border-top:1px solid #2b3841; border-bottom:1px solid #2b3841; background:#131a20; color:#d0a66a; font:9px "Segoe UI",Arial,sans-serif; }.breadth-tool__generic-diagnostics header { display:flex; justify-content:space-between; padding:4px 7px; position:sticky; top:0; background:#20282f; color:#9aabb6; }.breadth-tool__generic-diagnostics header span { color:#778994; }.breadth-tool__generic-diagnostics > div:not(header) { padding:2px 7px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
@container (max-width: 560px) {
  .breadth-tool__universe { flex-wrap:wrap; row-gap:4px; }
  .breadth-tool__universe > select { flex:1 1 100px; }
  .breadth-tool__universe > input { flex:0 1 42px; }
  .breadth-tool__universe > label { flex:0 0 auto; }
}
.metrics b { color: #d2dce3; font-weight: 500; text-align: right; }
.industry-list { height: 100%; overflow: auto; background: #11161b; font: 11px "Segoe UI", Arial, sans-serif; }
.industry-list__header { display: flex; gap: 8px; min-width: 920px; padding: 5px 7px; border-bottom: 1px solid #34434e; color: #91a6b2; font-size: 10px; font-weight: 600; white-space: nowrap; }
.industry-list__header span:first-child { min-width: 120px; flex: 1 1 auto; }
.industry-list__header span:not(:first-child) { flex: 0 0 52px; text-align: right; }
.industry-list__header span:nth-child(2) { flex-basis: 78px; }
.industry-list__header span:nth-child(3) { flex-basis: 58px; }
.industry-list__row { display: flex; width: 100%; justify-content: space-between; gap: 8px; padding: 7px; border: 0; border-bottom: 1px solid #20282f; background: transparent; color: #c7d0d8; text-align: left; cursor: pointer; }
.industry-list__row { min-width: 920px; }
.industry-list__metric { flex: 0 0 52px; overflow: hidden; text-align: right; text-overflow: ellipsis; white-space: nowrap; }
.industry-list__row:hover, .industry-list__row--active { background: #1d4057; }
.industry-list__classification { flex: 0 0 auto; max-width: 120px; overflow: hidden; color: #a9b7bf; font-size: 9px; text-overflow: ellipsis; white-space: nowrap; }
.industry-list__proxies { display: grid; gap: 3px; padding: 6px 7px; border-bottom: 1px solid #20282f; color: #8998a3; }
.industry-list__proxy-table { height: 170px; border: 1px solid #34434e; }
.constituent-tool { display: grid; grid-template-rows: minmax(0, 1fr) auto; height: 100%; min-height: 0; background: #11161b; }
.constituent-tool__provenance { display: block; overflow: hidden; padding: 3px 7px; border-top: 1px solid #28343c; background: #121920; color: #d5ae72; font: 9px "Segoe UI", Arial, sans-serif; text-overflow: ellipsis; white-space: nowrap; }
.instrument-report { height: 100%; overflow: auto; background: #11161b; }
.industry-list__row strong { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.industry-list__row span, .industry-list small { color: #7d9db0; }
.industry-list small { display: block; padding: 7px; line-height: 1.3; }
.industry-list__provenance { border-top: 1px solid #20282f; color: #8ea4b0; }
.breadth-tool__family-technicals { display:flex; flex-wrap:wrap; align-items:center; gap:4px 8px; padding:5px 7px; border-top:1px solid #2b3841; color:#9aabb6; font:10px "Segoe UI",Arial,sans-serif; }.breadth-tool__family-technical { padding-left:5px; border-left:1px solid #34434e; color:#8497a4; }.breadth-tool__family-technical b { color:#cad4db; }
.breadth-tool__family-breadth { display:flex; flex-wrap:wrap; align-items:center; gap:4px 8px; padding:5px 7px; border-top:1px solid #2b3841; color:#9aabb6; font:10px "Segoe UI",Arial,sans-serif; }.breadth-tool__family-breadth-role { padding-left:5px; border-left:1px solid #34434e; color:#8497a4; }.breadth-tool__family-breadth-role b { color:#cad4db; }
.breadth-tool__family-ranking { display:flex; flex-wrap:wrap; align-items:center; gap:4px 8px; padding:5px 7px; border-top:1px solid #2b3841; color:#9aabb6; font:10px "Segoe UI",Arial,sans-serif; }.breadth-tool__family-ranking-role { padding-left:5px; border-left:1px solid #34434e; color:#8497a4; }.breadth-tool__family-ranking-role b { color:#cad4db; }
.breadth-tool__cross-family-ranking { display:flex; flex-wrap:wrap; align-items:center; gap:4px 8px; padding:5px 7px; border-top:1px solid #2b3841; color:#9aabb6; font:10px "Segoe UI",Arial,sans-serif; }.breadth-tool__cross-family-ranking-row { padding-left:5px; border-left:1px solid #34434e; color:#8497a4; }.breadth-tool__cross-family-ranking-row b { color:#cad4db; }
.sr-only { position:absolute; width:1px; height:1px; padding:0; margin:-1px; overflow:hidden; clip:rect(0 0 0 0); white-space:nowrap; border:0; }
</style>
