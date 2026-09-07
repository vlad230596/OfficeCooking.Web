/** Hand-maintained mirror of backend/app/api/contracts until OpenAPI export is available. */
export type UUID = string
export type IsoDate = `${number}-${number}-${number}`
export type EnabledFilter = 'true' | 'false' | 'all'
export type CalculationStatus = 'valid' | 'empty' | 'error'
export type Role = 'viewer' | 'editor' | 'admin'

export type CurrentUser = { id: UUID; name: string; username: string; role: Role }
export type Account = CurrentUser & { authEnabled: boolean }
export type UpdateAccountRequest = {
  username: string | null
  password: string | null
  role: Role
  authEnabled: boolean
}

export type UserContact = {
  position: number
  value: string
}

export type User = {
  id: UUID
  legacyId: number
  name: string
  permanentSale: number
  enabled: boolean
  contacts: UserContact[]
}

export type SaveUserRequest = {
  name: string
  permanentSale: number
  enabled: boolean
  contacts: Array<{ value: string }>
}

export type TemplateSummary = {
  id: UUID
  name: string
  isMultivote: boolean
}

export type TemplateVoteVariant = {
  id: UUID
  position: number
  name: string
  value: number
}

export type TemplateIngredient = {
  id: UUID
  position: number
  name: string
  enabled: boolean
}

export type TemplateDetail = TemplateSummary & {
  voteVariants: TemplateVoteVariant[]
  ingredients: TemplateIngredient[]
}

export type SaveTemplateRequest = {
  name: string
  isMultivote: boolean
  voteVariants: Array<{ name: string; value: number }>
  ingredients: Array<{ name: string; enabled: boolean }>
}

export type SortDirection = 'asc' | 'desc'
export type OrderingMetadata = {
  fields: Array<{ field: string; direction: SortDirection }>
}

export type Page<T> = {
  items: T[]
  page: number
  pageSize: number
  totalItems: number
  totalPages: number
  ordering: OrderingMetadata
}

export type CookSummary = {
  id: UUID
  cookDate: IsoDate
  templateId: UUID | null
  typeSnapshot: string
  memberCount: number
  totalVoteWeight: number
  totalPrice: number | null
  rowVersion: number
}

export type CookVoteVariant = {
  id: UUID
  position: number
  name: string
  value: number
}

export type CookMember = {
  id: UUID
  position: number
  userId: UUID
  userName: string
  active: boolean
  permanentSaleSnapshot: number
  cookVoteVariantIds: UUID[]
  voteWeight: number
  effectiveWeight: number
  charge: number | null
}

export type CookProductPrice = {
  id: UUID
  position: number
  productName: string | null
  expression: string | null
  computedValue: number | null
  calculationStatus: CalculationStatus
  calculationError: string | null
  calculationVersion: number
}

export type CookDetail = {
  id: UUID
  cookDate: IsoDate
  templateId: UUID | null
  typeSnapshot: string
  sale: number
  totalPrice: number | null
  calculationVersion: number
  rowVersion: number
  voteVariants: CookVoteVariant[]
  members: CookMember[]
  productPrices: CookProductPrice[]
}

export type CreateCookMember = {
  position: number
  userId: UUID
  active: boolean
  voteVariantPositions: number[]
}

export type CreateCookProductPrice = {
  position: number
  productName?: string | null
  expression?: string | null
}

export type CreateCookRequest = {
  cookDate: IsoDate
  templateId: UUID
  members: CreateCookMember[]
  productPrices: CreateCookProductPrice[]
}

export type UpdateCookVoteVariant = CookVoteVariant

export type UpdateCookMember = {
  id?: UUID | null
  position: number
  userId: UUID
  active: boolean
  cookVoteVariantIds: UUID[]
}

export type UpdateCookProductPrice = {
  id?: UUID | null
  position: number
  productName?: string | null
  expression?: string | null
}

