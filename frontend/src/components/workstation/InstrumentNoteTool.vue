<template>
  <section class="note-tool" role="region" :aria-label="`${symbol} notes`" :aria-busy="loading">
    <div class="note-tool__status" :role="statusRole" :aria-live="statusRole === 'alert' ? 'assertive' : 'polite'" aria-atomic="true">{{ symbol }} · {{ status }}</div>
    <textarea v-model="content" :disabled="!instrumentId || loading" :placeholder="instrumentId ? 'Write a symbol note…' : 'Select a canonical instrument.'" aria-label="Instrument note" />
  </section>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useQueryClient } from '@tanstack/vue-query'
import { api } from '@/lib/api'
import { assertAuthSessionCurrent, captureAuthSession, type AuthSessionSnapshot } from '@/lib/authSession'

const props = defineProps<{ instrumentId: number | null | undefined; symbol: string }>()
const queryClient = useQueryClient()
const content = ref('')
const loading = ref(false)
const status = ref('No note')
const statusRole = computed(() => /unable|error|failed|unavailable/i.test(status.value) ? 'alert' : 'status')
type NoteCacheValue = { content: string; updated_at: string; pending?: boolean }
type PendingSave = { instrumentId: number; content: string; revision: number; authSession: AuthSessionSnapshot }
let saveTimer: ReturnType<typeof setTimeout> | null = null
let pendingSave: PendingSave | null = null
let loadedId: number | null = null
let loadGeneration = 0
let contentRevision = 0
let mounted = false
let hydrating = false
const latestRevisionByInstrument = new Map<number, number>()
const saveByInstrument = new Map<number, Promise<void>>()

function noteKey(instrumentId: number) {
  return ['workstation', 'instrument-note', instrumentId] as const
}

function flushPendingSave(): Promise<void> {
  const draft = pendingSave
  if (saveTimer) clearTimeout(saveTimer)
  saveTimer = null
  if (!draft) return Promise.resolve()
  pendingSave = null

  const previous = saveByInstrument.get(draft.instrumentId) ?? Promise.resolve()
  const operation = previous.catch(() => undefined).then(async () => {
    assertAuthSessionCurrent(draft.authSession)
    const note = await api.put<{ updated_at: string }>(`/notes/instruments/${draft.instrumentId}`, { content: draft.content })
    assertAuthSessionCurrent(draft.authSession)
    if (latestRevisionByInstrument.get(draft.instrumentId) !== draft.revision) return
    queryClient.setQueryData<NoteCacheValue>(noteKey(draft.instrumentId), {
      content: draft.content,
      updated_at: note.updated_at,
    })
    if (mounted && props.instrumentId === draft.instrumentId && loadedId === draft.instrumentId && content.value === draft.content) {
      status.value = `Saved ${new Date(note.updated_at).toLocaleString()}`
    }
  }).catch((cause: any) => {
    try {
      assertAuthSessionCurrent(draft.authSession)
    } catch {
      return
    }
    if (latestRevisionByInstrument.get(draft.instrumentId) === draft.revision
      && mounted && props.instrumentId === draft.instrumentId && loadedId === draft.instrumentId) {
      status.value = cause?.message ?? 'Unable to save note'
    }
  }).finally(() => {
    if (saveByInstrument.get(draft.instrumentId) === operation) saveByInstrument.delete(draft.instrumentId)
  })
  saveByInstrument.set(draft.instrumentId, operation)
  return operation
}

async function load() {
  void flushPendingSave()
  const generation = ++loadGeneration
  loadedId = null
  hydrating = true
  content.value = ''
  hydrating = false
  if (!props.instrumentId) {
    loading.value = false
    status.value = 'No canonical instrument'
    return
  }
  loading.value = true
  status.value = 'Loading…'
  try {
    const instrumentId = props.instrumentId
    const key = noteKey(instrumentId)
    const cached = queryClient.getQueryData<NoteCacheValue>(key)
    if (cached?.pending) {
      hydrating = true
      content.value = cached.content
      hydrating = false
      loadedId = instrumentId
      status.value = 'Unsaved draft retained'
      return
    }
    const note = await queryClient.fetchQuery<NoteCacheValue | null>({
      queryKey: key,
      queryFn: () => api.get<{ content: string; updated_at: string } | null>(`/notes/instruments/${instrumentId}`),
      staleTime: 30_000,
    })
    if (!mounted || generation !== loadGeneration || props.instrumentId !== instrumentId) return
    hydrating = true
    content.value = note?.content ?? ''
    hydrating = false
    loadedId = instrumentId
    status.value = note ? `Saved ${new Date(note.updated_at).toLocaleString()}` : 'No note'
  } catch (cause: any) {
    if (mounted && generation === loadGeneration) status.value = cause?.message ?? 'Unable to load note'
  } finally {
    if (mounted && generation === loadGeneration) loading.value = false
  }
}

watch(() => props.instrumentId, () => { void load() }, { immediate: true })
watch(content, () => {
  if (hydrating || !props.instrumentId || loadedId !== props.instrumentId || loading.value) return
  if (saveTimer) clearTimeout(saveTimer)
  status.value = 'Saving…'
  const instrumentId = props.instrumentId
  const draft: PendingSave = {
    instrumentId,
    content: content.value,
    revision: ++contentRevision,
    authSession: captureAuthSession(),
  }
  pendingSave = draft
  latestRevisionByInstrument.set(instrumentId, draft.revision)
  const previous = queryClient.getQueryData<NoteCacheValue>(noteKey(instrumentId))
  queryClient.setQueryData<NoteCacheValue>(noteKey(instrumentId), {
    content: draft.content,
    updated_at: previous?.updated_at ?? '',
    pending: true,
  })
  saveTimer = setTimeout(() => { void flushPendingSave() }, 550)
}, { flush: 'sync' })
onMounted(() => { mounted = true })
onBeforeUnmount(() => {
  mounted = false
  loadGeneration += 1
  void flushPendingSave()
})
</script>

<style scoped>
.note-tool { display: grid; height: 100%; min-height: 0; grid-template-rows: 20px minmax(0, 1fr); background: #11161b; }
.note-tool__status { padding: 4px 7px; border-bottom: 1px solid #2c3740; color: #81929e; font: 9px "Segoe UI", Arial, sans-serif; }
textarea { width: 100%; min-width: 0; min-height: 0; resize: none; border: 0; outline: 0; padding: 8px; background: #11161b; color: #d4dfe5; font: 11px/1.45 "Segoe UI", Arial, sans-serif; }
textarea:disabled { color: #75838c; }
</style>
