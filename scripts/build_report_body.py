"""Build the EPtask integration report body PDF (ReportLab, no cover).

Chapter numbering plan (mandatory):
| Outline | Type    | Chapter | Title                                    |
|---------|---------|---------|------------------------------------------|
| 1       | cover   | -       | Cover (separate HTML/Playwright PDF)     |
| 2       | toc     | -       | Contents                                 |
| 3       | content | 1       | Executive summary                        |
| 4       | content | 2       | Sources and integration map              |
| 5       | content | 3       | System architecture                      |
| 6       | content | 4       | Fidelity evidence                        |
| 7       | content | 5       | Interface redesign                       |
| 8       | content | 6       | Verification and test results            |
| 9       | content | 7       | Measured performance                     |
| 10      | content | 8       | Limitations and remaining requirements   |
"""
import os
import sys

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase.pdfmetrics import registerFontFamily
from reportlab.platypus import (CondPageBreak, KeepTogether, PageBreak, Paragraph,
                                SimpleDocTemplate, Spacer, Table, TableStyle)

PDF_SKILL = "/home/z/my-project/skills/pdf"
sys.path.insert(0, os.path.join(PDF_SKILL, "scripts"))
from pdf import install_font_fallback  # noqa: E402

FONT_DIR = "/usr/share/fonts"
pdfmetrics.registerFont(TTFont("NotoSerifSC", f"{FONT_DIR}/truetype/noto-serif-sc/NotoSerifSC-Regular.ttf"))
pdfmetrics.registerFont(TTFont("NotoSerifSC-Bold", f"{FONT_DIR}/truetype/noto-serif-sc/NotoSerifSC-Bold.ttf"))
pdfmetrics.registerFont(TTFont("FreeSerif", f"{FONT_DIR}/truetype/freefont/FreeSerif.ttf"))
pdfmetrics.registerFont(TTFont("FreeSerif-Bold", f"{FONT_DIR}/truetype/freefont/FreeSerifBold.ttf"))
pdfmetrics.registerFont(TTFont("FreeSerif-Italic", f"{FONT_DIR}/truetype/freefont/FreeSerifItalic.ttf"))
pdfmetrics.registerFont(TTFont("FreeSerif-BoldItalic", f"{FONT_DIR}/truetype/freefont/FreeSerifBoldItalic.ttf"))
pdfmetrics.registerFont(TTFont("DejaVuSans", f"{FONT_DIR}/truetype/dejavu/DejaVuSansMono.ttf"))
registerFontFamily("NotoSerifSC", normal="NotoSerifSC", bold="NotoSerifSC-Bold")
registerFontFamily("FreeSerif", normal="FreeSerif", bold="FreeSerif-Bold",
                   italic="FreeSerif-Italic", boldItalic="FreeSerif-BoldItalic")
install_font_fallback()

# ---- cascade palette (design_engine palette-cascade --intent cold --mode minimal) ----
PAGE_BG = colors.HexColor("#eff0f1")
CARD_BG = colors.HexColor("#e6eaec")
TABLE_STRIPE = colors.HexColor("#e8ebed")
HEADER_FILL = colors.HexColor("#3b5664")
BORDER = colors.HexColor("#c5cdd1")
ACCENT = colors.HexColor("#1b6d97")
TEXT_PRIMARY = colors.HexColor("#1b1d1e")
TEXT_MUTED = colors.HexColor("#858b8e")
SEM_SUCCESS = colors.HexColor("#4f8662")

MARGIN = 0.9 * inch
PAGE_W, PAGE_H = A4
AVAIL_W = PAGE_W - 2 * MARGIN

OUT = "/home/z/my-project/workspace/report_body.pdf"

# ---------------------------------------------------------------- styles
body = ParagraphStyle("Body", fontName="FreeSerif", fontSize=10.5, leading=16,
                      alignment=TA_JUSTIFY, textColor=TEXT_PRIMARY, spaceAfter=8)
h1 = ParagraphStyle("H1", fontName="FreeSerif", fontSize=19, leading=24,
                    textColor=HEADER_FILL, spaceBefore=18, spaceAfter=10)
h2 = ParagraphStyle("H2", fontName="FreeSerif", fontSize=14, leading=19,
                    textColor=HEADER_FILL, spaceBefore=12, spaceAfter=6)
