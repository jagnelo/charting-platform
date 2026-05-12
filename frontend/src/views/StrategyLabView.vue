<template>
  <div class="strategy-lab-view">
    <aside class="strategy-sidebar">
      <div class="sidebar-header">
        <div>
          <h1>Strategy Lab</h1>
          <p>Build rule-based strategies, publish revisions, and backtest them visually.</p>
        </div>
        <button class="btn-primary" type="button" @click="startNew">+ New</button>
      </div>

      <div class="sidebar-note">
        <strong>Current focus</strong>
        <p>Rule-built strategies are fully editable here now. Platform-signal replays will plug into the same workspace next.</p>
      </div>

      <div class="definition-list">
        <button
          v-for="definition in strategyLab.definitions"
          :key="definition.id"
          type="button"
          class="definition-item"
          :class="{ active: strategyLab.selectedDefinitionId === definition.id }"
          @click="selectDefinition(definition.id)"
        >
          <div class="definition-head">
            <strong>{{ definition.name }}</strong>
            <span class="state-dot" :class="{ inactive: !definition.is_active }">
              {{ definition.is_active ? 'Active' : 'Paused' }}
            </span>
          </div>
          <div class="definition-meta">
            <span>{{ definition.tags.join(' · ') || 'Rule-built strategy' }}</span>
            <span v-if="definition.versions[0]">· v{{ definition.versions[0].version_number }}</span>
          </div>
          <div v-if="definition.runs[0]" class="definition-runline">
            Last backtest: {{ humanizeToken(definition.runs[0].status) }}
            <span v-if="definition.runs[0].result_summary?.performance?.trade_count != null">
              · {{ definition.runs[0].result_summary.performance.trade_count }} trades
            </span>
          </div>
        </button>
        <div v-if="!strategyLab.definitions.length && !strategyLab.isLoading" class="empty-state">
          No strategies yet.
        </div>
      </div>
    </aside>

    <section class="strategy-main">
      <div v-if="strategyLab.error" class="error-banner">{{ strategyLab.error }}</div>

      <div class="detail-header">
        <div>
          <h2>{{ isNew ? 'New Strategy' : draft.name || 'Strategy' }}</h2>
          <p>
            Build the logic visually, then publish a revision when you want that version to become the one you backtest.
          </p>
        </div>
        <div class="detail-actions">
          <button class="btn-secondary" type="button" @click="reload" :disabled="strategyLab.isLoading">Refresh</button>
          <button
            v-if="!isNew && strategyLab.selectedDefinition"
            class="btn-secondary"
            type="button"
            @click="saveProfileOnly"
            :disabled="strategyLab.isSaving"
          >
            {{ strategyLab.isSaving ? 'Saving…' : 'Save profile' }}
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
          <small>{{ currentVersion?.notes || 'Publish a revision to lock this logic in and test it.' }}</small>
        </div>
        <div class="hero-card">
          <span class="hero-label">Universe</span>
          <strong>{{ logicDraft.symbols.length }}</strong>
          <small>{{ logicDraft.symbols.slice(0, 4).join(', ') || 'Add symbols to define the strategy universe.' }}</small>
        </div>
        <div class="hero-card">
          <span class="hero-label">Entry rules</span>
          <strong>{{ logicDraft.conditions.length }}</strong>
          <small>{{ logicDraft.entry_logic === 'all' ? 'All conditions must align' : 'Any one condition can trigger' }}</small>
        </div>
        <div class="hero-card">
          <span class="hero-label">Backtests</span>
          <strong>{{ selectedRuns.length }}</strong>
          <small>{{ selectedRunDetail?.result_summary?.performance?.trade_count != null ? `${selectedRunDetail.result_summary.performance.trade_count} trades in selected run` : 'Run a backtest to inspect performance.' }}</small>
        </div>
      </div>

      <div class="detail-grid">
        <div class="panel">
          <div class="panel-head">
            <div>
              <h3>Strategy profile</h3>
              <p>Name the strategy, describe it briefly, and define the market it should scan.</p>
            </div>
          </div>

          <div class="form-grid two-up">
            <label class="field">
              <span class="field-label">Name</span>
              <input v-model="draft.name" class="form-input" placeholder="Momentum Continuation" />
            </label>
            <label class="field">
              <span class="field-label">Tags</span>
              <input v-model="tagsInput" class="form-input" placeholder="momentum, swing, equities" />
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
              <h4>Universe</h4>
              <HoverTooltip text="Add the symbols this strategy should evaluate by default. You can still run one-off backtests on a smaller subset later.">
                <button type="button" class="help-dot" aria-label="Universe info">i</button>
              </HoverTooltip>
            </div>

            <div class="chip-row">
              <span v-for="symbol in logicDraft.symbols" :key="symbol" class="symbol-chip">
                {{ symbol }}
                <button type="button" @click="removeSymbol(symbol)">×</button>
              </span>
              <span v-if="!logicDraft.symbols.length" class="empty-inline">No symbols added yet.</span>
            </div>

            <div class="inline-form">
              <input
                v-model="symbolInput"
                class="form-input"
                placeholder="Add symbol (e.g. AAPL)"
                @keydown.enter.prevent="addSymbolsFromInput"
              />
              <button class="btn-secondary" type="button" @click="addSymbolsFromInput">Add</button>
            </div>
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
              <input v-model="logicDraft.benchmark_symbol" class="form-input" placeholder="SPY" />
            </label>
          </div>
        </div>

        <div class="panel">
          <div class="panel-head">
            <div>
              <h3>Entry logic</h3>
              <p>Choose how conditions combine and what market relationships should create an entry signal.</p>
            </div>
            <button class="btn-secondary" type="button" @click="addCondition">+ Condition</button>
          </div>

          <div class="form-grid two-up">
            <label class="field">
              <span class="field-label">
                Trigger mode
                <HoverTooltip text="All means every condition must be true together. Any means one matching condition is enough to create a signal.">
                  <button type="button" class="help-dot" aria-label="Trigger mode info">i</button>
                </HoverTooltip>
              </span>
              <select v-model="logicDraft.entry_logic" class="form-select">
                <option value="all">All conditions</option>
                <option value="any">Any condition</option>
              </select>
            </label>
            <label class="field">
              <span class="field-label">Revision note</span>
              <input v-model="versionNotes" class="form-input" placeholder="What changed in this revision?" />
            </label>
          </div>

          <div class="condition-list">
            <div v-for="(condition, index) in logicDraft.conditions" :key="condition.id" class="condition-card">
              <div class="condition-head">
                <strong>Condition {{ index + 1 }}</strong>
                <button
                  v-if="logicDraft.conditions.length > 1"
                  class="icon-btn"
                  type="button"
                  @click="removeCondition(condition.id)"
                >
                  Remove
                </button>
              </div>

              <div class="condition-grid">
                <label class="field">
                  <span class="field-label">Left side</span>
                  <select v-model="condition.leftKind" class="form-select">
                    <option v-for="option in leftSideOptions" :key="option.value" :value="option.value">
                      {{ option.label }}
                    </option>
                  </select>
                </label>
                <label v-if="needsPeriod(condition.leftKind)" class="field">
                  <span class="field-label">Period</span>
                  <input v-model.number="condition.leftPeriod" type="number" min="1" class="form-input" />
                </label>
                <label class="field">
                  <span class="field-label">Relationship</span>
                  <select v-model="condition.operator" class="form-select">
                    <option v-for="option in operatorOptions" :key="option.value" :value="option.value">
                      {{ option.label }}
                    </option>
                  </select>
                </label>
                <label class="field">
                  <span class="field-label">Right side</span>
                  <select v-model="condition.rightKind" class="form-select">
                    <option v-for="option in rightSideOptions" :key="option.value" :value="option.value">
                      {{ option.label }}
                    </option>
                  </select>
                </label>
                <label v-if="condition.rightKind === 'value'" class="field">
                  <span class="field-label">Value</span>
                  <input v-model.number="condition.rightValue" type="number" step="0.01" class="form-input" />
                </label>
                <label v-if="needsPeriod(condition.rightKind)" class="field">
                  <span class="field-label">Period</span>
                  <input v-model.number="condition.rightPeriod" type="number" min="1" class="form-input" />
                </label>
              </div>
            </div>
          </div>

          <div class="rule-preview">
            <span class="rule-preview__label">How this reads</span>
            <p>{{ strategyNarrative }}</p>
          </div>
        </div>
      </div>

      <div class="detail-grid detail-grid--bottom">
        <div class="panel">
          <div class="panel-head">
            <div>
              <h3>Risk and exits</h3>
              <p>Define how far the idea can move against you, how much reward you want, and how long trades can stay open.</p>
            </div>
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
          </div>

          <div class="execution-summary">
            <strong>Execution model</strong>
            <p>Entries and exits are simulated directly from the completed bar stream. Stops, targets, time exits, slippage, and commissions are all applied when you run the backtest.</p>
          </div>
        </div>

        <div class="panel">
          <div class="panel-head">
            <div>
              <h3>Backtest</h3>
              <p>Run the current published revision over a chosen time range and inspect the resulting trades and curve.</p>
            </div>
            <button
              v-if="currentVersion && !isNew"
              class="btn-primary"
              type="button"
              @click="runCurrentVersion"
              :disabled="strategyLab.isRunning"
            >
              {{ strategyLab.isRunning ? 'Running…' : 'Run backtest' }}
            </button>
          </div>

          <div class="mode-strip">
            <span class="mode-pill mode-pill--active">Backtest</span>
            <span class="mode-pill">Walk forward</span>
            <span class="mode-pill">Paper forward</span>
          </div>

          <div class="form-grid three-up">
            <label class="field">
              <span class="field-label">Backtest timeframe</span>
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
          </div>

          <div class="subsection">
            <div class="subsection-head">
              <h4>Optional run subset</h4>
              <HoverTooltip text="Leave this empty to backtest the full published universe. Add symbols here only when you want to run the same strategy on a smaller subset.">
                <button type="button" class="help-dot" aria-label="Run subset info">i</button>
              </HoverTooltip>
            </div>
            <div class="chip-row">
              <span v-for="symbol in runDraft.overrideSymbols" :key="symbol" class="symbol-chip symbol-chip--alt">
                {{ symbol }}
                <button type="button" @click="removeRunSymbol(symbol)">×</button>
              </span>
              <span v-if="!runDraft.overrideSymbols.length" class="empty-inline">Using the published strategy universe.</span>
            </div>
            <div class="inline-form">
              <input
                v-model="runSymbolInput"
                class="form-input"
                placeholder="Optional subset symbol"
                @keydown.enter.prevent="addRunSymbolsFromInput"
              />
              <button class="btn-secondary" type="button" @click="addRunSymbolsFromInput">Add</button>
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

      <div class="panel panel--results">
        <div class="panel-head">
          <div>
            <h3>Results</h3>
            <p>Inspect how the selected backtest behaved, which trades it took, and where the main risks showed up.</p>
          </div>
        </div>

        <div v-if="selectedRunDetail" class="run-detail">
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
                  <span>{{ selectedRunDetail.result_summary.result_kind === 'rules_backtest' ? 'Backtest progression' : 'Research snapshot' }}</span>
                </div>
                <svg v-if="equityPolyline" viewBox="0 0 320 120" class="equity-chart" role="img" aria-label="Equity curve">
                  <polyline :points="equityPolyline" />
                </svg>
                <div v-else class="empty-inline">No equity curve for this run yet.</div>
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
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'

