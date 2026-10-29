// Mirrors backend matching.py (norm_tokens / phon / local_match / fast_verdict) so the turn can be judged instantly in the browser.
const NUMS = { 0: "zero", 1: "um", 2: "dois", 3: "tres", 4: "quatro", 5: "cinco", 6: "seis", 7: "sete", 8: "oito", 9: "nove", 10: "dez", 11: "onze", 12: "doze", 15: "quinze", 20: "vinte", 30: "trinta", 100: "cem" };
const COLLOQUIAL = [
  [/\bpara (a|à)\b/g, "pra"], [/\bpara o\b/g, "pro"], [/\b(para|pa|pra)\b/g, "pra"],
  [/\bestas\b/g, "tas"], [/\besta\b/g, "ta"], [/\bestou\b/g, "tou"], [/\bestava\b/g, "tava"],
  [/\bestavas\b/g, "tavas"], [/\bestamos\b/g, "tamos"], [/\bestao\b/g, "tao"],
  [/\bnao e\b/g, "ne"], [/\bcom o\b/g, "co"], [/\bcom a\b/g, "ca"], [/\bde um\b/g, "dum"], [/\bde uma\b/g, "duma"],
  [/\bem um\b/g, "num"], [/\bem uma\b/g, "numa"], [/\bpois e\b/g, "poise"],
];
const FILLERS = new Set(["hum", "hmm", "eh", "ah", "ahn", "uh", "pronto"]);
const NEGATIONS = new Set(["nao", "ne", "nunca", "nada", "nem", "ninguem", "jamais", "sim"]);
const NEEDS_AI = /\b(texto|linha|deixa|mudamos|mudaram|agora digo|passei a dizer|em vez de|cortamos|nao me lembro|como e que e)\b/;
export const HELP_RE = /\b(texto|linha|nao me lembro|como e que e)\b/g;
export const NOTE_RE = /\b(mudamos|mudaram|agora digo|passei a dizer|em vez de|cortamos)\b/;

