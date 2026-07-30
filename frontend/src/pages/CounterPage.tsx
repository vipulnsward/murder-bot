import { useState, type FormEvent } from "react";
import { counterGenerals, demoCounter, type CounterGeneralsResponse, type CounterPlan, type CounterRole } from "@/api";
import { CounterGeneralList } from "@/components/CounterGeneralList";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardTitle } from "@/components/ui/card";

const troopTypes = ["GROUND", "MOUNTED", "RANGED", "SIEGE"];
const fieldClass =
  "mt-1.5 w-full rounded-lg border border-gold/25 bg-[rgba(8,6,4,.7)] px-3 py-2.5 text-foreground";

export default function CounterPage() {
  const [targetMode, setTargetMode] = useState<"type" | "general">("type");
  const [enemyType, setEnemyType] = useState("GROUND");
  const [general, setGeneral] = useState("");
  const [power, setPower] = useState(60);
  const [role, setRole] = useState<CounterRole>("attack");
  const [counters, setCounters] = useState<CounterGeneralsResponse | null>(null);
  const [plan, setPlan] = useState<CounterPlan | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setLoading(true);
    setError("");
    setCounters(null);
    setPlan(null);

    try {
      const enemy = targetMode === "general" ? general.trim() : enemyType;
      const nextCounters = await counterGenerals(enemy, role, 5);
      const nextPlan = await demoCounter(power, nextCounters.enemy_type ?? enemyType);
      setCounters(nextCounters);
      setPlan(nextPlan);
      if (nextCounters.error) setError(nextCounters.error);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Counter request failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="relative z-10 min-h-[calc(100vh-4rem)] py-12">
      <div className="mx-auto w-[min(1000px,92vw)]">
        <div className="text-xs font-bold uppercase tracking-[0.16em] text-gold">Battle desk</div>
        <h1 className="mt-1.5 font-display text-3xl font-extrabold text-gold-bright md:text-4xl">
          Build the counter
        </h1>
        <p className="mt-3 max-w-[64ch] text-muted-foreground">
          Identify the enemy lead, size the incoming march, and get the recommended response.
        </p>

        <Card className="mt-8">
          <form onSubmit={submit} className="relative z-10 grid gap-5">
            <fieldset>
              <legend className="text-sm text-muted-foreground">Identify the enemy by</legend>
              <div className="mt-2 flex gap-4">
                <label className="flex items-center gap-2 text-sm">
                  <input
                    type="radio"
                    name="target-mode"
                    checked={targetMode === "type"}
                    onChange={() => setTargetMode("type")}
                    className="accent-[#e6c35c]"
                  />
                  Troop type
                </label>
                <label className="flex items-center gap-2 text-sm">
                  <input
                    type="radio"
                    name="target-mode"
                    checked={targetMode === "general"}
                    onChange={() => setTargetMode("general")}
                    className="accent-[#e6c35c]"
                  />
                  Named general
                </label>
              </div>
            </fieldset>

            <div className="grid gap-4 md:grid-cols-2">
              {targetMode === "type" ? (
                <label className="text-sm text-muted-foreground">
                  Enemy troop type
                  <select value={enemyType} onChange={(event) => setEnemyType(event.target.value)} className={fieldClass}>
                    {troopTypes.map((type) => (
                      <option key={type}>{type}</option>
                    ))}
                  </select>
                </label>
              ) : (
                <label className="text-sm text-muted-foreground">
                  Enemy general
                  <input
                    value={general}
                    onChange={(event) => setGeneral(event.target.value)}
                    required
                    placeholder="e.g. Elektra"
                    className={fieldClass}
                  />
                </label>
              )}

              <label className="text-sm text-muted-foreground">
                Role
                <select value={role} onChange={(event) => setRole(event.target.value as CounterRole)} className={fieldClass}>
                  <option value="attack">Attack</option>
                  <option value="defense">Defense</option>
                </select>
              </label>
            </div>

            <label className="text-sm text-muted-foreground">
              Incoming power <strong className="text-gold-bright">{power}M</strong>
              <input
                type="range"
                min={1}
                max={5000}
                step={1}
                value={power}
                onChange={(event) => setPower(Number(event.target.value))}
                className="mt-3 w-full accent-[#e6c35c]"
              />
            </label>

            <Button type="submit" className="justify-self-start" disabled={loading}>
              {loading ? "Reading the field…" : "Recommend counter →"}
            </Button>
          </form>
        </Card>

        {error && <p role="alert" className="mt-5 text-sm text-ember">{error}</p>}

        {plan && (
          <Card className="mt-6 border-gold/40 shadow-[0_0_44px_-16px_rgba(230,195,92,.35)]">
            <div className="relative z-10 text-xs font-bold uppercase tracking-[0.16em] text-gold">Recommended action</div>
            <CardTitle className="mt-2 text-2xl uppercase">{plan.action ?? "Hold"}</CardTitle>
            <CardContent className="mt-3 leading-relaxed">{plan.reasoning ?? "No reasoning was returned."}</CardContent>
          </Card>
        )}

        {counters && (
          <Card className="mt-6">
            <CardTitle className="mb-4 text-xl">Counter generals</CardTitle>
            <CounterGeneralList generals={counters.recommendations ?? []} />
          </Card>
        )}
      </div>
    </main>
  );
}
