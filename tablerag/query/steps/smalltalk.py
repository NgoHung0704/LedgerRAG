"""Small-talk step: answer a greeting as a greeting, not as a failed search.

"Salut", "merci", "que peux-tu faire ?" are not document questions. Running them
through routing + retrieval burns an LLM routing call, an embedding, three
Qdrant searches and a rerank, and then answers "no relevant passages were found"
— slow, and rude to a user who just said hello.

Classification is DETERMINISTIC (no model call) and deliberately conservative,
because the expensive mistake is one-directional: misreading a real question as
small talk would refuse to search the documents at all. So a message is small
talk ONLY when EVERY word belongs to a closed conversational vocabulary (or the
whole message matches a capability question). Any content word, any digit, or
more than a handful of words -> normal retrieval. "Bonjour, quel est le salaire
de la classe 11 ?" therefore goes to retrieval, as it must.

Test guard: every question in the eval sets must classify as NOT small talk
(tests/unit/test_smalltalk.py).
"""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass
from typing import AsyncIterator

from tablerag.query.pipeline import QueryContext

logger = logging.getLogger(__name__)

# a conversational opener is short; anything longer is a real request
MAX_WORDS = 8

_PUNCT = re.compile(r"[^\w\s]", re.UNICODE)
_WS = re.compile(r"\s+")


# NFKD leaves these alone — they are letters in their own right, not a base
# plus a combining mark — so fold them by hand or Vietnamese never matches
# ("được" would normalise to "đuoc", not "duoc").
_LETTER_FOLD = str.maketrans({"đ": "d", "Đ": "d", "ø": "o", "æ": "ae", "œ": "oe",
                              "ß": "ss", "ł": "l"})


def _norm(text: str) -> str:
    """lowercase, accent-folded, punctuation -> space ("d'accord" -> "d accord")."""
    folded = unicodedata.normalize("NFKD", text.lower().translate(_LETTER_FOLD))
    folded = "".join(c for c in folded if not unicodedata.combining(c))
    return _WS.sub(" ", _PUNCT.sub(" ", folded)).strip()


# (kind, language, phrases). Phrases are normalized at import time; their words
# also form the allowed vocabulary, so combinations like "bonjour ca va" work.
_CATEGORIES: list[tuple[str, str, tuple[str, ...]]] = [
    ("greeting", "fr", ("salut", "bonjour", "bonsoir", "coucou", "allo",
                        "bonne journee", "bonne soiree")),
    ("greeting", "en", ("hello", "hi", "hey", "yo", "good morning",
                        "good afternoon", "good evening")),
    ("greeting", "vi", ("chao", "xin chao", "chao ban", "alo")),
    ("thanks", "fr", ("merci", "merci beaucoup", "mille mercis")),
    ("thanks", "en", ("thanks", "thank you", "thx", "many thanks")),
    ("thanks", "vi", ("cam on", "cam on ban", "cam on nhe")),
    ("bye", "fr", ("au revoir", "a bientot", "adieu", "bonne fin de journee")),
    ("bye", "en", ("bye", "goodbye", "see you", "good night")),
    ("bye", "vi", ("tam biet", "hen gap lai")),
    ("howareyou", "fr", ("ca va", "comment ca va", "comment vas tu",
                         "comment allez vous", "tu vas bien", "vous allez bien")),
    ("howareyou", "en", ("how are you", "how are you doing", "how s it going")),
    ("howareyou", "vi", ("ban khoe khong", "khoe khong")),
    ("ack", "fr", ("ok", "d accord", "tres bien", "parfait", "super",
                   "compris", "entendu", "genial")),
    ("ack", "en", ("ok", "okay", "got it", "alright", "cool", "nice",
                   "perfect", "great")),
    ("ack", "vi", ("ok", "duoc roi", "hieu roi", "tot roi")),
]

