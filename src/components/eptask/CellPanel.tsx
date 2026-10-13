"use client";
// CellPanel -- live VEC-cell console (micro scale): env.VECEnv driven by the
// shipped ONNX policy exports, with C2 counterfactuals from the notebook.

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ApiError, runJob } from "@/lib/eptask/client";
import type { CellResult, CellTick, MetaInfo } from "@/lib/eptask/types";
import { Metric } from "./CorridorPanel";

const TARGETS = ["Edge server", "Nearby vehicle", "Local (on-board)", "Cloud"];
const ROLE = ["Normal", "Emergency", "Sensing"];
const TIER = ["—", "MINOR", "DELAYED", "IMMEDIATE"];
const TARGET_COLORS = ["#7ba3c9", "#9a8fc2", "#7d8a97", "#b08d57"];

function RoadStrip({ result, tick, onSelect }: { result: CellResult; tick: number; onSelect: (i: number) => void }) {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const cv = ref.current;
    if (!cv) return;
    const ctx = cv.getContext("2d");
    if (!ctx) return;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const W = cv.clientWidth, H = cv.clientHeight;
    cv.width = W * dpr; cv.height = H * dpr;
    ctx.scale(dpr, dpr);
    ctx.clearRect(0, 0, W, H);
    const rec = result.ticks[tick];
    const L = result.config.L;
    const padX = 30, roadY = H * 0.52, roadH = 30;
    const xOf = (m: number) => padX + (m / L) * (W - padX * 2);

    // road
    ctx.fillStyle = "#1d242e";
    ctx.fillRect(padX, roadY, W - padX * 2, roadH);
    ctx.strokeStyle = "#334155";
    ctx.setLineDash([4, 4]);
    ctx.beginPath();
    ctx.moveTo(padX, roadY + roadH / 2);
    ctx.lineTo(W - padX, roadY + roadH / 2);
    ctx.stroke();
    ctx.setLineDash([]);
    // kilometre marks
    ctx.fillStyle = "#475569";
    ctx.font = "9px ui-monospace, monospace";
    for (const frac of [0, 0.25, 0.5, 0.75, 1]) {
      const x = padX + frac * (W - padX * 2);
      ctx.fillRect(x, roadY + roadH + 2, 1, 4);
      ctx.fillText(`${Math.round((frac * L) / 1000 * 10) / 10} km`, x - 10, roadY + roadH + 16);
    }

    // edge servers
    const S = result.config.S;
    for (let s = 0; s < S; s++) {
      const cx = xOf(result.config.edge_x[s]);
      const alive = rec.alive[s] === 1;
      ctx.fillStyle = alive ? "#2e5d44" : "#5d2e2e";
      ctx.strokeStyle = alive ? "#46a06b" : "#a8433f";
      ctx.beginPath();
      ctx.roundRect(cx - 9, roadY - 26, 18, 14, 2);
      ctx.fill();
      ctx.stroke();
      ctx.fillStyle = alive ? "#8fd0ab" : "#d99a97";
      ctx.fillText(alive ? "ON" : "DOWN", cx - 8, roadY - 16);
      ctx.fillStyle = "#475569";
      ctx.fillText(`e${s}`, cx - 4, roadY - 30);
      // coverage zone
      ctx.strokeStyle = alive ? "rgba(70,160,107,0.25)" : "rgba(168,67,63,0.2)";
      ctx.beginPath();
      ctx.moveTo(cx, roadY - 12);
      ctx.lineTo(cx, roadY + roadH + 6);
      ctx.stroke();
    }

    // vehicles: two directions
    for (let v = 0; v < result.config.V; v++) {
      const x = xOf(rec.x[v]);
      const dir = result.config.dir[v];
      const isEm = result.config.emergency.includes(v);
      const y = roadY + (dir > 0 ? roadH * 0.3 : roadH * 0.7);
      ctx.beginPath();
      ctx.arc(x, y, isEm ? 4.5 : 3, 0, Math.PI * 2);
      ctx.fillStyle = isEm ? "#d64541" : dir > 0 ? "#9fb0c2" : "#7d8fa1";
      ctx.fill();
      if (rec.i === v) {
        ctx.strokeStyle = "#d9a13c";
        ctx.lineWidth = 2;
        ctx.stroke();
        ctx.lineWidth = 1;
      }
    }
    // current request position highlight
    if (rec.s >= 0) {
      ctx.strokeStyle = "rgba(217,161,60,0.8)";
      ctx.setLineDash([3, 3]);
      ctx.beginPath();
      ctx.moveTo(xOf(rec.x[rec.i]), roadY - 4);
      ctx.lineTo(xOf(result.config.edge_x[rec.s]), roadY - 10);
      ctx.stroke();
      ctx.setLineDash([]);
    }
    ctx.fillStyle = "#64748b";
    ctx.fillText(`t = ${rec.t}s   ·   hazard event ${result.config.event.at}–${result.config.event.at + result.config.event.dur}s (RSUs ${result.config.event.s0}–${result.config.event.s0 + result.config.event.k - 1})`, padX, 14);
  }, [result, tick]);
  return <canvas ref={ref} className="h-[150px] w-full" role="img" aria-label="VEC cell road diagram" />;
}

