<template>
  <div class="basket-view">
    <aside class="basket-sidebar">
      <div class="basket-sidebar__head">
        <div>
          <h1>Baskets</h1>
          <p>Reusable weighted universes.</p>
        </div>
      </div>

      <div class="basket-list">
        <div v-if="loading" class="basket-list__state">Loading baskets...</div>
        <template v-else>
          <button
            v-for="basket in baskets"
            :key="basket.id"
            type="button"
            class="basket-card"
            :class="{ 'basket-card--active': selectedBasket?.id === basket.id }"
            :disabled="loading || saving || deleting"
            @click="requestSelectBasket(basket)"
          >
            <span class="basket-card__top">
              <span class="basket-card__name">{{ basket.name }}</span>
              <span v-if="basket.is_system_managed" class="basket-card__badge">ETF</span>
              <span v-else class="basket-card__badge basket-card__badge--manual">Manual</span>
            </span>
            <span class="basket-card__meta">
              {{ basket.members.length }} symbols
              <span v-if="basket.weighting_scheme"> · {{ humanize(basket.weighting_scheme) }}</span>
            </span>
          </button>
        </template>

        <button type="button" class="basket-new" :disabled="loading || saving || deleting" @click="startNew">+ New</button>
      </div>
    </aside>

    <main class="basket-main">
      <section class="basket-panel">
        <div class="panel-title-row">
          <div>
            <h2>{{ isEditingExisting ? draft.name || 'Basket' : 'New basket' }}</h2>
            <p v-if="selectedBasket?.is_system_managed">
              Read-only basket materialized from an ETF holdings snapshot.
            </p>
            <p v-else>
              Create a reusable equal-weight or custom-weight universe from provider-resolved instruments.
            </p>
          </div>
          <div class="panel-actions">
            <button
              v-if="selectedBasket"
              type="button"
              class="btn btn-secondary"
              data-testid="basket-open-chart"
              :disabled="loading || saving || deleting || isDirty || !selectedBasket.members.length"
              @click="openBasketChart"
            >
              Open chart
            </button>
            <button
              v-if="isEditingExisting && !isReadOnly"
              type="button"
              class="btn btn-danger"
              :disabled="loading || saving || deleting"
              @click="showDelete = true"
            >
              Delete
            </button>
            <button
              type="button"
              class="btn btn-secondary"
              :disabled="loading || isDirty || saving || deleting || showDelete"
              title="Discard or save your edits before refreshing saved baskets."
              @click="handleReload"
            >Refresh</button>
            <button
              v-if="isDirty"
              type="button"
              class="btn btn-secondary"
              data-testid="basket-discard-edits"
              :disabled="saving"
              @click="discardCurrentEdits"
            >Discard edits</button>
            <button
              type="button"
              class="btn btn-primary"
              :disabled="!canSave || loading || saving || deleting"
              @click="saveBasket"
            >
              {{ isEditingExisting ? 'Save' : 'Create' }}
            </button>
          </div>
        </div>

        <div v-if="loadError" class="notice notice--error">{{ loadError }}</div>
        <div v-if="saveError" class="notice notice--error">{{ saveError }}</div>
        <div v-if="savedMessage" class="notice notice--success">{{ savedMessage }}</div>
        <p v-if="!draft.name.trim()" class="field-hint" role="status">Enter a name to save this basket.</p>
        <p v-else-if="!draft.members.length" class="field-hint" role="status">Choose at least one resolved instrument to save this basket.</p>
        <p v-else-if="draft.weighting_scheme === 'custom' && Math.abs(remainingAllocation) > 0.01" class="field-hint" role="status">
          Custom weights must total 100%. {{ remainingAllocationLabel }}.
        </p>

        <section
          v-if="selectedBasket?.is_system_managed"
          class="basket-source-summary"
          data-testid="basket-source-summary"
          aria-label="Issuer snapshot summary"
        >
          <p>
            <strong>{{ selectedBasket.metadata?.etf_symbol || 'ETF' }}</strong>
            · {{ selectedBasket.metadata?.source_provider || 'Source not established' }}
            · As of {{ selectedBasket.metadata?.as_of_date || selectedBasket.composition_date || 'date unknown' }}
            · {{ sourceSnapshotFreshness }}
          </p>
          <p>Current eligibility is assessed separately in ETF Holdings; this basket retains a dated composition.</p>
        </section>

        <div class="form-grid">
          <label class="field">
            <span class="field-label">Name</span>
            <input
              v-model="draft.name"
              class="form-input"
              :disabled="isReadOnly || loading || saving"
              placeholder="Basket name"
            />
          </label>
          <label class="field">
            <span class="field-label">Weighting</span>
            <select v-model="draft.weighting_scheme" class="form-select" :disabled="isReadOnly || loading || saving">
              <option value="equal">Equal weight</option>
              <option value="custom">Custom weights</option>
            </select>
          </label>
          <label class="field field--full">
            <span class="field-label">Description</span>
            <textarea
              v-model="draft.description"
              class="form-textarea"
              :disabled="isReadOnly || loading || saving"
              placeholder="What does this basket represent?"
            />
          </label>
        </div>

        <div v-if="draft.weighting_scheme === 'custom'" class="allocation-strip">
          <span :class="remainingClass">{{ remainingAllocationLabel }}</span>
          <div class="allocation-track">
            <span class="allocation-fill" :style="{ width: `${allocatedPct}%` }" />
          </div>
        </div>

        <div class="member-toolbar">
          <div>
            <h3>Members</h3>
            <span>{{ draft.members.length }} instruments</span>
          </div>
          <div v-if="!isReadOnly" class="member-search">
            <SearchBar
              v-model="memberSearch"
              placeholder="Add instrument"
              mode="picker"
              fluid
              :show-recent="false"
              :show-screener-link="false"
              :allow-expressions="false"
              :readonly="loading || saving"
              @select="addMember"
            />
          </div>
        </div>

        <div
          class="member-table"
          :class="{ 'member-table--custom': draft.weighting_scheme === 'custom' }"
        >
          <div class="member-row member-row--head">
            <span>Symbol</span>
            <span>Name</span>
            <span v-if="draft.weighting_scheme === 'custom'">Weight %</span>
            <span />
          </div>
          <div v-for="member in draft.members" :key="member.key" class="member-row">
            <button type="button" class="member-symbol" @click="openChart(member.symbol)">
              {{ member.symbol }}
            </button>
            <span class="member-name">{{ member.name || 'Resolved instrument' }}</span>
            <label v-if="draft.weighting_scheme === 'custom'" class="weight-input-wrap">
              <input
                v-model="member.weight_pct"
                class="form-input weight-input"
                type="number"
                min="0"
                max="100"
                step="0.01"
                :disabled="isReadOnly || loading || saving"
              />
            </label>
            <button
              v-if="!isReadOnly"
              type="button"
              class="remove-btn"
              :aria-label="`Remove ${member.symbol}`"
              :disabled="loading || saving"
              @click="removeMember(member.key)"
            >
              ×
            </button>
            <span v-else />
          </div>
          <div v-if="!draft.members.length" class="empty-state">
            Add at least one resolved instrument to create a basket.
          </div>
        </div>

        <details
          v-if="selectedBasket?.is_system_managed"
          class="basket-provenance"
          data-testid="basket-source-provenance"
        >
          <summary>Source details</summary>
          <section aria-label="Issuer snapshot provenance">
            <dl>
              <div><dt>ETF</dt><dd>{{ selectedBasket.metadata?.etf_symbol || 'Unknown' }}</dd></div>
              <div><dt>Composition date</dt><dd>{{ selectedBasket.composition_date || 'Unknown' }}</dd></div>
              <div><dt>Source provider</dt><dd>{{ selectedBasket.metadata?.source_provider || 'Unknown' }}</dd></div>
              <div><dt>Provenance</dt><dd>{{ selectedBasket.metadata?.provenance || 'Unknown' }}</dd></div>
              <div><dt>Source quality</dt><dd>{{ selectedBasket.metadata?.source_quality || 'Unknown' }}</dd></div>
              <div><dt>Completeness</dt><dd>{{ selectedBasket.metadata?.completeness_status || 'Unknown' }}</dd></div>
              <div><dt>Snapshot ID</dt><dd>{{ selectedBasket.source_snapshot_id ?? 'Unknown' }}</dd></div>
              <div><dt>Known at</dt><dd>{{ selectedBasket.metadata?.known_at || 'Unknown' }}</dd></div>
              <div v-if="selectedBasket.metadata?.as_of_date"><dt>As of</dt><dd>{{ selectedBasket.metadata.as_of_date }}</dd></div>
              <div v-if="selectedBasket.metadata?.source_identifier"><dt>Source identifier</dt><dd>{{ selectedBasket.metadata.source_identifier }}</dd></div>
              <div v-if="selectedBasket.metadata?.source_url"><dt>Source URL</dt><dd class="basket-provenance__url">{{ selectedBasket.metadata.source_url }}</dd></div>
              <div v-if="selectedBasket.metadata?.snapshot_hash"><dt>Snapshot SHA256</dt><dd>{{ selectedBasket.metadata.snapshot_hash }}</dd></div>
              <div v-if="selectedBasket.metadata?.source_artifact_id"><dt>Raw artifact ID</dt><dd>{{ selectedBasket.metadata.source_artifact_id }}</dd></div>
              <div v-if="selectedBasket.metadata?.source_artifact_hash"><dt>Raw artifact SHA256</dt><dd>{{ selectedBasket.metadata.source_artifact_hash }}</dd></div>
            </dl>
            <p v-if="snapshotLineageError" role="status" class="basket-list__state">{{ snapshotLineageError }}</p>
            <ul v-else class="basket-snapshot-history" data-testid="basket-snapshot-history">
              <li v-for="snapshot in selectedSnapshots" :key="snapshot.id">
                <span>{{ snapshot.composition_date }} · {{ snapshot.member_count }} members</span>
                <small>
                  {{ snapshot.metadata?.source_provider || snapshot.source_type }} · {{ snapshot.metadata?.provenance || 'provenance unavailable' }}
                  · known at {{ snapshot.known_at || 'unknown' }} · source snapshot {{ snapshot.source_snapshot_id ?? 'unknown' }}
                </small>
              </li>
            </ul>
          </section>
        </details>
      </section>
    </main>

    <Teleport to="body">
      <div v-if="showDelete" class="modal-overlay" @click.self="showDelete = false">
        <div class="modal" role="dialog" aria-modal="true" aria-labelledby="basket-delete-title">
          <h3 id="basket-delete-title">Delete basket?</h3>
          <p>This removes "{{ selectedBasket?.name }}" from reusable universes.</p>
          <div class="modal-actions">
            <button type="button" class="btn btn-secondary" :disabled="deleting" @click="showDelete = false">Cancel</button>
            <button type="button" class="btn btn-danger" :disabled="loading || deleting" @click="deleteSelected">{{ deleting ? 'Deleting…' : 'Delete' }}</button>
          </div>
        </div>
      </div>
    </Teleport>

    <Teleport to="body">
      <div v-if="showDiscard" class="modal-overlay" @click.self="cancelDiscard">
        <div class="modal" role="dialog" aria-modal="true" aria-labelledby="basket-discard-title">
          <h3 id="basket-discard-title">Discard unsaved changes?</h3>
          <p>Your basket edits have not been saved.</p>
          <div class="modal-actions">
            <button type="button" class="btn btn-secondary" @click="cancelDiscard">Keep editing</button>
            <button type="button" class="btn btn-danger" data-testid="basket-confirm-discard" @click="confirmDiscard">Discard changes</button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import SearchBar from '@/components/common/SearchBar.vue'
