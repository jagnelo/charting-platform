<template>
  <section ref="gaugeRoot" class="market-gauge" role="region" aria-label="Market Gauge" :aria-busy="loading">
    <header class="market-gauge__controls">
      <select v-model="selectedId" aria-label="Saved EasyScan">
        <option value="">Select saved EasyScan</option>
        <option v-for="scan in scans" :key="scan.id" :value="String(scan.id)">{{ scan.name }}</option>
      </select>
      <button type="button" :disabled="loading" @click="refresh">{{ loading ? 'Refreshing…' : 'Refresh' }}</button>
    <span v-if="gauge" class="market-gauge__freshness" role="status" aria-live="polite" aria-atomic="true" :data-freshness="freshnessKind">{{ freshnessLabel }}</span>
    </header>
    <p v-if="error" class="market-gauge__error" role="alert" aria-live="assertive" aria-atomic="true">{{ error }}</p>
    <p v-else-if="preparationNotice" class="market-gauge__preparation" role="status" aria-live="polite" aria-atomic="true">{{ preparationNotice }}</p>
    <p v-if="scanReplacementPending" class="market-gauge__preparation" role="status" aria-live="polite" aria-atomic="true">A replacement scan is {{ latestScanStatus }}; the last completed gauge remains visible.</p>
    <p v-else-if="latestGaugeRefreshPending" class="market-gauge__preparation" role="status" aria-live="polite" aria-atomic="true">Refreshing gauge metrics for the completed scan; the last completed gauge remains visible.</p>
    <p v-else-if="gaugeRefreshNotice" class="market-gauge__preparation" role="status" aria-live="polite" aria-atomic="true">{{ gaugeRefreshNotice }}</p>
    <p v-else-if="scansQuery.isPending.value && !gauge" class="market-gauge__state" role="status" aria-live="polite" aria-atomic="true">Loading saved scans…</p>
    <template v-if="gauge">
      <div class="market-gauge__reading"><b>{{ percentage }}</b><span>{{ gauge.matched_count }} matches</span></div>
      <p>{{ gauge.evaluated_count }}/{{ gauge.universe_count }} evaluated · {{ gauge.exclusions.length }} excluded</p>
      <small>{{ gauge.run_at ? `Updated ${new Date(gauge.run_at).toLocaleString()}` : gauge.exclusions[0]?.message ?? 'Run scan first.' }}</small>
      <small v-if="gauge.data_provenance" class="market-gauge__lineage">{{ gauge.data_provenance }} · {{ gauge.calculation_version }}</small>
      <small v-if="gauge.exclusions.length" class="market-gauge__warnings" :title="gauge.exclusions.map(item => item.message).join('\n')">Coverage warnings: {{ gauge.exclusions.length }}</small>
    </template>
    <p v-else-if="!error && !scanReplacementPending && !scansQuery.isPending.value" class="market-gauge__state" role="status" aria-live="polite" aria-atomic="true">Choose a retained EasyScan result.</p>
  </section>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useQuery } from '@tanstack/vue-query'
