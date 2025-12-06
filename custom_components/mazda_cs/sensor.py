def _pct(value):
    try:
        if value is None:
            return None
        v = float(value)
        if v < 0 or v > 100:
            return None
        return float(v)
    except Exception:
        return None

def _num(value):
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None