import { api } from '@/lib/api'
import type { Basket } from '@/types'

interface BasketMemberDraft {
  key: string
  instrument_id?: number | null
  symbol: string
  name?: string | null
  weight_pct: string
}

interface BasketDraft {
  name: string
  description: string
  weighting_scheme: 'equal' | 'custom'
  members: BasketMemberDraft[]
}

interface BasketPickerResult {
  instrument_id?: number | null
  name?: string | null
  symbol?: string
}

interface BasketSnapshotLineage {
  id: number
  composition_date: string
  known_at?: string | null
  source_type: string
  source_snapshot_id?: number | null
  member_count: number
  metadata?: { source_provider?: string | null; provenance?: string | null } | null
}

type PendingDiscardAction = { kind: 'basket'; basket: Basket } | { kind: 'new' } | null

const router = useRouter()
const baskets = ref<Basket[]>([])
const selectedBasket = ref<Basket | null>(null)
const loading = ref(false)
const loadError = ref('')
const saveError = ref('')
const savedMessage = ref('')
const memberSearch = ref('')
const showDelete = ref(false)
const showDiscard = ref(false)
const pendingDiscardAction = ref<PendingDiscardAction>(null)
const selectedSnapshots = ref<BasketSnapshotLineage[]>([])
const snapshotLineageError = ref('')
const saving = ref(false)
const deleting = ref(false)
let lifecycleGeneration = 0
let reloadSequence = 0
let selectionGeneration = 0

