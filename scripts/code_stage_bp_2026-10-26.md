# שלב BP — סבב 2 (תיקונים): רקע מפרופיל עסקי, תרגום ב-Azure, רינדור מתבנית — 2026-10-26

> מסד: **test בלבד**. ייצור לא נגע. מסמך מקור: `docs/ai/ValueCompass_AI_Skills_Other_2026-10-26_10-30.md` (3.1–3.2) + התיקונים שבהודעה שלך. מבנה הדוח כמו בסבב 1.

## 1. סיכום

- **קריאות Gemini בפועל בסבב הזה: 10** מתוך תקרה של 20 (סבב 1: 23 מתוך 25; סה"כ 33). מודל flash-lite בלבד, תהליך אחד, המונה המשותף. BP-1 נשאל שוב **רק על השדות שהפרומפט שלהם השתנה**: `display_name`, `customer_types`, `revenue_models`, `competitors`, `competitor_types` (קריאה אחת לחברה; ל-KO נוספו 2 ניסיונות ל-`display_name`). המגזרים, האזורים והמוצרים מ-XBRL נקראו מחדש בלי מודל.
- **תרגום: Azure Translator** (`TRANSLATION_PROVIDER=azure`, מפתח ואזור מ-`.env`, לא מודפסים; Google נשאר כחלופה בקוד). 95 ביטויים נשלחו בבקשות מרוכזות (עד 25 בבקשה), 42 נשמרו ב-`term_translations` כ-`azure`/`unreviewed`; 22 מונחי מילון (17 המקוריים + accident and health, P&C, A&H ושתי הצורות property and casualty insurance / accident and health insurance) `approved`/`human`.
- **הטקסטים העבריים של כל 7 החברות** מאושרים (`approval_status=approved`) עם `human_reviewed=false` — המשתמש יראה "תרגום אוטומטי" עד שתאשר את הביטויים (`vc.py terms review` / `approve` / `edit`).
- ריצה חוזרת: `render --all` נותן 0 שינויים, ו-BP-1 לא נשאל שוב על אותו `accession` — ראו סעיף 8.

### מה בוצע מההודעה שלך (לפי הסעיפים)

1. **Azure:** מומש (v3, `from=en&to=he`, כמה ביטויים בבקשה, `textType=html` כדי שסימני ההגנה על שמות ומונחים יישמרו). מיגרציה 18 על test הוסיפה `azure` לערכי `source`.
2. **מגזרי XBRL:** נבדקים כל מושגי ההכנסות (`Revenues`, `RevenueFromContract…`, `RevenuesNetOfInterestExpense`, `PremiumsEarnedNet`, `RevenueForReportableSegments`, `SalesRevenueNet` ועוד — כל מושג ששמו כולל Revenue/Premiums), נבחר המושג שסכום הממברים שלו הקרוב ביותר לסך ההכנסות, וגם הקשרים עם `ConsolidationItemsAxis=OperatingSegmentsMember` מתקבלים. כשהממברים חופפים (סכום > 102%) נבחרת הקבוצה הגדולה ביותר שסכומה הוא סך ההכנסות (בגבול 0.5%) — **רק לציר המגזרים**. פירוט לכל חברה בסעיף 5.
3. **`display_name`:** שדה חדש ב-BP-1 (גרסת סקיל 2) עם ציטוט; הקוד מסיר סיומת משפטית (Inc./Corp./Co./Company…) ו-"The" מתחילת השם בתנאי שהשם הקצר עדיין בציטוט; כשל → נופלים לשם מה-EDGAR המנוקה. נשמר בעמודה `display_name` (מיגרציה 18) ומשמש בתבנית.
4. **BP-1:** (א) `revenue_models` רק כשהטקסט מתאר ממה ההכנסות, הראשי ראשון; (ב) נשלחות **כל** פסקאות התחרות של Item 1 (גם של כל מגזר), עד 12,000 תווים; (ג) `customer_types` כולל לקוחות עסקיים/מוסדיים/ממשלתיים כשמוזכרים.
5. **רשימות:** נוסף `revenue_models.investment_income` (הכנסות מהשקעות); `U.S. & Canada` → `north_america`; 22 התוויות ברבים אושרו ו-`active=true`, עם שני התיקונים (ברוקרי ביטוח ונותני שירותי ביטוח; חברות בנייה ויזמות נדל"ן).
6. **מילון:** `accident and health` → "ביטוח תאונות ובריאות" נוסף; `P&C` ו-`A&H` מורחבים (property and casualty / accident and health) לפני התרגום, ונשמרו גם כערכים ישירים `approved`/`human`.
7. **תבנית:** (א) שיעור מוצג רק כשהוא שיעור מההכנסות מ-XBRL — אחרת שם בלי שיעור (וניסוח "ביניהם" במקום "הגדולים שבהם"); (ב) פריט בשם Other / Other Countries / Other Operating Segment לא מוצג ולא נספר; (ג) INCOME_REAL_ESTATE: "Its main property types are…" / "סוגי הנכסים העיקריים"; (ד) אזורים בלי שיעורי XBRL: "It operates in …" / "פועלת ב…".
8. **סיווג UBER:** ראו להלן.

### UBER — סיווג הענף (דיווח בלבד, לא שיניתי)

UBER מסווגת **Software** (פרופיל `TECH_ASSET_LIGHT`) ולכן מופיעה כ"חברה דומה" ל-MSFT. הנימוק בראוטר: ה-SIC שלה, 7389, הוא קוד כללי ("multi") שלא מכריע, ולכן הוחלט לפי **ענף הספק** (`Software - Application` → Software, tier = provider). ההגדרה של "Internet platforms and advertising" כוללת שווקים שמחברים קונים ומוכרים — Uber (נסיעות ומשלוחים) קרובה אליה יותר מאשר לתוכנה. שינוי כזה הוא החלטת ענף (ישפיע על קבוצת העמיתים ועל התוויות), לכן אני מחכה להחלטתך; אם תאשר, התיקון הוא override ענף ל-UBER בראוטר והרצה מחדש של הציון בלבד.

### החלטות ושינויים שאני מבקש שתבדוק

1. **איכות התרגום האוטומטי — כל הביטויים `unreviewed`, ויש שגיאות שאני מבקש שתתקן עם `terms edit`:** "Windows" תורגם "חלונות" (שם מוצר שהוא מילה רגילה); "Concentrate operations" → "פעולות ריכוז" (המילון מכיר "concentrates" ברבים בלבד); ב-JPM "עוסקת בנקאות השקעות … וניהול ניהול נכסים" (ה-"ב" נבלעת ו"ניהול" כפול סביב מונח המילון); שמות מגזרי CB ("Insurance Overseas General" → "אינשורנס אוברסיז ג'נרל", "Life" → "חייו"). הגנה אוטומטית יש לשמות עם אות גדולה באמצע / ראשי תיבות ולמונחי המילון (כסימון מילון של Azure, כדי שהמונח יישמר בתוך הדקדוק); המילה Segment בתחילת/סוף שם מגזר לא מתורגמת. מותר להשאיר שם בלטינית: `terms edit <id> --he "Windows"`.
2. **"הכנסות מהשקעות"** מקבל "מ" פעמיים בעברית ("מהכנסות מהשקעות") — תקין אך כבד; מוכן לשנות את התווית אם תרצה.
3. **שיעורים שמוצגים:** רק שיעורי XBRL מההכנסות. שיעורי מגזרים מהטקסט (למשל אחוזי NPE ב-CB) לא מוצגים; אם מגזר מופיע בלי שיעור, המשפט אומר "ביניהם" ולא "הגדולים שבהם".
4. **שמות מגזרי XBRL** באנגלית באים מה-label של החברה; אם אין (MSFT: אין קובץ `_lab.xml` בפילינג) הם נגזרים משם הממבר ("More Personal Computing"). שם כמו "Segment Insurance North American Commercial P&C" (CB) הוא ה-label של החברה עצמה.
5. **בדיקת 70% מילות תוכן / פועל בגוף שלישי / ממברים מצטברים / סף 60% כיסוי**: כמו בסבב 1 (מאושרות 2 ו-3 לפי הודעתך; 4–6 בעינן).
6. **שיוך `Other Countries`** (אינטל) ל-`other`, לא ל-`outside_us` — כמו בסבב 1.

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
|  | licensing (רישוי ותמלוגים) | ai | The Global Ventures operating segment was established in 2019 primarily to oversee the Company’s ownership of Costa Limited (“Cos… | תקין |
| אזורים | outside_us (מחוץ לארה"ב) 60.1% [Non-US] | xbrl | srt:StatementGeographicalAxis/us-gaap:Revenues | תקין |
|  | us (ארצות הברית) 39.9% [UNITED STATES] | xbrl | srt:StatementGeographicalAxis/us-gaap:Revenues | תקין |
| מתחרים (בשם) | PepsiCo, Inc. | ai | In many of the countries in which we do business, PepsiCo, Inc. is a primary competitor. | תקין |
|  | Nestlé S.A. | ai | Other significant competitors include, but are not limited to, Nestlé S.A., Keurig Dr Pepper Inc., Danone S.A., Suntory Beverage … | תקין |
|  | Keurig Dr Pepper Inc. | ai | Other significant competitors include, but are not limited to, Nestlé S.A., Keurig Dr Pepper Inc., Danone S.A., Suntory Beverage … | תקין |
|  | Danone S.A. | ai | Other significant competitors include, but are not limited to, Nestlé S.A., Keurig Dr Pepper Inc., Danone S.A., Suntory Beverage … | תקין |
|  | Suntory Beverage & Food Limited | ai | Other significant competitors include, but are not limited to, Nestlé S.A., Keurig Dr Pepper Inc., Danone S.A., Suntory Beverage … | תקין |
| סוגי מתחרים | — | ai |  | לא נמצא |

**הטקסט באנגלית** (מאושר, `ai_texts` kind=background, template_version=1, profile_id=1):

> Coca-Cola owns or licenses and markets numerous beverage brands. Its main product lines are Concentrate operations (59% of revenue) and Finished product operations (41%). It sells mainly to consumers, distributors and channel partners and retailers, earning its revenue from product sales and licensing and royalties. It reports 5 segments, the largest being North America Segment (41%), Europe, Middle East, Africa (23%) and Latin America Segment (13%); 60% of revenue comes from outside the United States and 40% from the United States. Revenue in FY2025: $47.9 billion.
>
> Its main competitors include PepsiCo, Inc., Nestlé S.A., Keurig Dr Pepper Inc., Danone S.A. and Suntory Beverage & Food Limited. A clear competitive advantage: brand.

**הטקסט בעברית** — מצב: `stored` / `approved`. להלן תצוגה מקדימה: מקומות שבהם ביטוי עדיין לא מתורגם מסומנים `[ממתין: ...]`; מה ששמור בפועל במסד הוא הגרסה בלי המשפטים האלה.

> חברת Coca-Cola מחזיקה או מעניקה רישיונות ומשווקת מותגי משקאות רבים. קווי המוצרים העיקריים: פעולות ריכוז (59% מההכנסות) ותפעול המוצר הסופי (41%). לקוחותיה הם בעיקר צרכנים, מפיצים ושותפי הפצה וקמעונאים, והכנסותיה ממכירת מוצרים ומרישוי ותמלוגים. היא מדווחת על 5 מגזרים, הגדולים שבהם צפון אמריקה (41%), אירופה, המזרח התיכון, אפריקה (23%) ואמריקה הלטינית (13%); 60% מההכנסות מחוץ לארה"ב ו-40% מארצות הברית. הכנסות ב-FY2025: 47.9 מיליארד $.
>
> בין המתחרים העיקריים: PepsiCo, Inc., Nestlé S.A., Keurig Dr Pepper Inc., Danone S.A. ו-Suntory Beverage & Food Limited. יתרון תחרותי ברור: מותג.

**ביטויים שתורגמו (אנגלית → עברית):** 

| אנגלית | עברית | סוג | מקור/סטטוס |
|---|---|---|---|
| owns or licenses and markets numerous beverage brands | מחזיקה או מעניקה רישיונות ומשווקת מותגי משקאות רבים | core_activity | azure/unreviewed |
| Concentrate operations | פעולות ריכוז | product_line | azure/unreviewed |
| Finished product operations | תפעול המוצר הסופי | product_line | azure/unreviewed |
| North America Segment | צפון אמריקה | segment | azure/unreviewed |
| Europe, Middle East, Africa | אירופה, המזרח התיכון, אפריקה | segment | azure/unreviewed |
| Latin America Segment | אמריקה הלטינית | segment | azure/unreviewed |

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
> It competes with international software companies and internet platforms and advertising companies. Similar companies in ValueCompass: Oracle, Uber Technologies, Salesforce. A clear competitive advantage: scale.

**הטקסט בעברית** — מצב: `stored` / `approved`. להלן תצוגה מקדימה: מקומות שבהם ביטוי עדיין לא מתורגם מסומנים `[ממתין: ...]`; מה ששמור בפועל במסד הוא הגרסה בלי המשפטים האלה.

> חברת Microsoft מפתחת ותומכת בתוכנה, שירותים, מכשירים ופתרונות. קווי המוצרים העיקריים: חלונות, Azure ו-Microsoft 365 קופיילוט; בין המותגים: LinkedIn. לקוחותיה הם בעיקר צרכנים, ארגונים גדולים ועסקים קטנים ובינוניים, והכנסותיה ממכירת מוצרים, ממנויים ומפרסום. היא מדווחת על 3 מגזרים, הגדולים שבהם פרודוקטיביות ותהליכים עסקיים (42%), ענן אינטליגנטי (42%) ומחשוב אישי נוסף (16%); 51% מההכנסות מארצות הברית ו-49% מחוץ לארה"ב. הכנסות ב-FY2026: 331.8 מיליארד $.
>
> מתחרה בחברות תוכנה בינלאומיות ובפלטפורמות אינטרנט וחברות פרסום. חברות דומות ב-ValueCompass: Oracle, Uber Technologies, Salesforce. יתרון תחרותי ברור: יתרון לגודל.

**ביטויים שתורגמו (אנגלית → עברית):** 

| אנגלית | עברית | סוג | מקור/סטטוס |
|---|---|---|---|
| develops and supports software, services, devices, and solutions | מפתחת ותומכת בתוכנה, שירותים, מכשירים ופתרונות | core_activity | azure/unreviewed |
| Windows | חלונות | product_line | azure/unreviewed |
| Azure | Azure | product_line | azure/unreviewed |
| Microsoft 365 Copilot | Microsoft 365 קופיילוט | product_line | azure/unreviewed |
| Productivity and Business Processes | פרודוקטיביות ותהליכים עסקיים | segment | azure/unreviewed |
| Intelligent Cloud | ענן אינטליגנטי | segment | azure/unreviewed |
| More Personal Computing | מחשוב אישי נוסף | segment | azure/unreviewed |

### INTC — INTEL CORP  (FY2025, accession `0000050863-26-000011`, פרופיל #3, מודל `gemini-3.5-flash-lite`, גרסת סקיל 2)

| שדה | ערך | מקור | ציטוט / תגית | סטטוס |
|---|---|---|---|---|
| שם תצוגה | Intel | ai | We aim to build a new Intel for the future | תקין |
| פעילות מרכזית | designs and manufactures semiconductor products | ai | We are a global designer and manufacturer of semiconductor products. | תקין |
| מגזרים | Client Computing Group 61.0% | xbrl | us-gaap:StatementBusinessSegmentsAxis/us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax | תקין |
|  | Datacenter and AI 32.0% | xbrl | us-gaap:StatementBusinessSegmentsAxis/us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax | תקין |
|  | Other Operating Segment 6.7% | xbrl | us-gaap:StatementBusinessSegmentsAxis/us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax | תקין |
| מוצרים ושירותים | CPUs [product_line] | ai | The CPUs and other semiconductor solutions that we design, manufacture, market, sell and service | תקין |
|  | foundry services [service] | ai | we offer third-party foundry services to external customers and aim to establish this business as a leading external foundry. | תקין |
|  | Intel Core Ultra Series 3 processors [brand] | ai | In 2025, we released our initial Intel Core Ultra Series 3 processors, the first products to be manufactured using our new Intel … | תקין |
| סוגי לקוחות | consumers (צרכנים) | ai | utilized globally by consumers, enterprises, governments and educational organizations. | תקין |
|  | enterprises (ארגונים גדולים) | ai | utilized globally by consumers, enterprises, governments and educational organizations. | תקין |
|  | government (ממשלות וגופים ציבוריים) | ai | utilized globally by consumers, enterprises, governments and educational organizations. | תקין |
| מודלי הכנסות | — | ai |  | לא נמצא |
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

> Intel designs and manufactures semiconductor products. Its main product lines are CPUs and foundry services; its brands include Intel Core Ultra Series 3 processors. It sells mainly to consumers, large enterprises and governments and public bodies. It reports 2 segments, the largest being Client Computing Group (61%) and Datacenter and AI (32%); 57% of revenue comes from Asia-Pacific and 30% from the United States. Revenue in FY2025: $52.9 billion.
>
> Its main competitors include AMD, Apple, Qualcomm, MediaTek and NVIDIA. A clear competitive advantage: switching costs.

**הטקסט בעברית** — מצב: `stored` / `approved`. להלן תצוגה מקדימה: מקומות שבהם ביטוי עדיין לא מתורגם מסומנים `[ממתין: ...]`; מה ששמור בפועל במסד הוא הגרסה בלי המשפטים האלה.

> חברת Intel מתכננת ומייצרת מוצרי מוליכים למחצה. קווי המוצרים העיקריים: CPUs ושירותי ייצור שבבים (Foundry); בין המותגים: Intel Core Ultra Series 3 processors. לקוחותיה הם בעיקר צרכנים, ארגונים גדולים וממשלות וגופים ציבוריים. היא מדווחת על 2 מגזרים, הגדולים שבהם קבוצת מחשוב לקוחות (61%) ומרכז נתונים ו- AI (32%); 57% מההכנסות מאסיה-פסיפיק ו-30% מארצות הברית. הכנסות ב-FY2025: 52.9 מיליארד $.
>
> בין המתחרים העיקריים: AMD, Apple, Qualcomm, MediaTek ו-NVIDIA. יתרון תחרותי ברור: עלויות מעבר.

**ביטויים שתורגמו (אנגלית → עברית):** 

| אנגלית | עברית | סוג | מקור/סטטוס |
|---|---|---|---|
| designs and manufactures semiconductor products | מתכננת ומייצרת מוצרי מוליכים למחצה | core_activity | azure/unreviewed |
| CPUs | CPUs | product_line | azure/unreviewed |
| foundry services | שירותי ייצור שבבים (Foundry) | product_line | azure/unreviewed |
| Client Computing Group | קבוצת מחשוב לקוחות | segment | azure/unreviewed |
| Datacenter and AI | מרכז נתונים ו- AI | segment | azure/unreviewed |
| Other Operating Segment | פעילות נוספת | segment | azure/unreviewed |

### JPM — JPMORGAN CHASE & CO  (FY2025, accession `0001628280-26-008131`, פרופיל #4, מודל `gemini-3.5-flash-lite`, גרסת סקיל 2)

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
| מודלי הכנסות | — | ai |  | לא נמצא |
| אזורים | north_america (צפון אמריקה) 76.6% [North America] | xbrl | srt:StatementGeographicalAxis/us-gaap:Revenues | תקין |
|  | europe (אירופה) 13.4% [EMEA] | xbrl | srt:StatementGeographicalAxis/us-gaap:Revenues | תקין |
|  | asia_pacific (אסיה-פסיפיק) 7.7% [Asia Pacific] | xbrl | srt:StatementGeographicalAxis/us-gaap:Revenues | תקין |
|  | latin_america (אמריקה הלטינית) 2.3% [Latin America] | xbrl | srt:StatementGeographicalAxis/us-gaap:Revenues | תקין |
| מתחרים (בשם) | — | ai |  | לא נמצא |
| סוגי מתחרים | banks | ai | Competitors include other banks, brokerage firms, investment banking companies, merchant banks, hedge funds, commodity trading co… | תקין |

**הטקסט באנגלית** (מאושר, `ai_texts` kind=background, template_version=1, profile_id=4):

> JPMorganChase engages in investment banking, financial services, commercial banking, asset management. Its main product lines are investment banking, financial services for consumers and small businesses and commercial banking. It sells mainly to consumers, small and medium-sized businesses and governments and public bodies. It reports 3 segments, the largest being Commercial And Investment Bank (43%), Consumer & Community Banking (42%) and Asset and Wealth Management Segment (13%); 77% of revenue comes from North America and 13% from Europe, and 10% from other regions. Revenue in FY2025: $182.4 billion.
>
> It competes with banks. Similar companies in ValueCompass: Bank of America, Citigroup, Wells Fargo. A clear competitive advantage: scale.

**הטקסט בעברית** — מצב: `stored` / `approved`. להלן תצוגה מקדימה: מקומות שבהם ביטוי עדיין לא מתורגם מסומנים `[ממתין: ...]`; מה ששמור בפועל במסד הוא הגרסה בלי המשפטים האלה.

> חברת JPMorganChase עוסקת בנקאות השקעות, שירותים פיננסיים, בנקאות מסחרית וניהול ניהול נכסים. קווי המוצרים העיקריים: בנקאות השקעות, שירותים פיננסיים לצרכנים ולעסקים קטנים ובנקאות מסחרית. לקוחותיה הם בעיקר צרכנים, עסקים קטנים ובינוניים וממשלות וגופים ציבוריים. היא מדווחת על 3 מגזרים, הגדולים שבהם בנק מסחרי והשקעות (43%), בנקאות צרכנית וקהילתית (42%) וניהול עושר ונכסים (13%); 77% מההכנסות מצפון אמריקה ו-13% מאירופה, ו-10% מאזורים אחרים. הכנסות ב-FY2025: 182.4 מיליארד $.
>
> מתחרה בבנקים. חברות דומות ב-ValueCompass: Bank of America, Citigroup, Wells Fargo. יתרון תחרותי ברור: יתרון לגודל.

**ביטויים שתורגמו (אנגלית → עברית):** 

| אנגלית | עברית | סוג | מקור/סטטוס |
|---|---|---|---|
| engages in investment banking, financial services, commercial banking, asset management | עוסקת בנקאות השקעות, שירותים פיננסיים, בנקאות מסחרית וניהול ניהול נכסים | core_activity | azure/unreviewed |
| investment banking | בנקאות השקעות | product_line | human/approved |
| financial services for consumers and small businesses | שירותים פיננסיים לצרכנים ולעסקים קטנים | product_line | azure/unreviewed |
| commercial banking | בנקאות מסחרית | product_line | azure/unreviewed |
| Commercial And Investment Bank | בנק מסחרי והשקעות | segment | azure/unreviewed |
| Consumer & Community Banking | בנקאות צרכנית וקהילתית | segment | azure/unreviewed |
| Asset and Wealth Management Segment | ניהול עושר ונכסים | segment | azure/unreviewed |

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

> Chubb provides commercial and consumer P&C insurance, A&H, reinsurance, and life insurance. Its main product lines are Property, Liability and Casualty Insurance Product Line (72% of revenue), Accident and Health Insurance Product Line (11%) and Life Insurance Product Line (6.5%). It sells mainly to large enterprises and consumers, earning its revenue from insurance premiums and investment income. It reports 6 segments, the largest being Insurance North American Commercial P&C (34%), Insurance Overseas General (24%) and Life (12%). Revenue in FY2025: $59.2 billion.
>
> It competes with international insurance carriers and banks. Similar companies in ValueCompass: American International, Travelers Companies, Progressive. A clear competitive advantage: scale.

**הטקסט בעברית** — מצב: `stored` / `approved`. להלן תצוגה מקדימה: מקומות שבהם ביטוי עדיין לא מתורגם מסומנים `[ממתין: ...]`; מה ששמור בפועל במסד הוא הגרסה בלי המשפטים האלה.

> חברת Chubb מספקת ביטוח רכוש וחבויות מסחרי וצרכני, ביטוח תאונות ובריאות, ביטוח משנה וביטוח חיים. קווי המוצרים העיקריים: קו מוצרי ביטוח רכוש, אחריות ונזקים (72% מההכנסות), קו מוצרי ביטוח תאונות ובריאות (11%) וקו מוצרי ביטוח חיים (6.5%). לקוחותיה הם בעיקר ארגונים גדולים וצרכנים, והכנסותיה מפרמיות ביטוח ומהכנסות מהשקעות. היא מדווחת על 6 מגזרים, הגדולים שבהם ביטוח ביטוח רכוש וחבויות מסחריות בצפון אמריקה (34%), אינשורנס אוברסיז ג'נרל (24%) וחייו (12%). הכנסות ב-FY2025: 59.2 מיליארד $.
>
> מתחרה בחברות ביטוח בינלאומיות ובבנקים. חברות דומות ב-ValueCompass: American International, Travelers Companies, Progressive. יתרון תחרותי ברור: יתרון לגודל.

**ביטויים שתורגמו (אנגלית → עברית):** 

| אנגלית | עברית | סוג | מקור/סטטוס |
|---|---|---|---|
| provides commercial and consumer P&C insurance, A&H, reinsurance, and life insurance | מספקת ביטוח רכוש וחבויות מסחרי וצרכני, ביטוח תאונות ובריאות, ביטוח משנה וביטוח חיים | core_activity | azure/unreviewed |
| Property, Liability and Casualty Insurance Product Line | קו מוצרי ביטוח רכוש, אחריות ונזקים | product_line | azure/unreviewed |
| Accident and Health Insurance Product Line | קו מוצרי ביטוח תאונות ובריאות | product_line | azure/unreviewed |
| Life Insurance Product Line | קו מוצרי ביטוח חיים | product_line | azure/unreviewed |
| Insurance North American Commercial P&C | ביטוח ביטוח רכוש וחבויות מסחריות בצפון אמריקה | segment | azure/unreviewed |
| Insurance Overseas General | אינשורנס אוברסיז ג'נרל | segment | azure/unreviewed |
| Life | חייו | segment | azure/unreviewed |

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
> It competes with property REITs and income real estate companies. Similar companies in ValueCompass: Simon Property, Public Storage, Prologis. A clear competitive advantage: scale.

**הטקסט בעברית** — מצב: `stored` / `approved`. להלן תצוגה מקדימה: מקומות שבהם ביטוי עדיין לא מתורגם מסומנים `[ממתין: ...]`; מה ששמור בפועל במסד הוא הגרסה בלי המשפטים האלה.

> חברת Realty Income רוכשת, מחזיקה ומנהלת באופן פעיל נכסים מסחריים עצמאיים. סוגי הנכסים העיקריים: קמעונאות (75% מההכנסות) ותעשייתי (15%). לקוחותיה הם בעיקר שוכרים, והכנסותיה מהכנסות שכירות. פועלת בארצות הברית ובאירופה. הכנסות ב-FY2025: 5.7 מיליארד $.
>
> מתחרה בחברות נדל"ן מניב וקרנות ריט. חברות דומות ב-ValueCompass: Simon Property, Public Storage, Prologis. יתרון תחרותי ברור: יתרון לגודל.

**ביטויים שתורגמו (אנגלית → עברית):** 

| אנגלית | עברית | סוג | מקור/סטטוס |
|---|---|---|---|
| acquires, owns, and actively manages freestanding commercial properties | רוכשת, מחזיקה ומנהלת באופן פעיל נכסים מסחריים עצמאיים | core_activity | azure/unreviewed |
| Retail | קמעונאות | product_line | azure/unreviewed |
| Industrial | תעשייתי | product_line | azure/unreviewed |
| Other | אחר | product_line | azure/unreviewed |

### AMT — AMERICAN TOWER CORP /MA/  (FY2025, accession `0001053507-26-000035`, פרופיל #7, מודל `gemini-3.5-flash-lite`, גרסת סקיל 2)

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
| סוגי לקוחות | enterprises (ארגונים גדולים) | ai | leasing of space primarily to enterprises, network operators, cloud providers and supporting service providers. | תקין |
|  | government (ממשלות וגופים ציבוריים) | ai | wireless service providers, radio and television broadcast companies, wireless data providers, government agencies and municipali… | תקין |
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

> American Tower leases space on communications sites to wireless service providers. Its main property types are Property Revenue (97% of revenue) and Service (3.2%). It sells mainly to large enterprises and governments and public bodies, earning its revenue from rental income and services. It reports 5 segments, the largest being Property, US And Canada (52%), Property, Latin America (15%) and Property, Africa & APAC (13%). It operates in Europe and Latin America. Revenue in FY2025: $10.6 billion.
>
> Its main competitors include Crown Castle International Corp., SBA Communications Corporation, Vertical Bridge, Telesites S.A.B. de C.V. and Cellnex Telecom, S.A. A clear competitive advantage: switching costs.

**הטקסט בעברית** — מצב: `stored` / `approved`. להלן תצוגה מקדימה: מקומות שבהם ביטוי עדיין לא מתורגם מסומנים `[ממתין: ...]`; מה ששמור בפועל במסד הוא הגרסה בלי המשפטים האלה.

> חברת American Tower משכירה שטחים באתרי תקשורת לספקי שירותי אלחוט. סוגי הנכסים העיקריים: הכנסות מקרקעין (97% מההכנסות) ושירות (3.2%). לקוחותיה הם בעיקר ארגונים גדולים וממשלות וגופים ציבוריים, והכנסותיה מהכנסות שכירות ומשירותים. היא מדווחת על 5 מגזרים, הגדולים שבהם נדל"ן, US וקנדה (52%), נדל"ן, אמריקה הלטינית (15%) ונדל"ן, אפריקה APAC (13%). פועלת באירופה ובאמריקה הלטינית. הכנסות ב-FY2025: 10.6 מיליארד $.
>
> בין המתחרים העיקריים: Crown Castle International Corp., SBA Communications Corporation, Vertical Bridge, Telesites S.A.B. de C.V. ו-Cellnex Telecom, S.A. יתרון תחרותי ברור: עלויות מעבר.

**ביטויים שתורגמו (אנגלית → עברית):** 

| אנגלית | עברית | סוג | מקור/סטטוס |
|---|---|---|---|
| leases space on communications sites to wireless service providers | משכירה שטחים באתרי תקשורת לספקי שירותי אלחוט | core_activity | azure/unreviewed |
| Property Revenue | הכנסות מקרקעין | product_line | azure/unreviewed |
| Service | שירות | product_line | azure/unreviewed |
| Property, US And Canada | נדל"ן, US וקנדה | segment | azure/unreviewed |
| Property, Latin America | נדל"ן, אמריקה הלטינית | segment | azure/unreviewed |
| Property, Africa & APAC | נדל"ן, אפריקה APAC | segment | azure/unreviewed |

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
| **Gemini — סבב 2 (תקרה 20, נאכפת בקוד)** | **10** |
| Gemini — סה"כ | 33 |
| Azure Translator — ביטויים שנשלחו | 95 (בבקשות של עד 25 ביטויים; תקרה 200) |
| Azure — ביטויים שנשמרו | 42 |
| Google Translate | 0 (חלופה, לא בשימוש) |

ביטויים שנדחו בבדיקות (נשארים "ממתינים" עד תרגום מחדש או תיקון ידני): ראו `translation_failed` ב-`scripts/ai_store/bp_calls.json`; בסבב זה הבדיקות תוקנו (שם/ראשי תיבות שנשארים לטיניים, מונח מילון ארוך) והביטויים שנכשלו תורגמו מחדש. הניסיון החוזר של BP-1 (אחד לכל קריאה, עם הסיבה המדויקת) כלול בספירה.

## 7. מבנה ומסד

- מיגרציה 17 (סבב 1) ומיגרציה 18 (`supabase/migrations/20261026160018_bp_display_name_azure.sql`, rollback ב-`supabase/rollback/`): העמודה `display_name` ב-`company_business_profiles` והערך `azure` ב-`term_translations.source`. על test: md5 של `companies`, `extraction_items`, `ai_assessments`, `financial_facts`, `score_runs` זהה לפני ואחרי (5 מתוך 5); ה-rollback נוסה בבלוק שבוטל והחזיר את המצב.
- RLS ללא שינוי: משתמש מחובר קורא פרופילים, אוצר מילים פעיל ותרגומים; אין לו כתיבה; טקסטים — רק `approved`.
- `business_vocab`: 63 קודים; `sync-vocab` עדכן 22 תוויות/דגלי `active` והוסיף `investment_income`.

## 8. בדיקות ואידמפוטנטיות

- **בדיקות יחידה (בלי רשת, בלי DB אמיתי, בלי מודל):** 765 passed. בסבב הזה נוספו ב-`tests/test_bp_round2.py` ובעדכוני `tests/test_bp.py`: ספק Azure (בקשה אחת למספר ביטויים, מפתח ואזור בכותרות בלבד, תקרת ביטויים, בחירת ספק לפי `TRANSLATION_PROVIDER`), הרחבת P&C / A&H והמילון, `display_name` (הסרת סיומת משפטית), פרומפט v2, כל פסקאות התחרות, `refresh` לשדות נבחרים, שיעור רק מ-XBRL, פריטי Other מוסתרים, סוגי נכסים, "פועלת ב…", עדכוני אוצר המילים ו-`sync`, בחירת מושג ההכנסות לפי הסכום, הקשר OperatingSegmentsMember, מושגי Premiums, בחירת חלוקה בממברים חופפים, ותוויות (הגדרה אינה שם; כמה משאבי label לממבר אחד).
- **אידמפוטנטיות (מסד test, בפועל):** `vc.py render --all` הורץ פעמיים ברצף — בשתי הריצות 0 שינויים בכל 7 החברות. `bp_stage.py recheck` (כל משימת הרקע שוב) לא ביצע אף קריאת Gemini ולא יצר פרופיל חדש; BP-1 לא נשאל שוב על אותו `accession` (בסבב 2 נשאל שוב רק במפורש, על שדות שהפרומפט שלהם השתנה).
- **RLS כ-`authenticated` (בדיקה בפועל, סבב 1; לא שונה):** פרופילים, אוצר מילים פעיל ותרגומים נקראים; `pending_review` / `superseded` / `failed` לא גלויים; כתיבה ל-`term_translations` נדחית.
- **golden:** לא שונה. מיגרציות, מחיקות וכתיבות — test בלבד; ייצור לא נגע. הדוחות וה-cache של SEC: נקראו (תוויות `_lab.xml` נוספו ל-cache).

