import os, tempfile
os.environ.update(DEV="1", DB_PATH=tempfile.mktemp(suffix=".db"), RESEARCHER_EMAIL="r@x.org", RESEARCHER_PASSWORD="research-pass-1")
