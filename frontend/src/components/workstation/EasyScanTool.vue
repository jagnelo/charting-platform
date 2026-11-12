<template>
  <section class="easy-scan" :class="{ 'easy-scan--plot-drop-active': plotDropActive }" @dragover.prevent="dragOverPlot" @dragleave="dragLeavePlot" @drop.prevent="dropPlot">
    <p v-if="plotDropActive" class="easy-scan__plot-drop-hint" role="status" aria-live="polite" aria-atomic="true">Drop to add the chart plot as a technical condition</p>
    <div class="easy-scan__builder">
      <input v-model.trim="conditionName" aria-label="Condition name" placeholder="Condition name" />
      <select v-model="field" aria-label="Price field"><option value="close">Close</option><option value="volume">Volume</option></select>
      <select v-model="operator" aria-label="Comparison"><option value="gt">&gt;</option><option value="gte">≥</option><option value="lt">&lt;</option><option value="lte">≤</option></select>
      <input v-model="value" aria-label="Condition threshold" inputmode="decimal" placeholder="Value" />
      <button type="button" :disabled="busy || !validCondition" @click="saveCondition">Save</button>
    </div>
    <button ref="advancedToggle" type="button" class="easy-scan__advanced-toggle" :aria-controls="advancedConditionId" :aria-expanded="advancedMode" @click="toggleAdvancedConditions">{{ advancedMode ? 'Use simple condition' : 'Build technical condition tree' }}</button>
    <div v-if="advancedMode" :id="advancedConditionId" ref="advancedRoot" class="easy-scan__advanced-drag-source" role="region" aria-label="Advanced technical condition builder" draggable="true" @dragstart="startConditionDrag">
      <ConditionGroupEditor v-model="advancedGroup" class="easy-scan__advanced" aria-label="Technical condition tree" />
    </div>
    <div class="easy-scan__controls">
      <select v-model="selectedKey" :disabled="busy" aria-label="Saved condition">
        <option value="">Select saved condition</option>
        <option v-for="condition in conditions" :key="condition.stable_key" :value="condition.stable_key">{{ condition.name }} · v{{ condition.version }}</option>
      </select>
      <select v-model="selectedPythonVersion" :disabled="busy" aria-label="Python condition">
        <option value="">Python condition: Off</option>
        <option v-for="asset in pythonConditions" :key="asset.versionId" :value="String(asset.versionId)">{{ asset.name }}</option>
      </select>
      <select v-model="universeType" :disabled="busy" aria-label="Scan universe">
        <option value="all">All instruments</option>
        <option value="watchlist">Watchlist ID</option>
        <option value="basket">Basket ID</option>
        <option value="custom">Instrument IDs</option>
      </select>
      <input v-if="universeType !== 'all'" v-model.trim="universeValue" :disabled="busy" aria-label="Scan universe value" :placeholder="universeType === 'custom' ? '1,2,3' : 'ID'" />
      <select v-model="scanTimeframe" :disabled="busy" aria-label="Scan timeframe">
        <option v-for="timeframe in scanTimeframes" :key="timeframe" :value="timeframe">{{ timeframe }}</option>
      </select>
      <select v-model="scanSchedule" :disabled="busy" aria-label="Scan schedule">
        <option value="manual">Manual</option>
        <option value="daily_close">Daily close</option>
        <option value="weekly_close">Weekly close</option>
      </select>
      <input v-model.trim="scanName" :disabled="busy || (!selectedKey && !selectedPythonVersion)" aria-label="Scan name" placeholder="EasyScan name" />
      <button type="button" :disabled="busy || (!selectedKey && !selectedPythonVersion) || !scanName" @click="run">Run</button>
    </div>
    <p v-if="error" class="easy-scan__error" role="alert" aria-live="assertive" aria-atomic="true">{{ error }}</p>
    <p v-if="plotDropStatus" class="easy-scan__drop-status" role="status" aria-live="polite" aria-atomic="true">{{ plotDropStatus }}</p>
    <p v-if="preparationNotice" class="easy-scan__preparation-notice" role="status" aria-live="polite" aria-atomic="true">{{ preparationNotice }}</p>
    <p v-if="busy || activeRunStatus" class="easy-scan__state" role="status" aria-live="polite" aria-atomic="true"><span>{{ activeRunStatus || status }}</span><button v-if="activeResearchRunId" type="button" @click="cancelPythonRun">Cancel</button></p>
    <div v-if="result" class="easy-scan__result">
      <label v-if="resultHistory.length" class="easy-scan__history">Result <select v-model="selectedResultId" aria-label="Scan result history"><option value="">Latest</option><option v-for="item in resultHistory" :key="item.id" :value="String(item.id)">{{ item.run_at ? new Date(item.run_at).toLocaleString() : `Run ${item.id}` }}</option></select></label>
      <span><b>{{ result.matched_ids?.length ?? 0 }}</b> matches · {{ coverageText }}</span>
      <span class="easy-scan__alert"><select v-model="alertTrigger" aria-label="Scan alert trigger"><option value="entered">Entry</option><option value="left">Exit</option><option value="both">Entry/exit</option></select><button type="button" :disabled="busy || !scanId" @click="createAlert">{{ alertCreated ? 'Alert active' : 'Alert' }}</button></span>
    </div>
    <p v-else-if="!busy" class="easy-scan__state" role="status" aria-live="polite" aria-atomic="true">Save a price/volume condition, then run it against local canonical data.</p>
  </section>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, useId, watch } from 'vue'
