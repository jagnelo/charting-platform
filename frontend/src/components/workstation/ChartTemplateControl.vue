<template>
  <section class="chart-template" aria-label="Chart templates" @keydown.esc="closeToTrigger">
    <button ref="trigger" type="button" title="Chart templates" aria-label="Chart templates" :aria-expanded="open" aria-haspopup="menu" @click="toggleOpen" @keydown="handleTriggerKeydown">Templates</button>
    <div v-if="open" ref="menuRoot" class="chart-template__menu" role="menu" :style="menuStyle" @keydown="handleMenuKeydown">
      <header><b>Chart templates</b><button type="button" aria-label="Close chart templates" @click="closeToTrigger"><WorkstationGlyph kind="close" /></button></header>
      <div class="chart-template__save">
      <input ref="firstEditor" v-model.trim="name" aria-label="Chart template name" placeholder="Template name" @keydown.enter.prevent="save" />
        <button type="button" :disabled="!name || busy" @click="save">Save</button>
      </div>
      <label class="chart-template__bar-type">Bar type
        <select :value="currentBarType" aria-label="Chart bar type" @change="setBarType(($event.target as HTMLSelectElement).value)">
          <option v-for="type in barTypes" :key="type.value" :value="type.value">{{ type.label }}</option>
        </select>
      </label>
      <p v-if="error" class="chart-template__error">{{ error }}</p>
      <p v-else-if="loading" class="chart-template__state">Loading templates…</p>
      <p v-else-if="!items.length" class="chart-template__state">No saved templates.</p>
      <ul v-else>
        <li v-for="item in items" :key="item.stable_key">
          <template v-if="renamingKey === item.stable_key">
            <input :ref="element => setRenameInput(item.stable_key, element)" v-model.trim="renameDraft" class="chart-template__rename-input" :aria-label="`Rename ${item.name}`" @keydown.enter.prevent="rename(item)" @keydown.esc="cancelRename" />
            <button type="button" aria-label="Save template name" :disabled="!renameDraft || busy" @click="rename(item)">Save</button>
            <button type="button" aria-label="Cancel template rename" :disabled="busy" @click="cancelRename"><WorkstationGlyph kind="close" /></button>
          </template>
          <template v-else>
            <button type="button" class="chart-template__apply" @click="apply(item)">{{ item.name }} <small>v{{ item.version }}</small></button>
            <button type="button" :aria-label="`Rename ${item.name}`" :disabled="busy" @click="beginRename(item)"><WorkstationGlyph kind="edit" /></button>
          </template>
          <button type="button" :aria-label="`Clone ${item.name}`" :disabled="busy" @click="clone(item)"><WorkstationGlyph kind="duplicate" /></button>
          <button type="button" :aria-label="`Export ${item.name}`" @click="exportItem(item)"><WorkstationGlyph kind="export" /></button>
          <button type="button" :aria-label="`Delete ${item.name}`" :disabled="busy" @click="remove(item)"><WorkstationGlyph kind="delete" /></button>
        </li>
      </ul>
      <footer>
        <button type="button" @click="reset">Reset chart defaults</button>
        <label><input ref="importInput" type="file" accept="application/json" @change="importItem" />Import</label>
      </footer>
    </div>
  </section>
</template>

<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch, type ComponentPublicInstance } from 'vue'
import { useQueryClient } from '@tanstack/vue-query'
import { api } from '@/lib/api'
import { CHART_BAR_TYPES, type ChartBarType, type IndicatorConfig } from '@/types'
import WorkstationGlyph from './WorkstationGlyph.vue'

type TemplateItem = { stable_key: string; name: string; version: number; payload: { configuration?: Record<string, unknown> } }
const props = defineProps<{ configuration: Record<string, unknown>; indicatorConfigs?: IndicatorConfig[] }>()
const emit = defineEmits<{ apply: [configuration: Record<string, unknown>] }>()
const queryClient = useQueryClient()
const open = ref(false)
const trigger = ref<HTMLButtonElement | null>(null)
const menuRoot = ref<HTMLElement | null>(null)
const firstEditor = ref<HTMLInputElement | null>(null)
const menuStyle = ref<Record<string, string>>({})
const loading = ref(false)
const busy = ref(false)
const error = ref('')
const name = ref('')
const items = ref<TemplateItem[]>([])
const importInput = ref<HTMLInputElement | null>(null)
const renamingKey = ref<string | null>(null)
const renameDraft = ref('')
const renameInputs = new Map<string, HTMLInputElement>()
const identityKeys = new Set(['symbol', 'instrument_id', 'expression'])
const barTypes = CHART_BAR_TYPES
function validatedBarType(value: unknown): ChartBarType {
  return typeof value === 'string' && barTypes.some(type => type.value === value)
    ? value as ChartBarType
    : 'candles'
}
const currentBarType = ref<ChartBarType>(validatedBarType(props.configuration.bar_type))
watch(() => props.configuration.bar_type, requested => {
  currentBarType.value = validatedBarType(requested)
})

