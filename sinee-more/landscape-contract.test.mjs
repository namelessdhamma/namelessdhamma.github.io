import fs from 'node:fs';

const index = fs.readFileSync(new URL('./index.html', import.meta.url), 'utf8');
const app = fs.readFileSync(new URL('./app.js', import.meta.url), 'utf8');
const layout = fs.readFileSync(new URL('./landscape-16x9.css', import.meta.url), 'utf8');
const shell = fs.readFileSync(new URL('./landscape-shell-fix.css', import.meta.url), 'utf8');

function check(ok, message) {
  if (!ok) throw new Error(message);
}

check(index.includes('href="./landscape-16x9.css"'), 'index must load landscape-16x9.css');
check(index.includes('href="./landscape-shell-fix.css"'), 'index must load landscape-shell-fix.css');
check(layout.includes('@media (orientation:landscape)'), 'landscape media contract missing');
check(layout.includes('grid-template-areas:"title title title" "dark board light"'), 'three-column gameplay shell missing');
check(layout.includes('width:min(70dvh,52vw,620px)!important'), 'desktop board cap drifted');
check(layout.includes('width:min(72dvh,48vw,350px)!important'), 'compact board cap drifted');
check(shell.includes('#turn + .player{grid-area:dark'), 'dark player must bind through #turn sibling');
check(!shell.includes('.settings + .player'), 'invalid dark-player sibling selector returned');
check(shell.includes('grid-template-columns:repeat(3,minmax(44px,1fr))'), 'reserve touch-target floor missing');
check(shell.includes('.actions{grid-area:auto;grid-column:3;grid-row:3;grid-template-columns:repeat(3,minmax(44px,1fr))'), 'action touch-target floor missing');
check(app.includes("matchMedia('(orientation: landscape)').matches){board.style.width='';board.style.height='';return;}"), 'fitBoard must yield geometry to landscape CSS');

console.log('Blue Sea landscape source contract: PASS');
