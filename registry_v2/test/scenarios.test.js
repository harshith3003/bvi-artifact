const { expect } = require("chai");
const { ethers } = require("hardhat");
const { loadFixture } = require("@nomicfoundation/hardhat-network-helpers");
const { fixture } = require("./fixture");
const { Status, Tri, Outcome, CH, SID, claimOf, PK, merkleRoot, pathStatus,
        trustedAttestations, verify } = require("./verifier");

/**
 * ATTACK SCENARIOS - the rows of Table II, executed on BVIRegistry v2.
 *
 * Order and names follow Table II exactly:
 *   A1 identifier spoofing          A7 expired credential use
 *   A2 forged issuer                A8 in-path identifier rewriting
 *   A3 credential theft             A9 in-transit media substitution
 *   A4 assertion replay             A10 credential-valid synthesis
 *   A5 credential tampering         A11 live human under a valid credential
 *   A6 revoked credential use
 *
 * Renumbering from the previous suite: old A7 -> A4, old A4 -> A5,
 * old A5 -> A6, old A6 -> A7. A11 is new (stated limitation).
 *
 * The final block is a real check: it fails unless every row of TABLE_II has
 * exactly one describe block, in table order, whose tests all passed.
 */

const TABLE_II = [
  ["A1", "identifier spoofing", "Layer 1"],
  ["A2", "forged issuer", "Layer 1"],
  ["A3", "credential theft", "Layer 1 + revocation (window stated)"],
  ["A4", "assertion replay", "Layer 3 session binding"],
  ["A5", "credential tampering", "Layer 1"],
  ["A6", "revoked credential use", "Layer 1"],
  ["A7", "expired credential use", "Layer 1"],
  ["A8", "in-path identifier rewriting", "Layer 2 (unknown when unobserved)"],
  ["A9", "in-transit media substitution", "Layer 3 digest"],
  ["A10", "credential-valid synthesis", "Layer 4 (demote only)"],
  ["A11", "live human under a valid credential", "not defended (stated limitation)"],
];
const title = (id) => { const r = TABLE_II.find((x) => x[0] === id); return `${r[0]} - ${r[1]}`; };
const ROOT = merkleRoot([CH("genuine-0"), CH("genuine-1")]);

async function layer1Verdict(registry, did, channelHash) {
  const rec = await registry.resolve(did);
  if (Number(rec.status) !== Status.Active) return { pass: false, reason: "status" };
  if (!(await registry.isAuthorisedChannel(did, channelHash))) return { pass: false, reason: "channel" };
  return { pass: true, record: rec };
}

describe(title("A1"), () => {
  it("an unregistered DID resolves to Unregistered and fails Layer 1", async () => {
    const { registry } = await loadFixture(fixture);
    const v = await layer1Verdict(registry, CH("did:bvi:notabank"), CH("+61300000000"));
    expect(v.pass).to.equal(false);
    expect(v.reason).to.equal("status");
  });

  it("an unregistered party cannot write attestations or anchors at all", async () => {
    const { registry, attacker } = await loadFixture(fixture);
    const sid = SID(CH("n"), CH("c"));
    await expect(registry.connect(attacker).attest(sid, 0, CH("claim"), CH("claim"), 0))
      .to.be.revertedWithCustomError(registry, "NotRegisteredHop");
    await expect(registry.connect(attacker).anchorSession(CH("did:bvi:notabank"), sid, CH("r"), CH("p"), 1, 1))
      .to.be.revertedWithCustomError(registry, "UnknownDid");
  });
});

describe(title("A2"), () => {
  it("a key not matching the on-chain hash fails verification", async () => {
    const { registry, did } = await loadFixture(fixture);
    const rec = await registry.resolve(did);
    expect(ethers.keccak256(PK("forged"))).to.not.equal(rec.pubKeyHash);
    expect(ethers.keccak256(PK("bank"))).to.equal(rec.pubKeyHash);
  });

  it("an attacker cannot issue (register) a credential", async () => {
    const { registry, attacker } = await loadFixture(fixture);
    await expect(registry.connect(attacker).register(CH("did:bvi:fakebank"), PK("fake"), [], attacker.address))
      .to.be.revertedWithCustomError(registry, "NotRegistrar");
  });

  it("a registered organisation cannot claim another organisation's number", async () => {
    const { registry, registrar, otherCtl, chid } = await loadFixture(fixture);
    const fakeDid = CH("did:bvi:fakebank");
    await registry.connect(registrar).register(fakeDid, PK("fake"), [], otherCtl.address);
    expect(await registry.isAuthorisedChannel(fakeDid, chid)).to.equal(false);
    await expect(registry.connect(otherCtl).addChannel(fakeDid, chid))
      .to.be.revertedWithCustomError(registry, "NotRegistrar");
  });
});

