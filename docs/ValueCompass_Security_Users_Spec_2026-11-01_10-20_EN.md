---
title: "ValueCompass — Security and Users Specification"
subtitle: "2026-11-01_10-20 · English (source of truth) · approved"
---

# Security and Users

**Purpose:** who can use ValueCompass, what each user sees, and how data and keys are protected. This stage runs **before K7**, because sign-in is the first screen of K7. It builds the database side, the server functions and the rules. K7 builds the screens.

**Decisions of 2026-10-29 (Elad):**

- Registration is by invitation, or open with admin approval.
- Two roles: user and admin.
- Stock data is shared. Portfolio, watchlist and support requests are private.
- Adding a company to the database has no limit.
- Smart search is invisible to the user.

## 1. Registration and sign-in

### 1.1 Registration modes

There are two modes. The admin chooses one in the settings (`registration_mode`).

| Mode | Flow |
|---|---|
| **Invite** (default) | **Invitation:** the admin enters an email on the admin page. Supabase Auth sends an invitation link, and the user sets a password. **Self-sign-up is blocked.** |
| **Open with approval** | **Sign-up:** anyone can sign up and verify the email. The account starts as `pending`. **Approval:** the admin approves → `active`, or rejects → `disabled`. A pending user sees only "ממתין לאישור מנהל". |

- **Email verification:** required in both modes.
- **When a user signs up** in open mode, the admin receives an email.

### 1.2 Sign-in

- **Method:** email and password, through Supabase Auth.
- **Password:** at least 10 characters (Auth setting).
- **Reset:** by email link.
- **Session:** the Supabase default with refresh. Sign-out from the menu.
- **Google sign-in:** later, before opening to the public (decision of 2026-10-23).
- **Admin second factor (TOTP):** optional, recommended before opening to the public.

## 2. Roles

| Role | Can |
|---|---|
| **User** | All screens. Own portfolio and watchlist. Search. Add a company that is not in the database. Import a broker file. Send a support request. |
| **Admin** (Elad: also the approver and the developer at this stage) | Everything a user can, plus the admin pages: users (invite, approve, disable), the extraction approval queue, Hebrew text review, support requests, system status (queue, scheduler, quota). |

- **Storage:** the role and status live in `user_profiles`.
- **Checks:** every admin action is checked in the database (RLS function `is_admin()`) and in the server functions, never only in the screen.
- **No viewer-only role:** a user simply decides whether to add a portfolio.

## 3. What is shared and what is private

| Data | Who sees it |
|---|---|
| **Stock data:** financial facts, scores, values and buy prices, backgrounds, analyses, prices, approved extraction and AI answers | Every **active** user. Unauthenticated, pending and disabled accounts see nothing. |
| **Portfolio, watchlist** | The owner only |
| **Support requests** | The owner, and the admin |
| **Unapproved extraction, work queue, logs** | The admin only, in the admin pages |

**What the admin sees:**

- **Portfolios and watchlists:** the admin screens do **not** show a user's portfolio or watchlist.
- **Counts only:** the admin and the scheduler see aggregates only, e.g., "this stock is in 3 portfolios or watchlists". The scheduler needs this to pick hot stocks (`v_holding_counts`, security-definer view, no user ids).
- **Attached to a request:** when a user attaches the portfolio to a support request, the admin sees it there.
- **Database access:** as the owner of the database, the admin can technically see all data through the Supabase dashboard. This cannot be prevented and is stated in the privacy note.

## 3a. Access model: read through views, write through functions (decided 2026-11-01)

**Principle:** only the admin can edit the database. A user never edits the database directly. A user only uses the system: views the screens, searches, requests a stock that was not found, and manages their own portfolio, watchlist and requests **through the system's actions**.

| Access | User (active) | Admin |
|---|---|---|
| **Tables** | **No access at all** — no read, no write (all table privileges revoked from `anon` and `authenticated`) | Full |
| **Read** | Only a fixed list of read-only views (below), each limited to approved stock data or to the user's own rows | All |
| **Write** | **Only through server functions**, each one action, each checking the user is active and the row is the user's own | All, and every admin action goes to `admin_audit_log` |

