<template>
  <section class="condition-group" :class="{ 'condition-group--nested': canRemove }">
    <header>
      <span>{{ canRemove ? 'Condition group' : 'Technical conditions' }}</span>
      <select v-model="group.operator" aria-label="Condition group operator">
        <option value="AND">Match all (AND)</option>
        <option value="OR">Match any (OR)</option>
        <option value="NOT">Exclude (NOT)</option>
      </select>
      <button v-if="canRemove" type="button" aria-label="Remove condition group" @click="emit('remove')"><WorkstationGlyph kind="delete" /></button>
    </header>
    <div class="condition-group__children">
      <template v-for="(child, index) in group.conditions" :key="index">
        <ConditionGroupEditor
          v-if="isGroup(child)"
          :model-value="childGroup(index)"
          :can-remove="true"
          @update:model-value="updateChild(index, $event)"
          @remove="removeChild(index)"
        />
        <TechnicalConditionEditor
          v-else
          :model-value="childCondition(index)"
          :can-remove="group.conditions.length > 1"
          @update:model-value="updateChild(index, $event)"
          @remove="removeChild(index)"
        />
      </template>
    </div>
    <footer>
      <button type="button" @click="addCondition">+ Condition</button>
      <button type="button" @click="addGroup">+ Group</button>
    </footer>
  </section>
</template>

<script setup lang="ts">
import TechnicalConditionEditor from '@/components/common/TechnicalConditionEditor.vue'
import { createDefaultTechnicalCondition, type TechnicalConditionDraft } from '@/lib/technicalConditions'
import WorkstationGlyph from './WorkstationGlyph.vue'

interface ConditionGroup {
  operator: 'AND' | 'OR' | 'NOT'
  conditions: ConditionNode[]
}
type ConditionNode = TechnicalConditionDraft | ConditionGroup

const props = withDefaults(defineProps<{ modelValue: ConditionGroup; canRemove?: boolean }>(), { canRemove: false })
const emit = defineEmits<{ 'update:modelValue': [value: ConditionGroup]; remove: [] }>()
const group = props.modelValue
const canRemove = props.canRemove

function isGroup(value: ConditionNode): value is ConditionGroup {
  return Boolean(value && typeof value === 'object' && 'operator' in value && 'conditions' in value)
}
function childGroup(index: number) { return group.conditions[index] as ConditionGroup }
function childCondition(index: number) { return group.conditions[index] as TechnicalConditionDraft }
function updateChild(index: number, value: ConditionNode) { group.conditions[index] = value }
function removeChild(index: number) {
  if (group.conditions.length <= 1) return
  group.conditions.splice(index, 1)
}
function addCondition() { group.conditions.push(createDefaultTechnicalCondition()) }
function addGroup() { group.conditions.push({ operator: 'AND', conditions: [createDefaultTechnicalCondition()] }) }
</script>

<style scoped>
.condition-group { display: grid; gap: 5px; min-width: 0; padding: 5px; border: 1px solid var(--tc-border); background: var(--tc-panel-bg); color: var(--tc-text); }
.condition-group--nested { border-color: var(--tc-border); background: var(--tc-window-bg); }
.condition-group header, .condition-group footer { display: flex; align-items: center; flex-wrap: wrap; gap: 4px; }
.condition-group header span { color: var(--tc-text-muted); font-size: 11px; font-weight: 600; }
.condition-group header select { margin-left: auto; }
.condition-group select,
.condition-group button { min-height: 26px; border: 1px solid var(--tc-border); border-radius: var(--tc-radius); background: var(--tc-control-bg); color: var(--tc-text); font: inherit; padding: 3px 7px; }
.condition-group header button { display: inline-flex; align-items: center; justify-content: center; padding: 2px 6px; }
.condition-group button:hover { border-color: var(--tc-border-strong); background: var(--tc-window-bg); }
.condition-group button:focus-visible,
.condition-group select:focus-visible { outline: 2px solid var(--tc-accent); outline-offset: 1px; }
.condition-group__children { display: grid; gap: 5px; min-width: 0; }
.condition-group footer button { padding: 3px 7px; }
</style>
