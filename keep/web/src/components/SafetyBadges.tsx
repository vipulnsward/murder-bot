import type { StatusResponse } from '../api'

export function SafetyBadges({ safety }: { safety?: StatusResponse['safety'] }) {
  const badges = [
    ['🔒 no gems', safety ? !safety.gem_spend : true],
    ['disconnect-safe', safety?.disconnect_safe],
    ['humanized', safety?.humanized],
    ['macro-on', safety?.macro_on],
  ] as const

  return (
    <div className="flex flex-wrap gap-2">
      {badges.map(([label, active]) => (
        <span className={`rounded-full border px-2.5 py-1 text-xs ${active ? 'semantic-good text-good' : 'border-border text-muted'}`} key={label}>
          {active ? '✓ ' : ''}{label}
        </span>
      ))}
    </div>
  )
}
