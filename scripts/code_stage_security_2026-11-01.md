# דוח שלב אבטחה ומשתמשים — 2026-11-01

ענף `security` (worktree: `..\valuecompass-security`), מפרט `ValueCompass_Security_Users_Spec_2026-11-01_10-20` (נוסף ל-git; הישן 2026-10-29 נמחק) + תוספת סעיף 1.5 (טבלת `support_tickets`) שהתקבלה באמצע העבודה.
**נעשה על test בלבד** (`wbhxjcegoobkbnjnuise`). ייצור לא נגעתי. 0 קריאות Gemini, 0 Azure, לא הורצו ריצות קבלה, שום דבר לא נכנס ל-`work_queue`.
**לא מוזג ל-main.**

## 1. מצב בקצרה
| תחום | מצב |
|---|---|
| מיגרציות (7 קבצים + rollback לכל אחד) | הורצו על test. rollback נבדק כשרשרת שלמה בתוך טרנזקציה שבוטלה: מחזיר את user_profiles (עמודות, 3 פוליסות) ומסיר כל אובייקט חדש |
| סגירת טבלאות | `authenticated` מחזיק רק SELECT על 8 התצוגות. `anon` — כלום (`scripts/security_privileges_check.sql`) |
| פונקציות שרת | 14 נכתבו. **5 נפרסו ל-test** (ראו 4). בדיקות Deno נכתבו, **לא הורצו** (אין Deno) |
| בדיקות קבלה | 14 + 4 משלימות (0a, 0b, 3b, 13b): **כולן עברו** (`scripts/security_acceptance.py`, משתמשים אמיתיים ו-JWT אמיתי) |
| pytest | 955 עברו (כולל 8 חדשים ב-`tests/test_security_stage.py`). `vc.py status KO` מול test תקין אחרי כל שינוי |
| Auth | `supabase/config.toml` + 3 תבניות מייל בעברית נכתבו. **לא הוחלו** (אין CLI) — הוראות בסעיף 6 |
| גיבוי | מודול + בדיקות. כבוי עד `SUPABASE_PROD_DB_URL`. `pg_dump` לא מותקן אצלך |

## 2. מיגרציות (`supabase/migrations`, קידומת `security_` אחרי החותמת)
החותמות 20261101120100–120800, כדי שלא יתנגשו עם השיחה השנייה. (שם הקובץ: `<חותמת>_security_<שם>.sql`, כמו המוסכמה הקיימת — חותמת קודם, כדי שה-CLI יקרא אותן.)
| # | קובץ | תוכן |
|---|---|---|
| 1 | `security_users` | `app_settings`; `user_profiles` + `role`/`status`/`invited_by`; הסרת פוליסות ההוספה/עדכון העצמיות; `is_admin()`/`is_active()` (security definer, `search_path` קבוע); טריגר הרשמה; טריגר-שומר (גם עם הרשאת כתיבה, `authenticated` לא משנה role/status/invited_by); `support_tickets`, `user_notifications`, `admin_audit_log`, `smart_search_usage`; `v_holding_counts` |
| 2 | `security_lockdown` | `revoke all` על כל הטבלאות/רצפים/פונקציות מ-`anon` ו-`authenticated`, וגם ברירות מחדל עתידיות |
| 4 | `security_tickets_rework` | התוספת 1.5: `support_tickets` מקבלת `type` (support/bug/company_request), `requested_ticker`, `company_id`, `fail_reason`, `closed_at`. הטבלה `company_requests` שנוצרה במיגרציה 1 נמחקה. טריגרים: הודעה על כל מעבר מצב/תשובה, סנכרון בקשות חברה עם `companies.processing_state`, `closed_at` אוטומטי, פונקציית `security_retention` |
| 5 | `security_views` | 8 התצוגות |
| 6 | `security_smart_search_cap` | `smart_search_take()` — מונה יומי אטומי |
| 7 | `security_function_grants` | `EXECUTE` על `is_active`/`is_admin` ל-`authenticated` (תצוגה בודקת הרשאת פונקציה מול המשתמש הקורא, לא בעל התצוגה — נמצא בבדיקה); ביטול `EXECUTE` מ-PUBLIC על `set_updated_at` |
| 8 | `security_internal_views_owner_run` | `v_display_metrics` ו-`v_fin_*` הפכו ל-owner-run (היו security_invoker ונכשלו בתוך `v_stock_page`) |

