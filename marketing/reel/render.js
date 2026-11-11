// Usage: node render.js stills t1 t2 ...   -> stills/t_<t>.png
//        node render.js frames             -> frames/00000.jpg ... (every frame)
const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');

(async () => {
  const mode = process.argv[2];
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1080, height: 1920 }, deviceScaleFactor: 1 });
  await page.goto('file://' + path.join(__dirname, 'index.html'));
  await page.evaluate(() => document.fonts.ready);
  await page.waitForFunction(() => [...document.images].every(i => i.complete && i.naturalWidth > 0));
  const fps = await page.evaluate(() => window.FPS);
  const dur = await page.evaluate(() => window.DURATION);
  if (mode === 'stills') {
    fs.mkdirSync(path.join(__dirname, 'stills'), { recursive: true });
    for (const t of process.argv.slice(3).map(Number)) {
      await page.evaluate(t => window.render(t), t);
      await page.screenshot({ path: path.join(__dirname, 'stills', `t_${t.toFixed(2)}.png`) });
    }
  } else {
    const dir = path.join(__dirname, 'frames');
    fs.rmSync(dir, { recursive: true, force: true });
    fs.mkdirSync(dir);
    const n = Math.round(dur * fps);
    for (let i = 0; i < n; i++) {
      await page.evaluate(t => window.render(t), i / fps);
      await page.screenshot({ path: path.join(dir, String(i).padStart(5, '0') + '.jpg'), type: 'jpeg', quality: 95 });
      if (i % 150 === 0) console.log(`frame ${i}/${n}`);
    }
    console.log(`done ${n} frames`);
  }
  await browser.close();
})();
