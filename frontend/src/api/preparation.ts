import { apiRequest } from './client'

export type PreparationOption = { key: string; name: string; values: string[]; batchSize: number }
export type PreparationGroup = { userId: string; quantity: number; choices: Record<string, string> }
export type PreparationPlan = { options: PreparationOption[]; groups: PreparationGroup[] }
export type PreparationWarning = { optionKey: string; optionName: string; value: string; quantity: number; batchSize: number }
export type TemplatePreparation = PreparationPlan & { version: number }
export type CookPreparation = PreparationPlan & { rowVersion: number; warnings: PreparationWarning[] }

export const getTemplatePreparation = (id: string, signal?: AbortSignal) => apiRequest<TemplatePreparation>(`templates/${encodeURIComponent(id)}/preparation`, { signal })
export const saveTemplatePreparation = (id: string, plan: PreparationPlan, expectedVersion: number) => apiRequest<TemplatePreparation>(`templates/${encodeURIComponent(id)}/preparation`, { method: 'PUT', body: { ...plan, expectedVersion } })
export const getCookPreparation = (id: string, signal?: AbortSignal) => apiRequest<CookPreparation>(`cooks/${encodeURIComponent(id)}/preparation`, { signal })
export const saveCookPreparation = (id: string, plan: PreparationPlan, expectedVersion: number) => apiRequest<CookPreparation>(`cooks/${encodeURIComponent(id)}/preparation`, { method: 'PUT', body: { ...plan, expectedVersion } })