import HoverTooltip from '@/components/common/HoverTooltip.vue'
import { useStrategyLabStore } from '@/stores/strategyLab'
import type { StrategyDefinition, StrategyRun, StrategyVersion } from '@/types'

type RuleSideKind = 'close' | 'sma' | 'ema' | 'rsi'
type RuleOperator = 'gt' | 'gte' | 'lt' | 'lte' | 'crosses_above' | 'crosses_below'

interface BuilderCondition {
  id: string
  leftKind: RuleSideKind
  leftPeriod: number
  operator: RuleOperator
  rightKind: 'value' | RuleSideKind
  rightPeriod: number
  rightValue: number
}

const strategyLab = useStrategyLabStore()
const timeframes = ['M1', 'M5', 'M15', 'M30', 'H1', 'H2', 'H4', 'H12', 'D1', 'W1', 'MN']
const leftSideOptions = [
  { value: 'close', label: 'Close price' },
  { value: 'sma', label: 'SMA' },
  { value: 'ema', label: 'EMA' },
  { value: 'rsi', label: 'RSI' },
]
const rightSideOptions = [
  { value: 'value', label: 'Fixed value' },
  { value: 'close', label: 'Close price' },
  { value: 'sma', label: 'SMA' },
  { value: 'ema', label: 'EMA' },
  { value: 'rsi', label: 'RSI' },
]
const operatorOptions = [
  { value: 'gt', label: 'is above' },
  { value: 'gte', label: 'is at or above' },
  { value: 'lt', label: 'is below' },
  { value: 'lte', label: 'is at or below' },
  { value: 'crosses_above', label: 'crosses above' },
  { value: 'crosses_below', label: 'crosses below' },
]

