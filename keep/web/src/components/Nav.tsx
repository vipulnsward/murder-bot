import { NavLink } from 'react-router-dom'

const items = [
  ['/', '▚', 'Dashboard', true],
  ['/live', '⧉', 'Live', true],
  ['/tasks', '☰', 'Tasks', true],
  ['/config', '⚙', 'Config', true],
  ['/schedule', '⏱', 'Schedule', true],
  ['/generals', '♜', 'Generals', true],
  ['/fleet', '⚔', 'Fleet', false],
  ['/logs', '▤', 'Logs', true],
  ['/vision', '◉', 'Vision', false],
  ['/knowledge', '◈', 'Knowledge', true],
  ['/safety', '🔒', 'Safety', true],
] as const

export function Nav() {
  return (
    <nav aria-label="Primary" className="fixed inset-y-0 left-0 z-30 flex w-rail flex-col items-center border-r border-border bg-surface py-2">
      <div className="mb-2 flex h-9 w-9 items-center justify-center rounded-lg bg-accent text-xs font-bold text-[#07111f]" title="Murder Bot">
        MB
      </div>
      {items.map(([to, icon, label, enabled]) => enabled ? (
        <NavLink
          aria-label={label}
          className={({ isActive }) => `my-0.5 flex h-10 w-10 items-center justify-center rounded-lg text-lg transition ${
            isActive ? 'bg-surface-2 text-accent' : 'text-muted hover:bg-surface-2 hover:text-text'
          }`}
          end={to === '/'}
          key={to}
          title={label}
          to={to}
        >
          <span aria-hidden="true">{icon}</span>
        </NavLink>
      ) : (
        <span
          aria-label={`${label} (coming later)`}
          className="my-0.5 flex h-10 w-10 cursor-not-allowed items-center justify-center rounded-lg text-lg text-muted opacity-35"
          key={to}
          role="img"
          title={`${label} — later phase`}
        >
          {icon}
        </span>
      ))}
    </nav>
  )
}
