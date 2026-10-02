<template>
  <Teleport to="body">
    <div class="indicator-settings-backdrop" @click.self="emit('cancel')">
      <section
        ref="dialogRoot"
        class="indicator-settings-dialog"
        role="dialog"
        aria-modal="true"
        :aria-label="`Indicator settings: ${displayName}`"
        @keydown="handleKeydown"
      >
        <header>
          <strong>{{ displayName }}</strong>
          <button type="button" aria-label="Close indicator settings" @click="emit('cancel')">×</button>
        </header>
        <form @submit.prevent="apply">
          <label v-for="param in parameterDefs" :key="param.key" class="indicator-settings-dialog__field">
            <span>{{ param.label }}</span>
            <select
              v-if="param.input === 'select'"
              :aria-label="param.label"
              :value="String(draft.params[param.key] ?? '')"
              @change="setSelectParam(param.key, ($event.target as HTMLSelectElement).value)"
            >
              <option v-for="option in param.options ?? []" :key="option.value" :value="option.value">{{ option.label }}</option>
            </select>
            <input
              v-else-if="param.input === 'datetime'"
              :aria-label="param.label"
              type="datetime-local"
              :value="dateTimeValue(draft.params[param.key])"
              @input="setDateTimeParam(param.key, ($event.target as HTMLInputElement).value)"
            />
            <input
              v-else
              :aria-label="param.label"
              type="number"
              step="any"
              :value="String(draft.params[param.key] ?? '')"
              @input="setNumberParam(param.key, ($event.target as HTMLInputElement).value)"
            />
          </label>

          <label class="indicator-settings-dialog__field">
            <span>Line color</span>
            <input ref="fallbackInitialControl" aria-label="Line color" type="color" v-model="draft.color" />
          </label>
          <label class="indicator-settings-dialog__field">
            <span>Line width</span>
            <input aria-label="Line width" type="number" min="0.25" max="5" step="0.25" v-model.number="draft.lineWidth" />
          </label>
          <label class="indicator-settings-dialog__field">
            <span>Timeframes</span>
            <select aria-label="Timeframe applicability" v-model="draft.timeframeMode">
              <option value="all">All timeframes</option>
              <option value="locked">Only selected timeframes</option>
            </select>
          </label>
          <fieldset v-if="draft.timeframeMode === 'locked'" class="indicator-settings-dialog__timeframes">
            <legend>Active on</legend>
            <label v-for="timeframe in timeframes" :key="timeframe">
              <input v-model="draft.lockedTimeframes" type="checkbox" :value="timeframe" />
              {{ timeframe }}
            </label>
          </fieldset>

          <p v-if="!canApply" class="indicator-settings-dialog__guidance" role="status">
            Enter valid indicator settings and select at least one timeframe when locking this plot.
          </p>
          <footer>
            <button type="button" @click="emit('cancel')">Cancel</button>
            <button type="submit" :disabled="!canApply">Apply settings</button>
          </footer>
        </form>
      </section>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from 'vue'
import { cloneDefaultIndicator, indicatorDefaultPane, INDICATOR_BY_TYPE, normalizeIndicatorParams, type IndicatorParamDef } from '@/lib/indicators/catalog'
import type { IndicatorConfig, Timeframe } from '@/types'

const props = defineProps<{ indicator: IndicatorConfig; displayName: string }>()
const emit = defineEmits<{
  cancel: []
  apply: [indicator: IndicatorConfig]
}>()

const timeframes: Timeframe[] = ['M1', 'M5', 'M15', 'M30', 'H1', 'H2', 'H4', 'H12', 'D1', 'W1', 'MN']
const parameterDefs = computed<IndicatorParamDef[]>(() => INDICATOR_BY_TYPE[props.indicator.type]?.params ?? [])
const fallbackInitialControl = ref<HTMLInputElement | null>(null)
const dialogRoot = ref<HTMLElement | null>(null)
const defaultIndicator = cloneDefaultIndicator(props.indicator.type)
const draft = ref({
  params: {
    ...normalizeIndicatorParams(props.indicator.type, defaultIndicator.params),
    ...normalizeIndicatorParams(props.indicator.type, props.indicator.params),
  },
  color: props.indicator.style.color,
  lineWidth: props.indicator.style.lineWidth ?? 0.75,
  timeframeMode: props.indicator.lockedTimeframes?.length ? 'locked' as const : 'all' as const,
  lockedTimeframes: [...(props.indicator.lockedTimeframes ?? [])],
})