(מספר 3 נדלג: קובץ התצוגות עבר ל-5 כדי לבוא אחרי שינוי `support_tickets`.)

**הערה למיזוג:** מיגרציה עתידית בשיחה השנייה שתיצור מחדש את `v_display_metrics`/`v_fin_*` חייבת לשמור `security_invoker = false`, אחרת `v_stock_page` ישבר.

### תיעוד שנדרש: מה `authenticated` ראה לפני השינוי
- **קריאה, 20 טבלאות:** ai_assessments, ai_texts, business_vocab, companies, company_business_profiles, company_listings, company_profile_history, company_score_summary, dictionary_items, extraction_items, fact_tags, filing_periods, financial_facts, fx_rates, gov_yields, market_snapshot, score_details, score_runs, term_translations, valuations.
- **קריאה וכתיבה (לפי RLS):** user_profiles (כולל הוספה ועדכון), portfolios, portfolio_holdings, user_watchlist.
- **9 תצוגות (SELECT):** portfolio_overview_view, stock_score_overview_view, watchlist_overview_view, v_company_status, v_display_metrics, v_fin_bank, v_fin_insurance, v_fin_realestate, v_fin_standard.
- **ללא גישה:** data_update_log, market_calendar, work_queue.

### הרשאות אחרי השינוי (`scripts/security_privileges_check.sql`)
| אובייקט | anon | authenticated |
|---|---|---|
| כל 34 הטבלאות | — | — |
| 9 התצוגות הישנות + `v_holding_counts` | — | — (`v_holding_counts`: service_role בלבד) |
| `v_stocks`, `v_stock_page`, `v_top_ranked`, `v_my_profile`, `v_my_portfolio`, `v_my_watchlist`, `v_my_tickets`, `v_my_notifications` | — | SELECT |
| `is_active()`, `is_admin()` | — | EXECUTE (מחזירות רק את מצב הקורא) |
| כל פונקציה אחרת ב-public, כל הרצפים | — | — |

### שדות `v_stock_page`
פרטים (שם, תצוגה, בורסה, מדינה, סקטור, תעשייה, פרופיל, מטבע דיווח) · שוק (מחיר, שווי שוק, 52 שבועות, תאריך, `is_stale`) · ציונים (4 ציונים, כיסוי, שווי הוגן ומחיר קנייה לכל מודל, שנת דוח, סטטוס, גרסת כללים, זמן ריצה) · רקע עסקי (פעילות, מגזרים, מוצרים, אזורים, הוקמה, נרשמה) · `valuations` (השיטה ורכיביה כפי ששמורים) · `criteria` (8 קריטריונים: שם וציון בלבד, ללא פירוט חישוב) · `metrics` (שורות `v_display_metrics` לשש התרשימים) · `texts` (רקע וניתוח, עברית ואנגלית, **approved בלבד**). מוצגות רק חברות במצב scored_partial / ai_in_progress / complete.
`v_top_ranked`: שורה לכל (סוג דירוג, היקף סקטור, היקף מדינה, מקום ≤5); סוגים: combined (רק עם 4 ציונים; ציון מחיר ×10), וארבעת הדירוגים. הסינון = בחירת `sector_scope`/`country_scope` (NULL = ללא סינון).

### הערות על המבנה שהחלטתי (לאישורך)
1. **הודעות על מניה מבוקשת ללא שינוי במריץ:** טריגר ב-DB על `companies.processing_state` מעדכן את פניות `company_request` (in_progress / done / failed + סיבה), וטריגר על הפנייה יוצר את ההודעה. **לא נגעתי בקוד המריץ.** מגבלה: כש-`failed` — המריץ לא שומר סיבה ב-DB, לכן הסיבה היא "העיבוד נכשל" (ל-unsupported — הסיבה האמיתית).
2. **מנהל ראשון:** הטריגר נותן `admin` + `active` רק למייל מוזמן (`invited_at`) השווה ל-`app_settings.admin_email`. לכן את הראשון מזמינים מממשק Supabase (Authentication → Invite user) למייל `eladb203@gmail.com`.
3. **הרשמה ללא הזמנה במצב invite → `disabled`** (הגנה נוספת מעבר לחסימה בהגדרות Auth).
4. פניות קיימות: בטבלה לא היו שורות. משתמשי test הקיימים (user-a, user-b) סומנו `active`.
5. `support-send` לא משרתת משתמש לא מחובר ("לא מצליח להיכנס") — פנייה דורשת בעלים. נשאר לדיון ב-K7.
6. החיפוש הרגיל הוא `ilike` על סימול ושם (לא סובלני לשגיאות כתיב). `pg_trgm` — לשקול ב-K7.

