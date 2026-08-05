export interface PopoutGeometry {
  left: number
  top: number
  width: number
  height: number
}

export interface PopoutScreen {
  availLeft?: number
  availTop?: number
}

const DEFAULT_GEOMETRY: PopoutGeometry = { left: 80, top: 80, width: 1100, height: 760 }
const MIN_WIDTH = 320
const MIN_HEIGHT = 240

function finite(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value)
}

export function readPopoutGeometry(style: Record<string, unknown> | null | undefined, screen?: PopoutScreen): PopoutGeometry {
  const fallback = {
    ...DEFAULT_GEOMETRY,
    left: finite(screen?.availLeft) ? screen.availLeft + DEFAULT_GEOMETRY.left : DEFAULT_GEOMETRY.left,
    top: finite(screen?.availTop) ? screen.availTop + DEFAULT_GEOMETRY.top : DEFAULT_GEOMETRY.top,
  }
  const candidate = style?.popout
  if (!candidate || typeof candidate !== 'object') return fallback
  const value = candidate as Record<string, unknown>
  return {
    left: finite(value.left) ? Math.round(value.left) : fallback.left,
    top: finite(value.top) ? Math.round(value.top) : fallback.top,
    width: finite(value.width) ? Math.max(MIN_WIDTH, Math.round(value.width)) : fallback.width,
    height: finite(value.height) ? Math.max(MIN_HEIGHT, Math.round(value.height)) : fallback.height,
  }
}

export function popoutWindowFeatures(geometry: PopoutGeometry): string {
  const value = readPopoutGeometry({ popout: geometry })
  return `popup=yes,width=${value.width},height=${value.height},left=${value.left},top=${value.top},resizable=yes,scrollbars=no`
}

export function capturePopoutGeometry(popup: Window): PopoutGeometry | null {
  const values = {
    left: Number(popup.screenX),
    top: Number(popup.screenY),
    width: Number(popup.outerWidth),
    height: Number(popup.outerHeight),
  }
  return Object.values(values).every(Number.isFinite) ? readPopoutGeometry({ popout: values }) : null
}
