const { expect } = require("chai");
const { ethers } = require("hardhat");
const { loadFixture } = require("@nomicfoundation/hardhat-network-helpers");
const { fixture } = require("./fixture");
const { Status, CH, PK } = require("./verifier");

/**
 * REVOCATION - Sections 4.2 and 7.1, on BVIRegistry v2.
 *
 *   (a) TWO INDEPENDENT PRINCIPALS: the organisation's own controller and the
 *       registrar can each revoke without the other; the registrar cannot be the
 *       controller; only the organisation can rotate its key.
 *   (b) REVOCATION IS TERMINAL.   (c) EFFECT IS IMMEDIATE.   (d) OBSERVABLE.
 *
 * In v1, register() made the registrar the controller, so (a) held only in name.
 */

describe("(a) two independent principals can revoke", () => {
  it("the organisation's controller can revoke without the registrar", async () => {
    const { registry, bankCtl, registrar, did } = await loadFixture(fixture);
    expect(bankCtl.address).to.not.equal(registrar.address);
    expect(await registry.controllerOf(did)).to.equal(bankCtl.address);
    await expect(registry.connect(bankCtl).setStatus(did, Status.Revoked))
      .to.emit(registry, "StatusChanged").withArgs(did, Status.Active, Status.Revoked);
  });

  it("the registrar can revoke without the controller", async () => {
    const { registry, registrar, did } = await loadFixture(fixture);
    await registry.connect(registrar).setStatus(did, Status.Revoked);
    expect((await registry.resolve(did)).status).to.equal(Status.Revoked);
  });

  it("the registrar cannot be made an organisation's controller", async () => {
    const { registry, registrar } = await loadFixture(fixture);
    await expect(registry.connect(registrar).register(CH("did:bvi:x"), PK("x"), [], registrar.address))
      .to.be.revertedWithCustomError(registry, "ControllerIsRegistrar");
    await expect(registry.connect(registrar).register(CH("did:bvi:y"), PK("y"), [], ethers.ZeroAddress))
      .to.be.revertedWithCustomError(registry, "ZeroAddress");
  });

  it("only the organisation can rotate its key; the registrar cannot", async () => {
    const { registry, registrar, bankCtl, did } = await loadFixture(fixture);
    await expect(registry.connect(registrar).rotateKey(did, PK("registrar-chosen")))
      .to.be.revertedWithCustomError(registry, "NotController");
    await registry.connect(bankCtl).rotateKey(did, PK("bank-2"));
    expect((await registry.resolve(did)).keyEpoch).to.equal(2);
  });

  it("nobody outside the two principals can revoke", async () => {
    const { registry, outsider, did } = await loadFixture(fixture);
    await expect(registry.connect(outsider).setStatus(did, Status.Revoked))
      .to.be.revertedWithCustomError(registry, "NotAuthorisedToSetStatus");
  });

  it("a captured or negligent registrar cannot block the organisation revoking itself", async () => {
    // The registrar simply does nothing; the organisation acts alone.
    const { registry, bankCtl, did } = await loadFixture(fixture);
    await registry.connect(bankCtl).setStatus(did, Status.Revoked);
    expect((await registry.resolve(did)).status).to.equal(Status.Revoked);
  });
});

describe("(b) revocation is terminal and cannot be undone", () => {
  it("neither principal can return a revoked DID to Active", async () => {
    const { registry, registrar, bankCtl, did } = await loadFixture(fixture);
    await registry.connect(bankCtl).setStatus(did, Status.Revoked);
    for (const who of [registrar, bankCtl]) {
      await expect(registry.connect(who).setStatus(did, Status.Active))
        .to.be.revertedWithCustomError(registry, "RevokedIsTerminal");
    }
  });

  it("a revoked DID cannot be moved to Suspended either", async () => {
    const { registry, registrar, did } = await loadFixture(fixture);
    await registry.connect(registrar).setStatus(did, Status.Revoked);
    await expect(registry.connect(registrar).setStatus(did, Status.Suspended))
      .to.be.revertedWithCustomError(registry, "RevokedIsTerminal");
  });

  it("a revoked DID cannot be re-registered to clear its history", async () => {
    const { registry, registrar, otherCtl, did } = await loadFixture(fixture);
    await registry.connect(registrar).setStatus(did, Status.Revoked);
    await expect(registry.connect(registrar).register(did, PK("again"), [], otherCtl.address))
      .to.be.revertedWithCustomError(registry, "AlreadyRegistered");
  });

  it("rotating the key of a revoked organisation does not revive it", async () => {
    const { registry, registrar, bankCtl, did } = await loadFixture(fixture);
    await registry.connect(registrar).setStatus(did, Status.Revoked);
    await registry.connect(bankCtl).rotateKey(did, PK("fresh"));
    expect((await registry.resolve(did)).status).to.equal(Status.Revoked);
  });
});

