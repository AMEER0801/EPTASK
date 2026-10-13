#!/usr/bin/env bash
# package_zip.sh -- build the portable laptop delivery.
set -euo pipefail
cd /home/z/my-project
STAGE=/tmp/eptask_zip_stage
OUT=/home/z/my-project/download/EPtask-Ops-Console-v2.zip
NAME=EPtask-Ops-Console

rm -rf "$STAGE"; mkdir -p "$STAGE/$NAME"
cd "$STAGE/$NAME"

# ---- root docs & configs ----
cp /home/z/my-project/README.md /home/z/my-project/SETUP_GUIDE.md ./
cp /home/z/my-project/.env.example ./
cp /home/z/my-project/.gitignore ./
mkdir -p docs
cp /home/z/my-project/docs/API.md /home/z/my-project/docs/ARCHITECTURE.md /home/z/my-project/docs/LIMITATIONS.md docs/

# laptop frontend env (direct mode) -- sandbox gateway config stays out
cat > .env.local <<'EOF'
# EPtask Ops Console -- laptop defaults (direct mode).
# The browser talks to the simulation service directly; CORS is open.
NEXT_PUBLIC_API_URL=http://localhost:8100

# Sandbox/gateway deployments instead set:
# NEXT_PUBLIC_GATEWAY_MODE=1
# NEXT_PUBLIC_API_URL=
EOF

# ---- frontend ----
mkdir -p src public prisma
cp -r /home/z/my-project/src/. src/
rm -f src/lib/db.ts                          # unused prisma scaffold
cp -r /home/z/my-project/public/. public/
cp -r /home/z/my-project/prisma/. prisma/ 2>/dev/null || true
for f in package.json bun.lock next.config.ts tailwind.config.ts postcss.config.mjs \
         tsconfig.json eslint.config.mjs components.json; do
  cp /home/z/my-project/$f ./
done

# ---- backend ----
mkdir -p mini-services
cd mini-services
rsync -a --exclude '__pycache__' --exclude 'data' --exclude '*.log' \
      --exclude '.venv' --exclude '.pytest_cache' \
      /home/z/my-project/mini-services/eptask-api/ ./eptask-api/
cd "$STAGE/$NAME"

# ---- report what goes in ----
echo "== staged size:"
du -sh "$STAGE/$NAME"
echo "== file count: $(find "$STAGE/$NAME" -type f | wc -l)"
echo "== no junk check:"
find "$STAGE/$NAME" \( -name node_modules -o -name .next -o -name __pycache__ -o -name "*.log" -o -name data \) -print | head
mkdir -p /home/z/my-project/download
rm -f "$OUT"
cd "$STAGE" && zip -q -r -9 "$OUT" "$NAME"
echo "== zip written:"
ls -lh "$OUT"
unzip -l "$OUT" | head -12
unzip -l "$OUT" | tail -3
