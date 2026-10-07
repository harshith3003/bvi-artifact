/**
 * verifier_latency_v2.js — chain-read cost of the LIVE verdict on the final contract.
 * verify() reads resolve, isAuthorisedChannel, getAttestations and hopOf per attestation.
 *
 *   in-process : npx hardhat run scripts/verifier_latency_v2.js
 *   JSON-RPC   : npx hardhat node  (other terminal)  then
 *                npx hardhat run --network localhost scripts/verifier_latency_v2.js
 * Writes ../results/registry_v2/verifier_latency_v2_<network>.json with machine and runtime info.
 */
const { ethers, network } = require("hardhat");
const os = require("os");
const fs = require("fs");
const path = require("path");
const V = require("../test/verifier");

const RUNS = Number(process.env.RUNS || 2000);
const pct = (a, q) => a[Math.min(a.length - 1, Math.floor(q * a.length))];

async function main() {
  const s = await ethers.getSigners();
  const [registrar, ctl, c0, c1, c2] = s;
  const reg = await (await ethers.getContractFactory("BVIRegistry")).deploy(registrar.address);
  await reg.waitForDeployment();
  const did = V.CH("did:bvi:latency"), chid = V.CH("+61312345678");
  await (await reg.connect(registrar).register(did, V.PK("org"), [chid], ctl.address)).wait();
  const carriers = [c0, c1, c2];
  for (let i = 0; i < 3; i++) {
    await (await reg.connect(registrar).registerHop(V.CH(`carrier-${i}`), carriers[i].address, "", false)).wait();
  }
  const sid = V.SID(V.CH("nonce"), chid);
  for (let i = 0; i < 3; i++) {
    const c = V.claimOf(did, chid, sid);
    await (await reg.connect(carriers[i]).attest(sid, i, c, c, V.CODEC.PASSTHROUGH)).wait();
  }
  const args = { did, presentedChid: chid, sid, content: V.Tri.PASS, detector: "live" };
  for (let i = 0; i < 50; i++) await V.verify(reg, args);
  const t = [];
  for (let i = 0; i < RUNS; i++) {
    const a = process.hrtime.bigint();
    const v = await V.verify(reg, args);
    t.push(Number(process.hrtime.bigint() - a) / 1e6);
    if (v.outcome !== V.Outcome.VERIFIED) throw new Error("unexpected verdict " + v.outcome);
  }
  t.sort((x, y) => x - y);
  const res = {
    contract: "BVIRegistry (final)", network: network.name,
    what: "live verify(): resolve + isAuthorisedChannel + getAttestations + hopOf x3 (trusted-attestor filter), sequential",
    case: "honest session, 3 attesting carriers; not pooled across attacks",
    runs: RUNS, warmup: 50,
    median_ms: +pct(t, 0.5).toFixed(4), p95_ms: +pct(t, 0.95).toFixed(4), p99_ms: +pct(t, 0.99).toFixed(4),
    machine: { platform: `${os.platform()} ${os.release()}`, arch: os.arch(), cpu: os.cpus()[0].model,
               cores: os.cpus().length, memory_gb: +(os.totalmem() / 2 ** 30).toFixed(1) },
    runtime: { node: process.versions.node, ethers: ethers.version },
  };
  const out = path.join(__dirname, "..", "..", "results", "registry_v2");
  fs.mkdirSync(out, { recursive: true });
  fs.writeFileSync(path.join(out, `verifier_latency_v2_${network.name}.json`), JSON.stringify(res, null, 2));
  console.log(JSON.stringify(res, null, 2));
}
main().catch((e) => { console.error(e); process.exit(1); });
