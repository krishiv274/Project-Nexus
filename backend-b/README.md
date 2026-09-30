# Backend B

Backend B is a minimal Python HTTP service that runs on port 3002 and exposes a small JSON API.

## Functionality

- Handles GET requests on `/` and `/api/status`
- Returns JSON with backend identity and status
- Adds `X-Backend: B` to responses
- Adds `Cache-Control: max-age=60` and `ETag` headers
- Supports conditional validation with `If-None-Match`
- Returns HTTP 304 when the current response body has not changed

## Example responses

- `/` -> `{ "backend": "B", "status": "running" }`
- `/api/status` -> `{ "backend": "B", "status": "ok" }`

This backend provides the second upstream for nginx round-robin load balancing and validates the same caching behavior as Backend A.
