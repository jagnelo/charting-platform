/**
 * Enhanced crosshair plugin with OHLCV tooltip.
 */
import type uPlot from 'uplot'

export function crosshairPlugin(): uPlot.Plugin {
  return {
    hooks: {
      setCursor: [
        (u: uPlot) => {
          // The built-in cursor handles crosshair rendering.
          // This hook can be extended for custom tooltip DOM updates.
        },
      ],
    },
  }
}
