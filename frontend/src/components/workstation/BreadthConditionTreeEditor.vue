<template>
  <section class="breadth-condition-tree" :class="{ 'breadth-condition-tree--nested': !root }" :aria-label="root ? 'Breadth condition tree' : `Nested breadth condition ${path}`">
    <header class="breadth-condition-tree__header">
      <strong>{{ root ? 'Nested condition tree' : 'Condition group' }}</strong>
      <template v-if="isGroupNode">
        <label>
          <span class="sr-only">Group operator {{ path }}</span>
          <select :value="node.kind" :aria-label="`Breadth group operator ${path}`" @change="setGroupKind(($event.target as HTMLSelectElement).value as GroupKind)">
            <option value="all">Match all (AND)</option>
            <option value="any">Match any (OR)</option>
            <option value="not">Exclude (NOT)</option>
          </select>
        </label>
      </template>
      <button v-if="!root" type="button" :aria-label="`Remove breadth condition ${path}`" @click="emit('remove')">Remove</button>
    </header>

    <template v-if="isGroupNode">
      <div class="breadth-condition-tree__children">
        <BreadthConditionTreeEditor
          v-for="(child, index) in conditions"
          :key="`${path}.${index}`"
          :model-value="child"
          :path="`${path}.${index + 1}`"
          :root="false"
          :python-series-assets="pythonSeriesAssets"
          :python-series-assets-loading="pythonSeriesAssetsLoading"
          @update:model-value="updateChild(index, $event)"
          @remove="removeChild(index)"
        />
      </div>
      <footer class="breadth-condition-tree__footer">
        <button type="button" @click="addLeaf">+ Condition</button>
        <button type="button" @click="addGroup">+ Group</button>
      </footer>
    </template>

    <div v-else class="breadth-condition-tree__leaf">
      <label>
        <span class="field-label">Measured condition</span>
        <select :value="leafKind" :aria-label="`Breadth condition type ${path}`" @change="setLeafKind(($event.target as HTMLSelectElement).value as BreadthLeafKind)">
          <option v-for="option in LEAF_OPTIONS" :key="option.value" :value="option.value">{{ option.label }}</option>
        </select>
      </label>

      <template v-if="leafKind === 'above_moving_average'">
        <label><span class="field-label">Period</span><input :value="numberParam('period', 200)" :aria-label="`Breadth period ${path}`" type="number" min="2" max="252" @change="setParam('period', numberValue($event, 200, 2, 252))" /></label>
        <label><span class="field-label">Average</span><select :value="stringParam('average', 'sma')" :aria-label="`Breadth average ${path}`" @change="setParam('average', ($event.target as HTMLSelectElement).value)"><option value="sma">SMA</option><option value="ema">EMA</option></select></label>
      </template>

      <template v-else-if="leafKind === 'within_52_week_high'">
        <label><span class="field-label">Direction</span><select :value="stringParam('direction', 'high')" :aria-label="`Breadth 52-week direction ${path}`" @change="setParam('direction', ($event.target as HTMLSelectElement).value)"><option value="high">Near 52-week high</option><option value="low">Near 52-week low</option></select></label>
        <label><span class="field-label">Threshold</span><input :value="numberParam('threshold', 0.01)" :aria-label="`Breadth 52-week threshold ${path}`" type="number" min="0.001" max="0.5" step="0.001" @change="setParam('threshold', numberValue($event, 0.01, 0.001, 0.5))" /></label>
        <label><span class="field-label">Lookback</span><input :value="numberParam('lookback', 252)" :aria-label="`Breadth 52-week lookback ${path}`" type="number" min="2" max="504" @change="setParam('lookback', numberValue($event, 252, 2, 504))" /></label>
      </template>

      <template v-else-if="leafKind === 'new_high_low'">
        <label><span class="field-label">Direction</span><select :value="stringParam('direction', 'high')" :aria-label="`Breadth new high low direction ${path}`" @change="setParam('direction', ($event.target as HTMLSelectElement).value)"><option value="high">New high</option><option value="low">New low</option></select></label>
        <label><span class="field-label">Lookback</span><input :value="numberParam('lookback', 20)" :aria-label="`Breadth new high low lookback ${path}`" type="number" min="2" max="252" @change="setParam('lookback', numberValue($event, 20, 2, 252))" /></label>
      </template>

      <template v-else-if="leafKind === 'prior_high_low'">
        <label><span class="field-label">Direction</span><select :value="stringParam('direction', 'high')" :aria-label="`Breadth prior high low direction ${path}`" @change="setParam('direction', ($event.target as HTMLSelectElement).value)"><option value="high">Prior high</option><option value="low">Prior low</option></select></label>
        <label><span class="field-label">Lookback</span><input :value="numberParam('lookback', 20)" :aria-label="`Breadth prior high low lookback ${path}`" type="number" min="2" max="5000" @change="setParam('lookback', numberValue($event, 20, 2, 5000))" /></label>
        <label><span class="field-label">Operator</span><select :value="stringParam('operator', 'gte')" :aria-label="`Breadth prior high low operator ${path}`" @change="setParam('operator', ($event.target as HTMLSelectElement).value)"><option value="gte">At or above</option><option value="lte">At or below</option><option value="gt">Above</option><option value="lt">Below</option><option value="eq">Equal</option></select></label>
        <label><span class="field-label">Distance</span><input :value="numberParam('threshold', 0)" :aria-label="`Breadth prior high low threshold ${path}`" type="number" step="0.001" @change="setParam('threshold', numberValue($event, 0))" /></label>
      </template>

      <template v-else-if="leafKind === 'trend'">
        <label><span class="field-label">Fast period</span><input :value="numberParam('fast_period', 20)" :aria-label="`Breadth trend fast period ${path}`" type="number" min="2" max="100" @change="setParam('fast_period', numberValue($event, 20, 2, 100))" /></label>
        <label><span class="field-label">Slow period</span><input :value="numberParam('slow_period', 50)" :aria-label="`Breadth trend slow period ${path}`" type="number" min="3" max="252" @change="setParam('slow_period', numberValue($event, 50, 3, 252))" /></label>
        <label><span class="field-label">Direction</span><select :value="stringParam('direction', 'up')" :aria-label="`Breadth trend direction ${path}`" @change="setParam('direction', ($event.target as HTMLSelectElement).value)"><option value="up">Uptrend</option><option value="down">Downtrend</option></select></label>
      </template>

      <template v-else-if="leafKind === 'rsi' || leafKind === 'volume_ratio' || leafKind === 'relative_strength'">
        <label v-if="leafKind === 'rsi'"><span class="field-label">Period</span><input :value="numberParam('period', 14)" :aria-label="`Breadth RSI period ${path}`" type="number" min="2" max="252" @change="setParam('period', numberValue($event, 14, 2, 252))" /></label>
        <label v-else-if="leafKind === 'volume_ratio'"><span class="field-label">Period</span><input :value="numberParam('period', 20)" :aria-label="`Breadth volume period ${path}`" type="number" min="2" max="252" @change="setParam('period', numberValue($event, 20, 2, 252))" /></label>
        <label v-else><span class="field-label">Lookback</span><input :value="numberParam('lookback', 20)" :aria-label="`Breadth relative strength lookback ${path}`" type="number" min="2" max="252" @change="setParam('lookback', numberValue($event, 20, 2, 252))" /></label>
        <label><span class="field-label">Operator</span><select :value="stringParam('operator', 'gte')" :aria-label="`Breadth operator ${path}`" @change="setParam('operator', ($event.target as HTMLSelectElement).value)"><option value="gte">At or above</option><option value="lte">At or below</option><option value="gt">Above</option><option value="lt">Below</option><option value="eq">Equal</option></select></label>
        <label><span class="field-label">Threshold</span><input :value="numberParam('threshold', leafKind === 'rsi' ? 50 : 1)" :aria-label="`Breadth threshold ${path}`" type="number" step="0.001" @change="setParam('threshold', numberValue($event, leafKind === 'rsi' ? 50 : 1))" /></label>
      </template>

      <template v-else-if="leafKind === 'comparison'">
        <label><span class="field-label">Field</span><select :value="stringParam('field', 'close')" :aria-label="`Breadth comparison field ${path}`" @change="setParam('field', ($event.target as HTMLSelectElement).value)"><option value="close">Close</option><option value="return">Return</option><option value="volume">Volume</option><option value="rsi">RSI</option><option value="distance_to_52w_high">Distance to 52-week high</option><option value="distance_to_52w_low">Distance to 52-week low</option><option value="relative_strength">Relative strength</option></select></label>
        <label><span class="field-label">Operator</span><select :value="stringParam('operator', 'gte')" :aria-label="`Breadth comparison operator ${path}`" @change="setParam('operator', ($event.target as HTMLSelectElement).value)"><option value="gte">At or above</option><option value="lte">At or below</option><option value="gt">Above</option><option value="lt">Below</option><option value="eq">Equal</option></select></label>
        <label><span class="field-label">Threshold</span><input :value="numberParam('threshold', 0)" :aria-label="`Breadth comparison threshold ${path}`" type="number" step="0.001" @change="setParam('threshold', numberValue($event, 0))" /></label>
      </template>

      <template v-else-if="leafKind === 'series_comparison'">
        <label><span class="field-label">Member field</span><select :value="stringParam('field', 'return')" :aria-label="`Breadth series member field ${path}`" @change="setParam('field', ($event.target as HTMLSelectElement).value)"><option value="close">Close</option><option value="return">Return</option><option value="volume">Volume</option><option value="rsi">RSI</option><option value="distance_to_52w_high">Distance to 52-week high</option><option value="distance_to_52w_low">Distance to 52-week low</option></select></label>
        <label><span class="field-label">Reference field</span><select :value="stringParam('target_field', 'return')" :aria-label="`Breadth series reference field ${path}`" @change="setParam('target_field', ($event.target as HTMLSelectElement).value)"><option value="close">Close</option><option value="return">Return</option><option value="volume">Volume</option><option value="rsi">RSI</option><option value="distance_to_52w_high">Distance to 52-week high</option><option value="distance_to_52w_low">Distance to 52-week low</option></select></label>
        <label><span class="field-label">Relation</span><select :value="stringParam('relation', 'difference')" :aria-label="`Breadth series relation ${path}`" @change="setParam('relation', ($event.target as HTMLSelectElement).value)"><option value="difference">Difference</option><option value="ratio">Ratio minus one</option></select></label>
        <label><span class="field-label">Operator</span><select :value="stringParam('operator', 'gte')" :aria-label="`Breadth series operator ${path}`" @change="setParam('operator', ($event.target as HTMLSelectElement).value)"><option value="gte">At or above</option><option value="lte">At or below</option><option value="gt">Above</option><option value="lt">Below</option><option value="eq">Equal</option></select></label>
        <label><span class="field-label">Threshold</span><input :value="numberParam('threshold', 0)" :aria-label="`Breadth series threshold ${path}`" type="number" step="0.001" @change="setParam('threshold', numberValue($event, 0))" /></label>
      </template>

      <template v-else-if="leafKind === 'event'">
        <label><span class="field-label">Event type</span><select :value="stringParam('event_type', 'any')" :aria-label="`Breadth event type ${path}`" @change="setParam('event_type', ($event.target as HTMLSelectElement).value)"><option value="any">Any event</option><option value="earnings">Earnings</option><option value="dividend">Dividend</option><option value="ex_dividend">Ex-dividend</option><option value="split">Split</option></select></label>
        <label><span class="field-label">Lookback days</span><input :value="numberParam('lookback_days', 0)" :aria-label="`Breadth event lookback days ${path}`" type="number" min="0" max="3660" @change="setParam('lookback_days', numberValue($event, 0, 0, 3660))" /></label>
        <label class="breadth-condition-tree__check"><input :checked="booleanParam('include_estimates', false)" :aria-label="`Breadth include event estimates ${path}`" type="checkbox" @change="setParam('include_estimates', ($event.target as HTMLInputElement).checked)" /> Include estimates</label>
        <label><span class="field-label">Operator</span><select :value="stringParam('operator', 'gte')" :aria-label="`Breadth event operator ${path}`" @change="setParam('operator', ($event.target as HTMLSelectElement).value)"><option value="gte">Occurred</option><option value="lt">Did not occur</option></select></label>
      </template>

      <template v-else-if="leafKind === 'python_series'">
        <label>
          <span class="field-label">Python series asset</span>
          <select
            :value="numberParam('code_version_id', 0) || ''"
            :aria-label="`Breadth Python series condition asset ${path}`"
            @change="setParam('code_version_id', numberValue($event, 0, 1))"
          >
            <option value="">Select numeric series…</option>
            <option v-for="asset in pythonSeriesAssets" :key="asset.versionId" :value="asset.versionId">{{ asset.name }}</option>
          </select>
        </label>
        <label>
          <span class="field-label">Scope</span>
          <select :value="stringParam('scope', 'member')" :aria-label="`Breadth Python series scope ${path}`" @change="setParam('scope', ($event.target as HTMLSelectElement).value)">
            <option value="member">Member value</option><option value="cross_sectional">Cross-sectional group</option>
          </select>
        </label>
        <label v-if="stringParam('scope', 'member') === 'cross_sectional'">
          <span class="field-label">Statistic</span>
          <select :value="stringParam('statistic', 'mean')" :aria-label="`Breadth Python series group statistic ${path}`" @change="setParam('statistic', ($event.target as HTMLSelectElement).value)">
            <option value="mean">Mean</option><option value="median">Median</option><option value="min">Minimum</option><option value="max">Maximum</option><option value="std">Standard deviation</option>
          </select>
        </label>
        <label>
          <span class="field-label">Operator</span>
          <select :value="stringParam('operator', 'gte')" :aria-label="`Breadth Python series operator ${path}`" @change="setParam('operator', ($event.target as HTMLSelectElement).value)">
            <option value="gte">At or above</option><option value="gt">Above</option><option value="lte">At or below</option><option value="lt">Below</option><option value="eq">Equal to</option><option value="ne">Not equal</option>
          </select>
        </label>
        <label><span class="field-label">Threshold</span><input :value="numberParam('threshold', 0)" :aria-label="`Breadth Python series threshold ${path}`" type="number" step="0.001" @change="setParam('threshold', numberValue($event, 0))" /></label>
        <small v-if="pythonSeriesAssetsLoading" role="status">Loading Python assets…</small>
        <small v-else-if="!pythonSeriesAssets.length" class="breadth-condition-tree__warning">No numeric-series condition assets available.</small>
        <small class="breadth-condition-tree__hint">Cross-sectional leaves compare each member's isolated series with the selected same-timestamp group statistic.</small>
      </template>

      <template v-else-if="leafKind === 'python_series_comparison'">
        <label>
          <span class="field-label">Left Python series</span>
          <select :value="numberParam('left_code_version_id', 0) || ''" :aria-label="`Breadth Python left series asset ${path}`" @change="setParam('left_code_version_id', numberValue($event, 0, 1))">
            <option value="">Select numeric series…</option>
            <option v-for="asset in pythonSeriesAssets" :key="`left-${asset.versionId}`" :value="asset.versionId">{{ asset.name }}</option>
          </select>
        </label>
        <label>
          <span class="field-label">Right Python series</span>
          <select :value="numberParam('right_code_version_id', 0) || ''" :aria-label="`Breadth Python right series asset ${path}`" @change="setParam('right_code_version_id', numberValue($event, 0, 1))">
            <option value="">Select numeric series…</option>
            <option v-for="asset in pythonSeriesAssets" :key="`right-${asset.versionId}`" :value="asset.versionId">{{ asset.name }}</option>
          </select>
        </label>
        <label><span class="field-label">Relation</span><select :value="stringParam('relation', 'difference')" :aria-label="`Breadth Python series relation ${path}`" @change="setParam('relation', ($event.target as HTMLSelectElement).value)"><option value="difference">Difference</option><option value="ratio">Ratio minus one</option></select></label>
        <label><span class="field-label">Operator</span><select :value="stringParam('operator', 'gte')" :aria-label="`Breadth Python comparison operator ${path}`" @change="setParam('operator', ($event.target as HTMLSelectElement).value)"><option value="gte">At or above</option><option value="gt">Above</option><option value="lte">At or below</option><option value="lt">Below</option><option value="eq">Equal to</option><option value="ne">Not equal</option></select></label>
        <label><span class="field-label">Threshold</span><input :value="numberParam('threshold', 0)" :aria-label="`Breadth Python comparison threshold ${path}`" type="number" step="0.001" @change="setParam('threshold', numberValue($event, 0))" /></label>
        <small v-if="pythonSeriesAssetsLoading" role="status">Loading Python assets…</small>
        <small v-else-if="!pythonSeriesAssets.length" class="breadth-condition-tree__warning">No numeric-series condition assets available.</small>
        <small class="breadth-condition-tree__hint">Both isolated series are evaluated on the same prepared member and timestamp; either series may use its declared benchmark dataset.</small>
      </template>

      <template v-else-if="leafKind === 'range'">
        <label><span class="field-label">Field</span><select :value="stringParam('field', 'close')" :aria-label="`Breadth range field ${path}`" @change="setParam('field', ($event.target as HTMLSelectElement).value)"><option value="close">Close</option><option value="return">Return</option><option value="volume">Volume</option><option value="distance_to_52w_high">Distance to 52-week high</option></select></label>
        <label><span class="field-label">Minimum</span><input :value="numberParam('lower', 0)" :aria-label="`Breadth range minimum ${path}`" type="number" step="0.001" @change="setParam('lower', numberValue($event, 0))" /></label>
        <label><span class="field-label">Maximum</span><input :value="numberParam('upper', 1)" :aria-label="`Breadth range maximum ${path}`" type="number" step="0.001" @change="setParam('upper', numberValue($event, 1))" /></label>
        <label class="breadth-condition-tree__check"><input :checked="booleanParam('inclusive', true)" :aria-label="`Breadth inclusive range ${path}`" type="checkbox" @change="setParam('inclusive', ($event.target as HTMLInputElement).checked)" /> Inclusive</label>
      </template>

      <template v-else-if="leafKind === 'cross_sectional_statistic'">
        <label><span class="field-label">Scope</span><select value="cross_sectional" :aria-label="`Breadth group statistic scope ${path}`" disabled><option value="cross_sectional">Cross-sectional group</option></select></label>
        <label><span class="field-label">Field</span><select :value="stringParam('field', 'close')" :aria-label="`Breadth group statistic field ${path}`" @change="setParam('field', ($event.target as HTMLSelectElement).value)"><option value="close">Close</option><option value="return">Return</option><option value="volume">Volume</option><option value="moving_average_distance">Moving-average distance</option></select></label>
        <label><span class="field-label">Statistic</span><select :value="stringParam('statistic', 'mean')" :aria-label="`Breadth group statistic function ${path}`" @change="setParam('statistic', ($event.target as HTMLSelectElement).value)"><option value="mean">Mean</option><option value="median">Median</option><option value="min">Minimum</option><option value="max">Maximum</option><option value="std">Standard deviation</option></select></label>
        <label><span class="field-label">Operator</span><select :value="stringParam('operator', 'gte')" :aria-label="`Breadth group statistic operator ${path}`" @change="setParam('operator', ($event.target as HTMLSelectElement).value)"><option value="gte">At or above</option><option value="lte">At or below</option><option value="gt">Above</option><option value="lt">Below</option><option value="eq">Equal</option></select></label>
        <label><span class="field-label">Difference</span><input :value="numberParam('threshold', 0)" :aria-label="`Breadth group statistic difference ${path}`" type="number" step="0.001" @change="setParam('threshold', numberValue($event, 0))" /></label>
      </template>

      <template v-else>
        <label><span class="field-label">Scope</span><select :value="stringParam('target_scope', 'member')" :aria-label="`Breadth percentile scope ${path}`" @change="setNodeField('target_scope', ($event.target as HTMLSelectElement).value)"><option value="member">Member rolling percentile</option><option value="cross_sectional">Cross-sectional percentile</option></select></label>
        <label><span class="field-label">Field</span><select :value="stringParam('field', 'close')" :aria-label="`Breadth percentile field ${path}`" @change="setParam('field', ($event.target as HTMLSelectElement).value)"><option value="close">Close</option><option value="return">Return</option><option value="volume">Volume</option><option value="moving_average_distance">Moving-average distance</option></select></label>
        <label><span class="field-label">Window</span><input :value="numberParam('period', 252)" :aria-label="`Breadth percentile window ${path}`" type="number" min="2" max="5000" @change="setParam('period', numberValue($event, 252, 2, 5000))" /></label>
        <label><span class="field-label">Operator</span><select :value="stringParam('operator', 'gte')" :aria-label="`Breadth percentile operator ${path}`" @change="setParam('operator', ($event.target as HTMLSelectElement).value)"><option value="gte">At or above</option><option value="lte">At or below</option><option value="gt">Above</option><option value="lt">Below</option></select></label>
        <label><span class="field-label">Percentile</span><input :value="numberParam('percentile', 0.8)" :aria-label="`Breadth percentile target ${path}`" type="number" min="0" max="1" step="0.01" @change="setParam('percentile', numberValue($event, 0.8, 0, 1))" /></label>
      </template>

      <button v-if="root" type="button" class="breadth-condition-tree__wrap" @click="wrapLeaf">Wrap in group</button>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'

