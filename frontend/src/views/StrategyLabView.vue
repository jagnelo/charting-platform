<template>
  <div class="strategy-lab-view">
    <aside
      class="strategy-sidebar"
      :class="{ 'strategy-sidebar--collapsed': sidebarCollapsed }"
      :style="sidebarCollapsed ? undefined : { width: `${sidebarWidth}px` }"
    >
      <div v-if="!sidebarCollapsed" class="strategy-sidebar-body">
        <div class="sidebar-header">
          <div>
            <h1>Strategy Lab</h1>
          </div>
        </div>

        <div class="definition-list definition-list--dense">
          <button
            v-if="!strategyLab.definitions.length"
            type="button"
            class="definition-item definition-item--new sidebar-new-btn"
            @click="startNew"
          >
            + New
          </button>
          <button
            v-for="definition in strategyLab.definitions"
            :key="definition.id"
            type="button"
            class="definition-item"
            :class="{ active: strategyLab.selectedDefinitionId === definition.id }"
            @click="selectDefinition(definition.id)"
          >
            <div class="definition-tile definition-tile--dense">
              <span class="state-dot definition-state-dot" :class="{ inactive: !definition.is_active }" />
              <div class="definition-copy">
                <strong>{{ definition.name }}</strong>
                <small>
                  v{{ definition.versions[0]?.version_number ?? 1 }}
                </small>
                <div v-if="definitionDisplayTags(definition).length" class="definition-tags">
                  <span
                    v-for="tag in definitionDisplayTags(definition)"
                    :key="tag"
                    class="definition-tag"
                    :style="tagPillStyle(tag)"
                  >
                    {{ tag }}
                  </span>
                </div>
              </div>
            </div>
          </button>
          <button
            v-if="strategyLab.definitions.length"
            type="button"
            class="definition-item definition-item--new sidebar-new-btn"
            @click="startNew"
          >
            + New
          </button>
        </div>
      </div>

      <button
        class="sidebar-toggle-strip"
        :title="sidebarCollapsed ? 'Expand strategy list' : 'Collapse strategy list'"
        type="button"
        @click="sidebarCollapsed = !sidebarCollapsed"
      >
        {{ sidebarCollapsed ? '▸' : '◂' }}
      </button>
    </aside>
    <ResizeHandle
      direction="horizontal"
      :value="sidebarCollapsed ? STRATEGY_SIDEBAR_COLLAPSED_WIDTH : sidebarWidth"
      :min="sidebarCollapsed ? STRATEGY_SIDEBAR_COLLAPSED_WIDTH : STRATEGY_SIDEBAR_MIN_WIDTH"
      :max="STRATEGY_SIDEBAR_MAX_WIDTH"
      @change="resizeSidebar"
    />

    <section class="strategy-main">
      <div v-if="strategyLab.error" class="error-banner">{{ strategyLab.error }}</div>

      <div class="detail-header">
        <div>
          <div class="detail-title-row">
            <h2>{{ isNew ? 'New Strategy' : draft.name || 'Strategy' }}</h2>
            <span v-if="currentVersion && !isNew" class="detail-version-pill">v{{ currentVersion.version_number }}</span>
          </div>
        </div>
        <div class="detail-actions">
          <button
            class="btn-secondary btn-icon-only"
            type="button"
            title="Refresh"
            aria-label="Refresh"
            @click="reload"
            :disabled="strategyLab.isLoading"
          >
            <svg viewBox="0 0 16 16" aria-hidden="true">
              <path d="M13.5 3.5v3h-3" />
              <path d="M12.2 6A5 5 0 1 0 13 10" />
            </svg>
          </button>
          <button
            v-if="!isNew && strategyLab.selectedDefinition"
            class="btn-secondary btn-icon-only"
            type="button"
            title="Save profile"
            aria-label="Save profile"
            @click="saveProfileOnly"
            :disabled="strategyLab.isSaving"
          >
            <svg viewBox="0 0 16 16" aria-hidden="true">
              <path d="M3 2.5h8l2 2V13.5H3z" />
              <path d="M5 2.5v4h5v-4" />
              <path d="M5 13.5V9h6v4.5" />
            </svg>
          </button>
          <button
            v-if="!isNew && strategyLab.selectedDefinition"
            class="btn-danger btn-icon-only"
            type="button"
            title="Delete strategy"
            aria-label="Delete strategy"
            @click="showDeleteModal = true"
            :disabled="strategyLab.isSaving"
          >
            <svg viewBox="0 0 16 16" aria-hidden="true">
              <path d="M3.5 4.5h9" />
              <path d="M6 2.5h4" />
              <path d="M5 4.5v8h6v-8" />
              <path d="M7 6.5v4" />
              <path d="M9 6.5v4" />
            </svg>
          </button>
          <button
            class="btn-primary"
            type="button"
            @click="publishStrategy"
            :disabled="strategyLab.isSaving || !canPublish"
          >
            {{ strategyLab.isSaving ? 'Saving…' : isNew ? 'Create strategy' : 'Publish revision' }}
          </button>
        </div>
      </div>

      <div class="detail-columns">
          <div class="panel">
            <div class="panel-head">
              <div class="panel-head-title">
                <button
                  type="button"
                  class="panel-toggle"
                  :aria-expanded="sectionExpanded.profile ? 'true' : 'false'"
                  :title="sectionExpanded.profile ? 'Collapse Strategy profile' : 'Expand Strategy profile'"
                  @click="toggleSection('profile')"
                >
                  <span class="panel-toggle__icon" :class="{ 'panel-toggle__icon--expanded': sectionExpanded.profile }">▸</span>
                </button>
                <h3 class="panel-head-heading" @click="toggleSection('profile')">Strategy profile</h3>
              </div>
            </div>

            <div v-if="sectionExpanded.profile" class="panel-body">
            <div class="form-grid two-up">
              <label class="field">
                <span class="field-label">
                  Name
                  <span v-if="showNameValidation" class="field-inline-hint">Required</span>
                </span>
                <input
                  v-model="draft.name"
                  class="form-input"
                  :class="{ 'form-input--invalid': showNameValidation }"
                  placeholder="Momentum Continuation"
                />
              </label>
              <label class="field">
                <span class="field-label">Source</span>
                <select v-model="sourceType" class="form-select">
                  <option value="custom">Custom rules</option>
                  <option value="radar">Platform signal research</option>
                </select>
              </label>
              <label class="field">
                <span class="field-label">Tags</span>
                <TagPicker
                  v-model="draft.tags"
                  :options="availableTags"
                  placeholder="Add or reuse tags"
                />
              </label>
              <label class="field field--full">
                <span class="field-label">Description</span>
                <textarea
                  v-model="draft.description"
                  class="form-textarea form-textarea--short"
                  placeholder="What market behaviour is this strategy trying to capture?"
                />
              </label>
              <label class="field field--checkbox">
                <input v-model="draft.is_active" type="checkbox" />
                <span>Strategy is active</span>
              </label>
            </div>

            <div class="subsection">
              <div class="subsection-head">
                <div class="subsection-title">
                  <h4>{{ sourceType === 'radar' ? 'Universe scope' : 'Universe' }}</h4>
                  <HoverTooltip :text="sourceType === 'radar'
                    ? 'Radar provides the source instruments by default. Use the scope controls only when you want to narrow replay to a manual symbol list, watchlist, or screener result.'
                    : 'Use a manual symbol list or a watchlist-backed universe. Run-specific subsets can still narrow the published universe later.'">
                    <button type="button" class="help-dot" aria-label="Universe info">i</button>
                  </HoverTooltip>
                </div>
              </div>

              <div class="form-grid two-up">
                <label class="field">
                  <span class="field-label">
                    Universe type
                    <span v-if="showUniverseValidation" class="field-inline-hint">Required</span>
                  </span>
                  <select v-model="universeMode" class="form-select" :class="{ 'form-select--invalid': showUniverseValidation }">
                    <option v-if="sourceType === 'radar'" value="radar">Radar outputs</option>
                    <option value="symbols">Manual symbols</option>
                    <option value="watchlist">Watchlist</option>
                    <option value="screener">Latest screener result</option>
                    <option value="basket">Basket</option>
                    <option value="etf_holdings">ETF holdings snapshot</option>
                  </select>
                </label>
                <label v-if="universeMode === 'watchlist'" class="field">
                  <span class="field-label">Watchlist</span>
                  <select v-model="selectedWatchlistId" class="form-select">
                    <option :value="null">Select watchlist</option>
                    <option v-for="watchlist in availableWatchlists" :key="watchlist.id" :value="watchlist.id">
                      {{ watchlist.name }}
                    </option>
                  </select>
                </label>
                <label v-else-if="universeMode === 'screener'" class="field">
                  <span class="field-label">Screener</span>
                  <select v-model="selectedScreenerId" class="form-select">
                    <option :value="null">Select screener</option>
                    <option v-for="screener in availableScreeners" :key="screener.id" :value="screener.id">
                      {{ screener.name }}
                    </option>
                  </select>
                </label>
                <label v-else-if="universeMode === 'basket'" class="field">
                  <span class="field-label">Basket</span>
                  <select v-model="selectedBasketId" class="form-select">
                    <option :value="null">Select basket</option>
                    <option v-for="basket in availableBaskets" :key="basket.id" :value="basket.id">
                      {{ basket.name }} · {{ basket.members.length }} symbols
                    </option>
                  </select>
                </label>
                <label v-else-if="universeMode === 'etf_holdings'" class="field">
                  <span class="field-label">ETF</span>
                  <select v-model="selectedEtfHoldingSymbol" class="form-select">
                    <option value="">Select ETF</option>
                    <option v-for="etf in availableEtfHoldings" :key="etf.id" :value="etf.symbol">
                      {{ etf.symbol }}{{ etf.latest_composition_date ? ` · ${etf.latest_composition_date}` : '' }}
                    </option>
                  </select>
                </label>
              </div>

              <div v-if="universeMode === 'etf_holdings'" class="form-grid two-up">
                <label class="field">
                  <span class="field-label">Snapshot</span>
                  <select v-model="selectedEtfHoldingSnapshotMode" class="form-select">
                    <option value="latest">Latest available</option>
                    <option value="date">On or before date</option>
                    <option value="dynamic">Dynamic through time</option>
                  </select>
                </label>
                <label v-if="selectedEtfHoldingSnapshotMode === 'date'" class="field">
                  <span class="field-label">Snapshot date</span>
                  <input v-model="selectedEtfHoldingSnapshotDate" type="date" class="form-input" />
                </label>
              </div>
              <div v-if="universeMode === 'basket' && basketSupportsDynamicHistory" class="form-grid two-up">
                <label class="field">
                  <span class="field-label">Basket history</span>
                  <select v-model="selectedBasketSnapshotMode" class="form-select">
                    <option value="static">Static basket members</option>
                    <option value="dynamic">Dynamic history</option>
                  </select>
                </label>
              </div>

              <template v-if="universeMode === 'radar'">
                <div class="empty-inline">Using Radar outputs.</div>
              </template>
              <template v-else-if="universeMode === 'symbols'">
                <div class="chip-row">
                  <span v-for="symbol in logicDraft.symbols" :key="symbol" class="symbol-chip">
                    {{ symbol }}
                    <button type="button" @click="removeSymbol(symbol)">×</button>
                  </span>
                  <span v-if="!logicDraft.symbols.length" class="empty-inline">No symbols added yet.</span>
                </div>

                <div class="inline-search">
                  <SearchBar
                    v-model="symbolInput"
                    placeholder="Add symbol (e.g. AAPL)"
                    mode="picker"
                    fluid
                    :show-recent="false"
                    :show-screener-link="false"
                    @select="addSelectedSymbol"
                  />
                </div>
              </template>
              <template v-else>
                <div class="chip-row">
                  <span
                    v-if="universeMode === 'watchlist'"
                    v-for="item in selectedWatchlist?.items.slice(0, 10) ?? []"
                    :key="item.id"
                    class="symbol-chip symbol-chip--alt"
                  >
                    {{ item.symbol || item.name || item.instrument_id }}
                  </span>
                  <span v-if="universeMode === 'watchlist' && !selectedWatchlist" class="empty-inline">Select a watchlist to define the universe.</span>
                  <span v-if="universeMode === 'screener' && selectedScreener" class="symbol-chip symbol-chip--alt">
                    {{ selectedScreener.name }}
                  </span>
                  <span v-if="universeMode === 'screener' && !selectedScreener" class="empty-inline">Select a screener to use its latest results as the research universe.</span>
                  <span
                    v-if="universeMode === 'basket'"
                    v-for="member in selectedBasket?.members.slice(0, 10) ?? []"
                    :key="member.id"
                    class="symbol-chip symbol-chip--alt"
                  >
                    {{ member.symbol || member.name || member.instrument_id }}
                  </span>
                  <span v-if="universeMode === 'basket' && selectedBasket && selectedBasket.members.length > 10" class="empty-inline">
                    +{{ selectedBasket.members.length - 10 }} more
                  </span>
                  <span v-if="universeMode === 'basket' && !selectedBasket" class="empty-inline">Select a basket to define the universe.</span>
                  <span v-if="universeMode === 'etf_holdings' && selectedEtfHolding" class="symbol-chip symbol-chip--alt">
                    {{ selectedEtfHolding.symbol }}
                  </span>
                  <span v-if="universeMode === 'etf_holdings' && !selectedEtfHolding" class="empty-inline">Select an ETF with holdings snapshots.</span>
                </div>
              </template>
            </div>

            <div class="form-grid three-up">
              <label class="field">
                <span class="field-label">Timeframe</span>
                <select v-model="logicDraft.timeframe" class="form-select">
                  <option v-for="tf in timeframes" :key="tf" :value="tf">{{ tf }}</option>
                </select>
              </label>
              <label class="field">
                <span class="field-label">Direction</span>
                <select v-model="logicDraft.direction" class="form-select">
                  <option value="long">Long</option>
                  <option value="short">Short</option>
                </select>
              </label>
              <label class="field">
                <span class="field-label">Benchmark</span>
                <SearchBar
                  v-model="logicDraft.benchmark_symbol"
                  placeholder="SPY"
                  mode="picker"
                  fluid
                  :show-recent="false"
                  :show-screener-link="false"
                />
              </label>
            </div>
            </div>
          </div>

          <div class="panel">
          <div class="panel-head">
            <div class="panel-head-title">
              <button
                type="button"
                class="panel-toggle"
                :aria-expanded="sectionExpanded.entry ? 'true' : 'false'"
                :title="sectionExpanded.entry ? `Collapse ${sourceType === 'radar' ? 'Signal source' : 'Entry logic'}` : `Expand ${sourceType === 'radar' ? 'Signal source' : 'Entry logic'}`"
                @click="toggleSection('entry')"
              >
                <span class="panel-toggle__icon" :class="{ 'panel-toggle__icon--expanded': sectionExpanded.entry }">▸</span>
              </button>
              <h3 class="panel-head-heading" @click="toggleSection('entry')">{{ sourceType === 'radar' ? 'Signal source' : 'Entry logic' }}</h3>
            </div>
          </div>

          <div v-if="sectionExpanded.entry" class="panel-body">
          <template v-if="sourceType === 'custom'">
            <div class="form-grid one-up">
              <label class="field">
                <span class="field-label">Revision note</span>
                <input v-model="versionNotes" class="form-input" placeholder="What changed in this revision?" />
              </label>
            </div>
            <div class="cb-header cb-header--strategy">
              <span class="section-label">Technical conditions</span>
              <span class="tree-builder-kicker">{{ rootGroupMode === 'all' ? 'Match ALL at the root' : 'Match ANY at the root' }}</span>
            </div>
            <StrategyRuleTreeEditor
              :node="logicDraft.ruleTree"
              :depth="0"
              :can-remove="false"
              :type-options="STRATEGY_LAB_CONDITION_TYPE_OPTIONS"
              @remove="removeNodeFromTree"
              @add-condition="addConditionToTree"
              @add-group="(nodeId, type) => addGroupToTree(nodeId, type)"
            />
          </template>
          <template v-else>
            <div class="form-grid two-up">
              <label class="field">
                <span class="field-label">Revision note</span>
                <input v-model="versionNotes" class="form-input" placeholder="What changed in this revision?" />
              </label>
              <label class="field">
                <span class="field-label">Minimum score</span>
                <input v-model.number="radarDraft.min_score" type="number" min="0" max="1" step="0.01" class="form-input" />
              </label>
            </div>
            <div class="form-grid two-up">
              <label class="field">
                <span class="field-label">Setup families</span>
                <div class="multi-select-field">
                  <button
                    type="button"
                    class="multi-select-trigger"
                    @click="toggleRadarMenu('setup')"
                  >
                    <span>{{ radarSetupSummary }}</span>
                    <span class="multi-select-caret">{{ radarSetupMenuOpen ? '▴' : '▾' }}</span>
                  </button>
                  <div v-if="radarSetupMenuOpen" class="multi-select-menu">
                    <label
                      v-for="option in radarSetupOptions"
                      :key="option.value"
                      class="multi-select-option"
                    >
                      <input
                        :checked="radarDraft.setup_types.includes(option.value)"
                        type="checkbox"
                        @change="toggleRadarDraftValue(radarDraft.setup_types, option.value, checkboxValue($event))"
                      />
                      <span>{{ option.label }}</span>
                    </label>
                    <button
                      v-if="radarDraft.setup_types.length"
                      type="button"
                      class="multi-select-clear"
                      @click="radarDraft.setup_types = []"
                    >
                      Clear selection
                    </button>
                  </div>
                </div>
              </label>
              <label class="field">
                <span class="field-label">States</span>
                <div class="multi-select-field">
                  <button
                    type="button"
                    class="multi-select-trigger"
                    @click="toggleRadarMenu('state')"
                  >
                    <span>{{ radarStateSummary }}</span>
                    <span class="multi-select-caret">{{ radarStateMenuOpen ? '▴' : '▾' }}</span>
                  </button>
                  <div v-if="radarStateMenuOpen" class="multi-select-menu">
                    <label
                      v-for="option in radarStateOptions"
                      :key="option.value"
                      class="multi-select-option"
                    >
                      <input
                        :checked="radarDraft.states.includes(option.value)"
                        type="checkbox"
                        @change="toggleRadarDraftValue(radarDraft.states, option.value, checkboxValue($event))"
                      />
                      <span>{{ option.label }}</span>
                    </label>
                    <button
                      v-if="radarDraft.states.length"
                      type="button"
                      class="multi-select-clear"
                      @click="radarDraft.states = []"
                    >
                      Clear selection
                    </button>
                  </div>
                </div>
              </label>
            </div>
          </template>

          <div class="rule-preview">
            <span class="rule-preview__label">How this reads</span>
            <p>{{ strategyNarrative }}</p>
          </div>
          </div>
          </div>

          <div class="panel">
            <div class="panel-head">
              <div class="panel-head-title">
                <button
                  type="button"
                  class="panel-toggle"
                  :aria-expanded="sectionExpanded.risk ? 'true' : 'false'"
                  :title="sectionExpanded.risk ? 'Collapse Risk' : 'Expand Risk'"
                  @click="toggleSection('risk')"
                >
                  <span class="panel-toggle__icon" :class="{ 'panel-toggle__icon--expanded': sectionExpanded.risk }">▸</span>
                </button>
                <h3 class="panel-head-heading" @click="toggleSection('risk')">Risk</h3>
              </div>
            </div>

            <div v-if="sectionExpanded.risk" class="panel-body">
            <div class="form-grid three-up">
              <label class="field">
                <span class="field-label">
                  Stop model
                  <HoverTooltip text="Choose whether the initial stop is a fixed percent distance from entry or a volatility-aware ATR multiple.">
                    <button type="button" class="help-dot" aria-label="Stop model info">i</button>
                  </HoverTooltip>
                </span>
                <select v-model="logicDraft.stop_model" class="form-select">
                  <option value="percent">Fixed percent</option>
                  <option value="atr">ATR multiple</option>
                </select>
              </label>
              <div class="field field--sweep">
                <span class="field-label">
                  {{ logicDraft.stop_model === 'atr' ? 'ATR period' : 'Stop loss %' }}
                  <HoverTooltip
                    v-if="logicDraft.stop_model !== 'atr'"
                    :text="sweepModeTooltip(sweepDraft.stop_loss_pct)"
                    :show-on-focus="false"
                  >
                    <button
                      type="button"
                      class="sweep-indicator"
                      :class="`sweep-indicator--${sweepDraft.stop_loss_pct.mode}`"
                      :aria-label="sweepModeAriaLabel(sweepDraft.stop_loss_pct)"
                      @click.prevent.stop="cycleSweepMode(sweepDraft.stop_loss_pct, { min: 0.1, step: 0.1 })"
                    >
                      <span></span><span></span><span></span><span></span>
                    </button>
                  </HoverTooltip>
                  <HoverTooltip :text="logicDraft.stop_model === 'atr'
                    ? 'ATR lookback used for the volatility-based stop model. The stop sits this many ATR multiples away from the entry price.'
                    : 'Percent distance from the entry price to the stop. Position size is derived from this and your run-time risk budget when percent-risk sizing is active.'">
                    <button type="button" class="help-dot" aria-label="Stop loss info">i</button>
                  </HoverTooltip>
                </span>
                <template v-if="logicDraft.stop_model === 'atr'">
                  <input v-model.number="logicDraft.stop_atr_period" type="number" min="1" step="1" class="form-input" />
                </template>
                <template v-else>
                  <SweepValueInput
                    v-model="sweepDraft.stop_loss_pct"
                    :min="0.1"
                    :step="0.1"
                    placeholder="Stop %"
                  />
                </template>
              </div>
              <label class="field">
                <span class="field-label">
                  {{ logicDraft.stop_model === 'atr' ? 'ATR multiple' : 'Hard trail %' }}
                  <HoverTooltip :text="logicDraft.stop_model === 'atr'
                    ? 'Distance from entry to the initial stop, expressed as a multiple of ATR.'
                    : 'A percent-based trailing stop measured from the best price reached after entry. Leave empty to disable this hard trailing stop.'">
                    <button type="button" class="help-dot" :aria-label="logicDraft.stop_model === 'atr' ? 'ATR multiple info' : 'Hard trailing stop info'">i</button>
                  </HoverTooltip>
                </span>
                <template v-if="logicDraft.stop_model === 'atr'">
                  <input v-model.number="logicDraft.stop_atr_multiple" type="number" min="0.1" step="0.1" class="form-input" />
                </template>
                <template v-else>
                  <input v-model.number="logicDraft.hard_trailing_stop_pct" type="number" min="0" step="0.1" class="form-input" placeholder="Disabled" />
                </template>
              </label>
              <label class="field">
                <span class="field-label">
                  Position sizing
                  <HoverTooltip text="Choose how to size each position: percent-risk uses the run risk budget, while the others size from fixed quantity or capital allocation.">
                    <button type="button" class="help-dot" aria-label="Position sizing info">i</button>
                  </HoverTooltip>
                </span>
                <select v-model="logicDraft.position_sizing_mode" class="form-select">
                  <option value="percent_risk">Percent risk</option>
                  <option value="fixed_cash">Fixed cash</option>
                  <option value="percent_capital">% of capital</option>
                  <option value="fixed_quantity">Fixed quantity</option>
                </select>
              </label>
              <label v-if="logicDraft.position_sizing_mode !== 'percent_risk'" class="field">
                <span class="field-label">
                  {{ positionSizingValueLabel }}
                  <HoverTooltip :text="positionSizingValueHelp">
                    <button type="button" class="help-dot" aria-label="Position sizing value info">i</button>
                  </HoverTooltip>
                </span>
                <input
                  v-model.number="logicDraft.position_sizing_value"
                  type="number"
                  :min="positionSizingValueMin"
                  :step="positionSizingValueStep"
                  class="form-input"
                />
              </label>
              <label class="field">
                <span class="field-label">
                  Arm hard trail after gain %
                  <HoverTooltip text="Do not activate the hard percent trail until the trade has moved this much in your favor. Set to 0 to arm it immediately from entry.">
                    <button type="button" class="help-dot" aria-label="Hard trailing activation info">i</button>
                  </HoverTooltip>
                </span>
                <input v-model.number="logicDraft.hard_trailing_activation_pct" type="number" min="0" step="0.1" class="form-input" />
              </label>
              <label class="field">
                <span class="field-label">
                  Break-even after R
                  <HoverTooltip text="Move the stop to the entry price once the trade reaches this many R units in open profit. Leave empty to disable break-even handling. 1R equals the initial stop distance.">
                    <button type="button" class="help-dot" aria-label="Break-even info">i</button>
                  </HoverTooltip>
                </span>
                <input v-model.number="logicDraft.break_even_rr" type="number" min="0" step="0.25" class="form-input" placeholder="Disabled" />
              </label>
              <label class="field">
                <span class="field-label">
                  Trail distance (R)
                  <HoverTooltip text="Trailing stop distance expressed in R units, not percent. Leave empty to disable the R-based trailing stop. 1R equals the initial stop distance. Example: 1.5R trails the stop 1.5 initial-risk units behind the best price reached.">
                    <button type="button" class="help-dot" aria-label="Trailing stop info">i</button>
                  </HoverTooltip>
                </span>
                <input v-model.number="logicDraft.trailing_stop_rr" type="number" min="0" step="0.25" class="form-input" placeholder="Disabled" />
              </label>
              <label class="field">
                <span class="field-label">
                  Max entries
                  <HoverTooltip text="Maximum number of entries allowed for the same idea, including scale-ins or pyramiding attempts.">
                    <button type="button" class="help-dot" aria-label="Max entries info">i</button>
                  </HoverTooltip>
                </span>
                <input v-model.number="logicDraft.pyramiding_max_entries" type="number" min="1" step="1" class="form-input" />
              </label>
            </div>
            </div>
          </div>

          <div class="panel">
            <div class="panel-head">
              <div class="panel-head-title">
                <button
                  type="button"
                  class="panel-toggle"
                  :aria-expanded="sectionExpanded.exits ? 'true' : 'false'"
                  :title="sectionExpanded.exits ? 'Collapse Exits' : 'Expand Exits'"
                  @click="toggleSection('exits')"
                >
                  <span class="panel-toggle__icon" :class="{ 'panel-toggle__icon--expanded': sectionExpanded.exits }">▸</span>
                </button>
                <h3 class="panel-head-heading" @click="toggleSection('exits')">Exits</h3>
              </div>
            </div>

            <div v-if="sectionExpanded.exits" class="panel-body">
            <div class="form-grid two-up">
              <div class="field field--sweep">
                <span class="field-label">
                  Target (R)
                  <HoverTooltip
                    :text="sweepModeTooltip(sweepDraft.take_profit_rr)"
                    :show-on-focus="false"
                  >
                    <button
                      type="button"
                      class="sweep-indicator"
                      :class="`sweep-indicator--${sweepDraft.take_profit_rr.mode}`"
                      :aria-label="sweepModeAriaLabel(sweepDraft.take_profit_rr)"
                      @click.prevent.stop="cycleSweepMode(sweepDraft.take_profit_rr, { min: 0, step: 0.25 })"
                    >
                      <span></span><span></span><span></span><span></span>
                    </button>
                  </HoverTooltip>
                  <HoverTooltip text="Take profit expressed as a multiple of the initial risk distance. Leave empty to disable fixed profit targets and rely on condition-based or time-based exits instead.">
                    <button type="button" class="help-dot" aria-label="Target info">i</button>
                  </HoverTooltip>
                </span>
                <SweepValueInput
                  v-model="sweepDraft.take_profit_rr"
                  :min="0"
                  :step="0.25"
                  placeholder="Disabled"
                />
              </div>
              <div class="field field--sweep">
                <span class="field-label">
                  Max bars in trade
                  <HoverTooltip
                    :text="sweepModeTooltip(sweepDraft.max_bars_in_trade)"
                    :show-on-focus="false"
                  >
                    <button
                      type="button"
                      class="sweep-indicator"
                      :class="`sweep-indicator--${sweepDraft.max_bars_in_trade.mode}`"
                      :aria-label="sweepModeAriaLabel(sweepDraft.max_bars_in_trade)"
                      @click.prevent.stop="cycleSweepMode(sweepDraft.max_bars_in_trade, { min: 1, step: 1, integer: true })"
                    >
                      <span></span><span></span><span></span><span></span>
                    </button>
                  </HoverTooltip>
                  <HoverTooltip text="Close the trade after this many bars if no other exit fired first. Leave empty to disable time-based exits.">
                    <button type="button" class="help-dot" aria-label="Max bars info">i</button>
                  </HoverTooltip>
                </span>
                <SweepValueInput
                  v-model="sweepDraft.max_bars_in_trade"
                  :min="1"
                  :step="1"
                  integer
                  placeholder="Disabled"
                />
              </div>
            </div>

            <div class="cb-header cb-header--strategy">
              <span class="section-label">Exit conditions</span>
              <span class="tree-builder-kicker">{{ exitRootGroupMode === 'all' ? 'Match ALL at the root' : 'Match ANY at the root' }}</span>
            </div>
            <StrategyRuleTreeEditor
              :node="logicDraft.exitRuleTree"
              :depth="0"
              :can-remove="false"
              :type-options="STRATEGY_LAB_CONDITION_TYPE_OPTIONS"
              @remove="removeNodeFromExitTree"
              @add-condition="addConditionToExitTree"
              @add-group="(nodeId, type) => addGroupToExitTree(nodeId, type)"
            />
            </div>
          </div>

          <div class="panel">
          <div class="panel-head">
            <div class="panel-head-title">
              <button
                type="button"
                class="panel-toggle"
                :aria-expanded="sectionExpanded.runs ? 'true' : 'false'"
                :title="sectionExpanded.runs ? 'Collapse Research runs' : 'Expand Research runs'"
                @click="toggleSection('runs')"
              >
                <span class="panel-toggle__icon" :class="{ 'panel-toggle__icon--expanded': sectionExpanded.runs }">▸</span>
              </button>
              <h3 class="panel-head-heading" @click="toggleSection('runs')">Research runs</h3>
            </div>
            <div class="panel-head-controls">
              <button
                v-if="currentVersion && !isNew"
                class="btn-primary"
                type="button"
                @click="runCurrentVersion"
                :disabled="strategyLab.isRunning || showRunSubsetValidation"
              >
                {{ strategyLab.isRunning ? 'Running…' : runDraft.test_mode === 'walk_forward' ? 'Run walk-forward' : runDraft.test_mode === 'paper_forward' ? 'Run paper-forward' : 'Run backtest' }}
              </button>
            </div>
          </div>

          <div v-if="sectionExpanded.runs" class="panel-body">
          <div class="mode-strip">
            <button type="button" class="mode-pill" :class="{ 'mode-pill--active': runDraft.test_mode === 'backtest' }" @click="runDraft.test_mode = 'backtest'">Backtest</button>
            <button type="button" class="mode-pill" :class="{ 'mode-pill--active': runDraft.test_mode === 'walk_forward' }" @click="runDraft.test_mode = 'walk_forward'">Walk forward</button>
            <button type="button" class="mode-pill" :class="{ 'mode-pill--active': runDraft.test_mode === 'paper_forward' }" @click="runDraft.test_mode = 'paper_forward'">Paper forward</button>
          </div>

          <div class="form-grid three-up">
            <label class="field">
              <span class="field-label">Run timeframe</span>
              <select v-model="runDraft.timeframe" class="form-select">
                <option value="">Use strategy timeframe</option>
                <option v-for="tf in timeframes" :key="tf" :value="tf">{{ tf }}</option>
              </select>
            </label>
            <label class="field">
              <span class="field-label">Date from</span>
              <input v-model="runDraft.date_from" type="date" class="form-input" />
            </label>
            <label class="field">
              <span class="field-label">Date to</span>
              <input v-model="runDraft.date_to" type="date" class="form-input" />
            </label>
            <label class="field">
              <span class="field-label">Initial capital</span>
              <input v-model.number="runDraft.initial_capital" type="number" min="1000" step="1000" class="form-input" />
            </label>
            <label v-if="logicDraft.position_sizing_mode === 'percent_risk'" class="field">
              <span class="field-label">Risk per trade %</span>
              <input v-model.number="runDraft.risk_per_trade_pct" type="number" min="0.1" step="0.1" class="form-input" />
            </label>
            <label class="field">
              <span class="field-label">Slippage (bps)</span>
              <input v-model.number="runDraft.slippage_bps" type="number" min="0" step="1" class="form-input" placeholder="None" />
            </label>
            <label class="field">
              <span class="field-label">
                Commission model
                <HoverTooltip text="Choose how broker commissions should be applied during the run: a flat round-trip fee, a flat fee on each entry/exit order, or a percent of order notional.">
                  <button type="button" class="help-dot" aria-label="Commission model info">i</button>
                </HoverTooltip>
              </span>
              <select v-model="runDraft.commission_model" class="form-select">
                <option value="fixed_round_trip">Flat round-trip</option>
                <option value="fixed_per_order">Flat per order</option>
                <option value="percent_of_notional">Percent of notional</option>
              </select>
            </label>
            <label class="field">
              <span class="field-label">
                {{ commissionValueLabel }}
                <HoverTooltip :text="commissionValueHelp">
                  <button type="button" class="help-dot" aria-label="Commission value info">i</button>
                </HoverTooltip>
              </span>
              <input
                v-model.number="runDraft.commission_value"
                type="number"
                :min="commissionValueMin"
                :step="commissionValueStep"
                class="form-input"
                placeholder="None"
              />
            </label>
            <label class="field">
              <span class="field-label">Max concurrent positions</span>
              <input v-model.number="runDraft.max_concurrent_positions" type="number" min="1" step="1" class="form-input" />
            </label>
            <label class="field">
              <span class="field-label">Max portfolio risk %</span>
              <input v-model.number="runDraft.max_portfolio_risk_pct" type="number" min="0.5" step="0.5" class="form-input" />
            </label>
            <label class="field">
              <span class="field-label">Max symbol allocation %</span>
              <input v-model.number="runDraft.max_symbol_allocation_pct" type="number" min="1" max="100" step="1" class="form-input" />
            </label>
            <label class="field field--checkbox">
              <input v-model="runDraft.close_open_positions_at_end" type="checkbox" />
              <span class="field-label">
                Close open positions at run end
                <HoverTooltip text="When enabled, positions still open at the selected end date are liquidated and counted as realized P&L. When disabled, they remain open-at-end and are shown as unrealized P&L.">
                  <button type="button" class="help-dot" aria-label="Run-end position handling info">i</button>
                </HoverTooltip>
              </span>
            </label>
            <label v-if="usesDynamicEtfUniverse" class="field">
              <span class="field-label">
                Constituent removal
                <HoverTooltip text="Controls positions already open when a dynamic ETF universe no longer contains that constituent. Leave open keeps them marked at the last eligible bar; close on removal realizes them at that last eligible mark.">
                  <button type="button" class="help-dot" aria-label="Constituent removal policy info">i</button>
                </HoverTooltip>
              </span>
              <select v-model="runDraft.dynamic_universe_exit_policy" class="form-select">
                <option value="leave_open">Leave open</option>
                <option value="close_on_removal">Close on removal</option>
              </select>
            </label>
          </div>

          <div v-if="runDraft.test_mode === 'walk_forward'" class="form-grid two-up">
            <label class="field">
              <span class="field-label">Segments</span>
              <input v-model.number="runDraft.walk_forward_segments" type="number" min="2" step="1" class="form-input" />
            </label>
            <label class="field">
              <span class="field-label">Training share</span>
              <input v-model.number="runDraft.walk_forward_training_share" type="number" min="0.3" max="0.9" step="0.05" class="form-input" />
            </label>
          </div>

          <div v-if="runDraft.test_mode === 'paper_forward'" class="form-grid two-up">
            <label class="field">
              <span class="field-label">Forward window bars</span>
              <input v-model.number="runDraft.paper_forward_bars" type="number" min="5" step="1" class="form-input" />
            </label>
          </div>

          <div class="subsection coverage-preview-section">
            <div class="subsection-head">
              <div class="subsection-title">
                <h4>Coverage preview</h4>
                <HoverTooltip text="Preview the local historical price coverage that matches the current run window, universe selection, run subset, and benchmark. Shared universe shows the overlap every selected symbol has in common; any selected symbol shows the broadest local range available across the chosen universe.">
                  <button type="button" class="help-dot" aria-label="Coverage preview info">i</button>
                </HoverTooltip>
              </div>
            </div>
            <StrategyCoveragePanel
              :coverage="coveragePreview"
              :loading="coveragePreviewLoading"
              :error="coveragePreviewError"
              empty-label="Choose a universe and run window to preview local coverage."
            />
          </div>

          <div class="subsection">
            <button
              type="button"
              class="advanced-toggle"
              @click="showAdvancedRunOptions = !showAdvancedRunOptions"
            >
              <span class="advanced-toggle__title">
                <span class="advanced-toggle__icon" :class="{ 'advanced-toggle__icon--expanded': showAdvancedRunOptions }">▸</span>
                <span>Advanced run options</span>
              </span>
            </button>

            <div v-show="showAdvancedRunOptions" class="advanced-panel">
              <template v-if="availableRunSubsetSymbols.length">
                <div class="subsection-head">
                  <div class="subsection-title">
                    <h4>Run subset</h4>
                    <HoverTooltip text="Use this only when you want to test a smaller slice of the already-published universe without changing the saved strategy universe itself.">
                      <button type="button" class="help-dot" aria-label="Run subset info">i</button>
                    </HoverTooltip>
                  </div>
                </div>

                <label class="field field--checkbox">
                  <input v-model="runDraft.use_subset" type="checkbox" />
                  <span>Limit this run to a subset of the published universe</span>
                </label>

                <div v-if="runDraft.use_subset" class="multi-select-field">
                  <button
                    type="button"
                    class="multi-select-trigger"
                    :class="{ 'form-select--invalid': showRunSubsetValidation }"
                    @click="runSubsetMenuOpen = !runSubsetMenuOpen"
                  >
                    <span>{{ runSubsetSummary }}</span>
                    <span class="multi-select-caret">{{ runSubsetMenuOpen ? '▴' : '▾' }}</span>
                  </button>
                  <div v-if="runSubsetMenuOpen" class="multi-select-menu">
                    <label
                      v-for="symbol in availableRunSubsetSymbols"
                      :key="symbol"
                      class="multi-select-option"
                    >
                      <input
                        :checked="runDraft.overrideSymbols.includes(symbol)"
                        type="checkbox"
                        @change="toggleRunSubsetSymbol(symbol, checkboxValue($event))"
                      />
                      <span>{{ symbol }}</span>
                    </label>
                  </div>
                </div>
              </template>
            </div>
          </div>

          <div class="scroll-list-section">
            <button
              type="button"
              class="scroll-list-toggle"
              :aria-expanded="runHistoryExpanded ? 'true' : 'false'"
              @click="runHistoryExpanded = !runHistoryExpanded"
            >
              <span class="scroll-list-toggle__icon" :class="{ 'scroll-list-toggle__icon--expanded': runHistoryExpanded }">▸</span>
              <span>Run history</span>
              <small>{{ selectedRunBatches.length }} {{ selectedRunBatches.length === 1 ? 'batch' : 'batches' }}</small>
            </button>

          <div v-if="runHistoryExpanded" class="run-list">
            <article
              v-for="batch in selectedRunBatches"
              :key="batch.id"
              class="run-batch"
              :class="{ 'run-batch--active': batch.runs.some(run => strategyLab.selectedRunId === run.id) }"
            >
              <button
                type="button"
                class="run-batch__head"
                @click="strategyLab.selectedRunId = batch.primaryRun?.id ?? null"
              >
                <span>
                  <strong>{{ batch.label }}</strong>
                  <small>{{ formatDateTime(batch.created_at) }}</small>
                </span>
                <span class="status-chip" :class="`status-chip--${batch.status}`">{{ humanizeToken(batch.status) }}</span>
              </button>
              <div class="run-batch__summary">
                <span>{{ batch.runs.length }} {{ batch.runs.length === 1 ? 'run' : 'runs' }}</span>
                <span v-if="batch.bestMarked" :class="pnlClass(batch.bestMarked.value)">Best {{ formatSignedPercent(batch.bestMarked.value) }}</span>
                <span v-if="batch.worstMarked" :class="pnlClass(batch.worstMarked.value)">Worst {{ formatSignedPercent(batch.worstMarked.value) }}</span>
                <span v-if="batch.leastDrawdown" :class="riskCostClass(batch.leastDrawdown.value)">Least DD {{ formatPercent(batch.leastDrawdown.value) }}</span>
              </div>
              <div v-if="batch.changedParameters.length" class="run-batch__parameters">
                <span v-for="parameter in batch.changedParameters" :key="parameter">{{ parameter }}</span>
              </div>
              <div class="run-batch__runs">
                <button
                  v-for="run in batch.runs"
                  :key="run.id"
                  type="button"
                  class="run-item"
                  :class="{ active: strategyLab.selectedRunId === run.id }"
                  @click="strategyLab.selectedRunId = run.id"
                >
                  <div class="run-item__header">
                    <strong>{{ runParameterDiffLabel(run) }}</strong>
                    <span>{{ run.timeframe || currentVersion?.definition_snapshot?.timeframe || 'D1' }}</span>
                  </div>
                  <div class="run-item__meta">
                    <span>{{ run.result_summary?.performance?.closed_trade_count ?? run.result_summary?.performance?.trade_count ?? 0 }} closed</span>
                    <span>·</span>
                    <span>{{ run.result_summary?.performance?.open_position_count ?? 0 }} open</span>
                    <span v-if="run.result_summary?.performance?.realized_net_return_pct != null" class="run-item__metric run-item__metric--primary" :class="pnlClass(run.result_summary.performance.realized_net_return_pct)">R {{ formatSignedPercent(run.result_summary.performance.realized_net_return_pct) }}</span>
                    <span v-if="run.result_summary?.performance?.unrealized_return_pct != null" class="run-item__metric run-item__metric--secondary" :class="pnlClass(run.result_summary.performance.unrealized_return_pct)">U {{ formatSignedPercent(run.result_summary.performance.unrealized_return_pct) }}</span>
                    <span v-if="run.result_summary?.performance?.net_return_pct != null" class="run-item__metric run-item__metric--muted" :class="pnlClass(run.result_summary.performance.net_return_pct)">M {{ formatSignedPercent(run.result_summary.performance.net_return_pct) }}</span>
                  </div>
                </button>
              </div>
            </article>
            <div v-if="!selectedRuns.length" class="empty-state empty-state--small">No backtests yet.</div>
          </div>
          </div>
          </div>
      </div>
      </div>

      <div class="panel panel--results">
        <div class="panel-head">
          <div class="panel-head-title">
            <button
              type="button"
              class="panel-toggle"
              :aria-expanded="sectionExpanded.results ? 'true' : 'false'"
              :title="sectionExpanded.results ? 'Collapse Results' : 'Expand Results'"
              @click="toggleSection('results')"
            >
              <span class="panel-toggle__icon" :class="{ 'panel-toggle__icon--expanded': sectionExpanded.results }">▸</span>
            </button>
            <h3 class="panel-head-heading" @click="toggleSection('results')">Results</h3>
          </div>
          <div class="panel-head-controls">
            <div v-if="selectedRunDetail" class="detail-actions">
              <button
                v-if="selectedRunDetail.test_mode === 'paper_forward'"
                class="btn-secondary btn-icon-only"
                type="button"
                title="Refresh paper-forward"
                aria-label="Refresh paper-forward"
                @click="refreshPaperForwardRun"
                :disabled="strategyLab.isRunning"
              >
                <svg viewBox="0 0 16 16" aria-hidden="true">
                  <path d="M13.5 3.5v3h-3" />
                  <path d="M12.2 6A5 5 0 1 0 13 10" />
                </svg>
              </button>
              <div ref="exportMenuRef" class="export-menu" @click.stop>
                <button
                  class="btn-secondary btn-icon-only export-menu__trigger"
                  type="button"
                  title="Export"
                  aria-label="Export"
                  @click="exportMenuOpen = !exportMenuOpen"
                >
                  <svg viewBox="0 0 16 16" aria-hidden="true">
                    <path d="M8 2.5v7" />
                    <path d="M5.5 7 8 9.5 10.5 7" />
                    <path d="M3 12.5h10" />
                  </svg>
                  <span class="export-menu__caret">{{ exportMenuOpen ? '▴' : '▾' }}</span>
                </button>
                <div v-if="exportMenuOpen" class="export-menu__panel">
                  <button type="button" class="export-menu__item" @click="handleExport('summary')">Export summary</button>
                  <button type="button" class="export-menu__item" @click="handleExport('trades')">Export trades CSV</button>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div v-if="sectionExpanded.results" class="panel-body">
        <div v-if="selectedRunDetail" class="run-detail">
          <div class="form-grid two-up" v-if="selectedRuns.length > 1">
            <label class="field">
              <span class="field-label">Compare against</span>
              <select v-model="compareRunId" class="form-select">
                <option :value="null">No comparison</option>
                <option
                  v-for="run in compareCandidates"
                  :key="run.id"
                  :value="run.id"
                >
                  {{ formatDateTime(run.created_at) }} · {{ humanizeToken(run.test_mode) }}
                </option>
              </select>
            </label>
          </div>

          <div class="run-summary-grid">
            <div class="summary-card">
              <span class="summary-label">Realized return</span>
              <strong :class="pnlClass(performance.realized_net_return_pct)">{{ formatSignedPercent(performance.realized_net_return_pct) }}</strong>
              <div class="summary-breakdown">
                <small class="summary-breakdown__primary">
                  <span>Realized P&amp;L</span>
                  <b :class="pnlClass(performance.realized_net_return_pct)">{{ formatSignedPercent(performance.realized_net_return_pct) }} · {{ formatSignedMoney(realizedPnl) }}</b>
                </small>
                <small class="summary-breakdown__secondary">
                  <span>Unrealized</span>
                  <b :class="pnlClass(performance.unrealized_return_pct)">{{ formatSignedPercent(performance.unrealized_return_pct) }} · {{ formatSignedMoney(performance.unrealized_pnl) }}</b>
                </small>
                <small class="summary-breakdown__muted">
                  <span>Marked total</span>
                  <b :class="pnlClass(performance.net_return_pct)">{{ formatSignedPercent(performance.net_return_pct) }}</b>
                </small>
                <small>
                  <span>Positions</span>
                  <b>{{ performance.closed_trade_count ?? performance.trade_count ?? 0 }} closed · {{ performance.open_position_count ?? 0 }} open</b>
                </small>
              </div>
            </div>
            <div class="summary-card">
              <span class="summary-label">Win rate</span>
              <strong :class="positiveMetricClass(performance.win_rate)">{{ formatPercent(performance.win_rate) }}</strong>
              <small>
                <span v-if="performance.expectancy_r != null" :class="pnlClass(performance.expectancy_r)">
                  {{ performance.expectancy_r.toFixed(2) }}R expectancy
                </span>
                <template v-else>No expectancy yet</template>
              </small>
            </div>
            <div class="summary-card">
              <span class="summary-label">Drawdown</span>
              <strong :class="riskCostClass(performance.max_drawdown_pct)">{{ formatPercent(performance.max_drawdown_pct) }}</strong>
              <small>
                <span v-if="performance.profit_factor != null" :class="profitFactorClass(performance.profit_factor)">
                  {{ performance.profit_factor.toFixed(2) }} profit factor
                </span>
                <template v-else>Profit factor unavailable</template>
              </small>
            </div>
            <div class="summary-card">
              <span class="summary-label">Coverage</span>
              <strong>{{ selectedRunCoverageDetail?.universe.total_bars ?? 0 }} bars</strong>
              <small>
                <template v-if="coverageDurationLabel">{{ coverageDurationLabel }} · </template>
                {{ selectedRunCoverageDetail?.universe.instruments_with_requested_data ?? selectedRunCoverageDetail?.universe.instruments_with_data ?? 0 }} symbols with requested data
              </small>
            </div>
          </div>

          <div class="coverage-detail-panel">
            <div class="subsection-head">
              <div class="subsection-title">
                <h4>Coverage detail</h4>
                <HoverTooltip text="Break down what local history was actually available for the selected run, including the shared overlap across the tested universe, each symbol’s own local range, and the benchmark’s local range.">
                  <button type="button" class="help-dot" aria-label="Coverage detail info">i</button>
                </HoverTooltip>
              </div>
            </div>
            <StrategyCoveragePanel
              :coverage="selectedRunCoverageDetail"
              empty-label="Run a test to inspect detailed coverage."
            />
          </div>

          <div class="result-layout">
            <div class="result-column">
              <div class="equity-panel">
                <div class="equity-panel__head">
                  <strong>Performance</strong>
                  <span>
                    {{
                      selectedRunDetail.result_summary.benchmark?.symbol
                        ? `Strategy vs ${selectedRunDetail.result_summary.benchmark.symbol}`
                        : humanizeToken(selectedRunDetail.result_summary.result_kind || selectedRunDetail.test_mode)
                    }}
                  </span>
                </div>
                <StrategyResultChart
                  :series="performanceChartSeries"
                  label="Strategy performance versus benchmark"
                  :percent="true"
                  empty-label="No performance curve for this run yet."
                />
                <div
                  v-if="selectedRunDetail.result_summary.benchmark?.symbol || benchmarkReturnLabel !== '—' || benchmarkMaxDrawdownLabel !== '—'"
                  class="detail-list detail-list--benchmark-meta detail-list--performance-meta"
                >
                  <div>
                    <span>Benchmark return</span>
                    <strong :class="pnlClass(benchmarkReturnValue)">{{ benchmarkReturnLabel }}</strong>
                  </div>
                  <div>
                    <span>Strategy realized</span>
                    <strong :class="pnlClass(performance.realized_net_return_pct)">{{ strategyRealizedReturnLabel }}</strong>
                  </div>
                  <div>
                    <span>Strategy unrealized</span>
                    <strong class="detail-list__secondary-value" :class="pnlClass(performance.unrealized_pnl)">{{ strategyUnrealizedReturnLabel }}</strong>
                  </div>
                  <div>
                    <span>Strategy marked</span>
                    <strong class="detail-list__muted-value" :class="pnlClass(performance.net_return_pct)">{{ strategyReturnLabel }}</strong>
                  </div>
                  <div v-if="benchmarkMaxDrawdownLabel !== '—'">
                    <span>Benchmark drawdown</span>
                    <strong :class="riskCostClass(selectedRunDetail.result_summary.benchmark?.performance?.max_drawdown_pct)">
                      {{ benchmarkMaxDrawdownLabel }}
                    </strong>
                  </div>
                  <div v-if="benchmarkHoldSpanLabel !== '—'">
                    <span>Hold span</span>
                    <strong>{{ benchmarkHoldSpanLabel }}</strong>
                  </div>
                </div>
                <div v-if="benchmarkCoverageNote" class="equity-panel__footnote">
                  {{ benchmarkCoverageNote }}
                </div>
                <div
                  v-if="selectedRunDetail.result_summary.benchmark_comparison?.excess_return_pct != null"
                  class="equity-panel__footnote"
                  :class="pnlClass(selectedRunDetail.result_summary.benchmark_comparison.excess_return_pct)"
                >
                  {{ formatPercent(selectedRunDetail.result_summary.benchmark_comparison?.excess_return_pct) }} excess versus benchmark
                </div>
              </div>

              <div class="equity-panel">
                <div class="equity-panel__head">
                  <strong>Drawdown</strong>
                  <span>{{ drawdownPanelLabel }}</span>
                </div>
                <StrategyResultChart
                  :series="drawdownChartSeries"
                  label="Drawdown curve"
                  :percent="true"
                  :show-legend="drawdownChartSeries.length > 1"
                  empty-label="No drawdown curve for this run yet."
                />
              </div>

              <div class="equity-panel">
                <div class="equity-panel__head">
                  <strong>Position evolution</strong>
                  <div class="equity-panel__head-meta">
                    <span>{{ positionTimelines.length }} positions</span>
                    <div class="chart-mode-toggle" role="group" aria-label="Position evolution value mode">
                      <button
                        type="button"
                        class="chart-mode-toggle__button"
                        :class="{ 'chart-mode-toggle__button--active': positionEvolutionMode === 'currency' }"
                        aria-label="Show position evolution in currency"
                        @click="positionEvolutionMode = 'currency'"
                      >
                        $
                      </button>
                      <button
                        type="button"
                        class="chart-mode-toggle__button"
                        :class="{ 'chart-mode-toggle__button--active': positionEvolutionMode === 'percent' }"
                        aria-label="Show position evolution in percent"
                        @click="positionEvolutionMode = 'percent'"
                      >
                        %
                      </button>
                    </div>
                  </div>
                </div>
                <StrategyResultChart
                  :series="positionEvolutionSeries"
                  label="Per-position evolution"
                  :currency="positionEvolutionMode === 'currency'"
                  :percent="positionEvolutionMode === 'percent'"
                  :show-legend="false"
                  :height="164"
                  :focus-nearest-series="true"
                  empty-label="No closed positions are available for evolution yet."
                />
              </div>

              <div class="equity-panel">
                <div class="equity-panel__head">
                  <strong>Portfolio capital</strong>
                  <span>Deployed vs idle</span>
                </div>
                <StrategyResultChart
                  :series="portfolioCapitalSeries"
                  label="Portfolio capital over time"
                  :currency="true"
                  empty-label="No portfolio capital timeline for this run yet."
                />
              </div>

              <div class="equity-panel">
                <div class="equity-panel__head">
                  <strong>Open positions</strong>
                  <span>Count over time</span>
                </div>
                <StrategyResultChart
                  :series="portfolioPositionsSeries"
                  label="Open positions over time"
                  :integer-axis="true"
                  :show-legend="false"
                  empty-label="No open-position timeline for this run yet."
                />
              </div>
            </div>

            <div class="result-column result-column--wide">
              <div class="result-panels-grid">
                <div class="mini-panel mini-panel--returns">
                  <div class="subsection-head subsection-head--returns">
                    <h4>Return breakdown</h4>
                    <div class="chart-mode-toggle" role="group" aria-label="Return breakdown mode">
                      <button
                        type="button"
                        class="chart-mode-toggle__button"
                        :class="{ 'chart-mode-toggle__button--active': activeReturnsMode === 'monthly' }"
                        aria-label="Show monthly returns"
                        @click="returnsViewMode = 'monthly'"
                      >
                        M
                      </button>
                      <button
                        type="button"
                        class="chart-mode-toggle__button"
                        :class="{ 'chart-mode-toggle__button--active': activeReturnsMode === 'quarterly' }"
                        aria-label="Show quarterly returns"
                        @click="returnsViewMode = 'quarterly'"
                      >
                        Q
                      </button>
                      <button
                        v-if="yearlyReturns.length"
                        type="button"
                        class="chart-mode-toggle__button"
                        :class="{ 'chart-mode-toggle__button--active': activeReturnsMode === 'yearly' }"
                        aria-label="Show yearly returns"
                        @click="returnsViewMode = 'yearly'"
                      >
                        Y
                      </button>
                    </div>
                  </div>
                  <ReturnsHeatmap
                    :rows="activeReturnsRows"
                    :mode="activeReturnsMode"
                    :empty-label="activeReturnsEmptyLabel"
                    :cell-details="activeReturnsDetails"
                  />
                </div>

                <div class="mini-panel">
                  <div class="subsection-head"><h4>Return by symbol</h4></div>
                  <SymbolPerformanceBars
                    :rows="symbolPerformance"
                    :events="executionLog"
                    empty-label="No per-symbol attribution yet."
                  />
                </div>

                <div class="mini-panel" v-if="selectedRunDetail.result_summary.signal_summary">
                  <div class="subsection-head"><h4>Signal replay</h4></div>
                  <SignalReplayBreakdown
                    :signal-count="selectedRunDetail.result_summary.signal_summary.signal_count ?? 0"
                    :replayed-signal-count="selectedRunDetail.result_summary.signal_summary.replayed_signal_count ?? 0"
                    :setup-type-breakdown="selectedRunDetail.result_summary.signal_summary.setup_type_breakdown ?? {}"
                  />
                </div>

                <div class="mini-panel" v-if="optimizationRows.length">
                  <div class="subsection-head"><h4>Optimization</h4></div>
                  <OptimizationLeaderboard
                    :rows="optimizationRows"
                    empty-label="No optimization leaderboard yet."
                  />
                </div>

                <div class="mini-panel mini-panel--wide" v-if="walkForwardSegments.length">
                  <div class="subsection-head"><h4>Walk-forward</h4></div>
                  <WalkForwardSegments
                    :segments="walkForwardSegments"
                    :training-share="selectedRunDetail.result_summary.walk_forward?.training_share ?? null"
                    :avg-out-sample-return-pct="selectedRunDetail.result_summary.walk_forward?.out_of_sample_avg_return_pct ?? null"
                    empty-label="No walk-forward segments yet."
                  />
                </div>

                <div class="mini-panel mini-panel--wide" v-if="paperForwardSnapshots.length || paperForwardCurve.length">
                  <div class="subsection-head"><h4>Paper-forward monitor</h4></div>
                  <PaperForwardMonitorPanel
                    :snapshots="paperForwardSnapshots"
                    :forward-curve="paperForwardCurve"
                    :window-bars="selectedRunDetail.result_summary.paper_forward?.window_bars ?? null"
                    empty-label="No paper-forward monitor yet."
                  />
                </div>

                <div class="mini-panel mini-panel--wide" v-if="comparisonRows.length">
                  <div class="subsection-head"><h4>Run comparison</h4></div>
                  <RunComparisonTable
                    :current-label="currentRunComparisonLabel"
                    :compare-label="compareRunComparisonLabel"
                    :rows="comparisonRows"
                    empty-label="No comparison selected."
                  />
                </div>

                <div class="mini-panel" v-if="tradeDistributions.r_histogram?.length">
                  <div class="subsection-head"><h4>Closed trade R multiples</h4></div>
                  <DistributionBars
                    :rows="tradeDistributions.r_histogram"
                    :trades="visibleTrades"
                    empty-label="No closed trade R multiples yet."
                  />
                </div>
                <div class="mini-panel mini-panel--wide" v-if="tradeDistributions.mae_mfe?.rows?.length">
                  <div class="subsection-head"><h4>Trade excursions</h4></div>
                  <ExcursionBars :rows="tradeDistributions.mae_mfe.rows" />
                </div>
              </div>

              <div class="trade-table-wrap">
                <div class="subsection-head subsection-head--table">
                  <h4>Execution log</h4>
                </div>
                <div class="trade-table-scroll">
                <table class="trade-table">
                  <thead>
                    <tr>
                      <th v-for="column in executionLogColumns" :key="column.key">
                        <div class="trade-table__head-cell">
                          <button
                            type="button"
                            class="trade-table__sort"
                            :aria-label="`Sort execution log by ${column.label}`"
                            @click="toggleExecutionLogSort(column.key)"
                          >
                            <span>{{ column.label }}</span>
                            <span
                              class="trade-table__sort-icon"
                              :class="{ 'trade-table__sort-icon--active': executionLogSort.key === column.key }"
                              aria-hidden="true"
                            >
                              {{ executionLogSort.key === column.key ? (executionLogSort.direction === 'asc' ? '▲' : '▼') : '↕' }}
                            </span>
                          </button>
                          <button
                            type="button"
                            class="trade-table__filter-button"
                            :class="{ 'trade-table__filter-button--active': isExecutionLogFilterActive(column.key) }"
                            :aria-label="`${isExecutionLogFilterActive(column.key) ? 'Edit active' : 'Filter'} execution log by ${column.label}`"
                            @click.stop="toggleExecutionLogFilter(column.key)"
                          >
                            <span aria-hidden="true">⌕</span>
                          </button>
                          <div
                            v-if="openExecutionLogFilter === column.key"
                            class="trade-table__filter-popover"
                            @pointerdown.stop
                            @click.stop
                          >
                            <div class="trade-table__filter-popover-head">
                              <span>Filter {{ column.label }}</span>
                              <button
                                type="button"
                                aria-label="Close execution log filter"
                                @click="openExecutionLogFilter = null"
                              >
                                ×
                              </button>
                            </div>
                            <input
                              v-model="executionLogFilters[column.key]"
                              class="trade-table__filter"
                              type="search"
                              :placeholder="`Type ${column.label.toLowerCase()}…`"
                              :aria-label="`Filter execution log by ${column.label}`"
                              @keydown.esc="openExecutionLogFilter = null"
                            >
                            <button
                              v-if="isExecutionLogFilterActive(column.key)"
                              type="button"
                              class="trade-table__filter-clear"
                              @click="executionLogFilters[column.key] = ''"
                            >
                              Clear
                            </button>
                          </div>
                        </div>
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="event in filteredExecutionLog" :key="`${event.position_id}-${event.event_type}-${event.ts}`">
                      <td>{{ formatShortDateTime(event.ts) }}</td>
                      <td>{{ humanizeToken(event.event_type) }}</td>
                      <td>{{ event.symbol || '—' }}</td>
                      <td>{{ event.side ? humanizeToken(event.side) : '—' }}</td>
                      <td>{{ event.price != null ? formatMoney(event.price) : '—' }}</td>
                      <td>{{ event.quantity != null ? Number(event.quantity).toFixed(2) : '—' }}</td>
                      <td :class="pnlClass(event.pnl_pct ?? event.pnl)">
                        <div v-if="event.pnl != null" class="pnl-cell">
                          <strong>{{ event.pnl_pct != null ? formatSignedPercent(event.pnl_pct) : formatSignedMoney(event.pnl) }}</strong>
                          <small v-if="event.pnl_pct != null">{{ formatSignedMoney(event.pnl) }}</small>
                        </div>
                        <template v-else>—</template>
                      </td>
                      <td>
                        <div class="execution-reason-cell">
                          <strong>{{ humanizeToken(event.reason || event.event_type) }}</strong>
                          <small v-if="executionUniverseContext(event)">{{ executionUniverseContext(event) }}</small>
                        </div>
                      </td>
                    </tr>
                    <tr v-if="!filteredExecutionLog.length">
                      <td colspan="8" class="trade-table__empty">
                        {{ executionLog.length ? 'No execution events match the current filters.' : 'No execution events were recorded for this run.' }}
                      </td>
                    </tr>
                  </tbody>
                </table>
                </div>
            </div>
          </div>
          </div>
        </div>
        <div v-else class="empty-state">Run a backtest, then select it here to inspect the results.</div>
        </div>
      </div>
    </section>

    <TextPromptModal
      v-model="showDeleteModal"
      title="Delete Strategy"
      :message="deleteStrategyMessage"
      confirm-label="Delete"
      cancel-label="Cancel"
      :show-input="false"
      @submit="deleteCurrentStrategy"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'

