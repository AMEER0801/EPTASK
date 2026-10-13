"use client";
// OverviewPanel -- provenance, health, model registry and the integration map.

import { useEffect, useState } from "react";
import { fetchHealth, type MetaInfo, type ServiceCatalogue } from "@/lib/eptask/client";

export default function OverviewPanel({ meta }: { meta: MetaInfo | null }) {
  const [health, setHealth] = useState<(ServiceCatalogue & { status: string }) | null>(null);
  useEffect(() => {
    const load = () => fetchHealth().then(setHealth).catch(() => setHealth(null));
    load();
    const t = setInterval(load, 15000);
    return () => clearInterval(t);
  }, []);

  const run = meta?.run;
  const cg = meta?.corridor_graph;

  return (
    <div className="flex flex-col gap-4">
      <section className="grid gap-3 md:grid-cols-3">
        <div className="rounded-lg border border-slate-800 bg-slate-900/40 p-4 md:col-span-2">
          <h2 className="text-sm font-semibold text-slate-100">EPtask operations console</h2>
          <p className="mt-1 text-xs leading-relaxed text-slate-400">
            This application executes the EPtask V7.1 research code live: the road-scale corridor
            co-simulation (<code className="text-slate-300">corridor.py</code>), the vehicular edge-computing
            cell (<code className="text-slate-300">env.VECEnv</code>) driven by the shipped ONNX exports of the
            trained MEPPO policies, and the paired outage study
            (<code className="text-slate-300">policies.rollout</code>). Nothing on the simulation pages is
            pre-recorded: every run you launch is computed by the original notebook modules at request time
            by the Python service, and results are checked against the notebook&apos;s own recorded outputs
            by the repository&apos;s consistency tests.
          </p>
          <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1.5 text-xs md:grid-cols-3">
            <Fact label="Notebook run" value={run ? run.run_id : "—"} />
            <Fact label="Mode" value={run ? `${run.mode} (device ${run.device})` : "—"} />
            <Fact label="Started" value={run ? run.started : "—"} />
            <Fact label="Model A budget" value={meta ? `${meta.budget.ep_A} episodes` : "—"} />
            <Fact label="Model B budget" value={meta ? `${meta.budget.ep_B} episodes` : "—"} />
            <Fact label="Seeds" value={meta ? meta.budget.seeds.join(", ") : "—"} />
            <Fact label="Roads / hazard data" value={run ? run.data_mode : "—"} />
            <Fact label="Corridor graph" value={cg ? `${cg.n_nodes} nodes · ${cg.n_edges} edges` : "—"} />
            <Fact label="Open route" value={cg ? `${cg.open_km?.toFixed(1)} km · ${cg.open_min?.toFixed(0)} min` : "—"} />
          </dl>
        </div>
        <div className="rounded-lg border border-slate-800 bg-slate-900/40 p-4">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-400">Service health</h3>
          {health ? (
            <ul className="mt-2 space-y-1.5 text-xs">
              <li className="flex items-center gap-2">
                <span className={`inline-block h-2 w-2 rounded-full ${health.status === "ok" ? "bg-emerald-400" : "bg-amber-400"}`} />
                <span className="text-slate-300">{health.status === "ok" ? "eptask-api ready" : "degraded"}</span>
                <span className="ml-auto font-mono text-slate-500">up {Math.round(health.uptime_s / 60)} min</span>
              </li>
              <li className="text-slate-400">Graph: {health.graph_nodes} nodes loaded</li>
              <li className="text-slate-400">Latency arms: {health.latency_arms.join(", ") || "—"}</li>
              <li className="text-slate-400">ONNX exports: {health.onnx_exports.length} files</li>
              <li className="text-slate-400">Cached policies: {health.policies_cached.join(", ") || "none yet"}</li>
              <li className="text-slate-400">Reference artifacts: {health.reference_loaded ? "loaded" : "missing"}</li>
            </ul>
          ) : (
            <p className="mt-2 text-xs text-red-300">eptask-api unreachable — check that the mini-service is running (mini-services/eptask-api, port 8100).</p>
          )}
        </div>
      </section>

      <section className="grid gap-3 md:grid-cols-2">
        <div className="rounded-lg border border-slate-800 bg-slate-900/40 p-4">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-400">Model registry</h3>
          <table className="mt-2 w-full text-left text-xs">
            <thead><tr className="text-slate-500">
              <th className="py-1 font-medium">Model</th><th className="py-1 font-medium">Design</th>
              <th className="py-1 font-medium">Trained</th><th className="py-1 font-medium">Exports</th>
            </tr></thead>
            <tbody className="text-slate-300">
              <tr className="border-t border-slate-800">
                <td className="py-1.5">Model A — static MEPPO</td>
                <td className="py-1.5">calm-world task offloading (v6.1 replication + 2 fixes)</td>
                <td className="py-1.5 tabular-nums">{meta?.budget.ep_A ?? "—"} episodes</td>
                <td className="py-1.5">meppo_A_v10/30/50.onnx</td>
              </tr>
              <tr className="border-t border-slate-800">
                <td className="py-1.5">Model B — DR-MEPPO</td>
                <td className="py-1.5">disaster-aware training (domain-randomised outages, miss-penalised reward)</td>
                <td className="py-1.5 tabular-nums">{meta?.budget.ep_B ?? "—"} episodes</td>
                <td className="py-1.5">meppo_B_v10/30/50.onnx</td>
              </tr>
            </tbody>
          </table>
          {meta?.checks?.onnx_vs_torch_disagreements_of_500 != null && (
            <p className="mt-2 text-[11px] text-slate-500">
              Export fidelity (notebook check): {meta.checks.onnx_vs_torch_disagreements_of_500}/500 decisions differed between the ONNX export and the torch model.
            </p>
          )}
        </div>
        <div className="rounded-lg border border-slate-800 bg-slate-900/40 p-4">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-400">What is live vs static here</h3>
          <ul className="mt-2 space-y-1.5 text-xs text-slate-300">
            <li><span className="rounded bg-emerald-950/60 px-1.5 py-px text-emerald-300">live</span> corridor trials, cell rollouts, outage studies, decision explanations, coverage curves — computed per request from the notebook modules.</li>
            <li><span className="rounded bg-sky-950/60 px-1.5 py-px text-sky-300">reference</span> results_v71.json tables, figures, the corridor graph, ONNX models and micro-latency samples — fixed artifacts shipped with the notebook.</li>
            <li><span className="rounded bg-amber-950/60 px-1.5 py-px text-amber-300">assumption</span> hazard presets (footprint/traffic), convoy dispatch times, vehicle-type mix, road speeds — declared in the notebook code itself.</li>
          </ul>
        </div>
      </section>

      <section className="rounded-lg border border-slate-800 bg-slate-900/40 p-4">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-400">Research context — read before quoting numbers</h3>
        <ul className="mt-2 list-disc space-y-1 pl-5 text-xs leading-relaxed text-slate-300">
          <li>Disaster-aware training (model B) trades a small calm-traffic penalty for a win under severe outages — measure it yourself in the outage study, and note the paired design before interpreting.</li>
          <li>The corridor is the SCHEMATIC two-route map through real place positions; the run had no OpenStreetMap/NASA access, so the hazard prior is uniform and COOLR points are absent.</li>
          <li>N1/N2 scheduling effects measured in the notebook were within noise at the deadline level; the notebook is explicit about what its results do and do not support.</li>
          <li>Every simulation is deterministic given (seed, parameters): the repository&apos;s tests reproduce the notebook&apos;s recorded traces exactly.</li>
        </ul>
      </section>
    </div>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-[11px] text-slate-500">{label}</dt>
      <dd className="font-mono text-slate-300">{value}</dd>
    </div>
  );
}
