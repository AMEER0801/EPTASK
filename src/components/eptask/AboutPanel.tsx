"use client";
// AboutPanel -- architecture & integration summary served with the product.

const SECTIONS: { title: string; body: React.ReactNode }[] = [
  {
    title: "What is new in v2",
    body: (
      <ul className="list-disc space-y-1 pl-5">
        <li><strong className="text-slate-200">Real OpenStreetMap roads</strong> — the Corridor panel can now fetch drivable highways for the corridor from the Overpass API, cache the extract, and hand it to the notebook&apos;s own <code>corridor.build_corridor()</code>, which keeps OSM only when the graph is connected and a detour exists. Offline or rejected → it falls back to the schematic and tells you exactly why.</li>
        <li><strong className="text-slate-200">Compare networks</strong> tab — adjust the hazard preset (footprint, traffic, seed, dispatch) and run two information modes side by side: two maps, informed-share curves and a per-metric delta from live runs of the original <code>run_trial</code>.</li>
        <li><strong className="text-slate-200">Persistent job history</strong> — every run (including full results) is stored in a local SQLite database and survives restarts; the in-memory LRU remains the hot cache.</li>
        <li><strong className="text-slate-200">Optional API-key auth</strong> — set <code>EPTASK_API_KEY</code> to lock the HTTP surface; the console shows a key gate and sends <code>X-API-Key</code>. Unset = local single-user mode.</li>
        <li><strong className="text-slate-200">Portable packaging</strong> — the app ships as a zip that runs on a laptop with a Python venv and Node/bun; see SETUP_GUIDE.md.</li>
      </ul>
    ),
  },
  {
    title: "What this application is",
    body: (
      <>
        <p>
          The original deliverable pair was (a) a static 3D demo that <em>replayed</em> pre-recorded
          simulations and (b) the EPtask V7.1 research notebook that produced those simulations. This
          application merges them: the notebook&apos;s modules now run on a server, and the interface
          requests real executions instead of replaying embedded JSON.
        </p>
        <p>
          The demo&apos;s 3D situation map (terrain, routes, vehicles, RSUs, playback) was preserved and
          restyled to an operational look; its embedded 7.2&nbsp;MB dataset was removed. Everything that
          moves on the map is now returned by the simulation service for the parameters you chose.
        </p>
      </>
    ),
  },
  {
    title: "Architecture",
    body: (
      <>
        <pre className="overflow-x-auto rounded bg-slate-950 p-3 text-[11px] leading-relaxed text-slate-300">{`browser ── Caddy gateway (:443/:3000)
   ├── Next.js console (this app)  /      — launcher, 3D map, tables, charts
   └── /api/*?XTransformPort=8100 ──►  eptask-api (FastAPI, port 8100)
        ├── core/                 the ORIGINAL eptask modules, unmodified
        ├── assets/demo_bundle/   graph, results_v71.json, ONNX exports, latency samples
        └── app/                  thin services: corridor_svc, cell_svc, outage_svc, jobs`}</pre>
        <p>
          The Python service imports <code>corridor.py</code>, <code>env.py</code>,
          <code> policies.py</code>, <code>contributions.py</code> and <code>config.py</code> exactly as
          the notebook does — the algorithms, parameters and preprocessing are untouched. Policies run
          through onnxruntime with the notebook&apos;s own <code>OnnxPolicy</code> wrapper and the shipped
          sidecar JSONs; no model was retrained or re-exported.
        </p>
      </>
    ),
  },
  {
    title: "Where each demo element comes from now",
    body: (
      <table className="w-full text-left text-xs">
        <thead><tr className="text-slate-500">
          <th className="py-1 pr-3 font-medium">Element</th><th className="py-1 pr-3 font-medium">Old demo</th><th className="py-1 font-medium">This application</th>
        </tr></thead>
        <tbody className="text-slate-300">
          {[
            ["Corridor replay (12 traces embedded)", "replayed demo_data.json", "corridor.run_trial executed per request; recorder verified against an unrecorded rerun"],
            ["Ambulance / convoy behaviour", "embedded", "live; same blockage, traffic seed and RSUs per convoy member"],
            ["Cell tick replay", "embedded (520 ticks)", "VECEnv + OnnxPolicy live, counterfactuals from env.peek"],
            ["C3 outage table", "static table", "paired live study via policies.rollout (any k, seeds, policies)"],
            ["results_v71.json numbers", "mixed into panels", "shown only in Reference, explicitly labeled as recorded artifacts"],
            ["Figures", "embedded PNGs", "served from the notebook bundle, labeled recorded"],
          ].map(([a, b, c]) => (
            <tr key={a} className="border-t border-slate-800">
              <td className="py-1.5 pr-3">{a}</td>
              <td className="py-1.5 pr-3 text-slate-400">{b}</td>
              <td className="py-1.5">{c}</td>
            </tr>
          ))}
        </tbody>
      </table>
    ),
  },
  {
    title: "Fidelity evidence",
    body: (
      <>
        <p>
          The service is deterministic given (seed, parameters), which makes equivalence testable:
          <code> scripts/test_consistency.py</code> re-runs all 12 corridor presets and the 520-tick cell
          trace live and compares them with the recording embedded in the original demo. As of the last
          run: ambulance tracks, civilian tracks and summaries match exactly; all 520 cell ticks match
          field-for-field.
        </p>
        <p>
          The recording hook used for traces is the demo builder&apos;s own anchored-patch technique; every
          recorded run is re-verified against an unrecorded rerun before being served, and the service
          refuses to return a trace if the two ever disagree.
        </p>
      </>
    ),
  },
  {
    title: "Engineering notes",
    body: (
      <ul className="list-disc space-y-1 pl-5">
        <li>Jobs are queued on a 2-worker pool; heavy studies never block the HTTP event loop, and progress is reported by the simulation itself (per convoy member / per tick / per rollout).</li>
        <li>All inputs are validated server-side with strict ranges (V ≤ 60, ticks ≤ 3000, ≤ 6 seeds, ≤ 4 outage sizes); no user input ever reaches a filesystem path.</li>
        <li>Models, graph and reference data load once at startup; ONNX sessions are cached after first use (~20 ms each), so repeated requests pay only simulation cost.</li>
        <li>Errors surface with actionable messages (including the API&apos;s validation details) and never expose stack traces to the client.</li>
        <li>The frontend degrades gracefully: without WebGL the consoles remain fully usable; without the Python service every panel explains what is missing.</li>
      </ul>
    ),
  },
  {
    title: "Known limitations",
    body: (
      <ul className="list-disc space-y-1 pl-5">
        <li>Real roads need network access: where Overpass is unreachable (as in the original notebook environment and this sandbox), the service keeps the schematic graph and reports the fetch failure honestly. The cached extract keeps working offline once fetched. NASA COOLR landslide points remain the bundled sample (live COOLR needs an Earthdata login).</li>
        <li>Outage studies run the ONNX exports (v30) rather than the notebook&apos;s in-memory torch checkpoints; the notebook itself verified 0/500 decision disagreements between the two.</li>
        <li>The micro-latency samples feeding corridor service delays come from the recorded arm you select; recomputing them live per request would double run time for identical numbers.</li>
        <li>Performance: a corridor request runs 6–7 full 6-hour trials (~8 s); the paired outage study scales linearly with policies × sizes × seeds (µ2 rollouts × ~0.9 s). The OSM rebuild blocks one simulation worker for up to ~2 min on a slow network.</li>
        <li>Auth is a single shared API key (constant-time compared, stored server-side via the environment) — sized for a research console, not for multi-user public deployment. Job history lives in SQLite without row-level access control.</li>
        <li>Results inherit the notebook&apos;s assumptions: Poisson traffic, fixed radio ranges, dispatch-time conventions. They support engineering comparison, not operational claims.</li>
      </ul>
    ),
  },
];

export default function AboutPanel() {
  return (
    <div className="flex flex-col gap-4">
      {SECTIONS.map((s) => (
        <section key={s.title} className="rounded-lg border border-slate-800 bg-slate-900/40 p-4">
          <h2 className="mb-2 text-sm font-semibold text-slate-100">{s.title}</h2>
          <div className="space-y-2 text-xs leading-relaxed text-slate-300">{s.body}</div>
        </section>
      ))}
    </div>
  );
}