const isNew = ref(false)
const tagsInput = ref('')
const versionNotes = ref('')
const symbolInput = ref('')
const runSymbolInput = ref('')

const draft = reactive({
  name: '',
  description: '',
  is_active: true,
})

const logicDraft = reactive({
  timeframe: 'D1',
  direction: 'long',
  entry_logic: 'all',
  stop_loss_pct: 2,
  take_profit_rr: 2,
  max_bars_in_trade: 20,
  benchmark_symbol: 'SPY',
  symbols: [] as string[],
  conditions: [createCondition()] as BuilderCondition[],
})

const runDraft = reactive({
  timeframe: '',
  date_from: '',
  date_to: '',
  initial_capital: 100000,
  risk_per_trade_pct: 1,
  slippage_bps: 5,
  commission_per_trade: 0,
  overrideSymbols: [] as string[],
})

const currentVersion = computed<StrategyVersion | null>(() =>
  strategyLab.selectedDefinition?.versions.find(version => version.is_current)
  ?? strategyLab.selectedDefinition?.versions[0]
  ?? null
)

const selectedRuns = computed<StrategyRun[]>(() => strategyLab.selectedDefinition?.runs ?? [])
const selectedRunDetail = computed<StrategyRun | null>(() =>
  selectedRuns.value.find(run => run.id === strategyLab.selectedRunId) ?? selectedRuns.value[0] ?? null
)

