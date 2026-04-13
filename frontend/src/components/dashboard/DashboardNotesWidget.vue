<template>
  <div class="notes-widget">
    <template v-if="config.mode === 'checklist'">
      <div class="check-actions">
        <button @click="setAll(true)">Check all</button>
        <button @click="setAll(false)">Clear</button>
        <button @click="addItem">Add item</button>
      </div>
      <div class="check-list">
        <label v-for="item in items" :key="item.id" class="check-row">
          <input type="checkbox" :checked="item.done" @change="toggleItem(item.id)" />
          <input :value="item.text" placeholder="Task..." @change="renameItem(item.id, $event)" />
          <button @click="removeItem(item.id)">x</button>
        </label>
      </div>
    </template>
    <textarea
      v-else
      class="notes-area"
      :value="config.text || ''"
      placeholder="Notes..."
      @change="emitPatch({ text: inputValue($event) })"
    />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

interface CheckItem {
  id: string
  text: string
  done: boolean
}

const props = defineProps<{ config: Record<string, any> }>()
const emit = defineEmits<{ patchConfig: [patch: Record<string, any>] }>()

const items = computed<CheckItem[]>(() => Array.isArray(props.config.items) ? props.config.items : [])

function inputValue(event: Event) {
  return (event.target as HTMLInputElement | HTMLTextAreaElement).value
}

function emitPatch(patch: Record<string, any>) {
  emit('patchConfig', patch)
}

function replaceItems(next: CheckItem[]) {
  emitPatch({ items: next })
}

function addItem() {
  replaceItems([...items.value, { id: `${Date.now()}`, text: 'New item', done: false }])
}

function removeItem(id: string) {
  replaceItems(items.value.filter(item => item.id !== id))
}

function toggleItem(id: string) {
  replaceItems(items.value.map(item => item.id === id ? { ...item, done: !item.done } : item))
}

function renameItem(id: string, event: Event) {
  const text = inputValue(event)
  replaceItems(items.value.map(item => item.id === id ? { ...item, text } : item))
}

function setAll(done: boolean) {
  replaceItems(items.value.map(item => ({ ...item, done })))
}
</script>

<style scoped>
.notes-widget {
  height: 100%;
  min-height: 0;
}
.notes-area {
  width: 100%;
  height: 100%;
  resize: none;
  background: #0a0a0a;
  color: #ccc;
  border: 1px solid #222;
  border-radius: 4px;
  padding: 8px;
  font-family: inherit;
  font-size: 12px;
  line-height: 1.45;
}
.check-actions {
  display: flex;
  gap: 5px;
  margin-bottom: 7px;
}
.check-actions button,
.check-row button {
  background: #151515;
  color: #aaa;
  border: 1px solid #282828;
  border-radius: 4px;
  padding: 4px 6px;
  font-family: inherit;
  font-size: 9px;
  cursor: pointer;
}
.check-list {
  height: calc(100% - 30px);
  overflow: auto;
}
.check-row {
  display: grid;
  grid-template-columns: auto 1fr auto;
  gap: 7px;
  align-items: center;
  min-height: 30px;
  border-bottom: 1px solid #181818;
}
.check-row input[type='text'] {
  min-width: 0;
  background: transparent;
  color: #ccc;
  border: 0;
  outline: none;
  font-family: inherit;
  font-size: 11px;
}
</style>