cap = ParagraphStyle("Cap", fontName="FreeSerif", fontSize=9, leading=12,
                     alignment=TA_CENTER, textColor=TEXT_MUTED, spaceBefore=3, spaceAfter=6)
th = ParagraphStyle("TH", fontName="FreeSerif", fontSize=9.5, leading=12.5,
                    textColor=colors.white, alignment=TA_LEFT)
td_ = ParagraphStyle("TD", fontName="FreeSerif", fontSize=9.5, leading=12.5,
                     textColor=TEXT_PRIMARY, alignment=TA_LEFT)
td_mono = ParagraphStyle("TDm", fontName="DejaVuSans", fontSize=8.2, leading=11,
                         textColor=TEXT_PRIMARY, alignment=TA_LEFT)
toc_h = ParagraphStyle("TocH", fontName="FreeSerif", fontSize=19, leading=24,
                       textColor=HEADER_FILL, spaceAfter=14)
quote = ParagraphStyle("Quote", fontName="FreeSerif-Italic", fontSize=10.5, leading=16,
                       leftIndent=24, textColor=TEXT_PRIMARY, spaceAfter=8,
                       borderPadding=(0, 0, 0, 8))

# ---------------------------------------------------------------- TOC machinery
from reportlab.platypus.tableofcontents import TableOfContents  # noqa: E402


class TocDocTemplate(SimpleDocTemplate):
    def afterFlowable(self, flowable):
        if hasattr(flowable, "bookmark_name"):
            level = flowable.bookmark_level
            text = flowable.bookmark_text
            display_page = max(1, self.page - 1)  # body pages display 1-based after the TOC page
            key = flowable.bookmark_key
            self.notify("TOCEntry", (level, text, display_page, key))  # 4-tuple -> clickable links
            self.canv.bookmarkPage(key)
            self.canv.addOutlineEntry(text, key, level=level, closed=False)


def head(text, level=0):
    key = f"h{level}-{abs(hash(text)) % 99999}"
    style = h1 if level == 0 else h2
    p = Paragraph(f'<a name="{key}"/><b>{text}</b>', style)
    p.bookmark_name = key
    p.bookmark_level = level
    p.bookmark_text = text
    p.bookmark_key = key
    return p


def footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("FreeSerif", 9)
    canvas.setFillColor(TEXT_MUTED)
    if doc.page == 1:
        label = "i"                      # front matter (contents page)
    else:
        label = str(doc.page - 1)        # body resets to arabic 1
    canvas.drawCentredString(PAGE_W / 2, 0.5 * inch, label)
    canvas.setFont("FreeSerif-Italic", 8)
    canvas.drawRightString(PAGE_W - MARGIN, 0.5 * inch, "EPtask Ops Console - Integration Report")
    canvas.restoreState()


MAX_KEEP = PAGE_H * 0.4


def safe_keep(elements):
    total = 0
    for el in elements:
        w, hgt = el.wrap(AVAIL_W, PAGE_H)
        total += hgt
    if total <= MAX_KEEP:
        return [KeepTogether(elements)]
    if len(elements) >= 2:
        return [KeepTogether(elements[:2])] + list(elements[2:])
    return list(elements)


def make_table(header, rows, widths, mono_cols=(), stripe_from=1):
    data = [[Paragraph(f"<b>{c}</b>", th) for c in header]]
    for r_i, row in enumerate(rows):
        cells = []
        for c_i, c in enumerate(row):
            st = td_mono if c_i in mono_cols else td_
            cells.append(Paragraph(str(c), st))
        data.append(cells)
    scale = min(1.0, AVAIL_W / sum(widths))
    widths = [w * scale for w in widths]
    t = Table(data, colWidths=widths, hAlign="CENTER", repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), HEADER_FILL),
        ("GRID", (0, 0), (-1, -1), 0.5, BORDER),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]
    for i in range(stripe_from, len(data)):
        if (i - stripe_from) % 2 == 1:
            style.append(("BACKGROUND", (0, i), (-1, i), TABLE_STRIPE))
    t.setStyle(TableStyle(style))
    return t


# ---------------------------------------------------------------- content
story = []

