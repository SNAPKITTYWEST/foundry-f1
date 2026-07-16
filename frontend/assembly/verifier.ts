// Foundry F1 — client engine (WASM). Real logic ported from the C++ foundry_core:
// Goldilocks field arithmetic, Banach contraction criterion, SHA-256 receipt hashing.

export const P: u64 = 0xffffffff00000001;

const INPUT_CAP: i32 = 1 << 16;
const RESULT_CAP: i32 = 1 << 16;

let inputBuf = new StaticArray<u8>(INPUT_CAP);
let resultBuf = new StaticArray<u8>(RESULT_CAP);
let shaOut = new StaticArray<u8>(32);

export function inputPtr(): usize { return changetype<usize>(inputBuf); }
export function resultPtr(): usize { return changetype<usize>(resultBuf); }
export function shaOutPtr(): usize { return changetype<usize>(shaOut); }

export function dbgInput0(): u32 {
  return ((inputBuf[0] as u32) << 24) | ((inputBuf[1] as u32) << 16) | ((inputBuf[2] as u32) << 8) | (inputBuf[3] as u32);
}
export function dbgMsg0(): u32 {
  return ((shaMsg[0] as u32) << 24) | ((shaMsg[1] as u32) << 16) | ((shaMsg[2] as u32) << 8) | (shaMsg[3] as u32);
}
export function dbgW(t: i32): u32 { return shaW[t]; }
export function dbgS(x: u32): u32 { return rotr(x, 17) ^ rotr(x, 19) ^ (x >>> 10); }

function mul64x64(a: u64, b: u64): u64 {
  let a0 = a & 0xffffffff;
  let a1 = a >> 32;
  let b0 = b & 0xffffffff;
  let b1 = b >> 32;
  let z0 = a0 * b0;
  let z1 = a1 * b0;
  let z2 = a0 * b1;
  let z3 = a1 * b1;
  let mid = (z1 & 0xffffffff) + (z2 & 0xffffffff);
  let midLo = mid & 0xffffffff;
  let midHi = (mid >> 32) + (z1 >> 32) + (z2 >> 32);
  let lo: u64 = z0 + (midLo << 32);
  let carryLo = lo < z0 ? 1 : 0;
  let s = midHi + z3;
  let sCarry = s < midHi ? 1 : 0;
  let hi = s + (carryLo as u64);
  let carry128 = (sCarry != 0 || hi < s) ? 1 : 0;
  let r = reduce128(hi, lo);
  if (carry128 != 0) {
    if (r >= 0x100000000) r -= 0x100000000; else r = r + P - 0x100000000;
  }
  return r;
}

function reduce128(hi: u64, lo: u64): u64 {
  let R: u64 = 0xffffffff;
  let hiL = hi & 0xffffffff;
  let hiH = hi >> 32;
  let pL = hiL * R;
  let pH = hiH * R;
  let pHL = pH & 0xffffffff;
  let pHH = pH >> 32;
  let acc: u64 = lo;
  let b: u64;
  b = acc; acc = acc + pL; if (acc < b) acc = acc + R;
  b = acc; acc = acc + (pHL << 32); if (acc < b) acc = acc + R;
  if (pHH > 0) {
    let add = pHH * R;
    b = acc; acc = acc + add; if (acc < b) acc = acc + R;
  }
  while (acc >= P) acc -= P;
  return acc;
}

export function goldilocksAdd(a: u64, b: u64): u64 {
  let s = (a % P) + (b % P);
  if (s >= P) s -= P;
  return s;
}

export function goldilocksSub(a: u64, b: u64): u64 {
  let x = a % P;
  let y = b % P;
  let s = x - y;
  if (x < y) s += P;
  return s;
}

export function goldilocksMul(a: u64, b: u64): u64 {
  return mul64x64(a % P, b % P);
}

export function goldilocksPow(a: u64, e: u64): u64 {
  let base = a % P;
  let result: u64 = 1;
  let exp = e;
  while (exp > 0) {
    if ((exp & 1) != 0) result = mul64x64(result, base);
    base = mul64x64(base, base);
    exp = exp >> 1;
  }
  return result;
}

