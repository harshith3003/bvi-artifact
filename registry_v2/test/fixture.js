/**
 * fixture.js — shared deployment for the v2 suites.
 *
 * Principals:
 *   registrar   onboards organisations and carriers
 *   bankCtl     the organisation's OWN controller key (not the registrar)
 *   c0..c4      five registered carriers; c2 has the translator role
 *   attacker    an unregistered account
 *   outsider    another unregistered account
 */
const { ethers } = require("hardhat");
const { CH, PK } = require("./verifier");

const BANK_DID = CH("did:bvi:examplebank");
const BANK_CHID = CH("+61312345678");
const TRANSLATOR_INDEX = 2;

async function fixture() {
  const s = await ethers.getSigners();
  const [registrar, bankCtl, c0, c1, c2, c3, c4, attacker, outsider, otherCtl, spare] = s;
  const registry = await (await ethers.getContractFactory("BVIRegistry")).deploy(registrar.address);
  await registry.waitForDeployment();

  await registry.connect(registrar).register(BANK_DID, PK("bank"), [BANK_CHID], bankCtl.address);

  const carriers = [c0, c1, c2, c3, c4];
  for (let i = 0; i < carriers.length; i++) {
    await registry.connect(registrar).registerHop(
      CH(`carrier-${i}`), carriers[i].address, `https://carrier${i}.example/bvi.json`, i === TRANSLATOR_INDEX
    );
  }
  return {
    registry, registrar, bankCtl, carriers, attacker, outsider, otherCtl, spare,
    did: BANK_DID, chid: BANK_CHID, signers: s,
  };
}

module.exports = { fixture, BANK_DID, BANK_CHID, TRANSLATOR_INDEX };
