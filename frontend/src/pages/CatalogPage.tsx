import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState, type FormEvent } from 'react'
import {
  createTemplate,
  createUser,
  getTemplate,
  listTemplates,
  listUsers,
  updateTemplate,
  updateUser,
  type SaveTemplateRequest,
  type SaveUserRequest,
  type TemplateDetail,
  type User,
} from '../api'
import { ApiError } from '../api'
import { ErrorState, LoadingState } from '../components/AsyncState'
import { PageIntro } from '../components/PageIntro'
import './CatalogPage.css'

type CatalogTab = 'users' | 'dishes'
type UserDraft = Omit<SaveUserRequest, 'permanentSale'> & { permanentSale: string }
type DishDraft = Omit<SaveTemplateRequest, 'voteVariants'> & {
  voteVariants: Array<{ name: string; value: string }>
}

const emptyUser = (): UserDraft => ({ name: '', permanentSale: '1', enabled: true, contacts: [] })
const emptyDish = (): DishDraft => ({ name: '', isMultivote: false, voteVariants: [], ingredients: [] })

export function CatalogPage() {
  const [tab, setTab] = useState<CatalogTab>('users')

  return (
    <section className="catalog-page">
      <PageIntro eyebrow="Настройка" title="Справочники" description="Участники и блюда для новых готовок." />
      <div className="catalog-tabs" role="tablist" aria-label="Справочники">
        <button role="tab" aria-selected={tab === 'users'} className={tab === 'users' ? 'is-active' : ''} onClick={() => setTab('users')}>Пользователи</button>
        <button role="tab" aria-selected={tab === 'dishes'} className={tab === 'dishes' ? 'is-active' : ''} onClick={() => setTab('dishes')}>Блюда</button>
      </div>
      {tab === 'users' ? <UsersEditor /> : <DishesEditor />}
    </section>
  )
}

function UsersEditor() {
  const queryClient = useQueryClient()
  const usersQuery = useQuery({ queryKey: ['users', 'all'], queryFn: ({ signal }) => listUsers({ enabled: 'all', signal }) })
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [draft, setDraft] = useState<UserDraft>(emptyUser)
  const selected = usersQuery.data?.find(item => item.id === selectedId)

  useEffect(() => {
    if (selected) setDraft(userToDraft(selected))
  }, [selected])

  const save = useMutation({
    mutationFn: (request: SaveUserRequest) => selectedId ? updateUser(selectedId, request) : createUser(request),
    onSuccess: async (user) => {
      await queryClient.invalidateQueries({ queryKey: ['users'] })
      setSelectedId(user.id)
      setDraft(userToDraft(user))
    },
  })

  function submit(event: FormEvent) {
    event.preventDefault()
    const permanentSale = Number(draft.permanentSale)
    if (!Number.isFinite(permanentSale)) return
    save.mutate({ ...draft, name: draft.name.trim(), permanentSale, contacts: draft.contacts.filter(item => item.value.trim()).map(item => ({ value: item.value.trim() })) })
  }

  if (usersQuery.isPending) return <LoadingState label="Загружаем пользователей…" />
  if (usersQuery.isError) return <ErrorState message="Не удалось загрузить пользователей." onRetry={() => usersQuery.refetch()} />

  return (
    <div className="catalog-workspace">
      <CatalogList title="Пользователи" addLabel="Добавить пользователя" onAdd={() => { setSelectedId(null); setDraft(emptyUser()); save.reset() }}>
        {usersQuery.data?.map(user => (
          <button key={user.id} type="button" className={selectedId === user.id ? 'is-selected' : ''} onClick={() => { setSelectedId(user.id); save.reset() }}>
            <span>{user.name}</span><small>{user.enabled ? 'активен' : 'отключён'}</small>
          </button>
        ))}
      </CatalogList>
      <form className="catalog-editor" onSubmit={submit}>
        <EditorHeading title={selectedId ? 'Редактирование пользователя' : 'Новый пользователь'} />
        <div className="catalog-fields catalog-fields--two">
          <label>Имя<input required maxLength={200} value={draft.name} onChange={event => setDraft(current => ({ ...current, name: event.target.value }))} /></label>
          <label>Постоянный коэффициент<input required inputMode="decimal" type="number" step="any" value={draft.permanentSale} onChange={event => setDraft(current => ({ ...current, permanentSale: event.target.value }))} /></label>
        </div>
        <label className="catalog-check"><input type="checkbox" checked={draft.enabled} onChange={event => setDraft(current => ({ ...current, enabled: event.target.checked }))} />Показывать при создании готовки</label>
        <CollectionHeading title="Контакты для сопоставления платежей" onAdd={() => setDraft(current => ({ ...current, contacts: [...current.contacts, { value: '' }] }))} />
        <div className="catalog-rows">
          {draft.contacts.length === 0 && <p className="catalog-empty">Контактов пока нет.</p>}
          {draft.contacts.map((contact, index) => (
            <div className="catalog-row" key={index}>
              <input aria-label={`Контакт ${index + 1}`} value={contact.value} onChange={event => setDraft(current => ({ ...current, contacts: replaceAt(current.contacts, index, { value: event.target.value }) }))} />
              <RowActions index={index} length={draft.contacts.length} onMove={(to) => setDraft(current => ({ ...current, contacts: move(current.contacts, index, to) }))} onRemove={() => setDraft(current => ({ ...current, contacts: current.contacts.filter((_, itemIndex) => itemIndex !== index) }))} />
            </div>
          ))}
        </div>
        <SaveBar pending={save.isPending} error={save.error} label={selectedId ? 'Сохранить изменения' : 'Добавить пользователя'} />
      </form>
    </div>
  )
}

