<template>
  <section ref="studyLabRoot" class="study-lab-tool">
    <header class="study-lab-tool__header">
      <div class="study-lab-tool__header-main">
        <input v-model.trim="name" aria-label="Study name" placeholder="Study name" />
        <input v-model.trim="symbol" aria-label="Study symbol" placeholder="Symbol" />
        <select v-model="factoryStudyKey" aria-label="Factory study" @change="applyFactoryStudy"><option value="custom">Custom Python</option><option v-for="template in factoryStudyTemplates" :key="template.key" :value="template.key">{{ template.name }}</option></select>
        <button type="button" :disabled="busy" @click="validate">Validate</button>
        <button type="button" :disabled="busy || !validation?.valid" @click="saveAndRun">Run</button>
      </div>
      <div class="study-lab-tool__dataset" aria-label="Study dataset controls">
        <label>Timeframe <select v-model="timeframe" aria-label="Study timeframe"><option v-for="option in timeframeOptions" :key="option.value" :value="option.value">{{ option.label }}</option></select></label>
        <label>Benchmark <input v-model.trim="benchmark" aria-label="Study benchmark" placeholder="SPY" /></label>
        <label>Universe <input v-model.trim="universeSymbols" aria-label="Study universe" placeholder="SPY, XLK, XLE" /></label>
        <label>Adjustment <select v-model="adjustment" aria-label="Study adjustment"><option value="split_adjusted">Split adjusted</option><option value="raw">Raw</option></select></label>
        <label>Session <select v-model="session" aria-label="Study session"><option value="regular">Regular</option><option value="all">All</option></select></label>
        <label>From <input v-model.trim="startDate" aria-label="Study start date" type="date" /></label>
        <label>To <input v-model.trim="endDate" aria-label="Study end date" type="date" /></label>
        <label>As of <input v-model.trim="asOf" aria-label="Study as of" type="datetime-local" /></label>
      </div>
      <p v-if="requiresDeclaredUniverse" class="study-lab-tool__universe-warning" role="status">This factory study needs a declared comma-separated universe; it will not fall back to the active symbol.</p>
      <section class="study-lab-tool__parameters" aria-label="Study parameter controls">
        <label>Parameter schema <textarea v-model="parameterSchemaText" aria-label="Study parameter schema" spellcheck="false" placeholder='{"properties":{"lookback":{"type":"integer","default":20}}}' /></label>
        <div v-if="parameterDefinitions.length" class="study-lab-tool__parameter-grid">
          <label v-for="definition in parameterDefinitions" :key="definition.name">{{ definition.name }}
            <select v-if="definition.enum?.length" :value="String(parameterDrafts[definition.name] ?? '')" :aria-label="`Study parameter ${definition.name}`" @change="setParameterDraft(definition.name, ($event.target as HTMLSelectElement).value)">
              <option v-for="option in definition.enum" :key="String(option)" :value="String(option)">{{ option }}</option>
            </select>
            <input v-else :type="definition.type === 'boolean' ? 'checkbox' : definition.type === 'number' || definition.type === 'integer' ? 'number' : 'text'" :step="definition.type === 'integer' ? '1' : 'any'" :checked="definition.type === 'boolean' ? parameterDrafts[definition.name] === true : undefined" :value="definition.type === 'boolean' ? undefined : String(parameterDrafts[definition.name] ?? '')" :aria-label="`Study parameter ${definition.name}`" @change="setParameterDraft(definition.name, definition.type === 'boolean' ? ($event.target as HTMLInputElement).checked : ($event.target as HTMLInputElement).value)" />
          </label>
        </div>
        <small v-if="parameterSchemaError" class="study-lab-tool__parameter-error">{{ parameterSchemaError }}</small>
      </section>
    </header>
    <div class="study-lab-tool__editor-shell">
      <textarea ref="editor" v-model="source" aria-label="Study Python source" spellcheck="false" @input="sourceInput" @keyup="updateSuggestions" @focus="updateSuggestions" @blur="hideSuggestions" />
      <div v-if="showSuggestions && editorSuggestions.length" class="study-lab-tool__suggestions" role="listbox" aria-label="Python SDK suggestions">
        <button v-for="suggestion in editorSuggestions" :key="suggestion.insert" type="button" role="option" @mousedown.prevent="insertSuggestion(suggestion.insert)">{{ suggestion.insert }} <small>{{ suggestion.signature }}</small></button>
      </div>
    </div>
    <details class="study-lab-tool__sdk-reference">
      <summary>SDK reference</summary>
      <span><b>market</b>: close/open/high/low/volume/vwap/ohlcv, benchmark_* accessors, timestamps, sessions, metadata</span>
      <span><b>ta</b>: sma, ema, rsi, atr, highest, lowest, rate_of_change</span>
      <span><b>stats</b>: streaks, ranks, percentiles, rolling, correlation, regression, distributions</span>
      <span><b>research</b>: forward_returns, occurrences, regimes, breadth, historical comparisons</span>
      <span><b>output</b>: scalar, boolean, series, table, events, bar, histogram, range, scatter, heatmap, dashboard</span>
    </details>
    <section v-if="validation" class="study-lab-tool__validation" :class="{ 'study-lab-tool__validation--bad': !validation.valid }">
      <strong>{{ validation.valid ? 'Validated for isolated execution' : 'Validation errors' }}</strong>
      <pre v-if="validation.diagnostics.length">{{ validation.diagnostics }}</pre>
      <span v-else>Dependencies: {{ validation.dependencies.join(', ') || 'none' }} · Lookback: {{ validation.lookback_hint ?? 'none' }} · Outputs: {{ validation.output_contracts.join(', ') || 'none' }}</span>
    </section>
    <section v-if="run" class="study-lab-tool__run">
      <div><strong>Run #{{ run.id }}</strong><span :class="`study-lab-tool__run-status--${run.status}`">{{ run.status }}</span><small v-if="progressLabel">{{ progressLabel }}</small><button v-if="canCancel" type="button" @click="cancel">Cancel</button><button v-if="canRerun" type="button" :disabled="rerunBusy" @click="rerun(true)">{{ rerunBusy ? 'Rerunning…' : 'Rerun snapshot' }}</button><button v-if="canRerun" type="button" :disabled="rerunBusy" @click="rerun(false)">{{ rerunBusy ? 'Rerunning…' : 'Rerun latest' }}</button></div>
      <div v-if="promotableKind && run.status === 'completed'" class="study-lab-tool__promotions" aria-label="Promote study result">
        <button v-if="promotableKind === 'scalar'" type="button" :disabled="promotionBusy" @click="promote('column')">{{ promotionBusy ? 'Promoting…' : 'Save as column' }}</button>
        <button v-if="promotableKind === 'series'" type="button" :disabled="promotionBusy" @click="promote('plot')">{{ promotionBusy ? 'Promoting…' : 'Save as chart plot' }}</button>
        <button v-if="promotableKind === 'boolean'" type="button" :disabled="promotionBusy" @click="promote('scan')">{{ promotionBusy ? 'Promoting…' : 'Promote to scan' }}</button>
        <button v-if="promotableKind === 'boolean'" type="button" :disabled="promotionBusy" @click="promote('alert')">{{ promotionBusy ? 'Promoting…' : 'Promote to alert' }}</button>
        <button v-if="promotableKind === 'boolean' || promotableKind === 'events'" type="button" :disabled="promotionBusy" @click="promote('signal')">{{ promotionBusy ? 'Promoting…' : 'Save as Strategy signal' }}</button>
      </div>
      <p v-if="run.reproducibility_hash">Reproducibility {{ run.reproducibility_hash }}</p>
      <p class="study-lab-tool__dataset-summary">Dataset: {{ universeSymbols || symbol }} · {{ timeframe }} · {{ adjustment === 'split_adjusted' ? 'split adjusted' : 'raw' }} · {{ session }} session · benchmark {{ benchmark || 'none' }} ({{ benchmarkCoverageLabel }}) · {{ startDate || 'earliest available' }} → {{ endDate || 'latest available' }}</p>
      <pre v-if="run.diagnostics?.length">{{ run.diagnostics }}</pre>
      <div v-if="metricArtifacts.length" class="study-lab-tool__metrics"><article v-for="artifact in metricArtifacts" :key="artifact.id" :class="{ 'study-lab-tool__metric--true': artifact.artifact_type === 'boolean' && artifact.payload.value === true, 'study-lab-tool__metric--false': artifact.artifact_type === 'boolean' && artifact.payload.value === false }"><small>{{ artifact.name }}</small><strong>{{ formatMetric(artifact) }}</strong></article></div>
      <article v-for="artifact in nonScalarArtifacts" :key="artifact.id">
        <strong>{{ artifact.name }}</strong><small>{{ artifact.artifact_type }}</small>
        <table v-if="artifact.artifact_type === 'table' && tableRows(artifact).length"><thead><tr><th v-for="column in tableColumns(artifact)" :key="column">{{ column }}</th></tr></thead><tbody><tr v-for="(row, index) in tableRows(artifact)" :key="index"><td v-for="column in tableColumns(artifact)" :key="column">{{ formatCell(row[column]) }}</td></tr></tbody></table>
        <StudySeriesUPlot v-else-if="artifact.artifact_type === 'series' && seriesData(artifact)" :name="artifact.name" :timestamps="seriesData(artifact)!.timestamps" :values="seriesData(artifact)!.values" />
        <StudyBarsUPlot v-else-if="artifact.artifact_type === 'bar' && barData(artifact)" :name="artifact.name" :labels="barData(artifact)!.labels" :values="barData(artifact)!.values" />
        <StudyHistogramUPlot v-else-if="artifact.artifact_type === 'histogram' && histogramData(artifact)" :name="artifact.name" :bins="histogramData(artifact)!.bins" :current="histogramData(artifact)!.current" />
        <StudyRangeUPlot v-else-if="artifact.artifact_type === 'range' && rangeData(artifact)" :name="artifact.name" :timestamps="rangeData(artifact)!.timestamps" :lower="rangeData(artifact)!.lower" :upper="rangeData(artifact)!.upper" :center="rangeData(artifact)!.center" />
        <StudyScatterUPlot v-else-if="artifact.artifact_type === 'scatter' && scatterData(artifact)" :name="artifact.name" :x="scatterData(artifact)!.x" :y="scatterData(artifact)!.y" />
        <StudyHeatmap v-else-if="artifact.artifact_type === 'heatmap' && heatmapData(artifact)" :name="artifact.name" :rows="heatmapData(artifact)!.rows" :columns="heatmapData(artifact)!.columns" :values="heatmapData(artifact)!.values" />
        <StudyDashboard v-else-if="artifact.artifact_type === 'dashboard' && dashboardData(artifact)" :name="artifact.name" :panels="dashboardData(artifact)!" :artifacts="run?.artifacts ?? []" @occurrence="emit('occurrence', $event)" />
        <div v-else-if="artifact.artifact_type === 'events' && eventRows(artifact).length" class="study-lab-tool__events"><button v-for="(event, index) in eventRows(artifact)" :key="`${event.timestamp}-${index}`" type="button" @click="emit('occurrence', event)"><strong>{{ event.symbol }}</strong><span>{{ event.timestamp }}</span><small>{{ event.kind ?? 'Event' }}</small></button></div>
        <pre v-else>{{ artifactText(artifact.payload) }}</pre>
      </article>
    </section>
    <p v-if="error" class="study-lab-tool__error">{{ error }}</p>
    <p v-else-if="promotionStatus" class="study-lab-tool__promotion-status" role="status">{{ promotionStatus }}</p>
    <p v-else class="study-lab-tool__notice">Canonical local data only · isolated no-network runner · results are versioned by code and dataset manifest.</p>
  </section>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useQuery } from '@tanstack/vue-query'