function isCurrentLifecycle(generation: number) {
  return generation === lifecycleGeneration
}

const draft = reactive<BasketDraft>({
  name: '',
  description: '',
  weighting_scheme: 'equal',
  members: [],
})

const isEditingExisting = computed(() => selectedBasket.value != null)
const isReadOnly = computed(() => Boolean(
  selectedBasket.value?.is_read_only || selectedBasket.value?.is_system_managed,
))
const customWeightTotal = computed(() =>
  draft.members.reduce((sum, member) => sum + numericWeight(member.weight_pct), 0)
)
const remainingAllocation = computed(() => 100 - customWeightTotal.value)
const allocatedPct = computed(() => Math.max(0, Math.min(100, customWeightTotal.value)))
const remainingClass = computed(() => ({
  'allocation-value': true,
  'allocation-value--ok': Math.abs(remainingAllocation.value) <= 0.01,
  'allocation-value--bad': Math.abs(remainingAllocation.value) > 0.01,
}))
const remainingAllocationLabel = computed(() => {
  const value = remainingAllocation.value
  if (Math.abs(value) <= 0.01) return 'Fully allocated'
  return `${formatPct(Math.abs(value))} ${value > 0 ? 'remaining' : 'over'}`
})
const canSave = computed(() => {
  if (isReadOnly.value) return false
  if (!draft.name.trim() || !draft.members.length) return false
  if (draft.weighting_scheme === 'custom') {
    return draft.members.every(member => numericWeight(member.weight_pct) > 0)
      && Math.abs(remainingAllocation.value) <= 0.01
  }
  return true
})

