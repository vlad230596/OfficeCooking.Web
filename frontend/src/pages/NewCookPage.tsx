import { useEffect, useMemo, useRef, useState } from 'react'
import { useMutation, useQueries, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useNavigate, useParams } from 'react-router-dom'
import {
  ApiError,
  createCook,
  getCook,
  getTemplate,
  listCooks,
  listTemplates,
  listUsers,
  previewExpression,
  previewCook,
  updateCook,
  updateTemplate,
} from '../api'
import type {
  CookDetail,
  CookVoteVariant,
  CreateCookRequest,
  IsoDate,
  TemplateIngredient,
  UpdateCookRequest,
  UUID,
} from '../api'
import { ErrorState, LoadingState } from '../components/AsyncState'
import { PageIntro } from '../components/PageIntro'
import { formatQuantity, formatWholeAmount } from '../format'
import { useAuth } from '../auth'
import './NewCookPage.css'

type MemberDraft = { id?: UUID; userId: UUID; active: boolean; selectedVotes: UUID[] }
type ExpenseDraft = { id?: UUID; productName: string | null; expression: string; enabled?: boolean }

const today = (): IsoDate => {
  const value = new Date()
  const year = value.getFullYear()
  const month = String(value.getMonth() + 1).padStart(2, '0')
  const day = String(value.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}` as IsoDate
}

function useDebouncedExpressions(expenses: ExpenseDraft[]) {
  const expressions = useMemo(() => expenses.map((item) => item.expression), [expenses])
  const [debounced, setDebounced] = useState(expressions)
  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(expressions), 350)
    return () => window.clearTimeout(timer)
  }, [expressions])
  return debounced
}

const errorMessage = (error: unknown) => error instanceof Error ? error.message : 'Не удалось выполнить запрос.'

export function NewCookPage() {
  const { cookId } = useParams<{ cookId?: UUID }>()
  const isEditing = Boolean(cookId)
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { hasRole } = useAuth()
  const initializedCook = useRef<UUID | null>(null)
  const initializedTemplate = useRef<UUID | null>(null)
  const [cookDate, setCookDate] = useState<IsoDate>(today)
  const [templateId, setTemplateId] = useState<UUID>('')
  const [showDisabledUsers, setShowDisabledUsers] = useState(false)
  const [showParticipantsOnly, setShowParticipantsOnly] = useState(true)
  const [members, setMembers] = useState<MemberDraft[]>([])
  const [expenses, setExpenses] = useState<ExpenseDraft[]>([])
  const [submitMessage, setSubmitMessage] = useState<string | null>(null)
  const [templateMessage, setTemplateMessage] = useState<string | null>(null)

  const usersQuery = useQuery({
    queryKey: ['users', 'all'],
    queryFn: ({ signal }) => listUsers({ enabled: 'all', signal }),
  })
  const templatesQuery = useQuery({
    queryKey: ['templates'],
    queryFn: ({ signal }) => listTemplates({ signal }),
  })
  const cookQuery = useQuery({
    queryKey: ['cook', cookId],
    queryFn: ({ signal }) => getCook(cookId!, { signal }),
    enabled: isEditing,
  })
  const dateAvailabilityQuery = useQuery({
    queryKey: ['cook-date-availability', cookDate],
    queryFn: ({ signal }) => listCooks({
      dateFrom: cookDate,
      dateTo: cookDate,
      page: 1,
      pageSize: 2,
      signal,
    }),
    enabled: Boolean(cookDate) && (!isEditing || Boolean(cookQuery.data)),
  })
  const conflictingCook = dateAvailabilityQuery.data?.items.find((item) => item.id !== cookId)

  useEffect(() => {
    if (!isEditing && !templateId && templatesQuery.data?.[0]) setTemplateId(templatesQuery.data[0].id)
  }, [isEditing, templateId, templatesQuery.data])

  const templateQuery = useQuery({
    queryKey: ['template', templateId],
    queryFn: ({ signal }) => getTemplate(templateId, { signal }),
    enabled: Boolean(templateId),
  })

  useEffect(() => {
    if (!usersQuery.data) return
    const visibleUsers = isEditing || showDisabledUsers
      ? usersQuery.data
      : usersQuery.data.filter((user) => user.enabled)
    setMembers((current) => visibleUsers.map((user) => current.find((item) => item.userId === user.id)
      ?? { userId: user.id, active: false, selectedVotes: [] }))
  }, [isEditing, showDisabledUsers, usersQuery.data])

  useEffect(() => {
    const template = templateQuery.data
    if (isEditing || !template || initializedTemplate.current === template.id) return
    initializedTemplate.current = template.id
    setMembers((current) => current.map((member) => ({ ...member, selectedVotes: [] })))
    setExpenses(template.ingredients.map(toExpenseDraft))
  }, [isEditing, templateQuery.data])

  useEffect(() => {
    const cook = cookQuery.data
    if (!cook || initializedCook.current === cook.id) return
    initializedCook.current = cook.id
    setCookDate(cook.cookDate)
    setTemplateId(cook.templateId ?? '')
    setMembers(mergeCookMembers(cook, usersQuery.data ?? []))
    setExpenses(cook.productPrices.map((item) => ({
      id: item.id,
      productName: item.productName,
      expression: item.expression ?? '',
    })))
  }, [cookQuery.data, usersQuery.data])

  const voteVariants = isEditing ? cookQuery.data?.voteVariants ?? [] : templateQuery.data?.voteVariants ?? []
  const debouncedExpressions = useDebouncedExpressions(expenses)
  const previewQueries = useQueries({
    queries: debouncedExpressions.map((expression, index) => ({
      queryKey: ['expression-preview', index, expression],
      queryFn: ({ signal }: { signal: AbortSignal }) => previewExpression({ expression }, { signal }),
      enabled: expenses[index]?.expression === expression,
      staleTime: Number.POSITIVE_INFINITY,
    })),
  })
  const previewsReady = previewQueries.length === expenses.length
    && debouncedExpressions.every((expression, index) => expenses[index]?.expression === expression)
    && previewQueries.every((query) => query.isSuccess && query.data.status !== 'error')
  const totalPreview = previewsReady
    ? previewQueries.reduce((sum, query) => sum + (query.data?.computedValue ?? 0), 0)
    : null
  const voteSummary = useMemo(() => voteVariants.map((vote) => {
    const count = members.filter((member) => member.selectedVotes.includes(vote.id)).length
    return { id: vote.id, name: vote.name, count, weight: count * vote.value }
  }), [members, voteVariants])
  const totalVoteWeight = voteSummary.reduce((sum, item) => sum + item.weight, 0)
  const draftPreviewRequest = useMemo(() => ({
    cookId: cookId ?? null,
    voteVariants: voteVariants.map((vote) => ({ id: vote.id, position: vote.position, value: vote.value })),
    members: participatingMembers(members).map((member, position) => ({
      position,
      userId: member.userId,
      active: member.active,
      cookVoteVariantIds: member.selectedVotes,
    })),
    productPrices: expenses.map((expense, position) => ({
      position,
      productName: expense.productName,
      expression: debouncedExpressions[position] ?? '',
    })),
  }), [cookId, debouncedExpressions, expenses, members, voteVariants])
  const draftPreviewQuery = useQuery({
    queryKey: ['cook-draft-preview', draftPreviewRequest],
    queryFn: ({ signal }) => previewCook(draftPreviewRequest, { signal }),
    enabled: previewsReady && draftPreviewRequest.members.length > 0 && voteVariants.length > 0,
  })
  const chargeByUserId = useMemo(
    () => new Map(draftPreviewQuery.data?.members.map((member) => [member.userId, member.charge]) ?? []),
    [draftPreviewQuery.data?.members],
  )
  const savedChargeByUserId = useMemo(
    () => new Map(cookQuery.data?.members.map((member) => [member.userId, member.charge]) ?? []),
    [cookQuery.data?.members],
  )
  const displayedMembers = useMemo(
    () => isEditing && showParticipantsOnly ? participatingMembers(members) : members,
    [isEditing, members, showParticipantsOnly],
  )
  const currentUpdateRequest = useMemo(
    () => cookQuery.data
      ? makeUpdateRequest(cookQuery.data, cookDate, members, expenses)
      : null,
    [cookDate, cookQuery.data, expenses, members],
  )
  const initialUpdateRequest = useMemo(() => {
    const cook = cookQuery.data
    if (!cook) return null
    return makeUpdateRequest(
      cook,
      cook.cookDate,
      mergeCookMembers(cook, usersQuery.data ?? []),
      cook.productPrices.map((item) => ({
        id: item.id,
        productName: item.productName,
        expression: item.expression ?? '',
      })),
    )
  }, [cookQuery.data, usersQuery.data])
  const hasChanges = !isEditing || JSON.stringify(currentUpdateRequest) !== JSON.stringify(initialUpdateRequest)

  const templateMutation = useMutation({
    mutationFn: () => updateTemplate(templateId, {
      name: templateQuery.data!.name,
      isMultivote: templateQuery.data!.isMultivote,
      voteVariants: templateQuery.data!.voteVariants.map((variant) => ({
        name: variant.name,
        value: variant.value,
      })),
      ingredients: expenses.map((expense) => ({
        name: expense.productName!.trim(),
        enabled: expense.enabled ?? true,
      })),
    }),
    onMutate: () => setTemplateMessage(null),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['templates'] })
      setTemplateMessage('Состав шаблона обновлён. Сохранённые готовки не изменились.')
    },
    onError: (error) => setTemplateMessage(errorMessage(error)),
  })
  const canUpdateTemplate = hasRole('admin')
    && Boolean(templateId)
    && Boolean(templateQuery.data)
    && expenses.length <= 200
    && expenses.every((expense) => {
      const name = expense.productName?.trim() ?? ''
      return name.length > 0 && name.length <= 200
    })
    && !templateMutation.isPending

  const mutation = useMutation({
    mutationFn: () => isEditing
      ? updateCook(cookId!, currentUpdateRequest!)
      : createCook(makeCreateRequest(cookDate, templateId, members, expenses, voteVariants)),
    onSuccess: () => navigate('/cooks'),
    onError: (error) => {
      if (error instanceof ApiError && error.status === 409) {
        if (error.code === 'cook_date_conflict') {
          setSubmitMessage('На выбранную дату уже существует готовка. Откройте её из списка готовок для редактирования.')
        } else {
          const current = typeof error.details.currentVersion === 'number'
            ? ` Текущая версия: ${error.details.currentVersion}.`
            : ''
          setSubmitMessage(`Готовка была изменена в другом окне.${current} Обновите страницу и повторите.`)
        }
      } else setSubmitMessage(errorMessage(error))
    },
  })

  const loading = usersQuery.isPending || templatesQuery.isPending
    || (isEditing ? cookQuery.isPending : Boolean(templateId) && templateQuery.isPending)
  const loadingError = usersQuery.error || templatesQuery.error || cookQuery.error || templateQuery.error
  const canSubmit = Boolean(cookDate) && (isEditing ? Boolean(cookQuery.data) : Boolean(templateId))
    && members.some((member) => member.selectedVotes.length > 0)
    && previewsReady
    && draftPreviewQuery.isSuccess
    && hasChanges
    && !conflictingCook
    && !dateAvailabilityQuery.isPending
    && !mutation.isPending

  if (loading || loadingError) return (
    <section className="cook-editor">
      <PageIntro
        eyebrow={isEditing ? 'Редактирование' : 'Новая запись'}
        title={isEditing ? 'Редактирование готовки' : 'Новая готовка'}
        description="Дата, участники, варианты порций и Legacy-выражения расходов."
      />
      {loading
        ? <LoadingState label="Загрузка редактора готовки…" />
        : <ErrorState message={errorMessage(loadingError)} onRetry={() => window.location.reload()} />}
    </section>
  )

  return (
    <section className="cook-editor">
      <PageIntro
        eyebrow={isEditing ? 'Редактирование' : 'Новая запись'}
        title={isEditing ? 'Редактирование готовки' : 'Новая готовка'}
        description="Дата, участники, варианты порций и Legacy-выражения расходов."
        actions={<button className="button" type="submit" form="cook-form" disabled={!canSubmit}>{mutation.isPending ? 'Сохранение…' : 'Сохранить'}</button>}
      />
      <form id="cook-form" onSubmit={(event) => { event.preventDefault(); setSubmitMessage(null); mutation.mutate() }}>
        {isEditing && cookQuery.data && (
          <div className="editor-mode-note" role="note">
            <strong>Редактирование сохранённой готовки</strong>
            <span>Дата: {formatDisplayDate(cookQuery.data.cookDate)} · Сохранённая общая сумма: {cookQuery.data.totalPrice === null ? 'ошибка расчёта' : formatWholeAmount(cookQuery.data.totalPrice)}</span>
          </div>
        )}
        {submitMessage && <div className="editor-alert" role="alert">{submitMessage}</div>}
        {conflictingCook && <div className="editor-alert" role="alert">На {formatDisplayDate(cookDate)} уже есть готовка «{conflictingCook.typeSnapshot}». <Link to={`/cooks/${conflictingCook.id}`}>Открыть её для редактирования</Link>.</div>}
        <article className="editor-panel">
          <div className="editor-panel__heading"><span>01</span><h2>Параметры</h2></div>
          <div className="editor-fields">
            <label>Дата готовки<input required type="date" value={cookDate} onChange={(event) => setCookDate(event.target.value as IsoDate)} /></label>
            <label>Блюдо
              <select required disabled={isEditing} value={templateId} onChange={(event) => { initializedTemplate.current = null; setTemplateId(event.target.value) }}>
                <option value="">Выберите блюдо</option>
                {templatesQuery.data?.map((template) => <option key={template.id} value={template.id}>{template.name}</option>)}
              </select>
            </label>
            {!isEditing && <label className="editor-fields__checkbox"><input type="checkbox" checked={showDisabledUsers} onChange={(event) => setShowDisabledUsers(event.target.checked)} />Показывать отключённых пользователей</label>}
            {isEditing && <label className="editor-fields__checkbox"><input type="checkbox" checked={showParticipantsOnly} onChange={(event) => setShowParticipantsOnly(event.target.checked)} />Показывать только участников</label>}
          </div>
        </article>

        <article className="editor-panel">
          <div className="editor-panel__heading"><span>02</span><div><h2>Участники</h2><p>Можно выбрать несколько вариантов для любого блюда.</p></div></div>
          <div className="editor-table-wrap">
            <table className="member-table" aria-label="Участники и варианты порций">
              <thead><tr><th>Участник</th><th>Активен</th>{voteVariants.map((vote) => <th key={vote.id}>{vote.name}</th>)}<th>К оплате</th></tr></thead>
              <tbody>{displayedMembers.map((member) => {
                const userName = usersQuery.data?.find((item) => item.id === member.userId)?.name
                  ?? cookQuery.data?.members.find((item) => item.userId === member.userId)?.userName
                const displayName = userName ?? member.userId
                return (
                  <tr key={member.userId} role="group" aria-label={displayName}>
                    <th scope="row">{displayName}</th>
                    <td><input aria-label={`Активен — ${displayName}`} type="checkbox" checked={member.active} onChange={(event) => updateMember(member.userId, { active: event.target.checked }, setMembers)} /></td>
                    {voteVariants.map((vote) => (
                      <td key={vote.id}><input aria-label={vote.name} type="checkbox" checked={member.selectedVotes.includes(vote.id)} onChange={() => toggleVote(member.userId, vote.id, setMembers)} /></td>
                    ))}
                    <td className="member-table__charge">{member.selectedVotes.length === 0
                      ? '—'
                      : chargeByUserId.has(member.userId)
                        ? formatWholeAmount(chargeByUserId.get(member.userId) ?? 0)
                        : savedChargeByUserId.get(member.userId) !== null && savedChargeByUserId.get(member.userId) !== undefined
                          ? formatWholeAmount(savedChargeByUserId.get(member.userId)!)
                          : draftPreviewQuery.isError
                            ? 'Ошибка'
                            : '…'}</td>
                  </tr>
                )
              })}</tbody>
            </table>
          </div>
          <div className="vote-summary" aria-label="Итоги выбранных вариантов">
            {voteSummary.map((item) => <span key={item.id}>{item.name}: <strong>{item.count}</strong></span>)}
            <span>Общий вес: <strong>{formatQuantity(totalVoteWeight)}</strong></span>
            {draftPreviewQuery.isError && <span className="member-preview-error" role="alert">Не удалось рассчитать стоимость участников.</span>}
          </div>
        </article>

        <article className="editor-panel">
          <div className="editor-panel__heading"><span>03</span><div><h2>Расходы</h2><p>Состав блюда — начальная заготовка; эта готовка сохранится отдельно.</p></div><div className="expense-actions">{hasRole('admin') && <button className="expense-add" type="button" disabled={!canUpdateTemplate} title="Сохраняет в шаблон названия и порядок строк, но не выражения" onClick={() => templateMutation.mutate()}>{templateMutation.isPending ? 'Обновление…' : 'Обновить шаблон составом'}</button>}<button className="expense-add" type="button" onClick={() => setExpenses((current) => [...current, { productName: '', expression: '' }])}>+ Добавить строку</button></div></div>
          {templateMessage && <div className={templateMutation.isError ? 'template-update-status template-update-status--error' : 'template-update-status'} role={templateMutation.isError ? 'alert' : 'status'}>{templateMessage}</div>}
          <div className="editor-table-wrap">
            <table className="expense-table">
              <thead><tr><th>Название расхода</th><th>Выражение</th><th>Результат</th><th><span className="sr-only">Действия</span></th></tr></thead>
              <tbody>{expenses.map((expense, index) => {
              const preview = previewQueries[index]
              const error = preview?.data?.status === 'error' ? preview.data.error : preview?.error ? errorMessage(preview.error) : null
              return (
                <tr key={expense.id ?? `${expense.productName}-${index}`}>
                  <td><label className="sr-only" htmlFor={`expense-name-${index}`}>Название расхода</label><input id={`expense-name-${index}`} value={expense.productName ?? ''} onChange={(event) => setExpenses((current) => current.map((item, position) => position === index ? { ...item, productName: event.target.value || null } : item))} placeholder={`Расход ${index + 1}`} />{expense.enabled === false && <small>Отключён в блюде, сохранён для Legacy</small>}</td>
                  <td><label className="sr-only" htmlFor={`expense-expression-${index}`}>Выражение</label><input id={`expense-expression-${index}`} aria-invalid={Boolean(error)} aria-describedby={error ? `expense-error-${index}` : undefined} value={expense.expression} onChange={(event) => setExpenses((current) => current.map((item, position) => position === index ? { ...item, expression: event.target.value } : item))} placeholder="Например, 2*350+90" />{error && <small className="expense-row__error" id={`expense-error-${index}`}>{error}</small>}</td>
                  <td><output aria-live="polite">{!preview || preview.isPending ? '…' : error ? 'Ошибка' : formatWholeAmount(preview.data?.computedValue ?? 0)}</output></td>
                  <td><button className="expense-remove" type="button" aria-label={`Удалить расход ${expense.productName || index + 1}`} onClick={() => setExpenses((current) => current.filter((_, position) => position !== index))}>×</button></td>
                </tr>
              )
            })}</tbody>
            </table>
          </div>
          <div className="expense-total"><span>Предварительный итог</span><strong>{totalPreview === null ? '—' : formatWholeAmount(totalPreview)}</strong></div>
        </article>
        <div className="editor-submit"><button className="button" type="submit" disabled={!canSubmit}>{mutation.isPending ? 'Сохранение…' : 'Сохранить готовку'}</button></div>
      </form>
    </section>
  )
}

function toExpenseDraft(item: TemplateIngredient): ExpenseDraft {
  return { productName: item.name, expression: '', enabled: item.enabled }
}

function mergeCookMembers(cook: CookDetail, users: Array<{ id: UUID }>): MemberDraft[] {
  const existing = new Map(cook.members.map((member) => [member.userId, member]))
  const ids = [...new Set([...users.map((user) => user.id), ...cook.members.map((member) => member.userId)])]
  return ids.map((userId) => {
    const member = existing.get(userId)
    return { id: member?.id, userId, active: member?.active ?? false, selectedVotes: member?.cookVoteVariantIds ?? [] }
  })
}

type SetMembers = React.Dispatch<React.SetStateAction<MemberDraft[]>>
function updateMember(userId: UUID, update: Partial<MemberDraft>, setMembers: SetMembers) {
  setMembers((current) => current.map((member) => member.userId === userId ? { ...member, ...update } : member))
}
function toggleVote(userId: UUID, voteId: UUID, setMembers: SetMembers) {
  setMembers((current) => current.map((member) => member.userId !== userId ? member : {
    ...member,
    selectedVotes: member.selectedVotes.includes(voteId)
      ? member.selectedVotes.filter((id) => id !== voteId)
      : [...member.selectedVotes, voteId],
  }))
}
const participatingMembers = (members: MemberDraft[]) => members.filter((member) => member.selectedVotes.length > 0)

function makeCreateRequest(cookDate: IsoDate, templateId: UUID, members: MemberDraft[], expenses: ExpenseDraft[], votes: CookVoteVariant[]): CreateCookRequest {
  const positionById = new Map(votes.map((vote) => [vote.id, vote.position]))
  return {
    cookDate,
    templateId,
    members: participatingMembers(members).map((member, position) => ({
      position, userId: member.userId, active: member.active,
      voteVariantPositions: member.selectedVotes.map((id) => positionById.get(id)!).sort((a, b) => a - b),
    })),
    productPrices: expenses.map((expense, position) => ({ position, productName: expense.productName, expression: expense.expression })),
  }
}

function makeUpdateRequest(cook: CookDetail, cookDate: IsoDate, members: MemberDraft[], expenses: ExpenseDraft[]): UpdateCookRequest {
  return {
    expectedVersion: cook.rowVersion,
    cookDate,
    voteVariants: cook.voteVariants.map((vote) => ({ ...vote })),
    members: participatingMembers(members).map((member, position) => ({
      id: member.id, position, userId: member.userId, active: member.active, cookVoteVariantIds: member.selectedVotes,
    })),
    productPrices: expenses.map((expense, position) => ({
      id: expense.id, position, productName: expense.productName, expression: expense.expression,
    })),
  }
}

function formatDisplayDate(value: string): string { const [year, month, day] = value.split('-'); return `${day}.${month}.${year}` }
