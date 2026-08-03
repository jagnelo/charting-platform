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
