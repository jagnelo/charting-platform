export interface PopoutGeometry {
  left: number
  top: number
  width: number
  height: number
}

export interface PopoutScreen {
  availLeft?: number
  availTop?: number
  availWidth?: number
  availHeight?: number
}

const DEFAULT_GEOMETRY: PopoutGeometry = { left: 80, top: 80, width: 1100, height: 760 }
const MIN_WIDTH = 320
const MIN_HEIGHT = 240

function finite(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value)
}

function hasBounds(screen: PopoutScreen): screen is Required<PopoutScreen> {
  return finite(screen.availLeft)
    && finite(screen.availTop)
    && finite(screen.availWidth)
    && finite(screen.availHeight)
    && screen.availWidth > 0
    && screen.availHeight > 0
}

/**
 * A window is considered visible when at least a small portion of its usable
 * rectangle intersects a known display. This deliberately allows a window to
 * straddle two monitors while rejecting a saved display that is no longer
 * available after a monitor disconnect.
 */
export function geometryVisibleOnAnyScreen(geometry: PopoutGeometry, screens: PopoutScreen[]): boolean {
  return screens.filter(hasBounds).some(screen => {
    const right = geometry.left + geometry.width
    const bottom = geometry.top + geometry.height
    const screenRight = screen.availLeft + screen.availWidth
    const screenBottom = screen.availTop + screen.availHeight
    return Math.min(right, screenRight) > Math.max(geometry.left, screen.availLeft)
      && Math.min(bottom, screenBottom) > Math.max(geometry.top, screen.availTop)
  })
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

/**
 * Recover a saved pop-out only when the browser has supplied a complete
 * multi-screen inventory. If the inventory is unavailable (older browsers or
 * denied Window Management permission), the persisted geometry remains
 * authoritative so a valid secondary-monitor placement is never destroyed by
 * a guessed single-screen fallback.
 */
export function recoverPopoutGeometry(
  style: Record<string, unknown> | null | undefined,
  screens: PopoutScreen[] | null | undefined,
  fallbackScreen?: PopoutScreen,
): PopoutGeometry {
  const candidate = readPopoutGeometry(style, fallbackScreen)
  // Treat the inventory as authoritative only when every reported display has
  // complete usable bounds. Filtering malformed entries would make a partial
  // response look complete and could move a valid window based on incomplete
  // Window Management API data.
  const usableScreens = screens && screens.length > 0 && screens.every(hasBounds) ? screens : null
  if (!usableScreens || geometryVisibleOnAnyScreen(candidate, usableScreens)) return candidate
  return readPopoutGeometry(null, fallbackScreen)
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