const isDirty = computed(() =>
  draftSignature(draft) !== draftSignature(selectedBasket.value ? draftFromBasket(selectedBasket.value) : emptyDraft()),
)
const sourceSnapshotFreshness = computed(() => {
  const basket = selectedBasket.value
  if (!basket?.composition_date) return 'Snapshot date unavailable'
  if (basket.latest_snapshot_date === basket.composition_date) return 'Latest stored snapshot'
  if (basket.latest_snapshot_date) return `Historical snapshot · latest stored ${basket.latest_snapshot_date}`
  return 'Dated snapshot · latest stored date unavailable'
})

onMounted(() => reload())

async function handleReload() {
  await reload()
}

async function reload(generation = lifecycleGeneration) {
  if (!isCurrentLifecycle(generation)) return
  const sequence = ++reloadSequence
  loading.value = true
  loadError.value = ''
  try {
    const loaded = await api.get<Basket[]>('/baskets')
    if (!isCurrentLifecycle(generation) || sequence !== reloadSequence) return
    baskets.value = loaded
    if (selectedBasket.value) {
      const refreshed = baskets.value.find(basket => basket.id === selectedBasket.value?.id) ?? null
      if (refreshed) selectBasket(refreshed)
      else startNew()
    } else if (baskets.value.length) {
      selectBasket(baskets.value[0])
    } else {
      startNew()
    }
  } catch (err: any) {
    if (!isCurrentLifecycle(generation) || sequence !== reloadSequence) return
    loadError.value = err?.message ?? 'Failed to load baskets'
  } finally {
    if (isCurrentLifecycle(generation) && sequence === reloadSequence) loading.value = false
  }
}

function selectBasket(basket: Basket) {
  if (selectedBasket.value?.id === basket.id && !isDirty.value) {
    selectedBasket.value = basket
    draft.name = basket.name
    draft.description = basket.description ?? ''
    draft.weighting_scheme = basket.weighting_scheme === 'custom' ? 'custom' : 'equal'
    draft.members = draftFromBasket(basket).members
    refreshBasketLineage(basket, ++selectionGeneration)
    return
  }
  selectionGeneration += 1
  selectedBasket.value = basket
  savedMessage.value = ''
  saveError.value = ''
  draft.name = basket.name
  draft.description = basket.description ?? ''
  draft.weighting_scheme = basket.weighting_scheme === 'custom' ? 'custom' : 'equal'
  draft.members = draftFromBasket(basket).members
  void refreshBasketLineage(basket, selectionGeneration)
}

function requestSelectBasket(basket: Basket) {
  if (saving.value || deleting.value || selectedBasket.value?.id === basket.id) return
  if (isDirty.value) {
    pendingDiscardAction.value = { kind: 'basket', basket }
    showDiscard.value = true
    return
  }
  selectBasket(basket)
}

function startNew() {
  if (saving.value || deleting.value) return
  if (isDirty.value) {
    pendingDiscardAction.value = { kind: 'new' }
    showDiscard.value = true
    return
  }
  resetNewDraft()
}

function resetNewDraft() {
  selectionGeneration += 1
  selectedBasket.value = null
  selectedSnapshots.value = []
  snapshotLineageError.value = ''
  savedMessage.value = ''
  saveError.value = ''
  draft.name = ''
  draft.description = ''
  draft.weighting_scheme = 'equal'
  draft.members = []
}

function discardCurrentEdits() {
  if (selectedBasket.value) selectBasket(selectedBasket.value)
  else resetNewDraft()
}

function cancelDiscard() {
  showDiscard.value = false
  pendingDiscardAction.value = null
}

function confirmDiscard() {
  const action = pendingDiscardAction.value
  showDiscard.value = false
  pendingDiscardAction.value = null
  if (action?.kind === 'basket') selectBasket(action.basket)
  else if (action?.kind === 'new') resetNewDraft()
}

