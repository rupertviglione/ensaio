import os
import re
import difflib
import unicodedata
from typing import List

NUMS = {"0": "zero", "1": "um", "2": "dois", "3": "tres", "4": "quatro", "5": "cinco", "6": "seis", "7": "sete",
        "8": "oito", "9": "nove", "10": "dez", "11": "onze", "12": "doze", "15": "quinze", "20": "vinte",
        "30": "trinta", "100": "cem"}
COLLOQUIAL = [
    (r"\bpara (a|à)\b", "pra"), (r"\bpara o\b", "pro"), (r"\b(para|pa|pra)\b", "pra"),
    (r"\bestas\b", "tas"), (r"\besta\b", "ta"), (r"\bestou\b", "tou"), (r"\bestava\b", "tava"),
    (r"\bestavas\b", "tavas"), (r"\bestamos\b", "tamos"), (r"\bestao\b", "tao"),
    (r"\bnao e\b", "ne"), (r"\bcom o\b", "co"), (r"\bcom a\b", "ca"), (r"\bde um\b", "dum"), (r"\bde uma\b", "duma"),
    (r"\bem um\b", "num"), (r"\bem uma\b", "numa"), (r"\bpois e\b", "poise"),
]
FILLERS = {"hum", "hmm", "eh", "ah", "ahn", "uh", "um hum", "pronto"}
NEGATIONS = {"nao", "ne", "nunca", "nada", "nem", "ninguem", "jamais", "sim"}
NEEDS_AI = re.compile(r"\b(texto|linha|deixa|mudamos|mudaram|agora digo|passei a dizer|em vez de|cortamos|nao me lembro|como e que e)\b")


def norm_tokens(text: str) -> List[str]:
    t = re.sub(r"\([^)]*\)", " ", text.lower()).replace("ç", "ss")
    t = unicodedata.normalize("NFKD", t)
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = re.sub(r"[-'’`´]", " ", t)
    t = re.sub(r"[^\w\s]", " ", t)
    t = " ".join(NUMS.get(w, w) for w in t.split())
    for pat, rep in COLLOQUIAL:
        t = re.sub(pat, rep, t)
    return [w for w in t.split() if w not in FILLERS]


def phon(w: str) -> str:
    """Simplified pt-PT phonetic key: words that sound alike get the same key."""
    if not w:
        return w
    p = w.replace("ss", "S").replace("rr", "R").replace("ch", "x").replace("lh", "L").replace("nh", "N").replace("h", "")
    p = re.sub(r"qu(?=[ei])", "k", p)
    p = re.sub(r"gu(?=[ei])", "g", p)
    p = re.sub(r"c(?=[ei])", "S", p)
    p = p.replace("qu", "k").replace("q", "k").replace("c", "k")
    p = re.sub(r"g(?=[ei])", "j", p)
    p = re.sub(r"(?<=[aeiou])s(?=[aeiou])", "z", p).replace("S", "s")
    p = re.sub(r"^r", "R", p).replace("w", "v").replace("y", "i")
    p = re.sub(r"z$", "s", p)
    p = re.sub(r"am$", "ao", p)
    if len(p) > 3:
        p = re.sub(r"es$", "s", p)
        p = re.sub(r"e$", "", p)
    p = p.replace("ou", "o").replace("ei", "e")
    if len(p) > 1:
        p = re.sub(r"os$", "us", p)
        p = re.sub(r"o$", "u", p)
    p = re.sub(r"(.)\1+", r"\1", p)
    return p or w


def ratio(a: str, b: str) -> float:
    return difflib.SequenceMatcher(a=a, b=b, autojunk=False).ratio()


def same_word(x: str, y: str, fuzzy: float = 0.75) -> bool:
    if x == y:
        return True
    px, py = phon(x), phon(y)
    if px == py:
        return True
    if min(len(px), len(py)) >= 5 and ratio(px, py) >= 0.85:
        return True
    return ratio(x, y) >= fuzzy


def same_run(a: List[str], b: List[str], fuzzy: float = 0.75) -> bool:
    """Merged / split words or small distortions over a whole run ("deixei o" ~ "deixeio")."""
    ja, jb = "".join(phon(x) for x in a), "".join(phon(x) for x in b)
    if not ja or not jb:
        return False
    if ja == jb or phon("".join(a)) == phon("".join(b)):
        return True
    if min(len(ja), len(jb)) >= 4 and ratio(ja, jb) >= max(0.85, fuzzy):
        return True
    # pt-PT reduces unstressed vowels: same consonant skeleton + close spelling sounds alike ("parece a" ~ "pra essa")
    return min(len(ja), len(jb)) >= 5 and skeleton(ja) == skeleton(jb) and ratio(ja, jb) >= 0.75


