import sys, os, re
tpl = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "template.html"), encoding="utf-8").read()
data = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "demo_data.json"), encoding="utf-8").read().replace("</", "<\\/")
assert tpl.count("__SCRIPTS__") == 1 and tpl.count("__DATA__") == 1
EX = ["shaders/CopyShader.js", "shaders/LuminosityHighPassShader.js", "postprocessing/EffectComposer.js",
      "postprocessing/RenderPass.js", "postprocessing/ShaderPass.js", "postprocessing/UnrealBloomPass.js"]
LOCAL = ["three.min.js"] + ["js/" + os.path.basename(p) for p in EX]
CDN = ["https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"] + \
      ["https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/" + p for p in EX]
def build(srcs, out):
    tags = "\n".join(f'<script src="{s}"></script>' for s in srcs)
    html = tpl.replace("__SCRIPTS__", tags).replace("__DATA__", data)
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    open(out, "w", encoding="utf-8").write(html)
    print(f"built {out}: {os.path.getsize(out)/1e6:.2f} MB")
build(LOCAL, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "index.html"))
build(CDN, sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "eptask_3d_demo.html"))