const performance = computed<Record<string, number | null>>(() =>
  selectedRunDetail.value?.result_summary?.performance ?? {}
)

const visibleTrades = computed<any[]>(() =>
  Array.isArray(selectedRunDetail.value?.result_summary?.trades)
    ? selectedRunDetail.value?.result_summary?.trades
    : []
)

const equityPolyline = computed(() => {
  const points = selectedRunDetail.value?.result_summary?.equity_curve
  if (!Array.isArray(points) || points.length < 2) return ''
  const values = points.map((point: any) => Number(point.equity)).filter(Number.isFinite)
  if (values.length < 2) return ''
  const min = Math.min(...values)
  const max = Math.max(...values)
  const width = 320
  const height = 120
  return values
    .map((value, index) => {
      const x = (index / Math.max(values.length - 1, 1)) * width
      const y = max === min ? height / 2 : height - ((value - min) / (max - min)) * (height - 12) - 6
      return `${x.toFixed(2)},${y.toFixed(2)}`
    })
    .join(' ')
})

const strategyNarrative = computed(() => {
  const conditionText = logicDraft.conditions.map(describeCondition).join(
    logicDraft.entry_logic === 'all' ? ' and ' : ' or ',
  )
  return `Go ${logicDraft.direction} on ${logicDraft.timeframe} when ${conditionText || 'conditions are satisfied'}, using a ${logicDraft.stop_loss_pct}% stop, a ${logicDraft.take_profit_rr}R target, and a ${logicDraft.max_bars_in_trade}-bar time exit.`
})

const canPublish = computed(() =>
  Boolean(draft.name.trim())
  && logicDraft.symbols.length > 0
  && logicDraft.conditions.length > 0
)

onMounted(async () => {
  await strategyLab.loadAll()
  hydrateFromSelection(strategyLab.selectedDefinition)
})

watch(() => strategyLab.selectedDefinition, value => {
  hydrateFromSelection(value)
})

function createCondition(overrides: Partial<BuilderCondition> = {}): BuilderCondition {
  return {
    id: crypto.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    leftKind: 'close',
    leftPeriod: 20,
    operator: 'gt',
    rightKind: 'sma',
    rightPeriod: 20,
    rightValue: 50,
    ...overrides,
  }
}

