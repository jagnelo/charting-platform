<template>
  <div class="tech-cond-card">
    <button
      v-if="canRemove"
      class="icon-btn icon-btn--danger icon-btn--remove"
      type="button"
      title="Remove condition"
      aria-label="Remove condition"
      @click="$emit('remove')"
    >
      ×
    </button>
    <div class="tech-cond-top">
      <label class="field">
        <span class="field-label">Condition type</span>
        <select v-model="condition.type" class="form-select" @change="resetType">
          <option v-for="option in typeOptions" :key="option.value" :value="option.value">
            {{ option.label }}
          </option>
        </select>
      </label>
    </div>

    <div class="tech-cond-grid">
      <template v-if="condition.type === 'indicator_threshold'">
        <label class="field">
          <span class="field-label">Indicator</span>
          <select v-model="condition.indicator" class="form-select" @change="resetSingleIndicator">
            <option v-for="indicator in indicatorOptions" :key="indicator.value" :value="indicator.value">{{ indicator.label }}</option>
          </select>
        </label>
        <template v-for="param in singleIndicatorParamDefs" :key="`single-${param.key}`">
          <label class="field">
            <span class="field-label">{{ param.label }}</span>
            <input
              v-if="indicatorParamInputKind(condition.indicator!, param.key) === 'number'"
              :value="indicatorParamValue(condition.params, param.key)"
              type="number"
              step="any"
              class="form-input"
              @input="updateIndicatorParam(condition.params!, param.key, ($event.target as HTMLInputElement).value)"
            />
            <input
              v-else-if="indicatorParamInputKind(condition.indicator!, param.key) === 'date'"
              :value="indicatorDateValue(condition.params, param.key)"
              type="date"
              class="form-input"
              @input="updateIndicatorDateParam(condition.params!, param.key, ($event.target as HTMLInputElement).value)"
            />
            <select
              v-else-if="indicatorParamInputKind(condition.indicator!, param.key) === 'select'"
              :value="String(indicatorParamValue(condition.params, param.key) ?? '')"
              class="form-select"
              @change="updateIndicatorParam(condition.params!, param.key, ($event.target as HTMLSelectElement).value)"
            >
              <option
                v-for="option in indicatorParamSelectOptions(condition.indicator!, param.key)"
                :key="option.value"
                :value="option.value"
              >
                {{ option.label }}
              </option>
            </select>
            <label v-else class="field-checkbox">
              <input
                :checked="Boolean(indicatorParamValue(condition.params, param.key))"
                type="checkbox"
                @change="updateIndicatorBooleanParam(condition.params!, param.key, ($event.target as HTMLInputElement).checked)"
              />
              <span>Enabled</span>
            </label>
          </label>
        </template>
        <label v-if="singleIndicatorOutputs.length" class="field">
          <span class="field-label">Output</span>
          <select v-model="condition.output" class="form-select">
            <option v-for="output in singleIndicatorOutputs" :key="output.value" :value="output.value">{{ output.label }}</option>
          </select>
        </label>
        <label class="field">
          <span class="field-label">Relationship</span>
          <select v-model="condition.op" class="form-select">
            <option value="lt">&lt;</option>
            <option value="lte">≤</option>
            <option value="gt">&gt;</option>
            <option value="gte">≥</option>
          </select>
        </label>
        <label class="field">
          <span class="field-label">Value</span>
          <input v-model.number="condition.value" type="number" step="0.01" class="form-input" />
        </label>
      </template>

      <template v-else-if="condition.type === 'indicator_cross'">
        <label class="field">
          <span class="field-label">Left indicator</span>
          <select v-model="condition.indicator_a!.type" class="form-select" @change="resetIndicatorRef(condition.indicator_a!)">
            <option v-for="indicator in indicatorOptions" :key="indicator.value" :value="indicator.value">{{ indicator.label }}</option>
          </select>
        </label>
        <template v-for="param in indicatorRefParamDefs(condition.indicator_a!)" :key="`left-${param.key}`">
          <label class="field">
            <span class="field-label">Left {{ param.label }}</span>
            <input
              v-if="indicatorParamInputKind(condition.indicator_a!.type, param.key) === 'number'"
              :value="indicatorParamValue(condition.indicator_a!.params, param.key)"
              type="number"
              step="any"
              class="form-input"
              @input="updateIndicatorParam(condition.indicator_a!.params, param.key, ($event.target as HTMLInputElement).value)"
            />
            <input
              v-else-if="indicatorParamInputKind(condition.indicator_a!.type, param.key) === 'date'"
              :value="indicatorDateValue(condition.indicator_a!.params, param.key)"
              type="date"
              class="form-input"
              @input="updateIndicatorDateParam(condition.indicator_a!.params, param.key, ($event.target as HTMLInputElement).value)"
            />
            <select
              v-else-if="indicatorParamInputKind(condition.indicator_a!.type, param.key) === 'select'"
              :value="String(indicatorParamValue(condition.indicator_a!.params, param.key) ?? '')"
              class="form-select"
              @change="updateIndicatorParam(condition.indicator_a!.params, param.key, ($event.target as HTMLSelectElement).value)"
            >
              <option
                v-for="option in indicatorParamSelectOptions(condition.indicator_a!.type, param.key)"
                :key="option.value"
                :value="option.value"
              >
                {{ option.label }}
              </option>
            </select>
            <label v-else class="field-checkbox">
              <input
                :checked="Boolean(indicatorParamValue(condition.indicator_a!.params, param.key))"
                type="checkbox"
                @change="updateIndicatorBooleanParam(condition.indicator_a!.params, param.key, ($event.target as HTMLInputElement).checked)"
              />
              <span>Enabled</span>
            </label>
          </label>
        </template>
        <label v-if="indicatorRefOutputs(condition.indicator_a!).length" class="field">
          <span class="field-label">Left output</span>
          <select v-model="condition.indicator_a!.output" class="form-select">
            <option v-for="output in indicatorRefOutputs(condition.indicator_a!)" :key="output.value" :value="output.value">{{ output.label }}</option>
          </select>
        </label>
        <label class="field">
          <span class="field-label">Relationship</span>
          <select v-model="condition.op" class="form-select">
            <option value="crosses_above">crosses above</option>
            <option value="crosses_below">crosses below</option>
            <option value="gt">is above</option>
            <option value="lt">is below</option>
          </select>
        </label>
        <label class="field">
          <span class="field-label">Right indicator</span>
          <select v-model="condition.indicator_b!.type" class="form-select" @change="resetIndicatorRef(condition.indicator_b!)">
            <option v-for="indicator in indicatorOptions" :key="indicator.value" :value="indicator.value">{{ indicator.label }}</option>
          </select>
        </label>
        <template v-for="param in indicatorRefParamDefs(condition.indicator_b!)" :key="`right-${param.key}`">
          <label class="field">
            <span class="field-label">Right {{ param.label }}</span>
            <input
              v-if="indicatorParamInputKind(condition.indicator_b!.type, param.key) === 'number'"
              :value="indicatorParamValue(condition.indicator_b!.params, param.key)"
              type="number"
              step="any"
              class="form-input"
              @input="updateIndicatorParam(condition.indicator_b!.params, param.key, ($event.target as HTMLInputElement).value)"
            />
            <input
              v-else-if="indicatorParamInputKind(condition.indicator_b!.type, param.key) === 'date'"
              :value="indicatorDateValue(condition.indicator_b!.params, param.key)"
              type="date"
              class="form-input"
              @input="updateIndicatorDateParam(condition.indicator_b!.params, param.key, ($event.target as HTMLInputElement).value)"
            />
            <select
              v-else-if="indicatorParamInputKind(condition.indicator_b!.type, param.key) === 'select'"
              :value="String(indicatorParamValue(condition.indicator_b!.params, param.key) ?? '')"
              class="form-select"
              @change="updateIndicatorParam(condition.indicator_b!.params, param.key, ($event.target as HTMLSelectElement).value)"
            >
              <option
                v-for="option in indicatorParamSelectOptions(condition.indicator_b!.type, param.key)"
                :key="option.value"
                :value="option.value"
              >
                {{ option.label }}
              </option>
            </select>
            <label v-else class="field-checkbox">
              <input
                :checked="Boolean(indicatorParamValue(condition.indicator_b!.params, param.key))"
                type="checkbox"
                @change="updateIndicatorBooleanParam(condition.indicator_b!.params, param.key, ($event.target as HTMLInputElement).checked)"
              />
              <span>Enabled</span>
            </label>
          </label>
        </template>
        <label v-if="indicatorRefOutputs(condition.indicator_b!).length" class="field">
          <span class="field-label">Right output</span>
          <select v-model="condition.indicator_b!.output" class="form-select">
            <option v-for="output in indicatorRefOutputs(condition.indicator_b!)" :key="output.value" :value="output.value">{{ output.label }}</option>
          </select>
        </label>
      </template>

      <template v-else-if="condition.type === 'price_indicator'">
        <label class="field">
          <span class="field-label">Price field</span>
          <select v-model="condition.field" class="form-select">
            <option value="close">Close</option>
            <option value="open">Open</option>
            <option value="high">High</option>
            <option value="low">Low</option>
          </select>
        </label>
        <label class="field">
          <span class="field-label">Relationship</span>
          <select v-model="condition.op" class="form-select">
            <option value="gt">is above</option>
            <option value="gte">is at or above</option>
            <option value="lt">is below</option>
            <option value="lte">is at or below</option>
            <option value="crosses_above">crosses above</option>
            <option value="crosses_below">crosses below</option>
          </select>
        </label>
        <label class="field">
          <span class="field-label">Indicator</span>
          <select v-model="condition.indicator" class="form-select" @change="resetSingleIndicator">
            <option v-for="indicator in indicatorOptions" :key="indicator.value" :value="indicator.value">{{ indicator.label }}</option>
          </select>
        </label>
        <template v-for="param in singleIndicatorParamDefs" :key="`price-${param.key}`">
          <label class="field">
            <span class="field-label">Indicator {{ param.label }}</span>
            <input
              v-if="indicatorParamInputKind(condition.indicator!, param.key) === 'number'"
              :value="indicatorParamValue(condition.params, param.key)"
              type="number"
              step="any"
              class="form-input"
              @input="updateIndicatorParam(condition.params!, param.key, ($event.target as HTMLInputElement).value)"
            />
            <input
              v-else-if="indicatorParamInputKind(condition.indicator!, param.key) === 'date'"
              :value="indicatorDateValue(condition.params, param.key)"
              type="date"
              class="form-input"
              @input="updateIndicatorDateParam(condition.params!, param.key, ($event.target as HTMLInputElement).value)"
            />
            <select
              v-else-if="indicatorParamInputKind(condition.indicator!, param.key) === 'select'"
              :value="String(indicatorParamValue(condition.params, param.key) ?? '')"
              class="form-select"
              @change="updateIndicatorParam(condition.params!, param.key, ($event.target as HTMLSelectElement).value)"
            >
              <option
                v-for="option in indicatorParamSelectOptions(condition.indicator!, param.key)"
                :key="option.value"
                :value="option.value"
              >
                {{ option.label }}
              </option>
            </select>
            <label v-else class="field-checkbox">
              <input
                :checked="Boolean(indicatorParamValue(condition.params, param.key))"
                type="checkbox"
                @change="updateIndicatorBooleanParam(condition.params!, param.key, ($event.target as HTMLInputElement).checked)"
              />
              <span>Enabled</span>
            </label>
          </label>
        </template>
        <label v-if="singleIndicatorOutputs.length" class="field">
          <span class="field-label">Output</span>
          <select v-model="condition.output" class="form-select">
            <option v-for="output in singleIndicatorOutputs" :key="output.value" :value="output.value">{{ output.label }}</option>
          </select>
        </label>
      </template>

      <template v-else-if="condition.type === 'price_threshold'">
        <label class="field">
          <span class="field-label">Price field</span>
          <select v-model="condition.field" class="form-select">
            <option value="close">Close</option>
            <option value="open">Open</option>
            <option value="high">High</option>
            <option value="low">Low</option>
            <option value="volume">Volume</option>
          </select>
        </label>
        <label class="field">
          <span class="field-label">Relationship</span>
          <select v-model="condition.op" class="form-select">
            <option value="gt">&gt;</option>
            <option value="lt">&lt;</option>
            <option value="gte">≥</option>
            <option value="lte">≤</option>
          </select>
        </label>
        <label class="field">
          <span class="field-label">Value</span>
          <input v-model.number="condition.value" type="number" step="0.01" class="form-input" />
        </label>
      </template>

      <template v-else-if="condition.type === 'price_change_period' || condition.type === 'performance'">
        <label class="field">
          <span class="field-label">{{ condition.type === 'performance' ? 'Calendar period' : 'Lookback period' }}</span>
          <select v-model="condition.period" class="form-select">
            <option v-for="period in periodOptions" :key="period" :value="period">{{ period }}</option>
          </select>
        </label>
        <label class="field">
          <span class="field-label">Relationship</span>
          <select v-model="condition.op" class="form-select">
            <option value="gt">&gt;</option>
            <option value="lt">&lt;</option>
            <option value="gte">≥</option>
            <option value="lte">≤</option>
          </select>
        </label>
        <label class="field">
          <span class="field-label">Value</span>
          <input v-model.number="condition.value" type="number" step="0.001" class="form-input" />
        </label>
      </template>

      <template v-else-if="condition.type === 'price_change'">
        <label class="field">
          <span class="field-label">Lookback bars</span>
          <input v-model.number="condition.lookback_bars" type="number" min="1" class="form-input" />
        </label>
        <label class="field">
          <span class="field-label">Relationship</span>
          <select v-model="condition.op" class="form-select">
            <option value="gt">&gt;</option>
            <option value="lt">&lt;</option>
            <option value="gte">≥</option>
            <option value="lte">≤</option>
          </select>
        </label>
        <label class="field">
          <span class="field-label">Value</span>
          <input v-model.number="condition.value" type="number" step="0.001" class="form-input" />
        </label>
      </template>

      <template v-else-if="condition.type === 'pct_from_52w_high' || condition.type === 'pct_from_52w_low'">
        <label class="field">
          <span class="field-label">Relationship</span>
          <select v-model="condition.op" class="form-select">
            <option value="lt">&lt;</option>
            <option value="lte">≤</option>
            <option value="gt">&gt;</option>
            <option value="gte">≥</option>
          </select>
        </label>
        <label class="field">
          <span class="field-label">Distance</span>
          <input v-model.number="condition.value" type="number" step="0.001" class="form-input" />
        </label>
      </template>

      <template v-else-if="condition.type === 'stats_filter'">
        <label class="field">
          <span class="field-label">Stat field</span>
          <select v-model="condition.field" class="form-select">
            <option v-for="field in statsFields" :key="field.value" :value="field.value">{{ field.label }}</option>
          </select>
        </label>
        <label class="field">
          <span class="field-label">Relationship</span>
          <select v-model="condition.op" class="form-select">
            <option value="gt">&gt;</option>
            <option value="lt">&lt;</option>
            <option value="gte">≥</option>
            <option value="lte">≤</option>
            <option value="eq">=</option>
          </select>
        </label>
        <label class="field">
          <span class="field-label">Value</span>
          <input v-model.number="condition.value" type="number" step="1" class="form-input" />
        </label>
      </template>

      <template v-else-if="condition.type === 'fundamental_filter'">
        <label class="field">
          <span class="field-label">Field</span>
          <select v-model="condition.field" class="form-select">
            <option v-for="field in fundamentalFields" :key="field.value" :value="field.value">{{ field.label }}</option>
          </select>
        </label>
        <label class="field">
          <span class="field-label">Relationship</span>
          <select v-model="condition.op" class="form-select">
            <option v-if="selectedFundamentalKind === 'string'" value="eq">matches</option>
            <option v-if="selectedFundamentalKind === 'string'" value="contains">contains</option>
            <option v-if="selectedFundamentalKind === 'number'" value="gt">&gt;</option>
            <option v-if="selectedFundamentalKind === 'number'" value="lt">&lt;</option>
            <option v-if="selectedFundamentalKind === 'number'" value="gte">≥</option>
            <option v-if="selectedFundamentalKind === 'number'" value="lte">≤</option>
            <option v-if="selectedFundamentalKind === 'number'" value="eq">=</option>
          </select>
        </label>
        <label class="field">
          <span class="field-label">Value</span>
          <input
            v-if="selectedFundamentalKind === 'number'"
            v-model.number="condition.value"
            type="number"
            step="1"
            class="form-input"
          />
          <input
            v-else
            v-model="condition.value"
            type="text"
            class="form-input"
          />
        </label>
      </template>

      <template v-else>
        <div class="cond-note">This condition type does not need extra parameters.</div>
      </template>
    </div>

    <div v-if="showNarrative" class="tech-cond-readout">
      <span class="tech-cond-readout__label">How this reads</span>
      <p>{{ describeTechnicalCondition(condition) }}</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

