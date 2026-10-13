"use client";
// CorridorMap -- live 3D situation map for the road-scale (N1) simulation.
//
// The terrain, route geometry and trace playback are ported from the demo's
// tools/template.html (demo.zip) so the recorded/live traces render exactly as
// the research demo rendered them. The visual language is deliberately
// restrained for operations use: no bloom, no decorative glow, no scripted
// damage animations -- every visible element is trace data or map furniture.
//
// The trace data itself is produced live by the eptask-api service
// (corridor.py run_trial), not embedded in the page.

import { forwardRef, useCallback, useEffect, useImperativeHandle, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import type { CorridorResult, GraphData } from "@/lib/eptask/types";

export interface MapHandle {
  seek: (t: number) => void;
  getTime: () => number;
}

interface Props {
  graph: GraphData | null;
  trace: CorridorResult | null;
  playing: boolean;
  speed: number;
  onTick?: (t: number, done: boolean, nVeh: number) => void;
}

// ---------------------------------------------------------------- geometry helpers (ported)
const lerp = (a: number, b: number, f: number) => a + (b - a) * f;
const clamp = (v: number, a: number, b: number) => Math.max(a, Math.min(b, v));

function poly(pts: [number, number][]) {
  const cum = [0];
  for (let i = 1; i < pts.length; i++)
    cum.push(cum[i - 1] + Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]));
  return { pts, cum, L: cum[cum.length - 1] || 1 };
}

function nearest(P: { pts: [number, number][]; cum: number[]; L: number }, x: number, y: number) {
  let best = 1e30, bs = 0;
  const p = P.pts;
  for (let i = 0; i < p.length - 1; i++) {
    const ax = p[i][0], ay = p[i][1], dx = p[i + 1][0] - ax, dy = p[i + 1][1] - ay;
    const l2 = dx * dx + dy * dy || 1;
    let u = ((x - ax) * dx + (y - ay) * dy) / l2;
    u = u < 0 ? 0 : u > 1 ? 1 : u;
    const qx = ax + u * dx - x, qy = ay + u * dy - y, d = qx * qx + qy * qy;
    if (d < best) { best = d; bs = (P.cum[i] + u * Math.sqrt(l2)) / P.L; }
  }
  return [Math.sqrt(best), bs] as const;
}

function densify(pts: [number, number][], step: number): [number, number][] {
  const out: [number, number][] = [pts[0]];
  for (let i = 1; i < pts.length; i++) {
    const a = pts[i - 1], b = pts[i];
    const L = Math.hypot(b[0] - a[0], b[1] - a[1]);
    const n = Math.max(1, Math.ceil(L / step));
    for (let k = 1; k <= n; k++) out.push([lerp(a[0], b[0], k / n), lerp(a[1], b[1], k / n)]);
  }
  return out;
}

function offsetLine(pts: [number, number][], off: number): [number, number][] {
  return pts.map((p, i) => {
    const a = pts[Math.max(0, i - 1)], b = pts[Math.min(pts.length - 1, i + 1)];
    const dx = b[0] - a[0], dy = b[1] - a[1], l = Math.hypot(dx, dy) || 1;
    return [p[0] - (dy / l) * off, p[1] + (dx / l) * off];
  });
}

function hash2(i: number, j: number) {
  let h = (Math.imul(i, 374761393) ^ Math.imul(j, 668265263)) >>> 0;
  h = Math.imul(h ^ (h >>> 13), 1274126177) >>> 0;
  return ((h ^ (h >>> 16)) >>> 0) / 4294967296;
}
function vnoise(x: number, y: number) {
  const i = Math.floor(x), j = Math.floor(y), fx = x - i, fy = y - j;
  const u = fx * fx * (3 - 2 * fx), v = fy * fy * (3 - 2 * fy);
  const a = hash2(i, j), b = hash2(i + 1, j), c = hash2(i, j + 1), d = hash2(i + 1, j + 1);
  return a + (b - a) * u + (c - a) * v + (a - b - c + d) * u * v;
}
function fbm(x: number, y: number) {
  let s = 0, a = 0.5, f = 1;
  for (let o = 0; o < 5; o++) { s += a * vnoise(x * f, y * f); f *= 2.03; a *= 0.5; }
  return s;
}
function smooth(a: number, b: number, x: number) {
  const t = clamp((x - a) / (b - a), 0, 1);
  return t * t * (3 - 2 * t);
}

// vehicle mix: the demo's type shares (positions are recorded; the mix is the demo's stated assumption)
const VTYPES = [
  { key: "car", share: 0.45, len: 2.2 },
  { key: "motorbike", share: 0.2, len: 1.2 },
  { key: "bus", share: 0.15, len: 4.2 },
  { key: "truck", share: 0.2, len: 3.7 },
];
function vtypeOf(vid: number) {
  let h = (Math.imul(vid, 374761393) ^ Math.imul(911, 668265263)) >>> 0;
  h = Math.imul(h ^ (h >>> 13), 1274126177) >>> 0;
  const u = ((h ^ (h >>> 16)) >>> 0) / 4294967296;
  let acc = 0;
  for (let i = 0; i < VTYPES.length; i++) { acc += VTYPES[i].share; if (u < acc) return i; }
  return 0;
}

