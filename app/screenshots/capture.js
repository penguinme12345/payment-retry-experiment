const { chromium } = require('playwright');
(async () => {
  const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: 1400, height: 1000 }, deviceScaleFactor: 1 });
  const pages = [['', 'overview'], ['Segments', 'segments'], ['Guardrails', 'guardrails'], ['Explore', 'explore'], ['Methodology', 'methodology']];
  for (const [path, name] of pages) {
    await p.goto('http://localhost:8599/' + path, { waitUntil: 'networkidle' });
    await p.waitForSelector('[data-testid="stAppViewContainer"]');
    await p.waitForTimeout(4000);
    const h = await p.evaluate(() => { const m = document.querySelector('[data-testid="stMain"]') || document.querySelector('section.main'); return m ? m.scrollHeight : 1000; });
    await p.setViewportSize({ width: 1400, height: Math.min(Math.max(h, 1000), 4000) });
    await p.waitForTimeout(2000);
    await p.screenshot({ path: process.argv[2] + '/' + name + '.png', fullPage: true });
    await p.setViewportSize({ width: 1400, height: 1000 });
  }
  await b.close();
})();
