/**
 * ROUND 6: linked carrier records (BVI-R) on the real contract, and the eight configurations end to end.
 * Every attack is checked against the original rule (BVI-0 / positional) and the corrected rule (linked).
 */
const { expect } = require("chai");
const { ethers } = require("hardhat");
const { loadFixture } = require("@nomicfoundation/hardhat-network-helpers");
const { fixture } = require("./fixture");
const { CH, SID, claimOf, pathStatus, trustedAttestations, contentThreshold, CODEC } = require("./verifier");
const { CONFIGS, linkedPathStatus, chainThreshold, endpointThreshold, linkedRecords, verifyConfigured } = require("./verifier_r");

const ORIGIN = ethers.keccak256(ethers.toUtf8Bytes("ORIGIN"));
const RECIPIENT = ethers.keccak256(ethers.toUtf8Bytes("RECIPIENT"));
const ID = (i) => CH(`carrier-${i}`);
const ORG_A2 = "+61312340000";                         // the organisation's second authorised number
// Held-out round-5 thresholds (pause rule on), as used in the paper.
const TH = { pooled: 0.4554, g711u: 0.2147, g711a: 0.2124, opus16: 0.3163, amr122: 0.4042, amr475: 0.5000 };

/** carriers: list of [carrierIndex, hop, inClaim, outClaim, prevId, nextId, codec] */
async function writeLinked(ctx, sid, rows) {
  for (const [i, hop, inn, out, prev, next, codec] of rows) {
    await ctx.registry.connect(ctx.carriers[i]).attestLinked(sid, hop, inn, out, codec || CODEC.PASSTHROUGH,
      { prevCarrier: prev, nextCarrier: next });
  }
}
const ctxRule = (T, presented, signed) => ({ terminatingCarrier: ID(T), presentedClaim: presented, signedCallingClaim: signed, ORIGIN, RECIPIENT });

describe("ROUND 6 - attestLinked on the contract", () => {
  it("stores the neighbour links and the same attestation fields as attest()", async () => {
    const ctx = await loadFixture(fixture); const sid = SID(CH("r6-links"), ctx.chid); const c = claimOf(ctx.did, ctx.chid, sid);
    await writeLinked(ctx, sid, [[0, 0, c, c, ORIGIN, ID(1)], [1, 1, c, c, ID(0), ID(3)], [3, 2, c, c, ID(1), RECIPIENT]]);
    const l = await ctx.registry.getLinks(sid, ctx.carriers[1].address);
    expect(l.prevCarrier).to.equal(ID(0)); expect(l.nextCarrier).to.equal(ID(3));
    const atts = await ctx.registry.getAttestations(sid);
    expect(atts.length).to.equal(3); expect(atts[1].carrierId).to.equal(ID(1)); expect(Number(atts[2].hop)).to.equal(2);
  });

  it("keeps every write protection of attest() and rejects empty links", async () => {
    const ctx = await loadFixture(fixture); const sid = SID(CH("r6-protect"), ctx.chid); const c = claimOf(ctx.did, ctx.chid, sid);
    const L = { prevCarrier: ORIGIN, nextCarrier: ID(1) };
    await expect(ctx.registry.connect(ctx.attacker).attestLinked(sid, 0, c, c, 0, L)).to.be.revertedWithCustomError(ctx.registry, "NotRegisteredHop");
    await expect(ctx.registry.connect(ctx.carriers[0]).attestLinked(sid, 0, c, c, 0, { prevCarrier: ethers.ZeroHash, nextCarrier: ID(1) }))
      .to.be.revertedWithCustomError(ctx.registry, "ZeroCarrier");
    await ctx.registry.connect(ctx.carriers[0]).attest(sid, 0, c, c, 0);
    await expect(ctx.registry.connect(ctx.carriers[0]).attestLinked(sid, 0, c, c, 0, L)).to.be.revertedWithCustomError(ctx.registry, "AlreadyAttested");
    await expect(ctx.registry.connect(ctx.carriers[1]).attestLinked(ethers.ZeroHash, 1, c, c, 0, L)).to.be.revertedWithCustomError(ctx.registry, "ZeroSession");
  });
});

