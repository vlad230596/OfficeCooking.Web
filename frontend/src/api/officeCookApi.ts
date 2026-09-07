import { apiRequest } from './client'
import type {
  BalancesResponse,
  Account,
  CurrentUser,
  CalculateSelectionRequest,
  CalculateSelectionResponse,
  CookDetail,
  CookSummary,
  CreateCookRequest,
  CreateBalancePaymentRequest,
  DraftCookPreviewRequest,
  DraftCookPreviewResponse,
  EnabledFilter,
  ExpressionPreviewRequest,
  ExpressionPreviewResponse,
  IsoDate,
  Page,
  SaveTemplateRequest,
  SaveUserRequest,
  TemplateDetail,
  TemplateSummary,
  UpdateCookRequest,
  UpdateAccountRequest,
  User,
  UserBalanceDetail,
  UUID,
  SaveZenMoneySettingsRequest,
  ZenMoneyAccount,
  ZenMoneyBulkApproveResult,
  ZenMoneySettings,
  ZenMoneyStatus,
  ZenMoneySyncResult,
  ZenMoneyTransaction,
} from './contracts'

type WithSignal = { signal?: AbortSignal }

export function login(username: string, password: string): Promise<CurrentUser> {
  return apiRequest('auth/login', { method: 'POST', body: { username, password } })
}

export function getCurrentUser({ signal }: WithSignal = {}): Promise<CurrentUser> {
  return apiRequest('auth/me', { signal })
}

export function logout(): Promise<void> {
  return apiRequest('auth/logout', { method: 'POST', body: {} })
}

export function listAccounts({ signal }: WithSignal = {}): Promise<Account[]> {
  return apiRequest('auth/accounts', { signal })
}

export function updateAccount(userId: UUID, request: UpdateAccountRequest): Promise<Account> {
  return apiRequest(`auth/accounts/${encodeURIComponent(userId)}`, { method: 'PUT', body: request })
}

export type ListUsersOptions = WithSignal & { enabled?: EnabledFilter }
export type ListCooksOptions = WithSignal & {
  dateFrom: IsoDate
  dateTo: IsoDate
  templateId?: UUID
  page?: number
  pageSize?: number
}
export type BalanceRangeOptions = WithSignal & { dateFrom: IsoDate; dateTo: IsoDate }
export type ListBalancesOptions = BalanceRangeOptions & { nonZeroOnly?: boolean }

export function listUsers({ enabled = 'all', signal }: ListUsersOptions = {}): Promise<User[]> {
  return apiRequest(withSearchParams('users', { enabled }), { signal })
}

export function createUser(request: SaveUserRequest, { signal }: WithSignal = {}): Promise<User> {
  return apiRequest('users', { method: 'POST', body: request, signal })
}

export function updateUser(userId: UUID, request: SaveUserRequest, { signal }: WithSignal = {}): Promise<User> {
  return apiRequest(`users/${encodeURIComponent(userId)}`, { method: 'PUT', body: request, signal })
}

export function listTemplates({ signal }: WithSignal = {}): Promise<TemplateSummary[]> {
  return apiRequest('templates', { signal })
}

export function getTemplate(templateId: UUID, { signal }: WithSignal = {}): Promise<TemplateDetail> {
  return apiRequest(`templates/${encodeURIComponent(templateId)}`, { signal })
}

export function createTemplate(request: SaveTemplateRequest, { signal }: WithSignal = {}): Promise<TemplateDetail> {
  return apiRequest('templates', { method: 'POST', body: request, signal })
}

export function updateTemplate(templateId: UUID, request: SaveTemplateRequest, { signal }: WithSignal = {}): Promise<TemplateDetail> {
  return apiRequest(`templates/${encodeURIComponent(templateId)}`, { method: 'PUT', body: request, signal })
}

export function listCooks({ dateFrom, dateTo, templateId, page = 1, pageSize = 50, signal }: ListCooksOptions): Promise<Page<CookSummary>> {
  return apiRequest(withSearchParams('cooks', { dateFrom, dateTo, templateId, page, pageSize }), { signal })
}

export function getCook(cookId: UUID, { signal }: WithSignal = {}): Promise<CookDetail> {
  return apiRequest(`cooks/${encodeURIComponent(cookId)}`, { signal })
}

