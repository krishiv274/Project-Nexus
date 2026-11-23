# Drill 2: One backend down (Backend A stopped)

**Fault injected:** Backend A stopped on app01 (Ctrl+C in the `python3 app.py` terminal, port 3001).

## Symptom
The client sees **no error**. Every request returns `200`, but the load balancing has stopped alternating:
```text
HTTP/1.1 200 OK X-Backend: B X-Upstream: 10.211.55.8:3002
HTTP/1.1 200 OK X-Backend: B X-Upstream: 10.211.55.7:3001, 10.211.55.8:3002
HTTP/1.1 200 OK X-Backend: B X-Upstream: 10.211.55.8:3002
...
```
This is the hardest kind of fault to notice: it only shows up in the response headers and the edge logs.

## Commands run and observations (bottom-up)

| Layer | Command | Observation | Conclusion |
|---|---|---|---|
| 0 | 6-request `curl` loop printing `X-Backend` / `X-Upstream` | all `200`, always `X-Backend: B`; one request lists two upstreams `10.211.55.7:3001, 10.211.55.8:3002` | The edge tried A, failed, and retried on B |
| 1–5 | DNS, TCP 443, TLS, HTTP | all healthy (`200` responses through the edge) | The fault is behind the edge |
| 6 | `sudo tail -f /var/log/nginx/cn_error.log` on edge01 | `connect() failed (111: Connection refused) while connecting to upstream … upstream: "http://10.211.55.7:3001/api/status"` then `upstream server temporarily disabled` | Errno 111 = TCP RST: the host is up but nothing listens on 3001 |
| 6 | access log `cn_access.log` | `upstream=10.211.55.7:3001, 10.211.55.8:3002 ustatus=502, 200`, then `upstream=10.211.55.8:3002` only | nginx marked A down for `fail_timeout=10s` and stopped trying it |
| Server | `sudo ss -lntp` on app01 | *(not captured)* expected: no listener on `:3001` | Root cause: the Backend A process is not running |

## Layer identified
**Application / behind the edge** (backend process down). The edge's passive health check hid it from the client.

## Fix
On app01: `python3 app.py`. After about 10 s (`fail_timeout`) the loop shows A and B alternating again.

## Lesson
`Connection refused` (RST) is detected instantly. A dead host that sends nothing back can only be detected by
a timeout, which is why `proxy_connect_timeout` was lowered to 2 s. The `X-Upstream` header and the
`cn_upstream` log format are what make this fault visible.

**Evidence:** `images/p2_fig12_ha_backend_a_down.png`, `images/p2_fig13_nginx_error_log.png`,
`images/p2_fig14_ha_recovery.png`, `vm_logs/edge01/cn_error.log`, `vm_logs/edge01/cn_access.log` (lines from 01:59:17).