import { api } from '@/lib/api'
import StudyBarsUPlot from './StudyBarsUPlot.vue'
import StudyHistogramUPlot from './StudyHistogramUPlot.vue'
import StudyHeatmap from './StudyHeatmap.vue'
import StudyDashboard from './StudyDashboard.vue'
import StudyRangeUPlot from './StudyRangeUPlot.vue'
import StudyScatterUPlot from './StudyScatterUPlot.vue'
import StudySeriesUPlot from './StudySeriesUPlot.vue'

interface Validation { valid: boolean; diagnostics: unknown[]; dependencies: string[]; lookback_hint: number | null; output_contracts: string[] }
interface ParameterDefinition { name: string; type: string; default?: unknown; enum?: unknown[]; minimum?: number; maximum?: number }
interface Run { id: number; status: string; progress?: { status?: string; completed_cells?: number; total_cells?: number }; diagnostics?: unknown[]; reproducibility_hash?: string | null; dataset_manifest?: { benchmark_coverage?: { status?: string; reason?: string } }; artifacts?: Array<{ id: number; name: string; artifact_type: string; payload: Record<string, unknown> }> }
type Artifact = NonNullable<Run['artifacts']>[number]

const props = defineProps<{ activeSymbol: string; configuration?: Record<string, unknown> }>()
const emit = defineEmits<{ occurrence: [event: { symbol: string; timestamp: string; kind?: string }]; configuration: [configuration: Record<string, unknown>] }>()
const name = ref('Consecutive Positive Closes')
const symbol = ref(props.activeSymbol)
const positiveStreakSource = "streaks = stats.positive_close_streaks(dataset)\nindices = [record['end_index'] for record in streaks['records']]\noutput.scalar('current_streak', streaks['current'])\noutput.scalar('longest_streak', streaks['longest'])\noutput.scalar('average_streak', streaks['average'])\noutput.scalar('shortest_streak', streaks['shortest'])\noutput.table('completed_streaks', streaks['records'])\noutput.table('forward_returns', research.forward_returns(dataset, indices, [1, 5, 20]))\noutput.events('streak_events', research.occurrences(dataset, indices, 'positive_close_streak'))\noutput.histogram('streak_distribution', streaks['lengths'], 8, streaks['current'])"
const negativeStreakSource = "closes = market.close()\nindices = []\nlengths = []\ncurrent = 0\nfor index in range(1, len(closes)):\n    if closes[index] < closes[index - 1]:\n        current += 1\n    else:\n        if current > 0:\n            indices.append(index - 1)\n            lengths.append(current)\n        current = 0\nif current > 0:\n    indices.append(len(closes) - 1)\n    lengths.append(current)\noutput.scalar('current_negative_streak', current)\noutput.scalar('longest_negative_streak', max(lengths) if lengths else 0)\noutput.scalar('average_negative_streak', sum(lengths) / len(lengths) if lengths else 0)\noutput.scalar('shortest_negative_streak', min(lengths) if lengths else 0)\noutput.table('completed_negative_streaks', [{'end_index': index, 'length': length} for index, length in zip(indices, lengths)])\noutput.table('forward_returns', research.forward_returns(dataset, indices, [1, 5, 20]))\noutput.events('negative_streak_events', research.occurrences(dataset, indices, 'negative_close_streak'))\noutput.histogram('negative_streak_distribution', lengths, 8, current)"
const movingAverageParticipationSource = "closes = market.close()\naverage = ta.sma(closes, 20)\nparticipation = [100 if value is not None and closes[index] > value else 0 for index, value in enumerate(average)]\noutput.series('above_20_day_average', participation)\noutput.boolean('currently_above_20_day_average', participation[-1] == 100 if participation else False)\noutput.scalar('percent_above_20_day_average', sum(participation) / len(participation) if participation else 0)"
const forwardReturnDistributionSource = "closes = market.close()\nindices = [index for index in range(1, len(closes)) if closes[index] > closes[index - 1]]\nrows = research.forward_returns(dataset, indices, [1, 5, 20])\nfive_day = [row['forward_return'] for row in rows if row['horizon'] == 5]\noutput.scalar('positive_close_count', len(indices))\noutput.scalar('five_day_sample_size', len(five_day))\noutput.scalar('five_day_average_return', sum(five_day) / len(five_day) if five_day else 0)\noutput.histogram('five_day_forward_return_distribution', five_day, 12, five_day[-1] if five_day else None)\noutput.table('forward_return_observations', rows)"
const highLowBreakoutSource = "closes = market.close()\nlookback = 20\nnew_highs = []\nnew_lows = []\nfor index in range(len(closes)):\n    if index < lookback:\n        continue\n    window = closes[index - lookback:index]\n    if closes[index] > max(window):\n        new_highs.append(index)\n    if closes[index] < min(window):\n        new_lows.append(index)\noutput.scalar('new_high_count', len(new_highs))\noutput.scalar('new_low_count', len(new_lows))\noutput.events('new_high_events', research.occurrences(dataset, new_highs, '20_day_new_high'))\noutput.events('new_low_events', research.occurrences(dataset, new_lows, '20_day_new_low'))\noutput.table('new_high_forward_returns', research.forward_returns(dataset, new_highs, [1, 5, 20]))\noutput.table('new_low_forward_returns', research.forward_returns(dataset, new_lows, [1, 5, 20]))"
const volatilityRegimeSource = "closes = market.close()\nreturns = [0] + [(closes[index] / closes[index - 1]) - 1 for index in range(1, len(closes))]\nvolatility = []\nfor index in range(len(returns)):\n    window = returns[max(0, index - 19):index + 1]\n    average = sum(window) / len(window) if window else 0\n    squared_error = 0\n    for value in window:\n        squared_error += (value - average) ** 2\n    variance = squared_error / len(window) if window else 0\n    volatility.append(variance ** 0.5)\nmedian_volatility = sorted(volatility)[len(volatility) // 2] if volatility else 0\nregime = [1 if value >= median_volatility else 0 for value in volatility]\noutput.series('realised_volatility_20', volatility)\noutput.series('high_volatility_regime', regime)\noutput.boolean('currently_high_volatility', bool(regime and regime[-1]))\noutput.histogram('volatility_distribution', volatility, 12, volatility[-1] if volatility else None)"
const seasonalitySource = "timestamps = market.timestamps()\ncloses = market.close()\nreturns_by_month = {}\nfor index in range(1, len(closes)):\n    month = timestamps[index][5:7]\n    returns_by_month.setdefault(month, []).append((closes[index] / closes[index - 1]) - 1)\nmonths = sorted(returns_by_month.keys())\naverages = [sum(returns_by_month[month]) / len(returns_by_month[month]) for month in months]\noutput.bar('average_monthly_return', months, averages)\noutput.table('monthly_observations', [{'month': month, 'sample_size': len(returns_by_month[month]), 'average_return': average} for month, average in zip(months, averages)])"
const relativeStrengthRegimeSource = "closes = market.close()\nbenchmark = market.benchmark_close()\nratio = [value / base if base else None for value, base in zip(closes, benchmark)]\ntrend = ta.sma([value if value is not None else 0 for value in ratio], 20)\nchanges = []\nfor index in range(1, len(ratio)):\n    if ratio[index] is None or trend[index] is None or ratio[index - 1] is None or trend[index - 1] is None:\n        continue\n    crossed_up = ratio[index - 1] <= trend[index - 1] and ratio[index] > trend[index]\n    crossed_down = ratio[index - 1] >= trend[index - 1] and ratio[index] < trend[index]\n    if crossed_up or crossed_down:\n        changes.append(index)\noutput.series('relative_strength_ratio', ratio)\noutput.series('relative_strength_trend', trend)\noutput.scalar('regime_change_count', len(changes))\noutput.events('relative_strength_regime_changes', research.occurrences(dataset, changes, 'relative_strength_regime_change'))"
const crossSectionalRankSource = "rows = research.cross_sectional_rank(dataset, 20)\noutput.table('cross_sectional_rank', rows)\noutput.bar('trailing_20_day_return', [row['symbol'] for row in rows], [row['return'] for row in rows])\noutput.scalar('ranked_symbols', len(rows))"
const breadthParticipationSource = "breadth = research.breadth_snapshot(dataset, 20)\noutput.scalar('breadth_coverage', breadth['coverage'])\noutput.scalar('above_20_day_average', breadth['above_count'])\noutput.scalar('percent_above_20_day_average', breadth['percent_above'] if breadth['percent_above'] is not None else 0)\noutput.boolean('breadth_thrust', breadth['percent_above'] is not None and breadth['percent_above'] >= 90)\noutput.table('breadth_members', breadth['rows'])"
const source = ref(positiveStreakSource)
const factoryStudyTemplates = [
  { key: 'positive_streak', name: 'Consecutive positive closes', source: positiveStreakSource },
  { key: 'negative_streak', name: 'Consecutive negative closes', source: negativeStreakSource },
  { key: 'moving_average_participation', name: 'Moving-average participation', source: movingAverageParticipationSource },
  { key: 'forward_return_distribution', name: 'Forward-return distribution', source: forwardReturnDistributionSource },
  { key: 'high_low_breakouts', name: 'Highs and lows', source: highLowBreakoutSource },
  { key: 'volatility_regime', name: 'Volatility regime', source: volatilityRegimeSource },
  { key: 'seasonality', name: 'Monthly seasonality', source: seasonalitySource },
  { key: 'relative_strength_regime', name: 'Relative-strength regime changes', source: relativeStrengthRegimeSource },
  { key: 'cross_sectional_rank', name: 'Cross-sectional ranking', source: crossSectionalRankSource, requiresUniverse: true },
  { key: 'breadth_participation', name: 'Breadth participation', source: breadthParticipationSource, requiresUniverse: true },
  { key: 'relative_strength_history', name: 'Relative-strength history', source: "closes = market.close()\nbenchmark = market.benchmark_close()\nratio = [value / base if base else None for value, base in zip(closes, benchmark)]\noutput.series('relative_strength_ratio', ratio)\noutput.scalar('latest_relative_strength', ratio[-1] if ratio else None)" },
]
const timeframeOptions = [
  { value: 'D1', label: 'Daily' },
  { value: 'W1', label: 'Weekly' },
  { value: 'MN', label: 'Monthly' },
  { value: 'M15', label: '15 minute' },
]
const configString = (key: string, fallback: string) => typeof props.configuration?.[key] === 'string' ? String(props.configuration[key]) : fallback
const factoryStudyKey = ref('positive_streak')
const selectedFactoryStudy = computed(() => factoryStudyTemplates.find(item => item.key === factoryStudyKey.value))
const requiresDeclaredUniverse = computed(() => selectedFactoryStudy.value?.requiresUniverse === true)
const normaliseTimeframe = (value: string) => value === 'MN1' ? 'MN' : timeframeOptions.some(option => option.value === value) ? value : 'D1'
const timeframe = ref(normaliseTimeframe(configString('timeframe', 'D1')))
const benchmark = ref(configString('benchmark', 'SPY'))
const universeSymbols = ref(configString('symbols', ''))
const adjustment = ref<'split_adjusted' | 'raw'>(configString('adjustment', 'split_adjusted') === 'raw' ? 'raw' : 'split_adjusted')
const session = ref<'regular' | 'all'>(configString('session', 'regular') === 'all' ? 'all' : 'regular')
const startDate = ref(configString('start_date', ''))
const endDate = ref(configString('end_date', ''))
const asOf = ref(configString('as_of', '').slice(0, 16))
const parameterSchemaText = ref(typeof props.configuration?.parameter_schema === 'string' ? String(props.configuration.parameter_schema) : '')
const parameterDrafts = ref<Record<string, string | boolean>>({})
const editor = ref<HTMLTextAreaElement | null>(null)
const showSuggestions = ref(false)
const editorPrefix = ref('')
const editorSuggestionCatalog = [
  { prefix: 'market', insert: 'market.close()', signature: 'series[float]' },
  { prefix: 'market', insert: 'market.ohlcv()', signature: 'list[OHLCVRow]' },
  { prefix: 'market', insert: 'market.benchmark_close()', signature: 'series[float]' },
  { prefix: 'market', insert: 'market.metadata()', signature: 'dict[str, object]' },
  { prefix: 'ta', insert: 'ta.sma(market.close(), 20)', signature: 'series, period' },
  { prefix: 'ta', insert: 'ta.rsi(market.close(), 14)', signature: 'series, period' },
  { prefix: 'stats', insert: 'stats.positive_close_streaks(dataset)', signature: 'dataset' },
  { prefix: 'research', insert: 'research.forward_returns(dataset, indices, [1, 5, 20])', signature: 'dataset, events, horizons' },
  { prefix: 'research', insert: 'research.cross_sectional_rank(dataset, 20)', signature: 'dataset, lookback' },
  { prefix: 'research', insert: 'research.breadth_snapshot(dataset, 20)', signature: 'dataset, period' },
  { prefix: 'output', insert: "output.scalar('name', value)", signature: 'name, value' },
  { prefix: 'output', insert: "output.series('name', values)", signature: 'name, values' },
  { prefix: 'output', insert: "output.bar('name', labels, values)", signature: 'labels, values' },
  { prefix: 'output', insert: "output.range('name', lower, upper, center)", signature: 'lower, upper, center?' },
  { prefix: 'output', insert: "output.table('name', rows)", signature: 'name, rows' },
]
const busy = ref(false)
const promotionBusy = ref(false)
const promotionStatus = ref('')
const rerunBusy = ref(false)
const validation = ref<Validation | null>(null)
const run = ref<Run | null>(null)
const runSource = ref('')
const runContract = ref<string | null>(null)
const error = ref('')
const studyLabRoot = ref<HTMLElement | null>(null)
const surfaceVisible = ref(true)
const documentVisible = ref(typeof document === 'undefined' || document.visibilityState !== 'hidden')
let visibilityObserver: IntersectionObserver | null = null
function updateDocumentVisibility() { documentVisible.value = document.visibilityState !== 'hidden' }
const runQuery = useQuery({
  queryKey: computed(() => ['workstation', 'study-run', run.value?.id ?? null]),
  queryFn: async () => {
    const runId = run.value?.id
    if (!runId) throw new Error('Study run refresh requires a run id')
    const refreshed = await api.get<Run>(`/research/runs/${runId}`)
    if (!refreshed) throw new Error('Study run refresh returned no data')
    return refreshed
  },
  enabled: computed(() => Boolean(run.value?.id) && !['completed', 'failed', 'canceled'].includes(run.value?.status ?? '') && surfaceVisible.value && documentVisible.value),
  staleTime: 0,
  refetchOnWindowFocus: true,
  refetchInterval: query => {
    const status = query.state.data?.status
    return status && !['completed', 'failed', 'canceled'].includes(status) ? 1_000 : false
  },
})
watch(() => runQuery.data.value, next => { if (next && next.id === run.value?.id) run.value = next })
watch(() => runQuery.error.value, cause => {
  if (cause) error.value = cause instanceof Error ? cause.message : 'Unable to refresh study run'
})