function startNew() {
  isNew.value = true
  strategyLab.selectDefinition(null)
  draft.name = ''
  draft.description = ''
  draft.is_active = true
  tagsInput.value = ''
  versionNotes.value = ''
  symbolInput.value = ''
  runSymbolInput.value = ''
  logicDraft.timeframe = 'D1'
  logicDraft.direction = 'long'
  logicDraft.entry_logic = 'all'
  logicDraft.stop_loss_pct = 2
  logicDraft.take_profit_rr = 2
  logicDraft.max_bars_in_trade = 20
  logicDraft.benchmark_symbol = 'SPY'
  logicDraft.symbols = []
  logicDraft.conditions = [createCondition()]
  runDraft.timeframe = ''
  runDraft.date_from = ''
  runDraft.date_to = ''
  runDraft.initial_capital = 100000
  runDraft.risk_per_trade_pct = 1
  runDraft.slippage_bps = 5
  runDraft.commission_per_trade = 0
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
  tagsInput.value = definition.tags.join(', ')

  const liveVersion = definition.versions.find(version => version.is_current) ?? definition.versions[0]
  hydrateFromVersion(liveVersion)
}

function hydrateFromVersion(version: StrategyVersion | null | undefined) {
  if (!version) return
  const snapshot = version.definition_snapshot ?? {}
  const risk = snapshot.risk ?? {}
  versionNotes.value = version.notes ?? ''
  logicDraft.timeframe = String(snapshot.timeframe ?? 'D1')
  logicDraft.direction = String(snapshot.direction ?? 'long')
  logicDraft.entry_logic = String(snapshot.entry_logic ?? 'all')
  logicDraft.stop_loss_pct = toPositiveNumber(risk.stop_loss_pct, 2)
  logicDraft.take_profit_rr = toPositiveNumber(risk.take_profit_rr, 2)
  logicDraft.max_bars_in_trade = Math.max(1, Math.round(toPositiveNumber(risk.max_bars_in_trade, 20)))
  logicDraft.benchmark_symbol = String(version.benchmark_config?.symbol ?? 'SPY')
  logicDraft.symbols = normalizeSymbols(version.universe_config?.symbols ?? [])

  const rawConditions = Array.isArray(snapshot.conditions) ? snapshot.conditions : []
  logicDraft.conditions = rawConditions.length
    ? rawConditions.map(parseCondition)
    : [createCondition()]
}

function parseCondition(raw: Record<string, any>): BuilderCondition {
  const leftKind = raw.left_source === 'indicator'
    ? normalizeIndicatorKind(raw.left_indicator)
    : 'close'
  let rightKind: BuilderCondition['rightKind'] = 'value'
  if (raw.right_source === 'indicator') rightKind = normalizeIndicatorKind(raw.right_indicator)
  else if (raw.right_source === 'price') rightKind = 'close'

  return createCondition({
    leftKind,
    leftPeriod: Math.max(1, Math.round(toPositiveNumber(raw.left_period, 20))),
    operator: normalizeOperator(raw.operator),
    rightKind,
    rightPeriod: Math.max(1, Math.round(toPositiveNumber(raw.right_period, 20))),
    rightValue: Number(raw.right_value ?? 50),
  })
}

function normalizeIndicatorKind(value: unknown): RuleSideKind {
  const token = String(value ?? '').toLowerCase()
  return ['sma', 'ema', 'rsi'].includes(token) ? token as RuleSideKind : 'close'
}

function normalizeOperator(value: unknown): RuleOperator {
  const token = String(value ?? '').toLowerCase()
  return operatorOptions.some(option => option.value === token)
    ? token as RuleOperator
    : 'gt'
}

function addCondition() {
  logicDraft.conditions.push(createCondition())
}

function removeCondition(id: string) {
  logicDraft.conditions = logicDraft.conditions.filter(condition => condition.id !== id)
}

function addSymbolsFromInput() {
  logicDraft.symbols = mergeSymbols(logicDraft.symbols, symbolInput.value)
  symbolInput.value = ''
}

function addRunSymbolsFromInput() {
  runDraft.overrideSymbols = mergeSymbols(runDraft.overrideSymbols, runSymbolInput.value)
  runSymbolInput.value = ''
}

