import { useMutation, useQuery } from '@tanstack/react-query'
import { useMemo, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import {
  calculateCookSelection,
  listCooks,
  listTemplates,
  type CalculateSelectionResponse,
  type CookSummary,
  type IsoDate,
} from '../api'
import { EmptyState, ErrorState, LoadingState } from '../components/AsyncState'
import { PageIntro } from '../components/PageIntro'
import { formatQuantity, formatWholeAmount } from '../format'
import './CooksPage.css'

const DEFAULT_DATE_FROM = '2022-01-01' as IsoDate
const PAGE_SIZES = [10, 25, 50, 100]

type Filters = { dateFrom: IsoDate; dateTo: IsoDate; templateId: string }

function currentLocalDate(): IsoDate {
  const now = new Date()
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}` as IsoDate
}

const initialFilters = (): Filters => ({
  dateFrom: DEFAULT_DATE_FROM,
  dateTo: currentLocalDate(),
  templateId: '',
})

export function CooksPage() {
  const [draftFilters, setDraftFilters] = useState<Filters>(initialFilters)
  const [filters, setFilters] = useState<Filters>(initialFilters)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(25)
  const [selectedIds, setSelectedIds] = useState<Set<string>>(() => new Set())
  const templatesQuery = useQuery({
    queryKey: ['templates'],
    queryFn: ({ signal }) => listTemplates({ signal }),
  })
  const cooksQuery = useQuery({
    queryKey: ['cooks', filters, page, pageSize],
    queryFn: ({ signal }) => listCooks({
      dateFrom: filters.dateFrom,
      dateTo: filters.dateTo,
      templateId: filters.templateId || undefined,
      page,
      pageSize,
      signal,
    }),
    placeholderData: previous => previous,
  })
  const calculation = useMutation({
    mutationFn: (cookIds: string[]) => calculateCookSelection({ cookIds }),
  })
  const pageIds = useMemo(
    () => cooksQuery.data?.items.map(cook => cook.id) ?? [],
    [cooksQuery.data?.items],
  )
  const allPageSelected = pageIds.length > 0 && pageIds.every(id => selectedIds.has(id))
  const weekBandByCookId = useMemo(() => {
    const bands = new Map<string, number>()
    let previousWeek = ''
    let band = -1
    for (const cook of cooksQuery.data?.items ?? []) {
      const currentWeek = legacyWeekDisplay(cook.cookDate)
      if (currentWeek !== previousWeek) {
        band += 1
        previousWeek = currentWeek
      }
      bands.set(cook.id, band % 2)
    }
    return bands
  }, [cooksQuery.data?.items])

  function applyFilters(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setFilters(draftFilters)
    setPage(1)
    setSelectedIds(new Set())
    calculation.reset()
  }

  function toggleCook(cookId: string) {
    setSelectedIds(current => {
      const next = new Set(current)
      if (next.has(cookId)) next.delete(cookId)
      else next.add(cookId)
      return next
    })
    calculation.reset()
  }

  function togglePage() {
    setSelectedIds(current => {
      const next = new Set(current)
      for (const id of pageIds) {
        if (allPageSelected) next.delete(id)
        else next.add(id)
      }
      return next
    })
    calculation.reset()
  }

  const calculateSelected = () => {
    if (selectedIds.size > 0) calculation.mutate([...selectedIds])
  }

  return (
    <section className={`cooks-page${calculation.data ? ' has-result' : ''}`}>
      <PageIntro eyebrow="История" title="Готовки" description="Найдите готовки, выберите нужные и рассчитайте начисления участникам." />
      <form className="cooks-filters" aria-label="Фильтры готовок" onSubmit={applyFilters}>
        <label>С даты<input type="date" value={draftFilters.dateFrom} max={draftFilters.dateTo} onChange={event => setDraftFilters(current => ({ ...current, dateFrom: event.target.value as IsoDate }))} /></label>
        <label>По дату<input type="date" value={draftFilters.dateTo} min={draftFilters.dateFrom} onChange={event => setDraftFilters(current => ({ ...current, dateTo: event.target.value as IsoDate }))} /></label>
        <label className="cooks-filters__template">
          Блюдо
          <select value={draftFilters.templateId} disabled={templatesQuery.isPending || templatesQuery.isError} onChange={event => setDraftFilters(current => ({ ...current, templateId: event.target.value }))}>
            <option value="">Все блюда</option>
            {templatesQuery.data?.map(template => <option key={template.id} value={template.id}>{template.name}</option>)}
          </select>
        </label>
        <button className="button" type="submit">Показать</button>
        {templatesQuery.isError && <p className="cooks-filters__error" role="alert">Блюда не загрузились. Фильтр по блюду недоступен.</p>}
      </form>

      {cooksQuery.isPending && <LoadingState label="Загрузка готовок…" />}
      {cooksQuery.isError && <ErrorState message="Не удалось загрузить список готовок." onRetry={() => void cooksQuery.refetch()} />}
      {cooksQuery.data && cooksQuery.data.items.length === 0 && <EmptyState title="Готовки не найдены">Измените даты или выберите другое блюдо.</EmptyState>}
      {cooksQuery.data && cooksQuery.data.items.length > 0 && (
        <>
          <div className="cooks-list-heading">
            <p>Найдено: <strong>{cooksQuery.data.totalItems}</strong>{cooksQuery.isFetching && <span aria-live="polite"> · Обновление…</span>}</p>
            <label>На странице<select value={pageSize} onChange={event => { setPageSize(Number(event.target.value)); setPage(1) }}>{PAGE_SIZES.map(size => <option key={size} value={size}>{size}</option>)}</select></label>
          </div>
          <div className="cooks-table-wrap">
            <table className="cooks-table" aria-label="Готовки">
              <thead><tr><th className="cooks-table__check"><input type="checkbox" aria-label="Выбрать все готовки на странице" checked={allPageSelected} onChange={togglePage} /></th><th>Дата</th><th>Год</th><th>Неделя</th><th>Блюдо</th><th><span className="table-label-long">Участники</span><span className="table-label-short">Уч.</span></th><th><span className="table-label-long">Порции</span><span className="table-label-short">Порц.</span></th><th><span className="table-label-long">Стоимость</span><span className="table-label-short">Сумма</span></th><th><span className="sr-only">Действия</span></th></tr></thead>
              <tbody>{cooksQuery.data.items.map(cook => <CookTableRow key={cook.id} cook={cook} selected={selectedIds.has(cook.id)} weekBand={weekBandByCookId.get(cook.id) ?? 0} onToggle={() => toggleCook(cook.id)} />)}</tbody>
            </table>
          </div>
          <Pagination page={cooksQuery.data.page} totalPages={cooksQuery.data.totalPages} onPageChange={setPage} />
        </>
      )}

      {selectedIds.size > 0 && (
        <aside className={`cooks-selection${calculation.data ? ' cooks-selection--settled' : ''}`} aria-label="Расчёт выбранных готовок">
          <div><strong>Выбрано: {selectedIds.size}</strong><span>Расчёт не зависит от текущей страницы</span></div>
          <button className="button" type="button" disabled={calculation.isPending} onClick={calculateSelected}>{calculation.isPending ? 'Считаем…' : 'Рассчитать'}</button>
        </aside>
      )}
      {calculation.isError && <div className="cooks-calculation-error" role="alert">Не удалось рассчитать выбранные готовки.<button type="button" onClick={calculateSelected}>Повторить</button></div>}
      {calculation.data && <CalculationResult result={calculation.data} />}
    </section>
  )
}

type CookItemProps = { cook: CookSummary; selected: boolean; weekBand: number; onToggle: () => void }

function CookTableRow({ cook, selected, weekBand, onToggle }: CookItemProps) {
  const [weekYear, weekNumber] = legacyWeekDisplay(cook.cookDate).split('#')
  return (
    <tr className={`${weekBand ? 'week-band--alternate' : 'week-band--base'}${selected ? ' is-selected' : ''}`}>
      <td className="cooks-table__check"><input type="checkbox" aria-label={`Выбрать готовку ${formatDate(cook.cookDate)}`} checked={selected} onChange={onToggle} /></td>
      <td><time dateTime={cook.cookDate}><span className="table-date-long">{formatDate(cook.cookDate)}</span><span className="table-date-short">{formatShortDate(cook.cookDate)}</span></time></td><td>{weekYear}</td><td>{weekNumber}</td><td><strong>{cook.typeSnapshot}</strong></td><td>{cook.memberCount}</td><td>{formatQuantity(cook.totalVoteWeight)}</td><td>{formatNullableNumber(cook.totalPrice)}</td>
      <td><Link aria-label={`Открыть готовку ${formatDate(cook.cookDate)}`} className="cooks-edit-link" to={`/cooks/${cook.id}`}><span className="table-action-long">Открыть</span><span aria-hidden="true" className="table-action-short">↗</span></Link></td>
    </tr>
  )
}

function Pagination({ page, totalPages, onPageChange }: { page: number; totalPages: number; onPageChange: (page: number) => void }) {
  if (totalPages <= 1) return null
  return <nav className="cooks-pagination" aria-label="Страницы готовок"><button type="button" disabled={page <= 1} onClick={() => onPageChange(page - 1)}>Назад</button><span>Страница {page} из {totalPages}</span><button type="button" disabled={page >= totalPages} onClick={() => onPageChange(page + 1)}>Вперёд</button></nav>
}

function CalculationResult({ result }: { result: CalculateSelectionResponse }) {
  const [copied, setCopied] = useState(false)
  const copyText = result.positiveCharges
    .map(item => `${item.userName} ${formatWholeAmount(item.charge)}`)
    .join('\n')

  async function copyResult() {
    try {
      await navigator.clipboard.writeText(copyText)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1800)
    } catch {
      setCopied(false)
    }
  }

  return (
    <section className="cooks-result" aria-live="polite">
      <div className="cooks-result__heading">
        <div><span>Начисления</span><h2>Положительные суммы</h2></div>
        <div className="cooks-result__actions"><strong>{formatWholeAmount(result.positiveTotal)}</strong>{result.positiveCharges.length > 0 && <button type="button" onClick={() => void copyResult()}>{copied ? 'Скопировано' : 'Копировать'}</button>}</div>
      </div>
      {result.positiveCharges.length === 0
        ? <p className="cooks-result__empty">Положительных начислений нет.</p>
        : <pre className="cooks-result__copy" aria-label="Таблица начислений" tabIndex={0}>{copyText}</pre>}
    </section>
  )
}

function formatDate(value: string): string { const [year, month, day] = value.split('-'); return `${day}.${month}.${year}` }
function formatShortDate(value: string): string { const [, month, day] = value.split('-'); return `${day}.${month}` }
export function legacyWeekDisplay(value: string): string {
  const [year, month, day] = value.split('-').map(Number)
  const date = new Date(Date.UTC(year, month - 1, day))
  const first = new Date(Date.UTC(year, 0, 1))
  const dayOfYear = Math.floor((date.getTime() - first.getTime()) / 86_400_000) + 1
  const mondayBasedOffset = (first.getUTCDay() + 6) % 7
  const week = Math.floor((dayOfYear + mondayBasedOffset - 1) / 7) + 1
  return `${year}#${week}`
}
function formatNullableNumber(value: number | null): string { return value === null ? 'Ошибка расчёта' : formatWholeAmount(value) }
