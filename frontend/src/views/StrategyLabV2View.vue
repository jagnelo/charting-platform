<template>
  <main class="strategy-lab-v2" aria-labelledby="strategy-lab-v2-title">
    <header class="strategy-lab-v2__header">
      <div>
        <p class="strategy-lab-v2__eyebrow">IMMUTABLE EXPERIMENT RECORDS</p>
        <h1 id="strategy-lab-v2-title">Strategy Lab v2</h1>
        <p class="strategy-lab-v2__subtitle">
          Inspect owner-scoped strategies, trials and persisted artifacts without dispatching work.
        </p>
      </div>
      <router-link class="strategy-lab-v2__back" to="/">Back to workstation</router-link>
    </header>

    <section class="strategy-lab-v2__boundary" aria-label="Execution boundary">
      <strong>Read-only boundary.</strong>
      <span>This view does not start a backtest or forward run. Native, broker and capital actions remain unavailable.</span>
    </section>

    <nav class="strategy-lab-v2__tabs" aria-label="Strategy Lab v2 resources">
      <button
        v-for="resource in resources"
        :key="resource.kind"
        type="button"
        :aria-pressed="activeKind === resource.kind"
        @click="selectKind(resource.kind)"
      >
        {{ resource.label }}
        <span class="strategy-lab-v2__count">{{ pages[resource.kind].items.length }}</span>
      </button>
    </nav>

    <section class="strategy-lab-v2__content">
      <div class="strategy-lab-v2__list" aria-label="Resource collection">
        <div class="strategy-lab-v2__list-heading">
          <h2>{{ activeLabel }}</h2>
          <button type="button" :disabled="pages[activeKind].loading" @click="loadCollection(activeKind)">
            {{ pages[activeKind].loading ? 'Loading…' : 'Refresh' }}
          </button>
        </div>

        <p v-if="pages[activeKind].error" class="strategy-lab-v2__error" role="alert">
          {{ pages[activeKind].error }}
        </p>
        <p v-else-if="pages[activeKind].loading && pages[activeKind].items.length === 0" role="status">
          Loading {{ activeLabel.toLowerCase() }}…
        </p>
        <p v-else-if="pages[activeKind].items.length === 0" class="strategy-lab-v2__empty">
          No {{ activeLabel.toLowerCase() }} are available for this account yet.
        </p>

        <ul v-else class="strategy-lab-v2__items">
          <li v-for="item in pages[activeKind].items" :key="`${item.type}:${item.id}`">
            <button
              type="button"
              class="strategy-lab-v2__item"
              :class="{ 'is-selected': selected?.type === item.type && selected.id === item.id }"
              :aria-current="selected?.type === item.type && selected.id === item.id ? 'true' : undefined"
              @click="openResource(item)"
            >
              <span class="strategy-lab-v2__item-name">{{ resourceName(item) }}</span>
              <span class="strategy-lab-v2__item-id">{{ item.id }}</span>
            </button>
          </li>
        </ul>

        <button
          v-if="pages[activeKind].nextCursor"
          type="button"
          class="strategy-lab-v2__next"
          :disabled="pages[activeKind].loading"
          @click="loadCollection(activeKind, pages[activeKind].nextCursor ?? undefined, true)"
        >
          Load next page
        </button>
      </div>

      <article class="strategy-lab-v2__detail" aria-label="Selected resource detail" aria-live="polite">
        <template v-if="detailLoading">
          <h2>Resource detail</h2>
          <p role="status">Loading persisted detail…</p>
        </template>
        <template v-else-if="detailError">
          <h2>Resource detail</h2>
          <p class="strategy-lab-v2__error" role="alert">{{ detailError }}</p>
        </template>
        <template v-else-if="detail">
          <p class="strategy-lab-v2__eyebrow">{{ detail.type }}</p>
          <h2>{{ resourceName(detail) }}</h2>
          <p class="strategy-lab-v2__detail-id">{{ detail.id }}</p>

          <section v-if="selectedStudyReference" class="strategy-lab-v2__study" aria-label="Pinned Study lineage">
            <h3>Pinned Study lineage</h3>
            <dl>
              <div v-for="field in studyFields" :key="field">
                <dt>{{ field }}</dt>
                <dd>{{ selectedStudyReference[field] }}</dd>
              </div>
            </dl>
            <p>This is immutable Study provenance, not proof of native execution.</p>
          </section>

          <details class="strategy-lab-v2__json">
            <summary>Persisted attributes</summary>
            <pre>{{ formatAttributes(detail.attributes) }}</pre>
          </details>
        </template>
        <div v-else class="strategy-lab-v2__placeholder">
          <h2>Resource detail</h2>
          <p>Select a persisted record to inspect its owner-scoped attributes and immutable lineage.</p>
        </div>
      </article>
    </section>
  </main>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import { api } from '@/lib/api'

