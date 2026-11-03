// Тексты игры на трёх языках. Статичные тексты в разметке помечены data-i18n (текст) и data-i18n-aria (aria-label);
// setLang переводит их и посылает событие 'sinee-more:lang', по которому игра перерисовывает свои строки.
export const LANGS = { en: 'English', ru: 'Русский', th: 'ไทย' };
const KEY = 'sinee-more-lang';

const T = {
  ru: {
    title: 'СИНЕЕ МОРЕ', subtitle: 'Стратегическая игра', mainMenu: 'Главное меню', menu: 'Меню',
    start: 'Начать игру', settings: 'Настройки', rules: 'Правила', tutorial: 'Обучение', support: 'Поддержать проект',
    theme: 'Тема', language: 'Язык', back: 'Назад',
    rulesText: 'Ставьте фигуры на свободные клетки или накрывайте меньшие фигуры соперника большими. Побеждает тот, кто первым соберёт три свои верхние фигуры в ряд.',
    rulesExtra: 'Всегда действует одно из правил ниже, сначала — C. Выбрать его можно в игре, на карточке «Правила игры»:',
    supportText: 'Nameless Dhamma развивается на пожертвования. Способ пожертвовать появится после проверки требований Google Play.',
    gameSettings: 'Настройки игры', cardRules: 'Правила игры', cardOpponent: 'С кем играть', cardStrategy: 'Стратегия ИИ', cardTheme: 'Тема',
    currentTurn: 'Текущий ход', board: 'Игровое поле', light: 'СВЕТЛЫЕ', dark: 'ТЁМНЫЕ',
    undo: 'НАЗАД', reset: 'СБРОС', next: 'СЛЕДУЮЩАЯ', close: 'ЗАКРЫТЬ',
    rulesTitle: 'ПРАВИЛА ИГРЫ',
    ruleC: 'C · СТЕК 2', ruleCText: 'В клетке не больше двух фигур: накрыть можно только один раз, потом клетка закрыта.',
    ruleD: 'D · ЛЕСТНИЦА', ruleDText: 'Числа верхних фигур в ряду идут по порядку, как ступеньки, — растут или убывают от края к краю. 1‑4‑9 или 8‑5‑2 — победа, 3‑7‑5 — нет.',
    ruleCD: 'CD · СТЕК 2 + ЛЕСТНИЦА', ruleCDText: 'Оба правила одновременно.',
    moveText: 'Ход: выберите неиспользованную фигуру и поставьте её на пустую клетку либо накройте меньшую верхнюю фигуру соперника. Свою фигуру накрывать нельзя.',
    opponentTitle: 'С КЕМ ИГРАТЬ',
    oppTwo: 'ДРУГОЙ ИГРОК', oppTwoText: 'Игра вдвоём на одном устройстве.',
    oppEasy: 'ИИ · ЛЁГКИЙ', oppEasyText: 'Живой соперник, который допускает заметные ошибки.',
    oppMedium: 'ИИ · СРЕДНИЙ', oppMediumText: 'Тактически устойчивый соперник с умеренной глубиной расчёта.',
    oppHard: 'ИИ · СЛОЖНЫЙ', oppHardText: 'Глубже считает варианты и избегает грубых промахов.',
    strategyTitle: 'СТРАТЕГИЯ ИИ',
    mixed: 'СМЕШАННАЯ', mixedText: 'В каждой партии новый характер соперника.',
    architect: 'АРХИТЕКТОР', architectText: 'Строит долгие комбинации и гибкие лестницы.',
    hunter: 'ОХОТНИК', hunterText: 'Давит, накрывает и быстро создаёт угрозы.',
    sentinel: 'СТРАЖ', sentinelText: 'Экономит сильные фигуры и разрушает ваши планы.',
    trickster: 'ЛОВКАЧ', tricksterText: 'Ищет вилки, неожиданные линии и менее очевидные ходы.',
    themeTitle: 'ТЕМА',
    ndText: 'Чёрное поле, нейтральные серебряные лучи и тёплое/холодное серебро фигур.',
    pirateText: 'Стол капитана, карта архипелага, пергаментное поле и кожаные пиратские фигуры.',
    atlantisText: 'Затонувший храмовый город, каменные платформы, светящиеся водяные каналы и ступенчатые пирамиды.',
    valTwo: 'Другой игрок', valAi: 'ИИ · {level}', easy: 'лёгкий', medium: 'средний', hard: 'сложный',
    valC: 'C · стек 2', valD: 'D · лестница', valCD: 'CD · стек 2 + лестница',
    valMixed: 'Смешанная', valArchitect: 'Архитектор', valHunter: 'Охотник', valSentinel: 'Страж', valTrickster: 'Ловкач',
    cell: 'Клетка {n}', empty: 'пусто', piece: '{side} · фигура {r}',
    thinking: 'Компьютер думает…', turn: 'ХОД: {side}', draw: 'НИЧЬЯ', win: '{side} ПОБЕДИЛИ',
    computer: 'КОМПЬЮТЕР · {name}', you: 'ВЫ', computerTurn: 'Ход компьютера.', pick: '{side}: выберите размер.',
    moves: 'Ходов: {n}', over: 'Партия завершена.', resetConfirm: 'Сбросить текущую партию?',
    tutIntro: 'Короткое обучение: покажу, что значит каждая кнопка и как сделать ход.',
    tutRules: 'Правила. C — в клетке не больше двух фигур. D — побеждает только ряд, где числа растут или убывают: 1‑4‑9. CD — оба правила.',
    tutOpponent: 'С кем играть: с другом на этом устройстве или с ИИ — лёгким, средним или сложным.',
    tutStrategy: 'Стратегия ИИ: характер компьютера, то есть как он будет играть.',
    tutTheme: 'Тема: вид поля и фигур.',
    tutDark: 'Фигуры тёмных. В игре с ИИ ими ходит компьютер.',
    tutLight: 'Ваши фигуры, от 1 до 9. Каждую можно поставить один раз.',
    tutBoard: 'Поле. Ставьте фигуру на пустую клетку или накрывайте меньшую фигуру соперника. Три ваши верхние фигуры в ряд — победа.',
    tutUndo: 'Назад: отменить последний ход.', tutReset: 'Сброс: начать партию заново.',
    tutNextBtn: 'Следующая: новая партия, когда эта закончится.', tutMenu: 'Меню: настройки, язык и правила.',
    tutPick: 'Ваш ход. Нажмите на любую свою фигуру.', tutPlace: 'Теперь нажмите на подсвеченную клетку.',
    tutPlay: 'Отлично! Доиграйте партию, потом начнётся обычная игра.', tutDone: 'Обучение пройдено! Начинаем обычную игру.',
    tutGo: 'Далее', tutSkip: 'Пропустить', tutOk: 'Понятно', tutPlayNow: 'Играть', tutStep: '{n} из {total}'
  },
  en: {
    title: 'BLUE SEA', subtitle: 'A strategy game', mainMenu: 'Main menu', menu: 'Menu',
    start: 'Start game', settings: 'Settings', rules: 'Rules', tutorial: 'Tutorial', support: 'Support the project',
    theme: 'Theme', language: 'Language', back: 'Back',
    rulesText: 'Place pieces on empty cells or cover smaller enemy pieces with bigger ones. The first to line up three of their top pieces wins.',
    rulesExtra: 'One of the rules below is always on, C at first. You can pick it in the game, on the “Rules” card:',
    supportText: 'Nameless Dhamma lives on donations. A way to donate will appear once the Google Play requirements are checked.',
    gameSettings: 'Game settings', cardRules: 'Rules', cardOpponent: 'Opponent', cardStrategy: 'AI style', cardTheme: 'Theme',
    currentTurn: 'Current turn', board: 'Game board', light: 'LIGHT', dark: 'DARK',
    undo: 'UNDO', reset: 'RESET', next: 'NEXT', close: 'CLOSE',
    rulesTitle: 'GAME RULES',
    ruleC: 'C · STACK 2', ruleCText: 'At most two pieces per cell: a piece can be covered only once, then the cell is closed.',
    ruleD: 'D · LADDER', ruleDText: 'The top numbers in the line go in order like steps, rising or falling from end to end. 1‑4‑9 or 8‑5‑2 wins, 3‑7‑5 does not.',
    ruleCD: 'CD · STACK 2 + LADDER', ruleCDText: 'Both rules at once.',
    moveText: 'On your turn, pick an unused piece and place it on an empty cell, or cover a smaller top piece of your opponent. You cannot cover your own piece.',
    opponentTitle: 'OPPONENT',
    oppTwo: 'ANOTHER PLAYER', oppTwoText: 'Two players on one device.',
    oppEasy: 'AI · EASY', oppEasyText: 'A lively opponent that makes noticeable mistakes.',
    oppMedium: 'AI · MEDIUM', oppMediumText: 'A tactically solid opponent that looks a few moves ahead.',
    oppHard: 'AI · HARD', oppHardText: 'Calculates deeper and avoids blunders.',
    strategyTitle: 'AI STYLE',
    mixed: 'MIXED', mixedText: 'A new opponent character every game.',
    architect: 'ARCHITECT', architectText: 'Builds long combinations and flexible ladders.',
    hunter: 'HUNTER', hunterText: 'Presses, covers your pieces and creates threats fast.',
    sentinel: 'SENTINEL', sentinelText: 'Saves its strong pieces and breaks your plans.',
    trickster: 'TRICKSTER', tricksterText: 'Looks for forks, unexpected lines and less obvious moves.',
    themeTitle: 'THEME',
    ndText: 'A black board, neutral silver rays, warm and cool silver pieces.',
    pirateText: "The captain's table, an archipelago chart, a parchment board and leather pirate pieces.",
    atlantisText: 'A sunken temple city, stone platforms, glowing water channels and stepped pyramids.',
    valTwo: 'Another player', valAi: 'AI · {level}', easy: 'easy', medium: 'medium', hard: 'hard',
    valC: 'C · stack 2', valD: 'D · ladder', valCD: 'CD · stack 2 + ladder',
    valMixed: 'Mixed', valArchitect: 'Architect', valHunter: 'Hunter', valSentinel: 'Sentinel', valTrickster: 'Trickster',
    cell: 'Cell {n}', empty: 'empty', piece: '{side} · piece {r}',
    thinking: 'The computer is thinking…', turn: 'TURN: {side}', draw: 'DRAW', win: '{side} WINS',
    computer: 'COMPUTER · {name}', you: 'YOU', computerTurn: "Computer's turn.", pick: '{side}: choose a size.',
    moves: 'Moves: {n}', over: 'Game over.', resetConfirm: 'Reset the current game?',
    tutIntro: 'A quick tour: what each button does and how to make a move.',
    tutRules: 'Rules. C: at most two pieces per cell. D: only a line whose numbers rise or fall wins: 1‑4‑9. CD: both.',
    tutOpponent: 'Opponent: a friend on this device, or the AI at easy, medium or hard.',
    tutStrategy: "AI style: the computer's character, that is, how it plays.",
    tutTheme: 'Theme: the look of the board and pieces.',
    tutDark: 'Dark pieces. Against the AI, the computer plays them.',
    tutLight: 'Your pieces, 1 to 9. Each one can be placed once.',
    tutBoard: 'The board. Place a piece on an empty cell or cover a smaller enemy piece. Three of your top pieces in a row wins.',
    tutUndo: 'Undo: take back the last move.', tutReset: 'Reset: start this game over.',
    tutNextBtn: 'Next: a new game once this one ends.', tutMenu: 'Menu: settings, language and rules.',
    tutPick: 'Your turn. Tap any of your pieces.', tutPlace: 'Now tap a highlighted cell.',
    tutPlay: 'Well done! Finish this game, then a regular game begins.', tutDone: 'Tutorial complete! Starting a regular game.',
    tutGo: 'Next', tutSkip: 'Skip', tutOk: 'Got it', tutPlayNow: 'Play', tutStep: '{n} of {total}'
  },
  th: {
    title: 'ทะเลสีคราม', subtitle: 'เกมวางแผน', mainMenu: 'เมนูหลัก', menu: 'เมนู',
    start: 'เริ่มเกม', settings: 'ตั้งค่า', rules: 'กติกา', tutorial: 'บทเรียน', support: 'สนับสนุนโครงการ',
    theme: 'ธีม', language: 'ภาษา', back: 'กลับ',
    rulesText: 'วางหมากบนช่องว่าง หรือวางหมากที่ใหญ่กว่าทับหมากของฝ่ายตรงข้ามที่เล็กกว่า ใครเรียงหมากบนสุดของตนได้สามตัวในแถวเดียวก่อนเป็นผู้ชนะ',
    rulesExtra: 'จะใช้กติกาข้อใดข้อหนึ่งด้านล่างเสมอ เริ่มต้นคือ C เลือกได้ในเกมที่การ์ด “กติกา”:',
    supportText: 'Nameless Dhamma ดำเนินงานด้วยเงินบริจาค ช่องทางบริจาคจะเปิดหลังจากตรวจสอบข้อกำหนดของ Google Play แล้ว',
    gameSettings: 'ตั้งค่าเกม', cardRules: 'กติกา', cardOpponent: 'คู่แข่ง', cardStrategy: 'สไตล์ AI', cardTheme: 'ธีม',
    currentTurn: 'ตาปัจจุบัน', board: 'กระดาน', light: 'ฝ่ายสว่าง', dark: 'ฝ่ายมืด',
    undo: 'ย้อน', reset: 'เริ่มใหม่', next: 'เกมถัดไป', close: 'ปิด',
    rulesTitle: 'กติกาการเล่น',
    ruleC: 'C · ซ้อน 2', ruleCText: 'ช่องหนึ่งมีหมากได้ไม่เกินสองตัว ทับได้เพียงครั้งเดียว จากนั้นช่องจะปิด',
    ruleD: 'D · บันได', ruleDText: 'ตัวเลขของหมากบนสุดในแถวต้องเรียงกันเหมือนขั้นบันได เพิ่มขึ้นหรือลดลงจากปลายหนึ่งไปอีกปลายหนึ่ง 1‑4‑9 หรือ 8‑5‑2 ชนะ แต่ 3‑7‑5 ไม่ชนะ',
    ruleCD: 'CD · ซ้อน 2 + บันได', ruleCDText: 'ใช้ทั้งสองกติกาพร้อมกัน',
    moveText: 'การเดิน: เลือกหมากที่ยังไม่ได้ใช้ แล้ววางบนช่องว่าง หรือวางทับหมากบนสุดของฝ่ายตรงข้ามที่เล็กกว่า ห้ามทับหมากของตัวเอง',
    opponentTitle: 'เลือกคู่แข่ง',
    oppTwo: 'ผู้เล่นอีกคน', oppTwoText: 'เล่นสองคนบนเครื่องเดียวกัน',
    oppEasy: 'AI · ง่าย', oppEasyText: 'คู่แข่งที่เล่นสนุก แต่พลาดให้เห็นบ่อย',
    oppMedium: 'AI · ปานกลาง', oppMediumText: 'คู่แข่งที่มั่นคงทางยุทธวิธี คิดล่วงหน้าพอสมควร',
    oppHard: 'AI · ยาก', oppHardText: 'คิดได้ลึกกว่าและไม่ค่อยพลาด',
    strategyTitle: 'สไตล์ของ AI',
    mixed: 'ผสม', mixedText: 'แต่ละเกมคู่แข่งจะมีนิสัยใหม่',
    architect: 'สถาปนิก', architectText: 'วางแผนต่อเนื่องยาวและสร้างบันไดที่ยืดหยุ่น',
    hunter: 'นักล่า', hunterText: 'กดดัน วางทับ และสร้างภัยคุกคามอย่างรวดเร็ว',
    sentinel: 'ผู้พิทักษ์', sentinelText: 'เก็บหมากตัวใหญ่ไว้และทำลายแผนของคุณ',
    trickster: 'จอมเล่ห์', tricksterText: 'หาทางขู่สองทาง แถวที่คาดไม่ถึง และการเดินที่ไม่ชัดเจน',
    themeTitle: 'ธีม',
    ndText: 'กระดานสีดำ แสงสีเงินเรียบ ๆ และหมากสีเงินโทนอุ่นกับโทนเย็น',
    pirateText: 'โต๊ะกัปตัน แผนที่หมู่เกาะ กระดานกระดาษหนัง และหมากโจรสลัดหนัง',
    atlantisText: 'นครวิหารใต้ทะเล แท่นหิน คลองน้ำเรืองแสง และพีระมิดขั้นบันได',
    valTwo: 'ผู้เล่นอีกคน', valAi: 'AI · {level}', easy: 'ง่าย', medium: 'ปานกลาง', hard: 'ยาก',
    valC: 'C · ซ้อน 2', valD: 'D · บันได', valCD: 'CD · ซ้อน 2 + บันได',
    valMixed: 'ผสม', valArchitect: 'สถาปนิก', valHunter: 'นักล่า', valSentinel: 'ผู้พิทักษ์', valTrickster: 'จอมเล่ห์',
    cell: 'ช่อง {n}', empty: 'ว่าง', piece: '{side} · หมาก {r}',
    thinking: 'คอมพิวเตอร์กำลังคิด…', turn: 'ตา: {side}', draw: 'เสมอ', win: '{side} ชนะ',
    computer: 'คอมพิวเตอร์ · {name}', you: 'คุณ', computerTurn: 'ตาของคอมพิวเตอร์', pick: '{side}: เลือกขนาดหมาก',
    moves: 'จำนวนตา: {n}', over: 'จบเกมแล้ว', resetConfirm: 'เริ่มเกมนี้ใหม่หรือไม่?',
    tutIntro: 'บทเรียนสั้น ๆ: ปุ่มแต่ละปุ่มทำอะไร และเดินหมากอย่างไร',
    tutRules: 'กติกา C: ช่องละไม่เกินสองตัว D: ชนะได้เฉพาะแถวที่ตัวเลขเพิ่มขึ้นหรือลดลง เช่น 1‑4‑9 CD: ใช้ทั้งสองอย่าง',
    tutOpponent: 'คู่แข่ง: เพื่อนบนเครื่องนี้ หรือ AI ระดับง่าย ปานกลาง หรือยาก',
    tutStrategy: 'สไตล์ AI: นิสัยของคอมพิวเตอร์ ว่าจะเล่นแบบไหน',
    tutTheme: 'ธีม: หน้าตาของกระดานและหมาก',
    tutDark: 'หมากฝ่ายมืด เมื่อเล่นกับ AI คอมพิวเตอร์จะเดินหมากเหล่านี้',
    tutLight: 'หมากของคุณ เลข 1 ถึง 9 แต่ละตัววางได้ครั้งเดียว',
    tutBoard: 'กระดาน วางหมากบนช่องว่าง หรือวางทับหมากของฝ่ายตรงข้ามที่เล็กกว่า หมากบนสุดของคุณสามตัวเรียงกันคือชนะ',
    tutUndo: 'ย้อน: ยกเลิกการเดินล่าสุด', tutReset: 'เริ่มใหม่: เริ่มเกมนี้ใหม่ตั้งแต่ต้น',
    tutNextBtn: 'เกมถัดไป: เริ่มเกมใหม่เมื่อเกมนี้จบ', tutMenu: 'เมนู: ตั้งค่า ภาษา และกติกา',
    tutPick: 'ตาของคุณ แตะหมากของคุณตัวใดก็ได้', tutPlace: 'ทีนี้แตะช่องที่ไฮไลต์ไว้',
    tutPlay: 'เยี่ยมมาก! เล่นเกมนี้ให้จบ แล้วเกมปกติจะเริ่มต่อ', tutDone: 'จบบทเรียนแล้ว! เริ่มเกมปกติกันเลย',
    tutGo: 'ต่อไป', tutSkip: 'ข้าม', tutOk: 'เข้าใจแล้ว', tutPlayNow: 'เล่นเลย', tutStep: '{n}/{total}'
  }
};

let lang = 'ru';
try { const v = localStorage.getItem(KEY); if (T[v]) lang = v; } catch (_) {}

export function getLang() { return lang; }

export function t(key, vars) {
  const s = T[lang][key];
  if (s === undefined) throw new Error('i18n: no text for ' + key);
  return vars ? s.replace(/\{(\w+)\}/g, (_, k) => vars[k]) : s;
}

export function applyStatic(root = document) {
  document.documentElement.lang = lang;
  document.title = t('title') + ' · AI 1.0-rc1';
  root.querySelectorAll('[data-i18n]').forEach(e => { e.textContent = t(e.dataset.i18n); });
  root.querySelectorAll('[data-i18n-aria]').forEach(e => { e.setAttribute('aria-label', t(e.dataset.i18nAria)); });
}

export function setLang(next) {
  if (!T[next] || next === lang) return;
  lang = next;
  try { localStorage.setItem(KEY, lang); } catch (_) {}
  applyStatic();
  window.dispatchEvent(new CustomEvent('sinee-more:lang', { detail: lang }));
}
