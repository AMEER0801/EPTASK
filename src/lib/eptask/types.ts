// API types mirroring the eptask-api service (mini-services/eptask-api).

export interface MetaInfo {
  run: { run_id: string; mode: string; started: string; python: string; seed: number; device: string; data_mode: string; code_digest: string };
  budget: { ep_A: number; ep_B: number; seeds: number[]; corridor_trials: number };
  data: { mode: string; places: Record<string, { lat: number; lon: number; km?: number }>; n_coolr: number };
  corridor_graph: Record<string, unknown> & { ok?: boolean; open_km?: number; open_min?: number; n_nodes?: number; n_edges?: number; junction_name?: string; chosen?: string; reason?: string };
  training: Record<string, Record<string, unknown>>;
  checks: { onnx_vs_torch_disagreements_of_500?: number; v61_regression?: unknown[] };
  hazards: Record<string, { label: string; footprint_m: number; traffic_vph: number }>;
  fleet: { key: string; label: string; dispatch_s: number }[];
  latency_arms: string[];
  onnx_checks: number | null;
  figures: string[];
  service: ServiceCatalogue;
  osm?: OsmStatus;
  auth_required?: boolean;
  history?: { path?: string; jobs_stored?: number; size_bytes?: number; error?: string };
}

export interface ServiceCatalogue {
  graph_loaded: boolean;
  graph_nodes: number;
  graph_source: string;
  latency_arms: string[];
  reference_loaded: boolean;
  policies_cached: string[];
  onnx_exports: string[];
  uptime_s: number;
}

export interface OsmStatus {
  overpass_urls: string[];
  cache: { available: boolean; fetched_at?: string; url?: string; elements?: number; size_kb?: number };
  graph_source: string;
}

export interface GraphSourceInfo extends OsmStatus {
  analysis: Record<string, unknown>;
}

export interface OsmBuildRequest { prefer_osm: boolean; refresh: boolean }

export interface OsmBuildResult {
  prefer_osm: boolean; refresh: boolean; bbox: number[];
  fetch?: { ok: boolean; url?: string; elements?: number; ways?: number; seconds?: number; error?: string };
  chosen: "osm" | "synthetic";
  reason: string;
  osm_payload: "fetched" | "cache" | null;
  graph_source: string; nodes: number; edges: number;
  analysis: { ok?: boolean; open_km?: number; open_min?: number; n_candidates?: number;
    frac_with_detour?: number; detour_min?: number; junction_name?: string };
  named_snapped: Record<string, { node: number; snap_m: number }>;
}

export interface CompareRequest {
  modes: [string, string] | string[];
  hazard: string;
  footprint_m?: number | null;
  traffic_vph?: number | null;
  hazard_seed?: number;
  candidate_index?: number | null;
  dispatch_s?: number;
  seed?: number | null;
  latency_arm?: string | null;
  trace?: boolean;
  frame_dt?: number;
}

export interface CompareResult {
  config: {
    modes: string[]; hazard: string; hazard_label: string; hazard_seed: number;
    candidate_index: number | null; dispatch_s: number; seed: number;
    latency_arm: string; params: Record<string, number>; generator: string;
  };
  delta: Record<string, number | null>;
  runs: CorridorResult[];
  timing: { total_seconds: number };
}

export interface CorridorRequest {
  hazard: "earthquake" | "landslide" | "flood" | "custom";
  info_mode: "NONE" | "V2V" | "RSU" | "V2V+RSU";
  footprint_m?: number | null;
  traffic_vph?: number | null;
  hazard_seed?: number;
  dispatch_s?: number;
  seed?: number | null;
  latency_arm?: string | null;
  convoy: boolean;
  trace: boolean;
  frame_dt: number;
}

export interface CorridorSummary {
  arrival_min: number; oracle_min: number; extra_min: number; missed_junction: boolean;
  informed_min: number | null; saw_block: boolean; unreachable: boolean;
  service_wait_s: number; trapped: number; civilians: number;
  rsu_alive: number; rsu_verified_s: number | null;
}

