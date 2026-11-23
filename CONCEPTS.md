# Course Concepts: How Project Nexus Maps to the Course Topics

This document covers the topic mapping in section 6.1 of the project document: where each protocol sits, what
each machine represents in the cloud, and the "explanation only" topics. Packet numbers refer to the Phase 1
captures in `phase-1/evidence/wireshark/`, so every claim can be shown in Wireshark.

Deployed network: `10.211.55.0/24`. dns01 `.5`, edge01 `.6`, app01 `.7`, app02 `.8`, gateway `.1`.

---

## 1. Moving data through the core: one request, end to end

A client (app02, `10.211.55.8`) runs `curl https://app.cn.test/api/status`:

1. **DNS.** The stub resolver asks dns01 `A? app.cn.test` over UDP/53 and gets `10.211.55.6` (edge01).
2. **ARP / link.** app02 finds edge01's MAC on the LAN (same subnet, so no router is involved).
3. **TCP.** A three-way handshake to edge01:443.
4. **TLS.** ClientHello with SNI `app.cn.test`; edge01 proves its identity with a certificate signed by the project CA.
5. **HTTP.** `GET /api/status` travels encrypted inside TLS.
6. **Reverse proxy.** nginx decrypts it, picks a backend round-robin and opens a *new* plain-HTTP TCP connection to
   app01:3001 or app02:3002.
7. **Response.** It flows back the same way: backend → nginx → TLS → client, with `X-Backend: A|B`.

Captured in `phase1_https_tcp_tls.pcapng` (client side) and `phase1_nginx_backend_lb.pcapng` (edge side, frames
5–10 client↔edge, then frames 15/17 edge → app01:3001 and frames 40/41 edge → app02:3002).

---

## 2. OSI vs TCP/IP: where each protocol sits

| Protocol in this project | OSI layer | TCP/IP layer | Where we see it |
|---|---|---|---|
| HTTP/1.1 (`GET /api/status`, `X-Backend`, `Cache-Control`) | 7 Application | Application | curl `-v`, Postman, `phase1_http_headers.pcapng` |
| DNS (`A? app.cn.test`) | 7 Application | Application | `dig`, `phase1_dns_query.pcapng` |
| TLS 1.2 / 1.3 | 6 Presentation / 5 Session (encryption, session setup) | between Application and Transport | ClientHello / ServerHello in the HTTPS pcaps |
| TCP (443, 3001, 3002) | 4 Transport | Transport | SYN / SYN-ACK / ACK |
| UDP (DNS on 53) | 4 Transport | Transport | DNS frames |
| IPv4 (`10.211.55.0/24`) | 3 Network | Internet | IP header: source/destination address, TTL |
| Ethernet / virtual NIC `enp0s5`, ARP, MAC `00:1c:42:…` | 2 Data link | Link | Ethernet II header in every frame |
| Parallels virtual network | 1 Physical | Link | (virtualised) |

TLS is often drawn "on top of TCP" in the TCP/IP model because it is a library used by the application, while in
the OSI model it best fits the presentation/session layers: it negotiates a session and encrypts the data.

---

## 3. Devices, topologies and cloud equivalents

| Our component | What it does here | Cloud equivalent |
|---|---|---|
| dns01 (dnsmasq), authoritative for `cn.test` | Private DNS zone | **AWS Route 53 private hosted zone**, GCP Cloud DNS private zone |
| dns02 on app01 (backup resolver) | Second DNS server with the same records | Route 53's multiple redundant name servers |
| 30 s TTL + record change (Ext. B/E) | DNS-based traffic shifting | Route 53 weighted / failover routing, blue-green deployments |
| edge01 (nginx: TLS termination, reverse proxy, round-robin) | Single entry point | **AWS Application Load Balancer (ALB)**, GCP HTTPS Load Balancer; also a **CDN edge** node (CloudFront) |
| `max_fails` / `fail_timeout` passive health checks | Remove a failed backend | ALB **target group health checks** (active, on a path such as `/api/status`) |
| Local CA + server certificate | TLS identity | **AWS Certificate Manager (ACM)** certificate on the load balancer |
| app01 / app02 backends | Application servers | EC2 instances / containers in a **target group** or auto-scaling group |
| iptables: ports 3001/3002 only from the edge (Ext. C) | Backend isolation | **Security group** rule "allow 3001 from the ALB's security group"; backends in a **private subnet** |
| edge02 standby + DNS cutover | Edge migration | A second load balancer / region with Route 53 failover records |
| `10.211.55.0/24` Parallels network | Private LAN | **VPC** with a private subnet |