import { useQueryClient } from '@tanstack/vue-query'
import { api, setQueuedApiRequestPriority, type ApiRequestPriority } from '@/lib/api'
import { PreparationProgressRefreshQueue, dataPreparationCoordinator, isPreparationTimeframe, preparationStatusMessage, savedScreenerPreparationContextKey, shouldRefreshAnalysisProgress } from '@/lib/dataPreparation'
import ConditionGroupEditor from '@/components/workstation/ConditionGroupEditor.vue'
import { createDefaultTechnicalCondition } from '@/lib/technicalConditions'
import { CHART_PLOT_DRAG_MIME, createTechnicalConditionDragPayload, readChartPlotDrag, writeTechnicalConditionDrag, technicalConditionFromPlot } from '@/lib/workstation/plotDrag'
import { fetchCodeAssets } from '@/lib/workstation/libraryQueries'
import type { Timeframe } from '@/types'

type ConditionAsset = { stable_key: string; name: string; version: number; payload: { condition?: Record<string, unknown>; python_code_version_id?: number } }
type ScanResult = { id?: number; run_at?: string; matched_ids?: number[]; result_data?: Record<string, unknown>; error?: string | null }
type SavedScanDefinition = {
  id: number
  name: string
  universe_type: 'all' | 'watchlist' | 'basket' | 'custom' | string
  universe_watchlist_id?: number | null
  universe_asset_class_id?: number | null
  universe_basket_id?: number | null
  universe_instrument_ids?: number[] | null
  timeframe: string
  conditions: Record<string, unknown>
  schedule?: string | null
  is_active?: boolean
  created_at?: string
  updated_at: string
}

const props = withDefaults(defineProps<{ sourceWindowKey?: string; requestPriority?: ApiRequestPriority }>(), {
  sourceWindowKey: 'easy-scan',
  requestPriority: 'auto',
})
const queryClient = useQueryClient()
const easyScanInstanceId = useId()
const advancedConditionId = `${easyScanInstanceId}-advanced-conditions`

const conditions = ref<ConditionAsset[]>([])
const pythonConditions = ref<Array<{ versionId: number; name: string }>>([])
const selectedKey = ref('')
const selectedPythonVersion = ref('')
const conditionName = ref('')
const field = ref('close')
const operator = ref('gt')
const value = ref('')
const advancedMode = ref(false)
const advancedGroup = ref({ operator: 'AND' as const, conditions: [createDefaultTechnicalCondition()] })
const scanName = ref('')
const universeType = ref<'all' | 'watchlist' | 'basket' | 'custom'>('all')
const universeValue = ref('')
const scanTimeframe = ref('D1')
const scanTimeframes = ['M1', 'M5', 'M15', 'M30', 'H1', 'H2', 'H4', 'H12', 'D1', 'W1', 'MN']
const scanSchedule = ref<'manual' | 'daily_close' | 'weekly_close'>('manual')
const busy = ref(false)
const status = ref('')
const error = ref('')
const preparationNotice = ref('')
const result = ref<ScanResult | null>(null)
const resultHistory = ref<ScanResult[]>([])
const selectedResultId = ref('')
const scanId = ref<number | null>(null)
const resultContextKey = ref('')
const alertTrigger = ref('entered')
const alertCreated = ref(false)
const cancelRequested = ref(false)
const activeResearchRunId = ref<number | null>(null)
const activeRunStatus = ref('')
const plotDropActive = ref(false)
const plotDropStatus = ref('')
const advancedToggle = ref<HTMLButtonElement | null>(null)
const advancedRoot = ref<HTMLElement | null>(null)
let mounted = false
let loadGeneration = 0
let runGeneration = 0
let preparationController: AbortController | null = null
let preparationContextKey = ''
let preparationRefreshQueue = new PreparationProgressRefreshQueue()
const validCondition = computed(() => Boolean(conditionName.value) && (advancedMode.value
  ? advancedGroup.value.conditions.length > 0
  : Number.isFinite(Number(value.value))))
