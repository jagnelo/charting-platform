import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

import UnknownToolRecovery from '@/components/workstation/UnknownToolRecovery.vue'

describe('UnknownToolRecovery', () => {
  it('keeps unsupported serialized tool state exportable', async () => {
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined)
    const createObjectURL = vi.fn().mockReturnValue('blob:tool')
    const revokeObjectURL = vi.fn()
    Object.defineProperties(URL, {
      createObjectURL: { configurable: true, value: createObjectURL },
      revokeObjectURL: { configurable: true, value: revokeObjectURL },
    })
    const wrapper = mount(UnknownToolRecovery, { props: { tool: {
      id: 1, instance_key: 'legacy-tool', tool_type: 'legacy_unknown', title: 'Legacy Tool', link_group: 'blue', configuration: { value: 1 }, style: {}, state_schema_version: 1, position: 0,
    } } })

    expect(wrapper.text()).toContain('legacy_unknown')
    await wrapper.find('button').trigger('click')

    expect(createObjectURL).toHaveBeenCalled()
    expect(click).toHaveBeenCalled()
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:tool')
  })
})