function Timeline({ result, tick, onSelect }: { result: CellResult; tick: number; onSelect: (t: number) => void }) {
  const ticks = result.ticks;
  const maxT = Math.max(4, ...ticks.map((r) => Math.max(r.T, r.D)));
  const H = 92, W = 1000, padL = 6, padR = 6;
  const n = ticks.length;
  const xOf = (i: number) => padL + (i / (n - 1 || 1)) * (W - padL - padR);
  const yOf = (v: number) => 6 + (1 - v / maxT) * (H - 18);
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full cursor-crosshair" role="img" aria-label="Reported service time per tick"
      onClick={(e) => {
        const rect = e.currentTarget.getBoundingClientRect();
        const frac = (e.clientX - rect.left) / rect.width;
        onSelect(Math.min(n - 1, Math.max(0, Math.round(frac * (n - 1)))));
      }}>
      <line x1={0} x2={W} y1={yOf(maxT)} y2={yOf(maxT)} stroke="#1e293b" />
      {ticks.map((r, i) => {
        const late = r.Tt != null && r.Tt > r.D;
        const col = late ? "#d64541" : "#3f7f63";
        return (
          <rect key={i} x={xOf(i) - 0.6} y={yOf(r.T)} width={1.2} height={Math.max(0.8, H - 12 - yOf(r.T))} fill={col} opacity={0.85} />
        );
      })}
      {/* event window */}
      <rect x={xOf(result.config.event.at)} width={xOf(Math.min(n - 1, result.config.event.at + result.config.event.dur)) - xOf(result.config.event.at)}
        y={2} height={H - 4} fill="rgba(168,67,63,0.10)" />
      <line x1={xOf(tick)} x2={xOf(tick)} y1={2} y2={H - 2} stroke="#d9a13c" strokeWidth={1.4} />
      <text x={xOf(result.config.event.at) + 3} y={11} fontSize={8.5} fill="#a8433f">outage window</text>
    </svg>
  );
}

