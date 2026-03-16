<template>
  <div class="screener-view">
    <div class="screener-sidebar">
      <div class="sidebar-header">
        <span>Screeners</span>
        <button class="btn-new" @click="showBuilder = true">+ New</button>
      </div>
      <div class="screener-list">
        <div
          v-for="s in screeners"
          :key="s.id"
          :class="['screener-item', { active: selectedId === s.id }]"
          @click="select(s)"
        >
          <div class="si-name">{{ s.name }}</div>
          <div class="si-meta">{{ s.timeframe }} · {{ s.universe_type }}</div>
        </div>
        <div v-if="!screeners.length" class="empty-list">No screeners yet</div>
      </div>
    </div>

    <div class="screener-main">
      <!-- Builder panel -->
      <div v-if="showBuilder" class="builder-panel">
        <h3>New Screener</h3>
        <div class="field">
          <label>Name</label>
          <input v-model="draft.name" class="form-input" placeholder="e.g. RSI Oversold" />
        </div>
        <div class="field-row">
          <div class="field">
            <label>Timeframe</label>
            <select v-model="draft.timeframe" class="form-select">
              <option v-for="tf in timeframes" :key="tf" :value="tf">{{ tf }}</option>
            </select>
          </div>
          <div class="field">
            <label>Universe</label>
            <select v-model="draft.universe_type" class="form-select">
              <option value="all">All instruments</option>
              <option value="asset_class">Asset class</option>
            </select>
          </div>
        </div>

        <div class="conditions-builder">
          <div class="cb-header">
            <span>Conditions</span>
            <select v-model="draftRootOp" class="op-select">
              <option value="AND">Match ALL (AND)</option>
              <option value="OR">Match ANY (OR)</option>
            </select>
          </div>

          <div v-for="(cond, i) in draftConditions" :key="i" class="condition-row">
            <select v-model="cond.type" class="form-select cond-type">
              <option value="indicator_threshold">Indicator vs Value</option>
              <option value="indicator_cross">Indicator vs Indicator</option>
              <option value="price_threshold">Price vs Value</option>
              <option value="price_change">Price % Change</option>
            </select>

            <template v-if="cond.type === 'indicator_threshold'">
              <select v-model="cond.indicator" class="form-select cond-ind">
                <option v-for="ind in indicatorTypes" :key="ind" :value="ind">{{ ind.toUpperCase() }}</option>
              </select>
              <input v-if="cond.indicator === 'rsi' || cond.indicator === 'sma' || cond.indicator === 'ema'"
                     v-model.number="cond.params.period" type="number" class="form-input cond-param" placeholder="period" />
              <select v-model="cond.op" class="form-select cond-op">
                <option value="lt">&lt;</option><option value="lte">≤</option>
                <option value="gt">&gt;</option><option value="gte">≥</option>
              </select>
              <input v-model.number="cond.value" type="number" class="form-input cond-val" step="0.01" />
            </template>

            <template v-if="cond.type === 'price_threshold'">
              <select v-model="cond.field" class="form-select cond-ind">
                <option value="close">Close</option><option value="open">Open</option>
                <option value="high">High</option><option value="low">Low</option><option value="volume">Volume</option>
              </select>
              <select v-model="cond.op" class="form-select cond-op">
                <option value="gt">&gt;</option><option value="lt">&lt;</option>
              </select>
              <input v-model.number="cond.value" type="number" class="form-input cond-val" step="0.01" />
            </template>

            <template v-if="cond.type === 'price_change'">
              <span class="cond-label">over</span>
              <input v-model.number="cond.lookback_bars" type="number" class="form-input cond-param" placeholder="bars" />
              <span class="cond-label">bars</span>
              <select v-model="cond.op" class="form-select cond-op">
                <option value="gt">&gt;</option><option value="lt">&lt;</option>
              </select>
              <input v-model.number="cond.value" type="number" class="form-input cond-val" step="0.001" placeholder="0.03" />
            </template>

            <button class="btn-remove-cond" @click="draftConditions.splice(i,1)">✕</button>
          </div>

          <button class="btn-add-cond" @click="addCondition">+ Add Condition</button>
        </div>

        <div class="builder-actions">
          <button class="btn-cancel" @click="showBuilder = false">Cancel</button>
          <button class="btn-save" :disabled="!draft.name" @click="saveScreener">Save Screener</button>
        </div>
      </div>

      <!-- Results panel -->
      <div v-else-if="selectedScreener" class="results-panel">
        <div class="results-header">
          <div class="rh-left">
            <h3>{{ selectedScreener.name }}</h3>
            <span class="rh-meta">{{ selectedScreener.timeframe }} · {{ selectedScreener.universe_type }}</span>
          </div>
          <div class="rh-right">
            <button class="btn-run" :disabled="running" @click="runScreener">
              {{ running ? 'Running…' : '▶ Run Now' }}
            </button>
            <button class="btn-delete" @click="deleteScreener(selectedScreener.id)">Delete</button>
          </div>
        </div>

        <div v-if="latestResult" class="results-meta">
          Ran {{ fmtDate(latestResult.run_at) }} · {{ latestResult.duration_ms }}ms ·
          <strong>{{ latestResult.matched_ids.length }}</strong> matches
        </div>

        <div class="results-table-wrap" v-if="latestResult?.matched_ids.length">
          <table class="results-table">
            <thead><tr><th>#</th><th>Symbol</th><th v-for="col in resultCols" :key="col">{{ col }}</th></tr></thead>
            <tbody>
              <tr v-for="(id, i) in latestResult.matched_ids" :key="id">
                <td>{{ i + 1 }}</td>
                <td class="td-sym">
                  <router-link :to="`/chart/${instrumentSymbols[id] || id}`">
                    {{ instrumentSymbols[id] || id }}
                  </router-link>
                </td>
                <td v-for="col in resultCols" :key="col">
                  {{ fmtVal(latestResult.result_data[String(id)]?.[col]) }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <div v-else-if="latestResult" class="no-matches">No instruments matched this screener</div>
        <div v-else class="no-matches">Run the screener to see results</div>
      </div>

      <div v-else class="screener-empty">
        <p>Select a screener or create a new one</p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, reactive } from 'vue'
