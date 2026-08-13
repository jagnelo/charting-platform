import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import PythonSourceEditor from '@/components/workstation/PythonSourceEditor.vue'

describe('PythonSourceEditor', () => {
  it('offers context-aware unified SDK suggestions and inserts the selected expression', async () => {
    const wrapper = mount(PythonSourceEditor, { props: { modelValue: '', ariaLabel: 'Python source' } })
    const editor = wrapper.find('[aria-label="Python source"]')
    await wrapper.setProps({ modelValue: 'market.' })
    ;(editor.element as HTMLTextAreaElement).setSelectionRange(7, 7)
    ;(editor.element as HTMLTextAreaElement).focus()
    await editor.trigger('keyup')
    expect(editor.element.tagName).toBe('TEXTAREA')
    expect(editor.attributes('role')).toBeUndefined()
    expect(editor.attributes('aria-haspopup')).toBe('listbox')
    expect(editor.attributes('aria-expanded')).toBe('true')
    expect(editor.attributes('aria-controls')).toBeTruthy()
    expect(wrapper.find(`#${editor.attributes('aria-controls')}`).attributes('role')).toBe('listbox')
    expect(wrapper.find('[aria-label="Python source SDK suggestions"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('market.close()')
    await wrapper.find('[aria-label="Python source SDK suggestions"] button').trigger('mousedown')
    const nextValue = wrapper.emitted('update:modelValue')?.at(-1)?.[0]
    expect(nextValue).toBe('market.close()')
    await wrapper.setProps({ modelValue: nextValue })
    expect((editor.element as HTMLTextAreaElement).value).toContain('market.close()')
  })

  it('normalizes line endings and trailing whitespace without changing code semantics', async () => {
    const wrapper = mount(PythonSourceEditor, { props: { modelValue: 'x = 1  \r\n\r\n', ariaLabel: 'Python source' } })
    await wrapper.find('[aria-label="Normalize Python source"]').trigger('click')
    expect(wrapper.emitted('update:modelValue')?.at(-1)?.[0]).toBe('x = 1\n')
  })

  it('supports keyboard selection and completion without stealing editor navigation when suggestions are closed', async () => {
    const wrapper = mount(PythonSourceEditor, { props: { modelValue: 'market.', ariaLabel: 'Python source' } })
    const editor = wrapper.find('[aria-label="Python source"]')
    ;(editor.element as HTMLTextAreaElement).setSelectionRange(7, 7)
    ;(editor.element as HTMLTextAreaElement).focus()
    await editor.trigger('keyup')
    expect(wrapper.find('[aria-activedescendant="Python-source-suggestion-0"]').exists()).toBe(true)

    await editor.trigger('keydown', { key: 'ArrowDown' })
    expect(wrapper.find('[aria-activedescendant="Python-source-suggestion-1"]').exists()).toBe(true)
    await editor.trigger('keydown', { key: 'Enter' })
    expect(wrapper.emitted('update:modelValue')?.at(-1)?.[0]).toBe('market.ohlcv()')

    await editor.trigger('keydown', { key: 'Escape' })
    expect(wrapper.find('[role="listbox"]').exists()).toBe(false)
    expect(editor.attributes('aria-expanded')).toBe('false')
    expect(editor.attributes('aria-controls')).toBeUndefined()
  })

  it('keeps suggestion popup identifiers unique across linked editor instances', async () => {
    const first = mount(PythonSourceEditor, { props: { modelValue: 'market.', ariaLabel: 'Python source' } })
    const second = mount(PythonSourceEditor, { props: { modelValue: 'market.', ariaLabel: 'Python source' } })
    await first.find('textarea').trigger('focus')
    await first.find('textarea').trigger('keyup')
    await second.find('textarea').trigger('focus')
    await second.find('textarea').trigger('keyup')
    const firstId = first.find('textarea').attributes('aria-controls')
    const secondId = second.find('textarea').attributes('aria-controls')
    expect(firstId).toBeTruthy()
    expect(secondId).toBeTruthy()
    expect(firstId).not.toBe(secondId)
    first.unmount()
    second.unmount()
  })
})
