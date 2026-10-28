/**
 * verifier_r.js (round 6): BVI-R and BVI-B route and codec rules, beside the round-5 verifier (BVI-0), which
 * is left unchanged. The rule logic is pure (plain objects in, plain objects out) so it can be unit-tested
 * without a chain; verifyConfigured() reads the registry and applies one configuration.
 *
 * Linked rule (BVI-R route), on records from attestLinked():
 *  1. Records a and b are LINKED when a.next == b.carrierId, b.prev == a.carrierId and b.hop == a.hop + 1.
 *     Maximal runs of linked records form segments.
 *  2. Admissible evidence: segments of two or more linked records, plus the record of the recipient's own
 *     terminating carrier. A record no neighbour confirms (isolated or off-path) is ignored, so it can neither
 *     launder a rewrite nor block an honest call.
 *  3. Admissible records must not share a hop, and a neighbour claim must not name a different carrier than an
 *     admissible record at that hop; either means someone lied about the route -> fail.
 *  4. Claims are compared within segments and ACROSS GAPS between consecutive segments; a declared change is
 *     allowed only for carriers with the translator role.
 *  5. COMPLETE = one admissible segment from hop 0 (prev = ORIGIN) to the terminating carrier.
 * Codec rules:
 *  carrier  (BVI-0): round-5 contentThreshold (worst declared codec; pooled if a hop up to T did not attest)
 *  chain    (BVI-R): worst of the origin codec and the codecs of a COMPLETE linked chain, else pooled
 *  endpoint (BVI-B): origin codec (signed) vs the recipient's received codec; equal -> that codec; different ->
 *                    strict: uncertain (not verified) | lenient: pooled
 */
const ORIGIN_TAG = "ORIGIN", RECIPIENT_TAG = "RECIPIENT";
const CODEC_NAME = { 1: "g711u", 2: "g711a", 3: "opus16", 4: "amr122", 5: "amr475" };
const Tri = { PASS: "pass", UNKNOWN: "unknown", FAIL: "fail", UNVERIFIABLE: "unverifiable", UNCERTAIN: "uncertain" };

function linkedPathStatus(records, { terminatingCarrier, presentedClaim, signedCallingClaim, ORIGIN, RECIPIENT }) {
  // records: [{ carrierId, hop, inClaim, outClaim, translator, codec, prev, next }]
  const by = new Map();
  for (const r of records) if (!by.has(r.carrierId)) by.set(r.carrierId, { ...r, hop: Number(r.hop) });
  const rs = [...by.values()];
  const succ = new Map(), pred = new Map();
  for (const a of rs) {
    const b = by.get(a.next);
    if (b && b.prev === a.carrierId && b.hop === a.hop + 1) { succ.set(a.carrierId, b); pred.set(b.carrierId, a); }
  }
  const segs = [];
  for (const r of rs) {
    if (pred.has(r.carrierId)) continue;
    const seg = [r]; let cur = r;
    while (succ.has(cur.carrierId)) { cur = succ.get(cur.carrierId); seg.push(cur); }
    if (seg.length >= 2 || r.carrierId === terminatingCarrier) segs.push(seg);
  }
  if (segs.length === 0) return { status: Tri.UNKNOWN, reason: "no linked evidence", admissible: [], complete: false };
  segs.sort((x, y) => x[0].hop - y[0].hop);
  const adm = segs.flat();
  const atHop = new Map();
  for (const r of adm) {
    if (atHop.has(r.hop) && atHop.get(r.hop) !== r.carrierId) return { status: Tri.FAIL, reason: "two linked records claim one hop", admissible: adm, complete: false };
    atHop.set(r.hop, r.carrierId);
  }
  for (const r of adm) {
    for (const [h, claim] of [[r.hop - 1, r.prev], [r.hop + 1, r.next]]) {
      if (atHop.has(h) && claim !== ORIGIN && claim !== RECIPIENT && atHop.get(h) !== claim) {
        return { status: Tri.FAIL, reason: "neighbour claim contradicts a linked record", admissible: adm, complete: false };
      }
    }
  }
  for (const r of adm) {
    if (r.inClaim !== r.outClaim && !r.translator) return { status: Tri.FAIL, reason: "declared change without translator role", admissible: adm, complete: false };
  }
  for (const s of segs) {
    for (let i = 0; i + 1 < s.length; i++) {
      if (s[i].outClaim !== s[i + 1].inClaim) return { status: Tri.FAIL, reason: "undeclared change inside a linked segment", admissible: adm, complete: false };
    }
  }
  for (let i = 0; i + 1 < segs.length; i++) {
    const a = segs[i][segs[i].length - 1], b = segs[i + 1][0];
    if (a.outClaim !== b.inClaim) return { status: Tri.FAIL, reason: "undeclared change across a gap", admissible: adm, complete: false, between: [a.hop, b.hop] };
  }
  const t = by.get(terminatingCarrier);
  if (t && adm.includes(t) && presentedClaim && t.outClaim !== presentedClaim) {
    return { status: Tri.FAIL, reason: "terminating carrier's claim differs from the presented number", admissible: adm, complete: false };
  }
  const first = segs[0][0];
  const complete = segs.length === 1 && first.hop === 0 && first.prev === ORIGIN && segs[0][segs[0].length - 1].carrierId === terminatingCarrier;
  if (signedCallingClaim && first.hop === 0 && first.prev === ORIGIN && first.inClaim !== signedCallingClaim) {
    return { status: Tri.FAIL, reason: "first carrier received a number other than the one the organisation signed", admissible: adm, complete };
  }
  if (adm.length < 2) return { status: Tri.UNKNOWN, reason: "only the terminating carrier's record", admissible: adm, complete };
  return { status: Tri.PASS, reason: "linked evidence consistent", admissible: adm, complete };
}