**Default closed:** a table or view not on the list is invisible. Forgetting a rule hides data; it never exposes it.

**Read-only views (the core list; K7 may add views by a reviewed migration):**

| View | Shows |
|---|---|
| `v_stocks` | Company list for search: ticker, display name, industry, profile, processing state |
| `v_stock_page` | The stock page: approved scores, ranges, values, buy prices, price position, background and analysis texts (approved only), display metrics |
| `v_my_profile` | The user's own name, language, role and status (read-only) |
| `v_my_portfolio`, `v_my_watchlist` | The user's own rows only |
| `v_my_tickets` | The user's own support requests, with status and the admin's reply ("My requests" screen) |
| `v_top_ranked` | Top-ranked stocks (Display Spec 3.3): top 5 combined (only stocks with all four scores), top 5 in each of the four ratings; filters by sector and country; approved data only |
| `v_my_notifications` | The user's own in-app notifications, unread first |

**Write functions (Edge Functions):**

| Function | Action |
|---|---|
| `portfolio-save`, `portfolio-delete` | Add, change or delete a holding in the user's own portfolio |
| `watchlist-add`, `watchlist-remove` | The user's own watchlist |
| `broker-import` | Import a broker file into the user's own portfolio (S2) |
| `request-company` | Request a stock that is not in the database (see below) |
| `support-send` | A support request or error report |
| `profile-update` | Only the user's display name and language |
| `account-delete` | Deletes the user's own private data |
| `notifications-read` | Marks the user's own notifications as read |

**Search and automatic request:**

1. **Search:** reads `v_stocks` (ticker and name, typo-tolerant); smart search runs behind it (section 5).
2. **No result:** the system calls `request-company` **automatically**:
   - RESOLVE checks SEC.
   - **Found and supported:** the company is queued at priority 1, and the screen shows "בעיבוד — יושלם בהמשך".
   - **Not found or unsupported:** the screen shows the reason, and the report form is offered already filled in (section 6).

**User table:** `user_profiles` (existing) is extended with `role`, `status` and `invited_by`. Users have **no** insert or update right on it (the existing self-insert and self-update policies are removed). The row is created by the sign-up trigger; the user changes only name and language, through `profile-update`; role and status change only by the admin, through `admin-users`.

**In-app notifications (decided 2026-11-01; users get no email):**

- **Table `user_notifications`:** user, type, text, link, created, read. Written only by server functions and the runner; the user reads it through `v_my_notifications`.
- **When:** the admin replied to a request, or changed its status; a stock the user requested finished processing ("המניה X מוכנה"), or failed with a reason.
- **Screen (K7):** a bell icon in the top bar with the unread count; the "My requests" screen from the menu.
- **The admin** still receives an email for each new request.

## 4. Adding a company

- **No limit,** per user or per day.
- **Flow:**
  1. The code part runs at once: SEC data and a first score without AI.
  2. The AI tasks enter the queue at priority 1.
- **The screen shows "בעיבוד — יושלם בהמשך".** It never promises "tomorrow", because a heavy queue may take longer.
- **Broker file import:** may add many companies at once. They all enter the queue and complete over the following days.

## 5. Smart search

- **One search bar.** The user does not know that a smart search exists: no label, no message, no quota notice.
- **Flow:**
  1. Ticker and name matching first (code, typo-tolerant).
  2. Otherwise S1 runs in an Edge Function, with its own Gemini key and Google project.
- **Limits:** a global daily cap in code, with no per-user limit (small invited group).
- **When the cap is reached:** the search silently falls back to the regular search. The user sees the regular results, or "לא נמצא", with the option to add the company.

## 6. Support requests and error reports

- **Button:** "דיווח תקלה / פנייה" in the menu and on every error message.
- **Form:**
  - Type: fault or request.
  - Free text.
  - Optional attachment of the portfolio.
  - Technical details added automatically: screen, ticker, error code, time.
