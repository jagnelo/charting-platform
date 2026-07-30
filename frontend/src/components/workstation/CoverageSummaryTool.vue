<template>
  <section class="coverage-summary" aria-live="polite">
    <p v-if="loading" class="coverage-summary__state">Loading local coverage…</p>
    <p v-else-if="error" class="coverage-summary__state coverage-summary__state--error">{{ error }}</p>
    <template v-else>
      <div class="coverage-summary__identity">
        <span>Canonical instrument</span><strong>{{ symbol }}</strong>
      </div>
      <div v-if="daily" class="coverage-summary__grid">
        <span>Adjusted daily bars</span><b>{{ daily.bar_count.toLocaleString() }}</b>
        <span>Local range</span><b>{{ formatRange(daily.oldest, daily.newest) }}</b>
      </div>
      <p v-else class="coverage-summary__state">No local adjusted daily observations.</p>
      <div v-if="datasetStates.length" class="coverage-summary__datasets">
        <span>Dataset state</span>
        <ul>
          <li v-for="state in datasetStates" :key="`${state.dataset_type}:${state.dataset_key}`" :class="`coverage-summary__dataset--${state.status}`">
            {{ state.dataset_type }}{{ state.dataset_key ? ` · ${state.dataset_key}` : '' }}: {{ state.status }}
          </li>
        </ul>
      </div>
      <p class="coverage-summary__note">Local canonical data only · source and freshness limitations remain explicit in each dataset state.</p>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { api } from '@/lib/api'

interface CoverageRange { oldest: string | null; newest: string | null; bar_count: number }
interface DatasetState { dataset_type: string; dataset_key: string; status: 'fresh' | 'stale' | 'pending' | 'failed'; updated_at?: string | null }

const props = defineProps<{ symbol: string }>()
const loading = ref(false)
const error = ref<string | null>(null)
const coverage = ref<Record<string, CoverageRange>>({})
const datasetStates = ref<DatasetState[]>([])
let requestId = 0

const daily = computed(() => coverage.value.D1 ?? null)

watch(() => props.symbol, async symbol => {
  const id = ++requestId
  loading.value = true
  error.value = null
  try {
    const [coverageResponse, provenance] = await Promise.all([
      api.get<{ coverage: Record<string, CoverageRange> }>(`/instruments/${encodeURIComponent(symbol)}/data-coverage`),
      api.get<{ dataset_states?: DatasetState[] }>(`/instruments/${encodeURIComponent(symbol)}/provenance`),
    ])
    if (id !== requestId) return
    coverage.value = coverageResponse.coverage ?? {}
    datasetStates.value = (provenance.dataset_states ?? []).slice(0, 6)
  } catch (caught: any) {
    if (id !== requestId) return
    coverage.value = {}
    datasetStates.value = []
    error.value = caught?.message ?? 'Coverage is unavailable.'
  } finally {
    if (id === requestId) loading.value = false
  }
}, { immediate: true })

function formatRange(start: string | null, end: string | null) {
  if (!start || !end) return 'Unavailable'
  return `${new Date(start).toLocaleDateString()} – ${new Date(end).toLocaleDateString()}`
}
</script>

<style scoped>
.coverage-summary { display: grid; gap: 9px; padding: 9px; font-size: 12px; color: var(--text-secondary, #bdc5d1); }
.coverage-summary__identity, .coverage-summary__grid { display: grid; grid-template-columns: minmax(110px, 1fr) minmax(0, 1.6fr); gap: 5px 9px; align-items: baseline; }
.coverage-summary strong, .coverage-summary b { color: var(--text-primary, #f2f5f8); font-variant-numeric: tabular-nums; }
.coverage-summary__state { margin: 0; color: var(--text-secondary, #bdc5d1); }
.coverage-summary__state--error, .coverage-summary__dataset--failed { color: var(--danger, #ff7b72); }
.coverage-summary__datasets { border-top: 1px solid var(--border, #36404b); padding-top: 8px; }
.coverage-summary__datasets > span { color: var(--text-muted, #8893a1); }
.coverage-summary__datasets ul { display: grid; gap: 3px; margin: 5px 0 0; padding: 0; list-style: none; }
.coverage-summary__dataset--stale { color: var(--warning, #e8b44b); }
.coverage-summary__dataset--pending { color: var(--text-muted, #8893a1); }
.coverage-summary__note { margin: 0; color: var(--text-muted, #8893a1); font-size: 11px; line-height: 1.35; }
</style>