function worstCodec(thresholds, names) {
  let worst = names[0];
  for (const n of names) if (thresholds[n] > thresholds[worst]) worst = n;
  return worst;
}

function chainThreshold({ thresholds, originCodec, linked }) {
  if (!CODEC_NAME[originCodec]) return { theta: thresholds.pooled, basis: "pooled: origin codec not declared" };
  if (!linked.complete) return { theta: thresholds.pooled, basis: "pooled: no complete linked chain to the recipient's carrier" };
  const names = [CODEC_NAME[originCodec]];
  for (const r of linked.admissible) if (Number(r.codec) !== 0 && CODEC_NAME[Number(r.codec)]) names.push(CODEC_NAME[Number(r.codec)]);
  const w = worstCodec(thresholds, names);
  return { theta: thresholds[w], basis: `worst codec in the complete linked chain: ${w}` };
}

function endpointThreshold({ thresholds, originCodec, receivedCodec, strict }) {
  const a = CODEC_NAME[originCodec], b = CODEC_NAME[receivedCodec];
  if (a && a === b) return { theta: thresholds[a], basis: `endpoint codec ${a}` };
  if (strict) return { theta: null, basis: "uncertain: endpoint codecs differ" };
  return { theta: thresholds.pooled, basis: "pooled: endpoint codecs differ" };
}

/** Final verdict. identity: pass|fail; route: pass|unknown|fail|unused; content: pass|fail|unknown|unverifiable|uncertain */
function combineR({ identity, route, routeDecides, content, detector }) {
  if (identity === Tri.FAIL || (routeDecides && route === Tri.FAIL) || content === Tri.FAIL) return "fail";
  if (content === Tri.UNVERIFIABLE || content === Tri.UNCERTAIN) return "not verified";
  if (detector === "synthetic") return "not verified";
  return "verified";
}