function DishesEditor() {
  const queryClient = useQueryClient()
  const templatesQuery = useQuery({ queryKey: ['templates'], queryFn: ({ signal }) => listTemplates({ signal }) })
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [draft, setDraft] = useState<DishDraft>(emptyDish)
  const detailQuery = useQuery({ queryKey: ['templates', selectedId], queryFn: ({ signal }) => getTemplate(selectedId!, { signal }), enabled: selectedId !== null })

  useEffect(() => {
    if (detailQuery.data) setDraft(dishToDraft(detailQuery.data))
  }, [detailQuery.data])

  const save = useMutation({
    mutationFn: (request: SaveTemplateRequest) => selectedId ? updateTemplate(selectedId, request) : createTemplate(request),
    onSuccess: async (dish) => {
      queryClient.setQueryData(['templates', dish.id], dish)
      await queryClient.invalidateQueries({ queryKey: ['templates'] })
      setSelectedId(dish.id)
      setDraft(dishToDraft(dish))
    },
  })

  function submit(event: FormEvent) {
    event.preventDefault()
    const voteVariants = draft.voteVariants.map(item => ({ name: item.name.trim(), value: Number(item.value) }))
    if (voteVariants.some(item => !item.name || !Number.isFinite(item.value))) return
    save.mutate({ name: draft.name.trim(), isMultivote: draft.isMultivote, voteVariants, ingredients: draft.ingredients.map(item => ({ ...item, name: item.name.trim() })) })
  }

  if (templatesQuery.isPending) return <LoadingState label="Загружаем блюда…" />
  if (templatesQuery.isError) return <ErrorState message="Не удалось загрузить блюда." onRetry={() => templatesQuery.refetch()} />

  return (
    <div className="catalog-workspace">
      <CatalogList title="Блюда" addLabel="Добавить блюдо" onAdd={() => { setSelectedId(null); setDraft(emptyDish()); save.reset() }}>
        {templatesQuery.data?.map(dish => (
          <button key={dish.id} type="button" className={selectedId === dish.id ? 'is-selected' : ''} onClick={() => { setSelectedId(dish.id); save.reset() }}>
            <span>{dish.name}</span><small>{dish.isMultivote ? 'несколько вариантов' : 'один вариант'}</small>
          </button>
        ))}
      </CatalogList>
      <form className="catalog-editor" onSubmit={submit}>
        <EditorHeading title={selectedId ? 'Редактирование блюда' : 'Новое блюдо'} />
        {detailQuery.isFetching && selectedId ? <LoadingState label="Загружаем блюдо…" /> : <>
          <div className="catalog-fields"><label>Название<input required maxLength={200} value={draft.name} onChange={event => setDraft(current => ({ ...current, name: event.target.value }))} /></label></div>
          <label className="catalog-check"><input type="checkbox" checked={draft.isMultivote} onChange={event => setDraft(current => ({ ...current, isMultivote: event.target.checked }))} />Разрешить несколько вариантов порции</label>
          <CollectionHeading title="Варианты порции" onAdd={() => setDraft(current => ({ ...current, voteVariants: [...current.voteVariants, { name: '', value: '1' }] }))} />
          <div className="catalog-rows">
            {draft.voteVariants.length === 0 && <p className="catalog-empty">Добавьте хотя бы один вариант порции.</p>}
            {draft.voteVariants.map((variant, index) => (
              <div className="catalog-row catalog-row--variant" key={index}>
                <input required aria-label={`Вариант ${index + 1}`} placeholder="Название" value={variant.name} onChange={event => setDraft(current => ({ ...current, voteVariants: replaceAt(current.voteVariants, index, { ...variant, name: event.target.value }) }))} />
                <input required aria-label={`Коэффициент варианта ${index + 1}`} title="Коэффициент" type="number" step="any" value={variant.value} onChange={event => setDraft(current => ({ ...current, voteVariants: replaceAt(current.voteVariants, index, { ...variant, value: event.target.value }) }))} />
                <RowActions index={index} length={draft.voteVariants.length} onMove={(to) => setDraft(current => ({ ...current, voteVariants: move(current.voteVariants, index, to) }))} onRemove={() => setDraft(current => ({ ...current, voteVariants: current.voteVariants.filter((_, itemIndex) => itemIndex !== index) }))} />
              </div>
            ))}
          </div>
          <CollectionHeading title="Ингредиенты и расходы" onAdd={() => setDraft(current => ({ ...current, ingredients: [...current.ingredients, { name: '', enabled: true }] }))} />
          <div className="catalog-rows">
            {draft.ingredients.length === 0 && <p className="catalog-empty">Строк расходов пока нет.</p>}
            {draft.ingredients.map((ingredient, index) => (
              <div className="catalog-row catalog-row--ingredient" key={index}>
                <input required aria-label={`Ингредиент ${index + 1}`} placeholder="Название" value={ingredient.name} onChange={event => setDraft(current => ({ ...current, ingredients: replaceAt(current.ingredients, index, { ...ingredient, name: event.target.value }) }))} />
                <label className="catalog-check catalog-check--compact"><input type="checkbox" checked={ingredient.enabled} onChange={event => setDraft(current => ({ ...current, ingredients: replaceAt(current.ingredients, index, { ...ingredient, enabled: event.target.checked }) }))} />Включён</label>
                <RowActions index={index} length={draft.ingredients.length} onMove={(to) => setDraft(current => ({ ...current, ingredients: move(current.ingredients, index, to) }))} onRemove={() => setDraft(current => ({ ...current, ingredients: current.ingredients.filter((_, itemIndex) => itemIndex !== index) }))} />
              </div>
            ))}
          </div>
          <SaveBar pending={save.isPending} error={save.error ?? detailQuery.error} label={selectedId ? 'Сохранить изменения' : 'Добавить блюдо'} />
        </>}
      </form>
    </div>
  )
}