import HoverTooltip from '@/components/common/HoverTooltip.vue'
import ResizeHandle from '@/components/common/ResizeHandle.vue'
import SearchBar from '@/components/common/SearchBar.vue'
import TagPicker from '@/components/common/TagPicker.vue'
import TextPromptModal from '@/components/common/TextPromptModal.vue'
import DistributionBars from '@/components/strategy/DistributionBars.vue'
import ExcursionBars from '@/components/strategy/ExcursionBars.vue'
import OptimizationLeaderboard from '@/components/strategy/OptimizationLeaderboard.vue'
import PaperForwardMonitorPanel from '@/components/strategy/PaperForwardMonitorPanel.vue'
import ReturnsHeatmap from '@/components/strategy/ReturnsHeatmap.vue'
import RunComparisonTable from '@/components/strategy/RunComparisonTable.vue'
import SignalReplayBreakdown from '@/components/strategy/SignalReplayBreakdown.vue'
import SweepValueInput from '@/components/strategy/SweepValueInput.vue'
import SymbolPerformanceBars from '@/components/strategy/SymbolPerformanceBars.vue'
import StrategyCoveragePanel from '@/components/strategy/StrategyCoveragePanel.vue'
import StrategyResultChart from '@/components/strategy/StrategyResultChart.vue'
import StrategyRuleTreeEditor from '@/components/strategy/StrategyRuleTreeEditor.vue'
import WalkForwardSegments from '@/components/strategy/WalkForwardSegments.vue'
import { api } from '@/lib/api'
import {
  STRATEGY_LAB_CONDITION_TYPE_OPTIONS,
  createDefaultTechnicalCondition,
  describeTechnicalCondition,
  normalizeTechnicalCondition,
  type TechnicalConditionDraft,
} from '@/lib/technicalConditions'
import { useStrategyLabStore } from '@/stores/strategyLab'
import type {
  Basket,
  ETFProfile,
  StrategyCoverageInstrument,
  StrategyCoverageBenchmark,
  StrategyCoveragePreview,
  StrategyCoverageUniverse,
  StrategyDefinition,
  StrategyRun,
  StrategyRunBatch,
  StrategyVersion,
  Watchlist,
} from '@/types'

