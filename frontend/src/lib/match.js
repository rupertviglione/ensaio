const NUMS = { 0: "zero", 1: "um", 2: "dois", 3: "tres", 4: "quatro", 5: "cinco", 6: "seis", 7: "sete", 8: "oito", 9: "nove", 10: "dez", 11: "onze", 12: "doze", 15: "quinze", 20: "vinte", 30: "trinta", 100: "cem" };
const COLLOQUIAL = [
  [/\bpara (a|à)\b/g, "pra"], [/\bpara o\b/g, "pro"], [/\b(para|pa|pra)\b/g, "pra"],
  [/\bestas\b/g, "tas"], [/\besta\b/g, "ta"], [/\bestou\b/g, "tou"], [/\bestava\b/g, "tava"],
  [/\bnao e\b/g, "ne"], [/\bcom o\b/g, "co"], [/\bcom a\b/g, "ca"], [/\bde um\b/g, "dum"], [/\bde uma\b/g, "duma"],
];
const FILLERS = new Set(["hum", "hmm", "eh", "ah", "ahn", "uh", "pronto"]);
const HELP = /\b(texto|linha|deixa|mudamos|agora digo|em vez de|nao me lembro)\b/;

export function normTokens(text) {
  let t = (text || "").toLowerCase().replace(/\([^)]*\)/g, " ").normalize("NFD").replace(/[\u0300-\u036f]/g, "");
  t = t.replace(/[-'’`´]/g, " ").replace(/[^\w\s]/g, " ");
  t = t.split(/\s+/).filter(Boolean).map((w) => NUMS[w] || w).join(" ");
  COLLOQUIAL.forEach(([re, rep]) => { t = t.replace(re, rep); });
  return t.split(/\s+/).filter((w) => w && !FILLERS.has(w));
}

const similar = (a, b) => {
  if (a === b) return true;
  const n = Math.max(a.length, b.length);
  let same = 0;
  for (let i = 0; i < Math.min(a.length, b.length); i++) if (a[i] === b[i]) same++;
  return same / n >= 0.75;
};

export function isComplete(expected, said) {
  const exp = normTokens(expected);
  const got = normTokens(said);
  if (!got.length) return false;
  if (HELP.test(got.join(" "))) return false;
  const tail = exp.slice(-Math.min(3, exp.length));
  const win = got.slice(-(tail.length + 2));
  let hits = 0;
  let j = 0;
  tail.forEach((t) => {
    for (let k = j; k < win.length; k++) if (similar(t, win[k])) { hits++; j = k + 1; break; }
  });
  return hits >= Math.max(1, Math.round(tail.length * 0.67)) && got.length >= Math.max(1, Math.floor(exp.length * 0.6));
}
