// Обучение: по очереди обводит кнопки и объясняет их, потом ведёт через первый ход.
// Когда партия обучения кончается, само начинает обычную игру. Игра сообщает о себе через tutorialRender.
import { t } from './i18n.js';

const $ = id => document.getElementById(id);
const STEPS = [
  { key: 'tutIntro' },
  { key: 'tutRules', target: () => $('rules') },
  { key: 'tutOpponent', target: () => $('opponent') },
  { key: 'tutStrategy', target: () => $('strategy') },
  { key: 'tutTheme', target: () => $('theme') },
  { key: 'tutDark', target: () => $('darkRes').parentNode },
  { key: 'tutLight', target: () => $('lightRes').parentNode },
  { key: 'tutBoard', target: () => $('board') },
  { key: 'tutUndo', target: () => $('undo') },
  { key: 'tutReset', target: () => $('reset') },
  { key: 'tutNextBtn', target: () => $('next') },
  { key: 'tutMenu', target: () => document.querySelector('.smGameMenu') },
  // Шаги с wait ждут действия игрока: нажимать можно только то, что перечислено в allow.
  { key: 'tutPick', target: () => $('lightRes'), allow: () => [$('lightRes')], wait: true },
  { key: 'tutPlace', target: () => $('board'), allow: () => [$('board'), $('lightRes')], wait: true }
];
const PICK = STEPS.length - 2, PLACE = STEPS.length - 1;
const PLAY = { key: 'tutPlay', ok: 'tutOk', free: true }, DONE = { key: 'tutDone', ok: 'tutPlayNow' };
const AUTO_MS = 4000;

let restart = null, cur = null, root = null, ring, tip, timer = 0;

function build() {
  root = document.createElement('div');
  root.className = 'coach';
  root.innerHTML = '<div class="coach__ring"></div><div class="coach__tip" role="dialog" tabindex="-1"><p class="coach__text" aria-live="polite"></p>'
    + '<div class="coach__bar"><span class="coach__count"></span><button type="button" class="coach__btn coach__btn--ghost" data-coach="skip"></button>'
    + '<button type="button" class="coach__btn coach__btn--main" data-coach="next"></button></div></div>';
  ring = root.firstChild; tip = root.lastChild;
  tip.addEventListener('click', e => {
    const b = e.target.closest('[data-coach]'); if (!b) return;
    if (b.dataset.coach === 'skip') stopTutorial(); else next();
  });
  document.body.appendChild(root);
}

function next() {
  if (cur === DONE) finish();
  else if (cur === PLAY) show(null);
  else show(STEPS[STEPS.indexOf(cur) + 1]);
}

function show(step) {
  cur = step;
  if (!step) { root.hidden = true; return; }
  root.hidden = false;
  tip.querySelector('.coach__text').textContent = t(step.key);
  const i = STEPS.indexOf(step);
  tip.querySelector('.coach__count').textContent = i >= 0 ? t('tutStep', { n: i + 1, total: STEPS.length }) : '';
  const skip = tip.querySelector('[data-coach="skip"]'), main = tip.querySelector('[data-coach="next"]');
  skip.textContent = t('tutSkip'); skip.hidden = i < 0;
  main.textContent = t(step.ok || 'tutGo'); main.hidden = !!step.wait;
  layout();
  if (!step.free) (main.hidden ? tip : main).focus({ preventScroll: true });
}

const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));

// Маленькую кнопку обводит эллипс вокруг неё, большую область — скруглённая рамка; подсказка встаёт с той стороны, где больше места.
function layout() {
  const el = cur.target && cur.target();
  root.classList.toggle('dim', !el && !cur.free);
  const w = Math.min(340, innerWidth - 24), gap = 10;
  tip.style.width = w + 'px';
  const h = tip.offsetHeight;
  let x = (innerWidth - w) / 2, y = cur.free ? 60 : (innerHeight - h) / 2;
  if (el) {
    const r = el.getBoundingClientRect(), small = r.width < 160 && r.height < 100;
    const rw = small ? r.width * 1.42 + 4 : r.width + 12, rh = small ? r.height * 1.42 + 4 : r.height + 12;
    const top = clamp(r.top + r.height / 2 - rh / 2, 2, innerHeight - rh - 2), left = clamp(r.left + r.width / 2 - rw / 2, 2, innerWidth - rw - 2);
    Object.assign(ring.style, { display: 'block', left: left + 'px', top: top + 'px', width: rw + 'px', height: rh + 'px', borderRadius: small ? '50%' : '18px' });
    x = r.left + r.width / 2 - w / 2;
    y = r.top + r.height / 2 < innerHeight / 2 ? top + rh + gap : top - gap - h;
  } else ring.style.display = 'none';
  tip.style.left = clamp(x, 12, innerWidth - w - 12) + 'px';
  tip.style.top = clamp(y, 12, innerHeight - h - 12) + 'px';
}

// Пока идёт объяснение, нажатия мимо подсказки и разрешённых мест до игры не доходят.
// Меню (оболочка) лежит поверх обучения и всегда остаётся нажимаемым.
window.addEventListener('click', e => {
  if (!cur || cur.free || tip.contains(e.target) || e.target.closest('#smProductShell')) return;
  if (cur.allow && cur.allow().some(n => n && n.contains(e.target))) return;
  e.preventDefault(); e.stopPropagation();
}, true);
// Игра подгоняет поле под окно в своём обработчике resize, поэтому замер — после него.
window.addEventListener('resize', () => setTimeout(() => { if (cur) layout(); }, 0));
window.addEventListener('sinee-more:lang', () => { if (cur) show(cur); });

function finish() { const r = restart; stopTutorial(); r(); }

export function startTutorial(newGame) {
  stopTutorial();
  newGame();
  restart = newGame;
  if (!root) build();
  show(STEPS[0]);
}

export function stopTutorial() {
  clearTimeout(timer);
  restart = null;
  if (root) show(null);
}

// Вызывается после каждой перерисовки игры: продвигает обучение по действиям игрока.
export function tutorialRender(game) {
  if (!restart) return;
  if (cur === STEPS[PICK] && game.sel !== null) show(STEPS[PLACE]);
  else if (cur === STEPS[PLACE]) show(game.moved ? PLAY : game.sel === null ? STEPS[PICK] : cur);
  else if (cur === PLAY && game.sel !== null) show(null);
  if (game.over && cur !== DONE) { show(DONE); timer = setTimeout(finish, AUTO_MS); }
  else if (cur) layout();
}