export type UpdateCookRequest = {
  expectedVersion: number
  cookDate: IsoDate
  voteVariants: UpdateCookVoteVariant[]
  members: UpdateCookMember[]
  productPrices: UpdateCookProductPrice[]
}

export type UserCharge = {
  userId: UUID
  userName: string
  charge: number
}

export type CalculateSelectionRequest = { cookIds: UUID[] }
export type CalculateSelectionResponse = {
  cookIds: UUID[]
  charges: UserCharge[]
  total: number
  positiveCharges: UserCharge[]
  positiveTotal: number
}

export type DraftCookPreviewRequest = {
  cookId?: UUID | null
  voteVariants: Array<{ id: UUID; position: number; value: number }>
  members: Array<{
    position: number
    userId: UUID
    active: boolean
    cookVoteVariantIds: UUID[]
  }>
  productPrices: Array<{
    position: number
    productName?: string | null
    expression?: string | null
  }>
}

export type DraftCookPreviewResponse = {
  totalPrice: number
  members: Array<{ userId: UUID; userName: string; charge: number }>
  calculationVersion: number
}

export type ExpressionPreviewRequest = { expression?: string | null }
export type ExpressionPreviewResponse = {
  expression: string | null
  status: CalculationStatus
  computedValue: number | null
  error: string | null
  calculationVersion: number
}

export type UserBalance = {
  userId: UUID
  userName: string
  positive: number
  negative: number
  cooksCount: number
  cumulativeBalance: number
}

export type BalancesResponse = {
  dateFrom: IsoDate
  dateTo: IsoDate
  items: UserBalance[]
  ordering: OrderingMetadata
}

export type WeekBalance = {
  year: number
  week: number
  display: string
  positive: number
  negative: number
  cooksCount: number
  weeklyDelta: number
  cumulativeBalance: number
  payments: BalancePayment[]
  cooks: BalanceCook[]
}

export type BalancePayment = {
  id: UUID
  paymentDate: IsoDate
  amount: number
  paymentTypeName: string
  comment: string
  source: string
}

export type BalanceCook = {
  id: UUID
  cookDate: IsoDate
  title: string
  amount: number
}

export type UserBalanceDetail = {
  userId: UUID
  userName: string
  dateFrom: IsoDate
  dateTo: IsoDate
  weeks: WeekBalance[]
  paymentTypes: Array<{ id: UUID; name: string }>
  ordering: OrderingMetadata
}

export type CreateBalancePaymentRequest = {
  paymentDate: IsoDate
  amount: number
  paymentTypeId: UUID
  comment: string
}

export type ZenMoneyStatus = 'matched' | 'review' | 'blacklisted' | 'rejected'
export type ZenMoneyAccount = {
  id: string
  title: string
  companyTitle: string | null
  syncIds: string[]
  archived: boolean
}
export type ZenMoneyPaymentType = { id: UUID; name: string }
export type ZenMoneySettings = {
  configured: boolean
  tokenConfigured: boolean
  accountId: string | null
  accountTitle: string | null
  paymentTypeId: UUID | null
  serverTimestamp: number
  lastSyncAt: string | null
  blacklist: string[]
  paymentTypes: ZenMoneyPaymentType[]
}
export type SaveZenMoneySettingsRequest = {
  accessToken?: string
  accountId: string
  accountTitle: string
  paymentTypeId: UUID
  blacklist: string[]
}
export type ZenMoneySyncResult = {
  received: number
  created: number
  updated: number
  matched: number
  review: number
  blacklisted: number
  serverTimestamp: number
}
export type ZenMoneyBulkApproveResult = { approved: number; skipped: number }
export type ZenMoneyTransaction = {
  id: UUID
  transactionDate: IsoDate
  amount: number
  payee: string | null
  originalPayee: string | null
  comment: string | null
  hold: boolean
  deleted: boolean
  status: ZenMoneyStatus
  decisionSource: 'automatic' | 'manual'
  matchReason: string | null
  userId: UUID | null
  userName: string | null
  paymentId: UUID | null
}