const COLORS = {
  bg: 0x0b0e13,
  terrainLow: 0x171c24,
  terrainHigh: 0x39424f,
  roadV: 0x5c7ea3,   // NH42 valley (desaturated steel)
  roadH: 0x71805f,   // NH18 hill (moss)
  river: 0x2c4854,
  pin: 0xd8dee6,
  veh: 0xcfd6de,
  ambBody: 0xf2f4f6,
  ambStripe: 0xd64541,
  rsu: 0x46a06b,
  rsuDead: 0xa8433f,
  hazard: 0xc0392b,
  trail: 0xd64541,
  fleet: { police: 0x9fb6d9, fire: 0xb8552f, army: 0x6f7a4b },
};

interface Prepared {
  tStart: number; tEnd: number; frameDt: number; nFrames: number; frameT: number[];
  tracks: { f0: number; inf: number; stuck: number; amb: number; xy: number[]; type: number }[];
  amb: number[][];
  fleet: { key: string; label: string; dispatch_s: number; track: number[][] }[];
  tArr: number;
}

function prep(tr: CorridorResult): Prepared {
  const tracks = tr.veh.map((r) => {
    const n = (r.length - 5) / 2;
    return { f0: r[1], inf: r[2], stuck: r[3], amb: (r[4] >> 1) & 1, xy: r.slice(5), type: vtypeOf(r[0]) };
  });
  const a = tr.amb;
  const tArr = a.length ? a[a.length - 1][0] : tr.frame_t[tr.frame_t.length - 1];
  const lastFrame = tr.frame_t[tr.frame_t.length - 1];
  const fa = (tr.fleet || []).map((f) => (f.track.length ? f.track[f.track.length - 1][0] : 0));
  const tEnd = Math.max(tArr + 120, lastFrame, ...(fa.length ? fa : [0])) + 60;
  return { tStart: tr.frame_t[0], tEnd, frameDt: tr.frame_dt, nFrames: tr.n_frames, frameT: tr.frame_t, tracks, amb: a, fleet: tr.fleet || [], tArr };
}

function ambAt(rows: number[][], t: number) {
  if (!rows.length || t < rows[0][0]) return null;
  let lo = 0, hi = rows.length - 1;
  if (t >= rows[hi][0]) {
    const p = rows[Math.max(0, hi - 1)];
    return { x: rows[hi][1] * 10, y: rows[hi][2] * 10, dx: rows[hi][1] - p[1], dy: rows[hi][2] - p[2], s: rows[hi], i: hi };
  }
  while (hi - lo > 1) { const m = (lo + hi) >> 1; if (rows[m][0] <= t) lo = m; else hi = m; }
  const A = rows[lo], B = rows[hi];
  const f = (t - A[0]) / (B[0] - A[0] || 1);
  return { x: lerp(A[1], B[1], f) * 10, y: lerp(A[2], B[2], f) * 10, dx: B[1] - A[1], dy: B[2] - A[2], s: A, i: lo };
}

function trackAt(a: number[][], t: number) {
  if (!a || !a.length || t < a[0][0]) return null;
  let lo = 0, hi = a.length - 1;
  if (t >= a[hi][0]) {
    const p = a[Math.max(0, hi - 1)];
    return { x: a[hi][1] * 10, y: a[hi][2] * 10, dx: a[hi][1] - p[1], dy: a[hi][2] - p[2], f: a[hi][3] };
  }
  while (hi - lo > 1) { const m = (lo + hi) >> 1; if (a[m][0] <= t) lo = m; else hi = m; }
  const A = a[lo], B = a[hi];
  const k = (t - A[0]) / (B[0] - A[0] || 1);
  return { x: lerp(A[1], B[1], k) * 10, y: lerp(A[2], B[2], k) * 10, dx: B[1] - A[1], dy: B[2] - A[2], f: A[3] };
}

