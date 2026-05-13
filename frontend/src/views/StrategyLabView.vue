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
          <h2>{{ isNew ? 'New Strategy' : draft.name || 'Strategy' }}</h2>
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

      <div class="hero-strip">
        <div class="hero-card">
          <span class="hero-label">Current revision</span>
          <strong>{{ currentVersion ? `v${currentVersion.version_number}` : 'Draft only' }}</strong>
        </div>
        <div class="hero-card">
          <span class="hero-label">Universe</span>
          <strong>
            {{
              sourceType === 'radar' && universeMode === 'radar'
                ? 'Dynamic'
                : universeMode === 'watchlist'
                ? (selectedWatchlist?.items.length ?? 0)
                : universeMode === 'screener'
                  ? 1
                  : logicDraft.symbols.length
            }}
          </strong>
        </div>
        <div class="hero-card">
          <span class="hero-label">{{ sourceType === 'radar' ? 'Signal filters' : 'Entry rules' }}</span>
          <strong>{{ sourceType === 'radar' ? radarDraft.setup_types.length || radarSetupOptions.length : conditionCount }}</strong>
        </div>
        <div class="hero-card">
          <span class="hero-label">Research runs</span>
          <strong>{{ selectedRuns.length }}</strong>
        </div>
      </div>

      <div class="detail-columns">
        <div class="detail-column">
          <div class="panel">
            <div class="panel-head">
              <div><h3>Strategy profile</h3></div>
            </div>

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

          <div class="panel">
            <div class="panel-head">
              <div><h3>Risk and exits</h3></div>
            </div>

            <div class="form-grid three-up">
              <label class="field">
                <span class="field-label">
                  Stop loss %
                  <HoverTooltip text="Percent distance from the entry price to the stop. Position size is derived from this and your run-time risk budget.">
                    <button type="button" class="help-dot" aria-label="Stop loss info">i</button>
                  </HoverTooltip>
                </span>
                <input v-model.number="logicDraft.stop_loss_pct" type="number" min="0.1" step="0.1" class="form-input" />
              </label>
              <label class="field">
                <span class="field-label">
                  Target (R)
                  <HoverTooltip text="Take profit expressed as a multiple of the initial risk distance. 2R means the target sits two times the stop distance away from the entry.">
                    <button type="button" class="help-dot" aria-label="Target info">i</button>
                  </HoverTooltip>
                </span>
                <input v-model.number="logicDraft.take_profit_rr" type="number" min="0.25" step="0.25" class="form-input" />
              </label>
              <label class="field">
                <span class="field-label">
                  Max bars in trade
                  <HoverTooltip text="If the trade has not hit stop or target by this many bars, it is closed as a time exit.">
                    <button type="button" class="help-dot" aria-label="Max bars info">i</button>
                  </HoverTooltip>
                </span>
                <input v-model.number="logicDraft.max_bars_in_trade" type="number" min="1" step="1" class="form-input" />
              </label>
              <label class="field">
                <span class="field-label">Break-even after R</span>
                <input v-model.number="logicDraft.break_even_rr" type="number" min="0" step="0.25" class="form-input" />
              </label>
              <label class="field">
                <span class="field-label">Trail stop after R</span>
                <input v-model.number="logicDraft.trailing_stop_rr" type="number" min="0" step="0.25" class="form-input" />
              </label>
              <label class="field">
                <span class="field-label">Max entries</span>
                <input v-model.number="logicDraft.pyramiding_max_entries" type="number" min="1" step="1" class="form-input" />
              </label>
            </div>
          </div>
        </div>

        <div class="detail-column">
          <div class="panel">
          <div class="panel-head">
            <div><h3>{{ sourceType === 'radar' ? 'Signal source' : 'Entry logic' }}</h3></div>
          </div>

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

          <div class="panel">
          <div class="panel-head">
            <div><h3>Research runs</h3></div>
            <button
              v-if="currentVersion && !isNew"
              class="btn-primary"
              type="button"
              @click="runCurrentVersion"
              :disabled="strategyLab.isRunning"
            >
              {{ strategyLab.isRunning ? 'Running…' : runDraft.test_mode === 'walk_forward' ? 'Run walk-forward' : runDraft.test_mode === 'paper_forward' ? 'Run paper-forward' : 'Run backtest' }}
            </button>
          </div>

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
            <label class="field">
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
            <div class="subsection-head">
              <div class="subsection-title">
                <h4>Optional run subset</h4>
                <HoverTooltip text="Leave this empty to backtest the full published universe. Add symbols here only when you want to run the same strategy on a smaller subset.">
                  <button type="button" class="help-dot" aria-label="Run subset info">i</button>
                </HoverTooltip>
              </div>
            </div>
            <div class="chip-row">
              <span v-for="symbol in runDraft.overrideSymbols" :key="symbol" class="symbol-chip symbol-chip--alt">
                {{ symbol }}
                <button type="button" @click="removeRunSymbol(symbol)">×</button>
              </span>
              <span v-if="!runDraft.overrideSymbols.length" class="empty-inline">Using the published strategy universe.</span>
            </div>
            <div class="inline-search">
              <SearchBar
                v-model="runSymbolInput"
                placeholder="Optional subset symbol"
                mode="picker"
                fluid
                :show-recent="false"
                :show-screener-link="false"
                @select="addSelectedRunSymbol"
              />
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
          <div><h3>Results</h3></div>
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
            <button
              class="btn-secondary btn-icon-only"
              type="button"
              title="Export summary"
              aria-label="Export summary"
              @click="exportSummaryJson"
            >
              <svg viewBox="0 0 16 16" aria-hidden="true">
                <path d="M8 2.5v7" />
                <path d="M5.5 7 8 9.5 10.5 7" />
                <path d="M3 12.5h10" />
              </svg>
            </button>
            <button
              class="btn-secondary btn-icon-only"
              type="button"
              title="Export trades CSV"
              aria-label="Export trades CSV"
              @click="exportTradesCsv"
            >
              <svg viewBox="0 0 16 16" aria-hidden="true">
                <path d="M8 2.5v7" />
                <path d="M5.5 7 8 9.5 10.5 7" />
                <path d="M3 12.5h10" />
              </svg>
            </button>
          </div>
        </div>

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
              <small>{{ performance.trade_count ?? 0 }} trades</small>
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
              <small>{{ selectedRunDetail.result_summary.coverage?.instruments_with_data ?? 0 }} symbols with data</small>
            </div>
          </div>

          <div class="result-layout">
            <div class="result-column">
              <div class="equity-panel">
                <div class="equity-panel__head">
                  <strong>Equity curve</strong>
                  <span>{{ humanizeToken(selectedRunDetail.result_summary.result_kind || selectedRunDetail.test_mode) }}</span>
                </div>
                <svg v-if="equityPolyline" viewBox="0 0 320 120" class="equity-chart" role="img" aria-label="Equity curve">
                  <polyline :points="equityPolyline" />
                </svg>
                <div v-else class="empty-inline">No equity curve for this run yet.</div>
              </div>

              <div class="equity-panel">
                <div class="equity-panel__head">
                  <strong>Benchmark</strong>
                  <span>{{ selectedRunDetail.result_summary.benchmark?.symbol || 'No benchmark' }}</span>
                </div>
                <svg v-if="benchmarkPolyline" viewBox="0 0 320 120" class="equity-chart equity-chart--benchmark" role="img" aria-label="Benchmark curve">
                  <polyline :points="benchmarkPolyline" />
                </svg>
                <div v-else class="empty-inline">No benchmark curve for this run yet.</div>
              </div>

              <div class="equity-panel">
                <div class="equity-panel__head">
                  <strong>Drawdown</strong>
                  <span>{{ formatPercent(selectedRunDetail.result_summary.benchmark_comparison?.excess_return_pct) }} excess</span>
                </div>
                <svg v-if="drawdownPolyline" viewBox="0 0 320 120" class="equity-chart equity-chart--drawdown" role="img" aria-label="Drawdown curve">
                  <polyline :points="drawdownPolyline" />
                </svg>
                <div v-else class="empty-inline">No drawdown curve for this run yet.</div>
              </div>

              <div class="warnings-panel">
                <div class="subsection-head">
                  <h4>Warnings</h4>
                </div>
                <ul class="detail-list">
                  <li v-for="warning in selectedRunDetail.warning_log" :key="warning">{{ warning }}</li>
                  <li v-if="!selectedRunDetail.warning_log.length">No warnings.</li>
                </ul>
              </div>
            </div>

            <div class="result-column result-column--wide">
              <div class="result-panels-grid">
                <div class="mini-panel">
                  <div class="subsection-head"><h4>Monthly returns</h4></div>
                  <ul class="detail-list">
                    <li v-for="row in monthlyReturns.slice(0, 8)" :key="row.period">
                      <span>{{ row.period }}</span>
                      <strong>{{ row.return_pct != null ? formatPercent(row.return_pct) : '—' }}</strong>
                    </li>
                    <li v-if="!monthlyReturns.length">No monthly return breakdown yet.</li>
                  </ul>
                </div>

                <div class="mini-panel">
                  <div class="subsection-head"><h4>Quarterly returns</h4></div>
                  <ul class="detail-list">
                    <li v-for="row in quarterlyReturns.slice(0, 6)" :key="row.period">
                      <span>{{ row.period }}</span>
                      <strong>{{ row.return_pct != null ? formatPercent(row.return_pct) : '—' }}</strong>
                    </li>
                    <li v-if="!quarterlyReturns.length">No quarterly return breakdown yet.</li>
                  </ul>
                </div>

                <div class="mini-panel">
                  <div class="subsection-head"><h4>Per symbol</h4></div>
                  <ul class="detail-list">
                    <li v-for="row in symbolPerformance.slice(0, 8)" :key="row.symbol">
                      <span>{{ row.symbol }}</span>
                      <strong>{{ formatMoney(row.net_pnl) }}</strong>
                    </li>
                    <li v-if="!symbolPerformance.length">No per-symbol attribution yet.</li>
                  </ul>
                </div>

                <div class="mini-panel" v-if="selectedRunDetail.result_summary.portfolio">
                  <div class="subsection-head"><h4>Portfolio controls</h4></div>
                  <ul class="detail-list">
                    <li>
                      <span>Accepted trades</span>
                      <strong>{{ selectedRunDetail.result_summary.portfolio.accepted_trade_count ?? 0 }}</strong>
                    </li>
                    <li>
                      <span>Rejected trades</span>
                      <strong>{{ selectedRunDetail.result_summary.portfolio.rejected_trade_count ?? 0 }}</strong>
                    </li>
                    <li>
                      <span>Peak concurrent</span>
                      <strong>{{ selectedRunDetail.result_summary.portfolio.peak_concurrent_positions ?? 0 }}</strong>
                    </li>
                  </ul>
                </div>

                <div class="mini-panel" v-if="selectedRunDetail.result_summary.signal_summary">
                  <div class="subsection-head"><h4>Signal replay</h4></div>
                  <ul class="detail-list">
                    <li>
                      <span>Signals</span>
                      <strong>{{ selectedRunDetail.result_summary.signal_summary.signal_count ?? 0 }}</strong>
                    </li>
                    <li>
                      <span>Replayed</span>
                      <strong>{{ selectedRunDetail.result_summary.signal_summary.replayed_signal_count ?? 0 }}</strong>
                    </li>
                  </ul>
                </div>

                <div class="mini-panel" v-if="optimizationRows.length">
                  <div class="subsection-head"><h4>Optimization</h4></div>
                  <ul class="detail-list">
                    <li v-for="(row, index) in optimizationRows.slice(0, 5)" :key="`${row.stop_loss_pct}-${row.take_profit_rr}-${row.max_bars_in_trade}`">
                      <span>#{{ index + 1 }} · {{ row.stop_loss_pct }}% / {{ row.take_profit_rr }}R / {{ row.max_bars_in_trade }} bars</span>
                      <strong>{{ formatMoney(row.net_pnl) }}</strong>
                    </li>
                  </ul>
                </div>

                <div class="mini-panel" v-if="walkForwardSegments.length">
                  <div class="subsection-head"><h4>Walk-forward</h4></div>
                  <ul class="detail-list">
                    <li v-for="segment in walkForwardSegments" :key="segment.segment">
                      <span>Segment {{ segment.segment }}</span>
                      <strong>{{ segment.out_sample_return_pct != null ? formatPercent(segment.out_sample_return_pct) : '—' }}</strong>
                    </li>
                  </ul>
                </div>

                <div class="mini-panel" v-if="paperForwardSnapshots.length">
                  <div class="subsection-head"><h4>Paper-forward monitor</h4></div>
                  <ul class="detail-list">
                    <li v-for="snapshot in paperForwardSnapshots.slice(-6).reverse()" :key="snapshot.snapshot_at">
                      <span>{{ formatShortDateTime(snapshot.snapshot_at) }}</span>
                      <strong>{{ formatMoney(snapshot.latest_equity) }}</strong>
                    </li>
                  </ul>
                </div>

                <div class="mini-panel" v-if="comparisonRows.length">
                  <div class="subsection-head"><h4>Run comparison</h4></div>
                  <ul class="detail-list">
                    <li v-for="row in comparisonRows" :key="row.label">
                      <span>{{ row.label }}</span>
                      <strong>{{ row.current }} vs {{ row.compare }}</strong>
                    </li>
                  </ul>
                </div>

                <div class="mini-panel" v-if="tradeDistributions.r_histogram?.length">
                  <div class="subsection-head"><h4>R distribution</h4></div>
                  <ul class="detail-list">
                    <li v-for="(row, index) in tradeDistributions.r_histogram.slice(0, 6)" :key="`r-${index}`">
                      <span>{{ row.lower }} → {{ row.upper }}</span>
                      <strong>{{ row.count }}</strong>
                    </li>
                  </ul>
                </div>
              </div>

              <div class="trade-table-wrap">
                <table class="trade-table">
                  <thead>
                    <tr>
                      <th>Symbol</th>
                      <th>Side</th>
                      <th>Entry</th>
                      <th>Exit</th>
                      <th>P&amp;L</th>
                      <th>R</th>
                      <th>Reason</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="trade in visibleTrades" :key="`${trade.instrument_symbol}-${trade.entry_at}-${trade.exit_at}`">
                      <td>{{ trade.instrument_symbol }}</td>
                      <td>{{ humanizeToken(trade.side) }}</td>
                      <td>{{ formatShortDateTime(trade.entry_at) }}</td>
                      <td>{{ formatShortDateTime(trade.exit_at) }}</td>
                      <td :class="{ positive: Number(trade.pnl) > 0, negative: Number(trade.pnl) < 0 }">
                        {{ formatMoney(trade.pnl) }}
                      </td>
                      <td>{{ formatR(trade.r_multiple) }}</td>
                      <td>{{ humanizeToken(trade.exit_reason) }}</td>
                    </tr>
                    <tr v-if="!visibleTrades.length">
                      <td colspan="7" class="trade-table__empty">No trades were recorded for this run.</td>
                    </tr>
                  </tbody>
                </table>
            </div>
          </div>
        </div>
      </div>

        <div v-else class="empty-state">Run a backtest, then select it here to inspect the results.</div>
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
import { computed, onMounted, reactive, ref, watch } from 'vue'

