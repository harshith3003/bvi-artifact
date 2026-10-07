/**
 * Route check with declared translations (item 3).
 *
 * Each participating carrier attests BOTH the ID it received and the ID it sent on:
 *   { hop, inClaim, outClaim }      inClaim === outClaim unless the carrier translated
 * Claims are H(did || chid || sid) as in the paper, one for each direction.
 *
 * Rule:
 *   sort attestations by hop; fewer than 2  -> "unknown" (does not block)
 *   for consecutive participants i < k: require outClaim_i === inClaim_k
 *   any mismatch -> "fail" (an UNDECLARED change happened between them)
 *   otherwise    -> "pass"
 *
 * A participating translator never causes a fail because it declares the change.
 * A NON-participating translator between two participants does: this is the
 * residual false-flag case measured in translation_sim.py.
 *
 * Caveat (for the paper): a participating MALICIOUS carrier can also declare a
 * rewrite as a "translation". Declaration turns that case from detection into
 * attribution (the change is signed by that carrier). Whether declared
 * translations should be restricted (e.g. to number-equivalent forms, or to
 * carriers registered as translators) is a policy question.
 */
const Tri = { PASS: "pass", UNKNOWN: "unknown", FAIL: "fail" };

function pathStatusDeclared(attestations, k = 2) {
  const atts = [...attestations].sort((x, y) => Number(x.hop) - Number(y.hop));
  if (atts.length < k) return { status: Tri.UNKNOWN, declared: [], mismatchAt: null };
  const declared = atts.filter((a) => a.inClaim !== a.outClaim).map((a) => Number(a.hop));
  for (let i = 0; i + 1 < atts.length; i++) {
    if (atts[i].outClaim !== atts[i + 1].inClaim) {
      return { status: Tri.FAIL, declared, mismatchAt: [Number(atts[i].hop), Number(atts[i + 1].hop)] };
    }
  }
  return { status: Tri.PASS, declared, mismatchAt: null };
}

// The current paper rule, for comparison: carriers attest only what they received.
function pathStatusUndeclared(receivedClaims, k = 2) {
  if (receivedClaims.length < k) return Tri.UNKNOWN;
  return receivedClaims.every((c) => c === receivedClaims[0]) ? Tri.PASS : Tri.FAIL;
}

module.exports = { Tri, pathStatusDeclared, pathStatusUndeclared };
