import { Navigate, Route, Routes } from 'react-router-dom'
import { AppShell } from './components/AppShell'
import { BalancesPage } from './pages/BalancesPage'
import { CooksPage } from './pages/CooksPage'
import { CatalogPage } from './pages/CatalogPage'
import { NewCookPage } from './pages/NewCookPage'

export function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<Navigate replace to="/balances" />} />
        <Route path="balances" element={<BalancesPage />} />
        <Route path="cooks/new" element={<NewCookPage />} />
        <Route path="cooks/:cookId" element={<NewCookPage />} />
        <Route path="cooks" element={<CooksPage />} />
        <Route path="catalog" element={<CatalogPage />} />
        <Route path="*" element={<Navigate replace to="/balances" />} />
      </Route>
    </Routes>
  )
}