function removeSymbol(symbol: string) {
  logicDraft.symbols = logicDraft.symbols.filter(item => item !== symbol)
}

function removeRunSymbol(symbol: string) {
  runDraft.overrideSymbols = runDraft.overrideSymbols.filter(item => item !== symbol)
}

function mergeSymbols(current: string[], raw: string) {
  const next = new Set(current)
  for (const symbol of normalizeSymbols(raw.split(/[,\s]+/))) next.add(symbol)
  return Array.from(next)
}

function normalizeSymbols(values: unknown[]) {
  return values
    .map(value => String(value ?? '').trim().toUpperCase())
    .filter(Boolean)
}

function buildVersionPayload() {
  return {
    definition_snapshot: {
      timeframe: logicDraft.timeframe,
      direction: logicDraft.direction,
      entry_logic: logicDraft.entry_logic,
      conditions: logicDraft.conditions.map(compileCondition),
      risk: {
        stop_loss_pct: logicDraft.stop_loss_pct,
        take_profit_rr: logicDraft.take_profit_rr,
        max_bars_in_trade: logicDraft.max_bars_in_trade,
      },
    },
    parameter_schema: {
      stop_loss_pct: { type: 'number', min: 0.1 },
      take_profit_rr: { type: 'number', min: 0.25 },
      max_bars_in_trade: { type: 'integer', min: 1 },
    },
    default_parameters: {
      stop_loss_pct: logicDraft.stop_loss_pct,
      take_profit_rr: logicDraft.take_profit_rr,
      max_bars_in_trade: logicDraft.max_bars_in_trade,
    },
    universe_config: {
      symbols: logicDraft.symbols,
    },
    benchmark_config: logicDraft.benchmark_symbol.trim()
      ? { symbol: logicDraft.benchmark_symbol.trim().toUpperCase() }
      : {},
    execution_model: {
      entry: 'next_bar_open',
      exits: ['stop_loss', 'take_profit', 'time_exit'],
      sizing: 'percent_risk',
    },
    notes: versionNotes.value.trim() || null,
  }
}

function compileCondition(condition: BuilderCondition) {
  return {
    left_source: condition.leftKind === 'close' ? 'price' : 'indicator',
    ...(condition.leftKind === 'close'
      ? {}
      : {
          left_indicator: condition.leftKind,
          left_period: condition.leftPeriod,
        }),
    operator: condition.operator,
    ...(condition.rightKind === 'value'
      ? {
          right_source: 'value',
          right_value: condition.rightValue,
        }
      : condition.rightKind === 'close'
        ? { right_source: 'price' }
        : {
            right_source: 'indicator',
            right_indicator: condition.rightKind,
            right_period: condition.rightPeriod,
          }),
  }
}

async function saveProfileOnly() {
  if (!strategyLab.selectedDefinition) return
  const updated = await strategyLab.updateDefinition(strategyLab.selectedDefinition.id, buildDefinitionPayload())
  hydrateFromSelection(updated)
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
    test_mode: 'backtest',
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
    },
  })
  strategyLab.selectedRunId = submitted.id
}

function buildDefinitionPayload() {
  return {
    name: draft.name.trim(),
    description: draft.description.trim() || null,
    source_type: 'custom',
    definition_type: 'rules',
    is_active: draft.is_active,
    tags: parseTags(tagsInput.value),
    metadata: {},
  }
}

async function reload() {
  await strategyLab.loadAll()
  hydrateFromSelection(strategyLab.selectedDefinition)
}

function parseTags(raw: string) {
  return raw
    .split(',')
    .map(tag => tag.trim())
    .filter(Boolean)
}

function needsPeriod(kind: BuilderCondition['rightKind'] | RuleSideKind) {
  return kind === 'sma' || kind === 'ema' || kind === 'rsi'
}

function describeCondition(condition: BuilderCondition) {
  const left = describeSide(condition.leftKind, condition.leftPeriod)
  const right = condition.rightKind === 'value'
    ? `${condition.rightValue}`
    : describeSide(condition.rightKind, condition.rightPeriod)
  const operator = operatorOptions.find(option => option.value === condition.operator)?.label ?? condition.operator
  return `${left} ${operator} ${right}`
}

