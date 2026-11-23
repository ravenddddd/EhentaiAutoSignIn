# E-Hentai Check-in

A small self-hosted service that visits the E-Hentai news page on a schedule,
keeps the account cookie fresh, reads the account balances, and shows everything
in a local Web UI.

This is a fork of [AkiyaKiko/EhentaiAutoSignIn](https://github.com/AkiyaKiko/EhentaiAutoSignIn).
See [UPSTREAM.md](UPSTREAM.md) for the list of changes.

## What it does

- Requests `https://e-hentai.org/news.php` with your cookie and reports one of:
  already signed in, reward received, or a Random Encounter.
- Merges the six Cookie fields the site rotates (`ipb_member_id`,
  `ipb_pass_hash`, `sk`, `hath_perks`, `nw`, `event`) and writes them back to
  `.env` when they change.
- Reads GP, Credits and Hath from the exchange and perk pages; the 2025 front
  site no longer shows a wallet bar, so each value is taken from the first page
  that reports it.
- Serves a single-user Web UI with the balances, the cookie editor and the
  check-in history.
- Appends every run to `/data/runs.jsonl` (one JSON object per line).

It does not download galleries, does not handle Random Encounter, and does not
log in for you: you paste an existing browser cookie.

## Run with Docker

```yaml
services:
  ehentai-signin:
    image: ghcr.io/ravenddddd/ehentaiautosignin:latest
    restart: unless-stopped
    user: "1000:1000"          # match the owner of ./data
    environment:
      TZ: Asia/Shanghai
      E_PROXY: http://clash:7890
      WEB_PORT: "18391"
      WEB_PASSWORD: "a long random password"
    volumes:
      - ./data:/data
    ports:
      - "192.168.1.10:18391:18391"
    read_only: true
    tmpfs:
      - /tmp
    cap_drop: [ALL]
    security_opt:
      - no-new-privileges:true
    logging:
      driver: json-file
      options:
        max-size: "5m"
        max-file: "3"
```

Open `http://<host>:18391`, sign in with `WEB_PASSWORD`, and paste the cookie on
the first visit. The container writes `/data/.env` and `/data/runs.jsonl`.

`read_only` works because only `/data` is writable and Python bytecode caching is
disabled in the image. `/tmp` is a tmpfs because the root filesystem is read-only.

## Configuration

`.env` lives in `/data` and its values override the container environment.

| Key | Default | Meaning |
| --- | --- | --- |
| `E_COOKIE` | — | Account cookie; written by the Web UI. |
| `E_PROXY` | empty | Proxy for check-in and balance requests. |
| `E_USER_AGENT` | Chrome | Override the User-Agent. |
| `E_SCHEDULE` | `00:30,06:30,12:30,18:30` | Local run times, ascending. |
| `WEB_PASSWORD` | — | Required; the Web UI refuses to start without it. |
| `WEB_PORT` | `18391` | Port inside the container. |
| `LOG_ENABLED` | `false` | Write `LOG_DIR/ehentai.log`. |
| `LOG_DIR` | `logs` | Relative to `/data`. |
| `LOG_MAX_MB` | `5` | Rotate size. |
| `LOG_RETENTION_DAYS` | `30` | Delete older rotated files. |

The cookie can also be pasted after the service has started; no restart is
needed. Changing `E_SCHEDULE`, `WEB_PORT` or the logging settings needs a restart.

## Web UI

- **Balances**: GP, Credits and Hath, with the page each value came from.
- **Cookie**: masked value, expiry dates reported by the site, and a paste box.
- **History**: the last 30 runs with trigger, result, GP, Credits and message.
- **Check in now**: starts one run in the background; the page polls until it
  finishes. Manual runs are rate limited to one every 30 seconds.

If a balance cannot be parsed, the page shows a **Balance debug** panel with the
text it found on the account pages and no secret values.

## Security notes

- The Web UI can read and replace your E-Hentai cookie. Bind the published port
  to a LAN address, keep `WEB_PASSWORD` long, and never expose the page to the
  internet.
- The password is stored in plain text in the compose file and in `.env`; keep
  both out of any public repository.
- Sessions are HMAC-signed cookies derived from `WEB_PASSWORD`; changing the
  password invalidates every session.
- `/data` must be a local volume, not an SMB or NFS share: the cookie and the
  history file are written with atomic replacement.

## Local development

```bash
python -m venv .venv
.venv/bin/pip install ".[test]"
.venv/bin/python -m pytest -q
.venv/bin/python main.py --once      # one check-in, no Web UI
EHENTAI_DATA_DIR=/tmp/eh WEB_PASSWORD=secret .venv/bin/python main.py
```

`--once` exits with status 1 when no cookie is configured or the check-in fails.

## License

MIT, same as upstream. See [LICENSE](LICENSE).
