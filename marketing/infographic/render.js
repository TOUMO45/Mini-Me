// node render.js  -> Mini_Me_Infographic_4x5.png (1080x1350) and _2x.png (2160x2700)
const { chromium } = require('playwright');
const path = require('path');

(async () => {
  const browser = await chromium.launch();
  for (const [scale, name] of [[1, 'Mini_Me_Infographic_4x5.png'], [2, 'Mini_Me_Infographic_4x5_2x.png']]) {
    const page = await browser.newPage({ viewport: { width: 1080, height: 1350 }, deviceScaleFactor: scale });
    await page.goto('file://' + path.join(__dirname, 'index.html'));
    await page.evaluate(() => document.fonts.ready);
    await page.waitForFunction(() => [...document.images].every(i => i.complete && i.naturalWidth > 0));
    // Fail loudly if anything spills outside the canvas.
    const overflow = await page.evaluate(() => [...document.querySelectorAll('.wrap *')]
      .filter(e => { const r = e.getBoundingClientRect(); return r.right > 1080.5 || r.bottom > 1350.5; })
      .map(e => e.className || e.tagName));
    if (overflow.length) console.log('OVERFLOW:', overflow);
    await page.screenshot({ path: path.join(__dirname, name) });
    await page.close();
  }
  await browser.close();
  console.log('done');
})();