def skeleton(p: str) -> str:
    return re.sub(r"[aeiou]", "", p)


LETTERS = {"a": "á", "b": "bê", "c": "cê", "d": "dê", "e": "é", "f": "efe", "g": "guê", "h": "agá", "i": "i", "j": "jota", "k": "capa",
           "l": "ele", "m": "eme", "n": "ene", "o": "ó", "p": "pê", "q": "quê", "r": "erre", "s": "esse", "t": "tê", "u": "u", "v": "vê",
           "w": "dâblio", "x": "xis", "y": "ípsilon", "z": "zê"}
ONE_LETTER_WORDS = {"a", "e", "o", "à", "é", "ó", "á", "ò"}


def spell_heard(said: str) -> tuple:
    """ASR output → (text, set of implausible words): acronyms/letters are spelled out, digits become words."""
    out, odd = [], set()
    for raw in re.findall(r"\S+", said or ""):
        core = re.sub(r"^\W+|\W+$", "", raw)
        if re.fullmatch(r"[A-Z]{2,6}", core) or (len(core) == 1 and core.isalpha() and core.lower() not in ONE_LETTER_WORDS):
            names = [LETTERS.get(c.lower(), c) for c in core]
            out.extend(names)
            odd.update(norm_tokens(" ".join(names)))
        elif re.fullmatch(r"\d+([.,]\d+)?", core):
            try:
                from num2words import num2words
                out.append(num2words(int(re.sub(r"\D", "", core)), lang="pt_PT"))
            except Exception:
                out.append(core)
        else:
            out.append(raw)
    return " ".join(out), odd


def is_word(w: str) -> bool:
    try:
        from wordfreq import zipf_frequency
        return zipf_frequency(w, "pt") > 0 or len(w) <= 2
    except Exception:
        return True


def sim(a: List[str], b: List[str]) -> float:
    """Phonetic similarity of two word runs (character level, merges allowed, prefix-tolerant)."""
    ja, jb = "".join(phon(x) for x in a), "".join(phon(x) for x in b)
    if not ja or not jb:
        return 0.0
    if ja == jb:
        return 1.0
    r = ratio(ja, jb)
    if min(len(ja), len(jb)) >= 5 and skeleton(ja) == skeleton(jb):
        r = max(r, 0.8)
    pre = len(os.path.commonprefix([ja, jb]))
    if pre >= 5 and pre >= 0.6 * len(ja) and len(jb) <= len(ja) + 2:
        r = max(r, 0.8)
    return r


MERGES = [(1, 1), (1, 2), (2, 1), (1, 3), (3, 1), (2, 3), (3, 2)]


def align_region(a: List[str], b: List[str], odd: set, thr: float) -> List[tuple]:
    """DP alignment of expected run a vs heard run b. Returns steps (i1, i2, j1, j2, ok)."""
    n, m = len(a), len(b)
    INF = float("inf")
    cost = [[INF] * (m + 1) for _ in range(n + 1)]
    back = [[None] * (m + 1) for _ in range(n + 1)]
    cost[0][0] = 0.0
    for i in range(n + 1):
        for j in range(m + 1):
            c = cost[i][j]
            if c == INF:
                continue
            cand = [(1, 0, 1.0, False), (0, 1, 0.0 if j < m and b[j] in odd else 0.9, False)]
            for di, dj in MERGES:
                if i + di <= n and j + dj <= m:
                    ha = b[j:j + dj]
                    s = sim(a[i:i + di], ha)
                    ok = s >= thr or all(w in odd for w in ha)
                    cand.append((di, dj, (1 - s) * 0.5 if ok else 1.2, ok))
            for di, dj, w, ok in cand:
                if i + di > n or j + dj > m:
                    continue
                if c + w < cost[i + di][j + dj]:
                    cost[i + di][j + dj] = c + w
                    back[i + di][j + dj] = (i, j, ok)
    steps, i, j = [], n, m
    while i or j:
        pi, pj, ok = back[i][j]
        steps.append((pi, i, pj, j, ok))
        i, j = pi, pj
    return steps[::-1]


def apply_aliases(got: List[str], aliases) -> List[str]:
    for variant, orig in sorted(aliases or [], key=lambda x: -len(x[0])):
        v, o = [phon(w) for w in norm_tokens(variant)], norm_tokens(orig)
        if not v:
            continue
        i, out = 0, []
        while i < len(got):
            if [phon(w) for w in got[i:i + len(v)]] == v:
                out.extend(o)
                i += len(v)
            else:
                out.append(got[i])
                i += 1
        got = out
    return got


