<template>
  <div class="gex-widget">
    <OptionsExposurePanel
      :symbol="symbol"
      title="GEX / DEX Ladder"
    />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import OptionsExposurePanel from '@/components/options/exposure/OptionsExposurePanel.vue'

const props = defineProps<{
  config: Record<string, any>
  overrideSymbol?: string
}>()

const symbol = computed(() =>
  (props.overrideSymbol?.trim() || String(props.config.symbol ?? '').trim()).toUpperCase()
)
</script>

<style scoped>
.gex-widget {
  height: 100%;
  min-height: 0;
}
</style>