# whole-message "who are you / what can you do" questions. Matched as anchored
# regexes so their content words never enter the permissive vocabulary, and a
# question that merely STARTS this way ("qui es-tu et quel est le salaire… ?")
# still goes to retrieval.
#
# Conjugation and word order vary far more than a literal list survives — real
# users write "qui est tu ?", "t'es qui", "vous êtes qui ?" — so each pattern
# spells out the variants rather than one canonical form.
_CAPABILITY: list[tuple[str, str]] = [
    # FR — identity
    ("fr", r"^(qui (es|est|etes|ete|es ce que|est ce que) (tu|vous|ce)"
           r"|(tu|vous) (es|est|etes) qui"
           r"|t es qui|c est qui|qui est ce"
           r"|c est quoi (ce|cet|cette) (chat|bot|assistant|outil|truc)"
           r"|presente toi|presentez vous)$"),
    # FR — capability
    ("fr", r"^((que|qu est ce que|qu est ce qu|quoi que) ?(tu peux|tu sais"
           r"|vous pouvez|vous savez) faire"
           r"|(tu peux|tu sais|vous pouvez|vous savez) faire quoi"
           r"|que (peux|sais) tu faire|que (pouvez|savez) vous faire"
           r"|(tu sers|vous servez) a quoi|a quoi (tu sers|sers tu"
           r"|vous servez|servez vous|ca sert|sert ce chat)"
           r"|comment (ca|cela) (marche|fonctionne)"
           r"|comment (tu|vous) (marche|marches|marchez|fonctionne|fonctionnes"
           r"|fonctionnez)"
           r"|quelles sont tes (capacites|fonctions|competences)"
           r"|(tu peux|vous pouvez) m aider"
           r"|aide|aide moi|a l aide)$"),
    # EN
    ("en", r"^((who|what) (are|r) (you|u)|who is this|what is this( chat| bot"
           r"| tool| assistant)?|introduce yourself)$"),
    ("en", r"^(what can (you|u) do|what do (you|u) do|how (do|does) (you|this"
           r"|it) work|what are you for|help|help me)$"),
    # VI
    ("vi", r"^(ban la ai|ban ten (gi|la gi)|ai day|ban la gi"
           r"|gioi thieu( ve)?( ban| minh| chinh minh)?)$"),
    ("vi", r"^(ban lam duoc gi|ban co the lam gi|ban giup duoc gi|giup gi"
           r"|huong dan|ban dung de lam gi)$"),
]

# a greeting glued in front of a capability question ("bonjour, qui es-tu ?")
# is still small talk — strip the greeting, then match
_LEADING_GREETING = re.compile(
    r"^(bonjour|bonsoir|salut|coucou|hello|hi|hey|xin chao|chao|alo|allo)\s+")
# trailing politeness likewise
_TRAILING_POLITENESS = re.compile(
    r"\s+(s il (te|vous) plait|svp|stp|please|merci|nhe|a)$")

# glue words that may appear alongside a greeting without making it a request
_FILLERS = frozenset((
    "et", "s", "il", "vous", "te", "toi", "plait", "svp", "stp", "please",
    "beaucoup", "bien", "tout", "le", "la", "les", "de", "du", "a", "au",
    "je", "tu", "moi", "encore", "aussi", "donc", "alors", "hein", "bon",
    "the", "you", "so", "much", "very", "all", "again", "and", "ban", "nhe",
    "a", "oi", "voi", "nha",
))

_VOCAB = frozenset(
    word
    for _, _, phrases in _CATEGORIES
    for phrase in phrases
    for word in _norm(phrase).split()
) | _FILLERS

_HAS_DIGIT = re.compile(r"\d")


@dataclass(frozen=True)
class SmallTalkMatch:
    kind: str          # greeting | thanks | bye | howareyou | ack | capability
    language: str | None   # fr | en | vi | None when undetermined