def merge_ops(ops, exp: List[str]) -> list:
    """A lone short word matched between two gaps is usually a coincidence: merge into one region."""
    out = []
    for op in ops:
        if out and op[0] != "equal" and out[-1][0] != "equal":
            p = out[-1]
            out[-1] = ("replace", p[1], op[2], p[3], op[4])
        else:
            out.append(tuple(op))
    k = 1
    while k < len(out) - 1:
        op, i1, i2 = out[k][:3]
        if op == "equal" and i2 - i1 == 1 and len(exp[i1]) <= 2 and out[k - 1][0] != "equal" and out[k + 1][0] != "equal":
            out[k - 1:k + 2] = [("replace", out[k - 1][1], out[k + 1][2], out[k - 1][3], out[k + 1][4])]
            k = max(1, k - 1)
        else:
            k += 1
    return out


def local_match(expected: str, said: str, fuzzy_ratio: float = 0.75, aliases=()) -> dict:
    heard, odd = spell_heard(said)
    exp, got = norm_tokens(expected), apply_aliases(norm_tokens(heard), aliases)
    if not exp:
        return {"accuracy": 100.0, "max_gap": 0, "extra": 0, "differences": []}
    odd |= {w for w in got if len(w) > 3 and not is_word(w) and w not in exp}
    thr = max(0.72, fuzzy_ratio - 0.03)
    pe, pg = [phon(w) for w in exp], [phon(w) for w in got]
    sm = difflib.SequenceMatcher(a=pe, b=pg, autojunk=False)
    matched, extra, max_gap, diffs = 0, 0, 0, []

    def add(i1, i2, j1, j2):
        nonlocal extra, max_gap
        a, b = exp[i1:i2], got[j1:j2]
        if not a and all(w in odd for w in b):
            return
        max_gap = max(max_gap, len(a))
        extra += max(0, len(b) - len(a))
        kind = "acrescento" if not a else "omissão" if not b and len(a) < 5 else "salto" if not b else "troca"
        diffs.append({"expected": " ".join(a), "said": " ".join(b), "type": kind, "pos": i1})

    for op, i1, i2, j1, j2 in merge_ops(sm.get_opcodes(), exp):
        if op == "equal":
            matched += i2 - i1
            continue
        a, b = exp[i1:i2], got[j1:j2]
        if a and b and (same_run(a, b, fuzzy_ratio) or (all(w in odd for w in b) and len(b) <= 3 * len(a) + 2)):
            matched += len(a)
            continue
        if not a or not b or len(a) * len(b) > 400:
            add(i1, i2, j1, j2)
            continue
        pend = None
        for si1, si2, sj1, sj2, ok in align_region(a, b, odd, thr):
            if ok:
                matched += si2 - si1
                if pend:
                    add(*pend)
                    pend = None
            elif pend:
                pend = (pend[0], i1 + si2, pend[2], j1 + sj2)
            else:
                pend = (i1 + si1, i1 + si2, j1 + sj1, j1 + sj2)
        if pend:
            add(*pend)
    return {"accuracy": round(100 * matched / len(exp), 1), "max_gap": max_gap, "extra": extra, "differences": diffs}


def fast_verdict(strictness: str, m: dict, n_words: int, said: str = ""):
    """Devolve (aceita_já, severidade) ou None para pedir à IA."""
    acc, gap, extra = m["accuracy"], m["max_gap"], m["extra"]
    if acc < 97 and NEEDS_AI.search(" ".join(norm_tokens(said))):
        return None
    if strictness == "nunca":
        return (True, ("none" if acc >= 97 else "minor")) if acc >= 50 else None
    if any(w in NEGATIONS for d in m["differences"] for w in f"{d['expected']} {d['said']}".split()):
        return None
    if strictness == "rigor":
        if acc >= 97 and extra <= 1:
            return True, "none"
        return None
    short = n_words <= 3
    if acc >= 97 and extra <= 2:
        return True, "none"
    if (acc >= (50 if short else 72)) and gap < 5 and extra < max(4, n_words // 2):
        return True, "minor"
    return None


def final_accuracy(n_exp: int, real: List[dict]) -> float:
    if not n_exp:
        return 100.0
    lost = sum(len(d.get("expected", "").split()) or max(1, len(d.get("said", "").split()) // 2) for d in real)
    return round(max(0.0, 100 * (n_exp - lost) / n_exp), 1)
