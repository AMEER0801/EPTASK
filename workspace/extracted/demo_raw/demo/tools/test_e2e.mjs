// End-to-end test of the EPtask 3D demo. Usage: node test_e2e.mjs <path/to/index.html> [fixed|legacy|both]
// Drives the in-page self-test (every hazard x warning network x step, timeline end, zoom extremes)
// and checks boot, the log, page errors and console errors. Exit code 0 = pass.
import puppeteer from 'puppeteer-core';
import path from 'node:path';
const page_ = path.resolve(process.argv[2] || 'index.html'), which = process.argv[3] || 'both';
const CHROME = process.env.CHROME || '/opt/google/chrome/chrome';
async function run(qs) {
  const browser = await puppeteer.launch({ executablePath: CHROME, headless: true, protocolTimeout: 1800000,   // the page is busy for minutes while the self-test runs
    args: ['--no-sandbox', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
  const page = await browser.newPage(); await page.setViewport({ width: 1440, height: 900 });
  const consoleErrors = [], pageErrors = [];
  page.on('console', m => { if (m.type() === 'error' && !/ERR_NAME_NOT_RESOLVED|net::|fonts\.g/.test(m.text())) consoleErrors.push(m.text().slice(0, 200)); });
  page.on('pageerror', e => pageErrors.push(e.message));
  const t0 = Date.now();
  await page.goto('file://' + page_ + qs, { waitUntil: 'domcontentloaded', timeout: 120000 });
  await page.waitForFunction('window.__demo && window.__demo.selftest', { timeout: 250000 });
  const r = await page.evaluate(() => ({ st: window.__demo.selftest, boot: window.__demo.log.find(e => e.cat === 'boot' && e.msg === 'demo ready'), errs: window.__demo.log.filter(e => e.level === 'error').map(e => e.msg) }));
  await browser.close();
  return Object.assign(r, { consoleErrors, pageErrors, secs: (Date.now() - t0) / 1000 });
}
let ok = true;
if (which !== 'legacy') {
  const f = await run('?fx=0&selftest=1');
  console.log(`FIXED : ${f.st.pass}/${f.st.states} checks passed, ${f.st.fails.length} failed, ${f.st.jsErrors} script errors, boot logged: ${!!f.boot}, log errors: ${f.errs.length}, page errors: ${f.pageErrors.length}, console errors: ${f.consoleErrors.length} (${f.secs.toFixed(0)} s)`);
  f.st.fails.slice(0, 8).forEach(x => console.log('   FAIL', x.state, '->', x.problems.join('; ')));
  ok = ok && f.st.fails.length === 0 && !!f.boot && !f.errs.length && !f.pageErrors.length && !f.consoleErrors.length;
}
if (which !== 'fixed') {
  const l = await run('?fx=0&selftest=1&legacy=1');
  const kinds = {}; l.st.fails.forEach(x => x.problems.forEach(p => { const k = p.replace(/[0-9]+/g, 'N'); kinds[k] = (kinds[k] || 0) + 1; }));
  console.log(`LEGACY: ${l.st.fails.length} of ${l.st.states} checks fail on the pre-fix placement (the test must catch the old flaw):`);
  Object.entries(kinds).forEach(([k, n]) => console.log(`   ${n} x ${k}`));
  ok = ok && l.st.fails.length > 0;
}
console.log(ok ? 'E2E PASS' : 'E2E FAIL'); process.exit(ok ? 0 : 1);
