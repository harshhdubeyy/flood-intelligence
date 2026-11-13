# Flood Intelligence Platform

Premium, light-themed municipal flood command center built with Next.js 14, TypeScript, Tailwind CSS, Framer Motion, TanStack Query, Axios, Mapbox GL, react-map-gl, Deck.gl, Lucide and Recharts.

## Run

1. Create `.env.local` and set `NEXT_PUBLIC_API_URL` to the backend base (defaults
   to `http://localhost:8000/v1`).
2. Add `NEXT_PUBLIC_MAPBOX_TOKEN` to enable the live map canvas.
3. For the operator console, set the server-only `BACKEND_API_URL` (or use
   `NEXT_PUBLIC_API_URL`) and generate a random `OPERATOR_SESSION_SECRET` with at
   least 32 characters. Keep it out of `NEXT_PUBLIC_*` variables. The backend must
   have `FLOOD_OPERATOR_TOKENS` configured for named operators.
4. Run `npm install`, then `npm run dev`.

Routes: `/dashboard`, `/dashboard/reports`, `/dashboard/alerts`, `/dashboard/social`,
`/dashboard/responders`, and `/operations`.

The operator route uses an encrypted, HttpOnly, SameSite=Strict cookie through a
same-origin Next.js server proxy; bearer tokens are not stored in browser storage.
Production deployments must serve the frontend and backend API over HTTPS and use
a durable, access-controlled evidence store rather than the backend's local `/tmp`
development storage.

The UI does not create simulated operational data. Until a backend returns records, it uses loading skeletons, intentional empty states, errors and retry actions.
