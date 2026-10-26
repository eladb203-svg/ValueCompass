# שלב BP — רקע מפרופיל עסקי (XBRL + BP-1), אוצר מילים סגור, תרגום ביטויים, רינדור מתבנית — 2026-10-26

> מסד: **test בלבד**. ייצור לא נגע. החליף את D1/T1 בתור. מסמך מקור: `docs/ai/ValueCompass_AI_Skills_Other_2026-10-26_10-30.md` (3.1–3.2).

## 1. סיכום

- **קריאות Gemini בפועל: 23** מתוך תקרה של 25 לשלב (12 בריצה הראשונה על 7 החברות, 11 בריצות תיקון); מודל flash-lite בלבד, תהליך אחד, המונה המשותף.
- **קריאות Google Translate בפועל: 0.** **חסר `GOOGLE_TRANSLATE_API_KEY` ב-`.env`** (יש שם רק משתני Azure: `TRANSLATION_PROVIDER`, `AZURE_TRANSLATOR_*`). לפי ההנחיה לא השתמשתי במודל במקום, ולא ב-Azure. הטקסט האנגלי נוצר ואושר; **הטקסט העברי של כל 7 החברות מסומן "ממתין לתרגום"** (`state=awaiting_translation`, `approval_status=pending_review`, לא מוצג למשתמשים) — בכל חברה יש לפחות ביטוי אחד בלי תרגום (פעילות מרכזית, שמות קווי מוצרים או שמות מגזרים). מה שמתורגם מהמילון הקיים (17 מונחי `t1_glossary.yaml`, נטענו כ-`approved`/`human`) נמצא, אבל לא מספיק.
- **איך משלימים:** להוסיף את המפתח ל-`.env` ולהריץ `python scripts/vc.py ai-queue` (או `bp_stage.py recheck`); הביטויים יתורגמו (עד 200), יסומנו `unreviewed`, והטקסטים העבריים ירונדרו מחדש. `human_reviewed` יהיה `true` רק אחרי `terms approve`/`terms edit` לכל הביטויים שבטקסט.
- ריצה שנייה לא מבקשת שוב מ-BP-1 (אותו `accession`) ורינדור שני נותן 0 שינויים — ראו סעיף 8.

### החלטות ושינויים שאני מבקש שתבדוק

1. **ספק התרגום:** המסמך (3.2.5) כותב Azure; ההנחיה שלך כותבת Google. פעלתי לפי ההנחיה (Google Cloud Translation v2, מפתח בכותרת הבקשה, לא מודפס). אם תרצה לעדכן את המסמך — לא נגעתי בו.
2. **שמות מגזרים מתורגמים:** ההנחיה מפרטת רק `core_activity` ושמות קווי מוצרים; המסמך (3.2.4–3.2.5) מוסיף שמות מגזרים. עשיתי לפי המסמך ("הם הקובעים") — עד 3 מגזרים, ורק כשיש 2 מגזרים או יותר.
3. **בדיקת "70% ממילות התוכן בציטוט" ב-`core_activity`:** המסמך לא מגדיר התאמת מילים. הגדרתי השוואה לפי גזע + משפחת מילים (designs ~ designer, manages ~ management); בלי זה ביטוי תקין כמו "designs and manufactures semiconductor products" נפסל. הוספתי גם בדיקה שהמילה הראשונה היא פועל בגוף שלישי יחיד ("manufactures", לא "designer" / "develop") — כי הרינדור הוא "חברת X {פעילות}" והתרגום תלוי בזה. זה לא כתוב במסמך.
4. **ציר XBRL שלא משמש:** ציר נחשב "לא שמיש" כשהממברים מכסים פחות מ-60% מההכנסות או חופפים (סכום > 102%) — אז BP-1 משלים (`source=ai`). קרה ב-MSFT (ציר מוצרים חופף).
5. **ממברים מצטברים:** ממבר נפסל אם שמו מצטבר (`Total`, `Corporate and other`, `Eliminations` וכו') או אם הוא שווה לסכום של 2–8 ממברים אחרים (סטייה עד 0.1%, לפחות מיליון).
6. **שיוך אזורים:** "Other Countries" אינו "מחוץ לארה"ב" (באינטל זה מופיע לצד סינגפור וטאיוואן) — מסומן `other` עם הטקסט המקורי. רק Non-US / International / Rest of world / Foreign → `outside_us`.
7. **שדה שנכשל לא נכתב בטקסט** (גם אם נשארו בו פריטים חלקיים בפרופיל). `segments` של KO נכשל (ציטוט של EMEA לא נמצא בטקסט) ולכן אין משפט מגזרים ב-KO.
8. **ניסוח אזורים בעברית:** "מחוץ לארה"ב" לא מקבל "מ" נוספת ("60% מההכנסות מחוץ לארה"ב ו-40% מארצות הברית").
9. **`human_reviewed` באנגלית** נשאר `false` (אין שם ביטויים לסקירה, ואף אחד לא קרא אותו); בעברית `true` רק כשכל הביטויים שבטקסט `approved`.
10. **הכנסות** נלקחות מאותם מספרים שהציון משתמש בהם (ה-result שנבנה מ-`financial_facts`), לא משאילתה נפרדת לטבלה; החפיר מ-A7 (`B3.2-Q5`) ב-`ai_assessments`.
11. **ריצות הרקע (D1/T1) הקודמות:** סומנו `superseded` (לא נמחקו). התור: `ai_background` מריץ עכשיו BP-1 → פרופיל → תרגום → רינדור; קוד D1/T1 נשאר מסומן deprecated.
12. **מקור הדוחות:** הדוחות הם ה-10-K האחרון שב-cache המקומי (MSFT: FY2026, שנה פיסקלית שנגמרת ב-30.6.2026). תוויות החברה (`label linkbase`) נשלפו מ-SEC לכל חברה שיש לה קובץ כזה; ל-MSFT אין קובץ כזה ושמות הממברים נגזרים משמם.

## 2. 7 חברות סט הפיתוח

### KO — COCA COLA CO  (FY2025, accession `0001628280-26-010047`, פרופיל #1, מודל `gemini-3.5-flash-lite`, גרסת סקיל 1)

