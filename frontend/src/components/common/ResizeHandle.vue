<template>
  <div
    class="resize-handle"
    :class="[`resize-handle--${direction}`, { dragging }]"
    @pointerdown.prevent="onPointerDown"
  />
</template>

<script setup lang="ts">
import { ref } from 'vue'

const props = defineProps<{
  direction: 'horizontal' | 'vertical'
  min?: number
  max?: number
  value: number
  inverted?: boolean
}>()

const emit = defineEmits<{
  change: [value: number]
}>()

const dragging = ref(false)

function onPointerDown(e: PointerEvent) {
  e.preventDefault()
  dragging.value = true
  const startPos = props.direction === 'horizontal' ? e.clientX : e.clientY
  const startVal = props.value

  const onMove = (ev: PointerEvent) => {
    const raw = props.direction === 'horizontal' ? ev.clientX - startPos : ev.clientY - startPos
    const delta = props.inverted ? -raw : raw
    let next = startVal + delta
    if (props.min != null) next = Math.max(props.min, next)
    if (props.max != null) next = Math.min(props.max, next)
    emit('change', next)
  }

  const onUp = () => {
    dragging.value = false
    window.removeEventListener('pointermove', onMove)
    window.removeEventListener('pointerup', onUp)
  }

  window.addEventListener('pointermove', onMove)
  window.addEventListener('pointerup', onUp)
}
</script>

<style scoped>
.resize-handle {
  flex-shrink: 0;
  background: transparent;
  z-index: 10;
}
.resize-handle--horizontal {
  width: 4px;
  cursor: col-resize;
}
.resize-handle--vertical {
  height: 4px;
  cursor: row-resize;
}
.resize-handle:hover,
.resize-handle.dragging {
  background: #2a6bff44;
}
</style>
