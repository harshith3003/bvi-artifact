/**
 * PROTECTIONS (item 2) on BVIRegistry v2
 *
 *   P1  slot squatting fails        P2  anchor squatting fails
 *   P3  unauthorised writes are rejected before any storage changes
 *   C4  attestation griefing        X4  domain separation (did, sid, chainid)
 *   C6  anchor front-running        D2  spam / storage bound per session
 *   T2  translator role, on chain + verifier
 */
const { expect } = require("chai");
const { ethers } = require("hardhat");
const { loadFixture } = require("@nomicfoundation/hardhat-network-helpers");
const { fixture } = require("./fixture");
const { Status, Tri, Outcome, CH, SID, claimOf, PK, merkleRoot, transcriptCommitment,
        trustedAttestations, verify, audit } = require("./verifier");

const ROOT = merkleRoot([CH("f0"), CH("f1"), CH("f2")]);

async function snapshot(registry, did, sid, who) {
  return {
    count: Number(await registry.attestationCount(sid)),
    anchor: (await registry.getAnchor(did, sid)).anchoredBy,
    rec: (await registry.resolve(did)).toObject(),
    hop: (await registry.hopOf(who)).toObject(),
  };
}

describe("P1 - attestation slot squatting fails", () => {
  it("an unregistered key cannot attest, and nothing is written", async () => {
    const { registry, attacker, did, chid } = await loadFixture(fixture);
    const sid = SID(CH("p1a"), chid);
    await expect(registry.connect(attacker).attest(sid, 1, claimOf(did, chid, sid), claimOf(did, chid, sid), 0))
      .to.be.revertedWithCustomError(registry, "NotRegisteredHop");
    expect(await registry.attestationCount(sid)).to.equal(0n);
  });

  it("slots are keyed by attester: an earlier writer at the same hop cannot lock out an honest carrier", async () => {
    const { registry, carriers, did, chid } = await loadFixture(fixture);
    const sid = SID(CH("p1b"), chid);
    const fake = claimOf(did, CH("+61299990000"), sid);
    await registry.connect(carriers[3]).attest(sid, 1, fake, fake, 0);           // writes first, at hop 1
    const real = claimOf(did, chid, sid);
    await registry.connect(carriers[1]).attest(sid, 1, real, real, 0);           // honest carrier still writes
    const atts = await registry.getAttestations(sid);
    expect(atts.map((a) => a.attestor)).to.have.members([carriers[3].address, carriers[1].address]);
  });

  it("a carrier attests at most once per session, even with a second key", async () => {
    const { registry, registrar, carriers, spare, did, chid } = await loadFixture(fixture);
    const sid = SID(CH("p1c"), chid);
    const c = claimOf(did, chid, sid);
    await registry.connect(carriers[0]).attest(sid, 0, c, c, 0);
    await expect(registry.connect(carriers[0]).attest(sid, 3, c, c, 0))
      .to.be.revertedWithCustomError(registry, "AlreadyAttested");
    await registry.connect(registrar).registerHop(CH("carrier-0"), spare.address, "second key", false);
    await expect(registry.connect(spare).attest(sid, 4, c, c, 0))
      .to.be.revertedWithCustomError(registry, "CarrierAlreadyAttested");
    expect(await registry.attestationCount(sid)).to.equal(1n);
  });

  it("suspended and revoked carriers cannot attest", async () => {
    const { registry, registrar, carriers, did, chid } = await loadFixture(fixture);
    const sid = SID(CH("p1d"), chid);
    const c = claimOf(did, chid, sid);
    await registry.connect(registrar).setHopStatus(carriers[1].address, Status.Suspended);
    await expect(registry.connect(carriers[1]).attest(sid, 1, c, c, 0))
      .to.be.revertedWithCustomError(registry, "HopNotActive");
    await registry.connect(registrar).setHopStatus(carriers[1].address, Status.Revoked);
    await expect(registry.connect(registrar).setHopStatus(carriers[1].address, Status.Active))
      .to.be.revertedWithCustomError(registry, "RevokedIsTerminal");
  });
});

