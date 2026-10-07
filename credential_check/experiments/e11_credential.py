#!/usr/bin/env python3
"""
E11 — credential layer, end to end, plus the attack scenarios.

The honest-path demo is the easy half. The attack scenarios are what make this
an experiment rather than a demonstration: each one is a way the credential
layer could be defeated, and the layer is only worth fusing if it resists them.

Run:  python experiments/e11_credential.py --out results/e11
"""

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np

from bvi.credential import (
    AnchorRegistry, Issuer, Holder, Verifier, DIDKey,
    canonicalise, b64url, resolve_did,
)


def honest_path(verbose=True):
    """Issue -> present -> verify. The path a legitimate call takes."""
    registry = AnchorRegistry()
    bank = Issuer("Example Bank", registry)
    agent = Holder("agent-0417")
    verifier = Verifier(registry)

    cred = bank.issue(agent.did, role="customer-service-agent")
    agent.receive(cred)

    challenge = verifier.new_challenge()
    presentation = agent.present(cred, challenge, verifier.domain)
    result = verifier.verify(presentation, challenge, expected_issuer=bank.did)

    if verbose:
        print("=" * 72)
        print("HONEST PATH")
        print("=" * 72)
        print(f"  issuer DID    {bank.did}")
        print(f"  subject DID   {agent.did}")
        print(f"  valid         {result.valid}")
        print(f"  S_cred        {result.s_cred}")
        print(f"  latency       {result.latency_ms:.3f} ms")
        print(f"  checks        {json.dumps(result.checks)}")

    return registry, bank, agent, verifier, cred, result


def attack_scenarios(verbose=True):
    """
    Seven scenarios. Each must fail closed.

    These are the constructed trials referred to in the methodology: no dataset
    pairs organisational credentials with audio, so the credential side of the
    fusion is evaluated against attacks defined in advance rather than observed
    in the wild. Defining them before running anything is what keeps this
    honest — the list below was fixed before the first result was produced.
    """
    results = {}

    # --- 1. No credential at all --------------------------------------------
    registry = AnchorRegistry()
    bank = Issuer("Example Bank", registry)
    verifier = Verifier(registry)
    imposter = Holder("imposter")
    challenge = verifier.new_challenge()
    empty = {"@context": [], "type": ["VerifiablePresentation"],
             "holder": imposter.did, "verifiableCredential": [],
             "proof": {"challenge": challenge, "domain": verifier.domain,
                       "proofValue": b64url(b"\x00" * 64),
                       "verificationMethod": imposter.key.verification_method}}
    r = verifier.verify(empty, challenge)
    results["no_credential"] = r.to_dict()

    # --- 2. Self-signed: imposter issues to itself --------------------------
    registry2 = AnchorRegistry()
    real_bank = Issuer("Example Bank", registry2)
    fake_bank = Issuer("Example Bank", registry2)      # same display name
    v2 = Verifier(registry2)
    imp = Holder("imposter")
    fake_cred = fake_bank.issue(imp.did, role="customer-service-agent")
    ch = v2.new_challenge()
    pres = imp.present(fake_cred, ch, v2.domain)
    r = v2.verify(pres, ch, expected_issuer=real_bank.did)
    results["self_signed_issuer"] = r.to_dict()

    # --- 3. Stolen credential presented by the wrong holder -----------------
    registry3 = AnchorRegistry()
    bank3 = Issuer("Example Bank", registry3)
    v3 = Verifier(registry3)
    real_agent = Holder("agent-real")
    thief = Holder("thief")
    cred3 = bank3.issue(real_agent.did, role="customer-service-agent")
    ch = v3.new_challenge()
    stolen = thief.present(cred3, ch, v3.domain)   # thief signs with own key
    r = v3.verify(stolen, ch, expected_issuer=bank3.did)
    results["stolen_credential"] = r.to_dict()

    # --- 4. Replay of a previously observed presentation --------------------
    registry4 = AnchorRegistry()
    bank4 = Issuer("Example Bank", registry4)
    v4 = Verifier(registry4)
    ag4 = Holder("agent")
    cred4 = bank4.issue(ag4.did, role="customer-service-agent")
    ch1 = v4.new_challenge()
    pres1 = ag4.present(cred4, ch1, v4.domain)
    v4.verify(pres1, ch1, expected_issuer=bank4.did)       # legitimate call
    ch2 = v4.new_challenge()
    r = v4.verify(pres1, ch2, expected_issuer=bank4.did)   # replayed later
    results["replayed_presentation"] = r.to_dict()

    # --- 5. Tampered claim: role escalated after issuance -------------------
    registry5 = AnchorRegistry()
    bank5 = Issuer("Example Bank", registry5)
    v5 = Verifier(registry5)
    ag5 = Holder("agent")
    cred5 = bank5.issue(ag5.did, role="customer-service-agent")
    tampered = json.loads(json.dumps(cred5))
    tampered["credentialSubject"]["role"] = "fraud-team-supervisor"
    ch = v5.new_challenge()
    pres = ag5.present(tampered, ch, v5.domain)
    r = v5.verify(pres, ch, expected_issuer=bank5.did)
    results["tampered_claim"] = r.to_dict()

    # --- 6. Revoked credential (dismissed agent) ----------------------------
    registry6 = AnchorRegistry()
    bank6 = Issuer("Example Bank", registry6)
    v6 = Verifier(registry6)
    ag6 = Holder("agent-dismissed")
    cred6 = bank6.issue(ag6.did, role="customer-service-agent")
    bank6.revoke(cred6)
    ch = v6.new_challenge()
    pres = ag6.present(cred6, ch, v6.domain)
    r = v6.verify(pres, ch, expected_issuer=bank6.did)
    results["revoked_credential"] = r.to_dict()

    # --- 7. Expired credential ----------------------------------------------
    registry7 = AnchorRegistry()
    bank7 = Issuer("Example Bank", registry7)
    v7 = Verifier(registry7)
    ag7 = Holder("agent")
    cred7 = bank7.issue(ag7.did, role="agent", validity_seconds=-10)
    ch = v7.new_challenge()
    pres = ag7.present(cred7, ch, v7.domain)
    r = v7.verify(pres, ch, expected_issuer=bank7.did)
    results["expired_credential"] = r.to_dict()

    if verbose:
        print()
        print("=" * 72)
        print("ATTACK SCENARIOS  (all must show valid=False)")
        print("=" * 72)
        for name, res in results.items():
            flag = "PASS" if not res["valid"] else "*** FAIL ***"
            print(f"  {flag:12s} {name:24s} S_cred={res['s_cred']:.1f}  {res['reason']}")

    return results