type StrategyUniverseMode = 'radar' | 'symbols' | 'watchlist' | 'screener' | 'basket' | 'etf_holdings'
type EtfHoldingSnapshotMode = 'latest' | 'date' | 'dynamic'
type BasketSnapshotMode = 'static' | 'dynamic'
type StrategyLabSectionKey = 'profile' | 'entry' | 'risk' | 'exits' | 'runs' | 'results'
type StrategyLabSectionState = Record<StrategyLabSectionKey, boolean>
type StrategyLabStoredSectionStates = Record<string, Partial<StrategyLabSectionState>>
type ExecutionLogColumnKey = 'time' | 'event' | 'symbol' | 'side' | 'price' | 'size' | 'pnl' | 'reason'
type SortDirection = 'asc' | 'desc'
type BatchMetricRef = { run: StrategyRun; value: number } | null

interface RunBatchView {
  id: string
  label: string
  status: string
  created_at: string
  runs: StrategyRun[]
  primaryRun: StrategyRun | null
  changedParameters: string[]
  bestMarked: BatchMetricRef
  worstMarked: BatchMetricRef
  leastDrawdown: BatchMetricRef
}

interface BuilderConditionNode {
  id: string
  kind: 'condition'
  condition: TechnicalConditionDraft
}

interface BuilderGroupNode {
  id: string
  kind: 'group'
  type: 'all' | 'any'
  children: BuilderRuleNode[]
}

interface BuilderNotNode {
  id: string
  kind: 'not'
  condition: BuilderRuleNode | null
}

type BuilderRuleNode = BuilderConditionNode | BuilderGroupNode | BuilderNotNode

interface RadarReplayDraft {
  setup_types: string[]
  states: string[]
  min_score: number
}

interface ScreenerOption {
  id: number
  name: string
}

const STRATEGY_SIDEBAR_STORAGE_KEY = 'strategyLab.sidebar.v1'
const STRATEGY_SIDEBAR_MIN_WIDTH = 272
const STRATEGY_SIDEBAR_MAX_WIDTH = 420
const STRATEGY_SIDEBAR_DEFAULT_WIDTH = 308
const STRATEGY_SIDEBAR_COLLAPSED_WIDTH = 16
const STRATEGY_SECTION_STORAGE_KEY = 'strategyLab.sections.v1'
const initialSidebarState = loadStrategySidebarState()
const initialSectionStates = loadStrategySectionStates()

const strategyLab = useStrategyLabStore()
const availableWatchlists = ref<Watchlist[]>([])
const availableScreeners = ref<ScreenerOption[]>([])
const availableBaskets = ref<Basket[]>([])
const availableEtfHoldings = ref<ETFProfile[]>([])
const timeframes = ['M1', 'M5', 'M15', 'M30', 'H1', 'H2', 'H4', 'H12', 'D1', 'W1', 'MN']
const radarSetupOptions = [
  { value: 'approaching_support', label: 'Approaching support' },
  { value: 'approaching_resistance', label: 'Approaching resistance' },
  { value: 'breakout', label: 'Breakout' },
  { value: 'breakout_retest', label: 'Breakout retest' },
  { value: 'breakdown', label: 'Breakdown' },
  { value: 'breakdown_retest', label: 'Breakdown retest' },
  { value: 'fakeout', label: 'Fakeout' },
  { value: 'fakedown', label: 'Fakedown' },
  { value: 'failed_reclaim', label: 'Failed reclaim' },
  { value: 'failed_breakdown_recovery', label: 'Failed breakdown recovery' },
  { value: 'compression_support', label: 'Compression support' },
  { value: 'compression_resistance', label: 'Compression resistance' },
  { value: 'reclaim', label: 'Reclaim' },
  { value: 'rejection', label: 'Rejection' },
]
const radarStateOptions = [
  { value: 'developing', label: 'Developing' },
  { value: 'confirmed', label: 'Confirmed' },
  { value: 'resolved', label: 'Resolved' },
  { value: 'invalidated', label: 'Invalidated' },
  { value: 'stale', label: 'Stale' },
]
const executionLogColumns: Array<{ key: ExecutionLogColumnKey; label: string }> = [
  { key: 'time', label: 'Time' },
  { key: 'event', label: 'Event' },
  { key: 'symbol', label: 'Symbol' },
  { key: 'side', label: 'Side' },
  { key: 'price', label: 'Price' },
  { key: 'size', label: 'Size' },
  { key: 'pnl', label: 'P&L' },
  { key: 'reason', label: 'Reason' },
]
const isNew = ref(false)
const versionNotes = ref('')
const symbolInput = ref('')
const sourceType = ref<'custom' | 'radar'>('custom')
const universeMode = ref<StrategyUniverseMode>('symbols')
const selectedWatchlistId = ref<number | null>(null)
const selectedScreenerId = ref<number | null>(null)
const selectedBasketId = ref<number | null>(null)
const selectedBasketSnapshotMode = ref<BasketSnapshotMode>('static')
const selectedEtfHoldingSymbol = ref('')
const selectedEtfHoldingSnapshotMode = ref<EtfHoldingSnapshotMode>('latest')
const selectedEtfHoldingSnapshotDate = ref('')
const compareRunId = ref<number | null>(null)
const showDeleteModal = ref(false)
const radarSetupMenuOpen = ref(false)
const radarStateMenuOpen = ref(false)
const showAdvancedRunOptions = ref(false)
const runSubsetMenuOpen = ref(false)
const exportMenuOpen = ref(false)
const exportMenuRef = ref<HTMLElement | null>(null)
const runHistoryExpanded = ref(false)
const sidebarWidth = ref(initialSidebarState.width)
const sidebarCollapsed = ref(initialSidebarState.collapsed)
const storedSectionStates = ref<StrategyLabStoredSectionStates>(initialSectionStates)
const sectionExpanded = ref<StrategyLabSectionState>(defaultSectionState(false))
const coveragePreview = ref<StrategyCoveragePreview | null>(null)
const coveragePreviewLoading = ref(false)
const coveragePreviewError = ref<string | null>(null)
const executionLogSort = reactive<{ key: ExecutionLogColumnKey; direction: SortDirection }>({
  key: 'time',
  direction: 'asc',
})
const executionLogFilters = reactive<Record<ExecutionLogColumnKey, string>>({
  time: '',
  event: '',
  symbol: '',
  side: '',
  price: '',
  size: '',
  pnl: '',
  reason: '',
})
const openExecutionLogFilter = ref<ExecutionLogColumnKey | null>(null)
let coveragePreviewSequence = 0

type OptionalNumberInput = number | string | '' | null
type SweepMode = 'single' | 'list' | 'range'

interface SweepValueDraft {
  mode: SweepMode
  single: OptionalNumberInput
  list: number[]
  range: {
    start: OptionalNumberInput
    end: OptionalNumberInput
    step: OptionalNumberInput
  }
}

function createSweepDraft(single: OptionalNumberInput, step: number): SweepValueDraft {
  return {
    mode: 'single',
    single,
    list: [],
    range: {
      start: single,
      end: single,
      step,
    },
  }
}

function normalizeEtfHoldingSnapshotMode(config: Record<string, any>): EtfHoldingSnapshotMode {
  const rawMode = String(config.snapshot_mode ?? config.mode ?? '').trim().toLowerCase()
  if (['dynamic', 'point_in_time', 'point-in-time', 'historical'].includes(rawMode)) return 'dynamic'
  if (['date', 'as_of_date', 'specific_date'].includes(rawMode) || config.snapshot_date) return 'date'
  return 'latest'
}

const draft = reactive({
  name: '',
  description: '',
  is_active: true,
  tags: [] as string[],
})

const logicDraft = reactive({
  timeframe: 'D1',
  direction: 'long',
  stop_model: 'percent' as 'percent' | 'atr',
  stop_atr_period: 14,
  stop_atr_multiple: 2,
  hard_trailing_stop_pct: '' as OptionalNumberInput,
  hard_trailing_activation_pct: 0,
  break_even_rr: '' as OptionalNumberInput,
  trailing_stop_rr: '' as OptionalNumberInput,
  position_sizing_mode: 'percent_risk' as 'percent_risk' | 'fixed_cash' | 'percent_capital' | 'fixed_quantity',
  position_sizing_value: 1,
  pyramiding_max_entries: 1,
  benchmark_symbol: 'SPY',
  symbols: [] as string[],
  ruleTree: createGroupNode('all', []) as BuilderGroupNode,
  exitRuleTree: createGroupNode('all', []) as BuilderGroupNode,
})

const sweepDraft = reactive({
  stop_loss_pct: createSweepDraft(2, 0.1),
  take_profit_rr: createSweepDraft(2, 0.25),
  max_bars_in_trade: createSweepDraft(20, 1),
})

const radarDraft = reactive<RadarReplayDraft>({
  setup_types: [],
  states: [],
  min_score: 0.65,
})

const runDraft = reactive({
  test_mode: 'backtest' as 'backtest' | 'walk_forward' | 'paper_forward',
  timeframe: '',
  date_from: '',
  date_to: '',
  initial_capital: 100000,
  risk_per_trade_pct: 1,
  slippage_bps: 5 as OptionalNumberInput,
  commission_model: 'fixed_round_trip' as 'fixed_round_trip' | 'fixed_per_order' | 'percent_of_notional',
  commission_value: '' as OptionalNumberInput,
  walk_forward_segments: 3,
  walk_forward_training_share: 0.6,
  paper_forward_bars: 20,
  max_concurrent_positions: 4,
  max_portfolio_risk_pct: 4,
  max_symbol_allocation_pct: 35,
  close_open_positions_at_end: false,
  dynamic_universe_exit_policy: 'leave_open' as 'leave_open' | 'close_on_removal',
  use_subset: false,
  overrideSymbols: [] as string[],
})

const currentVersion = computed<StrategyVersion | null>(() =>
  strategyLab.selectedDefinition?.versions.find(version => version.is_current)
  ?? strategyLab.selectedDefinition?.versions[0]
  ?? null
)
const selectedWatchlist = computed(() =>
  availableWatchlists.value.find(item => item.id === selectedWatchlistId.value) ?? null
)
const selectedScreener = computed(() =>
  availableScreeners.value.find(item => item.id === selectedScreenerId.value) ?? null
)
const selectedBasket = computed(() =>
  availableBaskets.value.find(item => item.id === selectedBasketId.value) ?? null
)
const basketSupportsDynamicHistory = computed(() => {
  const basket = selectedBasket.value
  return Boolean(basket?.source_etf_profile_id) || Number(basket?.snapshot_count ?? 0) > 0
})
const selectedEtfHolding = computed(() =>
  availableEtfHoldings.value.find(item => item.symbol === selectedEtfHoldingSymbol.value) ?? null
)
const usesDynamicEtfUniverse = computed(() =>
  (universeMode.value === 'etf_holdings' && selectedEtfHoldingSnapshotMode.value === 'dynamic')
  || (universeMode.value === 'basket' && basketSupportsDynamicHistory.value && selectedBasketSnapshotMode.value === 'dynamic')
)
const availableRunSubsetSymbols = computed(() => {
  if (universeMode.value === 'symbols') return [...logicDraft.symbols]
  if (universeMode.value === 'watchlist') {
    return normalizeSymbols((selectedWatchlist.value?.items ?? []).map(item => item.symbol || item.name || ''))
  }
  if (universeMode.value === 'basket') {
    return normalizeSymbols((selectedBasket.value?.members ?? []).map(item => item.symbol || item.name || ''))
  }
  if (universeMode.value === 'etf_holdings') {
    return normalizeSymbols(coveragePreview.value?.universe.resolved_symbols ?? [])
  }
  return []
})
const effectiveRunUniverseConfig = computed<Record<string, any>>(() => {
  if (runDraft.use_subset && runDraft.overrideSymbols.length) {
    return { symbols: [...runDraft.overrideSymbols] }
  }
  if (sourceType.value === 'radar' && universeMode.value === 'radar') return {}
  if (universeMode.value === 'watchlist' && selectedWatchlistId.value != null) {
    return { watchlist_id: selectedWatchlistId.value }
  }
  if (universeMode.value === 'screener' && selectedScreenerId.value != null) {
    return { screener_id: selectedScreenerId.value }
  }
  if (universeMode.value === 'basket' && selectedBasketId.value != null) {
    return {
      basket_id: selectedBasketId.value,
      ...(selectedBasketSnapshotMode.value === 'dynamic'
        ? { basket_snapshot_mode: selectedBasketSnapshotMode.value }
        : {}),
    }
  }
  if (universeMode.value === 'etf_holdings' && selectedEtfHoldingSymbol.value) {
    return {
      etf_holdings: {
        symbol: selectedEtfHoldingSymbol.value,
        snapshot_mode: selectedEtfHoldingSnapshotMode.value,
        ...(selectedEtfHoldingSnapshotMode.value === 'date' && selectedEtfHoldingSnapshotDate.value
          ? { snapshot_date: selectedEtfHoldingSnapshotDate.value }
          : {}),
      },
    }
  }
  return { symbols: [...logicDraft.symbols] }
})
const availableTags = computed(() =>
  Array.from(new Set(strategyLab.definitions.flatMap(definition => normalizeTags(definition.tags)))).sort((a, b) =>
    a.localeCompare(b),
  )
)
const radarSetupSummary = computed(() => summarizeRadarOptions(radarDraft.setup_types, radarSetupOptions, 'All setup families'))
const radarStateSummary = computed(() => summarizeRadarOptions(radarDraft.states, radarStateOptions, 'All states'))
const deleteStrategyMessage = computed(() => {
  const name = strategyLab.selectedDefinition?.name?.trim()
  if (!name) return 'Delete this strategy? This action cannot be undone.'
  return `Delete strategy "${name}"? This action cannot be undone.`
})
const coveragePreviewPayload = computed(() => ({
  source_type: sourceType.value,
  timeframe: runDraft.timeframe || logicDraft.timeframe || 'D1',
  date_from: runDraft.date_from ? `${runDraft.date_from}T00:00:00Z` : null,
  date_to: runDraft.date_to ? `${runDraft.date_to}T23:59:59Z` : null,
  universe_config: effectiveRunUniverseConfig.value,
  benchmark_config: logicDraft.benchmark_symbol.trim()
    ? { symbol: logicDraft.benchmark_symbol.trim().toUpperCase() }
    : {},
}))
const coveragePreviewSignature = computed(() => JSON.stringify(coveragePreviewPayload.value))

const selectedRuns = computed<StrategyRun[]>(() => strategyLab.selectedDefinition?.runs ?? [])
const selectedRunBatches = computed<RunBatchView[]>(() => buildRunBatchViews(
  strategyLab.selectedDefinition?.run_batches ?? [],
  selectedRuns.value,
))
const selectedRunDetail = computed<StrategyRun | null>(() =>
  selectedRuns.value.find(run => run.id === strategyLab.selectedRunId) ?? selectedRuns.value[0] ?? null
)
const compareCandidates = computed<StrategyRun[]>(() =>
  selectedRunDetail.value
    ? selectedRuns.value.filter(run => run.id !== selectedRunDetail.value?.id)
    : []
)
const compareRun = computed<StrategyRun | null>(() =>
  selectedRuns.value.find(run => run.id === compareRunId.value) ?? null
)