## 3. שמירה (ממשק, 180 יום)
`security_retention(180)`: פנייה סגורה (done/closed/failed) נמחקת 180 יום אחרי `closed_at`; פנייה פתוחה לא נמחקת; הודעות — 180 יום אחרי `created_at`. נקראת מעבודת הניקוי השבועית **רק במצב `apply: true`** (כמו כל מחיקה בעבודה הזו). שינוי ב-`src/sched/jobs.py` (ראו 8).

## 4. פונקציות שרת (`supabase/functions`)
קוד משותף: `_shared/lib.ts` (JWT → משתמש → `user_profiles.status/role` → 401/403, עטיפה, ביקורת), `_shared/request.ts` (RESOLVE מול SEC).
| פונקציה | בדיקה | נפרסה ל-test |
|---|---|---|
| portfolio-save | פעיל; תיק/שורה שייכים לקורא; 404 אחיד ל"לא שלך" ול"לא קיים" | ✅ |
| portfolio-delete, watchlist-add, watchlist-remove, profile-update (שם ושפה בלבד), account-delete (לא למנהל) | פעיל | ❌ |
| notifications-read | פעיל; רק הודעות הקורא | ✅ |
| support-send | פעיל; שומרת תמיד; מגבלה 20 ליום; מייל למנהל רק עם `RESEND_API_KEY`; תיק מצורף = של הקורא | ❌ |
| request-company | פעיל; SEC; נתמכת → `work_queue` עדיפות 1 + פנייה `company_request`; לא נמצאה/לא נתמכת/SEC לא זמין → סיבה + טופס דיווח ממולא | ✅ (**גרסה ישנה** — בלי המצב `unavailable`) |
| smart-search | פעיל; רגיל קודם; S1 רק עם `GEMINI_SEARCH_KEY` ותקרה (`smart_search_take`); כישלון/תקרה → חזרה שקטה; לא נמצא וסימול → קורא ל-request-company | ✅ |
| broker-import | פעיל; מיפוי כותרת בטבלת מילים נרדפות (בלי AI — אין מפתח); לא מוכרים → request-company | ❌ |
| admin-invite, admin-tickets | מנהל; ביקורת | ❌ |
| admin-users | מנהל; list / holding_counts / set_status / set_role; ביקורת; לא משנה את עצמו | ✅ |

הפריסה בוצעה דרך חיבור Supabase (אין CLI), עם `verify_jwt=false` — האימות נעשה בתוך הפונקציה (`auth.getUser`), כדי שלא תהיה תלות בפורמט המפתחות. הקוד שנפרס זהה לקוד שבענף פרט להערות שהוסרו.
בדיקות Deno: `supabase/functions/_tests/functions_test.ts` (14 בדיקות, לקוח מדומה ו-fetch מדומה, בלי רשת). **לא הורצו**: Deno לא מותקן. נתקלתי בכך שניתן להתקין דרך `pip install deno` — לא התקנתי בלי אישורך.