export function goldilocksInv(a: u64): u64 {
  return goldilocksPow(a % P, P - 2);
}

export function banachQ(xiNorm: f64, lambdaNorm: f64, tNorm: f64, epsilon: f64): bool {
  let q = xiNorm + lambdaNorm * tNorm;
  return q < (1.0 - epsilon);
}

function matchAt(buf: StaticArray<u8>, off: i32, str: string): bool {
  let n = str.length;
  for (let i = 0; i < n; i++) {
    if (buf[off + i] != (str.charCodeAt(i) as u8)) return false;
  }
  return true;
}

export function verifyLean(len: i32): i32 {
  let sorryCount = 0;
  let hasTheorem = false;
  let hasLemma = false;
  let hasBy = false;
  for (let i = 0; i + 5 <= len; i++) {
    if (matchAt(inputBuf, i, "sorry")) { sorryCount++; i += 4; }
  }
  for (let i = 0; i + 7 <= len; i++) {
    if (matchAt(inputBuf, i, "theorem")) hasTheorem = true;
    if (matchAt(inputBuf, i, "lemma")) hasLemma = true;
  }
  for (let i = 0; i + 2 <= len; i++) {
    if (matchAt(inputBuf, i, "by")) hasBy = true;
  }
  let status = 0;
  if (!hasTheorem && !hasLemma) status = 0;
  else if (sorryCount > 0) status = 1;
  else if (hasBy) status = 2;
  else status = 3;
  let packed: i32 = (status & 7)
    | ((sorryCount & 0xff) << 3)
    | (((hasTheorem || hasLemma) ? 1 : 0) << 11)
    | ((hasBy ? 1 : 0) << 12);
  return packed;
}

let shaMsg = new StaticArray<u8>(1 << 16);
let shaW = new StaticArray<u32>(64);

const K: StaticArray<u32> = new StaticArray<u32>(64);
K[0] = 0x428a2f98; K[1] = 0x71374491; K[2] = 0xb5c0fbcf; K[3] = 0xe9b5dba5;
K[4] = 0x3956c25b; K[5] = 0x59f111f1; K[6] = 0x923f82a4; K[7] = 0xab1c5ed5;
K[8] = 0xd807aa98; K[9] = 0x12835b01; K[10] = 0x243185be; K[11] = 0x550c7dc3;
K[12] = 0x72be5d74; K[13] = 0x80deb1fe; K[14] = 0x9bdc06a7; K[15] = 0xc19bf174;
K[16] = 0xe49b69c1; K[17] = 0xefbe4786; K[18] = 0x0fc19dc6; K[19] = 0x240ca1cc;
K[20] = 0x2de92c6f; K[21] = 0x4a7484aa; K[22] = 0x5cb0a9dc; K[23] = 0x76f988da;
K[24] = 0x983e5152; K[25] = 0xa831c66d; K[26] = 0xb00327c8; K[27] = 0xbf597fc7;
K[28] = 0xc6e00bf3; K[29] = 0xd5a79147; K[30] = 0x06ca6351; K[31] = 0x14292967;
K[32] = 0x27b70a85; K[33] = 0x2e1b2138; K[34] = 0x4d2c6dfc; K[35] = 0x53380d13;
K[36] = 0x650a7354; K[37] = 0x766a0abb; K[38] = 0x81c2c92e; K[39] = 0x92722c85;
K[40] = 0xa2bfe8a1; K[41] = 0xa81a664b; K[42] = 0xc24b8b70; K[43] = 0xc76c51a3;
K[44] = 0xd192e819; K[45] = 0xd6990624; K[46] = 0xf40e3585; K[47] = 0x106aa070;
K[48] = 0x19a4c116; K[49] = 0x1e376c08; K[50] = 0x2748774c; K[51] = 0x34b0bcb5;
K[52] = 0x391c0cb3; K[53] = 0x4ed8aa4a; K[54] = 0x5b9cca4f; K[55] = 0x682e6ff3;
K[56] = 0x748f82ee; K[57] = 0x78a5636f; K[58] = 0x84c87814; K[59] = 0x8cc70208;
K[60] = 0x90befffa; K[61] = 0xa4506ceb; K[62] = 0xbef9a3f7; K[63] = 0xc67178f2;

