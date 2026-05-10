<template>
  <div class="strategy-lab-view">
    <aside class="strategy-sidebar">
      <div class="sidebar-header">
        <div>
          <h1>Strategy Lab</h1>
          <p>Persist, version, and run research ideas.</p>
        </div>
        <button class="btn-primary" type="button" @click="startNew">+ New</button>
      </div>

      <div class="engine-strip">
        <div
          v-for="engine in strategyLab.engines"
          :key="engine.key"
          class="engine-pill"
          :class="{ offline: !engine.is_available }"
        >
          <span>{{ engine.label }}</span>
          <small>{{ engine.is_available ? 'available' : 'planned' }}</small>
        </div>
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
            <span>{{ humanizeToken(definition.source_type) }}</span>
            <span>·</span>
            <span>{{ humanizeToken(definition.definition_type) }}</span>
            <span v-if="definition.versions[0]">· v{{ definition.versions[0].version_number }}</span>
          </div>
          <div v-if="definition.runs[0]" class="definition-runline">
            Last run: {{ humanizeToken(definition.runs[0].status) }} · {{ formatDateTime(definition.runs[0].created_at) }}
          </div>
        </button>
        <div v-if="!strategyLab.definitions.length && !strategyLab.isLoading" class="empty-state">
          No strategy definitions yet.
        </div>
      </div>
    </aside>

    <section class="strategy-main">
      <div v-if="strategyLab.error" class="error-banner">{{ strategyLab.error }}</div>

      <div class="detail-header">
        <div>
          <h2>{{ isNew ? 'New Strategy Definition' : draft.name || 'Strategy Definition' }}</h2>
          <p>{{ isNew ? 'Create the canonical definition and initial version.' : 'Edit definition metadata, publish new versions, and run research snapshots.' }}</p>
        </div>
        <div class="detail-actions">
          <button class="btn-secondary" type="button" @click="reload" :disabled="strategyLab.isLoading">Refresh</button>
          <button class="btn-primary" type="button" @click="saveDefinition" :disabled="strategyLab.isSaving">
            {{ strategyLab.isSaving ? 'Saving…' : isNew ? 'Create definition' : 'Save definition' }}
          </button>
        </div>
      </div>

      <div class="detail-grid">
        <div class="panel">
          <h3>Definition</h3>
          <div class="form-grid two-up">
            <label class="field">
              <span class="field-label">Name</span>
              <input v-model="draft.name" class="form-input" placeholder="Momentum Pilot" />
            </label>
            <label class="field">
              <span class="field-label">Tags</span>
              <input v-model="tagsInput" class="form-input" placeholder="momentum, swing, platform" />
            </label>
            <label class="field">
              <span class="field-label">
                Source
                <HoverTooltip text="Where the signal logic ultimately comes from. Use Custom for user-authored logic, or Radar when the strategy is a replay/evaluation wrapper around platform-owned Radar detections.">
                  <button type="button" class="help-dot" aria-label="Source info">i</button>
                </HoverTooltip>
              </span>
              <select v-model="draft.source_type" class="form-select">
                <option value="custom">Custom</option>
                <option value="radar">Radar</option>
              </select>
            </label>
            <label class="field">
              <span class="field-label">
                Definition type
                <HoverTooltip :text="definitionTypeHelp.tooltip">
                  <button type="button" class="help-dot" aria-label="Definition type info">i</button>
                </HoverTooltip>
              </span>
              <select v-model="draft.definition_type" class="form-select">
                <option value="rules">Rules</option>
                <option value="dsl">DSL</option>
                <option value="python">Python</option>
                <option value="signal_source">Signal source</option>
              </select>
            </label>
            <label class="field field--checkbox">
              <input v-model="draft.is_active" type="checkbox" />
              <span>Definition is active</span>
            </label>
          </div>

          <div class="type-hint-card">
            <strong>{{ definitionTypeHelp.title }}</strong>
            <p>{{ definitionTypeHelp.summary }}</p>
          </div>

          <label class="field">
            <span class="field-label">Description</span>
            <textarea
              v-model="draft.description"
              class="form-textarea form-textarea--short"
              placeholder="Short explanation of what this research definition is trying to do."
            />
          </label>
          <label class="field">
            <span class="field-label">
              Metadata JSON
              <HoverTooltip text="Optional notes for humans or future automation. Good uses: owner, idea stage, market regime, ticket references, or whether this is experimental. This does not define entry/exit logic.">
                <button type="button" class="help-dot" aria-label="Metadata JSON info">i</button>
              </HoverTooltip>
            </span>
            <textarea
              v-model="metadataText"
              class="form-textarea"
              spellcheck="false"
              :placeholder="metadataPlaceholder"
            />
          </label>
        </div>

        <div class="panel">
          <div class="panel-head">
            <div>
              <h3>{{ isNew ? 'Initial version' : 'Publish next version' }}</h3>
              <p v-if="currentVersion">Current live version: v{{ currentVersion.version_number }} · {{ humanizeToken(currentVersion.engine_type) }}</p>
            </div>
            <button
              v-if="!isNew && strategyLab.selectedDefinition"
              class="btn-secondary"
              type="button"
              @click="publishVersion"
              :disabled="strategyLab.isSaving"
            >
              Publish version
            </button>
          </div>
          <div class="form-grid two-up">
            <label class="field">
              <span class="field-label">
                Engine
                <HoverTooltip text="The simulation/execution backend that will process this run. Only engines that are actually available are selectable here. Planned engines are shown in the left sidebar for visibility but cannot be chosen yet.">
                  <button type="button" class="help-dot" aria-label="Engine info">i</button>
                </HoverTooltip>
              </span>
              <select v-model="versionDraft.engine_type" class="form-select">
                <option v-for="engine in availableEngines" :key="engine.key" :value="engine.key">
                  {{ engine.label }}
                </option>
              </select>
            </label>
            <label class="field">
              <span class="field-label">Notes</span>
              <input v-model="versionDraft.notes" class="form-input" placeholder="What changed in this version?" />
            </label>
          </div>
          <div class="json-grid">
            <label class="field">
              <span class="field-label">
                {{ definitionSnapshotLabel }}
                <HoverTooltip :text="definitionTypeHelp.snapshotInfo">
                  <button type="button" class="help-dot" :aria-label="`${definitionSnapshotLabel} info`">i</button>
                </HoverTooltip>
              </span>
              <textarea
                v-model="versionDraft.definition_snapshot"
                class="form-textarea"
                spellcheck="false"
                :placeholder="definitionSnapshotPlaceholder"
              />
            </label>
            <label class="field">
              <span class="field-label">
                Universe config JSON
                <HoverTooltip text="Defines the set of instruments the strategy should run on. Start small while the lab is young: symbols or instrument_ids are the safest current inputs.">
                  <button type="button" class="help-dot" aria-label="Universe config JSON info">i</button>
                </HoverTooltip>
              </span>
              <textarea
                v-model="versionDraft.universe_config"
                class="form-textarea"
                spellcheck="false"
                :placeholder="universePlaceholder"
              />
            </label>
            <label class="field">
              <span class="field-label">
                Parameter schema JSON
                <HoverTooltip text="Describes which knobs exist and how they should be interpreted later. Use it to declare names, types, ranges, and defaults for parameters the strategy may expose.">
                  <button type="button" class="help-dot" aria-label="Parameter schema JSON info">i</button>
                </HoverTooltip>
              </span>
              <textarea
                v-model="versionDraft.parameter_schema"
                class="form-textarea"
                spellcheck="false"
                :placeholder="parameterSchemaPlaceholder"
              />
            </label>
            <label class="field">
              <span class="field-label">
                Default parameters JSON
                <HoverTooltip text="The concrete parameter values this version should use by default when no run-time overrides are provided. These should line up with the declared parameter schema.">
                  <button type="button" class="help-dot" aria-label="Default parameters JSON info">i</button>
                </HoverTooltip>
              </span>
              <textarea
                v-model="versionDraft.default_parameters"
                class="form-textarea"
                spellcheck="false"
                :placeholder="defaultParametersPlaceholder"
              />
            </label>
            <label class="field">
              <span class="field-label">
                Execution model JSON
                <HoverTooltip text="Describes how signals should translate into trades later: entry timing, exits, stop policy, target policy, sizing assumptions, and similar execution semantics.">
                  <button type="button" class="help-dot" aria-label="Execution model JSON info">i</button>
                </HoverTooltip>
              </span>
              <textarea
                v-model="versionDraft.execution_model"
                class="form-textarea"
                spellcheck="false"
                :placeholder="executionModelPlaceholder"
              />
            </label>
            <label class="field">
              <span class="field-label">
                Benchmark config JSON
                <HoverTooltip text="Optional comparison target for research. For example, compare your strategy against SPY buy-and-hold, QQQ, or a custom benchmark later on.">
                  <button type="button" class="help-dot" aria-label="Benchmark config JSON info">i</button>
                </HoverTooltip>
              </span>
              <textarea
                v-model="versionDraft.benchmark_config"
                class="form-textarea"
                spellcheck="false"
                :placeholder="benchmarkPlaceholder"
              />
            </label>
          </div>
        </div>
      </div>

      <div class="detail-grid detail-grid--bottom">
        <div class="panel">
          <div class="panel-head">
            <div>
              <h3>Runs</h3>
              <p>Run a persisted version against a timeframe and date range, then inspect the research summary.</p>
            </div>
            <button
              v-if="currentVersion && !isNew"
              class="btn-primary"
              type="button"
              @click="runCurrentVersion"
              :disabled="strategyLab.isRunning"
            >
              {{ strategyLab.isRunning ? 'Running…' : 'Run current version' }}
            </button>
          </div>
          <div class="form-grid three-up">
            <label class="field">
              <span class="field-label">
                Mode
                <HoverTooltip text="Backtest replays history, walk forward evaluates repeated train/test windows, and paper forward is the eventual future-facing simulated mode on fresh incoming data.">
                  <button type="button" class="help-dot" aria-label="Mode info">i</button>
                </HoverTooltip>
              </span>
              <select v-model="runDraft.test_mode" class="form-select">
                <option value="backtest">Backtest</option>
                <option value="walk_forward">Walk forward</option>
                <option value="paper_forward">Paper forward</option>
              </select>
            </label>
            <label class="field">
              <span class="field-label">Timeframe</span>
              <select v-model="runDraft.timeframe" class="form-select">
                <option value="">Inherit</option>
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
          </div>
          <div class="json-grid json-grid--run">
            <label class="field">
              <span class="field-label">
                Parameter overrides JSON
                <HoverTooltip text="Override default parameter values for this specific run only. Leave empty to use the version's defaults unchanged.">
                  <button type="button" class="help-dot" aria-label="Parameter overrides JSON info">i</button>
                </HoverTooltip>
              </span>
              <textarea
                v-model="runDraft.parameter_values"
                class="form-textarea"
                spellcheck="false"
                :placeholder="parameterOverridesPlaceholder"
              />
            </label>
            <label class="field">
              <span class="field-label">
                Universe override JSON
                <HoverTooltip text="Optional one-off universe override for this run. Good for quickly testing the same strategy version on a different small symbol set.">
                  <button type="button" class="help-dot" aria-label="Universe override JSON info">i</button>
                </HoverTooltip>
              </span>
              <textarea
                v-model="runDraft.universe_config"
                class="form-textarea"
                spellcheck="false"
                :placeholder="universeOverridePlaceholder"
              />
            </label>
            <label class="field">
              <span class="field-label">
                Execution assumptions JSON
                <HoverTooltip text="Run-specific frictions and assumptions such as slippage, commissions, or other temporary overrides you want applied to this research run.">
                  <button type="button" class="help-dot" aria-label="Execution assumptions JSON info">i</button>
                </HoverTooltip>
              </span>
              <textarea
                v-model="runDraft.execution_assumptions"
                class="form-textarea"
                spellcheck="false"
                :placeholder="executionAssumptionsPlaceholder"
              />
            </label>
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
                <strong>{{ humanizeToken(run.test_mode) }}</strong>
                <span class="status-chip" :class="`status-chip--${run.status}`">{{ humanizeToken(run.status) }}</span>
              </div>
              <div class="run-item__meta">
                <span>{{ run.timeframe || currentVersion?.definition_snapshot?.timeframe || 'D1' }}</span>
                <span>·</span>
                <span>{{ formatDateTime(run.created_at) }}</span>
              </div>
            </button>
            <div v-if="!selectedRuns.length" class="empty-state empty-state--small">No runs yet.</div>
          </div>
        </div>

        <div class="panel">
          <h3>Run detail</h3>
          <div v-if="selectedRunDetail" class="run-detail">
            <div class="run-summary-grid">
              <div class="summary-card">
                <span class="summary-label">Coverage</span>
                <strong>{{ selectedRunDetail.result_summary.coverage?.total_bars ?? 0 }} bars</strong>
                <small>{{ selectedRunDetail.result_summary.coverage?.instruments_with_data ?? 0 }} instruments with data</small>
              </div>
              <div class="summary-card">
                <span class="summary-label">Universe</span>
                <strong>{{ selectedRunDetail.result_summary.universe?.resolved_instrument_count ?? 0 }} symbols</strong>
                <small>{{ selectedRunDetail.result_summary.universe?.resolved_symbols?.slice?.(0, 3)?.join(', ') || 'No symbols resolved' }}</small>
              </div>
              <div class="summary-card">
                <span class="summary-label">Readiness</span>
                <strong>{{ selectedRunDetail.result_summary.readiness?.has_coverage ? 'Covered' : 'Needs data' }}</strong>
                <small>{{ selectedRunDetail.result_summary.result_kind || 'foundation_research_snapshot' }}</small>
              </div>
            </div>

            <div class="detail-columns">
              <div>
                <h4>Warnings</h4>
                <ul class="detail-list">
                  <li v-for="warning in selectedRunDetail.warning_log" :key="warning">{{ warning }}</li>
                  <li v-if="!selectedRunDetail.warning_log.length">No warnings.</li>
                </ul>
              </div>
              <div>
                <h4>Result summary</h4>
                <pre class="json-preview">{{ prettyJson(selectedRunDetail.result_summary) }}</pre>
              </div>
            </div>
          </div>
          <div v-else class="empty-state">Select a run to inspect its summary.</div>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'

