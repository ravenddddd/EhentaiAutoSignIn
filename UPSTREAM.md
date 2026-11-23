# Fork notes

Base: `AkiyaKiko/EhentaiAutoSignIn` at `eee89e6` (2026-11-03).

This fork is not meant to be merged back. Upstream fixes to the check-in logic
are cherry-picked by hand when they matter; everything else is allowed to drift.

## Removed

| Path | Why |
| --- | --- |
| `notify.py` | 23 push channels, unused here; it also pulled in a `node -e` call for the Qinglong panel. |
| `autosignin.py` | Qinglong compatibility script, unmaintained upstream. |
| `README.qinglong.md`, `README.en.md` | Folded into `README.md`. |
| `uv.lock` | Stale after the dependency and module changes; regenerate with `uv lock` if uv is adopted again. |
| `.github/scripts/` | Only used by the PyInstaller binary release, which this fork no longer builds. |
| Binary release workflow | Replaced by a container-only workflow. |

## Added

| Path | Purpose |
| --- | --- |
| `ehentai/web.py`, `ehentai/static/` | Single-user Web UI: balances, cookie editor, history, manual run. |
| `ehentai/store.py` | Append-only history in `/data/runs.jsonl`. |
| `ehentai/balance.py` | GP / Credits / Hath parsing from the exchange and perk pages. |
| `ehentai/runner.py` | One run = check-in + balances + history record, serialised by a lock. |
| `Dockerfile`, `.dockerignore` | Container image, non-root, `/data` as the only writable path. |
| `tests/test_web.py`, `test_store.py`, `test_balance.py`, `test_runner.py`, `test_config.py`, `test_main.py` | Coverage for the new modules. |

## Behaviour changes

- All code, comments, log messages and UI text are English.
- Without a cookie the service still starts and the Web UI shows "Not
  configured"; upstream exited with an error. `--once` keeps the strict
  behaviour and exits 1.
- Check-in results are stored instead of pushed to notification channels.
- The cookie is still persisted to `.env` with the upstream atomic rewrite.

## Keeping up with upstream

```bash
git remote add upstream https://github.com/AkiyaKiko/EhentaiAutoSignIn.git
git fetch upstream
git diff HEAD upstream/main -- ehentai/signin.py ehentai/log_setup.py
```

Apply by hand only what touches the request/parse logic. Do not merge.