describe("(c) the effect is immediate", () => {
  it("a revocation is visible to a reader in the same block", async () => {
    const { registry, bankCtl, did } = await loadFixture(fixture);
    const receipt = await (await registry.connect(bankCtl).setStatus(did, Status.Revoked)).wait();
    const atBlock = await registry.resolve(did, { blockTag: receipt.blockNumber });
    expect(atBlock.status).to.equal(Status.Revoked);
  });

  it("no settlement or challenge window exists in the contract", async () => {
    const { registry } = await loadFixture(fixture);
    const names = registry.interface.fragments.filter((f) => f.type === "function").map((f) => f.name);
    for (const forbidden of ["finalizeStatus", "commitStatus", "confirmStatus"]) {
      expect(names).to.not.include(forbidden);
    }
  });
});

describe("(d) the effect is observable without polling", () => {
  it("StatusChanged carries both the old and new status", async () => {
    const { registry, registrar, did } = await loadFixture(fixture);
    await expect(registry.connect(registrar).setStatus(did, Status.Suspended))
      .to.emit(registry, "StatusChanged").withArgs(did, Status.Active, Status.Suspended);
    await expect(registry.connect(registrar).setStatus(did, Status.Revoked))
      .to.emit(registry, "StatusChanged").withArgs(did, Status.Suspended, Status.Revoked);
  });

  it("StatusChanged indexes the DID so a client can filter server-side", async () => {
    const { registry } = await loadFixture(fixture);
    const did = registry.interface.getEvent("StatusChanged").inputs.find((i) => i.name === "did");
    expect(did.indexed).to.equal(true);
  });

  it("a client filtering on one DID does not see another organisation's events", async () => {
    const { registry, registrar, otherCtl, did } = await loadFixture(fixture);
    const other = CH("did:bvi:otherbank");
    await registry.connect(registrar).register(other, PK("other"), [], otherCtl.address);
    await registry.connect(registrar).setStatus(other, Status.Suspended);
    await registry.connect(registrar).setStatus(did, Status.Revoked);
    const logs = await registry.queryFilter(registry.filters.StatusChanged(did));
    expect(logs.length).to.equal(2); // registration + revocation
    expect(logs[1].args.newStatus).to.equal(Status.Revoked);
  });
});

describe("status transitions - remaining state machine", () => {
  it("Suspended is reversible by either principal", async () => {
    const { registry, registrar, bankCtl, did } = await loadFixture(fixture);
    await registry.connect(registrar).setStatus(did, Status.Suspended);
    await registry.connect(bankCtl).setStatus(did, Status.Active);
    expect((await registry.resolve(did)).status).to.equal(Status.Active);
  });

  it("a no-op transition reverts rather than emitting a misleading event", async () => {
    const { registry, registrar, did } = await loadFixture(fixture);
    await expect(registry.connect(registrar).setStatus(did, Status.Active))
      .to.be.revertedWithCustomError(registry, "NoStatusChange");
  });

  it("a DID cannot be pushed back to Unregistered", async () => {
    const { registry, registrar, did } = await loadFixture(fixture);
    await expect(registry.connect(registrar).setStatus(did, Status.Unregistered))
      .to.be.revertedWithCustomError(registry, "CannotSetUnregistered");
  });

  it("an unknown DID resolves to Unregistered rather than reverting", async () => {
    const { registry } = await loadFixture(fixture);
    const rec = await registry.resolve(CH("did:bvi:nonexistent"));
    expect(rec.status).to.equal(Status.Unregistered);
    expect(rec.pubKeyHash).to.equal(ethers.ZeroHash);
  });
});
