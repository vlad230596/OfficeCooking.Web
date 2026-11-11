import { useEffect, useMemo, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useAuth } from '../auth'
import { draftKey, readDraft, removeDraft, writeDraft } from '../drafts'
import {
  getCookPreparation, getTemplatePreparation, saveCookPreparation, saveTemplatePreparation,
  type PreparationGroup, type PreparationOption, type PreparationPlan, type TemplatePreparation, type CookPreparation,
} from '../api/preparation'
import './PreparationEditor.css'

type Participant = { userId: string; userName: string }
type SavedDraft = { plan: PreparationPlan; version: number }
function isDraft(value: unknown): value is SavedDraft {
  if (!value || typeof value !== 'object') return false
  const item = value as SavedDraft
  return Number.isInteger(item.version) && Array.isArray(item.plan?.options) && Array.isArray(item.plan?.groups)
    && item.plan.options.every(option => option !== null && typeof option === 'object' && typeof option.key === 'string' && typeof option.name === 'string'
      && Array.isArray(option.values) && option.values.every(value => typeof value === 'string') && Number.isInteger(option.batchSize))
    && item.plan.groups.every(group => group !== null && typeof group === 'object' && typeof group.userId === 'string' && Number.isInteger(group.quantity)
      && group.choices !== null && typeof group.choices === 'object' && Object.values(group.choices).every(value => typeof value === 'string'))
}

export function TemplatePreparationEditor({ templateId }: { templateId: string }) {
  return <PreparationEditor key={templateId} kind="template" id={templateId} members={[]} />
}
export function CookPreparationEditor({ cookId, rowVersion, members, onSaved }: {
  cookId: string; rowVersion: number; members: Participant[]; onSaved?: () => void
}) {
  return <PreparationEditor key={cookId} kind="cook" id={cookId} rowVersion={rowVersion} members={members} onSaved={onSaved} />
}

