# Flood Intelligence Platform

Premium, light-themed municipal flood command center built with Next.js 14, TypeScript, Tailwind CSS, Framer Motion, TanStack Query, Axios, Mapbox GL, react-map-gl, Deck.gl, Lucide and Recharts.

## Run

1. Copy `.env.example` to `.env.local`.
2. Set `NEXT_PUBLIC_API_URL` to the backend base (defaults to `http://localhost:8000/v1`).
3. Add `NEXT_PUBLIC_MAPBOX_TOKEN` to enable the live map canvas.
4. Run `npm install`, then `npm run dev`.

Routes: `/dashboard`, `/dashboard/reports`, `/dashboard/alerts`, `/dashboard/social`, and `/dashboard/responders`.

The UI does not create simulated operational data. Until a backend returns records, it uses loading skeletons, intentional empty states, errors and retry actions.
