<template>
  <section class="easy-scan">
    <div class="easy-scan__builder">
      <input v-model.trim="conditionName" aria-label="Condition name" placeholder="Condition name" />
      <select v-model="field" aria-label="Price field"><option value="close">Close</option><option value="volume">Volume</option></select>
      <select v-model="operator" aria-label="Comparison"><option value="gt">&gt;</option><option value="gte">≥</option><option value="lt">&lt;</option><option value="lte">≤</option></select>
      <input v-model="value" aria-label="Condition threshold" inputmode="decimal" placeholder="Value" />
      <button type="button" :disabled="busy || !validCondition" @click="saveCondition">Save</button>
    </div>
    <button type="button" class="easy-scan__advanced-toggle" @click="toggleAdvancedConditions">{{ advancedMode ? 'Use simple condition' : 'Build technical condition tree' }}</button>
    <ConditionGroupEditor v-if="advancedMode" v-model="advancedGroup" class="easy-scan__advanced" aria-label="Advanced technical condition builder" />
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
      <input v-model.trim="scanName" :disabled="busy || (!selectedKey && !selectedPythonVersion)" aria-label="Scan name" placeholder="EasyScan name" />
      <button type="button" :disabled="busy || (!selectedKey && !selectedPythonVersion) || !scanName" @click="run">Run</button>
    </div>
    <p v-if="error" class="easy-scan__error">{{ error }}</p>
    <p v-else-if="busy" class="easy-scan__state"><span>{{ status }}</span><button v-if="pythonResearchRunId" type="button" @click="cancelPythonRun">Cancel</button></p>
    <div v-else-if="result" class="easy-scan__result"><b>{{ result.matched_ids.length }}</b> matches · {{ coverageText }}<span class="easy-scan__alert"><select v-model="alertTrigger" aria-label="Scan alert trigger"><option value="entered">Entry</option><option value="left">Exit</option><option value="both">Entry/exit</option></select><button type="button" :disabled="busy || !scanId" @click="createAlert">{{ alertCreated ? 'Alert active' : 'Alert' }}</button></span></div>
    <p v-else class="easy-scan__state">Save a price/volume condition, then run it against local canonical data.</p>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { api } from '@/lib/api'
import ConditionGroupEditor from '@/components/workstation/ConditionGroupEditor.vue'
import { createDefaultTechnicalCondition } from '@/lib/technicalConditions'

type ConditionAsset = { stable_key: string; name: string; version: number; payload: { condition?: Record<string, unknown> } }
type ScanResult = { matched_ids: number[]; result_data: Record<string, unknown>; error: string | null }

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
const busy = ref(false)
const status = ref('')
const error = ref('')
const result = ref<ScanResult | null>(null)
const scanId = ref<number | null>(null)
const alertTrigger = ref('entered')
const alertCreated = ref(false)
const cancelRequested = ref(false)
const pythonResearchRunId = computed(() => {
  const value = result.value?.result_data?._python_research_run_id
  return Number.isInteger(value) ? value as number : null
})
const validCondition = computed(() => Boolean(conditionName.value) && (advancedMode.value
  ? advancedGroup.value.conditions.length > 0
  : Number.isFinite(Number(value.value))))
const coverageText = computed(() => {
  const coverage = result.value?.result_data._coverage as { evaluated_count?: number; universe_count?: number; excluded?: Record<string, unknown> } | undefined
  if (!coverage) return 'coverage unavailable'
  const excluded = Object.keys(coverage.excluded ?? {}).length
  return `${coverage.evaluated_count ?? 0}/${coverage.universe_count ?? 0} evaluated${excluded ? ` · ${excluded} excluded` : ''}`
})

