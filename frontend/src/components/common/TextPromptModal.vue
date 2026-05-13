<template>
  <Teleport to="body">
    <div v-if="modelValue" class="prompt-overlay" @click.self="close">
      <div class="prompt-modal" role="dialog" aria-modal="true" :aria-label="title">
        <div class="prompt-title">{{ title }}</div>
        <div v-if="message" class="prompt-message">{{ message }}</div>
        <label v-if="showInput && label" class="prompt-label">
          <span>{{ label }}</span>
          <input
            ref="inputRef"
            v-model="draft"
            class="prompt-input"
            :placeholder="placeholder"
            @keydown.enter.prevent="submit"
            @keydown.esc.prevent="close"
          />
        </label>
        <input
          v-else-if="showInput"
          ref="inputRef"
          v-model="draft"
          class="prompt-input"
          :placeholder="placeholder"
          @keydown.enter.prevent="submit"
          @keydown.esc.prevent="close"
        />
        <div v-if="error" class="prompt-error">{{ error }}</div>
        <div class="prompt-actions">
          <button class="prompt-btn" type="button" @click="close">{{ cancelLabel }}</button>
          <button
            class="prompt-btn prompt-btn--primary"
            type="button"
            :disabled="showInput && !draft.trim()"
            @click="submit"
          >
            {{ confirmLabel }}
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'

const props = withDefaults(defineProps<{
  modelValue: boolean
  title: string
  message?: string
  label?: string
  placeholder?: string
  confirmLabel?: string
  cancelLabel?: string
  initialValue?: string
  error?: string
  showInput?: boolean
}>(), {
  message: '',
  label: '',
  placeholder: '',
  confirmLabel: 'Save',
  cancelLabel: 'Cancel',
  initialValue: '',
  error: '',
  showInput: true,
})

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  submit: [value: string]
}>()

const draft = ref('')
const inputRef = ref<HTMLInputElement | null>(null)

watch(
  () => props.modelValue,
  async (open) => {
    if (!open) return
    draft.value = props.initialValue
    await nextTick()
    if (!props.showInput) return
    inputRef.value?.focus()
    inputRef.value?.select()
  },
  { immediate: true },
)

watch(
  () => props.initialValue,
  (value) => {
    if (props.modelValue) draft.value = value
  },
)

function close() {
  emit('update:modelValue', false)
}

function submit() {
  const value = draft.value.trim()
  if (props.showInput && !value) return
  emit('submit', value)
}
</script>

<style scoped>
.prompt-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.65);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 3000;
  padding: 16px;
}

.prompt-modal {
  width: min(420px, 100%);
  background: #111;
  border: 1px solid #2a2a2a;
  border-radius: 6px;
  padding: 14px;
  color: #d6d6d6;
  box-shadow: 0 16px 40px rgba(0, 0, 0, 0.45);
}

.prompt-title {
  font-size: 13px;
  font-weight: 700;
  color: #fff;
}

.prompt-message {
  margin-top: 8px;
  font-size: 12px;
  color: #9a9a9a;
  line-height: 1.45;
}

.prompt-label {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-top: 12px;
  font-size: 11px;
  color: #9a9a9a;
}

.prompt-input {
  width: 100%;
  margin-top: 12px;
  background: #0a0a0a;
  border: 1px solid #333;
  border-radius: 4px;
  color: #e0e0e0;
  padding: 8px 10px;
  font-size: 12px;
  font-family: inherit;
  outline: none;
}

.prompt-label .prompt-input {
  margin-top: 0;
}

.prompt-input:focus {
  border-color: #64b5f6;
}

.prompt-error {
  margin-top: 8px;
  font-size: 11px;
  color: #ff8a80;
}

.prompt-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 14px;
}

.prompt-btn {
  background: #1a1a1a;
  border: 1px solid #333;
  border-radius: 4px;
  color: #b9b9b9;
  font-size: 11px;
  font-family: inherit;
  padding: 6px 10px;
  cursor: pointer;
}

.prompt-btn:hover {
  border-color: #4a4a4a;
  color: #efefef;
}

.prompt-btn--primary {
  border-color: #2a4f70;
  color: #d8ecff;
}

.prompt-btn--primary:disabled {
  opacity: 0.55;
  cursor: default;
}
</style>
