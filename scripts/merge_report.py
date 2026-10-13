"""Merge cover + body into the final report PDF, normalising page sizes to A4."""
from pypdf import PdfReader, PdfWriter

A4_W, A4_H = 595.28, 841.89
COVER = "/home/z/my-project/workspace/report_cover.pdf"
BODY = "/home/z/my-project/workspace/report_body.pdf"
OUT = "/home/z/my-project/download/EPtask_Integration_Report.pdf"

writer = PdfWriter()
writer.append(COVER)
writer.append(BODY)          # append() preserves link annotations + outline tree
for page in writer.pages:
    w, h = float(page.mediabox.width), float(page.mediabox.height)
    if abs(w - A4_W) > 0.1 or abs(h - A4_H) > 0.1:
        page.scale_to(A4_W, A4_H)
writer.add_metadata({
    "/Title": "EPtask Operations Console - Architecture and Integration Report",
    "/Author": "Z.ai",
    "/Creator": "Z.ai",
    "/Subject": "Integration of demo.zip and Notebook.zip into a live application",
})
with open(OUT, "wb") as f:
    writer.write(f)

r = PdfReader(OUT)
print("merged:", OUT, "pages:", len(r.pages),
      "outline entries:", len(r.outline) if r.outline else 0)
