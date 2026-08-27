import { Navigate, Route, Routes } from 'react-router-dom'
import { AppShell } from './components/AppShell'
import { BalancesPage } from './pages/BalancesPage'
import { CooksPage } from './pages/CooksPage'
import { CatalogPage } from './pages/CatalogPage'
import { NewCookPage } from './pages/NewCookPage'
import { AccessPage } from './pages/AccessPage'
import { LoginPage } from './pages/LoginPage'
import { AuthProvider, useAuth } from './auth'

export function App() {
  return <AuthProvider><AuthenticatedRoutes /></AuthProvider>
}

function AuthenticatedRoutes() {
  const { user, loading, hasRole } = useAuth()
  if (loading) return <div className="auth-loading"><div className="spinner" /><span>Проверяем сессию…</span></div>
  if (!user) return <LoginPage />
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<Navigate replace to="/cooks" />} />
        <Route path="balances" element={<BalancesPage />} />
        <Route path="cooks/new" element={hasRole('editor') ? <NewCookPage /> : <Navigate replace to="/cooks" />} />
        <Route path="cooks/:cookId" element={hasRole('editor') ? <NewCookPage /> : <Navigate replace to="/cooks" />} />
        <Route path="cooks" element={<CooksPage />} />
        <Route path="catalog" element={hasRole('admin') ? <CatalogPage /> : <Navigate replace to="/cooks" />} />
        <Route path="access" element={hasRole('admin') ? <AccessPage /> : <Navigate replace to="/cooks" />} />
        <Route path="*" element={<Navigate replace to="/cooks" />} />
      </Route>
    </Routes>
  )
}
