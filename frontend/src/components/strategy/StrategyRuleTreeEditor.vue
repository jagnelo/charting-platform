<template>
  <div class="rule-node" :class="[`rule-node--${node.kind}`, `depth-${depth}`]">
    <template v-if="node.kind === 'condition'">
      <div class="condition-card">
        <div class="condition-head">
          <strong>{{ label || 'Condition' }}</strong>
          <button
            v-if="canRemove"
            class="icon-btn"
            type="button"
            @click="$emit('remove', node.id)"
          >
            Remove
          </button>
        </div>

        <div class="condition-grid">
          <label class="field">
            <span class="field-label">Left side</span>
            <select v-model="node.leftKind" class="form-select">
              <option v-for="option in leftSideOptions" :key="option.value" :value="option.value">
                {{ option.label }}
              </option>
            </select>
          </label>
          <label v-if="needsPeriod(node.leftKind)" class="field">
            <span class="field-label">Period</span>
            <input v-model.number="node.leftPeriod" type="number" min="1" class="form-input" />
          </label>
          <label class="field">
            <span class="field-label">Relationship</span>
            <select v-model="node.operator" class="form-select">
              <option v-for="option in operatorOptions" :key="option.value" :value="option.value">
                {{ option.label }}
              </option>
            </select>
          </label>
          <label class="field">
            <span class="field-label">Right side</span>
            <select v-model="node.rightKind" class="form-select">
              <option v-for="option in rightSideOptions" :key="option.value" :value="option.value">
                {{ option.label }}
              </option>
            </select>
          </label>
          <label v-if="node.rightKind === 'value'" class="field">
            <span class="field-label">Value</span>
            <input v-model.number="node.rightValue" type="number" step="0.1" class="form-input" />
          </label>
          <label v-else-if="needsPeriod(node.rightKind)" class="field">
            <span class="field-label">Period</span>
            <input v-model.number="node.rightPeriod" type="number" min="1" class="form-input" />
          </label>
        </div>
      </div>
    </template>

    <template v-else-if="node.kind === 'not'">
      <div class="group-card">
        <div class="group-head">
          <div>
            <strong>NOT group</strong>
            <p>Invert the result of the child rule or group.</p>
          </div>
          <div class="group-actions">
            <button class="btn-secondary btn-quiet" type="button" @click="$emit('add-condition', node.id)">
              + Rule
            </button>
            <button class="btn-secondary btn-quiet" type="button" @click="$emit('add-group', node.id, 'all')">
              + All group
            </button>
            <button class="btn-secondary btn-quiet" type="button" @click="$emit('add-group', node.id, 'any')">
              + Any group
            </button>
            <button
              v-if="canRemove"
              class="icon-btn"
              type="button"
              @click="$emit('remove', node.id)"
            >
              Remove
            </button>
          </div>
        </div>

        <div class="group-body">
          <StrategyRuleTreeEditor
            v-if="node.condition"
            :node="node.condition"
            :depth="depth + 1"
            :can-remove="true"
            :left-side-options="leftSideOptions"
            :right-side-options="rightSideOptions"
            :operator-options="operatorOptions"
            label="Negated rule"
            @remove="forwardRemove"
            @add-condition="forwardAddCondition"
            @add-group="forwardAddGroup"
          />
          <div v-else class="empty-inline">Add a child rule to define what this NOT group inverts.</div>
        </div>
      </div>
    </template>

    <template v-else>
      <div class="group-card">
        <div class="group-head">
          <div>
            <strong>{{ depth === 0 ? 'Root logic' : 'Rule group' }}</strong>
            <p>{{ node.type === 'all' ? 'Every child must match.' : 'Any child may match.' }}</p>
          </div>
          <div class="group-actions">
            <label class="field field--inline">
              <span class="field-label">Combine with</span>
              <select v-model="node.type" class="form-select">
                <option value="all">All</option>
                <option value="any">Any</option>
              </select>
            </label>
            <button class="btn-secondary btn-quiet" type="button" @click="$emit('add-condition', node.id)">
              + Rule
            </button>
            <button class="btn-secondary btn-quiet" type="button" @click="$emit('add-group', node.id, 'all')">
              + All group
            </button>
            <button class="btn-secondary btn-quiet" type="button" @click="$emit('add-group', node.id, 'any')">
              + Any group
            </button>
            <button class="btn-secondary btn-quiet" type="button" @click="$emit('add-group', node.id, 'not')">
              + NOT group
            </button>
            <button
              v-if="canRemove"
              class="icon-btn"
              type="button"
              @click="$emit('remove', node.id)"
            >
              Remove
            </button>
          </div>
        </div>

        <div class="group-body">
          <StrategyRuleTreeEditor
            v-for="(child, index) in node.children"
            :key="child.id"
            :node="child"
            :depth="depth + 1"
            :can-remove="true"
            :left-side-options="leftSideOptions"
            :right-side-options="rightSideOptions"
            :operator-options="operatorOptions"
            :label="child.kind === 'condition' ? `Condition ${index + 1}` : undefined"
            @remove="forwardRemove"
            @add-condition="forwardAddCondition"
            @add-group="forwardAddGroup"
          />
          <div v-if="!node.children.length" class="empty-inline">Add rules or groups to define this branch.</div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