function stableKey(seed: string) {
  const normalized = seed.toLowerCase().trim().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'chart-template'
  return `${normalized}-${crypto.randomUUID().slice(0, 8)}`
}

function templateConfiguration(value: Record<string, unknown>) {
  return Object.fromEntries(Object.entries(value).filter(([key]) => !identityKeys.has(key)))
}

function currentTemplateConfiguration() {
  return {
    ...props.configuration,
    // Copy the plot stack deeply enough that later in-chart edits cannot mutate an
    // already saved immutable library version through a retained array reference.
    indicators: (props.indicatorConfigs ?? []).map(indicator => ({
      ...indicator,
      params: { ...indicator.params },
      style: { ...indicator.style },
      lockedTimeframes: indicator.lockedTimeframes ? [...indicator.lockedTimeframes] : indicator.lockedTimeframes,
    })),
  }
}

function setRenameInput(key: string, element: Element | ComponentPublicInstance | null) {
  if (element instanceof HTMLInputElement) renameInputs.set(key, element)
}

function beginRename(item: TemplateItem) {
  renamingKey.value = item.stable_key
  renameDraft.value = item.name
  void nextTick(() => renameInputs.get(item.stable_key)?.select())
}

function cancelRename() {
  renamingKey.value = null
  renameDraft.value = ''
}

function toggleOpen() {
  open.value = !open.value
  if (open.value) void nextTick(() => {
    positionMenu()
    window.addEventListener('resize', positionMenu)
    window.addEventListener('scroll', positionMenu, true)
    firstEditor.value?.focus()
  })
  else {
    window.removeEventListener('resize', positionMenu)
    window.removeEventListener('scroll', positionMenu, true)
    void nextTick(() => trigger.value?.focus())
  }
}

function positionMenu() {
  const rect = trigger.value?.getBoundingClientRect()
  if (!rect) return
  const width = 238
  const gutter = 8
  const left = Math.max(gutter, Math.min(rect.right - width, window.innerWidth - width - gutter))
  const menuHeight = Math.min(300, Math.max(120, window.innerHeight - gutter * 2))
  const below = rect.bottom + 4
  const above = rect.top - menuHeight - 4
  const top = below + menuHeight <= window.innerHeight - gutter
    ? below
    : Math.max(gutter, above)
  menuStyle.value = { position: 'fixed', left: `${Math.round(left)}px`, top: `${Math.round(top)}px`, width: `${width}px`, maxHeight: `${Math.round(menuHeight)}px` }
}

function closeToTrigger() {
  if (!open.value) return
  open.value = false
  window.removeEventListener('resize', positionMenu)
  window.removeEventListener('scroll', positionMenu, true)
  void nextTick(() => trigger.value?.focus())
}

function handleTriggerKeydown(event: KeyboardEvent) {
  if (event.key === 'Enter' || event.key === ' ' || event.key === 'ArrowDown') {
    event.preventDefault()
    if (!open.value) toggleOpen()
    else void nextTick(() => firstEditor.value?.focus())
  }
}

function handleMenuKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') {
    event.preventDefault()
    closeToTrigger()
  }
}

function apply(item: TemplateItem) {
  // A template is an appearance/mechanics preset, never a symbol navigation action.
  const configuration = { ...templateConfiguration(props.configuration), ...(item.payload.configuration ?? {}) }
  currentBarType.value = validatedBarType(configuration.bar_type)
  emit('apply', configuration)
  error.value = ''
}

function setBarType(value: string) {
  if (!barTypes.some(type => type.value === value)) return
  currentBarType.value = value as ChartBarType
  emit('apply', { ...props.configuration, bar_type: value })
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    items.value = await queryClient.fetchQuery<TemplateItem[]>({
      queryKey: ['workstation', 'library-items', 'chart_template'],
      queryFn: async () => (await api.get<TemplateItem[]>('/workspaces/library/items', { kind: 'chart_template' })) ?? [],
      staleTime: 30_000,
    })
  }
  catch (cause: any) { error.value = cause?.message ?? 'Unable to load chart templates' }
  finally { loading.value = false }
}