import HoverTooltip from '@/components/common/HoverTooltip.vue'
import { useStrategyLabStore } from '@/stores/strategyLab'
import type { StrategyDefinition, StrategyRun, StrategyVersion } from '@/types'

const strategyLab = useStrategyLabStore()
const timeframes = ['M1', 'M5', 'M15', 'M30', 'H1', 'H2', 'H4', 'H12', 'D1', 'W1', 'MN']
const definitionTypeCopy: Record<string, { title: string; summary: string; tooltip: string; snapshotInfo: string }> = {
  rules: {
    title: 'Rules',
    summary: 'Use structured rule objects when the strategy can be expressed with named conditions, thresholds, and relationships.',
    tooltip: 'Rules = structured, platform-readable logic. DSL = a future compact custom language. Python = external/custom code references. Signal source = strategies driven by another engine such as Radar detections.',
    snapshotInfo: 'For Rules, define the strategy as structured JSON: clauses, indicators, thresholds, confirmations, and similar machine-readable logic.',
  },
  dsl: {
    title: 'DSL',
    summary: 'Use a compact declarative language definition once the platform-specific syntax exists. For now this mostly reserves the shape.',
    tooltip: 'DSL stands for domain-specific language: a compact text-like or expression-like layer the platform can parse later without exposing raw Python.',
    snapshotInfo: 'For DSL, store the future parsed representation or source payload the DSL compiler or translator will later consume.',
  },
  python: {
    title: 'Python',
    summary: 'Use this when the real strategy logic lives in custom Python code or an adapter module outside the plain rules format.',
    tooltip: 'Python means the version is backed by code rather than only declarative rules. The JSON here should describe the entrypoint, module, class, or runtime arguments rather than contain executable code directly.',
    snapshotInfo: 'For Python, describe the callable entrypoint and runtime wiring rather than pasting raw source code into this field.',
  },
  signal_source: {
    title: 'Signal source',
    summary: 'Use this when the strategy is really a replay or evaluation wrapper around another signal engine, such as Radar.',
    tooltip: 'Signal source strategies do not originate their own entry logic. Instead, they consume events emitted elsewhere and evaluate them under defined execution rules.',
    snapshotInfo: 'For Signal source, identify the upstream producer and the filters needed to select which signals belong to this strategy version.',
  },
}
const definitionSnapshotPlaceholders: Record<string, string> = {
  rules: `{
  "logic": {
    "operator": "AND",
    "conditions": [
      { "type": "indicator_threshold", "indicator": "ema", "params": { "period": 50 }, "field": "close", "operator": "gt" },
      { "type": "indicator_threshold", "indicator": "rsi", "params": { "period": 14 }, "operator": "gt", "value": 55 }
    ]
  },
  "timeframe": "D1"
}`,
  dsl: `{
  "dsl_source": "close > ema(50) and rsi(14) > 55",
  "timeframe": "D1"
}`,
  python: `{
  "module": "strategies.momentum",
  "callable": "MomentumContinuationStrategy",
  "kwargs": { "ema_period": 50 }
}`,
  signal_source: `{
  "source": "radar",
  "filters": {
    "setup_types": ["breakout", "breakout_retest"],
    "states": ["confirmed"],
    "min_score": 0.8
  }
}`,
}