## 5. מפתחות, גיבוי
- בדיקה בסוויטה (`test_no_key_pattern_in_a_file_git_holds`): תבניות Supabase secret, Gemini, Tavily, Resend, Azure, JWT עם `role` שאינו anon, כתובת Postgres עם סיסמה — בכל קובץ ש-git מחזיק או שעומד להתווסף. `.env` מוגדר ב-ignore (נבדק). `.env.example` — שמות בלי ערכים (נבדק שאין ערכים).
- "החבילה של המסך מכילה רק מפתח פומבי": אין עדיין מסך (K7) — לא ניתן לבדוק עכשיו.
- **גיבוי:** `src/sched/backup.py`, רץ בתוך עבודת הניקוי השבועית (אין עבודה חדשה במתזמן). `pg_dump --data-only` של schemas `public` ו-`auth` ל-`backups/` (ב-`.gitignore`), 4 עותקים אחרונים, הסיסמה עוברת במשתני סביבה ולא בשורת הפקודה. כבוי כברירת מחדל; פועל רק עם `SUPABASE_PROD_DB_URL`. נבדק עם `pg_dump` מדומה: ללא משתנה, ללא `pg_dump`, הצלחה + גיזום ל-4, כישלון לא משאיר קובץ ולא עוצר את העבודה.
- **בדיקת שחזור:** `pg_dump`/`psql` לא מותקנים במחשב, לכן **לא הרצתי dump אמיתי**. בדקתי ב-SQL על test: העתקת `app_settings` ל-schema זמני `restore_check`, השוואת md5 — זהה, מחיקת ה-schema. זו בדיקת הלוגיקה בלבד. dump/restore אמיתי — אחרי התקנת `pg_dump`.
- **תוכנית חינמית:** לפי תיעוד Supabase, גיבויים יומיים (7 ימים) רק ב-Pro ומעלה; בחינמית אין גיבוי לשחזור והם ממליצים על ייצוא עצמי (`supabase db dump`) — מאשש את הצורך בגיבוי השבועי. לא בדקתי את הדשבורד שלך.

## 6. הגדרות Auth ב-test — מה שלא ניתן להחיל מכאן
`supabase/config.toml` מכיל הכל (`supabase config push`), אבל אין CLI. ידנית בדשבורד של **הפרויקט (test ואחר כך ייצור)**:
1. Authentication → Sign In / Providers → **Allow new users to sign up = כבוי** (הרשמה עצמית חסומה).
2. אותו מסך → Email → **Confirm email = דלוק**.
3. Authentication → Policies (Password) → **Minimum password length = 10**; מומלץ גם Require lowercase, uppercase, digits.
4. Authentication → Email Templates → Invite user / Reset password / Confirm signup: הדבק את `supabase/templates/*.html` וכתבו את הנושא מ-`config.toml` (עברית).
5. Authentication → URL Configuration → Site URL = כתובת האתר (K7).
6. "Leaked password protection" מופיע כאזהרה — זמין בתוכנית Pro.
**נבדק בפועל:** יצירת משתמשים דרך ה-API יוצרת פרופיל `disabled` (במצב invite, בלי הזמנה). לא בדקתי חסימת הרשמה עצמית דרך `/signup` כי ההגדרה עדיין לא הוחלה.

