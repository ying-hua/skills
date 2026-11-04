// 自动抓 GitHub 素材（不用用户截图/录屏）。用 web-search skill 的 playwright-core + 本机 Chrome 无头 + 本地代理。
//
//   node tools/capture.mjs repo   <owner/repo> <outdir> [--about "中文简介"]   仓库首页高清截图 + 项目名/Star 坐标；--about 把侧栏简介换成中文(按钮保持英文)
//        --stars 8.3k：Star 按钮和侧栏 stars 改成配音念的数(真实数已经涨了/四舍五入不一致时，用户 2026-10-26 要求)
//   node tools/capture.mjs select <owner/repo> <outdir> [选项]          鼠标拖选简介的「选字录屏」+ 3D 运镜 job.json
//        --text "要选的一段字"      默认 README 第一段像简介的文字(>=12 字)
//        --set "替换成的中文"       把这段字替换成中文再选(相当于用户用浏览器翻译)
//        --url <页面>               不用仓库首页，改用某个页面(如 README_CN 的 blob 页)
//        --zh zh.json               同 page --zh，周围的 README 段落也换成中文
//        --dur 2.6 --lead 0.5 --tail 0.4   拖选时长 / 拖选前停顿 / 选完停顿(秒)
//   node tools/capture.mjs page   <url> <outdir> [--sel CSS] [--name readme] [--download] [--zh zh.json]
//        --zh：没有中文 README 时用(用户 2026-10-21：画面一律中文)。zh.json = {"块的英文原文(innerText 去多余空白)": "中文 HTML"}，
//        --find "短语1|短语2" 输出每个短语在分图里的像素框(found)，直接给 tl.spot。
//        key 以 * 结尾表示前缀匹配；截图前把对应的 h1~h4/p/li/td/th 换成中文(可带 <code>/<strong>)；代码块和 Star/Fork 等 GitHub 界面不动。没匹配上的 key 会打印出来
//        README/文档 分段高清长图 + 每个块(标题/段落/图/表/代码)的坐标；列出页面里的视频和大小，--download 才下载 mp4
//   node tools/capture.mjs docs   <owner/repo> <outdir>                 列 docs/ 下的 md、主页、README 里的视频(只列不下载)
//
// 输出图都是 deviceScaleFactor=2；JSON 里的 box 都是该 PNG 的像素坐标 [x0,y0,x1,y1]，可直接给 jy.zshot / tl.pop / tl.spot。
import fs from 'node:fs';
import path from 'node:path';
import { spawn } from 'node:child_process';
import os from 'node:os';
import { pathToFileURL } from 'node:url';

// 依赖 web-search skill 自带的 playwright-core；装在别处就设环境变量 WEB_SEARCH_SKILL
const SKILL = (process.env.WEB_SEARCH_SKILL || path.join(os.homedir(), '.claude/skills/web-search')).replace(/\\/g, '/');
const { chromium } = await import(pathToFileURL(`${SKILL}/node_modules/playwright-core/index.mjs`).href);
const { findProxy } = await import(pathToFileURL(`${SKILL}/scripts/lib.mjs`).href);

const UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36';
const DPR = 2;
const FPS = 30;

function args(argv) {
  const pos = [], opt = {};
  for (let i = 0; i < argv.length; i++) {
    if (argv[i].startsWith('--')) opt[argv[i].slice(2)] = argv[i + 1]?.startsWith('--') || argv[i + 1] === undefined ? true : argv[++i];
    else pos.push(argv[i]);
  }
  return { pos, opt };
}

async function open(viewport = { width: 1280, height: 720 }) {
  const server = await findProxy();
  const browser = await chromium.launch({ channel: 'chrome', headless: true, ...(server ? { proxy: { server } } : {}) });
  const ctx = await browser.newContext({ userAgent: UA, locale: 'en-US', viewport, deviceScaleFactor: DPR, colorScheme: 'light' });
  const page = await ctx.newPage();
  return { browser, page };
}

async function goto(page, url) {
  await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await page.waitForLoadState('networkidle', { timeout: 20000 }).catch(() => {});
  // 去掉登录横幅、cookie 条等干扰
  await page.addStyleTag({ content: `
    .js-notification-shelf, .flash-full, [data-testid="cookie-consent"], .cookie-consent, #cookie-consent-banner,
    .signup-prompt, .js-signup-prompt { display: none !important; }
    ::selection { background: #3a6fd9 !important; color: #fff !important; }
    * { scroll-behavior: auto !important; caret-color: transparent !important; }` });
}

