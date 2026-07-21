import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, type KeepConfig } from '../api'
import { ConfigForm } from '../components/ConfigForm'
import { DEFAULT_CONFIG } from '../defaults'

export function Config() {
  const queryClient = useQueryClient()
  const query = useQuery({ queryKey: ['config'], queryFn: api.getConfig, retry: false })
  const [draft, setDraft] = useState<KeepConfig>(DEFAULT_CONFIG)

  useEffect(() => {
    if (query.data) setDraft(query.data)
  }, [query.data])

  const save = useMutation({
    mutationFn: api.putConfig,
    onSuccess: ({ config }) => {
      setDraft(config)
      queryClient.setQueryData(['config'], config)
    },
  })
  const source = query.data ?? DEFAULT_CONFIG
  const dirty = JSON.stringify(draft) !== JSON.stringify(source)

  return (
    <div>
      <div className="page-heading"><div><p className="eyebrow">Validated settings</p><h1>Config</h1></div><span className="font-mono text-sm text-muted">v{draft.version}</span></div>
      {query.isPending && <div className="mb-4 text-sm text-muted">Loading config…</div>}
      {query.isError && <div className="offline-banner">Backend unavailable. Defaults are shown read-only so no partial config can be submitted.</div>}
      {save.isError && <div className="error-banner">{save.error.message}</div>}
      <ConfigForm
        config={draft}
        dirty={dirty}
        disabled={!query.data}
        onChange={setDraft}
        onRevert={() => setDraft(source)}
        onSave={() => save.mutate(draft)}
        saving={save.isPending}
      />
    </div>
  )
}
