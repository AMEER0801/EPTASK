"use client";
// ComparePanel -- hazard preset editor + side-by-side warning networks.
// One scenario, two information modes, everything else identical: the same
// hazard draw, the same traffic seed, the same RSU layout -- only the warning
// network differs. Both runs execute the ORIGINAL corridor.run_trial live.

import { useCallback, useEffect, useState } from "react";
import { ApiError, fetchGraph, runJob } from "@/lib/eptask/client";
import type { CompareResult, GraphData, MetaInfo } from "@/lib/eptask/types";
import WarningMap from "./WarningMap";

const MODES = [
  { v: "NONE", label: "None — no warning network" },
  { v: "V2V", label: "V2V relay only" },
  { v: "RSU", label: "Roadside units only" },
  { v: "V2V+RSU", label: "V2V + roadside units" },
];
const MODE_COLOR: Record<string, string> = {
  NONE: "#94a3b8", V2V: "#38bdf8", RSU: "#a78bfa", "V2V+RSU": "#f59e0b",
};

const METRICS: { key: string; label: string; unit: string; better: "low" | "high" | "info" }[] = [
  { key: "arrival_min", label: "Ambulance arrival", unit: "min", better: "low" },
  { key: "extra_min", label: "Excess over oracle route", unit: "min", better: "low" },
  { key: "informed_min", label: "Driver first informed", unit: "min", better: "low" },
  { key: "missed_junction", label: "Missed the junction", unit: "", better: "info" },
  { key: "saw_block", label: "Saw the blockage itself", unit: "", better: "info" },
  { key: "service_wait_s", label: "Mean service wait", unit: "s", better: "low" },
  { key: "rsu_verified_s", label: "RSU verified hazard", unit: "s", better: "low" },
  { key: "rsu_alive", label: "RSUs alive", unit: "", better: "high" },
  { key: "trapped", label: "Civilians trapped", unit: "", better: "low" },
  { key: "civilians", label: "Civilians simulated", unit: "", better: "info" },
];

const fmtMin = (v: number | null | undefined, d = 1) =>
  v == null || !isFinite(v) ? "n/a" : v.toFixed(d);
const fmtDelta = (key: string, v: number | null, a: unknown, b: unknown) => {
  if (v != null && isFinite(v)) return `${v > 0 ? "+" : ""}${fmtMin(v, 1)}`;
  if (typeof a === "boolean" && typeof b === "boolean") return a === b ? "same" : `${a ? "yes" : "no"} → ${b ? "yes" : "no"}`;
  return "n/a";
};

function CoverageChart({ runs }: { runs: CompareResult["runs"] }) {
  const W = 1000, H = 260;
  const colors = ["#38bdf8", "#f59e0b"];
  const maxT = Math.max(...runs.map((r) => (r.coverage.length ? r.coverage[r.coverage.length - 1][0] : 1)), 1);
  const paths = runs.map((r) => {
    const segs: string[] = [];
    let open = false;
    r.coverage.forEach(([t, f]) => {
      if (f == null) { open = false; return; }
      const x = (t / maxT) * (W - 80) + 55;
      const y = H - 38 - f * (H - 62);
      segs.push(`${open ? "L" : "M"}${x.toFixed(1)},${y.toFixed(1)}`);
      open = true;
    });
    return segs.join(" ");
  });
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="block h-auto w-full" role="img"
         aria-label="Informed share of vehicles over time, both modes">
      {[0, 0.25, 0.5, 0.75, 1].map((g) => (
        <g key={g}>
          <line x1={55} x2={W - 25} y1={H - 38 - g * (H - 62)} y2={H - 38 - g * (H - 62)}
                stroke="#1e293b" strokeWidth={1} />
          <text x={45} y={H - 34 - g * (H - 62)} fontSize={15} fill="#64748b" textAnchor="end">
            {Math.round(g * 100)}%
          </text>
        </g>
      ))}
      <text x={W / 2} y={H - 6} fontSize={16} fill="#64748b" textAnchor="middle">
        simulation time (minutes) — 0 … {(maxT / 60).toFixed(1)}
      </text>
      {paths.map((d, i) => (
        <path key={i} d={d} fill="none" stroke={colors[i]} strokeWidth={2.5} />
      ))}
    </svg>
  );
}

