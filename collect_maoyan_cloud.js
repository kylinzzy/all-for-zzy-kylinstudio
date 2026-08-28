// 猫眼专业版采集 - 云端版（headless chromium，无本机 Chrome / 无本机登录态）
// 用于 GitHub Actions 等 CI 环境：H5guard 在 headless 下不拦（已验证）。
// 输出原始数据 JSON 到指定路径（默认 /tmp/maoyan_raw.json），供 build_maoyan.py 转成 maoyan_data.json。
//
// 用法：node collect_maoyan_cloud.js [输出路径]
const { chromium } = require('playwright');
const fs = require('fs');

const OUT = process.argv[2] || '/tmp/maoyan_raw.json';
const SERIES_ID = 1607407;
const PAGE = `https://piaofang.maoyan.com/i/tv-datainfo/${SERIES_ID}/platform`;

function toWan(s) {
  if (s === null || s === undefined) return null;
  s = ('' + s).trim();
  if (s.includes('亿')) return parseFloat(s.replace('亿', '')) * 10000;
  if (s.includes('万')) return parseFloat(s.replace('万', ''));
  return parseFloat(s);
}

async function tryCollect() {
  const browser = await chromium.launch({
    headless: true,
    args: [
      '--disable-blink-features=AutomationControlled',
      '--no-sandbox',
      '--disable-dev-shm-usage',
      '--disable-gpu',
    ],
  });
  try {
    const context = await browser.newContext({
      userAgent: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    });
    const page = await context.newPage();
    const captured = { statuses: [] };
    page.on('response', async (r) => {
      const u = r.url();
      try {
        if (u.includes('/api/netWorkPlatFrom/getPlatData')) {
          const status = r.status();
          captured.statuses.push(status);
          if (status === 200) captured.plat = await r.json();
        }
      } catch (e) {}
    });
    await page.goto(PAGE, { waitUntil: 'domcontentloaded', timeout: 30000 });
    try {
      await page.waitForResponse(
        (r) => r.url().includes('/api/netWorkPlatFrom/getPlatData') && r.status() === 200,
        { timeout: 20000 }
      );
    } catch (e) {}
    await page.waitForTimeout(1500);
    if (!captured.plat || !captured.plat.data) {
      console.error('NO_DATA statuses=' + JSON.stringify(captured.statuses));
      return null;
    }
    const d = captured.plat.data;
    const nh = d.networkHeat || {};
    const daily = {};
    (d.rows || []).forEach((r) => { daily[r.dateTimeDesc] = toWan(r.sumPlayCountDesc); });
    return {
      cumulative_yi: nh.sumPlayCountDesc != null ? parseFloat(nh.sumPlayCountDesc) : null,
      cumulative_unit: nh.sumPlayCountUnit || '亿',
      today_wan: nh.todayPlayCountDesc != null ? parseFloat(nh.todayPlayCountDesc) : null,
      yesterday_yi: nh.yesterdayPlayCountDesc != null ? parseFloat(nh.yesterdayPlayCountDesc) : null,
      daily: daily,
      source: 'maoyan-cloud-headless',
      series_id: SERIES_ID,
    };
  } finally {
    await browser.close();
  }
}

(async () => {
  let lastErr = '';
  for (let attempt = 1; attempt <= 3; attempt++) {
    try {
      const out = await tryCollect();
      if (out) {
        fs.writeFileSync(OUT, JSON.stringify(out, null, 2));
        console.log('OK collected -> ' + OUT);
        console.log('累计=' + out.cumulative_yi + '亿 昨日=' + out.yesterday_yi + '亿 今日=' +
          out.today_wan + '万 明细=' + Object.keys(out.daily).length + '天');
        return;
      }
      lastErr = 'NO_DATA';
    } catch (e) {
      lastErr = 'ERR ' + e.message;
    }
    if (attempt < 3) await new Promise((r) => setTimeout(r, 3000));
  }
  console.error(lastErr);
  process.exit(2);
})();
