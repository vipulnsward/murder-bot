import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api, type TaskRuntime } from '../api'

interface Props {
  tasks: TaskRuntime[]
  offline?: boolean
}

function time(value: string | null) {
  return value ? new Date(value).toLocaleTimeString([], { hour12: false }) : '—'
}

function guardValue(value: unknown) {
  if (Array.isArray(value)) return value.join(', ')
  if (typeof value === 'object' && value !== null) return JSON.stringify(value)
  return String(value)
}

export function TaskTable({ tasks, offline = false }: Props) {
  const [expanded, setExpanded] = useState<string | null>(null)
  const queryClient = useQueryClient()
  const toggle = useMutation({
    mutationFn: api.toggleTask,
    onMutate: async (name) => {
      await queryClient.cancelQueries({ queryKey: ['tasks'] })
      const previous = queryClient.getQueryData<{ tasks: TaskRuntime[] }>(['tasks'])
      queryClient.setQueryData<{ tasks: TaskRuntime[] }>(['tasks'], (current) => current && ({
        tasks: current.tasks.map((item) => item.name === name ? { ...item, enabled: !item.enabled } : item),
      }))
      return previous
    },
    onError: (_error, _name, previous) => queryClient.setQueryData(['tasks'], previous),
    onSettled: () => queryClient.invalidateQueries({ queryKey: ['tasks'] }),
  })

  return (
    <div className="overflow-hidden rounded-card border border-border bg-surface">
      <div className="overflow-x-auto">
        <table className="w-full min-w-[780px] text-left text-sm">
          <thead className="border-b border-border bg-surface-2 text-xs uppercase tracking-[0.06em] text-muted">
            <tr>
              <th className="px-4 py-3 font-medium">Task</th>
              <th className="px-3 py-3 font-medium">Enabled</th>
              <th className="px-3 py-3 font-medium">Interval</th>
              <th className="px-3 py-3 font-medium">Priority</th>
              <th className="px-3 py-3 font-medium">Last</th>
              <th className="px-3 py-3 font-medium">Next</th>
              <th className="px-3 py-3 font-medium">State</th>
              <th className="px-3 py-3 font-medium"><span className="sr-only">Expand</span></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {tasks.map((task) => {
              const open = expanded === task.name
              return (
                <tr className="group" key={task.name}>
                  <td colSpan={8} className="p-0">
                    <div className="grid min-h-10 grid-cols-[minmax(160px,1fr)_90px_90px_90px_110px_110px_120px_40px] items-center hover:bg-surface-2/60">
                      <div className="px-4 font-medium">{task.name} {!task.wired && <span className="ml-1 rounded bg-surface-2 px-1.5 py-0.5 text-[11px] text-warn">wire</span>}</div>
                      <div className="px-3">
                        <button
                          aria-checked={task.enabled}
                          aria-label={`${task.enabled ? 'Disable' : 'Enable'} ${task.name}`}
                          className={`relative h-5 w-9 rounded-full transition ${task.enabled ? 'bg-accent' : 'bg-border'} disabled:cursor-not-allowed disabled:opacity-50`}
                          disabled={offline || (toggle.isPending && toggle.variables === task.name)}
                          onClick={() => toggle.mutate(task.name)}
                          role="switch"
                          type="button"
                        >
                          <span className={`absolute top-0.5 h-4 w-4 rounded-full bg-white transition ${task.enabled ? 'left-[18px]' : 'left-0.5'}`} />
                        </button>
                      </div>
                      <div className="px-3 font-mono tabular-nums">{task.interval}s</div>
                      <div className="px-3 font-mono tabular-nums">{task.priority}</div>
                      <div className="px-3 font-mono text-muted tabular-nums">{time(task.last_run)}</div>
                      <div className="px-3 font-mono text-muted tabular-nums">{time(task.next_run)}</div>
                      <div className="px-3"><span className="rounded bg-surface-2 px-2 py-1 text-xs text-muted">{task.state}</span></div>
                      <button
                        aria-expanded={open}
                        aria-label={`${open ? 'Collapse' : 'Expand'} ${task.name} policy`}
                        className="h-10 text-muted hover:text-text"
                        onClick={() => setExpanded(open ? null : task.name)}
                        type="button"
                      >
                        {open ? '▴' : '▾'}
                      </button>
                    </div>
                    {open && (
                      <div className="border-t border-border bg-surface-2/50 px-4 py-4">
                        <p className="mb-3 text-xs uppercase tracking-[0.06em] text-muted">Policy parameters</p>
                        {Object.keys(task.guard).length ? (
                          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                            {Object.entries(task.guard).map(([key, value]) => (
                              <label className="text-xs text-muted" key={key}>
                                {key}
                                <input className="field mt-1 font-mono" disabled value={guardValue(value)} />
                              </label>
                            ))}
                          </div>
                        ) : <p className="text-sm text-muted">No safety policy fields reported.</p>}
                      </div>
                    )}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