defineOptions({ name: 'BreadthConditionTreeEditor' })

export type BreadthLeafKind =
  | 'above_moving_average'
  | 'within_52_week_high'
  | 'new_high_low'
  | 'prior_high_low'
  | 'trend'
  | 'rsi'
  | 'volume_ratio'
  | 'relative_strength'
  | 'series_comparison'
  | 'python_series'
  | 'python_series_comparison'
  | 'event'
  | 'comparison'
  | 'range'
  | 'percentile'
  | 'cross_sectional_statistic'
export type BreadthGroupKind = 'all' | 'any' | 'not'
type GroupKind = BreadthGroupKind
export interface BreadthConditionNode {
  kind: BreadthLeafKind | BreadthGroupKind
  target_scope?: 'member' | 'cross_sectional'
  params: Record<string, unknown>
}

const LEAF_OPTIONS: Array<{ value: BreadthLeafKind; label: string }> = [
  { value: 'above_moving_average', label: 'Above moving average' },
  { value: 'within_52_week_high', label: 'Within 52-week high/low distance' },
  { value: 'new_high_low', label: 'New high/low' },
  { value: 'prior_high_low', label: 'Prior high/low target' },
  { value: 'trend', label: 'Trend state' },
  { value: 'rsi', label: 'RSI threshold' },
  { value: 'volume_ratio', label: 'Volume ratio threshold' },
  { value: 'relative_strength', label: 'Relative strength threshold' },
  { value: 'series_comparison', label: 'Member versus reference series' },
  { value: 'python_series', label: 'Python numeric series target' },
  { value: 'python_series_comparison', label: 'Python series versus Python series' },
  { value: 'event', label: 'Event occurred in trailing window' },
  { value: 'comparison', label: 'Measured-field comparison' },
  { value: 'range', label: 'Measured-field range' },
  { value: 'percentile', label: 'Measured-field percentile' },
  { value: 'cross_sectional_statistic', label: 'Cross-sectional group statistic' },
]

