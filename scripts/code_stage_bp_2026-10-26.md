# שלב BP — סבב 5: העלאה לייצור (אחרי סבבי התיקונים 1–4) — 2026-10-26

> מסד: **test בלבד**. ייצור לא נגע. בסבב הזה **לא בוצעה אף קריאת Gemini ואף קריאת תרגום** (סה"כ Gemini בכל השלבים: 36).

## 00. תיקון באג: "חברות דומות" בייצור

- **מקור הרשימה (הבאג):** קבצי תוצאות הציון שעל הדיסק (`scripts/output_k6c/results`, שמקורם ב-54 חברות ה-golden), דרך `peer_source.load_records`. הרשימה לא נבדקה מול `companies` של ה-DB, ולכן בייצור (7 חברות בלבד) הופיעו חברות שאינן בו.
- **תיקון:** המועמדים נבחרים רק מ-`companies` של אותו DB (שורות US), באותו פרופיל וענף (כולל `industry_override`), ורק אם יש להם נתון גודל ב-`financial_facts` של אותו DB (סך נכסים לבנקים ולמבטחים, הכנסות לשאר, שנה אחרונה); לחברה עצמה חייב להיות נתון כזה. אין מועמדים — המשפט לא נכתב. בדיקות יחידה: חברה שאינה ב-companies, חברה בלי עובדות, חברה בלי נתון גודל, override, בלי מועמדים.
- **חברה חדשה נטענת:** בסוף כתיבת תוצאת ציון (`exec_score`) מוכנסת לתור משימת רינדור (`ai_background`, skill `render`) לכל חברה באותו פרופיל וענף שכבר יש לה פרופיל עסקי. היא לא צורכת תקציב מודל, לא מתרגמת, ונרשמת פעם אחת בלבד. בדוק ביחידה.
- **נדל"ן — אותו סוג נכס (תוספת):** ב-INCOME_REAL_ESTATE מועמד נבחר רק אם יש לו אותו `asset_type` של מנוע הנדל"ן (למשל `net lease`, `communication towers`, `retail (malls)`; ערך מדויק, מהקלט של המנוע ברשומת התוצאה). חברה בלי סוג נכס, או מועמד בלי סוג — לא נבחרים. בדיקות יחידה: אותו סוג נבחר, סוג אחר לא (AMT מגדלים לעומת O שכירות נטו), חברה בלי סוג, מועמד בלי סוג, מועמד שאינו ב-`companies`, והרשומה של מנוע הנדל"ן נושאת את הסוג.
- **`render --all` בייצור (אחרי התוספת):** **אין משפט "חברות דומות" באף אחת מ-7 החברות — גם לא ב-O** (O היא `net lease`, AMT `communication towers`). רינדור חוזר של O — 0 שינויים.
- **`render --all` ב-test:** ב-test יש 64 חברות עם נתוני גודל (כולל ה-golden שנטענו), ולכן שם המשפט נשאר ב-JPM, CB, MSFT; ב-O הוא נעלם גם שם, כי אין ב-test חברת net lease נוספת. ריצה נוספת — 0 שינויים בכל 7. הערה: בריצות הרינדור המקבילות היו שגיאות רשת חולפות (`WinError 10054`, `getaddrinfo`); כל החברות רונדרו אחר כך ברצף בהצלחה.

## 0. ייצור (אושר על ידך בצ'אט)

**תוצאה:** מיגרציות 17, 18, 19 הוחלו בייצור (`zwpftrjryxyymrxsprqh`), אוצר המילים והתרגומים נטענו, 7 הפרופילים הועתקו מ-test, הטקסטים רונדרו בייצור, וטקסטי D1/T1 הישנים (17) סומנו `superseded`. **0 קריאות Gemini ו-0 קריאות תרגום בייצור.** יש **אי-התאמה אחת** מול test (MSFT) — ראו להלן.

| שלב | תוצאה |
|---|---|
| תיקונים ב-test לפני הייצור | `CPUs` → "מעבדים" (כלל חדש: ראשי תיבות רבים כלליים כמו CPUs/GPUs מתורגמים; AWS נשאר לטיני); `terms approve` לפעילות המרכזית של INTC ו-AMT; נמחקו 18 שורות `term_translations` שלא בשימוש והשלב יצר; נשארו 55 שורות, כולן `approved`; `render --all` ואז ריצה שנייה — 0 שינויים |
| (א) fingerprint | 23 הטבלאות הקיימות — מבנה עמודות, אילוצים, אינדקסים, מדיניות RLS ומצב RLS — **זהים בייצור ובtest** פרט לשינויים של 17–19 (העמודות והאילוצים החדשים ב-`ai_texts`/`companies` והטבלאות החדשות הוצאו מהשוואה). אי-התאמה — אין |
| (ב) מיגרציות | 17 → 18 → 19 לפי הסדר. md5 של `companies`, `ai_assessments`, `extraction_items`, `financial_facts`, `score_runs` ושל עמודות `ai_texts` הישנות **זהה לפני ואחרי** (6 מתוך 6; ב-`companies` בלי שתי העמודות החדשות, שהן NULL). **rollback נוסה בייצור** בבלוק שבוטל (מחיקת העמודות/הטבלאות של 19, 18, 17 לפי הסדר ההפוך): md5 של `companies` ושל `ai_texts` חזר בדיוק למקור, ושלוש הטבלאות נעלמו; אחרי הביטול המיגרציות נשארו מוחלות |
| RLS בייצור כ-`authenticated` | 7 פרופילים, 64 שורות אוצר מילים (כולן פעילות), 55 תרגומים, 14 טקסטי רקע חדשים גלויים; **0** שורות `pending_review` / `superseded` / `failed` גלויות; 0 טקסטי D1/T1 ישנים גלויים; הכנסה ועדכון נדחו |
| (ג) טעינה | `business_vocab`: 64 שורות; `term_translations`: 55 שורות `approved` בלבד (0 `unreviewed` ב-test, ולכן לא הועתק דבר שלא אושר) |
| (ד) 7 החברות | הפרופילים הועתקו מ-test (KO, MSFT, INTC, JPM, CB, O, AMT; אותם `accession`), טקסטים רונדרו בייצור, 17 טקסטי D1/T1 הישנים `superseded` (לא נמחקו) |
| (ה) אימות | 6 מתוך 7 חברות: טקסט אנגלי ועברי **זהים ל-test**, `human_reviewed=true`, `approved`; רינדור שני = 0 שינויים בכל 7; `v_company_status`: 7 חברות `complete`, `background_status=approved`, `background_human_reviewed=true` |

**אי-ההתאמה (MSFT):** משפט "חברות דומות" שונה — בייצור: Oracle, Uber Technologies, Salesforce; ב-test: Oracle, Salesforce, Adobe. הסיבה: UBER קיימת בייצור **רק** כתוצאת golden בקובץ ואינה שורה ב-`companies`, ולכן `industry_override` (שהוא עמודה בשורת החברה) לא קיים בייצור והיא עדיין מסווגת Software. לא יצרתי שורת חברה ל-UBER בייצור (זה היה מוסיף חברה בלי נתונים מחוץ לסט הפיתוח). התיקון יתקיים מעצמו כשתיטען UBER לייצור עם ה-override, או שאוכל להוסיף שורה ריקה עם ה-override אם תאשר. שאר הטקסט של MSFT זהה.

## 1. סיכום סבב 4 (קודם)

- **`scripts/terms_fix_2026-10-26.md` הוחל:** 37 שורות עודכנו ל-`human`/`approved` (שורות שהשם בהן נוקה בסעיף 1 הותאמו לשם המנוקה; "(להשאיר בלטינית)" נשמר כערך באנגלית: Windows, Azure, Microsoft 365 Copilot). `render --all` הורץ; ריצה שנייה — 0 שינויים בכל 7 החברות.
- **שורות שלא נמצאו (2):** (א) `INTC | Intel Core Ultra Series 3 processors (מותג)` — שם מותג אינו ביטוי מתורגם; ביצעתי את ההוראה על הפרופיל עצמו: שם הפריט שונה ל-"Intel Core Ultra" (המקור נשמר ב-`name_original`). (ב) `AMT | Europe (Property, …)` — אין ביטוי כזה בטבלה: הטקסט העברי מתרגם רק 3 מגזרים ראשונים (US and Canada, Latin America, Africa & APAC), "Europe" אינו ביניהם.
- **חפיפה בטבלה:** "Latin America" מופיע ב-KO וב-AMT וגם "Europe, Middle East, Africa" — מפתח הביטוי משותף, ולכן התיקון חל על שתיהן; שורת "Accident and Health Insurance" ושורת "Data Centers" התאימו לשורות המילון הקיימות (אותו תרגום) ולכן לא שינו דבר.
- **ביטויים שנשארו `unreviewed`:** 0 (ראו סעיף 2א, עם התרגום הנוכחי). `human`/`approved`: 53. נותרו 2 שורות `azure` — מהן 0 עדיין לא נסקרו. בטקסט העברי של חברה `human_reviewed=true` רק כשכל הביטויים שבו `approved` (סעיף 2א מציין).
- **interest_income בבנק (סעיף 2 בהודעה):** הקוד מוסיף את `interest_income` כראשון רק כשהכנסות הריבית נטו ≥ 30% מהכנסות הבנק (שניהם מתוצאת הציון, כלומר מ-`financial_facts`); הפריט `source=code`, עם תגית ("financial_facts: net_interest_income / bank revenue = X%") והשיעור. אחרת לא מוסיף, ופריט שהוסף בעבר בקוד ומפר את הכלל מוסר. JPM: הריבית נטו 95.4 מיליארד $ מתוך הכנסות 182.4 מיליארד $ = 52.3% — ולכן נוסף, והוא ראשון. אם המודל כבר החזיר אותו (בלי ציטוט קוד) הוא נשאר כפי שהוא.
- **אזורים מעורבים (סעיף 3):** במפת האזורים נוסף מקטע `multi`: "Africa & APAC" → mea + asia_pacific; "Europe, Middle East & Africa" / EMEA → europe + mea, ועוד כמה צירופים. הפיצול קורה רק לפריט בלי שיעור (שיעור אי אפשר לפצל; ציר XBRL עם שיעור נשאר בקוד אחד, ו-EMEA ב-JPM ממשיך להיות europe). AMT: "פועלת בצפון אמריקה, באמריקה הלטינית, …" — ראו הטקסט.

## 2. 7 חברות סט הפיתוח

### KO — COCA COLA CO  (FY2025, accession `0001628280-26-010047`, פרופיל #1, מודל `gemini-3.5-flash-lite`, גרסת סקיל 2)

| שדה | ערך | מקור | ציטוט / תגית | סטטוס |
|---|---|---|---|---|
| שם תצוגה | Coca-Cola | ai | In this report, the terms “The Coca-Cola Company,” “Company,” “we,” “us” and “our” mean The Coca-Cola Company and all entities in… | תקין |
| פעילות מרכזית | owns or licenses and markets numerous beverage brands | ai | We own or license and market numerous beverage brands | תקין |
| מגזרים | North America Segment 40.8% | xbrl | us-gaap:StatementBusinessSegmentsAxis/us-gaap:RevenueForReportableSegments | תקין |
|  | Europe, Middle East, Africa 22.6% | xbrl | us-gaap:StatementBusinessSegmentsAxis/us-gaap:RevenueForReportableSegments | תקין |
|  | Latin America Segment 13.2% | xbrl | us-gaap:StatementBusinessSegmentsAxis/us-gaap:RevenueForReportableSegments | תקין |
|  | Bottling investments 11.9% | xbrl | us-gaap:StatementBusinessSegmentsAxis/us-gaap:RevenueForReportableSegments | תקין |
|  | A. Pacific 11.1% | xbrl | us-gaap:StatementBusinessSegmentsAxis/us-gaap:RevenueForReportableSegments | תקין |
| מוצרים ושירותים | Concentrate operations [product_line] 59.4% | xbrl | srt:ProductOrServiceAxis/us-gaap:Revenues | תקין |
|  | Finished product operations [product_line] 40.6% | xbrl | srt:ProductOrServiceAxis/us-gaap:Revenues | תקין |
| סוגי לקוחות | consumers (צרכנים) | ai | We believe our success depends on our ability to connect with consumers by providing them with a wide variety of beverage options… | תקין |
|  | distributors (מפיצים ושותפי הפצה) | ai | We make our branded beverage products available to consumers throughout the world through our network of independent bottling par… | תקין |
|  | retailers (קמעונאים) | ai | We make our branded beverage products available to consumers throughout the world through our network of independent bottling par… | תקין |
| מודלי הכנסות | product_sales (מכירת מוצרים) | ai | Our concentrate operations typically generate net operating revenues by selling beverage concentrates, sometimes referred to as “… | תקין |
| אזורים | outside_us (מחוץ לארה"ב) 60.1% [Non-US] | xbrl | srt:StatementGeographicalAxis/us-gaap:Revenues | תקין |
|  | us (ארצות הברית) 39.9% [UNITED STATES] | xbrl | srt:StatementGeographicalAxis/us-gaap:Revenues | תקין |
| מתחרים (בשם) | PepsiCo, Inc. | ai | In many of the countries in which we do business, PepsiCo, Inc. is a primary competitor. | תקין |
|  | Nestlé S.A. | ai | Other significant competitors include, but are not limited to, Nestlé S.A., Keurig Dr Pepper Inc., Danone S.A., Suntory Beverage … | תקין |
|  | Keurig Dr Pepper Inc. | ai | Other significant competitors include, but are not limited to, Nestlé S.A., Keurig Dr Pepper Inc., Danone S.A., Suntory Beverage … | תקין |
|  | Danone S.A. | ai | Other significant competitors include, but are not limited to, Nestlé S.A., Keurig Dr Pepper Inc., Danone S.A., Suntory Beverage … | תקין |
|  | Suntory Beverage & Food Limited | ai | Other significant competitors include, but are not limited to, Nestlé S.A., Keurig Dr Pepper Inc., Danone S.A., Suntory Beverage … | תקין |
| סוגי מתחרים | — | ai |  | לא נמצא |

**הטקסט באנגלית** (מאושר, `ai_texts` kind=background, template_version=1, profile_id=1):

> Coca-Cola owns or licenses and markets numerous beverage brands. Its main product lines are Concentrate operations (59% of revenue) and Finished product operations (41%). It sells mainly to consumers, distributors and channel partners and retailers, earning its revenue from product sales. It reports 5 segments, the largest being North America (41%), Europe, Middle East, Africa (23%) and Latin America (13%); 60% of revenue comes from outside the United States and 40% from the United States. Revenue in FY2025: $47.9 billion.
>
> Its main competitors include PepsiCo, Inc., Nestlé S.A., Keurig Dr Pepper Inc., Danone S.A. and Suntory Beverage & Food Limited. A clear competitive advantage: brand.

**הטקסט בעברית** — מצב: `stored` / `approved`. להלן תצוגה מקדימה: מקומות שבהם ביטוי עדיין לא מתורגם מסומנים `[ממתין: ...]`; מה ששמור בפועל במסד הוא הגרסה בלי המשפטים האלה.

> חברת Coca-Cola מחזיקה ומשווקת מותגי משקאות רבים, בבעלותה או ברישיון. קווי המוצרים העיקריים: פעילות התרכיזים (59% מההכנסות) ופעילות המוצרים המוגמרים (41%). לקוחותיה הם בעיקר צרכנים, מפיצים ושותפי הפצה וקמעונאים, והכנסותיה ממכירת מוצרים. היא מדווחת על 5 מגזרים, הגדולים שבהם צפון אמריקה (41%), אירופה, המזרח התיכון ואפריקה (23%) ואמריקה הלטינית (13%); 60% מההכנסות מחוץ לארה"ב ו-40% מארצות הברית. הכנסות ב-FY2025: 47.9 מיליארד $.
>
> בין המתחרים העיקריים: PepsiCo, Inc., Nestlé S.A., Keurig Dr Pepper Inc., Danone S.A. ו-Suntory Beverage & Food Limited. יתרון תחרותי ברור: מותג.

**ביטויים שתורגמו (אנגלית → עברית):** אין.

| אנגלית | עברית | סוג | מקור/סטטוס |
|---|---|---|---|
| owns or licenses and markets numerous beverage brands | מחזיקה ומשווקת מותגי משקאות רבים, בבעלותה או ברישיון | core_activity | human/approved |
| Concentrate operations | פעילות התרכיזים | product_line | human/approved |
| Finished product operations | פעילות המוצרים המוגמרים | product_line | human/approved |
| North America | צפון אמריקה | segment | human/approved |
| Europe, Middle East, Africa | אירופה, המזרח התיכון ואפריקה | segment | human/approved |
| Latin America | אמריקה הלטינית | segment | human/approved |

### MSFT — MICROSOFT CORP  (FY2026, accession `0001193125-26-323660`, פרופיל #2, מודל `gemini-3.5-flash-lite`, גרסת סקיל 2)

| שדה | ערך | מקור | ציטוט / תגית | סטטוס |
|---|---|---|---|---|
| שם תצוגה | Microsoft | ai | Microsoft is a technology company committed to making digital technology and artificial intelligence (“AI”) available broadly and… | תקין |
| פעילות מרכזית | develops and supports software, services, devices, and solutions | ai | we develop and support software, services, devices, and solutions that deliver new value for customers and help people and busine… | תקין |
| מגזרים | Productivity and Business Processes 42.2% | xbrl | us-gaap:StatementBusinessSegmentsAxis/us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax | תקין |
|  | Intelligent Cloud 41.5% | xbrl | us-gaap:StatementBusinessSegmentsAxis/us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax | תקין |
|  | More Personal Computing 16.3% | xbrl | us-gaap:StatementBusinessSegmentsAxis/us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax | תקין |
| מוצרים ושירותים | Windows [product_line] | ai | Windows faces competition from various software products and from alternative platforms and devices. | תקין |
|  | LinkedIn [brand] | ai | LinkedIn connects the world’s professionals to make them more productive and successful and transforms the way companies hire, ma… | תקין |
|  | Azure [service] | ai | Server products and cloud services, including Azure and other cloud services, comprising cloud and AI consumption-based services | תקין |
|  | Microsoft 365 Copilot [product_line] | ai | Applying AI and ambient intelligence to drive insights, revolutionize many types of work and business processes, and provide subs… | תקין |
|  | GitHub [service] | ai | GitHub cloud services, Health and Life Sciences cloud services (formerly Nuance Healthcare cloud services), virtual desktop offer… | תקין |
| סוגי לקוחות | consumers (צרכנים) | ai | We develop and support a broad portfolio of technology solutions for individuals and businesses, focusing on secure, trusted, and… | תקין |
|  | enterprises (ארגונים גדולים) | ai | For enterprises, digital technology empowers employees, optimizes operations, engages customers, and in some cases, changes the v… | תקין |
|  | smb (עסקים קטנים ובינוניים) | ai | Growth depends on our ability to reach new users in new markets such as frontline workers, small and medium businesses, and growt… | תקין |
| מודלי הכנסות | product_sales (מכירת מוצרים) | ai | Our products include operating systems, server applications, business solution applications, software development tools, desktop … | תקין |
|  | subscriptions (מנויים) | ai | Microsoft 365 Consumer cloud revenue and Office Consumer products revenue is mainly affected by the percentage of customers that … | תקין |
|  | advertising (פרסום) | ai | We also deliver relevant online advertising to a global audience. | תקין |
| אזורים | us (ארצות הברית) 51.5% [US] | xbrl | srt:StatementGeographicalAxis/us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax | תקין |
|  | outside_us (מחוץ לארה"ב) 48.5% [Non Us] | xbrl | srt:StatementGeographicalAxis/us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax | תקין |
| מתחרים (בשם) | — | ai |  | לא נמצא |
| סוגי מתחרים | software / international | ai | Competitors to Office include software and global application vendors, web-based and mobile application companies, AI-first appli… | תקין |
|  | internet_platforms_advertising | ai | LinkedIn faces competition from online professional networks; recruiting, talent management, and human resource services companie… | תקין |

**הטקסט באנגלית** (מאושר, `ai_texts` kind=background, template_version=1, profile_id=2):

> Microsoft develops and supports software, services, devices, and solutions. Its main product lines are Windows, Azure and Microsoft 365 Copilot; its brands include LinkedIn. It sells mainly to consumers, large enterprises and small and medium-sized businesses, earning its revenue from product sales, subscriptions and advertising. It reports 3 segments, the largest being Productivity and Business Processes (42%), Intelligent Cloud (42%) and More Personal Computing (16%); 51% of revenue comes from the United States and 49% from outside the United States. Revenue in FY2026: $331.8 billion.
>
> It competes with international software companies and internet platforms and advertising companies. Similar companies in ValueCompass: Oracle, Salesforce, Adobe. A clear competitive advantage: scale.

**הטקסט בעברית** — מצב: `stored` / `approved`. להלן תצוגה מקדימה: מקומות שבהם ביטוי עדיין לא מתורגם מסומנים `[ממתין: ...]`; מה ששמור בפועל במסד הוא הגרסה בלי המשפטים האלה.

> חברת Microsoft מפתחת ותומכת בתוכנה, בשירותים, במכשירים ובפתרונות. קווי המוצרים העיקריים: Windows, Azure ו-Microsoft 365 Copilot; בין המותגים: LinkedIn. לקוחותיה הם בעיקר צרכנים, ארגונים גדולים ועסקים קטנים ובינוניים, והכנסותיה ממכירת מוצרים, ממנויים ומפרסום. היא מדווחת על 3 מגזרים, הגדולים שבהם פרודוקטיביות ותהליכים עסקיים (42%), ענן חכם (42%) ומחשוב אישי (16%); 51% מההכנסות מארצות הברית ו-49% מחוץ לארה"ב. הכנסות ב-FY2026: 331.8 מיליארד $.
>
> מתחרה בחברות תוכנה בינלאומיות ובפלטפורמות אינטרנט וחברות פרסום. חברות דומות ב-ValueCompass: Oracle, Salesforce, Adobe. יתרון תחרותי ברור: יתרון לגודל.

**ביטויים שתורגמו (אנגלית → עברית):** אין.

| אנגלית | עברית | סוג | מקור/סטטוס |
|---|---|---|---|
| develops and supports software, services, devices, and solutions | מפתחת ותומכת בתוכנה, בשירותים, במכשירים ובפתרונות | core_activity | human/approved |
| Productivity and Business Processes | פרודוקטיביות ותהליכים עסקיים | segment | human/approved |
| Intelligent Cloud | ענן חכם | segment | human/approved |
| More Personal Computing | מחשוב אישי | segment | human/approved |

### INTC — INTEL CORP  (FY2025, accession `0000050863-26-000011`, פרופיל #3, מודל `gemini-3.5-flash-lite`, גרסת סקיל 3)

| שדה | ערך | מקור | ציטוט / תגית | סטטוס |
|---|---|---|---|---|
| שם תצוגה | Intel | ai | We aim to build a new Intel for the future | תקין |
| פעילות מרכזית | designs and manufactures semiconductor products | ai | We are a global designer and manufacturer of semiconductor products. | תקין |
| מגזרים | Client Computing Group 61.0% | xbrl | us-gaap:StatementBusinessSegmentsAxis/us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax | תקין |
|  | Datacenter and AI 32.0% | xbrl | us-gaap:StatementBusinessSegmentsAxis/us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax | תקין |
|  | Other Operating Segment 6.7% | xbrl | us-gaap:StatementBusinessSegmentsAxis/us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax | תקין |
| מוצרים ושירותים | CPUs [product_line] | ai | The CPUs and other semiconductor solutions that we design, manufacture, market, sell and service | תקין |
|  | foundry services [service] | ai | we offer third-party foundry services to external customers and aim to establish this business as a leading external foundry. | תקין |
|  | Intel Core Ultra [brand] | ai | In 2025, we released our initial Intel Core Ultra Series 3 processors, the first products to be manufactured using our new Intel … | תקין |
| סוגי לקוחות | consumers (צרכנים) | ai | utilized globally by consumers, enterprises, governments and educational organizations. | תקין |
|  | enterprises (ארגונים גדולים) | ai | utilized globally by consumers, enterprises, governments and educational organizations. | תקין |
|  | government (ממשלות וגופים ציבוריים) | ai | utilized globally by consumers, enterprises, governments and educational organizations. | תקין |
| מודלי הכנסות | product_sales (מכירת מוצרים) | ai | We are a global designer and manufacturer of semiconductor products. | תקין |
|  | services (שירותים) | ai | In addition to manufacturing our own products, we offer third-party foundry services to external customers and aim to establish t… | תקין |
| אזורים | asia_pacific (אסיה-פסיפיק) 56.6% [China (Including Hong Kong), SINGAPORE, TAIWAN] | xbrl | srt:StatementGeographicalAxis/us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax | תקין |
|  | us (ארצות הברית) 29.8% [UNITED STATES] | xbrl | srt:StatementGeographicalAxis/us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax | תקין |
|  | other (אחר) 13.6% — «Other Countries» | xbrl | srt:StatementGeographicalAxis/us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax | other (מסומן) |
| מתחרים (בשם) | AMD | ai | CCG's primary competitor is AMD, which like us designs processors based on the x86 architecture. | תקין |
|  | Apple | ai | We also face significant competition from companies that design processors based on the ARM architecture, such as Apple with its … | תקין |
|  | Qualcomm | ai | Qualcomm with its Snapdragon products | תקין |
|  | MediaTek | ai | MediaTek with its Kompanio products. | תקין |
|  | NVIDIA | ai | providers of GPU systems such as NVIDIA, whose GPU systems have experienced the highest demand in the market | תקין |
| סוגי מתחרים | — | ai |  | לא נמצא |

**הטקסט באנגלית** (מאושר, `ai_texts` kind=background, template_version=1, profile_id=3):

> Intel designs and manufactures semiconductor products. Its main product lines are CPUs and foundry services; its brands include Intel Core Ultra. It sells mainly to consumers, large enterprises and governments and public bodies, earning its revenue from product sales and services. It reports 2 segments, the largest being Client Computing Group (61%) and Datacenter and AI (32%); 57% of revenue comes from Asia-Pacific and 30% from the United States. Revenue in FY2025: $52.9 billion.
>
> Its main competitors include AMD, Apple, Qualcomm, MediaTek and NVIDIA. A clear competitive advantage: switching costs.

**הטקסט בעברית** — מצב: `stored` / `approved`. להלן תצוגה מקדימה: מקומות שבהם ביטוי עדיין לא מתורגם מסומנים `[ממתין: ...]`; מה ששמור בפועל במסד הוא הגרסה בלי המשפטים האלה.

> חברת Intel מתכננת ומייצרת מוצרי מוליכים למחצה. קווי המוצרים העיקריים: מעבדים ושירותי ייצור שבבים (Foundry); בין המותגים: Intel Core Ultra. לקוחותיה הם בעיקר צרכנים, ארגונים גדולים וממשלות וגופים ציבוריים, והכנסותיה ממכירת מוצרים ומשירותים. היא מדווחת על 2 מגזרים, הגדולים שבהם מחשוב לקוחות (61%) ומרכזי נתונים ובינה מלאכותית (32%); 57% מההכנסות מאסיה-פסיפיק ו-30% מארצות הברית. הכנסות ב-FY2025: 52.9 מיליארד $.
>
> בין המתחרים העיקריים: AMD, Apple, Qualcomm, MediaTek ו-NVIDIA. יתרון תחרותי ברור: עלויות מעבר.

**ביטויים שתורגמו (אנגלית → עברית):** 

| אנגלית | עברית | סוג | מקור/סטטוס |
|---|---|---|---|
| designs and manufactures semiconductor products | מתכננת ומייצרת מוצרי מוליכים למחצה | core_activity | azure/approved |
| CPUs | מעבדים | product_line | human/approved |
| foundry services | שירותי ייצור שבבים (Foundry) | product_line | human/approved |
| Client Computing Group | מחשוב לקוחות | segment | human/approved |
| Datacenter and AI | מרכזי נתונים ובינה מלאכותית | segment | human/approved |

### JPM — JPMORGAN CHASE & CO  (FY2025, accession `0001628280-26-008131`, פרופיל #4, מודל `gemini-3.5-flash-lite`, גרסת סקיל 3)

| שדה | ערך | מקור | ציטוט / תגית | סטטוס |
|---|---|---|---|---|
| שם תצוגה | JPMorganChase | ai | JPMorgan Chase & Co. (“JPMorganChase” or the “Firm”, NYSE: JPM) | תקין |
| פעילות מרכזית | engages in investment banking, financial services, commercial banking, asset management | ai | The Firm is a leader in investment banking, financial services for consumers and small businesses, commercial banking, financial … | תקין |
| מגזרים | Commercial And Investment Bank 43.0% | xbrl | us-gaap:StatementBusinessSegmentsAxis/us-gaap:RevenuesNetOfInterestExpense | תקין |
|  | Consumer & Community Banking 41.7% | xbrl | us-gaap:StatementBusinessSegmentsAxis/us-gaap:RevenuesNetOfInterestExpense | תקין |
|  | Asset and Wealth Management Segment 13.2% | xbrl | us-gaap:StatementBusinessSegmentsAxis/us-gaap:RevenuesNetOfInterestExpense | תקין |
| מוצרים ושירותים | investment banking [service] | ai | investment banking | תקין |
|  | financial services for consumers and small businesses [service] | ai | financial services for consumers and small businesses | תקין |
|  | commercial banking [service] | ai | commercial banking | תקין |
|  | financial transaction processing [service] | ai | financial transaction processing | תקין |
|  | asset management [service] | ai | asset management | תקין |
| סוגי לקוחות | consumers (צרכנים) | ai | financial services for consumers and small businesses | תקין |
|  | smb (עסקים קטנים ובינוניים) | ai | financial services for consumers and small businesses | תקין |
|  | government (ממשלות וגופים ציבוריים) | ai | many of the world’s most prominent corporate, institutional and government clients globally. | תקין |
| מודלי הכנסות | interest_income (הכנסות ריבית) | code | financial_facts: net_interest_income / bank revenue = 52.3% (FY2025, threshold 30%) | תקין |
|  | fees_asset_mgmt (עמלות וניהול נכסים) | ai | The Firm is a leader in investment banking, financial services for consumers and small businesses, commercial banking, financial … | תקין |
| אזורים | north_america (צפון אמריקה) 76.6% [North America] | xbrl | srt:StatementGeographicalAxis/us-gaap:Revenues | תקין |
|  | europe (אירופה) 13.4% [EMEA] | xbrl | srt:StatementGeographicalAxis/us-gaap:Revenues | תקין |
|  | asia_pacific (אסיה-פסיפיק) 7.7% [Asia Pacific] | xbrl | srt:StatementGeographicalAxis/us-gaap:Revenues | תקין |
|  | latin_america (אמריקה הלטינית) 2.3% [Latin America] | xbrl | srt:StatementGeographicalAxis/us-gaap:Revenues | תקין |
| מתחרים (בשם) | — | ai |  | לא נמצא |
| סוגי מתחרים | banks | ai | Competitors include other banks, brokerage firms, investment banking companies, merchant banks, hedge funds, commodity trading co… | תקין |

**הטקסט באנגלית** (מאושר, `ai_texts` kind=background, template_version=1, profile_id=4):

> JPMorganChase engages in investment banking, financial services, commercial banking, asset management. Its main product lines are investment banking, financial services for consumers and small businesses and commercial banking. It sells mainly to consumers, small and medium-sized businesses and governments and public bodies, earning its revenue from interest income and fees and asset management. It reports 3 segments, the largest being Commercial And Investment Bank (43%), Consumer & Community Banking (42%) and Asset and Wealth Management (13%); 77% of revenue comes from North America and 13% from Europe, and 10% from other regions. Revenue in FY2025: $182.4 billion.
>
> It competes with banks. Similar companies in ValueCompass: Bank of America, Citigroup, Wells Fargo. A clear competitive advantage: scale.

**הטקסט בעברית** — מצב: `stored` / `approved`. להלן תצוגה מקדימה: מקומות שבהם ביטוי עדיין לא מתורגם מסומנים `[ממתין: ...]`; מה ששמור בפועל במסד הוא הגרסה בלי המשפטים האלה.

> חברת JPMorganChase עוסקת בבנקאות השקעות, בשירותים פיננסיים, בבנקאות מסחרית ובניהול נכסים. קווי המוצרים העיקריים: בנקאות השקעות, שירותים פיננסיים לצרכנים ולעסקים קטנים ובנקאות מסחרית. לקוחותיה הם בעיקר צרכנים, עסקים קטנים ובינוניים וממשלות וגופים ציבוריים, והכנסותיה מהכנסות ריבית ומעמלות וניהול נכסים. היא מדווחת על 3 מגזרים, הגדולים שבהם בנקאות מסחרית והשקעות (43%), בנקאות צרכנית וקהילתית (42%) וניהול נכסים ועושר (13%); 77% מההכנסות מצפון אמריקה ו-13% מאירופה, ו-10% מאזורים אחרים. הכנסות ב-FY2025: 182.4 מיליארד $.
>
> מתחרה בבנקים. חברות דומות ב-ValueCompass: Bank of America, Citigroup, Wells Fargo. יתרון תחרותי ברור: יתרון לגודל.

**ביטויים שתורגמו (אנגלית → עברית):** אין.

| אנגלית | עברית | סוג | מקור/סטטוס |
|---|---|---|---|
| engages in investment banking, financial services, commercial banking, asset management | עוסקת בבנקאות השקעות, בשירותים פיננסיים, בבנקאות מסחרית ובניהול נכסים | core_activity | human/approved |
| investment banking | בנקאות השקעות | product_line | human/approved |
| financial services for consumers and small businesses | שירותים פיננסיים לצרכנים ולעסקים קטנים | product_line | human/approved |
| commercial banking | בנקאות מסחרית | product_line | human/approved |
| Commercial And Investment Bank | בנקאות מסחרית והשקעות | segment | human/approved |
| Consumer & Community Banking | בנקאות צרכנית וקהילתית | segment | human/approved |
| Asset and Wealth Management | ניהול נכסים ועושר | segment | human/approved |

### CB — Chubb Ltd  (FY2025, accession `0000896159-26-000005`, פרופיל #5, מודל `gemini-3.5-flash-lite`, גרסת סקיל 2)

| שדה | ערך | מקור | ציטוט / תגית | סטטוס |
|---|---|---|---|---|
| שם תצוגה | Chubb | ai | Chubb Limited is the Swiss-incorporated holding company of the Chubb Group of Companies. | תקין |
| פעילות מרכזית | provides commercial and consumer P&C insurance, A&H, reinsurance, and life insurance | ai | Chubb provides commercial and consumer P&C insurance, A&H, reinsurance, and life insurance to a diverse group of clients. | תקין |
| מגזרים | Insurance North American Commercial P&C 34.3% | xbrl | us-gaap:StatementBusinessSegmentsAxis/us-gaap:PremiumsEarnedNet | תקין |
|  | Insurance Overseas General 24.2% | xbrl | us-gaap:StatementBusinessSegmentsAxis/us-gaap:PremiumsEarnedNet | תקין |
|  | Life 12.2% | xbrl | us-gaap:StatementBusinessSegmentsAxis/us-gaap:PremiumsEarnedNet | תקין |
|  | Insurance North American Personal P&C 11.4% | xbrl | us-gaap:StatementBusinessSegmentsAxis/us-gaap:PremiumsEarnedNet | תקין |
|  | Insurance North American Agriculture 4.9% | xbrl | us-gaap:StatementBusinessSegmentsAxis/us-gaap:PremiumsEarnedNet | תקין |
|  | Global Reinsurance 2.3% | xbrl | us-gaap:StatementBusinessSegmentsAxis/us-gaap:PremiumsEarnedNet | תקין |
| מוצרים ושירותים | Property, Liability and Casualty Insurance Product Line [product_line] 71.7% | xbrl | srt:ProductOrServiceAxis/us-gaap:PremiumsEarnedNet | תקין |
|  | Accident and Health Insurance Product Line [product_line] 11.1% | xbrl | srt:ProductOrServiceAxis/us-gaap:PremiumsEarnedNet | תקין |
|  | Life Insurance Product Line [product_line] 6.5% | xbrl | srt:ProductOrServiceAxis/us-gaap:PremiumsEarnedNet | תקין |
| סוגי לקוחות | enterprises (ארגונים גדולים) | ai | We serve multinational corporations, mid-size and small businesses with property and casualty insurance and risk engineering serv… | תקין |
|  | consumers (צרכנים) | ai | affluent and high net worth individuals with substantial assets to protect; individuals purchasing life, personal accident, suppl… | תקין |
|  | other (אחר) — «affinity groups and insurers» | ai | companies and affinity groups providing or offering accident and health insurance programs and life insurance to their employees … | other (מסומן) |
| מודלי הכנסות | insurance_premiums (פרמיות ביטוח) | ai | We generate earnings from three primary sources of income: P&C underwriting income, investment income, and life segment income. | תקין |
|  | investment_income (הכנסות מהשקעות) | ai | We generate earnings from three primary sources of income: P&C underwriting income, investment income, and life segment income. | תקין |
| אזורים | — | ai | axis_not_in_filing | לא נמצא |
| מתחרים (בשם) | — | ai |  | לא נמצא |
| סוגי מתחרים | insurance_carriers / international | ai | Chubb International's primary competitors include U.S.-based companies with global operations, as well as non-U.S. global carrier… | תקין |
|  | banks | ai | For the A&H and personal lines businesses, locally based competitors also include financial institutions and bank owned insurance… | תקין |

**הטקסט באנגלית** (מאושר, `ai_texts` kind=background, template_version=1, profile_id=5):

> Chubb provides commercial and consumer P&C insurance, A&H, reinsurance, and life insurance. Its main product lines are Property, Liability and Casualty Insurance (72% of revenue), Accident and Health Insurance (11%) and Life Insurance (6.5%). It sells mainly to large enterprises and consumers, earning its revenue from insurance premiums and investment income. It reports 6 segments, the largest being North American Commercial P&C (34%), Overseas General (24%) and Life (12%). Revenue in FY2025: $59.2 billion.
>
> It competes with international insurance carriers and banks. Similar companies in ValueCompass: American International, Travelers Companies, Progressive. A clear competitive advantage: scale.

**הטקסט בעברית** — מצב: `stored` / `approved`. להלן תצוגה מקדימה: מקומות שבהם ביטוי עדיין לא מתורגם מסומנים `[ממתין: ...]`; מה ששמור בפועל במסד הוא הגרסה בלי המשפטים האלה.

> חברת Chubb מספקת ביטוח רכוש וחבויות לעסקים ולצרכנים, ביטוח תאונות ובריאות, ביטוח משנה וביטוח חיים. קווי המוצרים העיקריים: ביטוח רכוש וחבויות (72% מההכנסות), ביטוח תאונות ובריאות (11%) וביטוח חיים (6.5%). לקוחותיה הם בעיקר ארגונים גדולים וצרכנים, והכנסותיה מפרמיות ביטוח ומהכנסות מהשקעות. היא מדווחת על 6 מגזרים, הגדולים שבהם ביטוח רכוש וחבויות מסחרי בצפון אמריקה (34%), ביטוח כללי מחוץ לצפון אמריקה (24%) וביטוח חיים (12%). הכנסות ב-FY2025: 59.2 מיליארד $.
>
> מתחרה בחברות ביטוח בינלאומיות ובבנקים. חברות דומות ב-ValueCompass: American International, Travelers Companies, Progressive. יתרון תחרותי ברור: יתרון לגודל.

**ביטויים שתורגמו (אנגלית → עברית):** אין.

| אנגלית | עברית | סוג | מקור/סטטוס |
|---|---|---|---|
| provides commercial and consumer P&C insurance, A&H, reinsurance, and life insurance | מספקת ביטוח רכוש וחבויות לעסקים ולצרכנים, ביטוח תאונות ובריאות, ביטוח משנה וביטוח חיים | core_activity | human/approved |
| Property, Liability and Casualty Insurance | ביטוח רכוש וחבויות | product_line | human/approved |
| Accident and Health Insurance | ביטוח תאונות ובריאות | product_line | human/approved |
| Life Insurance | ביטוח חיים | product_line | human/approved |
| North American Commercial P&C | ביטוח רכוש וחבויות מסחרי בצפון אמריקה | segment | human/approved |
| Overseas General | ביטוח כללי מחוץ לצפון אמריקה | segment | human/approved |
| Life | ביטוח חיים | segment | human/approved |

### O — REALTY INCOME CORP  (FY2025, accession `0000726728-26-000011`, פרופיל #6, מודל `gemini-3.5-flash-lite`, גרסת סקיל 2)

| שדה | ערך | מקור | ציטוט / תגית | סטטוס |
|---|---|---|---|---|
| שם תצוגה | Realty Income | ai | Realty Income (NYSE: O), an S&P 500 company, is real estate partner to the world's leading companies®. | תקין |
| פעילות מרכזית | acquires, owns, and actively manages freestanding commercial properties | ai | Our primary business is the acquisition, ownership, and active management of freestanding commercial properties | תקין |
| מגזרים | — | ai | axis_not_in_filing | לא נמצא |
| מוצרים ושירותים | Retail [product_line] 75.2% | xbrl | srt:ProductOrServiceAxis/us-gaap:Revenues | תקין |
|  | Industrial [product_line] 15.0% | xbrl | srt:ProductOrServiceAxis/us-gaap:Revenues | תקין |
|  | Other [product_line] 4.3% | xbrl | srt:ProductOrServiceAxis/us-gaap:Revenues | תקין |
| סוגי לקוחות | tenants (שוכרים) | ai | Our primary business is the acquisition, ownership, and active management of freestanding commercial properties leased under long… | תקין |
| מודלי הכנסות | rental_income (הכנסות שכירות) | ai | Under a net lease structure, clients are typically responsible for most or all property-level operating expenses, including real … | תקין |
| אזורים | United States → us (ארצות הברית) | ai | portfolio of over 15,500 properties in all 50 states of the United States ("U.S.") | תקין |
|  | United Kingdom → europe (אירופה) | ai | the United Kingdom ("U.K.") | תקין |
|  | Europe → europe (אירופה) | ai | and eight other countries in Europe. | תקין |
| מתחרים (בשם) | — | ai |  | לא נמצא |
| סוגי מתחרים | property_reits | ai | The Company faces competition from other REITs, businesses and other entities in the acquisition, development and operation of fr… | תקין |

**הטקסט באנגלית** (מאושר, `ai_texts` kind=background, template_version=1, profile_id=6):

> Realty Income acquires, owns, and actively manages freestanding commercial properties. Its main property types are Retail (75% of revenue) and Industrial (15%). It sells mainly to tenants, earning its revenue from rental income. It operates in the United States and Europe. Revenue in FY2025: $5.7 billion.
>
> It competes with property REITs and income real estate companies. A clear competitive advantage: scale.

**הטקסט בעברית** — מצב: `stored` / `approved`. להלן תצוגה מקדימה: מקומות שבהם ביטוי עדיין לא מתורגם מסומנים `[ממתין: ...]`; מה ששמור בפועל במסד הוא הגרסה בלי המשפטים האלה.

> חברת Realty Income רוכשת, מחזיקה ומנהלת באופן פעיל נכסים מסחריים עצמאיים. סוגי הנכסים העיקריים: נכסי מסחר קמעונאי (75% מההכנסות) ונכסים תעשייתיים (15%). לקוחותיה הם בעיקר שוכרים, והכנסותיה מהכנסות שכירות. פועלת בארצות הברית ובאירופה. הכנסות ב-FY2025: 5.7 מיליארד $.
>
> מתחרה בחברות נדל"ן מניב וקרנות ריט. יתרון תחרותי ברור: יתרון לגודל.

**ביטויים שתורגמו (אנגלית → עברית):** אין.

| אנגלית | עברית | סוג | מקור/סטטוס |
|---|---|---|---|
| acquires, owns, and actively manages freestanding commercial properties | רוכשת, מחזיקה ומנהלת באופן פעיל נכסים מסחריים עצמאיים | core_activity | human/approved |
| Retail | נכסי מסחר קמעונאי | product_line | human/approved |
| Industrial | נכסים תעשייתיים | product_line | human/approved |

### AMT — AMERICAN TOWER CORP /MA/  (FY2025, accession `0001053507-26-000035`, פרופיל #7, מודל `gemini-3.5-flash-lite`, גרסת סקיל 3)

| שדה | ערך | מקור | ציטוט / תגית | סטטוס |
|---|---|---|---|---|
| שם תצוגה | American Tower | ai | training led by American Tower leaders globally. | תקין |
| פעילות מרכזית | leases space on communications sites to wireless service providers | ai | Our primary business is the leasing of space on communications sites to wireless service providers, radio and television broadcas… | תקין |
| מגזרים | Property, US And Canada 52.5% | xbrl | us-gaap:StatementBusinessSegmentsAxis/us-gaap:Revenues | תקין |
|  | Property, Latin America 15.4% | xbrl | us-gaap:StatementBusinessSegmentsAxis/us-gaap:Revenues | תקין |
|  | Property, Africa & APAC 13.4% | xbrl | us-gaap:StatementBusinessSegmentsAxis/us-gaap:Revenues | תקין |
|  | Property, Data Centers 9.9% | xbrl | us-gaap:StatementBusinessSegmentsAxis/us-gaap:Revenues | תקין |
|  | Property, Europe 8.8% | xbrl | us-gaap:StatementBusinessSegmentsAxis/us-gaap:Revenues | תקין |
| מוצרים ושירותים | Property Revenue [product_line] 96.8% | xbrl | srt:ProductOrServiceAxis/us-gaap:Revenues | תקין |
|  | Service [product_line] 3.2% | xbrl | srt:ProductOrServiceAxis/us-gaap:Revenues | תקין |
| סוגי לקוחות | telecom_operators (ספקי תקשורת) | ai | wireless service providers, radio and television broadcast companies, wireless data providers | תקין |
|  | government (ממשלות וגופים ציבוריים) | ai | government agencies and municipalities | תקין |
|  | enterprises (ארגונים גדולים) | ai | enterprises, network operators, cloud providers and supporting service providers | תקין |
| מודלי הכנסות | rental_income (הכנסות שכירות) | ai | Our revenue is primarily generated from tenant leases. | תקין |
|  | services (שירותים) | ai | We also offer tower-related services in the United States, which we refer to as our services operations. | תקין |
| אזורים | U.S. & Canada → other (אחר) — «U.S. & Canada» | ai | 42,224 communications sites in the U.S. & Canada | other (מסומן) |
|  | Africa & APAC → other (אחר) — «Africa & APAC» | ai | 27,857 communications sites in Africa & APAC | other (מסומן) |
|  | Europe → europe (אירופה) | ai | 32,524 communications sites in Europe | תקין |
|  | Latin America → latin_america (אמריקה הלטינית) | ai | 47,081 communications sites in Latin America | תקין |
| מתחרים (בשם) | Crown Castle International Corp. | ai | other public tower companies, such as Crown Castle International Corp., SBA Communications Corporation, Vertical Bridge, Telesite… | תקין |
|  | SBA Communications Corporation | ai | other public tower companies, such as Crown Castle International Corp., SBA Communications Corporation, Vertical Bridge, Telesite… | תקין |
|  | Vertical Bridge | ai | other public tower companies, such as Crown Castle International Corp., SBA Communications Corporation, Vertical Bridge, Telesite… | תקין |
|  | Telesites S.A.B. de C.V. | ai | other public tower companies, such as Crown Castle International Corp., SBA Communications Corporation, Vertical Bridge, Telesite… | תקין |
|  | Cellnex Telecom, S.A. | ai | other public tower companies, such as Crown Castle International Corp., SBA Communications Corporation, Vertical Bridge, Telesite… | תקין |
| סוגי מתחרים | — | ai |  | לא נמצא |

**הטקסט באנגלית** (מאושר, `ai_texts` kind=background, template_version=1, profile_id=7):

> American Tower leases space on communications sites to wireless service providers. It sells mainly to telecom operators, governments and public bodies and large enterprises, earning its revenue from rental income and services. It reports 5 segments, the largest being US And Canada (52%), Latin America (15%) and Africa & APAC (13%). It operates in North America, the Middle East and Africa, Asia-Pacific, Europe and Latin America. Revenue in FY2025: $10.6 billion.
>
> Its main competitors include Crown Castle International Corp., SBA Communications Corporation, Vertical Bridge, Telesites S.A.B. de C.V. and Cellnex Telecom, S.A. A clear competitive advantage: switching costs.

**הטקסט בעברית** — מצב: `stored` / `approved`. להלן תצוגה מקדימה: מקומות שבהם ביטוי עדיין לא מתורגם מסומנים `[ממתין: ...]`; מה ששמור בפועל במסד הוא הגרסה בלי המשפטים האלה.

> חברת American Tower משכירה שטחים באתרי תקשורת לספקי שירותי אלחוט. לקוחותיה הם בעיקר ספקי תקשורת, ממשלות וגופים ציבוריים וארגונים גדולים, והכנסותיה מהכנסות שכירות ומשירותים. היא מדווחת על 5 מגזרים, הגדולים שבהם ארה"ב וקנדה (52%), אמריקה הלטינית (15%) ואפריקה ואסיה-פסיפיק (13%). פועלת בצפון אמריקה, במזרח התיכון ואפריקה, באסיה-פסיפיק, באירופה ובאמריקה הלטינית. הכנסות ב-FY2025: 10.6 מיליארד $.
>
> בין המתחרים העיקריים: Crown Castle International Corp., SBA Communications Corporation, Vertical Bridge, Telesites S.A.B. de C.V. ו-Cellnex Telecom, S.A. יתרון תחרותי ברור: עלויות מעבר.

**ביטויים שתורגמו (אנגלית → עברית):** 

| אנגלית | עברית | סוג | מקור/סטטוס |
|---|---|---|---|
| leases space on communications sites to wireless service providers | משכירה שטחים באתרי תקשורת לספקי שירותי אלחוט | core_activity | azure/approved |
| US And Canada | ארה"ב וקנדה | segment | human/approved |
| Latin America | אמריקה הלטינית | segment | human/approved |
| Africa & APAC | אפריקה ואסיה-פסיפיק | segment | human/approved |

## 2א. ביטויים שנשארו `unreviewed` — עם התרגום הנוכחי

| # | אנגלית | עברית (נוכחית, Azure) | בשימוש ב |
|---|---|---|---|

`human_reviewed` של הטקסט העברי: KO: כן, MSFT: כן, INTC: כן, JPM: כן, CB: כן, O: כן, AMT: כן. שורות "(לא בשימוש בטקסט)" הן שאריות של שמות לפני הניקוי (Segment, Product Line, "Property, "): הטקסט משתמש עכשיו בשם המנוקה, שתוקן בטבלה; השאריות לא משפיעות על שום טקסט. שני הביטויים היחידים שבשימוש ועדיין לא נסקרו הם פעילות מרכזית של INTC ושל AMT, ולכן הטקסט העברי שלהן `human_reviewed=false`.

## 3. טבלת התוויות ברבים לסוגי המתחרים

**אושרו על ידך וכולן `active=true`** (עם שני התיקונים). "Other" לא נכלל — יש קוד `other` כללי. עמודת המין (ז/נ) קובעת התאמת "ארציים/ארציות" בטקסט.

| קוד | ענף (מהראוטר) | אנגלית ברבים | עברית (מאושרת) | מין | בשימוש ב |
|---|---|---|---|---|---|
| `asset_managers` | Asset managers | asset managers | מנהלי נכסים | ז |  |
| `bdcs_credit_funds` | BDCs and credit funds | BDCs and credit funds | חברות BDC וקרנות אשראי | נ |  |
| `banks` | Banks | banks | בנקים | ז | CB, JPM |
| `communications_equipment` | Communications equipment | communications equipment makers | יצרני ציוד תקשורת | ז |  |
| `consumer_commercial_credit` | Consumer and commercial credit | consumer and commercial credit companies | חברות אשראי לצרכנים ולעסקים | נ |  |
| `electronic_components` | Electronic components | electronic component makers | יצרני רכיבים אלקטרוניים | ז |  |
| `exchanges_data` | Exchanges and data | exchanges and data providers | בורסות וספקי נתונים | נ |  |
| `hardware` | Hardware | hardware makers | יצרני חומרה | ז |  |
| `homebuilders_developers` | Homebuilders and developers | homebuilders and developers | חברות בנייה ויזמות נדל"ן | ז |  |
| `it_services` | IT services | IT services companies | חברות שירותי מחשוב | נ |  |
| `insurance_brokers_services` | Insurance brokers and services | insurance brokers and service providers | ברוקרי ביטוח ונותני שירותי ביטוח | ז |  |
| `insurance_carriers` | Insurance carriers | insurance carriers | חברות ביטוח | נ | CB |
| `internet_platforms_advertising` | Internet platforms and advertising | internet platforms and advertising companies | פלטפורמות אינטרנט וחברות פרסום | נ | MSFT |
| `investment_banks_brokers` | Investment banks and brokers | investment banks and brokers | בנקי השקעות וברוקרים | ז |  |
| `managed_health_insurance` | Managed health insurance | managed health insurers | חברות ביטוח בריאות מנוהל | נ |  |
| `mortgage_reits` | Mortgage REITs | mortgage REITs | קרנות ריט למשכנתאות | נ |  |
| `payments` | Payments | payments companies | חברות תשלומים | נ |  |
| `property_reits` | Property REITs and income real estate | property REITs and income real estate companies | חברות נדל"ן מניב וקרנות ריט | נ | O |
| `spacs_abs` | SPACs and asset-backed issuers | SPACs and asset-backed issuers | חברות SPAC ומנפיקות מגובות נכסים | נ |  |
| `semiconductor_equipment` | Semiconductor equipment | semiconductor equipment makers | יצרני ציוד למוליכים למחצה | ז |  |
| `semiconductors` | Semiconductors | semiconductor makers | יצרני מוליכים למחצה | ז |  |
| `software` | Software | software companies | חברות תוכנה | נ | MSFT |

נוספו ל-`revenue_models`: `investment_income` (הכנסות מהשקעות). מיפוי אזורים: `U.S. & Canada` → `north_america`.

## 4. ערכי `other` שנמצאו

| חברה | שדה | ערך | הטקסט המקורי |
|---|---|---|---|
| INTC | אזורים | other (אחר) 13.6% — «Other Countries» | Other Countries |
| CB | סוגי לקוחות | other (אחר) — «affinity groups and insurers» | affinity groups and insurers |
| AMT | אזורים | U.S. & Canada → other (אחר) — «U.S. & Canada» | U.S. & Canada |
| AMT | אזורים | Africa & APAC → other (אחר) — «Africa & APAC» | Africa & APAC |

כלל ההצעה (אותו `other` ב-3 חברות ומעלה → קוד חדש) לא הופעל — יש 7 חברות בלבד.

## 5. צירי XBRL שנמצאו או חסרו

| חברה | סה"כ הכנסות (XBRL) | תוויות ב-linkbase | מגזרים | מוצרים ושירותים | אזורים |
|---|---|---|---|---|---|
| KO | 47.9 מיליארד $ | 1248 | חסר → BP-1 | נמצא (2 פריטים, כיסוי 100%) | נמצא (2 פריטים, כיסוי 100%) |
| MSFT | 331.8 מיליארד $ | 0 | נמצא (3 פריטים, כיסוי 100%) | נמצא (11 פריטים, כיסוי 169%, 1 הוסרו, members_overlap) | נמצא (2 פריטים, כיסוי 100%) |
| INTC | 52.9 מיליארד $ | 1231 | חסר → BP-1 | חסר → BP-1 | נמצא (5 פריטים, כיסוי 100%) |
| JPM | 182.4 מיליארד $ | 2142 | חסר → BP-1 | חסר → BP-1 | נמצא (4 פריטים, כיסוי 100%, 1 הוסרו) |
| CB | 59.4 מיליארד $ | 1626 | חסר → BP-1 | חסר → BP-1 | חסר → BP-1 |
| O | 5.7 מיליארד $ | 1256 | חסר → BP-1 | נמצא (3 פריטים, כיסוי 95%) | חסר → BP-1 |
| AMT | 10.6 מיליארד $ | 1274 | נמצא (5 פריטים, כיסוי 100%) | נמצא (2 פריטים, כיסוי 100%) | חסר → BP-1 |

"חסר → BP-1" = הציר לא קיים ב-10-K (BP-1 מילא, `source=ai`); דגל `members_overlap` / `low_coverage` = הציר נמצא אך לא שמיש.

### מגזרים מ-XBRL — מה נמצא ב-KO, INTC, JPM, CB (ובשאר)

| חברה | מושג שנבחר (סכום הממברים הקרוב ביותר לסך ההכנסות) | כיסוי | מגזרים (שיעור מההכנסות) | ממברים שהוסרו | הערה |
|---|---|---|---|---|---|
| KO | RevenueForReportableSegments |  | North America Segment (40.8%); Europe, Middle East, Africa (22.6%); Latin America Segment (13.2%); Bottling investments (11.9%); A. Pacific (11.1%) | 0 | לפני התיקון: הציר לא נמצא כלל. הערכים מדווחים בהקשר OperatingSegmentsMember. |
| INTC | RevenueFromContractWithCustomerExcludingAssessedTax |  | Client Computing Group (61.0%); Datacenter and AI (32.0%); Other Operating Segment (6.7%) | 0 | הממברים חופפים (יש גם ממבר-על); נבחרה הקבוצה הגדולה ביותר שסכומה הוא סך ההכנסות — Intel Foundry לא נכנס אליה. |
| JPM | RevenuesNetOfInterestExpense |  | Commercial And Investment Bank (43.0%); Consumer & Community Banking (41.7%); Asset and Wealth Management Segment (13.2%) | 0 | ההפרש מ-100% הוא הכנסות שאינן משויכות לשלושת המגזרים. |
| CB | PremiumsEarnedNet |  | Insurance North American Commercial P&C (34.3%); Insurance Overseas General (24.2%); Life (12.2%); Insurance North American Personal P&C (11.4%); Insurance North American Agriculture (4.9%); Global Reinsurance (2.3%) | 0 | כיסוי 89% — ההפרש הוא הכנסות שאינן במושג שנבחר. |
| MSFT | RevenueFromContractWithCustomerExcludingAssessedTax | 100% | Productivity and Business Processes (42.2%); Intelligent Cloud (41.5%); More Personal Computing (16.3%) | 0 |  |
| O | (מהטקסט, source=ai) |  | — | 0 |  |
| AMT | Revenues | 100% | Property, US And Canada (52.5%); Property, Latin America (15.4%); Property, Africa & APAC (13.4%); Property, Data Centers (9.9%); Property, Europe (8.8%) | 0 |  |

- **KO**: נמצאו 5 מגזרים (North America, Europe/Middle East/Africa, Latin America, Bottling Investments, Asia Pacific) בכיסוי 99.7%.
- **INTC**: נמצאו 3 פריטים לאחר פתרון החפיפה; **JPM**: 3 מגזרים בכיסוי 98%; **CB**: 6 מגזרים בכיסוי 89%.

## 6. קריאות בפועל

| | מספר |
|---|---|
| Gemini — סבב 1 | 23 (מתוך 25) |
| Gemini — סבב 2 | 10 (מתוך 20) |
| Gemini — סבב 3 | 3 (מתוך 20) |
| **Gemini — סבב 4 (זה)** | **0** |
| Gemini — סה"כ | 36 |
| Azure Translator — סבב 4 | 0 |
| Azure — שורות `azure` בטבלה | 2 |
| Google Translate | 0 (חלופה, לא בשימוש) |

## 7. מבנה ומסד

- מיגרציה 19 (`supabase/migrations/20261026190019_companies_industry_override.sql`): `companies.industry_override` + `industry_override_reason` (rollback נוסה). מיגרציה 17 (סבב 1) ומיגרציה 18 (`supabase/migrations/20261026160018_bp_display_name_azure.sql`, rollback ב-`supabase/rollback/`): העמודה `display_name` ב-`company_business_profiles` והערך `azure` ב-`term_translations.source`. על test: md5 של `companies`, `extraction_items`, `ai_assessments`, `financial_facts`, `score_runs` זהה לפני ואחרי (5 מתוך 5); ה-rollback נוסה בבלוק שבוטל והחזיר את המצב.
- RLS ללא שינוי: משתמש מחובר קורא פרופילים, אוצר מילים פעיל ותרגומים; אין לו כתיבה; טקסטים — רק `approved`.
- `business_vocab`: 64 קודים; `sync-vocab` עדכן 22 תוויות/דגלי `active` והוסיף `investment_income`.

## 8. בדיקות ואידמפוטנטיות

- **בדיקות יחידה (בלי רשת, בלי DB אמיתי, בלי מודל):** 784 passed. בסבב 3 נוספו ב-`tests/test_bp_round3.py`: הסרת מילים כלליות משמות (Segment, Product Line, "Property, ", "Insurance " במגזרים בלבד), הסתרת קווי מוצרים כלליים ופריטי Other, שמות מסחריים שנשארים לטיניים ולא נשלחים לתרגום, קוד אזור מהטקסט שנגזר מחדש מהמפה (U.S. & Canada), interest_income ראשון בבנק (ונוסף בקוד כשחסר), כלל הרישוי (ציטוט על הכנסות רישוי), פרומפט גרסה 3 ו-telecom_operators, בדיקה חוזרת שמסירה פריט רישוי בלי ציטוט, פרופיל קיים לא נשאל שוב לכל גרסת סקיל, Override הענף (מהשורה, מנצח את הנתב, נכנס לרשומות העמיתים וקורא מהמאגר), ו-`terms apply-file`.
- **אידמפוטנטיות (מסד test, בפועל):** `vc.py render --all` הורץ פעמיים ברצף — בשתי הריצות 0 שינויים בכל 7 החברות; `bp_stage.py recheck` לא קורא ל-Gemini ולא יוצר פרופילים חדשים. פרופיל קיים של אותו `accession` לא נשאל שוב (נשאל רק במפורש, על שדות נבחרים).
- **מיגרציה 19 על test:** md5 של `companies` זהה אחרי rollback בבלוק שבוטל; ה-md5 של 5 הטבלאות הקיימות נבדק בסבב 2 ולא נגענו בהן.
- **golden:** לא שונה. ייצור לא נגע.
- **סבב 4 (בדיקות חדשות ב-`tests/test_bp_round3.py`; סה"כ 788 passed):** ריבית בבנק לפי כלל 30% (נוסף / לא נוסף / מוסר / חד-פעמי / ערך המודל נשמר ולא משוכפל), פיצול אזורים מעורבים רק בלי שיעור, וטבלת התיקונים עם עמודת חברה, הערות בסוגריים ו"להשאיר בלטינית". `render --all` הורץ פעמיים אחרי התיקונים — 0 שינויים בכל 7 החברות בריצה השנייה.

