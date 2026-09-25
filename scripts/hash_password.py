"""Print the SHA-256 hash of the club password for hugo.toml → params.submit.passwordHash.

    py scripts/hash_password.py

The password itself is never stored in the repo. Note this gate only keeps
casual visitors out: the hash and form endpoint are visible in the page
source, so rely on Formspree's own spam protection and domain restriction too.
"""
import getpass
import hashlib

pw = getpass.getpass("Club password: ")
if pw != getpass.getpass("Again: "):
    raise SystemExit("Passwords don't match.")
print(hashlib.sha256(pw.encode("utf-8")).hexdigest())
