<template>
  <section class="research-results-tool">
    <header>
      <strong>Persisted runs</strong>
      <button type="button" :disabled="loading" @click="refresh">Refresh</button>
    </header>
    <p v-if="error" class="research-results-tool__error">{{ error }}</p>
    <p v-else-if="loading && !runs.length" class="research-results-tool__notice">Loading reproducible research runs…</p>
    <p v-else-if="!runs.length" class="research-results-tool__notice">No persisted studies yet. Run a study in the adjacent Study Lab pane.</p>
    <div v-else class="research-results-tool__runs" role="list">
      <button
        v-for="run in runs"
        :key="run.id"
        type="button"
        role="listitem"
        :class="{ 'research-results-tool__run--selected': selectedRun?.id === run.id }"
        class="research-results-tool__run"
        @click="selectedRun = run"
      >
        <strong>Run #{{ run.id }}</strong>
        <span :class="`research-results-tool__status--${run.status}`">{{ run.status }}</span>
        <small>{{ run.artifacts.length }} artifact{{ run.artifacts.length === 1 ? '' : 's' }}</small>
      </button>
    </div>
    <article v-if="selectedRun" class="research-results-tool__detail">
      <strong>Run #{{ selectedRun.id }}</strong>
      <small v-if="selectedRun.reproducibility_hash">{{ selectedRun.reproducibility_hash }}</small>
      <p v-if="selectedRun.diagnostics?.length">{{ selectedRun.diagnostics.join(' · ') }}</p>
      <div v-if="selectedRun.artifacts.length" class="research-results-tool__artifacts">
        <article v-for="artifact in selectedRun.artifacts" :key="artifact.id">
          <strong>{{ artifact.name }}</strong><small>{{ artifact.artifact_type }}</small>
          <strong v-if="artifact.artifact_type === 'scalar'">{{ artifact.payload.value ?? '—' }}</strong>
          <table v-else-if="artifact.artifact_type === 'table' && tableRows(artifact).length"><thead><tr><th v-for="column in tableColumns(artifact)" :key="column">{{ column }}</th></tr></thead><tbody><tr v-for="(row, index) in tableRows(artifact)" :key="index"><td v-for="column in tableColumns(artifact)" :key="column">{{ formatCell(row[column]) }}</td></tr></tbody></table>
          <StudySeriesUPlot v-else-if="artifact.artifact_type === 'series' && seriesData(artifact)" :name="artifact.name" :timestamps="seriesData(artifact)!.timestamps" :values="seriesData(artifact)!.values" />
          <div v-else-if="artifact.artifact_type === 'events'" class="research-results-tool__events"><button v-for="(event, index) in eventRows(artifact)" :key="`${event.symbol}-${event.timestamp}-${index}`" type="button" @click="emit('occurrence', event)"><strong>{{ event.symbol }}</strong><span>{{ event.timestamp }}</span></button></div>
          <pre v-else>{{ artifactText(artifact.payload) }}</pre>
        </article>
      </div>
      <p v-else class="research-results-tool__notice">No structured artifacts have been produced yet.</p>
    </article>
  </section>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { api } from '@/lib/api'
import StudySeriesUPlot from './StudySeriesUPlot.vue'

interface ResearchRunSummary {
  id: number
  status: string
  reproducibility_hash?: string | null
  diagnostics?: string[]
  artifacts: Array<{ id: number; name: string; artifact_type: string; payload: Record<string, unknown> }>
}

const runs = ref<ResearchRunSummary[]>([])
const selectedRun = ref<ResearchRunSummary | null>(null)
const loading = ref(false)
const error = ref('')
const emit = defineEmits<{ occurrence: [event: { symbol: string; timestamp: string; kind?: string }] }>()
const shouldPoll = computed(() => runs.value.some(run => !['completed', 'failed', 'canceled'].includes(run.status)))
let poller: ReturnType<typeof setInterval> | null = null

