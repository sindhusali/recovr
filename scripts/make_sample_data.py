"""Generate a FAKE ledger for demos and tests. Never use real shop data here.

Usage:  python scripts/make_sample_data.py
Output: data/sample_ledger.csv
"""
import csv
import random
from datetime import date, timedelta
from pathlib import Path

random.seed(42)

FIRST = ["Ravi", "Suresh", "Lakshmi", "Venkat", "Anitha", "Kiran", "Sravani",
         "Mahesh", "Padma", "Ramesh", "Divya", "Srinivas", "Harika", "Naveen",
         "Bhavani", "Prasad", "Swathi", "Krishna", "Madhavi", "Rajesh"]
SHOPS = ["General Stores", "Traders", "Textiles", "Electricals", "Medicals",
         "Hardware", "Enterprises", "Kirana", "Agencies", "Mart"]

TODAY = date.today()


def make_customers(n: int = 30) -> list[tuple[str, str]]:
    customers = set()
    while len(customers) < n:
        customers.add(f"{random.choice(FIRST)} {random.choice(SHOPS)}")
    # fake 10-digit numbers starting with 9, clearly not real
    return [(c, "9" + "".join(random.choices("0123456789", k=9))) for c in sorted(customers)]


def main(rows: int = 200) -> None:
    customers = make_customers()
    out = Path(__file__).resolve().parent.parent / "data" / "sample_ledger.csv"
    out.parent.mkdir(exist_ok=True)

    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Party Name", "Bill No", "Bill Date", "Due Date",
                    "Bill Amount", "Received", "Mobile"])
        for i in range(1, rows + 1):
            name, phone = random.choice(customers)
            bill_date = TODAY - timedelta(days=random.randint(5, 150))
            due = bill_date + timedelta(days=random.choice([15, 30, 45]))
            amount = random.randrange(1000, 60000, 50)
            paid = random.choice([0, 0, amount, amount, amount // 2])
            w.writerow([name, f"INV-{1000 + i}", bill_date.strftime("%d/%m/%Y"),
                        due.strftime("%d/%m/%Y"), amount, paid, phone])
    print(f"Wrote {rows} fake invoices to {out}")


if __name__ == "__main__":
    main()
