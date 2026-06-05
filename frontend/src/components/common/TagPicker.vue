<template>
  <div class="tag-picker" ref="rootRef">
    <div class="tag-picker-shell" @click="focusInput">
      <span
        v-for="tag in modelValue"
        :key="tag"
        class="tag-chip"
        :style="tagStyle(tag)"
        role="button"
        tabindex="0"
        :aria-label="`Remove tag ${tag}`"
        @click.stop="removeTag(tag)"
        @mousedown.stop
        @keydown.enter.prevent="removeTag(tag)"
        @keydown.space.prevent="removeTag(tag)"
      >
        <span class="tag-chip__label">{{ tag }}</span>
        <span class="tag-chip__remove" aria-hidden="true">×</span>
      </span>
      <input
        ref="inputRef"
        v-model="draft"
        class="tag-input"
        :placeholder="modelValue.length ? '' : placeholder"
        @focus="open"
        @keydown.enter.prevent="commitHighlighted"
        @keydown.escape="close"
        @keydown.backspace="removeLast"
        @keydown.arrow-down.prevent="moveDown"
        @keydown.arrow-up.prevent="moveUp"
      />
    </div>
    <div v-if="showDropdown" class="tag-dropdown">
      <button
        v-for="(option, index) in filteredOptions"
        :key="option"
        type="button"
        :class="['tag-option', { active: index === highlightIndex }]"
        @mouseenter="highlightIndex = index"
        @click="addTag(option)"
      >
        {{ option }}
      </button>
      <button
        v-if="canCreate"
        type="button"
        :class="['tag-option', 'tag-option--create', { active: highlightIndex === filteredOptions.length }]"
        @mouseenter="highlightIndex = filteredOptions.length"
        @click="addTag(normalizedDraft)"
      >
        Create “{{ normalizedDraft }}”
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'

const props = withDefaults(defineProps<{
  modelValue: string[]
  options?: string[]
  placeholder?: string
}>(), {
  options: () => [],
  placeholder: 'Add tag',
})

const emit = defineEmits<{ 'update:modelValue': [value: string[]] }>()

const draft = ref('')
const openState = ref(false)
const highlightIndex = ref(0)
const rootRef = ref<HTMLDivElement | null>(null)
const inputRef = ref<HTMLInputElement | null>(null)

const normalizedDraft = computed(() => normalizeTag(draft.value))

const filteredOptions = computed(() => {
  const used = new Set(props.modelValue.map(normalizeTag))
  const query = normalizedDraft.value
  const deduped = Array.from(new Set(props.options.map(normalizeTag).filter(Boolean)))
  return deduped
    .filter(option => !used.has(option))
    .filter(option => !query || option.includes(query))
})

const canCreate = computed(() => {
  const normalized = normalizedDraft.value
  if (!normalized) return false
  return !props.modelValue.some(tag => normalizeTag(tag) === normalized)
    && !props.options.some(option => normalizeTag(option) === normalized)
})

const showDropdown = computed(() => openState.value && (filteredOptions.value.length > 0 || canCreate.value))

function update(next: string[]) {
  emit('update:modelValue', next)
}

function addTag(raw: string) {
  const tag = normalizeTag(raw)
  if (!tag) return
  if (props.modelValue.some(existing => normalizeTag(existing) === tag)) {
    draft.value = ''
    highlightIndex.value = 0
    openState.value = true
    focusInputSoon()
    return
  }
  update([...props.modelValue, tag])
  draft.value = ''
  highlightIndex.value = 0
  openState.value = true
  focusInputSoon()
}

function removeTag(tag: string) {
  update(props.modelValue.filter(existing => existing !== tag))
}

function removeLast() {
  if (draft.value || !props.modelValue.length) return
  update(props.modelValue.slice(0, -1))
}

function commitHighlighted() {
  if (showDropdown.value) {
    if (highlightIndex.value < filteredOptions.value.length) {
      addTag(filteredOptions.value[highlightIndex.value])
      return
    }
    if (canCreate.value) {
      addTag(draft.value)
      return
    }
  }
  if (normalizedDraft.value) addTag(normalizedDraft.value)
}

