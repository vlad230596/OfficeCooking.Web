import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { createUserAdjustment, createUserPayment, deleteUserPayment, getUserBalance, listBalances } from '../api'
import type { BalancePayment, IsoDate, UserBalance } from '../api'
import { useAuth } from '../auth'
import { EmptyState, ErrorState, LoadingState } from '../components/AsyncState'
import { PageIntro } from '../components/PageIntro'
import { formatWholeAmount } from '../format'
import './BalancesPage.css'

const FIRST_BALANCE_DATE: IsoDate = '2023-06-05'

function localToday(): IsoDate {
  const today = new Date()
  const year = today.getFullYear()
  const month = String(today.getMonth() + 1).padStart(2, '0')
  const day = String(today.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}` as IsoDate
}

// Legacy data does not contain a currency, so the UI must not invent one.
const amount = formatWholeAmount
const displayDate = (value: IsoDate) => new Date(`${value}T00:00:00`).toLocaleDateString('ru-RU', { day: '2-digit', month: 'short' })

export function BalancesPage() {
  const { hasRole } = useAuth()
  const queryClient = useQueryClient()
  const [dateFrom, setDateFrom] = useState<IsoDate>(FIRST_BALANCE_DATE)
  const [dateTo, setDateTo] = useState<IsoDate>(localToday)
  const [nonZeroOnly, setNonZeroOnly] = useState(false)
  const [selectedUser, setSelectedUser] = useState<UserBalance | null>(null)
  const [paymentFormOpen, setPaymentFormOpen] = useState(false)
  const [paymentDate, setPaymentDate] = useState<IsoDate>(localToday)
  const [paymentAmount, setPaymentAmount] = useState('')
  const [paymentTypeId, setPaymentTypeId] = useState('')
  const [paymentComment, setPaymentComment] = useState('')
  const [adjustmentOpen, setAdjustmentOpen] = useState(false)
  const [adjustmentDate, setAdjustmentDate] = useState<IsoDate>(localToday)
  const [adjustmentAmount, setAdjustmentAmount] = useState('')
  const [adjustmentReason, setAdjustmentReason] = useState('')
  const rangeIsValid = /^\d{4}-\d{2}-\d{2}$/.test(dateFrom)
    && /^\d{4}-\d{2}-\d{2}$/.test(dateTo)
    && dateFrom <= dateTo

  const balancesQuery = useQuery({
    queryKey: ['balances', dateFrom, dateTo, nonZeroOnly],
    queryFn: ({ signal }) => listBalances({ dateFrom, dateTo, nonZeroOnly, signal }),
    enabled: rangeIsValid,
  })
  const detailQuery = useQuery({
    queryKey: ['balance-detail', selectedUser?.userId, dateFrom, dateTo],
    queryFn: ({ signal }) => getUserBalance(selectedUser!.userId, { dateFrom, dateTo, signal }),
    enabled: rangeIsValid && selectedUser !== null,
  })
  const deletePayment = useMutation({
    mutationFn: ({ userId, paymentId }: { userId: string; paymentId: string }) => deleteUserPayment(userId, paymentId),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['balances'] }),
        queryClient.invalidateQueries({ queryKey: ['balance-detail'] }),
        queryClient.invalidateQueries({ queryKey: ['zenmoney-transactions'] }),
      ])
    },
  })
  const createPayment = useMutation({
    mutationFn: ({ userId, paymentDate, amount, paymentTypeId, comment }: { userId: string; paymentDate: IsoDate; amount: number; paymentTypeId: string; comment: string }) => createUserPayment(userId, { paymentDate, amount, paymentTypeId, comment }),
    onSuccess: async () => {
      setPaymentFormOpen(false)
      setPaymentAmount('')
      setPaymentComment('')
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['balances'] }),
        queryClient.invalidateQueries({ queryKey: ['balance-detail'] }),
      ])
    },
  })
  const createAdjustment = useMutation({
    mutationFn: ({ userId, value, reason }: { userId: string; value: number; reason: string }) => createUserAdjustment(userId, { balanceDateFrom: dateFrom, balanceDateTo: dateTo, adjustmentDate, expectedBalance: selectedUser!.cumulativeBalance, amount: value, reason }),
    onSuccess: async () => {
      setAdjustmentOpen(false)
      setAdjustmentAmount('')
      setAdjustmentReason('')
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['balances'] }),
        queryClient.invalidateQueries({ queryKey: ['balance-detail'] }),
      ])
    },
  })

  function requestPaymentDeletion(payment: BalancePayment) {
    if (!selectedUser || !window.confirm(`Удалить платёж ${amount(payment.amount)} от ${displayDate(payment.paymentDate)}? Он перестанет учитываться в балансе.`)) return
    deletePayment.mutate({ userId: selectedUser.userId, paymentId: payment.id })
  }

  function openPaymentForm() {
    const types = detailQuery.data?.paymentTypes ?? []
    setPaymentTypeId(types.find(type => type.name === 'Alpha')?.id ?? types[0]?.id ?? '')
    setPaymentDate(localToday())
    setPaymentFormOpen(true)
  }

  function submitPayment(event: FormEvent) {
    event.preventDefault()
    const value = Number(paymentAmount)
    if (!selectedUser || !paymentTypeId || !Number.isInteger(value) || value <= 0) return
    createPayment.mutate({ userId: selectedUser.userId, paymentDate, amount: value, paymentTypeId, comment: paymentComment.trim() })
  }

  function openAdjustmentForm() {
    if (!selectedUser) return
    setPaymentFormOpen(false)
    setAdjustmentOpen(true)
    setAdjustmentDate(dateTo)
    setAdjustmentAmount('')
    setAdjustmentReason('')
  }

  function submitAdjustment(event: FormEvent) {
    event.preventDefault()
    const value = Number(adjustmentAmount)
    if (!selectedUser || !Number.isInteger(value) || value === 0 || !adjustmentReason.trim()) return
    createAdjustment.mutate({ userId: selectedUser.userId, value, reason: adjustmentReason.trim() })
  }

  return (
    <section className="balances-page">
      <PageIntro
        eyebrow="Финансы команды"
        title="Балансы"
        description="Расчёт по неделям готовки. Платежи показаны по фактической дате и уменьшают общий накопленный долг — без искусственной привязки к отдельному блюду."
        actions={<button className="button" type="button" disabled={!rangeIsValid} onClick={() => balancesQuery.refetch()}>Обновить</button>}
      />
      <div className="filter-bar balances-page__filters" aria-label="Фильтры балансов">
        <label htmlFor="balance-date-from">С даты
          <input id="balance-date-from" type="date" value={dateFrom} onChange={(event) => setDateFrom(event.target.value as IsoDate)} />
        </label>
        <label htmlFor="balance-date-to">По дату
          <input id="balance-date-to" type="date" value={dateTo} onChange={(event) => setDateTo(event.target.value as IsoDate)} />
        </label>
        <label className="checkbox" htmlFor="balance-non-zero">
          <input id="balance-non-zero" type="checkbox" checked={nonZeroOnly} onChange={(event) => setNonZeroOnly(event.target.checked)} />
          Только ненулевые
        </label>
      </div>

      {!rangeIsValid && <div className="balances-page__validation" role="alert">Начальная дата не может быть позже конечной.</div>}
      {rangeIsValid && balancesQuery.isPending && <LoadingState label="Загружаем балансы…" />}
      {rangeIsValid && balancesQuery.isError && <ErrorState message="Не удалось загрузить балансы за выбранный период." onRetry={() => balancesQuery.refetch()} />}
      {balancesQuery.data?.items.length === 0 && (
        <EmptyState title="За выбранный период балансов нет">Измените диапазон дат или отключите фильтр ненулевых значений.</EmptyState>
      )}
      {balancesQuery.data && balancesQuery.data.items.length > 0 && (
        <div className="balances-page__layout">
          <section className="balances-panel" aria-labelledby="balances-list-title">
            <div className="balances-panel__heading">
              <div><span className="eyebrow">Участники</span><h2 id="balances-list-title">Итоги за период</h2></div>
              <span className="balances-panel__count">{balancesQuery.data.items.length}</span>
            </div>
            <div className="balances-table-wrap">
              <table className="balances-table">
                <thead><tr><th scope="col">Участник</th><th scope="col">Внесено</th><th scope="col">Начислено</th><th scope="col">Готовок</th><th scope="col">Баланс</th></tr></thead>
                <tbody>{balancesQuery.data.items.map((user) => (
                  <tr key={user.userId} data-selected={selectedUser?.userId === user.userId}>
                    <th scope="row"><button type="button" onClick={() => { setSelectedUser(user); setPaymentFormOpen(false); setAdjustmentOpen(false) }}>{user.userName}</button></th>
                    <td>{amount(user.positive)}</td><td>{amount(user.negative)}</td><td>{user.cooksCount}</td>
                    <td className={user.cumulativeBalance < 0 ? 'amount--negative' : 'amount--positive'}>{amount(user.cumulativeBalance)}</td>
                  </tr>
                ))}</tbody>
              </table>
            </div>
          </section>

          <section className="balances-panel balances-detail" aria-labelledby="balance-detail-title">
            <div className="balances-panel__heading"><div><span className="eyebrow">Расчётные недели</span><h2 id="balance-detail-title">{selectedUser?.userName ?? 'Выберите участника'}</h2></div>{selectedUser && hasRole('editor') && <div className="balance-actions"><button className="button button--secondary add-payment-button" type="button" onClick={() => paymentFormOpen ? setPaymentFormOpen(false) : openPaymentForm()}>{paymentFormOpen ? 'Отмена' : 'Добавить платёж'}</button><button className="button button--secondary" type="button" onClick={() => adjustmentOpen ? setAdjustmentOpen(false) : openAdjustmentForm()}>{adjustmentOpen ? 'Отмена' : 'Корректировка'}</button></div>}</div>
            {paymentFormOpen && selectedUser && detailQuery.data && <form className="manual-payment" onSubmit={submitPayment}>
              <strong>Полученный платёж · {selectedUser.userName}</strong>
              <label>Дата получения<input required type="date" value={paymentDate} onChange={event => setPaymentDate(event.target.value as IsoDate)} /></label>
              <label>Сумма<input required min="1" step="1" inputMode="numeric" type="number" value={paymentAmount} onChange={event => setPaymentAmount(event.target.value)} /></label>
              <label>Тип<select required value={paymentTypeId} onChange={event => setPaymentTypeId(event.target.value)}>{detailQuery.data.paymentTypes.map(type => <option value={type.id} key={type.id}>{type.name}</option>)}</select></label>
              <label className="manual-payment__comment">Комментарий<input maxLength={1000} value={paymentComment} onChange={event => setPaymentComment(event.target.value)} /></label>
              <button className="button" disabled={createPayment.isPending || !paymentTypeId || !Number.isInteger(Number(paymentAmount)) || Number(paymentAmount) <= 0} type="submit">{createPayment.isPending ? 'Добавляем…' : 'Добавить в баланс'}</button>
              {createPayment.isError && <p className="form-error">Не удалось добавить платёж: {createPayment.error.message}</p>}
            </form>}
            {adjustmentOpen && selectedUser && <form className="manual-payment" onSubmit={submitAdjustment}>
              <strong>Корректировка · {selectedUser.userName} · текущий баланс за период: {amount(selectedUser.cumulativeBalance)}</strong>
              <label>Дата<input required type="date" min={dateFrom} max={dateTo} value={adjustmentDate} onChange={event => setAdjustmentDate(event.target.value as IsoDate)} /></label>
              <label>Сумма<input required step="1" inputMode="numeric" type="number" value={adjustmentAmount} onChange={event => setAdjustmentAmount(event.target.value)} placeholder="Например, -155 или 200" /></label>
              <label className="manual-payment__comment">Причина<input required maxLength={1000} value={adjustmentReason} onChange={event => setAdjustmentReason(event.target.value)} placeholder="Например: закрытие старой погрешности" /></label>
              <button className="button" disabled={createAdjustment.isPending || !Number.isInteger(Number(adjustmentAmount)) || Number(adjustmentAmount) === 0 || !adjustmentReason.trim()} type="submit">{createAdjustment.isPending ? 'Сохраняем…' : 'Добавить корректировку'}</button>
              {createAdjustment.isError && <p className="form-error">Не удалось сохранить корректировку: {createAdjustment.error.message}</p>}
            </form>}
            {!selectedUser && <p className="balances-detail__prompt">Нажмите на участника, чтобы увидеть недельные итоги.</p>}
            {selectedUser && detailQuery.isPending && <LoadingState label="Загружаем детализацию…" />}
            {selectedUser && detailQuery.isError && <ErrorState message="Не удалось загрузить недельную детализацию." onRetry={() => detailQuery.refetch()} />}
            {detailQuery.data?.weeks.length === 0 && <EmptyState title="Недельных данных нет" />}
            {deletePayment.isError && <p className="form-error balance-delete-error">Не удалось удалить платёж: {deletePayment.error.message}</p>}
            {detailQuery.data && detailQuery.data.weeks.length > 0 && (
              <div className="week-ledger" aria-label={`Недельные итоги: ${detailQuery.data.userName}`}>
                {[...detailQuery.data.weeks].reverse().map((week) => (
                  <article className="week-card" key={`${week.year}-${week.week}`}>
                    <header className="week-card__header">
                      <div><span className="eyebrow">Неделя {week.week}</span><h3>{week.display}</h3></div>
                      <div className="week-card__balances"><span><small>На начало</small><strong>{amount(week.cumulativeBalance - week.weeklyDelta)}</strong></span><span className={week.cumulativeBalance < 0 ? 'week-card__balance is-negative' : 'week-card__balance is-positive'}><small>На конец</small><strong>{amount(week.cumulativeBalance)}</strong></span></div>
                    </header>
                    <div className="week-card__summary">
                      <div className="summary-paid"><small>Получено в эту неделю</small><strong>+{amount(week.positive)}</strong></div>
                      <div className="summary-charged"><small>Готовки этой недели</small><strong>−{amount(week.negative)}</strong></div>
                      {week.adjustment !== 0 && <div><small>Корректировка</small><strong>{week.adjustment > 0 ? '+' : ''}{amount(week.adjustment)}</strong></div>}
                      <div className={week.weeklyDelta < 0 ? 'summary-delta is-negative' : 'summary-delta is-positive'}><small>Изменение баланса</small><strong>{week.weeklyDelta > 0 ? '+' : ''}{amount(week.weeklyDelta)}</strong></div>
                    </div>
                    <div className="week-card__activity">
                      <section><h4>Начисления за готовки <span>{week.cooks.length}</span></h4>
                        {week.cooks.length === 0 ? <p>Начислений не было</p> : week.cooks.map(cook => <div className="activity-row" key={cook.id}><span><time>{displayDate(cook.cookDate)}</time>{cook.title}</span><strong className="activity-charge">−{amount(cook.amount)}</strong></div>)}
                      </section>
                      <section><h4>Платежи по дате получения <span>{week.payments.length}</span></h4>
                        {week.payments.length === 0 ? <p>Платежей не было</p> : week.payments.map(payment => <div className="activity-row" key={payment.id}><span><time>{displayDate(payment.paymentDate)}</time>{payment.paymentTypeName}<small>{payment.source}{payment.comment ? ` · ${payment.comment}` : ''}</small></span><strong className="activity-payment">+{amount(payment.amount)}</strong>{hasRole('editor') && <button className="payment-delete" type="button" disabled={deletePayment.isPending} aria-label={`Удалить платёж ${amount(payment.amount)} от ${displayDate(payment.paymentDate)}`} onClick={() => requestPaymentDeletion(payment)}>Удалить</button>}</div>)}
                      </section>
                      {week.adjustments.length > 0 && <section><h4>Корректировки <span>{week.adjustments.length}</span></h4>{week.adjustments.map(item => <div className="activity-row" key={item.id}><span><time>{displayDate(item.adjustmentDate)}</time>{item.reason}<small>Баланс до: {amount(item.balanceBefore)}{item.createdByName ? ` · ${item.createdByName}` : ''}</small></span><strong className={item.amount < 0 ? 'activity-charge' : 'activity-payment'}>{item.amount > 0 ? '+' : ''}{amount(item.amount)}</strong></div>)}</section>}
                    </div>
                  </article>
                ))}
              </div>
            )}
          </section>
        </div>
      )}
    </section>
  )
}
