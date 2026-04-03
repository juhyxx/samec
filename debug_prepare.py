#!/usr/bin/env python3
import json
import re
from pathlib import Path


def _normalize_code_token(tok: str) -> str:
    if not tok:
        return tok
    t = tok.strip()
    t = t.replace("I", "1").replace("l", "1").replace("O", "0").replace("o", "0")
    t = re.sub(r"^[^A-Za-z0-9]+|[^A-Za-z0-9]+$", "", t)
    t = re.sub(r"[\s\._]+", "-", t)
    m = re.match(r"^([A-Za-z]{1,3}-?\d{1,4})", t)
    if m:
        return m.group(1)
    return t


def _is_code_like(tok: str) -> bool:
    if not tok:
        return False
    t = _normalize_code_token(tok)
    if re.match(r"^[A-Za-z]{1,3}-?\d{1,4}$", t):
        return True
    if re.match(r"^\d{1,3}[\.]?\d{1,3}$", t):
        return True
    return False


rows = json.loads(Path("data/gunze_rows.json").read_text())
test_idx = 3  # H2 X-1 21 7
r = rows[test_idx]

raw_name = (r.get("raw_reference") or r.get("reference") or "").strip()
code_field = (r.get("name") or "").strip()
print(f"raw_name: {raw_name!r}")
print(f"code_field: {code_field!r}")

code = None
display_name = raw_name
print(f"initial display_name: {display_name!r}")

if code_field and _is_code_like(code_field):
    print(f"code_field is code-like")
    code = _normalize_code_token(code_field).upper()
    display_name = raw_name or code
else:
    print(f"code_field not code-like, checking raw_name")
    tokens = raw_name.split()
    print(f"tokens: {tokens}")
    for i in range(1, min(4, len(tokens) + 1)):
        cand = tokens[-i]
        print(f"  i={i}, cand={cand!r}, is_code_like={_is_code_like(cand)}")
        if _is_code_like(cand):
            code = _normalize_code_token(cand).upper()
            display_name = " ".join(tokens[:-i]).strip() or raw_name
            print(f"  -> found code: {code}")
            break
    if not code:
        print(f"no code found, using code_field")
        if code_field:
            code = _normalize_code_token(code_field).upper()
        else:
            code = raw_name

print(f"\ncode after extraction: {code!r}")
print(f"display_name before cleaning: {display_name!r}")

# Clean display name
if display_name:
    display_name = re.sub(r"^\s*[Il](?=[A-Z])", "", display_name)
    print(f"after I/l removal: {display_name!r}")
    display_name = re.sub(r"^[^A-Za-z0-9]+", "", display_name)
    print(f"after leading punct removal: {display_name!r}")
    display_name = re.sub(r"[^A-Za-z0-9\s-]+$", "", display_name).strip()
    print(f"after trailing punct removal: {display_name!r}")

    toks = display_name.split()
    while toks and _is_code_like(toks[-1]):
        toks.pop()
    display_name = " ".join(toks).strip()
    print(f"after code token removal: {display_name!r}")

print(f"\nfinal code: {code!r}")
print(f"final display_name: {display_name!r}")