toc = TableOfContents()
toc.levelStyles = [
    ParagraphStyle("TOC1", fontName="FreeSerif", fontSize=11, leading=18, leftIndent=6, textColor=TEXT_PRIMARY),
    ParagraphStyle("TOC2", fontName="FreeSerif", fontSize=10, leading=15, leftIndent=22, textColor=TEXT_MUTED),
]
story.append(Paragraph("<b>Contents</b>", toc_h))
story.append(toc)
story.append(PageBreak())

# ================================================================ 1
story.extend(safe_keep([
    head("1. Executive summary"),
    Paragraph(
        "This report documents the transformation of two research artifacts - a static Three.js "
        "demonstration that replayed pre-recorded simulations, and the EPtask V7.1 executed notebook "
        "that produced those simulations - into a single live application. The delivered system is an "
        "operations console: a Next.js 16 frontend over a Python FastAPI service that executes the "
        "notebook's original modules on every request. Nothing visible on the simulation pages is "
        "pre-computed; each launched run is computed at request time, and the repository's tests prove "
        "that the live outputs are identical to the notebook's recorded ones.", body),
]))
story.append(Paragraph(
    "The integration preserves the demo's strongest asset - its 3D situation map of the Trishuli "
    "valley corridor - while removing its embedded 7.2 MB dataset, decorative bloom effects, and "
    "scripted story machinery. The notebook's strongest assets - the corridor co-simulation, the "
    "vehicular edge-computing (VEC) cell environment, the trained MEPPO policies, and the paired "
    "outage protocol - now serve live requests through their original, unmodified code. Where the "
    "original sources were assumptions or static artifacts, the new application keeps them static "
    "and says so in the interface.", body))
story.append(Paragraph(
    "All acceptance criteria from the integration brief were verified: the main workflow operates "
    "end to end in a real browser; notebook-derived outputs match the original implementation "
    "exactly; errors and missing dependencies are handled with actionable messages; and setup "
    "instructions allow another developer to reproduce the verified environment. The measured "
    "performance figures and the remaining limitations are reported honestly in sections 7 and 8.", body))

# ================================================================ 2
story.append(CondPageBreak(PAGE_H * 0.25))
story.extend(safe_keep([
    head("2. Sources and integration map"),
    Paragraph(
        "Both archives were inventoried before any change. The demo is a self-contained HTML/Three.js "
        "application whose data pipeline is documented by its own build tools: tools/make_traces.py "
        "converts a notebook results bundle into the replayable demo_data.json, and tools/build_demo.py "
        "inlines that JSON into the page. The notebook archive contains the v7.1 full run (16 Python "
        "modules, checkpoints, ONNX exports, results bundle) plus earlier v5.1/v6.1 notebooks and "
        "v7.2 real-data attempts.", body),
]))
story.append(Spacer(1, 6))
t = make_table(
    ["Demo element", "Old demo", "New application"],
    [
        ["3D situation map (terrain, routes, vehicles, RSUs, playback)",
         "embedded replay", "ported renderer, driven by live API traces; restrained operational restyle"],
        ["Corridor traces (12 presets)", "embedded demo_data.json",
         "corridor.run_trial executed per request; recorder verified against an unrecorded rerun"],
        ["Convoy behaviour", "embedded",
         "live; one trial per member with the same blockage, traffic seed and RSUs"],
        ["Cell tick replay (520 ticks)", "embedded",
         "VECEnv + OnnxPolicy live, with env.peek counterfactuals"],
        ["C3 outage table", "static table", "paired live study via policies.rollout"],
        ["results_v71.json numbers and figures", "mixed into panels",
         "served as explicitly labeled reference artifacts"],
    ],
    widths=[150, 110, 230])
story.extend(safe_keep([t, Paragraph("Table 1. Where each demo element comes from now.", cap)]))
story.append(Spacer(1, 6))
story.append(Paragraph(
    "The v7.1 line was selected as the integration source because the demo replayed exactly that "
    "run (20261008-124455-ba2667). The v7.2 real-data attempts could not be integrated: they require "
    "live internet access to OpenStreetMap and NASA COOLR, which the original environment itself "
    "could not reach - the notebook rejected its own fetched OSM extract for disconnected roads and "
    "documented the COOLR server returning 404. This is documented rather than papered over; the "
    "application keeps the notebook's schematic two-route graph through the real place positions.", body))

