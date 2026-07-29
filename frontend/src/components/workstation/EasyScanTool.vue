<template>
  <section class="easy-scan">
    <div class="easy-scan__builder">
      <input v-model.trim="conditionName" aria-label="Condition name" placeholder="Condition name" />
      <select v-model="field" aria-label="Price field"><option value="close">Close</option><option value="volume">Volume</option></select>
      <select v-model="operator" aria-label="Comparison"><option value="gt">&gt;</option><option value="gte">≥</option><option value="lt">&lt;</option><option value="lte">≤</option></select>
      <input v-model="value" aria-label="Condition threshold" inputmode="decimal" placeholder="Value" />
      <button type="button" :disabled="busy || !validCondition" @click="saveCondition">Save</button>
    </div>
    <div class="easy-scan__controls">
      <select v-model="selectedKey" :disabled="busy" aria-label="Saved condition">
        <option value="">Select saved condition</option>
        <option v-for="condition in conditions" :key="condition.stable_key" :value="condition.stable_key">{{ condition.name }} · v{{ condition.version }}</option>
      </select>
      <input v-model.trim="scanName" :disabled="busy || !selectedKey" aria-label="Scan name" placeholder="EasyScan name" />
      <button type="button" :disabled="busy || !selectedKey || !scanName" @click="run">Run</button>
    </div>
    <p v-if="error" class="easy-scan__error">{{ error }}</p>
    <p v-else-if="busy" class="easy-scan__state">{{ status }}</p>
    <p v-else-if="result" class="easy-scan__result"><b>{{ result.matched_ids.length }}</b> matches · {{ coverageText }}</p>
    <p v-else class="easy-scan__state">Save a price/volume condition, then run it against local canonical data.</p>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { api } from '@/lib/api'

type ConditionAsset = { stable_key: string; name: string; version: number; payload: { condition?: Record<string, unknown> } }
type ScanResult = { matched_ids: number[]; result_data: Record<string, unknown>; error: string | null }

const conditions = ref<ConditionAsset[]>([])
const selectedKey = ref('')
const conditionName = ref('')
const field = ref('close')
const operator = ref('gt')
const value = ref('')
const scanName = ref('')
const busy = ref(false)
const status = ref('')
const error = ref('')
const result = ref<ScanResult | null>(null)
const validCondition = computed(() => Boolean(conditionName.value) && Number.isFinite(Number(value.value)))
const coverageText = computed(() => {
  const coverage = result.value?.result_data._coverage as { evaluated_count?: number; universe_count?: number; excluded?: Record<string, unknown> } | undefined
  if (!coverage) return 'coverage unavailable'
  const excluded = Object.keys(coverage.excluded ?? {}).length
  return `${coverage.evaluated_count ?? 0}/${coverage.universe_count ?? 0} evaluated${excluded ? ` · ${excluded} excluded` : ''}`
})

async function load() {
  try { conditions.value = await api.get<ConditionAsset[]>('/workspaces/library/conditions') }
  catch (cause: any) { error.value = cause?.message ?? 'Unable to load conditions' }
}
function stableKey(name: string) {
  return name.toLowerCase().trim().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 72) || 'condition'
}
async function saveCondition() {
  if (!validCondition.value) return
  busy.value = true; error.value = ''; status.value = 'Saving condition…'
  const key = stableKey(conditionName.value)
  try {
    const saved = await api.put<ConditionAsset>(`/workspaces/library/conditions/${encodeURIComponent(key)}`, {
      name: conditionName.value,
      condition: { operator: 'AND', conditions: [{ type: 'price_threshold', field: field.value, op: operator.value, value: Number(value.value) }] },
      dependency_metadata: { source: 'workstation-easyscan-builder', version: 1 },
    })
    const index = conditions.value.findIndex(item => item.stable_key === saved.stable_key)
    if (index >= 0) conditions.value.splice(index, 1, saved); else conditions.value.push(saved)
    conditions.value.sort((left, right) => left.name.localeCompare(right.name))
    selectedKey.value = saved.stable_key
    scanName.value = `${saved.name} Scan`
  } catch (cause: any) { error.value = cause?.message ?? 'Unable to save condition' }
  finally { busy.value = false }
}
async function run() {
  if (!selectedKey.value || !scanName.value) return
  busy.value = true; error.value = ''; result.value = null; status.value = 'Preparing local EasyScan…'
  try {
    let scan: { id: number }
    try {
      scan = await api.post<{ id: number }>(`/screeners/from-condition/${encodeURIComponent(selectedKey.value)}`, { name: scanName.value, universe_type: 'all', timeframe: 'D1' })
    } catch (cause: any) {
      if (!String(cause?.message ?? '').includes('→ 409:')) throw cause
      const existing = await api.get<Array<{ id: number; name: string }>>('/screeners')
      const found = existing.find(item => item.name.toLowerCase() === scanName.value.toLowerCase())
      if (!found) throw cause
      scan = found
    }
    status.value = 'Evaluating canonical local data…'
    result.value = await api.post<ScanResult>(`/screeners/${scan.id}/run`, {})
  } catch (cause: any) { error.value = cause?.message ?? 'Unable to run scan' }
  finally { busy.value = false }
}
watch(selectedKey, key => { if (key && !scanName.value) scanName.value = `${conditions.value.find(item => item.stable_key === key)?.name ?? 'EasyScan'} Scan` })
onMounted(() => { void load() })
</script>

<style scoped>
.easy-scan { display: grid; align-content: start; gap: 6px; height: 100%; padding: 6px; background: #11161b; color: #c7d0d8; font: 10px "Segoe UI", Arial, sans-serif; }
.easy-scan__builder { display: grid; grid-template-columns: minmax(70px, 1fr) 56px 34px 58px 38px; gap: 3px; }
.easy-scan__controls { display: grid; grid-template-columns: minmax(90px, 1fr) minmax(80px, 1fr) 38px; gap: 3px; }
input, select, button { min-width: 0; border: 1px solid #34434e; background: #172027; color: #d2dce3; font: inherit; }
input { padding: 2px 4px; } button { cursor: pointer; } button:disabled { cursor: default; opacity: .5; }
.easy-scan__state, .easy-scan__result, .easy-scan__error { margin: 2px 0; color: #8498a6; } .easy-scan__result b { color: #78b9e4; } .easy-scan__error { color: #e99a9a; }
</style>
