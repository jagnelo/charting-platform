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
              <label class="field">
                <span class="field-label">
                  {{ logicDraft.stop_model === 'atr' ? 'ATR period' : 'Stop loss %' }}
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
                  <input v-model.number="logicDraft.stop_loss_pct" type="number" min="0.1" step="0.1" class="form-input" />
                </template>
              </label>
              <label class="field">
                <span class="field-label">
                  {{ logicDraft.stop_model === 'atr' ? 'ATR multiple' : 'Hard trail %' }}
                  <HoverTooltip :text="logicDraft.stop_model === 'atr'
                    ? 'Distance from entry to the initial stop, expressed as a multiple of ATR.'
                    : 'A percent-based trailing stop measured from the best price reached after entry. Set to 0 to disable this hard trailing stop.'">
                    <button type="button" class="help-dot" :aria-label="logicDraft.stop_model === 'atr' ? 'ATR multiple info' : 'Hard trailing stop info'">i</button>
                  </HoverTooltip>
                </span>
                <template v-if="logicDraft.stop_model === 'atr'">
                  <input v-model.number="logicDraft.stop_atr_multiple" type="number" min="0.1" step="0.1" class="form-input" />
                </template>
                <template v-else>
                  <input v-model.number="logicDraft.hard_trailing_stop_pct" type="number" min="0" step="0.1" class="form-input" />
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
                  <HoverTooltip text="Move the stop to the entry price once the trade reaches this many R units in open profit. 1R equals the initial stop distance.">
                    <button type="button" class="help-dot" aria-label="Break-even info">i</button>
                  </HoverTooltip>
                </span>
                <input v-model.number="logicDraft.break_even_rr" type="number" min="0" step="0.25" class="form-input" />
              </label>
              <label class="field">
                <span class="field-label">
                  Trail distance (R)
                  <HoverTooltip text="Trailing stop distance expressed in R units, not percent. 1R equals the initial stop distance. Example: 1.5R trails the stop 1.5 initial-risk units behind the best price reached.">
                    <button type="button" class="help-dot" aria-label="Trailing stop info">i</button>
                  </HoverTooltip>
                </span>
                <input v-model.number="logicDraft.trailing_stop_rr" type="number" min="0" step="0.25" class="form-input" />
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
              <label class="field">
                <span class="field-label">
                  Target (R)
                  <HoverTooltip text="Take profit expressed as a multiple of the initial risk distance. Set to 0 to disable fixed profit targets and rely on condition-based or time-based exits instead.">
                    <button type="button" class="help-dot" aria-label="Target info">i</button>
                  </HoverTooltip>
                </span>
                <input v-model.number="logicDraft.take_profit_rr" type="number" min="0" step="0.25" class="form-input" />
              </label>
              <label class="field">
                <span class="field-label">
                  Max bars in trade
                  <HoverTooltip text="If greater than 0, close the trade after this many bars if no other exit fired first. Set to 0 to disable time-based exits.">
                    <button type="button" class="help-dot" aria-label="Max bars info">i</button>
                  </HoverTooltip>
                </span>
                <input v-model.number="logicDraft.max_bars_in_trade" type="number" min="0" step="1" class="form-input" />
              </label>
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
              <input v-model.number="runDraft.slippage_bps" type="number" min="0" step="1" class="form-input" />
            </label>
            <label class="field">
              <span class="field-label">Commission per trade</span>
              <input v-model.number="runDraft.commission_per_trade" type="number" min="0" step="0.1" class="form-input" />
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

          <div class="subsection">
            <div class="subsection-head">
              <div class="subsection-title">
                <h4>Parameter sweep</h4>
                <HoverTooltip text="Turn this on to evaluate a small grid of stop, target, and holding-period combinations alongside the main run.">
                  <button type="button" class="help-dot" aria-label="Parameter sweep info">i</button>
                </HoverTooltip>
              </div>
            </div>
            <label class="field field--checkbox">
              <input v-model="runDraft.optimization_enabled" type="checkbox" />
              <span>Evaluate parameter sweep leaderboard</span>
            </label>
            <div v-if="runDraft.optimization_enabled" class="form-grid three-up">
              <label class="field">
                <span class="field-label">Stop % values</span>
                <input v-model="runDraft.stop_loss_pct_values" class="form-input" placeholder="1.5, 2, 2.5, 3" />
              </label>
              <label class="field">
                <span class="field-label">Target R values</span>
                <input v-model="runDraft.take_profit_rr_values" class="form-input" placeholder="1.5, 2, 2.5, 3" />
              </label>
              <label class="field">
                <span class="field-label">Max bars values</span>
                <input v-model="runDraft.max_bars_in_trade_values" class="form-input" placeholder="10, 15, 20, 30" />
              </label>
            </div>
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

          <div class="run-list">
            <button
              v-for="run in selectedRuns"
              :key="run.id"
              type="button"
              class="run-item"
              :class="{ active: strategyLab.selectedRunId === run.id }"
              @click="strategyLab.selectedRunId = run.id"
            >
              <div class="run-item__header">
                <strong>{{ formatDateTime(run.created_at) }}</strong>
                <span class="status-chip" :class="`status-chip--${run.status}`">{{ humanizeToken(run.status) }}</span>
              </div>
              <div class="run-item__meta">
                <span>{{ run.timeframe || currentVersion?.definition_snapshot?.timeframe || 'D1' }}</span>
                <span>·</span>
                <span>{{ run.result_summary?.performance?.trade_count ?? 0 }} trades</span>
                <span v-if="run.result_summary?.performance?.net_return_pct != null">· {{ formatPercent(run.result_summary.performance.net_return_pct) }}</span>
              </div>
            </button>
            <div v-if="!selectedRuns.length" class="empty-state empty-state--small">No backtests yet.</div>
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
              <span class="summary-label">Net return</span>
              <strong>{{ formatPercent(performance.net_return_pct) }}</strong>
              <small v-if="(performance.open_position_count ?? 0) > 0">
                {{ performance.closed_trade_count ?? performance.trade_count ?? 0 }} closed ·
                {{ performance.open_position_count ?? 0 }} open ·
                {{ formatMoney(performance.unrealized_pnl) }} unrealized
              </small>
              <small v-else>{{ performance.closed_trade_count ?? performance.trade_count ?? 0 }} closed</small>
            </div>
            <div class="summary-card">
              <span class="summary-label">Win rate</span>
              <strong>{{ formatPercent(performance.win_rate) }}</strong>
              <small>{{ performance.expectancy_r != null ? `${performance.expectancy_r.toFixed(2)}R expectancy` : 'No expectancy yet' }}</small>
            </div>
            <div class="summary-card">
              <span class="summary-label">Drawdown</span>
              <strong>{{ formatPercent(performance.max_drawdown_pct) }}</strong>
              <small>{{ performance.profit_factor != null ? `${performance.profit_factor.toFixed(2)} profit factor` : 'Profit factor unavailable' }}</small>
            </div>
            <div class="summary-card">
              <span class="summary-label">Coverage</span>
              <strong>{{ selectedRunDetail.result_summary.coverage?.total_bars ?? 0 }} bars</strong>
              <small>
                <template v-if="coverageDurationLabel">{{ coverageDurationLabel }} · </template>
                {{ selectedRunDetail.result_summary.coverage?.instruments_with_data ?? 0 }} symbols with data
              </small>
            </div>
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
                <div v-if="benchmarkCoverageNote" class="equity-panel__footnote">
                  {{ benchmarkCoverageNote }}
                </div>
                <div v-if="selectedRunDetail.result_summary.benchmark_comparison?.excess_return_pct != null" class="equity-panel__footnote">
                  {{ formatPercent(selectedRunDetail.result_summary.benchmark_comparison?.excess_return_pct) }} excess versus benchmark
                </div>
              </div>

              <div class="equity-panel">
                <div class="equity-panel__head">
                  <strong>Benchmark</strong>
                  <span>{{ selectedRunDetail.result_summary.benchmark?.symbol || 'No benchmark' }}</span>
                </div>
                <div class="detail-list detail-list--benchmark-meta">
                  <div>
                    <span>Benchmark return</span>
                    <strong>{{ benchmarkReturnLabel }}</strong>
                  </div>
                  <div>
                    <span>Strategy return</span>
                    <strong>{{ strategyReturnLabel }}</strong>
                  </div>
                  <div v-if="benchmarkMaxDrawdownLabel !== '—'">
                    <span>Benchmark drawdown</span>
                    <strong>{{ benchmarkMaxDrawdownLabel }}</strong>
                  </div>
                  <div v-if="benchmarkHoldSpanLabel !== '—'">
                    <span>Hold span</span>
                    <strong>{{ benchmarkHoldSpanLabel }}</strong>
                  </div>
                </div>
                <div v-if="!benchmarkCurve.length" class="empty-inline">No benchmark curve for this run yet.</div>
                <div v-else-if="benchmarkCoverageNote" class="equity-panel__footnote">
                  {{ benchmarkCoverageNote }}
                </div>
                <StrategyResultChart
                  v-if="benchmarkPositionSeries.length"
                  :series="benchmarkPositionSeries"
                  label="Benchmark buy-and-hold position"
                  :percent="true"
                  :show-legend="false"
                  :height="120"
                  empty-label="No benchmark position path for this run yet."
                />
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
                  <div class="subsection-head"><h4>Per symbol</h4></div>
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
                  <div class="subsection-head"><h4>R distribution</h4></div>
                  <DistributionBars
                    :rows="tradeDistributions.r_histogram"
                    :trades="visibleTrades"
                    empty-label="No R distribution yet."
                  />
                </div>
              </div>

              <div class="trade-table-wrap">
                <div class="subsection-head subsection-head--table">
                  <h4>Execution log</h4>
                </div>
                <table class="trade-table">
                  <thead>
                    <tr>
                      <th>Time</th>
                      <th>Event</th>
                      <th>Symbol</th>
                      <th>Side</th>
                      <th>Price</th>
                      <th>Size</th>
                      <th>P&amp;L</th>
                      <th>Reason</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="event in executionLog" :key="`${event.position_id}-${event.event_type}-${event.ts}`">
                      <td>{{ formatShortDateTime(event.ts) }}</td>
                      <td>{{ humanizeToken(event.event_type) }}</td>
                      <td>{{ event.symbol || '—' }}</td>
                      <td>{{ event.side ? humanizeToken(event.side) : '—' }}</td>
                      <td>{{ event.price != null ? formatMoney(event.price) : '—' }}</td>
                      <td>{{ event.quantity != null ? Number(event.quantity).toFixed(2) : '—' }}</td>
                      <td :class="{ positive: Number(event.pnl) > 0, negative: Number(event.pnl) < 0 }">
                        <div v-if="event.pnl != null" class="pnl-cell">
                          <strong>{{ formatMoney(event.pnl) }}</strong>
                          <small v-if="event.pnl_pct != null">{{ formatSignedPercent(event.pnl_pct) }}</small>
                        </div>
                        <template v-else>—</template>
                      </td>
                      <td>{{ humanizeToken(event.reason || event.event_type) }}</td>
                    </tr>
                    <tr v-if="!executionLog.length">
                      <td colspan="8" class="trade-table__empty">No execution events were recorded for this run.</td>
                    </tr>
                  </tbody>
                </table>
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
import OptimizationLeaderboard from '@/components/strategy/OptimizationLeaderboard.vue'
import PaperForwardMonitorPanel from '@/components/strategy/PaperForwardMonitorPanel.vue'
import ReturnsHeatmap from '@/components/strategy/ReturnsHeatmap.vue'
import RunComparisonTable from '@/components/strategy/RunComparisonTable.vue'
import SignalReplayBreakdown from '@/components/strategy/SignalReplayBreakdown.vue'
import SymbolPerformanceBars from '@/components/strategy/SymbolPerformanceBars.vue'
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
import type { StrategyDefinition, StrategyRun, StrategyVersion, Watchlist } from '@/types'

