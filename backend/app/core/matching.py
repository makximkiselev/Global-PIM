import re
from typing import Any, Iterable, Set

from rapidfuzz import fuzz


_UNIT_TOKENS = {
    "mah",
    "ip",
    "мм",
    "см",
    "гц",
    "ом",
    "вт",
    "г",
    "ч",
    "мин",
    "мaч",
}


def normalize_match_text(value: Any, *, drop_units: bool = False) -> str:
    text = str(value or "").lower().strip().replace("ё", "е")
    text = re.sub(r"\(.*?\)", " ", text)
    text = re.sub(r"[,:;./\\|+_#№\"'`~!?-]+", " ", text)
    if drop_units:
        units = "|".join(re.escape(unit) for unit in sorted(_UNIT_TOKENS, key=len, reverse=True))
        text = re.sub(rf"\b({units})\b", " ", text, flags=re.I)
    return re.sub(r"\s+", " ", text).strip()


def match_tokens(value: Any, *, drop_units: bool = False) -> Set[str]:
    normalized = normalize_match_text(value, drop_units=drop_units)
    return {token for token in normalized.split(" ") if token}


def token_jaccard(left: Iterable[str], right: Iterable[str]) -> float:
    left_set = {str(item) for item in left if str(item or "").strip()}
    right_set = {str(item) for item in right if str(item or "").strip()}
    if not left_set or not right_set:
        return 0.0
    return len(left_set & right_set) / max(len(left_set | right_set), 1)


def fuzzy_text_similarity(left: Any, right: Any, *, drop_units: bool = False) -> float:
    left_norm = normalize_match_text(left, drop_units=drop_units)
    right_norm = normalize_match_text(right, drop_units=drop_units)
    if not left_norm or not right_norm:
        return 0.0
    if left_norm == right_norm:
        return 1.0
    token_set = fuzz.token_set_ratio(left_norm, right_norm) / 100.0
    token_sort = fuzz.token_sort_ratio(left_norm, right_norm) / 100.0
    partial = fuzz.partial_ratio(left_norm, right_norm) / 100.0
    return max(token_set, token_sort, partial * 0.92)


def value_pair_similarity(left: Any, right: Any) -> float:
    left_norm = normalize_match_text(left, drop_units=True)
    right_norm = normalize_match_text(right, drop_units=True)
    if not left_norm or not right_norm:
        return 0.0
    if left_norm == right_norm:
        return 1.0
    overlap = token_jaccard(left_norm.split(), right_norm.split())
    containment = 0.0
    if len(left_norm) >= 3 and left_norm in right_norm:
        containment = len(left_norm) / max(len(right_norm), 1)
    elif len(right_norm) >= 3 and right_norm in left_norm:
        containment = len(right_norm) / max(len(left_norm), 1)
    return max(overlap, containment * 0.9, fuzzy_text_similarity(left_norm, right_norm, drop_units=True))
