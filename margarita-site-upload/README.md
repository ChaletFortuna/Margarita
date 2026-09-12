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

Guests open `guest.html` and sign in with **their booking e-mail address** and **their
reservation number**. The guide is never served in readable form: it is encrypted with
AES-256-GCM, and each guest's e-mail + reservation number derives (PBKDF2, 300 000 iterations)
the key that unwraps the decryption key. A visitor without a valid pair only downloads ciphertext.

### Add a guest

```bash
pip install cryptography                       # once
python3 scripts/build_guide.py --add guest@example.com HMABC12345 "Smith family"
```

Then upload the two files in `guide/` to GitHub (they overwrite the old ones). The guest can
sign in a minute later. To remove a guest, delete their line from `guide-src/guests.csv` and run
`python3 scripts/build_guide.py`. Check a login offline with
`python3 scripts/build_guide.py --check EMAIL RESNO`.

Test login: `oesnou@gmail.com` / `Margarita1`.

### Edit the guide

Edit `guide-src/content.html` (each `<section data-title="…">` is a chapter in the sidebar),
run `python3 scripts/build_guide.py` and upload `guide/`. New photos go in `images/guide/`.

### Important

`guide-src/` holds the readable guide (including access codes and the Wi-Fi password), the
guest list and the content key. Keep a copy somewhere safe outside the repo. If
`guide-src/content.key` is lost, running the script generates a new key and every guest has to
be re-added.
