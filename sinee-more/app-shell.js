/* Синее море Stage 1 AppShell — presentation/navigation only. D2 gameplay is intentionally untouched. */
import { LANGS, getLang, setLang, applyStatic, t } from './i18n.js';

(() => {
  'use strict';

  const STORAGE_KEY = 'sineeMore.productConfig.v1';
  const DEFAULT_CONFIG = Object.freeze({
    environmentId: 'atlantis',
    mode: 'ai',
    difficulty: 'hard',
    sound: false,
    haptics: true,
    reducedMotion: false
  });

  // Тема задаёт и поле, и фигуры; названия тем не переводятся.
  const CATALOG = Object.freeze({
    environments: Object.freeze({
      nd: Object.freeze({ id: 'nd', label: 'ND Premium' }),
      pirate: Object.freeze({ id: 'pirate', label: 'Pirate Chart' }),
      atlantis: Object.freeze({ id: 'atlantis', label: 'Atlantis' })
    })
  });

  function safeParse(value) {
    try { return JSON.parse(value); } catch (_) { return null; }
  }

  function normalizeConfig(candidate) {
    const next = { ...DEFAULT_CONFIG, ...(candidate && typeof candidate === 'object' ? candidate : {}) };
    if (!CATALOG.environments[next.environmentId]) next.environmentId = DEFAULT_CONFIG.environmentId;
    return next;
  }

  // Без сохранённых настроек меню берёт тему, выбранную раньше в самой игре.
  function loadConfig() {
    try { return normalizeConfig(safeParse(localStorage.getItem(STORAGE_KEY)) || { environmentId: localStorage.getItem('sinee-more-theme') }); }
    catch (_) { return normalizeConfig(null); }
  }

  function saveConfig(next) {
    const normalized = normalizeConfig(next);
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify(normalized)); } catch (_) {}
    return normalized;
  }

  function ensureStyles() {
    if (document.getElementById('sm-shell-style')) return;
    const style = document.createElement('style');
    style.id = 'sm-shell-style';
    style.textContent = `
      .smShell{position:fixed;inset:0;z-index:100;background:#020303;color:#f2f2f0;display:flex;align-items:center;justify-content:center;padding:calc(max(10px,env(safe-area-inset-top)) + 54px) 18px max(18px,env(safe-area-inset-bottom));font-family:Arial,Helvetica,sans-serif}
      .smShell[hidden]{display:none}.smShell__panel{width:min(100%,430px);max-height:100%;overflow-x:hidden;overflow-y:auto;padding:4px;display:flex;flex-direction:column;gap:12px}.smShell__copy{margin:0}.smShell__rules{padding:0;list-style:none;display:flex;flex-direction:column;gap:9px}.smShell__rules b{display:block;color:#f2f2f0}.smShell__title{margin:0 0 10px;text-align:center;color:#d44740;font:700 clamp(34px,11vw,52px)/1 Georgia,serif;letter-spacing:1.5px}.smShell__subtitle{text-align:center;color:#a9aaa8;font-size:13px;margin:-4px 0 8px}.smShell__button{min-height:52px;border:1px solid rgba(242,242,240,.55);border-radius:12px;background:#090a0a;color:#f2f2f0;font:800 15px Arial;padding:12px}.smShell__button--primary{border-color:rgba(255,255,255,.9);background:#111}.smShell__button:focus-visible{outline:2px solid #fff;outline-offset:2px}.smShell__row{display:grid;grid-template-columns:1fr 1fr;gap:9px}.smShell__view{display:none}.smShell__view.isActive{display:flex;flex-direction:column;gap:10px}.smShell__copy{color:#c2c3c1;font-size:14px;line-height:1.45}.smShell__select{width:100%;min-height:48px;background:#090a0a;color:#f2f2f0;border:1px solid rgba(242,242,240,.45);border-radius:10px;padding:8px}.smShell__label{font-size:12px;color:#a9aaa8;margin-top:4px}.smShell__back{margin-top:6px}.smGameMenu{position:fixed;z-index:90;top:max(8px,env(safe-area-inset-top));right:9px;min-width:44px;min-height:44px;border:1px solid rgba(242,242,240,.55);border-radius:10px;background:rgba(5,6,6,.9);color:#f2f2f0;font-weight:900}.smGameplayHidden{visibility:hidden;pointer-events:none}
      .smShell__lang{position:absolute;z-index:2;top:max(10px,env(safe-area-inset-top));right:12px}.smShell__globe{min-width:44px;min-height:44px;display:flex;align-items:center;gap:6px;padding:0 11px;border:1px solid rgba(242,242,240,.55);border-radius:22px;background:rgba(9,10,10,.9);color:#f2f2f0;font:700 12px Arial;letter-spacing:.6px}.smShell__langs{position:absolute;right:0;top:calc(100% + 6px);min-width:160px;padding:6px;border:1px solid rgba(242,242,240,.45);border-radius:12px;background:#090a0a;box-shadow:0 8px 24px rgba(0,0,0,.6)}.smShell__langs[hidden]{display:none}.smShell__langItem{display:flex;align-items:center;justify-content:space-between;gap:12px;width:100%;min-height:44px;padding:0 12px;border:0;border-radius:8px;background:transparent;color:inherit;font:600 15px Arial;text-align:left}.smShell__langItem[aria-checked="true"]:after{content:"✓";font-weight:900}.smShell__langItem:hover,.smShell__langItem:focus-visible{background:rgba(255,255,255,.1)}
    `;
    document.head.appendChild(style);
  }

  function buildShell() {
    const shell = document.createElement('section');
    shell.id = 'smProductShell';
    shell.className = 'smShell';
    shell.innerHTML = `
      <div class="smShell__lang">
        <button class="smShell__globe" type="button" aria-haspopup="true" aria-expanded="false" data-i18n-aria="language"><svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c2.6 2.6 3.9 5.6 3.9 9s-1.3 6.4-3.9 9c-2.6-2.6-3.9-5.6-3.9-9S9.4 5.6 12 3z"/></svg><span class="smShell__code"></span></button>
        <div class="smShell__langs" role="menu" hidden></div>
      </div>
      <div class="smShell__panel">
        <section class="smShell__view isActive" data-view="menu">
          <h1 class="smShell__title" data-i18n="title"></h1>
          <p class="smShell__subtitle" data-i18n="subtitle"></p>
          <button class="smShell__button smShell__button--primary" data-action="start" data-i18n="start"></button>
          <button class="smShell__button" data-action="settings" data-i18n="settings"></button>
          <div class="smShell__row"><button class="smShell__button" data-action="rules" data-i18n="rules"></button><button class="smShell__button" data-action="tutorial" data-i18n="tutorial"></button></div>
          <button class="smShell__button" data-action="support" data-i18n="support"></button>
        </section>
        <section class="smShell__view" data-view="settings">
          <h2 data-i18n="settings"></h2>
          <label class="smShell__label" for="smEnvironment" data-i18n="theme"></label><select class="smShell__select" id="smEnvironment"></select>
          <label class="smShell__label" for="smLang" data-i18n="language"></label><select class="smShell__select" id="smLang"></select>
          <button class="smShell__button smShell__back" data-action="back" data-i18n="back"></button>
        </section>
        <section class="smShell__view" data-view="rules"><h2 data-i18n="rules"></h2><p class="smShell__copy" data-i18n="rulesText"></p><p class="smShell__copy" data-i18n="rulesExtra"></p>
          <ul class="smShell__copy smShell__rules"><li><b data-i18n="valC"></b><span data-i18n="ruleCText"></span></li><li><b data-i18n="valD"></b><span data-i18n="ruleDText"></span></li><li><b data-i18n="valCD"></b><span data-i18n="ruleCDText"></span></li></ul><button class="smShell__button smShell__back" data-action="back" data-i18n="back"></button></section>
        <section class="smShell__view" data-view="support"><h2 data-i18n="support"></h2><p class="smShell__copy" data-i18n="supportText"></p><button class="smShell__button smShell__back" data-action="back" data-i18n="back"></button></section>
      </div>`;
    document.body.appendChild(shell);
    return shell;
  }

  let view = 'menu';
  function setView(shell, name) {
    view = name;
    shell.querySelectorAll('[data-view]').forEach(el => el.classList.toggle('isActive', el.dataset.view === name));
    shell.setAttribute('aria-label', t(name === 'menu' ? 'mainMenu' : name));
  }

  // Глобус в углу: список языков, текущий отмечен галочкой.
  function fillLangs(box, code) {
    box.textContent = '';
    Object.keys(LANGS).forEach(id => {
      const item = document.createElement('button');
      item.type = 'button'; item.className = 'smShell__langItem'; item.setAttribute('role', 'menuitemradio');
      item.setAttribute('aria-checked', String(id === getLang())); item.dataset.lang = id; item.textContent = LANGS[id];
      box.appendChild(item);
    });
    code.textContent = getLang().toUpperCase();
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
    menuButton.className = 'smGameMenu'; menuButton.type = 'button'; menuButton.textContent = '☰'; menuButton.dataset.i18nAria = 'menu'; document.body.appendChild(menuButton);
    const environment = shell.querySelector('#smEnvironment'); const language = shell.querySelector('#smLang');
    const languages = Object.keys(LANGS).map(id => ({ id, label: LANGS[id] }));
    const globe = shell.querySelector('.smShell__globe'); const langs = shell.querySelector('.smShell__langs');
    const syncControls = () => { fillSelect(environment, CATALOG.environments, config.environmentId); fillSelect(language, languages, getLang()); fillLangs(langs, globe.querySelector('.smShell__code')); };
    const showLangs = open => { langs.hidden = !open; globe.setAttribute('aria-expanded', String(open)); if (open) langs.querySelector('[aria-checked="true"]').focus(); };
    // Тему могли сменить в игре (кнопка «Тема»), поэтому настройки перечитываются при каждом открытии меню.
    const openMenu = () => { config = loadConfig(); syncControls(); shell.hidden = false; if (gameRoot) gameRoot.classList.add('smGameplayHidden'); setView(shell, 'menu'); };
    const startGame = () => { config = saveConfig(config); showLangs(false); shell.hidden = true; if (gameRoot) gameRoot.classList.remove('smGameplayHidden'); window.dispatchEvent(new CustomEvent('sinee-more:product-config', { detail: config })); };
    applyStatic(); openMenu();
    shell.addEventListener('click', event => {
      const lang = event.target.closest('[data-lang]');
      if (lang) { setLang(lang.dataset.lang); showLangs(false); globe.focus(); return; }
      if (event.target.closest('.smShell__globe')) return showLangs(langs.hidden);
      showLangs(false);
      const action = event.target.closest('[data-action]')?.dataset.action; if (!action) return;
      if (action === 'start') return startGame();
      if (action === 'tutorial') { startGame(); return window.dispatchEvent(new CustomEvent('sinee-more:tutorial')); }
      if (action === 'back') return setView(shell, 'menu');
      setView(shell, action);
    });
    shell.addEventListener('keydown', event => { if (event.key === 'Escape' && !langs.hidden) { showLangs(false); globe.focus(); } });
    // Тема применяется сразу, поэтому и само меню перекрашивается в выбранную тему.
    environment.addEventListener('change', () => { config = saveConfig({ ...config, environmentId: environment.value }); window.dispatchEvent(new CustomEvent('sinee-more:product-config', { detail: config })); });
    language.addEventListener('change', () => setLang(language.value));
    window.addEventListener('sinee-more:lang', () => { syncControls(); setView(shell, view); });
    menuButton.addEventListener('click', openMenu);
    window.SineeMoreAppShell = Object.freeze({ loadConfig, saveConfig, normalizeConfig, catalog: CATALOG, openMenu, startGame });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, { once: true }); else init();
})();