const canCancel = computed(() => Boolean(run.value && !['completed', 'failed', 'canceled'].includes(run.value.status)))
const canRerun = computed(() => Boolean(run.value && ['completed', 'failed', 'canceled'].includes(run.value.status)))
const promotableKind = computed<'scalar' | 'boolean' | 'series' | 'events' | null>(() => {
  if (!run.value || run.value.status !== 'completed' || !runSource.value) return null
  return runContract.value === 'scalar' || runContract.value === 'boolean' || runContract.value === 'series' || runContract.value === 'events' ? runContract.value : null
})
const progressLabel = computed(() => {
  const progress = run.value?.progress
  if (!progress || progress.status !== 'running') return ''
  const total = Number(progress.total_cells ?? 0)
  return total > 0 ? `running ${Number(progress.completed_cells ?? 0)}/${total}` : 'runner active'
})
const metricArtifacts = computed(() => (run.value?.artifacts ?? []).filter(artifact => ['scalar', 'boolean'].includes(artifact.artifact_type)))
const nonScalarArtifacts = computed(() => (run.value?.artifacts ?? []).filter(artifact => !['scalar', 'boolean'].includes(artifact.artifact_type)))
const benchmarkCoverageLabel = computed(() => {
  const status = run.value?.dataset_manifest?.benchmark_coverage?.status
  if (status === 'ready') return 'ready'
  if (status === 'unavailable') return `unavailable: ${run.value?.dataset_manifest?.benchmark_coverage?.reason ?? 'unknown'}`
  return 'pending'
})
const parsedParameterSchema = computed<Record<string, unknown> | null>(() => {
  if (!parameterSchemaText.value.trim()) return {}
  try {
    const parsed = JSON.parse(parameterSchemaText.value)
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed as Record<string, unknown> : null
  } catch { return null }
})
const parameterDefinitions = computed<ParameterDefinition[]>(() => {
  const schema = parsedParameterSchema.value
  if (!schema) return []
  const properties = schema.properties && typeof schema.properties === 'object' && !Array.isArray(schema.properties) ? schema.properties as Record<string, unknown> : schema
  return Object.entries(properties).filter(([, value]) => value && typeof value === 'object' && !Array.isArray(value)).map(([name, value]) => {
    const spec = value as Record<string, unknown>
    return { name, type: typeof spec.type === 'string' ? spec.type : 'string', default: spec.default, enum: Array.isArray(spec.enum) ? spec.enum : undefined, minimum: typeof spec.minimum === 'number' ? spec.minimum : undefined, maximum: typeof spec.maximum === 'number' ? spec.maximum : undefined }
  })
})
const parameterSchemaError = computed(() => parameterSchemaText.value.trim() && !parsedParameterSchema.value ? 'Parameter schema must be a JSON object.' : '')
const editorSuggestions = computed(() => editorPrefix.value ? editorSuggestionCatalog.filter(item => item.prefix.startsWith(editorPrefix.value.split('.')[0]) && item.insert.startsWith(editorPrefix.value)).slice(0, 8) : [])
watch(() => props.activeSymbol, value => { if (!symbol.value || symbol.value === 'SPY') symbol.value = value })
watch(() => props.configuration, configuration => {
  if (typeof configuration?.timeframe === 'string') timeframe.value = normaliseTimeframe(configuration.timeframe)
  if (configuration && !('benchmark' in configuration)) benchmark.value = ''
  else if (typeof configuration?.benchmark === 'string') benchmark.value = configuration.benchmark
  if (configuration?.adjustment === 'raw' || configuration?.adjustment === 'split_adjusted') adjustment.value = configuration.adjustment
  if (configuration?.session === 'all' || configuration?.session === 'regular') session.value = configuration.session
  if (configuration && !('start_date' in configuration)) startDate.value = ''
  else if (typeof configuration?.start_date === 'string') startDate.value = configuration.start_date
  if (configuration && !('end_date' in configuration)) endDate.value = ''
  else if (typeof configuration?.end_date === 'string') endDate.value = configuration.end_date
  if (configuration && !('as_of' in configuration)) asOf.value = ''
  else if (typeof configuration?.as_of === 'string') asOf.value = configuration.as_of.slice(0, 16)
  if (configuration && !('symbols' in configuration)) universeSymbols.value = ''
  else if (typeof configuration?.symbols === 'string') universeSymbols.value = configuration.symbols
  if (configuration && !('parameter_schema' in configuration)) parameterSchemaText.value = ''
  else if (typeof configuration?.parameter_schema === 'string') parameterSchemaText.value = configuration.parameter_schema
}, { deep: true })
watch([timeframe, benchmark, universeSymbols, adjustment, session, startDate, endDate, asOf], () => {
  const configuration: Record<string, unknown> = { ...(props.configuration ?? {}), timeframe: timeframe.value, adjustment: adjustment.value, session: session.value }
  if (benchmark.value) configuration.benchmark = benchmark.value.toUpperCase()
  else delete configuration.benchmark
  if (startDate.value) configuration.start_date = startDate.value
  else delete configuration.start_date
  if (endDate.value) configuration.end_date = endDate.value
  else delete configuration.end_date
  if (asOf.value) configuration.as_of = asOf.value
  else delete configuration.as_of
  if (universeSymbols.value) configuration.symbols = universeSymbols.value.toUpperCase()
  else delete configuration.symbols
  emit('configuration', configuration)
})
watch(parameterSchemaText, value => {
  emit('configuration', { ...(props.configuration ?? {}), parameter_schema: value })
})
watch(parameterDefinitions, definitions => {
  const next: Record<string, string | boolean> = {}
  for (const definition of definitions) {
    const current = parameterDrafts.value[definition.name]
    if (current !== undefined) next[definition.name] = current
    else if (typeof definition.default === 'boolean') next[definition.name] = definition.default
    else if (definition.default !== undefined) next[definition.name] = String(definition.default)
    else next[definition.name] = definition.type === 'boolean' ? false : ''
  }
  parameterDrafts.value = next
}, { immediate: true })
function setParameterDraft(name: string, value: string | boolean) { parameterDrafts.value = { ...parameterDrafts.value, [name]: value } }
function updateSuggestions() {
  const element = editor.value
  if (!element) return
  const beforeCursor = source.value.slice(0, element.selectionStart)
  const match = beforeCursor.match(/(?:^|\s)([A-Za-z_]+(?:\.[A-Za-z_]*)?)$/)
  editorPrefix.value = match?.[1] ?? ''
  showSuggestions.value = Boolean(editorPrefix.value)
}
function sourceInput() { factoryStudyKey.value = 'custom'; updateSuggestions() }
function applyFactoryStudy() {
  const template = factoryStudyTemplates.find(item => item.key === factoryStudyKey.value)
  if (!template) return
  name.value = template.name
  source.value = template.source
  validation.value = null
  run.value = null
  runSource.value = ''
  runContract.value = null
  promotionStatus.value = ''
  error.value = ''
}
function hideSuggestions() { window.setTimeout(() => { showSuggestions.value = false }, 120) }
async function insertSuggestion(value: string) {
  const element = editor.value
  if (!element) return
  const cursor = element.selectionStart
  const prefix = editorPrefix.value
  source.value = `${source.value.slice(0, cursor - prefix.length)}${value}${source.value.slice(cursor)}`
  showSuggestions.value = false
  await nextTick()
  const nextCursor = cursor - prefix.length + value.length
  element.focus()
  element.setSelectionRange(nextCursor, nextCursor)
}
function buildParameters() {
  const values: Record<string, unknown> = {}
  for (const definition of parameterDefinitions.value) {
    const value = parameterDrafts.value[definition.name]
    if (value === '' || value === undefined) continue
    values[definition.name] = definition.type === 'number' || definition.type === 'integer' ? Number(value) : value
  }
  return values
}

