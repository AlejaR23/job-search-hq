# Setup notes

## 1. Password
Run `python -I tools/hq-dashboard/server.py --set-password` and type a unique password of at least 16 characters.
It is hashed into your app-data folder (outside the project). Never paste it anywhere. If sign-in is locked after
failed attempts, run `python -I tools/hq-dashboard/server.py --unlock` on the same PC.

## 2. Your data
- Copy `examples/applications-tracker.xlsx` to `work/applications-tracker.xlsx` and replace the fictional rows.
- Replace the fictional files in `evidence/` with your own facts. Each file needs the lines
  `- level: verified|stated|unverified`, `- public-safe: yes|no`, `- CV-ready bullets: ...` and optionally `- limit: ...`.
  Only `verified` or `stated`, `public-safe: yes` entries are ever sent to the AI.
- Copy `rules.example.md` to `rules.md` and edit it. `rules.md` and your own `evidence/` files are git-ignored.

## 3. AI worker (optional)
Install the Codex CLI and sign in with ChatGPT. `python tools/hq-dashboard/check_codex_worker.py` runs one fictional
connectivity check (it uses a little of your plan). The worker runs read-only with tools disabled and no API key.

## 4. Phone access
1. Install Tailscale on the PC and phone, sign in, and enable HTTPS and Funnel for your tailnet.
2. Run the server with your public origin: `python -I tools/hq-dashboard/server.py --origin https://<your-machine>.<your-tailnet>.ts.net`
3. `tailscale funnel --bg 8770` points the public address at the local server.
4. Open the address on your phone, sign in, and add it to your home screen.
Wrong Host or Origin values are rejected on purpose; the origin you pass must be exactly the address people type.

## 5. Start at boot (Windows)
`prepare-startup.ps1` writes a Task Scheduler definition that runs `run-server.py` at boot. Review it, import it
yourself, and test a reboot before relying on it. A copy of drafts to a synced folder is optional: set `HQ_COPY_DIR`.

## 6. Check a CV for length
`python -I tools/hq-dashboard/cv_onepage.py my-cv.md my-cv-1page.md my-cv-1page.docx`
