# Extra firewall domains go stale — refresh before reporting a block

This project allowlisted extra hosts (`$VIBE_EXTRA_DOMAINS`). They were resolved **once, at container start**, and their addresses pinned. Most SaaS APIs sit behind a CDN (Akamai, Cloudflare, Fastly) that moves them to another edge within the hour, so an allowlisted host that worked at session start can stop working later in the same session.

The symptom misleads: DNS still resolves, so the host looks fine, but the packet is rejected. You see connection refused, a connect timeout, `curl` exit 7 or 28, HTTP `000`, or `ECONNREFUSED` — on a host you were told is allowed.

When a request to one of those hosts fails that way, run this once and retry:

```
sudo /usr/local/bin/refresh-extra-domains.sh
```

It re-resolves this project's extra domains and adds their current addresses to the live allowlist. Additive and fast: never flushes the allowlist, never touches the GitHub ranges or iptables, takes no arguments or token. Re-running it when nothing moved is a no-op. If the retry still fails, it is not a stale pin — report the real error.

**Don't** run `sudo /usr/local/bin/init-firewall.sh` instead: it rebuilds everything, flushes a working allowlist, and wants the PAT on stdin that only `postStartCommand` supplies. **Don't** put the refresh on a timer or loop — a session open for weeks would re-resolve for nothing; a failure is the only trigger. **Don't** tell the user the host isn't allowlisted, or reach for `curl --resolve` or an SSH bridge, before the refresh-and-retry.