export interface FleetMember {
  key: string; label: string; dispatch_s: number;
  track: number[][]; // [t, x/10, y/10, flags]
  summary: Record<string, number | boolean>;
}

export interface CorridorResult {
  config: {
    hazard: string; hazard_label: string; hazard_seed: number; candidate_index: number | null;
    info_mode: string; seed: number; latency_arm: string; convoy: boolean;
    params: Record<string, number>; generator: string;
  };
  hazard_edge: [number, number][]; hazard_mid: [number, number];
  rsu: { xy: [number, number][]; alive: number[] };
  summary: CorridorSummary;
  coverage: [number, number | null][];
  fleet: FleetMember[];
  frame_dt: number; t0: number; n_frames: number; frame_t: number[];
  veh: number[][]; amb: number[][];
  rsu_t?: number | null;
  timing: { sim_seconds: number; total_seconds: number };
}

export interface CellRequest {
  policy: "A" | "B"; version: number; V: number; seed: number; ticks: number;
  event: { at: number; k: number; dur: number };
  floor: boolean; explain: boolean;
}

export interface CellTick {
  t: number; x: number[]; alive: number[]; i: number; n: number; role: number;
  key: string; prot: number; cwp: number; tier: number; ppl: number; est: number;
  mod: string; edge_ok: number;
  p?: number[][]; a?: number[]; real?: number[]; lvl?: number[]; s?: number; sev?: number;
  cf?: number[]; cfi?: number[]; kx?: number;
  T: number; D: number; Tt?: number; ok?: number;
}

export interface CellResult {
  config: {
    L: number; V: number; S: number; d_max: number; edge_x: number[]; tav: number[];
    dir: number[]; emergency: number[];
    event: { at: number; s0: number; k: number; dur: number };
    seed: number; onnx: string; policy: string;
    deadline_mult: Record<string, number>; floor_level: number;
    cwp_thresholds: number[]; modalities: string[];
    counts: { detections: number; emergency: number; settled: number };
    generator: string;
  };
  ticks: CellTick[];
  summary: {
    settled: number; pending: number;
    all: Block; outage: Block; emergency: Block; emergency_outage: Block; protected: Block;
    targets: { edge: number; v2v: number; local: number; cloud: number };
  };
  timing: { sim_seconds: number; total_seconds: number };
}

export interface Block { n: number; mean_T: number | null; miss_pct: number | null }

export interface OutageRequest {
  policies: string[]; V: number; k_list: number[]; seeds: number[];
  fail_at: number; fail_dur: number; post: number;
}

export interface OutageRow {
  k: number; policy: string; spec: string;
  during_pct: [number, number, number]; post_pct: [number, number, number];
  T_outage: [number, number, number]; T_control: [number, number, number];
  raw: { during: number[]; post: number[]; T_outage: number[]; T_control: number[] };
}

export interface OutageResult {
  config: { V: number; k_list: number[]; seeds: number[]; fail_at: number; fail_dur: number; post: number; steps: number; policies: string[]; generator: string };
  rows: Record<string, OutageRow>;
  order: string[];
  timing: { total_seconds: number };
}

export type JobStatus = "queued" | "running" | "done" | "error";

export interface Job<T = unknown> {
  id: string; kind: string; params: unknown; status: JobStatus;
  progress: number; stage: string; result: T | null;
  error: string | null; trace?: string;
  created: number; started: number | null; finished: number | null;
}

export interface JobListEntry {
  id: string; kind: string; status: JobStatus; progress: number; stage: string;
  created: number; started: number | null; finished: number | null;
  params: unknown;
}

export interface GraphData {
  source: string;
  nodes: [number, number, number, string][];
  edges: [number, number, string][];
  origin: number; dest: number; junction: number;
  named: Record<string, number>;
  routes: { access: [number, number][]; valley: [number, number][]; hill: [number, number][] };
  bbox: [number, number, number, number];
  coolr: [number, number][];
  places: Record<string, { lat: number; lon: number }>;
  cands: [number, number][];
}
