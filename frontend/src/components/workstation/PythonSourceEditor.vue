<template>
  <div ref="root" class="python-source-editor">
    <div class="python-source-editor__toolbar">
      <span>Python · unified market SDK</span>
      <button type="button" :aria-label="`Normalize ${ariaLabel}`" @click="normalize">Normalize</button>
    </div>
    <textarea
      ref="editor"
      :value="modelValue"
      :aria-label="ariaLabel"
      :aria-controls="showSuggestions && suggestions.length ? suggestionListId : undefined"
      :aria-expanded="showSuggestions && suggestions.length ? 'true' : 'false'"
      :aria-activedescendant="showSuggestions && suggestions.length ? suggestionId(selectedSuggestionIndex) : undefined"
      aria-autocomplete="list"
      aria-haspopup="listbox"
      :placeholder="placeholder"
      :style="{ minHeight }"
      spellcheck="false"
      @input="updateValue(($event.target as HTMLTextAreaElement).value)"
      @keydown="handleKeydown"
      @keyup="updateSuggestions"
      @focus="updateSuggestions"
      @blur="hideSuggestions"
    />
    <div v-if="showSuggestions && suggestions.length" :id="suggestionListId" class="python-source-editor__suggestions" role="listbox" :aria-label="`${ariaLabel} SDK suggestions`">
      <button v-for="(suggestion, index) in suggestions" :id="suggestionId(index)" :key="suggestion.insert" type="button" role="option" :aria-selected="index === selectedSuggestionIndex" :class="{ 'python-source-editor__suggestion--selected': index === selectedSuggestionIndex }" @mousedown.prevent="insertSuggestion(suggestion.insert)">
        <code>{{ suggestion.insert }}</code><small>{{ suggestion.signature }}</small>
      </button>
    </div>
    <p v-if="suggestionStatus" class="python-source-editor__sr-status" role="status" aria-live="polite" aria-atomic="true">{{ suggestionStatus }}</p>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

interface Suggestion {
  prefix: string
  insert: string
  signature: string
}

const props = withDefaults(defineProps<{
  modelValue: string
  ariaLabel: string
  placeholder?: string
  minHeight?: string
}>(), { placeholder: '', minHeight: '90px' })
const emit = defineEmits<{ 'update:modelValue': [value: string] }>()

