import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { getUserBalance, listBalances } from '../api'
import type { IsoDate, UserBalance } from '../api'
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

export function BalancesPage() {
  const [dateFrom, setDateFrom] = useState<IsoDate>(FIRST_BALANCE_DATE)
  const [dateTo, setDateTo] = useState<IsoDate>(localToday)
  const [nonZeroOnly, setNonZeroOnly] = useState(false)
  const [selectedUser, setSelectedUser] = useState<UserBalance | null>(null)
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

  return (
    <section className="balances-page">
      <PageIntro
        eyebrow="Финансы команды"
        title="Балансы"
        description="Накопительные балансы и недельная детализация участников."
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
                    <th scope="row"><button type="button" onClick={() => setSelectedUser(user)}>{user.userName}</button></th>
                    <td>{amount(user.positive)}</td><td>{amount(user.negative)}</td><td>{user.cooksCount}</td>
                    <td className={user.cumulativeBalance < 0 ? 'amount--negative' : 'amount--positive'}>{amount(user.cumulativeBalance)}</td>
                  </tr>
                ))}</tbody>
              </table>
            </div>
          </section>

          <section className="balances-panel balances-detail" aria-labelledby="balance-detail-title">
            <div className="balances-panel__heading"><div><span className="eyebrow">По неделям</span><h2 id="balance-detail-title">{selectedUser?.userName ?? 'Выберите участника'}</h2></div></div>
            {!selectedUser && <p className="balances-detail__prompt">Нажмите на участника, чтобы увидеть недельные итоги.</p>}
            {selectedUser && detailQuery.isPending && <LoadingState label="Загружаем детализацию…" />}
            {selectedUser && detailQuery.isError && <ErrorState message="Не удалось загрузить недельную детализацию." onRetry={() => detailQuery.refetch()} />}
            {detailQuery.data?.weeks.length === 0 && <EmptyState title="Недельных данных нет" />}
            {detailQuery.data && detailQuery.data.weeks.length > 0 && (
              <div className="week-table-wrap">
                <table className="week-table" aria-label={`Недельные итоги: ${detailQuery.data.userName}`}>
                  <thead><tr><th>Период</th><th>Готовок</th><th>За неделю</th><th>Накопительно</th></tr></thead>
                  <tbody>{detailQuery.data.weeks.map((week) => (
                    <tr key={`${week.year}-${week.week}`}>
                      <th scope="row">{week.display}</th><td>{week.cooksCount}</td><td>{amount(week.weeklyDelta)}</td><td>{amount(week.cumulativeBalance)}</td>
                    </tr>
                  ))}</tbody>
                </table>
              </div>
            )}
          </section>
        </div>
      )}
    </section>
  )
}
