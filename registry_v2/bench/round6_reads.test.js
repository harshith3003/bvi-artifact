/**
 * Item 6 benchmark: chain-read cost of the live verdict for each version, against path length.
 * Not part of the test suite (lives outside test/). Run:
 *   npx hardhat test bench/round6_reads.test.js
 * Writes ../results/round6_perf/chain_reads.json and prints a table.
 *   BVI-B : resolve + channel membership (no carrier records)
 *   BVI-0 : + trusted attestations (getAttestations + hopOf per attester)   [round-5 verifier]
 *   BVI-R : + neighbour links (getLinks per attester) + linked rule          [verifier_r.js]
 */
const fs = require("fs"), path = require("path");
const { ethers } = require("hardhat");
const { loadFixture } = require("@nomicfoundation/hardhat-network-helpers");
const { fixture } = require("../test/fixture");
const { CH, SID, claimOf, trustedAttestations, pathStatus } = require("../test/verifier");
const { linkedRecords, linkedPathStatus } = require("../test/verifier_r");

const ORIGIN = ethers.keccak256(ethers.toUtf8Bytes("ORIGIN"));
const RECIPIENT = ethers.keccak256(ethers.toUtf8Bytes("RECIPIENT"));
const RUNS = 200, HOPS = [1, 2, 3, 5, 8, 12];

async function timeIt(fn) {
  for (let i = 0; i < 10; i++) await fn();                       // warm-up
  const t = [];
  for (let i = 0; i < RUNS; i++) { const t0 = performance.now(); await fn(); t.push(performance.now() - t0); }
  t.sort((a, b) => a - b);
  return { median: t[Math.floor(RUNS / 2)], p95: t[Math.floor(RUNS * 0.95)] };
}

describe("ROUND 6 bench - chain reads per version", function () {
  this.timeout(600000);
  it("measures read latency for 1 to 12 attesting carriers", async () => {
    const ctx = await loadFixture(fixture);
    const s = await ethers.getSigners();
    const carriers = [...ctx.carriers];
    for (let i = 11; i < s.length && carriers.length < 14; i++) {         // accounts the fixture does not use
      await ctx.registry.connect(ctx.registrar).registerHop(CH(`carrier-${carriers.length}`), s[i].address, "https://bench.example", false);
      carriers.push(s[i]);
    }
    const ids = carriers.map((_, i) => CH(`carrier-${i}`));
    const rows = [];
    for (const h of HOPS) {
      const sid = SID(CH(`bench-${h}`), ctx.chid), c = claimOf(ctx.did, ctx.chid, sid);
      for (let j = 0; j < h; j++) {
        await ctx.registry.connect(carriers[j]).attestLinked(sid, j, c, c, 0,
          { prevCarrier: j === 0 ? ORIGIN : ids[j - 1], nextCarrier: j === h - 1 ? RECIPIENT : ids[j + 1] });
      }
      const base = async () => { await ctx.registry.resolve(ctx.did); await ctx.registry.isAuthorisedChannel(ctx.did, ctx.chid); };
      const B = await timeIt(base);
      const Z = await timeIt(async () => { await base(); pathStatus(await trustedAttestations(ctx.registry, sid)); });
      const R = await timeIt(async () => {
        await base();
        linkedPathStatus(await linkedRecords(ctx.registry, sid), { terminatingCarrier: ids[h - 1], presentedClaim: c, ORIGIN, RECIPIENT });
      });
      const check = linkedPathStatus(await linkedRecords(ctx.registry, sid), { terminatingCarrier: ids[h - 1], presentedClaim: c, ORIGIN, RECIPIENT });
      rows.push({ hops: h, bviB_ms: B, bvi0_ms: Z, bviR_ms: R, linked_status: check.status, complete: check.complete });
    }
    console.log("      attesting carriers | BVI-B median (p95) | BVI-0 median (p95) | BVI-R median (p95) ms | linked rule");
    for (const r of rows) {
      const f = (x) => `${x.median.toFixed(2)} (${x.p95.toFixed(2)})`;
      console.log(`      ${String(r.hops).padStart(18)} | ${f(r.bviB_ms).padStart(18)} | ${f(r.bvi0_ms).padStart(18)} | ${f(r.bviR_ms).padStart(20)} | ${r.linked_status}, complete=${r.complete}`);
    }
    const out = path.join(__dirname, "..", "..", "results", "round6_perf");
    fs.mkdirSync(out, { recursive: true });
    fs.writeFileSync(path.join(out, "chain_reads.json"), JSON.stringify({ runs: RUNS, network: "hardhat in-process", rows }, null, 2));
    for (const r of rows) if (r.hops >= 2 && (r.linked_status !== "pass" || !r.complete)) throw new Error(`honest linked chain not accepted at ${r.hops} hops`);
  });
});