function stableKey(value: string) { return value.toLowerCase().trim().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 56) || 'study' }
function artifactText(payload: Record<string, unknown>) { return JSON.stringify(payload.value ?? payload, null, 2) }
function formatMetric(artifact: Artifact) { return artifact.artifact_type === 'boolean' ? artifact.payload.value === true ? 'True' : artifact.payload.value === false ? 'False' : '—' : artifact.payload.value ?? '—' }
function tableRows(artifact: Artifact): Array<Record<string, unknown>> {
  const value = artifact.payload.value
  return Array.isArray(value) && value.every(row => row && typeof row === 'object' && !Array.isArray(row)) ? value as Array<Record<string, unknown>> : []
}
function tableColumns(artifact: Artifact) { return [...new Set(tableRows(artifact).flatMap(row => Object.keys(row)))] }
function formatCell(value: unknown) { return value == null ? '—' : typeof value === 'number' ? value.toLocaleString(undefined, { maximumFractionDigits: 6 }) : String(value) }
function seriesData(artifact: Artifact): { timestamps: string[]; values: Array<number | null> } | null {
  const value = artifact.payload.value
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  const candidate = value as { timestamps?: unknown; values?: unknown }
  if (!Array.isArray(candidate.timestamps) || !candidate.timestamps.every(item => typeof item === 'string') || !Array.isArray(candidate.values) || candidate.timestamps.length !== candidate.values.length || !candidate.values.every(item => item == null || typeof item === 'number')) return null
  return { timestamps: candidate.timestamps, values: candidate.values }
}
function barData(artifact: Artifact): { labels: string[]; values: number[] } | null {
  const value = artifact.payload.value
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  const candidate = value as { labels?: unknown; values?: unknown }
  return Array.isArray(candidate.labels) && candidate.labels.every(item => typeof item === 'string') && Array.isArray(candidate.values) && candidate.labels.length === candidate.values.length && candidate.values.every(item => typeof item === 'number' && Number.isFinite(item)) ? { labels: candidate.labels, values: candidate.values } : null
}
function rangeData(artifact: Artifact): { timestamps: string[]; lower: number[]; upper: number[]; center: number[] | null } | null {
  const value = artifact.payload.value
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  const candidate = value as { timestamps?: unknown; lower?: unknown; upper?: unknown; center?: unknown }
  if (!Array.isArray(candidate.timestamps) || !candidate.timestamps.every(item => typeof item === 'string') || !Array.isArray(candidate.lower) || !Array.isArray(candidate.upper) || candidate.lower.length !== candidate.upper.length || candidate.timestamps.length !== candidate.lower.length || !candidate.lower.every(item => typeof item === 'number' && Number.isFinite(item)) || !candidate.upper.every(item => typeof item === 'number' && Number.isFinite(item))) return null
  const center = candidate.center == null ? null : Array.isArray(candidate.center) && candidate.center.length === candidate.lower.length && candidate.center.every(item => typeof item === 'number' && Number.isFinite(item)) ? candidate.center : null
  return { timestamps: candidate.timestamps, lower: candidate.lower, upper: candidate.upper, center }
}
function histogramData(artifact: Artifact): { bins: Array<{ start: number; end: number; count: number }>; current: number | null } | null {
  const value = artifact.payload.value
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  const bins = (value as { bins?: unknown }).bins
  if (!Array.isArray(bins)) return null
  const normalized = bins.filter((bin): bin is { start: number; end: number; count: number } => Boolean(bin) && typeof bin === 'object' && Number.isFinite((bin as Record<string, unknown>).start) && Number.isFinite((bin as Record<string, unknown>).end) && Number.isFinite((bin as Record<string, unknown>).count))
  const current = (value as { current?: unknown }).current
  return normalized.length ? { bins: normalized, current: typeof current === 'number' && Number.isFinite(current) ? current : null } : null
}
function scatterData(artifact: Artifact): { x: number[]; y: number[] } | null {
  const value = artifact.payload.value
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  const candidate = value as { x?: unknown; y?: unknown }
  if (!Array.isArray(candidate.x) || !Array.isArray(candidate.y) || candidate.x.length !== candidate.y.length) return null
  const x = candidate.x.filter((item): item is number => typeof item === 'number' && Number.isFinite(item))
  const y = candidate.y.filter((item): item is number => typeof item === 'number' && Number.isFinite(item))
  return x.length === candidate.x.length && y.length === candidate.y.length ? { x, y } : null
}
function heatmapData(artifact: Artifact): { rows: string[]; columns: string[]; values: number[][] } | null {
  const value = artifact.payload.value
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  const candidate = value as { rows?: unknown; columns?: unknown; values?: unknown }
  if (!Array.isArray(candidate.rows) || !candidate.rows.every(item => typeof item === 'string') || !Array.isArray(candidate.columns) || !candidate.columns.every(item => typeof item === 'string') || !Array.isArray(candidate.values) || !candidate.values.every(row => Array.isArray(row) && row.every(item => typeof item === 'number' && Number.isFinite(item)))) return null
  const rows = candidate.rows as string[]
  const columns = candidate.columns as string[]
  const values = candidate.values as number[][]
  return values.length && values.every(row => row.length === columns.length) && values.length === rows.length ? { rows, columns, values } : null
}
function dashboardData(artifact: Artifact): Array<{ artifact: string; title: string; span: number }> | null {
  const value = artifact.payload.value
  if (!value || typeof value !== 'object' || Array.isArray(value) || !Array.isArray((value as { panels?: unknown }).panels)) return null
  const panels = (value as { panels: unknown[] }).panels
  const normalized = panels.filter((panel): panel is { artifact: string; title: string; span: number } => Boolean(panel) && typeof panel === 'object' && typeof (panel as Record<string, unknown>).artifact === 'string' && typeof (panel as Record<string, unknown>).title === 'string' && typeof (panel as Record<string, unknown>).span === 'number')
  return normalized.length === panels.length ? normalized : null
}
function eventRows(artifact: Artifact): Array<{ symbol: string; timestamp: string; kind?: string }> {
  const value = artifact.payload.value
  if (!Array.isArray(value)) return []
  return value.filter((item): item is { symbol: string; timestamp: string; kind?: string } => Boolean(item) && typeof item === 'object' && typeof (item as Record<string, unknown>).symbol === 'string' && typeof (item as Record<string, unknown>).timestamp === 'string').map(item => ({ symbol: item.symbol, timestamp: item.timestamp, kind: item.kind }))
}