const coverageText = computed(() => {
  const coverage = result.value?.result_data?._coverage as { evaluated_count?: number; universe_count?: number; excluded?: Record<string, unknown> } | undefined
  if (!coverage) return 'coverage unavailable'
  const excluded = Object.keys(coverage.excluded ?? {}).length
  return `${coverage.evaluated_count ?? 0}/${coverage.universe_count ?? 0} evaluated${excluded ? ` · ${excluded} excluded` : ''}`
})

async function load() {
  const generation = ++loadGeneration
  try {
    const [saved, assets] = await Promise.all([
      queryClient.fetchQuery<ConditionAsset[]>({
        queryKey: ['workstation', 'library-items', 'condition'],
        queryFn: ({ signal }) => api.get<ConditionAsset[]>('/workspaces/library/conditions', undefined, {
          signal, priority: props.requestPriority, queueKey: 'easy-scan:conditions',
        }),
        staleTime: 30_000,
      }),
      fetchCodeAssets(queryClient, { priority: props.requestPriority }),
    ])
    if (!mounted || generation !== loadGeneration) return
    conditions.value = saved
    pythonConditions.value = assets.filter(asset => asset.kind === 'condition').flatMap(asset => asset.versions.filter(version => version.id != null && version.output_contract === 'boolean').slice(-1).map(version => ({ versionId: version.id as number, name: `${asset.name} v${version.version_number}` })))
  }
  catch (cause: any) {
    if (mounted && generation === loadGeneration) error.value = cause?.message ?? 'Unable to load conditions'
  }
}
function stableKey(name: string) {
  return name.toLowerCase().trim().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 72) || 'condition'
}
function toggleAdvancedConditions() {
  advancedMode.value = !advancedMode.value
  if (advancedMode.value) void nextTick(() => {
    const firstControl = advancedRoot.value?.querySelector<HTMLElement>('select, input, button')
    firstControl?.focus()
  })
  else void nextTick(() => advancedToggle.value?.focus())
}
function startConditionDrag(event: DragEvent) {
  if (!event.dataTransfer) return
  writeTechnicalConditionDrag(event.dataTransfer, createTechnicalConditionDragPayload(advancedGroup.value, scanTimeframe.value as Timeframe, props.sourceWindowKey, conditionName.value || 'Technical conditions'))
}
function dragOverPlot(event: DragEvent) {
  const types = event.dataTransfer ? Array.from(event.dataTransfer.types) : []
  if (types.includes(CHART_PLOT_DRAG_MIME)) plotDropActive.value = true
}
function dragLeavePlot(event: DragEvent) {
  const current = event.currentTarget as HTMLElement | null
  const related = event.relatedTarget as Node | null
  if (!current || !related || !current.contains(related)) plotDropActive.value = false
}
function dropPlot(event: DragEvent) {
  plotDropActive.value = false
  const payload = readChartPlotDrag(event.dataTransfer)
  if (!payload) return
  const condition = technicalConditionFromPlot(payload)
  if (!condition) {
    plotDropStatus.value = 'This multi-output indicator cannot be added until an explicit output is selected.'
    return
  }
  advancedMode.value = true
  advancedGroup.value = { ...advancedGroup.value, conditions: [...advancedGroup.value.conditions, condition] }
  if (!conditionName.value) conditionName.value = `${payload.indicator.label} condition`
  plotDropStatus.value = `Added ${payload.indicator.label} to technical conditions`
  error.value = ''
}
async function saveCondition() {
  if (!validCondition.value) return
  busy.value = true; error.value = ''; status.value = 'Saving condition…'
  const key = stableKey(conditionName.value)
  try {
    const condition = advancedMode.value
      ? advancedGroup.value
      : { operator: 'AND', conditions: [{ type: 'price_threshold', field: field.value, op: operator.value, value: Number(value.value) }] }
    const saved = await api.put<ConditionAsset>(`/workspaces/library/conditions/${encodeURIComponent(key)}`, {
      name: conditionName.value,
      condition,
      dependency_metadata: { source: 'workstation-easyscan-builder', version: 1 },
    }, { priority: 'high' })
    const index = conditions.value.findIndex(item => item.stable_key === saved.stable_key)
    if (index >= 0) conditions.value.splice(index, 1, saved); else conditions.value.push(saved)
    conditions.value.sort((left, right) => left.name.localeCompare(right.name))
    queryClient.setQueryData<ConditionAsset[]>(['workstation', 'library-items', 'condition'], current => {
      const next = (current ?? []).filter(item => item.stable_key !== saved.stable_key)
      next.push(saved)
      return next.sort((left, right) => left.name.localeCompare(right.name))
    })
    void queryClient.invalidateQueries({ queryKey: ['workstation', 'library-items', 'condition'] })
    selectedKey.value = saved.stable_key
    // A visual save is compiled by the backend into the same immutable Python
    // Boolean version used by every other programmable surface.  Select that
    // version immediately so the first Run follows the isolated Python path.
    if (Number.isInteger(saved.payload?.python_code_version_id)) {
      selectedPythonVersion.value = String(saved.payload.python_code_version_id)
    }
    scanName.value = `${saved.name} Scan`
  } catch (cause: any) { error.value = cause?.message ?? 'Unable to save condition' }
  finally { busy.value = false }
}
async function run() {
  if (busy.value || (!selectedKey.value && !selectedPythonVersion.value) || !scanName.value) return
  const generation = ++runGeneration
  const isCurrentRun = () => mounted && generation === runGeneration
  busy.value = true; error.value = ''; preparationNotice.value = ''; alertCreated.value = false; cancelRequested.value = false; status.value = 'Preparing local EasyScan…'
  activeResearchRunId.value = null
  activeRunStatus.value = ''
  try {
    const universe: Record<string, unknown> = { universe_type: universeType.value, timeframe: scanTimeframe.value }
    if (scanSchedule.value !== 'manual') universe.schedule = scanSchedule.value === 'daily_close' ? '0 16 * * 1-5' : '0 16 * * 5'
    if (universeType.value === 'watchlist' || universeType.value === 'basket') {
      const id = Number(universeValue.value)
      if (!Number.isSafeInteger(id) || id <= 0) throw new Error(`Enter a valid ${universeType.value} ID`)
      universe[universeType.value === 'watchlist' ? 'universe_watchlist_id' : 'universe_basket_id'] = id
    } else if (universeType.value === 'custom') {
      const tokens = universeValue.value.split(',').map(item => item.trim()).filter(Boolean)
      if (!tokens.length || tokens.some(value => !/^\d+$/.test(value) || !Number.isSafeInteger(Number(value)) || Number(value) <= 0)) {
        throw new Error('Enter valid positive instrument IDs for the custom scan universe.')
      }
      universe.universe_instrument_ids = [...new Set(tokens.map(Number))]
    }
    let scan: { id: number }
    try {
      scan = await api.post<{ id: number }>(selectedPythonVersion.value
        ? `/screeners/from-python-condition/${encodeURIComponent(selectedPythonVersion.value)}`
        : `/screeners/from-condition/${encodeURIComponent(selectedKey.value)}`, { name: scanName.value, ...universe }, { priority: 'high' })
    } catch (cause: any) {
      if (!String(cause?.message ?? '').includes('→ 409:')) throw cause
      const existing = await queryClient.fetchQuery<Array<{ id: number; name: string }>>({
        queryKey: ['workstation', 'screeners'],
        queryFn: async ({ signal }) => (await api.get<Array<{ id: number; name: string }>>('/screeners', undefined, {
          signal, priority: 'high', queueKey: 'easy-scan:screener-list',
        })) ?? [],
        staleTime: 0,
      })
      const found = existing.find(item => item.name.toLowerCase() === scanName.value.toLowerCase())
      if (!found) throw cause
      scan = found
    }
    if (!isCurrentRun()) return
    const priorResultContext = resultContextKey.value
    scanId.value = scan.id
    // Publish the canonical scan immediately. Several already-mounted Gauge and
    // EasyScan tools can have overlapping list requests; a late response from
    // before creation must not hide the scan the user just ran.
    queryClient.setQueryData<Array<{ id: number; name: string }>>(['workstation', 'screeners'], current => {
      const existing = current ?? []
      const next = existing.filter(item => item.id !== scan.id)
      next.push({ id: scan.id, name: scanName.value })
      return next.sort((left, right) => left.name.localeCompare(right.name))
    })
    const savedDefinition = await api.get<SavedScanDefinition>(`/screeners/${scan.id}`, undefined, {
      priority: 'high', queueKey: `easy-scan:definition:${scan.id}`,
    })
    if (!savedDefinition) throw new Error('The saved scan definition is unavailable; no scan was run.')
    if (!isCurrentRun()) return
    assertSavedScanMatchesIntent(savedDefinition, universe)
    const savedContext = savedScreenerContextKey(savedDefinition)
    if (priorResultContext && priorResultContext !== savedContext) {
      result.value = null
      resultHistory.value = []
      selectedResultId.value = ''
    }
    resultContextKey.value = savedContext
    startSavedScreenerPreparation(savedDefinition, savedContext)
    // Market Gauge and other tools share the saved-scan query. Invalidate it
    // immediately so an already-mounted tab sees newly-created/reused scans
    // without requiring a manual refresh or remount.
    // The newly-created scan is already in the shared cache above. Refreshing
    // other mounted scan selectors is useful, but a slow list request must not
    // hold the user's Run action or its local evaluation behind it.
    void queryClient.invalidateQueries({ queryKey: ['workstation', 'screeners'] })
      .then(() => queryClient.refetchQueries({ queryKey: ['workstation', 'screeners'], type: 'all' }))
      .catch(() => undefined)
    status.value = 'Evaluating canonical local data…'
    const priorResult = result.value
    const submitted = await api.post<ScanResult>(`/screeners/${scan.id}/run`, {}, { priority: 'high' })
    if (!isCurrentRun()) return
    await followSubmittedScan(scan.id, submitted, isCurrentRun, priorResult)
    if (!isCurrentRun()) return
    await queryClient.invalidateQueries({ queryKey: ['workstation', 'screener-history', scan.id] })
    await loadResultHistory(scan.id, { selectLatest: activeRunStatus.value === 'Scan completed.', priority: 'high' })
  } catch (cause: any) { if (isCurrentRun()) error.value = cause?.message ?? 'Unable to run scan' }
  finally { if (isCurrentRun()) busy.value = false }
}

