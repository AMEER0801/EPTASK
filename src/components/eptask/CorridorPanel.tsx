"use client";
// CorridorPanel -- live road-scale (N1) simulation console.
// Submits a real corridor.py run to eptask-api, plays the returned trace on
// the 3D map, and shows the metrics computed by the original notebook code.

import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, fetchGraph, runJob } from "@/lib/eptask/client";
import type { CorridorResult, GraphData, MetaInfo, OsmBuildResult } from "@/lib/eptask/types";
import CorridorMap, { type MapHandle } from "./CorridorMap";

const MODES = [
  { v: "NONE", label: "No warning network" },
  { v: "V2V", label: "V2V relay only" },
  { v: "RSU", label: "Roadside units only" },
  { v: "V2V+RSU", label: "V2V + roadside units" },
];
const HAZARDS = [
  { v: "landslide", label: "Landslide (2 km footprint)" },
  { v: "earthquake", label: "Earthquake (20 km footprint)" },
  { v: "flood", label: "Outburst flood (12 km footprint)" },
  { v: "custom", label: "Custom footprint / traffic" },
];
const FLEET_FLAGS = ["warned", "rerouting", "passed Betrawati", "saw blockage", "missed junction", "no route", "arrived"];

function fmtClock(t: number) {
  const s = Math.round(t);
  const m = Math.floor(Math.abs(s) / 60);
  const sign = s < 0 ? "-" : "";
  return `${sign}${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}:${String(Math.abs(s) % 60).padStart(2, "0")}`;
}
const fmtMin = (v: number | null | undefined, d = 1) =>
  v == null || !isFinite(v) ? "n/a" : v.toFixed(d);

