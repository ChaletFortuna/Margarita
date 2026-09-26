#!/usr/bin/env python3
"""
Build the password-protected guest area of the Villa Margarita website.

Guests sign in with their FAMILY NAME (login) and RESERVATION NUMBER (password).

Private inputs (never committed):
  guide-src/content.html   the readable guest guide (only needed to re-encrypt the guide)
  guide-src/content.key    the content key (base64), kept stable between builds
  MARGARITA GUEST ACCESS.csv the access list kept on Google Drive ("Margarita website" folder):
        login,password,access_from,access_until,arrival,departure,guest,platform,bookings_row,status
        login = family name, password = reservation number,
        access_from / access_until = YYYY-MM-DD (inclusive, Beaulieu local date)

Public outputs (committed):
  guide/content.enc.json   the guide, AES-256-GCM encrypted with the content key
  guide/guests.json        the content key wrapped once per guest whose access window
                           is open today, under a key derived (PBKDF2-HMAC-SHA256)
                           from family name + reservation number

A guest outside their window (or with status "cancelled") is simply not in guests.json,
so the site refuses the login. Rebuild daily to open and close windows.

Usage:
  python3 scripts/build_guide.py --guests ACCESS.csv                 # rebuild guests.json only
  python3 scripts/build_guide.py --guests ACCESS.csv --content      # also re-encrypt content.html
  python3 scripts/build_guide.py --check "Family name" RESNO         # verify a login offline
Options:
  --key FILE     content key file (default guide-src/content.key)
  --today DATE   pretend today is DATE (YYYY-MM-DD), for testing
"""
import argparse, base64, csv, datetime, hashlib, json, re, secrets, sys, unicodedata
from pathlib import Path

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
except ImportError:
    sys.exit("Missing dependency: pip install cryptography")

ROOT = Path(__file__).resolve().parent.parent
SRC_HTML = ROOT / "guide-src" / "content.html"
DEFAULT_KEY = ROOT / "guide-src" / "content.key"
OUT_DIR = ROOT / "guide"
OUT_CONTENT = OUT_DIR / "content.enc.json"
OUT_GUESTS = OUT_DIR / "guests.json"

PBKDF2_ITER = 300_000
VERSION = 2


def b64(b: bytes) -> str:
    return base64.b64encode(b).decode()


def norm_name(s: str) -> str:
    """Same as guest.html: accents dropped, lower-case, letters and digits only.
    'Pierer-von Esch', 'pierer von esch' and 'PIERERVONESCH' all match."""
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]", "", s.lower())


def norm_resno(s: str) -> str:
    return re.sub(r"\s", "", s).upper()


def secret(name: str, resno: str) -> bytes:
    return f"{norm_name(name)}\n{norm_resno(resno)}".encode()


def lookup_id(name: str, resno: str) -> str:
    return hashlib.sha256(b"margarita-guest-v2:" + secret(name, resno)).hexdigest()


def derive(name: str, resno: str, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", secret(name, resno), salt, PBKDF2_ITER, 32)


def local_today() -> datetime.date:
    try:
        from zoneinfo import ZoneInfo
        return datetime.datetime.now(ZoneInfo("Europe/Paris")).date()
    except Exception:
        return datetime.date.today()


def load_key(path: Path) -> bytes:
    if path.exists():
        return base64.b64decode(path.read_text().strip())
    sys.exit(f"Content key not found: {path}  (the key is on Google Drive, 'Margarita website' folder)")


def read_access(path: Path, today: datetime.date):
    """Return (open_guests, report_lines)."""
    open_guests, report = [], []
    with path.open(newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            row = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
            login, pw = row.get("login", ""), row.get("password", "")
            if not login or not pw:
                continue
            status = row.get("status", "").lower()
            try:
                start = datetime.date.fromisoformat(row.get("access_from", ""))
                end = datetime.date.fromisoformat(row.get("access_until", ""))
            except ValueError:
                report.append(f"  skipped   {login}: bad access dates"); continue
            if "cancel" in status:
                state = "cancelled"
            elif today < start:
                state = f"opens {start}"
            elif today > end:
                state = "expired"
            else:
                state = "OPEN"
                open_guests.append((login, pw, row.get("guest", "") or login))
            report.append(f"  {state:<16} {login}")
    return open_guests, report


def fingerprint(guests) -> str:
    """Stable digest of who is open (changes when a login opens, closes or is renamed)."""
    lines = sorted(f"{lookup_id(n, r)}|{d}" for n, r, d in guests)
    return hashlib.sha256("\n".join(lines).encode()).hexdigest()


def write_guests(key: bytes, guests) -> bool:
    """Rewrite guests.json only when the set of open logins changed. Returns True if written."""
    fp = fingerprint(guests)
    try:
        if json.loads(OUT_GUESTS.read_text()).get("fp") == fp:
            return False
    except (OSError, ValueError):
        pass
    entries = {}
    for name, resno, display in guests:
        salt, iv = secrets.token_bytes(16), secrets.token_bytes(12)
        payload = json.dumps({"k": b64(key), "name": display}).encode()
        entries[lookup_id(name, resno)] = {
            "s": b64(salt), "iv": b64(iv),
            "w": b64(AESGCM(derive(name, resno, salt)).encrypt(iv, payload, None))}
    OUT_DIR.mkdir(exist_ok=True)
    OUT_GUESTS.write_text(json.dumps({"v": VERSION, "iter": PBKDF2_ITER, "fp": fp, "guests": entries}, indent=1))
    return True


def write_content(key: bytes):
    html = SRC_HTML.read_text(encoding="utf-8")
    iv = secrets.token_bytes(12)
    OUT_CONTENT.write_text(json.dumps({"v": 1, "alg": "AES-256-GCM", "iv": b64(iv),
                                       "ct": b64(AESGCM(key).encrypt(iv, html.encode(), None))}))


def check(name, resno):
    data = json.loads(OUT_GUESTS.read_text())
    e = data["guests"].get(lookup_id(name, resno))
    if not e:
        print("NOT FOUND (wrong login, or access window closed)"); return False
    p = AESGCM(derive(name, resno, base64.b64decode(e["s"]))).decrypt(
        base64.b64decode(e["iv"]), base64.b64decode(e["w"]), None)
    print("OK:", json.loads(p).get("name")); return True


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--guests", type=Path)
    ap.add_argument("--content", action="store_true")
    ap.add_argument("--key", type=Path, default=DEFAULT_KEY)
    ap.add_argument("--today")
    ap.add_argument("--check", nargs=2, metavar=("NAME", "RESNO"))
    a = ap.parse_args()
    if a.check:
        sys.exit(0 if check(*a.check) else 1)
    if not a.guests:
        ap.error("--guests ACCESS.csv is required")
    key = load_key(a.key)
    today = datetime.date.fromisoformat(a.today) if a.today else local_today()
    guests, report = read_access(a.guests, today)
    changed = write_guests(key, guests)
    if a.content:
        write_content(key)
        print("Re-encrypted guide/content.enc.json")
    print(f"Access list for {today}:")
    print("\n".join(report))
    print(f"guide/guests.json: {len(guests)} open login(s) — {'UPDATED' if changed else 'no change'}")
