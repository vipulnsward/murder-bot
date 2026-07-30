# Murder Bot — web (React v2)

Modern SPA: Vite + React + TypeScript + Tailwind + shadcn-style components.
Runs alongside the server-rendered product (which stays live); this is the v2 UI.

## Dev
```bash
pnpm install
pnpm dev          # http://localhost:5173  (set VITE_API_BASE to the backend)
VITE_API_BASE=http://178.156.152.222 pnpm dev
```

## Build
```bash
pnpm build        # -> dist/  (static, deploy anywhere)
```

## Deploy on Cloudflare Pages (Git integration — no wrangler auth needed)
1. Cloudflare dashboard → **Workers & Pages → Create → Pages → Connect to Git**.
2. Pick the `vipulnsward/murder-bot` repo.
3. Build settings:
   - **Root directory:** `frontend`
   - **Build command:** `pnpm build`
   - **Build output directory:** `dist`
   - **Environment variable:** `VITE_API_BASE = https://murderbot.gg` (or the backend URL)
4. Deploy. Every push to `main` auto-builds. You get `https://<project>.pages.dev` (+ custom domain).

The backend (FastAPI on Hetzner) already sends CORS for `*.pages.dev` and `murderbot.gg`.
The public brain demo works cross-origin today; credentialed auth needs the backend on
HTTPS with `SameSite=None` cookies (comes with the domain).