import {
  ALL_CONDITION_TYPE_OPTIONS,
  FUNDAMENTAL_FIELDS,
  getTechnicalIndicatorOutputOptions,
  getTechnicalIndicatorParamDefs,
  PERIOD_OPTIONS,
  STATS_FIELDS,
  TECHNICAL_INDICATOR_OPTIONS,
  createDefaultTechnicalIndicatorRef,
  describeTechnicalCondition,
  resetTechnicalConditionForType,
  type TechnicalConditionDraft,
  type TechnicalIndicatorParams,
  type TechnicalIndicatorRef,
  type TechnicalConditionType,
  type SupportedIndicatorType,
} from '@/lib/technicalConditions'
import { INDICATOR_BY_TYPE } from '@/lib/indicators/catalog'

const props = withDefaults(defineProps<{
  modelValue: TechnicalConditionDraft
  canRemove?: boolean
  typeOptions?: Array<{ value: TechnicalConditionType; label: string }>
  showNarrative?: boolean
}>(), {
  canRemove: true,
  typeOptions: () => ALL_CONDITION_TYPE_OPTIONS,
  showNarrative: true,
})

defineEmits<{ remove: [] }>()

const condition = props.modelValue
const indicatorOptions = TECHNICAL_INDICATOR_OPTIONS
const periodOptions = PERIOD_OPTIONS
const statsFields = STATS_FIELDS
const fundamentalFields = FUNDAMENTAL_FIELDS
const singleIndicatorParamDefs = computed(() =>
  condition.indicator ? getTechnicalIndicatorParamDefs(condition.indicator) : []
)
const singleIndicatorOutputs = computed(() =>
  condition.indicator ? getTechnicalIndicatorOutputOptions(condition.indicator) : []
)
const selectedFundamentalKind = computed(() =>
  fundamentalFields.find(field => field.value === condition.field)?.kind ?? 'string',
)