const isNew = ref(false)
const tagsInput = ref('')
const metadataText = ref('')
const draft = reactive({
  name: '',
  description: '',
  source_type: 'custom',
  definition_type: 'rules',
  is_active: true,
})
const versionDraft = reactive({
  engine_type: 'platform',
  notes: '',
  definition_snapshot: '',
  universe_config: '',
  parameter_schema: '',
  default_parameters: '',
  execution_model: '',
  benchmark_config: '',
})
const runDraft = reactive({
  test_mode: 'backtest',
  timeframe: '',
  date_from: '',
  date_to: '',
  parameter_values: '',
  universe_config: '',
  execution_assumptions: '',
})

const currentVersion = computed<StrategyVersion | null>(() =>
  strategyLab.selectedDefinition?.versions.find(version => version.is_current)
  ?? strategyLab.selectedDefinition?.versions[0]
  ?? null
)
const availableEngines = computed(() => strategyLab.engines.filter(engine => engine.is_available))
const definitionTypeHelp = computed(() => definitionTypeCopy[draft.definition_type] ?? definitionTypeCopy.rules)
const definitionSnapshotLabel = computed(() => `${definitionTypeHelp.value.title} snapshot JSON`)
const definitionSnapshotPlaceholder = computed(
  () => definitionSnapshotPlaceholders[draft.definition_type] ?? definitionSnapshotPlaceholders.rules,
)
const metadataPlaceholder = `{
  "owner": "swing-research",
  "stage": "idea",
  "notes": "Testing momentum continuation ideas"
}`
const universePlaceholder = `{
  "symbols": ["AAPL", "MSFT", "NVDA"]
}`
const parameterSchemaPlaceholder = `{
  "ema_period": { "type": "integer", "default": 50, "min": 5, "max": 250 },
  "risk_per_trade_pct": { "type": "number", "default": 1 }
}`
const defaultParametersPlaceholder = `{
  "ema_period": 50,
  "risk_per_trade_pct": 1
}`
const executionModelPlaceholder = `{
  "entry": "next_bar_open",
  "stop": "signal_invalidation",
  "target": "2R"
}`
const benchmarkPlaceholder = `{
  "symbol": "SPY",
  "mode": "buy_and_hold"
}`
const parameterOverridesPlaceholder = `{
  "ema_period": 34
}`
const universeOverridePlaceholder = `{
  "symbols": ["TSLA", "AMD"]
}`
const executionAssumptionsPlaceholder = `{
  "slippage_bps": 5,
  "commission_per_trade": 1
}`
const selectedRuns = computed<StrategyRun[]>(() => strategyLab.selectedDefinition?.runs ?? [])
const selectedRunDetail = computed<StrategyRun | null>(() =>
  selectedRuns.value.find(run => run.id === strategyLab.selectedRunId) ?? selectedRuns.value[0] ?? null
)

