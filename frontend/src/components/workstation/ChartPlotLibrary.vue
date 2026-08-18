<template>
  <section class="chart-plots" aria-label="Chart plot library" @pointerdown.stop @mousedown.stop @keydown.esc="closeToTrigger">
    <button ref="toggleButton" type="button" aria-label="Chart plot library" :aria-expanded="open" aria-haspopup="menu" @click="toggleOpen" @keydown="handleTriggerKeydown">Plots {{ chartStore.indicators.length + (pythonPlots?.length ?? 0) + (scanPlots?.length ?? 0) }}</button>
    <div v-if="open" ref="menuRoot" class="chart-plots__menu" role="menu" aria-label="Chart plot library menu" :style="menuStyle" @keydown="handleMenuKeydown">
      <header><b>Chart plots</b><button type="button" aria-label="Close chart plot library" @click="closeToTrigger"><WorkstationGlyph kind="close" /></button></header>
      <select ref="firstControl" aria-label="Add indicator plot" :value="''" @change="add(($event.target as HTMLSelectElement).value)">
        <option value="" disabled>Add indicator plot…</option>
        <option v-for="item in catalog" :key="item.type" :value="item.type">{{ item.pickerLabel }}</option>
      </select>
      <label class="chart-plots__target">Copy target
        <select v-model="selectedCopyTarget" aria-label="Copy plot target">
          <option value="linked">Linked charts ({{ linkedChartCount }})</option>
          <option v-for="target in chartTargets" :key="target.instance_key" :value="target.instance_key">{{ target.title || target.instance_key }} · {{ target.tool_type }}{{ target.link_group === linkGroup ? ' · linked' : '' }}</option>
        </select>
      </label>
      <label class="chart-plots__target">Promote plot
        <select v-model="selectedPromotionIndex" aria-label="Promotion plot">
          <option value="">Select a plot…</option>
          <option v-for="(indicator, index) in chartStore.indicators" :key="`promotion-${index}`" :value="String(index)">{{ label(indicator) }}</option>
        </select>
      </label>
      <section class="chart-plots__python" aria-label="Python plot assets">
        <button type="button" :disabled="pythonLoading" @click="loadPythonAssets">{{ pythonLoading ? 'Loading…' : 'Load Python plots' }}</button>
        <select v-if="pythonAssets.length" v-model="selectedPythonVersion" aria-label="Python plot asset"><option value="">Add Python plot…</option><option v-for="asset in pythonAssets" :key="asset.versionId" :value="String(asset.versionId)">{{ asset.name }}</option></select>
        <button v-if="selectedPythonVersion" type="button" @click="addPythonPlot">Add</button>
        <small v-if="pythonStatus">{{ pythonStatus }}</small>
      </section>
      <section class="chart-plots__python chart-plots__scan" aria-label="EasyScan plot assets">
        <button type="button" :disabled="scanLoading" @click="loadScanPlots">{{ scanLoading ? 'Loading…' : 'Load EasyScan plots' }}</button>
        <select v-if="scanAssets.length" v-model="selectedScanAsset" aria-label="EasyScan plot asset">
          <option value="">Add scan plot…</option>
          <option v-for="asset in scanAssets" :key="`${asset.screenerId}:${asset.metric}`" :value="`${asset.screenerId}:${asset.metric}`">{{ asset.name }} · {{ asset.metric }}</option>
        </select>
        <button v-if="selectedScanAsset" type="button" @click="addScanPlot">Add</button>
        <small v-if="scanStatus">{{ scanStatus }}</small>
      </section>
      <div v-if="selectedPromotionIndex !== ''" class="chart-plots__promotion">
        <select v-model="promotionTarget" aria-label="Plot promotion target"><option value="condition">Condition</option><option value="scan">EasyScan</option><option value="filter">Watchlist filter</option><option value="alert">Indicator alert</option></select>
        <select v-if="promotionTarget === 'filter'" v-model="selectedFilterTarget" aria-label="Plot promotion watchlist"><option value="" disabled>Select watchlist…</option><option v-for="target in watchlistTargets" :key="target.instance_key" :value="target.instance_key">{{ target.title || target.instance_key }}</option></select>
        <select v-model="promotionOperator" aria-label="Plot promotion operator"><option value="gt">&gt;</option><option value="gte">≥</option><option value="lt">&lt;</option><option value="lte">≤</option></select>
        <input v-model.number="promotionThreshold" aria-label="Plot promotion threshold" type="number" step="any" />
        <input v-model.trim="promotionName" aria-label="Plot promotion name" placeholder="Name" />
        <button type="button" :disabled="promotionBusy || !promotionName || !Number.isFinite(promotionThreshold) || (promotionTarget === 'filter' && !selectedFilterTarget)" @click="promoteSelected">{{ promotionBusy ? 'Saving…' : 'Copy' }}</button>
      </div>
      <p v-if="promotionStatus" class="chart-plots__promotion-status" role="status" aria-live="polite" aria-atomic="true">{{ promotionStatus }}</p>
      <p>Price history <small>active</small></p>
      <p v-if="!chartStore.indicators.length && !pythonPlots?.length && !scanPlots?.length">No indicator or reusable plots.</p>
      <ol v-else><li v-for="(plot, index) in (scanPlots ?? [])" :key="scanPlotKey(plot, index)" class="chart-plots__python-item chart-plots__scan-item" :class="{ muted: plot.hidden }">
        <input :value="plot.color ?? '#4dd0e1'" :aria-label="`${plot.name} color`" type="color" @input="updateScanPlot(index, { color: ($event.target as HTMLInputElement).value })" /><span>{{ plot.name }} <small>EasyScan · {{ plot.metric }}</small></span>
        <button type="button" :aria-label="`${plot.hidden ? 'Show' : 'Hide'} ${plot.name}`" @click="toggleScanPlot(index)"><WorkstationGlyph :kind="plot.hidden ? 'hidden' : 'visible'" /></button><button type="button" :aria-label="`Move ${plot.name} up`" :disabled="index === 0" @click="moveScanPlot(index, -1)"><WorkstationGlyph kind="move-up" /></button><button type="button" :aria-label="`Move ${plot.name} down`" :disabled="index === (scanPlots?.length ?? 0) - 1" @click="moveScanPlot(index, 1)"><WorkstationGlyph kind="move-down" /></button><button type="button" :aria-label="`Duplicate ${plot.name}`" @click="duplicateScanPlot(index)"><WorkstationGlyph kind="duplicate" /></button><button type="button" :aria-label="`Copy ${plot.name} to linked charts`" :disabled="!linkedTargets" @click="copyScanPlot(index, 'linked')"><WorkstationGlyph kind="copy-linked" /></button><button type="button" :aria-label="`Copy ${plot.name} to selected chart target`" :disabled="!copyTargetAvailable" @click="copyScanPlot(index, selectedCopyTarget)"><WorkstationGlyph kind="copy" /></button><button type="button" :aria-label="`Remove ${plot.name}`" @click="removeScanPlot(index)"><WorkstationGlyph kind="delete" /></button>
      </li><li v-for="(plot, index) in (pythonPlots ?? [])" :key="pythonPlotKey(plot, index)" class="chart-plots__python-item" :class="{ muted: plot.hidden }" draggable="true" @dragstart="startPythonDrag(index, $event)" @dragend="endDrag">
        <input :value="plot.color ?? '#ffb74d'" :aria-label="`${plot.name} color`" type="color" @input="updatePythonPlot(index, { color: ($event.target as HTMLInputElement).value })" /><span>{{ plot.name }} <small>Python</small></span>
        <button type="button" :aria-label="`${plot.hidden ? 'Show' : 'Hide'} ${plot.name}`" @click="togglePythonPlot(index)"><WorkstationGlyph :kind="plot.hidden ? 'hidden' : 'visible'" /></button><button type="button" :aria-label="`Move ${plot.name} up`" :disabled="index === 0" @click="movePythonPlot(index, -1)"><WorkstationGlyph kind="move-up" /></button><button type="button" :aria-label="`Move ${plot.name} down`" :disabled="index === (pythonPlots?.length ?? 0) - 1" @click="movePythonPlot(index, 1)"><WorkstationGlyph kind="move-down" /></button><button type="button" :aria-label="`Duplicate ${plot.name}`" @click="duplicatePythonPlot(index)"><WorkstationGlyph kind="duplicate" /></button><button type="button" :aria-label="`Copy ${plot.name} to linked charts`" :disabled="!linkedTargets" @click="copyPythonPlot(index, 'linked')"><WorkstationGlyph kind="copy-linked" /></button><button type="button" :aria-label="`Copy ${plot.name} to selected chart target`" :disabled="!copyTargetAvailable" @click="copyPythonPlot(index, selectedCopyTarget)"><WorkstationGlyph kind="copy" /></button><button type="button" :aria-label="`Remove ${plot.name}`" @click="removePythonPlot(index)"><WorkstationGlyph kind="delete" /></button>
      </li><li v-if="draggingPreview && !chartStore.indicators.some(indicator => indicator.type === draggingPreview!.type && JSON.stringify(indicator.params ?? {}) === JSON.stringify(draggingPreview!.params ?? {}))" class="chart-plots__drag-preview" draggable="true" @dragstart="startPreviewDrag($event)" @dragend="endDrag"><span>{{ indicatorDisplayName(draggingPreview) }}</span></li><li v-for="(indicator, index) in chartStore.indicators" :key="`${indicator.type}:${index}`" :class="{ muted: indicator.hidden }" draggable="true" @dragstart="startDrag(index, $event)" @dragend="endDrag">
        <input :value="indicator.style.color" :aria-label="`${label(indicator)} color`" type="color" @input="style(index, 'color', ($event.target as HTMLInputElement).value)" /><span>{{ label(indicator) }}</span>
        <input :value="indicator.style.lineWidth" :aria-label="`${label(indicator)} line width`" type="number" min="0.25" max="5" step="0.25" @change="style(index, 'lineWidth', Number(($event.target as HTMLInputElement).value))" />
        <button type="button" :aria-label="`${indicator.hidden ? 'Show' : 'Hide'} ${label(indicator)}`" @click="toggle(index)"><WorkstationGlyph :kind="indicator.hidden ? 'hidden' : 'visible'" /></button><button type="button" :aria-label="`Move ${label(indicator)} up`" :disabled="index === 0" @click="move(index, -1)"><WorkstationGlyph kind="move-up" /></button><button type="button" :aria-label="`Move ${label(indicator)} down`" :disabled="index === chartStore.indicators.length - 1" @click="move(index, 1)"><WorkstationGlyph kind="move-down" /></button><button type="button" :aria-label="`Duplicate ${label(indicator)}`" @click="duplicate(index)"><WorkstationGlyph kind="duplicate" /></button><button type="button" :aria-label="`Copy ${label(indicator)} to linked charts`" :disabled="!linkedTargets" @click="copy(index, 'linked')"><WorkstationGlyph kind="copy-linked" /></button><button type="button" :aria-label="`Copy ${label(indicator)} to selected chart target`" :disabled="!copyTargetAvailable" @click="copy(index, selectedCopyTarget)"><WorkstationGlyph kind="copy" /></button><button type="button" :aria-label="`Promote ${label(indicator)}`" @click="selectPromotion(index)"><WorkstationGlyph kind="promote" /></button><button type="button" :aria-label="`Delete ${label(indicator)}`" @click="chartStore.removeIndicator(index)"><WorkstationGlyph kind="delete" /></button>
      </li></ol>
    </div>
  </section>
