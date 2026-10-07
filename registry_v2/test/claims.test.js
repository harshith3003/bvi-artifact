const { expect } = require("chai");
const { ethers } = require("hardhat");
const { loadFixture } = require("@nomicfoundation/hardhat-network-helpers");
const { fixture } = require("./fixture");
const { CH, SID, claimOf, PK, merkleRoot, verify } = require("./verifier");

/**
 * CLAIM-BEARING TESTS on BVIRegistry v2. A failure here means a sentence in the
 * paper is false.
 *
 * Constant-cost claim, restated precisely for v2: the anchor now carries T and |Q|
 * as fixed-width fields. EXECUTION gas is identical for every call length and hop
 * count. Total gas differs only by calldata pricing (4 gas per zero byte, 16 per
 * non-zero byte), i.e. by a few tens of gas depending on the byte values.
 */

function calldataGas(data) {
  const b = ethers.getBytes(data);
  let g = 21000;
  for (const x of b) g += x === 0 ? 4 : 16;
  return g;
}

function digestRootForCall(seconds, fps = 50) {
  const n = Math.max(1, Math.round(seconds * fps));
  const leaves = Array.from({ length: n }, (_, i) =>
    ethers.keccak256(ethers.solidityPacked(["uint32"], [i >>> 0])));
  return { root: merkleRoot(leaves), frames: n };
}

async function anchorGas(registry, ctl, did, tag, seconds, hops) {
  const { root, frames } = digestRootForCall(seconds);
  const ptr = ethers.keccak256(ethers.toUtf8Bytes(`transcript-${tag}-${hops}`));
  const tx = await registry.connect(ctl).anchorSession(did, SID(CH(tag), CH("c1")), root, ptr, frames, hops);
  const rc = await tx.wait();
  return { total: Number(rc.gasUsed), exec: Number(rc.gasUsed) - calldataGas(tx.data), frames };
}

describe("CLAIM 2 - per-session anchor cost does not depend on call length or hop count", () => {
  it("execution gas is identical across a duration x hop-count grid; totals differ only by calldata", async () => {
    const { registry, bankCtl, did } = await loadFixture(fixture);
    const durations = [10, 60, 300, 1800, 3000];
    const hopCounts = [1, 2, 5, 8, 12, 20];
    const execs = new Set();
    const totals = [];
    let k = 0;
    for (const d of durations) {
      for (const h of hopCounts) {
        const g = await anchorGas(registry, bankCtl, did, `grid${k++}`, d, h);
        execs.add(g.exec);
        totals.push(g.total);
      }
    }
    expect(execs.size).to.equal(1, `execution gas varied: ${[...execs]}`);
    const spread = Math.max(...totals) - Math.min(...totals);
    console.log(`      ${totals.length} combinations: execution gas ${[...execs][0]} in every case; ` +
                `total ${Math.min(...totals)}-${Math.max(...totals)} (spread ${spread}, calldata only)`);
    expect(spread).to.be.lessThan(200);
  });
});

describe("CLAIM (R2, R9) - every call-time interaction is a gasless read", () => {
  const READ_METHODS = ["resolve", "isAuthorisedChannel", "getAttestations", "getAnchor",
                        "controllerOf", "attestationCount", "hopOf", "anchorKey"];

  it("all verification entry points are declared view in the ABI", async () => {
    const { registry } = await loadFixture(fixture);
    const abi = registry.interface.fragments.filter((f) => f.type === "function");
    for (const name of READ_METHODS) {
      const frag = abi.find((f) => f.name === name);
      expect(frag, `${name} missing`).to.not.be.undefined;
      expect(frag.stateMutability).to.equal("view", `${name} must be view (R2)`);
    }
  });

  it("a zero-balance account with no transaction history can run the full verifier", async () => {
    const { registry, bankCtl, carriers, did, chid } = await loadFixture(fixture);
    const sid = SID(CH("zero-bal"), chid);
    const c = claimOf(did, chid, sid);
    await registry.connect(carriers[0]).attest(sid, 0, c, c, 0);
    await registry.connect(carriers[4]).attest(sid, 4, c, c, 0);
    await registry.connect(bankCtl).anchorSession(did, sid, CH("root"), CH("ptr"), 150, 2);

    const cold = ethers.Wallet.createRandom().connect(ethers.provider);
    expect(await ethers.provider.getBalance(cold.address)).to.equal(0n);
    const v = await verify(registry.connect(cold), { did, presentedChid: chid, sid,
                                                     content: "pass", detector: "live" });
    expect(v.outcome).to.equal("verified");
    expect(await ethers.provider.getBalance(cold.address)).to.equal(0n);
    expect(await ethers.provider.getTransactionCount(cold.address)).to.equal(0);
  });
});

