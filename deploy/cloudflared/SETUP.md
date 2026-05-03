# Publishing chip-leader at https://chip.ogrady.football

End state: `https://chip.ogrady.football` reaches the Mac mini's local
chip-leader server through a Cloudflare Tunnel, gated by Cloudflare Access
(email magic link). No port forwarding, no static IP, no Let's Encrypt
plumbing. Bluehost stays the registrar; Cloudflare manages DNS for the zone.

Total time ~30 min, mostly waiting on DNS propagation.

---

## 1. Cloudflare account + add the zone

1. Sign up at https://dash.cloudflare.com (free plan).
2. **Add a Site** → enter `ogrady.football` → choose Free.
3. CF scans Bluehost DNS and imports the existing records. Sanity-check the
   import — especially MX records if any Bluehost mailboxes are in use, and
   any A records for the root domain or `www`.
4. CF shows two assigned nameservers, e.g. `arnold.ns.cloudflare.com` and
   `kim.ns.cloudflare.com`. Copy them.

## 2. Bluehost: swap nameservers

1. https://my.bluehost.com → Domains → `ogrady.football`.
2. Nameservers → Custom → paste the two CF nameservers.
3. Save. Propagation is usually < 1 hour, occasionally 24.
4. Verify: `dig +short NS ogrady.football` → returns the CF nameservers.
5. Cloudflare dashboard → the zone flips to **Active** automatically.

> Existing Bluehost web/email keeps working as long as the imported A/MX
> records are intact. The registrar stays Bluehost; only DNS moves to CF.

## 3. Mac mini: install cloudflared & create the tunnel

```zsh
brew install cloudflared
cloudflared tunnel login                            # opens browser → pick the zone
cloudflared tunnel create chipleader                # prints a TUNNEL-ID UUID
cloudflared tunnel route dns chipleader chip.ogrady.football
```

The `route dns` command writes the proxied CNAME (`chip → <id>.cfargotunnel.com`,
orange cloud on) automatically.

## 4. Tunnel config

Copy the template into place:

```zsh
mkdir -p ~/.cloudflared
cp ~/chip-leader/deploy/cloudflared/config.yml.template ~/.cloudflared/config.yml
# edit: replace <TUNNEL-ID> with the UUID from `tunnel create`
```

Final `~/.cloudflared/config.yml`:

```yaml
tunnel: chipleader
credentials-file: /Users/tensor/.cloudflared/<TUNNEL-ID>.json
ingress:
  - hostname: chip.ogrady.football
    service: http://localhost:8765
  - service: http_status:404
```

Smoke test in the foreground:

```zsh
cloudflared tunnel run chipleader
# in another shell:
curl -I https://chip.ogrady.football/             # should reach the Python server (200, or 302 to CF Access once configured)
```

## 5. Run as a service

```zsh
sudo cloudflared service install
# starts immediately and at boot via launchd
sudo launchctl list | grep cloudflared            # verify
tail -f ~/Library/Logs/com.cloudflare.cloudflared.out.log
```

## 6. Cloudflare Access (auth gate, free ≤ 50 users)

Without this, `chip.ogrady.football` would be wide-open to the internet.

1. Cloudflare dashboard → **Zero Trust** → **Access** → **Applications** →
   **Add an application** → **Self-hosted**.
2. Application name: `Chip Leader`.
3. Session duration: 1 month (long, since it's a phone bookmark).
4. Application domain: `chip.ogrady.football`.
5. Identity providers: enable **One-time PIN** (no setup; emails a code) and
   optionally **Google** if you want SSO instead.
6. Add a policy:
   - Name: `Allow Jason + pool members`
   - Action: **Allow**
   - Include → **Emails** → list `jason@ogrady.ai` and any pool members.
7. Save.

## 7. Verify end-to-end

```zsh
curl -sI https://chip.ogrady.football/                # → 302 to CF Access login
# from phone: open the URL, complete email PIN → leaderboard loads
```

On iPhone: open in Safari → Share → **Add to Home Screen**. The PWA icon
(beaver/trophy, wired in v1.1.1) appears as a real app launcher.

---

## Operational notes

- **Mac mini sleep.** `sudo pmset -a sleep 0 disksleep 0 displaysleep 30`.
- **DG quota under public access.** Auto-pause (overnight 7pm–7am +
  tab-hidden) keeps polls low. If Sunday traffic ever spikes, add a
  server-side `/data` cache (30s TTL keyed on `meta.last_update`).
- **iCloud symlink lag.** On tournament Sunday, force-sync if needed:
  `brctl download standings/standings_latest.json picks_history.json`.
- **Logs.**
  - chip-leader: `~/Library/Logs/chip-leader.log`
  - cloudflared: `~/Library/Logs/com.cloudflare.cloudflared.out.log`
- **Rotate access.** Revoke a user: Zero Trust → Access → Applications →
  Chip Leader → policy → remove email.
- **Tunnel teardown.** `sudo cloudflared service uninstall` then
  `cloudflared tunnel delete chipleader`.

## Why Cloudflare Tunnel over alternatives

- **Tailscale Funnel + custom domain.** Funnel only serves on `*.ts.net`
  (TLS SNI is fixed). Custom domain isn't supported as the served hostname.
- **Bluehost A record + port-forward + Let's Encrypt.** Requires static IP
  or dynamic DNS, opening port 443 on the home router, and Caddy with
  Let's Encrypt. Three moving parts vs zero with Cloudflare Tunnel.
- **Cloudflared also handles auth (CF Access).** No basicauth-in-Caddy
  needed; SSO/email PIN out of the box, free for ≤50 users.
