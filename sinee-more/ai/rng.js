export function createRng(seed = 1) {
  let x = seed >>> 0;
  if (x === 0) x = 0x9e3779b9;
  return function rng() {
    x ^= x << 13; x >>>= 0;
    x ^= x >>> 17; x >>>= 0;
    x ^= x << 5; x >>>= 0;
    return x / 0x100000000;
  };
}