describe("CLAIM (Section 5.1) - channel membership is one storage read", () => {
  // Compare EXECUTION gas (estimate minus intrinsic and calldata). Totals can differ
  // by 12 gas per zero/non-zero byte in the arguments, which says nothing about storage.
  const execGas = async (registry, did, ch) => {
    const est = Number(await registry.isAuthorisedChannel.estimateGas(did, ch));
    return est - calldataGas(registry.interface.encodeFunctionData("isAuthorisedChannel", [did, ch]));
  };

  it("membership test cost does not grow with the channel set size", async () => {
    const { registry, registrar, otherCtl } = await loadFixture(fixture);
    const small = CH("did:bvi:small"), large = CH("did:bvi:large");
    await registry.connect(registrar).register(small, PK("s"), [CH("s0")], otherCtl.address);
    await registry.connect(registrar).register(large, PK("l"),
      Array.from({ length: 16 }, (_, i) => CH(`L${i}`)), otherCtl.address);
    const gSmall = await execGas(registry, small, CH("s0"));
    const gLarge = await execGas(registry, large, CH("L15"));
    console.log(`      isAuthorisedChannel execution gas: ${gSmall} (1 channel), ${gLarge} (16 channels)`);
    expect(gLarge).to.equal(gSmall);
  });

  it("a negative membership test costs the same as a positive one", async () => {
    const { registry, did, chid } = await loadFixture(fixture);
    expect(await execGas(registry, did, CH("+61999999999"))).to.equal(await execGas(registry, did, chid));
  });
});

describe("CLAIM (Section 7.1) - anchors are non-repudiable", () => {
  it("an anchor cannot be overwritten, even by the organisation that wrote it", async () => {
    const { registry, bankCtl, did } = await loadFixture(fixture);
    const sid = SID(CH("immutable"), CH("chid"));
    await registry.connect(bankCtl).anchorSession(did, sid, CH("real-root"), CH("real-ptr"), 150, 2);
    await expect(registry.connect(bankCtl).anchorSession(did, sid, CH("forged"), CH("forged"), 150, 2))
      .to.be.revertedWithCustomError(registry, "SessionAlreadyAnchored");
    expect((await registry.getAnchor(did, sid)).root).to.equal(CH("real-root"));
  });

  it("the anchor timestamp comes from consensus, not from a party (R7)", async () => {
    const { registry, bankCtl, did } = await loadFixture(fixture);
    const sid = SID(CH("ts"), CH("chid"));
    const rc = await (await registry.connect(bankCtl).anchorSession(did, sid, CH("r"), CH("p"), 150, 2)).wait();
    const block = await ethers.provider.getBlock(rc.blockNumber);
    expect((await registry.getAnchor(did, sid)).blockTime).to.equal(BigInt(block.timestamp));
    const inputs = registry.interface.getFunction("anchorSession").inputs;
    expect(inputs.map((i) => i.type)).to.deep.equal(["bytes32", "bytes32", "bytes32", "bytes32", "uint32", "uint8"]);
    for (const i of inputs) expect(/time|stamp|date/i.test(i.name)).to.equal(false, i.name);
  });
});
