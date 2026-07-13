# Profile sharing integrity — design for the server side

Audience: Josh (server/web side, private repo). Written 2026-07-12 from
the Freight Fate client side. Goal: players share profiles through the
system and download them back, and edited/cheated profiles cannot enter
the shared pool. This is buildable and is standard, solved territory —
but the trust boundary has to sit on the server, not in the file format.

## 1. The one principle everything follows from

**Any secret that ships inside the game can be extracted.** The game
must read its own saves, so a key, salt, or cipher in the client is
documentation for the attacker, not protection. Hash strength is
irrelevant: nobody brute-forces a save file, they lift the key and use
it. And it only takes one person doing that once to publish a save
editor that makes cheating free for everyone.

Consequences, stated bluntly:

- A "tamper-proof local file" does not exist. Not with JSON, not with
  SQLite, not with SQLCipher (the decryption key ships in the client).
- A **tamper-proof shared pool** absolutely exists: the server refuses
  to bless anything it can't validate, and clients refuse anything the
  server hasn't blessed. Cheaters can still edit their own solo saves
  (unpreventable, and harmless to others); they can never inject one
  into the pool.

## 2. What the client already has (current state of the JSON)

A profile is one JSON document: the flat fields of the `Profile`
dataclass (money, current_city, wear meters, fatigue, active_buffs,
truck/trailers/upgrades) plus nested payloads — `career` (XP,
reputation, endorsements, delivery history counters), `market`, `hos`
(duty clock), `duty_log`, `achievements`, and optionally `active_trip`
(a mid-delivery snapshot). Loading filters to known fields, so extra
keys are dropped silently.

Integrity today: `_signature` = HMAC-SHA256 over the sorted,
canonically-serialized known fields, keyed by a **per-install** random
32-byte secret stored next to the saves. Invalid signature → the file
is quarantined (renamed `.invalid`), not loaded. Its docstring is
honest: "This is not DRM: local users can ultimately control local
files. It stops casual JSON edits from silently becoming trusted
career state." That is exactly what it does and all it can do — the
secret is on the player's disk. Keep it as the local layer; do not
rest the shared pool on it.

## 3. The server design

### Upload: validate, then sign

1. Player submits profile JSON (the same document, minus the local
   `_signature`, which means nothing to the server).
2. **Validation gate** — reject with a reason if any check fails:
   - Schema: known fields, sane types, no oversized payloads.
   - Range invariants: wear/fatigue/grime in 0..100, money and XP
     non-negative and below sanity ceilings, valid city slug, valid
     truck/upgrade/trailer keys and tiers.
   - Cross-field plausibility: money consistent with career deliveries
     and level (a level-2 driver with $9M fails); XP consistent with
     recorded miles; endorsements consistent with level or purchase
     history; achievements consistent with the stats that earn them.
   - Possession-implies-acquisition: any gated item (future: Golden
     Antler passes) must be accompanied by the event/counter trail
     that grants it. This is the anti-"just add the item" rule. Cheap
     version now: server-side allowlist of grantable items + counters;
     stronger version later: an append-only event ledger in the
     profile that the server replays and recomputes.
3. **Sign with Ed25519.** The private key exists ONLY on the server
   (env var / secrets manager, never in any repo). Sign the canonical
   serialization (sorted keys, compact separators, UTF-8 — the client
   already canonicalizes this way for its HMAC; reuse the recipe).
4. Store and serve the **envelope**:

```json
{
  "payload": { ...the validated profile... },
  "sig": "<base64 ed25519 signature of canonical payload>",
  "key_id": "2026-07",
  "signed_at": "2026-07-12T21:00:00Z",
  "validator_version": 3
}
```

`key_id` makes key rotation painless: the client ships a small map of
key_id → public key; retiring a key just stops signing with it.
`validator_version` lets old signed profiles be re-checked when the
validation rules tighten.

### Download: verify before trusting

The game embeds the **public** key(s) — safe to ship, safe to be read,
useless for forging. On import of a shared profile: canonicalize the
payload, verify the signature, reject cleanly (spoken, no jargon) if it
fails. Then re-sign locally with the per-install HMAC as usual so it
becomes a normal local save.

