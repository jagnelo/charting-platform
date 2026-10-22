/**
 * Global workstation/chart shortcuts must yield to every kind of editor, including
 * contenteditable code editors and composite controls whose focused descendant is not
 * itself an input element.
 */
export function isEditorTarget(target: EventTarget | null): boolean {
  if (typeof HTMLElement === 'undefined' || !(target instanceof HTMLElement)) return false
  const tag = target.tagName
  if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return true
  if (target.isContentEditable || target.getAttribute('contenteditable') === 'true') return true
  if (target.getAttribute('role') === 'textbox') return true
  return target.closest('[contenteditable="true"], [role="textbox"], [data-editor], [data-code-editor], [data-search-editor]') !== null
}

/**
 * Global workstation shortcuts must yield to controls that own native or ARIA
 * keyboard activation, even when the focused control is not a text editor.
 */
export function isInteractiveTarget(target: EventTarget | null): boolean {
  if (typeof Element === 'undefined' || !(target instanceof Element)) return false
  return target.closest([
    'button',
    'a[href]',
    'summary',
    '[role="button"]',
    '[role="tab"]',
    '[role="menuitem"]',
    '[role="menuitemcheckbox"]',
    '[role="menuitemradio"]',
    '[role="option"]',
    '[role="checkbox"]',
    '[role="radio"]',
    '[role="switch"]',
    '[role="slider"]',
    '[role="spinbutton"]',
    '[role="combobox"]',
  ].join(',')) !== null
}
