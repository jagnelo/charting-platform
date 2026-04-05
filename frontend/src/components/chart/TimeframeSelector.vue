<template>
  <select
    class="tf-select"
    :value="modelValue"
    @change="$emit('update:modelValue', ($event.target as HTMLSelectElement).value as Timeframe)"
  >
    <option v-for="tf in timeframes" :key="tf.value" :value="tf.value">{{ tf.label }}</option>
  </select>
</template>

<script setup lang="ts">
import type { Timeframe } from '@/types'
defineProps<{ modelValue: Timeframe }>()
defineEmits<{ 'update:modelValue': [tf: Timeframe] }>()

const timeframes: Array<{ value: Timeframe; label: string }> = [
  { value: 'M1',  label: '1m'  },
  { value: 'M5',  label: '5m'  },
  { value: 'M15', label: '15m' },
  { value: 'M30', label: '30m' },
  { value: 'H1',  label: '1h'  },
  { value: 'H2',  label: '2h'  },
  { value: 'H4',  label: '4h'  },
  { value: 'H12', label: '12h' },
  { value: 'D1',  label: '1D'  },
  { value: 'W1',  label: '1W'  },
  { value: 'MN',  label: '1M'  },
]
</script>

<style scoped>
.tf-select {
  background: #111;
  border: 1px solid #2a2a2a;
  border-radius: 4px;
  color: #aaa;
  font-size: 12px;
  font-family: 'JetBrains Mono', monospace;
  padding: 3px 6px;
  cursor: pointer;
  outline: none;
  appearance: none;
  -webkit-appearance: none;
  padding-right: 20px;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='6' viewBox='0 0 10 6'%3E%3Cpath d='M0 0l5 6 5-6z' fill='%23555'/%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-position: right 5px center;
  min-width: 52px;
}
.tf-select:hover { border-color: #444; color: #ccc; }
.tf-select:focus { border-color: #64b5f6; }
</style>
