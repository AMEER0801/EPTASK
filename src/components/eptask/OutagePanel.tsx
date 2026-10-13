"use client";
// OutagePanel -- live paired outage study (the notebook's C3 protocol): for
// every (k, policy, seed), one run with the outage and one identical control
// run; excess latency is the paired difference.

import { useCallback, useState } from "react";
import { ApiError, fetchReference, runJob } from "@/lib/eptask/client";
import type { OutageResult } from "@/lib/eptask/types";
import { Metric } from "./CorridorPanel";

const POLICY_OPTS = [
  { v: "A", label: "Model A (static, ONNX)" },
  { v: "B", label: "Model B (DR-MEPPO, ONNX)" },
  { v: "alive_aware", label: "Alive-aware rule (baseline)" },
  { v: "local", label: "Local-only (failure-proof bound)" },
];
const POLICY_COLORS: Record<string, string> = {
  "model A (static)": "#7ba3c9",
  "model B (DR-MEPPO)": "#d9a13c",
  "alive-aware rule": "#9a8fc2",
  "Local-only": "#7d8a97",
};

export default function OutagePanel() {
  const [result, setResult] = useState<OutageResult | null>(null);
  const [reference, setReference] = useState<Record<string, { during_pct: [number, number, number]; T_outage: [number, number, number] }> | null>(null);
  const [showRef, setShowRef] = useState(false);
  const [running, setRunning] = useState(false);
  const [progress, setProgress] = useState(0);
  const [stage, setStage] = useState("");
  const [error, setError] = useState<string | null>(null);

  const [policies, setPolicies] = useState<string[]>(["A", "B"]);
  const [V, setV] = useState(30);
  const [kList, setKList] = useState<string>("1, 2, 4");
  const [nSeeds, setNSeeds] = useState(3);
  const [failAt, setFailAt] = useState(600);
  const [failDur, setFailDur] = useState(300);
  const [post, setPost] = useState(200);

  const togglePolicy = (v: string) =>
    setPolicies((p) => (p.includes(v) ? p.filter((x) => x !== v) : p.length < 4 ? [...p, v] : p));

  const launch = useCallback(async () => {
    setRunning(true); setError(null); setResult(null); setProgress(0); setStage("submitting");
    try {
      const seeds = Array.from({ length: nSeeds }, (_, i) => i);
      const job = await runJob<OutageResult>("outage",
        {
          policies,
          V,
          k_list: kList.split(",").map((s) => Number(s.trim())).filter((n) => Number.isFinite(n) && n >= 1 && n <= 6),
          seeds,
          fail_at: failAt, fail_dur: failDur, post,
        },
        (f, s) => { setProgress(f); setStage(s ?? ""); });
      setResult(job.result);
      // load the notebook's recorded C3 table for the same k values (labeled reference)
      fetchReference<Record<string, { during_pct: [number, number, number]; T_outage: [number, number, number] }>>("c3")
        .then((r) => setReference((r.data as { rows: Record<string, { during_pct: [number, number, number]; T_outage: [number, number, number] }> }).rows ?? null))
        .catch(() => setReference(null));
    } catch (e) {
      setError(e instanceof ApiError ? e.message_text() : String(e));
    } finally {
      setRunning(false);
    }
  }, [policies, V, kList, nSeeds, failAt, failDur, post]);

  const rows = result
    ? result.order.map((key) => result.rows[key]).filter(Boolean)
    : [];

  // chart: grouped bars of during_pct per k per policy
  const ks = result ? result.config.k_list : [];
  const polNames = result ? result.config.policies : [];
  const chartW = 760, chartH = 220, pad = 40;
  const maxAbs = Math.max(10, ...rows.map((r) => Math.abs(r.during_pct[0]) + r.during_pct[1]));
  const xK = (i: number) => pad + (i + 0.5) * ((chartW - pad * 2) / Math.max(ks.length, 1));
  const yV = (v: number) => chartH / 2 - (v / maxAbs) * (chartH / 2 - 24);
  const barW = ks.length ? ((chartW - pad * 2) / ks.length) * 0.6 / Math.max(polNames.length, 1) : 20;

  return (
    <div className="flex flex-col gap-4">
      <section className="rounded-lg border border-slate-800 bg-slate-900/40 p-4">
        <header className="mb-3">
          <h2 className="text-sm font-semibold text-slate-100">Paired outage study · C3 protocol</h2>
          <p className="text-xs text-slate-400">
            For every (outage size, policy, seed): one run with the RSU outage and one identical run
            without it, from <code className="text-slate-300">policies.rollout</code>. Excess latency is the
            paired difference of mean completion time during the outage window.
          </p>
        </header>
        <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
          <div className="text-xs text-slate-400 xl:col-span-2">
            Policies
            <div className="mt-1 flex flex-col gap-1.5">
              {POLICY_OPTS.map((o) => (
                <label key={o.v} className="flex items-center gap-2 text-slate-300">
                  <input type="checkbox" checked={policies.includes(o.v)} onChange={() => togglePolicy(o.v)} disabled={running}
                    className="h-4 w-4 accent-amber-500" />
                  {o.label}
                </label>
              ))}
            </div>
          </div>
          <label className="text-xs text-slate-400">Vehicles V
            <input type="number" min={4} max={60} value={V} onChange={(e) => setV(Number(e.target.value))} disabled={running}
              className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-2 py-1.5 text-slate-200" />
          </label>
          <label className="text-xs text-slate-400">Outage sizes k (comma-sep)
            <input value={kList} onChange={(e) => setKList(e.target.value)} disabled={running}
              className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-2 py-1.5 text-slate-200" />
          </label>
          <label className="text-xs text-slate-400">Seeds (paired, 0..n-1)
            <input type="number" min={1} max={6} value={nSeeds} onChange={(e) => setNSeeds(Number(e.target.value))} disabled={running}
              className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-2 py-1.5 text-slate-200" />
          </label>
          <div className="grid grid-cols-3 gap-2 text-xs text-slate-400">
            <label>fail_at
              <input type="number" min={50} max={4000} value={failAt} onChange={(e) => setFailAt(Number(e.target.value))} disabled={running}
                className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-2 py-1.5 text-slate-200" />
            </label>
            <label>dur
              <input type="number" min={30} max={1500} value={failDur} onChange={(e) => setFailDur(Number(e.target.value))} disabled={running}
                className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-2 py-1.5 text-slate-200" />
            </label>
            <label>post
              <input type="number" min={20} max={1500} value={post} onChange={(e) => setPost(Number(e.target.value))} disabled={running}
                className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-2 py-1.5 text-slate-200" />
            </label>
          </div>
        </div>
        <div className="mt-3 flex items-center gap-3">
          <button onClick={launch} disabled={running || policies.length === 0}
            className="h-9 rounded bg-amber-600 px-4 text-sm font-semibold text-white hover:bg-amber-500 disabled:cursor-not-allowed disabled:bg-slate-700">
            {running ? "Running…" : "Run paired study"}
          </button>
          <span className="text-[11px] text-slate-500">
            ≈ {policies.length} policies × {kList.split(",").length} sizes × {nSeeds} seeds × 2 (paired control) rollouts — typically 5–25 s
          </span>
        </div>
        {running && (
          <div className="mt-3">
            <div className="h-1.5 w-full overflow-hidden rounded bg-slate-800">
              <div className="h-full bg-amber-500" style={{ width: `${Math.round(progress * 100)}%` }} />
            </div>
            <p className="mt-1 text-xs text-slate-400">{stage} — {Math.round(progress * 100)}%</p>
          </div>
        )}
        {error && <p role="alert" className="mt-3 rounded border border-red-900/60 bg-red-950/40 px-3 py-2 text-xs text-red-300">{error}</p>}
      </section>

      {result && (
        <>
          <section className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <Metric label="Rollouts executed" value={`${2 * result.config.policies.length * result.config.k_list.length * result.config.seeds.length}`} />
            <Metric label="Steps per rollout" value={`${result.config.steps}`} />
            <Metric label="Outage window" value={`[${result.config.fail_at}, ${result.config.fail_at + result.config.fail_dur}) s`} />
            <Metric label="Wall time" value={`${result.timing.total_seconds.toFixed(1)} s`} />
          </section>

          <section className="rounded-lg border border-slate-800 bg-slate-900/40 p-4">
            <h3 className="mb-3 text-xs font-semibold uppercase tracking-wide text-slate-400">
              Excess latency during the outage (% vs paired control) — mean ± 95% CI over seeds
            </h3>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[560px] text-left text-xs">
                <thead>
                  <tr className="text-slate-500">
                    <th className="py-1.5 font-medium">Outage</th>
                    <th className="py-1.5 font-medium">Policy</th>
                    <th className="py-1.5 font-medium text-right">T during outage</th>
                    <th className="py-1.5 font-medium text-right">T control</th>
                    <th className="py-1.5 font-medium text-right">Excess (paired)</th>
                    <th className="py-1.5 font-medium text-right">Post-recovery</th>
                  </tr>
                </thead>
                <tbody className="text-slate-300">
                  {rows.map((r) => (
                    <tr key={`${r.k}-${r.policy}`} className="border-t border-slate-800">
                      <td className="py-1.5">{r.k} RSU{r.k > 1 ? "s" : ""}</td>
                      <td className="py-1.5">
                        <span className="mr-2 inline-block h-2 w-2 rounded-sm align-middle" style={{ background: POLICY_COLORS[r.policy] ?? "#7d8a97" }} />
                        {r.policy}
                      </td>
                      <td className="py-1.5 text-right font-mono tabular-nums">{r.T_outage[0].toFixed(2)} ± {r.T_outage[1].toFixed(2)} s</td>
                      <td className="py-1.5 text-right font-mono tabular-nums">{r.T_control[0].toFixed(2)} s</td>
                      <td className={`py-1.5 text-right font-mono tabular-nums ${r.during_pct[0] > 15 ? "text-amber-300" : "text-emerald-300"}`}>
                        +{r.during_pct[0].toFixed(1)} ± {r.during_pct[1].toFixed(1)}%
                      </td>
                      <td className="py-1.5 text-right font-mono tabular-nums">{r.post_pct[0] >= 0 ? "+" : ""}{r.post_pct[0].toFixed(1)}%</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section className="rounded-lg border border-slate-800 bg-slate-900/40 p-4">
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">Excess by outage size</h3>
            <svg viewBox={`0 0 ${chartW} ${chartH}`} className="w-full" role="img" aria-label="Paired excess latency bar chart">
              <line x1={pad} x2={chartW - pad} y1={yV(0)} y2={yV(0)} stroke="#475569" />
              {ks.map((k, i) => {
                const group = polNames.map((p, j) => {
                  const r = rows.find((q) => q.k === k && q.policy === p);
                  if (!r) return null;
                  const x = xK(i) - (barW * polNames.length) / 2 + j * barW;
                  const v = r.during_pct[0];
                  return (
                    <g key={p}>
                      <rect x={x} width={barW - 3} y={Math.min(yV(v), yV(0))} height={Math.abs(yV(v) - yV(0))} fill={POLICY_COLORS[p] ?? "#7d8a97"} opacity={0.9} />
                      <text x={x + (barW - 3) / 2} y={Math.min(yV(v), yV(0)) - 4} fontSize={8.5} fill="#94a3b8" textAnchor="middle">{v.toFixed(0)}%</text>
                    </g>
                  );
                });
                return (
                  <g key={k}>
                    {group}
                    <text x={xK(i)} y={chartH - 8} fontSize={10} fill="#64748b" textAnchor="middle">{k} RSU{k > 1 ? "s" : ""}</text>
                  </g>
                );
              })}
              <text x={pad} y={14} fontSize={9} fill="#64748b">worse ↑ · excess vs paired control</text>
            </svg>
            <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-slate-400">
              {polNames.map((p) => (
                <span key={p} className="flex items-center gap-1.5">
                  <span className="inline-block h-2 w-2 rounded-sm" style={{ background: POLICY_COLORS[p] ?? "#7d8a97" }} />{p}
                </span>
              ))}
            </div>
          </section>

          {reference && (
            <section className="rounded-lg border border-slate-700/50 bg-slate-900/20 p-4">
              <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-400">
                Notebook reference (recorded artifact, not recomputed)
              </h3>
              <p className="mb-2 text-[11px] text-slate-500">
                Recorded by run 20261008-124455-ba2667 with trained torch policies, V=30, k∈&#123;1,2,4&#125;, seeds 0–4,
                outage [1200, 1600). Your live runs above use the shipped ONNX exports and your chosen
                parameters, so differences are expected.
              </p>
              <button onClick={() => setShowRef((s) => !s)} className="rounded border border-slate-700 px-2 py-1 text-xs text-slate-300 hover:bg-slate-800">
                {showRef ? "Hide" : "Show"} recorded C3 table
              </button>
              {showRef && (
                <div className="mt-2 overflow-x-auto">
                  <table className="w-full min-w-[520px] text-left text-xs">
                    <thead><tr className="text-slate-500"><th className="py-1 font-medium">Row</th><th className="py-1 font-medium text-right">Excess during (%)</th><th className="py-1 font-medium text-right">T outage (s)</th></tr></thead>
                    <tbody className="text-slate-300">
                      {Object.entries(reference).map(([key, r]) => (
                        <tr key={key} className="border-t border-slate-800">
                          <td className="py-1.5">{key}</td>
                          <td className="py-1.5 text-right font-mono tabular-nums">{r.during_pct[0].toFixed(1)} ± {r.during_pct[1].toFixed(1)}</td>
                          <td className="py-1.5 text-right font-mono tabular-nums">{r.T_outage[0].toFixed(2)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </section>
          )}
        </>
      )}
    </div>
  );
}