# ================================================================ 3
story.append(CondPageBreak(PAGE_H * 0.25))
story.extend(safe_keep([
    head("3. System architecture"),
    Paragraph(
        "The application separates presentation, orchestration and simulation. The Next.js console "
        "owns forms, tables, charts and the 3D map; the FastAPI service owns the notebook world - it "
        "imports the original modules from its core/ directory, loads the notebook's own bundle "
        "assets once at startup, and exposes a small, validated API. In the sandbox the two are "
        "joined by the platform gateway; in a plain deployment the frontend proxies to the service "
        "port directly. No database, queue or cloud service was added because no requirement "
        "justifies one.", body),
]))
story.append(Spacer(1, 6))
t = make_table(
    ["Layer", "Component", "Responsibility"],
    [
        ["Frontend", "Next.js 16 console (single route)",
         "launchers, playback, metrics, decision inspector, reference browser"],
        ["Gateway", "Caddy reverse proxy", "single external port; routes /api to the service by query parameter"],
        ["Service", "FastAPI (port 8100)", "validation, job queue, JSON serialisation, error mapping"],
        ["Simulation", "app/corridor_svc.py", "recorded corridor.run_trial runs + hook verification"],
        ["Simulation", "app/cell_svc.py", "VECEnv runs driven by shipped ONNX actors with explanations"],
        ["Simulation", "app/outage_svc.py", "paired outage studies via policies.rollout and runlog.mean_ci"],
        ["Assets", "core/ + assets/demo_bundle/", "the unmodified notebook modules and its recorded bundle"],
    ],
    widths=[70, 150, 270])
story.extend(safe_keep([t, Paragraph("Table 2. Service boundaries.", cap)]))
story.append(Spacer(1, 6))
story.append(Paragraph(
    "Requests that take longer than a moment are executed as jobs on a two-worker thread pool. The "
    "client submits, receives a job id, and polls; progress is reported by the simulation itself - "
    "per convoy member, per tick block, or per rollout - never fabricated. Job results are kept in "
    "a bounded in-memory registry (40 most recent) so the session's run history survives page "
    "navigation without introducing persistence the task does not need.", body))
story.append(Paragraph(
    "Every input is validated server-side with strict ranges: vehicle counts to 60, ticks to 3000, "
    "at most six paired seeds and four outage sizes per study, footprints between 500 and 30,000 m. "
    "No user input ever reaches a filesystem path; reference sections and figures are allow-listed. "
    "The service returns structured errors with actionable text and never exposes stack traces to "
    "the client.", body))

# ================================================================ 4
story.append(CondPageBreak(PAGE_H * 0.25))
story.extend(safe_keep([
    head("4. Fidelity evidence"),
    Paragraph(
        "The notebook's simulations are deterministic given a seed and parameters, which makes "
        "equivalence testable rather than aspirational. The original demo embedded traces produced by "
        "tools/make_traces.py from the notebook run; the live service re-executes the same code with "
        "the same inputs and the test suite compares the results field by field.", body),
]))
story.append(Spacer(1, 6))
t = make_table(
    ["Consistency check", "Scope", "Result"],
    [
        ["Corridor ambulance tracks", "12 preset traces (3 hazards x 4 warning modes)", "identical, all rows"],
        ["Corridor civilian tracks", "same 12 traces", "identical, all rows"],
        ["Corridor summaries", "arrival/oracle/extra/informed, flags", "equal within 1e-9"],
        ["Cell trace", "520 ticks, model B v30, V=30, seed 21", "identical, field-for-field"],
        ["Settled true times", "510 settled requests", "equal within 5e-4 s"],
        ["Determinism on repeat", "flood/RSU run twice, landslide repeat over HTTP", "identical summaries"],
        ["Recorder-hook neutrality", "every recorded run vs unrecorded rerun", "verified at request time; service refuses on mismatch"],
    ],
    widths=[130, 180, 180])
story.extend(safe_keep([t, Paragraph("Table 3. Output consistency against the notebook recording (scripts/test_consistency.py and tests/test_service.py).", cap)]))
story.append(Spacer(1, 6))
story.append(Paragraph(
    "Two fidelity mechanisms deserve mention. First, the recorder is the demo builder's own "
    "anchored-source-patch of corridor.run_trial; the service re-derives the patched function at "
    "startup, aborts if the anchor lines ever move, and re-runs each recorded trial unrecorded to "
    "prove the hook changes nothing before serving a trace. Second, policy decisions come from the "
    "shipped ONNX exports through the notebook's own OnnxPolicy wrapper; the notebook itself "
    "measured zero decision disagreements out of 500 between the exports and the torch checkpoints, "
    "so evaluating the exports is a documented, verified equivalence rather than a shortcut.", body))