async function validate() {
  busy.value = true; error.value = ''
  try { validation.value = await api.post<Validation>('/code/validate', { source: source.value }) }
  catch (cause: any) { error.value = cause?.message ?? 'Unable to validate study source' }
  finally { busy.value = false }
}
async function saveAndRun() {
  if (!validation.value?.valid || parameterSchemaError.value) return
  if (requiresDeclaredUniverse.value && !universeSymbols.value.split(',').some(value => value.trim())) {
    error.value = 'This factory study requires a declared comma-separated universe before it can run.'
    return
  }
  busy.value = true; error.value = ''
  try {
    runSource.value = source.value
    runContract.value = validation.value.output_contracts.length === 1 ? validation.value.output_contracts[0] : null
    promotionStatus.value = ''
    const parameters = buildParameters()
    const asset = await api.post<{ versions: Array<{ id: number }> }>('/code/assets', {
      stable_key: `${stableKey(name.value)}-${Date.now()}`,
      name: name.value,
      kind: 'study',
      initial_version: { source: source.value, output_contract: 'study', parameter_schema: parsedParameterSchema.value ?? {}, default_parameters: parameters },
    })
    const datasetControls: Record<string, string> = {
      timeframe: timeframe.value,
      adjustment: adjustment.value,
      session: session.value,
    }
    if (benchmark.value) datasetControls.benchmark = benchmark.value.toUpperCase()
    if (startDate.value) datasetControls.start_date = startDate.value
    if (endDate.value) datasetControls.end_date = endDate.value
    if (asOf.value) datasetControls.as_of = new Date(asOf.value).toISOString()
    const symbols = universeSymbols.value.split(',').map(value => value.trim().toUpperCase()).filter(Boolean)
    const runConfig: Record<string, unknown> = symbols.length ? { symbols, parameters, ...datasetControls } : { symbol: symbol.value.toUpperCase(), parameters, ...datasetControls }
    run.value = await api.post<Run>('/research/runs', {
      code_version_id: asset.versions[0].id,
      run_config: runConfig,
      dataset_manifest: { source: 'canonical_database', requested_at: new Date().toISOString(), ...datasetControls },
    })
  } catch (cause: any) { error.value = cause?.message ?? 'Unable to start isolated study run' }
  finally { busy.value = false }
}
type PromotionTarget = 'column' | 'plot' | 'scan' | 'alert' | 'signal'
async function promote(target: PromotionTarget) {
  const contract = promotableKind.value
  if (!contract || promotionBusy.value) return
  promotionBusy.value = true
  promotionStatus.value = ''
  try {
    const isBooleanTarget = target === 'scan' || target === 'alert'
    const kind = target === 'scan' || target === 'alert' ? 'condition' : target
    const asset = await api.post<{ versions: Array<{ id: number }> }>('/code/assets', {
      stable_key: `${stableKey(name.value)}-${kind}-${Date.now()}`,
      name: `${name.value} ${kind}`,
      kind,
      initial_version: {
        source: runSource.value,
        output_contract: isBooleanTarget ? 'boolean' : contract,
        parameter_schema: parsedParameterSchema.value ?? {},
        default_parameters: buildParameters(),
      },
    })
    const versionId = asset.versions[0]?.id
    if (!versionId) throw new Error('Promotion did not return a code version')
    if (target === 'column') promotionStatus.value = 'Saved as a reusable watchlist column.'
    else if (target === 'plot') promotionStatus.value = 'Saved as a reusable chart plot.'
    else if (target === 'signal') {
      await api.post(`/strategy-lab/signals/from-code/${versionId}`, {})
      promotionStatus.value = 'Saved as a reusable Strategy Lab signal.'
    }
    else {
      const scan = await api.post<{ id: number }>(`/screeners/from-python-condition/${versionId}`, {
        name: `${name.value} Scan`, universe_type: 'all', timeframe: timeframe.value,
      })
      if (target === 'alert') {
        await api.post('/alerts/screener', { screener_id: scan.id, trigger_type: 'entered', repeat: true })
        promotionStatus.value = 'Promoted to an active scan alert.'
      } else promotionStatus.value = 'Promoted to a reusable scan.'
    }
  } catch (cause: any) {
    promotionStatus.value = cause?.message ?? 'Unable to promote study result'
  } finally { promotionBusy.value = false }
}
async function rerun(snapshot: boolean) {
  if (!run.value || rerunBusy.value) return
  rerunBusy.value = true
  error.value = ''
  promotionStatus.value = ''
  try {
    run.value = await api.post<Run>(`/research/runs/${run.value.id}/rerun?snapshot=${snapshot}`, {})
  } catch (cause: any) {
    error.value = cause?.message ?? 'Unable to rerun study'
  } finally { rerunBusy.value = false }
}
async function cancel() {
  if (!run.value) return
  try { run.value = await api.post<Run>(`/research/runs/${run.value.id}/cancel`, {}) ; await runQuery.refetch() }
  catch (cause: any) { error.value = cause?.message ?? 'Unable to cancel study run' }
}
onMounted(() => {
  document.addEventListener('visibilitychange', updateDocumentVisibility)
  if (typeof IntersectionObserver !== 'undefined' && studyLabRoot.value) {
    visibilityObserver = new IntersectionObserver(entries => {
      surfaceVisible.value = entries.some(entry => entry.isIntersecting && entry.intersectionRatio > 0)
    })
    visibilityObserver.observe(studyLabRoot.value)
  }
})
onBeforeUnmount(() => {
  if (run.value && canCancel.value) void api.post(`/research/runs/${run.value.id}/cancel`, {})
  document.removeEventListener('visibilitychange', updateDocumentVisibility)
  visibilityObserver?.disconnect()
  visibilityObserver = null
})
</script>