| שדה | ערך | מקור | ציטוט / תגית | סטטוס |
|---|---|---|---|---|
| פעילות מרכזית | owns or licenses and markets numerous beverage brands | ai | We own or license and market numerous beverage brands | תקין |
| מגזרים | Latin America | ai | •Latin America | נכשל (פריט חלקי, לא נכתב בטקסט): segments/EMEA: quote_not_found |
|  | North America | ai | •North America | נכשל (פריט חלקי, לא נכתב בטקסט): segments/EMEA: quote_not_found |
|  | Asia Pacific | ai | •Asia Pacific | נכשל (פריט חלקי, לא נכתב בטקסט): segments/EMEA: quote_not_found |
|  | Bottling Investments | ai | •Bottling Investments | נכשל (פריט חלקי, לא נכתב בטקסט): segments/EMEA: quote_not_found |
| מוצרים ושירותים | Concentrate operations [product_line] 59.4% | xbrl | srt:ProductOrServiceAxis/us-gaap:Revenues | תקין |
|  | Finished product operations [product_line] 40.6% | xbrl | srt:ProductOrServiceAxis/us-gaap:Revenues | תקין |
| סוגי לקוחות | consumers (צרכנים) | ai | connect with consumers by providing them with a wide variety of beverage options | תקין |
|  | distributors (מפיצים ושותפי הפצה) | ai | network of independent bottling partners, distributors, wholesalers and retailers | תקין |
|  | retailers (קמעונאים) | ai | network of independent bottling partners, distributors, wholesalers and retailers | תקין |
| מודלי הכנסות | product_sales (מכירת מוצרים) | ai | Our concentrate operations typically generate net operating revenues by selling beverage concentrates, sometimes referred to as “… | תקין |
|  | licensing (רישוי ותמלוגים) | ai | We own or license and market numerous beverage brands | תקין |
| אזורים | outside_us (מחוץ לארה"ב) 60.1% [Non-US] | xbrl | srt:StatementGeographicalAxis/us-gaap:Revenues | תקין |
|  | us (ארצות הברית) 39.9% [UNITED STATES] | xbrl | srt:StatementGeographicalAxis/us-gaap:Revenues | תקין |
| מתחרים (בשם) | PepsiCo, Inc. | ai | In many of the countries in which we do business, PepsiCo, Inc. is a primary competitor. | תקין |
|  | Nestlé S.A. | ai | Other significant competitors include, but are not limited to, Nestlé S.A., Keurig Dr Pepper Inc., Danone S.A., Suntory Beverage … | תקין |
|  | Keurig Dr Pepper Inc. | ai | Other significant competitors include, but are not limited to, Nestlé S.A., Keurig Dr Pepper Inc., Danone S.A., Suntory Beverage … | תקין |
|  | Danone S.A. | ai | Other significant competitors include, but are not limited to, Nestlé S.A., Keurig Dr Pepper Inc., Danone S.A., Suntory Beverage … | תקין |
|  | Suntory Beverage & Food Limited | ai | Other significant competitors include, but are not limited to, Nestlé S.A., Keurig Dr Pepper Inc., Danone S.A., Suntory Beverage … | תקין |
| סוגי מתחרים | — | ai |  | לא נמצא |

**הטקסט באנגלית** (מאושר, `ai_texts` kind=background, template_version=1, profile_id=1):

> Coca Cola owns or licenses and markets numerous beverage brands. Its main product lines are Concentrate operations (59% of revenue) and Finished product operations (41%). It sells mainly to consumers, distributors and channel partners and retailers, earning its revenue from product sales and licensing and royalties. 60% of revenue comes from outside the United States and 40% from the United States. Revenue in FY2025: $47.9 billion.
>
> Its main competitors include PepsiCo, Inc., Nestlé S.A., Keurig Dr Pepper Inc., Danone S.A. and Suntory Beverage & Food Limited. A clear competitive advantage: brand.

**הטקסט בעברית** — מצב: `awaiting_translation` / `pending_review` — **ממתין לתרגום** (לא מוצג למשתמשים). להלן תצוגה מקדימה: מקומות שבהם ביטוי עדיין לא מתורגם מסומנים `[ממתין: ...]`; מה ששמור בפועל במסד הוא הגרסה בלי המשפטים האלה.

> חברת Coca Cola [ממתין: owns or licenses and markets numerous beverage brands]. קווי המוצרים העיקריים: [ממתין: Concentrate operations] (59% מההכנסות) ו-[ממתין: Finished product operations] (41%). לקוחותיה הם בעיקר צרכנים, מפיצים ושותפי הפצה וקמעונאים, והכנסותיה ממכירת מוצרים ומרישוי ותמלוגים. 60% מההכנסות מחוץ לארה"ב ו-40% מארצות הברית. הכנסות ב-FY2025: 47.9 מיליארד $.
>
> בין המתחרים העיקריים: PepsiCo, Inc., Nestlé S.A., Keurig Dr Pepper Inc., Danone S.A. ו-Suntory Beverage & Food Limited. יתרון תחרותי ברור: מותג.

**ביטויים שתורגמו (אנגלית → עברית):** אין — לא בוצעה אף קריאה ל-Google (חסר מפתח).

| אנגלית | עברית | סוג | מקור/סטטוס |
|---|---|---|---|
| owns or licenses and markets numerous beverage brands | *ממתין לתרגום* | core_activity |  |
| Concentrate operations | *ממתין לתרגום* | product_line |  |
| Finished product operations | *ממתין לתרגום* | product_line |  |

### MSFT — MICROSOFT CORP  (FY2026, accession `0001193125-26-323660`, פרופיל #2, מודל `gemini-3.5-flash-lite`, גרסת סקיל 1)

| שדה | ערך | מקור | ציטוט / תגית | סטטוס |
|---|---|---|---|---|
| פעילות מרכזית | develops and supports software, services, devices, and solutions | ai | we develop and support software, services, devices, and solutions that deliver new value for customers and help people and busine… | תקין |
| מגזרים | Productivity and Business Processes 42.2% | xbrl | us-gaap:StatementBusinessSegmentsAxis/us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax | תקין |
|  | Intelligent Cloud 41.5% | xbrl | us-gaap:StatementBusinessSegmentsAxis/us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax | תקין |
|  | More Personal Computing 16.3% | xbrl | us-gaap:StatementBusinessSegmentsAxis/us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax | תקין |
| מוצרים ושירותים | Windows [product_line] | ai | Windows faces competition from various software products and from alternative platforms and devices. | תקין |
|  | LinkedIn [brand] | ai | LinkedIn connects the world’s professionals to make them more productive and successful and transforms the way companies hire, ma… | תקין |
|  | Azure [service] | ai | Server products and cloud services, including Azure and other cloud services, comprising cloud and AI consumption-based services | תקין |
|  | Microsoft 365 Copilot [product_line] | ai | Applying AI and ambient intelligence to drive insights, revolutionize many types of work and business processes, and provide subs… | תקין |
|  | GitHub [service] | ai | GitHub cloud services, Health and Life Sciences cloud services (formerly Nuance Healthcare cloud services), virtual desktop offer… | תקין |
| סוגי לקוחות | consumers (צרכנים) | ai | Our mission is to empower every person and every organization on the planet to achieve more. | תקין |
|  | enterprises (ארגונים גדולים) | ai | For enterprises, digital technology empowers employees, optimizes operations, engages customers, and in some cases, changes the v… | תקין |
|  | smb (עסקים קטנים ובינוניים) | ai | Growth depends on our ability to reach new users in new markets such as frontline workers, small and medium businesses | תקין |
| מודלי הכנסות | product_sales (מכירת מוצרים) | ai | We also design and sell devices, including PCs, tablets, gaming and entertainment consoles, other intelligent devices, and relate… | תקין |
|  | subscriptions (מנויים) | ai | Microsoft 365 Consumer cloud revenue and Office Consumer products revenue is mainly affected by the percentage of customers that … | תקין |
|  | advertising (פרסום) | ai | We also deliver relevant online advertising to a global audience. | תקין |
| אזורים | us (ארצות הברית) 51.5% [US] | xbrl | srt:StatementGeographicalAxis/us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax | תקין |
|  | outside_us (מחוץ לארה"ב) 48.5% [Non Us] | xbrl | srt:StatementGeographicalAxis/us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax | תקין |
| מתחרים (בשם) | — | ai |  | לא נמצא |
| סוגי מתחרים | software / international | ai | Competitors to Office include software and global application vendors, web-based and mobile application companies, AI-first appli… | תקין |

**הטקסט באנגלית** (מאושר, `ai_texts` kind=background, template_version=1, profile_id=2):

> Microsoft develops and supports software, services, devices, and solutions. Its main product lines are Windows, Azure and Microsoft 365 Copilot; its brands include LinkedIn. It sells mainly to consumers, large enterprises and small and medium-sized businesses, earning its revenue from product sales, subscriptions and advertising. It reports 3 segments, the largest being Productivity and Business Processes (42%), Intelligent Cloud (42%) and More Personal Computing (16%); 51% of revenue comes from the United States and 49% from outside the United States. Revenue in FY2026: $331.8 billion.
>
> It competes with international software companies. Similar companies in ValueCompass: Oracle, Uber Technologies, Salesforce. A clear competitive advantage: scale.

**הטקסט בעברית** — מצב: `awaiting_translation` / `pending_review` — **ממתין לתרגום** (לא מוצג למשתמשים). להלן תצוגה מקדימה: מקומות שבהם ביטוי עדיין לא מתורגם מסומנים `[ממתין: ...]`; מה ששמור בפועל במסד הוא הגרסה בלי המשפטים האלה.

> חברת Microsoft [ממתין: develops and supports software, services, devices, and solutions]. קווי המוצרים העיקריים: [ממתין: Windows], [ממתין: Azure] ו-[ממתין: Microsoft 365 Copilot]; בין המותגים: LinkedIn. לקוחותיה הם בעיקר צרכנים, ארגונים גדולים ועסקים קטנים ובינוניים, והכנסותיה ממכירת מוצרים, ממנויים ומפרסום. היא מדווחת על 3 מגזרים, הגדולים שבהם [ממתין: Productivity and Business Processes] (42%), [ממתין: Intelligent Cloud] (42%) ו-[ממתין: More Personal Computing] (16%); 51% מההכנסות מארצות הברית ו-49% מחוץ לארה"ב. הכנסות ב-FY2026: 331.8 מיליארד $.
>
> מתחרה בחברות תוכנה בינלאומיות. חברות דומות ב-ValueCompass: Oracle, Uber Technologies, Salesforce. יתרון תחרותי ברור: יתרון לגודל.

**ביטויים שתורגמו (אנגלית → עברית):** אין — לא בוצעה אף קריאה ל-Google (חסר מפתח).

| אנגלית | עברית | סוג | מקור/סטטוס |
|---|---|---|---|
| develops and supports software, services, devices, and solutions | *ממתין לתרגום* | core_activity |  |
| Windows | *ממתין לתרגום* | product_line |  |
| Azure | *ממתין לתרגום* | product_line |  |
| Microsoft 365 Copilot | *ממתין לתרגום* | product_line |  |
| Productivity and Business Processes | *ממתין לתרגום* | segment |  |
| Intelligent Cloud | *ממתין לתרגום* | segment |  |
| More Personal Computing | *ממתין לתרגום* | segment |  |

### INTC — INTEL CORP  (FY2025, accession `0000050863-26-000011`, פרופיל #3, מודל `gemini-3.5-flash-lite`, גרסת סקיל 1)

| שדה | ערך | מקור | ציטוט / תגית | סטטוס |
|---|---|---|---|---|
| פעילות מרכזית | designs and manufactures semiconductor products | ai | We are a global designer and manufacturer of semiconductor products. | תקין |
| מגזרים | Intel Products | ai | Our products are designed and marketed by our Intel Products business, which includes our CCG and DCAI operating segments | תקין |
|  | Intel Foundry | ai | and are manufactured by our Intel Foundry operating segment and third-party suppliers. | תקין |
| מוצרים ושירותים | CPUs [product_line] | ai | The CPUs and other semiconductor solutions that we design, manufacture, market, sell and service | תקין |
|  | foundry services [service] | ai | we offer third-party foundry services to external customers and aim to establish this business as a leading external foundry. | תקין |
|  | Intel Core Ultra Series 3 processors [brand] | ai | In 2025, we released our initial Intel Core Ultra Series 3 processors, the first products to be manufactured using our new Intel … | תקין |
| סוגי לקוחות | consumers (צרכנים) | ai | utilized globally by consumers, enterprises, governments and educational organizations. | תקין |
|  | enterprises (ארגונים גדולים) | ai | utilized globally by consumers, enterprises, governments and educational organizations. | תקין |
|  | government (ממשלות וגופים ציבוריים) | ai | utilized globally by consumers, enterprises, governments and educational organizations. | תקין |
| מודלי הכנסות | product_sales (מכירת מוצרים) | ai | We are a global designer and manufacturer of semiconductor products. | תקין |
|  | services (שירותים) | ai | In addition to manufacturing our own products, we offer third-party foundry services to external customers | תקין |
| אזורים | asia_pacific (אסיה-פסיפיק) 56.6% [China (Including Hong Kong), SINGAPORE, TAIWAN] | xbrl | srt:StatementGeographicalAxis/us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax | תקין |
|  | us (ארצות הברית) 29.8% [UNITED STATES] | xbrl | srt:StatementGeographicalAxis/us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax | תקין |
|  | other (אחר) 13.6% — «Other Countries» | xbrl | srt:StatementGeographicalAxis/us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax | other (מסומן) |
| מתחרים (בשם) | AMD | ai | CCG's primary competitor is AMD, which like us designs processors based on the x86 architecture. | תקין |
|  | Apple | ai | We also face significant competition from companies that design processors based on the ARM architecture, such as Apple with its … | תקין |
|  | Qualcomm | ai | Qualcomm with its Snapdragon products | תקין |
|  | MediaTek | ai | MediaTek with its Kompanio products. | תקין |
| סוגי מתחרים | — | ai |  | לא נמצא |

**הטקסט באנגלית** (מאושר, `ai_texts` kind=background, template_version=1, profile_id=3):

> Intel designs and manufactures semiconductor products. Its main product lines are CPUs and foundry services; its brands include Intel Core Ultra Series 3 processors. It sells mainly to consumers, large enterprises and governments and public bodies, earning its revenue from product sales and services. It reports 2 segments, including Intel Products and Intel Foundry; 57% of revenue comes from Asia-Pacific and 30% from the United States. Revenue in FY2025: $52.9 billion.
>
> Its main competitors include AMD, Apple, Qualcomm and MediaTek. A clear competitive advantage: switching costs.

**הטקסט בעברית** — מצב: `awaiting_translation` / `pending_review` — **ממתין לתרגום** (לא מוצג למשתמשים). להלן תצוגה מקדימה: מקומות שבהם ביטוי עדיין לא מתורגם מסומנים `[ממתין: ...]`; מה ששמור בפועל במסד הוא הגרסה בלי המשפטים האלה.

> חברת Intel [ממתין: designs and manufactures semiconductor products]. קווי המוצרים העיקריים: [ממתין: CPUs] ו-[ממתין: foundry services]; בין המותגים: Intel Core Ultra Series 3 processors. לקוחותיה הם בעיקר צרכנים, ארגונים גדולים וממשלות וגופים ציבוריים, והכנסותיה ממכירת מוצרים ומשירותים. היא מדווחת על 2 מגזרים, ביניהם [ממתין: Intel Products] ו-[ממתין: Intel Foundry]; 57% מההכנסות מאסיה-פסיפיק ו-30% מארצות הברית. הכנסות ב-FY2025: 52.9 מיליארד $.
>
> בין המתחרים העיקריים: AMD, Apple, Qualcomm ו-MediaTek. יתרון תחרותי ברור: עלויות מעבר.

**ביטויים שתורגמו (אנגלית → עברית):** אין — לא בוצעה אף קריאה ל-Google (חסר מפתח).

| אנגלית | עברית | סוג | מקור/סטטוס |
|---|---|---|---|
| designs and manufactures semiconductor products | *ממתין לתרגום* | core_activity |  |
| CPUs | *ממתין לתרגום* | product_line |  |
| foundry services | *ממתין לתרגום* | product_line |  |
| Intel Products | *ממתין לתרגום* | segment |  |
| Intel Foundry | *ממתין לתרגום* | segment |  |

### JPM — JPMORGAN CHASE & CO  (FY2025, accession `0001628280-26-008131`, פרופיל #4, מודל `gemini-3.5-flash-lite`, גרסת סקיל 1)

| שדה | ערך | מקור | ציטוט / תגית | סטטוס |
|---|---|---|---|---|
| פעילות מרכזית | engages in investment banking, financial services, commercial banking, asset management | ai | The Firm is a leader in investment banking, financial services for consumers and small businesses, commercial banking, financial … | תקין |
| מגזרים | Consumer & Community Banking | ai | Consumer & Community Banking (“CCB”) | תקין |
|  | Commercial & Investment Bank | ai | Commercial & Investment Bank (“CIB”) | תקין |
|  | Asset & Wealth Management | ai | Asset & Wealth Management (“AWM”) | תקין |
| מוצרים ושירותים | investment banking [service] | ai | investment banking | תקין |
|  | financial services for consumers and small businesses [service] | ai | financial services for consumers and small businesses | תקין |
|  | commercial banking [service] | ai | commercial banking | תקין |
|  | financial transaction processing [service] | ai | financial transaction processing | תקין |
|  | asset management [service] | ai | asset management | תקין |
| סוגי לקוחות | consumers (צרכנים) | ai | financial services for consumers and small businesses | תקין |
|  | smb (עסקים קטנים ובינוניים) | ai | financial services for consumers and small businesses | תקין |
|  | government (ממשלות וגופים ציבוריים) | ai | corporate, institutional and government clients globally | תקין |
| מודלי הכנסות | fees_asset_mgmt (עמלות וניהול נכסים) | ai | asset management | תקין |
|  | services (שירותים) | ai | financial services for consumers and small businesses | תקין |
|  | interest_income (הכנסות ריבית) | ai | traditional banking products and services | תקין |
| אזורים | north_america (צפון אמריקה) 76.6% [North America] | xbrl | srt:StatementGeographicalAxis/us-gaap:Revenues | תקין |
|  | europe (אירופה) 13.4% [EMEA] | xbrl | srt:StatementGeographicalAxis/us-gaap:Revenues | תקין |
|  | asia_pacific (אסיה-פסיפיק) 7.7% [Asia Pacific] | xbrl | srt:StatementGeographicalAxis/us-gaap:Revenues | תקין |
|  | latin_america (אמריקה הלטינית) 2.3% [Latin America] | xbrl | srt:StatementGeographicalAxis/us-gaap:Revenues | תקין |
| מתחרים (בשם) | — | ai |  | לא נמצא |
| סוגי מתחרים | banks | ai | Competitors include other banks, brokerage firms, investment banking companies, merchant banks | תקין |
|  | investment_banks_brokers | ai | brokerage firms, investment banking companies, merchant banks | תקין |
|  | insurance_carriers | ai | insurance companies, mutual fund companies, investment managers | תקין |
|  | asset_managers | ai | mutual fund companies, investment managers, credit card companies | תקין |

**הטקסט באנגלית** (מאושר, `ai_texts` kind=background, template_version=1, profile_id=4):

> JPMorgan Chase engages in investment banking, financial services, commercial banking, asset management. Its main product lines are investment banking, financial services for consumers and small businesses and commercial banking. It sells mainly to consumers, small and medium-sized businesses and governments and public bodies, earning its revenue from fees and asset management, services and interest income. It reports 3 segments, including Consumer & Community Banking, Commercial & Investment Bank and Asset & Wealth Management; 77% of revenue comes from North America and 13% from Europe, and 10% from other regions. Revenue in FY2025: $182.4 billion.
>
> It competes with banks, investment banks and brokers, insurance carriers and asset managers. Similar companies in ValueCompass: Bank of America, Citigroup, Wells Fargo. A clear competitive advantage: scale.

**הטקסט בעברית** — מצב: `awaiting_translation` / `pending_review` — **ממתין לתרגום** (לא מוצג למשתמשים). להלן תצוגה מקדימה: מקומות שבהם ביטוי עדיין לא מתורגם מסומנים `[ממתין: ...]`; מה ששמור בפועל במסד הוא הגרסה בלי המשפטים האלה.

> חברת JPMorgan Chase [ממתין: engages in investment banking, financial services, commercial banking, asset management]. קווי המוצרים העיקריים: בנקאות השקעות, [ממתין: financial services for consumers and small businesses] ו-[ממתין: commercial banking]. לקוחותיה הם בעיקר צרכנים, עסקים קטנים ובינוניים וממשלות וגופים ציבוריים, והכנסותיה מעמלות וניהול נכסים, משירותים ומהכנסות ריבית. היא מדווחת על 3 מגזרים, ביניהם [ממתין: Consumer & Community Banking], [ממתין: Commercial & Investment Bank] ו-[ממתין: Asset & Wealth Management]; 77% מההכנסות מצפון אמריקה ו-13% מאירופה, ו-10% מאזורים אחרים. הכנסות ב-FY2025: 182.4 מיליארד $.
>
> מתחרה בבנקים, בבנקי השקעות וברוקרים, בחברות ביטוח ובמנהלי נכסים. חברות דומות ב-ValueCompass: Bank of America, Citigroup, Wells Fargo. יתרון תחרותי ברור: יתרון לגודל.

**ביטויים שתורגמו (אנגלית → עברית):** אין — לא בוצעה אף קריאה ל-Google (חסר מפתח).

| אנגלית | עברית | סוג | מקור/סטטוס |
|---|---|---|---|
| engages in investment banking, financial services, commercial banking, asset management | *ממתין לתרגום* | core_activity |  |
| investment banking | בנקאות השקעות | product_line | human/approved |
| financial services for consumers and small businesses | *ממתין לתרגום* | product_line |  |
| commercial banking | *ממתין לתרגום* | product_line |  |
| Consumer & Community Banking | *ממתין לתרגום* | segment |  |
| Commercial & Investment Bank | *ממתין לתרגום* | segment |  |
| Asset & Wealth Management | *ממתין לתרגום* | segment |  |

### CB — Chubb Ltd  (FY2025, accession `0000896159-26-000005`, פרופיל #5, מודל `gemini-3.5-flash-lite`, גרסת סקיל 1)

| שדה | ערך | מקור | ציטוט / תגית | סטטוס |
|---|---|---|---|---|
| פעילות מרכזית | provides commercial and consumer P&C insurance, A&H, reinsurance, and life insurance | ai | Chubb provides commercial and consumer P&C insurance, A&H, reinsurance, and life insurance to a diverse group of clients. | תקין |
| מגזרים | North America Commercial P&C Insurance 38.0% | ai | North America Commercial P&C Insurance (38 percent of 2025 Consolidated NPE) | תקין |
|  | North America Personal P&C Insurance 13.0% | ai | North America Personal P&C Insurance (13 percent of 2025 Consolidated NPE) | תקין |
|  | North America Agricultural Insurance | ai | North America Agricultural Insurance | תקין |
|  | Overseas General Insurance | ai | Overseas General Insurance | תקין |
|  | Global Reinsurance | ai | Global Reinsurance | תקין |
|  | Life Insurance | ai | Life Insurance | תקין |
| מוצרים ושירותים | P&C [product_line] | ai | Chubb provides commercial and consumer P&C insurance, A&H, reinsurance, and life insurance to a diverse group of clients. | תקין |
|  | A&H [product_line] | ai | Chubb provides commercial and consumer P&C insurance, A&H, reinsurance, and life insurance to a diverse group of clients. | תקין |
|  | reinsurance [product_line] | ai | Chubb provides commercial and consumer P&C insurance, A&H, reinsurance, and life insurance to a diverse group of clients. | תקין |
|  | life insurance [product_line] | ai | Chubb provides commercial and consumer P&C insurance, A&H, reinsurance, and life insurance to a diverse group of clients. | תקין |
| סוגי לקוחות | enterprises (ארגונים גדולים) | ai | We serve multinational corporations, mid-size and small businesses with property and casualty insurance and risk engineering serv… | תקין |
|  | consumers (צרכנים) | ai | affluent and high net worth individuals with substantial assets to protect; individuals purchasing life, personal accident, suppl… | תקין |
|  | financial_institutions (מוסדות פיננסיים) | ai | insurers managing exposures with reinsurance coverage. | תקין |
| מודלי הכנסות | insurance_premiums (פרמיות ביטוח) | ai | We generate earnings from three primary sources of income: P&C underwriting income, investment income, and life segment income. | תקין |
|  | interest_income (הכנסות ריבית) | ai | We generate earnings from three primary sources of income: P&C underwriting income, investment income, and life segment income. | תקין |
| אזורים | — | ai | axis_not_in_filing | לא נמצא |
| מתחרים (בשם) | — | ai |  | לא נמצא |
| סוגי מתחרים | insurance_carriers / national | ai | The Commercial Insurance operations compete against numerous insurance companies ranging from large national carriers to small an… | תקין |

**הטקסט באנגלית** (מאושר, `ai_texts` kind=background, template_version=1, profile_id=5):

> Chubb provides commercial and consumer P&C insurance, A&H, reinsurance, and life insurance. Its main product lines are P&C, A&H and reinsurance. It sells mainly to large enterprises, consumers and financial institutions, earning its revenue from insurance premiums and interest income. It reports 6 segments, including North America Commercial P&C Insurance (38%), North America Personal P&C Insurance (13%) and North America Agricultural Insurance. Revenue in FY2025: $59.2 billion.
>
> It competes with national insurance carriers. Similar companies in ValueCompass: American International, Travelers Companies, Progressive. A clear competitive advantage: scale.

**הטקסט בעברית** — מצב: `awaiting_translation` / `pending_review` — **ממתין לתרגום** (לא מוצג למשתמשים). להלן תצוגה מקדימה: מקומות שבהם ביטוי עדיין לא מתורגם מסומנים `[ממתין: ...]`; מה ששמור בפועל במסד הוא הגרסה בלי המשפטים האלה.

> חברת Chubb [ממתין: provides commercial and consumer P&C insurance, A&H, reinsurance, and life insurance]. קווי המוצרים העיקריים: [ממתין: P&C], [ממתין: A&H] וביטוח משנה. לקוחותיה הם בעיקר ארגונים גדולים, צרכנים ומוסדות פיננסיים, והכנסותיה מפרמיות ביטוח ומהכנסות ריבית. היא מדווחת על 6 מגזרים, ביניהם [ממתין: North America Commercial P&C Insurance] (38%), [ממתין: North America Personal P&C Insurance] (13%) ו-[ממתין: North America Agricultural Insurance]. הכנסות ב-FY2025: 59.2 מיליארד $.
>
> מתחרה בחברות ביטוח ארציות. חברות דומות ב-ValueCompass: American International, Travelers Companies, Progressive. יתרון תחרותי ברור: יתרון לגודל.

**ביטויים שתורגמו (אנגלית → עברית):** אין — לא בוצעה אף קריאה ל-Google (חסר מפתח).

| אנגלית | עברית | סוג | מקור/סטטוס |
|---|---|---|---|
| provides commercial and consumer P&C insurance, A&H, reinsurance, and life insurance | *ממתין לתרגום* | core_activity |  |
| P&C | *ממתין לתרגום* | product_line |  |
| A&H | *ממתין לתרגום* | product_line |  |
| reinsurance | ביטוח משנה | product_line | human/approved |
| North America Commercial P&C Insurance | *ממתין לתרגום* | segment |  |
| North America Personal P&C Insurance | *ממתין לתרגום* | segment |  |
| North America Agricultural Insurance | *ממתין לתרגום* | segment |  |

### O — REALTY INCOME CORP  (FY2025, accession `0000726728-26-000011`, פרופיל #6, מודל `gemini-3.5-flash-lite`, גרסת סקיל 1)

| שדה | ערך | מקור | ציטוט / תגית | סטטוס |
|---|---|---|---|---|
| פעילות מרכזית | acquires, owns, and actively manages freestanding commercial properties | ai | Our primary business is the acquisition, ownership, and active management of freestanding commercial properties | תקין |
| מגזרים | — | ai | axis_not_in_filing | לא נמצא |
| מוצרים ושירותים | Retail [product_line] 75.2% | xbrl | srt:ProductOrServiceAxis/us-gaap:Revenues | תקין |
|  | Industrial [product_line] 15.0% | xbrl | srt:ProductOrServiceAxis/us-gaap:Revenues | תקין |
|  | Other [product_line] 4.3% | xbrl | srt:ProductOrServiceAxis/us-gaap:Revenues | תקין |
| סוגי לקוחות | tenants (שוכרים) | ai | leased under long-term net lease agreements to a diversified base of operators, including a blend of investment grade, investment… | תקין |
| מודלי הכנסות | rental_income (הכנסות שכירות) | ai | while we are entitled to receive contractually defined rental payments, many of which include embedded contractual rent escalatio… | תקין |
| אזורים | United States → us (ארצות הברית) | ai | portfolio of over 15,500 properties in all 50 states of the United States ("U.S.") | תקין |
|  | United Kingdom → europe (אירופה) | ai | the United Kingdom ("U.K.") | תקין |
|  | Europe → europe (אירופה) | ai | and eight other countries in Europe. | תקין |
| מתחרים (בשם) | — | ai |  | לא נמצא |
| סוגי מתחרים | property_reits | ai | The Company faces competition from other REITs, businesses and other entities in the acquisition, development and operation of fr… | תקין |

**הטקסט באנגלית** (מאושר, `ai_texts` kind=background, template_version=1, profile_id=6):

> Realty Income acquires, owns, and actively manages freestanding commercial properties. Its main product lines are Retail (75% of revenue), Industrial (15%) and Other (4.3%). It sells mainly to tenants, earning its revenue from rental income. Revenue in FY2025: $5.7 billion.
>
> It competes with property REITs and income real estate companies. Similar companies in ValueCompass: Simon Property, Public Storage, Prologis. A clear competitive advantage: scale.

**הטקסט בעברית** — מצב: `awaiting_translation` / `pending_review` — **ממתין לתרגום** (לא מוצג למשתמשים). להלן תצוגה מקדימה: מקומות שבהם ביטוי עדיין לא מתורגם מסומנים `[ממתין: ...]`; מה ששמור בפועל במסד הוא הגרסה בלי המשפטים האלה.

> חברת Realty Income [ממתין: acquires, owns, and actively manages freestanding commercial properties]. קווי המוצרים העיקריים: [ממתין: Retail] (75% מההכנסות), [ממתין: Industrial] (15%) ו-[ממתין: Other] (4.3%). לקוחותיה הם בעיקר שוכרים, והכנסותיה מהכנסות שכירות. הכנסות ב-FY2025: 5.7 מיליארד $.
>
> מתחרה בחברות נדל"ן מניב וקרנות ריט. חברות דומות ב-ValueCompass: Simon Property, Public Storage, Prologis. יתרון תחרותי ברור: יתרון לגודל.

**ביטויים שתורגמו (אנגלית → עברית):** אין — לא בוצעה אף קריאה ל-Google (חסר מפתח).

| אנגלית | עברית | סוג | מקור/סטטוס |
|---|---|---|---|
| acquires, owns, and actively manages freestanding commercial properties | *ממתין לתרגום* | core_activity |  |
| Retail | *ממתין לתרגום* | product_line |  |
| Industrial | *ממתין לתרגום* | product_line |  |
| Other | *ממתין לתרגום* | product_line |  |

### AMT — AMERICAN TOWER CORP /MA/  (FY2025, accession `0001053507-26-000035`, פרופיל #7, מודל `gemini-3.5-flash-lite`, גרסת סקיל 1)

| שדה | ערך | מקור | ציטוט / תגית | סטטוס |
|---|---|---|---|---|
| פעילות מרכזית | leases space on communications sites to wireless service providers | ai | Our primary business is the leasing of space on communications sites to wireless service providers, radio and television broadcas… | תקין |
| מגזרים | Property, US And Canada 52.5% | xbrl | us-gaap:StatementBusinessSegmentsAxis/us-gaap:Revenues | תקין |
|  | Property, Latin America 15.4% | xbrl | us-gaap:StatementBusinessSegmentsAxis/us-gaap:Revenues | תקין |
|  | Property, Africa & APAC 13.4% | xbrl | us-gaap:StatementBusinessSegmentsAxis/us-gaap:Revenues | תקין |
|  | Property, Data Centers 9.9% | xbrl | us-gaap:StatementBusinessSegmentsAxis/us-gaap:Revenues | תקין |
|  | Property, Europe 8.8% | xbrl | us-gaap:StatementBusinessSegmentsAxis/us-gaap:Revenues | תקין |
| מוצרים ושירותים | Property Revenue [product_line] 96.8% | xbrl | srt:ProductOrServiceAxis/us-gaap:Revenues | תקין |
|  | Service [product_line] 3.2% | xbrl | srt:ProductOrServiceAxis/us-gaap:Revenues | תקין |
| סוגי לקוחות | tenants (שוכרים) | ai | Our customers include our tenants, licensees and other payers. | תקין |
| מודלי הכנסות | rental_income (הכנסות שכירות) | ai | Our revenue is primarily generated from tenant leases. | תקין |
|  | services (שירותים) | ai | We also offer tower-related services in the United States, which we refer to as our services operations. | תקין |
| אזורים | U.S. & Canada → other (אחר) — «U.S. & Canada» | ai | 42,224 communications sites in the U.S. & Canada | other (מסומן) |
|  | Africa & APAC → other (אחר) — «Africa & APAC» | ai | 27,857 communications sites in Africa & APAC | other (מסומן) |
|  | Europe → europe (אירופה) | ai | 32,524 communications sites in Europe | תקין |
|  | Latin America → latin_america (אמריקה הלטינית) | ai | 47,081 communications sites in Latin America | תקין |
| מתחרים (בשם) | Crown Castle International Corp. | ai | We compete, both for new business and for the acquisition of assets, with other public tower companies, such as Crown Castle Inte… | תקין |
|  | SBA Communications Corporation | ai | SBA Communications Corporation | תקין |
|  | Vertical Bridge | ai | Vertical Bridge | תקין |
|  | Telesites S.A.B. de C.V. | ai | Telesites S.A.B. de C.V. | תקין |
|  | Cellnex Telecom, S.A. | ai | Cellnex Telecom, S.A. | תקין |
| סוגי מתחרים | — | ai |  | לא נמצא |

**הטקסט באנגלית** (מאושר, `ai_texts` kind=background, template_version=1, profile_id=7):

> American Tower leases space on communications sites to wireless service providers. Its main product lines are Property Revenue (97% of revenue) and Service (3.2%). It sells mainly to tenants, earning its revenue from rental income and services. It reports 5 segments, the largest being Property, US And Canada (52%), Property, Latin America (15%) and Property, Africa & APAC (13%). Revenue in FY2025: $10.6 billion.
>
> Its main competitors include Crown Castle International Corp., SBA Communications Corporation, Vertical Bridge, Telesites S.A.B. de C.V. and Cellnex Telecom, S.A. A clear competitive advantage: switching costs.

**הטקסט בעברית** — מצב: `awaiting_translation` / `pending_review` — **ממתין לתרגום** (לא מוצג למשתמשים). להלן תצוגה מקדימה: מקומות שבהם ביטוי עדיין לא מתורגם מסומנים `[ממתין: ...]`; מה ששמור בפועל במסד הוא הגרסה בלי המשפטים האלה.

> חברת American Tower [ממתין: leases space on communications sites to wireless service providers]. קווי המוצרים העיקריים: [ממתין: Property Revenue] (97% מההכנסות) ו-[ממתין: Service] (3.2%). לקוחותיה הם בעיקר שוכרים, והכנסותיה מהכנסות שכירות ומשירותים. היא מדווחת על 5 מגזרים, הגדולים שבהם [ממתין: Property, US And Canada] (52%), [ממתין: Property, Latin America] (15%) ו-[ממתין: Property, Africa & APAC] (13%). הכנסות ב-FY2025: 10.6 מיליארד $.
>
> בין המתחרים העיקריים: Crown Castle International Corp., SBA Communications Corporation, Vertical Bridge, Telesites S.A.B. de C.V. ו-Cellnex Telecom, S.A. יתרון תחרותי ברור: עלויות מעבר.

**ביטויים שתורגמו (אנגלית → עברית):** אין — לא בוצעה אף קריאה ל-Google (חסר מפתח).

| אנגלית | עברית | סוג | מקור/סטטוס |
|---|---|---|---|
| leases space on communications sites to wireless service providers | *ממתין לתרגום* | core_activity |  |
| Property Revenue | *ממתין לתרגום* | product_line |  |
| Service | *ממתין לתרגום* | product_line |  |
| Property, US And Canada | *ממתין לתרגום* | segment |  |
| Property, Latin America | *ממתין לתרגום* | segment |  |
| Property, Africa & APAC | *ממתין לתרגום* | segment |  |

## 3. טבלת התוויות ברבים לסוגי המתחרים — לסקירה שלך

כל הענפים של ValueCompass (21 ענפים; "Other" לא נכלל — יש קוד `other` כללי). **`active=false` עד שתאשר.** אנא תקן את העברית בעמודה "הצעה" ואת המין (ז/נ — קובע התאמה של "ארציים/ארציות").

| קוד | ענף (מהראוטר) | אנגלית ברבים | הצעה בעברית | מין | בשימוש ב |
|---|---|---|---|---|---|
| `asset_managers` | Asset managers | asset managers | מנהלי נכסים | ז | JPM |
| `bdcs_credit_funds` | BDCs and credit funds | BDCs and credit funds | חברות BDC וקרנות אשראי | נ |  |
| `banks` | Banks | banks | בנקים | ז | JPM |
| `communications_equipment` | Communications equipment | communications equipment makers | יצרני ציוד תקשורת | ז |  |
| `consumer_commercial_credit` | Consumer and commercial credit | consumer and commercial credit companies | חברות אשראי לצרכנים ולעסקים | נ |  |
| `electronic_components` | Electronic components | electronic component makers | יצרני רכיבים אלקטרוניים | ז |  |
| `exchanges_data` | Exchanges and data | exchanges and data providers | בורסות וספקי נתונים | נ |  |
| `hardware` | Hardware | hardware makers | יצרני חומרה | ז |  |
| `homebuilders_developers` | Homebuilders and developers | homebuilders and developers | בוני בתים ויזמי נדל"ן | ז |  |
| `it_services` | IT services | IT services companies | חברות שירותי מחשוב | נ |  |
| `insurance_brokers_services` | Insurance brokers and services | insurance brokers and service providers | מתווכי ביטוח וספקי שירותי ביטוח | ז |  |
| `insurance_carriers` | Insurance carriers | insurance carriers | חברות ביטוח | נ | CB, JPM |
| `internet_platforms_advertising` | Internet platforms and advertising | internet platforms and advertising companies | פלטפורמות אינטרנט וחברות פרסום | נ |  |
| `investment_banks_brokers` | Investment banks and brokers | investment banks and brokers | בנקי השקעות וברוקרים | ז | JPM |
| `managed_health_insurance` | Managed health insurance | managed health insurers | חברות ביטוח בריאות מנוהל | נ |  |
| `mortgage_reits` | Mortgage REITs | mortgage REITs | קרנות ריט למשכנתאות | נ |  |
| `payments` | Payments | payments companies | חברות תשלומים | נ |  |
| `property_reits` | Property REITs and income real estate | property REITs and income real estate companies | חברות נדל"ן מניב וקרנות ריט | נ | O |
| `spacs_abs` | SPACs and asset-backed issuers | SPACs and asset-backed issuers | חברות SPAC ומנפיקות מגובות נכסים | נ |  |
| `semiconductor_equipment` | Semiconductor equipment | semiconductor equipment makers | יצרני ציוד למוליכים למחצה | ז |  |
| `semiconductors` | Semiconductors | semiconductor makers | יצרני מוליכים למחצה | ז |  |
| `software` | Software | software companies | חברות תוכנה | נ | MSFT |

תחומי הפעולה (scope) והסוגים הכלליים נטענו `active=true` כפי שכתבת: `local`, `regional`, `national`, `international`, `private_companies`, `private_label`, `startups`, `government_entities`, `other`.

## 4. ערכי `other` שנמצאו

| חברה | שדה | ערך | הטקסט המקורי |
|---|---|---|---|
| INTC | אזורים | other (אחר) 13.6% — «Other Countries» | Other Countries |
| AMT | אזורים | U.S. & Canada → other (אחר) — «U.S. & Canada» | U.S. & Canada |
| AMT | אזורים | Africa & APAC → other (אחר) — «Africa & APAC» | Africa & APAC |

כלל ההצעה (אותו `other` ב-3 חברות ומעלה → קוד חדש) לא הופעל — יש 7 חברות בלבד.

## 5. צירי XBRL שנמצאו או חסרו

| חברה | סה"כ הכנסות (XBRL) | תוויות ב-linkbase | מגזרים | מוצרים ושירותים | אזורים |
|---|---|---|---|---|---|
| KO | 47.9 מיליארד $ | 1248 | חסר → BP-1 | נמצא (2 פריטים, כיסוי 100%) | נמצא (2 פריטים, כיסוי 100%) |
| MSFT | 331.8 מיליארד $ | 0 | נמצא (3 פריטים, כיסוי 100%) | נמצא (11 פריטים, כיסוי 169%, 1 מצטברים הוסרו, members_overlap) | נמצא (2 פריטים, כיסוי 100%) |
| INTC | 52.9 מיליארד $ | 1231 | חסר → BP-1 | חסר → BP-1 | נמצא (5 פריטים, כיסוי 100%) |
| JPM | 182.4 מיליארד $ | 2142 | חסר → BP-1 | חסר → BP-1 | נמצא (4 פריטים, כיסוי 100%, 1 מצטברים הוסרו) |
| CB | 59.4 מיליארד $ | 1626 | חסר → BP-1 | חסר → BP-1 | חסר → BP-1 |
| O | 5.7 מיליארד $ | 1256 | חסר → BP-1 | נמצא (3 פריטים, כיסוי 95%) | חסר → BP-1 |
| AMT | 10.6 מיליארד $ | 1274 | נמצא (5 פריטים, כיסוי 100%) | נמצא (2 פריטים, כיסוי 100%) | חסר → BP-1 |

"חסר → BP-1" = הציר לא קיים ב-10-K; "נמצא" עם דגל `members_overlap` / `low_coverage` = לא שמיש, BP-1 השלים (`source=ai`).

## 6. קריאות בפועל

| | מספר |
|---|---|
| Gemini — ריצה ראשונה (7 חברות) | 12 |
| Gemini — תיקון שדות שנכשלו (`refresh`) | 11 |
| **Gemini — סה"כ (תקרה 25, נאכפת בקוד)** | **23** |
| Google Translate | 0 (אין מפתח) |

לפי חברה (ריצה ראשונה): KO=2, MSFT=2, INTC=2, JPM=2, CB=2, O=1, AMT=1.

ניסיונות החוזרים (retry) הקבועים בסקיל: אחד לכל קריאה, עם הסיבה המדויקת. `refresh` הוא ניסיון חוזר נוסף שמבקש רק את מה שנכשל, עם הסיבה כבר בניסיון הראשון.

## 7. מבנה ומסד

- מיגרציה 17 (`supabase/migrations/20261026103017_business_profile.sql`, rollback ב-`supabase/rollback/`): `company_business_profiles`, `business_vocab`, `term_translations`; ל-`ai_texts` נוספו `template_version`, `profile_id` והסטטוס `superseded`.
- בדיקות על test: md5 של `companies`, `extraction_items`, `ai_assessments`, `financial_facts`, `score_runs` זהה לפני ואחרי (5 מתוך 5); גם עמודות ה-`ai_texts` הישנות; rollback נוסה בבלוק שבוטל והחזיר את המצב המקורי (md5 של `ai_texts` זהה, שלוש הטבלאות נעלמו).
- RLS: משתמש מחובר קורא פרופילים, אוצר מילים פעיל (`active`) ותרגומים; אין לו כתיבה. טקסטים: רק `approved` (כמו קודם) — הטקסט העברי הממתין לתרגום והטקסטים `superseded` לא מוצגים.
- נטען: 62 שורות `business_vocab`, 17 מונחי מילון → `term_translations` (`approved`/`human`).

## 8. בדיקות ואידמפוטנטיות

- **בדיקות יחידה (בלי רשת, בלי DB אמיתי, בלי מודל):** 744 עברו (679 קודמות + 65 חדשות). הבדיקות החדשות ב-`tests/test_bp.py` (65): חילוץ צירים מ-iXBRL לדוגמה כולל ממבר מצטבר ושורת "Corporate and other"; מיפוי אזורים; בדיקות BP-1 (ציטוט, קודים, `other`, פעילות מרכזית, מתחרים, שדה שנכשל לא פוגע באחרים, ניסיון חוזר אחד עם סיבה); הגנת מונחים בתרגום; רינדור כל המקרים (שמות / סוגים / כלום, בלי מוצרים, בלי אזורים, שלוש רמות חפיר, ביטוי בלי תרגום, שדה שנכשל); בחירת חברות דומות לפי גודל; סימון הטקסטים הישנים `superseded`.
- **אידמפוטנטיות (מסד test, בפועל):** `vc.py render --all` הורץ פעמיים ברצף — בשתי הריצות 0 שינויים בכל 7 החברות. `bp_stage.py recheck` (שמריץ את כל משימת הרקע שוב לכל 7 החברות) לא ביצע אף קריאת Gemini ולא יצר פרופיל חדש (`profiles_reused`); BP-1 לא נשאל שוב על אותו `accession`.
- **RLS כ-`authenticated` (בדיקה בפועל):** 7 פרופילים, 40 שורות אוצר מילים (62 פחות 22 הצעות לא פעילות), 17 תרגומים, 7 טקסטים אנגליים מאושרים; 0 שורות `pending_review` / `superseded` / `failed` גלויות; ניסיון הכנסה ל-`term_translations` נדחה.
- **ai_texts אחרי השלב:** 17 טקסטי D1/T1 ישנים `superseded` (לא נמחקו); 7 טקסטים אנגליים `approved`; 7 עבריים `pending_review` (ממתינים לתרגום). 14 טקסטי הניתוח (D2) לא שונו.
- **`terms review`:** 0 ביטויים ממתינים (לא תורגם דבר); `terms approve|edit` ו-`profile show` / `render` פועלים (`profile show` ו-`render` נוסו בפועל).
- **golden:** לא שונה. מיגרציות, מחיקות וכתיבות — test בלבד.

