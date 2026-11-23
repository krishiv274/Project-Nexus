# CN Project - Private Network Service Platform

A fully local Computer Networks course project built with **one physical
Mac and four Ubuntu VMs**.

The project demonstrates an end-to-end network request:

``` text
Client
  │
  │ DNS query
  ▼
VM1 — dns01
Private DNS / dnsmasq
  │
  │ app.cn.test → Edge IP
  ▼
VM2 — edge01
nginx + TLS termination + Load Balancer
  │
  ├──────────────► VM3 — app01
  │                 Backend A :3001
  │
  └──────────────► VM4 — app02
                    Backend B :3002
```

The central idea is that **the network is the project**. The backend
applications are intentionally simple; the important parts are DNS, TCP,
TLS, HTTP, load balancing, caching, packet analysis, resilience, and
failure diagnosis.

The architecture follows the supplied course project: private DNS, an
nginx edge/load balancer, two HTTP backends, HTTPS/TLS termination, HTTP
caching, Wireshark evidence, and Phase 2 resilience/failure
demonstrations.

------------------------------------------------------------------------

## Table of Contents

-   [1. Project Goals](#1-project-goals)
-   [2. Architecture](#2-architecture)
-   [3. VM Inventory](#3-vm-inventory)
-   [4. Network Plan](#4-network-plan)
-   [5. Repository Structure](#5-repository-structure)
-   [6. Prerequisites](#6-prerequisites)
-   [7. First-Time Setup](#7-first-time-setup)
-   [8. Starting the Entire Network](#8-starting-the-entire-network)
-   [9. Verify the Network](#9-verify-the-network)
-   [10. Verify DNS](#10-verify-dns)
-   [11. Verify Backends](#11-verify-backends)
-   [12. Verify nginx and Load
    Balancing](#12-verify-nginx-and-load-balancing)
-   [13. Verify HTTPS and TLS](#13-verify-https-and-tls)
-   [14. Verify HTTP Caching](#14-verify-http-caching)
-   [15. Capture DNS → TCP → TLS →
    HTTP](#15-capture-dns--tcp--tls--http)
-   [16. Normal Startup Order](#16-normal-startup-order)
-   [17. Shutdown](#17-shutdown)
-   [18. Restarting One Component](#18-restarting-one-component)
-   [19. Phase 2 Resilience](#19-phase-2-resilience)
-   [20. Failure Demonstrations](#20-failure-demonstrations)
-   [21. Troubleshooting Method](#21-troubleshooting-method)
-   [22. Final Demonstration
    Checklist](#22-final-demonstration-checklist)
-   [23. Evidence Organization](#23-evidence-organization)
-   [24. Project Phases](#24-project-phases)
-   [25. Important Rules](#25-important-rules)

------------------------------------------------------------------------

# 1. Project Goals

The final system should allow a client VM to:

1.  Resolve a private `.test` domain through our own DNS server.
2.  Connect to the nginx edge using HTTPS.
3.  Complete a TLS handshake.
4.  Have nginx terminate TLS and forward HTTP traffic to a backend.
5.  Load-balance requests between Backend A and Backend B.
6.  Observe `X-Backend: A` and `X-Backend: B`.
7.  Demonstrate HTTP caching.
8.  Capture DNS, TCP and TLS traffic in Wireshark.
9.  Demonstrate controlled failures.
10. Demonstrate DNS failover, TTL behavior, service isolation and
    backend failover in Phase 2.

The course project requires the final Phase 1 system to resolve the
private domain, connect over HTTPS, and receive responses from both
backends through the load balancer.

------------------------------------------------------------------------

# 2. Architecture

## Logical topology

``` text
                         LOCAL MAC
                             │
                Parallels Desktop (macOS host)
                             │
                    ┌────────┴────────┐
                    │  Private VM LAN │
                    │  Shared Network │
                    │  10.211.55.0/24  │
                    └────────┬────────┘
                             │
        ┌────────────────────┼─────────────────────┐
        │                    │                     │
        ▼                    ▼                     │
 ┌─────────────┐      ┌─────────────┐              │
 │    dns01    │      │    edge01   │              │
 │  DNS/client │      │ nginx/TLS/LB│              │
 │   :53       │      │ :443/:8443  │              │
 └─────────────┘      └──────┬──────┘              │
                              │                    │
                    ┌─────────┴─────────┐           │
                    │                   │           │
                    ▼                   ▼           │
             ┌─────────────┐     ┌─────────────┐    │
             │    app01    │     │    app02    │    │
             │ Backend A   │     │ Backend B   │    │
             │   :3001     │     │   :3002     │    │
             └─────────────┘     └─────────────┘    │
```

## Request flow

``` text
1. Client
      │
      │ DNS query: app.cn.test
      ▼
2. dns01
      │
      │ DNS response: Edge IP
      ▼
3. edge01:443
      │
      │ TLS handshake
      │ TLS termination
      ▼
4. nginx
      │
      ├──────────► app01:3001
      │
      └──────────► app02:3002
```

The client should **not** need to know the backend IP addresses.

------------------------------------------------------------------------

# 3. VM Inventory

  VM    Hostname   Role                                   Main Services
  ----- ---------- -------------------------------------- -----------------------------
  VM1   `dns01`    Private DNS + client                   `dnsmasq`, `dig`, `curl`
  VM2   `edge01`   Edge / reverse proxy / load balancer   `nginx`, TLS
  VM3   `app01`    Backend A                              HTTP/REST on `3001`
  VM4   `app02`    Backend B + client                     HTTP/REST on `3002`, `curl`

In Phase 2, `app01` also runs the **backup DNS server ("dns02", :53)** and the
**standby edge ("edge02", nginx :443, normally stopped)**, and `app02` is the main test
client. See [architecture/ARCHITECTURE.md](architecture/ARCHITECTURE.md) for the full
role, IP and service tables.

------------------------------------------------------------------------

# 4. Network Plan

All four VMs are attached to the Parallels **Shared Network**. These are the deployed
addresses, taken from the captured VM configuration (`ip addr`, `ip route`).

### Deployed network

``` text
Network:  Parallels Shared Network
Subnet:   10.211.55.0/24
Gateway:  10.211.55.1   (Mac host; also the upstream DNS resolver)
```

### Deployed addressing

  Host         IP              Interface   MAC                 Purpose
  ---------- --------------- ----------- ------------------- ------------------------------------------
  `dns01`      `10.211.55.5`   `enp0s5`    00:1c:42:33:e1:29   Private DNS (primary) + test client
  `edge01`     `10.211.55.6`   `enp0s5`    00:1c:42:56:b5:e8   nginx / TLS / load balancer
  `app01`      `10.211.55.7`   `enp0s5`    00:1c:42:8c:63:30   Backend A (+ dns02, edge02 in Phase 2)
  `app02`      `10.211.55.8`   `enp0s5`    00:1c:42:9d:5c:ed   Backend B + main test client

### Service ports

  Service             Host               Port
  ------------------- ---------- ------------
  DNS                 `dns01`        `53/UDP`
  HTTPS               `edge01`      `443/TCP`
  Alternative HTTPS   `edge01`     `8443/TCP`
  Backend A           `app01`      `3001/TCP`
  Backend B           `app02`      `3002/TCP`

If the environment cannot bind to ports 80/443, the course permits using
8080/8443.

------------------------------------------------------------------------

# 5. Repository Structure

``` text
Project-Nexus
│
├── README.md                 this file (build, run and demo guide)
├── CONCEPTS.md               course topic explanations (OSI mapping, cloud equivalents, TCP, caching, HTTP/2/3, email)
├── architecture/
│   ├── ARCHITECTURE.md       architecture document (Phase 1, updated for Phase 2)
│   ├── topology.png          Phase 1 topology
│   ├── phase2_topology.*     Phase 2 topology (png + pdf)
│   ├── phase2_request_flow.* request flow per protocol layer (png + pdf)
│   └── src/                  TikZ sources of the Phase 2 diagrams
│
├── backend-a/                Backend A: app.py (:3001), README.md
├── backend-b/                Backend B: app.py (:3002), README.md
│
├── phase-1/
│   ├── artifacts/            Phase 1 report: main.tex, main.pdf
│   └── evidence/
│       ├── images/           fig01–fig54 screenshots
│       ├── failures/         the five required failure demonstrations
│       ├── vm_logs/          configs and command output per VM
│       └── wireshark/        DNS, TCP/TLS, HTTP headers, load-balancing pcaps
│
└── phase-2/
    ├── artifacts/            Phase 2 final report (IEEE format): main.tex, main.pdf, figures/
    └── evidence/
        ├── images/           p2_fig01–p2_fig23 screenshots
        ├── vm_logs/          Phase 2 configs, logs and firewall rules per VM
        ├── wireshark/        Phase 2 pcaps (DNS failover, HA failover, isolation, edge cutover)
        └── troubleshooting/  Extension F method and drill write-ups
```

------------------------------------------------------------------------

# 6. Prerequisites

## Host machine

-   macOS
-   Parallels Desktop (any local VM hypervisor works)
-   Four Ubuntu VMs
-   No cloud infrastructure is required

## Software inside the VMs

Depending on the phase:

``` text
dnsmasq
nginx
OpenSSL
Python 3
curl
dig / nslookup
tcpdump
Wireshark
```

The course project recommends Homebrew, dnsmasq, nginx, OpenSSL,
Python/Node.js, curl, dig/nslookup and Wireshark.

------------------------------------------------------------------------

# 7. First-Time Setup

This section is only for the initial setup. After the network has been
configured, use the startup procedure in [Starting the Entire
Network](#8-starting-the-entire-network).

## 7.1 Start all four VMs

Start:

``` text
dns01
edge01
app01
app02
```

Make sure every VM is connected to the same private VM network.

------------------------------------------------------------------------

## 7.2 Verify the interface

On each VM:

``` bash
ip addr
```

and:

``` bash
ip route
```

Record:

``` text
Hostname
IPv4 address
Prefix
Gateway
Interface
MAC address
```

------------------------------------------------------------------------

## 7.3 Verify connectivity

From `dns01`:

``` bash
ping -c 4 10.211.55.6
ping -c 4 10.211.55.7
ping -c 4 10.211.55.8
```

From `edge01`:

``` bash
ping -c 4 10.211.55.5
ping -c 4 10.211.55.7
ping -c 4 10.211.55.8
```

Repeat as needed from the client VMs.

The important point is that all VMs must be reachable over the private
VM LAN.

------------------------------------------------------------------------

# 8. Starting the Entire Network

The safest startup order is:

``` text
1. Start VMs
       ↓
2. Start DNS
       ↓
3. Start Backend A
       ↓
4. Start Backend B
       ↓
5. Start nginx / Edge
       ↓
6. Verify DNS
       ↓
7. Verify backends
       ↓
8. Verify HTTPS
       ↓
9. Verify load balancing
```

## Step 1 --- Start the VMs

Start all four VMs in the hypervisor:

``` text
dns01
edge01
app01
app02
```

------------------------------------------------------------------------

## Step 2 --- Start DNS on dns01

On `dns01`:

``` bash
sudo systemctl start dnsmasq
```

Check:

``` bash
sudo systemctl status dnsmasq
```

If the project configuration uses another service-management method, use
the project's configured dnsmasq startup command.

Verify that DNS is listening:

``` bash
sudo ss -lunp | grep ':53'
```

------------------------------------------------------------------------

## Step 3 --- Start Backend A

On `app01`, start the backend application according to the backend's
README.

The backend must listen on:

``` text
0.0.0.0:3001
```

or another LAN-accessible interface.

It must **not** bind only to:

``` text
127.0.0.1:3001
```

Verify:

``` bash
sudo ss -lntp | grep ':3001'
```

------------------------------------------------------------------------

## Step 4 --- Start Backend B

On `app02`, start the backend application according to the backend's
README.

The backend must listen on:

``` text
0.0.0.0:3002
```

Verify:

``` bash
sudo ss -lntp | grep ':3002'
```

------------------------------------------------------------------------

## Step 5 --- Start nginx on edge01

On `edge01`:

``` bash
sudo nginx -t
```

The result should indicate that the configuration syntax is valid.

Then:

``` bash
sudo systemctl start nginx
```

Check:

``` bash
sudo systemctl status nginx
```

Verify listening ports:

``` bash
sudo ss -lntp | grep -E ':443|:8443'
```

------------------------------------------------------------------------

# 9. Verify the Network

Run these checks before testing the application.

## 9.1 Check IP configuration

``` bash
ip addr
```

## 9.2 Check routes

``` bash
ip route
```

## 9.3 Check DNS server reachability

From a client:

``` bash
ping -c 4 10.211.55.5
```

## 9.4 Check edge reachability

``` bash
ping -c 4 10.211.55.6
```

## 9.5 Check backend reachability

Before Phase 2 service isolation:

``` bash
ping -c 4 10.211.55.7
ping -c 4 10.211.55.8
```

Remember:

``` text
Host reachable
      ≠
Service reachable
```

A successful ping does not prove that TCP port 3001, 3002 or 443 is
available.

------------------------------------------------------------------------

# 10. Verify DNS

The project domain used in our plan is:

``` text
cn.test
```

with:

``` text
app.cn.test
api.cn.test
```

> If the final project configuration uses a different `.test` name,
> replace `cn.test` everywhere below with the configured project domain.

## 10.1 Query the project DNS server directly

From a client:

``` bash
dig @10.211.55.5 app.cn.test
```

Expected result:

``` text
app.cn.test → EDGE_IP
```

For the planned address:

``` text
app.cn.test → 10.211.55.6
```

## 10.2 Query the API hostname

``` bash
dig @10.211.55.5 api.cn.test
```

Expected:

``` text
api.cn.test → EDGE_IP
```

## 10.3 Short output

``` bash
dig +short @10.211.55.5 app.cn.test
```

## 10.4 nslookup alternative

``` bash
nslookup app.cn.test 10.211.55.5
```

## 10.5 Verify the configured resolver

``` bash
resolvectl status
```

or, depending on the Ubuntu installation:

``` bash
cat /etc/resolv.conf
```

The client should be configured to use the project DNS server where
required.

------------------------------------------------------------------------

# 11. Verify Backends

The backend services are intentionally simple.

## Backend A

``` text
app01:3001
```

Expected:

``` http
X-Backend: A
```

and:

``` json
{
  "backend": "A",
  "status": "ok"
}
```

Test from a permitted client:

``` bash
curl -i http://10.211.55.7:3001/
```

and:

``` bash
curl -i http://10.211.55.7:3001/api/status
```

------------------------------------------------------------------------

## Backend B

``` text
app02:3002
```

Expected:

``` http
X-Backend: B
```

and:

``` json
{
  "backend": "B",
  "status": "ok"
}
```

Test:

``` bash
curl -i http://10.211.55.8:3002/
```

and:

``` bash
curl -i http://10.211.55.8:3002/api/status
```

------------------------------------------------------------------------

# 12. Verify nginx and Load Balancing

The client should access the application through the domain:

``` text
https://app.cn.test
```

not directly through a backend IP.

## 12.1 Check nginx configuration

On `edge01`:

``` bash
sudo nginx -t
```

Then:

``` bash
sudo systemctl status nginx
```

------------------------------------------------------------------------

## 12.2 Test the application

Once the client trusts the project's certificate:

``` bash
curl -i https://app.cn.test/
```

and:

``` bash
curl -i https://app.cn.test/api/status
```

Do not use:

``` bash
curl -k
```

for the final demonstration. Certificate validation should work
normally.

------------------------------------------------------------------------

## 12.3 Demonstrate load balancing

Run multiple requests:

``` bash
for i in {1..10}; do
    echo "Request $i"
    curl -skI https://app.cn.test/api/status | grep -i '^X-Backend:'
done
```

For the final demonstration, use normal certificate validation rather
than `-k` after the trust setup is complete:

``` bash
for i in {1..10}; do
    echo "Request $i"
    curl -sI https://app.cn.test/api/status | grep -i '^X-Backend:'
done
```

Expected pattern with round-robin load balancing:

``` text
X-Backend: A
X-Backend: B
X-Backend: A
X-Backend: B
...
```

The exact first backend is not important; the important evidence is that
both backends serve requests.

------------------------------------------------------------------------

# 13. Verify HTTPS and TLS

TLS terminates at `edge01`.

``` text
Client
   │
 HTTPS
   ▼
edge01 / nginx
   │
 TLS termination
   ▼
 HTTP
   │
   ├── app01:3001
   └── app02:3002
```

## 13.1 Test the certificate

``` bash
openssl s_client -connect app.cn.test:443 -servername app.cn.test
```

If using the alternative port:

``` bash
openssl s_client -connect app.cn.test:8443 -servername app.cn.test
```

------------------------------------------------------------------------

## 13.2 Test using curl

``` bash
curl -v https://app.cn.test/api/status
```

The output should show a successful TLS connection followed by the HTTP
response.

------------------------------------------------------------------------

## 13.3 Important TLS evidence

The course requires packet evidence for the TLS handshake, including:

``` text
ClientHello
ServerHello
Certificate
Key Exchange
Finished
```

and the required capture should show that application data is encrypted.

For the course's packet-analysis requirement, save the relevant
Wireshark capture under:

``` text
captures/
```

------------------------------------------------------------------------

# 14. Verify HTTP Caching

At least one endpoint should return a cache header such as:

``` http
Cache-Control: max-age=60
```

Optionally, the application may also use:

``` http
ETag: "..."
```

## Show response headers

``` bash
curl -I https://app.cn.test/api/status
```

Look for:

``` text
Cache-Control: max-age=60
```

If ETag is implemented:

``` text
ETag: "..."
```

## Conditional request

If the endpoint supports ETags:

``` bash
curl -i \
  -H 'If-None-Match: "YOUR_ETAG"' \
  https://app.cn.test/api/status
```

The intended demonstration is a cache hit or a conditional response such
as:

``` text
304 Not Modified
```

The exact behavior depends on the endpoint's implementation and client
caching.

------------------------------------------------------------------------

# 15. Capture DNS → TCP → TLS → HTTP

This is one of the most important parts of the project.

The complete logical flow is:

``` text
DNS
 │
 ▼
TCP
 │
 ├── SYN
 ├── SYN-ACK
 └── ACK
 │
 ▼
TLS
 │
 ├── ClientHello
 ├── ServerHello
 ├── Certificate
 ├── Key Exchange
 └── Finished
 │
 ▼
Encrypted Application Data
 │
 ▼
HTTP response at the client
```

## 15.1 Capture traffic

On the appropriate VM/interface:

``` bash
sudo tcpdump -i any -w full-request.pcapng
```

Generate one fresh request from the client:

``` bash
dig app.cn.test
curl -v https://app.cn.test/api/status
```

Stop tcpdump with:

``` text
Ctrl+C
```

Move/save the capture as:

``` text
captures/full-request.pcapng
```

If using Wireshark directly, save the capture as `.pcapng`.

------------------------------------------------------------------------

## 15.2 Useful Wireshark filters

DNS:

``` text
dns
```

TCP:

``` text
tcp
```

HTTPS:

``` text
tcp.port == 443
```

Alternative HTTPS port:

``` text
tcp.port == 8443
```

TLS:

``` text
tls
```

Backend A:

``` text
tcp.port == 3001
```

Backend B:

``` text
tcp.port == 3002
```

------------------------------------------------------------------------

## 15.3 Evidence to identify

### DNS

Show:

``` text
Client → dns01
DNS Query: app.cn.test
dns01 → Client
DNS Response: Edge IP
```

### TCP

Show:

``` text
SYN
SYN-ACK
ACK
```

Record the:

``` text
Source IP
Source ephemeral port
Destination IP
Destination port
```

### TLS

Show the TLS handshake packets and then encrypted application data.

### HTTP

Use:

``` bash
curl -v
```

or browser developer tools to show request/response headers.

The payload itself should not be readable as plaintext in the HTTPS
packet capture.

### Load balancing

Show multiple requests and correlate them with:

``` text
X-Backend: A
X-Backend: B
```

------------------------------------------------------------------------

# 16. Normal Startup Order

Use this every time you want to run the complete project.

``` text
┌─────────────────────────────┐
│ 1. Start all four VMs       │
└──────────────┬──────────────┘
               ▼
┌─────────────────────────────┐
│ 2. Verify VM LAN            │
│    ping / ip addr / routes  │
└──────────────┬──────────────┘
               ▼
┌─────────────────────────────┐
│ 3. Start dnsmasq on dns01   │
└──────────────┬──────────────┘
               ▼
┌─────────────────────────────┐
│ 4. Start Backend A app01    │
│    :3001                    │
└──────────────┬──────────────┘
               ▼
┌─────────────────────────────┐
│ 5. Start Backend B app02    │
│    :3002                    │
└──────────────┬──────────────┘
               ▼
┌─────────────────────────────┐
│ 6. Start nginx on edge01    │
│    :443 / :8443             │
└──────────────┬──────────────┘
               ▼
┌─────────────────────────────┐
│ 7. dig app.cn.test          │
└──────────────┬──────────────┘
               ▼
┌─────────────────────────────┐
│ 8. curl https://app.cn.test │
└──────────────┬──────────────┘
               ▼
┌─────────────────────────────┐
│ 9. Repeat curl requests     │
│    and show A/B backends    │
└─────────────────────────────┘
```

------------------------------------------------------------------------

# 17. Shutdown

For a clean shutdown, stop application services first and then shut down
the VMs.

## Stop nginx

On `edge01`:

``` bash
sudo systemctl stop nginx
```

## Stop DNS

On `dns01`:

``` bash
sudo systemctl stop dnsmasq
```

## Stop backend applications

Stop the backend processes on:

``` text
app01
app02
```

Use the method defined by each backend's startup configuration.

## Finally

Shut down the four VMs from Ubuntu:

``` bash
sudo shutdown -h now
```

or use the VM hypervisor's shutdown controls.

------------------------------------------------------------------------

# 18. Restarting One Component

## Restart DNS

``` bash
sudo systemctl restart dnsmasq
```

Verify:

``` bash
sudo systemctl status dnsmasq
```

Then:

``` bash
dig @10.211.55.5 app.cn.test
```

------------------------------------------------------------------------

## Restart nginx

``` bash
sudo nginx -t
sudo systemctl restart nginx
```

Verify:

``` bash
curl -I https://app.cn.test/
```

------------------------------------------------------------------------

## Restart Backend A

Restart the Backend A process on `app01`.

Verify:

``` bash
curl -i http://10.211.55.7:3001/api/status
```

------------------------------------------------------------------------

## Restart Backend B

Restart the Backend B process on `app02`.

Verify:

``` bash
curl -i http://10.211.55.8:3002/api/status
```

------------------------------------------------------------------------

# 19. Phase 2 Resilience

Phase 2 extends the existing network. **Do not rebuild Phase 1.**

**Status: all Extensions A–E implemented and demonstrated; Extension F method prepared.**

| Where | What |
|---|---|
| [phase-2/artifacts/main.pdf](phase-2/artifacts/main.pdf) | Phase 2 final report (IEEE): changes, test results, troubleshooting, learning summary |
| [architecture/ARCHITECTURE.md](architecture/ARCHITECTURE.md) | Phase 2 topology, roles, request flow, remaining single points of failure |
| [phase-2/evidence/](phase-2/evidence/) | screenshots, pcaps, configs and logs for every extension |
| [phase-2/evidence/troubleshooting/](phase-2/evidence/troubleshooting/) | layer-by-layer method and drills (Extension F) |

| Extension | Implementation | Evidence |
|---|---|---|
| A Backup DNS | dnsmasq on app01 (`10.211.55.7`), same records; clients use `.5` then `.7` | `p2_fig03`–`p2_fig07`, `phase2_dns_failover.pcapng` |
| B DNS TTL | `local-ttl=30`, record changed `.6` → `.7` and back | `p2_fig01`–`p2_fig02`, `p2_fig08`–`p2_fig10` |
| C Isolation | iptables on app01/app02: only loopback and the edge(s) reach 3001/3002 | `p2_fig15`–`p2_fig18`, `p2_fig23`, `vm_logs/app0*/iptables-*.rules` |
| D Failover | nginx `max_fails=1 fail_timeout=10s`, 2 s connect timeout, retry next upstream | `p2_fig11`–`p2_fig14`, `vm_logs/edge01/cn_*.log` |
| E Edge migration | standby nginx "edge02" on app01, DNS cutover with TTL 30 | `p2_fig19`–`p2_fig22`, `vm_logs/app01/edge02_*` |

The sections below summarise each procedure; the report has the full details.

The required resilience work includes:

-   Backup DNS
-   DNS TTL experiment
-   Backend service isolation
-   Backend failover / health behavior
-   Controlled edge migration
-   Troubleshooting

## Backup DNS

Architecture:

``` text
                 Client
                /      \
               /        \
          dns01          dns02 (on app01)
     10.211.55.5          10.211.55.7
         Primary         Backup
```

Test:

``` text
1. Configure both DNS servers.
2. Stop dns01.
3. Query app.cn.test.
4. Verify resolution continues through dns02.
5. Restore dns01.
```

------------------------------------------------------------------------

## DNS TTL

Use a short project TTL, for example:

``` text
30 seconds
```

Demonstration:

``` text
1. Resolve app.cn.test.
2. Change the DNS record.
3. Resolve again before TTL expiry.
4. Observe the cached old answer.
5. Wait for TTL expiry.
6. Resolve again.
7. Observe the new answer.
8. Flush the local DNS cache and repeat the test.
```

------------------------------------------------------------------------

## Backend service isolation

After hardening:

``` text
Client ─────X────► app01:3001
Client ─────X────► app02:3002

edge01 ──────────► app01:3001
edge01 ──────────► app02:3002
```

The goal is that only the edge can directly access the backend service
ports.

Keep a rollback copy of firewall rules before testing.

------------------------------------------------------------------------

## Backend failover

Stop Backend A:

``` text
app01 ✘
```

Then repeatedly access:

``` bash
curl -i https://app.cn.test/api/status
```

The remaining healthy backend should continue serving the application.

Restart Backend A and verify that load balancing resumes.

------------------------------------------------------------------------

## Edge migration

Create a standby nginx edge on another VM (we used `app01` as "edge02", `10.211.55.7`).

Then change:

``` text
app.cn.test → old edge
```

to:

``` text
app.cn.test → standby edge
```

Observe the effect of DNS caching and TTL.

------------------------------------------------------------------------

# 20. Failure Demonstrations

The project deliberately requires failures to be introduced and
explained.

## Failure 1 --- Wrong DNS server

### Symptom

``` text
ping by IP works
DNS lookup fails
```

### Diagnosis

``` bash
ping EDGE_IP
dig app.cn.test
```

The network can still be reachable even when DNS is incorrectly
configured.

------------------------------------------------------------------------

## Failure 2 --- Wrong DNS record

### Symptom

``` text
DNS resolves
but the client is sent to the wrong destination
```

### Diagnosis

``` bash
dig app.cn.test
```

Check the returned IP against the IP inventory.

------------------------------------------------------------------------

## Failure 3 --- Backend A stopped

### Symptom

Backend A is unavailable but the application should continue through
Backend B when failover/health behavior is configured.

Test:

``` bash
curl -i https://app.cn.test/api/status
```

Repeat several times.

------------------------------------------------------------------------

## Failure 4 --- Both backends stopped

The edge can still exist even though the application upstreams are
unavailable.

Expected application-layer behavior includes an upstream error such as:

``` text
502 Bad Gateway
```

This demonstrates that:

``` text
DNS/TLS/edge
      ≠
backend application
```

------------------------------------------------------------------------

## Failure 5 --- Wrong destination port

Example:

``` bash
curl http://10.211.55.7:9999
```

instead of:

``` bash
curl http://10.211.55.7:3001
```

A reachable host does not mean that a particular service port is open.

------------------------------------------------------------------------

# 21. Troubleshooting Method

When something fails, diagnose **from lower dependency layers toward the
application**.

``` text
                Request fails
                       │
                       ▼
              ┌────────────────┐
              │ 1. DNS works?  │
              └───────┬────────┘
                      │ YES
                      ▼
              ┌────────────────┐
              │ 2. TCP works?  │
              └───────┬────────┘
                      │ YES
                      ▼
              ┌────────────────┐
              │ 3. TLS works?  │
              └───────┬────────┘
                      │ YES
                      ▼
              ┌────────────────┐
              │ 4. HTTP/app?   │
              └────────────────┘
```

Useful commands:

### DNS

``` bash
dig app.cn.test
```

### Reachability

``` bash
ping EDGE_IP
```

### Port test

``` bash
nc -vz EDGE_IP 443
```

Backend:

``` bash
nc -vz APP_A_IP 3001
nc -vz APP_B_IP 3002
```

### TLS

``` bash
openssl s_client -connect app.cn.test:443 -servername app.cn.test
```

### HTTP

``` bash
curl -v https://app.cn.test/api/status
```

### Services

``` bash
sudo systemctl status dnsmasq
sudo systemctl status nginx
```

### Listening ports

``` bash
sudo ss -lntup
```

------------------------------------------------------------------------

# 22. Final Demonstration Checklist

The final demonstration follows the course's required sequence.

## 1. Show topology and IP/service inventory

Show:

``` text
Topology diagram
IP table
VM roles
Service ports
```

------------------------------------------------------------------------

## 2. Confirm private LAN

Show:

``` bash
ip addr
ip route
ping
```

------------------------------------------------------------------------

## 3. Resolve the private domain

Show:

``` bash
dig app.cn.test
```

and demonstrate that it resolves to the edge IP using the project DNS
server.

------------------------------------------------------------------------

## 4. Open HTTPS service

Show:

``` bash
curl -v https://app.cn.test/
```

or the browser.

Use the domain name, not the IP address.

The final demo should not depend on certificate-validation bypasses.

------------------------------------------------------------------------

## 5. Show load balancing

Show repeated requests:

``` bash
for i in {1..10}; do
    curl -sI https://app.cn.test/api/status | grep -i '^X-Backend:'
done
```

Demonstrate both:

``` text
X-Backend: A
X-Backend: B
```

------------------------------------------------------------------------

## 6. Show Wireshark evidence

Show:

``` text
DNS query/response
TCP SYN
TCP SYN-ACK
TCP ACK
TLS handshake
Encrypted application data
```

------------------------------------------------------------------------

## 7. Show HTTP caching

Show:

``` bash
curl -I https://app.cn.test/api/status
```

and demonstrate:

``` text
Cache-Control
```

plus a cache hit or conditional response where implemented.

------------------------------------------------------------------------

## 8. Fail one backend

Stop Backend A and show that the service continues through Backend B
when failover/health behavior is configured.

------------------------------------------------------------------------

## 9. Demonstrate Phase 2 resilience

Show at least the configured Phase 2 evidence, such as:

``` text
Backup DNS
DNS TTL/caching
Backend isolation
Backend failover
DNS-based edge cutover
```

------------------------------------------------------------------------

## 10. Diagnose an injected fault

Use:

``` text
DNS
 ↓
TCP
 ↓
TLS
 ↓
HTTP/application
```

Do not randomly change configurations. First identify the affected
layer.

------------------------------------------------------------------------

## 11. Individual viva

Every team member should be able to explain the complete request:

``` text
DNS
 ↓
IP
 ↓
TCP
 ↓
TLS
 ↓
HTTPS
 ↓
nginx
 ↓
load balancing
 ↓
Backend A/B
 ↓
HTTP response
```

------------------------------------------------------------------------

# 23. Evidence Organization

Evidence is organised per course phase so any required item can be found quickly:

| Course requirement | Location |
|---|---|
| Topology, roles, IP/service table, request flow | `architecture/` |
| DNS resolution (dig / nslookup) | `phase-1/evidence/vm_logs/*/dig_*`, `nslookup_*`; `images/fig07`–`fig13` |
| curl / headers / load balancing | `phase-1/evidence/vm_logs/edge01/`; `images/fig16`–`fig17`, `fig26`–`fig29` |
| Wireshark: DNS, TCP handshake, TLS handshake, HTTP, LB | `phase-1/evidence/wireshark/*.pcapng`; `images/fig31`–`fig37`, `fig44`–`fig48` |
| HTTP caching (Cache-Control, ETag, 304) | `phase-1/evidence/images/fig38`–`fig41` |
| Phase 1 failure demonstrations | `phase-1/evidence/failures/`; `images/fig49`–`fig54` |
| Configuration bundle | `phase-1/evidence/vm_logs/` (Phase 1), `phase-2/evidence/vm_logs/` (Phase 2, incl. firewall rules) |
| TLS certificate setup notes | Phase 1 report, Task E; section 13 of this README |
| Backend source + launch | `backend-a/`, `backend-b/`; section 8 of this README |
| Phase 2 extensions A–F | `phase-2/evidence/` (see section 19) |
| Reports | `phase-1/artifacts/main.pdf`, `phase-2/artifacts/main.pdf` |

The course deliverables also include the architecture document,
configuration bundle, backend source code, evidence folder, Phase 2
report and final presentation.

------------------------------------------------------------------------

# 24. Project Phases

Our local-VM implementation is organized into seven practical phases
while following the course's two official graded phases.

  Our Phase   Goal                                Course Mapping
  ----------- ----------------------------------- -------------------------
  Phase 0     Build VM laboratory                 Preparation
  Phase 1     Private VM LAN                      Task A
  Phase 2     Private DNS                         Task B
  Phase 3     Backends + nginx                    Tasks C + D
  Phase 4     HTTPS + caching + packet analysis   Tasks E + F + G
  Phase 5     Resilience + hardening              Phase 2 Extensions A--E
  Phase 6     Failure diagnosis                   Extension F
  Phase 7     Final evidence + demonstration      Final evaluation

### Official milestone

``` text
VM laboratory
     ↓
Private LAN
     ↓
Private DNS
     ↓
Backend A + Backend B
     ↓
nginx load balancer
     ↓
HTTPS/TLS
     ↓
Caching
     ↓
Wireshark evidence
     ↓
========================
 OFFICIAL PHASE 1 DONE
========================
     ↓
Backup DNS
     ↓
TTL experiment
     ↓
Service isolation
     ↓
Backend failover
     ↓
Edge migration
     ↓
Failure diagnosis
     ↓
========================
    FINAL PROJECT
========================
```

------------------------------------------------------------------------

# 25. Important Rules

## Use `.test`

Use a reserved `.test` domain for the private project.

Example:

``` text
app.cn.test
api.cn.test
```

Do **not** use `.local` for this project because it conflicts with mDNS
behavior.

------------------------------------------------------------------------

## Keep applications simple

The backend is not the main project.

The important evidence is:

``` text
DNS
TCP
TLS
HTTP
Load Balancing
Caching
Packet Analysis
Resilience
Troubleshooting
```

------------------------------------------------------------------------

## Do not bypass TLS validation in the final demo

Avoid:

``` bash
curl -k
```

for the final demonstration.

The client should trust the local certificate/CA properly.

------------------------------------------------------------------------

## Clients use the domain, not the backend IP

Correct:

``` text
https://app.cn.test
```

Not:

``` text
https://10.211.55.6
```

and normally not:

``` text
http://10.211.55.7:3001
```

for the final user-facing service.

Direct backend access is useful for testing during setup, but the final
architecture uses nginx as the public entry point.

------------------------------------------------------------------------

## Take snapshots

Keep VM snapshots/checkpoints such as:

``` text
clean-ubuntu
network-ready
phase1-complete
phase2-complete
```

This is especially useful because Phase 2 deliberately introduces
failures and configuration changes.

------------------------------------------------------------------------

# Quick Command Reference

## Start

``` bash
# dns01
sudo systemctl start dnsmasq

# edge01
sudo nginx -t
sudo systemctl start nginx

# app01
# start Backend A on :3001

# app02
# start Backend B on :3002
```

## Check

``` bash
ip addr
ip route
sudo ss -lntup
```

## DNS

``` bash
dig @10.211.55.5 app.cn.test
dig +short @10.211.55.5 app.cn.test
```

## Backend A

``` bash
curl -i http://10.211.55.7:3001/api/status
```

## Backend B

``` bash
curl -i http://10.211.55.8:3002/api/status
```

## HTTPS

``` bash
curl -v https://app.cn.test/api/status
```

## Headers / caching

``` bash
curl -I https://app.cn.test/api/status
```

## Load balancing

``` bash
for i in {1..10}; do
    echo "Request $i"
    curl -sI https://app.cn.test/api/status | grep -i '^X-Backend:'
done
```

## TLS inspection

``` bash
openssl s_client \
  -connect app.cn.test:443 \
  -servername app.cn.test
```

## Capture

``` bash
sudo tcpdump -i any -w full-request.pcapng
```

------------------------------------------------------------------------

# Project Status

Update this section as the build progresses.

``` text
[✔] Phase 0 — VM laboratory
[✔] Phase 1 — Private LAN
[✔] Phase 2 — Private DNS
[✔] Phase 3 — Backends + nginx
[✔] Phase 4 — HTTPS + caching + packet evidence
[✔] Phase 5 — Phase 2 resilience
[✔] Phase 6 — Failure injection + troubleshooting
[✔] Phase 7a — Documentation (reports, architecture, evidence)
[ ] Phase 7b — Final live demonstration + viva (at the evaluation)
```

------------------------------------------------------------------------

## Core Principle

> **The application stays simple. The network is the project.**

The goal is not simply to make the URL work. The goal is to be able to
**prove and explain every stage of the request**:

``` text
DNS
 ↓
TCP
 ↓
TLS
 ↓
HTTP
 ↓
nginx
 ↓
Load Balancer
 ↓
Backend
 ↓
Response
```

and then demonstrate what happens when individual components fail.
