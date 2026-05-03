# GD-Sim AI Frontend

React + TypeScript + Vite client for the group discussion simulator.

## Prerequisites

- Node.js 20+
- Backend running on port 8000
- Firebase web app config values

## Local Setup

1. Install dependencies:

```bash
npm install
```

2. Create a local env file `frontend/.env`:

```bash
VITE_API_BASE_URL=http://localhost:8000
VITE_FIREBASE_API_KEY=...
VITE_FIREBASE_AUTH_DOMAIN=...
VITE_FIREBASE_PROJECT_ID=...
VITE_FIREBASE_STORAGE_BUCKET=...
VITE_FIREBASE_MESSAGING_SENDER_ID=...
VITE_FIREBASE_APP_ID=...
```

3. Start development server:

```bash
npm run dev
```

## Build

```bash
npm run build
```

## Notes

- Session and analytics API calls now require Firebase bearer tokens.
- WebSocket session start sends an ID token and backend validates session ownership.
- Configure `VITE_API_BASE_URL` to your deployed backend URL in production.
