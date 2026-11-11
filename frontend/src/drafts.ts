/** Browser drafts are local to this account and never replace server data. */
export function draftKey(accountId: string, form: string): string {
  return `office-cook:draft:v1:${encodeURIComponent(accountId)}:${form}`
}

export function readDraft<T>(key: string, validate: (value: unknown) => value is T): T | null {
  try {
    const raw = window.localStorage.getItem(key)
    if (!raw) return null
    const value: unknown = JSON.parse(raw)
    return validate(value) ? value : null
  } catch { return null }
}

export function writeDraft(key: string, value: unknown): boolean {
  try {
    window.localStorage.setItem(key, JSON.stringify(value))
    return true
  } catch { return false }
}

export function removeDraft(key: string): boolean {
  try { window.localStorage.removeItem(key); return true } catch { return false }
}