## 7. בדיקות קבלה (הרצה: `scripts/security_acceptance.py`, משתמשים אמיתיים ב-test: ממתין, A, B, מנהל; נמחקו בסוף)
| # | בדיקה | תוצאה | איך נבדק |
|---|---|---|---|
| 1 | אנונימי לא רואה כלום | עבר | מפתח פומבי בלבד מול 50 טבלאות/תצוגות, 4 פונקציות rpc, 5 פונקציות שרת — הכל נדחה (401/403) |
| 2 | ממתין | עבר | כל התצוגות ריקות חוץ מ-`v_my_profile` (status=pending); קריאת `companies` ישירה — 403 |
| 3 | פעיל A | עבר | קורא `v_stocks`, `v_stock_page` (כולל metrics/criteria/valuations/texts), `v_top_ranked` (≤5); כותב תיק דרך `portfolio-save`; רואה את שורתו ב-`v_my_portfolio` |
| 4 | משתמש B | עבר | תצוגות ריקות; קריאה ישירה לפי id — 403; `portfolio-save` על שורה של A — 404; הכמות של A לא השתנתה |
| 5 | מנהל | עבר | פונקציות עובדות; `v_my_portfolio` של המנהל ריק; `holding_counts` בלי מזהי משתמשים; `admin_audit_log` רשם set_status עם before/after |
| 6 | לא-מנהל קורא פונקציית מנהל | עבר | פעיל, ממתין, ופעיל שמנסה להפוך את עצמו למנהל — 403 |
| 7 | תקרת חיפוש חכם | עבר | תקרה=1: `take()` true ואז false; חיפוש "coca" מחזיר תוצאה רגילה בלי אזכור חיפוש חכם/תקרה |
| 8 | מפתחות | עבר | pytest: סריקת קבצי git. (חלק "החבילה של המסך" — ממתין ל-K7) |
| 9 | גיבוי | חלקי | הלוגיקה והגיזום נבדקו; dump אמיתי ושחזור — לא (אין pg_dump). שחזור ב-SQL עבר |
| 10 | פעיל לא קורא/כותב טבלה ישירות | עבר | A מול 42 טבלאות/תצוגות × GET/POST/PATCH/DELETE (ללא הצלחה); קטלוג ההרשאות: `scripts/security_privileges_check.sql` — רק SELECT על 8 התצוגות |
| 11 | משתמש לא משנה role/status | עבר | PATCH/POST ישיר ו-`admin-users` — 403, הפרופיל לא השתנה. בנוסף ב-SQL (טרנזקציה שבוטלה, עם הרשאת עדכון זמנית ופוליסה פתוחה): הטריגר חוסם שינוי role, status ו-invited_by ("role and status are changed by the admin only") ומתיר שינוי שם |
| 12 | חיפוש שלא מצא מפעיל request-company | עבר | `smart-search` עם `ZZZZQ` → `not_found` + `request` עם סיבה וטופס דיווח. **נתמך (הכנסה לתור) נבדק רק בבדיקות Deno שלא הורצו** ובטריגרים (13), כדי לא להכניס משימה לתור ולא לעורר את המריץ של השיחה השנייה |
| 13 | הודעות רק למשתמש הנכון | עבר | פנייה `company_request` של A: מעברים data_loaded → complete יוצרים `company_started`, `company_ready`; תשובת מנהל וסגירה על פנייה רגילה: `ticket_reply`, `ticket_status`; B — אין הודעות; `notifications-read` מסמן רק של הקורא (חברת בדיקה זמנית נמחקה) |
| 14 | שמירה 180 יום | עבר | פנייה סגורה בת 181 יום נמחקה; סגורה בת 179 נשארה; פתוחה ישנה (181) נשארה; הודעה בת 181 נמחקה, בת 179 נשארה |
בדיקות SQL נוספות (טרנזקציה שבוטלה): מייל מוזמן השווה ל-admin_email → admin+active; מוזמן אחר → user+active, `invited_by` נקבע, ו-`role` שהוזרק במטא-דאטה **לא** נשמר; לא מוזמן במצב invite → disabled; לא מוזמן במצב open → pending.
**ניקוי:** משתמשי הבדיקה, פניות, הודעות, חברת הבדיקה ושורת ביקורת אחת שנשארה מריצה שהופסקה — נמחקו. `app_settings` חזר ל-`invite` ו-`200`.
**אזהרת Advisor (test):** `security_definer_view` ×8 (מכוון: התצוגות owner-run ומסוננות לפי `is_active()`/`auth.uid()` — זה המודל של 3א), `authenticated_security_definer_function_executable` ×2 (מכוון, ראו מיגרציה 7), `rls_enabled_no_policy` INFO (מכוון: טבלאות בלי גישה), `auth_leaked_password_protection` (Pro).
**בדיקת md5:** לפני/אחרי המיגרציות `portfolios` ו-`user_watchlist` זהות. בטבלאות הצינור (companies, work_queue, ai_texts, market_snapshot, company_score_summary) הספירות/hash השתנו בין המדידות כי השיחה השנייה כותבת ל-test במקביל — ההשוואה שם לא חד-משמעית; `vc.py status KO` תקין.

## 8. קבצים שנגעתי בהם מחוץ ל-`supabase/` ו-`tests/`
| קובץ | מה |
|---|---|
| `src/sched/hot.py` | `followed_company_ids` קורא `v_holding_counts` (במקום portfolio_holdings ו-user_watchlist) — 2 שורות |
| `src/sched/jobs.py` | ב-`cleanup`: קריאה לגיבוי השבועי; במצב apply — `security_retention` (+import) |
| `src/sched/backup.py` | **חדש** |
| `tests/test_k6d1_prices.py` | עודכן לתצוגה החדשה (17 עוברות) |
| `.gitignore` | `backups/` |
| `.env.example` | **חדש** |
| `scripts/security_acceptance.py`, `scripts/security_privileges_check.sql`, `scripts/code_stage_security_2026-11-01.md` | **חדשים** |
| `docs/…Security_Users_Spec_2026-11-01_10-20_*` | נוספו (הישנים 2026-10-29 נמחקו מהתיקייה הראשית — לא היו ב-git) |
לא נגעתי ב-`src/scoring`, `src/pipeline`, `src/ai`, `src/providers`, `scripts/vc.py`, ולא בקוד המריץ.
**שים לב:** קובץ `.env` שלך הועתק ל-worktree (נדרש להרצה; ב-ignore). בשגיאת shell אחת בתחילת העבודה (הרצתי `source .env`) הודפסו לפלט של השיחה הזו כמה ערכים מה-`.env` (מפתחות Supabase/Gemini/Tavily/Azure). זה נשאר בתמלול המקומי של השיחה בלבד; אם התמלולים מסונכרנים או משותפים, שקול לסובב את המפתחות.

