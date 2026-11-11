import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { getSettlements, saveSettlements, type Purchase } from '../api/settlements'
import { listUsers, type CookDetail } from '../api'
import { useAuth } from '../auth'
import { draftKey, readDraft, removeDraft, writeDraft } from '../drafts'
import { formatWholeAmount } from '../format'
import './SettlementEditor.css'

type PurchaseDraft = Omit<Purchase, 'amount' | 'repayments'> & { amount: string; repayments: Array<{ id?: string; amount: string; repaymentDate: string }> }
type Draft = { baseVersion: number; purchases: PurchaseDraft[] }
const toDraft = (purchases: Purchase[]): PurchaseDraft[] => purchases.map(purchase => ({ ...purchase, amount: String(purchase.amount), repayments: purchase.repayments.map(item => ({ ...item, amount: String(item.amount) })) }))
function isDraft(value: unknown): value is Draft {
  if (!value || typeof value !== 'object') return false
  const draft = value as Draft
  return Number.isInteger(draft.baseVersion) && draft.baseVersion > 0 && Array.isArray(draft.purchases) && draft.purchases.every(p => p && typeof p.userId === 'string' && typeof p.amount === 'string' && typeof p.description === 'string' && ['offset', 'separate'].includes(p.mode) && Array.isArray(p.repayments) && p.repayments.every(r => r && typeof r.amount === 'string' && typeof r.repaymentDate === 'string'))
}
const validAmount = (amount: string) => /^\d+$/.test(amount) && Number(amount) > 0 && Number(amount) <= 2_147_483_647
const repaidAmount = (purchase: PurchaseDraft) => purchase.repayments.reduce((sum, repayment) => sum + (Number(repayment.amount) || 0), 0)
const purchaseAmount = (purchase: PurchaseDraft) => Number(purchase.amount) || 0
const remainingAmount = (purchase: PurchaseDraft) => Math.max(0, purchaseAmount(purchase) - repaidAmount(purchase))
const today = () => { const date = new Date(); return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}` }

export function SettlementEditor({ cook }: { cook: CookDetail }) {
  const { user, hasRole } = useAuth()
  return <SettlementForm key={`${user?.id}:${cook.id}`} cook={cook} accountId={user?.id ?? ''} editable={hasRole('editor')} />
}

function SettlementForm({ cook, accountId, editable }: { cook: CookDetail; accountId: string; editable: boolean }) {
  const queryClient = useQueryClient()
  const key = draftKey(accountId, `settlements:${cook.id}`)
  const [draft, setDraft] = useState<Draft | null>(() => editable ? readDraft(key, isDraft) : null)
  const [dirty, setDirty] = useState(Boolean(draft))
  const [storageFailed, setStorageFailed] = useState(false)
  const query = useQuery({ queryKey: ['settlements', cook.id], queryFn: ({ signal }) => getSettlements(cook.id, signal) })
  useEffect(() => { void query.refetch() }, [cook.rowVersion])
  const users = useQuery({ queryKey: ['users', 'all'], queryFn: ({ signal }) => listUsers({ enabled: 'all', signal }) })
  useEffect(() => { if (query.data && !dirty) setDraft({ baseVersion: query.data.rowVersion, purchases: toDraft(query.data.purchases) }) }, [query.data, dirty])
  useEffect(() => { if (dirty && draft) setStorageFailed(!writeDraft(key, draft)) }, [draft, dirty, key])
  const save = useMutation({
    mutationFn: () => saveSettlements(cook.id, draft!.baseVersion, draft!.purchases.map(p => ({ ...p, amount: Number(p.amount), repayments: p.repayments.map(r => ({ ...r, amount: Number(r.amount) })) }))),
    onSuccess: async result => {
      removeDraft(key); setDirty(false); setDraft({ baseVersion: result.rowVersion, purchases: toDraft(result.purchases) }); queryClient.setQueryData(['settlements', cook.id], result)
      await Promise.all([queryClient.invalidateQueries({ queryKey: ['cook', cook.id] }), queryClient.invalidateQueries({ queryKey: ['cooks'] }), queryClient.invalidateQueries({ queryKey: ['balances'] }), queryClient.invalidateQueries({ queryKey: ['balance-detail'] })])
    },
  })
  const change = (purchases: PurchaseDraft[]) => { setDirty(true); setDraft({ baseVersion: draft?.baseVersion ?? cook.rowVersion, purchases }); save.reset() }
  const update = (index: number, values: Partial<PurchaseDraft>) => change(draft!.purchases.map((p, i) => i === index ? { ...p, ...values } : p))
  const stale = !!draft && draft.baseVersion !== Math.max(cook.rowVersion, query.data?.rowVersion ?? 0)
  const invalid = draft?.purchases.some(p => !p.userId || !validAmount(p.amount) || p.repayments.some(r => !validAmount(r.amount) || !/^\d{4}-\d{2}-\d{2}$/.test(r.repaymentDate)) || p.repayments.reduce((sum, r) => sum + Number(r.amount), 0) > Number(p.amount))
  const purchases = draft?.purchases ?? []
  const bought = purchases.reduce((sum, purchase) => sum + purchaseAmount(purchase), 0)
  const returned = purchases.reduce((sum, purchase) => sum + repaidAmount(purchase), 0)
  let owed = 0
  let offset = 0
  const offsetByUser = new Map<string, number>()
  const chargeByUser = new Map(cook.members.map(member => [member.userId, member.charge]))
  const appliedByRow = purchases.map(purchase => {
    const remaining = remainingAmount(purchase)
    if (purchase.mode === 'separate') { owed += remaining; return 0 }
    const charge = chargeByUser.get(purchase.userId)
    const before = offsetByUser.get(purchase.userId) ?? 0
    offsetByUser.set(purchase.userId, before + remaining)
    if (charge === null || !purchase.userId) return null
    const applied = Math.min(remaining, Math.max(0, (charge ?? 0) - before))
    offset += applied
    owed += remaining - applied
    return applied
  })
  const partialTotals = appliedByRow.some(value => value === null)
  return <section id="cook-settlements" className="settlement-editor" aria-labelledby="settlement-title">
    <header><div><span className="eyebrow">Взаиморасчёты</span><h2 id="settlement-title">Купили за свои</h2></div>{editable && <button type="button" className="button" disabled={!draft || save.isPending} onClick={() => change([...draft!.purchases, { userId: '', amount: '', description: '', mode: 'offset', repayments: [] }])}>Добавить покупку</button>}</header>
    <p>Сумма покупки уже должна входить в расходы готовки. Здесь укажите, кто её оплатил. Стоимость порций от этого не меняется.</p>
    <div className="settlement-metrics" aria-label="Итоги взаиморасчётов"><div><small>Купили за свои</small><strong>{formatWholeAmount(bought)}</strong></div><div><small>В зачёт оплаты</small><strong>{partialTotals ? '—' : formatWholeAmount(offset)}</strong></div><div><small>Уже вернули переводом</small><strong>{formatWholeAmount(returned)}</strong></div><div className={owed > 0 ? 'settlement-metrics__owed' : ''}><small>Осталось вернуть</small><strong>{partialTotals ? '—' : formatWholeAmount(owed)}</strong></div></div>
    {query.isPending && <p role="status">Загружаем взаиморасчёты…</p>}
    {query.isError && <p role="alert">Не удалось загрузить взаиморасчёты. <button type="button" onClick={() => void query.refetch()}>Повторить</button></p>}
    {users.isError && <p role="alert">Не удалось загрузить участников. <button type="button" onClick={() => void users.refetch()}>Повторить</button></p>}
    {storageFailed && <p role="alert">Браузер не смог сохранить черновик. Не обновляйте страницу до сохранения.</p>}
    {stale && dirty && <p role="alert">Готовка изменилась. Черновик нельзя отправить поверх новой версии. <button type="button" onClick={() => { removeDraft(key); setDirty(false); void query.refetch() }}>Отбросить черновик и загрузить сохранённое</button></p>}
    <form onSubmit={event => { event.preventDefault(); if (dirty && !invalid && !stale && !save.isPending) save.mutate() }}>
      {draft?.purchases.map((purchase, index) => {
        const repaid = repaidAmount(purchase)
        const charge = chargeByUser.get(purchase.userId)
        const net = (charge ?? 0) - (offsetByUser.get(purchase.userId) ?? 0)
        const applied = appliedByRow[index]
        return <fieldset key={index} disabled={!editable || save.isPending} className="settlement-purchase"><legend>Покупка {index + 1}</legend><div className="settlement-fields">
          <label>Кто оплатил<select required value={purchase.userId} onChange={e => update(index, { userId: e.target.value })}><option value="">Выберите участника</option>{users.data?.map(u => <option key={u.id} value={u.id}>{u.name}</option>)}{purchase.userId && !users.data?.some(u => u.id === purchase.userId) && <option value={purchase.userId}>{purchase.userName ?? purchase.userId}</option>}</select></label>
          <label>Сумма, ₽<input required min="1" step="1" type="number" value={purchase.amount} onChange={e => update(index, { amount: e.target.value })} /></label>
          <label>Как компенсировать<select value={purchase.mode} onChange={e => update(index, { mode: e.target.value as Purchase['mode'] })}><option value="offset">Уменьшить оплату за готовку</option><option value="separate">Вернуть отдельным переводом</option></select></label>
          <label>Что куплено<input maxLength={1000} value={purchase.description} onChange={e => update(index, { description: e.target.value })} /></label>
        </div>
        <div className="settlement-flow"><span>Купил <b>{formatWholeAmount(purchaseAmount(purchase))}</b></span><span aria-hidden="true">→</span>{purchase.mode === 'offset' && <span>В зачёт оплаты <b>{applied === null ? '—' : formatWholeAmount(applied)}</b></span>}<span>{purchase.mode === 'offset' ? 'Вернуть сверх зачёта' : 'Вернуть отдельно'} <b>{applied === null ? '—' : formatWholeAmount(remainingAmount(purchase) - applied)}</b></span><span className="settlement-status">{repaid === 0 ? 'Переводов пока нет' : `Возвращено ${formatWholeAmount(repaid)}`}</span></div>
        {purchase.userId && <p className="settlement-person-total">Итог участника по этой готовке: {charge === null ? 'ошибка расчёта порции' : net < 0 ? `вернуть ${formatWholeAmount(-net)} сверх зачёта` : `к оплате ${formatWholeAmount(net)}`}.</p>}
        {purchase.repayments.map((repayment, rIndex) => <div className="settlement-repayment" key={rIndex}><label>Дата фактического перевода<input required type="date" value={repayment.repaymentDate} onChange={e => update(index, { repayments: purchase.repayments.map((r, i) => i === rIndex ? { ...r, repaymentDate: e.target.value } : r) })} /></label><label>Уже вернули, ₽<input required type="number" min="1" step="1" value={repayment.amount} onChange={e => update(index, { repayments: purchase.repayments.map((r, i) => i === rIndex ? { ...r, amount: e.target.value } : r) })} /></label>{editable && <button type="button" onClick={() => update(index, { repayments: purchase.repayments.filter((_, i) => i !== rIndex) })}>Удалить перевод</button>}</div>)}
        {repaid > Number(purchase.amount) && <p role="alert">Возвраты не могут превышать сумму покупки.</p>}
        {editable && <div className="settlement-actions"><button type="button" onClick={() => update(index, { repayments: [...purchase.repayments, { amount: '', repaymentDate: today() }] })}>Записать выполненный перевод</button><button type="button" onClick={() => change(draft.purchases.filter((_, i) => i !== index))}>Удалить покупку</button></div>}
      </fieldset>})}
      {draft?.purchases.length === 0 && <p>Покупок за свои деньги пока нет.</p>}
      {editable && <button className="button" type="submit" disabled={!draft || !dirty || invalid || stale || save.isPending || !query.data}>{save.isPending ? 'Сохраняем…' : 'Сохранить взаиморасчёты'}</button>}
      {save.isSuccess && <p role="status">Взаиморасчёты сохранены.</p>}{save.isError && <p role="alert">Не удалось сохранить: {save.error.message}. Черновик сохранён в браузере.</p>}
      {dirty && !storageFailed && <p className="settlement-draft" role="status">Черновик сохраняется в этом браузере. Для учёта в статистике нажмите «Сохранить взаиморасчёты».</p>}
    </form>
  </section>
}
