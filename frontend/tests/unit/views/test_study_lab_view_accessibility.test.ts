import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

const { routerPush } = vi.hoisted(() => ({ routerPush: vi.fn() }))

vi.mock('vue-router', () => ({ useRouter: () => ({ push: routerPush }) }))
vi.mock('@/lib/api', () => ({ api: { get: vi.fn(), post: vi.fn() } }))

import StudyLabView from '@/views/StudyLabView.vue'

describe('StudyLabView accessibility', () => {
  it('names lifecycle controls and scopes its study controls', () => {
    const wrapper = mount(StudyLabView)

    expect(wrapper.get('header button').attributes('type')).toBe('button')
    expect(wrapper.get('header button').attributes('aria-label')).toBe('Back to workstation')
    expect(wrapper.get('section.study-lab__controls').attributes('aria-label')).toBe('Study controls')
    expect(wrapper.get('button[aria-label="Validate study"]').attributes('type')).toBe('button')
    expect(wrapper.get('button[aria-label="Save and run study"]').attributes('type')).toBe('button')
  })
})
