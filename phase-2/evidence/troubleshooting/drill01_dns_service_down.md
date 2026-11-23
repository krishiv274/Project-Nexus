# Drill 1: DNS service down (both resolvers)

**Fault injected:** `sudo systemctl stop dnsmasq` on dns01 (10.211.55.5) **and** on app01/dns02 (10.211.55.7).

## Symptom
On the client app02, after `sudo resolvectl flush-caches`:
```text
$ curl -sS -o /dev/null -w '%{http_code}\n' https://app.cn.test/api/status
curl: (6) Could not resolve host: app.cn.test
000
```
HTTP code `000` means no HTTP exchange happened at all. curl error `(6)` points at name resolution.

## Commands run and observations (bottom-up)

| Layer | Command | Observation | Conclusion |
|---|---|---|---|
| 0 | `curl … https://app.cn.test/api/status` | `Could not resolve host`, code `000` | Suspect DNS: no TCP connection was even attempted |
| 1 | `dig @10.211.55.5 app.cn.test` | `communications error to 10.211.55.5#53: connection refused` (seen earlier in fig05 when only the primary was down) | dnsmasq is not listening on the primary |
| 1 | `dig @10.211.55.7 app.cn.test` | *(not captured)* expected: `connection refused` as for the primary | Both resolvers are down, so failover to the backup cannot help |
| 2 | `ping -c 2 10.211.55.6` | 2/2 replies, ~1–2 ms | The edge host and the network are fine. Only name resolution fails |
| Server | `sudo journalctl -u dnsmasq` on dns01 and app01 | `exiting on receipt of SIGTERM` / `Stopped dnsmasq.service` (visible in fig05 and `vm_logs/*/dnsmasq-journal.txt`) | Root cause: the DNS **service** is stopped on both servers |

On the wire (`wireshark/phase2_dns_failover.pcapng`, filter `dns || icmp`), a query to a stopped dnsmasq is answered
by **ICMP Destination unreachable (Port unreachable)**: the host is up but nothing listens on UDP/53.

## Layer identified
**DNS (service failure).** IP, TCP, TLS and the application were never reached.

## Fix
`sudo systemctl start dnsmasq` on dns01 and on app01, then on app02 `sudo resolvectl flush-caches` and
`dig +short app.cn.test` → `10.211.55.6`; `curl` returns `200` again.

## Lesson
A DNS failure looks like "the site is down", but `ping` to the edge IP proves the service itself is healthy.
With only one of the two resolvers down (Extension A) the client silently fails over to the other one.

**Evidence:** `images/p2_fig06_dns_failure.png`, `images/p2_fig05_dns_failover.png`,
`wireshark/phase2_dns_failover.pcapng`, `vm_logs/dns01/dnsmasq-journal.txt`, `vm_logs/app01/dnsmasq-journal.txt`.
