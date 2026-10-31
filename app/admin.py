"""python -m app.admin create-researcher EMAIL PASSWORD   (set SECRET_KEY or DEV=1 and DB_PATH first)"""
import sys
from app.main import q, hash_pw, now
if len(sys.argv) == 4 and sys.argv[1] == "create-researcher":
    if len(sys.argv[3]) < 12: raise SystemExit("Use a password of 12+ characters.")
    q("insert into users(email,pw,role,created) values(?,?,?,?)", (sys.argv[2].lower(), hash_pw(sys.argv[3]), "researcher", now()), commit=True); print("created")
else: raise SystemExit(__doc__)