import { api, setQueuedApiRequestPriority, type ApiRequestPriority } from '@/lib/api'
import { formatWorkstationFreshness, normalizeWorkstationFreshness } from '@/lib/workstation/freshness'
import { PreparationProgressRefreshQueue, dataPreparationCoordinator, isPreparationTimeframe, preparationStatusMessage, savedScreenerPreparationContextKey, shouldRefreshAnalysisProgress } from '@/lib/dataPreparation'
type Scan = { id: number; name: string }
type SavedScanDefinition = {
  id: number
  name: string
  universe_type: string
  universe_watchlist_id?: number | null
  universe_asset_class_id?: number | null
  universe_basket_id?: number | null
  universe_instrument_ids?: number[] | null
  timeframe: string
  conditions: Record<string, unknown>
  schedule?: string | null
  updated_at: string
}
type Gauge = {
  matched_count: number
  evaluated_count: number
  universe_count: number
  percentage: number | null
  run_at: string | null
  freshness: string
  data_provenance: string
  calculation_version: string
  refreshed_at: string
  freshness_detail: Record<string, number>
  exclusions: Array<{ code?: string; message: string }>
}
type ScanResult = { id?: number; run_at?: string | null; result_data?: Record<string, unknown> }
const selectedId = ref('')
const props = withDefaults(defineProps<{ requestPriority?: ApiRequestPriority }>(), { requestPriority: 'auto' })
const gaugeRoot = ref<HTMLElement | null>(null)
const surfaceVisible = ref(true)
const documentVisible = ref(typeof document === 'undefined' || document.visibilityState !== 'hidden')
const preparationNotice = ref('')
let preparationController: AbortController | null = null
let preparationContextKey = ''
let preparationRefreshQueue = new PreparationProgressRefreshQueue()
let visibilityObserver: IntersectionObserver | null = null
let gaugeRefreshGeneration = 0
let gaugeRefreshPending = false
let gaugeRefreshDrain: Promise<void> | null = null
const lastCompletedGauge = ref<Gauge | null>(null)
const latestGaugeRefreshPending = ref(false)
const gaugeRefreshNotice = ref('')
function updateDocumentVisibility() { documentVisible.value = document.visibilityState !== 'hidden' }
const scansQuery = useQuery({
  queryKey: ['workstation', 'screeners'],
  queryFn: async ({ signal }) => (await api.get<Scan[]>('/screeners', undefined, {
    signal, priority: props.requestPriority, queueKey: 'market-gauge:screeners',
  })) ?? [],
  staleTime: 60_000,
  refetchOnWindowFocus: true,
})
const savedScanQuery = useQuery({
  queryKey: computed(() => ['workstation', 'screener-definition', selectedId.value]),
  queryFn: async ({ signal }) => {
    const id = selectedId.value
    const definition = await api.get<SavedScanDefinition>(`/screeners/${encodeURIComponent(id)}`, undefined, {
      signal, priority: props.requestPriority, queueKey: `market-gauge:definition:${id}`,
    })
    if (!definition) throw new Error('The saved EasyScan definition is unavailable.')
    return definition
  },
  enabled: computed(() => Boolean(selectedId.value)),
  staleTime: 0,
  refetchOnWindowFocus: true,
})
const scanResultsQuery = useQuery({
  queryKey: computed(() => ['workstation', 'screener-history', selectedId.value]),
  queryFn: async ({ signal }) => {
    const id = selectedId.value
    return (await api.get<ScanResult[]>(`/screeners/${encodeURIComponent(id)}/results`, { limit: 20 }, {
      signal, priority: props.requestPriority, queueKey: `market-gauge:history:${id}`,
    })) ?? []
  },
  enabled: computed(() => Boolean(selectedId.value) && surfaceVisible.value && documentVisible.value),
  staleTime: 0,
  refetchOnWindowFocus: true,
  refetchInterval: query => {
    const latest = query.state.data?.[0]
    const status = String(latest?.result_data?._status ?? '').toLowerCase()
    return ['queued', 'pending', 'running', 'leased'].includes(status) ? 350 : false
  },
})
const latestScanResult = computed(() => scanResultsQuery.data.value?.[0] ?? null)
const latestScanStatus = computed(() => String(latestScanResult.value?.result_data?._status ?? '').toLowerCase())
const scanReplacementPending = computed(() => ['queued', 'pending', 'running', 'leased'].includes(latestScanStatus.value))
const gaugeQuery = useQuery({
  queryKey: computed(() => ['workstation', 'market-gauge', selectedId.value]),
  queryFn: async ({ signal }) => {
    const id = selectedId.value
    const result = await api.get<Gauge>(`/analysis/gauges/${id}`, undefined, {
      signal, priority: props.requestPriority, queueKey: `market-gauge:metrics:${id}`,
    })
    if (!result) throw new Error('Market gauge refresh returned no data')
    return result
  },
  enabled: computed(() => Boolean(selectedId.value) && surfaceVisible.value && documentVisible.value
    && scanResultsQuery.isFetched.value && !scanReplacementPending.value),
  staleTime: 30_000,
  refetchInterval: 60_000,
  refetchOnWindowFocus: true,
})
const scans = computed(() => scansQuery.data.value ?? [])
const gauge = computed(() => (scanReplacementPending.value || latestGaugeRefreshPending.value || Boolean(gaugeRefreshNotice.value))
  ? lastCompletedGauge.value ?? gaugeQuery.data.value ?? null
  : gaugeQuery.data.value ?? lastCompletedGauge.value ?? null)