function scanResultStatus(scanResult: ScanResult): string {
  return String(scanResult.result_data?._status ?? '').toLowerCase()
}

function scanResultIsPending(scanResult: ScanResult): boolean {
  return ['queued', 'pending', 'running', 'leased'].includes(scanResultStatus(scanResult))
}

function scanResultIsCompleted(scanResult: ScanResult): boolean {
  return scanResultStatus(scanResult) === 'completed'
    || (!scanResultStatus(scanResult) && scanResult.result_data?._coverage != null)
}

function mostUsefulResult(results: ScanResult[]): ScanResult | undefined {
  return results.find(scanResultIsCompleted) ?? results[0]
}

function scanResearchRunId(scanResult: ScanResult): number | null {
  const value = scanResult.result_data?._python_research_run_id
  return Number.isSafeInteger(value) && Number(value) > 0 ? Number(value) : null
}

function scanResultRowId(scanResult: ScanResult): number | null {
  return Number.isSafeInteger(scanResult.id) && Number(scanResult.id) > 0 ? Number(scanResult.id) : null
}

function scanProgressMessage(value: string): string {
  if (value === 'queued' || value === 'pending') return 'Scan queued; waiting for results…'
  if (value === 'running' || value === 'leased') return 'Scan running…'
  return value ? `Scan status: ${value}.` : 'Scan submitted; waiting for results…'
}

