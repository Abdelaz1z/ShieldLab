# Deploying ShieldLab to Hugging Face Spaces (Docker)

The repo now carries everything a container host needs:

| File | Purpose |
|------|---------|
| `Dockerfile` | Builds the app image (Python 3.11, non-root UID 1000, Streamlit headless on :8501) |
| `.streamlit/config.toml` | Streamlit runtime config (headless, no telemetry) |
| `.dockerignore` | Keeps thesis/MC material and dev files out of the image |
| `README.md` (YAML frontmatter) | Tells HF this is a `sdk: docker` Space on `app_port: 8501` |

The same `Dockerfile` also runs unchanged on Render, Fly.io, Cloud Run, or any VPS — so
this is not a Hugging-Face lock-in.

---

## The one thing that needs care: the 33 MB model bundle

`models/surrogate_bundle.joblib` is **33 MB**. Hugging Face **rejects any file over 10 MB
that is not tracked with Git LFS.** On GitHub that file is a normal blob, so you cannot just
add the GitHub remote and push — the push will be refused because the large blob lives in
history. The clean fix below gives the Space its own LFS-from-commit-1 history and leaves
your GitHub repo untouched.

---

## Recommended path — a dedicated Space clone (safest)

Run these locally (needs a free Hugging Face account and `git-lfs` installed —
`git lfs install` once per machine).

```bash
# 1. Create the Space on huggingface.co:
#    New Space -> Owner: <your-hf-user> -> Name: shieldlab -> SDK: Docker -> Blank
#    (or via CLI:)
pip install huggingface_hub
huggingface-cli login                     # paste a WRITE token from hf.co/settings/tokens
huggingface-cli repo create shieldlab --type space --space_sdk docker

# 2. Clone the (empty) Space next to your project:
cd ..
git clone https://huggingface.co/spaces/<your-hf-user>/shieldlab hf-shieldlab
cd hf-shieldlab

# 3. Track large binaries with LFS BEFORE copying them in:
git lfs install
git lfs track "*.joblib"
git add .gitattributes

# 4. Copy the app tree in (everything except git/dev/thesis material).
#    From PowerShell on Windows:
#    robocopy "..\Control Claude Program" . /E /XD .git .venv __pycache__ datasets References .claude .agents /XF *.pyc
#    (or copy by hand: app.py, requirements.txt, Dockerfile, .dockerignore,
#     .streamlit/, README.md, radshield/, ui/, pages/, models/, examples/, tools/)

# 5. Commit and push — the .joblib goes up as an LFS object automatically:
git add .
git commit -m "ShieldLab initial Docker Space deploy"
git push
```

Hugging Face then builds the `Dockerfile` and serves the app at
`https://huggingface.co/spaces/<your-hf-user>/shieldlab`. First build takes a few minutes;
watch the **Logs** tab for the build.

### Updating later
Copy changed files from the GitHub project into `hf-shieldlab/`, then
`git add -A && git commit -m "..." && git push`. Two working copies, but zero history pain.

---

## Alternative — one repo, rewrite history to LFS (advanced)

If you would rather keep a single repo and add HF as a second remote, you must move the
`*.joblib` blobs into LFS across *all* history and force-push to **both** remotes:

```bash
git lfs install
git lfs migrate import --include="*.joblib" --everything
git remote add hf https://huggingface.co/spaces/<your-hf-user>/shieldlab
git push hf main
git push --force origin main       # GitHub history is rewritten — only if you accept that
```

Only do this if you are comfortable rewriting the GitHub history. The dedicated-clone path
above avoids all of it.

---

## Notes
- **RAM / limits:** HF Docker Spaces give far more headroom than Streamlit Community Cloud
  (the free CPU tier is 16 GB RAM, 2 vCPU), so `shap`, `numba`, and future heavier models
  are no longer a build risk. Install `shap` in the image later by adding it back to
  `requirements.txt` once you confirm the build stays green.
- **Sleep:** free Spaces pause after inactivity and wake on the next visit (a few seconds).
  A paid "always-on" upgrade or a Render/Railway host removes that if you need it.
- **Secrets:** none required — ShieldLab has no API keys or login.
- **Custom domain:** available on HF for paid tiers, or front the Space with your own domain
  via a redirect/proxy.
