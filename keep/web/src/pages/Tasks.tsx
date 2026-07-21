import { useQuery } from '@tanstack/react-query'
import { api } from '../api'
import { TaskTable } from '../components/TaskTable'
import { DEFAULT_TASKS } from '../defaults'

export function Tasks() {
  const query = useQuery({ queryKey: ['tasks'], queryFn: api.getTasks, retry: false })
  const tasks = query.data?.tasks ?? DEFAULT_TASKS

  return (
    <div>
      <div className="page-heading"><div><p className="eyebrow">Runtime</p><h1>Tasks</h1></div><span className="text-sm text-muted">{tasks.length} registered tasks</span></div>
      {query.isPending && <div className="mb-4 text-sm text-muted">Loading task state…</div>}
      {query.isError && <div className="offline-banner">Backend unavailable. Showing configured defaults; toggles are disabled.</div>}
      {!query.isPending && !query.isError && tasks.length === 0 ? <div className="empty-state">No tasks returned by the backend.</div> : <TaskTable offline={query.isError} tasks={tasks} />}
    </div>
  )
}
