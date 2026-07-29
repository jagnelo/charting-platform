<template>
  <section class="unknown-tool" role="alert">
    <strong>Tool recovery required</strong>
    <p>
      This saved tool (<code>{{ tool.tool_type }}</code>) is not available in this workstation build.
      Its serialized state has been retained and can be exported without affecting other tools.
    </p>
    <button type="button" @click="exportTool">Export saved tool state</button>
  </section>
</template>

<script setup lang="ts">
import type { WorkspaceWindowState } from '@/stores/workspace'

const props = defineProps<{ tool: WorkspaceWindowState }>()

function exportTool() {
  const payload = JSON.stringify(props.tool, null, 2)
  const blob = new Blob([payload], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `workstation-tool-${props.tool.instance_key}.json`
  link.click()
  URL.revokeObjectURL(url)
}
</script>

<style scoped>
.unknown-tool { display: grid; align-content: center; gap: 9px; height: 100%; box-sizing: border-box; padding: 18px; color: #ced9e0; background: #1c1715; font: 12px/1.35 "Segoe UI", Arial, sans-serif; }
.unknown-tool strong { color: #f0c482; font-size: 13px; }
.unknown-tool p { margin: 0; color: #b9a995; }
.unknown-tool code { color: #f3d4a3; }
.unknown-tool button { width: max-content; border: 1px solid #876a45; background: #30251d; color: #f2d7af; padding: 4px 8px; font: inherit; cursor: pointer; }
.unknown-tool button:hover { background: #453321; }
</style>
