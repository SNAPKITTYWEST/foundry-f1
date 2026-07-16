import { readFile } from "node:fs/promises";

const bytes = await readFile(new URL("../build/verifier.wasm", import.meta.url));
const env = {
  abort(msg, file, line, col) { throw new Error(`wasm abort @${line}:${col}`); },
  trace() {},
  seed() { return 42; },
};
const { instance } = await WebAssembly.instantiate(bytes, { env });
const e = instance.exports;

const P = 0xffffffff00000001n;
const MASK = 0xffffffffffffffffn;
const modp = (x) => ((x % P) + P) % P;
const u64 = (x) => BigInt(x);
const u = (x) => (typeof x === "bigint" ? x & MASK : BigInt(x) & MASK);

let pass = 0, fail = 0;
function check(name, cond, got, want) {
  const norm = (v) => (typeof v === "bigint" ? (v & MASK) : v);
  const g = norm(got), w = norm(want);
  const ok = cond || (g === w);
  if (ok) { pass++; console.log(`  ok  ${name}`); }
  else { fail++; console.log(`FAIL  ${name}\n      got:  ${got}\n      want: ${want}`); }
}

// Goldilocks mul vs BigInt
for (const [a, b] of [[42n, 1337n], [2n ** 40n, 2n ** 33n], [P - 1n, P - 2n], [123456789n, 987654321n]]) {
  const got = e.goldilocksMul(u64(a), u64(b));
  const want = modp(a * b);
  check(`goldilocksMul(${a},${b})`, got === want, got, want);
}

// inv * a == 1
for (const a of [2n, 1337n, 123456789n, P - 3n]) {
  const inv = e.goldilocksInv(u64(a));
  const got = e.goldilocksMul(inv, u64(a));
  check(`goldilocksInv*${a}==1`, got === 1n, got, 1n);
}

// pow: a^e mod p
for (const [a, ex] of [[5n, 100n], [7n, 0n], [3n, 64n]]) {
  const got = e.goldilocksPow(u64(a), u64(ex));
  const want = modp(a ** ex);
  check(`goldilocksPow(${a},${ex})`, got === want, got, want);
}

// add / sub
check("goldilocksAdd", e.goldilocksAdd(u64(10n), u64(20n)) === 30n, e.goldilocksAdd(10n, 20n), 30n);
check("goldilocksSub", e.goldilocksSub(u64(5n), u64(9n)) === modp(5n - 9n), e.goldilocksSub(5n, 9n), modp(5n - 9n));

// randomized mul vs BigInt
let mulFails = 0;
for (let i = 0; i < 500; i++) {
  const a = BigInt(Math.floor(Math.random() * 2 ** 32)) * 123456789n % P;
  const b = BigInt(Math.floor(Math.random() * 2 ** 32)) * 987654321n % P;
  const got = u(e.goldilocksMul(u64(a), u64(b)));
  const want = u(modp(a * b));
  if (got !== want) { mulFails++; if (mulFails <= 3) console.log(`  mulrand FAIL a=${a} b=${b} got=${got} want=${want}`); }
}
if (mulFails === 0) console.log("  ok  goldilocksMul x500 random");
else { fail += mulFails; console.log(`FAIL  goldilocksMul random: ${mulFails} mismatches`); }

// direct inverse for 1337
const inv1337 = u(e.goldilocksInv(u64(1337n)));
const invCheck = u(e.goldilocksMul(inv1337, u64(1337n)));
check("goldilocksInv(1337)*1337==1", invCheck === 1n, invCheck, 1n);

// SHA-256 of "abc"
function setInput(str) {
  const enc = new TextEncoder();
  const bytes = enc.encode(str);
  const ptr = e.inputPtr();
  new Uint8Array(e.memory.buffer).set(bytes, Number(ptr));
  return bytes.length;
}
setInput("abc");
e.sha256(3);
const shaBytes = new Uint8Array(e.memory.buffer).slice(Number(e.shaOutPtr()), Number(e.shaOutPtr()) + 32);
const hex = [...shaBytes].map((b) => b.toString(16).padStart(2, "0")).join("");
const shaWant = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad";
check("sha256('abc')", hex === shaWant, hex, shaWant);

// SHA-256 empty
setInput("");
e.sha256(0);
const emptyBytes = new Uint8Array(e.memory.buffer).slice(Number(e.shaOutPtr()), Number(e.shaOutPtr()) + 32);
const emptyHex = [...emptyBytes].map((b) => b.toString(16).padStart(2, "0")).join("");
check("sha256('')", emptyHex === "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855", emptyHex, "e3b0c4...");

// Banach q
check("banachQ pass", e.banachQ(0.5, 0.3, 1.0, 0.1) === 1, e.banachQ(0.5, 0.3, 1.0, 0.1), 1);
check("banachQ fail", e.banachQ(0.9, 0.5, 1.0, 0.01) === 0, e.banachQ(0.9, 0.5, 1.0, 0.01), 0);

// verifyLean
function verify(src) {
  const len = setInput(src);
  const packed = e.verifyLean(len);
  return {
    status: packed & 7,
    sorryCount: (packed >> 3) & 0xff,
    hasTheorem: ((packed >> 11) & 1) === 1,
    hasBy: ((packed >> 12) & 1) === 1,
  };
}
const v1 = verify("theorem foo : x = x := by sorry");
check("verifyLean debt", v1.status === 1 && v1.sorryCount === 1 && v1.hasTheorem && v1.hasBy, JSON.stringify(v1), "status1,1,sorry");

const v2 = verify("theorem bar : y = y := by simp");
check("verifyLean candidate", v2.status === 2 && v2.sorryCount === 0 && v2.hasTheorem, JSON.stringify(v2), "status2");

const v3 = verify("just some text");
check("verifyLean none", v3.status === 0 && !v3.hasTheorem, JSON.stringify(v3), "status0");

console.log(`\n${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
