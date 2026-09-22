/* Синее море Stage 1 AppShell — presentation/navigation only. D2 gameplay is intentionally untouched. */
(() => {
  'use strict';

  const STORAGE_KEY = 'sineeMore.productConfig.v1';
  const DEFAULT_CONFIG = Object.freeze({
    environmentId: 'atlantis',
    pieceSetId: 'atlantis',
    mode: 'ai',
    difficulty: 'hard',
    sound: false,
    haptics: true,
    reducedMotion: false
  });

  const CATALOG = Object.freeze({
    environments: Object.freeze({
      atlantis: Object.freeze({ id: 'atlantis', label: 'Атлантида', compatiblePieceSets: ['atlantis'] })
    }),
    pieceSets: Object.freeze({
      atlantis: Object.freeze({ id: 'atlantis', label: 'Атлантида', compatibleEnvironments: ['atlantis'] })
    })
  });

  function safeParse(value) {
    try { return JSON.parse(value); } catch (_) { return null; }
  }

  function normalizeConfig(candidate) {
    const next = { ...DEFAULT_CONFIG, ...(candidate && typeof candidate === 'object' ? candidate : {}) };
    if (!CATALOG.environments[next.environmentId]) next.environmentId = DEFAULT_CONFIG.environmentId;
    if (!CATALOG.pieceSets[next.pieceSetId]) next.pieceSetId = DEFAULT_CONFIG.pieceSetId;
    const env = CATALOG.environments[next.environmentId];
    if (!env.compatiblePieceSets.includes(next.pieceSetId)) {
      next.pieceSetId = env.compatiblePieceSets[0] || DEFAULT_CONFIG.pieceSetId;
    }
    return next;
  }

  function loadConfig() {
    return normalizeConfig(safeParse(localStorage.getItem(STORAGE_KEY)));
  }

  function saveConfig(next) {
    const normalized = normalizeConfig(next);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(normalized));
    return normalized;
  }

  function ensureStyles() {
    if (document.getElementById('sm-shell-style')) return;
    const style = document.createElement('style');
    style.id = 'sm-shell-style';
    style.textContent = `
      .smShell{position:fixed;inset:0;z-index:100;background:#020303;color:#f2f2f0;display:flex;align-items:center;justify-content:center;padding:max(18px,env(safe-area-inset-top)) 18px max(18px,env(safe-area-inset-bottom));font-family:Arial,Helvetica,sans-serif}
      .smShell[hidden]{display:none}.smShell__panel{width:min(100%,430px);display:flex;flex-direction:column;gap:12px}.smShell__title{margin:0 0 10px;text-align:center;color:#d44740;font:700 clamp(34px,11vw,52px)/1 Georgia,serif;letter-spacing:1.5px}.smShell__subtitle{text-align:center;color:#a9aaa8;font-size:13px;margin:-4px 0 8px}.smShell__button{min-height:52px;border:1px solid rgba(242,242,240,.55);border-radius:12px;background:#090a0a;color:#f2f2f0;font:800 15px Arial;padding:12px}.smShell__button--primary{border-color:rgba(255,255,255,.9);background:#111}.smShell__button:focus-visible{outline:2px solid #fff;outline-offset:2px}.smShell__row{display:grid;grid-template-columns:1fr 1fr;gap:9px}.smShell__view{display:none}.smShell__view.isActive{display:flex;flex-direction:column;gap:10px}.smShell__copy{color:#c2c3c1;font-size:14px;line-height:1.45}.smShell__select{width:100%;min-height:48px;background:#090a0a;color:#f2f2f0;border:1px solid rgba(242,242,240,.45);border-radius:10px;padding:8px}.smShell__label{font-size:12px;color:#a9aaa8;margin-top:4px}.smShell__back{margin-top:6px}.smGameMenu{position:fixed;z-index:90;top:max(8px,env(safe-area-inset-top));right:9px;min-width:44px;min-height:44px;border:1px solid rgba(242,242,240,.55);border-radius:10px;background:rgba(5,6,6,.9);color:#f2f2f0;font-weight:900}.smGameplayHidden{visibility:hidden;pointer-events:none}
    `;
    document.head.appendChild(style);
  }

  function buildShell() {
    const shell = document.createElement('section');
    shell.id = 'smProductShell';
    shell.className = 'smShell';
    shell.setAttribute('aria-label', 'Главное меню');
    shell.innerHTML = `
      <div class="smShell__panel">
        <section class="smShell__view isActive" data-view="menu">
          <h1 class="smShell__title">СИНЕЕ МОРЕ</h1>
          <p class="smShell__subtitle">Стратегическая игра</p>
          <button class="smShell__button smShell__button--primary" data-action="start">Начать игру</button>
          <button class="smShell__button" data-action="settings">Настройки</button>
          <div class="smShell__row"><button class="smShell__button" data-action="rules">Правила</button><button class="smShell__button" data-action="tutorial">Обучение</button></div>
          <button class="smShell__button" data-action="support">Поддержать проект</button>
        </section>
        <section class="smShell__view" data-view="settings">
          <h2>Настройки</h2>
          <label class="smShell__label" for="smEnvironment">Окружение / поле</label><select class="smShell__select" id="smEnvironment"></select>
          <label class="smShell__label" for="smPieces">Фигуры</label><select class="smShell__select" id="smPieces"></select>
          <button class="smShell__button smShell__back" data-action="back">Назад</button>
        </section>
        <section class="smShell__view" data-view="rules"><h2>Правила</h2><p class="smShell__copy">Ставьте фигуры на свободные клетки или накрывайте меньшие фигуры большими. Побеждает сторона, первой собравшая три свои верхние фигуры в ряд.</p><button class="smShell__button smShell__back" data-action="back">Назад</button></section>
        <section class="smShell__view" data-view="tutorial"><h2>Обучение</h2><p class="smShell__copy">Короткое интерактивное обучение будет подключено отдельным продуктовым этапом. Stage 1 сохраняет место и навигационный контракт без вмешательства в D2.</p><button class="smShell__button smShell__back" data-action="back">Назад</button></section>
        <section class="smShell__view" data-view="support"><h2>Поддержать проект</h2><p class="smShell__copy">Nameless Dhamma развивается на пожертвования. Платёжный маршрут будет подключён только после проверки требований Google Play.</p><button class="smShell__button smShell__back" data-action="back">Назад</button></section>
      </div>`;
    document.body.appendChild(shell);
    return shell;
  }

  function setView(shell, name) {
    shell.querySelectorAll('[data-view]').forEach(el => el.classList.toggle('isActive', el.dataset.view === name));
    shell.setAttribute('aria-label', name === 'menu' ? 'Главное меню' : name);
  }

  function fillSelect(select, records, selectedId) {
    select.textContent = '';
    Object.values(records).forEach(item => {
      const option = document.createElement('option'); option.value = item.id; option.textContent = item.label; option.selected = item.id === selectedId; select.appendChild(option);
    });
  }

  function init() {
    if (document.getElementById('smProductShell')) return;
    ensureStyles();
    let config = loadConfig();
    const gameRoot = document.querySelector('.app');
    const shell = buildShell();
    const menuButton = document.createElement('button');
    menuButton.className = 'smGameMenu'; menuButton.type = 'button'; menuButton.textContent = '☰'; menuButton.setAttribute('aria-label', 'Меню'); document.body.appendChild(menuButton);
    const environment = shell.querySelector('#smEnvironment'); const pieces = shell.querySelector('#smPieces');
    const syncControls = () => { fillSelect(environment, CATALOG.environments, config.environmentId); fillSelect(pieces, CATALOG.pieceSets, config.pieceSetId); };
    const openMenu = () => { shell.hidden = false; if (gameRoot) gameRoot.classList.add('smGameplayHidden'); setView(shell, 'menu'); };
    const startGame = () => { config = saveConfig(config); shell.hidden = true; if (gameRoot) gameRoot.classList.remove('smGameplayHidden'); window.dispatchEvent(new CustomEvent('sinee-more:product-config', { detail: config })); };
    syncControls(); openMenu();
    shell.addEventListener('click', event => { const action = event.target.closest('[data-action]')?.dataset.action; if (!action) return; if (action === 'start') return startGame(); if (action === 'back') return setView(shell, 'menu'); setView(shell, action); });
    environment.addEventListener('change', () => { config = saveConfig({ ...config, environmentId: environment.value }); syncControls(); });
    pieces.addEventListener('change', () => { config = saveConfig({ ...config, pieceSetId: pieces.value }); syncControls(); });
    menuButton.addEventListener('click', openMenu);
    window.SineeMoreAppShell = Object.freeze({ loadConfig, saveConfig, normalizeConfig, catalog: CATALOG, openMenu, startGame });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, { once: true }); else init();
})();