function buildRunBatchViews(batches: StrategyRunBatch[], runs: StrategyRun[]): RunBatchView[] {
  const runsByBatch = new Map<number, StrategyRun[]>()
  const unbatchedRuns: StrategyRun[] = []
  for (const run of runs) {
    if (run.run_batch_id != null) {
      const bucket = runsByBatch.get(run.run_batch_id) ?? []
      bucket.push(run)
      runsByBatch.set(run.run_batch_id, bucket)
    } else {
      unbatchedRuns.push(run)
    }
  }

  const views = batches.map(batch => {
    const batchRuns = (runsByBatch.get(batch.id) ?? []).sort(sortRunsDescending)
    return buildRunBatchView({
      id: `batch-${batch.id}`,
      label: batch.label || parameterDimensionLabel(batch.parameter_dimensions) || 'Parameter batch',
      status: batch.status,
      created_at: batch.created_at,
      runs: batchRuns,
      dimensions: batch.parameter_dimensions,
    })
  })

  for (const run of unbatchedRuns) {
    views.push(buildRunBatchView({
      id: `run-${run.id}`,
      label: humanizeToken(run.test_mode),
      status: String(run.status),
      created_at: run.created_at,
      runs: [run],
      dimensions: [],
    }))
  }

  return views
    .filter(batch => batch.runs.length)
    .sort((left, right) => String(right.created_at).localeCompare(String(left.created_at)))
}

function buildRunBatchView(input: {
  id: string
  label: string
  status: string
  created_at: string
  runs: StrategyRun[]
  dimensions: any[]
}): RunBatchView {
  const runs = [...input.runs].sort(sortRunsDescending)
  return {
    id: input.id,
    label: input.label,
    status: input.status,
    created_at: input.created_at,
    runs,
    primaryRun: bestRunByMetric(runs, 'net_return_pct')?.run ?? runs[0] ?? null,
    changedParameters: changedParameterLabels(input.dimensions, runs),
    bestMarked: bestRunByMetric(runs, 'net_return_pct'),
    worstMarked: bestRunByMetric(runs, 'net_return_pct', false),
    leastDrawdown: bestRunByMetric(runs, 'max_drawdown_pct', false),
  }
}

function sortRunsDescending(left: StrategyRun, right: StrategyRun) {
  return String(right.created_at).localeCompare(String(left.created_at)) || right.id - left.id
}

function runMetric(run: StrategyRun, key: string) {
  const value = Number(run.result_summary?.performance?.[key])
  return Number.isFinite(value) ? value : null
}

function bestRunByMetric(runs: StrategyRun[], key: string, higherIsBetter = true): BatchMetricRef {
  const ranked = runs
    .map(run => ({ run, value: runMetric(run, key) }))
    .filter((entry): entry is { run: StrategyRun; value: number } => entry.value != null)
    .sort((left, right) => higherIsBetter ? right.value - left.value : left.value - right.value)
  return ranked[0] ?? null
}

function parameterDimensionLabel(dimensions: any[]) {
  const labels = dimensions.map(dimension => String(dimension?.label || dimension?.key || '').trim()).filter(Boolean)
  if (!labels.length) return ''
  if (labels.length <= 3) return labels.join(' × ')
  return `${labels.slice(0, 3).join(' × ')} + ${labels.length - 3} more`
}

function changedParameterLabels(dimensions: any[], runs: StrategyRun[]) {
  const labels = new Map<string, string>()
  for (const dimension of dimensions) {
    const key = String(dimension?.key || '').trim()
    if (key) labels.set(key, String(dimension?.label || key))
  }
  const keys = new Set<string>()
  for (const run of runs) {
    for (const key of Object.keys(run.parameter_diff || run.parameter_values || {})) keys.add(key)
  }
  return [...keys].map(key => labels.get(key) || parameterKeyLabel(key)).slice(0, 4)
}

function runParameterDiffLabel(run: StrategyRun) {
  const entries = Object.entries(run.parameter_diff || run.parameter_values || {})
  if (!entries.length) return formatDateTime(run.created_at)
  return entries
    .slice(0, 3)
    .map(([key, value]) => `${parameterKeyLabel(key)} ${formatParameterValue(value)}`)
    .join(' · ')
}

function parameterKeyLabel(key: string) {
  const labels: Record<string, string> = {
    'risk.stop_loss_pct': 'Stop',
    'exits.take_profit_rr': 'Target',
    'exits.max_bars_in_trade': 'Bars',
  }
  const parts = key.split('.')
  return labels[key] || parts[parts.length - 1]?.replace(/_/g, ' ') || key
}

function formatParameterValue(value: unknown) {
  if (typeof value === 'number') return Number.isInteger(value) ? String(value) : value.toFixed(2)
  return String(value)
}
const conditionCount = computed(() => countConditionLeaves(logicDraft.ruleTree))
const rootGroupMode = computed(() => logicDraft.ruleTree.type)
const exitConditionCount = computed(() => countConditionLeaves(logicDraft.exitRuleTree))
const exitRootGroupMode = computed(() => logicDraft.exitRuleTree.type)
const paperForwardSnapshots = computed<any[]>(() =>
  Array.isArray(selectedRunDetail.value?.result_summary?.paper_forward?.monitor_snapshots)
    ? selectedRunDetail.value?.result_summary?.paper_forward?.monitor_snapshots
    : []
)
const paperForwardCurve = computed<any[]>(() =>
  Array.isArray(selectedRunDetail.value?.result_summary?.paper_forward?.forward_curve)
    ? selectedRunDetail.value?.result_summary?.paper_forward?.forward_curve
    : []
)

const performance = computed<Record<string, number | null>>(() =>
  selectedRunDetail.value?.result_summary?.performance ?? {}
)

const initialCapital = computed(() => {
  const value = Number(performance.value.initial_capital)
  return Number.isFinite(value) ? value : null
})

const realizedPnl = computed(() => {
  const realizedEnding = Number(performance.value.realized_ending_capital)
  const initial = initialCapital.value
  if (initial != null && Number.isFinite(realizedEnding)) return realizedEnding - initial

  const ending = Number(performance.value.ending_capital)
  const unrealized = Number(performance.value.unrealized_pnl)
  if (initial != null && Number.isFinite(ending) && Number.isFinite(unrealized)) {
    return ending - initial - unrealized
  }

  return null
})

const strategyRealizedReturnLabel = computed(() =>
  formatSignedPercent(performance.value.realized_net_return_pct),
)

const strategyUnrealizedReturnLabel = computed(() => {
  const returnLabel = formatSignedPercent(performance.value.unrealized_return_pct)
  const pnlLabel = formatSignedMoney(performance.value.unrealized_pnl)
  if (returnLabel === '—' && pnlLabel === '—') return '—'
  return `${returnLabel} · ${pnlLabel}`
})

const selectedRunCoverageDetail = computed<StrategyCoveragePreview | null>(() => {
  if (!selectedRunDetail.value) return null
  const rawCoverage = selectedRunDetail.value.result_summary?.coverage as Record<string, any> | undefined
  const runCoverage = coerceStrategyCoverageUniverse(rawCoverage)
  if (!runCoverage) return null
  return {
    timeframe: String(
      selectedRunDetail.value.timeframe
      || currentVersion.value?.definition_snapshot?.timeframe
      || 'D1',
    ),
    requested_date_from: String(rawCoverage?.requested_date_from ?? selectedRunDetail.value.date_from ?? '') || null,
    requested_date_to: String(rawCoverage?.requested_date_to ?? selectedRunDetail.value.date_to ?? '') || null,
    universe: runCoverage,
    benchmark: coerceStrategyCoverageBenchmark(selectedRunDetail.value.result_summary?.benchmark?.coverage),
    warnings: [],
  }
})

const coverageDurationLabel = computed(() => {
  const coverage = selectedRunCoverageDetail.value?.universe
  const totalBars = Number(coverage?.total_bars ?? 0)
  const instrumentsWithData = Math.max(
    1,
    Number(coverage?.instruments_with_requested_data ?? coverage?.instruments_with_data ?? 0) || 1,
  )
  if (!Number.isFinite(totalBars) || totalBars <= 0) return ''
  const timeframe = String(
    selectedRunCoverageDetail.value?.timeframe
      || selectedRunDetail.value?.timeframe
      || currentVersion.value?.definition_snapshot?.timeframe
      || 'D1',
  )
  const averageBarsPerSymbol = totalBars / instrumentsWithData
  const span = humanizeBarSpan(averageBarsPerSymbol, timeframe)
  return span ? `≈ ${span} per symbol on ${timeframe}` : ''
})

const visibleTrades = computed<any[]>(() =>
  Array.isArray(selectedRunDetail.value?.result_summary?.trades)
    ? selectedRunDetail.value?.result_summary?.trades
    : []
)

function eventSortOrder(eventType: string | null | undefined) {
  const value = String(eventType ?? '')
  if (value === 'entry') return 0
  if (value === 'exit') return 1
  if (value === 'open_at_end') return 2
  if (value === 'rejected') return 3
  return 4
}

function toggleExecutionLogSort(key: ExecutionLogColumnKey) {
  if (executionLogSort.key === key) {
    executionLogSort.direction = executionLogSort.direction === 'asc' ? 'desc' : 'asc'
    return
  }
  executionLogSort.key = key
  executionLogSort.direction = 'asc'
}

function toggleExecutionLogFilter(key: ExecutionLogColumnKey) {
  openExecutionLogFilter.value = openExecutionLogFilter.value === key ? null : key
}

function isExecutionLogFilterActive(key: ExecutionLogColumnKey) {
  return Boolean(executionLogFilters[key].trim())
}

function executionLogFilterMatches(event: any, key: ExecutionLogColumnKey) {
  const filter = executionLogFilters[key].trim().toLowerCase()
  if (!filter) return true
  const searchValue = executionLogSearchValue(event, key)
  return searchValue.includes(filter) || looseExecutionLogSearchValue(searchValue).includes(looseExecutionLogSearchValue(filter))
}

function executionLogSearchValue(event: any, key: ExecutionLogColumnKey) {
  const values = executionLogColumnSearchValues(event, key)
  return values
    .filter(value => value != null && value !== '')
    .map(value => String(value).toLowerCase())
    .join(' ')
}

function executionUniverseContext(event: any) {
  const compositionDate = event?.universe_snapshot_composition_date
  if (!compositionDate) return ''
  const status = event?.universe_membership_status
    ? humanizeToken(event.universe_membership_status)
    : 'Universe'
  const knownAt = event?.universe_snapshot_known_at
    ? ` · known ${formatShortDateTime(event.universe_snapshot_known_at)}`
    : ''
  return `${status} · ETF snapshot ${compositionDate}${knownAt}`
}

function executionLogColumnSearchValues(event: any, key: ExecutionLogColumnKey) {
  switch (key) {
    case 'time':
      return executionLogTimeSearchValues(event.ts)
    case 'event':
      return [event.event_type, humanizeToken(event.event_type)]
    case 'symbol':
      return [event.symbol]
    case 'side':
      return [event.side, humanizeToken(event.side)]
    case 'price':
      return [event.price, event.price != null ? formatMoney(event.price) : null]
    case 'size':
      return [event.quantity, event.quantity != null ? Number(event.quantity).toFixed(2) : null]
    case 'pnl':
      return [
        event.pnl,
        event.pnl_pct,
        event.pnl != null ? formatSignedMoney(event.pnl) : null,
        event.pnl_pct != null ? formatSignedPercent(event.pnl_pct) : null,
      ]
    case 'reason':
      return [
        event.reason,
        humanizeToken(event.reason || event.event_type),
        executionUniverseContext(event),
        event.universe_membership_status,
        event.universe_snapshot_composition_date,
        event.universe_snapshot_known_at,
        event.universe_profile_id,
      ]
    default:
      return []
  }
}

function executionLogTimeSearchValues(value: string | null | undefined) {
  if (!value) return []
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return [value]
  const localShort = formatShortDateTime(value)
  const localLong = formatDateTime(value)
  const utcDay = String(date.getUTCDate()).padStart(2, '0')
  const utcMonth = String(date.getUTCMonth() + 1).padStart(2, '0')
  const utcYear = String(date.getUTCFullYear())
  const utcHours = String(date.getUTCHours()).padStart(2, '0')
  const utcMinutes = String(date.getUTCMinutes()).padStart(2, '0')
  return [
    value,
    localShort,
    localLong,
    `${utcDay}/${utcMonth}`,
    `${utcDay}/${utcMonth}/${utcYear}`,
    `${utcHours}:${utcMinutes}`,
    `${utcDay}/${utcMonth}, ${utcHours}:${utcMinutes}`,
    `${utcDay}/${utcMonth}/${utcYear}, ${utcHours}:${utcMinutes}`,
  ]
}

function looseExecutionLogSearchValue(value: string) {
  return value.replace(/[^a-z0-9]/gi, '')
}

function executionLogSortValue(event: any, key: ExecutionLogColumnKey) {
  switch (key) {
    case 'time': {
      const timestamp = new Date(String(event.ts ?? '')).getTime()
      return Number.isNaN(timestamp) ? 0 : timestamp
    }
    case 'event':
      return eventSortOrder(event.event_type)
    case 'symbol':
      return String(event.symbol ?? '')
    case 'side':
      return String(event.side ?? '')
    case 'price':
      return Number(event.price ?? Number.NEGATIVE_INFINITY)
    case 'size':
      return Number(event.quantity ?? Number.NEGATIVE_INFINITY)
    case 'pnl':
      return Number(event.pnl_pct ?? event.pnl ?? Number.NEGATIVE_INFINITY)
    case 'reason':
      return humanizeToken(event.reason || event.event_type)
    default:
      return ''
  }
}

function compareExecutionLogRows(left: any, right: any) {
  const leftValue = executionLogSortValue(left, executionLogSort.key)
  const rightValue = executionLogSortValue(right, executionLogSort.key)
  let compare = 0
  if (typeof leftValue === 'number' && typeof rightValue === 'number') {
    compare = leftValue - rightValue
  } else {
    compare = String(leftValue).localeCompare(String(rightValue), undefined, {
      numeric: true,
      sensitivity: 'base',
    })
  }
  if (compare === 0) {
    const tsCompare = String(left.ts ?? '').localeCompare(String(right.ts ?? ''))
    if (tsCompare !== 0) compare = tsCompare
    else compare = String(left.symbol ?? '').localeCompare(String(right.symbol ?? ''))
  }
  return executionLogSort.direction === 'asc' ? compare : -compare
}

const executionLog = computed<any[]>(() => {
  const rows = Array.isArray(selectedRunDetail.value?.result_summary?.execution_log)
    ? selectedRunDetail.value?.result_summary?.execution_log
    : []
  const openPositions = Array.isArray(selectedRunDetail.value?.result_summary?.open_positions)
    ? selectedRunDetail.value?.result_summary?.open_positions
    : []
  const normalized = [...rows]
  const seenKeys = new Set(
    normalized.map(event =>
      [
        String(event.position_id ?? ''),
        String(event.event_type ?? ''),
        String(event.ts ?? ''),
      ].join('::'),
    ),
  )

  for (const position of openPositions) {
    const positionId = `${String(position.instrument_symbol ?? '')}-${String(position.entry_at ?? '')}`
    const entryKey = [positionId, 'entry', String(position.entry_at ?? '')].join('::')
    if (!seenKeys.has(entryKey)) {
      normalized.push({
        ts: position.entry_at,
        event_type: 'entry',
        position_id: positionId,
        symbol: position.instrument_symbol,
        side: position.side,
        quantity: position.quantity,
        price: position.entry_price,
        pnl: null,
        pnl_pct: null,
        r_multiple: null,
        reason: 'entry_signal',
      })
      seenKeys.add(entryKey)
    }

    const markKey = [positionId, 'open_at_end', String(position.current_at ?? '')].join('::')
    if (!seenKeys.has(markKey)) {
      normalized.push({
        ts: position.current_at,
        event_type: 'open_at_end',
        position_id: positionId,
        symbol: position.instrument_symbol,
        side: position.side,
        quantity: position.quantity,
        price: position.current_price,
        pnl: position.unrealized_pnl,
        pnl_pct: position.unrealized_pnl_pct,
        r_multiple: position.r_multiple,
        reason: 'run_end_mark',
      })
      seenKeys.add(markKey)
    }
  }

  return normalized.sort((left, right) => {
    const tsCompare = String(left.ts ?? '').localeCompare(String(right.ts ?? ''))
    if (tsCompare !== 0) return tsCompare
    const typeCompare = eventSortOrder(left.event_type) - eventSortOrder(right.event_type)
    if (typeCompare !== 0) return typeCompare
    return String(left.symbol ?? '').localeCompare(String(right.symbol ?? ''))
  })
})

const filteredExecutionLog = computed<any[]>(() => {
  const filteredRows = executionLog.value.filter(event =>
    executionLogColumns.every(column => executionLogFilterMatches(event, column.key)),
  )
  return filteredRows.sort((left, right) => compareExecutionLogRows(left, right))
})

const benchmarkCurve = computed<any[]>(() =>
  Array.isArray(selectedRunDetail.value?.result_summary?.benchmark?.equity_curve)
    ? selectedRunDetail.value?.result_summary?.benchmark?.equity_curve
    : []
)

const drawdownCurve = computed<any[]>(() =>
  Array.isArray(selectedRunDetail.value?.result_summary?.analytics?.drawdown_curve)
    ? selectedRunDetail.value?.result_summary?.analytics?.drawdown_curve
    : []
)

const monthlyReturns = computed<any[]>(() =>
  Array.isArray(selectedRunDetail.value?.result_summary?.analytics?.monthly_returns)
    ? selectedRunDetail.value?.result_summary?.analytics?.monthly_returns
    : []
)

const quarterlyReturns = computed<any[]>(() =>
  Array.isArray(selectedRunDetail.value?.result_summary?.analytics?.quarterly_returns)
    ? selectedRunDetail.value?.result_summary?.analytics?.quarterly_returns
    : []
)

const yearlyReturns = computed<any[]>(() => {
  const source = monthlyReturns.value.length ? monthlyReturns.value : quarterlyReturns.value
  if (!source.length) return []
  const grouped = new Map<string, number[]>()
  const allYears = new Set<string>()
  for (const row of source) {
    const period = String(row?.period ?? '')
    const year = period.slice(0, 4)
    if (!/^\d{4}$/.test(year)) continue
    allYears.add(year)
    const rawValue = row?.return_pct
    if (rawValue == null || !Number.isFinite(Number(rawValue))) continue
    if (!grouped.has(year)) grouped.set(year, [])
    grouped.get(year)!.push(Number(rawValue))
  }
  return Array.from(allYears)
    .sort()
    .map(year => {
      const values = grouped.get(year) ?? []
      if (!values.length) return { period: year, return_pct: null }
      const compounded = values.reduce((acc, value) => acc * (1 + (value / 100)), 1)
      return {
        period: year,
        return_pct: Number((((compounded - 1) * 100)).toFixed(4)),
      }
    })
})

function returnsPeriodKey(ts: string | null | undefined, mode: 'monthly' | 'quarterly' | 'yearly') {
  const value = String(ts ?? '')
  const year = value.slice(0, 4)
  const monthValue = Number(value.slice(5, 7))
  if (!/^\d{4}$/.test(year)) return null
  if (mode === 'yearly') return year
  if (!Number.isFinite(monthValue) || monthValue < 1 || monthValue > 12) return null
  if (mode === 'monthly') return `${year}-${String(monthValue).padStart(2, '0')}`
  return `${year}-Q${Math.floor((monthValue - 1) / 3) + 1}`
}

const availableReturnsModes = computed<Array<'monthly' | 'quarterly' | 'yearly'>>(() => {
  const modes: Array<'monthly' | 'quarterly' | 'yearly'> = []
  if (monthlyReturns.value.length) modes.push('monthly')
  if (quarterlyReturns.value.length) modes.push('quarterly')
  if (yearlyReturns.value.length) modes.push('yearly')
  return modes
})

function buildReturnsDetailMap(mode: 'monthly' | 'quarterly' | 'yearly') {
  const grouped: Record<string, any[]> = {}
  for (const event of executionLog.value) {
    if (!['exit', 'open_at_end'].includes(String(event?.event_type ?? ''))) continue
    const period = returnsPeriodKey(event?.ts, mode)
    if (!period) continue
    if (!grouped[period]) grouped[period] = []
    grouped[period].push(event)
  }

  for (const events of Object.values(grouped)) {
    events.sort((left, right) => String(left.ts ?? '').localeCompare(String(right.ts ?? '')))
  }
  return grouped
}

const symbolPerformance = computed<any[]>(() =>
  Array.isArray(selectedRunDetail.value?.result_summary?.symbol_performance)
    ? selectedRunDetail.value?.result_summary?.symbol_performance
    : []
)

const optimizationRows = computed<any[]>(() =>
  Array.isArray(selectedRunDetail.value?.result_summary?.optimization?.leaderboard)
    ? selectedRunDetail.value?.result_summary?.optimization?.leaderboard
    : []
)

const walkForwardSegments = computed<any[]>(() =>
  Array.isArray(selectedRunDetail.value?.result_summary?.walk_forward?.segments)
    ? selectedRunDetail.value?.result_summary?.walk_forward?.segments
    : []
)

const tradeDistributions = computed<Record<string, any>>(() =>
  selectedRunDetail.value?.result_summary?.analytics?.trade_distributions ?? {}
)
const positionTimelines = computed<any[]>(() =>
  Array.isArray(selectedRunDetail.value?.result_summary?.position_timelines)
    ? selectedRunDetail.value?.result_summary?.position_timelines
    : []
)
const portfolioTimeline = computed<any[]>(() =>
  Array.isArray(selectedRunDetail.value?.result_summary?.portfolio_timeline)
    ? selectedRunDetail.value?.result_summary?.portfolio_timeline
    : []
)

const currentRunComparisonLabel = computed(() =>
  selectedRunDetail.value ? `${formatShortDateTime(selectedRunDetail.value.created_at)} · ${humanizeToken(selectedRunDetail.value.test_mode)}` : 'Current run',
)

const compareRunComparisonLabel = computed(() =>
  compareRun.value ? `${formatShortDateTime(compareRun.value.created_at)} · ${humanizeToken(compareRun.value.test_mode)}` : 'Comparison run',
)

const comparisonRows = computed(() => {
  if (!selectedRunDetail.value || !compareRun.value) return []
  return [
    comparisonMetric('Marked return', selectedRunDetail.value.result_summary?.performance?.net_return_pct, compareRun.value.result_summary?.performance?.net_return_pct, 'percent', 'higher'),
    comparisonMetric('Realized return', selectedRunDetail.value.result_summary?.performance?.realized_net_return_pct, compareRun.value.result_summary?.performance?.realized_net_return_pct, 'percent', 'higher'),
    comparisonMetric('Unrealized return', selectedRunDetail.value.result_summary?.performance?.unrealized_return_pct, compareRun.value.result_summary?.performance?.unrealized_return_pct, 'percent', 'higher'),
    comparisonMetric('Win rate', selectedRunDetail.value.result_summary?.performance?.win_rate, compareRun.value.result_summary?.performance?.win_rate, 'percent', 'higher'),
    comparisonMetric('Expectancy', selectedRunDetail.value.result_summary?.performance?.expectancy_r, compareRun.value.result_summary?.performance?.expectancy_r, 'r', 'higher'),
    comparisonMetric('Drawdown', selectedRunDetail.value.result_summary?.performance?.max_drawdown_pct, compareRun.value.result_summary?.performance?.max_drawdown_pct, 'percent', 'lower'),
    comparisonMetric('Trade count', selectedRunDetail.value.result_summary?.performance?.trade_count, compareRun.value.result_summary?.performance?.trade_count, 'count', 'higher'),
    comparisonMetric('Unrealized P&L', selectedRunDetail.value.result_summary?.performance?.unrealized_pnl, compareRun.value.result_summary?.performance?.unrealized_pnl, 'money', 'higher'),
    comparisonMetric('Profit factor', selectedRunDetail.value.result_summary?.performance?.profit_factor, compareRun.value.result_summary?.performance?.profit_factor, 'plain', 'higher'),
  ]
})

const performanceChartSeries = computed(() => {
  const strategyCurve = Array.isArray(selectedRunDetail.value?.result_summary?.equity_curve)
    ? selectedRunDetail.value?.result_summary?.equity_curve
    : []
  const benchmarkSeries = benchmarkCurve.value

  const series = [
    buildNormalizedChartSeries(strategyCurve, 'Strategy', '#64b5f6', 'equity'),
    buildNormalizedChartSeries(
      benchmarkSeries,
      selectedRunDetail.value?.result_summary?.benchmark?.symbol || 'Benchmark',
      '#e0b35b',
      'equity',
    ),
  ]

  return series.filter((item): item is NonNullable<typeof item> => item != null)
})

const drawdownChartSeries = computed(() => {
  const strategySeries = buildRawChartSeries(
    negateSeriesValues(drawdownCurve.value, 'drawdown_pct'),
    'Strategy',
    '#ef7f88',
    'drawdown_pct',
  )
  const benchmarkDrawdownRows = Array.isArray(selectedRunDetail.value?.result_summary?.benchmark?.drawdown_curve)
    ? selectedRunDetail.value?.result_summary?.benchmark?.drawdown_curve
    : deriveDrawdownCurve(benchmarkCurve.value, 'equity')
  const benchmarkSeries = buildRawChartSeries(
    negateSeriesValues(benchmarkDrawdownRows, 'drawdown_pct'),
    selectedRunDetail.value?.result_summary?.benchmark?.symbol || 'Benchmark',
    '#e0b35b',
    'drawdown_pct',
  )
  return [strategySeries, benchmarkSeries].filter((item): item is NonNullable<typeof item> => item != null)
})

const drawdownPanelLabel = computed(() => (
  selectedRunDetail.value?.result_summary?.benchmark?.symbol
    ? `Strategy vs ${selectedRunDetail.value.result_summary.benchmark.symbol}`
    : 'Peak-to-trough'
))

const strategyReturnLabel = computed(() => {
  const strategyCurve = Array.isArray(selectedRunDetail.value?.result_summary?.equity_curve)
    ? selectedRunDetail.value?.result_summary?.equity_curve
    : []
  return formatSeriesReturn(strategyCurve, 'equity')
})

