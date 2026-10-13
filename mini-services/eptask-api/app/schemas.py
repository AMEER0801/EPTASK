"""app/schemas.py -- request validation. Tight bounds on everything the client
can send: this is the only surface the browser touches."""
from __future__ import annotations

from pydantic import BaseModel, Field, field_validator, model_validator


class CorridorRun(BaseModel):
    hazard: str = "landslide"
    info_mode: str = "V2V+RSU"
    footprint_m: float | None = Field(None, ge=500, le=30000)
    traffic_vph: float | None = Field(None, ge=5, le=120)
    hazard_seed: int = Field(7, ge=0, le=99999)
    candidate_index: int | None = Field(None, ge=0, le=100000)
    dispatch_s: float = Field(600, ge=60, le=3600)
    seed: int | None = Field(None, ge=0, le=999999)
    latency_arm: str | None = None
    convoy: bool = True
    trace: bool = True
    frame_dt: float = Field(60, ge=10, le=300)

    @field_validator("hazard")
    @classmethod
    def _hz(cls, v):
        if v not in ("earthquake", "landslide", "flood", "custom"):
            raise ValueError("hazard must be earthquake|landslide|flood|custom")
        return v

    @field_validator("info_mode")
    @classmethod
    def _mode(cls, v):
        if v not in ("NONE", "V2V", "RSU", "V2V+RSU"):
            raise ValueError("info_mode must be NONE|V2V|RSU|V2V+RSU")
        return v

    @model_validator(mode="after")
    def _custom_needs(self):
        if self.hazard == "custom" and self.footprint_m is None and self.candidate_index is None:
            raise ValueError("custom hazard needs footprint_m (and/or candidate_index)")
        return self


class CellEvent(BaseModel):
    at: int = Field(60, ge=1, le=2900)
    k: int = Field(3, ge=1, le=7)
    dur: int = Field(360, ge=30, le=2000)


class CellRun(BaseModel):
    policy: str = "B"
    version: int = 30
    V: int = Field(30, ge=4, le=60)
    seed: int = Field(21, ge=0, le=999999)
    ticks: int = Field(520, ge=20, le=3000)
    event: CellEvent = CellEvent()
    floor: bool = True
    explain: bool = True

    @field_validator("policy")
    @classmethod
    def _pol(cls, v):
        if v not in ("A", "B"):
            raise ValueError("policy must be A or B")
        return v

    @field_validator("version")
    @classmethod
    def _ver(cls, v):
        if v not in (10, 30, 50):
            raise ValueError("version must be 10, 30 or 50")
        return v

    @model_validator(mode="after")
    def _fits(self):
        if self.event.at + self.event.dur >= self.ticks:
            raise ValueError("event.at + event.dur must be < ticks")
        return self


class OutageRun(BaseModel):
    policies: list[str] = Field(default_factory=lambda: ["A", "B"])
    V: int = Field(30, ge=4, le=60)
    k_list: list[int] = Field(default_factory=lambda: [1, 2, 4])
    seeds: list[int] = Field(default_factory=lambda: [0, 1, 2])
    fail_at: int = Field(600, ge=50, le=4000)
    fail_dur: int = Field(300, ge=30, le=1500)
    post: int = Field(200, ge=20, le=1500)

    @field_validator("policies")
    @classmethod
    def _pols(cls, v):
        bad = [p for p in v if p not in ("A", "B", "alive_aware", "local")]
        if bad or not v:
            raise ValueError("policies must be a non-empty subset of A,B,alive_aware,local")
        return list(dict.fromkeys(v))[:4]

    @field_validator("k_list")
    @classmethod
    def _ks(cls, v):
        bad = [k for k in v if not 1 <= k <= 6]
        if bad or not v or len(v) > 4:
            raise ValueError("k_list must contain 1..4 values in 1..6")
        return sorted(set(v))

    @field_validator("seeds")
    @classmethod
    def _sds(cls, v):
        if not v or len(v) > 6:
            raise ValueError("seeds must contain 1..6 values")
        return v[:6]


class OsmBuild(BaseModel):
    """Rebuild the corridor graph from real OpenStreetMap data (or fall back)."""
    prefer_osm: bool = True
    refresh: bool = Field(False, description="re-fetch from Overpass even if a cache exists")


class CompareRun(BaseModel):
    """Side-by-side warning-network comparison: one hazard scenario, two
    information modes, everything else identical."""
    modes: list[str] = Field(default_factory=lambda: ["NONE", "V2V+RSU"])
    hazard: str = "landslide"
    footprint_m: float | None = Field(None, ge=500, le=30000)
    traffic_vph: float | None = Field(None, ge=5, le=120)
    hazard_seed: int = Field(7, ge=0, le=99999)
    candidate_index: int | None = Field(None, ge=0, le=100000)
    dispatch_s: float = Field(600, ge=60, le=3600)
    seed: int | None = Field(None, ge=0, le=999999)
    latency_arm: str | None = None
    trace: bool = True
    frame_dt: float = Field(60, ge=10, le=300)

    @field_validator("modes")
    @classmethod
    def _modes(cls, v):
        if len(v) != 2:
            raise ValueError("exactly two modes are required for a side-by-side comparison")
        bad = [m for m in v if m not in ("NONE", "V2V", "RSU", "V2V+RSU")]
        if bad:
            raise ValueError("modes must be chosen from NONE|V2V|RSU|V2V+RSU")
        return v

    @field_validator("hazard")
    @classmethod
    def _hz(cls, v):
        if v not in ("earthquake", "landslide", "flood", "custom"):
            raise ValueError("hazard must be earthquake|landslide|flood|custom")
        return v

    @model_validator(mode="after")
    def _custom_needs(self):
        if self.hazard == "custom" and self.footprint_m is None and self.candidate_index is None:
            raise ValueError("custom hazard needs footprint_m (and/or candidate_index)")
        return self
