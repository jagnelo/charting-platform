<template>
  <span
    ref="triggerRef"
    class="hover-tooltip-anchor"
    @mouseenter="show"
    @focusin="show"
    @mouseleave="hide"
    @focusout="hide"
  >
    <slot />
  </span>

  <Teleport to="body">
    <div
      v-if="tooltip"
      ref="tooltipRef"
      class="hover-tooltip"
      :style="{
        left: `${tooltip.left}px`,
        top: `${tooltip.top}px`,
        maxWidth: `${tooltip.maxWidth}px`,
        maxHeight: `${tooltip.maxHeight}px`,
        visibility: tooltip.visible ? 'visible' : 'hidden',
      }"
      role="tooltip"
    >
      {{ text }}
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { nextTick, onMounted, onUnmounted, ref } from 'vue'

const props = withDefaults(defineProps<{
  text?: string | null
  preferredWidth?: number
}>(), {
  text: '',
  preferredWidth: 240,
})

interface TooltipState {
  left: number
  top: number
  maxWidth: number
  maxHeight: number
  visible: boolean
}

const triggerRef = ref<HTMLElement | null>(null)
const tooltipRef = ref<HTMLElement | null>(null)
const tooltip = ref<TooltipState | null>(null)
let seq = 0

async function show() {
  if (!props.text || !triggerRef.value) return
  const rect = triggerRef.value.getBoundingClientRect()
  const viewportWidth = window.innerWidth
  const viewportHeight = window.innerHeight
  const margin = 12
  const gap = 10
  const minWidth = 160
  const rightSpace = viewportWidth - rect.right - margin
  const leftSpace = rect.left - margin
  const useRightSide = rightSpace >= leftSpace
  const chosenSideSpace = Math.max(useRightSide ? rightSpace : leftSpace, minWidth + gap)
  const maxWidth = Math.max(minWidth, Math.min(props.preferredWidth, chosenSideSpace - gap))
  const maxHeight = Math.max(72, viewportHeight - margin * 2)
  const currentSeq = ++seq

  tooltip.value = {
    left: margin,
    top: margin,
    maxWidth,
    maxHeight,
    visible: false,
  }

  await nextTick()
  if (currentSeq !== seq || !tooltipRef.value) return

  const tooltipWidth = tooltipRef.value.offsetWidth
  const tooltipHeight = tooltipRef.value.offsetHeight
  const unclampedLeft = useRightSide ? rect.right + gap : rect.left - gap - tooltipWidth
  const left = Math.max(margin, Math.min(unclampedLeft, viewportWidth - margin - tooltipWidth))
  const unclampedTop = rect.top + rect.height / 2 - tooltipHeight / 2
  const top = Math.max(margin, Math.min(unclampedTop, viewportHeight - margin - tooltipHeight))

  tooltip.value = {
    left,
    top,
    maxWidth,
    maxHeight,
    visible: true,
  }
}

function hide() {
  seq += 1
  tooltip.value = null
}

onMounted(() => {
  window.addEventListener('resize', hide)
  window.addEventListener('scroll', hide, true)
})

onUnmounted(() => {
  window.removeEventListener('resize', hide)
  window.removeEventListener('scroll', hide, true)
})
</script>

<style scoped>
.hover-tooltip-anchor {
  display: inline-flex;
  align-items: inherit;
}

.hover-tooltip {
  position: fixed;
  z-index: 1000;
  background: #1e1e1e;
  border: 1px solid #2e2e2e;
  border-radius: 4px;
  padding: 7px 9px;
  color: #999;
  font-size: 11px;
  line-height: 1.5;
  overflow-y: auto;
  white-space: pre-line;
  word-break: break-word;
  text-align: left;
  pointer-events: none;
  box-shadow: 0 10px 24px rgba(0, 0, 0, 0.45);
}
</style>