const benchmarkReturnValue = computed(() =>
  seriesReturnValue(benchmarkCurve.value, 'equity')
)
const benchmarkReturnLabel = computed(() => formatSeriesReturn(benchmarkCurve.value, 'equity'))
const benchmarkMaxDrawdownLabel = computed(() =>
  formatPercent(selectedRunDetail.value?.result_summary?.benchmark?.performance?.max_drawdown_pct),
)
const benchmarkHoldSpanLabel = computed(() => {
  const coverage = selectedRunCoverageDetail.value?.benchmark
  const first = String(coverage?.available_from ?? '')
  const last = String(coverage?.available_to ?? '')
  if (!first || !last) return '—'
  return `${formatShortDateTime(first)} → ${formatShortDateTime(last)}`
})
const benchmarkCoverageNote = computed(() => {
  const benchmark = selectedRunCoverageDetail.value?.benchmark
  if (!benchmark) return ''
  const note = String(benchmark.preview_note ?? '').trim()
  const firstRequested = String(benchmark.requested_first_bar_at ?? '')
  const requestedStart = String(selectedRunCoverageDetail.value?.requested_date_from ?? '')
  if (firstRequested && requestedStart) {
    const firstRequestedAt = new Date(firstRequested).getTime()
    const requestedStartAt = new Date(requestedStart).getTime()
    if (
      Number.isFinite(firstRequestedAt)
      && Number.isFinite(requestedStartAt)
      && firstRequestedAt > requestedStartAt
    ) {
      const suffix = note || 'Earlier benchmark bars are unavailable for this run.'
      return `Benchmark coverage starts on ${formatFullCoverageDateTime(firstRequested)}. ${suffix}`
    }
  }
  if (note) return note
  if (benchmark.requested_status === 'none') return 'No benchmark bars were found inside the selected run window.'
  if (benchmark.requested_status === 'missing') return 'No benchmark history is stored locally for this timeframe.'
  return ''
})
const runSubsetSummary = computed(() => {
  if (!runDraft.use_subset) return 'Use full universe'
  if (!runDraft.overrideSymbols.length) return 'Select at least one symbol'
  if (runDraft.overrideSymbols.length === 1) return runDraft.overrideSymbols[0]
  return `${runDraft.overrideSymbols.length} selected`
})
const showRunSubsetValidation = computed(() =>
  runDraft.use_subset && runDraft.overrideSymbols.length === 0
)
const positionEvolutionMode = ref<'currency' | 'percent'>('currency')
const returnsViewMode = ref<'monthly' | 'quarterly' | 'yearly'>('monthly')
const activeReturnsMode = computed<'monthly' | 'quarterly' | 'yearly'>(() => (
  availableReturnsModes.value.includes(returnsViewMode.value)
    ? returnsViewMode.value
    : (availableReturnsModes.value[0] ?? 'monthly')
))
const activeReturnsRows = computed<any[]>(() => {
  const rows = activeReturnsMode.value === 'quarterly'
    ? quarterlyReturns.value
    : activeReturnsMode.value === 'yearly'
      ? yearlyReturns.value
      : monthlyReturns.value
  return buildRealizedReturnRows(rows, activeReturnsMode.value)
})

const activeReturnsDetails = computed<Record<string, any[]>>(() => (
  buildReturnsDetailMap(activeReturnsMode.value)
))
const activeReturnsEmptyLabel = computed(() => {
  if (activeReturnsMode.value === 'quarterly') return 'No quarterly return breakdown yet.'
  if (activeReturnsMode.value === 'yearly') return 'No yearly return breakdown yet.'
  return 'No monthly return breakdown yet.'
})

function buildRealizedReturnRows(rows: any[], mode: 'monthly' | 'quarterly' | 'yearly') {
  const denominator = Number(performance.value.initial_capital)
  const canUsePortfolioBase = Number.isFinite(denominator) && denominator > 0
  const realizedByPeriod = new Map<string, number>()
  const fallbackPctByPeriod = new Map<string, number>()

  for (const event of executionLog.value) {
    if (String(event?.event_type ?? '') !== 'exit') continue
    const period = returnsPeriodKey(event?.ts, mode)
    if (!period) continue
    realizedByPeriod.set(period, (realizedByPeriod.get(period) ?? 0) + (Number(event.pnl) || 0))
    fallbackPctByPeriod.set(period, (fallbackPctByPeriod.get(period) ?? 0) + (Number(event.pnl_pct) || 0))
  }

  return rows.map(row => {
    const period = String(row?.period ?? '')
    if (row?.return_pct == null) return { ...row, return_pct: null }
    const realizedPnl = realizedByPeriod.get(period) ?? 0
    const fallbackPct = fallbackPctByPeriod.get(period) ?? 0
    return {
      ...row,
      return_pct: canUsePortfolioBase
        ? Number(((realizedPnl / denominator) * 100).toFixed(4))
        : Number(fallbackPct.toFixed(4)),
    }
  })
}
const positionEvolutionSeries = computed(() =>
  positionTimelines.value.map((timeline, index) => ({
    label: String(timeline.label || `${timeline.symbol || 'Position'} #${index + 1}`),
    color: seriesColorForKey(String(timeline.position_id || timeline.label || `${timeline.symbol || 'position'}-${index}`)),
    points: Array.isArray(timeline.points)
      ? timeline.points
          .map((point: any) => ({
            ts: String(point.ts ?? ''),
            value: positionEvolutionPointValue(timeline, Number(point.value)),
            detail: point.detail ? String(point.detail) : null,
            marker: point.marker ? String(point.marker) : null,
          }))
          .filter((point: any) => point.ts && Number.isFinite(point.value))
      : [],
  })).filter(series => series.points.length >= 2)
)
const portfolioCapitalSeries = computed(() => {
  const deployed = buildRawChartSeries(
    portfolioTimeline.value,
    'Deployed capital',
    '#7ec2ff',
    'deployed_capital',
  )
  const idle = buildRawChartSeries(
    portfolioTimeline.value,
    'Idle capital',
    '#7fd38c',
    'idle_capital',
  )
  return [deployed, idle].filter((series): series is NonNullable<typeof series> => series != null)
})
const portfolioPositionsSeries = computed(() => {
  const openPositions = buildRawChartSeries(
    portfolioTimeline.value,
    'Open positions',
    '#e0b35b',
    'open_position_count',
  )
  return openPositions ? [openPositions] : []
})

const positionSizingValueLabel = computed(() => {
  if (logicDraft.position_sizing_mode === 'fixed_cash') return 'Cash per position'
  if (logicDraft.position_sizing_mode === 'percent_capital') return 'Capital per position %'
  if (logicDraft.position_sizing_mode === 'fixed_quantity') return 'Quantity per entry'
  return 'Sizing value'
})

const positionSizingValueHelp = computed(() => {
  if (logicDraft.position_sizing_mode === 'fixed_cash') {
    return 'Allocate this much capital to each new position, regardless of stop distance.'
  }
  if (logicDraft.position_sizing_mode === 'percent_capital') {
    return 'Allocate this percent of the current capital base to each new position.'
  }
  if (logicDraft.position_sizing_mode === 'fixed_quantity') {
    return 'Use this fixed quantity for every new entry.'
  }
  return 'Sizing value for the selected model.'
})

const commissionValueLabel = computed(() => {
  if (runDraft.commission_model === 'percent_of_notional') return 'Commission %'
  if (runDraft.commission_model === 'fixed_per_order') return 'Commission per order'
  return 'Commission per round-trip'
})

const commissionValueHelp = computed(() => {
  if (runDraft.commission_model === 'percent_of_notional') {
    return 'Percent commission applied to each entry and exit order notional. Example: 0.1 means 0.10% of the order value.'
  }
  if (runDraft.commission_model === 'fixed_per_order') {
    return 'Flat commission charged on each entry and exit order, regardless of position size.'
  }
  return 'Flat commission charged once for the whole trade lifecycle. This preserves the older Strategy Lab flat-fee behavior.'
})

const commissionValueMin = computed(() => 0)
const commissionValueStep = computed(() =>
  runDraft.commission_model === 'percent_of_notional' ? 0.01 : 0.1,
)

const positionSizingValueStep = computed(() =>
  logicDraft.position_sizing_mode === 'fixed_quantity' ? 1 : 0.1,
)

const positionSizingValueMin = computed(() =>
  logicDraft.position_sizing_mode === 'fixed_quantity' ? 1 : 0,
)

function splitSweepTokens(value: unknown) {
  if (value === '' || value == null) return []
  return String(value)
    .split(',')
    .map(part => part.trim())
    .filter(Boolean)
}

function expandNumberToken(token: string) {
  const rangeMatch = token.match(/^(-?\d+(?:\.\d+)?)\s*\.\.\s*(-?\d+(?:\.\d+)?)(?::\s*(-?\d+(?:\.\d+)?))?$/)
  if (!rangeMatch) {
    const numeric = Number(token)
    return Number.isFinite(numeric) ? [numeric] : []
  }

  const start = Number(rangeMatch[1])
  const end = Number(rangeMatch[2])
  const requestedStep = rangeMatch[3] == null ? 1 : Math.abs(Number(rangeMatch[3]))
  if (!Number.isFinite(start) || !Number.isFinite(end) || !Number.isFinite(requestedStep) || requestedStep === 0) return []

  const direction = start <= end ? 1 : -1
  const step = requestedStep * direction
  const values: number[] = []
  for (let current = start; direction > 0 ? current <= end + 1e-9 : current >= end - 1e-9; current += step) {
    values.push(Number(current.toFixed(8)))
    if (values.length > 500) break
  }
  return values
}

function parseNumberList(raw: unknown) {
  const values = splitSweepTokens(raw).flatMap(expandNumberToken)
  return Array.from(new Set(values.filter(value => Number.isFinite(value))))
}

function optionalNumberValue(value: unknown): number | null {
  const [numeric] = parseNumberList(value)
  return Number.isFinite(numeric) ? numeric : null
}

function optionalNumberOrZero(value: unknown): number {
  return optionalNumberValue(value) ?? 0
}

function optionalIntegerOrZero(value: unknown): number {
  return Math.max(0, Math.round(optionalNumberOrZero(value)))
}

function optionalDisabledInput(value: unknown): OptionalNumberInput {
  const numeric = optionalNumberValue(value)
  return numeric == null || numeric === 0 ? '' : numeric
}

function optionalDisabledInputWithDefault(value: unknown, fallback: number): OptionalNumberInput {
  return value === undefined ? fallback : optionalDisabledInput(value)
}

function setSweepSingle(target: SweepValueDraft, value: OptionalNumberInput, step: number) {
  target.mode = 'single'
  target.single = value
  target.list = []
  target.range = {
    start: value,
    end: value,
    step,
  }
}

function normalizedSweepNumber(value: unknown, options: { integer?: boolean; min?: number } = {}) {
  const numeric = optionalNumberValue(value)
  if (numeric == null) return null
  const normalized = options.integer === true ? Math.round(numeric) : numeric
  if (options.min != null && normalized < options.min) return null
  return Number(normalized.toFixed(8))
}

function serializeSweepValue(target: SweepValueDraft, options: { integer?: boolean; min?: number } = {}) {
  return {
    mode: target.mode,
    single: normalizedSweepNumber(target.single, options),
    list: target.list
      .map(value => normalizedSweepNumber(value, options))
      .filter((value): value is number => value != null),
    range: {
      start: normalizedSweepNumber(target.range.start, options),
      end: normalizedSweepNumber(target.range.end, options),
      step: normalizedSweepNumber(target.range.step, { integer: options.integer, min: 0 }),
    },
  }
}

function serializeParameterSweeps() {
  return {
    stop_loss_pct: serializeSweepValue(sweepDraft.stop_loss_pct, { min: 0.1 }),
    take_profit_rr: serializeSweepValue(sweepDraft.take_profit_rr, { min: 0 }),
    max_bars_in_trade: serializeSweepValue(sweepDraft.max_bars_in_trade, { integer: true, min: 1 }),
  }
}

function normalizeSweepMode(value: unknown): SweepMode {
  return value === 'list' || value === 'range' ? value : 'single'
}

function applySweepSnapshot(
  target: SweepValueDraft,
  raw: unknown,
  fallback: OptionalNumberInput,
  step: number,
  options: { integer?: boolean; min?: number } = {},
) {
  setSweepSingle(target, fallback, step)
  if (!raw || typeof raw !== 'object') return

  const snapshot = raw as Partial<SweepValueDraft>
  const mode = normalizeSweepMode(snapshot.mode)
  target.mode = mode
  target.single = normalizedSweepNumber(snapshot.single, options) ?? fallback
  target.list = Array.isArray(snapshot.list)
    ? snapshot.list
        .map(value => normalizedSweepNumber(value, options))
        .filter((value): value is number => value != null)
    : []
  target.range = {
    start: normalizedSweepNumber(snapshot.range?.start, options) ?? target.single,
    end: normalizedSweepNumber(snapshot.range?.end, options) ?? target.single,
    step: normalizedSweepNumber(snapshot.range?.step, { integer: options.integer, min: 0 }) ?? step,
  }
}

function hydrateParameterSweeps(raw: unknown) {
  if (!raw || typeof raw !== 'object') return
  const sweeps = raw as Record<string, unknown>
  applySweepSnapshot(sweepDraft.stop_loss_pct, sweeps.stop_loss_pct, sweepDraft.stop_loss_pct.single, 0.1, { min: 0.1 })
  applySweepSnapshot(sweepDraft.take_profit_rr, sweeps.take_profit_rr, sweepDraft.take_profit_rr.single, 0.25, { min: 0 })
  applySweepSnapshot(sweepDraft.max_bars_in_trade, sweeps.max_bars_in_trade, sweepDraft.max_bars_in_trade.single, 1, { integer: true, min: 1 })
}

function nextSweepMode(mode: SweepMode): SweepMode {
  if (mode === 'single') return 'list'
  if (mode === 'list') return 'range'
  return 'single'
}

function sweepModeLabel(mode: SweepMode) {
  if (mode === 'single') return 'Single value'
  if (mode === 'list') return 'Fixed list'
  return 'Value range'
}

function sweepModeAriaLabel(target: SweepValueDraft) {
  return `${sweepModeLabel(target.mode)} parameter mode. Click to switch to ${sweepModeLabel(nextSweepMode(target.mode))}.`
}

function sweepModeTooltip(target: SweepValueDraft) {
  return `${sweepModeLabel(target.mode)} mode. Click to switch to ${sweepModeLabel(nextSweepMode(target.mode))}. Multiple values generate a run batch automatically.`
}

function cycleSweepMode(
  target: SweepValueDraft,
  options: { integer?: boolean; min?: number; step?: number } = {},
) {
  const mode = nextSweepMode(target.mode)
  const single = optionalNumberValue(target.single)
  const min = options.min ?? Number.NEGATIVE_INFINITY
  const step = options.step ?? 1
  target.mode = mode
  if (mode === 'list' && !target.list.length && single != null && single >= min) {
    target.list = [options.integer === true ? Math.round(single) : single]
  }
  if (mode === 'range') {
    const fallback = single != null && single >= min ? single : (Number.isFinite(min) ? min : '')
    target.range = {
      start: optionalNumberValue(target.range.start) ?? fallback,
      end: optionalNumberValue(target.range.end) ?? fallback,
      step: optionalNumberValue(target.range.step) ?? step,
    }
  }
}

function rangeValuesFromSweep(
  target: SweepValueDraft,
  options: { integer?: boolean; min?: number; step?: number } = {},
) {
  const integer = options.integer === true
  const min = options.min ?? Number.NEGATIVE_INFINITY
  const step = options.step ?? 1
  const start = optionalNumberValue(target.range.start)
  const end = optionalNumberValue(target.range.end)
  const requestedStep = Math.abs(optionalNumberValue(target.range.step) ?? step)
  if (start == null || end == null || requestedStep <= 0) return []

  const direction = start <= end ? 1 : -1
  const normalizedStep = requestedStep * direction
  const values: number[] = []
  for (
    let current = start;
    direction > 0 ? current <= end + 1e-9 : current >= end - 1e-9;
    current += normalizedStep
  ) {
    const value = integer ? Math.round(current) : Number(current.toFixed(8))
    if (value >= min) values.push(value)
    if (values.length > 500) break
  }
  return Array.from(new Set(values))
}

function valuesFromSweep(target: SweepValueDraft, options: { integer?: boolean; min?: number; step?: number } = {}) {
  const integer = options.integer === true
  const min = options.min ?? Number.NEGATIVE_INFINITY
  const step = options.step ?? 1
  if (target.mode === 'list') {
    return Array.from(new Set(
      target.list
        .map(value => (integer ? Math.round(value) : value))
        .filter(value => Number.isFinite(value) && value >= min),
    ))
  }
  if (target.mode === 'range') {
    return rangeValuesFromSweep(target, { integer, min, step })
  }
  const value = optionalNumberValue(target.single)
  if (value == null || value < min) return []
  return [integer ? Math.round(value) : value]
}

function primarySweepValue(target: SweepValueDraft, options: { integer?: boolean; min?: number; step?: number } = {}) {
  return valuesFromSweep(target, options)[0] ?? null
}

const strategyNarrative = computed(() => {
  if (sourceType.value === 'radar') {
    const setupText = radarDraft.setup_types.length
      ? radarDraft.setup_types.map(humanizeToken).join(', ')
      : 'all setup families'
    const stateText = radarDraft.states.length
      ? radarDraft.states.map(humanizeToken).join(', ')
      : 'all lifecycle states'
    return `Replay ${setupText} Radar signals on ${logicDraft.timeframe}, filtering to ${stateText} and score ${radarDraft.min_score.toFixed(2)} or higher, then evaluate them with the current risk and exit model.`
  }
  const conditionText = describeRuleNode(logicDraft.ruleTree)
  const exitText = describeRuleNode(logicDraft.exitRuleTree)
  const stopText = logicDraft.stop_model === 'atr'
    ? `${logicDraft.stop_atr_multiple} ATR stop (${logicDraft.stop_atr_period})`
    : `${primarySweepValue(sweepDraft.stop_loss_pct, { min: 0.1, step: 0.1 }) ?? 2}% stop`
  const sizingText = logicDraft.position_sizing_mode === 'percent_risk'
    ? `${runDraft.risk_per_trade_pct}% risk-per-trade sizing`
    : logicDraft.position_sizing_mode === 'fixed_cash'
      ? `${formatMoney(logicDraft.position_sizing_value)} fixed cash sizing`
      : logicDraft.position_sizing_mode === 'percent_capital'
        ? `${logicDraft.position_sizing_value}% capital sizing`
        : `${logicDraft.position_sizing_value.toFixed(0)} fixed quantity sizing`
  const takeProfitR = primarySweepValue(sweepDraft.take_profit_rr, { min: 0, step: 0.25 }) ?? 0
  const maxBarsInTrade = primarySweepValue(sweepDraft.max_bars_in_trade, { integer: true, min: 1, step: 1 }) ?? 0
  const hardTrailingStopPct = optionalNumberOrZero(logicDraft.hard_trailing_stop_pct)
  const breakEvenR = optionalNumberOrZero(logicDraft.break_even_rr)
  const trailingStopR = optionalNumberOrZero(logicDraft.trailing_stop_rr)
  const fixedTargetText = takeProfitR > 0 ? `${takeProfitR}R fixed target` : 'no fixed profit target'
  const timeExitText = maxBarsInTrade > 0 ? `${maxBarsInTrade}-bar time exit` : 'no time exit'
  const hardTrailText = hardTrailingStopPct > 0
    ? `, a hard ${hardTrailingStopPct}% trail${logicDraft.hard_trailing_activation_pct > 0 ? ` after a ${logicDraft.hard_trailing_activation_pct}% gain` : ''}`
    : ''
  const breakEvenText = breakEvenR > 0 ? `break-even after ${breakEvenR}R` : 'no break-even move'
  const trailingText = trailingStopR > 0 ? `a ${trailingStopR}R trailing stop` : 'no R-based trailing stop'
  return `Go ${logicDraft.direction} on ${logicDraft.timeframe} when ${conditionText || 'conditions are satisfied'}, using ${stopText} and ${sizingText}, with ${breakEvenText}, ${trailingText}${hardTrailText}, then exit via ${fixedTargetText}, ${timeExitText}${exitText ? `, or when ${exitText}` : ''}.`
})

const hasUniverseSelection = computed(() =>
  (sourceType.value === 'radar' && universeMode.value === 'radar')
  || (universeMode.value === 'symbols' && logicDraft.symbols.length > 0)
  || (universeMode.value === 'watchlist' && selectedWatchlistId.value != null)
  || (universeMode.value === 'screener' && selectedScreenerId.value != null)
  || (universeMode.value === 'basket' && selectedBasketId.value != null)
  || (universeMode.value === 'etf_holdings' && Boolean(selectedEtfHoldingSymbol.value)),
)

const hasEntryLogic = computed(() =>
  sourceType.value === 'radar' || conditionCount.value > 0
)

const canPublish = computed(() =>
  Boolean(draft.name.trim())
  && hasUniverseSelection.value
  && (isNew.value || hasEntryLogic.value)
)
const showNameValidation = computed(() => !draft.name.trim())
const showUniverseValidation = computed(() =>
  !(sourceType.value === 'radar' && universeMode.value === 'radar')
  && !hasUniverseSelection.value,
)

onMounted(async () => {
  await Promise.all([
    strategyLab.loadAll(),
    api.get<Watchlist[]>('/watchlists').then(rows => {
      availableWatchlists.value = rows
    }).catch(() => {
      availableWatchlists.value = []
    }),
    api.get<ScreenerOption[]>('/screeners').then(rows => {
      availableScreeners.value = rows.map(row => ({ id: row.id, name: row.name }))
    }).catch(() => {
      availableScreeners.value = []
    }),
    api.get<Basket[]>('/baskets').then(rows => {
      availableBaskets.value = rows
    }).catch(() => {
      availableBaskets.value = []
    }),
    api.get<ETFProfile[]>('/etf-holdings').then(rows => {
      availableEtfHoldings.value = rows
    }).catch(() => {
      availableEtfHoldings.value = []
    }),
  ])
  hydrateFromSelection(strategyLab.selectedDefinition)
})

function handleDocumentPointerDown(event: Event) {
  const target = event.target
  if (!(target instanceof Node)) return
  if (exportMenuRef.value?.contains(target)) return
  exportMenuOpen.value = false
  openExecutionLogFilter.value = null
}

onMounted(() => {
  document.addEventListener('pointerdown', handleDocumentPointerDown)
})

onBeforeUnmount(() => {
  document.removeEventListener('pointerdown', handleDocumentPointerDown)
})

watch([sidebarWidth, sidebarCollapsed], ([width, collapsed]) => {
  persistStrategySidebarState({ width, collapsed })
})

watch(sectionExpanded, value => {
  persistStrategySectionState(currentSectionStateStorageKey(), value)
}, { deep: true })

watch(coveragePreviewSignature, () => {
  scheduleCoveragePreview()
}, { immediate: true })

watch(() => strategyLab.selectedDefinition, value => {
  hydrateFromSelection(value)
  exportMenuOpen.value = false
})

function scheduleCoveragePreview() {
  void fetchCoveragePreview()
}

async function fetchCoveragePreview() {
  const requestId = ++coveragePreviewSequence
  coveragePreviewLoading.value = true
  coveragePreviewError.value = null
  try {
    const preview = await api.post<StrategyCoveragePreview>(
      '/strategy-lab/coverage-preview',
      coveragePreviewPayload.value,
    )
    if (requestId !== coveragePreviewSequence) return
    coveragePreview.value = preview
  } catch (err: any) {
    if (requestId !== coveragePreviewSequence) return
    coveragePreview.value = null
    coveragePreviewError.value = err?.message ?? 'Failed to refresh coverage preview'
  } finally {
    if (requestId === coveragePreviewSequence) {
      coveragePreviewLoading.value = false
    }
  }
}

watch(universeMode, mode => {
  if (mode !== 'watchlist') selectedWatchlistId.value = null
  if (mode !== 'screener') selectedScreenerId.value = null
  if (mode !== 'basket') {
    selectedBasketId.value = null
    selectedBasketSnapshotMode.value = 'static'
  }
  if (mode !== 'etf_holdings') {
    selectedEtfHoldingSymbol.value = ''
    selectedEtfHoldingSnapshotMode.value = 'latest'
    selectedEtfHoldingSnapshotDate.value = ''
  }
  if (mode !== 'symbols') logicDraft.symbols = []
})

watch(basketSupportsDynamicHistory, supportsDynamicHistory => {
  if (!supportsDynamicHistory) selectedBasketSnapshotMode.value = 'static'
})

watch(availableRunSubsetSymbols, symbols => {
  if (symbols.length) {
    const allowed = new Set(symbols)
    runDraft.overrideSymbols = runDraft.overrideSymbols.filter(symbol => allowed.has(symbol))
    return
  }
  if (!['symbols', 'watchlist', 'basket', 'etf_holdings'].includes(universeMode.value)) {
    runDraft.use_subset = false
    runSubsetMenuOpen.value = false
  }
})

watch(() => sourceType.value, value => {
  if (value === 'radar') {
    if (
      universeMode.value === 'symbols'
      && !logicDraft.symbols.length
      && selectedWatchlistId.value == null
      && selectedScreenerId.value == null
      && selectedBasketId.value == null
    ) {
      universeMode.value = 'radar'
    }
    return
  }
  if (universeMode.value === 'radar') universeMode.value = 'symbols'
})