export function createCook(request: CreateCookRequest, { signal }: WithSignal = {}): Promise<CookDetail> {
  return apiRequest('cooks', { method: 'POST', body: request, signal })
}

export function updateCook(cookId: UUID, request: UpdateCookRequest, { signal }: WithSignal = {}): Promise<CookDetail> {
  return apiRequest(`cooks/${encodeURIComponent(cookId)}`, { method: 'PUT', body: request, signal })
}

export function calculateCookSelection(request: CalculateSelectionRequest, { signal }: WithSignal = {}): Promise<CalculateSelectionResponse> {
  return apiRequest('cooks/calculate-selection', { method: 'POST', body: request, signal })
}

export function previewCook(request: DraftCookPreviewRequest, { signal }: WithSignal = {}): Promise<DraftCookPreviewResponse> {
  return apiRequest('cooks/preview', { method: 'POST', body: request, signal })
}

export function previewExpression(request: ExpressionPreviewRequest, { signal }: WithSignal = {}): Promise<ExpressionPreviewResponse> {
  return apiRequest('calculations/expressions/preview', { method: 'POST', body: request, signal })
}

export function listBalances({ dateFrom, dateTo, nonZeroOnly = false, signal }: ListBalancesOptions): Promise<BalancesResponse> {
  return apiRequest(withSearchParams('balances', { dateFrom, dateTo, nonZeroOnly }), { signal })
}

export function getUserBalance(userId: UUID, { dateFrom, dateTo, signal }: BalanceRangeOptions): Promise<UserBalanceDetail> {
  return apiRequest(withSearchParams(`balances/users/${encodeURIComponent(userId)}`, { dateFrom, dateTo }), { signal })
}

export function deleteUserPayment(userId: UUID, paymentId: UUID): Promise<void> {
  return apiRequest(`balances/users/${encodeURIComponent(userId)}/payments/${encodeURIComponent(paymentId)}/delete`, { method: 'POST', body: {} })
}

export function createUserPayment(userId: UUID, request: CreateBalancePaymentRequest): Promise<void> {
  return apiRequest(`balances/users/${encodeURIComponent(userId)}/payments`, { method: 'POST', body: request })
}

export function getZenMoneySettings({ signal }: WithSignal = {}): Promise<ZenMoneySettings> {
  return apiRequest('zenmoney/settings', { signal })
}

export function listZenMoneyAccounts(accessToken?: string): Promise<ZenMoneyAccount[]> {
  return apiRequest('zenmoney/settings/accounts', {
    method: 'POST', body: accessToken ? { accessToken } : {},
  })
}

export function saveZenMoneySettings(request: SaveZenMoneySettingsRequest): Promise<ZenMoneySettings> {
  return apiRequest('zenmoney/settings', { method: 'PUT', body: request })
}

export function syncZenMoney(): Promise<ZenMoneySyncResult> {
  return apiRequest('zenmoney/sync', { method: 'POST', body: {} })
}

export function approveAllMatchedZenMoneyTransactions(): Promise<ZenMoneyBulkApproveResult> {
  return apiRequest('zenmoney/transactions/approve-matched', { method: 'POST', body: {} })
}

export function listZenMoneyTransactions(
  { includeBlacklisted = false, status, signal }: WithSignal & { includeBlacklisted?: boolean; status?: ZenMoneyStatus } = {},
): Promise<ZenMoneyTransaction[]> {
  return apiRequest(withSearchParams('zenmoney/transactions', { includeBlacklisted, status }), { signal })
}

export function decideZenMoneyTransaction(
  transactionId: UUID,
  action: 'assign' | 'approve' | 'reject' | 'retry',
  userId?: UUID,
): Promise<ZenMoneyTransaction> {
  return apiRequest(`zenmoney/transactions/${encodeURIComponent(transactionId)}`, {
    method: 'PATCH', body: { action, ...(userId ? { userId } : {}) },
  })
}

function withSearchParams(path: string, values: Record<string, string | number | boolean | undefined>): string {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(values)) {
    if (value !== undefined) search.set(key, String(value))
  }
  const query = search.toString()
  return query ? `${path}?${query}` : path
}
