import {spawnSync} from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

const root = path.dirname(fileURLToPath(import.meta.url));
const [specPath, outputPath, browserExecutable] = process.argv.slice(2);
if (!specPath || !outputPath || !browserExecutable) {
  throw new Error('usage: render-hyperframes.mjs <spec.json> <output.mp4> <browser>');
}
const spec = JSON.parse(fs.readFileSync(specPath, 'utf8'));
if (!fs.existsSync(browserExecutable)) throw new Error(`browser is missing: ${browserExecutable}`);
const project = path.join(path.dirname(path.resolve(specPath)), 'hyperframes');
fs.mkdirSync(project, {recursive: true});
fs.copyFileSync(path.join(root, 'node_modules', 'gsap', 'dist', 'gsap.min.js'), path.join(project, 'gsap.min.js'));
const projectAssets = path.join(project, 'assets');
fs.mkdirSync(projectAssets, {recursive: true});
const sourceRoot = path.dirname(path.resolve(specPath));
const safeVisuals = spec.visuals.map((visual, index) => {
  const source = path.resolve(sourceRoot, visual.file);
  if (source !== sourceRoot && !source.startsWith(`${sourceRoot}${path.sep}`)) {
    throw new Error(`visual path escapes scene sandbox: ${visual.file}`);
  }
  if (!fs.statSync(source).isFile()) throw new Error(`visual is missing: ${visual.file}`);
  const extension = path.extname(source).toLowerCase().replace(/[^.a-z0-9]/g, '');
  const file = `assets/visual-${String(index).padStart(3, '0')}${extension}`;
  fs.copyFileSync(source, path.join(project, file));
  return {...visual, file};
});

const esc = (value) => String(value).replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;');
const visualMarkup = safeVisuals.map((visual, index) => {
  const style = `object-fit:${visual.fit};opacity:${index === 0 ? 1 : Math.max(0.2, 0.58 - index * 0.1)}`;
  if (visual.mediaType === 'video') {
    return `<video id="visual-${index}" src="${esc(visual.file)}" muted preload="auto" style="${style}"></video>`;
  }
  return `<img id="visual-${index}" src="${esc(visual.file)}" style="${style}" />`;
}).join('');
const headline = spec.text.find((item) => item.role === 'headline') || spec.text[0];
const body = spec.text.find((item) => item.role !== 'headline') || spec.text[1];
const html = `<!doctype html>
<html><head><meta charset="utf-8"/><script src="./gsap.min.js"></script><style>
@font-face{font-family:"MOS CJK";src:local("PingFang SC"),local("Hiragino Sans GB")}*{box-sizing:border-box}html,body{margin:0;background:#08100e;overflow:hidden;font-family:"MOS CJK",sans-serif}#root{position:relative;overflow:hidden;background:#08100e;color:#fffaf0}.visuals,.shade,.grid{position:absolute;inset:0}.visuals>*{position:absolute;inset:0;width:100%;height:100%}.shade{background:linear-gradient(180deg,rgba(3,8,7,.08),rgba(3,8,7,.25) 43%,rgba(3,8,7,.95)),radial-gradient(circle at 76% 18%,#ff765c55,transparent 34%)}.grid{opacity:.14;background-image:linear-gradient(#ff765c66 1px,transparent 1px),linear-gradient(90deg,#ff765c66 1px,transparent 1px);background-size:90px 90px}.top{position:absolute;left:6%;right:6%;top:4%;display:flex;justify-content:space-between;font-size:22px;font-weight:750;letter-spacing:4px}.tag{padding:12px 18px;border:1px solid #ff765c99;border-radius:999px;background:#08100e66}.copy{position:absolute;left:6%;right:6%;bottom:10%}.eyebrow{color:#ff765c;font-size:24px;font-weight:800;letter-spacing:7px;margin-bottom:24px}.headline{font-size:96px;line-height:1.04;font-weight:900;letter-spacing:-3px;text-shadow:0 6px 34px #0006}.body{font-size:34px;line-height:1.55;font-weight:560;opacity:.84;margin-top:30px;max-width:88%}.progress{height:6px;margin-top:42px;background:#ffffff2e;overflow:hidden}.bar{height:100%;background:#ff765c;transform-origin:left;box-shadow:0 0 20px #ff765c}.wipe{position:absolute;inset:0;background:#ff765c;transform:translateX(-110%) skewX(-8deg)}
</style></head><body><div id="root" data-composition-id="main" data-start="0" data-duration="${Number(spec.duration)}" data-width="${Number(spec.canvas.width)}" data-height="${Number(spec.canvas.height)}" data-fps="${Number(spec.canvas.fps)}"><div class="visuals">${visualMarkup}</div><div class="shade"></div><div class="grid"></div><div class="top"><span class="tag">MARKETING OS</span><span>${esc(spec.purpose.slice(0, 36).toUpperCase())}</span></div><div class="copy"><div class="eyebrow">DESIGNED MOTION / LIVE</div>${headline ? `<div class="headline">${esc(headline.text)}</div>` : ''}${body ? `<div class="body">${esc(body.text)}</div>` : ''}<div class="progress"><div class="bar"></div></div></div><div class="wipe"></div></div><script>
window.__timelines=window.__timelines||{};const duration=${Number(spec.duration)};const wipeDuration=Math.min(.65,duration*.22);const tl=gsap.timeline({paused:true});tl.fromTo('.wipe',{xPercent:-110,opacity:1},{xPercent:115,duration:wipeDuration,ease:'power2.inOut'},0);tl.set('.wipe',{opacity:0},wipeDuration+.001);tl.fromTo('.copy',{opacity:0,y:70},{opacity:1,y:0,duration:Math.min(.8,duration*.3),ease:'power3.out'},Math.min(.18,duration*.08));tl.fromTo('.bar',{scaleX:0},{scaleX:1,duration:duration,ease:'none'},0);${spec.visuals.map((_, index) => `tl.fromTo('#visual-${index}',{scale:${1.04 + index * .01}},{scale:1.13,duration:duration,ease:'none'},0);`).join('')}tl.to('.copy',{opacity:0,y:-28,duration:Math.min(.45,duration*.15),ease:'power2.in'},Math.max(0,duration-Math.min(.45,duration*.15)));window.__timelines.main=tl;
</script></body></html>`;
fs.writeFileSync(path.join(project, 'index.html'), html);
fs.mkdirSync(path.dirname(path.resolve(outputPath)), {recursive: true});
const cli = path.join(root, 'node_modules', 'hyperframes', 'dist', 'cli.js');
const result = spawnSync(process.execPath, [cli, 'render', '--output', path.resolve(outputPath), '--workers', '1', '--quality', 'high', '--no-best-effort', '--strict', project], {
  cwd: root,
  env: {...process.env, PRODUCER_HEADLESS_SHELL_PATH: path.resolve(browserExecutable), HYPERFRAMES_SKIP_SKILLS: '1', NO_UPDATE_NOTIFIER: '1'},
  stdio: 'inherit',
});
if (result.error) throw result.error;
if (result.status !== 0) process.exit(result.status ?? 1);