function resetType() {
  resetTechnicalConditionForType(condition, condition.type)
}

function resetSingleIndicator() {
  if (!condition.indicator) return
  const next = createDefaultTechnicalIndicatorRef(condition.indicator)
  condition.params = { ...next.params }
  condition.output = next.output
}

function resetIndicatorRef(ref: TechnicalIndicatorRef) {
  const next = createDefaultTechnicalIndicatorRef(ref.type)
  ref.params = { ...next.params }
  ref.output = next.output
}

function indicatorRefParamDefs(ref: TechnicalIndicatorRef | undefined) {
  return ref ? getTechnicalIndicatorParamDefs(ref.type) : []
}

function indicatorRefOutputs(ref: TechnicalIndicatorRef | undefined) {
  return ref ? getTechnicalIndicatorOutputOptions(ref.type) : []
}

function indicatorParamInputKind(type: SupportedIndicatorType, key: string) {
  const def = INDICATOR_BY_TYPE[type]?.params.find(item => item.key === key)
  if (def?.input === 'datetime') return 'date'
  if (def?.input === 'select') return 'select'
  const raw = INDICATOR_BY_TYPE[type]?.defaultConfig.params?.[key]
  return typeof raw === 'boolean' ? 'boolean' : 'number'
}

function indicatorParamSelectOptions(type: SupportedIndicatorType, key: string) {
  return INDICATOR_BY_TYPE[type]?.params.find(item => item.key === key)?.options ?? []
}