function createNodeId() {
  return crypto.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

function createConditionNode(overrides: Partial<BuilderConditionNode> = {}): BuilderConditionNode {
  return {
    id: createNodeId(),
    kind: 'condition',
    condition: createDefaultTechnicalCondition(),
    ...overrides,
  }
}

function createGroupNode(
  type: 'all' | 'any',
  children: BuilderRuleNode[] = [],
): BuilderGroupNode {
  return {
    id: createNodeId(),
    kind: 'group',
    type,
    children,
  }
}

function createNotNode(condition: BuilderRuleNode | null = null): BuilderNotNode {
  return {
    id: createNodeId(),
    kind: 'not',
    condition,
  }
}

function startNew() {
  isNew.value = true
  strategyLab.selectDefinition(null)
  sectionExpanded.value = resolveSectionState(null, true)
  draft.name = ''
  draft.description = ''
  draft.is_active = true
  sourceType.value = 'custom'
  universeMode.value = 'symbols'
  selectedWatchlistId.value = null
  selectedScreenerId.value = null
  selectedBasketId.value = null
  selectedBasketSnapshotMode.value = 'static'
  selectedEtfHoldingSymbol.value = ''
  selectedEtfHoldingSnapshotMode.value = 'latest'
  selectedEtfHoldingSnapshotDate.value = ''
  compareRunId.value = null
  draft.tags = []
  versionNotes.value = ''
  symbolInput.value = ''
  logicDraft.timeframe = 'D1'
  logicDraft.direction = 'long'
  logicDraft.stop_model = 'percent'
  setSweepSingle(sweepDraft.stop_loss_pct, 2, 0.1)
  logicDraft.stop_atr_period = 14
  logicDraft.stop_atr_multiple = 2
  logicDraft.hard_trailing_stop_pct = ''
  logicDraft.hard_trailing_activation_pct = 0
  setSweepSingle(sweepDraft.take_profit_rr, 2, 0.25)
  setSweepSingle(sweepDraft.max_bars_in_trade, 20, 1)
  logicDraft.break_even_rr = ''
  logicDraft.trailing_stop_rr = ''
  logicDraft.position_sizing_mode = 'percent_risk'
  logicDraft.position_sizing_value = 1
  logicDraft.pyramiding_max_entries = 1
  logicDraft.benchmark_symbol = 'SPY'
  logicDraft.symbols = []
  logicDraft.ruleTree = createGroupNode('all', [])
  logicDraft.exitRuleTree = createGroupNode('all', [])
  radarDraft.setup_types = []
  radarDraft.states = []
  radarDraft.min_score = 0.65
  runDraft.test_mode = 'backtest'
  runDraft.timeframe = ''
  runDraft.date_from = ''
  runDraft.date_to = ''
  runDraft.initial_capital = 100000
  runDraft.risk_per_trade_pct = 1
  runDraft.slippage_bps = 5
  runDraft.commission_model = 'fixed_round_trip'
  runDraft.commission_value = ''
  runDraft.walk_forward_segments = 3
  runDraft.walk_forward_training_share = 0.6
  runDraft.paper_forward_bars = 20
  runDraft.max_concurrent_positions = 4
  runDraft.max_portfolio_risk_pct = 4
  runDraft.max_symbol_allocation_pct = 35
  runDraft.close_open_positions_at_end = false
  runDraft.dynamic_universe_exit_policy = 'leave_open'
  runDraft.use_subset = false
  runDraft.overrideSymbols = []
  showAdvancedRunOptions.value = false
  runSubsetMenuOpen.value = false
}

function selectDefinition(id: number) {
  isNew.value = false
  strategyLab.selectDefinition(id)
  hydrateFromSelection(strategyLab.selectedDefinition)
}

function hydrateFromSelection(definition: StrategyDefinition | null | undefined) {
  if (!definition) {
    if (!isNew.value) startNew()
    return
  }
  isNew.value = false
  sectionExpanded.value = resolveSectionState(definition, false)
  draft.name = definition.name
  draft.description = definition.description ?? ''
  draft.is_active = definition.is_active
  sourceType.value = definition.source_type === 'radar' ? 'radar' : 'custom'
  draft.tags = normalizeTags(definition.tags)

  const liveVersion = definition.versions.find(version => version.is_current) ?? definition.versions[0]
  hydrateFromVersion(liveVersion)
  compareRunId.value = null
}

function hydrateFromVersion(version: StrategyVersion | null | undefined) {
  if (!version) return
  const snapshot = version.definition_snapshot ?? {}
  const risk = snapshot.risk ?? {}
  const exits = snapshot.exits ?? {}
  const radarFilters = snapshot.radar_filters ?? {}
  const executionModel = version.execution_model ?? {}
  const runDefaults = executionModel.run_defaults ?? {}
  versionNotes.value = version.notes ?? ''
  logicDraft.timeframe = String(snapshot.timeframe ?? 'D1')
  logicDraft.direction = String(snapshot.direction ?? 'long')
  logicDraft.stop_model = String(risk.stop_model ?? 'percent') === 'atr' ? 'atr' : 'percent'
  setSweepSingle(sweepDraft.stop_loss_pct, toPositiveNumber(risk.stop_loss_pct, 2), 0.1)
  logicDraft.stop_atr_period = Math.max(1, Math.round(toPositiveNumber(risk.stop_atr_period, 14)))
  logicDraft.stop_atr_multiple = Math.max(0.1, Number(risk.stop_atr_multiple ?? 2) || 2)
  logicDraft.hard_trailing_stop_pct = optionalDisabledInput(risk.hard_trailing_stop_pct)
  logicDraft.hard_trailing_activation_pct = Math.max(0, Number(risk.hard_trailing_activation_pct ?? 0) || 0)
  const takeProfitSource = Object.prototype.hasOwnProperty.call(exits, 'take_profit_rr')
    ? exits.take_profit_rr
    : Object.prototype.hasOwnProperty.call(risk, 'take_profit_rr')
      ? risk.take_profit_rr
      : undefined
  const maxBarsSource = Object.prototype.hasOwnProperty.call(exits, 'max_bars_in_trade')
    ? exits.max_bars_in_trade
    : Object.prototype.hasOwnProperty.call(risk, 'max_bars_in_trade')
      ? risk.max_bars_in_trade
      : undefined
  setSweepSingle(sweepDraft.take_profit_rr, optionalDisabledInputWithDefault(takeProfitSource, 2), 0.25)
  setSweepSingle(sweepDraft.max_bars_in_trade, optionalDisabledInputWithDefault(maxBarsSource, 20), 1)
  logicDraft.break_even_rr = optionalDisabledInput(risk.break_even_rr)
  logicDraft.trailing_stop_rr = optionalDisabledInput(risk.trailing_stop_rr)
  const sizingMode = String(risk.position_sizing_mode ?? 'percent_risk')
  logicDraft.position_sizing_mode = ['percent_risk', 'fixed_cash', 'percent_capital', 'fixed_quantity'].includes(sizingMode)
    ? (sizingMode as typeof logicDraft.position_sizing_mode)
    : 'percent_risk'
  logicDraft.position_sizing_value = Math.max(0, Number(risk.position_sizing_value ?? 1) || 1)
  logicDraft.pyramiding_max_entries = Math.max(1, Math.round(toPositiveNumber(risk.pyramiding_max_entries, 1)))
  logicDraft.benchmark_symbol = String(version.benchmark_config?.symbol ?? 'SPY')
  if (version.universe_config?.watchlist_id != null) {
    universeMode.value = 'watchlist'
    selectedWatchlistId.value = Number(version.universe_config.watchlist_id)
    selectedScreenerId.value = null
    selectedBasketId.value = null
    selectedEtfHoldingSymbol.value = ''
    logicDraft.symbols = []
  } else if (version.universe_config?.screener_id != null) {
    universeMode.value = 'screener'
    selectedScreenerId.value = Number(version.universe_config.screener_id)
    selectedWatchlistId.value = null
    selectedBasketId.value = null
    selectedEtfHoldingSymbol.value = ''
    logicDraft.symbols = []
  } else if (version.universe_config?.basket_id != null) {
    universeMode.value = 'basket'
    selectedBasketId.value = Number(version.universe_config.basket_id)
    selectedBasketSnapshotMode.value = version.universe_config.basket_snapshot_mode === 'dynamic'
      ? 'dynamic'
      : 'static'
    selectedWatchlistId.value = null
    selectedScreenerId.value = null
    selectedEtfHoldingSymbol.value = ''
    logicDraft.symbols = []
  } else if (version.universe_config?.etf_holdings != null) {
    const etfHoldingsConfig = version.universe_config.etf_holdings ?? {}
    universeMode.value = 'etf_holdings'
    selectedEtfHoldingSymbol.value = String(etfHoldingsConfig.symbol ?? '').toUpperCase()
    selectedEtfHoldingSnapshotMode.value = normalizeEtfHoldingSnapshotMode(etfHoldingsConfig)
    selectedEtfHoldingSnapshotDate.value = String(etfHoldingsConfig.snapshot_date ?? '')
    selectedWatchlistId.value = null
    selectedScreenerId.value = null
    selectedBasketId.value = null
    selectedBasketSnapshotMode.value = 'static'
    logicDraft.symbols = []
  } else {
    universeMode.value = sourceType.value === 'radar' ? 'radar' : 'symbols'
    selectedWatchlistId.value = null
    selectedScreenerId.value = null
    selectedBasketId.value = null
    selectedEtfHoldingSymbol.value = ''
    selectedEtfHoldingSnapshotMode.value = 'latest'
    selectedEtfHoldingSnapshotDate.value = ''
    logicDraft.symbols = normalizeSymbols(version.universe_config?.symbols ?? [])
  }
  radarDraft.setup_types = Array.isArray(radarFilters.setup_types)
    ? radarFilters.setup_types.map((value: unknown) => String(value))
    : []
  radarDraft.states = Array.isArray(radarFilters.states)
    ? radarFilters.states.map((value: unknown) => String(value))
    : []
  radarDraft.min_score = Number(radarFilters.min_score ?? 0.65)
  runDraft.max_concurrent_positions = Math.max(
    1,
    Math.round(Number(executionModel.max_concurrent_positions ?? 4) || 4),
  )
  runDraft.max_portfolio_risk_pct = Math.max(
    0.5,
    Number(executionModel.max_portfolio_risk_pct ?? 4) || 4,
  )
  runDraft.max_symbol_allocation_pct = Math.max(
    1,
    Number(executionModel.max_symbol_allocation_pct ?? 35) || 35,
  )
  runDraft.close_open_positions_at_end = runDefaults.close_open_positions_at_end === true
  runDraft.dynamic_universe_exit_policy = runDefaults.dynamic_universe_exit_policy === 'close_on_removal'
    ? 'close_on_removal'
    : 'leave_open'
  runDraft.test_mode = ['backtest', 'walk_forward', 'paper_forward'].includes(String(runDefaults.test_mode))
    ? runDefaults.test_mode
    : 'backtest'
  runDraft.timeframe = String(runDefaults.timeframe ?? '')
  runDraft.date_from = toDateInputValue(runDefaults.date_from)
  runDraft.date_to = toDateInputValue(runDefaults.date_to)
  runDraft.initial_capital = Math.max(1000, Number(runDefaults.initial_capital ?? 100000) || 100000)
  runDraft.risk_per_trade_pct = Math.max(0.1, Number(runDefaults.risk_per_trade_pct ?? 1) || 1)
  runDraft.slippage_bps = optionalDisabledInputWithDefault(runDefaults.slippage_bps, 5)
  runDraft.commission_model = ['fixed_round_trip', 'fixed_per_order', 'percent_of_notional'].includes(String(runDefaults.commission_model))
    ? runDefaults.commission_model
    : 'fixed_round_trip'
  const commissionSource = Object.prototype.hasOwnProperty.call(runDefaults, 'commission_value')
    ? runDefaults.commission_value
    : runDefaults.commission_per_trade
  runDraft.commission_value = optionalDisabledInput(commissionSource)
  runDraft.walk_forward_segments = Math.max(2, Math.round(Number(runDefaults.walk_forward_segments ?? 3) || 3))
  runDraft.walk_forward_training_share = Math.min(
    0.9,
    Math.max(0.3, Number(runDefaults.walk_forward_training_share ?? 0.6) || 0.6),
  )
  runDraft.paper_forward_bars = Math.max(5, Math.round(Number(runDefaults.paper_forward_bars ?? 20) || 20))
  hydrateParameterSweeps(runDefaults.parameter_sweeps)
  runDraft.overrideSymbols = normalizeSymbols(Array.isArray(runDefaults.override_symbols) ? runDefaults.override_symbols : [])
  runDraft.use_subset = runDraft.overrideSymbols.length > 0
  showAdvancedRunOptions.value = false
  runSubsetMenuOpen.value = false

  const rawConditions = Array.isArray(snapshot.conditions) ? snapshot.conditions : []
  logicDraft.ruleTree = parseRuleTree(
    snapshot.condition_tree,
    String(snapshot.entry_logic ?? 'all'),
    rawConditions,
  )
  const rawExitConditions = Array.isArray(exits.conditions) ? exits.conditions : []
  logicDraft.exitRuleTree = parseRuleTree(
    exits.condition_tree,
    String(exits.logic ?? exits.exit_logic ?? 'all'),
    rawExitConditions,
  )
}

function parseCondition(raw: Record<string, any>): BuilderConditionNode {
  return createConditionNode({
    condition: normalizeTechnicalCondition(raw),
  })
}

function parseRuleTree(
  rawTree: unknown,
  fallbackEntryLogic: string,
  rawConditions: unknown[],
): BuilderGroupNode {
  const parsed = parseRuleNode(rawTree)
  if (parsed?.kind === 'group') return parsed
  if (parsed) return createGroupNode('all', [parsed])
  if (rawConditions.length) {
    const children = rawConditions
      .filter((item): item is Record<string, any> => typeof item === 'object' && item !== null)
      .map(parseCondition)
    return createGroupNode(
      fallbackEntryLogic === 'any' ? 'any' : 'all',
      children,
    )
  }
  return createGroupNode(fallbackEntryLogic === 'any' ? 'any' : 'all', [])
}

function parseRuleNode(raw: unknown): BuilderRuleNode | null {
  if (!raw || typeof raw !== 'object') return null
  const node = raw as Record<string, any>
  const nodeType = String(node.type ?? node.entry_logic ?? '').toLowerCase()
  if (nodeType === 'not') {
    return createNotNode(parseRuleNode(node.condition))
  }
  if (nodeType === 'all' || nodeType === 'any') {
    const children = Array.isArray(node.conditions)
      ? node.conditions
          .map(parseRuleNode)
          .filter((item): item is BuilderRuleNode => item != null)
      : []
    return createGroupNode(nodeType, children)
  }
  return parseCondition(node)
}

function countConditionLeaves(node: BuilderRuleNode | null): number {
  if (!node) return 0
  if (node.kind === 'condition') return 1
  if (node.kind === 'not') return countConditionLeaves(node.condition)
  return node.children.reduce((total, child) => total + countConditionLeaves(child), 0)
}

function compileRuleNode(node: BuilderRuleNode): Record<string, any> {
  if (node.kind === 'condition') return compileCondition(node)
  if (node.kind === 'not') {
    return {
      type: 'not',
      condition: node.condition ? compileRuleNode(node.condition) : null,
    }
  }
  return {
    type: node.type,
    conditions: node.children.map(compileRuleNode),
  }
}

function flattenConditionNodes(node: BuilderRuleNode | null): BuilderConditionNode[] {
  if (!node) return []
  if (node.kind === 'condition') return [node]
  if (node.kind === 'not') return flattenConditionNodes(node.condition)
  return node.children.flatMap(child => flattenConditionNodes(child))
}

function addConditionToTree(targetId: string) {
  addConditionToBuilderTree(logicDraft.ruleTree, targetId)
}

function addConditionToExitTree(targetId: string) {
  addConditionToBuilderTree(logicDraft.exitRuleTree, targetId)
}

function addConditionToBuilderTree(tree: BuilderGroupNode, targetId: string) {
  applyNodeMutation(tree, targetId, target => {
    if (target.kind === 'group') target.children.push(createConditionNode())
    if (target.kind === 'not') target.condition = createConditionNode()
  })
}

function addGroupToTree(targetId: string, type: 'all' | 'any' | 'not') {
  addGroupToBuilderTree(logicDraft.ruleTree, targetId, type)
}

function addGroupToExitTree(targetId: string, type: 'all' | 'any' | 'not') {
  addGroupToBuilderTree(logicDraft.exitRuleTree, targetId, type)
}

function addGroupToBuilderTree(
  tree: BuilderGroupNode,
  targetId: string,
  type: 'all' | 'any' | 'not',
) {
  applyNodeMutation(tree, targetId, target => {
    const nextNode = type === 'not' ? createNotNode() : createGroupNode(type)
    if (target.kind === 'group') target.children.push(nextNode)
    if (target.kind === 'not') target.condition = nextNode
  })
}

function removeNodeFromTree(nodeId: string) {
  removeNodeFromBuilderTree('entry', nodeId)
}

function removeNodeFromExitTree(nodeId: string) {
  removeNodeFromBuilderTree('exit', nodeId)
}

function removeNodeFromBuilderTree(target: 'entry' | 'exit', nodeId: string) {
  const tree = target === 'entry' ? logicDraft.ruleTree : logicDraft.exitRuleTree
  if (tree.id === nodeId) {
    if (target === 'entry') logicDraft.ruleTree = createGroupNode('all', [])
    else logicDraft.exitRuleTree = createGroupNode('all', [])
    return
  }
  removeNodeRecursive(tree, nodeId)
}

function removeNodeRecursive(node: BuilderRuleNode, nodeId: string): boolean {
  if (node.kind === 'group') {
    const index = node.children.findIndex(child => child.id === nodeId)
    if (index !== -1) {
      node.children.splice(index, 1)
      return true
    }
    return node.children.some(child => removeNodeRecursive(child, nodeId))
  }
  if (node.kind === 'not') {
    if (node.condition?.id === nodeId) {
      node.condition = null
      return true
    }
    if (node.condition) return removeNodeRecursive(node.condition, nodeId)
  }
  return false
}

function applyNodeMutation(
  node: BuilderRuleNode,
  targetId: string,
  mutation: (node: BuilderRuleNode) => void,
): boolean {
  if (node.id === targetId) {
    mutation(node)
    return true
  }
  if (node.kind === 'group') {
    return node.children.some(child => applyNodeMutation(child, targetId, mutation))
  }
  if (node.kind === 'not' && node.condition) {
    return applyNodeMutation(node.condition, targetId, mutation)
  }
  return false
}

function addSelectedSymbol(symbol: string) {
  logicDraft.symbols = mergeSymbols(logicDraft.symbols, [symbol])
  symbolInput.value = ''
}

function checkboxValue(event: Event) {
  return (event.target as HTMLInputElement | null)?.checked === true
}

function toggleRadarDraftValue(target: string[], value: string, checked: boolean) {
  const next = new Set(target)
  if (checked) next.add(value)
  else next.delete(value)
  target.splice(0, target.length, ...next)
}

function toggleRadarMenu(kind: 'setup' | 'state') {
  if (kind === 'setup') {
    radarSetupMenuOpen.value = !radarSetupMenuOpen.value
    if (radarSetupMenuOpen.value) radarStateMenuOpen.value = false
    return
  }
  radarStateMenuOpen.value = !radarStateMenuOpen.value
  if (radarStateMenuOpen.value) radarSetupMenuOpen.value = false
}

function removeSymbol(symbol: string) {
  logicDraft.symbols = logicDraft.symbols.filter(item => item !== symbol)
}

function removeRunSymbol(symbol: string) {
  runDraft.overrideSymbols = runDraft.overrideSymbols.filter(item => item !== symbol)
}

function toggleRunSubsetSymbol(symbol: string, checked: boolean) {
  if (checked) {
    runDraft.overrideSymbols = mergeSymbols(runDraft.overrideSymbols, [symbol])
    return
  }
  removeRunSymbol(symbol)
}

function mergeSymbols(current: string[], rawValues: string[]) {
  const next = new Set(current)
  for (const symbol of normalizeSymbols(rawValues)) next.add(symbol)
  return Array.from(next)
}

function normalizeSymbols(values: unknown[]) {
  return values
    .map(value => String(value ?? '').trim().toUpperCase())
    .filter(Boolean)
}

function resizeSidebar(next: number) {
  if (next <= STRATEGY_SIDEBAR_COLLAPSED_WIDTH + 8) {
    sidebarCollapsed.value = true
    return
  }
  sidebarCollapsed.value = false
  sidebarWidth.value = Math.max(
    STRATEGY_SIDEBAR_MIN_WIDTH,
    Math.min(STRATEGY_SIDEBAR_MAX_WIDTH, Math.round(next)),
  )
}

function toggleSection(key: StrategyLabSectionKey) {
  sectionExpanded.value = {
    ...sectionExpanded.value,
    [key]: !sectionExpanded.value[key],
  }
}

function loadStrategySidebarState() {
  try {
    const raw = localStorage.getItem(STRATEGY_SIDEBAR_STORAGE_KEY)
    const parsed = raw ? JSON.parse(raw) : {}
    return {
      width: typeof parsed.width === 'number' ? parsed.width : STRATEGY_SIDEBAR_DEFAULT_WIDTH,
      collapsed: parsed.collapsed === true,
    }
  } catch {
    return {
      width: STRATEGY_SIDEBAR_DEFAULT_WIDTH,
      collapsed: false,
    }
  }
}

function defaultSectionState(hasRuns: boolean): StrategyLabSectionState {
  return hasRuns
    ? {
        profile: false,
        entry: false,
        risk: false,
        exits: false,
        runs: false,
        results: true,
      }
    : {
        profile: true,
        entry: true,
        risk: true,
        exits: true,
        runs: true,
        results: false,
      }
}

function mergeSectionState(
  defaults: StrategyLabSectionState,
  partial?: Partial<StrategyLabSectionState> | null,
): StrategyLabSectionState {
  return {
    profile: typeof partial?.profile === 'boolean' ? partial.profile : defaults.profile,
    entry: typeof partial?.entry === 'boolean' ? partial.entry : defaults.entry,
    risk: typeof partial?.risk === 'boolean' ? partial.risk : defaults.risk,
    exits: typeof partial?.exits === 'boolean' ? partial.exits : defaults.exits,
    runs: typeof partial?.runs === 'boolean' ? partial.runs : defaults.runs,
    results: typeof partial?.results === 'boolean' ? partial.results : defaults.results,
  }
}

function currentSectionStateStorageKey() {
  if (isNew.value || !strategyLab.selectedDefinition?.id) return 'draft'
  return `strategy:${strategyLab.selectedDefinition.id}`
}

function resolveSectionState(
  definition: StrategyDefinition | null | undefined,
  draftMode: boolean,
): StrategyLabSectionState {
  const key = draftMode || !definition?.id ? 'draft' : `strategy:${definition.id}`
  const hasRuns = draftMode ? false : (definition?.runs?.length ?? 0) > 0
  return mergeSectionState(defaultSectionState(hasRuns), storedSectionStates.value[key] ?? null)
}

function loadStrategySectionStates(): StrategyLabStoredSectionStates {
  try {
    const raw = localStorage.getItem(STRATEGY_SECTION_STORAGE_KEY)
    const parsed = raw ? JSON.parse(raw) as StrategyLabStoredSectionStates : {}
    return parsed && typeof parsed === 'object' ? parsed : {}
  } catch {
    return {}
  }
}

function stringHash(value: string) {
  let hash = 0
  for (let index = 0; index < value.length; index += 1) {
    hash = ((hash << 5) - hash) + value.charCodeAt(index)
    hash |= 0
  }
  return Math.abs(hash)
}

function normalizeTagValue(value: string) {
  return value
    .trim()
    .toLowerCase()
    .replace(/\s+/g, '-')
    .replace(/-+/g, '-')
}

function normalizeTags(values: string[]) {
  return Array.from(
    new Set(
      values
        .map(value => normalizeTagValue(String(value ?? '')))
        .filter(Boolean),
    ),
  )
}

function positionEvolutionPointValue(timeline: any, rawValue: number) {
  if (!Number.isFinite(rawValue)) return Number.NaN
  if (positionEvolutionMode.value === 'currency') return rawValue
  const denominator = positionEvolutionDenominator(timeline)
  if (!Number.isFinite(denominator) || denominator <= 0) return rawValue
  return (rawValue / denominator) * 100
}

function positionEvolutionDenominator(timeline: any) {
  const entryPrice = Number(timeline?.entry_price)
  const quantity = Number(timeline?.quantity)
  const entryNotional = Math.abs(entryPrice * quantity)
  if (Number.isFinite(entryNotional) && entryNotional > 0) return entryNotional

  const pnl = Number(timeline?.pnl)
  const pnlPct = Number(timeline?.pnl_pct)
  if (Number.isFinite(pnl) && Number.isFinite(pnlPct) && pnlPct !== 0) {
    const impliedNotional = Math.abs(pnl / (pnlPct / 100))
    if (Number.isFinite(impliedNotional) && impliedNotional > 0) return impliedNotional
  }

  return Number.NaN
}

function definitionDisplayTags(definition: StrategyDefinition) {
  if (!isNew.value && strategyLab.selectedDefinitionId === definition.id) {
    return normalizeTags(draft.tags)
  }
  return normalizeTags(definition.tags)
}

function tagPillStyle(tag: string) {
  const hue = stringHash(tag.trim().toLowerCase() || tag) % 360
  return {
    '--tag-bg': `hsl(${hue} 42% 13%)`,
    '--tag-border': `hsl(${hue} 38% 25%)`,
    '--tag-color': `hsl(${hue} 82% 80%)`,
  }
}

function seriesColorForKey(key: string) {
  const hue = stringHash(key.trim().toLowerCase() || key) % 360
  return `hsl(${hue} 72% 66%)`
}

function persistStrategySidebarState(value: { width: number; collapsed: boolean }) {
  try {
    localStorage.setItem(STRATEGY_SIDEBAR_STORAGE_KEY, JSON.stringify(value))
  } catch {
    // Ignore unavailable storage and keep the in-memory state.
  }
}

function persistStrategySectionState(key: string, value: StrategyLabSectionState) {
  try {
    storedSectionStates.value = {
      ...storedSectionStates.value,
      [key]: value,
    }
    localStorage.setItem(STRATEGY_SECTION_STORAGE_KEY, JSON.stringify(storedSectionStates.value))
  } catch {
    // Ignore unavailable storage and keep the in-memory state.
  }
}

function summarizeRadarOptions(
  values: string[],
  options: Array<{ value: string; label: string }>,
  emptyLabel: string,
) {
  if (!values.length) return emptyLabel
  if (values.length === 1) return options.find(option => option.value === values[0])?.label ?? humanizeToken(values[0])
  return `${values.length} selected`
}

function buildVersionPayload() {
  const flatConditions = flattenConditionNodes(logicDraft.ruleTree)
  const flatExitConditions = flattenConditionNodes(logicDraft.exitRuleTree)
  const hardTrailingStopPct = optionalNumberValue(logicDraft.hard_trailing_stop_pct)
  const breakEvenR = optionalNumberValue(logicDraft.break_even_rr)
  const trailingStopR = optionalNumberValue(logicDraft.trailing_stop_rr)
  const takeProfitR = primarySweepValue(sweepDraft.take_profit_rr, { min: 0, step: 0.25 })
  const maxBarsInTrade = primarySweepValue(sweepDraft.max_bars_in_trade, { integer: true, min: 1, step: 1 })
  const stopLossPct = primarySweepValue(sweepDraft.stop_loss_pct, { min: 0.1, step: 0.1 }) ?? 2
  const slippageBps = optionalNumberValue(runDraft.slippage_bps)
  const commissionValue = optionalNumberValue(runDraft.commission_value)
  const riskConfig = {
    stop_model: logicDraft.stop_model,
    stop_loss_pct: stopLossPct,
    stop_atr_period: logicDraft.stop_atr_period,
    stop_atr_multiple: logicDraft.stop_atr_multiple,
    hard_trailing_stop_pct: hardTrailingStopPct,
    hard_trailing_activation_pct: logicDraft.hard_trailing_activation_pct,
    break_even_rr: breakEvenR,
    trailing_stop_rr: trailingStopR,
    position_sizing_mode: logicDraft.position_sizing_mode,
    position_sizing_value: logicDraft.position_sizing_value,
    pyramiding_max_entries: logicDraft.pyramiding_max_entries,
  }
  const exitsConfig = {
    take_profit_rr: takeProfitR,
    max_bars_in_trade: maxBarsInTrade == null ? null : Math.round(maxBarsInTrade),
    logic: logicDraft.exitRuleTree.type,
    condition_tree: compileRuleNode(logicDraft.exitRuleTree),
    conditions: flatExitConditions.map(compileCondition),
  }
  return {
    definition_snapshot: {
      ...(sourceType.value === 'radar'
        ? {
            timeframe: logicDraft.timeframe,
            radar_filters: {
              timeframe: logicDraft.timeframe,
              setup_types: radarDraft.setup_types,
              states: radarDraft.states,
              min_score: radarDraft.min_score,
            },
            risk: riskConfig,
            exits: exitsConfig,
          }
        : {
            timeframe: logicDraft.timeframe,
            direction: logicDraft.direction,
            entry_logic: logicDraft.ruleTree.type,
            condition_tree: compileRuleNode(logicDraft.ruleTree),
            conditions: flatConditions.map(compileCondition),
            risk: riskConfig,
            exits: exitsConfig,
          }),
    },
    parameter_schema: {
      stop_model: { type: 'string', enum: ['percent', 'atr'] },
      stop_loss_pct: { type: 'number', min: 0.1 },
      stop_atr_period: { type: 'integer', min: 1 },
      stop_atr_multiple: { type: 'number', min: 0.1 },
      hard_trailing_stop_pct: { type: ['number', 'null'], min: 0 },
      hard_trailing_activation_pct: { type: 'number', min: 0 },
      take_profit_rr: { type: ['number', 'null'], min: 0 },
      max_bars_in_trade: { type: ['integer', 'null'], min: 0 },
      break_even_rr: { type: ['number', 'null'], min: 0 },
      trailing_stop_rr: { type: ['number', 'null'], min: 0 },
      position_sizing_mode: { type: 'string', enum: ['percent_risk', 'fixed_cash', 'percent_capital', 'fixed_quantity'] },
      position_sizing_value: { type: 'number', min: 0 },
      pyramiding_max_entries: { type: 'integer', min: 1 },
    },
    default_parameters: {
      stop_model: logicDraft.stop_model,
      stop_loss_pct: stopLossPct,
      stop_atr_period: logicDraft.stop_atr_period,
      stop_atr_multiple: logicDraft.stop_atr_multiple,
      hard_trailing_stop_pct: hardTrailingStopPct,
      hard_trailing_activation_pct: logicDraft.hard_trailing_activation_pct,
      take_profit_rr: takeProfitR,
      max_bars_in_trade: maxBarsInTrade == null ? null : Math.round(maxBarsInTrade),
      break_even_rr: breakEvenR,
      trailing_stop_rr: trailingStopR,
      position_sizing_mode: logicDraft.position_sizing_mode,
      position_sizing_value: logicDraft.position_sizing_value,
      pyramiding_max_entries: logicDraft.pyramiding_max_entries,
    },
    universe_config: {
      ...(universeMode.value === 'radar'
        ? {}
        : universeMode.value === 'watchlist' && selectedWatchlistId.value != null
        ? { watchlist_id: selectedWatchlistId.value }
        : universeMode.value === 'screener' && selectedScreenerId.value != null
          ? { screener_id: selectedScreenerId.value }
          : universeMode.value === 'basket' && selectedBasketId.value != null
            ? {
                basket_id: selectedBasketId.value,
                ...(selectedBasketSnapshotMode.value === 'dynamic'
                  ? { basket_snapshot_mode: selectedBasketSnapshotMode.value }
                  : {}),
              }
            : universeMode.value === 'etf_holdings' && selectedEtfHoldingSymbol.value
              ? {
                  etf_holdings: {
                    symbol: selectedEtfHoldingSymbol.value,
                    snapshot_mode: selectedEtfHoldingSnapshotMode.value,
                    ...(selectedEtfHoldingSnapshotMode.value === 'date' && selectedEtfHoldingSnapshotDate.value
                      ? { snapshot_date: selectedEtfHoldingSnapshotDate.value }
                      : {}),
                  },
                }
              : { symbols: logicDraft.symbols }),
    },
    benchmark_config: logicDraft.benchmark_symbol.trim()
      ? { symbol: logicDraft.benchmark_symbol.trim().toUpperCase() }
      : {},
    execution_model: {
      entry: 'next_bar_open',
      exits: [
        'stop_loss',
        ...(optionalNumberOrZero(takeProfitR) > 0 ? ['take_profit'] : []),
        ...(optionalNumberOrZero(maxBarsInTrade) > 0 ? ['time_exit'] : []),
        ...(optionalNumberOrZero(breakEvenR) > 0 ? ['break_even'] : []),
        ...(optionalNumberOrZero(trailingStopR) > 0 ? ['trailing_stop'] : []),
        ...(optionalNumberOrZero(hardTrailingStopPct) > 0 ? ['hard_trailing_stop'] : []),
        ...(exitConditionCount.value > 0 ? ['condition_exit'] : []),
      ],
      sizing: logicDraft.position_sizing_mode,
      max_entries: logicDraft.pyramiding_max_entries,
      max_concurrent_positions: runDraft.max_concurrent_positions,
      max_portfolio_risk_pct: runDraft.max_portfolio_risk_pct,
      max_symbol_allocation_pct: runDraft.max_symbol_allocation_pct,
      run_defaults: {
        test_mode: runDraft.test_mode,
        timeframe: runDraft.timeframe || null,
        date_from: runDraft.date_from || null,
        date_to: runDraft.date_to || null,
        initial_capital: runDraft.initial_capital,
        risk_per_trade_pct: runDraft.risk_per_trade_pct,
        slippage_bps: slippageBps,
        commission_model: runDraft.commission_model,
        commission_value: commissionValue,
        commission_per_trade: commissionValue,
        close_open_positions_at_end: runDraft.close_open_positions_at_end,
        dynamic_universe_exit_policy: usesDynamicEtfUniverse.value
          ? runDraft.dynamic_universe_exit_policy
          : 'leave_open',
        walk_forward_segments: runDraft.walk_forward_segments,
        walk_forward_training_share: runDraft.walk_forward_training_share,
        paper_forward_bars: runDraft.paper_forward_bars,
        parameter_sweeps: serializeParameterSweeps(),
        override_symbols: runDraft.use_subset ? runDraft.overrideSymbols : [],
      },
    },
    notes: versionNotes.value.trim() || null,
  }
}

function compileCondition(condition: BuilderConditionNode) {
  return {
    ...condition.condition,
    op: condition.condition.op ?? 'gt',
  }
}

async function saveProfileOnly() {
  if (!strategyLab.selectedDefinition || !currentVersion.value) return
  const definitionPayload = buildDefinitionPayload()
  const versionPayload = buildVersionPayload()
  await strategyLab.updateDefinition(strategyLab.selectedDefinition.id, definitionPayload)
  await strategyLab.updateVersion(currentVersion.value.id, strategyLab.selectedDefinition.id, versionPayload)
  const refreshed = await strategyLab.refreshDefinition(strategyLab.selectedDefinition.id)
  hydrateFromSelection(refreshed)
}

async function deleteCurrentStrategy() {
  const current = strategyLab.selectedDefinition
  if (!current) return
  await strategyLab.deleteDefinition(current.id)
  showDeleteModal.value = false
  if (strategyLab.selectedDefinition) {
    hydrateFromSelection(strategyLab.selectedDefinition)
    isNew.value = false
    return
  }
  startNew()
}

async function publishStrategy() {
  const definitionPayload = buildDefinitionPayload()
  const versionPayload = buildVersionPayload()
  if (isNew.value) {
    const created = await strategyLab.createDefinition({
      ...definitionPayload,
      initial_version: versionPayload,
    })
    strategyLab.selectedDefinitionId = created.id
    hydrateFromSelection(created)
    isNew.value = false
    return
  }
  if (!strategyLab.selectedDefinition) return
  await strategyLab.updateDefinition(strategyLab.selectedDefinition.id, definitionPayload)
  await strategyLab.publishVersion(strategyLab.selectedDefinition.id, versionPayload)
  await reload()
}

async function runCurrentVersion() {
  if (!currentVersion.value) return
  const slippageBps = optionalNumberValue(runDraft.slippage_bps)
  const commissionValue = optionalNumberValue(runDraft.commission_value)
  const submitted = await strategyLab.runVersion(currentVersion.value.id, {
    test_mode: runDraft.test_mode,
    timeframe: runDraft.timeframe || null,
    date_from: runDraft.date_from ? `${runDraft.date_from}T00:00:00Z` : null,
    date_to: runDraft.date_to ? `${runDraft.date_to}T23:59:59Z` : null,
    parameter_values: {},
    parameter_grid: parameterGridPayload(),
    universe_config: runDraft.use_subset && runDraft.overrideSymbols.length
      ? { symbols: runDraft.overrideSymbols }
      : {},
    execution_assumptions: {
      initial_capital: runDraft.initial_capital,
      risk_per_trade_pct: runDraft.risk_per_trade_pct,
      slippage_bps: slippageBps,
      commission_model: runDraft.commission_model,
      commission_value: commissionValue,
      commission_per_trade: commissionValue,
      close_open_positions_at_end: runDraft.close_open_positions_at_end,
      dynamic_universe_exit_policy: usesDynamicEtfUniverse.value
        ? runDraft.dynamic_universe_exit_policy
        : 'leave_open',
      max_concurrent_positions: runDraft.max_concurrent_positions,
      max_portfolio_risk_pct: runDraft.max_portfolio_risk_pct,
      max_symbol_allocation_pct: runDraft.max_symbol_allocation_pct,
      walk_forward_segments: runDraft.walk_forward_segments,
      walk_forward_training_share: runDraft.walk_forward_training_share,
      paper_forward_bars: runDraft.paper_forward_bars,
      optimization: { enabled: false },
    },
  })
  strategyLab.selectedRunId = submitted.id
}

async function refreshPaperForwardRun() {
  if (!selectedRunDetail.value || selectedRunDetail.value.test_mode !== 'paper_forward') return
  const refreshed = await strategyLab.refreshRun(selectedRunDetail.value.id)
  strategyLab.selectedRunId = refreshed.id
}

function handleExport(kind: 'summary' | 'trades') {
  exportMenuOpen.value = false
  if (kind === 'summary') {
    exportSummaryJson()
    return
  }
  exportTradesCsv()
}

function exportSummaryJson() {
  if (!selectedRunDetail.value) return
  downloadBlob(
    `strategy-run-${selectedRunDetail.value.id}.json`,
    'application/json',
    JSON.stringify(selectedRunDetail.value.result_summary ?? {}, null, 2),
  )
}

function exportTradesCsv() {
  if (!visibleTrades.value.length || !selectedRunDetail.value) return
  const header = ['symbol', 'side', 'entry_at', 'exit_at', 'entry_price', 'exit_price', 'pnl', 'r_multiple', 'exit_reason']
  const rows = visibleTrades.value.map((trade: any) => [
    trade.instrument_symbol,
    trade.side,
    trade.entry_at,
    trade.exit_at,
    trade.entry_price,
    trade.exit_price,
    trade.pnl,
    trade.r_multiple,
    trade.exit_reason,
  ])
  const csv = [header, ...rows]
    .map(row => row.map(value => `"${String(value ?? '').replace(/"/g, '""')}"`).join(','))
    .join('\n')
  downloadBlob(`strategy-run-${selectedRunDetail.value.id}-trades.csv`, 'text/csv', csv)
}

function downloadBlob(filename: string, mimeType: string, content: string) {
  const blob = new Blob([content], { type: mimeType })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  anchor.click()
  URL.revokeObjectURL(url)
}

function buildDefinitionPayload() {
  return {
    name: draft.name.trim(),
    description: draft.description.trim() || null,
    source_type: sourceType.value,
    definition_type: sourceType.value === 'radar' ? 'signal_source' : 'rules',
    is_active: draft.is_active,
    tags: normalizeTags(draft.tags),
    metadata: {},
  }
}

async function reload() {
  await strategyLab.loadAll()
  hydrateFromSelection(strategyLab.selectedDefinition)
}

function describeRuleNode(node: BuilderRuleNode | null): string {
  if (!node) return ''
  if (node.kind === 'condition') return describeCondition(node)
  if (node.kind === 'not') return `not (${describeRuleNode(node.condition) || 'empty rule'})`
  const joiner = node.type === 'all' ? ' and ' : ' or '
  return node.children.map(describeRuleNode).filter(Boolean).join(joiner)
}

function describeCondition(condition: BuilderConditionNode) {
  return describeTechnicalCondition(condition.condition)
}

function parameterGridPayload() {
  const parameters = [
    {
      key: 'risk.stop_loss_pct',
      label: 'Stop %',
      values: logicDraft.stop_model === 'percent'
        ? valuesFromSweep(sweepDraft.stop_loss_pct, { min: 0.1, step: 0.1 })
        : [],
    },
    {
      key: 'exits.take_profit_rr',
      label: 'Target R',
      values: valuesFromSweep(sweepDraft.take_profit_rr, { min: 0.0000001, step: 0.25 }),
    },
    {
      key: 'exits.max_bars_in_trade',
      label: 'Max bars',
      values: valuesFromSweep(sweepDraft.max_bars_in_trade, { integer: true, min: 1, step: 1 }),
    },
  ].filter(parameter => parameter.values.length > 1)
  return parameters.length ? { parameters } : null
}

function toDateInputValue(value: unknown) {
  if (!value) return ''
  const normalized = String(value)
  return normalized.includes('T') ? normalized.slice(0, 10) : normalized
}

function buildNormalizedChartSeries(
  rows: any[],
  label: string,
  color: string,
  valueKey: string,
) {
  if (!Array.isArray(rows) || rows.length < 2) return null
  const normalizedRows = rows
    .map((row: any) => ({
      ts: String(row.ts ?? ''),
      value: Number(row[valueKey]),
    }))
    .filter(row => row.ts && Number.isFinite(row.value))
  if (normalizedRows.length < 2) return null
  const base = normalizedRows.find(row => row.value !== 0)?.value ?? normalizedRows[0].value
  if (!Number.isFinite(base) || base === 0) return null
  return {
    label,
    color,
    points: normalizedRows.map(row => ({
      ts: row.ts,
      value: ((row.value - base) / base) * 100,
    })),
  }
}

function buildRawChartSeries(
  rows: any[],
  label: string,
  color: string,
  valueKey: string,
) {
  if (!Array.isArray(rows) || rows.length < 2) return null
  const normalizedRows = rows
    .map((row: any) => ({
      ts: String(row.ts ?? ''),
      value: Number(row[valueKey]),
    }))
    .filter(row => row.ts && Number.isFinite(row.value))
  if (normalizedRows.length < 2) return null
  return {
    label,
    color,
    points: normalizedRows,
  }
}

function deriveDrawdownCurve(rows: any[], valueKey: string) {
  if (!Array.isArray(rows) || rows.length < 2) return []
  let peak: number | null = null
  return rows
    .map((row: any) => {
      const ts = String(row?.ts ?? '')
      const value = Number(row?.[valueKey])
      if (!ts || !Number.isFinite(value)) return null
      if (peak == null || value > peak) peak = value
      const drawdownPct = !peak || peak <= 0 ? 0 : ((peak - value) / peak) * 100
      return {
        ts,
        drawdown_pct: Number(drawdownPct.toFixed(4)),
      }
    })
    .filter((row): row is { ts: string; drawdown_pct: number } => row != null)
}

function negateSeriesValues(rows: any[], valueKey: string) {
  return Array.isArray(rows)
    ? rows.map((row: any) => ({
      ...row,
      [valueKey]: Number.isFinite(Number(row?.[valueKey])) ? -Math.abs(Number(row[valueKey])) : row?.[valueKey],
    }))
    : []
}

function formatSeriesReturn(rows: any[], valueKey: string) {
  const value = seriesReturnValue(rows, valueKey)
  return value == null ? '—' : formatSignedPercent(value)
}

function seriesReturnValue(rows: any[], valueKey: string) {
  if (!Array.isArray(rows) || rows.length < 2) return null
  const values = rows
    .map((row: any) => Number(row[valueKey]))
    .filter(Number.isFinite)
  if (values.length < 2) return null
  const first = values.find(value => value !== 0) ?? values[0]
  const last = values[values.length - 1]
  if (!Number.isFinite(first) || !Number.isFinite(last) || first === 0) return null
  return ((last - first) / first) * 100
}

function coerceStrategyCoverageUniverse(value: unknown): StrategyCoverageUniverse | null {
  if (!value || typeof value !== 'object') return null
  const raw = value as Record<string, any>
  return {
    preview_mode: String(raw.preview_mode ?? 'resolved'),
    preview_note: raw.preview_note ? String(raw.preview_note) : null,
    instrument_count: Number(raw.instrument_count ?? 0),
    instruments_with_data: Number(raw.instruments_with_data ?? 0),
    instruments_with_requested_data: Number(raw.instruments_with_requested_data ?? 0),
    instruments_with_full_requested_coverage: Number(raw.instruments_with_full_requested_coverage ?? 0),
    instruments_with_partial_requested_coverage: Number(raw.instruments_with_partial_requested_coverage ?? 0),
    instruments_without_requested_coverage: Number(raw.instruments_without_requested_coverage ?? 0),
    total_bars: Number(raw.total_bars ?? 0),
    requested_first_bar_at: raw.requested_first_bar_at ? String(raw.requested_first_bar_at) : null,
    requested_last_bar_at: raw.requested_last_bar_at ? String(raw.requested_last_bar_at) : null,
    any_coverage_from: raw.any_coverage_from ? String(raw.any_coverage_from) : null,
    any_coverage_to: raw.any_coverage_to ? String(raw.any_coverage_to) : null,
    collective_coverage_from: raw.collective_coverage_from ? String(raw.collective_coverage_from) : null,
    collective_coverage_to: raw.collective_coverage_to ? String(raw.collective_coverage_to) : null,
    requested_fits_collective_range: typeof raw.requested_fits_collective_range === 'boolean'
      ? raw.requested_fits_collective_range
      : null,
    resolved_symbols: Array.isArray(raw.resolved_symbols) ? raw.resolved_symbols.map((item: unknown) => String(item)) : [],
    limiting_instruments: normalizeCoverageInstruments(raw.limiting_instruments),
    instruments: normalizeCoverageInstruments(raw.instruments),
    simulatable_instrument_count: Number.isFinite(Number(raw.simulatable_instrument_count))
      ? Number(raw.simulatable_instrument_count)
      : undefined,
    simulatable_symbols: Array.isArray(raw.simulatable_symbols)
      ? raw.simulatable_symbols.map((item: unknown) => String(item))
      : undefined,
  }
}

function normalizeCoverageInstruments(value: unknown): StrategyCoverageInstrument[] {
  if (!Array.isArray(value)) return []
  return value
    .filter((item): item is Record<string, any> => typeof item === 'object' && item !== null)
    .map(item => ({
      instrument_id: Number(item.instrument_id ?? 0),
      symbol: String(item.symbol ?? ''),
      available_from: item.available_from ? String(item.available_from) : null,
      available_to: item.available_to ? String(item.available_to) : null,
      requested_first_bar_at: item.requested_first_bar_at ? String(item.requested_first_bar_at) : null,
      requested_last_bar_at: item.requested_last_bar_at ? String(item.requested_last_bar_at) : null,
      total_bars: Number(item.total_bars ?? 0),
      requested_bars: Number(item.requested_bars ?? 0),
      requested_status: String(item.requested_status ?? 'missing'),
      note: item.note ? String(item.note) : null,
      ipo_date: item.ipo_date ? String(item.ipo_date) : null,
    }))
    .filter(item => item.symbol)
}

function coerceStrategyCoverageBenchmark(value: unknown): StrategyCoverageBenchmark {
  if (!value || typeof value !== 'object') {
    return {
      symbol: null,
      preview_note: 'No benchmark coverage detail is available for this run.',
      requested_status: 'unconfigured',
      available_from: null,
      available_to: null,
      requested_first_bar_at: null,
      requested_last_bar_at: null,
      total_bars: 0,
      requested_bars: 0,
      requested_fits_range: null,
    }
  }
  const raw = value as Record<string, any>
  return {
    symbol: raw.symbol ? String(raw.symbol) : null,
    preview_note: raw.preview_note ? String(raw.preview_note) : null,
    requested_status: String(raw.requested_status ?? 'unconfigured'),
    available_from: raw.available_from ? String(raw.available_from) : null,
    available_to: raw.available_to ? String(raw.available_to) : null,
    requested_first_bar_at: raw.requested_first_bar_at ? String(raw.requested_first_bar_at) : null,
    requested_last_bar_at: raw.requested_last_bar_at ? String(raw.requested_last_bar_at) : null,
    total_bars: Number(raw.total_bars ?? 0),
    requested_bars: Number(raw.requested_bars ?? 0),
    requested_fits_range: typeof raw.requested_fits_range === 'boolean' ? raw.requested_fits_range : null,
  }
}

type ComparisonMetricKind = 'percent' | 'money' | 'r' | 'count' | 'plain'
type ComparisonPreference = 'higher' | 'lower'

function formatComparisonValue(value: number, kind: ComparisonMetricKind) {
  if (kind === 'percent') return formatPercent(value)
  if (kind === 'money') return formatMoney(value)
  if (kind === 'r') return formatR(value)
  if (kind === 'count') return `${Math.round(value)}`
  return value.toFixed(2)
}

function formatComparisonDelta(value: number, kind: ComparisonMetricKind) {
  if (!Number.isFinite(value)) return '—'
  if (kind === 'percent') return formatSignedPercent(value)
  if (kind === 'money') {
    return `${value > 0 ? '+' : value < 0 ? '-' : ''}${formatMoney(Math.abs(value))}`
  }
  if (kind === 'r') return `${value > 0 ? '+' : ''}${value.toFixed(2)}R`
  if (kind === 'count') return `${value > 0 ? '+' : ''}${Math.round(value)}`
  return `${value > 0 ? '+' : ''}${value.toFixed(2)}`
}

function comparisonMetric(
  label: string,
  current: unknown,
  compare: unknown,
  kind: ComparisonMetricKind,
  betterWhen: ComparisonPreference,
) {
  const currentValue = Number(current)
  const compareValue = Number(compare)
  const printableCurrent = Number.isFinite(currentValue) ? formatComparisonValue(currentValue, kind) : '—'
  const printableCompare = Number.isFinite(compareValue) ? formatComparisonValue(compareValue, kind) : '—'
  const deltaValue = Number.isFinite(currentValue) && Number.isFinite(compareValue)
    ? currentValue - compareValue
    : Number.NaN
  let winner: 'current' | 'compare' | 'tie' | null = null
  if (Number.isFinite(currentValue) && Number.isFinite(compareValue)) {
    if (Math.abs(currentValue - compareValue) < 0.0001) {
      winner = 'tie'
    } else if (betterWhen === 'higher') {
      winner = currentValue > compareValue ? 'current' : 'compare'
    } else {
      winner = currentValue < compareValue ? 'current' : 'compare'
    }
  }
  return {
    label,
    current: printableCurrent,
    compare: printableCompare,
    delta: Number.isFinite(deltaValue) ? formatComparisonDelta(deltaValue, kind) : '—',
    deltaValue,
    winner,
  }
}

function toPositiveNumber(value: unknown, fallback: number) {
  const numeric = Number(value)
  return Number.isFinite(numeric) && numeric > 0 ? numeric : fallback
}

function humanizeToken(value: string | undefined | null) {
  return String(value ?? '—')
    .replace(/_/g, ' ')
    .replace(/\b\w/g, char => char.toUpperCase())
}

function formatDateTime(value: string | null | undefined) {
  if (!value) return '—'
  return new Date(value).toLocaleString('en-GB', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function formatFullCoverageDateTime(value: string | null | undefined) {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return String(value)
  const day = String(date.getUTCDate()).padStart(2, '0')
  const month = String(date.getUTCMonth() + 1).padStart(2, '0')
  const year = String(date.getUTCFullYear())
  const hours = String(date.getUTCHours()).padStart(2, '0')
  const minutes = String(date.getUTCMinutes()).padStart(2, '0')
  return `${day}/${month}/${year}, ${hours}:${minutes}`
}

function formatShortDateTime(value: string | null | undefined) {
  if (!value) return '—'
  return new Date(value).toLocaleString('en-GB', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function formatPercent(value: unknown) {
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) return '—'
  return `${numeric.toFixed(2)}%`
}

function formatSignedPercent(value: unknown) {
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) return '—'
  return `${numeric > 0 ? '+' : ''}${numeric.toFixed(2)}%`
}

function formatMoney(value: unknown) {
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) return '—'
  return numeric.toLocaleString('en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 2,
  })
}

function formatSignedMoney(value: unknown) {
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) return '—'
  const formatted = formatMoney(Math.abs(numeric))
  if (numeric > 0) return `+${formatted}`
  if (numeric < 0) return `-${formatted}`
  return formatted
}