async function load() {
  try {
    const [saved, assets] = await Promise.all([
      api.get<ConditionAsset[]>('/workspaces/library/conditions'),
      api.get<Array<{ kind: string; name: string; versions: Array<{ id: number; version_number: number; output_contract: string }> }>>('/code/assets'),
    ])
    conditions.value = saved
    pythonConditions.value = assets.filter(asset => asset.kind === 'condition').flatMap(asset => asset.versions.filter(version => version.output_contract === 'boolean').slice(-1).map(version => ({ versionId: version.id, name: `${asset.name} v${version.version_number}` })))
  }
  catch (cause: any) { error.value = cause?.message ?? 'Unable to load conditions' }
}
function stableKey(name: string) {
  return name.toLowerCase().trim().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 72) || 'condition'
}
function toggleAdvancedConditions() {
  advancedMode.value = !advancedMode.value
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
  if ((!selectedKey.value && !selectedPythonVersion.value) || !scanName.value) return
  busy.value = true; error.value = ''; result.value = null; scanId.value = null; alertCreated.value = false; cancelRequested.value = false; status.value = 'Preparing local EasyScan…'
  try {
    let scan: { id: number }
    const universe: Record<string, unknown> = { universe_type: universeType.value, timeframe: scanTimeframe.value }
    if (universeType.value === 'watchlist' || universeType.value === 'basket') {
      const id = Number(universeValue.value)
      if (!Number.isInteger(id) || id <= 0) throw new Error('Enter a valid universe ID')
      universe[universeType.value === 'watchlist' ? 'universe_watchlist_id' : 'universe_basket_id'] = id
    } else if (universeType.value === 'custom') {
      const ids = universeValue.value.split(',').map(item => Number(item.trim())).filter(id => Number.isInteger(id) && id > 0)
      if (!ids.length) throw new Error('Enter one or more instrument IDs')
      universe.universe_instrument_ids = ids
    }
    try {
      scan = await api.post<{ id: number }>(selectedPythonVersion.value
        ? `/screeners/from-python-condition/${encodeURIComponent(selectedPythonVersion.value)}`
        : `/screeners/from-condition/${encodeURIComponent(selectedKey.value)}`, { name: scanName.value, ...universe })
    } catch (cause: any) {
      if (!String(cause?.message ?? '').includes('→ 409:')) throw cause
      const existing = await api.get<Array<{ id: number; name: string }>>('/screeners')
      const found = existing.find(item => item.name.toLowerCase() === scanName.value.toLowerCase())
      if (!found) throw cause
      scan = found
    }
    scanId.value = scan.id
    status.value = 'Evaluating canonical local data…'
    result.value = await api.post<ScanResult>(`/screeners/${scan.id}/run`, {})
    if (selectedPythonVersion.value) {
      for (let attempt = 0; attempt < 30; attempt += 1) {
        const status = String(result.value.result_data._status ?? '')
        if (['completed', 'failed', 'canceled'].includes(status)) break
        await new Promise(resolve => setTimeout(resolve, 250))
        const retained = await api.get<ScanResult[]>(`/screeners/${scan.id}/results`, { limit: 1 })
        if (retained[0]) result.value = retained[0]
      }
    }
  } catch (cause: any) { error.value = cause?.message ?? 'Unable to run scan' }
  finally { busy.value = false }
}
async function cancelPythonRun() {
  if (!pythonResearchRunId.value || cancelRequested.value) return
  cancelRequested.value = true
  status.value = 'Cancel requested…'
  try { await api.post(`/research/runs/${pythonResearchRunId.value}/cancel`, {}) }
  catch (cause: any) { cancelRequested.value = false; error.value = cause?.message ?? 'Unable to cancel Python scan' }
}
async function createAlert() {
  if (!scanId.value || alertCreated.value) return
  busy.value = true; error.value = ''; status.value = 'Creating scan alert…'
  try { await api.post('/alerts/screener', { screener_id: scanId.value, trigger_type: alertTrigger.value, repeat: true }); alertCreated.value = true }
  catch (cause: any) { error.value = cause?.message ?? 'Unable to create scan alert' }
  finally { busy.value = false }
}
watch(selectedKey, key => { if (key && !scanName.value) scanName.value = `${conditions.value.find(item => item.stable_key === key)?.name ?? 'EasyScan'} Scan` })
watch(selectedPythonVersion, version => { if (version && !scanName.value) scanName.value = `${pythonConditions.value.find(item => item.versionId === Number(version))?.name ?? 'Python'} Scan` })
onMounted(() => { void load() })
</script>

<style scoped>
.easy-scan { display: grid; align-content: start; gap: 6px; height: 100%; overflow: auto; padding: 6px; background: #11161b; color: #c7d0d8; font: 10px "Segoe UI", Arial, sans-serif; }
.easy-scan__builder { display: grid; grid-template-columns: minmax(70px, 1fr) 56px 34px 58px 38px; gap: 3px; }
.easy-scan__controls { display: grid; grid-template-columns: repeat(3, minmax(80px, 1fr)) minmax(70px, 1fr) minmax(90px, 1fr) 38px; gap: 3px; }
.easy-scan__advanced-toggle { justify-self: start; padding: 2px 6px; }
.easy-scan__advanced { display: grid; gap: 5px; padding: 5px; border: 1px solid #34434e; background: #151b20; }
.easy-scan__advanced header { display: flex; align-items: center; justify-content: space-between; color: #a9bbc5; }
.easy-scan__advanced header select { width: 130px; }
.easy-scan__advanced > button { justify-self: start; padding: 2px 6px; }
input, select, button { min-width: 0; border: 1px solid #34434e; background: #172027; color: #d2dce3; font: inherit; }
input { padding: 2px 4px; } button { cursor: pointer; } button:disabled { cursor: default; opacity: .5; }
.easy-scan__state, .easy-scan__result, .easy-scan__error { margin: 2px 0; color: #8498a6; } .easy-scan__result b { color: #78b9e4; } .easy-scan__error { color: #e99a9a; }.easy-scan__alert { display:flex; gap:3px; margin-top:4px; }.easy-scan__alert select,.easy-scan__alert button { border:1px solid #34434e; background:#172027; color:#d2dce3; font:inherit; }
</style>
