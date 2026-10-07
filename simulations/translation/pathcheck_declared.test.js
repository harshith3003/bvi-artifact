/**
 * T-series tests for declared translations (item 3). Pure logic, no chain.
 * Run: npx hardhat test tifs_round3/item3_translation/pathcheck_declared.test.js
 */
const { expect } = require("chai");
const { ethers } = require("ethers");
const { Tri, pathStatusDeclared, pathStatusUndeclared } = require("./pathcheck_declared");

const CH = (s) => ethers.keccak256(ethers.toUtf8Bytes(s));
const DID = CH("did:bvi:examplebank");
const SID = CH("session-1");
const claim = (chid) =>
  ethers.keccak256(ethers.solidityPacked(["bytes32", "bytes32", "bytes32"], [DID, CH(chid), SID]));

const E164 = "+61312345678";
const NATIONAL = "0312345678";       // legitimate format translation at a border controller
const SPOOF = "+61299990000";        // attacker's rewrite

const att = (hop, inId, outId = inId) => ({ hop, inClaim: claim(inId), outClaim: claim(outId) });

describe("T1 — declared translations (route check, item 3)", () => {
  it("T1a: no translation, 3 participants agree -> pass", () => {
    const r = pathStatusDeclared([att(0, E164), att(2, E164), att(4, E164)]);
    expect(r.status).to.equal(Tri.PASS);
  });

  it("T1b: participating carrier translates and DECLARES it -> pass (old rule would fail)", () => {
    const atts = [att(0, E164), att(1, E164, NATIONAL), att(3, NATIONAL)];
    expect(pathStatusDeclared(atts).status).to.equal(Tri.PASS);
    expect(pathStatusDeclared(atts).declared).to.deep.equal([1]);
    // current rule (received IDs only): hop 0 saw E164, hop 3 saw NATIONAL -> fail
    expect(pathStatusUndeclared([claim(E164), claim(E164), claim(NATIONAL)])).to.equal(Tri.FAIL);
  });

  it("T1c: NON-participating carrier translates between two participants -> fail (residual false flag)", () => {
    // hop 2 translated but is silent; hop 1 sent E164, hop 3 received NATIONAL
    const r = pathStatusDeclared([att(1, E164), att(3, NATIONAL)]);
    expect(r.status).to.equal(Tri.FAIL);
    expect(r.mismatchAt).to.deep.equal([1, 3]);
  });

  it("T1d: undeclared rewrite by an in-path attacker between participants -> fail", () => {
    const r = pathStatusDeclared([att(0, E164), att(1, E164), att(3, SPOOF), att(4, SPOOF)]);
    expect(r.status).to.equal(Tri.FAIL);
    expect(r.mismatchAt).to.deep.equal([1, 3]);
  });

  it("T1e: translation AND attack on the same path -> fail at the undeclared change only", () => {
    const r = pathStatusDeclared([att(0, E164, NATIONAL), att(1, NATIONAL), att(3, SPOOF)]);
    expect(r.status).to.equal(Tri.FAIL);
    expect(r.mismatchAt).to.deep.equal([1, 3]);
    expect(r.declared).to.deep.equal([0]);
  });

  it("T1f: participating malicious carrier DECLARES a rewrite -> pass, but attributable (policy question)", () => {
    const r = pathStatusDeclared([att(0, E164), att(1, E164, SPOOF), att(3, SPOOF)]);
    expect(r.status).to.equal(Tri.PASS);
    expect(r.declared).to.deep.equal([1]); // the change is on record against hop 1's key
  });

  it("T1g: fewer than 2 participants -> unknown, whatever was translated", () => {
    expect(pathStatusDeclared([att(2, E164, NATIONAL)]).status).to.equal(Tri.UNKNOWN);
    expect(pathStatusDeclared([]).status).to.equal(Tri.UNKNOWN);
  });
});
