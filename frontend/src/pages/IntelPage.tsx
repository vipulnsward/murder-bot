import { useState, type FormEvent } from "react";
import { counterGenerals, type CounterGeneralsResponse } from "@/api";
import { CounterGeneralList } from "@/components/CounterGeneralList";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardTitle } from "@/components/ui/card";

const fieldClass =
  "mt-1.5 w-full rounded-lg border border-gold/25 bg-[rgba(8,6,4,.7)] px-3 py-2.5 text-foreground";

export default function IntelPage() {
  const [general, setGeneral] = useState("");
  const [intel, setIntel] = useState<CounterGeneralsResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setLoading(true);
    setError("");
    setIntel(null);

    try {
      const result = await counterGenerals(general.trim(), "attack", 5);
      setIntel(result);
      if (result.error) setError(result.error);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Intel request failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="relative z-10 min-h-[calc(100vh-4rem)] py-12">
      <div className="mx-auto w-[min(1000px,92vw)]">
        <div className="text-xs font-bold uppercase tracking-[0.16em] text-gold">Alliance intelligence</div>
        <h1 className="mt-1.5 font-display text-3xl font-extrabold text-gold-bright md:text-4xl">
          Enemy lookup
        </h1>
        <p className="mt-3 max-w-[64ch] text-muted-foreground">
          Search a named general to identify its formation and the generals best equipped to counter it.
        </p>

        <Card className="mt-8">
          <form onSubmit={submit} className="relative z-10 flex flex-col gap-4 sm:flex-row sm:items-end">
            <label className="flex-1 text-sm text-muted-foreground">
              Enemy general
              <input
                value={general}
                onChange={(event) => setGeneral(event.target.value)}
                required
                placeholder="e.g. Elektra"
                className={fieldClass}
              />
            </label>
            <Button type="submit" disabled={loading}>
              {loading ? "Scanning…" : "Run lookup →"}
            </Button>
          </form>
        </Card>

        {error && <p role="alert" className="mt-5 text-sm text-ember">{error}</p>}

        <Card className="mt-6 border-gold/30">
          <div className="relative z-10 text-xs font-bold uppercase tracking-[0.16em] text-gold">Intel card</div>
          <CardTitle className="mt-2 text-2xl">{intel ? intel.enemy : "Awaiting target"}</CardTitle>
          {intel ? (
            <>
              <div className="relative z-10 mt-3 flex flex-wrap gap-2 text-xs">
                <span className="rounded-full border border-gold/25 px-2.5 py-1 text-gold-bright">
                  Formation: {intel.enemy_type ?? "Unknown"}
                </span>
                <span className="rounded-full border border-ember/30 px-2.5 py-1 text-ember">
                  Counter with: {intel.counter_types?.join(", ") || "No match"}
                </span>
              </div>
              <div className="relative z-10 mt-5">
                <CounterGeneralList generals={intel.recommendations ?? []} />
              </div>
            </>
          ) : (
            <CardContent className="mt-3 leading-relaxed">
              Battle history, buffs, and player activity are not exposed by the public API yet. Search a general to
              populate the available formation and counter recommendations.
            </CardContent>
          )}
        </Card>
      </div>
    </main>
  );
}