import HoverTooltip from '@/components/common/HoverTooltip.vue'
import ResizeHandle from '@/components/common/ResizeHandle.vue'
import SearchBar from '@/components/common/SearchBar.vue'
import TagPicker from '@/components/common/TagPicker.vue'
import TextPromptModal from '@/components/common/TextPromptModal.vue'
import StrategyRuleTreeEditor from '@/components/strategy/StrategyRuleTreeEditor.vue'
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
const initialSidebarState = loadStrategySidebarState()

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
const runSymbolInput = ref('')
const sourceType = ref<'custom' | 'radar'>('custom')
const universeMode = ref<StrategyUniverseMode>('symbols')
const selectedWatchlistId = ref<number | null>(null)
const selectedScreenerId = ref<number | null>(null)
const compareRunId = ref<number | null>(null)
const showDeleteModal = ref(false)
const radarSetupMenuOpen = ref(false)
const radarStateMenuOpen = ref(false)
const sidebarWidth = ref(initialSidebarState.width)
const sidebarCollapsed = ref(initialSidebarState.collapsed)

const draft = reactive({
  name: '',
  description: '',
  is_active: true,
  tags: [] as string[],
})

const logicDraft = reactive({
  timeframe: 'D1',
  direction: 'long',
  stop_loss_pct: 2,
  take_profit_rr: 2,
  max_bars_in_trade: 20,
  break_even_rr: 0,
  trailing_stop_rr: 0,
  pyramiding_max_entries: 1,
  benchmark_symbol: 'SPY',
  symbols: [] as string[],
  ruleTree: createGroupNode('all', []) as BuilderGroupNode,
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
const paperForwardSnapshots = computed<any[]>(() =>
  Array.isArray(selectedRunDetail.value?.result_summary?.paper_forward?.monitor_snapshots)
    ? selectedRunDetail.value?.result_summary?.paper_forward?.monitor_snapshots
    : []
)

const performance = computed<Record<string, number | null>>(() =>
  selectedRunDetail.value?.result_summary?.performance ?? {}
)

const visibleTrades = computed<any[]>(() =>
  Array.isArray(selectedRunDetail.value?.result_summary?.trades)
    ? selectedRunDetail.value?.result_summary?.trades
    : []
)

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

const comparisonRows = computed(() => {
  if (!selectedRunDetail.value || !compareRun.value) return []
  return [
    comparisonMetric('Net return', selectedRunDetail.value.result_summary?.performance?.net_return_pct, compareRun.value.result_summary?.performance?.net_return_pct, '%'),
    comparisonMetric('Win rate', selectedRunDetail.value.result_summary?.performance?.win_rate, compareRun.value.result_summary?.performance?.win_rate, '%'),
    comparisonMetric('Expectancy', selectedRunDetail.value.result_summary?.performance?.expectancy_r, compareRun.value.result_summary?.performance?.expectancy_r, 'R'),
    comparisonMetric('Drawdown', selectedRunDetail.value.result_summary?.performance?.max_drawdown_pct, compareRun.value.result_summary?.performance?.max_drawdown_pct, '%'),
    comparisonMetric('Trade count', selectedRunDetail.value.result_summary?.performance?.trade_count, compareRun.value.result_summary?.performance?.trade_count, ''),
  ]
})

const equityPolyline = computed(() => {
  const points = selectedRunDetail.value?.result_summary?.equity_curve
  if (!Array.isArray(points) || points.length < 2) return ''
  const values = points.map((point: any) => Number(point.equity)).filter(Number.isFinite)
  if (values.length < 2) return ''
  return buildPolyline(values, 320, 120)
})

const benchmarkPolyline = computed(() => {
  const values = benchmarkCurve.value.map((point: any) => Number(point.equity)).filter(Number.isFinite)
  if (values.length < 2) return ''
  return buildPolyline(values, 320, 120)
})

const drawdownPolyline = computed(() => {
  const values = drawdownCurve.value
    .map((point: any) => Number(point.drawdown_pct))
    .filter(Number.isFinite)
  if (values.length < 2) return ''
  return buildPolyline(values, 320, 120)
})

const strategyNarrative = computed(() => {
  if (sourceType.value === 'radar') {
    const setupText = radarDraft.setup_types.length
      ? radarDraft.setup_types.map(humanizeToken).join(', ')
      : 'all setup families'
    const stateText = radarDraft.states.length
      ? radarDraft.states.map(humanizeToken).join(', ')
      : 'all lifecycle states'
    return `Replay ${setupText} Radar signals on ${logicDraft.timeframe}, filtering to ${stateText} and score ${radarDraft.min_score.toFixed(2)} or higher, then evaluate them with the current stop, target, and timing model.`
  }
  const conditionText = describeRuleNode(logicDraft.ruleTree)
  return `Go ${logicDraft.direction} on ${logicDraft.timeframe} when ${conditionText || 'conditions are satisfied'}, using a ${logicDraft.stop_loss_pct}% stop, a ${logicDraft.take_profit_rr}R target, break-even after ${logicDraft.break_even_rr}R, trailing after ${logicDraft.trailing_stop_rr}R, and a ${logicDraft.max_bars_in_trade}-bar time exit.`
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

watch([sidebarWidth, sidebarCollapsed], ([width, collapsed]) => {
  persistStrategySidebarState({ width, collapsed })
})

watch(() => strategyLab.selectedDefinition, value => {
  hydrateFromSelection(value)
})

watch(universeMode, mode => {
  if (mode !== 'watchlist') selectedWatchlistId.value = null
  if (mode !== 'screener') selectedScreenerId.value = null
  if (mode !== 'symbols') logicDraft.symbols = []
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
  runSymbolInput.value = ''
  logicDraft.timeframe = 'D1'
  logicDraft.direction = 'long'
  logicDraft.stop_loss_pct = 2
  logicDraft.take_profit_rr = 2
  logicDraft.max_bars_in_trade = 20
  logicDraft.break_even_rr = 0
  logicDraft.trailing_stop_rr = 0
  logicDraft.pyramiding_max_entries = 1
  logicDraft.benchmark_symbol = 'SPY'
  logicDraft.symbols = []
  logicDraft.ruleTree = createGroupNode('all', [])
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
  runDraft.overrideSymbols = []
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
  draft.name = definition.name
  draft.description = definition.description ?? ''
  draft.is_active = definition.is_active
  sourceType.value = definition.source_type === 'radar' ? 'radar' : 'custom'
  draft.tags = normalizeTags(definition.tags)

  const liveVersion = definition.versions.find(version => version.is_current) ?? definition.versions[0]
  hydrateFromVersion(liveVersion)
  compareRunId.value = definition.runs[1]?.id ?? null
}

function hydrateFromVersion(version: StrategyVersion | null | undefined) {
  if (!version) return
  const snapshot = version.definition_snapshot ?? {}
  const risk = snapshot.risk ?? {}
  const radarFilters = snapshot.radar_filters ?? {}
  const executionModel = version.execution_model ?? {}
  versionNotes.value = version.notes ?? ''
  logicDraft.timeframe = String(snapshot.timeframe ?? 'D1')
  logicDraft.direction = String(snapshot.direction ?? 'long')
  logicDraft.stop_loss_pct = toPositiveNumber(risk.stop_loss_pct, 2)
  logicDraft.take_profit_rr = toPositiveNumber(risk.take_profit_rr, 2)
  logicDraft.max_bars_in_trade = Math.max(1, Math.round(toPositiveNumber(risk.max_bars_in_trade, 20)))
  logicDraft.break_even_rr = Math.max(0, Number(risk.break_even_rr ?? 0))
  logicDraft.trailing_stop_rr = Math.max(0, Number(risk.trailing_stop_rr ?? 0))
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

  const rawConditions = Array.isArray(snapshot.conditions) ? snapshot.conditions : []
  logicDraft.ruleTree = parseRuleTree(
    snapshot.condition_tree,
    String(snapshot.entry_logic ?? 'all'),
    rawConditions,
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
  applyNodeMutation(logicDraft.ruleTree, targetId, target => {
    if (target.kind === 'group') target.children.push(createConditionNode())
    if (target.kind === 'not') target.condition = createConditionNode()
  })
}

function addGroupToTree(targetId: string, type: 'all' | 'any' | 'not') {
  applyNodeMutation(logicDraft.ruleTree, targetId, target => {
    const nextNode = type === 'not' ? createNotNode() : createGroupNode(type)
    if (target.kind === 'group') target.children.push(nextNode)
    if (target.kind === 'not') target.condition = nextNode
  })
}

function removeNodeFromTree(nodeId: string) {
  if (logicDraft.ruleTree.id === nodeId) {
    logicDraft.ruleTree = createGroupNode('all', [])
    return
  }
  removeNodeRecursive(logicDraft.ruleTree, nodeId)
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

function addSelectedRunSymbol(symbol: string) {
  runDraft.overrideSymbols = mergeSymbols(runDraft.overrideSymbols, [symbol])
  runSymbolInput.value = ''
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

function persistStrategySidebarState(value: { width: number; collapsed: boolean }) {
  try {
    localStorage.setItem(STRATEGY_SIDEBAR_STORAGE_KEY, JSON.stringify(value))
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
  const riskConfig = {
    stop_loss_pct: logicDraft.stop_loss_pct,
    take_profit_rr: logicDraft.take_profit_rr,
    max_bars_in_trade: logicDraft.max_bars_in_trade,
    break_even_rr: logicDraft.break_even_rr,
    trailing_stop_rr: logicDraft.trailing_stop_rr,
    pyramiding_max_entries: logicDraft.pyramiding_max_entries,
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
          }
        : {
            timeframe: logicDraft.timeframe,
            direction: logicDraft.direction,
            entry_logic: logicDraft.ruleTree.type,
            condition_tree: compileRuleNode(logicDraft.ruleTree),
            conditions: flatConditions.map(compileCondition),
            risk: riskConfig,
          }),
    },
    parameter_schema: {
      stop_loss_pct: { type: 'number', min: 0.1 },
      take_profit_rr: { type: 'number', min: 0.25 },
      max_bars_in_trade: { type: 'integer', min: 1 },
      break_even_rr: { type: 'number', min: 0 },
      trailing_stop_rr: { type: 'number', min: 0 },
      pyramiding_max_entries: { type: 'integer', min: 1 },
    },
    default_parameters: {
      stop_loss_pct: logicDraft.stop_loss_pct,
      take_profit_rr: logicDraft.take_profit_rr,
      max_bars_in_trade: logicDraft.max_bars_in_trade,
      break_even_rr: logicDraft.break_even_rr,
      trailing_stop_rr: logicDraft.trailing_stop_rr,
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
      exits: ['stop_loss', 'take_profit', 'time_exit', 'break_even', 'trailing_stop'],
      sizing: 'percent_risk',
      max_entries: logicDraft.pyramiding_max_entries,
      max_concurrent_positions: runDraft.max_concurrent_positions,
      max_portfolio_risk_pct: runDraft.max_portfolio_risk_pct,
      max_symbol_allocation_pct: runDraft.max_symbol_allocation_pct,
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
  if (!strategyLab.selectedDefinition) return
  const updated = await strategyLab.updateDefinition(strategyLab.selectedDefinition.id, buildDefinitionPayload())
  hydrateFromSelection(updated)
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
  const payload = buildDefinitionPayload()
  if (isNew.value) {
    const created = await strategyLab.createDefinition({
      ...payload,
      initial_version: buildVersionPayload(),
    })
    strategyLab.selectedDefinitionId = created.id
    hydrateFromSelection(created)
    isNew.value = false
    return
  }
  if (!strategyLab.selectedDefinition) return
  await strategyLab.updateDefinition(strategyLab.selectedDefinition.id, payload)
  await strategyLab.publishVersion(strategyLab.selectedDefinition.id, buildVersionPayload())
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
    universe_config: runDraft.overrideSymbols.length ? { symbols: runDraft.overrideSymbols } : {},
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

function buildPolyline(values: number[], width: number, height: number) {
  const min = Math.min(...values)
  const max = Math.max(...values)
  return values
    .map((value, index) => {
      const x = (index / Math.max(values.length - 1, 1)) * width
      const y = max === min ? height / 2 : height - ((value - min) / (max - min)) * (height - 12) - 6
      return `${x.toFixed(2)},${y.toFixed(2)}`
    })
    .join(' ')
}

function comparisonMetric(label: string, current: unknown, compare: unknown, suffix: string) {
  const currentValue = Number(current)
  const compareValue = Number(compare)
  const printableCurrent = Number.isFinite(currentValue)
    ? `${currentValue.toFixed(suffix === '' ? 0 : 2)}${suffix}`
    : '—'
  const printableCompare = Number.isFinite(compareValue)
    ? `${compareValue.toFixed(suffix === '' ? 0 : 2)}${suffix}`
    : '—'
  return {
    label,
    current: printableCurrent,
    compare: printableCompare,
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
  padding: 8px 9px;
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
  gap: 12px;
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
  margin-top: 6px;
  color: #7e7e7e;
  font-size: 11px;
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
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

.hero-strip,
.detail-columns {
  display: grid;
  gap: 16px;
}

.hero-strip {
  grid-template-columns: repeat(4, minmax(0, 1fr));
}

.hero-card,
.panel,
.condition-card,
.equity-panel,
.warnings-panel,
.mini-panel {
  background: #111;
  border: 1px solid #1b1b1b;
  border-radius: 4px;
}

.hero-card {
  padding: 12px;
  display: grid;
  gap: 8px;
  align-content: start;
  min-height: 92px;
}

.hero-label,
.summary-label {
  color: #6f6f6f;
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  line-height: 1;
}

.hero-card strong,
.summary-card strong {
  color: #f2f2f2;
  font-size: 16px;
  line-height: 1.1;
  display: block;
}

.hero-card small,
.summary-card small,
.equity-panel__head span {
  color: #7c7c7c;
  font-size: 11px;
  line-height: 1.4;
}

.detail-columns {
  grid-template-columns: repeat(2, minmax(0, 1fr));
  align-items: start;
}

.detail-column {
  display: grid;
  gap: 16px;
  align-content: start;
}

.panel {
  padding: 14px;
  display: grid;
  gap: 14px;
  min-width: 0;
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
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.mini-panel {
  padding: 12px;
  display: grid;
  gap: 10px;
}

.equity-panel,
.warnings-panel {
  padding: 12px;
}

.equity-panel__head {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 12px;
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
  .hero-strip,
  .run-summary-grid,
  .result-panels-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
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
  .hero-strip,
  .run-summary-grid,
  .result-panels-grid {
    grid-template-columns: 1fr;
  }
}
</style>
