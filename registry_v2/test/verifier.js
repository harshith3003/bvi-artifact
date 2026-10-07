/**
 * verifier.js (v2) — off-chain verifier for BVIRegistry v2.
 *
 *   verified  <=>  L1 ok  AND  L2 != fail  AND  L3 ok  AND  L4 not flagged
 *
 * Outcomes: "fail" (a cryptographic check found something wrong),
 *           "not verified" (only the local liveness detector objected),
 *           "verified".
 *
 * Layer 2 (route check):
 *   - trusted-attestor filter ON by default: only attestations whose key is a
 *     currently Active registered carrier count; others are treated as silent;
 *   - one vote per carrier (carrierId), enforced on chain and re-checked here;
 *   - a declared change (inClaim != outClaim) by a carrier WITHOUT the translator
 *     role is an inconsistency -> "fail";
 *   - fewer than 2 counted carriers -> "unknown" (does not block);
 *   - consecutive counted carriers must chain: outClaim_i == inClaim_{i+1};
 *     any break is an undeclared change -> "fail"; otherwise "pass".
 *
 * LIVE VERDICT (round 5) - what the recipient decides during the call:
 *   content (l3) is the result of the live check of the AUTHENTICATED digest stream:
 *     "pass"          stream authenticated, every conclusive window <= threshold
 *     "fail"          stream authenticated, some conclusive window > threshold
 *     "unknown"       stream authenticated but no conclusive window (e.g. silence); does not block
 *     "unverifiable"  key message missing or invalid, stream stripped, or any tag fails
 *                     -> "not verified" (decision: stripped or failing stream is not verified)
 *   The content threshold is the per-codec threshold of the WORST codec declared on
 *   the path (origin in its signed key message, transcoders in their attestation),
 *   falling back to the pooled threshold if any hop up to the terminating carrier
 *   did not attest, since an undeclared hop could have transcoded.
 *
 * AFTER-CALL AUDIT - the anchor is written at teardown, so it is NOT part of the live
 * verdict: audit() checks the anchored root against the recipient's recomputed root
 * and ptr against H(T_c) of the counted transcript.
 */
const { ethers } = require("hardhat");

const Status = { Unregistered: 0, Active: 1, Suspended: 2, Revoked: 3 };
const Tri = { PASS: "pass", UNKNOWN: "unknown", FAIL: "fail", UNVERIFIABLE: "unverifiable" };
const Outcome = { VERIFIED: "verified", NOT_VERIFIED: "not verified", FAIL: "fail" };

const CH = (s) => ethers.keccak256(ethers.toUtf8Bytes(s));
const SID = (nonce, chid) =>
  ethers.keccak256(ethers.solidityPacked(["bytes32", "bytes32"], [nonce, chid]));
const claimOf = (did, chid, sid) =>
  ethers.keccak256(ethers.solidityPacked(["bytes32", "bytes32", "bytes32"], [did, chid, sid]));
const PK = (tag) => ethers.concat([CH("pk-a-" + tag), CH("pk-b-" + tag)]); // deterministic 64 bytes

/** H(T_c): commitment to the ordered path transcript (hop, carrierId, inClaim, outClaim). */
function transcriptCommitment(atts) {
  const rows = [...atts]
    .sort((a, b) => Number(a.hop) - Number(b.hop))
    .map((a) => [Number(a.hop), a.carrierId, a.inClaim, a.outClaim]);
  return ethers.keccak256(
    ethers.AbiCoder.defaultAbiCoder().encode(["tuple(uint8,bytes32,bytes32,bytes32)[]"], [rows])
  );
}

function merkleRoot(leaves) {
  if (leaves.length === 0) return ethers.ZeroHash;
  let level = leaves.slice();
  while (level.length > 1) {
    const next = [];
    for (let i = 0; i < level.length; i += 2) {
      const r = i + 1 < level.length ? level[i + 1] : level[i];
      next.push(ethers.keccak256(ethers.concat([level[i], r])));
    }
    level = next;
  }
  return level[0];
}

/** Pure route rule over already-filtered attestations (sorted by hop). */
function pathStatus(atts, k = 2) {
  const seen = new Set();
  const counted = [];
  for (const a of [...atts].sort((x, y) => Number(x.hop) - Number(y.hop))) {
    if (seen.has(a.carrierId)) continue; // one vote per carrier
    seen.add(a.carrierId);
    counted.push(a);
  }
  for (const a of counted) {
    if (a.inClaim !== a.outClaim && !a.translator) {
      return { status: Tri.FAIL, reason: "declared change without translator role", counted };
    }
  }
  if (counted.length < k) return { status: Tri.UNKNOWN, reason: "fewer than 2 carriers", counted };
  for (let i = 0; i + 1 < counted.length; i++) {
    if (counted[i].outClaim !== counted[i + 1].inClaim) {
      return { status: Tri.FAIL, reason: "undeclared change", counted,
               between: [Number(counted[i].hop), Number(counted[i + 1].hop)] };
    }
  }
  return { status: Tri.PASS, reason: "consistent", counted };
}

