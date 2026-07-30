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
      <ul v-if="selectedRun.artifacts.length">
        <li v-for="artifact in selectedRun.artifacts" :key="artifact.id"><strong>{{ artifact.name }}</strong> · {{ artifact.artifact_type }}</li>
      </ul>
      <p v-else class="research-results-tool__notice">No structured artifacts have been produced yet.</p>
    </article>
  </section>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { api } from '@/lib/api'

interface ResearchRunSummary {
  id: number
  status: string
  reproducibility_hash?: string | null
  diagnostics?: string[]
  artifacts: Array<{ id: number; name: string; artifact_type: string }>
}

const runs = ref<ResearchRunSummary[]>([])
const selectedRun = ref<ResearchRunSummary | null>(null)
const loading = ref(false)
const error = ref('')
const shouldPoll = computed(() => runs.value.some(run => !['completed', 'failed', 'canceled'].includes(run.status)))
let poller: ReturnType<typeof setInterval> | null = null

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
.research-results-tool { display:grid; grid-template-rows:auto minmax(0,1fr) auto; gap:6px; height:100%; min-height:0; padding:6px; color:#cbd5dc; background:#11161b; font:10px "Segoe UI",Arial,sans-serif; }.research-results-tool header { display:flex; align-items:center; gap:6px; }.research-results-tool header button { margin-left:auto; }.research-results-tool button { border:1px solid #3a4954; background:#172027; color:#dce6ed; font:inherit; cursor:pointer; }.research-results-tool button:disabled { opacity:.55; cursor:default; }.research-results-tool__runs { overflow:auto; display:grid; align-content:start; gap:3px; }.research-results-tool__run { display:grid; grid-template-columns:minmax(55px,1fr) auto auto; gap:5px; padding:5px; text-align:left; }.research-results-tool__run:hover,.research-results-tool__run--selected { background:#1d3543; border-color:#52748a; }.research-results-tool__run small,.research-results-tool__detail small,.research-results-tool__notice { color:#8195a3; }.research-results-tool__detail { border-top:1px solid #34424c; padding-top:5px; overflow:auto; }.research-results-tool__detail p { margin:4px 0; }.research-results-tool__detail ul { margin:4px 0; padding-left:16px; }.research-results-tool__error { color:#f0a2a2; }.research-results-tool__status--completed { color:#82c49b; }.research-results-tool__status--failed,.research-results-tool__status--canceled { color:#ed9696; }.research-results-tool__status--queued,.research-results-tool__status--running { color:#80bce8; }
</style>
