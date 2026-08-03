<template>
  <section class="condition-group" :class="{ 'condition-group--nested': canRemove }">
    <header>
      <span>{{ canRemove ? 'Condition group' : 'Technical conditions' }}</span>
      <select v-model="group.operator" aria-label="Condition group operator">
        <option value="AND">Match all (AND)</option>
        <option value="OR">Match any (OR)</option>
        <option value="NOT">Exclude (NOT)</option>
      </select>
      <button v-if="canRemove" type="button" aria-label="Remove condition group" @click="emit('remove')">×</button>
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
.condition-group { display: grid; gap: 4px; padding: 5px; border: 1px solid #3d5360; background: #172027; }
.condition-group--nested { border-color: #34434e; background: #141a1f; }
.condition-group header, .condition-group footer { display: flex; align-items: center; gap: 4px; }
.condition-group header span { color: #a9bbc5; }
.condition-group header select { margin-left: auto; }
.condition-group header button { padding: 0 5px; }
.condition-group__children { display: grid; gap: 4px; }
.condition-group footer button { padding: 2px 6px; }
</style>
