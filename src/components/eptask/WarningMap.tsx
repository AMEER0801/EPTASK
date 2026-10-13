"use client";
// WarningMap -- compact 2D schematic of one corridor run for the side-by-side
// comparison. Draws the live road graph (schematic or OpenStreetMap), the
// hazard blockage, the roadside units (alive/destroyed) and the ambulance
// trajectory split at the moment it first got informed -- the two decisions
// that make the warning network visible: where it heard, and where it turned.

import { useMemo } from "react";
import type { CorridorResult, GraphData } from "@/lib/eptask/types";

const W = 1000; // viewBox width; height follows the graph aspect ratio
const MAJOR_ROADS = new Set(["trunk", "trunk_link", "primary", "primary_link",
  "secondary", "secondary_link", "tertiary", "tertiary_link",
  "access", "valley", "hill"]);
const MAX_MINOR_EDGES = 4000; // keep SVG maps snappy on real OSM extracts

export default function WarningMap({
  graph, run, label, accent = "#f59e0b",
}: {
  graph: GraphData | null;
  run: CorridorResult;
  label: string;
  accent?: string;
}) {
  const H = 620; // viewBox height

  const nodes = useMemo(() => {
    const m = new Map<number, { x: number; y: number; name: string }>();
    graph?.nodes.forEach(([id, x, y, name]) => m.set(id, { x, y, name }));
    return m;
  }, [graph]);

  const tf = useMemo(() => {
    if (!graph) return null;
    const [minX, minY, maxX, maxY] = graph.bbox;
    const pad = 0.02 * Math.max(maxX - minX, maxY - minY);
    const x0 = minX - pad, x1 = maxX + pad, y0 = minY - pad, y1 = maxY + pad;
    return {
      px: (x: number) => ((x - x0) / (x1 - x0)) * W,
      py: (y: number) => (1 - (y - y0) / (y1 - y0)) * H,
    };
  }, [graph]);

  // on real OSM extracts the server already filters to the corridor; cap the
  // remainder client-side: all major roads + a bounded sample of minor ways
  const edges = useMemo(() => {
    if (!graph || graph.edges.length <= MAX_MINOR_EDGES + 500) return graph?.edges ?? [];
    const major: [number, number, string][] = [];
    const minor: [number, number, string][] = [];
    graph.edges.forEach((e) => (MAJOR_ROADS.has(e[2]) ? major : minor).push(e));
    const stride = Math.max(1, Math.ceil(minor.length / MAX_MINOR_EDGES));
    for (let i = 0; i < minor.length; i += stride) major.push(minor[i]);
    return major;
  }, [graph]);

  const amb = useMemo(() => {
    // rows: [t, x/10, y/10, inf, reroute, passed, seen, missed, stuck, done]
    const rows = run.amb ?? [];
    const pts = rows.map((r) => ({ x: r[1] * 10, y: r[2] * 10, inf: r[3], done: r[9], stuck: r[8] }));
    const firstInf = pts.findIndex((p) => p.inf === 1);
    return { pts, firstInf };
  }, [run]);

  if (!graph || !tf) {
    return (
      <div className="flex h-64 items-center justify-center rounded border border-slate-800 bg-slate-900/40 text-xs text-slate-500">
        road graph unavailable
      </div>
    );
  }

  const hazard = run.hazard_edge.map(([x, y]) => [tf.px(x), tf.py(y)] as const);
  const before = amb.firstInf >= 0 ? amb.pts.slice(0, amb.firstInf + 1) : amb.pts;
  const after = amb.firstInf >= 0 ? amb.pts.slice(amb.firstInf) : [];
  const end = amb.pts[amb.pts.length - 1];
  const alive = run.rsu.xy.filter((_, i) => run.rsu.alive[i] === 1);
  const dead = run.rsu.xy.filter((_, i) => run.rsu.alive[i] !== 1);

  return (
    <figure className="overflow-hidden rounded-lg border border-slate-800 bg-slate-950">
      <figcaption className="flex items-center justify-between gap-2 border-b border-slate-800 px-3 py-2">
        <span className="text-xs font-semibold" style={{ color: accent }}>{label}</span>
        <span className="text-[11px] text-slate-500">{graph.source}</span>
      </figcaption>
      <svg viewBox={`0 0 ${W} ${H}`} className="block h-auto w-full" role="img"
           aria-label={`Warning network map: ${label}`}>
        {/* roads */}
        {edges.map(([u, v], i) => {
          const a = nodes.get(u), b = nodes.get(v);
          if (!a || !b) return null;
          return <line key={i} x1={tf.px(a.x)} y1={tf.py(a.y)} x2={tf.px(b.x)} y2={tf.py(b.y)}
                       stroke="#334155" strokeWidth={1.1} />;
        })}
        {/* hazard blockage */}
        {hazard.length === 2 && (
          <>
            <line x1={hazard[0][0]} y1={hazard[0][1]} x2={hazard[1][0]} y2={hazard[1][1]}
                  stroke="#ef4444" strokeWidth={5} strokeLinecap="round" />
            <circle cx={(hazard[0][0] + hazard[1][0]) / 2} cy={(hazard[0][1] + hazard[1][1]) / 2}
                    r={9} fill="#ef4444" />
            <text x={(hazard[0][0] + hazard[1][0]) / 2} y={(hazard[0][1] + hazard[1][1]) / 2 + 4}
                  textAnchor="middle" fontSize={11} fontWeight={700} fill="#0f172a">✕</text>
          </>
        )}
        {/* RSUs */}
        {alive.map(([x, y], i) => (
          <g key={`a${i}`}>
            <circle cx={tf.px(x)} cy={tf.py(y)} r={7} fill="#10b981" fillOpacity={0.9} />
            <circle cx={tf.px(x)} cy={tf.py(y)} r={13} fill="none" stroke="#10b981"
                    strokeOpacity={0.35} strokeWidth={1.5} />
          </g>
        ))}
        {dead.map(([x, y], i) => (
          <circle key={`d${i}`} cx={tf.px(x)} cy={tf.py(y)} r={6} fill="#475569" />
        ))}
        {/* ambulance trajectory */}
        {before.length > 1 && (
          <polyline fill="none" stroke="#38bdf8" strokeWidth={3} strokeLinejoin="round"
                    points={before.map((p) => `${tf.px(p.x)},${tf.py(p.y)}`).join(" ")} />
        )}
        {after.length > 1 && (
          <polyline fill="none" stroke={accent} strokeWidth={3} strokeLinejoin="round"
                    strokeDasharray="14 7"
                    points={after.map((p) => `${tf.px(p.x)},${tf.py(p.y)}`).join(" ")} />
        )}
        {amb.pts.length > 0 && (
          <>
            <circle cx={tf.px(amb.pts[0].x)} cy={tf.py(amb.pts[0].y)} r={8} fill="#38bdf8" />
            {end && (
              <circle cx={tf.px(end.x)} cy={tf.py(end.y)} r={8}
                      fill={end.stuck ? "#ef4444" : "#10b981"} stroke="#0f172a" strokeWidth={2} />
            )}
          </>
        )}
        {/* named places */}
        {graph.nodes.filter(([, , , name]) => name).map(([id]) => {
          const n = nodes.get(id);
          if (!n) return null;
          return (
            <text key={id} x={tf.px(n.x) + 10} y={tf.py(n.y) - 8} fontSize={19}
                  fill="#94a3b8" fontWeight={600}>{n.name}</text>
          );
        })}
      </svg>
      <figcaption className="flex flex-wrap gap-x-4 gap-y-1 border-t border-slate-800 px-3 py-1.5 text-[10px] text-slate-500">
        <span><i className="mr-1 inline-block h-1.5 w-4 bg-sky-400 align-middle" />before first warning</span>
        <span><i className="mr-1 inline-block h-1.5 w-4 align-middle" style={{ background: accent }} />informed / rerouting</span>
        <span><i className="mr-1 inline-block h-2 w-2 rounded-full bg-emerald-500 align-middle" />RSU alive</span>
        <span><i className="mr-1 inline-block h-2 w-2 rounded-full bg-slate-500 align-middle" />RSU lost</span>
        <span><i className="mr-1 inline-block h-2 w-2 rounded-full bg-red-500 align-middle" />blockage</span>
        {amb.pts.length === 0 && <span className="text-amber-500">trace off — geometry only</span>}
      </figcaption>
    </figure>
  );
}