def classify_smalltalk(question: str) -> SmallTalkMatch | None:
    """A conversational message, or None when it must go to retrieval.

    Conservative by construction: only a short message whose EVERY word is in
    the closed conversational vocabulary (or a whole-message capability
    question) qualifies. A digit or any content word means retrieval."""
    norm = _norm(question or "")
    if not norm:
        return None

    # "bonjour, qui es-tu, svp ?" is a capability question wearing manners
    core = norm
    while (m := _LEADING_GREETING.match(core)):
        core = core[m.end():]
    core = _TRAILING_POLITENESS.sub("", core).strip()
    for lang, pattern in _CAPABILITY:
        if core and re.match(pattern, core):
            return SmallTalkMatch("capability", lang)

    words = norm.split()
    if len(words) > MAX_WORDS or _HAS_DIGIT.search(norm):
        return None
    if not all(word in _VOCAB for word in words):
        return None

    # every word is conversational — name the category by the first phrase hit
    for kind, lang, phrases in _CATEGORIES:
        for phrase in phrases:
            tokens = _norm(phrase).split()
            if all(t in words for t in tokens):
                return SmallTalkMatch(kind, lang)
    return SmallTalkMatch("greeting", None)


SMALLTALK_SYSTEM = """\
You are {identity}

The user's message is conversational — a greeting, thanks, or a question about \
who you are and what you can do — not a question about the documents.

Reply in ONE or TWO short sentences, in the SAME language as the user's \
message. Be warm and plain. If they ask who you are or what you can do, say so \
from the description above and invite them to ask about their documents. You \
have not consulted any document for this message, so never state any fact, \
figure, name or date from one.\
"""


def build_smalltalk_prompt(identity: str = "",
                           extra_instructions: str = "") -> str:
    """Identity first — this is the path that answers "qui es-tu ?", so the
    assistant must know what it is. Falls back to the built-in description."""
    from tablerag.query.steps.generate import DEFAULT_IDENTITY

    prompt = SMALLTALK_SYSTEM.format(
        identity=(identity or "").strip() or DEFAULT_IDENTITY)
    extra = (extra_instructions or "").strip()
    # operator tone guidance still applies to conversational replies
    return f"{prompt}\n\n{extra}" if extra else prompt

# used only if the model is unreachable — a greeting must never surface an error
_FALLBACK = {
    "fr": "Je suis là pour répondre à vos questions sur vos documents — "
          "n'hésitez pas.",
    "en": "I'm here to answer questions about your documents — just ask.",
    "vi": "Tôi ở đây để trả lời câu hỏi về tài liệu của bạn — bạn cứ hỏi nhé.",
}


class SmallTalk:
    """First pipeline step. On a conversational message it answers directly and
    sets ctx.short_circuit, so routing, retrieval, reranking and verification
    are skipped entirely; otherwise it is a no-op."""

    async def run(self, ctx: QueryContext) -> QueryContext:
        async for _ in self.stream(ctx):
            pass
        return ctx

    async def stream(self, ctx: QueryContext) -> AsyncIterator[str]:
        from tablerag.core.config import get_settings

        if not get_settings().smalltalk_enabled:
            return
        match = classify_smalltalk(ctx.question)
        if match is None:
            return

        logger.info("small talk (%s/%s): answering without retrieval",
                    match.kind, match.language)
        ctx.short_circuit = True
        ctx.answer = ""
        try:
            async for token in self._reply(ctx):
                ctx.answer += token
                yield token
        except Exception:  # noqa: BLE001 — a greeting must never show an error
            logger.exception("small-talk reply failed; using the canned one")
        if not ctx.answer.strip():
            ctx.answer = _FALLBACK.get(match.language or "en", _FALLBACK["en"])
            yield ctx.answer

    async def _reply(self, ctx: QueryContext) -> AsyncIterator[str]:
        from tablerag.models.base import Msg
        from tablerag.models.registry import get_provider

        system = build_smalltalk_prompt(ctx.identity, ctx.extra_instructions)
        chat = get_provider("chat")
        messages = [Msg(role="system", content=system),
                    Msg(role="user", content=ctx.question)]
        async for token in chat.chat(messages, stream=True, temperature=0.0,
                                     options={"temperature": 0.0}):
            yield token