## 9. מה צריך מאלעד
1. **התקנת Supabase CLI** (`scoop install supabase` או מהאתר) — לפריסה ול-`config push`.
2. **התקנת PostgreSQL client tools** (`pg_dump`) ואישור להתקין Deno (`pip install deno`, או מ-deno.com) להרצת בדיקות הפונקציות.
3. **מחרוזת חיבור ישירה לייצור** → `SUPABASE_PROD_DB_URL` ב-`.env` (Supabase → Project Settings → Database → Connection string, URI; בחר "Session pooler" אם אין IPv4). אז הגיבוי השבועי יתחיל (בהרצת cleanup של יום ראשון) ואפשר לבדוק dump+שחזור לאמיתי.
4. **סודות לפונקציות** (`supabase secrets set --project-ref <ref> NAME=…`): `SEC_USER_AGENT` (חובה ל-request-company; SEC חוסמת בלי), `SITE_URL`, ואופציונלי: `RESEND_API_KEY`, `EMAIL_FROM`, `GEMINI_SEARCH_KEY` (+ `GEMINI_SEARCH_MODEL`) לחיפוש חכם. בלי המפתחות האחרונים: חיפוש רגיל ובלי מייל — כפי שנקבע.
5. **הגדרות Auth** (סעיף 6), בעיקר: חסימת הרשמה, אימות מייל, סיסמה 10.
6. **הזמנת המנהל הראשון** מהדשבורד (סעיף 2, הערה 2).
7. החלטה: האם משתמשים לא מחוברים שלא מצליחים להיכנס יכולים לפנות (נדחה ל-K7).

## 10. רשימה מוכנה לייצור (לפי הסדר; לא בוצע)
1. מוזג הענף ל-main אחרי השער של ק6ד-2 (ואימות שאין מיגרציה שיוצרת מחדש `v_display_metrics`/`v_fin_*` עם `security_invoker=true`).
2. גיבוי ידני של הייצור לפני: `supabase db dump --data-only` (או pg_dump).
3. הרצת מיגרציות 120100, 120200, 120400, 120500, 120600, 120700, 120800 על הייצור **בסדר הזה**, אחת-אחת; אחרי כל אחת: `VC_DB_TARGET=prod python scripts/vc.py status <טיקר>` (קריאה בלבד) ו-`scripts/security_privileges_check.sql`.
4. אחרי מיגרציה 1 בייצור: לבדוק מי הם המשתמשים הקיימים; המיגרציה מסמנת את כולם `active`.
5. פריסת 14 הפונקציות: `supabase functions deploy <שם> --project-ref zwpftrjryxyymrxsprqh --no-verify-jwt` לכל אחת (portfolio-save, portfolio-delete, watchlist-add, watchlist-remove, broker-import, support-send, profile-update, account-delete, request-company, smart-search, notifications-read, admin-invite, admin-users, admin-tickets). לפרוס מחדש גם ב-test את 9 החסרות ואת request-company.
6. סודות, הגדרות Auth, הזמנת מנהל (סעיפים 6, 9).
7. הרצת `scripts/security_acceptance.py` מול הייצור — **לא** (יוצר משתמשים); להתאים לריצה מצומצמת או להריץ ידנית את 1, 2, 6, 10 עם משתמשי בדיקה זמניים.
8. הפעלת הגיבוי השבועי (`SUPABASE_PROD_DB_URL`), `cleanup.apply: true` לאחר אישור.
9. לפני פתיחה לציבור: Google sign-in, TOTP למנהל, הערת הפרטיות.
