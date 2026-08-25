import { describe, expect, it } from 'vitest'
import { formatQuantity, formatWholeAmount } from '../src/format'

describe('display formatters', () => {
  it('rounds monetary amounts to whole units without grouping separators', () => {
    expect(formatWholeAmount(12_345.6)).toBe('12346')
    expect(formatWholeAmount(-9_876.4)).toBe('-9876')
    expect(formatWholeAmount(12_345.6)).not.toMatch(/\s/)
  })

  it('keeps fractional vote weights without grouping separators', () => {
    expect(formatQuantity(1_234.5)).toBe('1234,5')
  })
})
