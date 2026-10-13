"""Build the EPtask Ops Console - Laptop Setup & Operations Guide body PDF.

Chapter numbering plan (mandatory):
| Outline | Type    | Chapter | Title                                    |
|---------|---------|---------|------------------------------------------|
| 1       | cover   | -       | Cover (separate HTML/Playwright PDF)     |
| 2       | toc     | -       | Contents                                 |
| 3       | content | 1       | What you are installing                  |
| 4       | content | 2       | Prerequisites and system requirements    |
| 5       | content | 3       | Installing the simulation service        |
| 6       | content | 4       | Installing and building the console      |
| 7       | content | 5       | A two-minute tour of the console         |
| 8       | content | 6       | Configuration reference                  |
| 9       | content | 7       | Offline behaviour and data sources       |
| 10      | content | 8       | Troubleshooting                          |
| 11      | content | 9       | Tests and measured performance           |
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
pdfmetrics.registerFont(TTFont("DejaVuMono", f"{FONT_DIR}/truetype/dejavu/DejaVuSansMono.ttf"))
registerFontFamily("NotoSerifSC", normal="NotoSerifSC", bold="NotoSerifSC-Bold")
registerFontFamily("FreeSerif", normal="FreeSerif", bold="FreeSerif-Bold",
                   italic="FreeSerif-Italic", boldItalic="FreeSerif-BoldItalic")
install_font_fallback()

# ---- cascade palette (pdf.py palette.cascade, minimal mode) ----
PAGE_BG = colors.HexColor("#f5f5f5")
CARD_BG = colors.HexColor("#e9e8e3")
TABLE_STRIPE = colors.HexColor("#f1f1ef")
HEADER_FILL = colors.HexColor("#524a30")
BORDER = colors.HexColor("#d3cdbc")
ACCENT = colors.HexColor("#8d7325")
TEXT_PRIMARY = colors.HexColor("#1e1d1b")
TEXT_MUTED = colors.HexColor("#88857e")
SEM_SUCCESS = colors.HexColor("#45835a")

MARGIN = 0.9 * inch
PAGE_W, PAGE_H = A4
AVAIL_W = PAGE_W - 2 * MARGIN

OUT = "/home/z/my-project/workspace/setup_guide_body.pdf"

# ---------------------------------------------------------------- styles
body = ParagraphStyle("Body", fontName="FreeSerif", fontSize=10.5, leading=16,
                      alignment=TA_JUSTIFY, textColor=TEXT_PRIMARY, spaceAfter=8)
h1 = ParagraphStyle("H1", fontName="FreeSerif", fontSize=19, leading=24,
                    textColor=HEADER_FILL, spaceBefore=18, spaceAfter=10)
h2 = ParagraphStyle("H2", fontName="FreeSerif", fontSize=13.5, leading=18,
                    textColor=HEADER_FILL, spaceBefore=12, spaceAfter=6)
cap = ParagraphStyle("Cap", fontName="FreeSerif", fontSize=9, leading=12,
                     alignment=TA_CENTER, textColor=TEXT_MUTED, spaceBefore=3, spaceAfter=6)
th = ParagraphStyle("TH", fontName="FreeSerif", fontSize=9.5, leading=12.5,
                    textColor=colors.white, alignment=TA_LEFT)
td_ = ParagraphStyle("TD", fontName="FreeSerif", fontSize=9.5, leading=12.5,
                     textColor=TEXT_PRIMARY, alignment=TA_LEFT)
td_mono = ParagraphStyle("TDm", fontName="DejaVuMono", fontSize=8.2, leading=11,
                         textColor=TEXT_PRIMARY, alignment=TA_LEFT)
cmd = ParagraphStyle("Cmd", fontName="DejaVuMono", fontSize=8.8, leading=13.5,
                     textColor=TEXT_PRIMARY, alignment=TA_LEFT)
cmd_cmt = ParagraphStyle("CmdC", fontName="DejaVuMono", fontSize=8.8, leading=13.5,
                         textColor=TEXT_MUTED, alignment=TA_LEFT)
toc_h = ParagraphStyle("TocH", fontName="FreeSerif", fontSize=19, leading=24,
                       textColor=HEADER_FILL, spaceAfter=14)

# ---------------------------------------------------------------- TOC machinery
from reportlab.platypus.tableofcontents import TableOfContents  # noqa: E402


class TocDocTemplate(SimpleDocTemplate):
    def afterFlowable(self, flowable):
        if hasattr(flowable, "bookmark_name"):
            level = flowable.bookmark_level
            text = flowable.bookmark_text
            display_page = max(1, self.page - 1)  # body pages display 1-based after the TOC page
            key = flowable.bookmark_key
            self.notify("TOCEntry", (level, text, display_page, key))
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
        label = "i"
    else:
        label = str(doc.page - 1)
    canvas.drawCentredString(PAGE_W / 2, 0.5 * inch, label)
    canvas.setFont("FreeSerif-Italic", 8)
    canvas.drawRightString(PAGE_W - MARGIN, 0.5 * inch, "EPtask Ops Console - Setup and Operations Guide")
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


def code_block(lines, label=None):
    """A terminal block: light card, mono paragraphs, one line each."""
    rows = [[Paragraph(c, cmd_cmt if c.strip().startswith("#") else cmd)] for c in lines]
    t = Table(rows, colWidths=[AVAIL_W - 12], hAlign="CENTER")
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), CARD_BG),
        ("BOX", (0, 0), (-1, -1), 0.5, BORDER),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    out = [Spacer(1, 3), t]
    if label:
        out.append(Paragraph(label, cap))
    out.append(Spacer(1, 4))
    return out


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
    head("1. What you are installing"),
    Paragraph(
        "This guide installs the complete EPtask operations console on your own laptop: a "
        "professional Next.js frontend together with a FastAPI service that executes the original "
        "EPtask V7.1 research notebook code on every request. Nothing in the simulation pages is "
        "pre-computed or replayed - the corridor trials, the vehicular edge-computing cell and the "
        "paired outage studies all run live, with the notebook's own algorithms, parameters and "
        "trained policy exports. Two local processes are all that is required, and no cloud "
        "service, account or third-party key is involved at any point.", body),
]))
story.append(Paragraph(
    "The delivery is version 2 of the console, which adds four upgrades over the first release. "
    "Real OpenStreetMap roads can now replace the notebook's schematic map: the service fetches "
    "drivable highways for the corridor from the Overpass API, caches the extract on disk and "
    "rebuilds the road graph through the notebook's own <b>build_corridor()</b> function, which "
    "keeps the real roads only when they are connected and a detour exists, and otherwise falls "
    "back to the schematic with the reason displayed. A new Compare panel lets you adjust a hazard "
    "preset - footprint, traffic intensity, blockage seed, dispatch time - and run two warning "
    "networks side by side, with two maps, informed-share curves and a per-metric delta computed "
    "from live executions. Run history is now persistent: every job, including its full result, is "
    "stored in a local SQLite database and survives restarts. Finally, an optional API-key "
    "authentication layer can lock the HTTP surface when the machine is shared.", body))
story.append(Spacer(1, 4))
story.extend(code_block([
    "browser (Chrome / Edge / Firefox)",
    "   |",
    "   v",
    "frontend  Next.js 16 console          port 3000",
    "   |     Overview - Corridor 3D map - Compare networks",
    "   |     VEC cell - Outage study - Reference - About",
    "   |  HTTP, direct connection (CORS enabled)",
    "   v",
    "backend   FastAPI + onnxruntime       port 8100",
    "      core/      original eptask notebook modules (unmodified)",
    "      assets/    graph, ONNX models, reference results, OSM extract",
    "      app/       services, jobs + SQLite history, auth, OSM fetch",
]))

# ================================================================ 2
story.append(CondPageBreak(PAGE_H * 0.25))
story.extend(safe_keep([
    head("2. Prerequisites and system requirements"),
    Paragraph(
        "The console is a plain desktop application stack: Python for the simulation service and "
        "Node.js for the frontend build. There is no database server to install - the v2 job "
        "history uses the SQLite library built into Python - and no container runtime. The list "
        "below is deliberately conservative; if your machine runs a modern browser comfortably it "
        "will run the console.", body),
]))
story.append(Spacer(1, 4))
t = make_table(
    ["Requirement", "Minimum", "Notes"],
    [
        ["Operating system", "Windows 10/11, macOS 12+, Linux", "anything that runs Python and Node"],
        ["Python", "3.10 - 3.12 (3.12 recommended)", "on Windows, tick Add python.exe to PATH in the installer"],
        ["Node.js", "20 LTS or newer", "npm is included; bun 1.1+ also works"],
        ["Disk space", "about 5 GB", "the PyTorch CPU wheel is roughly 900 MB unpacked"],
        ["Memory", "8 GB recommended", "the OSM road-graph build peaks around 2 - 3 GB"],
        ["Internet", "first install and live OSM fetching only", "simulations run fully offline"],
    ],
    widths=[95, 150, 245])
story.extend(safe_keep([t, Paragraph("Table 1. Prerequisites. The app itself runs offline after installation.", cap)]))

# ================================================================ 3
story.append(CondPageBreak(PAGE_H * 0.25))
story.extend(safe_keep([
    head("3. Installing the simulation service"),
    Paragraph(
        "Unzip the delivery to a folder without spaces in its path, for example "
        "<b>C:\\EPtask</b> on Windows or <b>~/eptask</b> on macOS and Linux. Open a terminal in "
        "<b>mini-services/eptask-api</b> - that folder is the backend. Create a virtual "
        "environment so the notebook's dependencies stay isolated from your system Python, then "
        "install them. The install downloads PyTorch (CPU build), onnxruntime, FastAPI, networkx "
        "and a few smaller packages; on a normal connection this takes five to ten minutes, most "
        "of it PyTorch.", body),
]))
story.extend(code_block([
    "# macOS / Linux",
    "cd mini-services/eptask-api",
    "python3 -m venv .venv",
    "source .venv/bin/activate",
    "pip install -r requirements.txt",
    "",
    "# start the service",
    "bash run.sh",
]))
story.extend(code_block([
    "# Windows PowerShell",
    "cd mini-services\\eptask-api",
    "python -m venv .venv",
    ".venv\\Scripts\\Activate.ps1",
    "pip install -r requirements.txt",
    "",
    "# start the service",
    "python -m uvicorn main:app --host 0.0.0.0 --port 8100",
], "Terminal 1 - the simulation service on port 8100."))
story.append(Paragraph(
    "Wait for the line <b>Application startup complete.</b> - the service loads the notebook's "
    "graph, latency samples, reference results and model exports in one to two seconds. If "
    "Windows refuses to activate the virtual environment because script execution is disabled, "
    "run <b>Set-ExecutionPolicy -Scope CurrentUser RemoteSigned</b> once and retry; this is a "
    "PowerShell default, not a problem with the app. If the PyTorch download stalls, install it "
    "separately from the CPU wheel index (<b>pip install torch --index-url "
    "https://download.pytorch.org/whl/cpu</b>) and re-run the requirements install, which will "
    "then finish in seconds.", body))
story.append(Paragraph(
    "Verify the service before moving on. Opening <b>http://localhost:8100/health</b> in a "
    "browser should return a JSON object with <b>\"status\": \"ok\"</b>, the loaded graph size "
    "and the cached model list; <b>http://localhost:8100/docs</b> shows the interactive API "
    "documentation generated from the same code that serves the console. Leave this terminal "
    "running - the backend must stay up while you use the console.", body))

# ================================================================ 4
story.append(CondPageBreak(PAGE_H * 0.25))
story.extend(safe_keep([
    head("4. Installing and building the console"),
    Paragraph(
        "Open a second terminal in the project root - the folder that contains "
        "<b>package.json</b>. The frontend is a standard Next.js application: install its "
        "dependencies, produce the production build, and start it. The shipped <b>.env.local</b> "
        "already points the browser at <b>http://localhost:8100</b>, so no configuration is "
        "needed on a laptop.", body),
]))
story.extend(code_block([
    "# from the project root",
    "npm install        # 2 - 4 minutes",
    "npm run build      # production build (recommended)",
    "npm run start      # serves the console on http://localhost:3000",
    "",
    "# ...or, for development with hot reload:",
    "npm run dev",
], "Terminal 2 - the operations console on port 3000."))
story.append(Paragraph(
    "Open <b>http://localhost:3000</b> in any modern browser. Within a few seconds the header "
    "should show <b>simulation service online</b> with a green indicator; if it instead reports "
    "the service as unreachable, the backend from section 3 is not running, or the frontend was "
    "built before the <b>.env.local</b> file existed - start the backend and rebuild. The first "
    "page load after a fresh build is slower while the browser downloads the JavaScript bundles; "
    "subsequent navigation is immediate.", body))
story.append(Paragraph(
    "To stop the application, press Ctrl+C in each terminal. The SQLite run history, the OSM "
    "road cache and the logs all survive; the next start picks up exactly where you left off.",
    body))

# ================================================================ 5
story.append(CondPageBreak(PAGE_H * 0.25))
story.extend(safe_keep([
    head("5. A two-minute tour of the console"),
    Paragraph(
        "The console is organised into seven sections, each tied to a specific part of the "
        "notebook. The tour below follows the natural workflow: inspect the system, run the "
        "road-scale scenario, compare warning networks, then drill into the micro-scale cell and "
        "the outage study.", body),
]))
story.append(Spacer(1, 4))
t = make_table(
    ["Tab", "What it does", "What to try first"],
    [
        ["Overview", "provenance, service health, model registry, live-vs-static map",
         "check the health panel and the run identifier"],
        ["Corridor - N1", "3D map; runs corridor.run_trial live for the ambulance and convoy",
         "press Run simulation; then Load real OSM roads and run again on real roads"],
        ["Compare networks", "hazard preset editor + two warning modes side by side",
         "None vs V2V+RSU on Landslide; then tune the footprint slider and rerun"],
        ["VEC cell", "558 m micro-scale cell driven by the shipped ONNX policies",
         "launch model B v30 with the default outage event; open a decision explanation"],
        ["Outage study", "paired C3 study: any policies, outage sizes and seeds, live",
         "run the default A vs B study and compare with the notebook's recorded table"],
        ["Reference", "recorded artifacts from the notebook run, clearly labeled",
         "browse the recorded corridor analysis and figures"],
        ["About", "architecture, fidelity evidence and honest limitations",
         "read the v2 list and the limitations before relying on numbers"],
    ],
    widths=[80, 190, 220])
story.extend(safe_keep([t, Paragraph("Table 2. The seven console sections and a first exercise for each.", cap)]))
story.append(Paragraph(
    "Two behaviours are worth knowing about before you explore. First, simulations are queued on "
    "a two-worker pool: you can always launch a second study while one runs, and the progress "
    "bar names the real work in flight (per convoy member, per tick, per rollout) rather than "
    "pretending. Second, on the Corridor tab the <b>Road network source</b> card always tells "
    "you which road graph is live and why: after loading real OSM roads it shows the graph size, "
    "the reason the notebook's checks accepted it, and how far each named place had to be "
    "snapped to the nearest mapped road - distances that are themselves an honest quality "
    "measure of the data.", body))

# ================================================================ 6
story.append(CondPageBreak(PAGE_H * 0.25))
story.extend(safe_keep([
    head("6. Configuration reference"),
    Paragraph(
        "Everything is configured through environment variables; there are no config files to "
        "edit and no registry entries. Backend variables are read by the simulation service when "
        "it starts (the API key is re-read per request); frontend variables are baked in when the "
        "frontend is built, so after changing them run <b>npm run build</b> again. All of them "
        "are optional - the defaults are correct for a laptop.", body),
]))
story.append(Spacer(1, 4))
t = make_table(
    ["Variable", "Default", "Effect"],
    [
        ["EPTASK_PORT", "8100", "HTTP port of the simulation service"],
        ["EPTASK_API_KEY", "(unset)", "set it to require an API key on every /api call; clients send X-API-Key (or ?api_key= for images); the console shows a key gate"],
        ["EPTASK_DB", "data/jobs.db", "SQLite file for the persistent job history"],
        ["EPTASK_OSM_CACHE", "assets/osm_cache", "where Overpass extracts are cached"],
        ["EPTASK_LOG_LEVEL", "INFO", "DEBUG for verbose logs"],
        ["EPTASK_CORE / EPTASK_ASSETS", "bundled", "override the notebook modules / asset locations"],
        ["NEXT_PUBLIC_API_URL", "http://localhost:8100", "where the browser finds the API (frontend)"],
        ["NEXT_PUBLIC_GATEWAY_MODE", "(unset)", "leave unset on a laptop; sandbox deployments set 1"],
    ],
    widths=[130, 105, 255], mono_cols=(0,))
story.extend(safe_keep([t, Paragraph("Table 3. Environment variables. A commented .env.example ships with the zip.", cap)]))
story.append(Paragraph(
    "To enable authentication, export a long random string as <b>EPTASK_API_KEY</b> before "
    "starting the backend, then reload the console: a key gate appears, and the same key pasted "
    "once is stored in the browser and sent as the <b>X-API-Key</b> header on every request. "
    "The <b>/health</b> endpoint stays open without a key so that scripts and monitors can still "
    "check liveness. Wrong keys are rejected in constant time and logged with a request "
    "identifier - never the key itself. To disable authentication again, unset the variable and "
    "restart the service.", body))
story.extend(code_block([
    "# macOS / Linux - enable auth",
    "export EPTASK_API_KEY=\"a-long-random-string\"",
    "bash run.sh",
    "",
    "# Windows PowerShell - enable auth",
    "$env:EPTASK_API_KEY = \"a-long-random-string\"",
    "python -m uvicorn main:app --host 0.0.0.0 --port 8100",
]))

# ================================================================ 7
story.append(CondPageBreak(PAGE_H * 0.25))
story.extend(safe_keep([
    head("7. Offline behaviour and data sources"),
    Paragraph(
        "The console distinguishes three kinds of data, and the interface labels each one "
        "everywhere it appears. Live data is computed at request time: corridor trials, convoy "
        "behaviour, cell rollouts, outage studies and side-by-side comparisons. Static reference "
        "data is the notebook run's own recorded bundle - the results tables and figures in the "
        "Reference tab - served as-is and never presented as a live result. Assumptions "
        "inherited from the sources (hazard footprints, dispatch times, road speeds, fixed radio "
        "ranges) are declared in code and in the About panel.", body),
]))
story.append(Paragraph(
    "Real OpenStreetMap roads are live but network-dependent, and the delivery is prepared for "
    "both cases. A 17 MB Overpass extract of the corridor ships inside the zip, so the "
    "<b>Load real OSM roads</b> button works offline on first use; <b>Re-fetch</b> downloads "
    "fresh map data through four public Overpass mirrors and needs internet access. When every "
    "mirror is unreachable, the service keeps the current graph and reports the exact fetch "
    "errors in the source card - it never silently substitutes the schematic. The cached extract "
    "and the bundled one keep the OSM mode usable on a permanently offline machine. NASA COOLR "
    "landslide points remain the bundled sample because the live dataset requires an Earthdata "
    "login that a laptop deployment does not have; the console labels them accordingly.", body))

# ================================================================ 8
story.append(CondPageBreak(PAGE_H * 0.25))
story.extend(safe_keep([
    head("8. Troubleshooting"),
    Paragraph(
        "Most problems below are environmental rather than defects, and each has a one-line "
        "diagnosis. The backend log (the first terminal) and the browser console are the two "
        "places to look when the table does not cover a case; both produce structured, "
        "actionable messages by design.", body),
]))
story.append(Spacer(1, 4))
t = make_table(
    ["Symptom", "Cause and fix"],
    [
        ["Header says simulation service unreachable",
         "backend not running, or frontend built before .env.local existed; start the backend and rebuild"],
        ["pip install torch is slow or fails",
         "use the CPU wheel: pip install torch --index-url https://download.pytorch.org/whl/cpu, then reinstall requirements"],
        ["Port 8100 or 3000 already in use",
         "change the port (EPTASK_PORT, and NEXT_PUBLIC_API_URL in .env.local, then rebuild) or free the port"],
        ["Windows blocks venv activation",
         "Set-ExecutionPolicy -Scope CurrentUser RemoteSigned, then retry"],
        ["Firewall prompt on first start",
         "allow on private networks; for a strictly local machine start uvicorn with --host 127.0.0.1"],
        ["3D map is empty or grey",
         "WebGL2 unavailable; tables and charts stay usable - enable hardware acceleration or use Chrome/Edge/Firefox"],
        ["OSM fetch reports mirror failures",
         "network blocks Overpass; the bundled extract is used automatically, retry Re-fetch later"],
        ["First OSM load takes 20 - 60 s",
         "normal: about 160 k nodes are built and analysed once; runs on OSM roads then take 3 - 8 s per trial"],
        ["Auth gate loops",
         "the key in the browser must match EPTASK_API_KEY exactly; clear it (Cancel) and re-enter, or unset the variable"],
        ["History disappeared",
         "data/jobs.db was deleted; history resets, everything else is unaffected"],
    ],
    widths=[150, 340])
story.extend(safe_keep([t, Paragraph("Table 4. Environmental issues and their one-line fixes.", cap)]))

# ================================================================ 9
story.append(CondPageBreak(PAGE_H * 0.25))
story.extend(safe_keep([
    head("9. Tests and measured performance"),
    Paragraph(
        "The delivery includes a 55-case pytest suite that you can - and should - run on your "
        "machine after installing the backend. It covers asset integrity, the HTTP surface, "
        "deterministic reproduction of the notebook's recorded traces (byte-identical ambulance "
        "and civilian tracks across all twelve corridor presets, and the full 520-tick cell "
        "trace), input validation, the v2 upgrades specifically (authentication, persistence "
        "across restart, side-by-side comparison, OSM ingestion and offline fallback), and the "
        "end-to-end primary workflow.", body),
]))
story.extend(code_block([
    "cd mini-services/eptask-api",
    "python -m pytest tests/ -q     # 55 tests, about 3 minutes",
], "Expected result: 55 passed."))
story.append(Spacer(1, 4))
t = make_table(
    ["Operation", "Typical wall time"],
    [
        ["Backend startup (asset load)", "1 - 2 s"],
        ["Corridor run, schematic roads, no convoy", "1 - 2 s"],
        ["Corridor run, schematic roads, with convoy (7 trials)", "8 - 14 s"],
        ["Corridor run on real OSM roads, with convoy", "40 - 70 s"],
        ["Side-by-side comparison (2 live runs, no convoy)", "4 - 8 s"],
        ["VEC cell, 520 ticks", "1 - 2 s"],
        ["Paired outage study (2 policies x 3 sizes x 3 seeds)", "6 - 10 s"],
        ["OSM graph rebuild from the bundled cache", "15 - 30 s"],
        ["OSM graph rebuild with a fresh Overpass fetch", "+ 10 - 60 s network time"],
    ],
    widths=[280, 160])
story.extend(safe_keep([t, Paragraph("Table 5. Measured on 4 vCPU; scale roughly with core count for the convoy studies.", cap)]))
story.append(Paragraph(
    "Two simulations may run concurrently; further requests queue and the UI shows the real "
    "stage of the work. If a laptop has less than 8 GB of RAM, prefer the schematic roads for "
    "convoy-sized studies - the OSM graph build is the only step with a multi-gigabyte peak, and "
    "its result stays cached in memory afterwards. When a run contradicts your intuition, that "
    "is the console doing its job: every number comes from the notebook's own code, on the road "
    "network you chose, and the Reference tab is always there to separate a recorded artifact "
    "from a live result.", body))

# ---------------------------------------------------------------- build
doc = TocDocTemplate(OUT, pagesize=A4, leftMargin=MARGIN, rightMargin=MARGIN,
                     topMargin=0.85 * inch, bottomMargin=0.85 * inch,
                     title="EPtask Ops Console - Laptop Setup and Operations Guide",
                     author="Z.ai")
doc.multiBuild(story, onFirstPage=footer, onLaterPages=footer)
print("body built:", OUT)
