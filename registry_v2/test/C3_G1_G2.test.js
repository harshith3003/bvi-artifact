/**
 * C3, G1, G2 on BVIRegistry v2 (registered carriers, trusted-attestor filter on).
 */
const { expect } = require("chai");
const { ethers } = require("hardhat");
const { loadFixture } = require("@nomicfoundation/hardhat-network-helpers");
const { fixture } = require("./fixture");
const { Status, Tri, Outcome, CH, SID, claimOf, PK, merkleRoot, transcriptCommitment,
        pathStatus, combine, trustedAttestations, verify, audit } = require("./verifier");

const frames = (tag) => Array.from({ length: 50 }, (_, i) => CH(`${tag}-${i}`));
const GENUINE = merkleRoot(frames("genuine"));
const SUBSTITUTED = merkleRoot(frames("substituted"));
const SYNTHETIC = merkleRoot(frames("synthetic"));
const FAKE = CH("+61299990000");

const SENT = new Map(); // sid -> root of the audio the origin actually sent
async function session(ctx, tag, root, atts) {
  const { registry, bankCtl, carriers, did, chid } = ctx;
  const sid = SID(CH(`nonce:${tag}`), chid);
  for (const [hop, observed] of atts) {
    const c = claimOf(did, observed, sid);
    await registry.connect(carriers[hop]).attest(sid, hop, c, c, 0);
  }
  const ptr = transcriptCommitment(await trustedAttestations(registry, sid));
  await registry.connect(bankCtl).anchorSession(did, sid, root, ptr, 50, atts.length);
  SENT.set(sid, root);
  return sid;
}
// The live content check compares what was received with the authenticated stream of what was sent.
const check = (ctx, sid, received, detector) =>
  verify(ctx.registry, { did: ctx.did, presentedChid: ctx.chid, sid,
                         content: received === SENT.get(sid) ? Tri.PASS : Tri.FAIL, detector });
const log = (n, v) => console.log(`      ${n.padEnd(7)} L1=${v.l1} L2=${v.l2} L3=${v.l3} L4=${v.l4} -> ${v.outcome}`);