describe("P2 - anchor squatting fails", () => {
  it("nobody but the organisation's controller can anchor under its DID", async () => {
    const { registry, registrar, attacker, carriers, did, chid } = await loadFixture(fixture);
    const sid = SID(CH("p2a"), chid);
    for (const who of [attacker, registrar, carriers[0]]) {
      await expect(registry.connect(who).anchorSession(did, sid, ROOT, CH("ptr"), 150, 2))
        .to.be.revertedWithCustomError(registry, "NotController");
    }
    expect((await registry.getAnchor(did, sid)).anchoredBy).to.equal(ethers.ZeroAddress);
  });

  it("an attacker's own organisation anchoring the same sid does not block the victim", async () => {
    const { registry, registrar, bankCtl, otherCtl, did, chid } = await loadFixture(fixture);
    const sid = SID(CH("p2b"), chid);
    const evil = CH("did:bvi:evilcorp");
    await registry.connect(registrar).register(evil, PK("evil"), [], otherCtl.address);
    await registry.connect(otherCtl).anchorSession(evil, sid, CH("evil-root"), CH("evil-ptr"), 150, 2);
    await registry.connect(bankCtl).anchorSession(did, sid, ROOT, CH("ptr"), 150, 2);
    expect((await registry.getAnchor(did, sid)).root).to.equal(ROOT);
    expect((await registry.getAnchor(evil, sid)).root).to.equal(CH("evil-root"));
  });

  it("a suspended or revoked organisation cannot anchor", async () => {
    const { registry, bankCtl, did, chid } = await loadFixture(fixture);
    await registry.connect(bankCtl).setStatus(did, Status.Suspended);
    await expect(registry.connect(bankCtl).anchorSession(did, SID(CH("p2c"), chid), ROOT, CH("ptr"), 150, 2))
      .to.be.revertedWithCustomError(registry, "DidNotActive");
  });

  it("an anchor is write-once, even for the organisation", async () => {
    const { registry, bankCtl, did, chid } = await loadFixture(fixture);
    const sid = SID(CH("p2d"), chid);
    await registry.connect(bankCtl).anchorSession(did, sid, ROOT, CH("ptr"), 150, 2);
    await expect(registry.connect(bankCtl).anchorSession(did, sid, CH("other"), CH("ptr"), 150, 2))
      .to.be.revertedWithCustomError(registry, "SessionAlreadyAnchored");
  });
});

describe("P3 - unauthorised writes are rejected before touching storage", () => {
  it("every unauthorised write reverts and leaves all state unchanged", async () => {
    const { registry, registrar, bankCtl, attacker, carriers, did, chid } = await loadFixture(fixture);
    const sid = SID(CH("p3"), chid);
    const c = claimOf(did, chid, sid);
    const before = await snapshot(registry, did, sid, carriers[0].address);

    const attempts = [
      [() => registry.connect(attacker).attest(sid, 0, c, c, 0), "NotRegisteredHop"],
      [() => registry.connect(attacker).anchorSession(did, sid, ROOT, CH("ptr"), 150, 2), "NotController"],
      [() => registry.connect(registrar).anchorSession(did, sid, ROOT, CH("ptr"), 150, 2), "NotController"],
      [() => registry.connect(bankCtl).addChannel(did, CH("+61399999999")), "NotRegistrar"],
      [() => registry.connect(registrar).rotateKey(did, PK("registrar-rotation")), "NotController"],
      [() => registry.connect(attacker).rotateKey(did, PK("attacker")), "NotController"],
      [() => registry.connect(attacker).setStatus(did, Status.Revoked), "NotAuthorisedToSetStatus"],
      [() => registry.connect(attacker).registerHop(CH("evil"), attacker.address, "", true), "NotRegistrar"],
      [() => registry.connect(attacker).setHopStatus(carriers[0].address, Status.Revoked), "NotRegistrar"],
      [() => registry.connect(attacker).register(CH("did:x"), PK("x"), [], attacker.address), "NotRegistrar"],
    ];
    for (const [send, err] of attempts) {
      await expect(send()).to.be.revertedWithCustomError(registry, err);
    }
    expect(await snapshot(registry, did, sid, carriers[0].address)).to.deep.equal(before);
    expect(await registry.isAuthorisedChannel(did, CH("+61399999999"))).to.equal(false);
  });
});

