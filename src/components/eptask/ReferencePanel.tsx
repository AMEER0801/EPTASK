"use client";
// ReferencePanel -- the notebook's recorded artifacts, clearly labeled static.

import { useEffect, useState } from "react";
import { fetchReference, figureUrl } from "@/lib/eptask/client";

const SECTIONS = ["c3", "c1", "c2", "n1", "n2", "corridor", "training", "checks", "onnx"] as const;
type Section = (typeof SECTIONS)[number];

const SECTION_LABEL: Record<Section, string> = {
  c3: "C3 · paired outage",
  c1: "C1 · safety floor",
  c2: "C2 · explanations",
  n1: "N1 · emergency vehicles",
  n2: "N2 · casualty priority",
  corridor: "Road-scale experiment",
  training: "Training records",
  checks: "Regression checks",
  onnx: "ONNX export checks",
};

function Render<T>({ data }: { data: T }) {
  // generic, readable JSON browser with table-first rendering for row dicts
  if (data == null) return <p className="text-xs text-slate-500">—</p>;
  if (Array.isArray(data)) {
    if (data.length && typeof data[0] === "object" && data[0] !== null) {
      const cols = Array.from(new Set(data.flatMap((o) => Object.keys(o as object)))).slice(0, 8);
      return (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[480px] text-left text-xs">
            <thead><tr className="text-slate-500">{cols.map((c) => <th key={c} className="py-1 pr-3 font-medium">{c}</th>)}</tr></thead>
            <tbody className="text-slate-300">
              {data.slice(0, 40).map((row, i) => (
                <tr key={i} className="border-t border-slate-800">
                  {cols.map((c) => (
                    <td key={c} className="py-1 pr-3 font-mono tabular-nums">{fmtCell((row as Record<string, unknown>)[c])}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
          {data.length > 40 && <p className="mt-1 text-[11px] text-slate-500">showing 40 of {data.length} rows</p>}
        </div>
      );
    }
    return <p className="font-mono text-xs text-slate-300">{JSON.stringify(data).slice(0, 400)}</p>;
  }
  if (typeof data === "object") {
    return (
      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs">
          <tbody className="text-slate-300">
            {Object.entries(data as Record<string, unknown>).map(([k, v]) => (
              <tr key={k} className="border-t border-slate-800/70">
                <td className="w-56 py-1 pr-3 align-top text-slate-400">{k}</td>
                <td className="py-1 font-mono text-[11px]">{fmtCell(v)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }
  return <p className="font-mono text-xs text-slate-300">{String(data)}</p>;
}

function fmtCell(v: unknown): string {
  if (v == null) return "—";
  if (Array.isArray(v)) {
    if (v.length === 3 && v.every((x) => typeof x === "number") && v.some((x) => typeof x === "number" && !Number.isInteger(x)))
      return `${Number(v[0]).toFixed(2)} ± ${Number(v[1]).toFixed(2)} (n=${v[2]})`;
    const s = JSON.stringify(v);
    return s.length > 90 ? s.slice(0, 87) + "…" : s;
  }
  if (typeof v === "object") { const s = JSON.stringify(v); return s.length > 90 ? s.slice(0, 87) + "…" : s; }
  if (typeof v === "number") return Number.isInteger(v) ? String(v) : v.toFixed(3);
  return String(v);
}

export default function ReferencePanel({ figures }: { figures: string[] }) {
  const [section, setSection] = useState<Section>("c3");
  const [loaded, setLoaded] = useState<{ section: Section; data: unknown; note: string } | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    fetchReference(section)
      .then((r) => {
        if (!alive) return;
        setLoaded({ section, data: r.data, note: r.note });
        setError(null);
      })
      .catch((e) => {
        if (!alive) return;
        setError(String(e));
      });
    return () => {
      alive = false;
    };
  }, [section]);

  const loading = loaded === null || loaded.section !== section;

  return (
    <div className="flex flex-col gap-4">
      <section className="rounded-lg border border-slate-800 bg-slate-900/40 p-4">
        <div className="flex flex-wrap items-center gap-2">
          {SECTIONS.map((s) => (
            <button key={s} onClick={() => setSection(s)}
              className={`rounded px-2.5 py-1 text-xs font-medium transition ${section === s ? "bg-amber-600 text-white" : "border border-slate-700 text-slate-300 hover:bg-slate-800"}`}>
              {SECTION_LABEL[s]}
            </button>
          ))}
        </div>
        <p className="mt-3 text-[11px] text-slate-500">{loaded?.note ?? ""}</p>
      </section>

      <section className="rounded-lg border border-slate-800 bg-slate-900/40 p-4">
        {loading && <p className="text-xs text-slate-400">Loading reference artifact…</p>}
        {error && <p role="alert" className="text-xs text-red-300">{error}</p>}
        {!loading && !error && loaded && <Render data={loaded.data} />}
      </section>

      <section className="rounded-lg border border-slate-800 bg-slate-900/40 p-4">
        <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-400">Notebook figures (recorded)</h3>
        <p className="mb-3 text-[11px] text-slate-500">
          Generated by the notebook run; served as files. Live recomputation of these exact figures is
          the Outage/Corridor/Cell consoles&apos; job.
        </p>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {figures.map((f) => (
            <figure key={f} className="overflow-hidden rounded border border-slate-800 bg-slate-950">
              <img src={figureUrl(f)} alt={f.replace(/_/g, " ")} loading="lazy" className="h-44 w-full object-contain" />
              <figcaption className="border-t border-slate-800 px-2 py-1 text-[11px] text-slate-400">{f}</figcaption>
            </figure>
          ))}
        </div>
      </section>
    </div>
  );
}
