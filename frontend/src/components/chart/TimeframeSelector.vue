<template>
  <div class="tf-selector">
    <button
      v-for="tf in timeframes"
      :key="tf.value"
      :class="['tf-btn', { active: modelValue === tf.value }]"
      @click="$emit('update:modelValue', tf.value)"
    >{{ tf.label }}</button>
  </div>
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
.tf-selector {
  display: flex;
  gap: 2px;
  align-items: center;
}

.tf-btn {
  padding: 3px 8px;
  border: none;
  border-radius: 3px;
  background: transparent;
  color: #777;
  cursor: pointer;
  font-size: 12px;
  font-family: 'JetBrains Mono', monospace;
  transition: all 0.1s;
}

.tf-btn:hover { background: #1e1e1e; color: #ccc; }
.tf-btn.active { background: #1a3a5c; color: #64b5f6; }
</style>