function addMember(symbol: string, result?: BasketPickerResult) {
  const normalized = String(result?.symbol || symbol).trim().toUpperCase()
  if (!normalized) return
  const instrumentId = Number(result?.instrument_id)
  if (!Number.isSafeInteger(instrumentId) || instrumentId <= 0) {
    saveError.value = 'Choose a resolved instrument from the search results before adding it.'
    memberSearch.value = ''
    return
  }
  if (draft.members.some(member => member.instrument_id === instrumentId)) {
    saveError.value = `${normalized} is already in this basket.`
    memberSearch.value = ''
    return
  }
  draft.members.push({
    key: `${normalized}-${Date.now()}-${Math.random().toString(36).slice(2)}`,
    ...(Number.isSafeInteger(instrumentId) && instrumentId > 0 ? { instrument_id: instrumentId } : {}),
    symbol: normalized,
    name: result?.name ?? null,
    weight_pct: draft.weighting_scheme === 'custom' ? suggestedNewWeight() : '',
  })
  saveError.value = ''
  memberSearch.value = ''
}

function removeMember(key: string) {
  draft.members = draft.members.filter(member => member.key !== key)
}

function suggestedNewWeight() {
  const count = draft.members.length + 1
  return formatInputWeight(100 / count)
}

async function saveBasket() {
  if (!canSave.value || saving.value) return
  const generation = lifecycleGeneration
  const selection = selectionGeneration
  const selectedId = selectedBasket.value?.id ?? null
  saveError.value = ''
  savedMessage.value = ''
  saving.value = true
  const body = {
    name: draft.name.trim(),
    description: draft.description.trim() || null,
    weighting_scheme: draft.weighting_scheme,
    members: draft.members.map(member => ({
      ...(member.instrument_id ? { instrument_id: member.instrument_id } : { symbol: member.symbol }),
      ...(draft.weighting_scheme === 'custom'
        ? { weight: String(numericWeight(member.weight_pct) / 100) }
        : {}),
    })),
  }
  try {
    const saved = selectedBasket.value
      ? await api.patch<Basket>(`/baskets/${selectedBasket.value.id}`, body)
      : await api.post<Basket>('/baskets', body)
    if (!isCurrentLifecycle(generation) || selection !== selectionGeneration
      || selectedId !== (selectedBasket.value?.id ?? null)) return
    const index = baskets.value.findIndex(basket => basket.id === saved.id)
    if (index >= 0) baskets.value.splice(index, 1, saved)
    else baskets.value = [saved, ...baskets.value]
    selectBasket(saved)
    savedMessage.value = 'Basket saved.'
  } catch (err: any) {
    if (isCurrentLifecycle(generation) && selection === selectionGeneration) {
      saveError.value = err?.message ?? 'Failed to save basket'
    }
  } finally {
    if (isCurrentLifecycle(generation)) saving.value = false
  }
}

async function deleteSelected() {
  if (!selectedBasket.value || isReadOnly.value || deleting.value) return
  const generation = lifecycleGeneration
  const selection = selectionGeneration
  const id = selectedBasket.value.id
  deleting.value = true
  saveError.value = ''
  try {
    await api.delete(`/baskets/${id}`)
    if (!isCurrentLifecycle(generation) || selection !== selectionGeneration) return
    showDelete.value = false
    baskets.value = baskets.value.filter(basket => basket.id !== id)
    selectedBasket.value = null
    const next = baskets.value[0]
    if (next) selectBasket(next)
    else resetNewDraft()
    savedMessage.value = 'Basket deleted.'
  } catch (err: any) {
    if (isCurrentLifecycle(generation) && selection === selectionGeneration) {
      showDelete.value = false
      saveError.value = err?.message ?? 'Failed to delete basket'
    }
  } finally {
    if (isCurrentLifecycle(generation)) deleting.value = false
  }
}

onUnmounted(() => {
  lifecycleGeneration += 1
  reloadSequence += 1
  selectionGeneration += 1
})

function openChart(symbol: string) {
  if (!symbol) return
  router.push(`/chart/${encodeURIComponent(symbol)}`)
}

function openBasketChart() {
  if (!selectedBasket.value) return
  routeToBasketChart()
}

function routeToBasketChart() {
  const basketId = selectedBasket.value?.id
  if (!basketId) return
  void router.push(`/chart/${encodeURIComponent(`BASKET:${basketId}`)}`)
}