export default function CorridorPanel({ meta, onMetaRefresh }: {
  meta: import("@/lib/eptask/types").MetaInfo | null;
  onMetaRefresh?: () => void;
}) {
  const [graph, setGraph] = useState<GraphData | null>(null);
  const [trace, setTrace] = useState<CorridorResult | null>(null);
  const [running, setRunning] = useState(false);
  const [progress, setProgress] = useState(0);
  const [stage, setStage] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(30);
  const [clock, setClock] = useState(0);
  const mapRef = useRef<MapHandle>(null);
  const doneRef = useRef(false);

  // form state
  const [hazard, setHazard] = useState("landslide");
  const [infoMode, setInfoMode] = useState("V2V+RSU");
  const [traffic, setTraffic] = useState(30);
  const [footprint, setFootprint] = useState(2000);
  const [dispatch, setDispatch] = useState(600);
  const [seed, setSeed] = useState<number | "">("");
  const [latencyArm, setLatencyArm] = useState<string>("");
  const [convoy, setConvoy] = useState(true);

  // v2: road-network source (schematic <-> real OpenStreetMap)
  const [osmBusy, setOsmBusy] = useState(false);
  const [osmInfo, setOsmInfo] = useState<OsmBuildResult | null>(null);
  const [osmError, setOsmError] = useState<string | null>(null);

  useEffect(() => {
    fetchGraph().then(setGraph).catch(() => setError("failed to load corridor graph"));
  }, []);
  useEffect(() => {
    if (meta && !latencyArm) setLatencyArm(meta.latency_arms.includes("floor ON") ? "floor ON" : meta.latency_arms[0]);
  }, [meta, latencyArm]);

  const launch = useCallback(async () => {
    setRunning(true);
    setError(null);
    setTrace(null);
    setProgress(0);
    setStage("submitting");
    try {
      const job = await runJob<CorridorResult>(
        "corridor",
        {
          hazard,
          info_mode: infoMode,
          traffic_vph: hazard === "custom" ? traffic : null,
          footprint_m: hazard === "custom" ? footprint : null,
          dispatch_s: dispatch,
          seed: seed === "" ? null : Number(seed),
          latency_arm: latencyArm || null,
          convoy,
          trace: true,
          frame_dt: 60,
        },
        (f, s) => { setProgress(f); setStage(s ?? ""); },
      );
      setTrace(job.result);
      doneRef.current = false;
      setPlaying(true);
    } catch (e) {
      setError(e instanceof ApiError ? e.message_text() : String(e));
    } finally {
      setRunning(false);
    }
  }, [hazard, infoMode, traffic, footprint, dispatch, seed, latencyArm, convoy]);

  const onTick = useCallback((t: number, done: boolean) => {
    setClock(t);
    if (done && !doneRef.current) {
      doneRef.current = true;
      setPlaying(false);
    }
  }, []);

  const rebuildGraph = useCallback(async (prefer: boolean, refresh: boolean) => {
    setOsmBusy(true);
    setOsmError(null);
    setOsmInfo(null);
    try {
      const job = await runJob<OsmBuildResult>("osm", { prefer_osm: prefer, refresh },
        (f, s) => { setProgress(f); setStage(s ?? ""); });
      setOsmInfo(job.result);
      setGraph(await fetchGraph());
      setTrace(null);            // traces from the previous graph are not comparable
      onMetaRefresh?.();
    } catch (e) {
      setOsmError(e instanceof ApiError ? e.message_text() : String(e));
    } finally {
      setOsmBusy(false);
    }
  }, [onMetaRefresh]);

  const S = trace?.summary;
  const tArr = trace && trace.amb.length ? trace.amb[trace.amb.length - 1][0] : 0;
  const tHazard = 0;

  return (
    <div className="flex flex-col gap-4">
      <section className="rounded-lg border border-slate-800 bg-slate-900/40 p-4">
        <header className="mb-3 flex items-baseline justify-between gap-3">
          <div>
            <h2 className="text-sm font-semibold text-slate-100">Road-scale corridor simulation · N1</h2>
            <p className="text-xs text-slate-400">
              Runs <code className="text-slate-300">corridor.run_trial</code> live for every convoy member —
              hazard blockage, V2V relay, roadside units and micro-latency retries included.
            </p>
          </div>
          {trace && (
            <span className="hidden shrink-0 text-[11px] text-slate-500 lg:inline">
              computed in {trace.timing.total_seconds.toFixed(1)} s · seed {trace.config.seed} · {trace.config.generator.split("(")[0]}
            </span>
          )}
        </header>

        <div className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-7">
          <label className="text-xs text-slate-400">
            Hazard preset
            <select value={hazard} onChange={(e) => setHazard(e.target.value)} disabled={running}
              className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-2 py-1.5 text-slate-200 focus:border-amber-500/60 focus:outline-none">
              {HAZARDS.map((h) => <option key={h.v} value={h.v}>{h.label}</option>)}
            </select>
          </label>
          <label className="text-xs text-slate-400">
            Warning network
            <select value={infoMode} onChange={(e) => setInfoMode(e.target.value)} disabled={running}
              className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-2 py-1.5 text-slate-200 focus:border-amber-500/60 focus:outline-none">
              {MODES.map((m) => <option key={m.v} value={m.v}>{m.label}</option>)}
            </select>
          </label>
          {hazard === "custom" ? (
            <>
              <label className="text-xs text-slate-400">
                Footprint (m)
                <input type="number" min={500} max={30000} step={500} value={footprint}
                  onChange={(e) => setFootprint(Number(e.target.value))} disabled={running}
                  className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-2 py-1.5 text-slate-200 focus:border-amber-500/60 focus:outline-none" />
              </label>
              <label className="text-xs text-slate-400">
                Traffic (veh/h)
                <input type="number" min={5} max={120} step={5} value={traffic}
                  onChange={(e) => setTraffic(Number(e.target.value))} disabled={running}
                  className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-2 py-1.5 text-slate-200 focus:border-amber-500/60 focus:outline-none" />
              </label>
            </>
          ) : (
            <>
              <label className="text-xs text-slate-400">
                Ambulance dispatch (s)
                <input type="number" min={60} max={3600} step={30} value={dispatch}
                  onChange={(e) => setDispatch(Number(e.target.value))} disabled={running}
                  className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-2 py-1.5 text-slate-200 focus:border-amber-500/60 focus:outline-none" />
              </label>
              <label className="text-xs text-slate-400">
                Seed (blank = preset default)
                <input type="number" min={0} max={999999} value={seed}
                  onChange={(e) => setSeed(e.target.value === "" ? "" : Number(e.target.value))} disabled={running}
                  className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-2 py-1.5 text-slate-200 focus:border-amber-500/60 focus:outline-none" />
              </label>
            </>
          )}
          <label className="text-xs text-slate-400">
            Micro-latency arm
            <select value={latencyArm} onChange={(e) => setLatencyArm(e.target.value)} disabled={running}
              className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-2 py-1.5 text-slate-200 focus:border-amber-500/60 focus:outline-none">
              {(meta?.latency_arms ?? []).map((a) => <option key={a} value={a}>{a}</option>)}
            </select>
          </label>
          <label className="flex items-end gap-2 text-xs text-slate-400">
            <input type="checkbox" checked={convoy} onChange={(e) => setConvoy(e.target.checked)} disabled={running}
              className="mb-1.5 h-4 w-4 accent-amber-500" />
            <span className="mb-1">Include convoy<br />(+5 trials)</span>
          </label>
          <div className="flex items-end">
            <button onClick={launch} disabled={running || !meta}
              className="h-[34px] w-full rounded bg-amber-600 px-3 text-sm font-semibold text-white transition hover:bg-amber-500 disabled:cursor-not-allowed disabled:bg-slate-700">
              {running ? "Running…" : "Run simulation"}
            </button>
          </div>
        </div>

        {running && (
          <div className="mt-3">
            <div className="h-1.5 w-full overflow-hidden rounded bg-slate-800">
              <div className="h-full bg-amber-500 transition-[width]" style={{ width: `${Math.round(progress * 100)}%` }} />
            </div>
            <p className="mt-1 text-xs text-slate-400">{stage || "simulating"} — {Math.round(progress * 100)}%</p>
          </div>
        )}
        {error && (
          <p role="alert" className="mt-3 rounded border border-red-900/60 bg-red-950/40 px-3 py-2 text-xs text-red-300">
            {error}
          </p>
        )}
      </section>

      {/* v2: road-network source card */}
      <section className="rounded-lg border border-slate-800 bg-slate-900/40 p-4">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
          <div className="min-w-0">
            <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-400">Road network source</h3>
            <p className="mt-0.5 flex items-center gap-2 text-xs text-slate-300">
              <span className={`inline-block h-2 w-2 rounded-full ${graph?.source.startsWith("OpenStreetMap") ? "bg-emerald-400" : "bg-sky-400"}`} />
              {graph?.source ?? "loading…"}
              {graph && <span className="text-slate-500">· {graph.nodes.length} nodes / {graph.edges.length} edges</span>}
            </p>
            {osmInfo && (
              <p className={`mt-0.5 text-[11px] ${osmInfo.chosen === "osm" ? "text-emerald-400" : "text-slate-500"}`}>
                {osmInfo.reason}
                {osmInfo.fetch?.ok === false && ` · fetch error: ${osmInfo.fetch.error}`}
                {osmInfo.fetch?.ok && ` · fetched ${osmInfo.fetch.elements} OSM elements in ${osmInfo.fetch.seconds}s from ${osmInfo.fetch.url}`}
                {osmInfo.osm_payload === "cache" && " · using cached extract"}
              </p>
            )}
            {osmInfo?.chosen === "osm" && osmInfo.named_snapped && (
              <p className="mt-0.5 text-[11px] text-slate-500">
                place snapping: {Object.entries(osmInfo.named_snapped).map(([k, v]) => `${k} ±${Math.round(v.snap_m)} m`).join(", ")}
              </p>
            )}
            {osmError && <p className="mt-0.5 text-[11px] text-red-400">{osmError}</p>}
          </div>
          <div className="ml-auto flex flex-wrap gap-2">
            <button onClick={() => rebuildGraph(true, false)} disabled={osmBusy}
              className="h-8 rounded border border-slate-700 bg-slate-800 px-3 text-xs font-medium text-slate-200 transition hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-40">
              {osmBusy ? "working…" : "Load real OSM roads"}
            </button>
            <button onClick={() => rebuildGraph(true, true)} disabled={osmBusy}
              className="h-8 rounded border border-slate-700 bg-slate-800 px-3 text-xs font-medium text-slate-200 transition hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-40">
              Re-fetch
            </button>
            <button onClick={() => rebuildGraph(false, false)} disabled={osmBusy}
              className="h-8 rounded border border-slate-700 bg-slate-800 px-3 text-xs font-medium text-slate-400 transition hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-40">
              Notebook schematic
            </button>
          </div>
        </div>
        {osmBusy && (
          <div className="mt-2">
            <div className="h-1 w-full overflow-hidden rounded bg-slate-800">
              <div className="h-full bg-sky-500 transition-[width]" style={{ width: `${Math.round(progress * 100)}%` }} />
            </div>
            <p className="mt-1 text-[11px] text-slate-500">{stage || "rebuilding road network"} — the Overpass fetch can take up to a minute on first use</p>
          </div>
        )}
      </section>

      {trace && (
        <section className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-6">
          <Metric label="Ambulance arrival" value={`${fmtMin(S?.arrival_min, 0)} min`} />
          <Metric label="Oracle (informed at departure)" value={`${fmtMin(S?.oracle_min, 0)} min`} />
          <Metric label="Extra delay vs oracle" value={`${S && S.extra_min >= 0 ? "+" : ""}${fmtMin(S?.extra_min)} min`}
            accent={S && S.extra_min > 1 ? "warn" : "ok"} />
          <Metric label="First informed" value={S?.informed_min != null ? `${fmtMin(S.informed_min)} min` : "never"} />
          <Metric label="Civilians informed at end" value={`${pctInformed(trace)}%`} />
          <Metric label="RSUs alive" value={`${Math.round((S?.rsu_alive ?? 0) * 100)}%`} accent={(S?.rsu_alive ?? 1) < 1 ? "warn" : "ok"} />
        </section>
      )}

      <section className="grid gap-4 xl:grid-cols-[1fr_320px]">
        <div className="h-[420px] md:h-[520px]">
          <CorridorMap ref={mapRef} graph={graph} trace={trace} playing={playing} speed={speed} onTick={onTick} />
        </div>
        <div className="flex flex-col gap-4">
          {/* playback */}
          <div className="rounded-lg border border-slate-800 bg-slate-900/40 p-4">
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">Playback</h3>
            <div className="flex items-center gap-2">
              <button onClick={() => setPlaying((p) => !p)} disabled={!trace}
                className="h-8 w-20 rounded border border-slate-700 bg-slate-800 text-xs font-medium text-slate-200 hover:bg-slate-700 disabled:opacity-40">
                {playing ? "Pause" : "Play"}
              </button>
              <span className="font-mono text-sm tabular-nums text-slate-200">{fmtClock(clock)}</span>
              <select value={speed} onChange={(e) => setSpeed(Number(e.target.value))}
                className="ml-auto rounded border border-slate-700 bg-slate-950 px-1.5 py-1 text-xs text-slate-300"
                aria-label="Playback speed">
                {[5, 15, 30, 60, 120].map((s) => <option key={s} value={s}>{s}×</option>)}
              </select>
            </div>
            {trace && (
              <input type="range" min={trace.t0} max={trace.frame_t[trace.frame_t.length - 1]} step={30}
                value={Math.min(clock, trace.frame_t[trace.frame_t.length - 1])}
                onChange={(e) => { mapRef.current?.seek(Number(e.target.value)); setClock(Number(e.target.value)); }}
                className="mt-3 w-full accent-amber-500" aria-label="Timeline scrubber" />
            )}
            {trace && (
              <ul className="mt-2 space-y-1 text-[11px] text-slate-400">
                <li><span className="text-slate-500">hazard at</span> {fmtClock(tHazard)} · RSU verification {trace.rsu_t != null ? fmtClock(trace.rsu_t) : "n/a"}</li>
                <li><span className="text-slate-500">ambulance dispatched</span> {fmtClock(trace.config.params.dispatch_s)} · <span className="text-slate-500">arrives</span> {fmtClock(tArr)}</li>
              </ul>
            )}
          </div>

          {/* convoy table */}
          {trace && trace.fleet.length > 0 && (
            <div className="rounded-lg border border-slate-800 bg-slate-900/40 p-4">
              <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">Emergency convoy</h3>
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="text-slate-500">
                    <th className="py-1 font-medium">Unit</th>
                    <th className="py-1 font-medium">Dispatch</th>
                    <th className="py-1 font-medium">Arrival</th>
                    <th className="py-1 font-medium">Status</th>
                  </tr>
                </thead>
                <tbody className="text-slate-300">
                  <tr className="border-t border-slate-800">
                    <td className="py-1.5">Ambulance</td>
                    <td className="py-1.5 tabular-nums">{fmtClock(trace.config.params.dispatch_s)}</td>
                    <td className="py-1.5 tabular-nums">{fmtClock(tArr)}</td>
                    <td className="py-1.5">{S?.unreachable ? <Badge tone="bad">no route</Badge> : S?.missed_junction ? <Badge tone="warn">missed junction</Badge> : <Badge tone="ok">rerouted</Badge>}</td>
                  </tr>
                  {trace.fleet.map((f) => (
                    <tr key={f.key} className="border-t border-slate-800">
                      <td className="py-1.5">{f.label}</td>
                      <td className="py-1.5 tabular-nums">{fmtClock(f.dispatch_s)}</td>
                      <td className="py-1.5 tabular-nums">{fmtClock(f.track.length ? f.track[f.track.length - 1][0] : NaN)}</td>
                      <td className="py-1.5"><FleetStatus flags={f.track.length ? f.track[f.track.length - 1][3] : 0} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="mt-2 text-[11px] text-slate-500">
                Every unit is an independent corridor.run_trial with the same blockage and traffic;
                dispatch times are the demo&apos;s stated assumption. Flags: {FLEET_FLAGS.join(", ")}.
              </p>
            </div>
          )}
        </div>
      </section>

      {trace && <CoverageChart coverage={trace.coverage} />}
    </div>
  );
}

function pctInformed(tr: CorridorResult) {
  const last = tr.coverage.length ? tr.coverage[tr.coverage.length - 1][1] : null;
  return last == null ? "n/a" : Math.round(last * 100);
}

function FleetStatus({ flags }: { flags: number }) {
  if (flags & 64) return <Badge tone="ok">arrived</Badge>;
  if (flags & 32) return <Badge tone="bad">no route</Badge>;
  if (flags & 16) return <Badge tone="warn">missed junction</Badge>;
  if (flags & 8) return <Badge tone="warn">saw blockage</Badge>;
  if (flags & 4) return <Badge tone="info">passed Betrawati</Badge>;
  if (flags & 2) return <Badge tone="info">rerouting</Badge>;
  if (flags & 1) return <Badge tone="info">warned</Badge>;
  return <Badge tone="muted">en route</Badge>;
}

function Badge({ tone, children }: { tone: "ok" | "warn" | "bad" | "info" | "muted"; children: React.ReactNode }) {
  const map = {
    ok: "border-emerald-800/60 bg-emerald-950/40 text-emerald-300",
    warn: "border-amber-800/60 bg-amber-950/40 text-amber-300",
    bad: "border-red-800/60 bg-red-950/40 text-red-300",
    info: "border-slate-600 bg-slate-800/60 text-slate-300",
    muted: "border-slate-800 bg-slate-900 text-slate-400",
  } as const;
  return <span className={`inline-block rounded px-1.5 py-px text-[11px] ${map[tone]}`}>{children}</span>;
}

export function Metric({ label, value, accent }: { label: string; value: string; accent?: "ok" | "warn" }) {
  return (
    <div className="rounded-lg border border-slate-800 bg-slate-900/40 px-3 py-2.5">
      <div className="text-[11px] uppercase tracking-wide text-slate-500">{label}</div>
      <div className={`mt-0.5 font-mono text-lg tabular-nums ${accent === "warn" ? "text-amber-300" : accent === "ok" ? "text-emerald-300" : "text-slate-100"}`}>
        {value}
      </div>
    </div>
  );
}

export function CoverageChart({ coverage }: { coverage: [number, number | null][] }) {
  const pts = coverage.filter((c): c is [number, number] => c[1] != null);
  if (pts.length < 2) return null;
  const W = 720, H = 130, pad = 28;
  const t0 = pts[0][0], t1 = pts[pts.length - 1][0];
  const x = (t: number) => pad + ((t - t0) / (t1 - t0 || 1)) * (W - pad * 2);
  const y = (v: number) => H - pad - v * (H - pad * 1.6);
  const path = pts.map((p, i) => `${i ? "L" : "M"}${x(p[0]).toFixed(1)},${y(p[1]).toFixed(1)}`).join(" ");
  return (
    <section className="rounded-lg border border-slate-800 bg-slate-900/40 p-4">
      <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-400">
        Civilian warning coverage over time <span className="normal-case text-slate-500">(recorded by the simulation)</span>
      </h3>
      <svg viewBox={`0 0 ${W} ${H}`} className="mt-2 w-full" role="img" aria-label="Warning coverage line chart">
        {[0, 0.25, 0.5, 0.75, 1].map((v) => (
          <g key={v}>
            <line x1={pad} x2={W - pad} y1={y(v)} y2={y(v)} stroke="#1e293b" strokeWidth={1} />
            <text x={4} y={y(v) + 3} fill="#64748b" fontSize={9}>{Math.round(v * 100)}%</text>
          </g>
        ))}
        <path d={path} fill="none" stroke="#d9a13c" strokeWidth={1.8} />
        <text x={pad} y={H - 8} fill="#64748b" fontSize={9}>{fmtClock(t0)}</text>
        <text x={W - pad} y={H - 8} fill="#64748b" fontSize={9} textAnchor="end">{fmtClock(t1)}</text>
      </svg>
    </section>
  );
}
