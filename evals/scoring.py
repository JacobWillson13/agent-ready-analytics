import re

_FINAL = re.compile(r"FINAL ANSWER:\s*(.+)", re.IGNORECASE)


def extract(text: str) -> str | None:
    m = _FINAL.findall(text or "")
    return m[-1].strip() if m else None


def to_number(s: str) -> float | None:
    s = s.replace(",", "").replace("$", "").replace("%", "").strip()
    m = re.search(r"-?\d+(\.\d+)?", s)
    return float(m.group()) if m else None


def score(answer_text: str, expected, kind: str, tol: float) -> tuple[bool, str]:
    got = extract(answer_text)
    if got is None:
        return False, "no FINAL ANSWER line"
    if kind == "category":
        ok = got.strip().strip(".").upper() == str(expected).upper()
        return ok, f"got {got!r}, expected {expected!r}"
    val = to_number(got)
    if val is None:
        return False, f"unparseable {got!r}"
    exp = float(expected)
    if kind == "percent":
        ok = abs(val - exp) <= tol
    elif tol == 0:
        ok = round(val) == round(exp)
    else:
        ok = abs(val - exp) <= max(0.5, abs(exp) * tol)
    return ok, f"got {val}, expected {exp}"
