<template>
  <section class="study-dashboard" :aria-label="name">
    <article v-for="panel in panels" :key="`${panel.artifact}:${panel.title}`" class="study-dashboard__panel" :style="{ '--panel-span': panel.span }">
      <header><strong>{{ panel.title }}</strong><small>{{ panel.artifact }}</small></header>
      <template v-if="target(panel)?.artifact_type === 'scalar' || target(panel)?.artifact_type === 'boolean'">
        <strong class="study-dashboard__metric">{{ formatMetric(target(panel)!) }}</strong>
      </template>
      <table v-else-if="target(panel)?.artifact_type === 'table' && tableRows(target(panel)!).length"><thead><tr><th v-for="column in tableColumns(target(panel)!)" :key="column">{{ column }}</th></tr></thead><tbody><tr v-for="(row, index) in tableRows(target(panel)!)" :key="index"><td v-for="column in tableColumns(target(panel)!)" :key="column">{{ formatCell(row[column]) }}</td></tr></tbody></table>
      <StudySeriesUPlot v-else-if="target(panel)?.artifact_type === 'series' && seriesData(target(panel)!)" :name="panel.title" :timestamps="seriesData(target(panel)!)!.timestamps" :values="seriesData(target(panel)!)!.values" />
      <StudyBarsUPlot v-else-if="target(panel)?.artifact_type === 'bar' && barData(target(panel)!)" :name="panel.title" :labels="barData(target(panel)!)!.labels" :values="barData(target(panel)!)!.values" />
      <StudyHistogramUPlot v-else-if="target(panel)?.artifact_type === 'histogram' && histogramData(target(panel)!)" :name="panel.title" :bins="histogramData(target(panel)!)!.bins" :current="histogramData(target(panel)!)!.current" />
      <StudyRangeUPlot v-else-if="target(panel)?.artifact_type === 'range' && rangeData(target(panel)!)" :name="panel.title" :timestamps="rangeData(target(panel)!)!.timestamps" :lower="rangeData(target(panel)!)!.lower" :upper="rangeData(target(panel)!)!.upper" :center="rangeData(target(panel)!)!.center" />
      <StudyScatterUPlot v-else-if="target(panel)?.artifact_type === 'scatter' && scatterData(target(panel)!)" :name="panel.title" :x="scatterData(target(panel)!)!.x" :y="scatterData(target(panel)!)!.y" />
      <StudyHeatmap v-else-if="target(panel)?.artifact_type === 'heatmap' && heatmapData(target(panel)!)" :name="panel.title" :rows="heatmapData(target(panel)!)!.rows" :columns="heatmapData(target(panel)!)!.columns" :values="heatmapData(target(panel)!)!.values" />
      <div v-else-if="target(panel)?.artifact_type === 'events'" class="study-dashboard__events"><button v-for="(event, index) in eventRows(target(panel)!)" :key="`${event.timestamp}-${index}`" type="button" @click="emit('occurrence', event)"><strong>{{ event.symbol }}</strong><span>{{ event.timestamp }}</span></button></div>
      <pre v-else>{{ target(panel) ? JSON.stringify(target(panel)!.payload.value ?? target(panel)!.payload, null, 2) : 'Referenced artifact is unavailable.' }}</pre>
    </article>
  </section>
</template>

<script setup lang="ts">
import StudyHeatmap from './StudyHeatmap.vue'
import StudyBarsUPlot from './StudyBarsUPlot.vue'
import StudyHistogramUPlot from './StudyHistogramUPlot.vue'
import StudyScatterUPlot from './StudyScatterUPlot.vue'
import StudySeriesUPlot from './StudySeriesUPlot.vue'
import StudyRangeUPlot from './StudyRangeUPlot.vue'

interface Artifact { id: number; name: string; artifact_type: string; payload: Record<string, unknown> }
interface Panel { artifact: string; title: string; span: number }
const props = defineProps<{ name: string; panels: Panel[]; artifacts: Artifact[] }>()
const emit = defineEmits<{ occurrence: [event: { symbol: string; timestamp: string; kind?: string }] }>()
type ArtifactValue = Artifact | null

