import sqlite3
conn = sqlite3.connect("jobs.db")
conn.row_factory = sqlite3.Row

total = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
print(f"Total jobs in DB: {total}")

rows = conn.execute("SELECT source, COUNT(*) as cnt FROM jobs GROUP BY source").fetchall()
print("By source:")
for r in rows:
    print(f"  {r['source']:12s} {r['cnt']}")

print("\nLast 10 jobs:")
rows = conn.execute("SELECT id, source, title, status FROM jobs ORDER BY id DESC LIMIT 10").fetchall()
for r in rows:
    print(f"  id={r['id']:3d}  {r['source']:10s}  st={r['status']:12s}  {r['title'][:60]}")

conn.close()