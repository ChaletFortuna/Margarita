# Villa Margarita — Website

Trilingual (EN/FR/DE) website for Villa Margarita, Beaulieu-sur-Mer, with a reservation
calendar synced from Airbnb & VRBO and a private guest area (welcome guide behind a login).

Live at https://chaletfortuna.github.io/Margarita/ once GitHub Pages is enabled.

## Files

- `index.html` — the whole public site (design, 3 languages, gallery, calendar)
- `guest.html` — the guest area: login + the welcome guide
- `images/` — optimised photos of the villa; `images/guide/` — photos used in the welcome guide
- `guide/` — the **encrypted** welcome guide and guest logins (generated, safe to publish)
- `guide-src/` — the readable guide, the guest list and the key (**git-ignored — never upload**)
- `availability.json` — booked dates shown in the calendar (rewritten daily by the workflow)
- `scripts/sync_ical.py` — fetches the Airbnb and VRBO iCal feeds and rewrites `availability.json`
- `scripts/build_guide.py` — encrypts the welcome guide and the guest logins
- `.github/workflows/sync-calendar.yml` — runs the calendar script daily and commits the result

## Publish on GitHub Pages

1. Create the public repo `ChaletFortuna/Margarita` and upload the contents of this folder
   (not the folder itself). Dotfiles do not survive drag-and-drop: create `.gitignore` and
   `.github/workflows/sync-calendar.yml` with *Add file → Create new file*, pasting their content.
2. **Settings → Pages → Source: Deploy from a branch → main → / (root)** → Save.
3. **Actions → "Sync reservation calendar" → Run workflow** once. It then runs every day at
   05:00 UTC and updates `availability.json`.

## Guest area

Guests open `guest.html` and sign in with **their family name** and **their reservation
number** (case, accents, spaces and hyphens in the name are ignored). The guide is encrypted
(AES-256-GCM); each guest's name + reservation number derives (PBKDF2, 300 000 iterations)
the key that unwraps the decryption key, so visitors without a valid pair only get ciphertext.

### Who can log in: the access file on Google Drive

**MARGARITA GUEST ACCESS.csv**, "Margarita website" folder of the chalet.fortuna.zermatt@gmail.com
Drive (never in this repo):

```
login,password,access_from,access_until,arrival,departure,guest,platform,bookings_row,status
smith,HMABC12345,2026-11-02,2026-12-10,2026-12-02,2026-12-09,John Smith,Airbnb,,scheduled
```

Only guests whose `access_from`–`access_until` window includes today (Beaulieu date) are
written to `guide/guests.json`; a `status` containing "cancel" is always left out. The Claude
scheduled task "Margarita guest access – daily" reads the Drive file every night, rebuilds
`guide/guests.json` and pushes it when the open logins changed.

Rebuild by hand (content key: "MARGARITA GUIDE KEY - PRIVATE.txt" in the same Drive folder):

```bash
pip install cryptography
python3 scripts/build_guide.py --guests "MARGARITA GUEST ACCESS.csv" --key content.key
python3 scripts/build_guide.py --check "Smith" HMABC12345
git add guide/guests.json && git commit -m "Update guest access" && git push
```

To edit the guide: change `guide-src/content.html`, then add `--content` to the build command.
`guide-src/` is git-ignored — never commit it, the access file or the key.

Test login (in the access file): `esnou` / `MARGARITA1`.

### Edit the guide

Edit `guide-src/content.html` (each `<section data-title="…">` is a chapter in the sidebar),
run `python3 scripts/build_guide.py` and upload `guide/`. New photos go in `images/guide/`.

### Important

`guide-src/` holds the readable guide (including access codes and the Wi-Fi password), the
guest list and the content key. Keep a copy somewhere safe outside the repo. If
`guide-src/content.key` is lost, running the script generates a new key and every guest has to
be re-added.
