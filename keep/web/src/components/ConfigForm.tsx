import { useState, type FormEvent } from 'react'
import type { KeepConfig, NumberRange } from '../api'

type Section = 'safety' | 'humanize' | 'schedule' | 'tasks' | 'vision' | 'notify'
type ConfigSection = 'safety' | 'humanize' | 'macro' | 'vision' | 'notify'

interface Props {
  config: KeepConfig
  dirty: boolean
  disabled?: boolean
  saving?: boolean
  onChange: (config: KeepConfig) => void
  onRevert: () => void
  onSave: () => void
}

interface NumberFieldProps {
  label: string
  value: number
  onChange: (value: number) => void
  disabled?: boolean
  min?: number
  max?: number
  step?: number
}

function NumberField({ label, value, onChange, disabled, min, max, step = 1 }: NumberFieldProps) {
  return (
    <label className="field-label">
      {label}
      <input
        className="field font-mono tabular-nums"
        disabled={disabled}
        max={max}
        min={min}
        onChange={(event) => {
          const next = event.currentTarget.valueAsNumber
          if (Number.isFinite(next)) onChange(next)
        }}
        required
        step={step}
        type="number"
        value={value}
      />
    </label>
  )
}

function RangeFields({ label, value, onChange, disabled, step }: {
  label: string
  value: NumberRange
  onChange: (value: NumberRange) => void
  disabled?: boolean
  step?: number
}) {
  return (
    <fieldset className="grid grid-cols-2 gap-2">
      <legend className="col-span-2 mb-1 text-xs text-muted">{label}</legend>
      <NumberField disabled={disabled} label="Low" onChange={(lo) => onChange({ ...value, lo })} step={step} value={value.lo} />
      <NumberField disabled={disabled} label="High" onChange={(hi) => onChange({ ...value, hi })} step={step} value={value.hi} />
    </fieldset>
  )
}

function Toggle({ label, checked, onChange, disabled, note }: {
  label: string
  checked: boolean
  onChange: (value: boolean) => void
  disabled?: boolean
  note?: string
}) {
  return (
    <label className="flex min-h-11 items-center justify-between gap-4 rounded-lg border border-border bg-surface-2 px-3 py-2">
      <span><span className="block text-sm">{label}</span>{note && <span className="block text-xs text-muted">{note}</span>}</span>
      <input checked={checked} className="h-4 w-4 accent-accent" disabled={disabled} onChange={(event) => onChange(event.currentTarget.checked)} type="checkbox" />
    </label>
  )
}