async function followSubmittedScan(
  savedScanId: number,
  submitted: ScanResult,
  isCurrent: () => boolean,
  previousResult: ScanResult | null,
): Promise<void> {
  if (!isCurrent()) return
  void queryClient.invalidateQueries({ queryKey: ['workstation', 'screener-history', savedScanId] })
  const submittedStatus = scanResultStatus(submitted)
  const researchRunId = scanResearchRunId(submitted)
  const resultId = scanResultRowId(submitted)
  if (scanResultIsCompleted(submitted) || (!submittedStatus && researchRunId == null)) {
    result.value = submitted
    activeRunStatus.value = 'Scan completed.'
    activeResearchRunId.value = null
    return
  }
  if (submittedStatus === 'failed' || submittedStatus === 'canceled') {
    result.value = previousResult
    activeRunStatus.value = submittedStatus === 'failed' ? 'Scan failed.' : 'Scan canceled.'
    activeResearchRunId.value = null
    if (submitted.error) error.value = submitted.error
    return
  }
  if (researchRunId == null && resultId == null) {
    result.value = previousResult
    activeRunStatus.value = 'Scan submitted; its status identifier is unavailable.'
    error.value = 'The scan status could not be tracked. The last completed result remains available.'
    return
  }

  activeResearchRunId.value = researchRunId
  activeRunStatus.value = scanProgressMessage(submittedStatus)
  while (isCurrent()) {
    await new Promise(resolve => setTimeout(resolve, 250))
    if (!isCurrent()) return
    const retained = await queryClient.fetchQuery<ScanResult[]>({
      queryKey: ['workstation', 'screener-results', savedScanId],
      queryFn: async ({ signal }) => (await api.get<ScanResult[]>(`/screeners/${savedScanId}/results`, { limit: 20 }, {
        signal, priority: 'high', queueKey: `easy-scan:poll:${savedScanId}`,
      })) ?? [],
      staleTime: 0,
    })
    if (!isCurrent()) return
    const matching = retained.find(item => researchRunId != null
      ? scanResearchRunId(item) === researchRunId
      : scanResultRowId(item) === resultId)
    if (!matching) continue
    const currentStatus = scanResultStatus(matching)
    if (scanResultIsCompleted(matching)) {
      result.value = matching
      activeRunStatus.value = 'Scan completed.'
      activeResearchRunId.value = null
      return
    }
    if (currentStatus === 'failed' || currentStatus === 'canceled') {
      result.value = previousResult
      activeRunStatus.value = currentStatus === 'failed' ? 'Scan failed.' : 'Scan canceled.'
      activeResearchRunId.value = null
      if (matching.error) error.value = matching.error
      return
    }
    activeRunStatus.value = scanProgressMessage(currentStatus)
  }
}

