// Mirrors backend norm_tokens / local_match / fast_verdict so the turn can be judged instantly in the browser.
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
  let t = (text || "").toLowerCase().replace(/\([^)]*\)/g, " ").normalize("NFD").replace(/[\u0300-\u036f]/g, "");
  t = t.replace(/[-'’`´]/g, " ").replace(/[^\w\s]/g, " ");
  t = t.split(/\s+/).filter(Boolean).map((w) => NUMS[w] || w).join(" ");
  COLLOQUIAL.forEach(([re, rep]) => { t = t.replace(re, rep); });
  return t.split(/\s+/).filter((w) => w && !FILLERS.has(w));
}

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

export const similar = (a, b, r = 0.75) => !!a && !!b && (a === b || ratio(a, b) >= r);

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
  return hits >= Math.max(1, Math.round(tail.length * 0.67)) && got.length >= Math.max(1, Math.floor(exp.length * 0.6));
}

function opcodes(a, b) {
  const n = a.length;
  const m = b.length;
  const dp = Array.from({ length: n + 1 }, () => new Int32Array(m + 1));
  for (let i = n - 1; i >= 0; i--) for (let j = m - 1; j >= 0; j--) dp[i][j] = a[i] === b[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1]);
  const ops = [];
  let i = 0;
  let j = 0;
  let del = [];
  let ins = [];
  const flush = () => {
    if (del.length && ins.length) ops.push(["replace", del, ins]);
    else if (del.length) ops.push(["delete", del, []]);
    else if (ins.length) ops.push(["insert", [], ins]);
    del = []; ins = [];
  };
  while (i < n || j < m) {
    if (i < n && j < m && a[i] === b[j]) { flush(); ops.push(["equal", [a[i]], [b[j]]]); i++; j++; }
    else if (j >= m || (i < n && dp[i + 1][j] >= dp[i][j + 1])) del.push(a[i++]);
    else ins.push(b[j++]);
  }
  flush();
  return ops;
}

export function localMatch(expected, said, fuzzy = 0.75) {
  const exp = normTokens(expected);
  const got = normTokens(said);
  if (!exp.length) return { accuracy: 100, max_gap: 0, extra: 0, differences: [] };
  let matched = 0; let extra = 0; let maxGap = 0;
  const diffs = [];
  opcodes(exp, got).forEach(([op, a, b]) => {
    if (op === "equal") { matched += a.length; return; }
    if (op === "replace") {
      let fz = 0;
      for (let k = 0; k < Math.min(a.length, b.length); k++) if (ratio(a[k], b[k]) >= fuzzy) fz++;
      matched += fz;
      if (fz === a.length && a.length === b.length) return;
      maxGap = Math.max(maxGap, a.length - fz);
      extra += Math.max(0, b.length - a.length);
      diffs.push({ expected: a.join(" "), said: b.join(" ") });
    } else if (op === "delete") { maxGap = Math.max(maxGap, a.length); diffs.push({ expected: a.join(" "), said: "" }); }
    else { extra += b.length; diffs.push({ expected: "", said: b.join(" ") }); }
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