describe(title("A3"), () => {
  it("revocation terminates a stolen credential immediately", async () => {
    const { registry, registrar, did, chid } = await loadFixture(fixture);
    expect((await layer1Verdict(registry, did, chid)).pass).to.equal(true);
    await registry.connect(registrar).setStatus(did, Status.Revoked);
    const v = await layer1Verdict(registry, did, chid);
    expect(v.pass).to.equal(false);
    expect(v.reason).to.equal("status");
  });

  it("the thief cannot undo the revocation", async () => {
    const { registry, registrar, bankCtl, attacker, did } = await loadFixture(fixture);
    await registry.connect(registrar).setStatus(did, Status.Revoked);
    await expect(registry.connect(attacker).setStatus(did, Status.Active))
      .to.be.revertedWithCustomError(registry, "NotAuthorisedToSetStatus");
    // even the stolen controller key cannot undo it
    await expect(registry.connect(bankCtl).setStatus(did, Status.Active))
      .to.be.revertedWithCustomError(registry, "RevokedIsTerminal");
  });

  it("THE STATED GAP: sessions anchored before revocation still verify, inside a provable window", async () => {
    const { registry, registrar, bankCtl, did, chid } = await loadFixture(fixture);
    const sid = SID(CH("pre-revocation"), chid);
    await registry.connect(bankCtl).anchorSession(did, sid, ROOT, CH("ptr"), 150, 2);
    const before = await registry.getAnchor(did, sid);
    await registry.connect(registrar).setStatus(did, Status.Revoked);
    const rec = await registry.resolve(did);
    expect(before.blockTime).to.be.lessThanOrEqual(rec.updatedAt);
    expect((await registry.getAnchor(did, sid)).root).to.equal(before.root);
    // and no new session can be anchored after revocation
    await expect(registry.connect(bankCtl).anchorSession(did, SID(CH("post"), chid), ROOT, CH("ptr"), 150, 2))
      .to.be.revertedWithCustomError(registry, "DidNotActive");
  });
});

describe(title("A4"), () => {
  it("session binding: an anchor for one sid has no effect on another", async () => {
    const { registry, bankCtl, did, chid } = await loadFixture(fixture);
    const sidA = SID(CH("nonce-call-A"), chid);
    const sidB = SID(CH("nonce-call-B"), chid);
    await registry.connect(bankCtl).anchorSession(did, sidA, ROOT, CH("ptr"), 150, 2);
    expect((await registry.getAnchor(did, sidA)).root).to.equal(ROOT);
    expect((await registry.getAnchor(did, sidB)).root).to.equal(ethers.ZeroHash);
  });

  it("an attestation is bound to its session and cannot be transplanted", async () => {
    const { registry, carriers, did, chid } = await loadFixture(fixture);
    const sidA = SID(CH("nonce-A"), chid);
    const sidB = SID(CH("nonce-B"), chid);
    const c = claimOf(did, chid, sidA);
    await registry.connect(carriers[0]).attest(sidA, 0, c, c, 0);
    expect((await registry.getAttestations(sidA)).length).to.equal(1);
    expect((await registry.getAttestations(sidB)).length).to.equal(0);
  });

  it("the same nonce with a different channel yields a different session", async () => {
    const { registry, bankCtl, did } = await loadFixture(fixture);
    const nonce = CH("shared-nonce");
    const sid1 = SID(nonce, CH("+61312345678"));
    const sid2 = SID(nonce, CH("+61398765432"));
    expect(sid1).to.not.equal(sid2);
    await registry.connect(bankCtl).anchorSession(did, sid1, ROOT, CH("ptr"), 150, 2);
    expect((await registry.getAnchor(did, sid2)).root).to.equal(ethers.ZeroHash);
  });
});

describe(title("A5"), () => {
  it("the on-chain key hash cannot be altered by anyone but the organisation", async () => {
    const { registry, registrar, attacker, did } = await loadFixture(fixture);
    for (const who of [attacker, registrar]) {
      await expect(registry.connect(who).rotateKey(did, PK("tampered")))
        .to.be.revertedWithCustomError(registry, "NotController");
    }
  });

  it("nobody can add a channel to an organisation except the registrar", async () => {
    const { registry, bankCtl, attacker, did } = await loadFixture(fixture);
    for (const who of [attacker, bankCtl]) {
      await expect(registry.connect(who).addChannel(did, CH("+61399999999")))
        .to.be.revertedWithCustomError(registry, "NotRegistrar");
    }
  });
});