Topology: a single LAN segment (a logical **star** around the virtual switch). All four VMs are in one broadcast
domain, so no routing is involved between them; the gateway `.1` is only used for traffic leaving the LAN.

---

## 4. Transport layer: ports and socket pairs

A TCP connection is identified by the **4-tuple** (source IP, source port, destination IP, destination port), plus
the protocol. The server uses a well-known port, while the client's OS picks a random **ephemeral** port
(Linux range 32768–60999).

| Flow | Socket pair from our captures | Transport |
|---|---|---|
| DNS query | `10.211.55.8:45316 → 10.211.55.5:53` (`phase1_dns_query`, frames 3–4) | UDP |
| HTTPS client → edge | `10.211.55.8:49972 → 10.211.55.6:443` (`phase1_https_tcp_tls`, frame 7) | TCP |
| Edge → Backend A | `10.211.55.6:42788 → 10.211.55.7:3001` (`phase1_nginx_backend_lb`, frame 15) | TCP |
| Edge → Backend B | `10.211.55.6:52572 → 10.211.55.8:3002` (`phase1_nginx_backend_lb`, frame 40) | TCP |

Note that nginx is a **client** on the backend side: it gets its own ephemeral port, which is why the backends see
the edge's IP rather than the real client (the real client IP is passed in `X-Forwarded-For` / `X-Real-IP`).

Why UDP for DNS? One small question and one small answer: no handshake is needed and a lost packet is simply retried.
DNS falls back to TCP/53 for large answers and zone transfers.

---

## 5. TCP reliability: sequence and acknowledgement numbers

From `phase1_https_tcp_tls.pcapng` (Wireshark shows **relative** sequence numbers; the raw ISNs are random):

| Frame | Direction | Flags | Seq | Ack | Len | Meaning |
|---|---|---|---|---|---|---|
| 7 | client → edge | SYN | 0 (raw 71296886) | – | 0 | Client picks its initial sequence number (ISN), offers MSS 1460, window scaling, SACK |
| 8 | edge → client | SYN, ACK | 0 (raw 4283561509) | 1 | 0 | Server picks its own ISN and acknowledges the client's SYN (a SYN consumes one sequence number) |
| 9 | client → edge | ACK | 1 | 1 | 0 | Handshake complete, no data yet |
| 10 | client → edge | PSH, ACK | 1 | 1 | 1571 | ClientHello: 1571 bytes of data |
| 11 | edge → client | ACK | 1 | **1572** | 0 | "I have every byte up to 1571; send byte 1572 next" (1 + 1571) |
| 12 | edge → client | PSH, ACK | 1 | 1572 | 2963 | ServerHello and the encrypted handshake |
| 13 | client → edge | ACK | 1572 | **2964** | 0 | Cumulative ACK for the server's 2963 bytes |

How this gives reliability:
* **Sequence numbers** number every byte, so the receiver can put segments in order and detect gaps.
* **Cumulative ACKs** say "the next byte I expect". If an ACK does not arrive before the retransmission timeout
  (or three duplicate ACKs arrive), the sender **retransmits**. We saw exactly that in Phase 2: a SYN dropped by
  the firewall is retransmitted until `nc` gives up (`timed out`).
* **Flow control:** the `Win=` field (64240, 65160, … scaled by WS=256) is the receiver's advertised window: how many
  bytes the sender may have in flight without an acknowledgement. It stops a fast sender from overrunning a slow receiver.
* **Connection teardown** uses FIN/ACK in both directions; a **RST** aborts at once. A stopped backend answers a SYN
  with RST, which is why nginx logs `connect() failed (111: Connection refused)` (Extension D).

---

## 6. HTTP/1.1, HTTP/2, HTTP/3 and REST

* **REST:** the backends expose resources with `GET /` and `GET /api/status`, returning JSON, statelessly. Every
  request carries everything needed to answer it, which is what makes load balancing across two backends trivial.
* **HTTP/1.1 (demonstrated):** all our traffic is HTTP/1.1 (`HTTP/1.1 200 OK` in every capture). It is text-based,
  with one request at a time per connection; keep-alive reuses the TCP+TLS connection for several requests.
* **HTTP/2 (not enabled):** our nginx `listen 443 ssl;` does not include `http2`, so clients negotiate HTTP/1.1 via
  ALPN. Enabling it (`listen 443 ssl http2;` or `http2 on;` in newer nginx) would give binary framing, **multiplexing**
  of many requests over one connection, header compression (HPACK) and no application-level head-of-line blocking.
  It is negotiated inside the TLS handshake with the ALPN extension (`h2`).
