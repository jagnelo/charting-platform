<template>
  <div class="sweep-value-input">
    <input
      v-if="modelValue.mode === 'single'"
      class="sweep-value-input__control"
      :value="modelValue.single ?? ''"
      type="number"
      :inputmode="integer ? 'numeric' : 'decimal'"
      :min="min"
      :step="step"
      :placeholder="placeholder"
      @input="updateSingle"
    />

    <div v-else-if="modelValue.mode === 'list'" class="sweep-value-input__list">
      <div class="sweep-value-input__quick-add">
        <input
          v-model="pendingListValue"
          class="sweep-value-input__control"
          type="number"
          :inputmode="integer ? 'numeric' : 'decimal'"
          :min="min"
          :step="step"
          placeholder="Add value"
          aria-label="Add value to list"
          @keydown.enter.prevent="addPendingValue"
        />
        <button
          type="button"
          class="sweep-value-input__add"
          aria-label="Add list value"
          :disabled="!canAddPendingValue"
          @click="addPendingValue"
        >
          +
        </button>
      </div>
      <div class="sweep-value-input__chips" aria-label="Fixed sweep values">
        <button
          v-for="value in modelValue.list"
          :key="value"
          type="button"
          class="sweep-value-input__chip"
          :aria-label="`Remove ${formatValue(value)}`"
          @click="removeListValue(value)"
        >
          {{ formatValue(value) }}
          <span>×</span>
        </button>
        <span v-if="!modelValue.list.length" class="sweep-value-input__empty">No values</span>
      </div>
    </div>

    <div v-else class="sweep-value-input__range">
      <label class="sweep-value-input__inline-field">
        <span>From</span>
        <input
          class="sweep-value-input__control"
          :value="modelValue.range.start ?? ''"
          type="number"
          :inputmode="integer ? 'numeric' : 'decimal'"
          :min="min"
          :step="step"
          @input="event => updateRangeValue('start', event)"
        />
      </label>
      <label class="sweep-value-input__inline-field">
        <span>To</span>
        <input
          class="sweep-value-input__control"
          :value="modelValue.range.end ?? ''"
          type="number"
          :inputmode="integer ? 'numeric' : 'decimal'"
          :min="min"
          :step="step"
          @input="event => updateRangeValue('end', event)"
        />
      </label>
      <label class="sweep-value-input__inline-field">
        <span>Step</span>
        <input
          class="sweep-value-input__control"
          :value="modelValue.range.step ?? step"
          type="number"
          :inputmode="integer ? 'numeric' : 'decimal'"
          :min="step"
          :step="step"
          @input="event => updateRangeValue('step', event)"
        />
      </label>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'

type SweepMode = 'single' | 'list' | 'range'
type SweepInputNumber = number | string | '' | null

interface SweepValueDraft {
  mode: SweepMode
  single: SweepInputNumber
  list: number[]
  range: {
    start: SweepInputNumber
    end: SweepInputNumber
    step: SweepInputNumber
  }
}

const props = withDefaults(defineProps<{
  modelValue: SweepValueDraft
  min?: number
  step?: number
  integer?: boolean
  placeholder?: string
}>(), {
  min: undefined,
  step: 1,
  integer: false,
  placeholder: '',
})

const emit = defineEmits<{
  'update:modelValue': [value: SweepValueDraft]
}>()

const pendingListValue = ref('')

const canAddPendingValue = computed(() => normalizeNumber(pendingListValue.value) != null)

function cloneDraft(): SweepValueDraft {
  return {
    mode: props.modelValue.mode,
    single: props.modelValue.single,
    list: [...props.modelValue.list],
    range: { ...props.modelValue.range },
  }
}

function normalizeNumber(value: unknown): number | null {
  if (value === '' || value == null) return null
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) return null
  const normalized = props.integer ? Math.round(numeric) : numeric
  if (props.min != null && normalized < props.min) return null
  return Number(normalized.toFixed(8))
}

function updateSingle(event: Event) {
  const next = cloneDraft()
  const raw = (event.target as HTMLInputElement).value
  next.single = raw === '' ? '' : normalizeNumber(raw)
  emit('update:modelValue', next)
}

function addPendingValue() {
  const value = normalizeNumber(pendingListValue.value)
  if (value == null) return
  const next = cloneDraft()
  if (!next.list.includes(value)) {
    next.list = [...next.list, value]
  }
  pendingListValue.value = ''
  emit('update:modelValue', next)
}

function removeListValue(value: number) {
  const next = cloneDraft()
  next.list = next.list.filter(item => item !== value)
  emit('update:modelValue', next)
}

function updateRangeValue(key: keyof SweepValueDraft['range'], event: Event) {
  const next = cloneDraft()
  const raw = (event.target as HTMLInputElement).value
  next.range[key] = raw === '' ? '' : normalizeNumber(raw)
  emit('update:modelValue', next)
}

function formatValue(value: number) {
  return props.integer ? String(Math.round(value)) : Number(value.toFixed(4)).toString()
}
</script>

<style scoped>
.sweep-value-input {
  display: grid;
  gap: 8px;
}

.sweep-value-input__control {
  width: 100%;
  border: 1px solid #282828;
  border-radius: 4px;
  background: #111;
  color: #e0e0e0;
  font: inherit;
  font-size: 13px;
  min-height: 34px;
  padding: 8px 10px;
}

.sweep-value-input__control:focus {
  outline: none;
  border-color: #64b5f6;
}

.sweep-value-input__list {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  max-width: 100%;
  overflow: hidden;
}

.sweep-value-input__quick-add {
  display: grid;
  grid-template-columns: 112px 24px;
  gap: 6px;
  flex: 0 0 auto;
}

.sweep-value-input__quick-add .sweep-value-input__control {
  min-height: 26px;
  padding: 5px 8px;
  font-size: 12px;
}

.sweep-value-input__add {
  min-width: 24px;
  border: 1px solid rgba(100, 181, 246, 0.35);
  border-radius: 4px;
  background: rgba(33, 115, 191, 0.16);
  color: #9ed0ff;
  font: inherit;
  font-size: 12px;
  font-weight: 800;
  line-height: 1;
  cursor: pointer;
}

.sweep-value-input__add:disabled {
  cursor: not-allowed;
  opacity: 0.35;
}

.sweep-value-input__chips {
  display: flex;
  flex-wrap: nowrap;
  gap: 6px;
  min-height: 28px;
  min-width: 0;
  flex: 1 1 auto;
  overflow-x: auto;
  overflow-y: hidden;
  scrollbar-width: thin;
  padding-bottom: 2px;
}

.sweep-value-input__chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border: 1px solid rgba(126, 194, 255, 0.28);
  border-radius: 999px;
  background: rgba(34, 96, 154, 0.15);
  color: #c7e6ff;
  font: inherit;
  font-size: 11px;
  padding: 4px 8px;
  cursor: pointer;
  white-space: nowrap;
  flex: 0 0 auto;
}

.sweep-value-input__chip span {
  color: #9ed0ff;
}

.sweep-value-input__empty {
  color: #696969;
  font-size: 11px;
  line-height: 26px;
  white-space: nowrap;
}

.sweep-value-input__range {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
}

.sweep-value-input__inline-field {
  position: relative;
  display: block;
}

.sweep-value-input__inline-field span {
  position: absolute;
  left: 10px;
  top: 50%;
  transform: translateY(-50%);
  color: #7f7f7f;
  font-size: 9px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  pointer-events: none;
}

.sweep-value-input__inline-field .sweep-value-input__control {
  padding-left: 48px;
}
</style>