const loading = computed(() => scansQuery.isFetching.value || savedScanQuery.isFetching.value || scanResultsQuery.isFetching.value || gaugeQuery.isFetching.value)
const error = computed(() => {
  if (savedScanQuery.error.value) return 'The saved EasyScan definition is unavailable; existing gauge results remain visible.'
  const cause = scansQuery.error.value ?? gaugeQuery.error.value
  return cause instanceof Error ? cause.message : cause ? 'Unable to load market gauge' : ''
})
const percentage = computed(() => gauge.value?.percentage == null ? '—' : `${(gauge.value.percentage * 100).toFixed(1)}%`)
const freshnessKind = computed(() => normalizeWorkstationFreshness(gauge.value?.freshness) || 'unavailable')
const freshnessLabel = computed(() => formatWorkstationFreshness(gauge.value?.freshness))
watch(() => [props.requestPriority, selectedId.value] as const, ([priority, id]) => {
  if (priority !== 'high') return
  setQueuedApiRequestPriority('market-gauge:screeners', 'high')
  if (id) {
    setQueuedApiRequestPriority(`market-gauge:definition:${id}`, 'high')
    setQueuedApiRequestPriority(`market-gauge:history:${id}`, 'high')
    setQueuedApiRequestPriority(`market-gauge:metrics:${id}`, 'high')
  }
})
watch(() => gaugeQuery.data.value, value => {
  if (value && !scanReplacementPending.value && !latestGaugeRefreshPending.value) lastCompletedGauge.value = value
})
function requestLatestGaugeRefresh(expectedId = selectedId.value): Promise<void> {
  if (!expectedId || expectedId !== selectedId.value || !surfaceVisible.value || !documentVisible.value) return Promise.resolve()
  latestGaugeRefreshPending.value = true
  gaugeRefreshNotice.value = ''
  gaugeRefreshPending = true
  if (!gaugeRefreshDrain) {
    gaugeRefreshDrain = (async () => {
      while (gaugeRefreshPending) {
        gaugeRefreshPending = false
        const id = selectedId.value
        const generation = gaugeRefreshGeneration
        const isCurrent = () => generation === gaugeRefreshGeneration
          && id === selectedId.value
          && surfaceVisible.value
          && documentVisible.value

        // A GET started for the previous queued result can still be in flight
        // when Results publishes completion. Let it settle, then issue one
        // fresh metrics read so its late zero values cannot be the last write.
        if (gaugeQuery.isFetching.value) await gaugeQuery.refetch({ cancelRefetch: false })
        if (!isCurrent()) return
        // Requests received while the stale GET was draining are covered by
        // this post-drain read and should coalesce into it.
        gaugeRefreshPending = false
        await gaugeQuery.refetch()
        if (!isCurrent()) return
        const latestResult = latestScanResult.value
        if (gaugeQuery.data.value
          && latestResult?.result_data?._status === 'completed'
          && (!latestResult.run_at || gaugeQuery.data.value.run_at === latestResult.run_at)) {
          lastCompletedGauge.value = gaugeQuery.data.value
          latestGaugeRefreshPending.value = false
          gaugeRefreshNotice.value = ''
        } else if (latestResult?.result_data?._status === 'completed') {
          latestGaugeRefreshPending.value = false
          gaugeRefreshNotice.value = 'The completed scan is not reflected in gauge metrics yet; the last completed gauge remains visible.'
        }
      }
    })().finally(() => {
      gaugeRefreshDrain = null
      if (gaugeRefreshPending) void requestLatestGaugeRefresh()
    })
  }
  return gaugeRefreshDrain
}
watch([selectedId, surfaceVisible, documentVisible], ([id, visible, docVisible], [previousId]) => {
  gaugeRefreshGeneration += 1
  gaugeRefreshPending = false
  if (id !== previousId) {
    lastCompletedGauge.value = null
    latestGaugeRefreshPending.value = false
    gaugeRefreshNotice.value = ''
  }
  preparationController?.abort()
  preparationController = null
  preparationContextKey = ''
  preparationNotice.value = ''
  preparationRefreshQueue = new PreparationProgressRefreshQueue()
  if (visible && docVisible && latestGaugeRefreshPending.value) void requestLatestGaugeRefresh(id)
})
watch([selectedId, latestScanStatus], ([id, status], [previousId, previousStatus]) => {
  if (id && id === previousId && ['queued', 'pending', 'running', 'leased'].includes(previousStatus)
    && !['queued', 'pending', 'running', 'leased'].includes(status)) {
    void requestLatestGaugeRefresh(id)
  }
})
watch([() => savedScanQuery.data.value, surfaceVisible, documentVisible], ([definition, visible]) => {
  if (!definition || !selectedId.value || !visible || !documentVisible.value) return
  if (String(definition.id) !== selectedId.value || !isPreparationTimeframe(definition.timeframe)) {
    preparationNotice.value = 'The saved EasyScan timeframe is not supported for automatic history preparation.'
    return
  }
  const contextKey = savedScreenerPreparationContextKey(definition)
  if (contextKey === preparationContextKey) return
  preparationController?.abort()
  const controller = new AbortController()
  preparationController = controller
  preparationContextKey = contextKey
  preparationRefreshQueue = new PreparationProgressRefreshQueue()
  let receivedInitialProgress = false
  const isCurrent = () => preparationController === controller
    && preparationContextKey === contextKey
    && selectedId.value === String(definition.id)
    && surfaceVisible.value && documentVisible.value
  preparationNotice.value = `Preparing saved scan “${definition.name}”…`
  void dataPreparationCoordinator.ensure({
    target: { kind: 'screener', screener_id: definition.id },
    datasets: ['history'],
    timeframe: definition.timeframe,
  }, {
    signal: controller.signal,
    priority: props.requestPriority,
    contextKey,
    onProgress: progress => {
      if (!isCurrent()) return
      preparationNotice.value = `${preparationStatusMessage(progress.response)} ${progress.completed}/${progress.total} data tasks.`
      const refreshAnalysis = receivedInitialProgress && shouldRefreshAnalysisProgress(progress.response)
      receivedInitialProgress = true
      if (refreshAnalysis) {
        void preparationRefreshQueue.request(progress.response, async () => {
          if (!isCurrent()) return
          await scanResultsQuery.refetch()
          if (!isCurrent() || scanReplacementPending.value) return
          await requestLatestGaugeRefresh(String(definition.id))
        })
      }
    },
  }).then(response => {
    if (isCurrent()) preparationNotice.value = `${preparationStatusMessage(response)} Available gauge results remain visible.`
  }).catch(cause => {
    if (isCurrent() && !(cause instanceof DOMException && cause.name === 'AbortError')) {
      preparationNotice.value = 'History preparation could not be started. Available gauge results remain visible.'
    }
  })
})
async function refresh() {
  await scansQuery.refetch()
  if (selectedId.value) {
    await savedScanQuery.refetch()
    await scanResultsQuery.refetch()
    if (!scanReplacementPending.value) await requestLatestGaugeRefresh()
  }
}
onMounted(() => {
  document.addEventListener('visibilitychange', updateDocumentVisibility)
  if (typeof IntersectionObserver !== 'undefined' && gaugeRoot.value) {
    visibilityObserver = new IntersectionObserver(entries => {
      surfaceVisible.value = entries.some(entry => entry.isIntersecting && entry.intersectionRatio > 0)
    })
    visibilityObserver.observe(gaugeRoot.value)
  }
})
onBeforeUnmount(() => {
  gaugeRefreshGeneration += 1
  gaugeRefreshPending = false
  preparationController?.abort()
  preparationController = null
  document.removeEventListener('visibilitychange', updateDocumentVisibility)
  visibilityObserver?.disconnect()
  visibilityObserver = null
})
</script>