describe("ROUND 6 - linked rule vs the original positional rule, on chain", () => {
  async function launderingCall(ctx) {
    // path c0 (hop 0) -> c4 (hop 1) -> c1 (hop 2, silent rewriter) -> c3 (hop 3, recipient's carrier)
    await ctx.registry.connect(ctx.registrar).addChannel(ctx.did, CH(ORG_A2));
    const sid = SID(CH("r6-launder"), ctx.chid);
    const A = claimOf(ctx.did, ctx.chid, sid), F = claimOf(ctx.did, CH(ORG_A2), sid);
    await writeLinked(ctx, sid, [[0, 0, A, A, ORIGIN, ID(4)], [4, 1, A, A, ID(0), ID(1)], [3, 3, F, F, ID(1), RECIPIENT]]);
    // off-path translator c2 bridges the rewriter's hop, claiming the real neighbours
    await writeLinked(ctx, sid, [[2, 2, A, F, ID(4), ID(3)]]);
    return { sid, A, F };
  }

  it("off-path record laundering: the positional rule passes it, the linked rule fails it", async () => {
    const ctx = await loadFixture(fixture); const { sid, F } = await launderingCall(ctx);
    expect(pathStatus(await trustedAttestations(ctx.registry, sid)).status).to.equal("pass");          // BVI-0: laundered
    const linked = linkedPathStatus(await linkedRecords(ctx.registry, sid), ctxRule(3, F));
    expect(linked.status).to.equal("fail"); expect(linked.reason).to.contain("across a gap");
  });

  it("a false off-path record blocks an honest call under the positional rule, not the linked rule", async () => {
    const ctx = await loadFixture(fixture); const sid = SID(CH("r6-dos"), ctx.chid);
    const A = claimOf(ctx.did, ctx.chid, sid), X = claimOf(ctx.did, CH("+61399999999"), sid);
    await writeLinked(ctx, sid, [[0, 0, A, A, ORIGIN, ID(1)], [1, 1, A, A, ID(0), ID(3)], [3, 2, A, A, ID(1), RECIPIENT]]);
    await writeLinked(ctx, sid, [[4, 1, A, X, ID(0), ID(3)]]);                     // c4 is not a translator
    expect(pathStatus(await trustedAttestations(ctx.registry, sid)).status).to.equal("fail");          // BVI-0: honest call blocked
    expect(linkedPathStatus(await linkedRecords(ctx.registry, sid), ctxRule(3, A)).status).to.equal("pass");
  });

  it("off-path codec manipulation raises the BVI-0 threshold but is ignored by BVI-R and BVI-B", async () => {
    const ctx = await loadFixture(fixture); const sid = SID(CH("r6-codec-off"), ctx.chid); const A = claimOf(ctx.did, ctx.chid, sid);
    await writeLinked(ctx, sid, [[0, 0, A, A, ORIGIN, ID(1)], [1, 1, A, A, ID(0), ID(3)], [3, 2, A, A, ID(1), RECIPIENT]]);
    await writeLinked(ctx, sid, [[4, 1, A, A, ID(0), ID(3), CODEC.AMR475]]);
    const carrier = contentThreshold({ thresholds: TH, originCodec: CODEC.G711U, counted: pathStatus(await trustedAttestations(ctx.registry, sid)).counted, terminatingHop: 2 });
    expect(carrier.theta).to.equal(TH.amr475);
    const linked = linkedPathStatus(await linkedRecords(ctx.registry, sid), ctxRule(3, A));
    expect(chainThreshold({ thresholds: TH, originCodec: CODEC.G711U, linked }).theta).to.equal(TH.g711u);
    expect(endpointThreshold({ thresholds: TH, originCodec: CODEC.G711U, receivedCodec: CODEC.G711U, strict: true }).theta).to.equal(TH.g711u);
  });

  it("documented residual: an ON-path carrier lying about its codec is accepted by BVI-R, not by BVI-B", async () => {
    const ctx = await loadFixture(fixture); const sid = SID(CH("r6-codec-on"), ctx.chid); const A = claimOf(ctx.did, ctx.chid, sid);
    await writeLinked(ctx, sid, [[0, 0, A, A, ORIGIN, ID(1)], [1, 1, A, A, ID(0), ID(3), CODEC.AMR475], [3, 2, A, A, ID(1), RECIPIENT]]);
    const linked = linkedPathStatus(await linkedRecords(ctx.registry, sid), ctxRule(3, A));
    expect(chainThreshold({ thresholds: TH, originCodec: CODEC.G711U, linked }).theta).to.equal(TH.amr475);
    expect(endpointThreshold({ thresholds: TH, originCodec: CODEC.G711U, receivedCodec: CODEC.G711U, strict: true }).theta).to.equal(TH.g711u);
  });

  it("full collusion with consistent false records: caught only through number binding", async () => {
    const ctx = await loadFixture(fixture);
    await ctx.registry.connect(ctx.registrar).addChannel(ctx.did, CH(ORG_A2));
    const sid = SID(CH("r6-collude"), ctx.chid);
    const A = claimOf(ctx.did, ctx.chid, sid), F = claimOf(ctx.did, CH(ORG_A2), sid);
    await writeLinked(ctx, sid, [[0, 0, F, F, ORIGIN, ID(1)], [1, 1, F, F, ID(0), ID(3)], [3, 2, F, F, ID(1), RECIPIENT]]);
    expect(pathStatus(await trustedAttestations(ctx.registry, sid)).status).to.equal("pass");
    expect(linkedPathStatus(await linkedRecords(ctx.registry, sid), ctxRule(3, F)).status).to.equal("pass");
    expect(linkedPathStatus(await linkedRecords(ctx.registry, sid), ctxRule(3, F, A)).status).to.equal("fail");
  });
});

