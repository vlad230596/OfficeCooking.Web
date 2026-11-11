import { useEffect, useState } from 'react'
import { readDraft, writeDraft } from './drafts'

/** Mount the form with a key when its account/storage key changes. */
export function useLocalDraft<T>(key: string, initial: () => T, validate: (value: unknown) => value is T) {
  const [value, setValue] = useState(() => readDraft(key, validate) ?? initial())
  const [storageFailed, setStorageFailed] = useState(false)
  useEffect(() => { setStorageFailed(!writeDraft(key, value)) }, [key, value])
  return [value, setValue, storageFailed] as const
}
