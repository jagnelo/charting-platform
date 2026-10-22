import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import SymbolListTool from '@/components/workstation/SymbolListTool.vue'

describe('SymbolListTool accessibility', () => {
  it('exposes row context and the selected symbol state', async () => {
    const wrapper = mount(SymbolListTool, {
      props: {
        label: 'Sectors',
        symbols: ['XLK', 'XLE'],
        selected: 'XLK',
        comparison: 'SPY',
        descriptions: { XLK: 'Technology', XLE: 'Energy' },
        metrics: { XLK: 0.1234, XLE: null },
      },
    })

    const rows = wrapper.findAll('button.symbol-list__row')
    expect(rows).toHaveLength(2)
    expect(rows[0].attributes('aria-pressed')).toBe('true')
    expect(rows[0].attributes('aria-label')).toBe('XLK, Technology, 12.34%, ratio XLK/SPY')
    expect(rows[1].attributes('aria-pressed')).toBe('false')
    expect(rows[1].attributes('aria-label')).toBe('XLE, Energy, ratio XLE/SPY')

    await rows[1].trigger('click')
    expect(wrapper.emitted('select')).toEqual([['XLE']])
  })
})