function indicatorParamValue(params: TechnicalIndicatorParams | undefined, key: string) {
  return params?.[key]
}

function updateIndicatorParam(
  params: TechnicalIndicatorParams,
  key: string,
  rawValue: string,
) {
  const current = params[key]
  if (typeof current === 'number') {
    const parsed = Number(rawValue)
    params[key] = Number.isFinite(parsed) ? parsed : current
    return
  }
  params[key] = rawValue
}

function updateIndicatorBooleanParam(
  params: TechnicalIndicatorParams,
  key: string,
  value: boolean,
) {
  params[key] = value
}

function indicatorDateValue(params: TechnicalIndicatorParams | undefined, key: string) {
  const raw = params?.[key]
  const seconds = typeof raw === 'number' ? raw : Number(raw)
  if (!Number.isFinite(seconds) || seconds <= 0) return ''
  return new Date(seconds * 1000).toISOString().slice(0, 10)
}

function updateIndicatorDateParam(
  params: TechnicalIndicatorParams,
  key: string,
  value: string,
) {
  if (!value) {
    params[key] = 0
    return
  }
  const seconds = Math.floor(new Date(`${value}T00:00:00Z`).getTime() / 1000)
  params[key] = Number.isFinite(seconds) ? seconds : 0
}
</script>