def latency_benchmark(n=2000, verbose=True):
    """
    Verification latency.

    Worth measuring because it is the deployability argument for did:key over a
    ledger-anchored method. A verifier that must complete a network round trip
    before a call can proceed is not usable on a live call; local resolution is.
    Report the median and the 95th percentile, not the mean — tail latency is
    what a caller actually experiences.
    """
    registry = AnchorRegistry()
    bank = Issuer("Example Bank", registry)
    agent = Holder("agent")
    verifier = Verifier(registry)
    cred = bank.issue(agent.did, role="agent")

    lat = []
    for _ in range(n):
        ch = verifier.new_challenge()
        pres = agent.present(cred, ch, verifier.domain)
        r = verifier.verify(pres, ch, expected_issuer=bank.did)
        assert r.valid
        lat.append(r.latency_ms)

    lat = np.array(lat)
    stats = {
        "n": n,
        "median_ms": float(np.median(lat)),
        "p95_ms": float(np.percentile(lat, 95)),
        "p99_ms": float(np.percentile(lat, 99)),
        "max_ms": float(lat.max()),
    }
    if verbose:
        print()
        print("=" * 72)
        print("VERIFICATION LATENCY  (local did:key resolution, no network)")
        print("=" * 72)
        for k, v in stats.items():
            print(f"  {k:12s} {v:.4f}" if isinstance(v, float) else f"  {k:12s} {v}")
    return stats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="results/e11")
    ap.add_argument("--latency-n", type=int, default=2000)
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    _, _, _, _, _, honest = honest_path()
    attacks = attack_scenarios()
    lat = latency_benchmark(args.latency_n)

    all_blocked = all(not r["valid"] for r in attacks.values())

    summary = {
        "honest_path": honest.to_dict(),
        "attacks": attacks,
        "latency": lat,
        "all_attacks_blocked": all_blocked,
    }
    with open(out / "e11_results.json", "w") as f:
        json.dump(summary, f, indent=2)

    print()
    print("=" * 72)
    print(f"E11 {'PASSED' if all_blocked and honest.valid else 'FAILED'} "
          f"— results written to {out / 'e11_results.json'}")
    print("=" * 72)
    return 0 if (all_blocked and honest.valid) else 1


if __name__ == "__main__":
    raise SystemExit(main())
