<template>
  <section class="note-tool" role="region" :aria-label="`${symbol} notes`" :aria-busy="loading">
    <div class="note-tool__status" :role="statusRole" :aria-live="statusRole === 'alert' ? 'assertive' : 'polite'" aria-atomic="true">{{ symbol }} · {{ status }}</div>
    <textarea v-model="content" :disabled="!activeInstrumentId || loading" :placeholder="activeInstrumentId ? 'Write a symbol note…' : 'Select a canonical instrument.'" aria-label="Instrument note" />
  </section>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useQueryClient } from '@tanstack/vue-query'
import { api, setQueuedApiRequestPriority, type ApiRequestPriority } from '@/lib/api'
import { assertAuthSessionCurrent, captureAuthSession, type AuthSessionSnapshot } from '@/lib/authSession'
import { fetchCanonicalInstrument } from '@/lib/workstation/instrumentQueries'

const props = withDefaults(defineProps<{ instrumentId: number | null | undefined; symbol: string; requestPriority?: ApiRequestPriority }>(), {
  requestPriority: 'auto',
})
const queryClient = useQueryClient()
const content = ref('')
const loading = ref(false)
const status = ref('No note')
const statusRole = computed(() => /unable|error|failed|unavailable/i.test(status.value) ? 'alert' : 'status')
const resolvedIdentity = ref<{ symbol: string; instrumentId: number } | null>(null)
const activeInstrumentId = computed(() => {
  if (props.instrumentId != null) return props.instrumentId
  const symbol = props.symbol.trim().toUpperCase()
  return resolvedIdentity.value?.symbol === symbol ? resolvedIdentity.value.instrumentId : null
})
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
    if (mounted && activeInstrumentId.value === draft.instrumentId && loadedId === draft.instrumentId && content.value === draft.content) {
      status.value = `Saved ${new Date(note.updated_at).toLocaleString()}`
    }
  }).catch((cause: any) => {
    try {
      assertAuthSessionCurrent(draft.authSession)
    } catch {
      return
    }
    if (latestRevisionByInstrument.get(draft.instrumentId) === draft.revision
      && mounted && activeInstrumentId.value === draft.instrumentId && loadedId === draft.instrumentId) {
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
  loading.value = true
  const expectedSymbol = props.symbol.trim().toUpperCase()
  let instrumentId = props.instrumentId ?? (
    resolvedIdentity.value?.symbol === expectedSymbol ? resolvedIdentity.value.instrumentId : null
  )
  const authSession = captureAuthSession()
  try {
    if (instrumentId == null) {
      if (!expectedSymbol) {
        loading.value = false
        status.value = 'No canonical instrument'
        return
      }
      status.value = 'Resolving canonical instrument…'
      const instrument = await fetchCanonicalInstrument(queryClient, expectedSymbol)
      assertAuthSessionCurrent(authSession)
      if (!mounted || generation !== loadGeneration || props.symbol.trim().toUpperCase() !== expectedSymbol) return
      if (instrument.symbol.trim().toUpperCase() !== expectedSymbol || !Number.isSafeInteger(instrument.id) || instrument.id <= 0) {
        throw new Error('Canonical instrument lookup returned a mismatched identity')
      }
      resolvedIdentity.value = { symbol: expectedSymbol, instrumentId: instrument.id }
      instrumentId = instrument.id
    }
    status.value = 'Loading…'
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
    // A visible Notes panel can join the hidden Notes query already in flight
    // for this key. TanStack Query reuses that pending queryFn, so the new
    // fetch options cannot promote the queued HTTP request. Promote by queue
    // key before joining it; the watcher below handles later priority changes.
    if (props.requestPriority === 'high') {
      setQueuedApiRequestPriority(`instrument-note:${instrumentId}`, 'high')
    }
    const note = await queryClient.fetchQuery<NoteCacheValue | null>({
      queryKey: key,
      queryFn: ({ signal }) => api.get<{ content: string; updated_at: string } | null>(
        `/notes/instruments/${instrumentId}`,
        undefined,
        { signal, priority: props.requestPriority, queueKey: `instrument-note:${instrumentId}` },
      ),
      staleTime: 30_000,
    })
    assertAuthSessionCurrent(authSession)
    if (!mounted || generation !== loadGeneration || props.symbol.trim().toUpperCase() !== expectedSymbol) return
    hydrating = true
    content.value = note?.content ?? ''
    hydrating = false
    loadedId = instrumentId
    status.value = note ? `Saved ${new Date(note.updated_at).toLocaleString()}` : 'No note'
  } catch (cause: any) {
    try {
      assertAuthSessionCurrent(authSession)
    } catch {
      return
    }
    if (mounted && generation === loadGeneration) {
      status.value = cause?.status === 404
        ? 'No canonical instrument'
        : `Unable to resolve canonical instrument${cause?.message ? `: ${cause.message}` : ''}`
    }
  } finally {
    if (mounted && generation === loadGeneration) loading.value = false
  }
}

watch(() => [props.instrumentId, props.symbol] as const, () => { void load() }, { immediate: true })
watch(() => props.requestPriority, priority => {
  if (priority === 'high' && props.instrumentId) {
    setQueuedApiRequestPriority(`instrument-note:${props.instrumentId}`, 'high')
  }
})
watch(content, () => {
  const instrumentId = activeInstrumentId.value
  if (hydrating || instrumentId == null || loadedId !== instrumentId || loading.value) return
  if (saveTimer) clearTimeout(saveTimer)
  status.value = 'Saving…'
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