### Why this ends the arms race

Forging a server signature requires the private key, which never
leaves the server, or breaking Ed25519, which is not a thing that
happens. There is no client secret to extract — the thing that killed
every save-protection scheme is simply absent from the design. The
only remaining attack is crafting a cheated profile that passes
validation, which is why the validation gate is the part worth
continuous investment (and why an event ledger is the long-term
strengthener: the server recomputes the outcome instead of trusting
claimed totals).

## 4. Where SQLite fits (and where it does not)

- **Server side: yes.** SQLite (or Postgres when concurrency grows) is
  the right store for submitted profiles, signatures, validation
  results, and per-player submission history. Atomic, queryable,
  trivially backed up.
- **Client side: fine as a format, zero as a defense.** DB Browser for
  SQLite opens it like Notepad opens JSON; SQLCipher's key must ship
  in the client and gets extracted like any other. If the client ever
  moves saves to SQLite it should be for atomic-write robustness, not
  security. (The map-data SQLite plan is unrelated: that is read-only
  content, no integrity problem.)

## 5. Passwords, salts, and the right names for things

- **Salt + slow hash (argon2id or bcrypt)**: for storing player
  ACCOUNT PASSWORDS on the sharing service, if accounts exist. This is
  the one and only place "salt and hash" belongs in this design.
- **HMAC (keyed hash)**: integrity where signer and verifier share a
  secret. Right for the local casual-edit deterrent (already built);
  wrong for the pool, because the shared secret would have to ship.
- **Ed25519 signatures**: integrity where the verifier must not be
  able to forge. This is the pool's tool.
- **Encryption** hides content. Nothing here needs hiding — a profile
  is not secret, it just must not be forged. Skip it; it adds key
  management pain and no protection.

## 6. Reference snippets (Python, `cryptography` library)

Server — generate once, keep private key out of every repo:

```python
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
private_key = Ed25519PrivateKey.generate()
# persist private bytes to the secrets store; publish public bytes to the game
```

Server — sign a validated profile:

```python
import json
payload = json.dumps(profile, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
sig = private_key.sign(payload.encode("utf-8"))  # -> base64 into the envelope
```

Client — verify (public key baked into the game):

```python
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.exceptions import InvalidSignature
try:
    Ed25519PublicKey.from_public_bytes(PUBLIC_KEYS[envelope["key_id"]]).verify(
        base64.b64decode(envelope["sig"]), canonical(envelope["payload"])
    )
except InvalidSignature:
    reject("This shared profile failed its integrity check and was not imported.")
```

## 7. Division of labor

- **Josh / web side**: upload endpoint, validation gate (start with
  schema + ranges + a handful of plausibility rules; tighten over
  time), Ed25519 signing, envelope storage, download endpoint,
  account-password handling with argon2id if accounts exist.
- **Freight Fate client (this repo, small)**: embed public key(s),
  verify-on-import with a plain spoken rejection, and export a
  canonical "for sharing" payload. Later, if warranted: the
  append-only event ledger that upgrades validation from plausibility
  to recomputation.
- Validation rules need a maintained list of game invariants (what
  grants what) — the client side should keep that documented for the
  server as features land (Golden Antler being the first planned
  gated item).
Note: (Noel speaking here), the golden antler is an item I created which allows you to take your truck into the mythical and similar to Buc-Ee's truck stop. We'll also have a punch card which allows you entry x number of times (10) and it only lets you in there for a specific amount of time. You can't sleep at big bucks, you can't loiter, but youi can ejoy teh jerky wall, the fudge counter, brisket sandwiches etc. If you don't want to worry with paying for a card or obtaining the golden antlers, (for the really rich or the crazy ... haven't figured what gets you the golden antlers), you must drop your trailer somewhere and bobtail it into Big Buck's (bobtail). I wanted to make sure that I mentioned how this will work because there will be other things you'll be able to get (provided you're on board) if you pull off ands see a thing, get a souvenir, visit a welcome center etc. We do not want to allow a player to give themselves golden antlers because that bastard's gonna be really hard to get, not impossible mind, but hard indeed. I hope this helps.