import { api } from '@/lib/api'

interface Screener { id: number; name: string; timeframe: string; universe_type: string; conditions: any }
interface ScreenerResult { id: number; run_at: string; duration_ms: number; matched_ids: number[]; result_data: Record<string,any>; error?: string }

const screeners      = ref<Screener[]>([])
const selectedId     = ref<number | null>(null)
const showBuilder    = ref(false)
const running        = ref(false)
const results        = ref<ScreenerResult[]>([])
const instrumentSymbols = ref<Record<number, string>>({})

const selectedScreener = computed(() => screeners.value.find(s => s.id === selectedId.value) ?? null)
const latestResult     = computed(() => results.value[0] ?? null)
const resultCols       = computed(() => {
  if (!latestResult.value?.result_data) return []
  const allKeys = new Set<string>()
  Object.values(latestResult.value.result_data).forEach(v => Object.keys(v).forEach(k => allKeys.add(k)))
  return Array.from(allKeys).slice(0, 6)
})

const timeframes = ['M1','M5','M15','M30','H1','H2','H4','H12','D1','W1','MN']
const indicatorTypes = ['rsi','sma','ema','macd','bb','vwap','atr','stoch','cci','adx']

const draft = reactive({ name: '', timeframe: 'D1', universe_type: 'all' })
const draftRootOp = ref('AND')
const draftConditions = ref<any[]>([])

function addCondition() {
  draftConditions.value.push({ type: 'indicator_threshold', indicator: 'rsi', params: { period: 14 }, op: 'lt', value: 30 })
}

async function saveScreener() {
  const conditions = { operator: draftRootOp.value, conditions: draftConditions.value }
  const s = await api.post<Screener>('/screeners', { ...draft, conditions })
  screeners.value.push(s)
  selectedId.value = s.id
  showBuilder.value = false
  draftConditions.value = []
}

function select(s: Screener) {
  selectedId.value = s.id
  loadResults(s.id)
}

async function loadResults(id: number) {
  results.value = await api.get(`/screeners/${id}/results`, { limit: 5 })
}

async function runScreener() {
  if (!selectedId.value) return
  running.value = true
  try {
    const result = await api.post<ScreenerResult>(`/screeners/${selectedId.value}/run`, {})
    if (result.id !== -1) results.value.unshift(result)
    else setTimeout(() => loadResults(selectedId.value!), 3000)
  } finally {
    running.value = false
  }
}

async function deleteScreener(id: number) {
  await api.delete(`/screeners/${id}`)
  screeners.value = screeners.value.filter(s => s.id !== id)
  if (selectedId.value === id) selectedId.value = null
}

const fmtDate = (d: string) => new Date(d).toLocaleString()
const fmtVal  = (v: any)    => v == null ? '—' : typeof v === 'number' ? v.toFixed(3) : String(v)

onMounted(async () => {
  screeners.value = await api.get('/screeners')
})
</script>

<style scoped>
.screener-view { display: flex; height: 100vh; color: #ccc; font-size: 12px; }

.screener-sidebar {
  width: 220px;
  background: #0d0d0d;
  border-right: 1px solid #1a1a1a;
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
}

.sidebar-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px;
  border-bottom: 1px solid #1a1a1a;
  color: #eee;
  font-weight: 600;
}