describe("C3 - partial path control (silent carriers ignored)", () => {
  it("C3a: 3 of 5 carriers attest and agree -> pass, verified", async () => {
    const ctx = await loadFixture(fixture);
    const sid = await session(ctx, "c3a", GENUINE, [[0, ctx.chid], [2, ctx.chid], [4, ctx.chid]]);
    const v = await check(ctx, sid, GENUINE, "live"); log("C3a", v);
    expect(v.l2).to.equal(Tri.PASS); expect(v.outcome).to.equal(Outcome.VERIFIED);
    expect((await audit(ctx.registry, { did: ctx.did, sid, receivedRoot: GENUINE })).ptrMatches).to.equal(true);
  });

  it("C3b: only 1 carrier attests -> unknown, does not block", async () => {
    const ctx = await loadFixture(fixture);
    const sid = await session(ctx, "c3b", GENUINE, [[0, ctx.chid]]);
    const v = await check(ctx, sid, GENUINE, "live"); log("C3b", v);
    expect(v.l2).to.equal(Tri.UNKNOWN); expect(v.outcome).to.equal(Outcome.VERIFIED);
  });

  it("C3c: no carrier attests -> unknown, does not block", async () => {
    const ctx = await loadFixture(fixture);
    const sid = await session(ctx, "c3c", GENUINE, []);
    const v = await check(ctx, sid, GENUINE, "live"); log("C3c", v);
    expect(v.l2).to.equal(Tri.UNKNOWN); expect(v.outcome).to.equal(Outcome.VERIFIED);
  });

  it("C3d: rewrite with an honest participant on each side -> caught (fail)", async () => {
    const ctx = await loadFixture(fixture);
    const sid = await session(ctx, "c3d", GENUINE, [[0, ctx.chid], [3, FAKE]]);
    const v = await check(ctx, sid, GENUINE, "live"); log("C3d", v);
    expect(v.l2).to.equal(Tri.FAIL); expect(v.outcome).to.equal(Outcome.FAIL);
  });

  it("C3e: honest participants only downstream -> missed, path passes on the rewritten ID", async () => {
    const ctx = await loadFixture(fixture);
    const sid = await session(ctx, "c3e", GENUINE, [[3, FAKE], [4, FAKE]]);
    const v = await check(ctx, sid, GENUINE, "live"); log("C3e", v);
    expect(v.l2).to.equal(Tri.PASS);
  });

  it("C3f: full collusion, all 5 attest the fake ID -> route check misses it (as in C2)", async () => {
    const ctx = await loadFixture(fixture);
    const sid = await session(ctx, "c3f", GENUINE, [0, 1, 2, 3, 4].map((h) => [h, FAKE]));
    const v = await check(ctx, sid, GENUINE, "live"); log("C3f", v);
    expect(v.l2).to.equal(Tri.PASS); expect(v.outcome).to.equal(Outcome.VERIFIED);
  });

  it("C3g: a colluder is worth the same as a non-participant for detection", async () => {
    const ctx = await loadFixture(fixture);
    const a = await check(ctx, await session(ctx, "c3g-A", GENUINE, [[0, FAKE], [3, FAKE]]), GENUINE, "live");
    const b = await check(ctx, await session(ctx, "c3g-B", GENUINE, [[3, FAKE]]), GENUINE, "live");
    log("C3g-A", a); log("C3g-B", b);
    expect(a.l2).to.not.equal(Tri.FAIL); expect(b.l2).to.not.equal(Tri.FAIL);
    expect(a.l2).to.equal(Tri.PASS); expect(b.l2).to.equal(Tri.UNKNOWN);
  });

  it("C3h: revoked originator -> Layer 1 fail even with a consistent path", async () => {
    const ctx = await loadFixture(fixture);
    const sid = await session(ctx, "c3h", GENUINE, [[0, ctx.chid], [1, ctx.chid], [2, ctx.chid]]);
    await ctx.registry.connect(ctx.registrar).setStatus(ctx.did, Status.Revoked);
    const v = await check(ctx, sid, GENUINE, "live"); log("C3h", v);
    expect(v.l1).to.equal(Tri.FAIL); expect(v.outcome).to.equal(Outcome.FAIL);
  });
});

describe("G1 - the protocol has no field for a score; Layer 4 can only demote", () => {
  const WORDS = /(score|liveness|deepfake|spoof|detector|detection|confidence|probability|synthetic|genuine|trust|risk)/i;

  it("G1a: no writable function, parameter or event field is designated for a score", async () => {
    const { registry } = await loadFixture(fixture);
    const frags = registry.interface.fragments;
    const writable = frags.filter((f) => f.type === "function" && f.stateMutability !== "view" && f.stateMutability !== "pure");
    for (const f of writable) {
      expect(WORDS.test(f.name), f.name).to.equal(false);
      for (const i of f.inputs) expect(WORDS.test(i.name || ""), `${f.name}.${i.name}`).to.equal(false);
    }
    for (const e of frags.filter((f) => f.type === "event")) {
      for (const i of e.inputs) expect(WORDS.test(i.name || ""), `${e.name}.${i.name}`).to.equal(false);
    }
  });

  it("G1b: a 'score' written into an existing on-chain field does not change the verdict", async () => {
    const ctx = await loadFixture(fixture);
    const { registry, registrar, otherCtl } = ctx;
    const sid = await session(ctx, "g1b", GENUINE, [[0, ctx.chid], [1, ctx.chid]]);
    const before = [await check(ctx, sid, GENUINE, "live"), await check(ctx, sid, GENUINE, "synthetic")];
    const evil = CH("did:bvi:scorewriter");
    await registry.connect(registrar).register(evil, PK("evil"), [], otherCtl.address);
    const score = ethers.zeroPadValue(ethers.toBeHex(100), 32);
    await registry.connect(otherCtl).anchorSession(evil, sid, score, score, 100, 1);
    const after = [await check(ctx, sid, GENUINE, "live"), await check(ctx, sid, GENUINE, "synthetic")];
    expect(after).to.deep.equal(before);
    expect(after[1].outcome).to.equal(Outcome.NOT_VERIFIED);
  });

  it("G1c: exhaustive - Layer 4 never promotes, never touches a crypto fail, never itself yields 'fail'", () => {
    const rank = { [Outcome.FAIL]: 0, [Outcome.NOT_VERIFIED]: 1, [Outcome.VERIFIED]: 2 };
    let n = 0;
    for (const l1 of [Tri.PASS, Tri.FAIL])
      for (const l2 of [Tri.PASS, Tri.UNKNOWN, Tri.FAIL])
        for (const l3 of [Tri.PASS, Tri.UNKNOWN, Tri.FAIL, Tri.UNVERIFIABLE]) {
          const base = combine(l1, l2, l3, "live");
          for (const l4 of ["live", "synthetic"]) {
            const out = combine(l1, l2, l3, l4);
            expect(rank[out]).to.be.at.most(rank[base]);
            if (base === Outcome.FAIL) expect(out).to.equal(Outcome.FAIL);
            else expect(out).to.not.equal(Outcome.FAIL);
            if (l4 === "synthetic") expect(out).to.not.equal(Outcome.VERIFIED);
            n++;
          }
        }
    expect(n).to.equal(48);
  });
});