const CONFIGS = {
  "BVI-0":                 { binding: false, route: "positional", stream: "v1",        codec: "carrier",          routeDecides: true },
  "BVI-R":                 { binding: true,  route: "linked",     stream: "v2",        codec: "chain",            routeDecides: true },
  "BVI-B (strict)":        { binding: true,  route: "none",       stream: "v2",        codec: "endpoint_strict",  routeDecides: false },
  "BVI-B (lenient)":       { binding: true,  route: "none",       stream: "v2",        codec: "endpoint_lenient", routeDecides: false },
  "R - number binding":    { binding: false, route: "linked",     stream: "v2",        codec: "chain",            routeDecides: true },
  "R - linked chain":      { binding: true,  route: "positional", stream: "v2",        codec: "carrier",          routeDecides: true },
  "R - auth. termination": { binding: true,  route: "linked",     stream: "v2_noterm", codec: "chain",            routeDecides: true },
  "R + endpoint strict":   { binding: true,  route: "linked",     stream: "v2",        codec: "endpoint_strict",  routeDecides: true },
};

/** Reads attestations and links from the registry (trusted-attestor filter as in round 5). */
async function linkedRecords(registry, sid, trustAll = false) {
  const { trustedAttestations } = require("./verifier");
  const atts = await trustedAttestations(registry, sid, trustAll);
  const out = [];
  for (const a of atts) {
    const l = await registry.getLinks(sid, a.attestor);
    out.push({ carrierId: a.carrierId, hop: Number(a.hop), inClaim: a.inClaim, outClaim: a.outClaim,
               translator: a.translator, codec: Number(a.codec), prev: l.prevCarrier, next: l.nextCarrier, attestor: a.attestor });
  }
  return out;
}

/** Live verdict under one configuration. identity: result of the credential + (if binding) key-message number
 *  checks from digest_auth_v2; stream: "ok"|"unverifiable" from the stream check of that configuration. */
async function verifyConfigured(registry, cfgName, { did, presentedChid, sid, identityOk, streamOk, maxWindowBer,
                                                    thresholds, originCodec, receivedCodec, terminatingCarrier,
                                                    terminatingHop, presentedClaim, signedCallingClaim, detector, trustAll = false }) {
  const { pathStatus, contentThreshold, Status } = require("./verifier");
  const { ethers } = require("hardhat");
  const ORIGIN = ethers.keccak256(ethers.toUtf8Bytes(ORIGIN_TAG)), RECIPIENT = ethers.keccak256(ethers.toUtf8Bytes(RECIPIENT_TAG));
  const cfg = CONFIGS[cfgName];
  const rec = await registry.resolve(did);
  const cred = Number(rec.status) === Status.Active && (await registry.isAuthorisedChannel(did, presentedChid));
  const identity = cred && identityOk ? Tri.PASS : Tri.FAIL;
  let route = "unused", theta;
  if (cfg.route === "positional") {
    const atts = await require("./verifier").trustedAttestations(registry, sid, trustAll);
    const p = pathStatus(atts); route = p.status;
    if (cfg.codec === "carrier") theta = contentThreshold({ thresholds, originCodec, counted: p.counted, terminatingHop });
  } else if (cfg.route === "linked") {
    const linked = linkedPathStatus(await linkedRecords(registry, sid, trustAll),
      { terminatingCarrier, presentedClaim, signedCallingClaim: cfg.binding ? signedCallingClaim : undefined, ORIGIN, RECIPIENT });
    route = linked.status;
    if (cfg.codec === "chain") theta = chainThreshold({ thresholds, originCodec, linked });
  }
  if (cfg.codec.startsWith("endpoint")) theta = endpointThreshold({ thresholds, originCodec, receivedCodec, strict: cfg.codec === "endpoint_strict" });
  let content;
  if (!streamOk) content = Tri.UNVERIFIABLE;
  else if (theta.theta === null) content = Tri.UNCERTAIN;
  else if (maxWindowBer === null || maxWindowBer === undefined || Number.isNaN(maxWindowBer)) content = Tri.UNKNOWN;
  else content = maxWindowBer > theta.theta ? Tri.FAIL : Tri.PASS;
  return { outcome: combineR({ identity, route, routeDecides: cfg.routeDecides, content, detector }),
           identity, route, content, theta: theta.theta, thetaBasis: theta.basis };
}

module.exports = { Tri, CONFIGS, ORIGIN_TAG, RECIPIENT_TAG, linkedPathStatus, chainThreshold, endpointThreshold,
                   combineR, linkedRecords, verifyConfigured };
