import { describe, expect, it } from 'vitest'

import { isEditorTarget, isInteractiveTarget } from '@/lib/workstation/keyboard'

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

  it('yields global shortcuts to native and ARIA interactive controls', () => {
    const button = document.createElement('button')
    const buttonChild = document.createElement('span')
    button.appendChild(buttonChild)
    const tab = document.createElement('div')
    tab.setAttribute('role', 'tab')
    const menuItem = document.createElement('div')
    menuItem.setAttribute('role', 'menuitem')
    const option = document.createElement('div')
    option.setAttribute('role', 'option')
    const canvas = document.createElement('canvas')

    expect(isInteractiveTarget(buttonChild)).toBe(true)
    expect(isInteractiveTarget(tab)).toBe(true)
    expect(isInteractiveTarget(menuItem)).toBe(true)
    expect(isInteractiveTarget(option)).toBe(true)
    expect(isInteractiveTarget(canvas)).toBe(false)
    expect(isInteractiveTarget(null)).toBe(false)
  })
})