describe("C4 - attestation griefing (rerun on BVIRegistry v2)", () => {
  it("a carrier cannot attest under another carrier's identity", async () => {
    const { registry, carriers, did, chid } = await loadFixture(fixture);
    const sid = SID(CH("c4a"), chid);
    const c = claimOf(did, chid, sid);
    await registry.connect(carriers[3]).attest(sid, 0, c, c, 0);
    const [a] = await registry.getAttestations(sid);
    expect(a.carrierId).to.equal(CH("carrier-3")); // taken from the registry, not from the caller
  });

  it("out-of-range hops and empty claims are rejected", async () => {
    const { registry, carriers, did, chid } = await loadFixture(fixture);
    const sid = SID(CH("c4b"), chid);
    const c = claimOf(did, chid, sid);
    await expect(registry.connect(carriers[0]).attest(sid, 32, c, c, 0))
      .to.be.revertedWithCustomError(registry, "HopOutOfRange");
    await expect(registry.connect(carriers[0]).attest(sid, 0, ethers.ZeroHash, c, 0))
      .to.be.revertedWithCustomError(registry, "EmptyCommitment");
  });

  it("griefing attempts do not change an honest session's verdict", async () => {
    const { registry, bankCtl, carriers, attacker, did, chid } = await loadFixture(fixture);
    const sid = SID(CH("c4c"), chid);
    const c = claimOf(did, chid, sid);
    for (const i of [0, 1, 3]) await registry.connect(carriers[i]).attest(sid, i, c, c, 0);
    await expect(registry.connect(attacker).attest(sid, 2, CH("junk"), CH("junk"), 0))
      .to.be.revertedWithCustomError(registry, "NotRegisteredHop");
    const ptr = transcriptCommitment(await trustedAttestations(registry, sid));
    await registry.connect(bankCtl).anchorSession(did, sid, ROOT, ptr, 150, 3);
    const v = await verify(registry, { did, presentedChid: chid, sid, content: Tri.PASS, detector: "live" });
    expect(v.outcome).to.equal(Outcome.VERIFIED);
    expect((await audit(registry, { did, sid, receivedRoot: ROOT })).ptrMatches).to.equal(true);
  });
});

describe("X4 - anchors are keyed by (did, sid, chainid)", () => {
  it("the key commits to the chain id, so a record cannot be replayed as another chain's", async () => {
    const { registry, did, chid } = await loadFixture(fixture);
    const sid = SID(CH("x4"), chid);
    const { chainId } = await ethers.provider.getNetwork();
    const enc = (cid) => ethers.keccak256(
      ethers.AbiCoder.defaultAbiCoder().encode(["bytes32", "bytes32", "uint256"], [did, sid, cid]));
    expect(await registry.anchorKey(did, sid)).to.equal(enc(chainId));
    expect(await registry.anchorKey(did, sid)).to.not.equal(enc(chainId + 1n));
  });

  it("the key commits to the organisation, so the same sid under another DID is a different anchor", async () => {
    const { registry, did, chid } = await loadFixture(fixture);
    const sid = SID(CH("x4b"), chid);
    expect(await registry.anchorKey(did, sid)).to.not.equal(await registry.anchorKey(CH("did:bvi:other"), sid));
  });
});

describe("C6 - anchor front-running fails", () => {
  it("an observer of a pending anchor cannot write it first", async () => {
    const { registry, bankCtl, attacker, did, chid } = await loadFixture(fixture);
    const sid = SID(CH("c6"), chid);
    await expect(registry.connect(attacker).anchorSession(did, sid, CH("front"), CH("ptr"), 150, 2))
      .to.be.revertedWithCustomError(registry, "NotController");
    await registry.connect(bankCtl).anchorSession(did, sid, ROOT, CH("ptr"), 150, 2);
    expect((await registry.getAnchor(did, sid)).root).to.equal(ROOT);
  });
});

