import json, re, glob, os, sys
D = "/home/claude/mma_v2/import_into_axiom_bench"
bad = []
def need(cond, msg):
    if not cond: bad.append(msg)
ap = json.load(open(f"{D}/anti_patterns.json", encoding="utf-8")); dna = json.load(open(f"{D}/project_dna.json", encoding="utf-8")); sk = json.load(open(f"{D}/skills.json", encoding="utf-8"))
need(ap["schema"] == "mini_axiom_mma.anti_patterns.v1" and list(ap) == ["schema", "anti_patterns"], "anti_patterns schema")
need(dna["schema"] == "mini_axiom_mma.project_dna.v1" and set(dna) == {"schema", "decision_tree", "meta_lessons"}, "project_dna schema")
need(sk["schema"] == "mini_axiom_mma.skills.v1" and list(sk) == ["schema", "skills"], "skills schema")
APK = ["id", "title", "domain", "trigger", "symptom", "root_cause", "wrong_fix", "correct_fix", "generalization", "evidence", "confidence"]
DNK = ["id", "situation", "options", "chosen", "why", "outcome", "leads_to"]
SKK = ["id", "name", "statement", "first_example", "second_example", "rule1_passed", "confidence"]
def check_conf(c, who):
    need(isinstance(c, dict) and set(c) == {"value", "basis"} and isinstance(c["value"], (int, float)) and 0 <= c["value"] <= 1 and str(c["basis"]).strip(), f"{who}: confidence")
ids = []
for a in ap["anti_patterns"]:
    need(list(a) == APK, f"{a.get('id')}: keys {list(a)}"); ids.append(a["id"]); check_conf(a["confidence"], a["id"])
    need(all(isinstance(a[k], str) and a[k].strip() for k in APK if k != "confidence"), f"{a['id']}: empty field")
    need(re.fullmatch(r"EPT-AP-\d{3}", a["id"]), f"{a['id']}: id pattern")
for d in dna["decision_tree"]:
    need(list(d) == DNK, f"{d.get('id')}: keys"); ids.append(d["id"]); need(isinstance(d["options"], list) and len(d["options"]) >= 2 and isinstance(d["leads_to"], list), f"{d['id']}: lists")
    need(all(isinstance(d[k], str) and d[k].strip() for k in ("situation", "chosen", "why", "outcome")), f"{d['id']}: empty")
dn_ids = {d["id"] for d in dna["decision_tree"]}
for d in dna["decision_tree"]:
    for t in d["leads_to"]: need(t in dn_ids, f"{d['id']}: leads_to {t} does not exist")     # (EPT-DN-014 -> 013 is a backward link inherited from the first pack; allowed)
    if d["id"] >= "EPT-DN-016":
        for t in d["leads_to"]: need(t > d["id"], f"{d['id']}: new fork links backward to {t}")
need(all(isinstance(m, str) and m.strip() for m in dna["meta_lessons"]) and len(set(dna["meta_lessons"])) == len(dna["meta_lessons"]), "meta_lessons")
for s in sk["skills"]:
    need(list(s) == SKK, f"{s.get('id')}: keys"); ids.append(s["id"]); check_conf(s["confidence"], s["id"])
    none2 = s["second_example"].strip().upper().startswith("NONE")
    need(isinstance(s["rule1_passed"], bool) and s["rule1_passed"] == (not none2), f"{s['id']}: Rule 1 flag vs second_example")
    need(all(s[k].strip() for k in ("name", "statement", "first_example", "second_example")), f"{s['id']}: empty")
need(len(ids) == len(set(ids)), "duplicate ids")
for fam in ("AP", "DN", "SK"):
    n = sorted(int(i.split("-")[2]) for i in ids if i.split("-")[1] == fam); need(n == list(range(1, len(n) + 1)), f"{fam}: ids not contiguous {n}")
# reflections: importer reads lines that START with Best:/Worst:/Surprise: (bold allowed)
rx = {k: re.compile(rf"^\**{k}:\**\s*(.+)$", re.M) for k in ("Best", "Worst", "Surprise")}
files = sorted(glob.glob(f"{D}/reflections/*.md")); need(len(files) == 5, f"reflection files {len(files)}")
for f in files:
    t = open(f, encoding="utf-8").read(); lines = [l for l in t.splitlines()]
    need(len(lines) == 3 and all(l.strip() for l in lines), f"{os.path.basename(f)}: not exactly 3 non-empty lines ({len(lines)})")
    for k, r in rx.items(): need(len(r.findall(t)) == 1, f"{os.path.basename(f)}: {k}: found {len(r.findall(t))} times at line start")
    need(re.match(r"^\d{4}-\d{2}-\d{2}_.+\.md$", os.path.basename(f)) is not None, f"{os.path.basename(f)}: name pattern")
# excluded projects and secrets in every text file of the pack
blob = ""
for f in glob.glob("/home/claude/mma_v2/**/*", recursive=True):
    if os.path.isfile(f) and f.endswith((".json", ".md")): blob += open(f, encoding="utf-8").read() + "\n"
for term in ("xavhm", "razorpay", "axiom recover", "fed-", "api_key", "secret", "token", "password", "ghp_", "AKIA"):
    need(term.lower() not in blob.lower(), f"excluded or sensitive term present: {term}")
print(f"{len(ap['anti_patterns'])} AP, {len(dna['decision_tree'])} DN, {len(dna['meta_lessons'])} meta, {len(sk['skills'])} SK ({sum(s['rule1_passed'] for s in sk['skills'])} Rule-1 passed), {len(files)} reflections")
print("VALID" if not bad else "PROBLEMS:\n  " + "\n  ".join(bad))
sys.exit(1 if bad else 0)