export function ConfigForm({ config, dirty, disabled, saving, onChange, onRevert, onSave }: Props) {
  const [active, setActive] = useState<Section>('safety')
  const update = (section: ConfigSection, key: string, value: unknown) => {
    onChange({ ...config, [section]: { ...config[section], [key]: value } })
  }
  const updateTask = (name: string, key: string, value: unknown) => {
    onChange({
      ...config,
      tasks: { ...config.tasks, [name]: { ...config.tasks[name], [key]: value } },
    })
  }
  const submit = (event: FormEvent) => {
    event.preventDefault()
    onSave()
  }

  return (
    <form className="overflow-hidden rounded-card border border-border bg-surface" onSubmit={submit}>
      <div className="grid min-h-[520px] md:grid-cols-[160px_1fr]">
        <nav aria-label="Config sections" className="border-b border-border bg-surface-2 p-2 md:border-b-0 md:border-r">
          {(['safety', 'humanize', 'schedule', 'tasks', 'vision', 'notify'] as Section[]).map((section) => (
            <button
              className={`w-full rounded-lg px-3 py-2 text-left text-sm capitalize transition ${active === section ? 'bg-surface text-accent' : 'text-muted hover:text-text'}`}
              key={section}
              onClick={() => setActive(section)}
              type="button"
            >
              {section}
            </button>
          ))}
        </nav>

        <div className="p-4 md:p-6">
          <h2 className="mb-1 text-lg font-semibold capitalize">{active}</h2>
          <p className="mb-5 text-sm text-muted">Changes are sent as one validated config document.</p>

          {active === 'safety' && <div className="grid max-w-2xl gap-3 sm:grid-cols-2">
            <Toggle checked={false} disabled label="🔒 Gem spending" note="Locked invariant — can never be enabled" onChange={() => {}} />
            <label className="field-label">Disconnect policy<input className="field font-mono" disabled value={config.safety.disconnect_policy} /></label>
            <Toggle checked={config.safety.humanize_required} disabled={disabled} label="Humanization required" onChange={(value) => update('safety', 'humanize_required', value)} />
            <Toggle checked={config.safety.macro_required} disabled={disabled} label="Macro schedule required" onChange={(value) => update('safety', 'macro_required', value)} />
          </div>}

          {active === 'humanize' && <div className="grid max-w-3xl gap-4 sm:grid-cols-2">
            <RangeFields disabled={disabled} label="Delay between taps (seconds)" onChange={(value) => update('humanize', 'delay_between_taps', value)} step={0.05} value={config.humanize.delay_between_taps} />
            <RangeFields disabled={disabled} label="Tap duration (ms)" onChange={(value) => update('humanize', 'tap_duration_ms', value)} value={config.humanize.tap_duration_ms} />
            <NumberField disabled={disabled} label="Deliberate tap probability" max={1} min={0} onChange={(value) => update('humanize', 'deliberate_tap_prob', value)} step={0.01} value={config.humanize.deliberate_tap_prob} />
            <NumberField disabled={disabled} label="Same button maximum" min={1} onChange={(value) => update('humanize', 'same_button_max', value)} value={config.humanize.same_button_max} />
          </div>}

          {active === 'schedule' && <div className="grid max-w-3xl gap-4 sm:grid-cols-2">
            <Toggle checked={config.macro.enabled} disabled={disabled} label="Macro schedule" onChange={(value) => update('macro', 'enabled', value)} />
            <div />
            <RangeFields disabled={disabled} label="Sleep length (hours)" onChange={(value) => update('macro', 'sleep_len_h', value)} step={0.5} value={config.macro.sleep_len_h} />
            <RangeFields disabled={disabled} label="Sleep anchor (hour)" onChange={(value) => update('macro', 'sleep_anchor_h', value)} step={0.5} value={config.macro.sleep_anchor_h} />
            <RangeFields disabled={disabled} label="Break cadence (minutes)" onChange={(value) => update('macro', 'micro_break_every_min', value)} value={config.macro.micro_break_every_min} />
            <RangeFields disabled={disabled} label="Break length (minutes)" onChange={(value) => update('macro', 'micro_break_len_min', value)} value={config.macro.micro_break_len_min} />
          </div>}

          {active === 'tasks' && <div className="grid gap-3 xl:grid-cols-2">
            {Object.entries(config.tasks).map(([name, task]) => <fieldset className="rounded-lg border border-border p-3" key={name}>
              <legend className="px-1 font-medium">{name}</legend>
              <div className="grid grid-cols-3 gap-2">
                <Toggle checked={task.enabled} disabled={disabled} label="Enabled" onChange={(value) => updateTask(name, 'enabled', value)} />
                <NumberField disabled={disabled} label="Interval (s)" min={0.1} onChange={(value) => updateTask(name, 'interval', value)} step={0.1} value={task.interval} />
                <NumberField disabled={disabled} label="Priority" onChange={(value) => updateTask(name, 'priority', value)} value={task.priority} />
              </div>
            </fieldset>)}
          </div>}

          {active === 'vision' && <div className="grid max-w-2xl gap-3 sm:grid-cols-2">
            <Toggle checked={config.vision.ocr_first} disabled={disabled} label="OCR first" onChange={(value) => update('vision', 'ocr_first', value)} />
            <Toggle checked={config.vision.holo_fallback_on} disabled={disabled} label="Holo fallback" onChange={(value) => update('vision', 'holo_fallback_on', value)} />
            <label className="field-label sm:col-span-2">Holo model<input className="field" disabled={disabled} onChange={(event) => update('vision', 'holo_model', event.currentTarget.value)} value={config.vision.holo_model} /></label>
            <NumberField disabled={disabled} label="Max long side" min={1} onChange={(value) => update('vision', 'holo_max_long_side', value)} value={config.vision.holo_max_long_side} />
            <NumberField disabled={disabled} label="Template threshold" max={1} min={0} onChange={(value) => update('vision', 'template_match_threshold', value)} step={0.01} value={config.vision.template_match_threshold} />
          </div>}

          {active === 'notify' && <div className="grid max-w-2xl gap-3">
            <Toggle checked={config.notify.mac_banner} disabled={disabled} label="macOS banner" onChange={(value) => update('notify', 'mac_banner', value)} />
            <label className="field-label">Slack webhook<input className="field" disabled={disabled} onChange={(event) => update('notify', 'slack_webhook', event.currentTarget.value || null)} placeholder="Not configured" type="url" value={config.notify.slack_webhook ?? ''} /></label>
            <label className="field-label">Discord webhook<input className="field" disabled={disabled} onChange={(event) => update('notify', 'discord_webhook', event.currentTarget.value || null)} placeholder="Not configured" type="url" value={config.notify.discord_webhook ?? ''} /></label>
          </div>}
        </div>
      </div>

      <div className="flex items-center justify-end gap-2 border-t border-border bg-surface-2 px-4 py-3">
        <span className="mr-auto text-xs text-muted">{dirty ? 'Unsaved changes' : 'No changes'}</span>
        <button className="button-secondary" disabled={!dirty || saving} onClick={onRevert} type="button">Revert</button>
        <button className="button-primary" disabled={!dirty || disabled || saving} type="submit">{saving ? 'Saving…' : 'Save config'}</button>
      </div>
    </form>
  )
}