describe("G2 - deepfake with a fully valid on-chain record", () => {
  it("G2a: valid credential + consistent path + matching digest + synthetic voice -> 'not verified'", async () => {
    const ctx = await loadFixture(fixture);
    const sid = await session(ctx, "g2a", SYNTHETIC, [[0, ctx.chid], [2, ctx.chid], [4, ctx.chid]]);
    const v = await check(ctx, sid, SYNTHETIC, "synthetic"); log("G2a", v);
    expect([v.l1, v.l2, v.l3]).to.deep.equal([Tri.PASS, Tri.PASS, Tri.PASS]);
    expect(v.outcome).to.equal(Outcome.NOT_VERIFIED);
  });

  it("G2b: four cases - exactly one verified; only the digest mismatch gives 'fail'", async () => {
    const ctx = await loadFixture(fixture);
    const sid = await session(ctx, "g2b", GENUINE, [[0, ctx.chid], [2, ctx.chid]]);
    const cases = [
      [GENUINE, "live", Outcome.VERIFIED], [GENUINE, "synthetic", Outcome.NOT_VERIFIED],
      [SUBSTITUTED, "live", Outcome.FAIL], [SUBSTITUTED, "synthetic", Outcome.FAIL],
    ];
    let verified = 0;
    for (const [root, det, exp] of cases) {
      const v = await check(ctx, sid, root, det);
      expect(v.outcome).to.equal(exp);
      if (v.outcome === Outcome.VERIFIED) verified++;
    }
    expect(verified).to.equal(1);
  });
});

describe("Path rule (paper Layer 2, v2)", () => {
  it("pathStatus: one vote per carrier; <2 unknown; chained agree pass; break or unroled change fail", () => {
    const a = (hop, carrier, i, o = i, translator = false) =>
      ({ hop, carrierId: CH(carrier), inClaim: CH(i), outClaim: CH(o), translator });
    expect(pathStatus([]).status).to.equal(Tri.UNKNOWN);
    expect(pathStatus([a(0, "x", "A"), a(3, "x", "A")]).status).to.equal(Tri.UNKNOWN); // same carrier twice
    expect(pathStatus([a(0, "x", "A"), a(3, "y", "A")]).status).to.equal(Tri.PASS);
    expect(pathStatus([a(0, "x", "A"), a(3, "y", "B")]).status).to.equal(Tri.FAIL);
    expect(pathStatus([a(0, "x", "A", "B", true), a(3, "y", "B")]).status).to.equal(Tri.PASS);
    expect(pathStatus([a(0, "x", "A", "B", false), a(3, "y", "B")]).status).to.equal(Tri.FAIL);
  });
});