- **Storage:** a request is always saved in `support_tickets`, so none is lost even if the email fails.
- **Email:** sent to `ADMIN_EMAIL` (now eladb203@gmail.com, a setting) through an Edge Function and an email service (e.g., Resend, free tier).
- **Automatic offer:** when adding a company fails, the user sees the reason and a report form already filled in (ticker, failed stage, error). An "unsupported" company (e.g., a 20-F filer) is offered as a **request**, not a fault.
- **Admin page:** list, status (open / in progress / closed), reply by email.

## 7. Keys and secrets

| Key | Where | Never |
|---|---|---|
| Supabase publishable (anon) key | The screen (K7). Safe by design: everything it reaches is behind RLS | — |
| Supabase service-role key | The runner (`.env` on the PC) and Supabase Edge Function secrets | In the screen, in git, in logs |
| Gemini key (loading) | The runner | In the screen |
| Gemini key (smart search, separate project) | Edge Function secret | In the screen |
| Azure Translator, email service | The runner / Edge Function secrets | In the screen |

- **`.env`:** in `.gitignore`. A check in the tests fails if a key pattern appears in a tracked file.
- **Rotation:** if a key may have leaked, regenerate it in its console and update `.env` or the Function secrets. Each key has one place to change.

## 8. Database changes (new migrations)

| Change | Content |
|---|---|
| `user_profiles` (existing, extended) | New fields: `role` (`user` / `admin`), `status` (`pending` / `active` / `disabled`), `invited_by`. A trigger creates the row on sign-up: `pending` in open mode, `active` for an invited email. The user has **no** insert or update policy (section 3a) |
| `is_admin()`, `is_active()` | Security-definer functions used by RLS |
| Table privileges | **Revoked** from `anon` and `authenticated` on every table (section 3a); users read only the views of 3a |
| Views of 3a | Read-only, active users only, own rows only where personal; `security_invoker` off, filtered by `auth.uid()` and `is_active()` |
| `support_tickets` | Owner insert and read; admin read and update |
| `v_holding_counts` | Count per company, no user ids. For the scheduler and the admin |
| `admin_audit_log` | Every admin action: who, what, when, before and after. Covers user approval, extraction approval, text edits and glossary approval |
| `app_settings` | `registration_mode`, `ADMIN_EMAIL`, smart-search daily cap |

All changes go to **test first, then production**, with RLS tests that run as each role: anonymous, pending, active user, another user and admin.

## 9. Server functions (Supabase Edge Functions)

| Function | Does | Checks |
|---|---|---|
| `admin-invite` | Sends an invitation (Auth admin API) | Caller is admin |
| `admin-users` | Approve, disable, change role | Caller is admin; writes the audit log |
| `smart-search` | S1 + validated filter + DB query | Active user; global cap |
| `broker-import` | S2 mapping of the header and 5 rows; the rest stays in code | Active user |
| `support-send` | Stores the request and sends the email | Active user (or the sign-in page, for "can't sign in") |
| `request-company` | Writes a `work_queue` request (priority 1) | Active user |

## 10. Backups and privacy

- **Backups:**
  - **Free tier:** the free Supabase tier is not expected to include restorable backups (to confirm in the dashboard when this stage starts). Therefore a weekly job in the scheduler dumps the **production data** (`pg_dump --data-only`) to the runner PC, and the schema is in git.
  - **Retention:** the last 4 copies.
  - **Off the PC:** recommended to copy to a cloud folder.
  - **Restore test:** a restore into test, once.
- **Account deletion:** a user can delete the account. Portfolio, watchlist and requests are deleted; the audit log keeps the action without personal data.
- **Privacy note** (in Settings): what is stored, who sees it, and that the admin has technical access.

## 11. Acceptance tests

| Test | Pass |
|---|---|
| Anonymous | Sees no table, view or function |
| Pending user | Sees only the waiting screen; reads no stock data |
| Active user A | Reads stock data; reads and writes only A's portfolio, watchlist and requests |
| User B | Cannot read or change A's private data, even by id |
| Admin | Admin pages and functions work; A's portfolio is not visible in admin screens; the audit log records actions |
| Non-admin calls an admin function | Refused (403) |
| Smart-search cap reached | Regular search answers; no message about smart search |
| Keys | No key in tracked files; the screen bundle contains only the publishable key |
| Backup | Dump created; restore into test succeeds |
