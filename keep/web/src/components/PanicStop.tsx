import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../api'

export function PanicStop() {
  const queryClient = useQueryClient()
  const panic = useMutation({
    mutationFn: () => api.control('panic_stop'),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['status'] }),
  })

  return (
    <button
      className="rounded-lg bg-bad px-3 py-2 text-sm font-semibold text-[#1c1111] transition hover:brightness-110 disabled:cursor-wait disabled:opacity-60"
      disabled={panic.isPending}
      onClick={() => panic.mutate()}
      title={panic.isError ? panic.error.message : undefined}
      type="button"
    >
      {panic.isPending ? 'Stopping…' : panic.isError ? 'Stop failed' : 'Panic Stop'}
    </button>
  )
}
