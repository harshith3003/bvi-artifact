"""
E11 — the credential layer.

WHAT THIS IMPLEMENTS
--------------------
The full organisational credential path, end to end:

    issue -> hold -> present -> verify -> revoke

An organisation (the bank) holds a decentralised identifier and a signing key.
It issues a verifiable credential to a call-centre agent asserting that the
agent may speak on its behalf. During a call the agent presents that credential,
bound to a verifier-supplied challenge. The verifier resolves the issuer's DID,
checks the signature, checks the binding, checks expiry and checks revocation
status, and emits a credential score S_cred which E12 fuses with the audio score.

WHY did:key AND NOT A LEDGER
----------------------------
The proposal's risk register listed ledger tooling overrun as High likelihood,
High impact, with the fallback being "a simpler DID method with local
resolution". That risk materialised. did:key is the fallback, and it is a
defensible choice on its own terms, not merely an expedient one:

  - The public key is encoded *inside* the identifier, so resolution is a local
    decode with no network round trip. On a live call that matters: a verifier
    that must reach a ledger before the conversation can proceed is not
    deployable, and the latency argument is worth making in the thesis.
  - Nothing about the fusion in E12 depends on how S_cred was produced. The
    contribution is the combination of credential and acoustic evidence, not the
    identifier scheme.

WHAT IS GIVEN UP, STATED PLAINLY
--------------------------------
did:key has no update or deactivate operation, so key rotation means a new
identifier, and revocation cannot be anchored to a public ledger. Revocation
here is a locally hosted status list, which reintroduces a trusted party — the
precise thing a ledger would remove. This is a real limitation and belongs in
the results chapter, not an appendix. A migration to did:web (same code path,
resolution by HTTPS fetch) or to a ledger-anchored method is future work and is
a drop-in replacement for `resolve_did` below.

PRIVACY COMMITMENT (Section 6.1)
--------------------------------
Only identifiers, public keys and revocation status are ever anchored. The
credential itself travels issuer -> holder -> verifier and is never published.
No personal data of any individual is written to any anchor at any point. This
is enforced structurally: `AnchorRegistry.publish` accepts a DID document and a
status list, and nothing else.
"""

from __future__ import annotations

import base64
import hashlib
import json
import time
from dataclasses import dataclass, field, asdict

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey, Ed25519PublicKey,
)
from cryptography.hazmat.primitives import serialization
from cryptography.exceptions import InvalidSignature


# --------------------------------------------------------------------------
# Multibase / multicodec encoding for did:key
# --------------------------------------------------------------------------

_B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
ED25519_MULTICODEC = b"\xed\x01"  # varint prefix for Ed25519 public keys


def b58encode(data: bytes) -> str:
    n = int.from_bytes(data, "big")
    out = ""
    while n > 0:
        n, r = divmod(n, 58)
        out = _B58[r] + out
    for byte in data:                      # preserve leading zero bytes
        if byte == 0:
            out = _B58[0] + out
        else:
            break
    return out


