import assert from 'node:assert/strict';

const cases = [
  { w: 640, h: 360 },
  { w: 844, h: 390 },
  { w: 1280, h: 720 },
  { w: 1920, h: 1080 },
];

function model({w,h}) {
  const compact = h <= 430;
  const padX = compact ? 20 : 20;
  const gapX = compact ? 8 : 10;
  const sideMin = compact ? 145 : 160;
  const sidePreferred = w * (compact ? 0.21 : 0.22);
  const side = Math.max(sideMin, sidePreferred);
  const centerMin = compact ? 280 : 300;
  const center = w - padX - 2 * side - 2 * gapX;
  const board = Math.min(h * (compact ? 0.72 : 0.70), w * (compact ? 0.48 : 0.52), compact ? 350 : 620);
  const reserveH = Math.min(h * 0.58, compact ? 240 : 430);
  const reserveCellW = (side - 2 * (compact ? 3 : 5)) / 3;
  const reserveCellH = (reserveH - 2 * (compact ? 3 : 5)) / 3;
  const actionGap = compact ? 3 : 4;
  const actionW = (side - 2 * actionGap) / 3;
  const settingsSpan = side + gapX + center;
  const settingW = (settingsSpan - 3 * 5) / 4;
  return {compact,side,center,centerMin,board,reserveCellW,reserveCellH,actionW,settingW};
}

for (const c of cases) {
  const x = model(c);
  assert.ok(x.center >= x.centerMin, `${c.w}x${c.h}: center column below CSS minimum`);
  assert.ok(x.board <= x.center + 0.01, `${c.w}x${c.h}: board exceeds center column`);
  assert.ok(x.reserveCellW >= 44, `${c.w}x${c.h}: reserve target width <44`);
  assert.ok(x.reserveCellH >= 44, `${c.w}x${c.h}: reserve target height <44`);
  assert.ok(x.actionW >= 44, `${c.w}x${c.h}: action target width <44`);
  assert.ok(x.settingW >= 90, `${c.w}x${c.h}: setting card too narrow for labels`);
  console.log(`${c.w}x${c.h} PASS board=${x.board.toFixed(1)} reserve=${x.reserveCellW.toFixed(1)}x${x.reserveCellH.toFixed(1)} actionW=${x.actionW.toFixed(1)} settingW=${x.settingW.toFixed(1)}`);
}