type ResourceKind = 'strategies' | 'trials' | 'artifacts'
type ResourceDocument = {
  type: string
  id: string
  attributes: Record<string, unknown>
  meta?: Record<string, unknown>
}
type CollectionResponse = {
  data: ResourceDocument[]
  links?: { next?: string | null }
}
type ResourceResponse = { data: ResourceDocument }
type CollectionState = {
  items: ResourceDocument[]
  nextCursor: string | null
  loading: boolean
  error: string | null
  loaded: boolean
  requestId: number
}

const resources: ReadonlyArray<{ kind: ResourceKind; label: string }> = [
  { kind: 'strategies', label: 'Strategies' },
  { kind: 'trials', label: 'Trials' },
  { kind: 'artifacts', label: 'Artifacts' },
]

const studyFields = [
  'research_run_id',
  'code_version_id',
  'artifact_id',
  'artifact_name',
  'artifact_type',
  'output_contract',
  'run_reproducibility_hash',
  'code_version_digest',
  'dataset_manifest_digest',
  'artifact_content_digest',
] as const

const pages = reactive<Record<ResourceKind, CollectionState>>({
  strategies: { items: [], nextCursor: null, loading: false, error: null, loaded: false, requestId: 0 },
  trials: { items: [], nextCursor: null, loading: false, error: null, loaded: false, requestId: 0 },
  artifacts: { items: [], nextCursor: null, loading: false, error: null, loaded: false, requestId: 0 },
})

const activeKind = ref<ResourceKind>('strategies')
const selected = ref<ResourceDocument | null>(null)
const detail = ref<ResourceDocument | null>(null)
const detailLoading = ref(false)
const detailError = ref<string | null>(null)

const activeLabel = computed(() => resources.find(item => item.kind === activeKind.value)?.label ?? 'Resources')
const selectedStudyReference = computed(() => {
  const value = detail.value?.attributes.selected_study_artifact
  return isRecord(value) ? value : null
})

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function resourceName(resource: ResourceDocument): string {
  for (const key of ['name', 'label', 'display_name', 'title', 'strategy_id']) {
    const value = resource.attributes[key]
    if (typeof value === 'string' && value.trim()) return value
  }
  return `${resource.type} ${resource.id}`
}

function formatAttributes(attributes: Record<string, unknown>): string {
  return JSON.stringify(attributes, null, 2)
}

async function loadCollection(kind: ResourceKind, cursor?: string, append = false) {
  const state = pages[kind]
  const requestId = state.requestId + 1
  state.requestId = requestId
  state.loading = true
  state.error = null
  try {
    const response = await api.get<CollectionResponse>(`/strategy-lab/v2/${kind}`, {
      limit: 50,
      ...(cursor ? { cursor } : {}),
    })
    if (state.requestId !== requestId) return
    if (!Array.isArray(response.data)) throw new Error('The v2 resource response is invalid')
    state.items = append ? [...state.items, ...response.data] : response.data
    state.nextCursor = response.links?.next ?? null
    state.loaded = true
  } catch (cause) {
    if (state.requestId !== requestId) return
    state.error = cause instanceof Error ? cause.message : 'Unable to load Strategy Lab v2 resources'
  } finally {
    if (state.requestId === requestId) state.loading = false
  }
}

async function selectKind(kind: ResourceKind) {
  if (activeKind.value === kind) return
  activeKind.value = kind
  selected.value = null
  detail.value = null
  detailError.value = null
  if (!pages[kind].loaded) await loadCollection(kind)
}

async function openResource(resource: ResourceDocument) {
  selected.value = resource
  detail.value = null
  detailError.value = null
  detailLoading.value = true
  try {
    const response = await api.get<ResourceResponse>(
      `/strategy-lab/v2/${activeKind.value}/${encodeURIComponent(resource.id)}`,
    )
    if (selected.value?.type !== resource.type || selected.value.id !== resource.id) return
    if (!response.data || response.data.id !== resource.id || response.data.type !== resource.type) {
      throw new Error('The v2 resource detail did not match the selected record')
    }
    detail.value = response.data
  } catch (cause) {
    if (selected.value?.type !== resource.type || selected.value.id !== resource.id) return
    detailError.value = cause instanceof Error ? cause.message : 'Unable to load the selected resource'
  } finally {
    if (selected.value?.type === resource.type && selected.value.id === resource.id) {
      detailLoading.value = false
    }
  }
}

onMounted(() => {
  void loadCollection(activeKind.value)
})
</script>