export default function ComparePanel({ meta }: { meta: MetaInfo | null }) {
  const [graph, setGraph] = useState<GraphData | null>(null);
  const [res, setRes] = useState<CompareResult | null>(null);
  const [running, setRunning] = useState(false);
  const [progress, setProgress] = useState(0);
  const [stage, setStage] = useState("");
  const [error, setError] = useState<string | null>(null);

  // hazard preset editor state
  const [hazard, setHazard] = useState("landslide");
  const [footprint, setFootprint] = useState(2000);
  const [traffic, setTraffic] = useState(30);
  const [hazardSeed, setHazardSeed] = useState(7);
  const [modeA, setModeA] = useState("NONE");
  const [modeB, setModeB] = useState("V2V+RSU");
  const [dispatch, setDispatch] = useState(600);
  const [latencyArm, setLatencyArm] = useState("");
  const [seed, setSeed] = useState<number | "">("");

  useEffect(() => { fetchGraph().then(setGraph).catch(() => setError("failed to load the road graph")); }, []);
  useEffect(() => {
    if (meta && !latencyArm) setLatencyArm(meta.latency_arms.includes("floor ON") ? "floor ON" : meta.latency_arms[0]);
  }, [meta, latencyArm]);
  useEffect(() => {
    const p = meta?.hazards?.[hazard];
    if (p && hazard !== "custom") { setFootprint(p.footprint_m); setTraffic(p.traffic_vph); }
  }, [meta, hazard]);

  const run = useCallback(async () => {
    setRunning(true); setError(null); setRes(null); setProgress(0); setStage("submitting");
    try {
      const job = await runJob<CompareResult>("compare", {
        modes: [modeA, modeB], hazard,
        footprint_m: hazard === "custom" ? footprint : null,
        traffic_vph: hazard === "custom" ? traffic : null,
        hazard_seed: hazardSeed, dispatch_s: dispatch,
        seed: seed === "" ? null : Number(seed),
        latency_arm: latencyArm || null, trace: true, frame_dt: 60,
      }, (f, s) => { setProgress(f); setStage(s ?? ""); });
      setRes(job.result);
    } catch (e) {
      setError(e instanceof ApiError ? e.message_text() : String(e));
    } finally { setRunning(false); }
  }, [modeA, modeB, hazard, footprint, traffic, hazardSeed, dispatch, seed, latencyArm]);

  const hazardLabel = hazard === "custom"
    ? `Custom — ${(footprint / 1000).toFixed(1)} km footprint, ${traffic} veh/h`
    : (meta?.hazards?.[hazard]?.label ?? hazard);

  return (
    <div className="flex flex-col gap-4">
      {/* ---------------- preset editor ---------------- */}
      <section className="rounded-lg border border-slate-800 bg-slate-900/40 p-4">
        <header className="mb-3">
          <h2 className="text-sm font-semibold text-slate-100">Hazard preset editor · warning-network comparison</h2>
          <p className="text-xs text-slate-400">
            Adjust the scenario below, pick two information modes, and the console runs the
            ORIGINAL <code className="text-slate-300">corridor.run_trial</code> twice — same hazard draw,
            same traffic seed, same RSU layout — so every difference comes from the warning network alone.
          </p>
        </header>

        <div className="flex flex-wrap gap-2">
          {["landslide", "earthquake", "flood", "custom"].map((h) => (
            <button key={h} onClick={() => setHazard(h)}
              className={`rounded-full border px-3 py-1 text-xs font-medium transition ${
                hazard === h ? "border-amber-500 bg-amber-500/10 text-amber-400"
                             : "border-slate-700 text-slate-400 hover:text-slate-200"}`}>
              {h === "custom" ? "Custom" : (meta?.hazards?.[h]?.label ?? h)}
            </button>
          ))}
        </div>

        <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <label className="block text-xs text-slate-400">
            Footprint (destruction radius around the hazard): <span className="font-mono text-slate-200">{(footprint / 1000).toFixed(1)} km</span>
            <input type="range" min={500} max={30000} step={500} value={footprint}
                   disabled={hazard !== "custom"}
                   onChange={(e) => setFootprint(Number(e.target.value))}
                   className="mt-1 w-full accent-amber-500 disabled:opacity-40" />
          </label>
          <label className="block text-xs text-slate-400">
            Traffic (Poisson vehicles per hour): <span className="font-mono text-slate-200">{traffic} veh/h</span>
            <input type="range" min={5} max={120} step={5} value={traffic}
                   disabled={hazard !== "custom"}
                   onChange={(e) => setTraffic(Number(e.target.value))}
                   className="mt-1 w-full accent-amber-500 disabled:opacity-40" />
          </label>
          <label className="block text-xs text-slate-400">
            Hazard seed (which road segment is blocked)
            <input type="number" min={0} max={99999} value={hazardSeed}
                   onChange={(e) => setHazardSeed(Number(e.target.value))}
                   className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-2 py-1 font-mono text-xs text-slate-200" />
          </label>
          <label className="block text-xs text-slate-400">
            Side A — information mode
            <select value={modeA} onChange={(e) => setModeA(e.target.value)}
                    className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-2 py-1 text-xs text-slate-200">
              {MODES.map((m) => <option key={m.v} value={m.v}>{m.label}</option>)}
            </select>
          </label>
          <label className="block text-xs text-slate-400">
            Side B — information mode
            <select value={modeB} onChange={(e) => setModeB(e.target.value)}
                    className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-2 py-1 text-xs text-slate-200">
              {MODES.map((m) => <option key={m.v} value={m.v}>{m.label}</option>)}
            </select>
          </label>
          <label className="block text-xs text-slate-400">
            Ambulance dispatch: <span className="font-mono text-slate-200">{Math.floor(dispatch / 60)} min</span>
            <input type="range" min={60} max={3600} step={60} value={dispatch}
                   onChange={(e) => setDispatch(Number(e.target.value))}
                   className="mt-1 w-full accent-amber-500" />
          </label>
          <label className="block text-xs text-slate-400">
            Micro-latency arm
            <select value={latencyArm} onChange={(e) => setLatencyArm(e.target.value)}
                    className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-2 py-1 text-xs text-slate-200">
              {(meta?.latency_arms ?? []).map((a) => <option key={a} value={a}>{a}</option>)}
            </select>
          </label>
          <label className="block text-xs text-slate-400">
            Traffic seed (blank = preset convention)
            <input type="number" min={0} placeholder="auto" value={seed}
                   onChange={(e) => setSeed(e.target.value === "" ? "" : Number(e.target.value))}
                   className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-2 py-1 font-mono text-xs text-slate-200" />
          </label>
          <div className="flex items-end">
            <button onClick={run} disabled={running}
                    className="w-full rounded bg-amber-500 px-4 py-2 text-xs font-semibold text-slate-950 transition hover:bg-amber-400 disabled:cursor-not-allowed disabled:opacity-50">
              {running ? `running… ${Math.round(progress * 100)}%` : "Run side-by-side comparison"}
            </button>
          </div>
        </div>

        {running && (
          <div className="mt-3">
            <div className="h-1 overflow-hidden rounded bg-slate-800">
              <div className="h-full bg-amber-500 transition-all" style={{ width: `${progress * 100}%` }} />
            </div>
            <p className="mt-1 text-[11px] text-slate-500">{stage}</p>
          </div>
        )}
        {error && <p role="alert" className="mt-3 rounded border border-red-900/60 bg-red-950/40 px-3 py-2 text-xs text-red-300">{error}</p>}
      </section>

      {/* ---------------- results ---------------- */}
      {!res && !running && (
        <section className="rounded-lg border border-dashed border-slate-800 bg-slate-900/20 p-8 text-center">
          <h3 className="text-sm font-medium text-slate-300">No comparison yet</h3>
          <p className="mx-auto mt-2 max-w-xl text-xs leading-relaxed text-slate-500">
            Choose a hazard preset (or tune footprint and traffic yourself), pick two warning
            networks — for example <span className="text-slate-300">None</span> versus
            <span className="text-slate-300"> V2V + roadside units</span> — and press
            <span className="text-slate-300"> Run side-by-side comparison</span>. You will get two maps of the
            same scenario, the informed-share curves, and a per-metric delta computed from the live
            simulations, not from stored results.
          </p>
        </section>
      )}

      {res && (
        <>
          <section className="grid gap-4 lg:grid-cols-2">
            {res.runs.map((r, i) => (
              <WarningMap key={r.config.info_mode} graph={graph} run={r}
                          label={`${i === 0 ? "A" : "B"} · ${MODES.find((m) => m.v === r.config.info_mode)?.label ?? r.config.info_mode}`}
                          accent={MODE_COLOR[r.config.info_mode] ?? "#f59e0b"} />
            ))}
          </section>

          <section className="rounded-lg border border-slate-800 bg-slate-900/40 p-4">
            <h3 className="mb-1 text-sm font-semibold text-slate-100">Warning reach over time</h3>
            <p className="mb-2 text-xs text-slate-400">
              Share of civilians on the road that have the warning (via V2V, a surviving RSU, or
              store-carry-forward), as computed live by the original notebook code.
            </p>
            <CoverageChart runs={res.runs} />
            <div className="mt-1 flex gap-4 text-[11px]">
              {res.runs.map((r, i) => (
                <span key={r.config.info_mode} style={{ color: ["#38bdf8", "#f59e0b"][i] }}>
                  ── {r.config.info_mode}
                </span>
              ))}
            </div>
          </section>

          <section className="rounded-lg border border-slate-800 bg-slate-900/40 p-4">
            <h3 className="mb-2 text-sm font-semibold text-slate-100">Metrics · side B vs side A</h3>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="border-b border-slate-800 text-[11px] uppercase tracking-wide text-slate-500">
                    <th className="py-2 pr-4 font-medium">Metric</th>
                    <th className="py-2 pr-4 text-right font-medium">A · {res.runs[0].config.info_mode}</th>
                    <th className="py-2 pr-4 text-right font-medium">B · {res.runs[1].config.info_mode}</th>
                    <th className="py-2 text-right font-medium">Δ (B − A)</th>
                  </tr>
                </thead>
                <tbody>
                  {METRICS.map(({ key, label, unit }) => {
                    const a = res.runs[0].summary[key as keyof typeof res.runs[0]["summary"]];
                    const b = res.runs[1].summary[key as keyof typeof res.runs[1]["summary"]];
                    const d = res.delta[key];
                    const num = typeof a === "number" && typeof b === "number";
                    return (
                      <tr key={key} className="border-b border-slate-800/50">
                        <td className="py-1.5 pr-4 text-slate-300">{label}{unit && <span className="text-slate-500"> ({unit})</span>}</td>
                        <td className="py-1.5 pr-4 text-right font-mono text-slate-200">
                          {typeof a === "boolean" ? (a ? "yes" : "no") : fmtMin(a as number)}{num && unit === "min" ? "" : ""}
                        </td>
                        <td className="py-1.5 pr-4 text-right font-mono text-slate-200">
                          {typeof b === "boolean" ? (b ? "yes" : "no") : fmtMin(b as number)}
                        </td>
                        <td className={`py-1.5 text-right font-mono ${
                          typeof d === "number" && d < 0 ? "text-emerald-400"
                            : typeof d === "number" && d > 0 ? "text-red-400" : "text-slate-400"}`}>
                          {fmtDelta(key, d as number | null, a, b)}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <p className="mt-3 text-[11px] leading-relaxed text-slate-500">
              Scenario: {hazardLabel} · hazard seed {res.config.hazard_seed} · dispatch {Math.round(res.config.dispatch_s / 60)} min ·
              latency arm {res.config.latency_arm} · seed {res.config.seed} · generator {res.config.generator} ·
              wall time {res.timing.total_seconds}s. Negative Δ (green) means side B arrived sooner or lost less.
            </p>
          </section>
        </>
      )}
    </div>
  );
}