onMounted(async () => {
  await strategyLab.loadAll()
  hydrateFromSelection(strategyLab.selectedDefinition)
})

watch(() => strategyLab.selectedDefinition, value => {
  hydrateFromSelection(value)
}, { immediate: false })

function startNew() {
  isNew.value = true
  strategyLab.selectDefinition(null)
  Object.assign(draft, {
    name: '',
    description: '',
    source_type: 'custom',
    definition_type: 'rules',
    is_active: true,
  })
  tagsInput.value = ''
  metadataText.value = ''
  Object.assign(versionDraft, {
    engine_type: availableEngines.value[0]?.key ?? 'platform',
    notes: '',
    definition_snapshot: '',
    universe_config: '',
    parameter_schema: '',
    default_parameters: '',
    execution_model: '',
    benchmark_config: '',
  })
  Object.assign(runDraft, {
    test_mode: 'backtest',
    timeframe: '',
    date_from: '',
    date_to: '',
    parameter_values: '',
    universe_config: '',
    execution_assumptions: '',
  })
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
  draft.source_type = String(definition.source_type)
  draft.definition_type = String(definition.definition_type)
  draft.is_active = definition.is_active
  tagsInput.value = definition.tags.join(', ')
  metadataText.value = prettyJson(definition.metadata)
  const liveVersion = definition.versions.find(version => version.is_current) ?? definition.versions[0]
  if (liveVersion) {
    versionDraft.engine_type = availableEngines.value.some(engine => engine.key === String(liveVersion.engine_type))
      ? String(liveVersion.engine_type)
      : availableEngines.value[0]?.key ?? 'platform'
    versionDraft.notes = liveVersion.notes ?? ''
    versionDraft.definition_snapshot = prettyJson(liveVersion.definition_snapshot)
    versionDraft.universe_config = prettyJson(liveVersion.universe_config)
    versionDraft.parameter_schema = prettyJson(liveVersion.parameter_schema)
    versionDraft.default_parameters = prettyJson(liveVersion.default_parameters)
    versionDraft.execution_model = prettyJson(liveVersion.execution_model)
    versionDraft.benchmark_config = prettyJson(liveVersion.benchmark_config)
  }
}