type StrategyUniverseMode = 'radar' | 'symbols' | 'watchlist' | 'screener'
type StrategyLabSectionKey = 'profile' | 'entry' | 'risk' | 'exits' | 'runs' | 'results'
type StrategyLabSectionState = Record<StrategyLabSectionKey, boolean>
type StrategyLabStoredSectionStates = Record<string, Partial<StrategyLabSectionState>>

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
const isNew = ref(false)
const versionNotes = ref('')
const symbolInput = ref('')
const sourceType = ref<'custom' | 'radar'>('custom')
const universeMode = ref<StrategyUniverseMode>('symbols')
const selectedWatchlistId = ref<number | null>(null)
const selectedScreenerId = ref<number | null>(null)
const compareRunId = ref<number | null>(null)
const showDeleteModal = ref(false)
const radarSetupMenuOpen = ref(false)
const radarStateMenuOpen = ref(false)
const showAdvancedRunOptions = ref(false)
const runSubsetMenuOpen = ref(false)
const exportMenuOpen = ref(false)
const exportMenuRef = ref<HTMLElement | null>(null)
const sidebarWidth = ref(initialSidebarState.width)
const sidebarCollapsed = ref(initialSidebarState.collapsed)
const storedSectionStates = ref<StrategyLabStoredSectionStates>(initialSectionStates)
const sectionExpanded = ref<StrategyLabSectionState>(defaultSectionState(false))

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
  stop_loss_pct: 2,
  stop_atr_period: 14,
  stop_atr_multiple: 2,
  hard_trailing_stop_pct: 0,
  hard_trailing_activation_pct: 0,
  take_profit_rr: 2,
  max_bars_in_trade: 20,
  break_even_rr: 0,
  trailing_stop_rr: 0,
  position_sizing_mode: 'percent_risk' as 'percent_risk' | 'fixed_cash' | 'percent_capital' | 'fixed_quantity',
  position_sizing_value: 1,
  pyramiding_max_entries: 1,
  benchmark_symbol: 'SPY',
  symbols: [] as string[],
  ruleTree: createGroupNode('all', []) as BuilderGroupNode,
  exitRuleTree: createGroupNode('all', []) as BuilderGroupNode,
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
  slippage_bps: 5,
  commission_per_trade: 0,
  walk_forward_segments: 3,
  walk_forward_training_share: 0.6,
  paper_forward_bars: 20,
  max_concurrent_positions: 4,
  max_portfolio_risk_pct: 4,
  max_symbol_allocation_pct: 35,
  optimization_enabled: false,
  stop_loss_pct_values: '1.5, 2, 2.5, 3',
  take_profit_rr_values: '1.5, 2, 2.5, 3',
  max_bars_in_trade_values: '10, 15, 20, 30',
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
const availableRunSubsetSymbols = computed(() => {
  if (universeMode.value === 'symbols') return [...logicDraft.symbols]
  if (universeMode.value === 'watchlist') {
    return normalizeSymbols((selectedWatchlist.value?.items ?? []).map(item => item.symbol || item.name || ''))
  }
  return []
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

const selectedRuns = computed<StrategyRun[]>(() => strategyLab.selectedDefinition?.runs ?? [])
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

const coverageDurationLabel = computed(() => {
  const coverage = selectedRunDetail.value?.result_summary?.coverage
  const totalBars = Number(coverage?.total_bars ?? 0)
  const instrumentsWithData = Math.max(1, Number(coverage?.instruments_with_data ?? 0) || 1)
  if (!Number.isFinite(totalBars) || totalBars <= 0) return ''
  const timeframe = String(
    selectedRunDetail.value?.timeframe
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

const executionLog = computed<any[]>(() => {
  const rows = Array.isArray(selectedRunDetail.value?.result_summary?.execution_log)
    ? selectedRunDetail.value?.result_summary?.execution_log
    : []
  return [...rows].sort((left, right) => String(left.ts ?? '').localeCompare(String(right.ts ?? '')))
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
    comparisonMetric('Net return', selectedRunDetail.value.result_summary?.performance?.net_return_pct, compareRun.value.result_summary?.performance?.net_return_pct, 'percent', 'higher'),
    comparisonMetric('Win rate', selectedRunDetail.value.result_summary?.performance?.win_rate, compareRun.value.result_summary?.performance?.win_rate, 'percent', 'higher'),
    comparisonMetric('Expectancy', selectedRunDetail.value.result_summary?.performance?.expectancy_r, compareRun.value.result_summary?.performance?.expectancy_r, 'r', 'higher'),
    comparisonMetric('Drawdown', selectedRunDetail.value.result_summary?.performance?.max_drawdown_pct, compareRun.value.result_summary?.performance?.max_drawdown_pct, 'percent', 'lower'),
    comparisonMetric('Trade count', selectedRunDetail.value.result_summary?.performance?.trade_count, compareRun.value.result_summary?.performance?.trade_count, 'count', 'higher'),
    comparisonMetric('Unrealized', selectedRunDetail.value.result_summary?.performance?.unrealized_pnl, compareRun.value.result_summary?.performance?.unrealized_pnl, 'money', 'higher'),
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

const benchmarkReturnLabel = computed(() => formatSeriesReturn(benchmarkCurve.value, 'equity'))
const benchmarkMaxDrawdownLabel = computed(() =>
  formatPercent(selectedRunDetail.value?.result_summary?.benchmark?.performance?.max_drawdown_pct),
)
const benchmarkHoldSpanLabel = computed(() => {
  const coverage = selectedRunDetail.value?.result_summary?.benchmark?.coverage
  const first = String(coverage?.first_bar_at ?? '')
  const last = String(coverage?.last_bar_at ?? '')
  if (!first || !last) return '—'
  return `${formatShortDateTime(first)} → ${formatShortDateTime(last)}`
})
const benchmarkCoverageNote = computed(() => {
  const firstBenchmarkTs = String(benchmarkCurve.value[0]?.ts ?? '')
  const runStart = String(selectedRunDetail.value?.date_from ?? '')
  if (!firstBenchmarkTs || !runStart) return ''
  const firstBenchmarkAt = new Date(firstBenchmarkTs).getTime()
  const runStartAt = new Date(runStart).getTime()
  if (!Number.isFinite(firstBenchmarkAt) || !Number.isFinite(runStartAt) || firstBenchmarkAt <= runStartAt) {
    return ''
  }
  return `Benchmark coverage starts on ${formatFullCoverageDateTime(firstBenchmarkTs)}. Earlier benchmark bars are unavailable for this run.`
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
  if (activeReturnsMode.value === 'quarterly') return quarterlyReturns.value
  if (activeReturnsMode.value === 'yearly') return yearlyReturns.value
  return monthlyReturns.value
})

const activeReturnsDetails = computed<Record<string, any[]>>(() => (
  buildReturnsDetailMap(activeReturnsMode.value)
))
const activeReturnsEmptyLabel = computed(() => {
  if (activeReturnsMode.value === 'quarterly') return 'No quarterly return breakdown yet.'
  if (activeReturnsMode.value === 'yearly') return 'No yearly return breakdown yet.'
  return 'No monthly return breakdown yet.'
})
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
const benchmarkPositionSeries = computed(() => {
  const timeline = selectedRunDetail.value?.result_summary?.benchmark?.position_timeline
  const denominator = positionEvolutionDenominator(timeline)
  if (!timeline || !Array.isArray(timeline.points) || !Number.isFinite(denominator) || denominator <= 0) {
    return []
  }
  const points = timeline.points
    .map((point: any) => {
      const rawValue = Number(point?.value)
      if (!String(point?.ts ?? '') || !Number.isFinite(rawValue)) return null
      return {
        ts: String(point.ts),
        value: (rawValue / denominator) * 100,
        detail: point.detail ? String(point.detail) : null,
        marker: point.marker ? String(point.marker) : null,
      }
    })
    .filter((point: any): point is { ts: string; value: number; detail: string | null; marker: string | null } => point != null)
  if (points.length < 2) return []
  return [
    {
      label: `${selectedRunDetail.value?.result_summary?.benchmark?.symbol || 'Benchmark'} buy & hold`,
      color: '#e0b35b',
      points,
    },
  ]
})
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

const positionSizingValueStep = computed(() =>
  logicDraft.position_sizing_mode === 'fixed_quantity' ? 1 : 0.1,
)

const positionSizingValueMin = computed(() =>
  logicDraft.position_sizing_mode === 'fixed_quantity' ? 1 : 0,
)

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
    : `${logicDraft.stop_loss_pct}% stop`
  const sizingText = logicDraft.position_sizing_mode === 'percent_risk'
    ? `${runDraft.risk_per_trade_pct}% risk-per-trade sizing`
    : logicDraft.position_sizing_mode === 'fixed_cash'
      ? `${formatMoney(logicDraft.position_sizing_value)} fixed cash sizing`
      : logicDraft.position_sizing_mode === 'percent_capital'
        ? `${logicDraft.position_sizing_value}% capital sizing`
        : `${logicDraft.position_sizing_value.toFixed(0)} fixed quantity sizing`
  const fixedTargetText = logicDraft.take_profit_rr > 0 ? `${logicDraft.take_profit_rr}R fixed target` : 'no fixed profit target'
  const timeExitText = logicDraft.max_bars_in_trade > 0 ? `${logicDraft.max_bars_in_trade}-bar time exit` : 'no time exit'
  const hardTrailText = logicDraft.hard_trailing_stop_pct > 0
    ? `, a hard ${logicDraft.hard_trailing_stop_pct}% trail${logicDraft.hard_trailing_activation_pct > 0 ? ` after a ${logicDraft.hard_trailing_activation_pct}% gain` : ''}`
    : ''
  return `Go ${logicDraft.direction} on ${logicDraft.timeframe} when ${conditionText || 'conditions are satisfied'}, using ${stopText} and ${sizingText}, with break-even after ${logicDraft.break_even_rr}R, a trailing stop distance of ${logicDraft.trailing_stop_rr}R${hardTrailText}, then exit via ${fixedTargetText}, ${timeExitText}${exitText ? `, or when ${exitText}` : ''}.`
})

const hasUniverseSelection = computed(() =>
  (sourceType.value === 'radar' && universeMode.value === 'radar')
  || logicDraft.symbols.length > 0
  || selectedWatchlistId.value != null
  || selectedScreenerId.value != null,
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
  && logicDraft.symbols.length === 0
  && selectedWatchlistId.value == null
  && selectedScreenerId.value == null,
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
  ])
  hydrateFromSelection(strategyLab.selectedDefinition)
})

function handleDocumentPointerDown(event: Event) {
  const target = event.target
  if (!(target instanceof Node)) return
  if (exportMenuRef.value?.contains(target)) return
  exportMenuOpen.value = false
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

watch(() => strategyLab.selectedDefinition, value => {
  hydrateFromSelection(value)
  exportMenuOpen.value = false
})

watch(universeMode, mode => {
  if (mode !== 'watchlist') selectedWatchlistId.value = null
  if (mode !== 'screener') selectedScreenerId.value = null
  if (mode !== 'symbols') logicDraft.symbols = []
})

watch(availableRunSubsetSymbols, symbols => {
  if (symbols.length) {
    const allowed = new Set(symbols)
    runDraft.overrideSymbols = runDraft.overrideSymbols.filter(symbol => allowed.has(symbol))
    return
  }
  if (!['symbols', 'watchlist'].includes(universeMode.value)) {
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
  compareRunId.value = null
  draft.tags = []
  versionNotes.value = ''
  symbolInput.value = ''
  logicDraft.timeframe = 'D1'
  logicDraft.direction = 'long'
  logicDraft.stop_model = 'percent'
  logicDraft.stop_loss_pct = 2
  logicDraft.stop_atr_period = 14
  logicDraft.stop_atr_multiple = 2
  logicDraft.hard_trailing_stop_pct = 0
  logicDraft.hard_trailing_activation_pct = 0
  logicDraft.take_profit_rr = 2
  logicDraft.max_bars_in_trade = 20
  logicDraft.break_even_rr = 0
  logicDraft.trailing_stop_rr = 0
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
  runDraft.commission_per_trade = 0
  runDraft.walk_forward_segments = 3
  runDraft.walk_forward_training_share = 0.6
  runDraft.paper_forward_bars = 20
  runDraft.max_concurrent_positions = 4
  runDraft.max_portfolio_risk_pct = 4
  runDraft.max_symbol_allocation_pct = 35
  runDraft.optimization_enabled = false
  runDraft.stop_loss_pct_values = '1.5, 2, 2.5, 3'
  runDraft.take_profit_rr_values = '1.5, 2, 2.5, 3'
  runDraft.max_bars_in_trade_values = '10, 15, 20, 30'
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
  logicDraft.stop_loss_pct = toPositiveNumber(risk.stop_loss_pct, 2)
  logicDraft.stop_atr_period = Math.max(1, Math.round(toPositiveNumber(risk.stop_atr_period, 14)))
  logicDraft.stop_atr_multiple = Math.max(0.1, Number(risk.stop_atr_multiple ?? 2) || 2)
  logicDraft.hard_trailing_stop_pct = Math.max(0, Number(risk.hard_trailing_stop_pct ?? 0) || 0)
  logicDraft.hard_trailing_activation_pct = Math.max(0, Number(risk.hard_trailing_activation_pct ?? 0) || 0)
  logicDraft.take_profit_rr = Math.max(0, Number(exits.take_profit_rr ?? risk.take_profit_rr ?? 2) || 0)
  logicDraft.max_bars_in_trade = Math.max(0, Math.round(Number(exits.max_bars_in_trade ?? risk.max_bars_in_trade ?? 20) || 0))
  logicDraft.break_even_rr = Math.max(0, Number(risk.break_even_rr ?? 0))
  logicDraft.trailing_stop_rr = Math.max(0, Number(risk.trailing_stop_rr ?? 0))
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
    logicDraft.symbols = []
  } else if (version.universe_config?.screener_id != null) {
    universeMode.value = 'screener'
    selectedScreenerId.value = Number(version.universe_config.screener_id)
    selectedWatchlistId.value = null
    logicDraft.symbols = []
  } else {
    universeMode.value = sourceType.value === 'radar' ? 'radar' : 'symbols'
    selectedWatchlistId.value = null
    selectedScreenerId.value = null
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
  runDraft.test_mode = ['backtest', 'walk_forward', 'paper_forward'].includes(String(runDefaults.test_mode))
    ? runDefaults.test_mode
    : 'backtest'
  runDraft.timeframe = String(runDefaults.timeframe ?? '')
  runDraft.date_from = toDateInputValue(runDefaults.date_from)
  runDraft.date_to = toDateInputValue(runDefaults.date_to)
  runDraft.initial_capital = Math.max(1000, Number(runDefaults.initial_capital ?? 100000) || 100000)
  runDraft.risk_per_trade_pct = Math.max(0.1, Number(runDefaults.risk_per_trade_pct ?? 1) || 1)
  runDraft.slippage_bps = Math.max(0, Number(runDefaults.slippage_bps ?? 5) || 0)
  runDraft.commission_per_trade = Math.max(0, Number(runDefaults.commission_per_trade ?? 0) || 0)
  runDraft.walk_forward_segments = Math.max(2, Math.round(Number(runDefaults.walk_forward_segments ?? 3) || 3))
  runDraft.walk_forward_training_share = Math.min(
    0.9,
    Math.max(0.3, Number(runDefaults.walk_forward_training_share ?? 0.6) || 0.6),
  )
  runDraft.paper_forward_bars = Math.max(5, Math.round(Number(runDefaults.paper_forward_bars ?? 20) || 20))
  runDraft.optimization_enabled = runDefaults.optimization_enabled === true
  runDraft.stop_loss_pct_values = String(runDefaults.stop_loss_pct_values ?? '1.5, 2, 2.5, 3')
  runDraft.take_profit_rr_values = String(runDefaults.take_profit_rr_values ?? '1.5, 2, 2.5, 3')
  runDraft.max_bars_in_trade_values = String(runDefaults.max_bars_in_trade_values ?? '10, 15, 20, 30')
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
  const riskConfig = {
    stop_model: logicDraft.stop_model,
    stop_loss_pct: logicDraft.stop_loss_pct,
    stop_atr_period: logicDraft.stop_atr_period,
    stop_atr_multiple: logicDraft.stop_atr_multiple,
    hard_trailing_stop_pct: logicDraft.hard_trailing_stop_pct,
    hard_trailing_activation_pct: logicDraft.hard_trailing_activation_pct,
    break_even_rr: logicDraft.break_even_rr,
    trailing_stop_rr: logicDraft.trailing_stop_rr,
    position_sizing_mode: logicDraft.position_sizing_mode,
    position_sizing_value: logicDraft.position_sizing_value,
    pyramiding_max_entries: logicDraft.pyramiding_max_entries,
  }
  const exitsConfig = {
    take_profit_rr: logicDraft.take_profit_rr,
    max_bars_in_trade: logicDraft.max_bars_in_trade,
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
      hard_trailing_stop_pct: { type: 'number', min: 0 },
      hard_trailing_activation_pct: { type: 'number', min: 0 },
      take_profit_rr: { type: 'number', min: 0 },
      max_bars_in_trade: { type: 'integer', min: 0 },
      break_even_rr: { type: 'number', min: 0 },
      trailing_stop_rr: { type: 'number', min: 0 },
      position_sizing_mode: { type: 'string', enum: ['percent_risk', 'fixed_cash', 'percent_capital', 'fixed_quantity'] },
      position_sizing_value: { type: 'number', min: 0 },
      pyramiding_max_entries: { type: 'integer', min: 1 },
    },
    default_parameters: {
      stop_model: logicDraft.stop_model,
      stop_loss_pct: logicDraft.stop_loss_pct,
      stop_atr_period: logicDraft.stop_atr_period,
      stop_atr_multiple: logicDraft.stop_atr_multiple,
      hard_trailing_stop_pct: logicDraft.hard_trailing_stop_pct,
      hard_trailing_activation_pct: logicDraft.hard_trailing_activation_pct,
      take_profit_rr: logicDraft.take_profit_rr,
      max_bars_in_trade: logicDraft.max_bars_in_trade,
      break_even_rr: logicDraft.break_even_rr,
      trailing_stop_rr: logicDraft.trailing_stop_rr,
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
          : { symbols: logicDraft.symbols }),
    },
    benchmark_config: logicDraft.benchmark_symbol.trim()
      ? { symbol: logicDraft.benchmark_symbol.trim().toUpperCase() }
      : {},
    execution_model: {
      entry: 'next_bar_open',
      exits: [
        'stop_loss',
        ...(logicDraft.take_profit_rr > 0 ? ['take_profit'] : []),
        ...(logicDraft.max_bars_in_trade > 0 ? ['time_exit'] : []),
        ...(logicDraft.break_even_rr > 0 ? ['break_even'] : []),
        ...(logicDraft.trailing_stop_rr > 0 ? ['trailing_stop'] : []),
        ...(logicDraft.hard_trailing_stop_pct > 0 ? ['hard_trailing_stop'] : []),
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
        slippage_bps: runDraft.slippage_bps,
        commission_per_trade: runDraft.commission_per_trade,
        walk_forward_segments: runDraft.walk_forward_segments,
        walk_forward_training_share: runDraft.walk_forward_training_share,
        paper_forward_bars: runDraft.paper_forward_bars,
        optimization_enabled: runDraft.optimization_enabled,
        stop_loss_pct_values: runDraft.stop_loss_pct_values,
        take_profit_rr_values: runDraft.take_profit_rr_values,
        max_bars_in_trade_values: runDraft.max_bars_in_trade_values,
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
  const submitted = await strategyLab.runVersion(currentVersion.value.id, {
    test_mode: runDraft.test_mode,
    timeframe: runDraft.timeframe || null,
    date_from: runDraft.date_from ? `${runDraft.date_from}T00:00:00Z` : null,
    date_to: runDraft.date_to ? `${runDraft.date_to}T23:59:59Z` : null,
    parameter_values: {},
    universe_config: runDraft.use_subset && runDraft.overrideSymbols.length
      ? { symbols: runDraft.overrideSymbols }
      : {},
    execution_assumptions: {
      initial_capital: runDraft.initial_capital,
      risk_per_trade_pct: runDraft.risk_per_trade_pct,
      slippage_bps: runDraft.slippage_bps,
      commission_per_trade: runDraft.commission_per_trade,
      max_concurrent_positions: runDraft.max_concurrent_positions,
      max_portfolio_risk_pct: runDraft.max_portfolio_risk_pct,
      max_symbol_allocation_pct: runDraft.max_symbol_allocation_pct,
      walk_forward_segments: runDraft.walk_forward_segments,
      walk_forward_training_share: runDraft.walk_forward_training_share,
      paper_forward_bars: runDraft.paper_forward_bars,
      optimization: {
        enabled: runDraft.optimization_enabled,
        stop_loss_pct_values: parseNumberList(runDraft.stop_loss_pct_values),
        take_profit_rr_values: parseNumberList(runDraft.take_profit_rr_values),
        max_bars_in_trade_values: parseIntegerList(runDraft.max_bars_in_trade_values),
      },
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

function parseNumberList(raw: string) {
  return raw
    .split(',')
    .map(value => Number(value.trim()))
    .filter(value => Number.isFinite(value))
}

function parseIntegerList(raw: string) {
  return raw
    .split(',')
    .map(value => Math.round(Number(value.trim())))
    .filter(value => Number.isFinite(value) && value > 0)
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
  if (!Array.isArray(rows) || rows.length < 2) return '—'
  const values = rows
    .map((row: any) => Number(row[valueKey]))
    .filter(Number.isFinite)
  if (values.length < 2) return '—'
  const first = values.find(value => value !== 0) ?? values[0]
  const last = values[values.length - 1]
  if (!Number.isFinite(first) || !Number.isFinite(last) || first === 0) return '—'
  return formatPercent(((last - first) / first) * 100)
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

.field-label {
  color: #8d8d8d;
  font-size: 11px;
  display: inline-flex;
  align-items: center;
  gap: 8px;
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

.run-list {
  gap: 8px;
  max-height: 332px;
  overflow: auto;
  padding-right: 2px;
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

.equity-chart polyline {
  fill: none;
  stroke: #62b2ea;
  stroke-width: 2;
}

.equity-chart--benchmark polyline {
  stroke: #d6a85a;
}

.equity-chart--drawdown polyline {
  stroke: #dd7373;
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

.trade-table-wrap {
  overflow: auto;
  border: 1px solid #1f1f1f;
  border-radius: 4px;
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