// ---------------------------------------------------------------- component
const CorridorMap = forwardRef<MapHandle, Props>(function CorridorMap(
  { graph, trace, playing, speed, onTick },
  ref,
) {
  const hostRef = useRef<HTMLDivElement>(null);
  const coreRef = useRef<Core | null>(null);
  const [webglFail, setWebglFail] = useState(false);
  const [nVisible, setNVisible] = useState(0);

  // ---- build the scene once the graph is known; the map owns its own loop ----
  // onTick is part of the closure; callers must keep it stable (useCallback).
  useEffect(() => {
    if (!graph || !hostRef.current) return;
    let core: Core | null = null;
    try {
      core = new Core(hostRef.current, graph);
    } catch (e) {
      console.error("[CorridorMap] WebGL initialisation failed:", e);
      queueMicrotask(() => setWebglFail(true));
      return;
    }
    coreRef.current = core;
    core.onTickThrottled = (t, done, n) => {
      setNVisible(n);
      onTick(t, done, n);
    };
    return () => {
      core?.dispose();
      coreRef.current = null;
    };
  }, [graph, onTick]);

  // ---- swap the trace ----
  useEffect(() => {
    coreRef.current?.setTrace(trace);
  }, [trace]);

  // ---- play state ----
  useEffect(() => {
    coreRef.current?.setPlaying(playing, speed);
  }, [playing, speed]);

  useImperativeHandle(ref, () => ({
    seek: (t: number) => coreRef.current?.seek(t),
    getTime: () => coreRef.current?.getTime() ?? 0,
  }));

  return (
    <div ref={hostRef} className="relative h-full w-full overflow-hidden rounded-md border bg-[#0b0e13]" role="img"
      aria-label="3D situation map of the corridor simulation"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === "ArrowLeft") coreRef.current?.seek(coreRef.current.getTime() - 300);
        if (e.key === "ArrowRight") coreRef.current?.seek(coreRef.current.getTime() + 300);
      }}
    >
      {webglFail && (
        <div className="absolute inset-0 grid place-items-center p-6 text-center text-sm text-slate-400">
          WebGL is unavailable in this browser. All metrics and tables on this page still work.
        </div>
      )}
      {!webglFail && !graph && (
        <div className="absolute inset-0 grid place-items-center text-sm text-slate-500">Loading corridor geometry…</div>
      )}
      {!webglFail && graph && !trace && (
        <div className="absolute left-3 bottom-3 rounded border border-slate-700/70 bg-slate-900/80 px-2.5 py-1.5 text-xs text-slate-400">
          Run a simulation to populate the map
        </div>
      )}
      {!webglFail && trace && (
        <div className="pointer-events-none absolute left-3 bottom-3 flex flex-wrap gap-x-3 gap-y-1 rounded border border-slate-700/70 bg-slate-900/80 px-2.5 py-1.5 text-[11px] text-slate-400">
          <span><span className="text-slate-200">{nVisible}</span> vehicles drawn</span>
          <span>ambulance trail = travelled route</span>
          <span><span className="inline-block h-2 w-2 rounded-sm align-middle" style={{ background: "#46a06b" }} /> RSU alive</span>
          <span><span className="inline-block h-2 w-2 rounded-sm align-middle" style={{ background: "#a8433f" }} /> RSU down</span>
        </div>
      )}
    </div>
  );
});
export default CorridorMap;

// ---------------------------------------------------------------- three.js core
class Core {
  renderer: THREE.WebGLRenderer;
  scene: THREE.Scene;
  camera: THREE.PerspectiveCamera;
  controls: OrbitControls;
  raf = 0;
  clockT = 0;
  playing = false;
  speed = 1;
  lastFrameAt = 0;
  lastReport = 0;
  onTickThrottled: ((t: number, done: boolean, n: number) => void) | null = null;

  // geometry-space helpers
  Wx: (x: number) => number; Wz: (y: number) => number; Wy: (h: number) => number;
  heightAt: (x: number, y: number) => number;
  V3: (x: number, y: number, lift: number) => THREE.Vector3;
  BB: { minx: number; miny: number; maxx: number; maxy: number };
  CX: number; CY: number;
  VL: { pts: [number, number][]; cum: number[]; L: number };
  HL: { pts: [number, number][]; cum: number[]; L: number };
  RL: { pts: [number, number][]; cum: number[]; L: number };
  valleyPts: [number, number][];

  traceGroups: THREE.Group | null = null;
  prepared: Prepared | null = null;
  trace: CorridorResult | null = null;

  // trace-driven objects
  vehMeshes: THREE.InstancedMesh[] = [];
  vehCounts = [0, 0, 0, 0];
  amb = new THREE.Group();
  trailGeo = new THREE.BufferGeometry();
  rsuHeads: { head: THREE.Mesh; ring: THREE.Mesh; alive: boolean }[] = [];
  fleetObjs: { key: string; label: string; dispatch: number; group: THREE.Group }[] = [];
  labels: { el: HTMLDivElement; get: () => THREE.Vector3 | null }[] = [];
  labelHost: HTMLDivElement;
  dummy = new THREE.Object3D();
  tmpC = new THREE.Color();

