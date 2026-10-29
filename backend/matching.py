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


def local_match(expected: str, said: str, fuzzy_ratio: float = 0.75) -> dict:
    exp, got = norm_tokens(expected), norm_tokens(said)
    if not exp:
        return {"accuracy": 100.0, "max_gap": 0, "extra": 0, "differences": []}
    pe, pg = [phon(w) for w in exp], [phon(w) for w in got]
    sm = difflib.SequenceMatcher(a=pe, b=pg, autojunk=False)
    matched, extra, max_gap, diffs = 0, 0, 0, []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        a, b = exp[i1:i2], got[j1:j2]
        if op == "equal":
            matched += len(a)
            continue
        if op == "replace":
            if same_run(a, b, fuzzy_ratio):
                matched += len(a)
                continue
            fuzzy = sum(1 for x, y in zip(a, b) if same_word(x, y, fuzzy_ratio))
            matched += fuzzy
            if fuzzy == len(a) == len(b):
                continue
            max_gap = max(max_gap, len(a) - fuzzy)
            extra += max(0, len(b) - len(a))
            diffs.append({"expected": " ".join(a), "said": " ".join(b), "type": "troca", "pos": i1})
        elif op == "delete":
            max_gap = max(max_gap, len(a))
            diffs.append({"expected": " ".join(a), "said": "", "type": "omissão" if len(a) < 5 else "salto", "pos": i1})
        elif op == "insert":
            extra += len(b)
            diffs.append({"expected": "", "said": " ".join(b), "type": "acrescento", "pos": i1})
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
