<template>
  <section class="code-library-tool" aria-label="Python analysis library">
    <header class="code-library-tool__header">
      <strong>Python Library</strong>
      <input v-model.trim="filter" aria-label="Filter Python assets" placeholder="Filter assets" />
      <button type="button" :disabled="loading" @click="refresh">{{ loading ? 'Loading…' : 'Refresh' }}</button>
      <button type="button" @click="fileInput?.click()">Import</button>
      <input ref="fileInput" class="code-library-tool__file" type="file" accept="application/json,.json" @change="importAsset" />
    </header>
    <p v-if="error" class="code-library-tool__error">{{ error }}</p>
    <p v-else-if="loading && !assets.length" class="code-library-tool__notice">Loading user-owned assets…</p>
    <p v-else-if="!filteredAssets.length" class="code-library-tool__notice">No matching Python assets.</p>
    <div v-else class="code-library-tool__assets" role="list">
      <article v-for="asset in filteredAssets" :key="asset.id" class="code-library-tool__asset" :class="{ 'code-library-tool__asset--archived': asset.is_archived }" role="listitem">
        <div class="code-library-tool__asset-main">
          <strong>{{ asset.name }}</strong>
          <small>{{ asset.kind }} · {{ asset.versions.length }} version{{ asset.versions.length === 1 ? '' : 's' }}{{ asset.is_archived ? ' · archived' : '' }}</small>
        </div>
        <div class="code-library-tool__asset-actions">
          <button type="button" title="Export asset" @click="exportAsset(asset)">Export</button>
          <button type="button" title="Clone asset" @click="cloneAsset(asset)">Clone</button>
          <button type="button" :title="asset.is_archived ? 'Unarchive asset' : 'Archive asset'" @click="toggleArchive(asset)">{{ asset.is_archived ? 'Unarchive' : 'Archive' }}</button>
        </div>
      </article>
    </div>
    <p class="code-library-tool__notice">Versions are immutable and validated by the canonical Python contract before import or clone.</p>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { api } from '@/lib/api'

interface CodeVersion {
  id?: number
  version_number: number
  source: string
  output_contract: string
  parameter_schema: Record<string, unknown>
  default_parameters: Record<string, unknown>
}
interface CodeAsset {
  id: number
  stable_key: string
  name: string
  kind: string
  is_archived: boolean
  versions: CodeVersion[]
}

const assets = ref<CodeAsset[]>([])
const filter = ref('')
const loading = ref(false)
const error = ref('')
const fileInput = ref<HTMLInputElement | null>(null)
const filteredAssets = computed(() => {
  const needle = filter.value.toLowerCase()
  return assets.value.filter(asset => !needle || `${asset.name} ${asset.kind} ${asset.stable_key}`.toLowerCase().includes(needle))
})

async function refresh() {
  loading.value = true
  error.value = ''
  try { assets.value = await api.get<CodeAsset[]>('/code/assets') }
  catch (cause: any) { error.value = cause?.message ?? 'Unable to load Python assets' }
  finally { loading.value = false }
}
function exportAsset(asset: CodeAsset) {
  const payload = JSON.stringify({ stable_key: asset.stable_key, name: asset.name, kind: asset.kind, versions: asset.versions.map(({ id: _id, ...version }) => version) }, null, 2)
  const url = URL.createObjectURL(new Blob([payload], { type: 'application/json' }))
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = `${asset.stable_key || 'python-asset'}.json`
  anchor.click()
  URL.revokeObjectURL(url)
}
async function cloneAsset(asset: CodeAsset) {
  error.value = ''
  try {
    const suffix = Date.now().toString(36)
    const clone = await api.post<CodeAsset>(`/code/assets/${asset.id}/clone`, { stable_key: `${asset.stable_key}-copy-${suffix}`.slice(0, 80), name: `${asset.name} copy` })
    assets.value = [...assets.value, clone].sort((left, right) => left.name.localeCompare(right.name))
  } catch (cause: any) { error.value = cause?.message ?? 'Unable to clone Python asset' }
}
async function toggleArchive(asset: CodeAsset) {
  error.value = ''
  try {
    const updated = await api.post<CodeAsset>(`/code/assets/${asset.id}/archive`, { is_archived: !asset.is_archived })
    assets.value = assets.value.map(item => item.id === updated.id ? updated : item)
  } catch (cause: any) { error.value = cause?.message ?? 'Unable to update asset archive state' }
}
async function importAsset(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  error.value = ''
  try {
    const payload = JSON.parse(await file.text())
    const imported = await api.post<CodeAsset>('/code/assets/import', payload)
    assets.value = [...assets.value, imported].sort((left, right) => left.name.localeCompare(right.name))
  } catch (cause: any) { error.value = cause?.message ?? 'Unable to import Python asset' }
  finally { input.value = '' }
}
onMounted(() => { void refresh() })
</script>

<style scoped>
.code-library-tool { display:grid; grid-template-rows:auto auto minmax(0,1fr) auto; gap:6px; height:100%; min-height:0; padding:6px; background:#11161b; color:#cbd5dc; font:10px "Segoe UI",Arial,sans-serif; }
.code-library-tool__header { display:grid; grid-template-columns:auto minmax(0,1fr) auto auto; align-items:center; gap:5px; }
.code-library-tool__header input:not(.code-library-tool__file), .code-library-tool button { border:1px solid #3a4954; background:#172027; color:#dce6ed; font:inherit; padding:3px 5px; }
.code-library-tool__file { display:none; }
.code-library-tool__assets { overflow:auto; display:grid; align-content:start; gap:3px; }
.code-library-tool__asset { display:grid; grid-template-columns:minmax(0,1fr) auto; gap:6px; align-items:center; border:1px solid #293740; padding:5px; }
.code-library-tool__asset--archived { opacity:.62; }
.code-library-tool__asset-main { display:grid; gap:2px; min-width:0; }
.code-library-tool__asset-main strong { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.code-library-tool__asset-main small, .code-library-tool__notice { color:#8195a3; }
.code-library-tool__asset-actions { display:flex; gap:3px; }
.code-library-tool__asset-actions button { padding:2px 4px; }
.code-library-tool__error { color:#f0a2a2; }
</style>
