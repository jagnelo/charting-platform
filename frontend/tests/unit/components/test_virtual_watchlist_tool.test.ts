import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import VirtualWatchlistTool from '@/components/workstation/VirtualWatchlistTool.vue'

const rows = [
  { instrumentId: 1, symbol: 'XLK', name: 'Technology', values: { relative_1m: 0.12 } },
  { instrumentId: 2, symbol: 'XLE', name: 'Energy', values: { relative_1m: -0.03 } },
  { instrumentId: 3, symbol: 'XLV', name: 'Health Care', values: { relative_1m: 0.02 } },
]

describe('VirtualWatchlistTool', () => {
  it('filters canonical rows and publishes the selected canonical row', async () => {
    const wrapper = mount(VirtualWatchlistTool, {
      props: {
        label: 'Sectors',
        rows,
        columns: [
          { key: 'symbol', label: 'Symbol', width: '60px' },
          { key: 'name', label: 'Name', width: '1fr' },
        ],
      },
    })

    expect(wrapper.text()).toContain('XLK')
    await wrapper.find('input').setValue('energy')
    expect(wrapper.text()).toContain('XLE')
    expect(wrapper.text()).not.toContain('XLK')

    await wrapper.find('.watchlist__row').trigger('click')
    expect(wrapper.emitted('select')?.[0]).toEqual([rows[1]])
  })

  it('sorts a selected column without losing row identity', async () => {
    const wrapper = mount(VirtualWatchlistTool, {
      props: { label: 'Sectors', rows },
    })
    await wrapper.findAll('.watchlist__header button')[0].trigger('click')
    await wrapper.find('.watchlist__row').trigger('click')
    expect(wrapper.emitted('select')?.[0]?.[0]).toMatchObject({ instrumentId: 3, symbol: 'XLV' })
  })

  it('publishes a persisted visible-column set without allowing an empty table', async () => {
    const wrapper = mount(VirtualWatchlistTool, {
      props: {
        label: 'Sectors', rows,
        columns: [{ key: 'symbol', label: 'Symbol' }, { key: 'name', label: 'Name' }],
      },
    })
    await wrapper.find('.watchlist__columns-button').trigger('click')
    const choices = wrapper.findAll('.watchlist__column-menu input')
    await choices[1].setValue(false)
    expect(wrapper.emitted('update:visibleColumnKeys')?.[0]).toEqual([['symbol']])

    await wrapper.setProps({ visibleColumnKeys: ['symbol'] })
    await choices[0].setValue(false)
    expect(wrapper.emitted('update:visibleColumnKeys')).toHaveLength(1)
  })
})