async function persist(templateName: string, configuration: Record<string, unknown>, key = stableKey(templateName)) {
  busy.value = true
  error.value = ''
  try {
    await api.put(`/workspaces/library/items/chart_template/${encodeURIComponent(key)}`, {
      kind: 'chart_template', stable_key: key, name: templateName,
      payload: { configuration: templateConfiguration(configuration), schema_version: 1 },
      dependency_metadata: { contract: 'workstation_chart_template_v1' },
    })
    await queryClient.invalidateQueries({ queryKey: ['workstation', 'library-items', 'chart_template'] })
    await load()
  } catch (cause: any) { error.value = cause?.message ?? 'Unable to save chart template' }
  finally { busy.value = false }
}

async function rename(item: TemplateItem) {
  const nextName = renameDraft.value.trim()
  if (!nextName || !renamingKey.value) return
  await persist(nextName, item.payload.configuration ?? {}, item.stable_key)
  cancelRename()
}

async function save() { if (name.value) { await persist(name.value, { ...currentTemplateConfiguration(), bar_type: currentBarType.value }); name.value = '' } }
async function clone(item: TemplateItem) { await persist(`${item.name} copy`, item.payload.configuration ?? {}) }
async function remove(item: TemplateItem) {
  busy.value = true; error.value = ''
  try {
    await api.delete(`/workspaces/library/items/chart_template/${encodeURIComponent(item.stable_key)}`)
    await queryClient.invalidateQueries({ queryKey: ['workstation', 'library-items', 'chart_template'] })
    await load()
  }
  catch (cause: any) { error.value = cause?.message ?? 'Unable to delete chart template' }
  finally { busy.value = false }
}

function reset() { currentBarType.value = 'candles'; emit('apply', { timeframe: 'D1', bar_type: 'candles', indicators: [] }) }
function exportItem(item: TemplateItem) {
  const blob = new Blob([JSON.stringify({ kind: 'chart_template', name: item.name, payload: item.payload }, null, 2)], { type: 'application/json' })
  const href = URL.createObjectURL(blob); const link = document.createElement('a')
  link.href = href; link.download = `${item.stable_key}.json`; link.click(); URL.revokeObjectURL(href)
}
async function importItem(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0]
  if (!file) return
  try {
    const parsed = JSON.parse(await file.text())
    if (parsed?.kind !== 'chart_template' || typeof parsed?.name !== 'string' || !parsed?.payload?.configuration || typeof parsed.payload.configuration !== 'object') throw new Error('Not a chart-template export')
    await persist(parsed.name, parsed.payload.configuration)
  } catch (cause: any) { error.value = cause?.message ?? 'Unable to import chart template' }
  finally { if (importInput.value) importInput.value.value = '' }
}
onMounted(() => { void load() })
onBeforeUnmount(() => {
  window.removeEventListener('resize', positionMenu)
  window.removeEventListener('scroll', positionMenu, true)
})
</script>

<style scoped>
.chart-template{position:relative}.chart-template>button,.chart-template button,.chart-template input,.chart-template label{border:1px solid #3a4954;background:#172027;color:#dce6ed;font:10px "Segoe UI",Arial,sans-serif}.chart-template>button{height:18px;padding:0 5px;cursor:pointer}.chart-template__menu{z-index:120;display:grid;gap:4px;max-height:300px;padding:6px;border:1px solid #4a5b67;background:#131a20;box-shadow:0 6px 16px #000b}.chart-template__menu header,.chart-template__save,.chart-template__menu footer,.chart-template__menu li{display:flex;align-items:center;gap:4px}.chart-template__menu header button{margin-left:auto}.chart-template__save input{min-width:0;flex:1;padding:2px 4px}.chart-template__menu ul{display:grid;gap:2px;max-height:154px;margin:0;padding:0;overflow:auto;list-style:none}.chart-template__menu li{min-width:0}.chart-template__apply{min-width:0;flex:1;padding:2px 4px;text-align:left;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.chart-template__apply small{color:#8296a4}.chart-template__menu footer{justify-content:space-between;padding-top:3px;border-top:1px solid #2f3c45}.chart-template__menu footer label{padding:2px 4px;cursor:pointer}.chart-template__menu footer input{display:none}.chart-template__state,.chart-template__error{margin:2px 0;color:#8da0ab}.chart-template__error{color:#ef9b9b}
.chart-template__bar-type{display:grid;grid-template-columns:54px minmax(0,1fr);align-items:center;gap:4px;color:#94a5b0}.chart-template__bar-type select{min-width:0;padding:1px 3px}
</style>
