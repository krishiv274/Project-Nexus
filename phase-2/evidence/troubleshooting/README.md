# Extension F: Troubleshooting Method and Drills

During the evaluation the faculty injects one fault. We diagnose it **bottom-up, one layer at a time**, saying each
conclusion out loud, and change only one thing at a time.

## Method (run from the client, app02)

| Layer | Question | Command | Healthy result | Failure signatures |
|---|---|---|---|---|
| 0. Reproduce | What is the exact error? | `curl -v https://app.cn.test/api/status` | `200` | the curl error number points at a layer: `(6)` DNS, `(7)`/`(28)` TCP, `(35)`/`(60)` TLS, `502`/`504` behind the edge |
| 1. DNS | Does the name resolve to the edge, and do both servers agree? | `resolvectl status enp0s5`, `dig app.cn.test`, `dig @10.211.55.5 app.cn.test; dig @10.211.55.7 app.cn.test` | `NOERROR`, `10.211.55.6` from both | `connection refused` / `no servers could be reached` (service down); wrong IP (bad record); `NXDOMAIN` (missing record) |
| 2. IP | Is the edge host reachable? | `ping -c 3 10.211.55.6` | replies | 100 % loss: host down or network problem |
| 3. TCP | Is something listening on 443? | `nc -vz -w 3 10.211.55.6 443` | `succeeded` | `refused`: host up, nothing listening; `timed out`: firewall DROP or host down |
| 4. TLS | Is the certificate valid and trusted for this name? | `openssl s_client -connect 10.211.55.6:443 -servername app.cn.test -verify_hostname app.cn.test` | `Verify return code: 0 (ok)` | untrusted issuer, name mismatch, expired / clock wrong |
| 5. HTTP | Does the application answer? | `curl -sS -D - -o /dev/null https://app.cn.test/api/status` | `200`, `X-Backend` A/B alternating | `502`/`504`: the edge works, the backends don't |
| 6. Behind the edge (on edge01) | Can the edge reach each backend? | `nc -vz -w 3 10.211.55.7 3001; nc -vz -w 3 10.211.55.8 3002`, `sudo tail cn_error.log`, `sudo nginx -t` | both `succeeded` | `connect() failed (111)` = backend down; `(110) timed out` = firewall / dead host |

Server-side checks on the suspected VM: `systemctl status dnsmasq|nginx`, `sudo ss -lntup`, `sudo iptables -L INPUT -n -v`.

## Drill write-ups

Each drill is a fault that was actually produced during the Phase 2 work, so the observations below are taken from
the captured screenshots and logs in this evidence folder (`images/`, `vm_logs/`, `wireshark/`).

| # | File | Fault | Layer found |
|---|---|---|---|
| 1 | [drill01_dns_service_down.md](drill01_dns_service_down.md) | dnsmasq stopped on both DNS servers | DNS (service) |
| 2 | [drill02_one_backend_down.md](drill02_one_backend_down.md) | Backend A process stopped | Behind the edge (upstream) |
| 3 | [drill03_both_backends_down.md](drill03_both_backends_down.md) | Both backends stopped | Application |

Other faults practised from the guide's drill list (not written up): wrong DNS record, wrong client resolver,
nginx stopped, firewall DROP on 443, wrong listen port, wrong certificate file, CA removed from the trust store,
`api.cn.test` SAN mismatch, wrong upstream port, backend bound to 127.0.0.1, wrong firewall allow-list, wrong clock.

## Golden rules

1. Bottom-up: DNS, IP, TCP, TLS, HTTP, then behind the edge. Never start by restarting services.
2. Change one thing at a time and re-test.
3. Say each conclusion out loud: *"DNS returns .6 and TCP 443 connects, so it is not DNS or transport…"*
4. Backups are in `/root/phase1-backup/` on every VM.
