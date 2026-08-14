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
    <p v-else-if="scansQuery.isPending.value" class="market-gauge__state" role="status" aria-live="polite" aria-atomic="true">Loading saved scans…</p>
    <template v-else-if="gauge">
      <div class="market-gauge__reading"><b>{{ percentage }}</b><span>{{ gauge.matched_count }} matches</span></div>
      <p>{{ gauge.evaluated_count }}/{{ gauge.universe_count }} evaluated · {{ gauge.exclusions.length }} excluded</p>
      <small>{{ gauge.run_at ? `Updated ${new Date(gauge.run_at).toLocaleString()}` : gauge.exclusions[0]?.message ?? 'Run scan first.' }}</small>
      <small v-if="gauge.data_provenance" class="market-gauge__lineage">{{ gauge.data_provenance }} · {{ gauge.calculation_version }}</small>
      <small v-if="gauge.exclusions.length" class="market-gauge__warnings" :title="gauge.exclusions.map(item => item.message).join('\n')">Coverage warnings: {{ gauge.exclusions.length }}</small>
    </template>
    <p v-else class="market-gauge__state" role="status" aria-live="polite" aria-atomic="true">Choose a retained EasyScan result.</p>
  </section>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useQuery } from '@tanstack/vue-query'
import { api } from '@/lib/api'
import { formatWorkstationFreshness, normalizeWorkstationFreshness } from '@/lib/workstation/freshness'
type Scan = { id: number; name: string }
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
let visibilityObserver: IntersectionObserver | null = null
function updateDocumentVisibility() { documentVisible.value = document.visibilityState !== 'hidden' }
const scansQuery = useQuery({
  queryKey: ['workstation', 'screeners'],
  queryFn: async () => (await api.get<Scan[]>('/screeners')) ?? [],
  staleTime: 60_000,
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
const loading = computed(() => scansQuery.isFetching.value || gaugeQuery.isFetching.value)
const error = computed(() => {
  const cause = scansQuery.error.value ?? gaugeQuery.error.value
  return cause instanceof Error ? cause.message : cause ? 'Unable to load market gauge' : ''
})
const percentage = computed(() => gauge.value?.percentage == null ? '—' : `${(gauge.value.percentage * 100).toFixed(1)}%`)
const freshnessKind = computed(() => normalizeWorkstationFreshness(gauge.value?.freshness) || 'unavailable')
const freshnessLabel = computed(() => formatWorkstationFreshness(gauge.value?.freshness))
async function refresh() {
  await scansQuery.refetch()
  if (selectedId.value) await gaugeQuery.refetch()
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
  document.removeEventListener('visibilitychange', updateDocumentVisibility)
  visibilityObserver?.disconnect()
  visibilityObserver = null
})
</script>

<style scoped>
.market-gauge { display: grid; align-content: start; gap: 7px; height: 100%; padding: 7px; background: #11161b; color: #9aabb6; font: 10px "Segoe UI", Arial, sans-serif; }.market-gauge__controls { display: grid; grid-template-columns: minmax(0, 1fr) auto auto; gap: 4px; align-items: center; }.market-gauge select,.market-gauge button { min-width: 0; height: 20px; border: 1px solid #34434e; background: #172027; color: #d2dce3; font: inherit; }.market-gauge button { padding: 0 6px; cursor: pointer; }.market-gauge button:disabled { cursor: wait; opacity: .65; }.market-gauge__freshness { color: #a9c8a2; white-space: nowrap; text-transform: capitalize; }.market-gauge__freshness[data-freshness="delayed"],.market-gauge__freshness[data-freshness="stale"],.market-gauge__freshness[data-freshness="coverage-limited"] { color: #dfbd82; }.market-gauge__freshness[data-freshness="unavailable"] { color: #e99a9a; }.market-gauge__reading { display:flex; align-items:baseline; justify-content:space-between; }.market-gauge__reading b { color:#78b9e4; font-size:24px; font-weight:500; }.market-gauge p,.market-gauge small { margin:0; }.market-gauge__lineage,.market-gauge__warnings { color: #778994; }.market-gauge__error { color:#e99a9a; }.market-gauge__state { margin:0; }
</style>