export function normTokens(text) {
  let t = (text || "").toLowerCase().replace(/\([^)]*\)/g, " ").replace(/ç/g, "ss").normalize("NFD").replace(/[\u0300-\u036f]/g, "");
  t = t.replace(/[-'’`´]/g, " ").replace(/[^\w\s]/g, " ");
  t = t.split(/\s+/).filter(Boolean).map((w) => NUMS[w] || w).join(" ");
  COLLOQUIAL.forEach(([re, rep]) => { t = t.replace(re, rep); });
  return t.split(/\s+/).filter((w) => w && !FILLERS.has(w));
}

// Simplified pt-PT phonetic key (mirrors backend matching.phon): words that sound alike share a key.
export function phon(w) {
  if (!w) return w;
  let p = w.replace(/ss/g, "S").replace(/rr/g, "R").replace(/ch/g, "x").replace(/lh/g, "L").replace(/nh/g, "N").replace(/h/g, "");
  p = p.replace(/qu(?=[ei])/g, "k").replace(/gu(?=[ei])/g, "g").replace(/c(?=[ei])/g, "S");
  p = p.replace(/qu/g, "k").replace(/q/g, "k").replace(/c/g, "k").replace(/g(?=[ei])/g, "j");
  p = p.replace(/(?<=[aeiou])s(?=[aeiou])/g, "z").replace(/S/g, "s");
  p = p.replace(/^r/, "R").replace(/w/g, "v").replace(/y/g, "i").replace(/z$/, "s").replace(/am$/, "ao");
  if (p.length > 3) p = p.replace(/es$/, "s").replace(/e$/, "");
  p = p.replace(/ou/g, "o").replace(/ei/g, "e");
  if (p.length > 1) p = p.replace(/os$/, "us").replace(/o$/, "u");
  p = p.replace(/(.)\1+/g, "$1");
  return p || w;
}

// difflib-style ratio based on the longest common subsequence.
export function ratio(a, b) {
  if (a === b) return 1;
  if (!a.length || !b.length) return 0;
  let prev = new Array(b.length + 1).fill(0);
  for (let i = 1; i <= a.length; i++) {
    const cur = [0];
    for (let j = 1; j <= b.length; j++) cur[j] = a[i - 1] === b[j - 1] ? prev[j - 1] + 1 : Math.max(prev[j], cur[j - 1]);
    prev = cur;
  }
  return (2 * prev[b.length]) / (a.length + b.length);
}

export function sameWord(x, y, fuzzy = 0.75) {
  if (!x || !y) return false;
  if (x === y) return true;
  const px = phon(x);
  const py = phon(y);
  if (px === py) return true;
  if (Math.min(px.length, py.length) >= 5 && ratio(px, py) >= 0.85) return true;
  return ratio(x, y) >= fuzzy;
}

function sameRun(a, b, fuzzy = 0.75) {
  const ja = a.map(phon).join("");
  const jb = b.map(phon).join("");
  if (!ja || !jb) return false;
  if (ja === jb || phon(a.join("")) === phon(b.join(""))) return true;
  if (Math.min(ja.length, jb.length) >= 4 && ratio(ja, jb) >= Math.max(0.85, fuzzy)) return true;
  // pt-PT reduces unstressed vowels: same consonant skeleton + close spelling sounds alike.
  const sk = (p) => p.replace(/[aeiou]/g, "");
  return Math.min(ja.length, jb.length) >= 5 && sk(ja) === sk(jb) && ratio(ja, jb) >= 0.75;
}

export const similar = (a, b, r = 0.75) => sameWord(a, b, r);

export function isComplete(expected, said) {
  const exp = normTokens(expected);
  const got = normTokens(said);
  if (!got.length || !exp.length) return false;
  const tail = exp.slice(-Math.min(3, exp.length));
  const win = got.slice(-(tail.length + 2));
  let hits = 0;
  let j = 0;
  tail.forEach((t) => {
    for (let k = j; k < win.length; k++) if (similar(t, win[k])) { hits++; j = k + 1; break; }
  });
  if (hits < Math.max(1, Math.round(tail.length * 0.67)) && !sameRun(tail, win.slice(-tail.length))) return false;
  return got.length >= Math.max(1, Math.floor(exp.length * 0.6));
}

const LETTERS = { a: "á", b: "bê", c: "cê", d: "dê", e: "é", f: "efe", g: "guê", h: "agá", i: "i", j: "jota", k: "capa", l: "ele", m: "eme", n: "ene", o: "ó", p: "pê", q: "quê", r: "erre", s: "esse", t: "tê", u: "u", v: "vê", w: "dâblio", x: "xis", y: "ípsilon", z: "zê" };
const ONE_LETTER = new Set(["a", "e", "o", "à", "é", "ó", "á"]);

// ASR output → spelled-out acronyms/letters (marked implausible: nobody says "A RTP" for "arrota").
export function spellHeard(said) {
  const out = [];
  const odd = new Set();
  (said || "").split(/\s+/).filter(Boolean).forEach((raw) => {
    const core = raw.replace(/^[^\p{L}\p{N}]+|[^\p{L}\p{N}]+$/gu, "");
    if (/^[A-Z]{2,6}$/.test(core) || (core.length === 1 && /\p{L}/u.test(core) && !ONE_LETTER.has(core.toLowerCase()))) {
      const names = [...core].map((c) => LETTERS[c.toLowerCase()] || c);
      out.push(...names);
      normTokens(names.join(" ")).forEach((w) => odd.add(w));
    } else out.push(raw);
  });
  return [out.join(" "), odd];
}

const skeleton = (p) => p.replace(/[aeiou]/g, "");
const commonPrefix = (a, b) => { let k = 0; while (k < a.length && a[k] === b[k]) k++; return k; };

// Phonetic similarity of two word runs (character level, merges allowed, prefix-tolerant).
export function runSim(a, b) {
  const ja = a.map(phon).join("");
  const jb = b.map(phon).join("");
  if (!ja || !jb) return 0;
  if (ja === jb) return 1;
  let r = ratio(ja, jb);
  if (Math.min(ja.length, jb.length) >= 5 && skeleton(ja) === skeleton(jb)) r = Math.max(r, 0.8);
  const pre = commonPrefix(ja, jb);
  if (pre >= 5 && pre >= 0.6 * ja.length && jb.length <= ja.length + 2) r = Math.max(r, 0.8);
  return r;
}

const MERGES = [[1, 1], [1, 2], [2, 1], [1, 3], [3, 1], [2, 3], [3, 2]];

function alignRegion(a, b, odd, thr) {
  const n = a.length;
  const m = b.length;
  const cost = Array.from({ length: n + 1 }, () => new Array(m + 1).fill(Infinity));
  const back = Array.from({ length: n + 1 }, () => new Array(m + 1).fill(null));
  cost[0][0] = 0;
  for (let i = 0; i <= n; i++) {
    for (let j = 0; j <= m; j++) {
      const c = cost[i][j];
      if (c === Infinity) continue;
      const cand = [[1, 0, 1, false], [0, 1, j < m && odd.has(b[j]) ? 0 : 0.9, false]];
      MERGES.forEach(([di, dj]) => {
        if (i + di > n || j + dj > m) return;
        const hb = b.slice(j, j + dj);
        const sv = runSim(a.slice(i, i + di), hb);
        const ok = sv >= thr || hb.every((w) => odd.has(w));
        cand.push([di, dj, ok ? (1 - sv) * 0.5 : 1.2, ok]);
      });
      cand.forEach(([di, dj, w, ok]) => {
        if (i + di > n || j + dj > m) return;
        if (c + w < cost[i + di][j + dj]) { cost[i + di][j + dj] = c + w; back[i + di][j + dj] = [i, j, ok]; }
      });
    }
  }
  const steps = [];
  let i = n;
  let j = m;
  while (i || j) {
    const [pi, pj, ok] = back[i][j];
    steps.push([pi, i, pj, j, ok]);
    i = pi; j = pj;
  }
  return steps.reverse();
}

// LCS opcodes over keys; returns index ranges [op, i1, i2, j1, j2].
function opcodes(a, b) {
  const n = a.length;
  const m = b.length;
  const dp = Array.from({ length: n + 1 }, () => new Int32Array(m + 1));
  for (let i = n - 1; i >= 0; i--) for (let j = m - 1; j >= 0; j--) dp[i][j] = a[i] === b[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1]);
  const ops = [];
  let i = 0;
  let j = 0;
  let si = 0;
  let sj = 0;
  const flush = () => {
    if (i > si && j > sj) ops.push(["replace", si, i, sj, j]);
    else if (i > si) ops.push(["delete", si, i, sj, j]);
    else if (j > sj) ops.push(["insert", si, i, sj, j]);
  };
  while (i < n || j < m) {
    if (i < n && j < m && a[i] === b[j]) { flush(); ops.push(["equal", i, i + 1, j, j + 1]); i++; j++; si = i; sj = j; }
    else if (j >= m || (i < n && dp[i + 1][j] >= dp[i][j + 1])) i++;
    else j++;
  }
  flush();
  return ops;
}