* **HTTP/3 (explanation only):** HTTP over **QUIC**, which runs on **UDP/443** instead of TCP. QUIC builds TLS 1.3 into the
  transport, sets up a connection in 1 RTT (0-RTT on resumption), multiplexes streams so a lost packet blocks only its
  own stream (no TCP head-of-line blocking), and supports connection migration when a client's IP changes. Servers
  advertise it with the `Alt-Svc` header.

---

## 7. HTTPS and TLS

* **Termination at the edge:** TLS ends at nginx on edge01; the hop to the backends is plain HTTP inside the private
  LAN. This centralises certificates and lets nginx read headers to load-balance.
* **Certificate validation:** the client checks (1) that the certificate chains to a trusted CA (our local CA was
  added with `update-ca-certificates`), (2) that the name matches the **SAN** (`DNS:app.cn.test`), and (3) that it is
  within its validity dates. This is why we never need `curl -k`, and why `https://api.cn.test` fails (not in the SAN).
* **Handshake** (TLS 1.2, `phase1_https_tpc_tls12.pcapng`, frames 13–18): ClientHello (versions, cipher suites, SNI)
  → ServerHello (chosen cipher) → **Certificate** (visible in clear in TLS 1.2) → ServerKeyExchange (ECDHE) →
  ServerHelloDone → ClientKeyExchange → ChangeCipherSpec → Finished, then encrypted Application Data.
* **TLS 1.3** (`phase1_https_tcp_tls.pcapng`, frames 10–14): one round trip. The ServerHello is followed straight
  away by encrypted records, so the certificate itself is **not visible** in the capture. That is why the payload,
  including the HTTP headers, cannot be read in Wireshark without the session keys.

---

## 8. HTTP caching: fresh hit vs conditional request vs full request

The backends send `Cache-Control: max-age=60` and an `ETag` (SHA-256 of the body), and answer `304` when
`If-None-Match` matches.

| Case | What the client does | Network traffic | Server response |
|---|---|---|---|
| **Fresh cache hit** | Copy is younger than `max-age=60` → uses it directly | **none** | – |
| **Conditional request** (revalidation) | Copy is stale (or the user forces revalidation) → sends `If-None-Match: "<etag>"` | small request | **`304 Not Modified`**, no body: keep using the cached copy |
| **Full request** | No cached copy, or the ETag changed | request + full body | `200 OK` with the body and a new ETag |

Evidence: `phase-1/evidence/images/fig38`–`fig41` (Backend A and B headers, then 304 for a matching ETag).

Note that curl has no cache, so with curl we demonstrate the **conditional** request manually
(`curl -I -H 'If-None-Match: "<etag>"' …` → 304). A browser shows fresh hits as "(from memory cache)" or "(disk cache)".

**CDNs** apply the same rules at the edge: an edge node serves fresh objects without contacting the origin, and
revalidates stale ones with conditional requests. Our nginx edge is the place where such caching would be added
(`proxy_cache`).

**DNS caching** is the same idea one layer down: the 30 s DNS TTL is the `max-age` of a DNS answer (Extension B).

---

## 9. Email protocols (explanation only)

| Protocol | Port(s) | Role |
|---|---|---|
| **SMTP** | 25 (server-to-server), 587 (submission with STARTTLS), 465 (implicit TLS) | **Sending / relaying** mail: client → its mail server → recipient's mail server |
| **POP3** | 110, 995 (TLS) | **Retrieving** mail by downloading it, usually deleting it from the server |
| **IMAP** | 143, 993 (TLS) | **Accessing** mail kept on the server, with folders synced across devices |

Link to this project: mail delivery depends on DNS **MX records** (which host accepts mail for a domain), plus TXT
records for SPF/DKIM/DMARC. It is the same DNS-as-directory idea as our `app.cn.test` A record.

---

## 10. Cloud load balancing

Our nginx edge is a hand-built layer-7 load balancer:

| Feature | nginx (ours) | AWS ALB / GCP HTTPS LB |
|---|---|---|
| Algorithm | round-robin (`least_conn` possible) | round-robin / least outstanding requests |
| Health checks | **passive** (`max_fails=1 fail_timeout=10s`) | **active** probes on a path + passive |
| TLS | terminated at nginx with our CA's certificate | terminated with an ACM / managed certificate |
| Redundancy | single edge (a single point of failure), manual standby edge02 | multi-AZ by design, no single node |
| Backend isolation | iptables allow-list | security groups, private subnets |

Layer 4 vs layer 7: an **NLB** (layer 4) balances TCP connections without reading HTTP; an **ALB** (layer 7), like our
nginx, terminates TLS, reads HTTP and can add headers such as `X-Backend` / `X-Forwarded-For` or route by path.