<style scoped>
.market-gauge { display: grid; align-content: start; gap: 7px; height: 100%; padding: 7px; background: #11161b; color: #9aabb6; font: 10px "Segoe UI", Arial, sans-serif; }.market-gauge__controls { display: grid; grid-template-columns: minmax(0, 1fr) auto auto; gap: 4px; align-items: center; }.market-gauge select,.market-gauge button { min-width: 0; height: 20px; border: 1px solid #34434e; background: #172027; color: #d2dce3; font: inherit; }.market-gauge button { padding: 0 6px; cursor: pointer; }.market-gauge button:disabled { cursor: wait; opacity: .65; }.market-gauge__freshness { color: #a9c8a2; white-space: nowrap; text-transform: capitalize; }.market-gauge__freshness[data-freshness="delayed"],.market-gauge__freshness[data-freshness="stale"],.market-gauge__freshness[data-freshness="coverage-limited"] { color: #dfbd82; }.market-gauge__freshness[data-freshness="unavailable"] { color: #e99a9a; }.market-gauge__reading { display:flex; align-items:baseline; justify-content:space-between; }.market-gauge__reading b { color:#78b9e4; font-size:24px; font-weight:500; }.market-gauge p,.market-gauge small { margin:0; }.market-gauge__lineage,.market-gauge__warnings { color: #778994; }.market-gauge__error { color:#e99a9a; }.market-gauge__preparation { color:#9bb6c3; }.market-gauge__state { margin:0; }
</style>