describe("D2 - spam is rejected without storage and per-session storage is bounded", () => {
  it("unregistered spam writes nothing and does not affect an honest session", async () => {
    const { registry, bankCtl, carriers, attacker, did, chid } = await loadFixture(fixture);
    const sid = SID(CH("d2a"), chid);
    for (let i = 0; i < 20; i++) {
      await expect(registry.connect(attacker).attest(sid, i % 32, CH("s" + i), CH("s" + i), 0))
        .to.be.revertedWithCustomError(registry, "NotRegisteredHop");
    }
    expect(await registry.attestationCount(sid)).to.equal(0n);
    const c = claimOf(did, chid, sid);
    await registry.connect(carriers[0]).attest(sid, 0, c, c, 0);
    await registry.connect(carriers[4]).attest(sid, 4, c, c, 0);
    await registry.connect(bankCtl).anchorSession(did, sid, ROOT, CH("ptr"), 150, 2);
    const v = await verify(registry, { did, presentedChid: chid, sid, content: Tri.PASS, detector: "live" });
    expect(v.l2).to.equal(Tri.PASS);
  });

  it("at most MAX_HOPS attestations can be stored per session", async () => {
    const { registry, registrar, did, chid } = await loadFixture(fixture);
    const sid = SID(CH("d2b"), chid);
    const c = claimOf(did, chid, sid);
    const wallets = [];
    for (let i = 0; i < 33; i++) {
      const w = ethers.Wallet.createRandom().connect(ethers.provider);
      await registrar.sendTransaction({ to: w.address, value: ethers.parseEther("1") });
      await registry.connect(registrar).registerHop(CH(`bulk-${i}`), w.address, "", false);
      wallets.push(w);
    }
    for (let i = 0; i < 32; i++) await registry.connect(wallets[i]).attest(sid, i, c, c, 0);
    await expect(registry.connect(wallets[32]).attest(sid, 31, c, c, 0))
      .to.be.revertedWithCustomError(registry, "TooManyAttestations");
    expect(await registry.attestationCount(sid)).to.equal(32n);
  });
});

describe("T2 - translator role (on chain and in the verifier)", () => {
  const E164 = CH("+61312345678");
  const NATIONAL = CH("0312345678");

  it("a carrier WITH the translator role declares a change and the route passes", async () => {
    const { registry, carriers, did, chid } = await loadFixture(fixture);
    const sid = SID(CH("t2a"), chid);
    await registry.connect(carriers[0]).attest(sid, 0, claimOf(did, E164, sid), claimOf(did, E164, sid), 0);
    await registry.connect(carriers[2]).attest(sid, 2, claimOf(did, E164, sid), claimOf(did, NATIONAL, sid), 0);
    await registry.connect(carriers[4]).attest(sid, 4, claimOf(did, NATIONAL, sid), claimOf(did, NATIONAL, sid), 0);
    const v = await verify(registry, { did, presentedChid: chid, sid, content: Tri.PASS, detector: "live" });
    expect(v.l2).to.equal(Tri.PASS);
  });

  it("a carrier WITHOUT the role that declares a change makes the route fail", async () => {
    const { registry, carriers, did, chid } = await loadFixture(fixture);
    const sid = SID(CH("t2b"), chid);
    await registry.connect(carriers[0]).attest(sid, 0, claimOf(did, E164, sid), claimOf(did, E164, sid), 0);
    await registry.connect(carriers[1]).attest(sid, 1, claimOf(did, E164, sid), claimOf(did, NATIONAL, sid), 0);
    await registry.connect(carriers[4]).attest(sid, 4, claimOf(did, NATIONAL, sid), claimOf(did, NATIONAL, sid), 0);
    const v = await verify(registry, { did, presentedChid: chid, sid, content: Tri.PASS, detector: "live" });
    expect(v.l2).to.equal(Tri.FAIL);
    expect(v.reason).to.equal("declared change without translator role");
  });

  it("the trusted-attestor filter (on by default) ignores a carrier revoked after it attested", async () => {
    const { registry, registrar, carriers, did, chid } = await loadFixture(fixture);
    const sid = SID(CH("t2c"), chid);
    const c = claimOf(did, chid, sid);
    await registry.connect(carriers[0]).attest(sid, 0, c, c, 0);
    await registry.connect(carriers[1]).attest(sid, 1, c, c, 0);
    await registry.connect(registrar).setHopStatus(carriers[1].address, Status.Revoked);
    expect((await trustedAttestations(registry, sid)).length).to.equal(1);
    expect((await trustedAttestations(registry, sid, true)).length).to.equal(2);
    const v = await verify(registry, { did, presentedChid: chid, sid, content: Tri.PASS, detector: "live" });
    expect(v.l2).to.equal(Tri.UNKNOWN); // one counted carrier left
  });
});