async function reload() {
  await strategyLab.loadAll()
  hydrateFromSelection(strategyLab.selectedDefinition)
}

async function saveDefinition() {
  const payload = {
    name: draft.name.trim(),
    description: draft.description.trim() || null,
    source_type: draft.source_type,
    definition_type: draft.definition_type,
    is_active: draft.is_active,
    tags: parseTags(tagsInput.value),
    metadata: parseJson('metadata', metadataText.value),
  }
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
  const updated = await strategyLab.updateDefinition(strategyLab.selectedDefinition.id, payload)
  hydrateFromSelection(updated)
}

async function publishVersion() {
  if (!strategyLab.selectedDefinition) return
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
    parameter_values: parseJson('parameter overrides', runDraft.parameter_values),
    universe_config: parseJson('run universe override', runDraft.universe_config),
    execution_assumptions: parseJson('execution assumptions', runDraft.execution_assumptions),
  })
  strategyLab.selectedRunId = submitted.run.id
}

function buildVersionPayload() {
  return {
    engine_type: versionDraft.engine_type,
    notes: versionDraft.notes.trim() || null,
    definition_snapshot: parseJson('definition snapshot', versionDraft.definition_snapshot),
    universe_config: parseJson('universe config', versionDraft.universe_config),
    parameter_schema: parseJson('parameter schema', versionDraft.parameter_schema),
    default_parameters: parseJson('default parameters', versionDraft.default_parameters),
    execution_model: parseJson('execution model', versionDraft.execution_model),
    benchmark_config: parseJson('benchmark config', versionDraft.benchmark_config),
  }
}

