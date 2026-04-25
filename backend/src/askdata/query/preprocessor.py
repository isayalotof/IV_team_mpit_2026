import re
from askdata.semantic.loader import get_semantic_layer


def preprocess(text: str) -> str:
    text = text.strip()
    text = re.sub(r"\s+", " ", text)
    # Normalize ё → е
    text = text.replace("ё", "е").replace("Ё", "Е")

    sl = get_semantic_layer()
    text_lower = text.lower()

    # Expand synonyms using word boundaries to avoid partial-word replacement
    # Sort by length descending so longer synonyms are matched before shorter substrings
    _ye = lambda s: s.replace("ё", "е").replace("Ё", "Е")  # noqa: E731
    all_synonyms = []
    for canonical, synonyms in sl.synonyms.items():
        for syn in synonyms:
            syn_n = _ye(syn)
            if syn_n != _ye(canonical):
                all_synonyms.append((len(syn_n), syn_n, canonical))
    all_synonyms.sort(reverse=True)

    for _, syn, canonical in all_synonyms:
        # syn is already ё-normalized here so it matches against ё-normalized text_lower
        pattern = r'(?<!\w)' + re.escape(syn) + r'(?!\w)'
        text_lower = re.sub(pattern, canonical, text_lower)

    return text_lower
