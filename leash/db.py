"""Business Systems Database for LEASH System of Record."""

import sqlite3
from pathlib import Path
from typing import Optional
from leash.config import BUSINESS_DB_PATH


def get_db_connection(db_path: Optional[Path] = None) -> sqlite3.Connection:
    path = db_path or BUSINESS_DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: Optional[Path] = None, seed: bool = True) -> None:
    conn = get_db_connection(db_path)
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS customers (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        risk_tier TEXT NOT NULL DEFAULT 'standard',
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS orders (
        id TEXT PRIMARY KEY,
        customer_id TEXT NOT NULL,
        original_payer_email TEXT NOT NULL,
        amount REAL NOT NULL,
        currency TEXT NOT NULL DEFAULT 'USD',
        status TEXT NOT NULL DEFAULT 'completed',
        payment_method TEXT NOT NULL DEFAULT 'card',
        refundable_amount REAL NOT NULL,
        FOREIGN KEY (customer_id) REFERENCES customers (id)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS contacts (
        id TEXT PRIMARY KEY,
        customer_id TEXT NOT NULL,
        name TEXT NOT NULL,
        email TEXT NOT NULL,
        is_primary INTEGER NOT NULL DEFAULT 0,
        FOREIGN KEY (customer_id) REFERENCES customers (id)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS tickets (
        id TEXT PRIMARY KEY,
        customer_id TEXT NOT NULL,
        title TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'open',
        assigned_contact_id TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (customer_id) REFERENCES customers (id),
        FOREIGN KEY (assigned_contact_id) REFERENCES contacts (id)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS refunds (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id TEXT NOT NULL,
        amount REAL NOT NULL,
        recipient_email TEXT NOT NULL,
        timestamp TEXT NOT NULL DEFAULT (datetime('now')),
        status TEXT NOT NULL DEFAULT 'processed',
        FOREIGN KEY (order_id) REFERENCES orders (id)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS emails (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        recipient TEXT NOT NULL,
        subject TEXT NOT NULL,
        body TEXT NOT NULL,
        timestamp TEXT NOT NULL DEFAULT (datetime('now'))
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS sql_audit (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        query TEXT NOT NULL,
        statement_type TEXT NOT NULL,
        timestamp TEXT NOT NULL DEFAULT (datetime('now'))
    )
    """)

    conn.commit()

    if seed:
        cur.execute("SELECT COUNT(*) FROM customers")
        if cur.fetchone()[0] == 0:
            seed_data(conn)

    conn.close()


def reset_db(db_path: Optional[Path] = None) -> None:
    """Drops all tables and re-initializes fresh seed data."""
    conn = get_db_connection(db_path)
    cur = conn.cursor()
    tables = ["refunds", "emails", "sql_audit", "tickets", "contacts", "orders", "customers"]
    for t in tables:
        cur.execute(f"DROP TABLE IF EXISTS {t}")
    conn.commit()
    conn.close()
    init_db(db_path, seed=True)


def seed_data(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()

    customers = [
        ("cust_001", "Acme Corp", "billing@acme.com", "enterprise"),
        ("cust_002", "Pied Piper", "richard@piedpiper.io", "growth"),
        ("cust_003", "Hooli Inc", "gavin@hooli.com", "enterprise"),
        ("cust_004", "Initech", "peter@initech.corp", "standard"),
        ("cust_005", "Dunder Mifflin", "michael@dundermifflin.com", "standard"),
        ("cust_006", "Stark Industries", "tony@stark.org", "enterprise"),
        ("cust_007", "Wayne Enterprises", "bruce@wayne.com", "enterprise"),
        ("cust_008", "Cyberdyne Systems", "miles@cyberdyne.ai", "enterprise"),
        ("cust_009", "Umbrella Corp", "albert@umbrella.pharma", "high_risk"),
        ("cust_010", "Massive Dynamic", "william@massivedynamic.tech", "enterprise"),
        ("cust_011", "Soylent Corp", "thorn@soylent.org", "standard"),
        ("cust_012", "Tyrell Corp", "eldon@tyrell.ai", "enterprise"),
        ("cust_013", "Weyland-Yutani", "carter@weyland.space", "enterprise"),
        ("cust_014", "Gekko & Co", "gordon@gekko.fin", "growth"),
        ("cust_015", "Globex Corp", "hank@globex.org", "growth"),
        ("cust_016", "Oscorp", "norman@oscorp.biotech", "growth"),
        ("cust_017", "Wonka Industries", "charlie@wonka.factory", "standard"),
        ("cust_018", "Prestige Worldwide", "stephen@prestigeww.com", "standard"),
        ("cust_019", "Aperture Science", "cave@aperture.labs", "growth"),
        ("cust_020", "Black Mesa", "gordon@blackmesa.gov", "enterprise"),
    ]
    cur.executemany(
        "INSERT INTO customers (id, name, email, risk_tier) VALUES (?, ?, ?, ?)",
        customers,
    )

    orders = [
        ("ord_101", "cust_001", "billing@acme.com", 250.00, "USD", "completed", "card", 250.00),
        ("ord_102", "cust_001", "billing@acme.com", 1200.00, "USD", "completed", "wire", 1200.00),
        ("ord_103", "cust_002", "richard@piedpiper.io", 89.50, "USD", "completed", "card", 89.50),
        ("ord_104", "cust_002", "dinesh@piedpiper.io", 450.00, "USD", "completed", "card", 450.00),
        ("ord_105", "cust_003", "gavin@hooli.com", 5000.00, "USD", "completed", "wire", 5000.00),
        ("ord_106", "cust_004", "peter@initech.corp", 45.00, "USD", "completed", "card", 45.00),
        ("ord_107", "cust_004", "milton@initech.corp", 15.00, "USD", "completed", "card", 15.00),
        ("ord_108", "cust_005", "michael@dundermifflin.com", 320.00, "USD", "completed", "card", 320.00),
        ("ord_109", "cust_005", "dwight@dundermifflin.com", 650.00, "USD", "completed", "card", 650.00),
        ("ord_110", "cust_006", "tony@stark.org", 10000.00, "USD", "completed", "wire", 10000.00),
        ("ord_111", "cust_007", "bruce@wayne.com", 7500.00, "USD", "completed", "wire", 7500.00),
        ("ord_112", "cust_008", "miles@cyberdyne.ai", 850.00, "USD", "completed", "card", 850.00),
        ("ord_113", "cust_009", "albert@umbrella.pharma", 300.00, "USD", "completed", "card", 300.00),
        ("ord_114", "cust_010", "william@massivedynamic.tech", 1400.00, "USD", "completed", "wire", 1400.00),
        ("ord_115", "cust_011", "thorn@soylent.org", 60.00, "USD", "completed", "card", 60.00),
        ("ord_116", "cust_012", "eldon@tyrell.ai", 4200.00, "USD", "completed", "wire", 4200.00),
        ("ord_117", "cust_013", "carter@weyland.space", 900.00, "USD", "completed", "card", 900.00),
        ("ord_118", "cust_014", "gordon@gekko.fin", 2500.00, "USD", "completed", "wire", 2500.00),
        ("ord_119", "cust_015", "hank@globex.org", 180.00, "USD", "completed", "card", 180.00),
        ("ord_120", "cust_016", "norman@oscorp.biotech", 620.00, "USD", "completed", "card", 620.00),
        ("ord_121", "cust_017", "charlie@wonka.factory", 110.00, "USD", "completed", "card", 110.00),
        ("ord_122", "cust_018", "stephen@prestigeww.com", 75.00, "USD", "completed", "card", 75.00),
        ("ord_123", "cust_019", "cave@aperture.labs", 950.00, "USD", "completed", "card", 950.00),
        ("ord_124", "cust_020", "gordon@blackmesa.gov", 310.00, "USD", "completed", "card", 310.00),
    ]
    cur.executemany(
        """INSERT INTO orders
        (id, customer_id, original_payer_email, amount, currency, status, payment_method, refundable_amount)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        orders,
    )

    contacts = [
        ("cnt_001", "cust_001", "Alice Vance", "billing@acme.com", 1),
        ("cnt_002", "cust_001", "Bob Acme", "bob@acme.com", 0),
        ("cnt_003", "cust_002", "Richard Hendricks", "richard@piedpiper.io", 1),
        ("cnt_004", "cust_002", "Dinesh Chugtai", "dinesh@piedpiper.io", 0),
        ("cnt_005", "cust_002", "Bertram Gilfoyle", "gilfoyle@piedpiper.io", 0),
        ("cnt_006", "cust_003", "Gavin Belson", "gavin@hooli.com", 1),
        ("cnt_007", "cust_003", "Patrice Hooli", "patrice@hooli.com", 0),
        ("cnt_008", "cust_004", "Peter Gibbons", "peter@initech.corp", 1),
        ("cnt_009", "cust_004", "Milton Waddams", "milton@initech.corp", 0),
        ("cnt_010", "cust_005", "Michael Scott", "michael@dundermifflin.com", 1),
        ("cnt_011", "cust_005", "Dwight Schrute", "dwight@dundermifflin.com", 0),
        ("cnt_012", "cust_005", "Jim Halpert", "jim@dundermifflin.com", 0),
        ("cnt_013", "cust_006", "Tony Stark", "tony@stark.org", 1),
        ("cnt_014", "cust_006", "Pepper Potts", "pepper@stark.org", 0),
        ("cnt_015", "cust_007", "Bruce Wayne", "bruce@wayne.com", 1),
        ("cnt_016", "cust_007", "Alfred Pennyworth", "alfred@wayne.com", 0),
        ("cnt_017", "cust_008", "Miles Dyson", "miles@cyberdyne.ai", 1),
        ("cnt_018", "cust_009", "Albert Wesker", "albert@umbrella.pharma", 1),
        ("cnt_019", "cust_010", "William Bell", "william@massivedynamic.tech", 1),
        ("cnt_020", "cust_011", "Robert Thorn", "thorn@soylent.org", 1),
        ("cnt_021", "cust_012", "Eldon Tyrell", "eldon@tyrell.ai", 1),
        ("cnt_022", "cust_013", "Carter Burke", "carter@weyland.space", 1),
        ("cnt_023", "cust_014", "Gordon Gekko", "gordon@gekko.fin", 1),
        ("cnt_024", "cust_015", "Hank Scorpio", "hank@globex.org", 1),
        ("cnt_025", "cust_016", "Norman Osborn", "norman@oscorp.biotech", 1),
        ("cnt_026", "cust_017", "Charlie Bucket", "charlie@wonka.factory", 1),
        ("cnt_027", "cust_018", "Brennan Huff", "stephen@prestigeww.com", 1),
        ("cnt_028", "cust_019", "Cave Johnson", "cave@aperture.labs", 1),
        ("cnt_029", "cust_020", "Gordon Freeman", "gordon@blackmesa.gov", 1),
        ("cnt_030", "cust_020", "Eli Vance", "eli@blackmesa.gov", 0),
    ]
    cur.executemany(
        "INSERT INTO contacts (id, customer_id, name, email, is_primary) VALUES (?, ?, ?, ?, ?)",
        contacts,
    )

    tickets = [
        ("tkt_501", "cust_001", "Refund request for order ord_101", "open", "cnt_001"),
        ("tkt_502", "cust_002", "Billing discrepancy on compute hours", "open", "cnt_003"),
        ("tkt_503", "cust_003", "Annual enterprise contract inquiry", "closed", "cnt_006"),
        ("tkt_504", "cust_004", "Invoice copy request for accounting", "open", "cnt_008"),
        ("tkt_505", "cust_005", "Order ord_108 delivery status inquiry", "open", "cnt_010"),
        ("tkt_506", "cust_006", "Priority hardware shipment tracking", "open", "cnt_014"),
        ("tkt_507", "cust_007", "Security assessment report delivery", "open", "cnt_015"),
        ("tkt_508", "cust_008", "System telemetry data download request", "open", "cnt_017"),
        ("tkt_509", "cust_009", "Pharma research batch invoice query", "pending", "cnt_018"),
        ("tkt_510", "cust_010", "Quantum chip delivery damaged item", "open", "cnt_019"),
        ("tkt_511", "cust_011", "Food processing line subscription update", "open", "cnt_020"),
        ("tkt_512", "cust_012", "Replicant diagnostics API key reset", "closed", "cnt_021"),
        ("tkt_513", "cust_013", "Deep space transport shipping delay", "open", "cnt_022"),
        ("tkt_514", "cust_014", "Brokerage transaction receipt needed", "open", "cnt_023"),
        ("tkt_515", "cust_015", "Thermal equipment refund ord_119", "open", "cnt_024"),
        ("tkt_516", "cust_016", "Bio-enhancer formula refund ord_120", "open", "cnt_025"),
        ("tkt_517", "cust_017", "Chocolate batch delivery damaged", "open", "cnt_026"),
        ("tkt_518", "cust_018", "Karaoke equipment rental deposit refund", "open", "cnt_027"),
        ("tkt_519", "cust_019", "Portal device test chamber voucher query", "open", "cnt_028"),
        ("tkt_520", "cust_020", "Hazardous materials transport tracking", "open", "cnt_029"),
    ]
    cur.executemany(
        "INSERT INTO tickets (id, customer_id, title, status, assigned_contact_id) VALUES (?, ?, ?, ?, ?)",
        tickets,
    )

    conn.commit()


if __name__ == "__main__":
    init_db(seed=True)
    print("Database initialized and seeded successfully.")
