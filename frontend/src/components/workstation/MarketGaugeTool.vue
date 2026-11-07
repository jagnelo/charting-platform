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
    <p v-else-if="scansQuery.isPending.value && !gauge" class="market-gauge__state" role="status" aria-live="polite" aria-atomic="true">Loading saved scans…</p>
    <template v-if="gauge">
      <div class="market-gauge__reading"><b>{{ percentage }}</b><span>{{ gauge.matched_count }} matches</span></div>
      <p>{{ gauge.evaluated_count }}/{{ gauge.universe_count }} evaluated · {{ gauge.exclusions.length }} excluded</p>
      <small>{{ gauge.run_at ? `Updated ${new Date(gauge.run_at).toLocaleString()}` : gauge.exclusions[0]?.message ?? 'Run scan first.' }}</small>
      <small v-if="gauge.data_provenance" class="market-gauge__lineage">{{ gauge.data_provenance }} · {{ gauge.calculation_version }}</small>
      <small v-if="gauge.exclusions.length" class="market-gauge__warnings" :title="gauge.exclusions.map(item => item.message).join('\n')">Coverage warnings: {{ gauge.exclusions.length }}</small>
    </template>
    <p v-else-if="!error && !scansQuery.isPending.value" class="market-gauge__state" role="status" aria-live="polite" aria-atomic="true">Choose a retained EasyScan result.</p>
  </section>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useQuery } from '@tanstack/vue-query'
import { api } from '@/lib/api'
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
const selectedId = ref('')
const gaugeRoot = ref<HTMLElement | null>(null)
const surfaceVisible = ref(true)
const documentVisible = ref(typeof document === 'undefined' || document.visibilityState !== 'hidden')
const preparationNotice = ref('')
let preparationController: AbortController | null = null
let preparationContextKey = ''
let preparationRefreshQueue = new PreparationProgressRefreshQueue()
let visibilityObserver: IntersectionObserver | null = null
function updateDocumentVisibility() { documentVisible.value = document.visibilityState !== 'hidden' }
const scansQuery = useQuery({
  queryKey: ['workstation', 'screeners'],
  queryFn: async () => (await api.get<Scan[]>('/screeners')) ?? [],
  staleTime: 60_000,
  refetchOnWindowFocus: true,
})
const savedScanQuery = useQuery({
  queryKey: computed(() => ['workstation', 'screener-definition', selectedId.value]),
  queryFn: async () => {
    const definition = await api.get<SavedScanDefinition>(`/screeners/${encodeURIComponent(selectedId.value)}`)
    if (!definition) throw new Error('The saved EasyScan definition is unavailable.')
    return definition
  },
  enabled: computed(() => Boolean(selectedId.value)),
  staleTime: 0,
  refetchOnWindowFocus: true,
})
const gaugeQuery = useQuery({
  queryKey: computed(() => ['workstation', 'market-gauge', selectedId.value]),
  queryFn: async () => {
    const result = await api.get<Gauge>(`/analysis/gauges/${selectedId.value}`)
    if (!result) throw new Error('Market gauge refresh returned no data')
    return result
  },
  enabled: computed(() => Boolean(selectedId.value) && surfaceVisible.value && documentVisible.value),
  staleTime: 30_000,
  refetchInterval: 60_000,
  refetchOnWindowFocus: true,
})
const scans = computed(() => scansQuery.data.value ?? [])
const gauge = computed(() => gaugeQuery.data.value ?? null)
const loading = computed(() => scansQuery.isFetching.value || savedScanQuery.isFetching.value || gaugeQuery.isFetching.value)
const error = computed(() => {
  if (savedScanQuery.error.value) return 'The saved EasyScan definition is unavailable; existing gauge results remain visible.'
  const cause = scansQuery.error.value ?? gaugeQuery.error.value
  return cause instanceof Error ? cause.message : cause ? 'Unable to load market gauge' : ''
})
const percentage = computed(() => gauge.value?.percentage == null ? '—' : `${(gauge.value.percentage * 100).toFixed(1)}%`)
const freshnessKind = computed(() => normalizeWorkstationFreshness(gauge.value?.freshness) || 'unavailable')
const freshnessLabel = computed(() => formatWorkstationFreshness(gauge.value?.freshness))
watch([selectedId, surfaceVisible, documentVisible], () => {
  preparationController?.abort()
  preparationController = null
  preparationContextKey = ''
  preparationNotice.value = ''
  preparationRefreshQueue = new PreparationProgressRefreshQueue()
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
    contextKey,
    onProgress: progress => {
      if (!isCurrent()) return
      preparationNotice.value = `${preparationStatusMessage(progress.response)} ${progress.completed}/${progress.total} data tasks.`
      const refreshAnalysis = receivedInitialProgress && shouldRefreshAnalysisProgress(progress.response)
      receivedInitialProgress = true
      if (refreshAnalysis) {
        void preparationRefreshQueue.request(progress.response, async () => {
          if (!isCurrent()) return
          await gaugeQuery.refetch()
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
    await gaugeQuery.refetch()
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
