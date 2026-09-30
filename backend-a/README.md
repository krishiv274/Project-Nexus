# Backend A

Backend A is a minimal Python HTTP service that runs on port 3001 and exposes a small JSON API.

## Functionality

- Handles GET requests on `/` and `/api/status`
- Returns JSON with backend identity and status
- Adds `X-Backend: A` to responses
- Adds `Cache-Control: max-age=60` and `ETag` headers
- Supports conditional validation with `If-None-Match`
- Returns HTTP 304 when the current response body has not changed

## Example responses

- `/` -> `{ "backend": "A", "status": "running" }`
- `/api/status` -> `{ "backend": "A", "status": "ok" }`

This backend is used as one of the upstream servers behind the nginx reverse proxy and load balancer.