function describeSide(kind: BuilderCondition['rightKind'], period: number) {
  if (kind === 'close') return 'close price'
  if (kind === 'value') return 'value'
  return `${kind.toUpperCase()}(${period})`
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
}

.strategy-sidebar {
  width: 292px;
  min-width: 256px;
  max-width: 320px;
  border-right: 1px solid #171717;
  background: #0c0c0c;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.sidebar-header,
.detail-header,
.panel-head,
.subsection-head,
.condition-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.sidebar-header {
  padding: 14px 14px 12px;
  border-bottom: 1px solid #171717;
}

.sidebar-header h1,
.detail-header h2,
.panel h3 {
  font-size: 17px;
  color: #f2f2f2;
  margin-bottom: 4px;
}

.sidebar-header p,
.detail-header p,
.panel-head p,
.sidebar-note p,
.execution-summary p {
  color: #7e7e7e;
  font-size: 11px;
  line-height: 1.45;
}

.sidebar-note {
  margin: 12px 14px 0;
  padding: 12px;
  border-radius: 12px;
  border: 1px solid #1d262d;
  background: linear-gradient(180deg, #10141a, #0d1015);
}

.sidebar-note strong {
  display: block;
  font-size: 12px;
  color: #d9eef8;
  margin-bottom: 6px;
}

.definition-list {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 10px;
  display: grid;
  gap: 10px;
}

.definition-item,
.run-item {
  width: 100%;
  text-align: left;
  background: #111;
  border: 1px solid #1c1c1c;
  border-radius: 10px;
  padding: 11px 12px;
  cursor: pointer;
  color: inherit;
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
.mode-pill,
.symbol-chip {
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
  padding: 18px;
  display: grid;
  gap: 16px;
  align-content: start;
}

.detail-actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 10px;
}

.hero-strip,
.detail-grid {
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
.warnings-panel {
  background: #111;
  border: 1px solid #1b1b1b;
  border-radius: 14px;
}

.hero-card {
  padding: 14px;
  display: grid;
  gap: 6px;
}

.hero-label,
.summary-label {
  color: #6f6f6f;
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.hero-card strong,
.summary-card strong {
  color: #f2f2f2;
  font-size: 18px;
}

.hero-card small,
.summary-card small,
.equity-panel__head span {
  color: #7c7c7c;
  font-size: 11px;
  line-height: 1.4;
}

.detail-grid {
  grid-template-columns: minmax(0, 1.08fr) minmax(0, 1fr);
}

.detail-grid--bottom {
  align-items: start;
}

.panel {
  padding: 16px;
  display: grid;
  gap: 16px;
  min-width: 0;
}

.subsection,
.run-detail {
  display: grid;
  gap: 12px;
}

.subsection h4,
.panel--results h4,
.equity-panel strong {
  color: #f0f0f0;
  font-size: 13px;
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
  padding-top: 26px;
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

.form-input,
.form-select,
.form-textarea {
  width: 100%;
  border: 1px solid #2a2a2a;
  border-radius: 10px;
  background: #0b0b0b;
  color: #dfdfdf;
  padding: 10px 12px;
  font: inherit;
  font-size: 12px;
  min-width: 0;
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
  gap: 8px;
}

.symbol-chip button,
.icon-btn {
  border: none;
  background: transparent;
  color: inherit;
  cursor: pointer;
  font: inherit;
}

.inline-form {
  display: flex;
  gap: 10px;
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
  padding: 13px 14px;
  border-radius: 12px;
  border: 1px solid #21262c;
  background: #0d1116;
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

.run-summary-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.summary-card {
  padding: 13px 14px;
  border: 1px solid #1f2328;
  border-radius: 12px;
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

.equity-panel,
.warnings-panel {
  padding: 14px;
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
  border-radius: 12px;
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
.btn-secondary {
  border-radius: 10px;
  padding: 9px 12px;
  font: inherit;
  font-size: 12px;
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
  .run-summary-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .condition-grid,
  .form-grid.three-up {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 1180px) {
  .detail-grid,
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
  .condition-grid,
  .hero-strip,
  .run-summary-grid {
    grid-template-columns: 1fr;
  }

  .inline-form {
    flex-direction: column;
  }
}
</style>
