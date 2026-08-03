<template>
  <section class="note-tool">
    <div class="note-tool__status">{{ symbol }} · {{ status }}</div>
    <textarea v-model="content" :disabled="!instrumentId || loading" :placeholder="instrumentId ? 'Write a symbol note…' : 'Select a canonical instrument.'" aria-label="Instrument note" />
  </section>
</template>

<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import { api } from '@/lib/api'

const props = defineProps<{ instrumentId: number | null | undefined; symbol: string }>()
const content = ref('')
const loading = ref(false)
const status = ref('No note')
let saveTimer: ReturnType<typeof setTimeout> | null = null
let loadedId: number | null = null
let loadGeneration = 0

async function load() {
  const generation = ++loadGeneration
  if (saveTimer) clearTimeout(saveTimer)
  loadedId = null
  content.value = ''
  if (!props.instrumentId) {
    loading.value = false
    status.value = 'No canonical instrument'
    return
  }
  loading.value = true
  status.value = 'Loading…'
  try {
    const instrumentId = props.instrumentId
    const note = await api.get<{ content: string; updated_at: string } | null>(`/notes/instruments/${instrumentId}`)
    if (generation !== loadGeneration || props.instrumentId !== instrumentId) return
    content.value = note?.content ?? ''
    loadedId = instrumentId
    status.value = note ? `Saved ${new Date(note.updated_at).toLocaleString()}` : 'No note'
  } catch (cause: any) {
    if (generation === loadGeneration) status.value = cause?.message ?? 'Unable to load note'
  } finally {
    if (generation === loadGeneration) loading.value = false
  }
}

watch(() => props.instrumentId, () => { void load() }, { immediate: true })
watch(content, () => {
  if (!props.instrumentId || loadedId !== props.instrumentId || loading.value) return
  if (saveTimer) clearTimeout(saveTimer)
  status.value = 'Saving…'
  const instrumentId = props.instrumentId
  const draft = content.value
  saveTimer = setTimeout(async () => {
    try {
      const note = await api.put<{ updated_at: string }>(`/notes/instruments/${instrumentId}`, { content: draft })
      if (props.instrumentId === instrumentId && loadedId === instrumentId) status.value = `Saved ${new Date(note.updated_at).toLocaleString()}`
    } catch (cause: any) {
      if (props.instrumentId === instrumentId) status.value = cause?.message ?? 'Unable to save note'
    }
  }, 550)
})
onBeforeUnmount(() => { if (saveTimer) clearTimeout(saveTimer) })
</script>

<style scoped>
.note-tool { display: grid; height: 100%; min-height: 0; grid-template-rows: 20px minmax(0, 1fr); background: #11161b; }
.note-tool__status { padding: 4px 7px; border-bottom: 1px solid #2c3740; color: #81929e; font: 9px "Segoe UI", Arial, sans-serif; }
textarea { width: 100%; min-width: 0; min-height: 0; resize: none; border: 0; outline: 0; padding: 8px; background: #11161b; color: #d4dfe5; font: 11px/1.45 "Segoe UI", Arial, sans-serif; }
textarea:disabled { color: #75838c; }
</style>
