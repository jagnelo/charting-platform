import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import RunComparisonTable from '@/components/strategy/RunComparisonTable.vue'

describe('RunComparisonTable', () => {
  it('renders comparison rows and lead/lag counts', () => {
    const wrapper = mount(RunComparisonTable, {
      props: {
        currentLabel: 'Current',
        compareLabel: 'Previous',
        rows: [
          { label: 'Net return', current: '12.50%', compare: '8.00%', delta: '+4.50%', deltaValue: 4.5, winner: 'current' },
          { label: 'Drawdown', current: '3.40%', compare: '2.90%', delta: '+0.50%', deltaValue: 0.5, winner: 'compare' },
        ],
      },
    })

    expect(wrapper.text()).toContain('Current')
    expect(wrapper.text()).toContain('vs Previous')
    expect(wrapper.text()).toContain('1 ahead')
    expect(wrapper.text()).toContain('1 behind')
    expect(wrapper.text()).toContain('Net return')
    expect(wrapper.text()).toContain('+4.50%')
  })
})