<style scoped>
.strategy-lab-v2 {
  min-height: 100vh;
  overflow: auto;
  padding: 28px clamp(18px, 4vw, 56px) 48px;
  background: #0b0d10;
  color: #e4e8ee;
  font-family: Inter, system-ui, sans-serif;
}
.strategy-lab-v2__header { display: flex; align-items: flex-start; justify-content: space-between; gap: 24px; max-width: 1440px; margin: 0 auto 24px; }
.strategy-lab-v2__eyebrow { color: #8fa3b8; font-size: 11px; font-weight: 700; letter-spacing: .12em; }
.strategy-lab-v2 h1 { margin-top: 8px; font-size: clamp(26px, 4vw, 38px); }
.strategy-lab-v2__subtitle { margin-top: 8px; color: #aab5c2; }
.strategy-lab-v2__back { color: #a8d7ff; text-decoration: none; }
.strategy-lab-v2__boundary, .strategy-lab-v2__content { max-width: 1440px; margin: 0 auto; }
.strategy-lab-v2__boundary { display: flex; flex-wrap: wrap; gap: 8px; padding: 12px 14px; border: 1px solid #3c4b5a; border-radius: 8px; color: #c6d1dc; background: #121923; }
.strategy-lab-v2__tabs { display: flex; gap: 8px; max-width: 1440px; margin: 20px auto 12px; border-bottom: 1px solid #29323c; }
.strategy-lab-v2__tabs button, .strategy-lab-v2__list-heading button, .strategy-lab-v2__next { border: 1px solid #374452; border-radius: 6px; padding: 8px 12px; background: #141b23; color: #dce7f1; cursor: pointer; }
.strategy-lab-v2__tabs button[aria-pressed="true"] { border-color: #67b7f5; color: #b9e1ff; background: #15283a; }
.strategy-lab-v2__count { margin-left: 6px; color: #91a3b5; font-variant-numeric: tabular-nums; }
.strategy-lab-v2__content { display: grid; grid-template-columns: minmax(260px, 360px) minmax(0, 1fr); gap: 16px; }
.strategy-lab-v2__list, .strategy-lab-v2__detail { min-width: 0; border: 1px solid #29323c; border-radius: 9px; background: #10151b; }
.strategy-lab-v2__list { padding: 14px; }
.strategy-lab-v2__list-heading { display: flex; justify-content: space-between; align-items: center; gap: 12px; margin-bottom: 12px; }
.strategy-lab-v2 h2 { font-size: 17px; }
.strategy-lab-v2__items { display: grid; gap: 6px; list-style: none; }
.strategy-lab-v2__item { display: flex; width: 100%; flex-direction: column; gap: 4px; border: 1px solid transparent; border-radius: 6px; padding: 10px; text-align: left; background: #151c24; color: #dce7f1; cursor: pointer; }
.strategy-lab-v2__item:hover, .strategy-lab-v2__item.is-selected { border-color: #477aa0; background: #182b3a; }
.strategy-lab-v2__item-id, .strategy-lab-v2__detail-id { color: #9aa9b8; font-size: 12px; overflow-wrap: anywhere; }
.strategy-lab-v2__next { width: 100%; margin-top: 10px; }
.strategy-lab-v2__detail { padding: 20px; }
.strategy-lab-v2__detail h2 { margin: 6px 0; overflow-wrap: anywhere; }
.strategy-lab-v2__study { margin-top: 22px; border-top: 1px solid #29323c; padding-top: 16px; }
.strategy-lab-v2__study h3 { margin-bottom: 12px; font-size: 14px; }
.strategy-lab-v2__study dl { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
.strategy-lab-v2__study dl div { min-width: 0; border: 1px solid #29323c; border-radius: 6px; padding: 9px; }
.strategy-lab-v2__study dt { color: #9aa9b8; font-size: 11px; overflow-wrap: anywhere; }
.strategy-lab-v2__study dd { margin-top: 4px; color: #dce7f1; font-size: 12px; overflow-wrap: anywhere; }
.strategy-lab-v2__study p, .strategy-lab-v2__empty, .strategy-lab-v2__placeholder p { margin-top: 12px; color: #9aa9b8; line-height: 1.5; }
.strategy-lab-v2__json { margin-top: 18px; border-top: 1px solid #29323c; padding-top: 14px; }
.strategy-lab-v2__json summary { cursor: pointer; color: #b9d7ef; }
.strategy-lab-v2__json pre { max-height: 420px; overflow: auto; margin-top: 10px; border-radius: 6px; padding: 12px; background: #090c0f; color: #c9d5e0; font: 12px/1.5 ui-monospace, monospace; white-space: pre-wrap; overflow-wrap: anywhere; }
.strategy-lab-v2__error { color: #ff9d9d; line-height: 1.5; }
.strategy-lab-v2__placeholder { padding: 12px 0; }
@media (max-width: 760px) {
  .strategy-lab-v2__header { flex-direction: column; }
  .strategy-lab-v2__content { grid-template-columns: minmax(0, 1fr); }
  .strategy-lab-v2__study dl { grid-template-columns: minmax(0, 1fr); }
}
</style>