  constructor(host: HTMLDivElement, graph: GraphData) {
    const w = host.clientWidth || 800, h = host.clientHeight || 500;
    this.renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: "high-performance" });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    this.renderer.setSize(w, h);
    this.renderer.domElement.style.display = "block";
    host.appendChild(this.renderer.domElement);

    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color(COLORS.bg);
    this.scene.fog = new THREE.Fog(COLORS.bg, 260, 1400);

    this.camera = new THREE.PerspectiveCamera(42, w / h, 0.5, 6000);
    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.enableDamping = true;
    this.controls.maxPolarAngle = Math.PI * 0.49;

    this.scene.add(new THREE.HemisphereLight(0xbcc7d4, 0x232a33, 1.05));
    const sun = new THREE.DirectionalLight(0xffffff, 1.15);
    sun.position.set(-160, 220, 120);
    this.scene.add(sun);

    // ---------------- world transforms (ported) ----------------
    const BBm = 5000;
    const b = graph.bbox;
    this.BB = { minx: b[0] - BBm, miny: b[1] - BBm, maxx: b[2] + BBm, maxy: b[3] + BBm };
    this.CX = (this.BB.minx + this.BB.maxx) / 2;
    this.CY = (this.BB.miny + this.BB.maxy) / 2;
    const VEX = 1.5;
    this.Wx = (x) => (x - this.CX) / 100;
    this.Wz = (y) => -(y - this.CY) / 100;
    this.Wy = (hh) => ((hh - 500) / 100) * VEX;

    const nodeXY: Record<number, [number, number]> = {};
    graph.nodes.forEach((n) => { nodeXY[n[0]] = [n[1], n[2]]; });
    const named: Record<string, [number, number]> = {};
    Object.entries(graph.named).forEach(([k, v]) => { named[k] = nodeXY[v]; });

    const valleyPts = [...graph.routes.access, ...graph.routes.valley.slice(1)] as [number, number][];
    this.valleyPts = valleyPts;
    this.VL = poly(valleyPts);
    this.HL = poly(graph.routes.hill as [number, number][]);
    this.RL = poly(offsetLine(valleyPts, 170));
    const sJ = this.VL.cum[graph.routes.access.length - 1] / this.VL.L;
    const idxNear = (pts: [number, number][], q: [number, number]) => {
      let bi = 0, bd = 1e30;
      pts.forEach((p, i) => { const d = (p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2; if (d < bd) { bd = d; bi = i; } });
      return bi;
    };
    const sD = named.Dhunche ? this.HL.cum[idxNear(this.HL.pts, named.Dhunche)] / this.HL.L : 0.7;
    const VANCH = [[0, 540], [sJ, 650], [1, 1460]];
    const HANCH = [[0, 650], [sD, 1960], [1, 1460]];
    const anch = (A: number[][], s: number) => {
      for (let i = 1; i < A.length; i++)
        if (s <= A[i][0]) return lerp(A[i - 1][1], A[i][1], (s - A[i - 1][0]) / (A[i][0] - A[i - 1][0] || 1));
      return A[A.length - 1][1];
    };

    const rawH = (x: number, y: number) => {
      const [dv, sv] = nearest(this.VL, x, y);
      const [dh, sh] = nearest(this.HL, x, y);
      const [dr] = nearest(this.RL, x, y);
      const north = (y - this.BB.miny) / (this.BB.maxy - this.BB.miny);
      const base = 1150 + 1600 * fbm(x / 8500 + 3.1, y / 8500 - 1.7) + 950 * north;
      let hh = Math.min(base, anch(VANCH, sv) + 0.42 * Math.max(0, dv - 230));
      if (dr < 170) hh -= 24 * (1 - dr / 170);
      const wgt = smooth(430, 90, dh);
      return hh + (anch(HANCH, sh) - hh) * wgt;
    };

    const NX = 170;
    const NY = Math.round((NX * (this.BB.maxy - this.BB.miny)) / (this.BB.maxx - this.BB.minx));
    const HG = new Float32Array((NX + 1) * (NY + 1));
    for (let j = 0; j <= NY; j++)
      for (let i = 0; i <= NX; i++)
        HG[j * (NX + 1) + i] = rawH(this.BB.minx + (i / NX) * (this.BB.maxx - this.BB.minx), this.BB.miny + (j / NY) * (this.BB.maxy - this.BB.miny));

    this.heightAt = (x: number, y: number) => {
      const fx = clamp(((x - this.BB.minx) / (this.BB.maxx - this.BB.minx)) * NX, 0, NX - 1e-6);
      const fy = clamp(((y - this.BB.miny) / (this.BB.maxy - this.BB.miny)) * NY, 0, NY - 1e-6);
      const i = Math.floor(fx), j = Math.floor(fy);
      const u = fx - i, v = fy - j, k = j * (NX + 1) + i;
      const a = HG[k], b2 = HG[k + 1], c = HG[k + NX + 1], d = HG[k + NX + 2];
      return u + v <= 1 ? a + (b2 - a) * u + (c - a) * v : d + (c - d) * (1 - u) + (b2 - d) * (1 - v);
    };
    this.V3 = (x, y, lift) => new THREE.Vector3(this.Wx(x), this.Wy(this.heightAt(x, y) + (lift || 0)), this.Wz(y));

    // ---------------- terrain mesh: muted elevation shading ----------------
    const pos = new Float32Array((NX + 1) * (NY + 1) * 3);
    const elev = new Float32Array((NX + 1) * (NY + 1));
    for (let j = 0; j <= NY; j++)
      for (let i = 0; i <= NX; i++) {
        const k = j * (NX + 1) + i;
        const x = this.BB.minx + (i / NX) * (this.BB.maxx - this.BB.minx);
        const y = this.BB.miny + (j / NY) * (this.BB.maxy - this.BB.miny);
        pos[k * 3] = this.Wx(x); pos[k * 3 + 1] = this.Wy(HG[k]); pos[k * 3 + 2] = this.Wz(y);
        elev[k] = HG[k];
      }
    const idx: number[] = [];
    for (let j = 0; j < NY; j++)
      for (let i = 0; i < NX; i++) {
        const a = j * (NX + 1) + i, b2 = a + 1, c = a + NX + 1, d = c + 1;
        idx.push(a, b2, c, b2, d, c);
      }
    const tg = new THREE.BufferGeometry();
    tg.setAttribute("position", new THREE.BufferAttribute(pos, 3));
    tg.setAttribute("elev", new THREE.BufferAttribute(elev, 1));
    tg.setIndex(idx);
    tg.computeVertexNormals();
    const tmat = new THREE.MeshStandardMaterial({
      vertexColors: false, color: 0xffffff, roughness: 1, metalness: 0,
      onBeforeCompile: (sh) => {
        sh.vertexShader = "attribute float elev; varying float vE;\n" +
          sh.vertexShader.replace("#include <begin_vertex>", "#include <begin_vertex>\nvE=elev;");
        sh.fragmentShader = "uniform vec3 cLow; uniform vec3 cHigh; varying float vE;\n" +
          sh.fragmentShader.replace("#include <color_fragment>", `
            float t2 = clamp((vE - 500.0) / 2400.0, 0.0, 1.0);
            vec3 base = mix(cLow, cHigh, smoothstep(0.0, 1.0, t2));
            float h1 = vE / 200.0; float f1 = abs(fract(h1) - 0.5);
            float contour = 1.0 - smoothstep(0.0, 0.04, f1);
            diffuseColor.rgb = base + vec3(contour * 0.045);`);
        sh.uniforms.cLow = { value: new THREE.Color(COLORS.terrainLow) };
        sh.uniforms.cHigh = { value: new THREE.Color(COLORS.terrainHigh) };
      },
    });
    const terrain = new THREE.Mesh(tg, tmat);
    this.scene.add(terrain);

    // ---------------- roads, river ----------------
    const ribbon = (pts: [number, number][], width: number, lift: number, mat: THREE.Material) => {
      const n = pts.length;
      const rp = new Float32Array(n * 6);
      const ridx: number[] = [];
      for (let i = 0; i < n; i++) {
        const a = pts[Math.max(0, i - 1)], b2 = pts[Math.min(n - 1, i + 1)];
        const dx = b2[0] - a[0], dy = b2[1] - a[1], l = Math.hypot(dx, dy) || 1;
        const nx = -dy / l, ny = dx / l;
        for (let s = 0; s < 2; s++) {
          const sg = s ? 1 : -1;
          const x = pts[i][0] + (nx * width) / 2 * sg, y = pts[i][1] + (ny * width) / 2 * sg;
          const k = (i * 2 + s) * 3;
          rp[k] = this.Wx(x); rp[k + 1] = this.Wy(this.heightAt(x, y) + lift); rp[k + 2] = this.Wz(y);
        }
        if (i < n - 1) { const q = i * 2; ridx.push(q, q + 1, q + 2, q + 1, q + 3, q + 2); }
      }
      const g = new THREE.BufferGeometry();
      g.setAttribute("position", new THREE.BufferAttribute(rp, 3));
      g.setIndex(ridx);
      g.computeVertexNormals();
      return new THREE.Mesh(g, mat);
    };
    const roadMatV = new THREE.MeshBasicMaterial({ color: COLORS.roadV, side: THREE.DoubleSide });
    roadMatV.polygonOffset = true; roadMatV.polygonOffsetFactor = -2;
    const roadMatH = new THREE.MeshBasicMaterial({ color: COLORS.roadH, side: THREE.DoubleSide });
    roadMatH.polygonOffset = true; roadMatH.polygonOffsetFactor = -2;
    this.scene.add(ribbon(densify(valleyPts, 60), 95, 22, roadMatV));
    this.scene.add(ribbon(densify(graph.routes.hill as [number, number][], 60), 90, 26, roadMatH));
    const riverMat = new THREE.MeshBasicMaterial({ color: COLORS.river, transparent: true, opacity: 0.9, side: THREE.DoubleSide });
    this.scene.add(ribbon(densify(this.RL.pts as [number, number][], 90), 150, 8, riverMat));

    // ---------------- place pins + labels ----------------
    this.labelHost = document.createElement("div");
    this.labelHost.style.cssText = "position:absolute;inset:0;pointer-events:none;overflow:hidden";
    host.appendChild(this.labelHost);
    Object.entries(named).forEach(([k, p]) => {
      const base = this.V3(p[0], p[1], 30);
      const pin = new THREE.Mesh(new THREE.CylinderGeometry(0.12, 0.12, 9, 6), new THREE.MeshBasicMaterial({ color: COLORS.pin }));
      pin.position.copy(base).add(new THREE.Vector3(0, 4.5, 0));
      this.scene.add(pin);
      const orb = new THREE.Mesh(new THREE.SphereGeometry(0.75, 12, 8), new THREE.MeshBasicMaterial({ color: COLORS.pin }));
      orb.position.copy(base).add(new THREE.Vector3(0, 9, 0));
      this.scene.add(orb);
      this.addLabel(k, () => this.V3(p[0], p[1], 700), "text-[10px] font-medium text-slate-200 bg-slate-950/70 border-slate-600/60");
    });

    // ---------------- traffic: instanced low-poly vehicles ----------------
    const geoFor = (parts: number[][][]) => {
      const gpos: number[] = [], gcol: number[] = [];
      parts.forEach((p) => {
        const g = new THREE.BoxGeometry(p[0][0], p[0][1], p[0][2]).toNonIndexed();
        g.translate(p[1][0], p[1][1], p[1][2]);
        const a = g.attributes.position.array as Float32Array;
        const c = new THREE.Color(p[2][0]);
        for (let i = 0; i < a.length; i++) gpos.push(a[i]);
        for (let i = 0; i < a.length / 3; i++) gcol.push(c.r, c.g, c.b);
        g.dispose();
      });
      const g = new THREE.BufferGeometry();
      g.setAttribute("position", new THREE.Float32BufferAttribute(gpos, 3));
      g.setAttribute("color", new THREE.Float32BufferAttribute(gcol, 3));
      g.computeVertexNormals();
      return g;
    };
    const geos = [
      geoFor([[[2.2, 0.62, 1.1], [0, 0.31, 0], [0xd7dde4]], [[1.15, 0.5, 1.0], [-0.15, 0.87, 0], [0x8b98ab]]]),
      geoFor([[[1.2, 0.38, 0.32], [0, 0.3, 0], [0xd7dde4]], [[0.34, 0.55, 0.3], [-0.1, 0.75, 0], [0x9aa6b5]]]),
      geoFor([[[4.2, 1.15, 1.25], [0, 0.58, 0], [0xd7dde4]], [[4.22, 0.32, 1.27], [0, 0.82, 0], [0x8b98ab]]]),
      geoFor([[[1.1, 1.0, 1.15], [1.3, 0.5, 0], [0xd7dde4]], [[2.6, 1.25, 1.2], [-0.55, 0.63, 0], [0xaeb9c6]]]),
    ];
    this.vehMeshes = geos.map((g) => {
      const m = new THREE.InstancedMesh(g, new THREE.MeshBasicMaterial({ vertexColors: true }), 700);
      m.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
      m.frustumCulled = false;
      for (let i = 0; i < 700; i++) {
        this.dummy.position.set(0, -999, 0);
        this.dummy.scale.setScalar(0);
        this.dummy.updateMatrix();
        m.setMatrixAt(i, this.dummy.matrix);
      }
      this.scene.add(m);
      return m;
    });

    // ---------------- ambulance ----------------
    const body = new THREE.Mesh(new THREE.BoxGeometry(3.6, 1.6, 1.8), new THREE.MeshBasicMaterial({ color: COLORS.ambBody }));
    body.position.y = 0.8;
    this.amb.add(body);
    const stripe = new THREE.Mesh(new THREE.BoxGeometry(3.64, 0.35, 1.84), new THREE.MeshBasicMaterial({ color: COLORS.ambStripe }));
    stripe.position.y = 0.8;
    this.amb.add(stripe);
    const bcnR = new THREE.Mesh(new THREE.SphereGeometry(0.4, 10, 8), new THREE.MeshBasicMaterial({ color: 0xd64541 }));
    bcnR.position.set(0.4, 1.85, 0.42);
    this.amb.add(bcnR);
    const bcnB = new THREE.Mesh(new THREE.SphereGeometry(0.4, 10, 8), new THREE.MeshBasicMaterial({ color: 0x5a7ea6 }));
    bcnB.position.set(0.4, 1.85, -0.42);
    this.amb.add(bcnB);
    this.amb.scale.setScalar(1.35);
    this.amb.visible = false;
    this.scene.add(this.amb);
    const trailMat = new THREE.LineBasicMaterial({ color: COLORS.trail, transparent: true, opacity: 0.85 });
    this.scene.add(new THREE.Line(this.trailGeo, trailMat));
    this.addLabel("Ambulance", () => (this.amb.visible ? this.amb.position.clone().add(new THREE.Vector3(0, 6, 0)) : null), "text-[10px] font-semibold text-red-300 bg-slate-950/75 border-red-500/40");

    // default view
    this.camera.position.set(0, 210, 260);
    this.controls.target.set(0, 20, 0);
    this.loop();
  }

  addLabel(text: string, get: () => THREE.Vector3 | null, cls?: string) {
    const el = document.createElement("div");
    el.className = `absolute whitespace-nowrap rounded-sm border px-1.5 py-px will-change-transform ${cls || ""}`;
    el.textContent = text;
    el.style.display = "none";
    this.labelHost.appendChild(el);
    this.labels.push({ el, get });
  }

  // ---------------- trace handling ----------------
  setTrace(tr: CorridorResult | null) {
    if (this.traceGroups) {
      this.scene.remove(this.traceGroups);
      this.traceGroups.traverse((o) => {
        const m = o as THREE.Mesh;
        if (m.geometry) m.geometry.dispose();
        const mat = m.material as THREE.Material | THREE.Material[];
        if (Array.isArray(mat)) mat.forEach((x) => x.dispose());
        else if (mat) mat.dispose();
      });
      this.traceGroups = null;
    }
    this.fleetObjs = [];
    this.rsuHeads = [];
    this.trace = tr;
    this.prepared = tr ? prep(tr) : null;
    this.clockT = this.prepared ? this.prepared.tStart : 0;
    if (!tr || !this.prepared) return;

    const g = new THREE.Group();
    this.traceGroups = g;
    this.scene.add(g);

    // RSUs
    const mastGeo = new THREE.CylinderGeometry(0.14, 0.22, 3.6, 6);
    const headGeo = new THREE.SphereGeometry(0.55, 10, 8);
    const ringGeo = new THREE.RingGeometry(0.95, 1, 64);
    const R = tr.config.params.rsu_range_m / 100;
    tr.rsu.xy.forEach((p, i) => {
      const grp = new THREE.Group();
      grp.position.copy(this.V3(p[0], p[1], 15));
      const mast = new THREE.Mesh(mastGeo, new THREE.MeshLambertMaterial({ color: 0x8b95a3 }));
      mast.position.y = 1.8;
      grp.add(mast);
      const alive = !!tr.rsu.alive[i];
      const head = new THREE.Mesh(headGeo, new THREE.MeshBasicMaterial({ color: alive ? COLORS.rsu : COLORS.rsuDead }));
      head.position.y = 3.7;
      grp.add(head);
      const ring = new THREE.Mesh(ringGeo, new THREE.MeshBasicMaterial({ color: alive ? COLORS.rsu : COLORS.rsuDead, transparent: true, opacity: 0.3, side: THREE.DoubleSide, depthWrite: false }));
      ring.rotation.x = -Math.PI / 2;
      ring.position.y = 0.6;
      ring.scale.setScalar(R);
      grp.add(ring);
      g.add(grp);
      this.rsuHeads.push({ head, ring, alive });
    });

    // hazard: blocked road marker
    const [a, b2] = tr.hazard_edge;
    const m = tr.hazard_mid;
    const tl = Math.hypot(b2[0] - a[0], b2[1] - a[1]) || 1;
    const ux = (b2[0] - a[0]) / tl, uy = (b2[1] - a[1]) / tl;
    const block = new THREE.Mesh(new THREE.BoxGeometry(1.6, 1.4, 3.6), new THREE.MeshBasicMaterial({ color: COLORS.hazard }));
    block.position.copy(this.V3(m[0], m[1], 30));
    block.rotation.y = -Math.atan2(-uy, ux);
    g.add(block);
    const beam = new THREE.Mesh(new THREE.CylinderGeometry(0.25, 0.25, 60, 8, 1, true), new THREE.MeshBasicMaterial({ color: COLORS.hazard, transparent: true, opacity: 0.5, depthWrite: false }));
    beam.position.copy(this.V3(m[0], m[1], 30)).add(new THREE.Vector3(0, 30, 0));
    g.add(beam);

    // convoy members
    this.prepared.fleet.forEach((f) => {
      const grp = new THREE.Group();
      const col = f.key === "police" ? COLORS.fleet.police : f.key === "fire" ? COLORS.fleet.fire : COLORS.fleet.army;
      const len = f.key === "fire" ? 4.6 : f.key.startsWith("army") ? 4.1 : 2.6;
      const hgt = f.key === "fire" ? 1.55 : f.key.startsWith("army") ? 1.5 : 0.7;
      const bx = new THREE.Mesh(new THREE.BoxGeometry(len, hgt, 1.5), new THREE.MeshBasicMaterial({ color: col }));
      bx.position.y = hgt / 2;
      grp.add(bx);
      const cab = new THREE.Mesh(new THREE.BoxGeometry(len * 0.28, 0.5, 1.4), new THREE.MeshBasicMaterial({ color: 0xe8ecf1 }));
      cab.position.set(len * 0.3, hgt + 0.2, 0);
      grp.add(cab);
      grp.scale.setScalar(1.25);
      grp.visible = false;
      g.add(grp);
      this.fleetObjs.push({ key: f.key, label: f.label, dispatch: f.dispatch_s, group: grp });
      this.addLabel(f.label.split(",")[0], () => (grp.visible ? grp.position.clone().add(new THREE.Vector3(0, 5, 0)) : null), "text-[10px] text-slate-300 bg-slate-950/70 border-slate-600/50");
    });
  }

  countVisible() {
    return this.vehCounts.reduce((a, b) => a + b, 0) + (this.amb.visible ? 1 : 0);
  }

  setPlaying(p: boolean, speed: number) {
    this.playing = p;
    this.speed = speed;
  }
  seek(t: number) {
    if (!this.prepared) return;
    this.clockT = clamp(t, this.prepared.tStart, this.prepared.tEnd);
    this.lastFrameAt = performance.now();
    this.renderTrace(this.clockT);
  }
  getTime() {
    return this.clockT;
  }

  renderTrace(t: number) {
    const P = this.prepared;
    if (!P) return;
    const fi = (t - P.tStart) / P.frameDt;

    // civilians
    this.vehCounts = [0, 0, 0, 0];
    for (const tr of P.tracks) {
      const k = tr.type;
      if (this.vehCounts[k] >= 700) continue;
      const n = tr.xy.length / 2;
      if (fi < tr.f0 || fi > tr.f0 + n - 1) continue;
      const i = Math.floor(fi - tr.f0);
      const f = fi - tr.f0 - i;
      const x = lerp(tr.xy[i * 2], tr.xy[i * 2 + 2], f) * 10;
      const y = lerp(tr.xy[i * 2 + 1], tr.xy[i * 2 + 3], f) * 10;
      const dx = tr.xy[i * 2 + 2] - tr.xy[i * 2], dy = tr.xy[i * 2 + 3] - tr.xy[i * 2 + 1];
      const mesh = this.vehMeshes[k];
      const idx = this.vehCounts[k];
      const p3 = this.V3(x, y, 16);
      this.dummy.position.copy(p3);
      this.dummy.rotation.set(0, -Math.atan2(dy, dx) + Math.PI, 0);
      this.dummy.scale.setScalar(1.25);
      this.dummy.updateMatrix();
      mesh.setMatrixAt(idx, this.dummy.matrix);
      this.vehCounts[k]++;
    }
    this.vehMeshes.forEach((m, k) => {
      m.count = this.vehCounts[k];
      m.instanceMatrix.needsUpdate = true;
    });

    // ambulance + trail
    const A = ambAt(P.amb, t);
    if (A) {
      const p3 = this.V3(A.x, A.y, 20);
      this.amb.position.copy(p3);
      this.amb.rotation.y = -Math.atan2(A.dy, A.dx) + Math.PI;
      this.amb.visible = !A.s[9];
      const N = 42;
      const pts: THREE.Vector3[] = [];
      for (let j = Math.max(0, A.i ?? 0) - N; j <= Math.max(0, A.i ?? 0); j++) {
        const r = P.amb[Math.min(P.amb.length - 1, Math.max(0, j))];
        if (r) pts.push(this.V3(r[1] * 10, r[2] * 10, 18));
      }
      this.trailGeo.setFromPoints(pts);
    } else {
      this.amb.visible = false;
    }

    // convoy
    P.fleet.forEach((f, i) => {
      const o = this.fleetObjs[i];
      if (!o) return;
      const S = trackAt(f.track, t);
      if (!S || t < f.dispatch_s || S.f & 64) { o.group.visible = false; return; }
      const p3 = this.V3(S.x, S.y, 18);
      o.group.position.copy(p3);
      o.group.rotation.y = -Math.atan2(S.dy, S.dx) + Math.PI;
      o.group.visible = true;
    });
  }

  updateLabels() {
    const w = this.renderer.domElement.clientWidth, h = this.renderer.domElement.clientHeight;
    const v = new THREE.Vector3();
    for (const L of this.labels) {
      const p = L.get();
      if (!p) { L.el.style.display = "none"; continue; }
      v.copy(p).project(this.camera);
      const vis = v.z < 1 && v.z > -1 && Math.abs(v.x) < 1.05 && Math.abs(v.y) < 1.05;
      L.el.style.display = vis ? "block" : "none";
      if (vis)
        L.el.style.transform = `translate(${((v.x * 0.5 + 0.5) * w).toFixed(1)}px,${((-v.y * 0.5 + 0.5) * h).toFixed(1)}px) translate(-50%,-100%)`;
    }
  }

  resize() {
    const host = this.renderer.domElement.parentElement;
    if (!host) return;
    const w = host.clientWidth, h = host.clientHeight;
    if (w && h) {
      this.renderer.setSize(w, h);
      this.camera.aspect = w / h;
      this.camera.updateProjectionMatrix();
    }
  }

  loop = () => {
    this.raf = requestAnimationFrame(this.loop);
    try {
      const now = performance.now();
      const dt = Math.min(0.25, (now - this.lastFrameAt) / 1000 || 0);
      this.lastFrameAt = now;
      if (this.playing && this.prepared) {
        this.clockT += dt * this.speed;
        if (this.clockT >= this.prepared.tEnd) {
          this.clockT = this.prepared.tEnd;
          this.playing = false;
        }
        this.renderTrace(this.clockT);
        if (this.onTickThrottled && now - this.lastReport > 140) {
          this.lastReport = now;
          this.onTickThrottled(this.clockT, !this.playing, this.countVisible());
        }
      }
      this.controls.update();
      this.updateLabels();
      this.renderer.render(this.scene, this.camera);
    } catch (e) {
      console.error("[CorridorMap] frame error:", e);
    }
  };

  dispose() {
    cancelAnimationFrame(this.raf);
    this.controls.dispose();
    this.renderer.dispose();
    this.renderer.domElement.remove();
    this.labelHost?.remove();
  }
}