function parseJson(label: string, raw: string) {
  try {
    return JSON.parse(raw || '{}')
  } catch {
    throw new Error(`Invalid ${label} JSON`)
  }
}

function parseTags(raw: string) {
  return raw
    .split(',')
    .map(tag => tag.trim())
    .filter(Boolean)
}

function humanizeToken(value: string | undefined | null) {
  return String(value ?? '—')
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (char: string) => char.toUpperCase())
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

function prettyJson(value: unknown) {
  return JSON.stringify(value ?? {}, null, 2)
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
  width: 284px;
  min-width: 252px;
  max-width: 320px;
  border-right: 1px solid #171717;
  background: #0c0c0c;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.sidebar-header,
.detail-header,
.panel-head {
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
.panel-head p {
  color: #7e7e7e;
  font-size: 11px;
  line-height: 1.45;
}

.engine-strip {
  padding: 10px 14px;
  display: grid;
  gap: 8px;
  border-bottom: 1px solid #171717;
}

.engine-pill {
  border: 1px solid #23422f;
  background: #0e1712;
  border-radius: 10px;
  padding: 8px 10px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.engine-pill.offline {
  border-color: #3b3022;
  background: #17120d;
}

.engine-pill span {
  color: #d9efe0;
  font-size: 12px;
}

.engine-pill small {
  color: #7da58b;
  font-size: 10px;
  text-transform: uppercase;
}

.engine-pill.offline small {
  color: #b39062;
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
.status-chip {
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
.status-chip--running {
  border-color: #6a5424;
  background: #231d12;
  color: #e7cb85;
}

.status-chip--completed {
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
}

.detail-actions {
  display: flex;
  gap: 10px;
}

.detail-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.05fr) minmax(0, 1fr);
  gap: 14px;
  margin-top: 14px;
}

.detail-grid--bottom {
  margin-top: 14px;
}

.panel {
  background: #0f0f0f;
  border: 1px solid #1a1a1a;
  border-radius: 12px;
  padding: 14px;
  min-width: 0;
}

.form-grid {
  display: grid;
  gap: 10px;
}

.form-grid.two-up {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.form-grid.three-up {
  grid-template-columns: repeat(4, minmax(0, 1fr));
}

.field {
  display: grid;
  gap: 8px;
  margin-top: 10px;
}

.field-label {
  color: #909090;
  font-size: 11px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.field--checkbox {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 24px;
}

.field--checkbox span {
  font-size: 12px;
  color: #a7a7a7;
}

.form-input,
.form-select,
.form-textarea {
  width: 100%;
  border: 1px solid #2a2a2a;
  background: #121212;
  color: #ddd;
  border-radius: 8px;
  padding: 9px 10px;
  font: inherit;
  font-size: 12px;
}

.form-textarea {
  min-height: 128px;
  resize: vertical;
}

.form-textarea--short {
  min-height: 76px;
}

.json-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.json-grid--run {
  margin-top: 10px;
}

.btn-primary,
.btn-secondary {
  border-radius: 8px;
  padding: 8px 12px;
  font: inherit;
  font-size: 12px;
  cursor: pointer;
  border: 1px solid #275b86;
  background: #10263a;
  color: #78bff5;
}

.btn-secondary {
  border-color: #2d2d2d;
  background: #151515;
  color: #cfcfcf;
}

.btn-primary:disabled,
.btn-secondary:disabled {
  opacity: 0.6;
  cursor: default;
}

.run-list {
  display: grid;
  gap: 10px;
  margin-top: 14px;
}

.run-detail {
  display: grid;
  gap: 16px;
}

.run-summary-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.summary-card {
  border: 1px solid #1f1f1f;
  background: #121212;
  border-radius: 10px;
  padding: 12px;
  display: grid;
  gap: 6px;
}

.summary-label {
  color: #7d7d7d;
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
}

.summary-card strong {
  color: #f4f4f4;
  font-size: 15px;
}

.summary-card small {
  color: #8b8b8b;
  font-size: 11px;
}

.detail-columns {
  display: grid;
  grid-template-columns: minmax(220px, 0.8fr) minmax(0, 1.2fr);
  gap: 16px;
}

.detail-columns h4 {
  color: #f1f1f1;
  font-size: 13px;
  margin-bottom: 9px;
}

.detail-list {
  margin: 0;
  padding-left: 18px;
  color: #b7b7b7;
  display: grid;
  gap: 8px;
  font-size: 12px;
}

.json-preview {
  margin: 0;
  padding: 12px;
  border-radius: 10px;
  background: #111;
  border: 1px solid #1d1d1d;
  color: #88d0ff;
  font-size: 12px;
  white-space: pre-wrap;
  word-break: break-word;
}

.error-banner,
.empty-state {
  border-radius: 10px;
  border: 1px solid #3f2a2a;
  background: #1d1010;
  color: #efb0b0;
  padding: 12px 14px;
  font-size: 12px;
}

.empty-state {
  border-color: #222;
  background: #0f0f0f;
  color: #888;
}

.empty-state--small {
  padding: 12px;
}

.type-hint-card {
  margin-top: 12px;
  border: 1px solid #1f2630;
  background: #0f1318;
  border-radius: 10px;
  padding: 11px 12px;
}

.type-hint-card strong {
  display: block;
  color: #d9e7f2;
  font-size: 12px;
  margin-bottom: 4px;
}

.type-hint-card p {
  color: #8a97a3;
  font-size: 11px;
  line-height: 1.45;
}

.help-dot {
  width: 16px;
  height: 16px;
  border-radius: 999px;
  border: 1px solid #36516a;
  background: #0f1b26;
  color: #7eb7e1;
  font: inherit;
  font-size: 10px;
  line-height: 1;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: help;
  padding: 0;
}

@media (max-width: 1480px) {
  .detail-grid,
  .detail-columns {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 1180px) {
  .strategy-lab-view {
    flex-direction: column;
  }

  .strategy-sidebar {
    width: 100%;
    max-width: none;
    min-width: 0;
    border-right: 0;
    border-bottom: 1px solid #171717;
    max-height: 320px;
  }

  .form-grid.two-up,
  .form-grid.three-up,
  .json-grid,
  .run-summary-grid {
    grid-template-columns: 1fr;
  }
}
</style>