<style scoped>
.tech-cond-card {
  display: grid;
  gap: 12px;
  padding: 2px 0;
  position: relative;
}

.tech-cond-top {
  display: block;
  padding-right: 40px;
}

.tech-cond-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(168px, 1fr));
  gap: 10px;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
}

.field-checkbox {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 34px;
  color: #c9d1d9;
  font-size: 12px;
}

.field-label {
  color: #666;
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.form-input,
.form-select {
  width: 100%;
  min-width: 0;
  min-height: 34px;
  background: #141414;
  border: 1px solid #2a2a2a;
  color: #ccc;
  border-radius: 3px;
  padding: 7px 9px;
  font-size: 12px;
  font-family: inherit;
  box-sizing: border-box;
  transition: border-color 120ms ease, box-shadow 120ms ease, background 120ms ease, color 120ms ease;
}

.form-select {
  appearance: none;
  -webkit-appearance: none;
  -moz-appearance: none;
  padding-right: 28px;
  background-image:
    linear-gradient(45deg, transparent 50%, #777 50%),
    linear-gradient(135deg, #777 50%, transparent 50%);
  background-position:
    calc(100% - 14px) calc(50% - 1px),
    calc(100% - 9px) calc(50% - 1px);
  background-size: 5px 5px, 5px 5px;
  background-repeat: no-repeat;
}

.form-input:hover,
.form-select:hover {
  border-color: #3a3a3a;
}

.form-input:focus,
.form-select:focus {
  outline: none;
  border-color: #4e7da0;
  box-shadow: 0 0 0 1px rgba(78, 125, 160, 0.24);
}

.tech-cond-readout {
  padding: 9px 10px;
  border: 1px solid #1f252d;
  border-radius: 3px;
  background: #0d1116;
}

.tech-cond-readout__label {
  display: block;
  color: #666;
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  margin-bottom: 4px;
}

.tech-cond-readout p,
.cond-note {
  margin: 0;
  color: #c9d1d9;
  font-size: 11px;
  line-height: 1.4;
}

.icon-btn {
  border: 1px solid #333;
  background: transparent;
  color: #888;
  border-radius: 3px;
  min-width: 28px;
  min-height: 28px;
  padding: 0;
  cursor: pointer;
  font-size: 14px;
  line-height: 1;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  transition: border-color 120ms ease, color 120ms ease, background 120ms ease;
}

.icon-btn:hover {
  border-color: #585858;
  color: #d3d3d3;
  background: #151515;
}

.icon-btn--danger {
  border-color: #5a2d30;
  color: #efb1b1;
}

.icon-btn--danger:hover {
  border-color: #7b3e42;
  color: #ffd3d3;
  background: #1d1112;
}

.icon-btn--remove {
  position: absolute;
  top: 2px;
  right: 0;
  flex: 0 0 auto;
}
</style>