async function refreshBasketLineage(basket: Basket, generation: number) {
  const lifecycle = lifecycleGeneration
  selectedSnapshots.value = []
  snapshotLineageError.value = ''
  if (!basket.is_system_managed) return
  try {
    const snapshots = await api.get<BasketSnapshotLineage[]>(`/baskets/${basket.id}/snapshots`)
    if (!isCurrentLifecycle(lifecycle) || generation !== selectionGeneration
      || selectedBasket.value?.id !== basket.id) return
    selectedSnapshots.value = snapshots
  } catch {
    if (isCurrentLifecycle(lifecycle) && generation === selectionGeneration && selectedBasket.value?.id === basket.id) {
      snapshotLineageError.value = 'Snapshot history is temporarily unavailable; the selected source and composition date remain shown.'
    }
  }
}

function draftFromBasket(basket: Basket): BasketDraft {
  return {
    name: basket.name,
    description: basket.description ?? '',
    weighting_scheme: basket.weighting_scheme === 'custom' ? 'custom' : 'equal',
    members: basket.members.map(member => ({
      key: String(member.id),
      instrument_id: member.instrument_id,
      symbol: String(member.symbol ?? member.label ?? member.instrument_id).toUpperCase(),
      name: member.name,
      weight_pct: member.weight == null ? '' : formatInputWeight(Number(member.weight) * 100),
    })),
  }
}

function emptyDraft(): BasketDraft {
  return { name: '', description: '', weighting_scheme: 'equal', members: [] }
}

function draftSignature(value: BasketDraft) {
  return JSON.stringify({
    name: value.name,
    description: value.description,
    weighting_scheme: value.weighting_scheme,
    members: value.members.map(member => ({
      instrument_id: member.instrument_id ?? null,
      symbol: member.symbol,
      name: member.name ?? null,
      weight_pct: member.weight_pct,
    })),
  })
}

function numericWeight(value: string) {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : 0
}

function formatPct(value: number) {
  return `${value.toFixed(value >= 10 ? 1 : 2)}%`
}

function formatInputWeight(value: number) {
  return Number.isFinite(value) ? value.toFixed(2).replace(/\.?0+$/, '') : ''
}

function humanize(value: string) {
  return value.replace(/_/g, ' ')
}
</script>

<style scoped>
.basket-view {
  display: flex;
  height: 100%;
  min-width: 0;
  background: #0a0a0a;
  color: #d7d7d7;
  overflow: hidden;
  font-size: 12px;
}

.basket-sidebar {
  width: 308px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  border-right: 1px solid #1a1a1a;
  background: #0b0b0b;
}

.basket-sidebar__head {
  padding: 12px;
  border-bottom: 1px solid #1a1a1a;
}

.basket-sidebar__head h1,
.panel-title-row h2,
.member-toolbar h3,
.modal h3 {
  margin: 0;
  color: #f4f4f4;
  font-size: 15px;
  line-height: 1.1;
  letter-spacing: 0;
}

.basket-sidebar__head p,
.panel-title-row p,
.member-toolbar span,
.basket-card__meta,
.modal p {
  margin: 8px 0 0;
  color: #8d8d8d;
  font-size: 11px;
  line-height: 1.45;
}

.basket-list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 12px;
}

.basket-card,
.basket-new {
  width: 100%;
  border: 1px solid #242424;
  border-radius: 8px;
  background: #111;
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
}

.basket-list__state {
  color: #858585;
  padding: 14px 4px;
  font-size: 11px;
}

.basket-card {
  display: block;
  padding: 10px 12px;
  margin-bottom: 8px;
  transition: border-color 0.14s, background 0.14s;
}

.basket-card:hover,
.basket-card--active {
  border-color: #246da8;
  background: #0e1a22;
}

.basket-card__top {
  display: flex;
  align-items: center;
  gap: 10px;
  justify-content: space-between;
}

.basket-card__name {
  display: block;
  color: #f1f1f1;
  font-weight: 800;
  font-size: 12px;
}

.basket-card__badge {
  flex-shrink: 0;
  border: 1px solid #5b4720;
  border-radius: 999px;
  padding: 3px 7px;
  color: #f1cc76;
  background: #1c1608;
  font-size: 10px;
  font-weight: 900;
  letter-spacing: 0.08em;
}

.basket-card__badge--manual {
  border-color: #1f4f77;
  color: #8fc9ff;
  background: #0b1c2a;
}

.basket-card__meta {
  display: block;
  margin-top: 6px;
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
}

.basket-new {
  padding: 10px 12px;
  text-align: center;
  color: #8fc9ff;
  background: #0f2233;
  border-color: #1f5d92;
  font-weight: 800;
}

.basket-main {
  flex: 1;
  min-width: 0;
  overflow: auto;
  padding: 16px;
}

.basket-panel {
  border: 1px solid #202020;
  border-radius: 8px;
  background: #101010;
  padding: 16px;
}