function PreparationEditor({ kind, id, rowVersion, members, onSaved }: {
  kind: 'template' | 'cook'; id: string; rowVersion?: number; members: Participant[]; onSaved?: () => void
}) {
  const { user, hasRole } = useAuth()
  const canEdit = hasRole(kind === 'template' ? 'admin' : 'editor')
  const client = useQueryClient()
  const key = draftKey(user?.id ?? 'anonymous', `preparation:${kind}:${id}`)
  const [draft, setDraft] = useState<SavedDraft | null>(null)
  const [dirty, setDirty] = useState(false)
  const [message, setMessage] = useState('')
  const initialized = useRef(false)
  const queryKey = ['preparation', kind, id, rowVersion]
  const query = useQuery<TemplatePreparation | CookPreparation>({ queryKey, queryFn: async ({ signal }) => kind === 'template' ? getTemplatePreparation(id, signal) : getCookPreparation(id, signal) })
  useEffect(() => {
    if (!query.data) return
    const version = 'version' in query.data ? query.data.version : query.data.rowVersion
    const saved = !initialized.current ? readDraft(key, isDraft) : null
    if (!initialized.current || !dirty) {
      setDraft(saved ?? { plan: { options: query.data.options, groups: query.data.groups }, version })
      if (saved) { setDirty(true); setMessage('Восстановлен черновик пожеланий.') }
    }
    initialized.current = true
  }, [query.data, key, dirty])
  function change(plan: PreparationPlan) {
    if (!draft) return
    const next = { ...draft, plan }
    setDraft(next); setDirty(true)
    setMessage(writeDraft(key, next) ? 'Черновик сохранён на этом устройстве.' : 'Не удалось сохранить черновик на устройстве.')
  }
  const save = useMutation<TemplatePreparation | CookPreparation, Error>({
    mutationFn: async () => kind === 'template' ? saveTemplatePreparation(id, draft!.plan, draft!.version) : saveCookPreparation(id, draft!.plan, draft!.version),
    onSuccess: async (result) => {
      const version = 'version' in result ? result.version : result.rowVersion
      setDraft({ plan: { options: result.options, groups: result.groups }, version })
      setDirty(false); removeDraft(key); setMessage('Пожелания сохранены.')
      client.setQueryData(queryKey, result)
      await client.invalidateQueries({ queryKey: ['cook', id] })
      onSaved?.()
    },
  })
  if (query.isPending) return <p role="status">Загружаем план приготовления…</p>
  if (query.isError) return <div role="alert">Не удалось загрузить план приготовления. <button type="button" onClick={() => query.refetch()}>Повторить</button></div>
  if (!draft) return null
  const plan = draft.plan
  const stale = (kind === 'cook' && rowVersion !== undefined && rowVersion !== draft.version)
    || (query.data && draft.version !== ('version' in query.data ? query.data.version : query.data.rowVersion))
  const invalid = plan.options.some(option => !option.name.trim() || !option.values.length || option.values.some(value => !value.trim()) || new Set(option.values).size !== option.values.length || !Number.isInteger(option.batchSize) || option.batchSize < 1 || option.batchSize > 1000)
  return <section id={kind === 'cook' ? 'cook-preparation' : undefined} className="preparation" aria-label={kind === 'template' ? 'Настройки приготовления блюда' : 'План приготовления'}>
    <div className="preparation__heading"><div><span className="eyebrow">Приготовление</span><h2>{kind === 'template' ? 'Варианты и пожелания' : 'Что приготовить'}</h2></div>{kind === 'cook' && <strong className="preparation__total">{plan.groups.reduce((sum, group) => sum + group.quantity, 0)} <small>шт.</small></strong>}</div>
    <p className="preparation__hint">{kind === 'template' ? 'Первое значение используется по умолчанию. Кратность проверяется по общему количеству, например прожарка партиями по 5.' : 'Количество изделий задаётся отдельно от расчёта стоимости. Пожелания не меняют сумму к оплате.'}</p>
    {kind === 'cook' && <PreparationSummary plan={plan} members={members} />}
    {canEdit && <details open={kind === 'template'}><summary>Настроить варианты приготовления</summary><fieldset className="preparation__controls" disabled={save.isPending}><OptionsEditor options={plan.options} onChange={options => change({ ...plan, options, groups: reconcileGroups(plan.groups, options) })} /></fieldset></details>}
    {kind === 'cook' && <>
      {canEdit && <div className="preparation__members">{members.map(member => <fieldset disabled={save.isPending} className="preparation__member" key={member.userId}><legend>{member.userName}</legend>
        {plan.groups.map((group, index) => group.userId === member.userId && <div className="preparation__group" key={index}>
          <label>Количество<input type="number" min="1" max="1000" value={group.quantity} onChange={event => change({ ...plan, groups: plan.groups.map((item, i) => i === index ? { ...item, quantity: Number(event.target.value) } : item) })} /></label>
          {plan.options.map(option => <label key={option.key}>{option.name}<select value={group.choices[option.key] ?? option.values[0]} onChange={event => change({ ...plan, groups: plan.groups.map((item, i) => i === index ? { ...item, choices: { ...item.choices, [option.key]: event.target.value } } : item) })}>{option.values.map(value => <option key={value}>{value}</option>)}</select></label>)}
          <button type="button" aria-label={`Удалить комбинацию ${index + 1} — ${member.userName}`} onClick={() => change({ ...plan, groups: plan.groups.filter((_, i) => i !== index) })}>Удалить</button>
        </div>)}
        <button type="button" onClick={() => change({ ...plan, groups: [...plan.groups, { userId: member.userId, quantity: 1, choices: Object.fromEntries(plan.options.map(option => [option.key, option.values[0]])) }] })}>+ Добавить порцию / комбинацию</button>
      </fieldset>)}</div>}
    </>}
    {stale && <p role="alert">Данные на сервере изменились. Черновик сохранён; обновите план перед сохранением.</p>}
    {stale && <button type="button" onClick={() => { if (!query.data) return; setDraft({ plan: { options: query.data.options, groups: query.data.groups }, version: 'version' in query.data ? query.data.version : query.data.rowVersion }); setDirty(false); removeDraft(key); setMessage('Загружен актуальный план.') }}>Отбросить черновик и загрузить актуальный план</button>}
    {canEdit && <div className="preparation__save"><span role="status">{message}</span><button type="button" className="button" disabled={!dirty || save.isPending || invalid || stale || plan.groups.some(group => !Number.isInteger(group.quantity) || group.quantity < 1 || group.quantity > 1000)} onClick={() => save.mutate()}>{save.isPending ? 'Сохраняем…' : 'Сохранить пожелания'}</button></div>}
    {save.error && <p role="alert">{save.error.message} Черновик сохранён.</p>}
  </section>
}

