# Troke Frontend — Design Spec

**Date:** 2026-04-02
**Stack:** Next.js 14 (App Router) · Supabase · Tailwind CSS · TypeScript

---

## Overview

A business-facing website for Troke — an enterprise medical AI inference API. Two distinct zones:

1. **Marketing site** — pulls in enterprise customers, explains the product, drives "Request Access" CTA
2. **App** — authenticated dashboard for approved users to manage API keys

---

## Visual Style

Dark technical. Deep navy/black backgrounds (`#0a0a0f`, `#070d18`), electric blue accents (`#1a6fff`, `#4d9fff`), muted slate text (`#6b8ab0`), white headings. Monospace code samples throughout. Font: Inter.

Logo: "troke" in Inter, weight 700, letter-spacing -0.5px. No icon.

---

## Pages

### 1. `/` — Landing Page

**Nav:** Logo left. `Docs` · `Sign In` links center-right. `Request Access` CTA button right.

**Hero (centered):**
- Small pill badge: "MEDICAL AI INFERENCE API"
- H1: "Radiology. Dermatology. Pathology. Ophthalmology."
- Subtext: "Structured medical image inference via a single REST API. Built for clinical software teams."
- Two CTAs: `Request Access` (primary blue) · `View Docs →` (ghost)
- Code block teaser below: shows the two-step async flow (POST → job_id → GET → structured result)

**How It Works section:**
Three steps with icons: Submit image → Receive job ID → Poll for structured result. Emphasises async design and <90s latency.

**Domains section:**
Four cards (radiology, dermatology, pathology, ophthalmology). Each card lists: what you send, what fields come back.

**Use Cases section:**
Three short paragraphs targeting: clinical decision support apps, health record systems, medical device software.

**Footer:**
Logo · Docs · Request Access · © Troke

---

### 2. `/request-access` — Sign-Up Form

Fields:
- Full name (required)
- Work email (required)
- Company name (required)
- Role (dropdown: Engineer, Product, Clinical, Executive, Other)
- How you plan to use Troke (textarea, required)
- Password (required, min 8 chars)

On submit: Supabase `signUp` creates auth user + `profiles` row with `status: 'pending'`. User sees inline confirmation: "We'll review your application and be in touch." No redirect — stays on page.

After approval, you flip `profiles.status` to `'approved'` in the Supabase dashboard. The user's account already exists — they just sign in at `/login` and are routed through normally.

---

### 3. `/pending` — Under Review

Shown when an approved user signs in but `status` is still `'pending'`. Simple centered message: "Your application is under review. We'll email you when you're approved." No actions.

---

### 4. `/login` — Sign In

Standard email + password. After auth, middleware reads `profiles.status`:
- `pending` → redirect `/pending`
- `approved` → redirect `/dashboard`

---

### 5. `/dashboard` — API Key Management

**Layout:** Sidebar nav (left, dark `#070d18`) + main content area.

Sidebar items:
- troke logo (top)
- API Keys (active by default)
- Docs (links to `/docs`)
- Company name + Sign Out (bottom)

**Main — API Keys view:**
- Page title "API Keys" + "2 active keys" subtext
- `+ New Key` button (top right) — opens modal: label input → creates key → shows raw key once in a copy-to-clipboard field with warning "Store this now — it won't be shown again"
- List of key cards: label, masked key (`sk-tr-••••••••4f2a`), created date, `Revoke` button
- Revoke triggers confirmation dialog before calling API

---

### 6. `/docs` — API Reference

Renders `docs/api.md` as a styled page. Sidebar TOC (anchor links). Code blocks syntax-highlighted. Matches site dark theme. No separate build step — read at request time via `fs.readFileSync` + `react-markdown`.

---

## Auth Flow (Supabase)

```
User fills /request-access (email + password + company details)
  → Supabase signUp → auth user created + profiles row: status = 'pending'

Admin approves in Supabase dashboard
  → profiles.status = 'approved'

User signs in at /login
  → Middleware checks profiles.status
  → approved → /dashboard
  → pending → /pending
```

---

## Data Model (Supabase Postgres)

### `profiles`
| Column | Type | Notes |
|--------|------|-------|
| id | uuid | FK → auth.users.id |
| full_name | text | |
| company | text | |
| role | text | |
| use_case | text | |
| status | text | `pending` \| `approved` |
| created_at | timestamptz | |

### `api_keys`
| Column | Type | Notes |
|--------|------|-------|
| id | uuid | PK |
| user_id | uuid | FK → profiles.id |
| label | text | User-defined name |
| key_hash | text | SHA-256, matches what Troke stores in Redis |
| created_at | timestamptz | |
| revoked_at | timestamptz | null = active |

---

## Next.js API Routes

### `POST /api/keys`
1. Verify Supabase session (server-side)
2. Validate label (1–50 chars)
3. Call `POST /v1/admin/keys` on Troke backend (ADMIN_KEY from env, never exposed to browser)
4. SHA-256 hash the returned key
5. Insert row into `api_keys` table
6. Return raw key to client (once only — never stored plain)

### `DELETE /api/keys/[id]`
1. Verify session, confirm key belongs to this user
2. Fetch `key_hash` from `api_keys`
3. Call `DELETE /v1/admin/keys/{key_hash}` on Troke backend
4. Set `revoked_at = now()` in Supabase
5. Return 200

---

## Middleware

`middleware.ts` on `/dashboard/*`:
- No session → redirect `/login`
- Session + `status: pending` → redirect `/pending`
- Session + `status: approved` → allow

---

## Environment Variables

```
NEXT_PUBLIC_SUPABASE_URL
NEXT_PUBLIC_SUPABASE_ANON_KEY
SUPABASE_SERVICE_ROLE_KEY     # server-only, for admin operations
TROKE_API_URL                 # e.g. http://localhost:8000
TROKE_ADMIN_KEY               # server-only, never exposed to browser
```

---

## Project Structure

```
frontend/                     # new directory at repo root
  app/
    page.tsx                  # landing
    request-access/page.tsx
    pending/page.tsx
    login/page.tsx
    dashboard/
      layout.tsx              # sidebar shell
      page.tsx                # API keys view
    docs/page.tsx
    api/
      keys/route.ts           # POST
      keys/[id]/route.ts      # DELETE
  components/
    KeyCard.tsx
    NewKeyModal.tsx
    Sidebar.tsx
  lib/
    supabase.ts               # client + server instances
    troke.ts                  # typed wrapper for Troke admin calls
  middleware.ts
  tailwind.config.ts
```

---

## Out of Scope (for now)

- Pricing / billing / Stripe
- Usage metrics / rate limit display in dashboard
- Admin panel within the website (use Supabase dashboard for approvals)
- OAuth / SSO sign-in
