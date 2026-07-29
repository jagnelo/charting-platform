<template>
  <section class="market-gauge">
    <select v-model="selectedId" aria-label="Saved EasyScan" @change="loadGauge">
      <option value="">Select saved EasyScan</option>
      <option v-for="scan in scans" :key="scan.id" :value="String(scan.id)">{{ scan.name }}</option>
    </select>
    <p v-if="error" class="market-gauge__error">{{ error }}</p>
    <template v-else-if="gauge">
      <div class="market-gauge__reading"><b>{{ percentage }}</b><span>{{ gauge.matched_count }} matches</span></div>
      <p>{{ gauge.evaluated_count }}/{{ gauge.universe_count }} evaluated · {{ gauge.exclusions.length }} excluded</p>
      <small>{{ gauge.run_at ? `Updated ${new Date(gauge.run_at).toLocaleString()}` : gauge.exclusions[0]?.message ?? 'Run scan first.' }}</small>
    </template>
    <p v-else class="market-gauge__state">Choose a retained EasyScan result.</p>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { api } from '@/lib/api'
type Scan = { id: number; name: string }
type Gauge = { matched_count: number; evaluated_count: number; universe_count: number; percentage: number | null; run_at: string | null; exclusions: Array<{ message: string }> }
const scans = ref<Scan[]>([]); const selectedId = ref(''); const gauge = ref<Gauge | null>(null); const error = ref('')
const percentage = computed(() => gauge.value?.percentage == null ? '—' : `${(gauge.value.percentage * 100).toFixed(1)}%`)
async function loadGauge() { gauge.value = null; error.value = ''; if (!selectedId.value) return; try { gauge.value = await api.get<Gauge>(`/analysis/gauges/${selectedId.value}`) } catch (cause: any) { error.value = cause?.message ?? 'Unable to load gauge' } }
onMounted(async () => { try { scans.value = await api.get<Scan[]>('/screeners') } catch (cause: any) { error.value = cause?.message ?? 'Unable to load scans' } })
</script>

<style scoped>
.market-gauge { display: grid; align-content: start; gap: 7px; height: 100%; padding: 7px; background: #11161b; color: #9aabb6; font: 10px "Segoe UI", Arial, sans-serif; }.market-gauge select { min-width: 0; border: 1px solid #34434e; background: #172027; color: #d2dce3; font: inherit; }.market-gauge__reading { display:flex; align-items:baseline; justify-content:space-between; }.market-gauge__reading b { color:#78b9e4; font-size:24px; font-weight:500; }.market-gauge p,.market-gauge small { margin:0; }.market-gauge__error { color:#e99a9a; }.market-gauge__state { margin:0; }
</style>
