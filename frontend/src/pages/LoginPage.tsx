import { FormEvent, useState } from 'react'
import { ApiError } from '../api/client'
import { useAuth } from '../auth'

export function LoginPage() {
  const { login } = useAuth()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  async function submit(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError('')
    try { await login(username, password) }
    catch (reason) { setError(reason instanceof ApiError ? reason.message : 'Не удалось связаться с сервером.') }
    finally { setBusy(false) }
  }
  return <main className="login-page">
    <form className="login-card" onSubmit={submit}>
      <div className="brand__mark">ОК</div>
      <h1>Офисная кухня</h1>
      <p>Войдите, чтобы продолжить.</p>
      <label>Логин<input autoComplete="username" autoFocus required value={username} onChange={(e) => setUsername(e.target.value)} /></label>
      <label>Пароль<input autoComplete="current-password" required type="password" value={password} onChange={(e) => setPassword(e.target.value)} /></label>
      {error && <div className="form-error" role="alert">{error}</div>}
      <button className="button" disabled={busy} type="submit">{busy ? 'Вход…' : 'Войти'}</button>
    </form>
  </main>
}