describe(title("A6"), () => {
  it("a revoked credential fails Layer 1 in the same block", async () => {
    const { registry, registrar, did } = await loadFixture(fixture);
    const receipt = await (await registry.connect(registrar).setStatus(did, Status.Revoked)).wait();
    const rec = await registry.resolve(did, { blockTag: receipt.blockNumber });
    expect(Number(rec.status)).to.equal(Status.Revoked);
  });

  it("revocation is observable without polling", async () => {
    const { registry, registrar, did } = await loadFixture(fixture);
    await expect(registry.connect(registrar).setStatus(did, Status.Revoked))
      .to.emit(registry, "StatusChanged").withArgs(did, Status.Active, Status.Revoked);
  });
});

describe(title("A7"), () => {
  it("key rotation advances the epoch so an assertion under the old key is identifiable", async () => {
    const { registry, bankCtl, did } = await loadFixture(fixture);
    const before = await registry.resolve(did);
    expect(before.keyEpoch).to.equal(1);
    await registry.connect(bankCtl).rotateKey(did, PK("bank-2"));
    const after = await registry.resolve(did);
    expect(after.keyEpoch).to.equal(2);
    expect(after.pubKeyHash).to.equal(ethers.keccak256(PK("bank-2")));
    expect(after.pubKeyHash).to.not.equal(before.pubKeyHash);
  });

  it("a suspended credential fails Layer 1 and is reversible", async () => {
    const { registry, registrar, did, chid } = await loadFixture(fixture);
    await registry.connect(registrar).setStatus(did, Status.Suspended);
    expect((await layer1Verdict(registry, did, chid)).pass).to.equal(false);
    await registry.connect(registrar).setStatus(did, Status.Active);
    expect((await layer1Verdict(registry, did, chid)).pass).to.equal(true);
  });
});

describe(title("A8"), () => {
  it("a rewrite between two attesting carriers is an undeclared change -> fail", async () => {
    const { registry, carriers, did, chid } = await loadFixture(fixture);
    const sid = SID(CH("rewrite"), chid);
    const genuine = claimOf(did, chid, sid);
    const rewritten = claimOf(did, CH("+61399999999"), sid);
    await registry.connect(carriers[0]).attest(sid, 0, genuine, genuine, 0);
    await registry.connect(carriers[3]).attest(sid, 3, rewritten, rewritten, 0);
    const route = pathStatus(await trustedAttestations(registry, sid));
    expect(route.status).to.equal(Tri.FAIL);
    expect(route.between).to.deep.equal([0, 3]);
  });

  it("a rewrite with only one attesting carrier yields unknown, not failure", async () => {
    const { registry, carriers, did, chid } = await loadFixture(fixture);
    const sid = SID(CH("unobserved"), chid);
    const c = claimOf(did, chid, sid);
    await registry.connect(carriers[0]).attest(sid, 0, c, c, 0);
    expect(pathStatus(await trustedAttestations(registry, sid)).status).to.equal(Tri.UNKNOWN);
  });

  it("attestations are attributable to a registered carrier and key", async () => {
    const { registry, carriers, did, chid } = await loadFixture(fixture);
    const sid = SID(CH("attribution"), chid);
    const c = claimOf(did, CH("+61399999999"), sid);
    await registry.connect(carriers[1]).attest(sid, 1, c, c, 0);
    const [a] = await registry.getAttestations(sid);
    expect(a.attestor).to.equal(carriers[1].address);
    expect(a.carrierId).to.equal(CH("carrier-1"));
    expect(a.blockTime).to.be.greaterThan(0);
  });
});

describe(title("A9"), () => {
  it("the digest root is bound to (did, sid) and immutable once written", async () => {
    const { registry, bankCtl, attacker, did, chid } = await loadFixture(fixture);
    const sid = SID(CH("media"), chid);
    await registry.connect(bankCtl).anchorSession(did, sid, ROOT, CH("ptr"), 150, 2);
    await expect(registry.connect(attacker).anchorSession(did, sid, CH("subst"), CH("ptr"), 150, 2))
      .to.be.revertedWithCustomError(registry, "NotController");
    await expect(registry.connect(bankCtl).anchorSession(did, sid, CH("subst"), CH("ptr"), 150, 2))
      .to.be.revertedWithCustomError(registry, "SessionAlreadyAnchored");
    expect((await registry.getAnchor(did, sid)).root).to.equal(ROOT);
  });

  it("audio never reaches the chain - anchorSession takes only fixed-width values", async () => {
    const { registry } = await loadFixture(fixture);
    for (const input of registry.interface.getFunction("anchorSession").inputs) {
      expect(input.type).to.match(/^(bytes32|uint(8|16|32|64))$/, `${input.name} is ${input.type}`);
    }
  });

  it("a substituted stream fails the live content check", async () => {
    const { registry, bankCtl, carriers, did, chid } = await loadFixture(fixture);
    const sid = SID(CH("media-verify"), chid);
    const c = claimOf(did, chid, sid);
    await registry.connect(carriers[0]).attest(sid, 0, c, c, 0);
    await registry.connect(carriers[4]).attest(sid, 4, c, c, 0);
    await registry.connect(bankCtl).anchorSession(did, sid, ROOT, CH("ptr"), 150, 2);
    // live: the received audio no longer matches the authenticated stream
    const v = await verify(registry, { did, presentedChid: chid, sid, content: Tri.FAIL, detector: "live" });
    expect(v.l3).to.equal(Tri.FAIL);
    expect(v.outcome).to.equal(Outcome.FAIL);
  });
});