// 滚完整页触发懒加载图片
async function warm(page) {
  await page.evaluate(async () => {
    const H = document.documentElement.scrollHeight;
    for (let y = 0; y < H; y += 600) { window.scrollTo(0, y); await new Promise(r => setTimeout(r, 120)); }
    window.scrollTo(0, 0);
  });
  await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => {});
  await page.evaluate(() => Promise.all([...document.images].filter(i => !i.complete).map(i => new Promise(r => { i.onload = i.onerror = r; setTimeout(r, 5000); }))));
}

const px = r => r && [r.x, r.y, r.x + r.width, r.y + r.height].map(v => Math.round(v * DPR));

// 元数据走 gh CLI(已登录，不受匿名限流；代理出口 IP 的匿名 API 经常 403)
import { execFileSync } from 'node:child_process';
function gh(p) {
  try { return JSON.parse(execFileSync('gh', ['api', p], { encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] })); } catch { return null; }
}
async function api(repo) {
  const info = gh(`repos/${repo}`);
  const docs = info ? gh(`repos/${repo}/contents/docs`) : null;
  return { info, docs };
}

// 易被抖音限流的区域(用户 2026-10-16)：链接/网址/邮箱、注册登录付费充值赞助广告等字眼、赞助横幅图。
// 在页面里执行，返回页面绝对坐标(含 scrollY)的 CSS 像素框；build 时用 fx.blur_risky 局部模糊。
function findRisky(rootSel) {
  const AD = /赞助|(?<!拦截|屏蔽|去除?)广告(?!拦截|域名|追踪)|注册|登录|充值|付费|优惠|推广|领取|返利|邀请码|折起|倍率|额度|会员|购买|价格|微信|QQ群|公众号|sponsor|advertis|discount|coupon|sign ?(in|up)|log ?in|register|pricing|subscribe|buy|donat/i;
  const URLISH = /https?:\/\/|www\.|\b[a-z0-9-]+(\.[a-z0-9-]+)*\.(com|io|cn|dev|ai|net|org|cc|app|me|xyz|top|so|sh|co|tech|site)\b|[\w.-]+@[\w-]+\.[a-z]+/i;
  const root = rootSel ? (rootSel.split(',').map(x => document.querySelector(x.trim())).find(Boolean) || document.body) : document.body;
  const sy = scrollY, out = [];
  const add = (el, why) => {
    const r = el.getBoundingClientRect(); if (r.width < 4 || r.height < 4) return;
    out.push({ x: r.x, y: r.y + sy, w: r.width, h: r.height, why, text: (el.innerText || el.alt || '').replace(/\s+/g, ' ').trim().slice(0, 60) });
  };
  for (const a of root.querySelectorAll('a, button')) {
    const t = (a.innerText || '').trim();
    if (!t) continue;
    if (URLISH.test(t)) add(a, 'link');
    else if (AD.test(t) && t.length < 40) add(a, 'ad');
  }
  // 最小的含敏感字眼的文字块(不要把整个 section 糊掉)
  for (const el of root.querySelectorAll('p, li, h1, h2, h3, h4, td, th, blockquote, span, strong')) {
    const t = (el.innerText || '').trim();
    if (!t || t.length > 300 || !(AD.test(t) || URLISH.test(t))) continue;
    if ([...el.children].some(ch => { const u = (ch.innerText || '').trim(); return u && (AD.test(u) || URLISH.test(u)) && u.length > t.length * 0.6; })) continue;
    if (el.closest('pre, code')) continue;   // 代码里的 URL(安装命令)不算
    add(el, AD.test(t) ? 'ad' : 'link');
  }
  // 整个赞助/广告章节：从该标题糊到下一个同级或更高级标题(逐段判断会漏，用户 2026-10-16 第35期)
  for (const h of root.querySelectorAll('h1, h2, h3')) {
    if (!/赞助|广告|合作伙伴|推广|sponsor|backer|advertis|partner/i.test(h.innerText || '')) continue;
    const lv = +h.tagName[1], start = h.closest('.markdown-heading') || h;
    const r0 = start.getBoundingClientRect();
    let y1 = r0.bottom, x0 = r0.left, x1 = r0.right;
    for (let e = start.nextElementSibling; e; e = e.nextElementSibling) {
      const hh = e.matches('h1,h2,h3,h4,h5,h6') ? e : e.querySelector(':scope > h1, :scope > h2, :scope > h3, :scope > h4');
      if (hh && +hh.tagName[1] <= lv) break;
      const r = e.getBoundingClientRect();
      if (r.height) { y1 = Math.max(y1, r.bottom); x0 = Math.min(x0, r.left); x1 = Math.max(x1, r.right); }
    }
    out.push({ x: x0, y: r0.top + sy, w: x1 - x0, h: y1 - r0.top, why: 'section', text: (h.innerText || '').trim().slice(0, 60) });
  }
  for (const img of root.querySelectorAll('img')) {
    if (/sponsor|banner|advert|\bads?\b|coupon|qrcode|wechat|qr[-_]?code/i.test((img.currentSrc || img.src || '') + ' ' + (img.alt || '')) || AD.test(img.alt || ''))
      add(img, 'banner');
  }
  return out;
}