function moveDown() {
  const max = filteredOptions.value.length + (canCreate.value ? 1 : 0) - 1
  highlightIndex.value = Math.min(highlightIndex.value + 1, Math.max(0, max))
}

function moveUp() {
  highlightIndex.value = Math.max(highlightIndex.value - 1, 0)
}

function open() {
  openState.value = true
}

function close() {
  openState.value = false
  draft.value = ''
  highlightIndex.value = 0
}

function focusInput() {
  inputRef.value?.focus()
}

function focusInputSoon() {
  requestAnimationFrame(() => {
    inputRef.value?.focus()
  })
}

function handleClickOutside(event: MouseEvent) {
  if (rootRef.value && !rootRef.value.contains(event.target as Node)) close()
}

onMounted(() => document.addEventListener('mousedown', handleClickOutside))
onUnmounted(() => document.removeEventListener('mousedown', handleClickOutside))

function normalizeTag(value: string) {
  return value
    .trim()
    .toLowerCase()
    .replace(/\s+/g, '-')
    .replace(/-+/g, '-')
}

function stringHash(value: string) {
  let hash = 0
  for (let index = 0; index < value.length; index += 1) {
    hash = ((hash << 5) - hash) + value.charCodeAt(index)
    hash |= 0
  }
  return Math.abs(hash)
}

function tagStyle(tag: string) {
  const hue = stringHash(tag.trim().toLowerCase() || tag) % 360
  return {
    '--tag-bg': `hsl(${hue} 42% 13%)`,
    '--tag-border': `hsl(${hue} 38% 25%)`,
    '--tag-color': `hsl(${hue} 82% 80%)`,
    '--tag-remove-color': `hsl(${hue} 75% 70%)`,
  }
}
</script>

<style scoped>
.tag-picker {
  position: relative;
}

.tag-picker-shell {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  min-height: 32px;
  padding: 5px 8px;
  border: 1px solid #2a2a2a;
  border-radius: 3px;
  background: #0b0b0b;
}

.tag-chip {
  display: inline-flex;
  align-items: center;
  flex: 0 0 auto;
  gap: 6px;
  padding: 3px 7px;
  border-radius: 999px;
  background: var(--tag-bg);
  border: 1px solid var(--tag-border);
  color: var(--tag-color);
  font-size: 10px;
  user-select: none;
  max-width: 100%;
  cursor: pointer;
}

.tag-chip__label {
  display: inline-block;
  line-height: 1;
}

.tag-chip__remove {
  color: var(--tag-remove-color);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 12px;
  height: 12px;
  line-height: 1;
  flex: 0 0 auto;
}

.tag-chip:hover,
.tag-chip:focus-visible {
  filter: brightness(1.08);
  outline: none;
}

.tag-chip:hover .tag-chip__remove,
.tag-chip:focus-visible .tag-chip__remove {
  color: #fff;
}

.tag-input {
  flex: 1 1 120px;
  min-width: 90px;
  border: none;
  background: transparent;
  color: #c8c8c8;
  font: inherit;
  font-size: 11px;
  outline: none;
  line-height: 1.2;
}

.tag-input::placeholder {
  color: #6c6c6c;
  font-size: 11px;
}

.tag-dropdown {
  position: absolute;
  left: 0;
  right: 0;
  top: calc(100% + 6px);
  display: grid;
  gap: 4px;
  padding: 8px;
  border: 1px solid #232323;
  border-radius: 4px;
  background: #0c0f13;
  z-index: 40;
}

.tag-option {
  text-align: left;
  border: 1px solid transparent;
  background: #12171d;
  color: #c8d0d8;
  border-radius: 3px;
  padding: 7px 9px;
  cursor: pointer;
  font-size: 11px;
}

.tag-option.active {
  border-color: #3f7fb4;
  color: #eef7ff;
}

.tag-option--create {
  background: #101923;
}
</style>