function combine(l1, l2, l3, l4) {
  if (l1 === Tri.FAIL || l2 === Tri.FAIL || l3 === Tri.FAIL) return Outcome.FAIL;
  if (l3 === Tri.UNVERIFIABLE) return Outcome.NOT_VERIFIED;   // stripped or failing stream
  if (l4 === "synthetic") return Outcome.NOT_VERIFIED;
  return Outcome.VERIFIED;
}

// Codec ids used in attest() and in the origin's signed key message.
const CODEC = { PASSTHROUGH: 0, G711U: 1, G711A: 2, OPUS16: 3, AMR122: 4, AMR475: 5 };
const CODEC_NAME = { 1: "g711u", 2: "g711a", 3: "opus16", 4: "amr122", 5: "amr475" };

/**
 * Content threshold for this path.
 *   thresholds = { pooled, g711u, g711a, opus16, amr122, amr475 } from the item-1 results
 *   originCodec = codec id from the origin's signed key message (undefined if absent)
 *   counted     = counted attestations (after the trusted filter, one per carrier)
 *   terminatingHop = hop index of the recipient's own carrier (known locally)
 */
function contentThreshold({ thresholds, originCodec, counted, terminatingHop }) {
  if (!CODEC_NAME[originCodec]) return { theta: thresholds.pooled, basis: "pooled: origin codec not declared" };
  if (terminatingHop === undefined || terminatingHop === null) {
    return { theta: thresholds.pooled, basis: "pooled: path length unknown" };
  }
  const attested = new Set(counted.map((a) => Number(a.hop)));
  for (let h = 0; h <= terminatingHop; h++) {
    if (!attested.has(h)) return { theta: thresholds.pooled, basis: `pooled: hop ${h} did not attest and could have transcoded` };
  }
  const names = [CODEC_NAME[originCodec]];
  for (const a of counted) if (Number(a.codec) !== 0 && CODEC_NAME[Number(a.codec)]) names.push(CODEC_NAME[Number(a.codec)]);
  let worst = names[0];
  for (const n of names) if (thresholds[n] > thresholds[worst]) worst = n;
  return { theta: thresholds[worst], basis: `worst declared codec: ${worst}`, codecs: names };
}

/** Live content status from the authenticated stream check. */
function streamStatus({ keyOk, tagsOk, maxWindowBer, theta }) {
  if (!keyOk || !tagsOk || tagsOk.length === 0 || tagsOk.some((t) => !t)) return Tri.UNVERIFIABLE;
  if (maxWindowBer === null || maxWindowBer === undefined || Number.isNaN(maxWindowBer)) return Tri.UNKNOWN;
  return maxWindowBer > theta ? Tri.FAIL : Tri.PASS;
}

async function trustedAttestations(registry, sid, trustAll = false) {
  const atts = Array.from(await registry.getAttestations(sid));
  if (trustAll) return atts;
  const out = [];
  for (const a of atts) {
    const h = await registry.hopOf(a.attestor);
    if (Number(h.status) === Status.Active && h.carrierId === a.carrierId) out.push(a);
  }
  return out;
}

/** LIVE verdict. `content` is the live stream status (see streamStatus). */
async function verify(registry, { did, presentedChid, sid, content, detector, trustAll = false }) {
  const rec = await registry.resolve(did);
  const l1 = Number(rec.status) === Status.Active &&
             (await registry.isAuthorisedChannel(did, presentedChid)) ? Tri.PASS : Tri.FAIL;
  const atts = await trustedAttestations(registry, sid, trustAll);
  const route = pathStatus(atts);
  return { outcome: combine(l1, route.status, content, detector), l1, l2: route.status, l3: content,
           l4: detector, reason: route.reason };
}

/** AFTER-CALL AUDIT against the anchor written at teardown (not part of the live verdict). */
async function audit(registry, { did, sid, receivedRoot, trustAll = false }) {
  const anchor = await registry.getAnchor(did, sid);
  if (anchor.anchoredBy === ethers.ZeroAddress) return { anchored: false, rootMatches: null, ptrMatches: null };
  const route = pathStatus(await trustedAttestations(registry, sid, trustAll));
  return { anchored: true, rootMatches: anchor.root === receivedRoot,
           ptrMatches: anchor.ptr === transcriptCommitment(route.counted),
           frames: Number(anchor.frames), hops: Number(anchor.hops) };
}

module.exports = {
  Status, Tri, Outcome, CH, SID, claimOf, PK, merkleRoot, transcriptCommitment,
  pathStatus, combine, trustedAttestations, verify, audit,
  CODEC, CODEC_NAME, contentThreshold, streamStatus,
};