const root = ref<HTMLElement | null>(null)
const editor = ref<HTMLTextAreaElement | null>(null)
const showSuggestions = ref(false)
const editorPrefix = ref('')
const selectedSuggestionIndex = ref(0)
const instanceId = `python-source-editor-${typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function' ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`}`
const suggestionListId = `${instanceId}-suggestions`
const suggestionsCatalog: Suggestion[] = [
  { prefix: 'market', insert: 'market.close()', signature: 'series[float]' },
  { prefix: 'market', insert: 'market.open()', signature: 'series[float]' },
  { prefix: 'market', insert: 'market.high()', signature: 'series[float]' },
  { prefix: 'market', insert: 'market.low()', signature: 'series[float]' },
  { prefix: 'market', insert: 'market.volume()', signature: 'series[float | None]' },
  { prefix: 'market', insert: 'market.vwap()', signature: 'series[float | None]' },
  { prefix: 'market', insert: 'market.ohlcv()', signature: 'list[OHLCVRow]' },
  { prefix: 'market', insert: 'market.timestamps()', signature: 'list[str]' },
  { prefix: 'market', insert: 'market.sessions()', signature: 'list[str]' },
  { prefix: 'market', insert: 'market.metadata()', signature: 'dict[str, object]' },
  { prefix: 'market', insert: 'market.percent_change(20)', signature: 'float | None' },
  { prefix: 'market', insert: 'market.week52_new_high()', signature: 'bool' },
  { prefix: 'market', insert: 'market.week52_new_low()', signature: 'bool' },
  { prefix: 'market', insert: 'market.pct_from_52w_high()', signature: 'float | None' },
  { prefix: 'market', insert: 'market.pct_from_52w_low()', signature: 'float | None' },
  { prefix: 'market', insert: 'market.benchmark_close()', signature: 'series[float]' },
  { prefix: 'market', insert: 'market.benchmark_open()', signature: 'series[float]' },
  { prefix: 'market', insert: 'market.benchmark_high()', signature: 'series[float]' },
  { prefix: 'market', insert: 'market.benchmark_low()', signature: 'series[float]' },
  { prefix: 'market', insert: 'market.benchmark_volume()', signature: 'series[float | None]' },
  { prefix: 'market', insert: 'market.benchmark_vwap()', signature: 'series[float | None]' },
  { prefix: 'market', insert: 'market.benchmark_ohlcv()', signature: 'list[OHLCVRow]' },
  { prefix: 'market', insert: 'market.benchmark_timestamps()', signature: 'list[str]' },
  { prefix: 'market', insert: 'market.benchmark_sessions()', signature: 'list[str]' },
  { prefix: 'market', insert: 'market.benchmark_metadata()', signature: 'dict[str, object]' },
  { prefix: 'market', insert: 'market.universe()', signature: 'list[InstrumentRow]' },
  { prefix: 'ta', insert: "ta.indicator('rsi', {'period': 14})", signature: 'indicator, params, output?' },
  { prefix: 'ta', insert: 'ta.sma(market.close(), 20)', signature: 'series, period' },
  { prefix: 'ta', insert: 'ta.ema(market.close(), 20)', signature: 'series, period' },
  { prefix: 'ta', insert: 'ta.rsi(market.close(), 14)', signature: 'series, period' },
  { prefix: 'stats', insert: 'stats.positive_close_streaks(dataset)', signature: 'dataset' },
  { prefix: 'stats', insert: "stats.streaks(values, 'positive')", signature: 'values, direction, inclusive?' },
  { prefix: 'stats', insert: 'stats.mean(values)', signature: 'values' },
  { prefix: 'stats', insert: 'stats.median(values)', signature: 'values' },
  { prefix: 'stats', insert: 'stats.std(values)', signature: 'values' },
  { prefix: 'stats', insert: 'stats.percentile(values, 0.9)', signature: 'values, probability' },
  { prefix: 'stats', insert: 'stats.ranks(values)', signature: 'values, descending?' },
  { prefix: 'stats', insert: "stats.rolling(values, 20, 'mean')", signature: 'values, period, function?' },
  { prefix: 'stats', insert: 'stats.correlation(left, right)', signature: 'left, right' },
  { prefix: 'stats', insert: 'stats.regression(x, y)', signature: 'x, y' },
  { prefix: 'stats', insert: 'stats.distribution(values, 8, current)', signature: 'values, bins, current?' },
  { prefix: 'research', insert: 'research.forward_returns(dataset, indices, [1, 5, 20])', signature: 'dataset, events, horizons' },
  { prefix: 'research', insert: 'research.conditional_outcomes(dataset, indices, [1, 5, 20])', signature: 'dataset, events, horizons' },
  { prefix: 'research', insert: 'research.regimes(dataset, 20, 0.05)', signature: 'dataset, lookback, threshold?' },
  { prefix: 'research', insert: 'research.historical_comparison(values, current)', signature: 'values, current?' },
  { prefix: 'research', insert: 'research.cross_sectional_rank(dataset, 20)', signature: 'dataset, lookback' },
  { prefix: 'research', insert: 'research.breadth_snapshot(dataset, 20)', signature: 'dataset, period' },
  { prefix: 'research', insert: 'research.breadth_thrust(dataset, 90)', signature: 'dataset, threshold?' },
  { prefix: 'research', insert: "research.occurrences(dataset, indices, 'event')", signature: 'dataset, indices, kind' },
  { prefix: 'output', insert: "output.scalar('name', value)", signature: 'name, value' },
  { prefix: 'output', insert: "output.boolean('name', value)", signature: 'name, bool' },
  { prefix: 'output', insert: "output.series('name', values)", signature: 'name, values' },
  { prefix: 'output', insert: "output.table('name', rows)", signature: 'name, rows' },
  { prefix: 'output', insert: "output.bar('name', labels, values)", signature: 'name, labels, values' },
  { prefix: 'output', insert: "output.histogram('name', values, 8, current)", signature: 'name, values, bins, current?' },
  { prefix: 'output', insert: "output.range('name', lower, upper, center)", signature: 'name, lower, upper, center?' },
  { prefix: 'output', insert: "output.scatter('name', x, y)", signature: 'name, x, y' },
  { prefix: 'output', insert: "output.heatmap('name', values, rows, columns)", signature: 'name, matrix, rows?, columns?' },
  { prefix: 'output', insert: "output.dashboard('name', [{'artifact': 'series'}])", signature: 'name, panels' },
  { prefix: 'output', insert: "output.events('name', events)", signature: 'name, events' },
]
const suggestions = computed(() => {
  const prefix = editorPrefix.value.toLowerCase()
  if (!prefix) return suggestionsCatalog.slice(0, 8)
  return suggestionsCatalog.filter(item => item.prefix === prefix || item.insert.toLowerCase().startsWith(prefix)).slice(0, 8)
})
const suggestionStatus = computed(() => {
  if (!showSuggestions.value || !suggestions.value.length) return ''
  const selected = suggestions.value[selectedSuggestionIndex.value]
  return `${suggestions.value.length} SDK suggestions. ${selected?.insert ?? ''} selected.`
})
function suggestionId(index: number) {
  return `${instanceId}-suggestion-${index}`
}

watch(() => props.modelValue, value => {
  if (editor.value && editor.value.value !== value) editor.value.value = value
})

function updateValue(value: string) {
  emit('update:modelValue', value)
  updateSuggestions()
}
function updateSuggestions() {
  const target = editor.value
  if (!target) return
  const before = target.value.slice(0, target.selectionStart)
  const match = before.match(/([A-Za-z_]+(?:\.[A-Za-z_]*)?)$/)
  const nextPrefix = match?.[1] ?? ''
  if (nextPrefix !== editorPrefix.value) selectedSuggestionIndex.value = 0
  editorPrefix.value = nextPrefix
  // The handler is only bound to editor focus/input/key events. Do not rely on
  // document.activeElement here: detached pop-outs and component tests can have
  // a different document focus owner while the editor is still interactive.
  showSuggestions.value = true
}
function handleKeydown(event: KeyboardEvent) {
  if (!showSuggestions.value || !suggestions.value.length) return
  if (event.key === 'ArrowDown') {
    event.preventDefault()
    selectedSuggestionIndex.value = (selectedSuggestionIndex.value + 1) % suggestions.value.length
  } else if (event.key === 'ArrowUp') {
    event.preventDefault()
    selectedSuggestionIndex.value = (selectedSuggestionIndex.value - 1 + suggestions.value.length) % suggestions.value.length
  } else if (event.key === 'Enter' || event.key === 'Tab') {
    event.preventDefault()
    insertSuggestion(suggestions.value[selectedSuggestionIndex.value].insert)
  } else if (event.key === 'Escape') {
    event.preventDefault()
    showSuggestions.value = false
  }
}
function hideSuggestions() {
  window.setTimeout(() => { showSuggestions.value = false }, 0)
}
function dismissOnOutsidePointer(event: PointerEvent) {
  const target = event.target
  if (target instanceof Node && !root.value?.contains(target)) showSuggestions.value = false
}
function insertSuggestion(insert: string) {
  const target = editor.value
  if (!target) return
  const before = target.value.slice(0, target.selectionStart)
  const after = target.value.slice(target.selectionEnd)
  const match = before.match(/([A-Za-z_]+(?:\.[A-Za-z_]*)?)$/)
  const start = match ? before.length - match[1].length : before.length
  const value = `${before.slice(0, start)}${insert}${after}`
  emit('update:modelValue', value)
  showSuggestions.value = false
  void nextTick(() => {
    target.focus()
    const position = start + insert.length
    target.setSelectionRange(position, position)
  })
}
function normalize() {
  const normalized = props.modelValue.replace(/\r\n?/g, '\n').split('\n').map(line => line.replace(/[ \t]+$/g, '')).join('\n').replace(/^\n+|\n+$/g, '')
  emit('update:modelValue', normalized ? `${normalized}\n` : '')
}

onMounted(() => document.addEventListener('pointerdown', dismissOnOutsidePointer, true))
onBeforeUnmount(() => document.removeEventListener('pointerdown', dismissOnOutsidePointer, true))
</script>

<style scoped>
.python-source-editor { position:relative; display:grid; gap:3px; min-width:0; }
.python-source-editor__toolbar { display:flex; align-items:center; justify-content:space-between; color:#8195a3; font-size:9px; }
.python-source-editor__toolbar button { border:1px solid #3a4954; background:#172027; color:#dce6ed; padding:2px 5px; font:inherit; cursor:pointer; }
.python-source-editor textarea { width:100%; resize:vertical; box-sizing:border-box; border:1px solid #3a4954; background:#172027; color:#dce6ed; padding:4px 5px; font:10px/1.4 ui-monospace,SFMono-Regular,Menlo,monospace; }
.python-source-editor__suggestions { position:static; z-index:8; display:grid; max-height:120px; overflow:auto; border:1px solid #486274; background:#10171d; box-shadow:0 4px 12px #0008; }
.python-source-editor__suggestions button { display:grid; grid-template-columns:minmax(0,1fr) auto; gap:8px; align-items:baseline; width:100%; border:0; border-bottom:1px solid #283640; background:transparent; color:#dce6ed; padding:4px 6px; text-align:left; font:inherit; cursor:pointer; }
.python-source-editor__suggestions button:hover,.python-source-editor__suggestions button:focus,.python-source-editor__suggestion--selected { background:#1d3543; }
.python-source-editor__suggestions code { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; color:#9ed0ed; }
.python-source-editor__suggestions small { color:#8195a3; white-space:nowrap; }
.python-source-editor__sr-status { position:absolute; width:1px; height:1px; margin:-1px; padding:0; overflow:hidden; clip:rect(0 0 0 0); white-space:nowrap; border:0; }
</style>