const canApply = computed(() => {
  const validParams = parameterDefs.value.every(param => {
    const value = draft.value.params[param.key]
    if (param.input === 'datetime') return typeof value === 'number' && Number.isFinite(value)
    if (param.input === 'select') return (param.options ?? []).some(option => option.value === String(value ?? ''))
    return typeof value === 'number' && Number.isFinite(value)
  })
  return validParams
    && Number.isFinite(draft.value.lineWidth)
    && draft.value.lineWidth >= 0.25
    && draft.value.lineWidth <= 5
    && (draft.value.timeframeMode === 'all' || draft.value.lockedTimeframes.length > 0)
})

function setNumberParam(key: string, raw: string) {
  draft.value.params[key] = raw.trim() ? Number(raw) : null
}

function setSelectParam(key: string, value: string) {
  draft.value.params[key] = value
}

function setDateTimeParam(key: string, raw: string) {
  const timestamp = raw ? Date.parse(raw) / 1000 : Number.NaN
  draft.value.params[key] = Number.isFinite(timestamp) ? timestamp : null
}

function dateTimeValue(value: unknown) {
  const timestamp = Number(value)
  if (!Number.isFinite(timestamp)) return ''
  const date = new Date(timestamp * 1000)
  const pad = (part: number) => String(part).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`
}

function apply() {
  if (!canApply.value) return
  emit('apply', {
    ...props.indicator,
    params: { ...draft.value.params },
    style: { ...props.indicator.style, color: draft.value.color, lineWidth: Number(draft.value.lineWidth) },
    pane: props.indicator.pane ?? indicatorDefaultPane(props.indicator.type),
    lockedTimeframes: draft.value.timeframeMode === 'locked' ? [...draft.value.lockedTimeframes] : null,
  })
}

function handleKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') {
    event.preventDefault()
    event.stopPropagation()
    emit('cancel')
    return
  }
  if (event.key !== 'Tab') return
  const focusable = Array.from(dialogRoot.value?.querySelectorAll<HTMLElement>(
    'button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [tabindex]:not([tabindex="-1"])',
  ) ?? []).filter(element => !element.hidden)
  if (!focusable.length) return
  const first = focusable[0]
  const last = focusable[focusable.length - 1]
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault()
    last.focus()
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault()
    first.focus()
  }
}

onMounted(() => {
  void nextTick(() => {
    const firstControl = dialogRoot.value?.querySelector<HTMLElement>('form input:not([type="hidden"]), form select')
    const initialControl = firstControl ?? fallbackInitialControl.value
    initialControl?.focus()
  })
})
</script>

<style scoped>
.indicator-settings-backdrop{position:fixed;inset:0;z-index:240;display:grid;place-items:center;padding:12px;background:#0009}
.indicator-settings-dialog{display:grid;gap:10px;width:min(420px,calc(100vw - 24px));max-height:min(620px,calc(100vh - 24px));overflow:auto;padding:12px;border:1px solid #52636f;background:#151d23;color:#dce6ed;box-shadow:0 12px 32px #000c;font:12px "Segoe UI",Arial,sans-serif}
.indicator-settings-dialog header,.indicator-settings-dialog footer{display:flex;align-items:center;gap:8px}
.indicator-settings-dialog header button{margin-left:auto}
.indicator-settings-dialog form{display:grid;gap:9px}
.indicator-settings-dialog__field{display:grid;grid-template-columns:minmax(110px,1fr) minmax(130px,1.25fr);align-items:center;gap:12px}
.indicator-settings-dialog input,.indicator-settings-dialog select,.indicator-settings-dialog button{min-height:28px;border:1px solid #3a4954;background:#1b252d;color:#dce6ed;font:inherit}
.indicator-settings-dialog input[type=color]{width:100%;padding:2px}
.indicator-settings-dialog input[type=checkbox]{width:auto;min-height:0}
.indicator-settings-dialog__timeframes{display:flex;flex-wrap:wrap;gap:8px 14px;margin:0;padding:8px;border:1px solid #3a4954}
.indicator-settings-dialog__timeframes label{display:flex;align-items:center;gap:4px}
.indicator-settings-dialog__guidance{margin:0;color:#e2bd72}
.indicator-settings-dialog footer{justify-content:flex-end}
.indicator-settings-dialog button{padding:4px 9px;cursor:pointer}
.indicator-settings-dialog button:disabled{opacity:.5;cursor:not-allowed}
</style>
