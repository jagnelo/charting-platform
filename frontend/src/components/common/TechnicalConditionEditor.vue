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
          <select v-model="condition.indicator" class="form-select">
            <option v-for="indicator in indicatorTypes" :key="indicator" :value="indicator">{{ indicator.toUpperCase() }}</option>
          </select>
        </label>
        <label class="field">
          <span class="field-label">Period</span>
          <input v-model.number="condition.params!.period" type="number" min="1" class="form-input" />
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
          <select v-model="condition.indicator_a!.type" class="form-select">
            <option v-for="indicator in indicatorTypes" :key="indicator" :value="indicator">{{ indicator.toUpperCase() }}</option>
          </select>
        </label>
        <label class="field">
          <span class="field-label">Left period</span>
          <input v-model.number="condition.indicator_a!.params.period" type="number" min="1" class="form-input" />
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
          <select v-model="condition.indicator_b!.type" class="form-select">
            <option v-for="indicator in indicatorTypes" :key="indicator" :value="indicator">{{ indicator.toUpperCase() }}</option>
          </select>
        </label>
        <label class="field">
          <span class="field-label">Right period</span>
          <input v-model.number="condition.indicator_b!.params.period" type="number" min="1" class="form-input" />
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
          <select v-model="condition.indicator" class="form-select">
            <option v-for="indicator in indicatorTypes" :key="indicator" :value="indicator">{{ indicator.toUpperCase() }}</option>
          </select>
        </label>
        <label class="field">
          <span class="field-label">Indicator period</span>
          <input v-model.number="condition.params!.period" type="number" min="1" class="form-input" />
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
  PERIOD_OPTIONS,
  STATS_FIELDS,
  SUPPORTED_INDICATOR_TYPES,
  describeTechnicalCondition,
  resetTechnicalConditionForType,
  type TechnicalConditionDraft,
  type TechnicalConditionType,
} from '@/lib/technicalConditions'

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
const indicatorTypes = SUPPORTED_INDICATOR_TYPES
const periodOptions = PERIOD_OPTIONS
const statsFields = STATS_FIELDS
const fundamentalFields = FUNDAMENTAL_FIELDS
const selectedFundamentalKind = computed(() =>
  fundamentalFields.find(field => field.value === condition.field)?.kind ?? 'string',
)

function resetType() {
  resetTechnicalConditionForType(condition, condition.type)
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
