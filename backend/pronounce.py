"""Foreign words/names (Pronúncia): detection with Claude, TTS respelling, STT keyterms and matching aliases."""
import re
import unicodedata
from functools import lru_cache

from wordfreq import zipf_frequency

FOREIGN_SYSTEM = """Recebes falas de um texto de teatro em português europeu (PT-PT).
Lista as palavras, nomes de pessoas, lugares, obras e expressões que estão ESCRITOS NA FORMA ESTRANGEIRA (francês, inglês, italiano, alemão, espanhol, latim, etc.) e que por isso se dizem na língua original.
REGRA: segue a grafia do texto. "New York" diz-se em inglês; "Nova Iorque" diz-se em português e NÃO entra na lista. Nunca "corrijas" para a língua original uma palavra ou nome já escrito em português (ex.: Londres, Florença, Shakespeare aportuguesado como "Xequespir" fica como está).
Não incluas palavras portuguesas nem estrangeirismos totalmente aportuguesados (ex.: futebol, abajur, croquete).
Para cada uma dá:
- "text": exactamente como aparece no texto
- "lang": código ISO da língua (fr, en, it, de, es, la…)
- "say": grafia fonética para uma voz sintética PORTUGUESA (PT-PT) dizer como na língua original (ex.: "Jean Genet" → "Jã Jâné", "Shakespeare" → "Xêikspir", "Giuseppe" → "Djuzépe")
- "variants": 2 a 4 formas como um reconhecimento de voz português pode transcrever o que ouve (ex.: "jã jené", "jean jenê")
Responde APENAS JSON: {"items":[{"text":"...","lang":"..","say":"...","variants":["..."]}]}  (lista vazia se não houver)"""


def fold(s: str) -> str:
    s = unicodedata.normalize("NFKD", (s or "").lower())
    return "".join(c for c in s if not unicodedata.combining(c))


def clean_items(items) -> list:
    out, seen = [], set()
    for it in items or []:
        text = str(it.get("text", "")).strip()
        if not text or fold(text) in seen:
            continue
        seen.add(fold(text))
        out.append({"text": text, "lang": str(it.get("lang", "")).strip()[:5], "say": str(it.get("say") or text).strip(),
                    "variants": [str(v).strip() for v in (it.get("variants") or []) if str(v).strip()][:6]})
    return out


def _pattern(text: str):
    return re.compile(rf"(?<![\wÀ-ÿ]){re.escape(text)}(?![\wÀ-ÿ])", re.IGNORECASE)


def say_text(items: list, text: str) -> str:
    for it in sorted(items or [], key=lambda x: -len(x["text"])):
        if it.get("say") and it["say"] != it["text"]:
            text = _pattern(it["text"]).sub(it["say"], text)
    return text


def alias_pairs(items: list) -> list:
    """(heard variant, script spelling) pairs for matching."""
    return [(v, it["text"]) for it in items or [] for v in {it.get("say", ""), *it.get("variants", [])} if v and fold(v) != fold(it["text"])]


@lru_cache(maxsize=20000)
def rare(w: str) -> bool:
    return zipf_frequency(w.lower(), "pt") < 3.0


def line_keyterms(text: str, items: list) -> list:
    out = []
    t = re.sub(r"\([^)]*\)", " ", text)
    for it in items or []:
        if _pattern(it["text"]).search(t):
            out.append(it["text"])
    for k, mt in enumerate(re.finditer(r"[\wÀ-ÿ'’-]+", t)):
        w = mt.group(0).strip("-'’")
        before = t[:mt.start()].rstrip()
        cap = w[:1].isupper() and k > 0 and not w.isupper() and not before.endswith((".", "!", "?", "…", ":", "—", "–", "-"))
        if len(w) >= 4 and (rare(w) or cap) and w not in out:
            out.append(w)
    return out
