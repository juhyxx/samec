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


display_name = "Gloss Black"
print(f"Testing: {display_name!r}")
toks = display_name.split()
print(f"tokens: {toks}")

for tok in toks:
    norm = _normalize_code_token(tok)
    is_code = _is_code_like(tok)
    print(f"  {tok!r} -> normalized to {norm!r}, is_code_like={is_code}")

print("\nRemoving trailing code-like tokens:")
while toks and _is_code_like(toks[-1]):
    removed = toks.pop()
    print(f"  removed: {removed!r}")
display_name = " ".join(toks).strip()
print(f"result: {display_name!r}")
