import sys

from src.services.stock_import_service import StockImportService


def main():
    # בדיקה שהוזן סימול בשורת הפקודה
    if len(sys.argv) < 2:
        print("Usage: python scripts/import_stock.py <SYMBOL>")
        return

    # קבלת הסימול שהמשתמש הזין
    symbol = sys.argv[1]

    # יצירת שירות הייבוא
    service = StockImportService()

    try:
        # ייבוא החברה ושמירתה ב-DB
        company = service.import_company(symbol)

        print("Company imported successfully:")
        print(company)

    except Exception as error:
        # הצגת שגיאה בצורה ברורה
        print(f"Import failed: {error}")


if __name__ == "__main__":
    # הפעלת הסקריפט רק כאשר מריצים אותו ישירות
    main()