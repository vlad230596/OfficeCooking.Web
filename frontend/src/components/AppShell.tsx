import type { ReactNode } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import { useAuth } from '../auth'
import { BuildInfo } from './BuildInfo'

type NavigationItem = {
  to: string
  label: string
  shortLabel: string
  icon: ReactNode
}

const navigation: NavigationItem[] = [
  { to: '/balances', label: 'Балансы', shortLabel: 'Балансы', icon: <BalanceIcon /> },
  { to: '/cooks/new', label: 'Новая готовка', shortLabel: 'Новая', icon: <AddIcon /> },
  { to: '/cooks', label: 'Готовки', shortLabel: 'Готовки', icon: <ListIcon /> },
  { to: '/catalog', label: 'Справочники', shortLabel: 'Данные', icon: <CatalogIcon /> },
]

function Navigation({ mobile = false, items = navigation }: { mobile?: boolean; items?: NavigationItem[] }) {
  return (
    <nav aria-label={mobile ? 'Мобильная навигация' : 'Основная навигация'} className={mobile ? 'mobile-nav' : 'desktop-nav'}>
      {items.map((item) => (
        <NavLink key={item.to} className={({ isActive }) => `nav-link${isActive ? ' nav-link--active' : ''}`} to={item.to}>
          <span aria-hidden="true" className="nav-link__icon">{item.icon}</span>
          <span className={mobile ? 'nav-link__mobile-label' : undefined}>{mobile ? item.shortLabel : item.label}</span>
        </NavLink>
      ))}
    </nav>
  )
}

export function AppShell() {
  const { user, hasRole, logout } = useAuth()
  const visibleNavigation = navigation.filter(item => {
    if (item.to === '/catalog') return hasRole('admin')
    if (item.to === '/cooks/new') return hasRole('editor')
    return true
  })
  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="brand">
          <span aria-hidden="true" className="brand__mark">ОК</span>
          <div>
            <span className="brand__title">Офисная кухня</span>
            <span className="brand__subtitle">учёт готовок</span>
          </div>
        </div>
        <Navigation items={visibleNavigation} />
        {hasRole('admin') && <NavLink className="user-menu" to="/access">Доступы</NavLink>}
        <button className="logout-button" onClick={() => void logout()} title={`Выйти: ${user?.name}`}>Выйти</button>
      </header>
      <main className="app-content" id="main-content">
        <Outlet />
      </main>
      <footer className="app-footer">
        <BuildInfo />
      </footer>
      <Navigation items={visibleNavigation} mobile />
    </div>
  )
}

function BalanceIcon() {
  return <svg viewBox="0 0 24 24"><path d="M4 18h16M6 15V9m6 6V5m6 10v-3" /></svg>
}

function AddIcon() {
  return <svg viewBox="0 0 24 24"><path d="M12 5v14M5 12h14" /></svg>
}

function ListIcon() {
  return <svg viewBox="0 0 24 24"><path d="M8 6h11M8 12h11M8 18h11M4 6h.01M4 12h.01M4 18h.01" /></svg>
}

function CatalogIcon() {
  return <svg viewBox="0 0 24 24"><path d="M5 5h5v5H5zM14 5h5v5h-5zM5 14h5v5H5zM14 14h5v5h-5z" /></svg>
}