function rotr(x: u32, n: i32): u32 {
  return (x >>> n) | (x << (32 - n));
}

export function sha256(len: i32): void {
  let bitLen = len * 8;
  let base = len + 1;
  let k = (56 - (base % 64)) & 63;
  let paddedLen = base + k + 8;
  let msg = shaMsg;
  for (let i = 0; i < len; i++) msg[i] = inputBuf[i];
  msg[len] = 0x80;
  if (paddedLen < len + 1) paddedLen = len + 1;
  for (let i = len + 1; i < paddedLen; i++) msg[i] = 0;
  let bitsHi: u32 = 0;
  let bitsLo = bitLen as u32;
  msg[paddedLen - 8] = (bitsHi >>> 24) as u8;
  msg[paddedLen - 7] = (bitsHi >>> 16) as u8;
  msg[paddedLen - 6] = (bitsHi >>> 8) as u8;
  msg[paddedLen - 5] = bitsHi as u8;
  msg[paddedLen - 4] = (bitsLo >>> 24) as u8;
  msg[paddedLen - 3] = (bitsLo >>> 16) as u8;
  msg[paddedLen - 2] = (bitsLo >>> 8) as u8;
  msg[paddedLen - 1] = bitsLo as u8;

  let h0: u32 = 0x6a09e667; let h1: u32 = 0xbb67ae85;
  let h2: u32 = 0x3c6ef372; let h3: u32 = 0xa54ff53a;
  let h4: u32 = 0x510e527f; let h5: u32 = 0x9b05688c;
  let h6: u32 = 0x1f83d9ab; let h7: u32 = 0x5be0cd19;

  let w = shaW;
  for (let block = 0; block < paddedLen; block += 64) {
    for (let t = 0; t < 16; t++) {
      let j = block + t * 4;
      w[t] = ((msg[j] as u32) << 24) | ((msg[j + 1] as u32) << 16) | ((msg[j + 2] as u32) << 8) | (msg[j + 3] as u32);
    }
    for (let t = 16; t < 64; t++) {
      let s0 = rotr(w[t - 15], 7) ^ rotr(w[t - 15], 18) ^ (w[t - 15] >>> 3);
      let s1 = rotr(w[t - 2], 17) ^ rotr(w[t - 2], 19) ^ (w[t - 2] >>> 10);
      w[t] = w[t - 16] + s0 + w[t - 7] + s1;
    }
    let a = h0; let b = h1; let c = h2; let d = h3;
    let e = h4; let f = h5; let g = h6; let hh = h7;
    for (let t = 0; t < 64; t++) {
      let S1 = rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25);
      let ch = (e & f) ^ ((~e) & g);
      let temp1 = hh + S1 + ch + K[t] + w[t];
      let S0 = rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22);
      let maj = (a & b) ^ (a & c) ^ (b & c);
      let temp2 = S0 + maj;
      hh = g; g = f; f = e; e = d + temp1; d = c; c = b; b = a; a = temp1 + temp2;
    }
    h0 = h0 + a; h1 = h1 + b; h2 = h2 + c; h3 = h3 + d;
    h4 = h4 + e; h5 = h5 + f; h6 = h6 + g; h7 = h7 + hh;
  }
  let h = [h0, h1, h2, h3, h4, h5, h6, h7];
  for (let i = 0; i < 8; i++) {
    shaOut[i * 4] = (h[i] >>> 24) as u8;
    shaOut[i * 4 + 1] = (h[i] >>> 16) as u8;
    shaOut[i * 4 + 2] = (h[i] >>> 8) as u8;
    shaOut[i * 4 + 3] = h[i] as u8;
  }
}
