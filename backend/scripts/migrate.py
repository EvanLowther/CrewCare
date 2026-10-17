"""Apply db/migrations/*.sql in order, once each. Run: python dev.py migrate"""


from planit.config import REPO_ROOT
from planit.db import connection

MIGRATIONS = REPO_ROOT / "db" / "migrations"


def main() -> None:
    with connection() as conn:
        conn.autocommit = True  # continuous aggregates can't be created inside a transaction
        conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations "
                     "(name text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())")
        done = {r["name"] for r in conn.execute("SELECT name FROM schema_migrations").fetchall()}
        for path in sorted(MIGRATIONS.glob("*.sql")):
            if path.name in done:
                continue
            print(f"applying {path.name}")
            conn.execute(path.read_text())
            conn.execute("INSERT INTO schema_migrations (name) VALUES (%s)", (path.name,))
    print("migrations up to date")


if __name__ == "__main__":
    main()