function target(panel: Panel): ArtifactValue { return props.artifacts.find(artifact => artifact.name === panel.artifact) ?? null }
function formatMetric(artifact: Artifact) { return artifact.artifact_type === 'boolean' ? artifact.payload.value === true ? 'True' : artifact.payload.value === false ? 'False' : '—' : artifact.payload.value ?? '—' }
function tableRows(artifact: Artifact): Array<Record<string, unknown>> { const value = artifact.payload.value; return Array.isArray(value) && value.every(row => row && typeof row === 'object' && !Array.isArray(row)) ? value as Array<Record<string, unknown>> : [] }
function tableColumns(artifact: Artifact) { return [...new Set(tableRows(artifact).flatMap(row => Object.keys(row)))] }
function formatCell(value: unknown) { return value == null ? '—' : typeof value === 'number' ? value.toLocaleString(undefined, { maximumFractionDigits: 6 }) : String(value) }
function seriesData(artifact: Artifact): { timestamps: string[]; values: Array<number | null> } | null { const value = artifact.payload.value; if (!value || typeof value !== 'object' || Array.isArray(value)) return null; const candidate = value as { timestamps?: unknown; values?: unknown }; return Array.isArray(candidate.timestamps) && candidate.timestamps.every(item => typeof item === 'string') && Array.isArray(candidate.values) && candidate.timestamps.length === candidate.values.length && candidate.values.every(item => item == null || typeof item === 'number') ? { timestamps: candidate.timestamps, values: candidate.values } : null }
function barData(artifact: Artifact): { labels: string[]; values: number[] } | null { const value = artifact.payload.value; if (!value || typeof value !== 'object' || Array.isArray(value)) return null; const candidate = value as { labels?: unknown; values?: unknown }; return Array.isArray(candidate.labels) && candidate.labels.every(item => typeof item === 'string') && Array.isArray(candidate.values) && candidate.labels.length === candidate.values.length && candidate.values.every(item => typeof item === 'number' && Number.isFinite(item)) ? { labels: candidate.labels, values: candidate.values } : null }
function histogramData(artifact: Artifact): { bins: Array<{ start: number; end: number; count: number }>; current: number | null } | null { const value = artifact.payload.value; if (!value || typeof value !== 'object' || Array.isArray(value)) return null; const bins = (value as { bins?: unknown }).bins; if (!Array.isArray(bins)) return null; const normalized = bins.filter((bin): bin is { start: number; end: number; count: number } => Boolean(bin) && typeof bin === 'object' && Number.isFinite((bin as Record<string, unknown>).start) && Number.isFinite((bin as Record<string, unknown>).end) && Number.isFinite((bin as Record<string, unknown>).count)); const current = (value as { current?: unknown }).current; return normalized.length ? { bins: normalized, current: typeof current === 'number' && Number.isFinite(current) ? current : null } : null }
function rangeData(artifact: Artifact): { timestamps: string[]; lower: number[]; upper: number[]; center: number[] | null } | null { const value = artifact.payload.value; if (!value || typeof value !== 'object' || Array.isArray(value)) return null; const candidate = value as { timestamps?: unknown; lower?: unknown; upper?: unknown; center?: unknown }; if (!Array.isArray(candidate.timestamps) || !candidate.timestamps.every(item => typeof item === 'string') || !Array.isArray(candidate.lower) || !Array.isArray(candidate.upper) || candidate.lower.length !== candidate.upper.length || candidate.timestamps.length !== candidate.lower.length || !candidate.lower.every(item => typeof item === 'number' && Number.isFinite(item)) || !candidate.upper.every(item => typeof item === 'number' && Number.isFinite(item))) return null; const center = candidate.center == null ? null : Array.isArray(candidate.center) && candidate.center.length === candidate.lower.length && candidate.center.every(item => typeof item === 'number' && Number.isFinite(item)) ? candidate.center : null; return { timestamps: candidate.timestamps, lower: candidate.lower, upper: candidate.upper, center } }
function scatterData(artifact: Artifact): { x: number[]; y: number[] } | null { const value = artifact.payload.value; if (!value || typeof value !== 'object' || Array.isArray(value)) return null; const candidate = value as { x?: unknown; y?: unknown }; if (!Array.isArray(candidate.x) || !Array.isArray(candidate.y) || candidate.x.length !== candidate.y.length) return null; const x = candidate.x.filter((item): item is number => typeof item === 'number' && Number.isFinite(item)); const y = candidate.y.filter((item): item is number => typeof item === 'number' && Number.isFinite(item)); return x.length === candidate.x.length && y.length === candidate.y.length ? { x, y } : null }
function heatmapData(artifact: Artifact): { rows: string[]; columns: string[]; values: number[][] } | null { const value = artifact.payload.value; if (!value || typeof value !== 'object' || Array.isArray(value)) return null; const candidate = value as { rows?: unknown; columns?: unknown; values?: unknown }; if (!Array.isArray(candidate.rows) || !candidate.rows.every(item => typeof item === 'string') || !Array.isArray(candidate.columns) || !candidate.columns.every(item => typeof item === 'string') || !Array.isArray(candidate.values) || !candidate.values.every(row => Array.isArray(row) && row.every(item => typeof item === 'number' && Number.isFinite(item)))) return null; const rows = candidate.rows as string[]; const columns = candidate.columns as string[]; const values = candidate.values as number[][]; return values.length && values.length === rows.length && values.every(row => row.length === columns.length) ? { rows, columns, values } : null }
function eventRows(artifact: Artifact): Array<{ symbol: string; timestamp: string; kind?: string }> { const value = artifact.payload.value; return Array.isArray(value) ? value.filter((item): item is { symbol: string; timestamp: string; kind?: string } => Boolean(item) && typeof item === 'object' && typeof (item as Record<string, unknown>).symbol === 'string' && typeof (item as Record<string, unknown>).timestamp === 'string') : [] }
</script>

<style scoped>
.study-dashboard { display:grid; grid-template-columns:repeat(12,minmax(0,1fr)); gap:6px; min-height:0; }
.study-dashboard__panel { grid-column:span var(--panel-span); min-width:0; border:1px solid #2c3943; padding:5px; background:#141b20; overflow:auto; }
.study-dashboard__panel header { display:flex; gap:6px; align-items:baseline; margin-bottom:4px; }
.study-dashboard__panel header small { color:#8195a3; overflow:hidden; text-overflow:ellipsis; }
.study-dashboard__metric { display:block; font-size:16px; color:#eef4f7; }
.study-dashboard table { border-collapse:collapse; width:100%; font-size:10px; }
.study-dashboard th,.study-dashboard td { border:1px solid #2c3943; padding:2px 4px; text-align:left; }
.study-dashboard pre { max-height:120px; overflow:auto; white-space:pre-wrap; margin:0; }
.study-dashboard__events { display:grid; gap:2px; }
.study-dashboard__events button { display:grid; grid-template-columns:50px 1fr; border:1px solid #3a4954; background:#172027; color:#dce6ed; padding:3px; text-align:left; font:inherit; }
.study-dashboard__events span { color:#91a8b4; }
@media (max-width:700px) { .study-dashboard__panel { grid-column:span 12; } }
</style>
