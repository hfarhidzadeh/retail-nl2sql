"""Compare a predicted result table against the gold result table.

The model is allowed to return *extra* columns (e.g. store_name next to store_id)
and different column names. Every gold column must be matched, by its values,
by some predicted column, and the rows must then agree.
"""

from collections import Counter


def _norm(v):
    if v is None:
        return None
    if isinstance(v, str):
        try:
            v = float(v)
        except ValueError:
            return v.strip().lower()
    if isinstance(v, (int, float)):
        return round(float(v), 2)
    return v


def _key(v):
    # Lets None, numbers and strings sort together
    return (v is None, type(v).__name__, v if v is not None else 0)


def results_match(gold_rows, pred_rows, ordered=False) -> bool:
    gold = [[_norm(v) for v in r] for r in gold_rows]
    pred = [[_norm(v) for v in r] for r in pred_rows]
    if len(gold) != len(pred):
        return False
    if not gold:
        return True

    gold_cols = list(zip(*gold))
    pred_cols = list(zip(*pred))
    picked = []
    for gc in gold_cols:
        target = sorted(gc, key=_key)
        match = next((i for i, pc in enumerate(pred_cols)
                      if i not in picked and sorted(pc, key=_key) == target), None)
        if match is None:
            return False
        picked.append(match)

    projected = [tuple(r[i] for i in picked) for r in pred]
    gold_t = [tuple(r) for r in gold]
    return projected == gold_t if ordered else Counter(projected) == Counter(gold_t)
