// Renders README visuals into docs/assets/. Run from the repo root after build.py:
//   node docs/assets/src/render.js
const { chromium } = require('playwright');
const path = require('path');

const SRC = __dirname;
const OUT = path.join(__dirname, '..');

(async () => {
  const browser = await chromium.launch();
  const jobs = [
    { page: 'banner.html', out: 'banner.png', w: 1280, h: 640, scale: 2, full: false },
    { page: 'terminal.html', out: 'recall-terminal.png', w: 1200, h: 400, scale: 2, full: true, transparent: true },
  ];
  for (const j of jobs) {
    const page = await browser.newPage({ viewport: { width: j.w, height: j.h }, deviceScaleFactor: j.scale });
    await page.goto('file://' + path.join(SRC, j.page));
    await page.evaluate(() => document.fonts.ready);
    await page.waitForFunction(() => [...document.images].every(i => i.complete && i.naturalWidth > 0));
    await page.screenshot({ path: path.join(OUT, j.out), fullPage: j.full, omitBackground: !!j.transparent });
    await page.close();
    console.log('wrote', j.out);
  }
  await browser.close();
})();