def b58decode(s: str) -> bytes:
    n = 0
    for ch in s:
        idx = _B58.find(ch)
        if idx < 0:
            raise ValueError(f"invalid base58 character {ch!r}")
        n = n * 58 + idx
    body = n.to_bytes((n.bit_length() + 7) // 8, "big")
    pad = len(s) - len(s.lstrip(_B58[0]))
    return b"\x00" * pad + body


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def b64url_decode(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


# --------------------------------------------------------------------------
# DID
# --------------------------------------------------------------------------

@dataclass
class DIDKey:
    """An Ed25519 keypair with its did:key identifier."""
    did: str
    _private: Ed25519PrivateKey | None = field(default=None, repr=False)

    @classmethod
    def generate(cls) -> "DIDKey":
        priv = Ed25519PrivateKey.generate()
        pub = priv.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        did = "did:key:z" + b58encode(ED25519_MULTICODEC + pub)
        return cls(did=did, _private=priv)

    @property
    def verification_method(self) -> str:
        frag = self.did.split(":")[-1]
        return f"{self.did}#{frag}"

    def sign(self, payload: bytes) -> bytes:
        if self._private is None:
            raise ValueError("no private key held for this DID")
        return self._private.sign(payload)


def resolve_did(did: str) -> Ed25519PublicKey:
    """
    Resolve a did:key to its public key.

    This is the whole resolution step — a local decode, no network, no ledger,
    no trusted directory. Swapping in did:web or a ledger method means replacing
    only this function; nothing downstream changes.
    """
    if not did.startswith("did:key:z"):
        raise ValueError(f"unsupported DID method: {did!r} (only did:key handled)")

    raw = b58decode(did[len("did:key:z"):])
    if raw[:2] != ED25519_MULTICODEC:
        raise ValueError("DID does not encode an Ed25519 key")

    key_bytes = raw[2:]
    if len(key_bytes) != 32:
        raise ValueError(f"expected 32-byte Ed25519 key, got {len(key_bytes)}")
    return Ed25519PublicKey.from_public_bytes(key_bytes)


def did_document(did: str) -> dict:
    """
    The DID document. This — and only this — is what may be anchored.
    Note the absence of any field capable of carrying personal data.
    """
    frag = did.split(":")[-1]
    return {
        "@context": ["https://www.w3.org/ns/did/v1"],
        "id": did,
        "verificationMethod": [{
            "id": f"{did}#{frag}",
            "type": "Ed25519VerificationKey2020",
            "controller": did,
            "publicKeyMultibase": frag,
        }],
        "authentication": [f"{did}#{frag}"],
        "assertionMethod": [f"{did}#{frag}"],
    }


# --------------------------------------------------------------------------
# Canonical serialisation
# --------------------------------------------------------------------------

def canonicalise(obj: dict) -> bytes:
    """
    Deterministic JSON for signing.

    Sorted keys and no whitespace, so that the bytes signed by the issuer are
    exactly the bytes checked by the verifier. Without this, an intermediary
    that re-serialises the JSON silently breaks every signature — a failure mode
    that is tedious to diagnose at 2am in week 8.
    """
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


# --------------------------------------------------------------------------
# Revocation
# --------------------------------------------------------------------------

class StatusList:
    """
    Bitstring status list. Index i is 1 if credential i is revoked.

    A bitstring rather than a list of revoked identifiers, because publishing
    identifiers of revoked credentials leaks how many agents an organisation has
    dismissed and when — organisational metadata that has no business being
    public. A fixed-size bitstring reveals only its own length.
    """

    def __init__(self, size: int = 8192):
        self.size = size
        self._bits = bytearray(size // 8)

    def set_revoked(self, index: int, revoked: bool = True):
        if not 0 <= index < self.size:
            raise IndexError(f"status index {index} outside list of size {self.size}")
        byte, bit = divmod(index, 8)
        if revoked:
            self._bits[byte] |= (1 << bit)
        else:
            self._bits[byte] &= ~(1 << bit)

    def is_revoked(self, index: int) -> bool:
        if not 0 <= index < self.size:
            raise IndexError(f"status index {index} outside list of size {self.size}")
        byte, bit = divmod(index, 8)
        return bool(self._bits[byte] & (1 << bit))

    def encoded(self) -> str:
        return b64url(bytes(self._bits))

    def digest(self) -> str:
        return hashlib.sha256(bytes(self._bits)).hexdigest()


class AnchorRegistry:
    """
    Stand-in for the ledger.

    Deliberately accepts only DID documents and status lists. Every write path
    into the anchor goes through here, so the "no personal data on-chain"
    commitment in Section 6.1 is enforced by the type of the interface rather
    than by reviewer diligence. Say this in the viva — a design constraint
    expressed in code is a stronger claim than one expressed in prose.
    """

    def __init__(self):
        self.did_documents: dict[str, dict] = {}
        self.status_lists: dict[str, dict] = {}
        self.log: list[dict] = []

    def publish_did(self, did: str):
        doc = did_document(did)
        self.did_documents[did] = doc
        self.log.append({"op": "publish_did", "did": did, "t": time.time()})
        return doc

    def publish_status_list(self, list_id: str, status_list: StatusList):
        entry = {
            "id": list_id,
            "encodedList": status_list.encoded(),
            "digest": status_list.digest(),
            "size": status_list.size,
        }
        self.status_lists[list_id] = entry
        self.log.append({"op": "publish_status", "id": list_id,
                         "digest": entry["digest"], "t": time.time()})
        return entry

    def get_status_list(self, list_id: str) -> StatusList | None:
        entry = self.status_lists.get(list_id)
        if entry is None:
            return None
        sl = StatusList(size=entry["size"])
        sl._bits = bytearray(b64url_decode(entry["encodedList"]))
        return sl


# --------------------------------------------------------------------------
# Issuer / Holder / Verifier
# --------------------------------------------------------------------------

class Issuer:
    """An organisation. Issues credentials to its agents and can revoke them."""

    def __init__(self, name: str, registry: AnchorRegistry, list_size: int = 8192):
        self.name = name
        self.key = DIDKey.generate()
        self.registry = registry
        self.status_list = StatusList(size=list_size)
        self.status_list_id = f"{self.key.did}#status"
        self._next_index = 0

        registry.publish_did(self.key.did)
        registry.publish_status_list(self.status_list_id, self.status_list)

    @property
    def did(self) -> str:
        return self.key.did

    def issue(self, subject_did: str, role: str, validity_seconds: int = 86400 * 90) -> dict:
        """
        Issue a credential.

        The subject is identified by DID and role only. No name, no employee
        number, no personal identifier of any kind — the credential asserts an
        authorisation, not an identity, and the verifier's question is "may this
        party speak for the bank", not "who is this person".
        """
        idx = self._next_index
        self._next_index += 1

        now = int(time.time())
        payload = {
            "@context": [
                "https://www.w3.org/2018/credentials/v1",
                "https://w3id.org/security/suites/ed25519-2020/v1",
            ],
            "type": ["VerifiableCredential", "OrganisationalAuthorityCredential"],
            "issuer": self.key.did,
            "issuanceDate": now,
            "expirationDate": now + validity_seconds,
            "credentialSubject": {
                "id": subject_did,
                "role": role,
                "authorisedBy": self.name,
            },
            "credentialStatus": {
                "id": f"{self.status_list_id}?index={idx}",
                "type": "StatusList2021Entry",
                "statusListIndex": idx,
                "statusListCredential": self.status_list_id,
            },
        }

        sig = self.key.sign(canonicalise(payload))
        payload["proof"] = {
            "type": "Ed25519Signature2020",
            "created": now,
            "verificationMethod": self.key.verification_method,
            "proofPurpose": "assertionMethod",
            "proofValue": b64url(sig),
        }
        return payload

    def revoke(self, credential: dict):
        idx = credential["credentialStatus"]["statusListIndex"]
        self.status_list.set_revoked(idx, True)
        self.registry.publish_status_list(self.status_list_id, self.status_list)
        return idx


class Holder:
    """A call-centre agent. Holds credentials and presents them on challenge."""

    def __init__(self, name: str):
        self.name = name
        self.key = DIDKey.generate()
        self.credentials: list[dict] = []

    @property
    def did(self) -> str:
        return self.key.did

    def receive(self, credential: dict):
        self.credentials.append(credential)

    def present(self, credential: dict, challenge: str, domain: str) -> dict:
        """
        Build a verifiable presentation bound to the verifier's challenge.

        The challenge binding is what stops replay. Without it, anyone who
        observed one presentation could reuse it — which in this setting means
        a recorded call becomes a valid credential, and the whole layer is
        worthless. The holder signs the challenge with its own key, proving
        possession of the subject key rather than mere possession of the
        credential document.
        """
        payload = {
            "@context": ["https://www.w3.org/2018/credentials/v1"],
            "type": ["VerifiablePresentation"],
            "holder": self.key.did,
            "verifiableCredential": [credential],
        }
        to_sign = canonicalise({"presentation": payload,
                                "challenge": challenge, "domain": domain})
        sig = self.key.sign(to_sign)

        payload["proof"] = {
            "type": "Ed25519Signature2020",
            "created": int(time.time()),
            "verificationMethod": self.key.verification_method,
            "proofPurpose": "authentication",
            "challenge": challenge,
            "domain": domain,
            "proofValue": b64url(sig),
        }
        return payload


@dataclass
class VerificationResult:
    valid: bool
    s_cred: float
    checks: dict
    reason: str = ""
    latency_ms: float = 0.0

    def to_dict(self):
        return asdict(self)


class Verifier:
    """
    The customer's device. Resolves, verifies, and emits S_cred for fusion.
    """

    def __init__(self, registry: AnchorRegistry, domain: str = "bvi-assure.example"):
        self.registry = registry
        self.domain = domain
        self._issued_challenges: set[str] = set()

    def new_challenge(self) -> str:
        import secrets
        c = secrets.token_hex(16)
        self._issued_challenges.add(c)
        return c

    def verify(self, presentation: dict, challenge: str,
               expected_issuer: str | None = None) -> VerificationResult:
        """
        Returns S_cred in [0, 1] for fusion in E12.

        The score is near-binary by design and that asymmetry is the whole point
        of the fusion problem: the credential layer answers with near-certainty
        or not at all, while the audio layer answers with a continuous score
        carrying a measurable error rate. Setting the exchange rate between a
        near-certain binary and a calibrated continuous score is the open
        question this thesis addresses.

        The graded values below are not confidences. They encode *how* a
        verification failed, so that E12 can distinguish an expired credential
        from a forged one — a distinction that matters operationally, since the
        first is probably an administrative lapse and the second is an attack.
        """
        t0 = time.perf_counter()
        checks: dict[str, bool] = {}

        def fail(reason: str, score: float) -> VerificationResult:
            return VerificationResult(
                valid=False, s_cred=score, checks=checks, reason=reason,
                latency_ms=(time.perf_counter() - t0) * 1000)

        # --- challenge freshness ------------------------------------------
        checks["challenge_fresh"] = challenge in self._issued_challenges
        if not checks["challenge_fresh"]:
            return fail("challenge not issued by this verifier or already consumed", 0.0)

        proof = presentation.get("proof", {})
        checks["challenge_bound"] = proof.get("challenge") == challenge
        checks["domain_bound"] = proof.get("domain") == self.domain
        if not (checks["challenge_bound"] and checks["domain_bound"]):
            return fail("presentation not bound to this challenge and domain", 0.0)

        # --- holder signature over the challenge --------------------------
        try:
            holder_pub = resolve_did(presentation["holder"])
            unsigned = {k: v for k, v in presentation.items() if k != "proof"}
            holder_pub.verify(
                b64url_decode(proof["proofValue"]),
                canonicalise({"presentation": unsigned,
                              "challenge": challenge, "domain": self.domain}),
            )
            checks["holder_signature"] = True
        except (InvalidSignature, ValueError, KeyError) as e:
            checks["holder_signature"] = False
            return fail(f"holder signature invalid: {type(e).__name__}", 0.0)

        # --- credential ----------------------------------------------------
        try:
            cred = presentation["verifiableCredential"][0]
        except (KeyError, IndexError):
            return fail("no credential in presentation", 0.0)

        # subject binding: the presenter must be the credential's subject
        checks["subject_binding"] = (
            cred.get("credentialSubject", {}).get("id") == presentation["holder"])
        if not checks["subject_binding"]:
            return fail("presenter is not the credential subject", 0.0)

        # issuer signature
        try:
            issuer_did = cred["issuer"]
            issuer_pub = resolve_did(issuer_did)
            unsigned_cred = {k: v for k, v in cred.items() if k != "proof"}
            issuer_pub.verify(b64url_decode(cred["proof"]["proofValue"]),
                              canonicalise(unsigned_cred))
            checks["issuer_signature"] = True
        except (InvalidSignature, ValueError, KeyError) as e:
            checks["issuer_signature"] = False
            return fail(f"issuer signature invalid: {type(e).__name__}", 0.0)

        # expected issuer
        if expected_issuer is not None:
            checks["issuer_expected"] = (issuer_did == expected_issuer)
            if not checks["issuer_expected"]:
                return fail("credential issued by a different organisation "
                            "than the one claimed", 0.0)

        # anchor presence
        checks["issuer_anchored"] = issuer_did in self.registry.did_documents
        if not checks["issuer_anchored"]:
            return fail("issuer DID not present in the anchor registry", 0.0)

        # expiry
        now = int(time.time())
        checks["not_expired"] = now <= cred.get("expirationDate", 0)
        if not checks["not_expired"]:
            # 0.2 not 0.0 — an expired credential still proves the issuer once
            # authorised this subject. Operationally this is a lapsed badge,
            # not an impersonation, and E12 should be able to tell them apart.
            return fail("credential expired", 0.2)

        # revocation
        status = cred.get("credentialStatus", {})
        sl = self.registry.get_status_list(status.get("statusListCredential", ""))
        if sl is None:
            checks["revocation_checked"] = False
            # 0.5 — cannot verify status either way. Genuinely unknown, and the
            # fusion should treat it as uninformative rather than as evidence.
            return fail("status list unavailable; revocation could not be checked", 0.5)

        checks["revocation_checked"] = True
        checks["not_revoked"] = not sl.is_revoked(status["statusListIndex"])
        if not checks["not_revoked"]:
            return fail("credential revoked", 0.0)

        self._issued_challenges.discard(challenge)   # single use
        return VerificationResult(
            valid=True, s_cred=1.0, checks=checks, reason="all checks passed",
            latency_ms=(time.perf_counter() - t0) * 1000)
