import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { ApiError, listAccounts, updateAccount, type Account, type Role } from '../api'
import { ErrorState, LoadingState } from '../components/AsyncState'
import { PageIntro } from '../components/PageIntro'

export function AccessPage() {
  const client = useQueryClient()
  const [selectedId, setSelectedId] = useState('')
  const [pendingId, setPendingId] = useState<string | null>(null)
  const query = useQuery({ queryKey: ['accounts'], queryFn: ({ signal }) => listAccounts({ signal }) })
  const mutation = useMutation({
    mutationFn: ({ account, password }: { account: Account; password: string }) => updateAccount(account.id, {
      username: account.username || null,
      password: password || null,
      role: account.role,
      authEnabled: account.authEnabled,
    }),
    onSuccess: async (_, variables) => {
      if (pendingId === variables.account.id) setPendingId(null)
      await client.invalidateQueries({ queryKey: ['accounts'] })
    },
  })

  if (query.isPending) return <LoadingState label="Загружаем доступы…" />
  if (query.isError) return <ErrorState message="Не удалось загрузить доступы." onRetry={() => query.refetch()} />

  const configured = query.data.filter(account => account.authEnabled || account.username || account.id === pendingId)
  const available = query.data.filter(account => !account.authEnabled && !account.username && account.id !== pendingId)

  function addAccount() {
    if (!selectedId) return
    setPendingId(selectedId)
    setSelectedId('')
    mutation.reset()
  }

  return <section>
    <PageIntro eyebrow="Безопасность" title="Доступ пользователей" description="Логины, роли и блокировка учётных записей." />
    <div className="access-toolbar">
      <select aria-label="Пользователь для добавления" value={selectedId} onChange={(event) => setSelectedId(event.target.value)}>
        <option value="">Добавить пользователя…</option>
        {available.map(account => <option key={account.id} value={account.id}>{account.name}</option>)}
      </select>
      <button aria-label="Добавить доступ" className="access-add" disabled={!selectedId} onClick={addAccount} type="button">+</button>
    </div>
    {mutation.isError && <div className="form-error" role="alert">{mutation.error instanceof ApiError ? mutation.error.message : 'Не удалось сохранить доступ.'}</div>}
    <div className="access-list">
      {configured.length === 0 && <p className="access-empty">Доступ пока никому не настроен.</p>}
      {configured.map(account => <AccountEditor key={account.id} initial={account} busy={mutation.isPending} onSave={(next, password) => mutation.mutate({ account: next, password })} />)}
    </div>
  </section>
}

function AccountEditor({ initial, busy, onSave }: { initial: Account; busy: boolean; onSave: (account: Account, password: string) => void }) {
  const [account, setAccount] = useState(initial)
  const [password, setPassword] = useState('')
  useEffect(() => setAccount(initial), [initial])

  return <form className="access-row" onSubmit={(event) => { event.preventDefault(); onSave(account, password); setPassword('') }}>
    <strong>{account.name}</strong>
    <label>Логин<input minLength={3} value={account.username} onChange={(event) => setAccount({ ...account, username: event.target.value })} /></label>
    <label>Роль<select value={account.role} onChange={(event) => setAccount({ ...account, role: event.target.value as Role })}><option value="viewer">Просмотр</option><option value="editor">Редактор</option><option value="admin">Администратор</option></select></label>
    <label>Новый пароль<input minLength={12} placeholder="Не менять" type="password" value={password} onChange={(event) => setPassword(event.target.value)} /></label>
    <label className="access-enabled"><input type="checkbox" checked={account.authEnabled} onChange={(event) => setAccount({ ...account, authEnabled: event.target.checked })} /> Вход разрешён</label>
    <button className="button" disabled={busy} type="submit">Сохранить</button>
  </form>
}
