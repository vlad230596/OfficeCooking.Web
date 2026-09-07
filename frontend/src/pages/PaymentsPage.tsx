import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState, type FormEvent } from 'react'
import {
  approveAllMatchedZenMoneyTransactions,
  decideZenMoneyTransaction,
  getZenMoneySettings,
  listUsers,
  listZenMoneyAccounts,
  listZenMoneyTransactions,
  saveZenMoneySettings,
  syncZenMoney,
  type SaveZenMoneySettingsRequest,
  type UUID,
  type ZenMoneyAccount,
  type ZenMoneyStatus,
  type ZenMoneyTransaction,
} from '../api'
import { useAuth } from '../auth'
import { ErrorState, LoadingState } from '../components/AsyncState'
import { PageIntro } from '../components/PageIntro'
import './PaymentsPage.css'

const statusLabels: Record<ZenMoneyStatus, string> = {
  matched: 'Сопоставлено', review: 'Требует решения', blacklisted: 'Blacklist', rejected: 'Отклонено',
}

type PaymentView = 'new' | 'accepted' | 'excluded'
type DecisionAction = 'assign' | 'approve' | 'reject' | 'retry'

export function PaymentsPage() {
  const { hasRole } = useAuth()
  const queryClient = useQueryClient()
  const [view, setView] = useState<PaymentView>('new')
  const [status, setStatus] = useState<ZenMoneyStatus | ''>('')
  const [includeBlacklisted, setIncludeBlacklisted] = useState(false)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const transactions = useQuery({
    queryKey: ['zenmoney-transactions'],
    queryFn: ({ signal }) => listZenMoneyTransactions({ includeBlacklisted: true, signal }),
  })
  const users = useQuery({ queryKey: ['users', 'all'], queryFn: ({ signal }) => listUsers({ enabled: 'all', signal }) })
  const synchronize = useMutation({
    mutationFn: syncZenMoney,
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['zenmoney-transactions'] }),
        queryClient.invalidateQueries({ queryKey: ['balances'] }),
        queryClient.invalidateQueries({ queryKey: ['zenmoney-settings'] }),
      ])
    },
  })
  const decide = useMutation({
    mutationFn: ({ id, action, userId }: { id: UUID; action: DecisionAction; userId?: UUID }) =>
      decideZenMoneyTransaction(id, action, userId),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['zenmoney-transactions'] }),
        queryClient.invalidateQueries({ queryKey: ['balances'] }),
      ])
    },
  })
  const approveAll = useMutation({
    mutationFn: approveAllMatchedZenMoneyTransactions,
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['zenmoney-transactions'] }),
        queryClient.invalidateQueries({ queryKey: ['balances'] }),
      ])
    },
  })

  const allTransactions = transactions.data ?? []
  const acceptedCount = allTransactions.filter(item => item.paymentId && item.status === 'matched').length
  const excludedCount = allTransactions.filter(item => item.status === 'rejected').length
  const blacklistCount = allTransactions.filter(item => item.status === 'blacklisted').length
  const newCount = allTransactions.filter(item => !item.paymentId && item.status !== 'rejected' && item.status !== 'blacklisted').length
  const approvableCount = allTransactions.filter(item => !item.paymentId && item.status === 'matched').length
  const visibleTransactions = allTransactions.filter(item => {
    if (status && item.status !== status) return false
    if (!includeBlacklisted && item.status === 'blacklisted') return false
    if (view === 'accepted') return Boolean(item.paymentId) && item.status === 'matched'
    if (view === 'excluded') return item.status === 'rejected' || item.status === 'blacklisted'
    return !item.paymentId && item.status !== 'rejected'
  })

  return <section className="payments-page">
    <PageIntro eyebrow="Платежи" title="Входящие операции" description="Сначала загрузите и проверьте поступления. Баланс изменится только после отдельного подтверждения операции." />
    <div className="payments-views" role="tablist" aria-label="Этап обработки">
      <button className={view === 'new' ? 'is-active' : ''} type="button" onClick={() => setView('new')}>Новые <span>{newCount}</span></button>
      <button className={view === 'accepted' ? 'is-active' : ''} type="button" onClick={() => setView('accepted')}>Учтённые <span>{acceptedCount}</span></button>
      <button className={view === 'excluded' ? 'is-active' : ''} type="button" onClick={() => setView('excluded')}>Исключённые <span>{excludedCount}</span></button>
    </div>
    <div className="payments-toolbar">
      <label>Статус<select value={status} onChange={event => setStatus(event.target.value as ZenMoneyStatus | '')}>
        <option value="">Все</option>{Object.entries(statusLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
      </select></label>
      <label className="checkbox"><input type="checkbox" checked={includeBlacklisted} onChange={event => setIncludeBlacklisted(event.target.checked)} />Показывать blacklist ({blacklistCount})</label>
      {hasRole('admin') && <button className="button button--secondary payments-settings-button" type="button" onClick={() => setSettingsOpen(value => !value)}>Настройки ZenMoney</button>}
      <button className="button payment-approve" type="button" disabled={approveAll.isPending || approvableCount === 0} onClick={() => approveAll.mutate()}>{approveAll.isPending ? 'Учитываем…' : `Учесть все сопоставленные (${approvableCount})`}</button>
      <button className="button" type="button" disabled={synchronize.isPending} onClick={() => synchronize.mutate()}>{synchronize.isPending ? 'Синхронизация…' : 'Загрузить новые операции'}</button>
    </div>
    {synchronize.data && <p className="payments-result">Получено: {synchronize.data.received}; новых: {synchronize.data.created}; сопоставлено: {synchronize.data.matched}; на проверку: {synchronize.data.review}.</p>}
    {synchronize.isError && <p className="form-error">Не удалось синхронизировать операции: {synchronize.error.message}</p>}
    {approveAll.data && <p className="payments-result">Учтено платежей: {approveAll.data.approved}{approveAll.data.skipped ? `; пропущено: ${approveAll.data.skipped}` : ''}.</p>}
    {approveAll.isError && <p className="form-error">Не удалось учесть сопоставленные платежи: {approveAll.error.message}</p>}
    {settingsOpen && hasRole('admin') && <ZenMoneySettingsPanel onSaved={() => setSettingsOpen(false)} />}
    {transactions.isPending || users.isPending ? <LoadingState label="Загружаем операции…" /> :
      transactions.isError || users.isError ? <ErrorState message="Не удалось загрузить операции." onRetry={() => transactions.refetch()} /> :
      <div className="payment-list">
        {visibleTransactions.length === 0 && <p className="payments-empty">Операций по выбранному фильтру нет.</p>}
        {visibleTransactions.map(item => <TransactionCard key={item.id} item={item} users={users.data ?? []} pending={decide.isPending} onDecision={(action, userId) => decide.mutate({ id: item.id, action, userId })} />)}
      </div>}
  </section>
}

function TransactionCard({ item, users, pending, onDecision }: { item: ZenMoneyTransaction; users: Array<{ id: UUID; name: string }>; pending: boolean; onDecision: (action: DecisionAction, userId?: UUID) => void }) {
  const [userId, setUserId] = useState(item.userId ?? '')
  useEffect(() => setUserId(item.userId ?? ''), [item.userId])
  return <article className={`payment-card payment-card--${item.status}`}>
    <div className="payment-card__main">
      <div><span className="payment-card__date">{new Date(`${item.transactionDate}T00:00:00`).toLocaleDateString('ru-RU')}</span><strong>{item.amount.toLocaleString('ru-RU')} ₽</strong></div>
      <h2>{item.payee || item.originalPayee || 'Отправитель не указан'}</h2>
      {item.comment && <p>{item.comment}</p>}
      <small>{item.paymentId ? 'Учтено в балансе' : statusLabels[item.status]} · {matchReasonLabel(item.matchReason)}{item.decisionSource === 'manual' ? ' · правило сохранено' : ''}</small>
    </div>
    <div className="payment-card__actions">
      <select aria-label="Участник" value={userId} onChange={event => setUserId(event.target.value)}><option value="">Выберите участника</option>{users.map(user => <option key={user.id} value={user.id}>{user.name}</option>)}</select>
      <button className="button button--secondary" disabled={pending || !userId} type="button" onClick={() => onDecision('assign', userId)}>Сопоставить</button>
      {item.status === 'matched' && !item.paymentId && <button className="button payment-approve" disabled={pending} type="button" onClick={() => onDecision('approve')}>Учесть платёж</button>}
      <button className="button payment-reject" disabled={pending} type="button" onClick={() => onDecision('reject')}>Отклонить</button>
      {item.decisionSource === 'manual' && <button className="payment-retry" disabled={pending} type="button" onClick={() => onDecision('retry')}>Автопоиск</button>}
    </div>
  </article>
}

function matchReasonLabel(reason: string | null): string {
  const labels: Record<string, string> = {
    phone: 'совпадение по телефону',
    name: 'совпадение по имени',
    'saved name': 'совпадение по сохранённому имени',
    'learned phone': 'запомненное совпадение по телефону',
    'learned name': 'запомненное совпадение по имени',
    'manual assignment': 'выбрано вручную',
    'ambiguous contact': 'несколько совпадений по контакту',
    'ambiguous name': 'несколько совпадений по имени',
    'no unique user match': 'совпадение не найдено',
    'internal transfer': 'перевод между своими счетами',
  }
  return reason ? labels[reason] ?? reason : 'без пояснения'
}

function ZenMoneySettingsPanel({ onSaved }: { onSaved: () => void }) {
  const queryClient = useQueryClient()
  const settings = useQuery({ queryKey: ['zenmoney-settings'], queryFn: ({ signal }) => getZenMoneySettings({ signal }) })
  const [token, setToken] = useState('')
  const [accounts, setAccounts] = useState<ZenMoneyAccount[]>([])
  const [accountId, setAccountId] = useState('')
  const [paymentTypeId, setPaymentTypeId] = useState('')
  const [blacklist, setBlacklist] = useState('')
  useEffect(() => { if (settings.data) { setAccountId(settings.data.accountId ?? ''); setPaymentTypeId(settings.data.paymentTypeId ?? ''); setBlacklist(settings.data.blacklist.join('\n')) } }, [settings.data])
  const loadAccounts = useMutation({ mutationFn: () => listZenMoneyAccounts(token.trim() || undefined), onSuccess: setAccounts })
  const save = useMutation({
    mutationFn: (request: SaveZenMoneySettingsRequest) => saveZenMoneySettings(request),
    onSuccess: async () => { setToken(''); await queryClient.invalidateQueries({ queryKey: ['zenmoney-settings'] }); onSaved() },
  })
  function submit(event: FormEvent) {
    event.preventDefault()
    const account = accounts.find(value => value.id === accountId)
    const accountTitle = account ? [account.companyTitle, account.title].filter(Boolean).join(' · ') : settings.data?.accountTitle
    if (!accountId || !accountTitle || !paymentTypeId) return
    save.mutate({ ...(token.trim() ? { accessToken: token.trim() } : {}), accountId, accountTitle, paymentTypeId, blacklist: blacklist.split('\n').map(value => value.trim()).filter(Boolean) })
  }
  if (settings.isPending) return <LoadingState label="Загружаем настройки…" />
  if (settings.isError) return <ErrorState message="Не удалось загрузить настройки ZenMoney." onRetry={() => settings.refetch()} />
  return <form className="zen-settings" onSubmit={submit}>
    <h2>Настройки ZenMoney</h2><p>Токен после сохранения нельзя прочитать обратно. Оставьте поле пустым, чтобы сохранить текущий.</p>
    <div className="zen-settings__grid">
      <label>Access token<input type="password" autoComplete="off" spellCheck={false} value={token} placeholder={settings.data?.tokenConfigured ? 'Токен уже настроен' : 'Вставьте токен'} onChange={event => setToken(event.target.value)} /></label>
      <button className="button button--secondary" type="button" disabled={loadAccounts.isPending || (!token.trim() && !settings.data?.tokenConfigured)} onClick={() => loadAccounts.mutate()}>{loadAccounts.isPending ? 'Загрузка…' : 'Получить счета'}</button>
      <label>Счёт<select required value={accountId} onChange={event => setAccountId(event.target.value)}><option value="">Выберите счёт</option>{accountId && !accounts.some(value => value.id === accountId) && <option value={accountId}>{settings.data?.accountTitle}</option>}{accounts.filter(value => !value.archived).map(account => <option key={account.id} value={account.id}>{[account.companyTitle, account.title, account.syncIds.join(', ')].filter(Boolean).join(' · ')}</option>)}</select></label>
      <label>Тип платежа<select required value={paymentTypeId} onChange={event => setPaymentTypeId(event.target.value)}><option value="">Выберите тип</option>{settings.data?.paymentTypes.map(type => <option key={type.id} value={type.id}>{type.name}</option>)}</select></label>
    </div>
    <label>Blacklist — имя или телефон, по одному на строку<textarea rows={5} value={blacklist} onChange={event => setBlacklist(event.target.value)} /></label>
    {(loadAccounts.isError || save.isError) && <p className="form-error">{(loadAccounts.error || save.error)?.message}</p>}
    <button className="button" disabled={save.isPending || (!token.trim() && !settings.data?.tokenConfigured)} type="submit">{save.isPending ? 'Сохраняем…' : 'Сохранить настройки'}</button>
  </form>
}
