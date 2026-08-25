const wholeAmountFormatter = new Intl.NumberFormat('ru-RU', {
  maximumFractionDigits: 0,
  useGrouping: false,
})

const quantityFormatter = new Intl.NumberFormat('ru-RU', {
  maximumFractionDigits: 2,
  useGrouping: false,
})

export const formatWholeAmount = (value: number): string => wholeAmountFormatter.format(value)
export const formatQuantity = (value: number): string => quantityFormatter.format(value)
