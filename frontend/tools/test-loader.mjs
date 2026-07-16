import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';

globalThis.fetch = async (url) => {
  const p = fileURLToPath(url);
  const data = await readFile(p);
  return { arrayBuffer: async () => data.buffer.slice(data.byteOffset, data.byteOffset + data.byteLength) };
};

const { init, decodeLeanReport } = await import('../src/loader.mjs');
const api = await init();
console.log('P =', api.P.toString());

const sample = `theorem om001_closure_surface :\n  ∀ (x y : ℝ), contractive_family x y → fixed_point_exists x y := by\n  exact h.contraction_closed`;
const r = api.verifyLean(sample);
console.log('verifyLean:', JSON.stringify(r), 'decode ok:', r.status === 'candidate' && r.sorryCount === 0 && r.hasBy);

console.log('mul(1337,42) =', api.goldilocksMul(1337n, 42n).toString(), '(want', ((1337n * 42n) % api.P).toString() + ')');
console.log('inv(1337)*1337 =', api.goldilocksMul(api.goldilocksInv(1337n), 1337n).toString(), '(want 1)');
console.log('sha256(abc) =', api.sha256('abc'), '(want ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad)');
console.log('banachQ(0.20,0.30,0.90,0.05) =', api.banachQ(0.20, 0.30, 0.90, 0.05), '(want false: q=0.47? check)');

const debt = api.verifyLean('theorem foo : True := sorry');
console.log('verifyLean(debt):', JSON.stringify(debt), '(want proof-debt, sorryCount 1)');
console.log('decodeLeanReport smoke:', JSON.stringify(decodeLeanReport((1) | (1 << 3) | (1 << 11) | (1 << 12))));