</template>
<script setup lang="ts">
import { computed, inject, nextTick, onBeforeUnmount, ref } from 'vue'
import { useQueryClient } from '@tanstack/vue-query'
import { usePanelStore } from '@/stores/chart'
import { useWorkspaceStore } from '@/stores/workspace'
import { cloneDefaultIndicator, INDICATOR_CATALOG, indicatorDisplayName } from '@/lib/indicators/catalog'
import { api } from '@/lib/api'
import type { IndicatorConfig, IndicatorType } from '@/types'
import { clearAnalysisDrag, createChartPlotDragPayload, createPythonPlotDragPayload, scheduleAnalysisDragCleanup, writeChartPlotDrag, writePythonPlotDrag } from '@/lib/workstation/plotDrag'
import { fetchCodeAssets } from '@/lib/workstation/libraryQueries'
import WorkstationGlyph from './WorkstationGlyph.vue'
type PythonPlot = {
  code_version_id: number
  name: string
  color?: string
  timeframe?: string
  hidden?: boolean
  instance_key?: string
  universe_source_id?: string
  symbols?: string[]
}
type ScanPlot = { screener_id: number; name: string; metric: 'count' | 'percentage'; color?: string; hidden?: boolean; instance_key?: string }
type ScanAsset = { screenerId: number; name: string; metric: 'count' | 'percentage'; points: number }
const props = defineProps<{ sourceWindowKey: string; linkGroup: string; pythonPlots?: PythonPlot[]; scanPlots?: ScanPlot[] }>()
const emit = defineEmits<{ 'update:python-plots': [plots: PythonPlot[]]; 'update:scan-plots': [plots: ScanPlot[]] }>()
const chartStore = usePanelStore(inject<string>('panelId', 'chart')); const open = ref(false); const catalog = INDICATOR_CATALOG; const workspaceStore = useWorkspaceStore()
const queryClient = useQueryClient()
const toggleButton = ref<HTMLButtonElement | null>(null)
const menuRoot = ref<HTMLElement | null>(null)
const firstControl = ref<HTMLSelectElement | null>(null)
const menuStyle = ref<Record<string, string>>({})
function positionMenu() {
  const rect = toggleButton.value?.getBoundingClientRect()
  if (!rect) return
  const gutter = 8
  const width = Math.min(300, Math.max(180, window.innerWidth - gutter * 2))
  const left = Math.max(gutter, Math.min(rect.left, window.innerWidth - width - gutter))
  const menuHeight = Math.min(340, Math.max(120, window.innerHeight - gutter * 2))
  const below = rect.bottom + 4
  const above = rect.top - menuHeight - 4
  const top = below + menuHeight <= window.innerHeight - gutter ? below : Math.max(gutter, above)
  menuStyle.value = { position: 'fixed', left: `${Math.round(left)}px`, top: `${Math.round(top)}px`, width: `${Math.round(width)}px`, maxHeight: `${Math.round(menuHeight)}px` }
}
function toggleOpen() {
  open.value = !open.value
  if (open.value) void nextTick(() => {
    positionMenu()
    window.addEventListener('resize', positionMenu)
    window.addEventListener('scroll', positionMenu, true)
    firstControl.value?.focus()
  })
  else closeToTrigger()
}
function closeToTrigger() {
  if (!open.value) return
  open.value = false
  window.removeEventListener('resize', positionMenu)
  window.removeEventListener('scroll', positionMenu, true)
  void nextTick(() => toggleButton.value?.focus())
}
function handleTriggerKeydown(event: KeyboardEvent) {
  if (!['Enter', ' ', 'ArrowDown', 'ArrowUp'].includes(event.key)) return
  event.preventDefault()
  if (!open.value) toggleOpen()
  else firstControl.value?.focus()
}
function handleMenuKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') {
    event.preventDefault()
    event.stopPropagation()
    closeToTrigger()
  }
}
const selectedCopyTarget = ref('linked')
const chartTargets = computed(() => (workspaceStore.activeTab?.windows ?? []).filter(window => ['chart', 'watchlist'].includes(window.tool_type) && window.instance_key !== props.sourceWindowKey))
const watchlistTargets = computed(() => chartTargets.value.filter(window => window.tool_type === 'watchlist'))
const linkedChartCount = computed(() => chartTargets.value.filter(window => window.tool_type === 'chart' && window.link_group === props.linkGroup).length)
const linkedTargets = computed(() => linkedChartCount.value > 0)
const copyTargetAvailable = computed(() => selectedCopyTarget.value === 'linked' ? linkedTargets.value : chartTargets.value.some(window => window.instance_key === selectedCopyTarget.value))
const selectedPromotionIndex = ref('')
const promotionTarget = ref<'condition' | 'scan' | 'filter' | 'alert'>('condition')
const selectedFilterTarget = ref('')
const promotionOperator = ref('gt')
const promotionThreshold = ref(0)
const promotionName = ref('')
const promotionBusy = ref(false)
const promotionStatus = ref('')
type PythonAsset = { versionId: number; name: string; universeSourceId?: string; symbols?: string[] }
const pythonAssets = ref<PythonAsset[]>([])
const selectedPythonVersion = ref('')
const pythonLoading = ref(false)
const pythonStatus = ref('')
const scanAssets = ref<ScanAsset[]>([])
const selectedScanAsset = ref('')
const scanLoading = ref(false)
const scanStatus = ref('')
const draggingIndex = ref<number | null>(null)
const draggingPreview = ref<IndicatorConfig | null>(null)
function label(indicator: IndicatorConfig) { return indicatorDisplayName(indicator) }
async function loadPythonAssets() {
  pythonLoading.value = true; pythonStatus.value = ''
  try {
    const assets = await fetchCodeAssets(queryClient)
    pythonAssets.value = assets.filter(asset => asset.kind === 'plot' || asset.kind === 'study').flatMap(asset => asset.versions.slice(-1).flatMap(version => {
      if (!version.id || (version.output_contract !== 'series' && asset.kind !== 'plot')) return []
      const diagnostics = Array.isArray(version.diagnostics) ? version.diagnostics : []
      const promotion = diagnostics.find(item => item && typeof item.promotion_lineage === 'object' && !Array.isArray(item.promotion_lineage))?.promotion_lineage as Record<string, unknown> | undefined
      const sourceUniverse = promotion?.source_universe && typeof promotion.source_universe === 'object' && !Array.isArray(promotion.source_universe) ? promotion.source_universe as Record<string, unknown> : undefined
      const promotionSourceId = typeof promotion?.universe_source_id === 'string' ? promotion.universe_source_id.trim() : ''
      const universeSourceId = typeof sourceUniverse?.source_id === 'string' ? sourceUniverse.source_id.trim() : ''
      const sourceId = promotionSourceId || universeSourceId || undefined
      const symbolsValue = promotion?.source_symbols ?? sourceUniverse?.requested_symbols
      const symbols = Array.isArray(symbolsValue) ? symbolsValue.filter((symbol): symbol is string => typeof symbol === 'string' && symbol.trim().length > 0).map(symbol => symbol.trim().toUpperCase()) : undefined
      return [{ versionId: version.id, name: `${asset.name} v${version.version_number}`, ...(sourceId ? { universeSourceId: sourceId } : {}), ...(symbols?.length ? { symbols } : {}) }]
    }))
    pythonStatus.value = pythonAssets.value.length ? `${pythonAssets.value.length} plot asset${pythonAssets.value.length === 1 ? '' : 's'} available` : 'No Python plot assets available'
  } catch (cause: any) { pythonStatus.value = cause?.message ?? 'Unable to load Python plot assets' }
  finally { pythonLoading.value = false }
}
function addPythonPlot() {
  const versionId = Number(selectedPythonVersion.value)
  const asset = pythonAssets.value.find(item => item.versionId === versionId)
  if (!asset || (props.pythonPlots ?? []).some(plot => plot.code_version_id === versionId)) return
  const colors = ['#ffb74d', '#81c784', '#ba68c8', '#f06292', '#4dd0e1']
  const plot: PythonPlot = { code_version_id: versionId, name: asset.name, color: colors[(props.pythonPlots ?? []).length % colors.length], timeframe: chartStore.timeframe, instance_key: `${versionId}-${Date.now().toString(36)}`, ...(asset.universeSourceId ? { universe_source_id: asset.universeSourceId } : {}), ...(asset.symbols?.length ? { symbols: [...asset.symbols] } : {}) }
  emit('update:python-plots', [...(props.pythonPlots ?? []), plot])
  selectedPythonVersion.value = ''
  pythonStatus.value = `Added ${asset.name}`
}
async function loadScanPlots() {
  scanLoading.value = true
  scanStatus.value = ''
  try {
    const screeners = await api.get<Array<{ id: number; name: string }>>('/screeners')
    const assets = await Promise.all((screeners ?? []).map(async screener => {
      const entries = await Promise.all((['percentage', 'count'] as const).map(async metric => {
        const plot = await api.get<{ points?: Array<{ value?: number | null }> }>(`/screeners/${screener.id}/plot`, { metric })
        const points = (plot?.points ?? []).filter(point => typeof point.value === 'number' && Number.isFinite(point.value)).length
        return points ? { screenerId: screener.id, name: screener.name, metric, points } : null
      }))
      return entries.filter((entry): entry is ScanAsset => entry != null)
    }))
    scanAssets.value = assets.flat().filter((entry): entry is ScanAsset => entry != null)
    scanStatus.value = scanAssets.value.length ? `${scanAssets.value.length} historical scan plot${scanAssets.value.length === 1 ? '' : 's'} available` : 'No retained scan history available'
  } catch (cause: any) {
    scanStatus.value = cause?.message ?? 'Unable to load EasyScan plots'
  } finally {
    scanLoading.value = false
  }
}
function addScanPlot() {
  const [id, metric] = selectedScanAsset.value.split(':')
  const screenerId = Number(id)
  const asset = scanAssets.value.find(item => item.screenerId === screenerId && item.metric === metric)
  if (!asset || (props.scanPlots ?? []).some(plot => plot.screener_id === screenerId && plot.metric === asset.metric)) return
  const colors = ['#4dd0e1', '#ffb74d', '#81c784', '#ba68c8', '#f06292']
  const plot: ScanPlot = { screener_id: screenerId, name: asset.name, metric: asset.metric, color: colors[(props.scanPlots ?? []).length % colors.length], instance_key: `${screenerId}-${asset.metric}-${Date.now().toString(36)}` }
  emit('update:scan-plots', [...(props.scanPlots ?? []), plot])
  selectedScanAsset.value = ''
  scanStatus.value = `Added ${asset.name} · ${asset.metric}`
}
function pythonPlotKey(plot: PythonPlot, index: number) {
  return `python:${plot.instance_key ?? `${plot.code_version_id}:${index}`}`
}
function scanPlotKey(plot: ScanPlot, index: number) {
  return `scan:${plot.instance_key ?? `${plot.screener_id}:${plot.metric}:${index}`}`
}
function updateScanPlot(index: number, changes: Partial<ScanPlot>) {
  const plots = [...(props.scanPlots ?? [])]
  if (!plots[index]) return
  plots[index] = { ...plots[index], ...changes }
  emit('update:scan-plots', plots)
}
function toggleScanPlot(index: number) {
  const plot = props.scanPlots?.[index]
  if (plot) updateScanPlot(index, { hidden: !plot.hidden })
}
function moveScanPlot(index: number, delta: number) {
  const target = index + delta
  const plots = [...(props.scanPlots ?? [])]
  if (index < 0 || target < 0 || target >= plots.length) return
  const [plot] = plots.splice(index, 1)
  plots.splice(target, 0, plot)
  emit('update:scan-plots', plots)
}
function duplicateScanPlot(index: number) {
  const plot = props.scanPlots?.[index]
  if (!plot) return
  const plots = [...(props.scanPlots ?? [])]
  plots.splice(index + 1, 0, { ...plot, instance_key: `${plot.screener_id}-${plot.metric}-${Date.now().toString(36)}`, hidden: false })
  emit('update:scan-plots', plots)
}
function removeScanPlot(index: number) {
  const plots = [...(props.scanPlots ?? [])]
  if (!plots[index]) return
  plots.splice(index, 1)
  emit('update:scan-plots', plots)
}
function updatePythonPlot(index: number, changes: Partial<PythonPlot>) {
  const plots = [...(props.pythonPlots ?? [])]
  if (!plots[index]) return
  plots[index] = { ...plots[index], ...changes }
  emit('update:python-plots', plots)
}
function togglePythonPlot(index: number) {
  const plot = props.pythonPlots?.[index]
  if (plot) updatePythonPlot(index, { hidden: !plot.hidden })
}
function movePythonPlot(index: number, delta: number) {
  const target = index + delta
  const plots = [...(props.pythonPlots ?? [])]
  if (index < 0 || target < 0 || target >= plots.length) return
  const [plot] = plots.splice(index, 1)
  plots.splice(target, 0, plot)
  emit('update:python-plots', plots)
}
function duplicatePythonPlot(index: number) {
  const plot = props.pythonPlots?.[index]
  if (!plot) return
  const plots = [...(props.pythonPlots ?? [])]
  plots.splice(index + 1, 0, { ...plot, instance_key: `${plot.code_version_id}-${Date.now().toString(36)}`, hidden: false })
  emit('update:python-plots', plots)
}
function removePythonPlot(index: number) {
  const plots = [...(props.pythonPlots ?? [])]
  if (!plots[index]) return
  plots.splice(index, 1)
  emit('update:python-plots', plots)
}
function startPythonDrag(index: number, event: DragEvent) {
  const plot = props.pythonPlots?.[index]
  if (!plot || !event.dataTransfer) return
  const payload = createPythonPlotDragPayload(plot, chartStore.timeframe, props.sourceWindowKey)
  if (payload && writePythonPlotDrag(event.dataTransfer, payload)) draggingIndex.value = index
}
function startDrag(index: number, event: DragEvent) {
  const item = chartStore.indicators[index]
  if (!item || !event.dataTransfer) return
  const payload = createChartPlotDragPayload(item, chartStore.timeframe, props.sourceWindowKey)
  if (writeChartPlotDrag(event.dataTransfer, payload)) {
    draggingIndex.value = index
    draggingPreview.value = { ...item, params: { ...item.params }, style: { ...item.style } }
  }
}
function startPreviewDrag(event: DragEvent) {
  const item = draggingPreview.value
  if (!item || !event.dataTransfer) return
  const payload = createChartPlotDragPayload(item, chartStore.timeframe, props.sourceWindowKey)
  if (writeChartPlotDrag(event.dataTransfer, payload)) draggingIndex.value = 0
}
function endDrag() { draggingIndex.value = null; draggingPreview.value = null; scheduleAnalysisDragCleanup() }
async function add(value: string) {
  if (!INDICATOR_CATALOG.some(item => item.type === value)) return
  chartStore.addIndicator(cloneDefaultIndicator(value as IndicatorType))
  // Persist immediately because a real drag can activate another Golden Layout
  // tool before the chart store's debounced one-second save fires.
  await chartStore.saveIndicatorsForInstrument()
  // Selecting a plot is an insertion action, not a request to keep a modal
  // surface over the chart. Close the fixed menu so the next chart gesture
  // (drawing, pan, crosshair, or zoom) reaches the uPlot surface immediately.
  closeToTrigger()
}
function style(index: number, key: 'color' | 'lineWidth', value: string | number) { const item = chartStore.indicators[index]; if (item && (key !== 'lineWidth' || (Number.isFinite(value) && Number(value) > 0))) chartStore.updateIndicator(index, { ...item, style: { ...item.style, [key]: value } }) }
function toggle(index: number) { const item = chartStore.indicators[index]; if (item) chartStore.updateIndicator(index, { ...item, hidden: !item.hidden }) }
function duplicate(index: number) { const item = chartStore.indicators[index]; if (item) chartStore.indicators.splice(index + 1, 0, { ...item, params: { ...item.params }, style: { ...item.style }, lockedTimeframes: item.lockedTimeframes ? [...item.lockedTimeframes] : item.lockedTimeframes }) }
function move(index: number, delta: number) { const target = index + delta; if (target < 0 || target >= chartStore.indicators.length) return; const next = [...chartStore.indicators]; const [item] = next.splice(index, 1); next.splice(target, 0, item); chartStore.reorderIndicators(next) }
function copy(index: number, target: string) {
  const item = chartStore.indicators[index]
  if (!item) return
  for (const window of workspaceStore.activeTab?.windows ?? []) {
    if (window.instance_key === props.sourceWindowKey) continue
    if (target === 'linked' ? window.tool_type !== 'chart' || window.link_group !== props.linkGroup : window.instance_key !== target) continue
    if (window.tool_type === 'watchlist') {
      const columns = Array.isArray(window.configuration.indicator_columns) ? window.configuration.indicator_columns : []
      const key = `indicator:${item.type}:${JSON.stringify(item.params)}`
      if (!columns.some((column: any) => column?.key === key)) window.configuration.indicator_columns = [...columns, { key, name: label(item), indicator: item.type, params: { ...item.params }, timeframe: chartStore.timeframe, output: 'value' }]
    } else {
      const plots = Array.isArray(window.configuration.indicators) ? window.configuration.indicators : []
      window.configuration.indicators = [...plots, { ...item, params: { ...item.params }, style: { ...item.style }, lockedTimeframes: item.lockedTimeframes ? [...item.lockedTimeframes] : item.lockedTimeframes }]
    }
  }
  workspaceStore.scheduleSnapshot()
}
function copyPythonPlot(index: number, target: string) {
  const plot = props.pythonPlots?.[index]
  if (!plot) return
  for (const window of workspaceStore.activeTab?.windows ?? []) {
    if (window.instance_key === props.sourceWindowKey) continue
    if (target === 'linked' ? window.tool_type !== 'chart' || window.link_group !== props.linkGroup : window.instance_key !== target) continue
    if (window.tool_type === 'watchlist') {
      const columns = Array.isArray(window.configuration.python_columns) ? window.configuration.python_columns : []
      if (!columns.some((column: any) => column?.code_version_id === plot.code_version_id)) window.configuration.python_columns = [...columns, { code_version_id: plot.code_version_id, name: plot.name, timeframe: plot.timeframe ?? chartStore.timeframe }]
    } else {
      const plots = Array.isArray(window.configuration.python_plots) ? window.configuration.python_plots : []
      if (!plots.some((candidate: any) => candidate?.code_version_id === plot.code_version_id && candidate?.instance_key === plot.instance_key)) window.configuration.python_plots = [...plots, { ...plot, hidden: false, instance_key: `${plot.code_version_id}-${Date.now().toString(36)}` }]
    }
  }
  workspaceStore.scheduleSnapshot()
}
function copyScanPlot(index: number, target: string) {
  const plot = props.scanPlots?.[index]
  if (!plot) return
  for (const window of workspaceStore.activeTab?.windows ?? []) {
    if (window.instance_key === props.sourceWindowKey) continue
    if (target === 'linked' ? window.tool_type !== 'chart' || window.link_group !== props.linkGroup : window.instance_key !== target) continue
    if (window.tool_type !== 'chart') continue
    const plots = Array.isArray(window.configuration.scan_plots) ? window.configuration.scan_plots : []
    if (!plots.some((candidate: any) => candidate?.screener_id === plot.screener_id && candidate?.metric === plot.metric)) {
      window.configuration.scan_plots = [...plots, { ...plot, hidden: false, instance_key: `${plot.screener_id}-${plot.metric}-${Date.now().toString(36)}` }]
    }
  }
  workspaceStore.scheduleSnapshot()
}
function selectPromotion(index: number) {
  selectedPromotionIndex.value = String(index)
  promotionName.value = `${label(chartStore.indicators[index])} condition`
  selectedFilterTarget.value = watchlistTargets.value[0]?.instance_key ?? ''
  promotionStatus.value = ''
}
function promotionCondition(item: IndicatorConfig) {
  return { operator: 'AND', conditions: [{ type: 'indicator_threshold', indicator: item.type, params: { ...item.params }, output: 'value', op: promotionOperator.value, value: promotionThreshold.value }] }
}
function promotionKey(name: string) {
  return name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 72) || 'chart-plot-condition'
}
async function promoteSelected() {
  const item = chartStore.indicators[Number(selectedPromotionIndex.value)]
  if (!item || !promotionName.value || !Number.isFinite(promotionThreshold.value) || promotionBusy.value) return
  promotionBusy.value = true; promotionStatus.value = ''
  try {
    const key = promotionKey(promotionName.value)
    await api.put(`/workspaces/library/conditions/${encodeURIComponent(key)}`, {
      name: promotionName.value, condition: promotionCondition(item),
      dependency_metadata: { source: 'chart-plot-library', indicator_type: item.type, timeframe: chartStore.timeframe },
    })
    if (promotionTarget.value === 'scan' || promotionTarget.value === 'filter') {
      const scan = await api.post<{ id: number }>(`/screeners/from-condition/${encodeURIComponent(key)}`, { name: `${promotionName.value} Scan`, universe_type: 'all', timeframe: chartStore.timeframe })
      if (promotionTarget.value === 'filter') {
        const target = watchlistTargets.value.find(window => window.instance_key === selectedFilterTarget.value)
        if (!target) throw new Error('Select a watchlist window before applying a filter')
        target.configuration = { ...target.configuration, condition_screener_id: scan.id, condition_filter_mode: 'active' }
        workspaceStore.scheduleSnapshot()
        promotionStatus.value = `Copied ${label(item)} to ${target.title || target.instance_key} filter`
        return
      }
      promotionStatus.value = `Copied ${label(item)} to condition and EasyScan`
    } else if (promotionTarget.value === 'alert') {
      const instrumentId = chartStore.instrument?.id
      if (!instrumentId) throw new Error('Select a canonical instrument before creating an indicator alert')
      await api.post('/alerts/indicator', { instrument_id: instrumentId, timeframe: chartStore.timeframe, indicator_a_type: item.type, indicator_a_params: { ...item.params }, condition: promotionOperator.value, threshold_value: promotionThreshold.value, repeat: true, notes: promotionName.value })
      promotionStatus.value = `Copied ${label(item)} to condition and indicator alert`
    } else promotionStatus.value = `Copied ${label(item)} to reusable condition`
  } catch (cause: any) {
    promotionStatus.value = cause?.message ?? 'Unable to promote plot'
  } finally { promotionBusy.value = false }
}
onBeforeUnmount(() => {
  window.removeEventListener('resize', positionMenu)
  window.removeEventListener('scroll', positionMenu, true)
})
</script>
<style scoped>
.chart-plots{position:relative}.chart-plots button,.chart-plots select,.chart-plots input{border:1px solid #3a4954;background:#172027;color:#dce6ed;font:10px "Segoe UI",Arial,sans-serif}.chart-plots>button{height:18px;padding:0 5px;cursor:pointer}.chart-plots__menu{z-index:121;display:grid;gap:4px;max-height:340px;padding:6px;border:1px solid #4a5b67;background:#131a20;box-shadow:0 6px 16px #000b}.chart-plots__menu header{display:flex;align-items:center}.chart-plots__menu header button{margin-left:auto}.chart-plots select{min-width:0;padding:2px}.chart-plots p{margin:0;padding:3px 4px;color:#b4c3cd;border-top:1px solid #2d3942}.chart-plots p small{color:#8196a4}.chart-plots ol{display:grid;gap:2px;max-height:204px;margin:0;padding:0;overflow:auto;list-style:none}.chart-plots li{display:grid;grid-template-columns:18px minmax(0,1fr) 36px repeat(6,18px);align-items:center;gap:3px;padding:2px;border-top:1px solid #27323a}.chart-plots li span{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.chart-plots li input[type=color]{width:17px;height:16px;padding:0}.chart-plots li input[type=number]{min-width:0;padding:1px}.chart-plots li button{height:17px;padding:0;cursor:pointer}.chart-plots li button:disabled{opacity:.35}.muted{opacity:.5}
.chart-plots__promotion{display:grid;grid-template-columns:72px 34px 62px minmax(60px,1fr) 36px;gap:3px}.chart-plots__promotion input,.chart-plots__promotion select{min-width:0}.chart-plots__promotion-status{margin:0;padding:2px 4px;color:#9ec6a0}
</style>
