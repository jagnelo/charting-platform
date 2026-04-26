import { describe, expect, it } from 'vitest'

import { crosshairPlugin } from '@/lib/uplot/plugins/crosshair'

describe('crosshairPlugin', () => {
  it('exposes a setCursor hook', () => {
    const plugin = crosshairPlugin()
    expect(plugin.hooks?.setCursor).toHaveLength(1)
  })

  it('setCursor hook is callable', () => {
    const plugin = crosshairPlugin()
    expect(() => plugin.hooks?.setCursor?.[0]({} as any)).not.toThrow()
  })
})