describe(title("A10"), () => {
  it("the protocol has no field for a score: no write function or parameter is designated for one", async () => {
    const { registry } = await loadFixture(fixture);
    const writes = registry.interface.fragments.filter(
      (f) => f.type === "function" && f.stateMutability !== "view" && f.stateMutability !== "pure");
    for (const fn of writes) {
      expect(/score|liveness|deepfake|detector|confidence|probability|likelihood/i.test(fn.name)).to.equal(false);
      for (const input of fn.inputs) {
        expect(/score|liveness|deepfake|detector|confidence|probability|likelihood/i.test(input.name))
          .to.equal(false, `${fn.name}.${input.name}`);
      }
    }
  });

  it("the anchor record has no field a detector could populate", async () => {
    const { registry, bankCtl, did, chid } = await loadFixture(fixture);
    const sid = SID(CH("gating"), chid);
    await registry.connect(bankCtl).anchorSession(did, sid, ROOT, CH("ptr"), 150, 2);
    const fields = Object.keys((await registry.getAnchor(did, sid)).toObject()).sort();
    expect(fields).to.deep.equal(["anchoredBy", "blockTime", "did", "frames", "hops", "ptr", "root"]);
  });

  it("a credential-valid synthetic call is demoted to 'not verified' by Layer 4 only", async () => {
    const { registry, bankCtl, carriers, did, chid } = await loadFixture(fixture);
    const sid = SID(CH("synth"), chid);
    const c = claimOf(did, chid, sid);
    await registry.connect(carriers[0]).attest(sid, 0, c, c, 0);
    await registry.connect(carriers[4]).attest(sid, 4, c, c, 0);
    await registry.connect(bankCtl).anchorSession(did, sid, ROOT, CH("ptr"), 150, 2);
    const v = await verify(registry, { did, presentedChid: chid, sid, content: Tri.PASS, detector: "synthetic" });
    expect([v.l1, v.l2, v.l3]).to.deep.equal([Tri.PASS, Tri.PASS, Tri.PASS]);
    expect(v.outcome).to.equal(Outcome.NOT_VERIFIED);
  });
});

describe(title("A11"), () => {
  it("STATED LIMITATION: a live human using a valid credential is verified", async () => {
    // A11 is outside what BVI can detect: every layer is genuinely satisfied.
    const { registry, bankCtl, carriers, did, chid } = await loadFixture(fixture);
    const sid = SID(CH("insider"), chid);
    const c = claimOf(did, chid, sid);
    await registry.connect(carriers[0]).attest(sid, 0, c, c, 0);
    await registry.connect(carriers[4]).attest(sid, 4, c, c, 0);
    await registry.connect(bankCtl).anchorSession(did, sid, ROOT, CH("ptr"), 150, 2);
    const v = await verify(registry, { did, presentedChid: chid, sid, content: Tri.PASS, detector: "live" });
    expect(v.outcome).to.equal(Outcome.VERIFIED);
  });
});

describe("coverage table check (Table II)", () => {
  it("every Table II row has exactly one block, in table order, and all its tests passed", function () {
    const root = this.test.parent.parent;
    const rowSuites = root.suites.filter((s) => /^A\d+ - /.test(s.title));
    const ids = rowSuites.map((s) => s.title.split(" - ")[0]);
    expect(ids).to.deep.equal(TABLE_II.map((r) => r[0]), "blocks missing, extra or out of Table II order");
    for (const [id, name, layer] of TABLE_II) {
      const blocks = rowSuites.filter((s) => s.title === `${id} - ${name}`);
      expect(blocks.length).to.equal(1, `${id} - ${name}: expected exactly one block`);
      const tests = blocks[0].tests;
      expect(tests.length).to.be.greaterThan(0, `${id} has no tests`);
      for (const t of tests) expect(t.state).to.equal("passed", `${id}: "${t.title}" did not pass`);
      console.log(`      ${id.padEnd(4)} ${name.padEnd(38)} ${String(tests.length).padStart(2)} tests  -> ${layer}`);
    }
  });
});