defineOptions({ name: 'StrategyRuleTreeEditor' })

type RuleSideKind = 'close' | 'sma' | 'ema' | 'rsi'
type RuleOperator = 'gt' | 'gte' | 'lt' | 'lte' | 'crosses_above' | 'crosses_below'

interface BuilderConditionNode {
  id: string
  kind: 'condition'
  leftKind: RuleSideKind
  leftPeriod: number
  operator: RuleOperator
  rightKind: 'value' | RuleSideKind
  rightPeriod: number
  rightValue: number
}

interface BuilderGroupNode {
  id: string
  kind: 'group'
  type: 'all' | 'any'
  children: BuilderRuleNode[]
}

interface BuilderNotNode {
  id: string
  kind: 'not'
  condition: BuilderRuleNode | null
}

type BuilderRuleNode = BuilderConditionNode | BuilderGroupNode | BuilderNotNode

defineProps<{
  node: BuilderRuleNode
  depth: number
  canRemove: boolean
  leftSideOptions: Array<{ value: string; label: string }>
  rightSideOptions: Array<{ value: string; label: string }>
  operatorOptions: Array<{ value: string; label: string }>
  label?: string
}>()

const emit = defineEmits<{
  remove: [nodeId: string]
  'add-condition': [nodeId: string]
  'add-group': [nodeId: string, type: 'all' | 'any' | 'not']
}>()

function needsPeriod(kind: 'value' | RuleSideKind) {
  return kind === 'sma' || kind === 'ema' || kind === 'rsi'
}

function forwardRemove(nodeId: string) {
  emit('remove', nodeId)
}

function forwardAddCondition(nodeId: string) {
  emit('add-condition', nodeId)
}

function forwardAddGroup(nodeId: string, type: 'all' | 'any' | 'not') {
  emit('add-group', nodeId, type)
}
</script>

<style scoped>
.rule-node {
  min-width: 0;
}

.group-card,
.condition-card {
  border: 1px solid #1c1c1c;
  border-radius: 14px;
  background: #0d0d0d;
  padding: 12px;
}

.group-card {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.group-head,
.condition-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.group-head p {
  margin: 4px 0 0;
  color: #818181;
  font-size: 0.82rem;
}

.group-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.group-body {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.condition-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 10px;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
}

.field--inline {
  min-width: 118px;
}

.field-label {
  color: #9a9a9a;
  font-size: 0.78rem;
}

.form-select,
.form-input {
  width: 100%;
}

.btn-quiet {
  padding: 7px 10px;
}

.icon-btn {
  border: 1px solid #272727;
  background: #111;
  color: #c9c9c9;
  border-radius: 10px;
  padding: 7px 10px;
  cursor: pointer;
}

.empty-inline {
  color: #727272;
  font-size: 0.84rem;
}
</style>