const props = withDefaults(defineProps<{
  modelValue: BreadthConditionNode
  path?: string
  root?: boolean
  pythonSeriesAssets?: Array<{ versionId: number; name: string }>
  pythonSeriesAssetsLoading?: boolean
}>(), { path: '1', root: true })
const emit = defineEmits<{
  'update:modelValue': [value: BreadthConditionNode]
  remove: []
}>()

const node = computed(() => props.modelValue)
const pythonSeriesAssets = computed(() => props.pythonSeriesAssets ?? [])
const pythonSeriesAssetsLoading = computed(() => props.pythonSeriesAssetsLoading === true)
const isGroupNode = computed(() => ['all', 'any', 'not'].includes(node.value.kind))
const conditions = computed(() => Array.isArray(node.value.params?.conditions) ? node.value.params.conditions as BreadthConditionNode[] : [])
const leafKind = computed(() => (node.value.kind as BreadthLeafKind))

function cloneNode(value: BreadthConditionNode): BreadthConditionNode {
  return { ...value, params: { ...(value.params ?? {}) } }
}
function defaultLeaf(kind: BreadthLeafKind = 'above_moving_average'): BreadthConditionNode {
  const defaults: Record<BreadthLeafKind, Record<string, unknown>> = {
    above_moving_average: { period: 200, average: 'sma', comparator: 'above' },
    within_52_week_high: { lookback: 252, threshold: 0.01, direction: 'high' },
    new_high_low: { lookback: 20, direction: 'high' },
    prior_high_low: { lookback: 20, direction: 'high', operator: 'gte', threshold: 0 },
    trend: { fast_period: 20, slow_period: 50, direction: 'up' },
    rsi: { period: 14, operator: 'gte', threshold: 50 },
    volume_ratio: { period: 20, operator: 'gte', threshold: 1 },
    relative_strength: { lookback: 20, operator: 'gte', threshold: 1 },
    series_comparison: { field: 'return', target_field: 'return', relation: 'difference', operator: 'gte', threshold: 0 },
    python_series: { code_version_id: null, scope: 'member', statistic: 'mean', operator: 'gte', threshold: 0 },
    python_series_comparison: { left_code_version_id: null, right_code_version_id: null, relation: 'difference', operator: 'gte', threshold: 0 },
    event: { event_type: 'any', lookback_days: 0, include_estimates: false, operator: 'gte', threshold: 1 },
    comparison: { field: 'close', operator: 'gte', threshold: 0 },
    range: { field: 'close', lower: 0, upper: 1, inclusive: true },
    percentile: { field: 'close', period: 252, operator: 'gte', percentile: 0.8 },
    cross_sectional_statistic: { field: 'close', statistic: 'mean', operator: 'gte', threshold: 0 },
  }
  const next = { kind, params: { ...defaults[kind] } } as BreadthConditionNode
  if (kind === 'percentile') next.target_scope = 'member'
  if (kind === 'cross_sectional_statistic') next.target_scope = 'cross_sectional'
  return next
}
function defaultGroup(kind: BreadthGroupKind = 'all'): BreadthConditionNode {
  return { kind, params: { conditions: [defaultLeaf()] } }
}
function update(next: BreadthConditionNode) { emit('update:modelValue', next) }
function setGroupKind(kind: GroupKind) {
  if (!isGroupNode.value) return
  const next = cloneNode(node.value)
  next.kind = kind
  const children = conditions.value.length ? conditions.value : [defaultLeaf()]
  next.params.conditions = kind === 'not' ? [children[0]] : children
  update(next)
}
function setLeafKind(kind: BreadthLeafKind) { update(defaultLeaf(kind)) }
function setNodeField(key: string, value: unknown) {
  const next = cloneNode(node.value)
  if (key === 'target_scope') {
    const params = { ...next.params }
    delete params.target_scope
    update({ ...next, params, [key]: value as BreadthConditionNode['target_scope'] })
    return
  }
  update({ ...next, [key]: value })
}
function setParam(key: string, value: unknown) { update({ ...cloneNode(node.value), params: { ...node.value.params, [key]: value } }) }
function updateChild(index: number, value: BreadthConditionNode) {
  const next = cloneNode(node.value)
  next.params.conditions = conditions.value.map((child, childIndex) => childIndex === index ? value : child)
  update(next)
}
function removeChild(index: number) {
  if (conditions.value.length <= 1) return
  const next = cloneNode(node.value)
  next.params.conditions = conditions.value.filter((_, childIndex) => childIndex !== index)
  update(next)
}
function addLeaf() {
  const next = cloneNode(node.value)
  next.params.conditions = [...conditions.value, defaultLeaf()]
  update(next)
}
function addGroup() {
  const next = cloneNode(node.value)
  next.params.conditions = [...conditions.value, defaultGroup()]
  update(next)
}
function wrapLeaf() { update({ kind: 'all', params: { conditions: [cloneNode(node.value)] } }) }
function params() { return node.value.params ?? {} }
function stringParam(key: string, fallback: string) { const value = params()[key]; return typeof value === 'string' ? value : fallback }
function numberParam(key: string, fallback: number) { const value = Number(params()[key]); return Number.isFinite(value) ? value : fallback }
function booleanParam(key: string, fallback: boolean) { return typeof params()[key] === 'boolean' ? params()[key] as boolean : fallback }
function numberValue(event: Event, fallback: number, min?: number, max?: number) {
  const value = Number((event.target as HTMLInputElement).value)
  if (!Number.isFinite(value)) return fallback
  return Math.min(max ?? value, Math.max(min ?? value, value))
}
</script>

<style scoped>
.breadth-condition-tree { display: grid; gap: 5px; padding: 6px; border: 1px solid #3d5360; background: #172027; }
.breadth-condition-tree--nested { border-color: #34434e; background: #141a1f; }
.breadth-condition-tree__header, .breadth-condition-tree__footer { display: flex; align-items: center; gap: 5px; }
.breadth-condition-tree__header strong { color: #b9c9d1; }
.breadth-condition-tree__header label { margin-left: auto; }
.breadth-condition-tree__children { display: grid; gap: 5px; padding-left: 8px; }
.breadth-condition-tree__leaf { display: flex; flex-wrap: wrap; align-items: end; gap: 5px; }
.breadth-condition-tree__leaf label { display: grid; gap: 2px; }
.breadth-condition-tree__leaf input, .breadth-condition-tree__leaf select { min-height: 24px; }
.breadth-condition-tree__check { display: flex !important; align-items: center; gap: 4px; min-height: 24px; }
.breadth-condition-tree__wrap { margin-left: auto; }
.breadth-condition-tree button { padding: 2px 6px; }
.sr-only { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }
</style>
