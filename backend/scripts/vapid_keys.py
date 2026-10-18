"""Make a Web Push (VAPID) key pair for PLANIT_VAPID_PUBLIC_KEY / PLANIT_VAPID_PRIVATE_KEY.

    python scripts/vapid_keys.py

Run it once per server and keep the private key secret. Changing the pair later means every device has to turn
notifications on again.
"""

import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


key = ec.generate_private_key(ec.SECP256R1())
private = key.private_numbers().private_value.to_bytes(32, "big")
public = key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
print(f"PLANIT_VAPID_PUBLIC_KEY={b64url(public)}")
print(f"PLANIT_VAPID_PRIVATE_KEY={b64url(private)}")
