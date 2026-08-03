import { describe, expect, it } from 'vitest'

import { isEditorTarget } from '@/lib/workstation/keyboard'

describe('workstation keyboard target detection', () => {
  it('recognizes native editors and contenteditable/code/search surfaces', () => {
    const input = document.createElement('input')
    const code = document.createElement('div')
    code.setAttribute('data-code-editor', 'true')
    const contentEditable = document.createElement('span')
    contentEditable.setAttribute('contenteditable', 'true')
    const codeChild = document.createElement('span')
    code.appendChild(codeChild)
    const search = document.createElement('div')
    search.setAttribute('role', 'textbox')

    expect(isEditorTarget(input)).toBe(true)
    expect(isEditorTarget(codeChild)).toBe(true)
    expect(isEditorTarget(contentEditable)).toBe(true)
    expect(isEditorTarget(search)).toBe(true)
  })

  it('does not suppress shortcuts for chart surfaces', () => {
    const canvas = document.createElement('canvas')
    expect(isEditorTarget(canvas)).toBe(false)
    expect(isEditorTarget(null)).toBe(false)
  })
})