function pnlClass(value: unknown) {
  const numeric = Number(value)
  return {
    positive: Number.isFinite(numeric) && numeric > 0,
    negative: Number.isFinite(numeric) && numeric < 0,
  }
}

function positiveMetricClass(value: unknown) {
  const numeric = Number(value)
  return {
    positive: Number.isFinite(numeric) && numeric > 0,
    negative: Number.isFinite(numeric) && numeric < 0,
  }
}

function riskCostClass(value: unknown) {
  const numeric = Number(value)
  return {
    negative: Number.isFinite(numeric) && Math.abs(numeric) > 0,
  }
}

function profitFactorClass(value: unknown) {
  const numeric = Number(value)
  return {
    positive: Number.isFinite(numeric) && numeric > 1,
    negative: Number.isFinite(numeric) && numeric < 1,
  }
}

function formatR(value: unknown) {
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) return '—'
  return `${numeric.toFixed(2)}R`
}

function humanizeBarSpan(barCount: number, timeframe: string | null | undefined) {
  const normalizedTimeframe = String(timeframe ?? '').toUpperCase()
  const minutesPerBar = ({
    M1: 1,
    M5: 5,
    M15: 15,
    M30: 30,
    H1: 60,
    H2: 120,
    H4: 240,
    H12: 720,
    D1: 1440,
    W1: 10080,
    MN: 43200,
  } as Record<string, number>)[normalizedTimeframe]

  if (!minutesPerBar || !Number.isFinite(barCount) || barCount <= 0) return ''

  const totalMinutes = barCount * minutesPerBar
  const totalDays = totalMinutes / 1440
  if (totalDays >= 365) {
    const years = Math.floor(totalDays / 365)
    const months = Math.round((totalDays - years * 365) / 30.4375)
    if (months >= 12) return `${years + 1}y`
    return months > 0 ? `${years}y ${months}mo` : `${years}y`
  }
  if (totalDays >= 30) {
    const months = Math.floor(totalDays / 30.4375)
    const days = Math.round(totalDays - months * 30.4375)
    return days > 0 ? `${months}mo ${days}d` : `${months}mo`
  }
  if (totalDays >= 7) {
    const weeks = Math.floor(totalDays / 7)
    const days = Math.round(totalDays - weeks * 7)
    return days > 0 ? `${weeks}w ${days}d` : `${weeks}w`
  }
  if (totalDays >= 1) {
    const days = Math.floor(totalDays)
    const hours = Math.round((totalDays - days) * 24)
    return hours > 0 ? `${days}d ${hours}h` : `${days}d`
  }

  const totalHours = totalMinutes / 60
  if (totalHours >= 1) {
    const hours = Math.floor(totalHours)
    const minutes = Math.round((totalHours - hours) * 60)
    return minutes > 0 ? `${hours}h ${minutes}m` : `${hours}h`
  }

  return `${Math.max(1, Math.round(totalMinutes))}m`
}
</script>