.panel-title-row,
.member-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
}

.panel-title-row h2,
.member-toolbar h3,
.modal h3 {
  font-size: 15px;
}

.panel-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.btn {
  border: 1px solid #303030;
  border-radius: 6px;
  background: #151515;
  color: #d0d0d0;
  font: inherit;
  font-weight: 800;
  padding: 8px 12px;
  cursor: pointer;
}

.btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.btn-primary {
  color: #8fc9ff;
  background: #10293d;
  border-color: #1d5b8d;
}

.btn-danger {
  color: #ffb0ba;
  border-color: #73333d;
  background: #211012;
}

.form-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 240px;
  gap: 14px;
  margin-top: 16px;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.field--full {
  grid-column: 1 / -1;
}

.field-label {
  color: #929292;
  font-size: 11px;
  font-weight: 800;
}

.form-input,
.form-select,
.form-textarea {
  width: 100%;
  border: 1px solid #2a2a2a;
  border-radius: 6px;
  background: #111;
  color: #e6e6e6;
  font: inherit;
  padding: 10px 12px;
  outline: none;
}

.form-input:focus,
.form-select:focus,
.form-textarea:focus {
  border-color: #64b5f6;
}

.form-input:disabled,
.form-select:disabled,
.form-textarea:disabled {
  opacity: 0.65;
}

.form-textarea {
  min-height: 78px;
  resize: vertical;
}

.notice {
  margin-top: 12px;
  border-radius: 6px;
  padding: 10px 12px;
  font-size: 11px;
}

.notice--error {
  border: 1px solid #755037;
  color: #ffd985;
  background: #191407;
}

.notice--success {
  border: 1px solid #285b35;
  color: #89e7a3;
  background: #08170d;
}

.field-hint {
  margin: 10px 0 0;
  color: var(--tc-text-muted);
  font-size: 11px;
  line-height: 1.45;
}

.basket-provenance {
  margin-top: 2px;
  padding: 8px 10px;
  border: 1px solid var(--tc-border);
  border-radius: var(--tc-radius);
  background: var(--tc-window-bg);
}

.basket-source-summary {
  display: grid;
  gap: 3px;
  padding: 7px 10px;
  border: 1px solid var(--tc-border);
  border-radius: var(--tc-radius);
  background: var(--tc-window-bg);
  font-size: 11px;
}

.basket-source-summary p {
  margin: 0;
  color: var(--tc-text-muted);
}

.basket-source-summary strong {
  color: var(--tc-text);
}

.basket-provenance > summary,
.snapshot-source-details > summary {
  color: var(--tc-accent-soft);
  cursor: pointer;
  font-size: 11px;
  font-weight: 700;
  outline-offset: 3px;
}

.basket-provenance[open] > summary,
.snapshot-source-details[open] > summary {
  margin-bottom: 10px;
}

.basket-provenance dl {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 8px 16px;
  margin: 0;
}

.basket-provenance dl > div {
  min-width: 0;
}

.basket-provenance dt {
  color: var(--tc-text-muted);
  font-size: 10px;
  font-weight: 800;
}

.basket-provenance dd {
  margin: 3px 0 0;
  color: var(--tc-text);
  overflow-wrap: anywhere;
}

.basket-provenance__url {
  font-family: var(--tc-font-mono);
  font-size: 10px;
}

.basket-snapshot-history {
  display: grid;
  gap: 6px;
  margin: 12px 0 0;
  padding: 0;
  list-style: none;
}

.basket-snapshot-history li {
  display: grid;
  gap: 3px;
  padding-top: 8px;
  border-top: 1px solid var(--tc-border);
  color: var(--tc-text);
}

.basket-snapshot-history small {
  color: var(--tc-text-muted);
}

.allocation-strip {
  display: grid;
  grid-template-columns: 180px minmax(0, 1fr);
  gap: 10px;
  align-items: center;
  margin-top: 14px;
}

.allocation-value {
  font-weight: 800;
  font-size: 11px;
}