// A lone short word matched between two gaps is usually a coincidence ("arrota à" ~ "a RTP à"): merge into one region.
function mergeOps(ops, exp) {
  const out = [];
  ops.forEach((op) => {
    const prev = out[out.length - 1];
    if (prev && op[0] !== "equal" && prev[0] !== "equal") { out[out.length - 1] = ["replace", prev[1], op[2], prev[3], op[4]]; return; }
    out.push(op);
  });
  for (let k = 1; k < out.length - 1; k++) {
    const [op, i1, i2] = out[k];
    if (op === "equal" && i2 - i1 === 1 && exp[i1].length <= 2 && out[k - 1][0] !== "equal" && out[k + 1][0] !== "equal") {
      out.splice(k - 1, 3, ["replace", out[k - 1][1], out[k + 1][2], out[k - 1][3], out[k + 1][4]]);
      k -= 1;
    }
  }
  return out;
}

// Mirrors backend matching.local_match (without the dictionary check).
export function localMatch(expected, said, fuzzy = 0.75) {
  const [heard, odd] = spellHeard(said);
  const exp = normTokens(expected);
  const got = normTokens(heard);
  if (!exp.length) return { accuracy: 100, max_gap: 0, extra: 0, differences: [] };
  const thr = Math.max(0.72, fuzzy - 0.03);
  let matched = 0; let extra = 0; let maxGap = 0;
  const diffs = [];
  const add = (i1, i2, j1, j2) => {
    const a = exp.slice(i1, i2);
    const b = got.slice(j1, j2);
    if (!a.length && b.every((w) => odd.has(w))) return;
    maxGap = Math.max(maxGap, a.length);
    extra += Math.max(0, b.length - a.length);
    diffs.push({ expected: a.join(" "), said: b.join(" ") });
  };
  mergeOps(opcodes(exp.map(phon), got.map(phon)), exp).forEach(([op, i1, i2, j1, j2]) => {
    const a = exp.slice(i1, i2);
    const b = got.slice(j1, j2);
    if (op === "equal") { matched += a.length; return; }
    if (a.length && b.length && (sameRun(a, b, fuzzy) || (b.every((w) => odd.has(w)) && b.length <= 3 * a.length + 2))) { matched += a.length; return; }
    if (!a.length || !b.length || a.length * b.length > 400) { add(i1, i2, j1, j2); return; }
    let pend = null;
    alignRegion(a, b, odd, thr).forEach(([si1, si2, sj1, sj2, ok]) => {
      if (ok) { matched += si2 - si1; if (pend) { add(...pend); pend = null; } }
      else if (pend) pend = [pend[0], i1 + si2, pend[2], j1 + sj2];
      else pend = [i1 + si1, i1 + si2, j1 + sj1, j1 + sj2];
    });
    if (pend) add(...pend);
  });
  return { accuracy: Math.round((1000 * matched) / exp.length) / 10, max_gap: maxGap, extra, differences: diffs };
}

