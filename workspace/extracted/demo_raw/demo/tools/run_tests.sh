#!/usr/bin/env bash
# Full check of the demo. Needs: python3, node 18+, `npm i puppeteer-core`, Chrome (set CHROME=/path/to/chrome).
set -e
cd "$(dirname "$0")/.."
python3 tools/check_data.py demo_data.json
node tools/test_e2e.mjs index.html both
node tools/test_shots.mjs index.html shots
echo "All tests passed. Review the screenshots in ./shots"