function reconcileGroups(groups: PreparationGroup[], options: PreparationOption[]): PreparationGroup[] {
  return groups.map(group => ({ ...group, choices: Object.fromEntries(options.map(option => [option.key, option.values.includes(group.choices[option.key]) ? group.choices[option.key] : option.values[0]])) }))
}

function OptionsEditor({ options, onChange }: { options: PreparationOption[]; onChange: (options: PreparationOption[]) => void }) {
  function update(index: number, patch: Partial<PreparationOption>) { onChange(options.map((option, i) => i === index ? { ...option, ...patch } : option)) }
  return <div className="preparation__options">{options.map((option, index) => <div className="preparation__option" key={option.key}>
    <label>Название настройки<input maxLength={200} value={option.name} onChange={event => update(index, { name: event.target.value })} placeholder="Например, прожарка" /></label>
    <label>Значения через запятую<input value={option.values.join(',')} onChange={event => update(index, { values: event.target.value.split(',').map(value => value.trim()) })} placeholder="Medium, Well done" /></label>
    <label>Кратность партии<input type="number" min="1" max="1000" value={option.batchSize} onChange={event => update(index, { batchSize: Number(event.target.value) })} /></label>
    <button type="button" aria-label={`Удалить настройку ${option.name || index + 1}`} onClick={() => onChange(options.filter((_, i) => i !== index))}>Удалить</button>
  </div>)}<button type="button" onClick={() => onChange([...options, { key: crypto.randomUUID(), name: '', values: ['Обычный'], batchSize: 1 }])}>+ Добавить настройку</button></div>
}

export function PreparationSummary({ plan, members }: { plan: PreparationPlan; members: Participant[] }) {
  const combinations = useMemo(() => {
    const result = new Map<string, { quantity: number; choices: string[]; people: Map<string, number> }>()
    for (const group of plan.groups) {
      const choices = plan.options.map(option => `${option.name}: ${group.choices[option.key] ?? option.values[0]}`)
      const key = JSON.stringify(choices)
      const item = result.get(key) ?? { quantity: 0, choices, people: new Map<string, number>() }
      item.quantity += group.quantity
      item.people.set(group.userId, (item.people.get(group.userId) ?? 0) + group.quantity)
      result.set(key, item)
    }
    return [...result.values()]
  }, [plan])
  return <div className="preparation__summary">
    <h3>Сборка по комбинациям</h3>
    {!combinations.length && <p className="preparation__hint">Добавьте количество и пожелания участников — здесь появятся карточки для приготовления.</p>}
    <div className="preparation__cards">{combinations.map((item, index) => <article className="preparation__card" key={index}><strong className="preparation__quantity">{item.quantity}<small>шт.</small></strong><div className="preparation__badges">{item.choices.length ? item.choices.map(choice => <span key={choice}>{choice}</span>) : <span>Обычная порция</span>}</div><div className="preparation__people">{[...item.people].map(([userId, quantity]) => <span key={userId}>{members.find(member => member.userId === userId)?.userName ?? 'Участник'} · {quantity}</span>)}</div></article>)}</div>
    {plan.options.length > 0 && <h3>Партии по настройкам</h3>}
    <div className="preparation__batches">{plan.options.flatMap(option => option.values.map(value => {
      const quantity = plan.groups.filter(group => (group.choices[option.key] ?? option.values[0]) === value).reduce((sum, group) => sum + group.quantity, 0)
      const remainder = quantity % option.batchSize
      return <article className={`preparation__batch${remainder ? ' preparation__batch--warning' : ''}`} key={`${option.key}:${value}`}><div><span>{option.name}</span><strong>{value}</strong></div><b>{quantity} шт.</b><progress aria-label={`${option.name}: ${value}, заполнение партии`} max={option.batchSize} value={remainder || (quantity ? option.batchSize : 0)} />{remainder ? <p><svg aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M12 3 2 21h20L12 3Z"/><path d="M12 9v5m0 3v1"/></svg> {quantity} шт. — нужно кратно {option.batchSize}. До полной партии: {option.batchSize - remainder}.</p> : <p>{option.batchSize === 1 ? 'Любое количество' : `${quantity / option.batchSize} полных партий по ${option.batchSize}`}</p>}</article>
    }))}</div>
  </div>
}
