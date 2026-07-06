---
id: jwt-key-rotation
name: JWT Signing Key Rotation
description: Rotate JWT signing keys without invalidating live sessions — JWKS, multiple active kids.
tags: [jwt, key-rotation, signing, jwks, kid, sessions, token]
---
# JWT Signing Key Rotation

Use to rotate JWT signing keys while keeping users logged in — publish both old and new keys in JWKS, sign with the new kid, retire the old after expiry. NOT OAuth flows or CSRF.