.allocation-value--ok { color: #7ce79b; }
.allocation-value--bad { color: #ff9daa; }

.allocation-track {
  height: 8px;
  border-radius: 999px;
  background: #0a1720;
  border: 1px solid #1f3240;
  overflow: hidden;
}

.allocation-fill {
  display: block;
  height: 100%;
  background: linear-gradient(90deg, #64b5f6, #7ce79b);
}

.member-toolbar {
  align-items: center;
  margin-top: 18px;
}

.member-search {
  width: min(420px, 45vw);
}

.member-table {
  margin-top: 12px;
  border: 1px solid #202020;
  border-radius: 8px;
  overflow: hidden;
}

.member-row {
  display: grid;
  grid-template-columns: 150px minmax(0, 1fr) 44px;
  gap: 12px;
  align-items: center;
  min-height: 48px;
  padding: 8px 12px;
  border-bottom: 1px solid #1a1a1a;
}

.member-table--custom .member-row {
  grid-template-columns: 150px minmax(0, 1fr) 160px 44px;
}

.member-row:last-child {
  border-bottom: 0;
}

.member-row--head {
  min-height: 36px;
  color: #808080;
  background: #0b0b0b;
  font-size: 10px;
  font-weight: 800;
  text-transform: uppercase;
  letter-spacing: 0.08em;
}

.member-symbol {
  border: 0;
  background: transparent;
  color: #8fc9ff;
  font: inherit;
  font-weight: 900;
  text-align: left;
  cursor: pointer;
}

.member-symbol:hover {
  color: #cde9ff;
}

.member-name {
  color: #a5a5a5;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.weight-input-wrap {
  min-width: 0;
}

.weight-input {
  padding: 7px 9px;
}

.remove-btn {
  width: 32px;
  height: 32px;
  border: 1px solid #73333d;
  border-radius: 6px;
  background: #211012;
  color: #ffb0ba;
  font: inherit;
  font-weight: 900;
  cursor: pointer;
}

.empty-state {
  padding: 16px;
  color: #777;
  font-size: 11px;
}

.modal-overlay {
  position: fixed;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgb(0 0 0 / 0.68);
  z-index: 80;
}

.modal {
  width: min(440px, calc(100vw - 32px));
  border: 1px solid #2a2a2a;
  border-radius: 10px;
  background: #101010;
  padding: 16px;
  box-shadow: 0 28px 80px rgb(0 0 0 / 0.45);
}

.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 16px;
}

@media (max-width: 920px) {
  .basket-view {
    flex-direction: column;
  }

  .basket-sidebar {
    width: 100%;
    max-height: 280px;
    border-right: 0;
    border-bottom: 1px solid #1a1a1a;
  }

  .basket-main {
    padding: 14px;
  }

  .form-grid,
  .member-row {
    grid-template-columns: 1fr;
  }

  .member-search {
    width: 100%;
  }

  .panel-title-row,
  .member-toolbar {
    flex-direction: column;
    align-items: stretch;
  }
}
.basket-view { background: var(--tc-window-bg); color: var(--tc-text); font-family: var(--tc-font-family); font-size: 12px; }
.basket-sidebar { border-color: var(--tc-border); background: var(--tc-window-bg); }
.basket-sidebar__head { border-color: var(--tc-border); background: var(--tc-header-bottom); }
.basket-sidebar__head h1, .panel-title-row h2, .member-toolbar h3, .modal h3 { color: var(--tc-text); }
.basket-sidebar__head p, .panel-title-row p, .member-toolbar span, .basket-card__meta, .modal p { color: var(--tc-text-muted); }
.basket-panel, .basket-card, .modal { border-color: var(--tc-border); border-radius: var(--tc-radius); background: var(--tc-panel-bg); color: var(--tc-text); }
.basket-new { border-color: var(--tc-accent); border-radius: var(--tc-radius); background: var(--tc-control-bg); color: var(--tc-accent-soft); }
.basket-card:hover, .basket-card--active { border-color: var(--tc-accent); background: color-mix(in srgb, var(--tc-accent) 13%, var(--tc-panel-bg)); }
.basket-card__name { color: var(--tc-text); }
.basket-list__state, .empty-state, .field-label { color: var(--tc-text-muted); }
.member-table { border-color: var(--tc-border); }
.member-row { border-color: var(--tc-border); background: var(--tc-window-bg); color: var(--tc-text); }
.member-row--head { background: var(--tc-header-bottom); color: var(--tc-text-muted); }
.form-input, .form-select, .form-textarea { border-color: var(--tc-border-strong); border-radius: var(--tc-radius); background: var(--tc-input-bg); color: var(--tc-text); }
.btn { border-color: var(--tc-border-strong); border-radius: var(--tc-radius); background: var(--tc-control-bg); color: var(--tc-text); }
.btn-primary { border-color: var(--tc-accent); background: color-mix(in srgb, var(--tc-accent) 15%, var(--tc-control-bg)); color: var(--tc-accent-soft); }
.btn-danger, .remove-btn { border-color: color-mix(in srgb, var(--tc-negative) 55%, var(--tc-border)); background: color-mix(in srgb, var(--tc-negative) 12%, var(--tc-control-bg)); color: var(--tc-negative); }
.basket-view :is(button, input, select, textarea):focus-visible { outline: 2px solid var(--tc-accent); outline-offset: 2px; }
</style>