function canonicalValue(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(canonicalValue)
  if (!value || typeof value !== 'object') return value
  return Object.fromEntries(Object.entries(value as Record<string, unknown>).sort(([left], [right]) => left.localeCompare(right)).map(([key, item]) => [key, canonicalValue(item)]))
}

function expectedSavedCondition(): Record<string, unknown> {
  const selectedCondition = conditions.value.find(item => item.stable_key === selectedKey.value)
  const versionId = selectedPythonVersion.value
    ? Number(selectedPythonVersion.value)
    : selectedCondition?.payload?.python_code_version_id
  if (Number.isInteger(versionId) && Number(versionId) > 0) return { type: 'python_condition', code_version_id: Number(versionId) }
  const condition = selectedCondition?.payload?.condition
  if (!condition || typeof condition !== 'object' || Array.isArray(condition)) throw new Error('The selected condition has no saved executable definition.')
  return condition
}

function assertSavedScanMatchesIntent(saved: SavedScanDefinition, universe: Record<string, unknown>) {
  const same = (left: unknown, right: unknown) => JSON.stringify(canonicalValue(left)) === JSON.stringify(canonicalValue(right))
  const sameUniverse = saved.universe_type === universe.universe_type
    && saved.timeframe === universe.timeframe
    && (saved.universe_watchlist_id ?? null) === (universe.universe_watchlist_id ?? null)
    && (saved.universe_basket_id ?? null) === (universe.universe_basket_id ?? null)
    && (saved.universe_asset_class_id ?? null) === (universe.universe_asset_class_id ?? null)
    && same([...(saved.universe_instrument_ids ?? [])].sort((a, b) => a - b), [...((universe.universe_instrument_ids as number[] | undefined) ?? [])].sort((a, b) => a - b))
    && (saved.schedule ?? null) === (universe.schedule ?? null)
  if (!sameUniverse || !same(saved.conditions, expectedSavedCondition())) {
    throw new Error('This scan name is already saved with different condition, universe, or timeframe inputs. Choose a different name to keep the saved scan unchanged.')
  }
  if (!isPreparationTimeframe(saved.timeframe)) throw new Error('The saved scan timeframe is not supported for history preparation.')
}

