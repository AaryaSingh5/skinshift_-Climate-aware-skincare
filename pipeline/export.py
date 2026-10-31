"""Export de-identified check-ins of participants who opted in to research (data/checkins.csv). IDs are salted hashes."""
import argparse, hashlib, os, sqlite3
import pandas as pd

def export(db, out, salt):
    c = sqlite3.connect(db)
    d = pd.read_sql("select u.id uid, k.day date, k.city, k.comfort from checkins k join users u on u.id=k.user_id where u.research_consent=1 and u.role='consumer'", c)
    d["pid"] = d.uid.map(lambda i: hashlib.sha256(f"{salt}:{i}".encode()).hexdigest()[:12])
    d[["pid", "date", "city", "comfort"]].to_csv(out, index=False); return len(d)

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--db", default=os.getenv("DB_PATH", "skinshift.db")); ap.add_argument("--out", default="data/checkins.csv")
    a = ap.parse_args(); salt = os.getenv("EXPORT_SALT")
    if not salt: raise SystemExit("Set EXPORT_SALT (a secret string) so exported IDs cannot be reversed.")
    print(export(a.db, a.out, salt), "rows exported")