function fastVerdict(strictness, m, nWords, said) {
  const { accuracy: acc, max_gap: gap, extra } = m;
  if (acc < 97 && NEEDS_AI.test(normTokens(said).join(" "))) return null;
  if (strictness === "nunca") return acc >= 50 ? (acc >= 97 ? "none" : "minor") : null;
  if (m.differences.some((d) => `${d.expected} ${d.said}`.split(" ").some((w) => NEGATIONS.has(w)))) return null;
  if (strictness === "rigor") return acc >= 97 && extra <= 1 ? "none" : null;
  if (acc >= 97 && extra <= 2) return "none";
  if (acc >= (nWords <= 3 ? 50 : 72) && gap < 5 && extra < Math.max(4, Math.floor(nWords / 2))) return "minor";
  return null;
}

// Returns the severity when the server would accept the line without the LLM, else null.
export function localVerdict({ expected, said, strictness, memory = [] }) {
  const exp = normTokens(expected);
  const notes = memory.filter((n) => !n.new_text).map((n) => normTokens(n.text).join(" "));
  for (let i = 0; i < Math.max(1, exp.length - 3); i++) {
    const gram = exp.slice(i, i + 4).join(" ");
    if (notes.some((n) => n.includes(gram))) return null;
  }
  const m = localMatch(expected, said, strictness === "rigor" ? 0.9 : 0.75);
  return fastVerdict(strictness, m, exp.length, said);
}