function startSavedScreenerPreparation(saved: SavedScanDefinition, contextKey: string): void {
  if (!isPreparationTimeframe(saved.timeframe)) throw new Error('The saved scan timeframe is not supported for history preparation.')
  preparationController?.abort()
  const controller = new AbortController()
  const actionGeneration = runGeneration
  preparationController = controller
  preparationContextKey = contextKey
  preparationRefreshQueue = new PreparationProgressRefreshQueue()
  let receivedInitialProgress = false
  preparationNotice.value = `Preparing saved scan “${saved.name}”…`
  const isCurrent = () => mounted && preparationController === controller && preparationContextKey === contextKey
    && runGeneration === actionGeneration
  void dataPreparationCoordinator.ensure({
    target: { kind: 'screener', screener_id: saved.id },
    datasets: ['history'],
    timeframe: saved.timeframe,
  }, {
    signal: controller.signal,
    priority: 'high',
    contextKey,
    onProgress: progress => {
      if (!isCurrent()) return
      preparationNotice.value = `${preparationStatusMessage(progress.response)} ${progress.completed}/${progress.total} data tasks.`
      const refreshAnalysis = receivedInitialProgress && shouldRefreshAnalysisProgress(progress.response)
      receivedInitialProgress = true
      if (refreshAnalysis) {
        void preparationRefreshQueue.request(progress.response, async () => {
          if (!isCurrent() || resultContextKey.value !== contextKey) return
          const refreshed = await api.post<ScanResult>(`/screeners/${saved.id}/run`, {}, { priority: 'high' })
          if (!isCurrent() || resultContextKey.value !== contextKey) return
          const priorCompleted = result.value && scanResultIsCompleted(result.value) ? result.value : mostUsefulResult(resultHistory.value) ?? null
          await followSubmittedScan(saved.id, refreshed, isCurrent, priorCompleted)
          if (!isCurrent() || resultContextKey.value !== contextKey) return
          await queryClient.invalidateQueries({ queryKey: ['workstation', 'screener-history', saved.id] })
          if (isCurrent() && resultContextKey.value === contextKey) {
            await loadResultHistory(saved.id, { selectLatest: activeRunStatus.value === 'Scan completed.', priority: 'high' })
          }
        })
      }
    },
  }).then(response => {
    if (isCurrent()) preparationNotice.value = `${preparationStatusMessage(response)} Scan coverage will report any missing local data.`
  }).catch(cause => {
    if (isCurrent() && !(cause instanceof DOMException && cause.name === 'AbortError')) {
      preparationNotice.value = 'History preparation could not be started. The scan still uses its available local coverage.'
    }
  })
}

function savedScreenerContextKey(saved: SavedScanDefinition): string {
  return savedScreenerPreparationContextKey(saved)
}
async function loadResultHistory(id: number, options: { selectLatest?: boolean; priority?: ApiRequestPriority } = {}) {
  try {
    resultHistory.value = await queryClient.fetchQuery<ScanResult[]>({
      queryKey: ['workstation', 'screener-history', id],
      queryFn: async ({ signal }) => (await api.get<ScanResult[]>(`/screeners/${id}/results`, { limit: 20 }, {
        signal, priority: options.priority ?? props.requestPriority, queueKey: `easy-scan:history:${id}`,
      })) ?? [],
      staleTime: 5_000,
    })
    const preferred = mostUsefulResult(resultHistory.value)
    if (preferred && options.selectLatest !== false) {
      result.value = preferred
      selectedResultId.value = preferred.id == null ? '' : String(preferred.id)
    } else if (selectedResultId.value) {
      const selected = resultHistory.value.find(item => String(item.id) === selectedResultId.value)
      if (selected && !(scanResultIsPending(selected) && result.value && scanResultIsCompleted(result.value))) {
        result.value = selected
      }
    }
  } catch (cause: any) {
    // A completed scan remains usable when retention is unavailable.
    status.value = cause?.message ?? 'Scan history unavailable'
  }
}
async function cancelPythonRun() {
  if (!activeResearchRunId.value || cancelRequested.value) return
  cancelRequested.value = true
  activeRunStatus.value = 'Cancel requested…'
  try { await api.post(`/research/runs/${activeResearchRunId.value}/cancel`, {}, { priority: 'high' }) }
  catch (cause: any) { cancelRequested.value = false; error.value = cause?.message ?? 'Unable to cancel scan' }
}
async function createAlert() {
  if (!scanId.value || alertCreated.value) return
  busy.value = true; error.value = ''; status.value = 'Creating scan alert…'
  try { await api.post('/alerts/screener', { screener_id: scanId.value, trigger_type: alertTrigger.value, repeat: true }, { priority: 'high' }); alertCreated.value = true }
  catch (cause: any) { error.value = cause?.message ?? 'Unable to create scan alert' }
  finally { busy.value = false }
}
watch(selectedKey, key => { if (key && !scanName.value) scanName.value = `${conditions.value.find(item => item.stable_key === key)?.name ?? 'EasyScan'} Scan` })
watch(selectedPythonVersion, version => { if (version && !scanName.value) scanName.value = `${pythonConditions.value.find(item => item.versionId === Number(version))?.name ?? 'Python'} Scan` })
watch(selectedResultId, id => {
  if (!id) return
  const selected = resultHistory.value.find(item => String(item.id) === id)
  if (!selected) return
  if (scanResultIsPending(selected) && result.value && scanResultIsCompleted(result.value)) {
    activeRunStatus.value = scanProgressMessage(scanResultStatus(selected))
    return
  }
  result.value = selected
})
watch(() => [props.requestPriority, scanId.value] as const, ([priority, id]) => {
  if (priority !== 'high') return
  setQueuedApiRequestPriority('workstation:code-assets', 'high')
  setQueuedApiRequestPriority('easy-scan:conditions', priority)
  setQueuedApiRequestPriority('easy-scan:screener-list', priority)
  if (id) {
    setQueuedApiRequestPriority(`easy-scan:definition:${id}`, priority)
    setQueuedApiRequestPriority(`easy-scan:history:${id}`, priority)
    setQueuedApiRequestPriority(`easy-scan:poll:${id}`, priority)
  }
})
onMounted(() => {
  mounted = true
  void load()
})
onBeforeUnmount(() => {
  mounted = false
  loadGeneration += 1
  runGeneration += 1
  preparationController?.abort()
})
</script>