// ---------------------------------------------------------------- repo
async function cmdRepo(repo, out) {
  const { info } = await api(repo);
  const { browser, page } = await open({ width: 1280, height: 800 });
  await goto(page, `https://github.com/${repo}`);
  if (opt.about) {
    await page.waitForFunction(() => {
      const h = [...document.querySelectorAll('h2')].find(h => h.textContent.trim() === 'About' && h.getBoundingClientRect().width);
      return h && [...h.parentElement.querySelectorAll('p')].some(e => e.getBoundingClientRect().width);
    }, null, { timeout: 15000 }).catch(() => {});
    // 相当于 F12 改字：About 简介换成中文，保留开头的 emoji。GitHub 是 React 页面，可能重渲染改回去，
    // 所以挂一个 MutationObserver 一直保持
    const ok = await page.evaluate(text => {
      const find = () => {
        const h = [...document.querySelectorAll('h2')].find(h => h.textContent.trim() === 'About' && h.getBoundingClientRect().width);
        return h && [...h.parentElement.querySelectorAll('p')].find(e => e.getBoundingClientRect().width);
      };
      const apply = () => {
        const p = find(); if (!p || p.dataset.zh === '1' && p.textContent.includes(text)) return !!p;
        const emoji = p.querySelector('g-emoji, img.emoji');
        const lead = (p.textContent.trim().match(/^[\p{Extended_Pictographic}️‍]+\s*/u) || [''])[0];
        p.textContent = (emoji ? '' : lead) + text;
        if (emoji) p.prepend(emoji, ' ');
        p.dataset.zh = '1';
        return true;
      };
      new MutationObserver(apply).observe(document.body, { subtree: true, childList: true, characterData: true });
      return apply();
    }, opt.about);
    await page.waitForTimeout(1500);
    if (!ok) console.error('没找到 About 简介，未替换');
  }
  if (opt.stars) {
    // 用户 2026-10-26：Star 数和配音念的不一致(念 8.3k、页面已涨到 8.4k)时，前端改成配音的数再截
    const n = await page.evaluate(text => {
      const apply = () => {
        let n = 0;
        for (const e of document.querySelectorAll('span[class*=CounterLabel]')) {
          const b = e.closest('a,button,[role=button]');
          if (b && /star/i.test(b.parentElement.textContent) && e.textContent.trim() !== text) { e.textContent = text; n++; }
        }
        for (const s of document.querySelectorAll('a strong, span strong')) {
          if (/^\s*stars?\s*$/i.test(s.parentElement.textContent.replace(s.textContent, '')) && s.textContent.trim() !== text) { s.textContent = text; n++; }
        }
        return n;
      };
      new MutationObserver(apply).observe(document.body, { subtree: true, childList: true, characterData: true });
      return apply();
    }, String(opt.stars));
    await page.waitForTimeout(800);
    console.error(`Star 数改成 ${opt.stars}：${n} 处`);
  }
  const boxes = await page.evaluate(repoName => {
    const rect = el => { if (!el) return null; const r = el.getBoundingClientRect(); return r.width ? { x: r.x, y: r.y, width: r.width, height: r.height } : null; };
    const union = (...els) => {
      const rs = els.map(rect).filter(Boolean); if (!rs.length) return null;
      const x0 = Math.min(...rs.map(a => a.x)), y0 = Math.min(...rs.map(a => a.y));
      const x1 = Math.max(...rs.map(a => a.x + a.width)), y1 = Math.max(...rs.map(a => a.y + a.height));
      return { x: x0, y: y0, width: x1 - x0, height: y1 - y0 };
    };
    const vis = el => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
    const all = sel => [...document.querySelectorAll(sel)].filter(vis);
    // 大标题：头像右边那个 <strong><a>项目名</a></strong>(不是面包屑)
    const name = all('strong > a').find(a => a.textContent.trim() === repoName);
    const avatar = name && all('img').filter(i => Math.abs(i.getBoundingClientRect().y - name.getBoundingClientRect().y) < 30 && i.getBoundingClientRect().x < name.getBoundingClientRect().x)[0];
    // Star 按钮里的计数
    const counters = all('span').filter(e => /CounterLabel/.test(e.className) && e.closest('a,button,[role=button]'));
    const starCount = counters.find(e => /star/i.test(e.closest('a,button,[role=button]').parentElement.textContent));
    const starBtn = starCount && (starCount.closest('[class*=ButtonGroup]') || starCount.closest('a,button,[role=button]'));
    // About 侧栏
    const aboutH = all('h2').find(h => h.textContent.trim() === 'About');
    const side = aboutH && aboutH.parentElement;
    const about = side && [...side.querySelectorAll('p')].filter(vis)[0];
    // 侧栏「70.9k stars」(新版是 <span><strong>70.9k</strong> stars</span>，不再是链接)
    const aboutStars = all('a, span').find(e => /^[\d.,]+k?\s*stars?$/i.test(e.textContent.trim()) && e.querySelector('strong'));
    return {
      name: rect(name), title: union(avatar, name), star_button: rect(starBtn), star_count: rect(starCount),
      about_stars: rect(aboutStars), about: rect(about),
      star_text: starCount?.textContent.trim(), about_text: about?.textContent.trim(),
    };
  }, repo.split('/')[1]);
  const risky = await page.evaluate(findRisky, null);
  const png = path.join(out, 'repo_top.png');
  await page.screenshot({ path: png });
  await browser.close();
  const res = { png, url: `https://github.com/${repo}`, stars: info?.stargazers_count, forks: info?.forks_count,
    description: info?.description, homepage: info?.homepage, language: info?.language, pushed_at: info?.pushed_at,
    star_text: boxes.star_text, about_text: boxes.about_text, boxes: {} };
  for (const k of ['name', 'title', 'star_button', 'star_count', 'about_stars', 'about']) res.boxes[k] = px(boxes[k]);
  // 视口截图：scrollY=0，页面坐标即视口坐标；只留截图范围内的
  res.risky = risky.filter(r => r.y < 800 && r.y + r.h > 0)
    .map(r => ({ box: px({ x: r.x, y: r.y, width: r.w, height: r.h }), why: r.why, text: r.text }));
  fs.writeFileSync(path.join(out, 'repo.json'), JSON.stringify(res, null, 2));
  console.log(JSON.stringify(res, null, 2));
}