# ================================================================ 5
story.append(CondPageBreak(PAGE_H * 0.25))
story.extend(safe_keep([
    head("5. Interface redesign"),
    Paragraph(
        "The demo's holographic aesthetic - bloom, aurora terrain, stars, neon grid, scripted damage "
        "animations and an eight-step story - was replaced by a restrained operational design: a "
        "graphite terrain with subtle contours and elevation shading, desaturated road colours, "
        "status colour reserved for meaning (green alive, red down, amber attention), tabular "
        "numerals, and clear empty and loading states. Animation survives only as meaningful "
        "feedback: playback of the returned trace, an ambulance trail showing the travelled route, "
        "and progress bars whose stages name the real simulation work in flight.", body),
]))
story.append(Paragraph(
    "The console is organised into six sections. Overview carries provenance, service health and the "
    "model registry. Corridor launches road-scale trials and plays the returned trace on the map "
    "with scrubber and speed controls, alongside metric cards, the convoy table and the coverage "
    "curve. VEC cell renders the 558-metre highway with its eight roadside units and two traffic "
    "lanes on a canvas strip, a per-tick timeline of completion times against deadlines, and a "
    "decision inspector showing the policy's probabilities and exact counterfactuals for the "
    "selected request. Outage study runs the paired protocol and tabulates mean plus 95% confidence "
    "intervals with the notebook's recorded table available for context. Reference browses the "
    "recorded artifacts and figures. About documents the integration inside the product itself.", body))
story.append(Paragraph(
    "Accessibility and responsiveness were addressed directly: semantic landmarks and aria labels on "
    "charts and controls, keyboard operation of the map (arrow keys seek), 44 px touch targets, and "
    "layouts that collapse from a seven-column launcher grid to stacked mobile forms. Without WebGL "
    "the map degrades to a notice while every table and chart remains functional; without the "
    "Python service the header reports it and each panel explains what is missing.", body))

# ================================================================ 6
story.append(CondPageBreak(PAGE_H * 0.25))
story.extend(safe_keep([
    head("6. Verification and test results"),
    Paragraph(
        "The backend suite (pytest, 40 tests) covers asset integrity, startup and health, unit "
        "behaviour of each service, validation and invalid-request handling, output consistency "
        "against the notebook recording, missing-file failure modes, repeated-request determinism and "
        "the end-to-end job workflow over HTTP. All 40 pass. The frontend was verified in a real "
        "browser: every section was opened, a corridor simulation, a cell run and a paired outage "
        "study were launched through the interface, results rendered from live API data, and "
        "desktop and mobile layouts were exercised. Issues found during that verification (a label "
        "getter bug that disabled the 3D map, a stale variable in the reference panel) were fixed "
        "and re-verified.", body),
]))
story.append(Spacer(1, 6))
t = make_table(
    ["Area", "Checks", "Outcome"],
    [
        ["Asset and dependency integrity", "core modules present; bundle files present; imports succeed", "pass"],
        ["Backend startup and health", "/health readiness; /api/meta provenance; /api/graph geometry", "pass"],
        ["Unit behaviour", "corridor service, cell service, outage service incl. baselines", "pass"],
        ["Validation and invalid requests", "422 with field-level messages; unknown job/section 404", "pass"],
        ["Output consistency vs notebook", "12 corridor traces + 520-tick cell trace + summaries", "pass (exact)"],
        ["Failure modes", "missing model export raises actionable FileNotFoundError", "pass"],
        ["Repeated requests", "deterministic repeat; job listing; LRU bound", "pass"],
        ["End-to-end over HTTP", "submit, poll, complete corridor job; results sane", "pass"],
        ["Frontend (browser)", "all six sections; three live runs; desktop + mobile viewports", "pass after fixes"],
    ],
    widths=[130, 210, 90])