function artifactText(payload: Record<string, unknown>) { return JSON.stringify(payload.value ?? payload, null, 2) }
function tableRows(artifact: ResearchRunSummary['artifacts'][number]): Array<Record<string, unknown>> {
  const value = artifact.payload.value
  return Array.isArray(value) && value.every(row => row && typeof row === 'object' && !Array.isArray(row)) ? value as Array<Record<string, unknown>> : []
}
function tableColumns(artifact: ResearchRunSummary['artifacts'][number]) { return [...new Set(tableRows(artifact).flatMap(row => Object.keys(row)))] }
function formatCell(value: unknown) { return value == null ? '—' : typeof value === 'number' ? value.toLocaleString(undefined, { maximumFractionDigits: 6 }) : String(value) }
function seriesData(artifact: ResearchRunSummary['artifacts'][number]): { timestamps: string[]; values: Array<number | null> } | null {
  const value = artifact.payload.value
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  const candidate = value as { timestamps?: unknown; values?: unknown }
  return Array.isArray(candidate.timestamps) && candidate.timestamps.every(item => typeof item === 'string') && Array.isArray(candidate.values) && candidate.timestamps.length === candidate.values.length && candidate.values.every(item => item == null || typeof item === 'number') ? { timestamps: candidate.timestamps, values: candidate.values } : null
}
function eventRows(artifact: ResearchRunSummary['artifacts'][number]): Array<{ symbol: string; timestamp: string; kind?: string }> {
  const value = artifact.payload.value
  return Array.isArray(value) ? value.filter((item): item is { symbol: string; timestamp: string; kind?: string } => Boolean(item) && typeof item === 'object' && typeof (item as Record<string, unknown>).symbol === 'string' && typeof (item as Record<string, unknown>).timestamp === 'string') : []
}

async function refresh() {
  loading.value = true
  error.value = ''
  try {
    runs.value = await api.get<ResearchRunSummary[]>('/research/runs', { limit: 25 })
    const retained = selectedRun.value ? runs.value.find(run => run.id === selectedRun.value?.id) : null
    selectedRun.value = retained ?? runs.value[0] ?? null
    if (!shouldPoll.value && poller) { clearInterval(poller); poller = null }
  } catch (cause: any) {
    error.value = cause?.message ?? 'Unable to load persisted research runs'
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  void refresh()
  poller = setInterval(() => { if (shouldPoll.value) void refresh() }, 1000)
})
onBeforeUnmount(() => { if (poller) clearInterval(poller) })
</script>

<style scoped>
.research-results-tool { display:grid; grid-template-rows:auto minmax(55px,.35fr) minmax(0,1fr); gap:6px; height:100%; min-height:0; padding:6px; color:#cbd5dc; background:#11161b; font:10px "Segoe UI",Arial,sans-serif; }.research-results-tool header { display:flex; align-items:center; gap:6px; }.research-results-tool header button { margin-left:auto; }.research-results-tool button { border:1px solid #3a4954; background:#172027; color:#dce6ed; font:inherit; cursor:pointer; }.research-results-tool button:disabled { opacity:.55; cursor:default; }.research-results-tool__runs { overflow:auto; display:grid; align-content:start; gap:3px; }.research-results-tool__run { display:grid; grid-template-columns:minmax(55px,1fr) auto auto; gap:5px; padding:5px; text-align:left; }.research-results-tool__run:hover,.research-results-tool__run--selected { background:#1d3543; border-color:#52748a; }.research-results-tool__run small,.research-results-tool__detail small,.research-results-tool__notice { color:#8195a3; }.research-results-tool__detail { border-top:1px solid #34424c; padding-top:5px; overflow:auto; }.research-results-tool__detail p { margin:4px 0; }.research-results-tool__artifacts { display:grid; gap:5px; }.research-results-tool__artifacts article { display:grid; gap:3px; border-top:1px solid #29343c; padding-top:4px; }.research-results-tool__artifacts article > small { color:#8195a3; }.research-results-tool__artifacts table { border-collapse:collapse; width:100%; }.research-results-tool__artifacts th,.research-results-tool__artifacts td { padding:2px 4px; border:1px solid #2c3943; text-align:left; }.research-results-tool__events { display:grid; gap:2px; }.research-results-tool__events button { display:grid; grid-template-columns:50px 1fr; padding:3px 4px; text-align:left; }.research-results-tool__events span { color:#91a8b4; }.research-results-tool__artifacts pre { margin:0; max-height:100px; overflow:auto; white-space:pre-wrap; }.research-results-tool__error { color:#f0a2a2; }.research-results-tool__status--completed { color:#82c49b; }.research-results-tool__status--failed,.research-results-tool__status--canceled { color:#ed9696; }.research-results-tool__status--queued,.research-results-tool__status--running { color:#80bce8; }
</style>
