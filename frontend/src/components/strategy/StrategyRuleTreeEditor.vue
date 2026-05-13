<template>
  <div class="rule-node" :class="[`rule-node--${node.kind}`, `depth-${depth}`]">
    <template v-if="node.kind === 'condition'">
      <div class="condition-card">
        <div class="condition-head">
          <strong>{{ label || 'Condition' }}</strong>
        </div>
        <TechnicalConditionEditor
          :model-value="node.condition"
          :can-remove="canRemove"
          :type-options="typeOptions"
          @remove="$emit('remove', node.id)"
        />
      </div>
    </template>

    <template v-else-if="node.kind === 'not'">
      <div class="group-card">
        <div class="group-head">
          <div>
            <strong>NOT group</strong>
            <p>Invert the result of the child rule or group.</p>
          </div>
          <button
            v-if="canRemove"
            class="icon-btn icon-btn--danger"
            type="button"
            @click="$emit('remove', node.id)"
          >
            Remove
          </button>
        </div>

        <div class="group-body">
          <StrategyRuleTreeEditor
            v-if="node.condition"
            :node="node.condition"
            :depth="depth + 1"
            :can-remove="true"
            :type-options="typeOptions"
            label="Negated rule"
            @remove="forwardRemove"
            @add-condition="forwardAddCondition"
            @add-group="forwardAddGroup"
          />
          <div v-else class="empty-inline">Add a child rule to define what this NOT group inverts.</div>
        </div>

        <div class="group-builder-actions">
          <div class="builder-action-row">
            <button class="builder-action" type="button" @click="$emit('add-group', node.id, 'all')">
              + All group
            </button>
            <button class="builder-action" type="button" @click="$emit('add-group', node.id, 'any')">
              + Any group
            </button>
          </div>
          <button class="builder-action builder-action--primary" type="button" @click="$emit('add-condition', node.id)">
            + Add technical condition
          </button>
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
          <div class="group-head-controls">
            <label class="field field--inline">
              <span class="field-label">Combine with</span>
              <select v-model="node.type" class="form-select">
                <option value="all">All</option>
                <option value="any">Any</option>
              </select>
            </label>
            <button
              v-if="canRemove"
              class="icon-btn icon-btn--danger"
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
            :type-options="typeOptions"
            :label="child.kind === 'condition' ? `Condition ${index + 1}` : undefined"
            @remove="forwardRemove"
            @add-condition="forwardAddCondition"
            @add-group="forwardAddGroup"
          />
          <div v-if="!node.children.length" class="empty-inline">Add rules or groups to define this branch.</div>
        </div>

        <div class="group-builder-actions">
          <div class="builder-action-row">
            <button class="builder-action" type="button" @click="$emit('add-group', node.id, 'all')">
              + All group
            </button>
            <button class="builder-action" type="button" @click="$emit('add-group', node.id, 'any')">
              + Any group
            </button>
            <button class="builder-action" type="button" @click="$emit('add-group', node.id, 'not')">
              + NOT group
            </button>
          </div>
          <button class="builder-action builder-action--primary" type="button" @click="$emit('add-condition', node.id)">
            + Add technical condition
          </button>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
defineOptions({ name: 'StrategyRuleTreeEditor' })

import TechnicalConditionEditor from '@/components/common/TechnicalConditionEditor.vue'
import type { TechnicalConditionDraft, TechnicalConditionType } from '@/lib/technicalConditions'

interface BuilderConditionNode {
  id: string
  kind: 'condition'
  condition: TechnicalConditionDraft
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
  typeOptions: Array<{ value: TechnicalConditionType; label: string }>
  label?: string
}>()

const emit = defineEmits<{
  remove: [nodeId: string]
  'add-condition': [nodeId: string]
  'add-group': [nodeId: string, type: 'all' | 'any' | 'not']
}>()

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
  border: 1px solid #1f1f1f;
  border-radius: 4px;
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

.group-head-controls {
  display: flex;
  align-items: end;
  justify-content: flex-end;
  gap: 10px;
  flex-wrap: wrap;
}

.group-head p {
  margin: 3px 0 0;
  color: #757575;
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.icon-btn {
  border: 1px solid #333;
  background: #111;
  color: #888;
  border-radius: 3px;
  padding: 5px 8px;
  cursor: pointer;
  font-size: 11px;
  transition: border-color 120ms ease, color 120ms ease, background 120ms ease;
}

.icon-btn:hover {
  border-color: #5a2d30;
  color: #efb1b1;
  background: #1d1112;
}

.icon-btn--danger {
  min-height: 32px;
}

.group-builder-actions {
  display: grid;
  gap: 10px;
}

.builder-action-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.builder-action {
  min-height: 32px;
  padding: 5px 12px;
  border-radius: 3px;
  border: 1px solid #2c2c2c;
  background: #131313;
  color: #9a9a9a;
  font-size: 11px;
  font-family: inherit;
  cursor: pointer;
  transition: border-color 120ms ease, color 120ms ease, background 120ms ease;
}

.builder-action:hover {
  border-color: #4f6a82;
  color: #d2e4f2;
  background: #111920;
}

.builder-action--primary {
  width: 100%;
  justify-content: center;
  border-style: dashed;
  background: transparent;
  color: #8c8c8c;
}

.builder-action--primary:hover {
  border-color: #4e7da0;
  color: #d2e4f2;
  background: #10171d;
}

.group-body {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.field--inline {
  min-width: 108px;
}

.field-label {
  color: #666;
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.form-select {
  width: 100%;
  min-height: 32px;
  background: #141414;
  border: 1px solid #2a2a2a;
  color: #ccc;
  border-radius: 3px;
  padding: 6px 28px 6px 9px;
  font-size: 12px;
  font-family: inherit;
  box-sizing: border-box;
  appearance: none;
  -webkit-appearance: none;
  -moz-appearance: none;
  background-image:
    linear-gradient(45deg, transparent 50%, #777 50%),
    linear-gradient(135deg, #777 50%, transparent 50%);
  background-position:
    calc(100% - 14px) calc(50% - 1px),
    calc(100% - 9px) calc(50% - 1px);
  background-size: 5px 5px, 5px 5px;
  background-repeat: no-repeat;
  transition: border-color 120ms ease, box-shadow 120ms ease;
}

.form-select:hover {
  border-color: #3a3a3a;
}

.form-select:focus {
  outline: none;
  border-color: #4e7da0;
  box-shadow: 0 0 0 1px rgba(78, 125, 160, 0.24);
}

.empty-inline {
  color: #666;
  font-size: 11px;
}

.condition-head strong,
.group-head strong {
  color: #e5e5e5;
  font-size: 12px;
}
</style>
