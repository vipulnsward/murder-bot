import type { CounterGeneral } from "@/api";

export function CounterGeneralList({ generals }: { generals: CounterGeneral[] }) {
  if (!generals.length) {
    return <p className="text-sm text-muted-foreground">No rated counter generals were found.</p>;
  }

  return (
    <ol className="space-y-3">
      {generals.map((general, index) => (
        <li
          key={`${general.general}-${general.counter_type}`}
          className="rounded-xl border border-gold/15 bg-[rgba(8,6,4,.58)] p-4"
        >
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs font-bold text-ember">#{index + 1}</span>
            <h3 className="font-display text-lg font-bold text-gold-bright">{general.general}</h3>
            <span className="rounded-full border border-gold/25 px-2 py-0.5 text-xs uppercase tracking-wide text-gold">
              {general.counter_type}
            </span>
            <span className="text-xs font-bold text-muted-foreground">Tier {general.tier ?? "—"}</span>
          </div>
          <p className="mt-2 text-sm leading-relaxed text-muted-foreground">{general.why}</p>
        </li>
      ))}
    </ol>
  );
}
