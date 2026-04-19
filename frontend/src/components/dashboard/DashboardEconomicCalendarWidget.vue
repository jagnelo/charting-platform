<template>
  <div class="calendar-widget">
    <div v-if="!symbol" class="widget-state">Choose an instrument</div>
    <div v-else-if="loading" class="widget-state">Loading calendar...</div>
    <div v-else-if="error" class="widget-state error">{{ error }}</div>
    <div v-else-if="!events.length" class="widget-state">No calendar events found</div>
    <div v-else class="event-list">
      <div v-for="event in events" :key="`${event.date}-${event.event_type}`" class="event-row">
        <span class="event-date">{{ event.date }}</span>
        <span class="event-type">{{ labelFor(event.event_type) }}</span>
        <span class="event-title">{{ event.title }}</span>
        <span class="event-value">{{ valueFor(event) }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { api } from '@/lib/api'

interface CalendarEvent {
  date: string
  event_type: string
  symbol: string
  title: string
  value?: number | null
  actual?: number | null
  currency?: string | null
  is_estimate: boolean
}

const props = defineProps<{ config: Record<string, any>; overrideSymbol?: string }>()

const symbol = computed(() =>
  (props.overrideSymbol?.trim() || String(props.config.symbol ?? 'SPY').trim()).toUpperCase()
)
const events = ref<CalendarEvent[]>([])
const loading = ref(false)
const error = ref('')
let loadSeq = 0

async function load() {
  const seq = ++loadSeq
  if (!symbol.value) {
    events.value = []
    error.value = ''
    loading.value = false
    return
  }
  loading.value = true
  error.value = ''
  try {
    const loaded = await api.get<CalendarEvent[]>(`/calendar/instruments/${encodeURIComponent(symbol.value)}/calendar`)
    if (seq === loadSeq) events.value = loaded
  } catch (e: any) {
    if (seq === loadSeq) {
      error.value = e?.message ?? 'Calendar unavailable'
      events.value = []
    }
  } finally {
    if (seq === loadSeq) loading.value = false
  }
}

function labelFor(type: string) {
  return type.replace(/_/g, ' ')
}

function valueFor(event: CalendarEvent) {
  if (event.actual != null && event.value != null) return `${event.actual.toFixed(2)} / est ${event.value.toFixed(2)}`
  if (event.actual != null) return event.actual.toFixed(2)
  if (event.value != null) return event.value.toFixed(2)
  return event.is_estimate ? 'estimate' : ''
}

watch(symbol, load)
onMounted(load)
</script>

<style scoped>
.calendar-widget {
  height: 100%;
  min-height: 0;
  overflow: hidden;
}
.event-list {
  height: 100%;
  overflow: auto;
}
.event-row {
  display: grid;
  grid-template-columns: 82px 88px minmax(0, 1fr) auto;
  gap: 8px;
  align-items: center;
  min-height: 28px;
  padding: 5px 0;
  border-bottom: 1px solid #181818;
  font-size: 10px;
}
.event-date { color: #aaa; }
.event-type {
  color: #64b5f6;
  text-transform: capitalize;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.event-title {
  color: #777;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.event-value { color: #bbb; text-align: right; }
.widget-state {
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #555;
  font-size: 12px;
  text-align: center;
}
.widget-state.error { color: #ef5350; font-size: 10px; }
</style>
