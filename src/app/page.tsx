"use client";
// EPtask Operations Console -- single-route application shell (v2).
// v2 adds the Compare panel (hazard presets + side-by-side warning networks)
// and an API-key gate that appears when the backend requires authentication.

import { useCallback, useEffect, useState } from "react";
import { fetchMeta, setApiKey, setUnauthorizedHandler, type MetaInfo } from "@/lib/eptask/client";
import OverviewPanel from "@/components/eptask/OverviewPanel";
import CorridorPanel from "@/components/eptask/CorridorPanel";
import ComparePanel from "@/components/eptask/ComparePanel";
import CellPanel from "@/components/eptask/CellPanel";
import OutagePanel from "@/components/eptask/OutagePanel";
import ReferencePanel from "@/components/eptask/ReferencePanel";
import AboutPanel from "@/components/eptask/AboutPanel";

const TABS = [
  { v: "overview", label: "Overview" },
  { v: "corridor", label: "Corridor · N1" },
  { v: "compare", label: "Compare networks" },
  { v: "cell", label: "VEC cell" },
  { v: "outage", label: "Outage study" },
  { v: "reference", label: "Reference" },
  { v: "about", label: "About" },
] as const;
type Tab = (typeof TABS)[number]["v"];

export default function Home() {
  const [tab, setTab] = useState<Tab>("overview");
  const [meta, setMeta] = useState<MetaInfo | null>(null);
  const [apiUp, setApiUp] = useState<boolean | null>(null);
  const [authGate, setAuthGate] = useState(false);
  const [keyInput, setKeyInput] = useState("");
  const [authMsg, setAuthMsg] = useState<string | null>(null);

  const loadMeta = useCallback(() => {
    fetchMeta()
      .then((m) => { setMeta(m); setApiUp(true); setAuthGate(false); })
      .catch(() => setApiUp(false));
  }, []);

  useEffect(() => {
    setUnauthorizedHandler(() => setAuthGate(true));
    loadMeta();
    return () => setUnauthorizedHandler(null);
  }, [loadMeta]);

  const submitKey = () => {
    setApiKey(keyInput);
    setAuthGate(false);   // optimistic: the 401 handler reopens the gate if wrong
    loadMeta();
  };

  return (
    <div className="flex min-h-screen flex-col bg-slate-950 text-slate-200">
      <header className="sticky top-0 z-20 border-b border-slate-800 bg-slate-950/95 backdrop-blur">
        <div className="mx-auto flex max-w-[1400px] flex-wrap items-center gap-x-4 gap-y-2 px-4 py-2.5">
          <h1 className="text-sm font-semibold tracking-wide text-slate-100">
            EPtask <span className="text-amber-500">Ops</span> Console
          </h1>
          <span className="hidden text-[11px] text-slate-500 sm:inline">
            live execution of the V7.1 notebook · run {meta?.run.run_id ?? "…"}
          </span>
          <span className="ml-auto flex items-center gap-3 text-[11px] text-slate-400">
            {meta?.auth_required && (
              <span className="rounded border border-amber-700/60 bg-amber-950/40 px-1.5 py-0.5 text-amber-400">
                API key required
              </span>
            )}
            <span className="flex items-center gap-1.5">
              <span className={`inline-block h-2 w-2 rounded-full ${apiUp ? "bg-emerald-400" : apiUp === false ? "bg-red-500" : "bg-slate-500"}`} />
              {apiUp ? "simulation service online" : apiUp === false ? "simulation service unreachable" : "connecting…"}
            </span>
          </span>
        </div>
        <nav className="mx-auto max-w-[1400px] px-4" aria-label="Sections">
          <ul className="flex gap-1 overflow-x-auto pb-1">
            {TABS.map((t) => (
              <li key={t.v}>
                <button
                  onClick={() => setTab(t.v)}
                  aria-current={tab === t.v ? "page" : undefined}
                  className={`whitespace-nowrap rounded-t border-b-2 px-3 py-1.5 text-xs font-medium transition ${
                    tab === t.v
                      ? "border-amber-500 text-amber-400"
                      : "border-transparent text-slate-400 hover:text-slate-200"
                  }`}
                >
                  {t.label}
                </button>
              </li>
            ))}
          </ul>
        </nav>
      </header>

      <main className="mx-auto w-full max-w-[1400px] flex-1 px-4 py-4">
        {apiUp === false && (
          <p role="alert" className="mb-4 rounded border border-red-900/60 bg-red-950/40 px-3 py-2 text-xs text-red-300">
            The simulation service (eptask-api on port 8100) is not reachable. Start it with
            <code className="mx-1 rounded bg-slate-900 px-1.5 py-0.5">bash mini-services/eptask-api/run.sh</code>
            then reload this page. The panels below will remain empty until then.
          </p>
        )}
        {tab === "overview" && <OverviewPanel meta={meta} />}
        {tab === "corridor" && <CorridorPanel meta={meta} onMetaRefresh={loadMeta} />}
        {tab === "compare" && <ComparePanel meta={meta} />}
        {tab === "cell" && <CellPanel meta={meta} />}
        {tab === "outage" && <OutagePanel />}
        {tab === "reference" && <ReferencePanel figures={meta?.figures ?? []} />}
        {tab === "about" && <AboutPanel />}
      </main>

      <footer className="mt-auto border-t border-slate-800 py-3">
        <div className="mx-auto flex max-w-[1400px] flex-wrap items-center justify-between gap-2 px-4 text-[11px] text-slate-500">
          <span>EPtask V7.1 · MEPPO task-offloading research console · simulation service: FastAPI + onnxruntime</span>
          <span className="font-mono">data: {meta?.run.data_mode ?? "—"}{meta?.service?.graph_source ? ` · roads: ${meta.service.graph_source}` : ""}</span>
        </div>
      </footer>

      {/* ---- v2 auth gate ---- */}
      {authGate && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 p-4 backdrop-blur-sm"
             role="dialog" aria-modal="true" aria-label="API key required">
          <div className="w-full max-w-md rounded-lg border border-slate-700 bg-slate-900 p-6 shadow-2xl">
            <h2 className="text-sm font-semibold text-slate-100">API key required</h2>
            <p className="mt-2 text-xs leading-relaxed text-slate-400">
              This deployment sets <code className="rounded bg-slate-800 px-1 text-amber-400">EPTASK_API_KEY</code>,
              so the console must send it on every request. Paste the key once — it is stored
              in this browser only (localStorage) and sent as the <code className="rounded bg-slate-800 px-1">X-API-Key</code> header.
            </p>
            <input
              type="password" autoFocus value={keyInput}
              onChange={(e) => setKeyInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && submitKey()}
              placeholder="API key"
              className="mt-4 w-full rounded border border-slate-700 bg-slate-950 px-3 py-2 font-mono text-sm text-slate-200 focus:border-amber-500/60 focus:outline-none"
            />
            {authMsg && <p className="mt-2 text-xs text-red-400">{authMsg}</p>}
            <div className="mt-4 flex justify-end gap-2">
              <button onClick={() => { setApiKey(""); setKeyInput(""); setAuthGate(false); }}
                      className="rounded border border-slate-700 px-3 py-1.5 text-xs text-slate-400 hover:text-slate-200">
                Cancel
              </button>
              <button onClick={submitKey}
                      className="rounded bg-amber-500 px-4 py-1.5 text-xs font-semibold text-slate-950 hover:bg-amber-400">
                Save &amp; retry
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