// ---------------------------------------------------------------- select
// 简单的 Windows I 形光标(随鼠标移动的 DOM 元素，截图里能看到)
const CURSOR = `<svg xmlns="http://www.w3.org/2000/svg" width="13" height="26" viewBox="0 0 9 18"><path d="M1 1h2.5l1 1 1-1H8M4.5 2v14M1 17h2.5l1-1 1 1H8" fill="none" stroke="#fff" stroke-width="2.6"/><path d="M1 1h2.5l1 1 1-1H8M4.5 2v14M1 17h2.5l1-1 1 1H8" fill="none" stroke="#000" stroke-width="1.1"/></svg>`;

async function cmdSelect(repo, out, opt) {
  const W = 1280, H = 640;
  const { browser, page } = await open({ width: W, height: H });
  await goto(page, opt.url || `https://github.com/${repo}`);
  await applyZh(page, opt.zh);   // 选区周围的 README 文字也换成中文(--set 只换被选的那句)
  await warm(page);
  // 找要选的那段字，必要时换成中文
  const found = await page.evaluate(({ want, set }) => {
    const body = document.querySelector('article.markdown-body') || document.body;
    const blocks = [...body.querySelectorAll('p, h1, h2, h3, h4, li, blockquote, div[align]')];
    const textOf = el => el.innerText.replace(/\s+/g, ' ').trim();
    let el;
    if (want) el = blocks.filter(b => textOf(b).includes(want)).sort((a, b) => textOf(a).length - textOf(b).length)[0];
    else el = blocks.find(b => { const t = textOf(b); return t.length >= 12 && t.length <= 160 && !b.querySelector('img') && /[A-Za-z\u4e00-\u9fff]{4}/.test(t) && !/^(\[|English|中文|简体)/.test(t); });
    if (!el) return null;
    if (set) {
      // 用户的做法是浏览器翻译：只换文字，保留样式
      const tgt = want ? [...el.querySelectorAll('*'), el].reverse().find(n => textOf(n).includes(want)) : el;
      tgt.textContent = set;
      el = tgt;
    }
    el.id = '__sel_target';
    // 选区范围：want 精确匹配，否则整个元素的文字
    const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
    const nodes = []; let n; while ((n = walker.nextNode())) if (n.textContent.trim()) nodes.push(n);
    window.__nodes = nodes;
    const full = nodes.map(n => n.textContent).join('');
    let a = 0, b = full.length;
    const key = set || want;
    if (key && full.includes(key)) { a = full.indexOf(key); b = a + key.length; }
    while (a < b && /\s/.test(full[a])) a++;
    while (b > a && /\s/.test(full[b - 1])) b--;
    window.__range = [a, b];
    return { text: full.slice(a, b) };
  }, { want: opt.text, set: opt.set });
  if (!found) throw new Error('没找到要选的文字，用 --text 指定');
  // 把这段字滚到画面中间偏上
  await page.evaluate(() => { const r = document.getElementById('__sel_target').getBoundingClientRect(); window.scrollBy(0, r.y + r.height / 2 - innerHeight * 0.45); });
  await page.waitForTimeout(400);
  // 每个字符的位置（视口坐标）
  const chars = await page.evaluate(() => {
    const [a, b] = window.__range, res = []; let off = 0;
    for (const node of window.__nodes) {
      for (let i = 0; i < node.textContent.length; i++, off++) {
        if (off < a || off >= b) continue;
        const rg = document.createRange(); rg.setStart(node, i); rg.setEnd(node, i + 1);
        const r = rg.getBoundingClientRect(); if (r.width) res.push([r.x, r.y, r.width, r.height]);
      }
    }
    return res;
  });
  await page.evaluate(svg => {
    const c = document.createElement('div'); c.id = '__cursor'; c.innerHTML = svg;
    Object.assign(c.style, { position: 'fixed', left: '0', top: '0', zIndex: 2147483647, pointerEvents: 'none', width: '13px', height: '26px' });
    document.body.appendChild(c);
    addEventListener('mousemove', e => { c.style.transform = `translate(${e.clientX - 6.5}px, ${e.clientY - 13}px)`; }, true);
  }, CURSOR);

  const dur = +(opt.dur || 2.6), lead = +(opt.lead || 0.5), tail = +(opt.tail || 0.4);
  const ease = u => u < 0.5 ? 2 * u * u : 1 - (-2 * u + 2) ** 2 / 2;
  // 拖选：起步就有速度、接近匀速、结尾稍减速(用户 2026-10-15：ease-in-out 让前几个字拖得太慢)
  const drag = u => 0.7 * u + 0.3 * (1 - (1 - u) ** 2);
  const startPt = [chars[0][0] - 1, chars[0][1] + chars[0][3] / 2];
  const last = chars[chars.length - 1];
  const endPt = [last[0] + last[2] + 1, last[1] + last[3] / 2];
  const pathAt = u => { // u∈[0,1] -> 沿着字符走(支持换行)
    const k = u * chars.length, i = Math.min(chars.length - 1, Math.floor(k)), f = k - i, c = chars[i];
    if (u >= 1) return endPt;
    return [c[0] + c[2] * f, c[1] + c[3] / 2];
  };
  const N = Math.round((lead + dur + tail) * FPS);
  const ff = spawn('ffmpeg', ['-v', 'error', '-y', '-f', 'image2pipe', '-framerate', String(FPS), '-i', '-',
    '-c:v', 'libx264', '-crf', '14', '-pix_fmt', 'yuv420p', path.join(out, 'select.mp4')], { stdio: ['pipe', 'inherit', 'inherit'] });
  const track = [];
  // 光标从下方滑到起点
  const approach = [startPt[0] - 40, startPt[1] + 70];
  await page.mouse.move(...approach);
  let down = false;
  for (let f = 0; f < N; f++) {
    const t = f / FPS;
    let p;
    if (t < lead) { const u = ease(Math.min(1, t / (lead * 0.8))); p = [approach[0] + (startPt[0] - approach[0]) * u, approach[1] + (startPt[1] - approach[1]) * u]; }
    else if (t < lead + dur) { if (!down) { await page.mouse.move(...startPt); await page.mouse.down(); down = true; } p = pathAt(drag((t - lead) / dur)); }
    else { p = endPt; if (down) { await page.mouse.move(...p); await page.mouse.up(); down = false; } }
    await page.mouse.move(p[0], p[1]);
    track.push([+(p[0] * DPR).toFixed(1), +(p[1] * DPR).toFixed(1)]);
    ff.stdin.write(await page.screenshot({ type: 'png' }));
  }
  ff.stdin.end();
  await new Promise(r => ff.on('close', r));
  await browser.close();

  // 自动排 3D 运镜：把这行字按「一屏能看清的宽度」切成几段，光标走到下一段时换位
  // 第34期效果：先停在前半句，光标走过去时甩到后半句。默认 2 个停留点，字多(>34)用 3 个；
  // 放大倍数按「每段占输出宽 70%」反推(源是 2 倍图，倍数 3 左右也不糊)
  const x0 = chars[0][0] * DPR, x1 = endPt[0] * DPR, cy = Math.round((chars[0][1] + chars[0][3] / 2) * DPR);
  const nShots = +(opt.shots || (found.text.length > 34 ? 3 : 2));
  const OUT_W = 1920;
  const mag = +(opt.mag || Math.min(4, Math.max(1.2, (0.7 * OUT_W) / ((x1 - x0) / nShots))).toFixed(2));
  const seg = (x1 - x0) / nShots, shots = [];
  let sf = 0;
  for (let s = 0; s < nShots; s++) {
    const cx = Math.round(x0 + seg * (s + 0.5));
    // 光标越过本段 85% 时开始换位
    let ef = N - 1;
    if (s < nShots - 1) { const edge = x0 + seg * (s + 0.85); ef = track.findIndex(p => p[0] >= edge); if (ef < 0) ef = N - 1; ef = Math.max(sf + 8, ef - 4); }
    shots.push({ startFrame: sf, endFrame: ef, target: [cx, cy] });
    sf = ef + 4;
  }
  const job = { media: 'select.mp4', magnification: mag, shots, outputs: [{ name: 'landscape.mp4', width: OUT_W, height: 1080 }] };
  fs.writeFileSync(path.join(out, 'job.json'), JSON.stringify(job, null, 2));
  fs.writeFileSync(path.join(out, 'select.json'), JSON.stringify({ text: found.text, fps: FPS, frames: N, lead, dur, tail, track,
    chars: chars.map(c => px({ x: c[0], y: c[1], width: c[2], height: c[3] })) }, null, 1));
  console.log(`选字: ${found.text}\n${N} 帧 -> ${path.join(out, 'select.mp4')}\njob.json: ${JSON.stringify(shots)}`);
}

// --zh：README 块整块换成中文(page / select 共用)
async function applyZh(page, file, sel = 'article.markdown-body, .markdown-body') {
  if (!file) return;
  const map = JSON.parse(fs.readFileSync(file, 'utf8'));
  const miss = await page.evaluate(({ sel, map }) => {
    const root = sel.split(',').map(x => document.querySelector(x.trim())).find(Boolean) || document.body;
    const norm = t => t.replace(/\s+/g, ' ').trim(), used = new Set();
    for (const el of root.querySelectorAll('h1,h2,h3,h4,p,li,td,th,blockquote')) {
      const t = norm(el.innerText || '');
      // key 是整块文字，或以 * 结尾表示前缀(长段落不用抄全文)
      const k = t in map ? t : Object.keys(map).find(k => k.endsWith('*') && t.startsWith(k.slice(0, -1)));
      if (k && el.isConnected && !el.parentElement.closest('[data-zh]')) { el.innerHTML = map[k]; el.dataset.zh = 1; used.add(k); }
    }
    return Object.keys(map).filter(k => !used.has(k));
  }, { sel, map });
  await page.waitForTimeout(300);
  if (miss.length) console.error('zh 没匹配上:\n  ' + miss.join('\n  '));
}

// ---------------------------------------------------------------- page
async function cmdPage(url, out, opt) {
  const name = opt.name || 'page';
  const { browser, page } = await open({ width: 1280, height: 900 });
  await goto(page, url);
  const sel = opt.sel || 'article.markdown-body, .markdown-body, main article, main, article';
  await applyZh(page, opt.zh, sel);
  await warm(page);
  const info = await page.evaluate(sel => {
    // 逗号列表 querySelector 会按文档顺序返回(先命中 main)，这里按优先级逐个试
    const root = sel.split(',').map(x => document.querySelector(x.trim())).find(Boolean); if (!root) return null;
    const R = root.getBoundingClientRect(), sy = scrollY;
    const abs = el => { const r = el.getBoundingClientRect(); return [r.x, r.y + sy, r.width, r.height]; };
    const blocks = [];
    for (const el of root.querySelectorAll('h1,h2,h3,h4,p,li,pre,table,img,video,blockquote,picture')) {
      const [x, y, w, h] = abs(el); if (w < 8 || h < 8) continue;
      blocks.push({ tag: el.tagName.toLowerCase(), text: (el.innerText || el.alt || '').replace(/\s+/g, ' ').trim().slice(0, 120), x, y, w, h,
        src: el.currentSrc || el.src || undefined });
    }
    const videos = [...root.querySelectorAll('video, a[href]')].map(e => e.tagName === 'VIDEO' ? (e.currentSrc || e.src || e.querySelector('source')?.src) : e.href)
      .filter(u => u && /\.(mp4|webm|mov)(\?|$)|user-attachments\/assets|youtube\.com\/watch|youtu\.be\/|bilibili\.com\/video/i.test(u));
    return { root: [R.x, R.y + sy, R.width, R.height], blocks, videos: [...new Set(videos)] };
  }, sel);
  if (!info) throw new Error(`页面里没找到 ${sel}`);
  // 分段截：每段最多 2400 CSS px 高，段落尽量不切开
  const [rx, ry, rw, rh] = info.root, pad = 16, TILE = 2400;
  const cuts = [ry - pad]; let y = ry - pad;
  while (y + TILE < ry + rh + pad) {
    let c = y + TILE;
    const hit = info.blocks.find(b => b.y < c && b.y + b.h > c && b.h < TILE * 0.8);
    if (hit) c = hit.y - 8;
    cuts.push(c); y = c;
  }
  cuts.push(ry + rh + pad);
  const tiles = [];
  for (let i = 0; i < cuts.length - 1; i++) {
    const clip = { x: Math.max(0, rx - pad), y: cuts[i], width: rw + 2 * pad, height: cuts[i + 1] - cuts[i] };
    const png = path.join(out, `${name}_${String(i + 1).padStart(2, '0')}.png`);
    await page.screenshot({ path: png, clip, fullPage: true });
    tiles.push({ png, clip });
  }
  const riskyRaw = await page.evaluate(findRisky, sel);
  // --find "短语1|短语2"：每个短语在分图里的像素框(给 tl.spot 用，不用估字宽)
  const found = {};
  if (opt.find) {
    const hits = await page.evaluate(({ sel, words }) => {
      const root = sel.split(',').map(x => document.querySelector(x.trim())).find(Boolean) || document.body;
      const nodes = []; const w = document.createTreeWalker(root, NodeFilter.SHOW_TEXT); let n;
      while ((n = w.nextNode())) nodes.push(n);
      const full = nodes.map(n => n.textContent).join(''), res = {};
      const at = off => { let o = off; for (const n of nodes) { if (o <= n.textContent.length) return [n, o]; o -= n.textContent.length; } };
      for (const word of words) {
        const i = full.indexOf(word); if (i < 0) continue;
        const rg = document.createRange(); rg.setStart(...at(i)); rg.setEnd(...at(i + word.length));
        const rs = [...rg.getClientRects()].filter(r => r.width);
        res[word] = [Math.min(...rs.map(r => r.left)), Math.min(...rs.map(r => r.top)) + scrollY,
                     Math.max(...rs.map(r => r.right)), Math.max(...rs.map(r => r.bottom)) + scrollY];
      }
      return res;
    }, { sel, words: String(opt.find).split('|') });
    for (const [word, [x0, y0, x1, y1]] of Object.entries(hits)) {
      const t = tiles.find(t => y0 >= t.clip.y && y0 < t.clip.y + t.clip.height); if (!t) continue;
      found[word] = { tile: path.basename(t.png), box: [x0 - t.clip.x - 4, y0 - t.clip.y - 2, x1 - t.clip.x + 4, y1 - t.clip.y + 2].map(v => Math.round(v * DPR)) };
    }
    for (const word of String(opt.find).split('|')) if (!found[word]) console.error('find 没找到: ' + word);
  }
  const risky = [];
  for (const r of riskyRaw) for (const t of tiles) { // 可能跨两张分图，每张都记
    const c = t.clip, y0 = Math.max(r.y, c.y), y1 = Math.min(r.y + r.h, c.y + c.height);
    if (y1 <= y0) continue;
    risky.push({ tile: path.basename(t.png), why: r.why, text: r.text,
      box: [r.x - c.x, y0 - c.y, r.x - c.x + r.w, y1 - c.y].map(v => Math.round(v * DPR)) });
  }
  for (const b of info.blocks) { // 块 -> 所在分图的像素坐标
    const i = tiles.findIndex(t => b.y >= t.clip.y && b.y < t.clip.y + t.clip.height);
    if (i < 0) continue;
    const t = tiles[i].clip;
    b.tile = path.basename(tiles[i].png);
    b.box = [b.x - t.x, b.y - t.y, b.x - t.x + b.w, b.y - t.y + b.h].map(v => Math.round(v * DPR));
    delete b.x; delete b.y; delete b.w; delete b.h;
  }
  // 视频：查大小；--download 才下载(README 里的 mp4 是 5 分钟过期的签名链接，只能当场下)
  const videos = [];
  for (const [i, u] of info.videos.entries()) {
    const v = { url: u };
    if (!/youtu|bilibili/.test(u)) {
      const r = await page.request.head(u).catch(() => null);
      v.mb = r && +(+(r.headers()['content-length'] || 0) / 1048576).toFixed(1);
      if (opt.download) {
        const body = await (await page.request.get(u, { timeout: 300000 })).body();
        v.file = `${name}_video_${i + 1}.mp4`;
        fs.writeFileSync(path.join(out, v.file), body);
      }
    }
    videos.push(v);
  }
  await browser.close();
  info.videos = videos;
  const res = { url, tiles: tiles.map(t => path.basename(t.png)), videos, found, blocks: info.blocks, risky };
  fs.writeFileSync(path.join(out, `${name}.json`), JSON.stringify(res, null, 1));
  console.log(`${tiles.length} 张图 -> ${out}\\${name}_NN.png；${info.blocks.length} 个块；视频 ${info.videos.length} 个`);
  for (const v of videos) console.log(`  视频: ${v.mb != null ? v.mb + 'MB ' : ''}${v.file || ''} ${v.url.slice(0, 110)}`);
}

// ---------------------------------------------------------------- docs
async function cmdDocs(repo, out) {
  const { info, docs } = await api(repo);
  const md = (docs || []).filter(d => d.type === 'file' && /\.mdx?$/i.test(d.name)).map(d => d.html_url);
  const dirs = (docs || []).filter(d => d.type === 'dir').map(d => d.html_url);
  const res = { homepage: info?.homepage || null, default_branch: info?.default_branch, docs_md: md, docs_dirs: dirs };
  fs.writeFileSync(path.join(out, 'docs.json'), JSON.stringify(res, null, 2));
  console.log(JSON.stringify(res, null, 2));
}

const { pos, opt } = args(process.argv.slice(2));
const [cmd, target, out] = pos;
if (!cmd || !target || !out) { console.log(fs.readFileSync(new URL(import.meta.url), 'utf8').split('\n').slice(0, 13).join('\n')); process.exit(1); }
fs.mkdirSync(out, { recursive: true });
await ({ repo: cmdRepo, select: cmdSelect, page: cmdPage, docs: cmdDocs })[cmd](target, out, opt);