<style scoped>
.easy-scan { position: relative; display: grid; align-content: start; gap: 6px; height: 100%; min-width: 0; overflow: auto; padding: 6px; background: #11161b; color: #c7d0d8; font: 10px "Segoe UI", Arial, sans-serif; container-type: inline-size; }
.easy-scan--plot-drop-active { outline: 1px solid #69a9d2; outline-offset: -1px; }
.easy-scan__plot-drop-hint { position: absolute; z-index: 4; inset: 3px 3px auto; margin: 0; padding: 4px 6px; border: 1px solid #69a9d2; background: #193040eF; color: #dcecf6; text-align: center; pointer-events: none; }
.easy-scan__builder { display: grid; grid-template-columns: minmax(70px, 1fr) 56px 34px 58px 38px; gap: 3px; }
.easy-scan__controls { display: grid; grid-template-columns: repeat(3, minmax(80px, 1fr)) minmax(70px, 1fr) minmax(90px, 1fr) 38px; gap: 3px; }
.easy-scan__advanced-toggle { justify-self: start; padding: 2px 6px; }
.easy-scan__advanced-drag-source { cursor: grab; }
.easy-scan__advanced-drag-source:active { cursor: grabbing; }
.easy-scan__advanced { display: grid; gap: 4px; min-width: 0; padding: 4px; border: 1px solid var(--tc-border); background: var(--tc-panel-bg); color: var(--tc-text); }
.easy-scan__advanced :deep(.condition-group) { gap: 4px; padding: 4px; }
.easy-scan__advanced :deep(.condition-group__children) { gap: 4px; }
.easy-scan__advanced :deep(.tech-cond-card) { gap: 4px; }
.easy-scan__advanced :deep(.field-label) { color: var(--tc-text-muted); font-size: 11px; }
.easy-scan__advanced :deep(.form-input),
.easy-scan__advanced :deep(.form-select) { min-height: 26px; padding-block: 3px; }
.easy-scan__advanced header { display: flex; align-items: center; justify-content: space-between; color: var(--tc-text-muted); font-size: 12px; }
.easy-scan__advanced header select { width: min(150px, 45%); }
.easy-scan__advanced > button { justify-self: start; padding: 2px 6px; }
input, select, button { min-width: 0; border: 1px solid #34434e; background: #172027; color: #d2dce3; font: inherit; }
input { padding: 2px 4px; } button { cursor: pointer; } button:disabled { cursor: default; opacity: .5; }
.easy-scan__state, .easy-scan__result, .easy-scan__error, .easy-scan__drop-status, .easy-scan__preparation-notice { margin: 2px 0; color: #8498a6; } .easy-scan__result { display:flex; align-items:center; gap:8px; flex-wrap:wrap; }.easy-scan__result b { color: #78b9e4; } .easy-scan__error { color: #e99a9a; }.easy-scan__drop-status { color: #9ec6a0; }.easy-scan__preparation-notice { color: #9bb6c3; }.easy-scan__history { display:flex; align-items:center; gap:3px; }.easy-scan__alert { display:flex; gap:3px; margin-top:4px; }.easy-scan__alert select,.easy-scan__alert button,.easy-scan__history select { border:1px solid #34434e; background:#172027; color:#d2dce3; font:inherit; }
@container (max-width: 560px) {
  .easy-scan__builder { grid-template-columns: repeat(5, minmax(0, 1fr)); }
  .easy-scan__controls { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
</style>
