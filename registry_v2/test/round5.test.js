/**
 * ROUND 5 decisions, as tests.
 *   R1  a stripped or failing digest stream gives "not verified"
 *   R2  ptr and the anchored root belong to the after-call audit, not the live verdict
 *   R3  content threshold = worst codec declared on the path; pooled if an
 *       undeclared hop could have transcoded
 */
const { expect } = require("chai");
const { loadFixture } = require("@nomicfoundation/hardhat-network-helpers");
const { fixture } = require("./fixture");
const { Tri, Outcome, CH, SID, claimOf, transcriptCommitment, trustedAttestations, pathStatus,
        verify, audit, CODEC, contentThreshold, streamStatus } = require("./verifier");

// Test-fixture thresholds (the round-4 v1.2 calibration values). The live system
// uses the values from the held-out item-1 run, read from its results files.
const TH = { pooled: 0.548, g711u: 0.214, g711a: 0.211, opus16: 0.436, amr122: 0.552, amr475: 0.615 };

async function honestPath(ctx, tag, hops, codecs = {}) {
  const { registry, carriers, did, chid } = ctx;
  const sid = SID(CH(tag), chid);
  for (const h of hops) {
    const c = claimOf(did, chid, sid);
    await registry.connect(carriers[h]).attest(sid, h, c, c, codecs[h] || CODEC.PASSTHROUGH);
  }
  return sid;
}

describe("R1 - a stripped or failing stream is 'not verified'", () => {
  it("stream stripped (no key message): not verified, even with a perfect credential and path", async () => {
    const ctx = await loadFixture(fixture);
    const sid = await honestPath(ctx, "r1a", [0, 1, 2]);
    const content = streamStatus({ keyOk: false, tagsOk: [], maxWindowBer: null, theta: TH.g711u });
    const v = await verify(ctx.registry, { did: ctx.did, presentedChid: ctx.chid, sid, content, detector: "live" });
    expect([v.l1, v.l2, v.l3]).to.deep.equal([Tri.PASS, Tri.PASS, Tri.UNVERIFIABLE]);
    expect(v.outcome).to.equal(Outcome.NOT_VERIFIED);
  });

  it("any failing block tag: not verified (not 'fail')", async () => {
    const ctx = await loadFixture(fixture);
    const sid = await honestPath(ctx, "r1b", [0, 1]);
    const content = streamStatus({ keyOk: true, tagsOk: [true, true, false, true], maxWindowBer: 0.05, theta: TH.g711u });
    const v = await verify(ctx.registry, { did: ctx.did, presentedChid: ctx.chid, sid, content, detector: "live" });
    expect(v.outcome).to.equal(Outcome.NOT_VERIFIED);
  });

  it("authenticated stream: window above threshold -> fail; below -> pass; no conclusive window -> unknown", () => {
    const ok = { keyOk: true, tagsOk: [true, true] };
    expect(streamStatus({ ...ok, maxWindowBer: 0.30, theta: TH.g711u })).to.equal(Tri.FAIL);
    expect(streamStatus({ ...ok, maxWindowBer: 0.10, theta: TH.g711u })).to.equal(Tri.PASS);
    expect(streamStatus({ ...ok, maxWindowBer: null, theta: TH.g711u })).to.equal(Tri.UNKNOWN);
  });
});

