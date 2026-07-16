// Frontend WASM loader for foundry-f1.
// Connects the browser to the engine (Goldilocks field, Banach contraction,
// SHA-256 receipt hashing, Lean-buffer analysis) for real, client-side.

const wasmUrl = new URL('../build/verifier.wasm', import.meta.url);

let _mod = null;

export async function init() {
  if (_mod) return _mod;
  const imports = {
    env: {
      abort(msgPtr, filePtr, line, col) {
        throw new Error(`wasm abort @ ${line}:${col}`);
      },
      trace() {},
      seed() { return 42; },
    },
  };
  const { instance } = await WebAssembly.instantiate(await (await fetch(wasmUrl)).arrayBuffer(), imports);
  const e = instance.exports;
  const rawP = typeof e.P === 'object' && 'value' in e.P ? e.P.value : e.P;
  const P = BigInt(rawP) & 0xffffffffffffffffn;

  const u64 = (v) => BigInt(v);
  const toJs = (v) => (typeof v === 'bigint' ? v : BigInt(v));

  function writeInput(text) {
    const enc = new TextEncoder();
    const bytes = enc.encode(text);
    const ptr = Number(e.inputPtr());
    const mem = new Uint8Array(e.memory.buffer);
    mem.set(bytes, ptr);
    return bytes.length;
  }

  function readSha() {
    const ptr = Number(e.shaOutPtr());
    const mem = new Uint8Array(e.memory.buffer);
    let hex = '';
    for (let i = 0; i < 32; i++) hex += mem[ptr + i].toString(16).padStart(2, '0');
    return hex;
  }

  const api = {
    P,
    exports: e,

    goldilocksAdd: (a, b) => e.goldilocksAdd(toJs(a), toJs(b)),
    goldilocksSub: (a, b) => e.goldilocksSub(toJs(a), toJs(b)),
    goldilocksMul: (a, b) => e.goldilocksMul(toJs(a), toJs(b)),
    goldilocksPow: (a, exp) => e.goldilocksPow(toJs(a), toJs(exp)),
    goldilocksInv: (a) => e.goldilocksInv(toJs(a)),

    banachQ: (xiNorm, lambdaNorm, tNorm, epsilon) =>
      e.banachQ(Number(xiNorm), Number(lambdaNorm), Number(tNorm), Number(epsilon)),

    sha256: (input) => {
      const text = typeof input === 'string' ? input : new TextDecoder().decode(input);
      const len = writeInput(text);
      e.sha256(len);
      return readSha();
    },

    verifyLean: (text) => {
      const len = writeInput(text);
      const packed = e.verifyLean(len);
      return decodeLeanReport(packed);
    },
  };

  _mod = api;
  return api;
}

export function decodeLeanReport(packed) {
  const p = Number(packed);
  const statusCode = p & 7;
  const sorryCount = (p >> 3) & 0xff;
  const hasDecl = ((p >> 11) & 1) === 1;
  const hasBy = ((p >> 12) & 1) === 1;
  const status =
    statusCode === 0 ? 'infra'
    : statusCode === 1 ? 'proof-debt'
    : statusCode === 2 ? 'candidate'
    : 'infra-only';
  return { status, statusCode, sorryCount, hasTheoremOrLemma: hasDecl, hasBy };
}
