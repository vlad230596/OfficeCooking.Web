import { apiRequest } from './client'

export type Repayment = { id?: string; amount: number; repaymentDate: string }
export type Purchase = { id?: string; userId: string; userName?: string; amount: number; description: string; mode: 'offset' | 'separate'; repayments: Repayment[] }
export type CookSettlements = { cookId: string; rowVersion: number; purchases: Purchase[] }
export const getSettlements = (cookId: string, signal?: AbortSignal): Promise<CookSettlements> => apiRequest(`cooks/${encodeURIComponent(cookId)}/settlements`, { signal })
export const saveSettlements = (cookId: string, expectedVersion: number, purchases: Purchase[]): Promise<CookSettlements> => apiRequest(`cooks/${encodeURIComponent(cookId)}/settlements`, { method: 'PUT', body: { expectedVersion, purchases: purchases.map(({ userName: _, ...purchase }) => purchase) } })