story.extend(safe_keep([t, Paragraph("Table 4. Verification summary (mini-services/eptask-api/tests).", cap)]))
story.append(Spacer(1, 6))
story.append(Paragraph(
    "To reproduce: start the service (bash mini-services/eptask-api/run.sh), install its requirements, "
    "then run python3 -m pytest tests/ -v from mini-services/eptask-api. The consistency tests locate "
    "the original demo recording from the extracted demo.zip and can be pointed at any copy through "
    "the EPTASK_DEMO_DATA environment variable.", body))

# ================================================================ 7
story.append(CondPageBreak(PAGE_H * 0.25))
story.extend(safe_keep([
    head("7. Measured performance"),
    Paragraph(
        "Timings below were measured on the deployed sandbox (CPU-only, torch 2.14.1+cpu, the same "
        "build the notebook used). Startup loads the graph, reference bundle and latency arms in "
        "about two seconds; ONNX sessions load in about 20 ms each and are cached after first use, "
        "so repeated requests pay only simulation cost.", body),
]))
story.append(Spacer(1, 6))
t = make_table(
    ["Operation", "Measured", "Notes"],
    [
        ["Corridor run with convoy and trace", "8-14 s wall",
         "7 full 6-hour trials plus one unrecorded verification rerun per request"],
        ["Corridor run without convoy", "1-2 s", "ambulance trial + verification"],
        ["VEC cell, 520 ticks, explanations on", "0.6-2 s", "dominated by env.peek counterfactuals, as in the notebook"],
        ["Paired outage study, 2 policies x 3 sizes x 3 seeds", "6-10 s",
         "36 rollouts of 1101 steps; linear in policies x sizes x seeds"],
        ["Concurrent behaviour", "2 workers", "further jobs queue with honest 'queued' progress"],
        ["Frontend first render", "under 2 s", "trace payloads for one corridor run are 0.3-1 MB"],
    ],
    widths=[170, 90, 230])
story.extend(safe_keep([t, Paragraph("Table 5. Measured timings (sandbox, CPU).", cap)]))
story.append(Spacer(1, 6))
story.append(Paragraph(
    "No algorithm, parameter or preprocessing change was made for speed; the numbers above are the "
    "original notebook code's cost of doing real work per request. The dominant optimisations are "
    "architectural: models and assets load once, sessions are cached, and heavy runs are bounded by "
    "the worker pool instead of blocking the HTTP event loop.", body))

# ================================================================ 8
story.append(CondPageBreak(PAGE_H * 0.25))
story.extend(safe_keep([
    head("8. Limitations and remaining requirements"),
    Paragraph(
        "The corridor graph is the notebook's schematic two-route map through real place positions; "
        "live OpenStreetMap ingestion is not implemented, and the notebook's own v7.2 attempt "
        "documents why its fetched extract was rejected. Outage and cell studies evaluate the ONNX "
        "exports rather than the torch checkpoints - a verified equivalence (0/500 disagreements) "
        "rather than an identity. The micro-latency samples feeding corridor service delays are the "
        "recorded arms from the bundle, selectable per request; recomputing them live would double "
        "run times for identical numbers. Runs are kept in memory only; there is no authentication "
        "layer, which is proportionate to a research console but must be added before any exposure "
        "beyond a trusted network.", body),
]))
story.append(Paragraph(
    "Remaining setup for another developer is short: Python 3.12 with the requirements in "
    "mini-services/eptask-api/requirements.txt, Bun or Node 20 for the console, one environment "
    "variable for the service port if 8100 is unsuitable, and the two commands in the repository "
    "README. Browser verification covered headless Chromium (WebGL2) and standard desktop Chrome "
    "paths; Safari and Firefox were not exercised. Results inherit the sources' declared "
    "assumptions - schematic geometry, Poisson traffic, fixed radio ranges and the convoy's "
    "dispatch-time convention - and therefore support engineering comparison, not operational "
    "claims.", body))

# ---------------------------------------------------------------- build
doc = TocDocTemplate(OUT, pagesize=A4, leftMargin=MARGIN, rightMargin=MARGIN,
                     topMargin=0.85 * inch, bottomMargin=0.85 * inch,
                     title="EPtask Operations Console - Architecture and Integration Report",
                     author="Z.ai", creator="Z.ai",
                     subject="Integration of demo.zip and Notebook.zip into a live application")
doc.multiBuild(story, onFirstPage=footer, onLaterPages=footer)
print("body written:", OUT, os.path.getsize(OUT), "bytes")
