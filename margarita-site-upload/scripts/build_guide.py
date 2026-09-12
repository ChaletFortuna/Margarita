#!/usr/bin/env python3
"""
Build the password-protected guest area of the Villa Margarita website.

Reads (private, git-ignored):
  guide-src/content.html   the guest guide (HTML sections)
  guide-src/guests.csv     one guest per line:  email,reservation_number[,name]

Writes (public, committed):
  guide/content.enc.json   the guide, AES-256-GCM encrypted with a random content key
  guide/guests.json        the content key wrapped once per guest, with a key derived
                           from  email + reservation number  (PBKDF2-HMAC-SHA256)

Nothing readable is published: without a valid email + reservation number the
browser cannot decrypt the guide.  Run again whenever content.html or guests.csv
changes, then commit guide/*.json.

Usage:
  python3 scripts/build_guide.py                       # rebuild everything
  python3 scripts/build_guide.py --add EMAIL RESNO [NAME]   # add a guest and rebuild
  python3 scripts/build_guide.py --check EMAIL RESNO   # verify a login offline
"""
import base64, csv, hashlib, json, os, secrets, sys
from pathlib import Path

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
except ImportError:
    sys.exit("Missing dependency: pip install cryptography")

ROOT = Path(__file__).resolve().parent.parent
SRC_HTML = ROOT / "guide-src" / "content.html"
SRC_GUESTS = ROOT / "guide-src" / "guests.csv"
OUT_DIR = ROOT / "guide"
OUT_CONTENT = OUT_DIR / "content.enc.json"
OUT_GUESTS = OUT_DIR / "guests.json"
KEY_FILE = ROOT / "guide-src" / "content.key"   # keeps the content key stable between builds

PBKDF2_ITER = 300_000


def b64(b: bytes) -> str:
    return base64.b64encode(b).decode()


def normalise(email: str, resno: str) -> bytes:
    """Same normalisation as guest.html: e-mail lower-case, reservation upper-case."""
    return f"{email.strip().lower()}\n{resno.strip().upper()}".encode()


def lookup_id(email: str, resno: str) -> str:
    return hashlib.sha256(b"margarita-guest:" + normalise(email, resno)).hexdigest()


def derive(email: str, resno: str, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", normalise(email, resno), salt, PBKDF2_ITER, 32)


def load_content_key() -> bytes:
    if KEY_FILE.exists():
        return base64.b64decode(KEY_FILE.read_text().strip())
    key = secrets.token_bytes(32)
    KEY_FILE.write_text(b64(key))
    return key


def read_guests():
    guests = []
    if SRC_GUESTS.exists():
        with SRC_GUESTS.open(newline="", encoding="utf-8") as f:
            for row in csv.reader(f):
                if not row or row[0].strip().startswith("#"):
                    continue
                email, resno = row[0], row[1]
                name = row[2].strip() if len(row) > 2 else ""
                guests.append((email.strip(), resno.strip(), name))
    return guests


def build():
    OUT_DIR.mkdir(exist_ok=True)
    key = load_content_key()
    aes = AESGCM(key)

    # 1. encrypt the guide
    html = SRC_HTML.read_text(encoding="utf-8")
    iv = secrets.token_bytes(12)
    OUT_CONTENT.write_text(json.dumps({
        "v": 1, "alg": "AES-256-GCM",
        "iv": b64(iv), "ct": b64(aes.encrypt(iv, html.encode("utf-8"), None)),
    }))

    # 2. wrap the content key once per guest
    entries = {}
    for email, resno, name in read_guests():
        salt = secrets.token_bytes(16)
        wrap_iv = secrets.token_bytes(12)
        payload = json.dumps({"k": b64(key), "name": name}).encode()
        wrapped = AESGCM(derive(email, resno, salt)).encrypt(wrap_iv, payload, None)
        entries[lookup_id(email, resno)] = {"s": b64(salt), "iv": b64(wrap_iv), "w": b64(wrapped)}
    OUT_GUESTS.write_text(json.dumps({"v": 1, "iter": PBKDF2_ITER, "guests": entries}, indent=1))
    print(f"Encrypted guide: {OUT_CONTENT.relative_to(ROOT)} ({OUT_CONTENT.stat().st_size // 1024} KB)")
    print(f"Guest logins:    {OUT_GUESTS.relative_to(ROOT)} ({len(entries)} guest(s))")


def add_guest(email, resno, name=""):
    existing = read_guests()
    if any(e.lower() == email.lower() and r.upper() == resno.upper() for e, r, _ in existing):
        print("Guest already present.")
    else:
        with SRC_GUESTS.open("a", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow([email, resno, name])
        print(f"Added {email} / {resno}")
    build()


def check(email, resno):
    data = json.loads(OUT_GUESTS.read_text())
    e = data["guests"].get(lookup_id(email, resno))
    if not e:
        print("NOT FOUND"); return
    key = AESGCM(derive(email, resno, base64.b64decode(e["s"]))).decrypt(
        base64.b64decode(e["iv"]), base64.b64decode(e["w"]), None)
    print("OK, unwrapped:", json.loads(key).get("name") or "(no name)")


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:1] == ["--add"] and len(a) >= 3:
        add_guest(a[1], a[2], a[3] if len(a) > 3 else "")
    elif a[:1] == ["--check"] and len(a) == 3:
        check(a[1], a[2])
    else:
        build()