describe("R2 - the anchor belongs to the after-call audit, not the live verdict", () => {
  it("a wrong ptr does not change the live verdict; the audit reports it", async () => {
    const ctx = await loadFixture(fixture);
    const sid = await honestPath(ctx, "r2a", [0, 1, 2]);
    const live = await verify(ctx.registry, { did: ctx.did, presentedChid: ctx.chid, sid, content: Tri.PASS, detector: "live" });
    await ctx.registry.connect(ctx.bankCtl).anchorSession(ctx.did, sid, CH("root"), CH("WRONG-ptr"), 3000, 3);
    const liveAfter = await verify(ctx.registry, { did: ctx.did, presentedChid: ctx.chid, sid, content: Tri.PASS, detector: "live" });
    expect(liveAfter).to.deep.equal(live);
    expect(live.outcome).to.equal(Outcome.VERIFIED);
    const a = await audit(ctx.registry, { did: ctx.did, sid, receivedRoot: CH("root") });
    expect(a).to.include({ anchored: true, rootMatches: true, ptrMatches: false });
  });

  it("the audit reports a correct ptr and a root mismatch independently", async () => {
    const ctx = await loadFixture(fixture);
    const sid = await honestPath(ctx, "r2b", [0, 3]);
    const ptr = transcriptCommitment(await trustedAttestations(ctx.registry, sid));
    await ctx.registry.connect(ctx.bankCtl).anchorSession(ctx.did, sid, CH("sent-root"), ptr, 3000, 2);
    const a = await audit(ctx.registry, { did: ctx.did, sid, receivedRoot: CH("other-root") });
    expect(a).to.include({ anchored: true, rootMatches: false, ptrMatches: true });
  });

  it("before teardown there is no anchor, and the live verdict does not need one", async () => {
    const ctx = await loadFixture(fixture);
    const sid = await honestPath(ctx, "r2c", [0, 1]);
    expect((await audit(ctx.registry, { did: ctx.did, sid, receivedRoot: CH("x") })).anchored).to.equal(false);
    const v = await verify(ctx.registry, { did: ctx.did, presentedChid: ctx.chid, sid, content: Tri.PASS, detector: "live" });
    expect(v.outcome).to.equal(Outcome.VERIFIED);
  });
});

describe("R3 - content threshold from the codecs declared on the path", () => {
  const counted = async (ctx, sid) => pathStatus(await trustedAttestations(ctx.registry, sid)).counted;

  it("codec declarations are stored on chain with the attestation", async () => {
    const ctx = await loadFixture(fixture);
    const sid = await honestPath(ctx, "r3a", [0, 1, 2], { 1: CODEC.AMR475 });
    const atts = await ctx.registry.getAttestations(sid);
    expect(atts.map((a) => Number(a.codec))).to.deep.equal([0, CODEC.AMR475, 0]);
  });

  it("every hop attests, nobody transcodes -> the origin codec's threshold", async () => {
    const ctx = await loadFixture(fixture);
    const sid = await honestPath(ctx, "r3b", [0, 1, 2]);
    const t = contentThreshold({ thresholds: TH, originCodec: CODEC.G711U, counted: await counted(ctx, sid), terminatingHop: 2 });
    expect(t.theta).to.equal(TH.g711u);
  });

  it("a transcoder declares AMR-NB 4.75 -> the worst declared codec's threshold", async () => {
    const ctx = await loadFixture(fixture);
    const sid = await honestPath(ctx, "r3c", [0, 1, 2], { 1: CODEC.AMR475 });
    const t = contentThreshold({ thresholds: TH, originCodec: CODEC.G711U, counted: await counted(ctx, sid), terminatingHop: 2 });
    expect(t.theta).to.equal(TH.amr475);
    expect(t.basis).to.equal("worst declared codec: amr475");
  });

  it("a hop that did not attest could have transcoded -> pooled threshold", async () => {
    const ctx = await loadFixture(fixture);
    const sid = await honestPath(ctx, "r3d", [0, 2]);
    const t = contentThreshold({ thresholds: TH, originCodec: CODEC.G711U, counted: await counted(ctx, sid), terminatingHop: 2 });
    expect(t.theta).to.equal(TH.pooled);
    expect(t.basis).to.match(/hop 1 did not attest/);
  });

  it("origin codec not declared, or path length unknown -> pooled threshold", async () => {
    const ctx = await loadFixture(fixture);
    const sid = await honestPath(ctx, "r3e", [0, 1]);
    const c = await counted(ctx, sid);
    expect(contentThreshold({ thresholds: TH, originCodec: undefined, counted: c, terminatingHop: 1 }).theta).to.equal(TH.pooled);
    expect(contentThreshold({ thresholds: TH, originCodec: CODEC.G711U, counted: c }).theta).to.equal(TH.pooled);
  });
});