function DecisionInspector({ rec, cfg }: { rec: CellTick; cfg: CellResult["config"] }) {
  if (rec.n === 0 || !rec.a) {
    return <p className="text-xs text-slate-500">No request at the head of the queue at t={rec.t}s.</p>;
  }
  const k = rec.kx ?? 0;
  return (
    <div className="space-y-3 text-xs">
      <div className="grid grid-cols-2 gap-x-4 gap-y-1.5">
        <Field label="Vehicle">{rec.i}</Field>
        <Field label="Role">{ROLE[rec.role] ?? "?"}{rec.role === 2 ? ` · ${TIER[rec.tier] ?? ""}` : ""}</Field>
        <Field label="Deadline class">{rec.key} ×{cfg.deadline_mult[rec.key] ?? 1}</Field>
        <Field label="Protected">{rec.prot ? "yes (safety floor)" : "no"}</Field>
        <Field label="Reported T">{rec.T?.toFixed(2)} s · deadline {rec.D?.toFixed(2)} s</Field>
        <Field label="True T (settled)">{rec.Tt != null ? `${rec.Tt.toFixed(2)} s · ${rec.ok ? "on time" : "MISSED"}` : "pending"}</Field>
        {rec.role === 2 && <Field label="Casualty estimate">{rec.ppl ?? 0} people · {rec.mod}</Field>}
        {rec.role === 2 && <Field label="CWP score">{rec.cwp} ({TIER[rec.tier]})</Field>}
        <Field label="Edge reachable">{rec.edge_ok ? "yes" : "no"}</Field>
        <Field label="Chosen target">{TARGETS[rec.real?.[k] ?? rec.a[k] ?? 2]}</Field>
      </div>

      {rec.p && (
        <div>
          <div className="mb-1 text-[11px] uppercase tracking-wide text-slate-500">Policy head — offload probabilities (task {k})</div>
          <div className="space-y-1">
            {(rec.p[k] ?? []).map((p, j) => (
              <div key={j} className="flex items-center gap-2">
                <span className="w-28 text-slate-400">{TARGETS[j]}</span>
                <div className="h-2 flex-1 overflow-hidden rounded bg-slate-800">
                  <div className="h-full rounded" style={{ width: `${Math.round(p * 100)}%`, background: TARGET_COLORS[j] }} />
                </div>
                <span className="w-10 text-right font-mono tabular-nums text-slate-300">{p.toFixed(2)}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {rec.cf && (
        <div>
          <div className="mb-1 text-[11px] uppercase tracking-wide text-slate-500">
            Exact counterfactuals — env.peek(), reported T if task {k} moved
          </div>
          <div className="space-y-1">
            {rec.cf.map((t, j) => (
              <div key={j} className="flex items-center gap-2">
                <span className="w-28 text-slate-400">{TARGETS[j]}</span>
                <div className="h-2 flex-1 overflow-hidden rounded bg-slate-800">
                  <div className="h-full rounded"
                    style={{ width: `${Math.min(100, (t / Math.max(...rec.cf, 1e-6)) * 100)}%`, background: rec.cfi?.[j] ? "#a8433f" : TARGET_COLORS[j] }} />
                </div>
                <span className="w-24 text-right font-mono tabular-nums text-slate-300">
                  {t.toFixed(2)} s{rec.cfi?.[j] ? " · infeasible" : ""}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="text-[11px] text-slate-500">{label}</div>
      <div className="text-slate-200">{children}</div>
    </div>
  );
}

export default function CellPanel({ meta }: { meta: MetaInfo | null }) {
  const [result, setResult] = useState<CellResult | null>(null);
  const [tick, setTick] = useState(0);
  const [running, setRunning] = useState(false);
  const [progress, setProgress] = useState(0);
  const [stage, setStage] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [playing, setPlaying] = useState(false);
  const rafRef = useRef<number>(0);
  const lastStep = useRef(0);

  const [policy, setPolicy] = useState<"A" | "B">("B");
  const [version, setVersion] = useState(30);
  const [V, setV] = useState(30);
  const [seed, setSeed] = useState(21);
  const [ticks, setTicks] = useState(520);
  const [evAt, setEvAt] = useState(60);
  const [evK, setEvK] = useState(3);
  const [evDur, setEvDur] = useState(360);
  const [floor, setFloor] = useState(true);
  const [explain, setExplain] = useState(true);

  const launch = useCallback(async () => {
    setRunning(true); setError(null); setResult(null); setProgress(0); setStage("submitting");
    try {
      const job = await runJob<CellResult>("cell",
        { policy, version, V, seed, ticks, event: { at: evAt, k: evK, dur: evDur }, floor, explain },
        (f, s) => { setProgress(f); setStage(s ?? ""); });
      setResult(job.result);
      setTick(0);
      setPlaying(true);
    } catch (e) {
      setError(e instanceof ApiError ? e.message_text() : String(e));
    } finally {
      setRunning(false);
    }
  }, [policy, version, V, seed, ticks, evAt, evK, evDur, floor, explain]);

  // playback over ticks
  useEffect(() => {
    if (!playing || !result) return;
    let acc = 0;
    lastStep.current = performance.now();
    const step = (now: number) => {
      acc += (now - lastStep.current) / 1000;
      lastStep.current = now;
      const rate = 12; // ticks per second
      if (acc > 1 / rate) {
        setTick((t) => {
          const nt = t + Math.floor(acc * rate);
          acc = 0;
          if (nt >= result.ticks.length - 1) { setPlaying(false); return result.ticks.length - 1; }
          return nt;
        });
      }
      rafRef.current = requestAnimationFrame(step);
    };
    rafRef.current = requestAnimationFrame(step);
    return () => cancelAnimationFrame(rafRef.current);
  }, [playing, result]);

  const rec = result?.ticks[Math.min(tick, (result?.ticks.length ?? 1) - 1)];
  const SU = result?.summary;
  const emNote = useMemo(() => {
    if (!SU) return null;
    return SU.emergency.n === 0 ? "no emergency requests in this window" : null;
  }, [SU]);

  return (
    <div className="flex flex-col gap-4">
      <section className="rounded-lg border border-slate-800 bg-slate-900/40 p-4">
        <header className="mb-3">
          <h2 className="text-sm font-semibold text-slate-100">VEC cell · task-offloading policy under a scripted outage</h2>
          <p className="text-xs text-slate-400">
            Runs <code className="text-slate-300">env.VECEnv</code> live with the shipped ONNX actor
            (<code className="text-slate-300">meppo_A/B_v*.onnx</code>) and explains each decision with exact
            counterfactuals (<code className="text-slate-300">env.peek</code>).
          </p>
        </header>
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-8">
          <label className="text-xs text-slate-400">Policy
            <select value={policy} onChange={(e) => setPolicy(e.target.value as "A" | "B")} disabled={running}
              className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-2 py-1.5 text-slate-200">
              <option value="A">Model A (static)</option>
              <option value="B">Model B (DR-MEPPO)</option>
            </select>
          </label>
          <label className="text-xs text-slate-400">Export version
            <select value={version} onChange={(e) => setVersion(Number(e.target.value))} disabled={running}
              className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-2 py-1.5 text-slate-200">
              {[10, 30, 50].map((v) => <option key={v} value={v}>v{v}</option>)}
            </select>
          </label>
          <label className="text-xs text-slate-400">Vehicles V
            <input type="number" min={4} max={60} value={V} onChange={(e) => setV(Number(e.target.value))} disabled={running}
              className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-2 py-1.5 text-slate-200" />
          </label>
          <label className="text-xs text-slate-400">Seed
            <input type="number" min={0} value={seed} onChange={(e) => setSeed(Number(e.target.value))} disabled={running}
              className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-2 py-1.5 text-slate-200" />
          </label>
          <label className="text-xs text-slate-400">Ticks
            <input type="number" min={20} max={3000} step={20} value={ticks} onChange={(e) => setTicks(Number(e.target.value))} disabled={running}
              className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-2 py-1.5 text-slate-200" />
          </label>
          <label className="text-xs text-slate-400">Outage at (s)
            <input type="number" min={1} max={2900} value={evAt} onChange={(e) => setEvAt(Number(e.target.value))} disabled={running}
              className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-2 py-1.5 text-slate-200" />
          </label>
          <label className="text-xs text-slate-400">RSUs down / duration
            <span className="mt-1 flex gap-1">
              <input type="number" min={1} max={7} value={evK} onChange={(e) => setEvK(Number(e.target.value))} disabled={running}
                className="w-full rounded border border-slate-700 bg-slate-950 px-2 py-1.5 text-slate-200" />
              <input type="number" min={30} max={2000} step={30} value={evDur} onChange={(e) => setEvDur(Number(e.target.value))} disabled={running}
                className="w-full rounded border border-slate-700 bg-slate-950 px-2 py-1.5 text-slate-200" />
            </span>
          </label>
          <div className="flex flex-col justify-end gap-2">
            <label className="flex items-center gap-2 text-xs text-slate-400">
              <input type="checkbox" checked={floor} onChange={(e) => setFloor(e.target.checked)} disabled={running} className="h-4 w-4 accent-amber-500" />
              Safety floor
            </label>
            <button onClick={launch} disabled={running}
              className="h-[30px] rounded bg-amber-600 px-3 text-sm font-semibold text-white hover:bg-amber-500 disabled:cursor-not-allowed disabled:bg-slate-700">
              {running ? "Running…" : "Run policy"}
            </button>
          </div>
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

      {result && rec && (
        <>
          <section className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-6">
            <Metric label="Settled requests" value={`${SU.settled} (${SU.pending} pending)`} />
            <Metric label="Mean true T" value={`${SU.all.mean_T?.toFixed(2) ?? "n/a"} s`} />
            <Metric label="Deadline miss (all)" value={`${SU.all.miss_pct?.toFixed(1) ?? "n/a"}%`} accent={(SU.all.miss_pct ?? 0) > 20 ? "warn" : "ok"} />
            <Metric label="Miss during outage" value={`${SU.outage.miss_pct?.toFixed(1) ?? "n/a"}%`} />
            <Metric label="Emergency miss" value={SU.emergency.n ? `${SU.emergency.miss_pct?.toFixed(0)}% of ${SU.emergency.n}` : "—"} accent={SU.emergency.miss_pct && SU.emergency.miss_pct > 40 ? "warn" : undefined} />
            <Metric label="Targets edge / v2v / local / cloud" value={`${SU.targets.edge} / ${SU.targets.v2v} / ${SU.targets.local} / ${SU.targets.cloud}%`} />
          </section>

          <section className="rounded-lg border border-slate-800 bg-slate-900/40 p-4">
            <RoadStrip result={result} tick={tick} onSelect={() => {}} />
            <div className="mt-3">
              <Timeline result={result} tick={tick} onSelect={setTick} />
            </div>
            <div className="mt-2 flex items-center gap-2">
              <button onClick={() => setPlaying((p) => !p)}
                className="h-8 w-20 rounded border border-slate-700 bg-slate-800 text-xs font-medium text-slate-200 hover:bg-slate-700">
                {playing ? "Pause" : "Play"}
              </button>
              <input type="range" min={0} max={result.ticks.length - 1} value={tick} onChange={(e) => { setPlaying(false); setTick(Number(e.target.value)); }}
                className="flex-1 accent-amber-500" aria-label="Tick scrubber" />
              <span className="font-mono text-xs tabular-nums text-slate-300">t={rec.t}s</span>
            </div>
          </section>

          <section className="grid gap-4 xl:grid-cols-2">
            <div className="rounded-lg border border-slate-800 bg-slate-900/40 p-4">
              <h3 className="mb-3 text-xs font-semibold uppercase tracking-wide text-slate-400">
                Decision inspector · {result.config.policy} · {result.config.onnx}
              </h3>
              <DecisionInspector rec={rec} cfg={result.config} />
            </div>
            <div className="rounded-lg border border-slate-800 bg-slate-900/40 p-4">
              <h3 className="mb-3 text-xs font-semibold uppercase tracking-wide text-slate-400">Run facts</h3>
              <div className="grid grid-cols-2 gap-x-4 gap-y-2 text-xs">
                <Field label="World">{result.config.L.toFixed(0)} m highway · {result.config.S} RSUs · d_max {result.config.d_max.toFixed(1)} m</Field>
                <Field label="Event">{result.config.event.k} RSUs down [{result.config.event.s0}..{result.config.event.s0 + result.config.event.k - 1}] at t={result.config.event.at} for {result.config.event.dur}s</Field>
                <Field label="Floors">safety floor level {result.config.floor_level} · {floor ? "ON" : "OFF"}</Field>
                <Field label="Request stream">{result.config.counts.detections} sensing · {result.config.counts.emergency} emergency</Field>
                <Field label="Modalities (sensing weights)">{result.config.modalities.join(", ")}</Field>
                <Field label="Sim time">{result.timing.sim_seconds.toFixed(2)} s for {result.ticks.length} ticks</Field>
              </div>
              {emNote && <p className="mt-3 text-[11px] text-slate-500">{emNote}</p>}
              <p className="mt-3 text-[11px] text-slate-500">
                Probabilities are the raw actor head (softmax); counterfactuals are exact queue
                recomputations from the environment, not estimates. “Realised target” reflects the
                infeasibility fallback the environment applies after the policy acts.
              </p>
            </div>
          </section>
        </>
      )}
    </div>
  );
}
