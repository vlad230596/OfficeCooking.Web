import { afterEach, describe, expect, it, vi } from 'vitest'
import { draftKey, readDraft, removeDraft, writeDraft } from '../src/drafts'

afterEach(() => { vi.restoreAllMocks(); window.localStorage.clear() })

describe('local drafts', () => {
  const isText = (value: unknown): value is string => typeof value === 'string'

  it('rejects malformed and incompatible data', () => {
    window.localStorage.setItem('broken', '{')
    window.localStorage.setItem('wrong', '{"oldSchema":true}')
    expect(readDraft('broken', isText)).toBeNull()
    expect(readDraft('wrong', isText)).toBeNull()
    expect(readDraft('missing', isText)).toBeNull()
  })

  it('survives browsers denying storage access or exhausting its quota', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new Error('denied') })
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('quota') })
    vi.spyOn(Storage.prototype, 'removeItem').mockImplementation(() => { throw new Error('denied') })
    expect(readDraft('draft', isText)).toBeNull()
    expect(writeDraft('draft', 'text')).toBe(false)
    expect(removeDraft('draft')).toBe(false)
  })

  it('separates account and form identifiers', () => {
    expect(draftKey('one', 'cook:new')).not.toBe(draftKey('two', 'cook:new'))
    expect(draftKey('one', 'cook:new')).not.toBe(draftKey('one', 'cook:existing'))
  })
})