function CatalogList({ title, addLabel, onAdd, children }: { title: string; addLabel: string; onAdd: () => void; children: React.ReactNode }) {
  return <aside className="catalog-list"><div className="catalog-list__heading"><h2>{title}</h2><button type="button" onClick={onAdd}>+ Добавить</button></div><div className="catalog-list__items">{children}</div><button className="catalog-list__mobile-add button" type="button" onClick={onAdd}>{addLabel}</button></aside>
}

function EditorHeading({ title }: { title: string }) { return <div className="catalog-editor__heading"><span className="eyebrow">Карточка</span><h2>{title}</h2></div> }
function CollectionHeading({ title, onAdd }: { title: string; onAdd: () => void }) { return <div className="catalog-collection-heading"><h3>{title}</h3><button type="button" onClick={onAdd}>+ Добавить строку</button></div> }

function RowActions({ index, length, onMove, onRemove }: { index: number; length: number; onMove: (to: number) => void; onRemove: () => void }) {
  return <div className="catalog-row__actions"><button type="button" aria-label="Переместить выше" disabled={index === 0} onClick={() => onMove(index - 1)}>↑</button><button type="button" aria-label="Переместить ниже" disabled={index === length - 1} onClick={() => onMove(index + 1)}>↓</button><button type="button" aria-label="Удалить строку" onClick={onRemove}>×</button></div>
}

function SaveBar({ pending, error, label }: { pending: boolean; error: Error | null; label: string }) {
  const message = error instanceof ApiError && error.status === 409 ? error.message : error ? 'Не удалось сохранить изменения.' : null
  return <div className="catalog-save"><div aria-live="polite">{message && <p role="alert">{message}</p>}</div><button className="button" disabled={pending} type="submit">{pending ? 'Сохраняем…' : label}</button></div>
}

function userToDraft(user: User): UserDraft { return { name: user.name, permanentSale: String(user.permanentSale), enabled: user.enabled, contacts: user.contacts.map(item => ({ value: item.value })) } }
function dishToDraft(dish: TemplateDetail): DishDraft { return { name: dish.name, isMultivote: dish.isMultivote, voteVariants: dish.voteVariants.map(item => ({ name: item.name, value: String(item.value) })), ingredients: dish.ingredients.map(item => ({ name: item.name, enabled: item.enabled })) } }
function replaceAt<T>(items: T[], index: number, value: T): T[] { return items.map((item, itemIndex) => itemIndex === index ? value : item) }
function move<T>(items: T[], from: number, to: number): T[] { if (to < 0 || to >= items.length) return items; const result = [...items]; const [item] = result.splice(from, 1); result.splice(to, 0, item); return result }
