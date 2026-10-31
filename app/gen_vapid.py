"""python -m app.gen_vapid  -> prints VAPID keys for web push. Keep the private key secret."""
import base64
from py_vapid import Vapid
from cryptography.hazmat.primitives import serialization as s
v = Vapid(); v.generate_keys()
print("VAPID_PRIVATE_KEY=" + v.private_pem().decode().strip().replace("\n", "\\n"))
print("VAPID_PUBLIC_KEY=" + base64.urlsafe_b64encode(v.public_key.public_bytes(s.Encoding.X962, s.PublicFormat.UncompressedPoint)).rstrip(b"=").decode())
