<template>
  <div class="options-widget">
    <OptionsChainPanel
      :symbol="symbol"
      title="Options Chain"
      compact
      @open-symbol="openSymbol"
    />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import OptionsChainPanel from '@/components/options/OptionsChainPanel.vue'

const props = defineProps<{
  config: Record<string, any>
  overrideSymbol?: string
}>()

const router = useRouter()
const symbol = computed(() =>
  (props.overrideSymbol?.trim() || String(props.config.symbol ?? '').trim()).toUpperCase()
)

function openSymbol(nextSymbol: string) {
  router.push(`/chart/${encodeURIComponent(nextSymbol)}`)
}
</script>

<style scoped>
.options-widget {
  height: 100%;
  min-height: 0;
}
</style>
