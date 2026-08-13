import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import WorkstationGlyph from '@/components/workstation/WorkstationGlyph.vue'

describe('WorkstationGlyph', () => {
  it.each(['close', 'chevron-down', 'reset', 'move-left', 'move-right', 'move-up', 'move-down', 'delete', 'pause', 'resume', 'repeat'] as const)('renders deterministic %s geometry without text glyphs', kind => {
    const wrapper = mount(WorkstationGlyph, { props: { kind } })
    expect(wrapper.find('.workstation-glyph').classes()).toContain(`workstation-glyph--${kind}`)
    expect(wrapper.text()).toBe('')
    expect(wrapper.attributes('aria-hidden')).toBe('true')
  })

  it.each(['visible', 'hidden', 'duplicate', 'copy', 'copy-linked', 'promote', 'edit', 'export', 'plus', 'settings', 'chevron-up', 'warning', 'list', 'scan', 'apply'] as const)('renders deterministic extended %s geometry', kind => {
    const wrapper = mount(WorkstationGlyph, { props: { kind } })
    expect(wrapper.find('.workstation-glyph').classes()).toContain(`workstation-glyph--${kind}`)
    expect(wrapper.text()).toBe('')
  })
})