describe("ROUND 6 - the eight configurations on the laundering attack (on chain)", () => {
  it("only configurations without number binding AND without the linked rule verify the laundered call", async () => {
    const ctx = await loadFixture(fixture);
    await ctx.registry.connect(ctx.registrar).addChannel(ctx.did, CH(ORG_A2));
    const sid = SID(CH("r6-launder-cfg"), ctx.chid);
    const A = claimOf(ctx.did, ctx.chid, sid), F = claimOf(ctx.did, CH(ORG_A2), sid);
    await writeLinked(ctx, sid, [[0, 0, A, A, ORIGIN, ID(4)], [4, 1, A, A, ID(0), ID(1)], [3, 3, F, F, ID(1), RECIPIENT]]);
    await writeLinked(ctx, sid, [[2, 2, A, F, ID(4), ID(3)]]);
    const rows = {};
    for (const name of Object.keys(CONFIGS)) {
      const cfg = CONFIGS[name];
      // number binding (digest_auth_v2 test R4): the signed calling number is A, the presented one is ORG_A2
      const identityOk = !cfg.binding;
      const r = await verifyConfigured(ctx.registry, name, {
        did: ctx.did, presentedChid: CH(ORG_A2), sid, identityOk, streamOk: true, maxWindowBer: 0.12,
        thresholds: TH, originCodec: CODEC.G711U, receivedCodec: CODEC.G711U, terminatingCarrier: ID(3), terminatingHop: 3,
        presentedClaim: F, signedCallingClaim: A });
      rows[name] = `${r.outcome} (identity ${r.identity}, route ${r.route}, audio ${r.content})`;
    }
    console.log("      laundering attack under each configuration:");
    for (const [k, v] of Object.entries(rows)) console.log(`        ${k.padEnd(24)} ${v}`);
    expect(rows["BVI-0"]).to.match(/^verified/);
    expect(rows["R - number binding"]).to.match(/^fail .*route fail/);
    expect(rows["R - linked chain"]).to.match(/^fail .*identity fail.*route pass/);   // route laundered, identity catches it
    for (const n of ["BVI-R", "BVI-B (strict)", "BVI-B (lenient)", "R - auth. termination", "R + endpoint strict"]) expect(rows[n]).to.match(/^fail/);
  });
});

describe("ROUND 6 - gas: attestLinked vs the unchanged attest()", () => {
  it("measures first and subsequent attestations for both functions", async () => {
    const ctx = await loadFixture(fixture);
    const gas = async (tx) => Number((await (await tx).wait()).gasUsed);
    const s1 = SID(CH("r6-gas-a"), ctx.chid), c1 = claimOf(ctx.did, ctx.chid, s1);
    const a0 = await gas(ctx.registry.connect(ctx.carriers[0]).attest(s1, 0, c1, c1, 0));
    const a1 = await gas(ctx.registry.connect(ctx.carriers[1]).attest(s1, 1, c1, c1, 0));
    const s2 = SID(CH("r6-gas-b"), ctx.chid), c2 = claimOf(ctx.did, ctx.chid, s2);
    const l0 = await gas(ctx.registry.connect(ctx.carriers[0]).attestLinked(s2, 0, c2, c2, 0, { prevCarrier: ORIGIN, nextCarrier: ID(1) }));
    const l1 = await gas(ctx.registry.connect(ctx.carriers[1]).attestLinked(s2, 1, c2, c2, 0, { prevCarrier: ID(0), nextCarrier: RECIPIENT }));
    console.log(`      attest():       first ${a0}, subsequent ${a1}`);
    console.log(`      attestLinked(): first ${l0}, subsequent ${l1}  (+${l0 - a0} / +${l1 - a1} gas for the two links)`);
    expect(l0).to.be.greaterThan(a0); expect(l1 - a1).to.be.lessThan(60000);
  });
});
