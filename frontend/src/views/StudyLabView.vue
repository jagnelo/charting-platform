<template>
  <main class="study-lab">
    <header><strong>Study Lab</strong><span>Reproducible Python research</span><button @click="router.push('/')">Back to workstation</button></header>
    <section class="study-lab__controls">
      <input v-model="name" aria-label="Study name" placeholder="Study name" />
      <button @click="validate" :disabled="busy">Validate</button>
      <button @click="saveAndRun" :disabled="busy || !validation?.valid">Save & Run</button>
    </section>
    <textarea v-model="source" aria-label="Study Python source" spellcheck="false" />
    <section v-if="validation" class="study-lab__diagnostics" :class="{ bad: !validation.valid }">
      <strong>{{ validation.valid ? 'Validated for isolated execution' : 'Validation errors' }}</strong>
      <pre v-if="validation.diagnostics.length">{{ validation.diagnostics }}</pre>
      <p v-else>Dependencies: {{ validation.dependencies.join(', ') || 'none' }} · Lookback: {{ validation.lookback_hint ?? 'none' }}</p>
    </section>
    <section v-if="run" class="study-lab__run"><strong>Run #{{ run.id }}</strong><span>{{ run.status }}</span><button v-if="!['completed','failed','canceled'].includes(run.status)" @click="cancel">Cancel</button><pre v-if="run.diagnostics?.length">{{ run.diagnostics }}</pre><div v-for="artifact in run.artifacts ?? []" :key="artifact.id" class="study-lab__artifact"><strong>{{ artifact.name }}</strong><span>{{ artifact.artifact_type }}</span><pre>{{ artifact.payload.value }}</pre></div></section>
  </main>
</template>

<script setup lang="ts">
import { onBeforeUnmount, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '@/lib/api'

const router = useRouter()
const name = ref('Consecutive Positive Closes')
const source = ref("output.scalar('sample_size', 0)")
const busy = ref(false)
const validation = ref<any>(null)
const run = ref<any>(null)
let poller: ReturnType<typeof setInterval> | null = null

async function validate() {
  busy.value = true
  try { validation.value = await api.post('/code/validate', { source: source.value }) } finally { busy.value = false }
}
async function saveAndRun() {
  busy.value = true
  try {
    const stableKey = name.value.trim().toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'study'
    const asset = await api.post<any>('/code/assets', { stable_key: `${stableKey}-${Date.now()}`, name: name.value, kind: 'study', initial_version: { source: source.value, output_contract: 'study' } })
    run.value = await api.post('/research/runs', { code_version_id: asset.versions[0].id, dataset_manifest: { source: 'canonical_database', requested_at: new Date().toISOString() } })
    poller = setInterval(async () => {
      if (!run.value || ['completed', 'failed', 'canceled'].includes(run.value.status)) return
      run.value = await api.get(`/research/runs/${run.value.id}`)
    }, 1000)
  } finally { busy.value = false }
}
async function cancel() {
  if (!run.value) return
  run.value = await api.post(`/research/runs/${run.value.id}/cancel`, {})
  if (poller) clearInterval(poller)
}
onBeforeUnmount(() => { if (poller) clearInterval(poller) })
</script>

<style scoped>
.study-lab { height: 100%; padding: 14px; display: grid; grid-template-rows: 31px 32px minmax(180px,1fr) auto auto; gap: 8px; background:#101419; color:#d5dde4; font:12px "Segoe UI",Arial,sans-serif; }
header,.study-lab__controls { display:flex; align-items:center; gap:8px; } header span { color:#80909c; } header button { margin-left:auto; } input,textarea,button { background:#1a2127; color:#dce6ed; border:1px solid #46535e; padding:5px 7px; } input { width:260px; } textarea { width:100%; resize:none; font:12px/1.5 ui-monospace,monospace; } button { cursor:pointer; } .study-lab__diagnostics,.study-lab__run { padding:9px; border:1px solid #34424c; background:#151b20; } .bad { border-color:#b46363; color:#efaaaa; } pre { white-space:pre-wrap; margin-top:5px; color:#b4c4cf; }
</style>
