<template>
  <div class="alert-form">
    <h4 class="form-title">New Alert — {{ symbol }}</h4>
    <div class="form-row">
      <label>Condition</label>
      <select v-model="form.condition" class="form-select">
        <option value="crosses_above">Crosses Above</option>
        <option value="crosses_below">Crosses Below</option>
        <option value="touches">Touches</option>
      </select>
    </div>
    <div class="form-row">
      <label>Price</label>
      <input v-model.number="form.price" type="number" step="0.0001" class="form-input" placeholder="0.0000" />
    </div>
    <div class="form-row form-row-check">
      <label><input type="checkbox" v-model="form.repeat" /> Repeat (rearm after trigger)</label>
    </div>
    <div class="form-row">
      <label>Notes</label>
      <input v-model="form.notes" type="text" class="form-input" placeholder="Optional note…" />
    </div>
    <div class="form-actions">
      <button class="btn-cancel" @click="$emit('close')">Cancel</button>
      <button class="btn-create" :disabled="!isValid" @click="submit">Create Alert</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useAlertsStore } from '@/stores/alerts'

const props = defineProps<{ instrumentId: number; symbol: string }>()
const emit  = defineEmits<{ close: [] }>()

const alertsStore = useAlertsStore()

const form = ref({ condition: 'crosses_above' as const, price: 0, repeat: false, notes: '' })
const isValid = computed(() => form.value.price > 0)

async function submit() {
  await alertsStore.createAlert(
    props.instrumentId,
    form.value.condition,
    form.value.price,
    form.value.repeat,
    form.value.notes || undefined,
  )
  emit('close')
}
</script>

<style scoped>
.alert-form {
  background: #111;
  border: 1px solid #333;
  border-radius: 6px;
  padding: 16px;
  width: 280px;
  font-size: 12px;
  color: #aaa;
}

.form-title { color: #64b5f6; margin: 0 0 12px; font-size: 13px; }

.form-row {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-bottom: 10px;
}

.form-row-check { flex-direction: row; align-items: center; gap: 6px; }

.form-select, .form-input {
  background: #1a1a1a;
  border: 1px solid #333;
  color: #ccc;
  border-radius: 3px;
  padding: 5px 8px;
  font-size: 12px;
}

.form-actions {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
  margin-top: 12px;
}

.btn-cancel {
  background: none;
  border: 1px solid #444;
  color: #777;
  border-radius: 3px;
  padding: 4px 12px;
  cursor: pointer;
}

.btn-create {
  background: #1a3a5c;
  border: 1px solid #64b5f6;
  color: #64b5f6;
  border-radius: 3px;
  padding: 4px 12px;
  cursor: pointer;
}

.btn-create:disabled { opacity: 0.4; cursor: not-allowed; }
</style>