.btn-new {
  background: #1a3a5c;
  border: 1px solid #64b5f6;
  color: #64b5f6;
  border-radius: 3px;
  padding: 3px 10px;
  cursor: pointer;
  font-size: 11px;
}

.screener-list { flex: 1; overflow-y: auto; }

.screener-item {
  padding: 10px 12px;
  cursor: pointer;
  border-bottom: 1px solid #111;
}
.screener-item:hover { background: #111; }
.screener-item.active { background: #0f1f30; border-left: 2px solid #64b5f6; }

.si-name { color: #ddd; font-weight: 500; }
.si-meta { color: #555; font-size: 10px; margin-top: 2px; }
.empty-list { padding: 16px 12px; color: #444; font-style: italic; }

.screener-main { flex: 1; overflow: auto; padding: 20px; }

.builder-panel, .results-panel { max-width: 760px; }
.builder-panel h3, .results-panel h3 { color: #fff; font-size: 15px; margin-bottom: 16px; }

.field { display: flex; flex-direction: column; gap: 4px; margin-bottom: 12px; }
.field-row { display: flex; gap: 12px; }
.field label { font-size: 10px; color: #666; text-transform: uppercase; }

.form-input, .form-select {
  background: #141414;
  border: 1px solid #2a2a2a;
  color: #ccc;
  border-radius: 3px;
  padding: 5px 8px;
  font-size: 12px;
}

.conditions-builder {
  background: #0d0d0d;
  border: 1px solid #1e1e1e;
  border-radius: 4px;
  padding: 12px;
  margin-bottom: 16px;
}

.cb-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; color: #aaa; font-weight: 600; }
.op-select { background: #1a1a1a; border: 1px solid #333; color: #aaa; border-radius: 3px; padding: 3px 6px; font-size: 11px; }

.condition-row { display: flex; gap: 6px; align-items: center; margin-bottom: 8px; flex-wrap: wrap; }
.cond-type  { min-width: 180px; }
.cond-ind   { min-width: 80px; }
.cond-op    { width: 50px; }
.cond-param { width: 60px; }
.cond-val   { width: 80px; }
.cond-label { color: #666; font-size: 11px; white-space: nowrap; }

.btn-add-cond { background: none; border: 1px dashed #333; color: #555; border-radius: 3px; padding: 4px 12px; cursor: pointer; font-size: 11px; width: 100%; margin-top: 4px; }
.btn-add-cond:hover { border-color: #555; color: #888; }

.btn-remove-cond { background: none; border: none; color: #444; cursor: pointer; font-size: 11px; padding: 0 4px; }
.btn-remove-cond:hover { color: #ef5350; }

.builder-actions { display: flex; gap: 8px; justify-content: flex-end; }
.btn-cancel { background: none; border: 1px solid #333; color: #666; border-radius: 3px; padding: 6px 16px; cursor: pointer; }
.btn-save   { background: #1a3a5c; border: 1px solid #64b5f6; color: #64b5f6; border-radius: 3px; padding: 6px 16px; cursor: pointer; }
.btn-save:disabled { opacity: 0.4; cursor: not-allowed; }

.results-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 12px; }
.rh-left h3 { margin: 0 0 4px; }
.rh-meta { color: #555; font-size: 10px; }
.rh-right { display: flex; gap: 8px; }
.btn-run { background: #1a3a5c; border: 1px solid #64b5f6; color: #64b5f6; border-radius: 3px; padding: 5px 14px; cursor: pointer; font-size: 12px; }
.btn-delete { background: none; border: 1px solid #333; color: #666; border-radius: 3px; padding: 5px 10px; cursor: pointer; font-size: 11px; }
.btn-delete:hover { border-color: #ef5350; color: #ef5350; }

.results-meta { color: #666; font-size: 11px; margin-bottom: 12px; }

.results-table-wrap { overflow-x: auto; }
.results-table { width: 100%; border-collapse: collapse; font-family: monospace; font-size: 11px; }
.results-table th { background: #0d0d0d; color: #666; text-align: left; padding: 6px 10px; border-bottom: 1px solid #1a1a1a; }
.results-table td { padding: 6px 10px; border-bottom: 1px solid #111; }
.td-sym a { color: #64b5f6; text-decoration: none; }
.td-sym a:hover { text-decoration: underline; }

.no-matches { color: #444; padding: 24px 0; font-style: italic; }
.screener-empty { display: flex; align-items: center; justify-content: center; height: 200px; color: #333; }
</style>