<style scoped>
.strategy-lab-view {
  display: flex;
  height: 100%;
  min-width: 0;
  min-height: 0;
  background: #080808;
  color: #d0d0d0;
  font-family: 'JetBrains Mono', monospace;
}

.strategy-sidebar {
  width: 308px;
  min-width: 272px;
  max-width: 340px;
  border-right: 1px solid #171717;
  background: #0c0c0c;
  display: flex;
  flex-direction: row;
  min-height: 0;
}

.strategy-sidebar--collapsed {
  width: 16px;
  min-width: 16px;
  max-width: 16px;
}

.strategy-sidebar-body {
  flex: 1;
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.sidebar-toggle-strip {
  width: 16px;
  flex-shrink: 0;
  align-self: stretch;
  border: none;
  border-left: 1px solid #1a1a1a;
  background: #0d0d0d;
  color: #444;
  font: inherit;
  font-size: 10px;
  line-height: 1;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  transition: color 120ms ease, background 120ms ease;
}

.sidebar-toggle-strip:hover {
  color: #aaa;
  background: #111;
}

.sidebar-header,
.detail-header,
.panel-head,
.condition-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.subsection-head {
  display: flex;
  align-items: flex-start;
  justify-content: flex-start;
  gap: 12px;
}

.subsection-title {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.sidebar-header {
  padding: 12px 12px 10px;
  border-bottom: 1px solid #171717;
}

.sidebar-header h1,
.detail-header h2,
.panel h3 {
  font-size: 15px;
  color: #f2f2f2;
  margin-bottom: 4px;
}

.sidebar-header p,
.detail-header p,
.panel-head p,
.execution-summary p {
  color: #7e7e7e;
  font-size: 11px;
  line-height: 1.45;
}

.definition-list,
.definition-list--dense {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 10px;
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 8px;
}

.sidebar-new-btn {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  text-align: center;
  font-weight: 600;
}

.definition-item--new {
  border-style: solid;
  border-color: #2b3952;
  color: #7ec2ff;
  background: #10253b;
}

.definition-item--new:hover {
  border-color: #3f5d89;
  color: #d2e4f2;
  background: #14304d;
}

.definition-item,
.run-item {
  width: 100%;
  text-align: left;
  background: #111;
  border: 1px solid #1c1c1c;
  border-radius: 4px;
  padding: 7px 9px;
  cursor: pointer;
  color: inherit;
}

.definition-item {
  min-height: 0;
  padding: 7px 8px;
  flex: 0 0 auto;
}

.definition-item.active,
.run-item.active {
  border-color: #245f93;
  background: #10171d;
}

.definition-head,
.run-item__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.definition-tile {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.definition-tile--dense {
  min-height: 34px;
}

.definition-state-dot {
  width: 8px;
  height: 8px;
  padding: 0;
  flex: 0 0 auto;
}

.definition-copy {
  min-width: 0;
  display: grid;
  gap: 2px;
}

.definition-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 1px;
}

.definition-tag {
  display: inline-flex;
  align-items: center;
  max-width: 100%;
  padding: 1px 6px;
  border-radius: 999px;
  border: 1px solid var(--tag-border);
  background: var(--tag-bg);
  color: var(--tag-color);
  font-size: 9px;
  line-height: 1.2;
  white-space: nowrap;
}

.definition-copy strong,
.definition-copy small {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.definition-copy strong {
  font-size: 11px;
  color: #eef2f5;
}

.definition-meta,
.definition-runline,
.run-item__meta {
  margin-top: 3px;
  color: #7e7e7e;
  font-size: 10px;
  line-height: 1.35;
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.run-item__metric {
  font-weight: 700;
}

.run-item__metric--primary {
  color: #cfd4dc;
}

.run-item__metric--secondary {
  font-size: 9px;
  opacity: 0.86;
}

.run-item__metric--muted {
  font-size: 9px;
  opacity: 0.62;
}

.run-item {
  display: grid;
  grid-template-rows: auto auto;
  align-content: start;
  gap: 4px;
  min-height: 58px;
  padding: 10px 12px;
}

.run-item__header {
  align-items: flex-start;
}

.run-item__header strong {
  font-size: 12px;
  line-height: 1.2;
}

.state-dot,
.status-chip,
.mode-pill {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 999px;
  padding: 3px 8px;
  font-size: 10px;
  border: 1px solid #2b5a3f;
  background: #132417;
  color: #9edfb5;
}

.state-dot.inactive,
.status-chip--failed,
.status-chip--canceled {
  border-color: #673232;
  background: #251515;
  color: #f0aaaa;
}

.status-chip--queued,
.status-chip--running,
.mode-pill {
  border-color: #6a5424;
  background: #231d12;
  color: #e7cb85;
}

.status-chip--completed,
.mode-pill--active,
.symbol-chip--alt {
  border-color: #254f6f;
  background: #111e28;
  color: #8fcaf2;
}

.strategy-main {
  flex: 1;
  min-width: 0;
  min-height: 0;
  overflow: auto;
  padding: 16px;
  display: grid;
  gap: 14px;
  align-content: start;
}

.detail-actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 10px;
}

.panel-head-controls {
  display: inline-flex;
  align-items: center;
  justify-content: flex-end;
  gap: 10px;
  margin-left: auto;
}

.panel-head-title {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.panel-head-heading {
  cursor: pointer;
}

.panel-head-heading:hover {
  color: #f3f3f3;
}

.detail-title-row {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.detail-version-pill {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 22px;
  padding: 0 8px;
  border: 1px solid #27313b;
  border-radius: 999px;
  background: #12171c;
  color: #86b2d4;
  font-size: 11px;
  line-height: 1;
}

.detail-columns {
  display: grid;
  gap: 16px;
}

.panel,
.condition-card,
.equity-panel,
.mini-panel {
  background: #111;
  border: 1px solid #1b1b1b;
  border-radius: 4px;
}

.summary-label {
  color: #6f6f6f;
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  line-height: 1;
}

.summary-card strong {
  color: #f2f2f2;
  font-size: 16px;
  line-height: 1.1;
  display: block;
}

.summary-card small,
.equity-panel__head span {
  color: #7c7c7c;
  font-size: 11px;
  line-height: 1.4;
}

.summary-breakdown {
  display: grid;
  gap: 3px;
}

.summary-breakdown small {
  display: flex;
  justify-content: space-between;
  gap: 10px;
}

.summary-breakdown b {
  color: #cfd4dc;
  font-weight: 700;
  text-align: right;
}

.summary-breakdown__primary b {
  font-size: 12px;
}

.summary-breakdown__secondary {
  opacity: 0.88;
}

.summary-breakdown__secondary b {
  font-size: 10px;
}

.summary-breakdown__muted {
  opacity: 0.68;
}

.summary-breakdown__muted b {
  font-size: 10px;
  font-weight: 600;
}

.detail-columns {
  grid-template-columns: minmax(0, 1fr);
  align-items: stretch;
}

.panel {
  padding: 14px;
  display: grid;
  gap: 14px;
  min-width: 0;
}

.panel-body {
  display: grid;
  gap: 14px;
  min-width: 0;
}

.panel-toggle {
  padding: 0;
  border: none;
  background: transparent;
  color: #9e9e9e;
  font: inherit;
  font-size: 11px;
  line-height: 1;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  transition: color 140ms ease;
}

.panel-toggle:hover {
  color: #e1e1e1;
}

.panel-toggle__icon {
  display: inline-block;
  transform: rotate(0deg);
  transform-origin: center;
  transition: transform 140ms ease, color 140ms ease;
}

.panel-toggle__icon--expanded {
  transform: rotate(90deg);
}

.subsection,
.run-detail {
  display: grid;
  gap: 8px;
}

.coverage-preview-section,
.coverage-detail-panel {
  display: grid;
  gap: 10px;
}

.subsection h4,
.panel--results h4,
.equity-panel strong {
  color: #f0f0f0;
  font-size: 12px;
}

.form-grid {
  display: grid;
  gap: 12px;
}

.form-grid.two-up {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.form-grid.three-up {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.field {
  display: grid;
  gap: 6px;
}

.field--full {
  grid-column: 1 / -1;
}

.field--checkbox {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding-top: 0;
  color: #b4b4b4;
  font-size: 12px;
}

.field--sweep {
  align-content: start;
}

.field-label {
  color: #8d8d8d;
  font-size: 11px;
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.sweep-indicator {
  padding: 0;
  display: inline-grid;
  grid-template-columns: repeat(2, 4px);
  grid-template-rows: repeat(2, 4px);
  gap: 3px;
  width: 18px;
  height: 18px;
  place-content: center;
  border: 1px solid rgba(126, 194, 255, 0.32);
  border-radius: 6px;
  background: rgba(34, 96, 154, 0.12);
  box-shadow: inset 0 0 10px rgba(126, 194, 255, 0.04);
  cursor: pointer;
}

.sweep-indicator span {
  width: 4px;
  height: 4px;
  border-radius: 2px;
  background: #9ed0ff;
  opacity: 0.82;
}

.sweep-indicator--single {
  place-content: center;
}

.sweep-indicator--single span {
  display: none;
}

.sweep-indicator--single span:first-child {
  display: block;
}

.sweep-indicator--range {
  display: inline-flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 4px;
}

.sweep-indicator--range span {
  display: none;
}

.sweep-indicator--range span:first-child,
.sweep-indicator--range span:nth-child(3) {
  display: block;
  width: 4px;
  height: 4px;
  border-radius: 999px;
}

.sweep-indicator--range span:nth-child(2) {
  display: block;
  width: 7px;
  height: 2px;
  border-radius: 999px;
}

.advanced-toggle {
  width: fit-content;
  display: inline-flex;
  align-items: center;
  gap: 10px;
  padding: 0;
  border: none;
  background: transparent;
  color: #9d9d9d;
  font: inherit;
  font-size: 11px;
  cursor: pointer;
}

.advanced-toggle:hover {
  color: #d0d0d0;
}

.advanced-toggle__title {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.advanced-toggle__icon {
  display: inline-block;
  transform: rotate(0deg);
  transform-origin: center;
  transition: transform 140ms ease, color 140ms ease;
}

.advanced-toggle__icon--expanded {
  transform: rotate(90deg);
}

.advanced-panel {
  display: grid;
  gap: 10px;
  margin-top: 10px;
}

.field-inline-hint {
  color: #d7a06d;
  font-size: 10px;
  letter-spacing: 0.02em;
  text-transform: none;
}

.form-input,
.form-select,
.form-textarea {
  width: 100%;
  border: 1px solid #2a2a2a;
  border-radius: 3px;
  background: #141414;
  color: #ccc;
  padding: 5px 8px;
  font: inherit;
  font-size: 12px;
  min-width: 0;
  box-sizing: border-box;
}

.form-select {
  min-height: 32px;
}

.form-input--invalid,
.form-select--invalid,
.form-textarea--invalid {
  border-color: #6c3b3b;
  box-shadow: 0 0 0 1px rgba(108, 59, 59, 0.18);
}

.form-textarea {
  min-height: 92px;
  resize: vertical;
}

.form-textarea--short {
  min-height: 82px;
}

.chip-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  min-height: 30px;
}

.symbol-chip {
  display: inline-flex;
  align-items: center;
  justify-content: flex-start;
  align-self: flex-start;
  flex: 0 0 auto;
  width: auto;
  max-width: 100%;
  min-height: 24px;
  gap: 6px;
  padding: 4px 10px;
  border-radius: 999px;
  font-size: 11px;
  line-height: 1;
  white-space: nowrap;
  border: 1px solid #2b5a3f;
  background: #132417;
  color: #9edfb5;
}

.symbol-chip button,
.icon-btn {
  border: none;
  background: transparent;
  color: inherit;
  cursor: pointer;
  font: inherit;
}

.symbol-chip button {
  padding: 0;
  line-height: 1;
}

.inline-search {
  display: flex;
  width: 100%;
}

.inline-search :deep(.search-input-wrap) {
  min-height: 32px;
  border-color: #232323;
  border-radius: 3px;
  background: #0b0b0b;
}

.inline-search :deep(.search-input) {
  font-size: 11px;
  color: #c8c8c8;
}

.field :deep(.search-input-wrap) {
  min-height: 32px;
  border-color: #232323;
  border-radius: 3px;
  background: #0b0b0b;
}

.field :deep(.search-input) {
  font-size: 11px;
  color: #c8c8c8;
}

.multi-select-field {
  position: relative;
}

.multi-select-trigger {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  min-height: 32px;
  background: #050505;
  color: #ccc;
  border: 1px solid #282828;
  border-radius: 4px;
  padding: 7px 8px;
  font-family: inherit;
  font-size: 11px;
  cursor: pointer;
}

.multi-select-caret {
  color: #777;
  flex-shrink: 0;
}

.multi-select-menu {
  position: absolute;
  top: calc(100% + 6px);
  left: 0;
  right: 0;
  z-index: 4;
  display: flex;
  flex-direction: column;
  gap: 6px;
  max-height: 248px;
  overflow: auto;
  background: #101010;
  border: 1px solid #2b2b2b;
  border-radius: 6px;
  padding: 8px;
  box-shadow: 0 16px 32px rgba(0, 0, 0, 0.42);
}

.multi-select-option {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #b8b8b8;
  font-size: 11px;
}

.multi-select-option input {
  margin: 0;
}

.multi-select-clear {
  margin-top: 4px;
  align-self: flex-start;
  background: #171717;
  color: #9fbfe4;
  border: 1px solid #2f2f2f;
  border-radius: 4px;
  padding: 5px 7px;
  font-family: inherit;
  font-size: 10px;
  cursor: pointer;
}

.condition-list,
.run-list {
  display: grid;
  gap: 12px;
}

.scroll-list-section {
  display: grid;
  gap: 8px;
}

.scroll-list-toggle {
  display: inline-flex;
  align-items: center;
  justify-self: start;
  gap: 7px;
  padding: 0;
  border: 0;
  background: transparent;
  color: #d8d8d8;
  font-family: inherit;
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
}

.scroll-list-toggle:hover,
.scroll-list-toggle:focus-visible {
  color: #f2f2f2;
  outline: none;
}

.scroll-list-toggle__icon {
  display: inline-block;
  color: #898989;
  transform: rotate(0deg);
  transition: transform 0.16s ease, color 0.16s ease;
}

.scroll-list-toggle__icon--expanded {
  transform: rotate(90deg);
  color: #8fcaf2;
}

.scroll-list-toggle small {
  color: #858585;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.run-list {
  gap: 8px;
  max-height: 332px;
  overflow: auto;
  padding-right: 2px;
}

.run-batch {
  display: grid;
  gap: 8px;
  border: 1px solid #222831;
  border-radius: 8px;
  background: #0f1114;
  padding: 10px;
}

.run-batch--active {
  border-color: #1f6ca8;
  background: #0d1720;
}

.run-batch__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
  padding: 0;
  border: 0;
  background: transparent;
  color: #e3e7ee;
  font: inherit;
  text-align: left;
  cursor: pointer;
}

.run-batch__head:hover,
.run-batch__head:focus-visible {
  color: #ffffff;
  outline: none;
}

.run-batch__head > span:first-child {
  display: grid;
  gap: 2px;
}

.run-batch__head small {
  color: #8b93a1;
  font-size: 10px;
}

.run-batch__summary,
.run-batch__parameters,
.run-batch__runs {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.run-batch__summary span,
.run-batch__parameters span {
  border: 1px solid #252c35;
  border-radius: 999px;
  padding: 3px 7px;
  background: #101720;
  color: #a9b2c0;
  font-size: 10px;
  font-weight: 800;
}

.run-batch__parameters span {
  color: #90caff;
}

.run-batch__runs {
  display: grid;
  gap: 6px;
}

.condition-card {
  padding: 14px;
  display: grid;
  gap: 12px;
}

.condition-grid {
  display: grid;
  gap: 10px;
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.rule-preview,
.execution-summary {
  padding: 10px 12px;
  border-radius: 4px;
  border: 1px solid #21262c;
  background: #0d1116;
}

.tree-builder-note,
.run-mode-note {
  padding: 10px 12px;
  border-radius: 4px;
  border: 1px solid #21262c;
  background: #0d1116;
  color: #8ea7ba;
  font-size: 11px;
  line-height: 1.55;
}

.tree-builder-note--compact {
  margin-top: -4px;
}

.cb-header--strategy {
  margin-bottom: 0;
}

.section-label,
.tree-builder-kicker {
  font-size: 10px;
  color: #666;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.tree-builder-note code {
  color: #d4e7f4;
}

.rule-preview__label {
  display: block;
  margin-bottom: 6px;
  color: #6fa7d2;
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.rule-preview p,
.execution-summary strong {
  color: #d4e7f4;
  font-size: 12px;
  line-height: 1.5;
}

.mode-strip {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.mode-pill {
  cursor: pointer;
}

.run-summary-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.summary-card {
  padding: 12px;
  border: 1px solid #1f2328;
  border-radius: 4px;
  background: #0c0f12;
  display: grid;
  gap: 5px;
}

.result-layout {
  display: grid;
  grid-template-columns: minmax(280px, 0.85fr) minmax(0, 1.35fr);
  gap: 16px;
}

.result-column {
  display: grid;
  gap: 16px;
}

.result-panels-grid {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  gap: 12px;
}

.mini-panel {
  flex: 1 1 calc(50% - 6px);
  min-width: min(100%, 320px);
  padding: 12px;
  display: grid;
  gap: 10px;
}

.mini-panel--returns {
  flex-basis: 100%;
}

.mini-panel--wide {
  flex-basis: 100%;
}

.equity-panel,
.warnings-panel {
  padding: 12px;
}

.equity-panel__head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
}

.equity-panel__head-meta {
  display: inline-flex;
  align-items: center;
  gap: 10px;
}

.chart-mode-toggle {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px;
  border: 1px solid #23262b;
  border-radius: 999px;
  background: #101113;
}

.chart-mode-toggle__button {
  min-width: 28px;
  height: 24px;
  border: 0;
  border-radius: 999px;
  background: transparent;
  color: #7f848b;
  font: inherit;
  font-size: 11px;
  font-weight: 700;
  cursor: pointer;
  transition: background-color 0.14s ease, color 0.14s ease;
}

.chart-mode-toggle__button:hover {
  color: #d4d7dc;
}

.chart-mode-toggle__button--active {
  background: #1f5f9a;
  color: #eff6ff;
}

.equity-panel__footnote {
  margin-top: 8px;
  color: #7d7d7d;
  font-size: 11px;
  line-height: 1.4;
}

.equity-chart {
  width: 100%;
  height: 140px;
  background: #0a0a0a;
  border: 1px solid #1a1a1a;
  border-radius: 10px;
}

.detail-list {
  list-style: none;
  display: grid;
  gap: 8px;
  color: #b4b4b4;
  font-size: 12px;
  line-height: 1.5;
}

.detail-list--benchmark-meta {
  gap: 10px;
}

.detail-list--performance-meta {
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px solid #1f252c;
}

.detail-list--benchmark-meta > div {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  color: #9d9d9d;
  font-size: 11px;
}

.detail-list--benchmark-meta strong {
  color: #e8e8e8;
  font-size: 12px;
}

.detail-list--benchmark-meta .detail-list__secondary-value {
  font-size: 11px;
  opacity: 0.86;
}

.detail-list--benchmark-meta .detail-list__muted-value {
  font-size: 11px;
  opacity: 0.7;
}

.trade-table-wrap {
  padding: 12px;
  border: 1px solid #1f1f1f;
  border-radius: 4px;
  background: #111;
}

.trade-table-scroll {
  overflow: auto;
  margin-inline: -12px;
  margin-bottom: -12px;
}

.trade-table {
  width: 100%;
  border-collapse: collapse;
  min-width: 720px;
}

.trade-table th,
.trade-table td {
  padding: 10px 12px;
  border-bottom: 1px solid #1c1c1c;
  font-size: 11px;
  text-align: left;
  white-space: nowrap;
}

.trade-table th {
  color: #7d7d7d;
  background: #0f0f0f;
  position: sticky;
  top: 0;
  z-index: 2;
}

.trade-table__head-cell {
  position: relative;
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  gap: 8px;
}

.trade-table__sort {
  width: 100%;
  display: inline-flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 0;
  border: 0;
  background: transparent;
  color: inherit;
  font: inherit;
  font-weight: 800;
  letter-spacing: 0.04em;
  text-align: left;
  cursor: pointer;
}

.trade-table__filter-button {
  display: inline-grid;
  place-items: center;
  width: 22px;
  height: 22px;
  border: 1px solid transparent;
  border-radius: 999px;
  background: transparent;
  color: #59616e;
  font: inherit;
  font-size: 12px;
  cursor: pointer;
}

.trade-table__filter-button:hover,
.trade-table__filter-button:focus-visible,
.trade-table__filter-button--active {
  border-color: #254761;
  background: #0d1a25;
  color: #7ec2ff;
  outline: none;
}

.trade-table__filter-popover {
  position: absolute;
  top: calc(100% + 8px);
  left: 0;
  z-index: 20;
  width: min(220px, calc(100vw - 32px));
  display: grid;
  gap: 8px;
  padding: 10px;
  border: 1px solid #263142;
  border-radius: 8px;
  background: #0c1119;
  box-shadow: 0 18px 36px rgba(0, 0, 0, 0.42);
}

.trade-table__filter-popover-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  color: #9aa6b8;
  font-size: 10px;
  font-weight: 800;
  letter-spacing: 0.07em;
  text-transform: uppercase;
}

.trade-table__filter-popover-head button {
  border: 0;
  background: transparent;
  color: #ff9aa7;
  font: inherit;
  font-size: 14px;
  cursor: pointer;
}

.trade-table__filter-clear {
  justify-self: start;
  border: 0;
  background: transparent;
  color: #7ec2ff;
  font: inherit;
  font-size: 10px;
  cursor: pointer;
}

.trade-table__sort:hover,
.trade-table__sort:focus-visible {
  color: #d5deeb;
  outline: none;
}

.trade-table__sort-icon {
  color: #575f6c;
  font-size: 9px;
}

.trade-table__sort-icon--active {
  color: #7ec2ff;
}

.trade-table__filter {
  width: 100%;
  border: 1px solid #242b34;
  border-radius: 6px;
  background: #0b0d10;
  color: #d7dce5;
  font: inherit;
  font-size: 10px;
  padding: 6px 7px;
}

.trade-table__filter::placeholder {
  color: #5f6672;
}

.trade-table__filter:focus {
  border-color: #2b6ea9;
  outline: none;
  box-shadow: 0 0 0 1px rgba(126, 194, 255, 0.26);
}

.trade-table__empty {
  color: #737373;
  text-align: center;
}

.pnl-cell {
  display: grid;
  gap: 2px;
}

.pnl-cell strong {
  font-weight: 700;
}

.pnl-cell small {
  color: #7d7d7d;
  font-size: 10px;
  line-height: 1.2;
}

.execution-reason-cell {
  display: grid;
  gap: 2px;
}

.execution-reason-cell strong {
  font-weight: 700;
}

.execution-reason-cell small {
  color: #7d8796;
  font-size: 10px;
  line-height: 1.25;
}

.positive {
  color: #90d89e;
}

.negative {
  color: #ef9e9e;
}

.btn-primary,
.btn-secondary,
.btn-danger {
  border-radius: 3px;
  padding: 7px 10px;
  font: inherit;
  font-size: 11px;
  cursor: pointer;
  border: 1px solid #2b3952;
}

.btn-primary {
  background: #10253b;
  color: #7ec2ff;
}

.btn-secondary {
  background: #111;
  color: #bbb;
  border-color: #2a2a2a;
}

.btn-danger {
  background: #1d1112;
  color: #efb1b1;
  border-color: #5a2d30;
}

.btn-icon-only {
  width: 30px;
  min-width: 30px;
  height: 30px;
  padding: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.btn-icon-only svg {
  width: 14px;
  height: 14px;
  fill: none;
  stroke: currentColor;
  stroke-width: 1.4;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.export-menu {
  position: relative;
}

.export-menu__trigger {
  width: auto;
  min-width: 42px;
  padding: 0 6px;
  gap: 3px;
}

.export-menu__caret {
  font-size: 9px;
  color: #8c8c8c;
  line-height: 1;
}

.export-menu__panel {
  position: absolute;
  top: calc(100% + 6px);
  right: 0;
  min-width: 148px;
  display: grid;
  gap: 2px;
  padding: 6px;
  border: 1px solid #262626;
  border-radius: 4px;
  background: #111;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.35);
  z-index: 12;
}

.export-menu__item {
  width: 100%;
  padding: 7px 8px;
  border: 1px solid transparent;
  border-radius: 4px;
  background: transparent;
  color: #d4d4d4;
  font: inherit;
  font-size: 11px;
  text-align: left;
  cursor: pointer;
}

.export-menu__item:hover {
  background: #171717;
  border-color: #2a2a2a;
}

.help-dot {
  width: 16px;
  height: 16px;
  border-radius: 999px;
  border: 1px solid #384149;
  background: #12171c;
  color: #86b2d4;
  font-size: 10px;
  line-height: 1;
  cursor: help;
}

.error-banner,
.empty-state,
.empty-inline {
  color: #8a8a8a;
  font-size: 12px;
}

.error-banner {
  padding: 10px 12px;
  border: 1px solid #553030;
  background: #211414;
  color: #e1a5a5;
  border-radius: 10px;
}

@media (max-width: 1380px) {
  .run-summary-grid,
  .result-panels-grid {
    gap: 12px;
  }

  .condition-grid,
  .form-grid.three-up {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 1180px) {
  .detail-columns,
  .result-layout {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 920px) {
  .strategy-lab-view {
    flex-direction: column;
  }

  .strategy-sidebar {
    width: 100%;
    max-width: none;
    min-width: 0;
    border-right: none;
    border-bottom: 1px solid #171717;
  }

  .form-grid.two-up,
  .form-grid.three-up,
  .run-summary-grid,
  .result-panels-grid {
    grid-template-columns: 1fr;
  }

  .mini-panel {
    flex-basis: 100%;
    min-width: 0;
  }
}
</style>
