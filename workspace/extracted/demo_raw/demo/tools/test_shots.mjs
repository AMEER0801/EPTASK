// Visual check with bloom on. Usage: node test_shots.mjs <path/to/index.html> [out_dir]   -> PNGs to review by eye
import puppeteer from 'puppeteer-core'; import path from 'node:path'; import fs from 'node:fs';
const page_ = path.resolve(process.argv[2] || 'index.html'), out = process.argv[3] || 'shots'; fs.mkdirSync(out, { recursive: true });
const browser = await puppeteer.launch({ executablePath: process.env.CHROME || '/opt/google/chrome/chrome', headless: true, args: ['--no-sandbox', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
const page = await browser.newPage(); await page.setViewport({ width: 1440, height: 900 });
await page.goto('file://' + page_, { waitUntil: 'load' }); await page.waitForFunction('window.__demo && window.__demo.ready'); await new Promise(r => setTimeout(r, 2600));
for (const [name, hz, mode, step, t] of [['1_before', 'landslide', 'V2V+RSU', 0], ['2_landslide', 'landslide', 'V2V+RSU', 1, 220], ['3_earthquake', 'earthquake', 'V2V+RSU', 1, 70], ['4_flood', 'flood', 'V2V+RSU', 2, 230], ['5_convoy', 'landslide', 'V2V', 6, 1500], ['6_reached', 'landslide', 'V2V+RSU', 7]]) {
  await page.evaluate((h, m) => window.__demo.setScenario(h, m), hz, mode); await page.evaluate(i => window.__demo.goStep(i), step);
  if (t != null) await page.evaluate(x => window.__demo.setTime(x), t);
  await page.evaluate(() => window.__demo.render()); await page.screenshot({ path: path.join(out, name + '.png') }); console.log('saved', name);
}
console.log('errors:', JSON.stringify(await page.evaluate(() => window.__demo.errors))); await browser.close();