<style scoped>
.study-lab-tool { display:grid; height:100%; min-height:0; grid-template-rows:auto minmax(110px,1fr) auto auto auto; gap:5px; padding:6px; background:#11161b; color:#cbd5dc; font:10px "Segoe UI",Arial,sans-serif; }
.study-lab-tool__editor-shell { position:relative; min-height:0; }
.study-lab-tool__editor-shell textarea { width:100%; height:100%; min-height:110px; resize:none; }
.study-lab-tool__suggestions { position:absolute; z-index:5; top:4px; left:4px; display:grid; min-width:260px; max-width:calc(100% - 8px); border:1px solid #4a6675; background:#172027; box-shadow:0 3px 10px #0008; }
.study-lab-tool__suggestions button { display:flex; justify-content:space-between; gap:8px; padding:3px 5px; border:0; border-bottom:1px solid #293740; color:#dce6ed; background:#172027; font:inherit; text-align:left; }
.study-lab-tool__suggestions button:hover { background:#25485b; }
.study-lab-tool__suggestions small { color:#8ea3b0; }
.study-lab-tool__sdk-reference { display:grid; gap:2px; color:#8195a3; }
.study-lab-tool__sdk-reference summary { cursor:pointer; color:#b5c6d0; }
.study-lab-tool__parameters { display:grid; grid-template-columns:minmax(120px, 1fr) minmax(0, 2fr); gap:5px; align-items:start; color:#8ea3b0; }
.study-lab-tool__parameters > label { display:grid; gap:2px; }
.study-lab-tool__parameters textarea { min-height:28px; resize:vertical; }
.study-lab-tool__parameter-grid { display:flex; flex-wrap:wrap; gap:4px; align-items:start; }
.study-lab-tool__parameter-grid label { display:grid; gap:2px; min-width:78px; color:#9db0bc; }
.study-lab-tool__parameter-error { color:#ed9696; grid-column:1 / -1; }
.study-lab-tool__header { display:grid; gap:4px; } .study-lab-tool__header-main { display:grid; grid-template-columns:minmax(120px,1fr) 56px minmax(150px,1fr) 48px 38px; gap:4px; } .study-lab-tool__dataset { display:grid; grid-template-columns:repeat(6,minmax(0,1fr)); gap:4px; color:#8ea3b0; } .study-lab-tool__dataset label { display:grid; grid-template-columns:auto minmax(0,1fr); align-items:center; gap:3px; white-space:nowrap; } .study-lab-tool__dataset input,.study-lab-tool__dataset select { width:100%; min-width:0; }
input,textarea,button,select { min-width:0; border:1px solid #3a4954; background:#172027; color:#dce6ed; font:inherit; } input,select { padding:2px 4px; } textarea { width:100%; resize:none; padding:5px; font:11px/1.35 ui-monospace,SFMono-Regular,monospace; } button { cursor:pointer; } button:disabled { cursor:default; opacity:.5; }
.study-lab-tool__validation,.study-lab-tool__run { padding:5px; border:1px solid #34424c; background:#151b20; } .study-lab-tool__validation--bad,.study-lab-tool__error { border-color:#9e5757; color:#f0a2a2; } pre { max-height:100px; overflow:auto; margin:3px 0 0; color:#b8c6d0; white-space:pre-wrap; } .study-lab-tool__run > div { display:flex; align-items:center; gap:6px; } .study-lab-tool__run > div button { margin-left:auto; } .study-lab-tool__run p,.study-lab-tool__notice,.study-lab-tool__error { margin:0; color:#8195a3; } .study-lab-tool__universe-warning { margin:0; color:#e0b47d; } .study-lab-tool__dataset-summary { font-size:9px; } .study-lab-tool__run article { margin-top:5px; padding-top:4px; border-top:1px solid #29343c; } .study-lab-tool__run small { margin-left:5px; color:#779ab0; }.study-lab-tool__metrics { display:grid; grid-template-columns:repeat(auto-fit,minmax(70px,1fr)); gap:4px; margin-top:5px; }.study-lab-tool__metrics article { display:grid; gap:2px; margin:0; padding:4px; border:1px solid #29343c; background:#11161b; }.study-lab-tool__metrics strong { color:#b9e0f9; font-size:14px; }.study-lab-tool__metric--true { border-color:#3f8263!important; }.study-lab-tool__metric--true strong { color:#80d5a5!important; }.study-lab-tool__metric--false { border-color:#875454!important; }.study-lab-tool__metric--false strong { color:#f0a0a0!important; }.study-lab-tool__run table { width:100%; margin-top:4px; border-collapse:collapse; font-size:9px; }.study-lab-tool__run th,.study-lab-tool__run td { padding:2px 4px; border:1px solid #2c3943; text-align:left; white-space:nowrap; }.study-lab-tool__run th { color:#91a8b8; background:#1b252d; }.study-lab-tool__events { display:grid; gap:2px; margin-top:4px; }.study-lab-tool__events button { display:grid; grid-template-columns:50px 1fr auto; gap:5px; padding:3px 4px; border:1px solid #2d3c46; background:#11161b; color:#cddbe5; text-align:left; }.study-lab-tool__events button:hover { background:#1d3543; }.study-lab-tool__events span,.study-lab-tool__events small { color:#91a8b4; }.study-lab-tool__run-status--completed { color:#82c49b; }.study-lab-tool__run-status--failed { color:#ed9696; }.study-lab-tool__run-status--queued,.study-lab-tool__run-status--running { color:#80bce8; }
.study-lab-tool__promotions { display:flex; flex-wrap:wrap; gap:4px; margin-top:4px; }.study-lab-tool__promotions button { margin-left:0!important; }.study-lab-tool__promotion-status { color:#9fd3a9!important; }
</style>
