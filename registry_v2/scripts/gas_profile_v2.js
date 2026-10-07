/**
 * gas_profile_v2.js — every gas number for BVIRegistry v2.
 *   npx hardhat run scripts/gas_profile_v2.js
 *
 * Writes results/gas_*.csv, results/gas_manifest.json and results/gas_summary.txt.
 * gas_summary.txt is generated from the measured data; quote numbers from it,
 * never by hand. All values are receipt gasUsed (incl. 21,000 intrinsic + calldata).
 */
const { ethers, network } = require("hardhat");
const fs = require("fs");
const path = require("path");

const OUT = path.join(__dirname, "..", "results");
fs.mkdirSync(OUT, { recursive: true });
const CH = (s) => ethers.keccak256(ethers.toUtf8Bytes(s));
const SID = (n) => ethers.keccak256(ethers.solidityPacked(["bytes32", "bytes32"], [CH(n), CH("chan")]));
const PK = (t) => ethers.concat([CH("pk-a-" + t), CH("pk-b-" + t)]);
const gasOf = async (p) => Number((await (await p).wait()).gasUsed);
const calldataGas = (data) => ethers.getBytes(data).reduce((g, b) => g + (b === 0 ? 4 : 16), 21000);
const gasAndExec = async (p) => { const tx = await p; const g = Number((await tx.wait()).gasUsed);
                                  return [g, g - calldataGas(tx.data)]; };
const csv = (name, header, rows) => {
  fs.writeFileSync(path.join(OUT, name), [header.join(","), ...rows.map((r) => r.join(","))].join("\n") + "\n");
};

async function main() {
  const s = await ethers.getSigners();
  const [registrar, ctl, other] = s;
  const carriers = s.slice(3, 19); // 16 carrier keys
  const reg = await (await ethers.getContractFactory("BVIRegistry")).deploy(registrar.address);
  await reg.waitForDeployment();
  const MAX = Number(await reg.MAX_HOPS());
  const did = CH("did:bvi:gasbank");
  const summary = [];

  // ── admin calls ─────────────────────────────────────────────────────────────
  const admin = [];
  admin.push(["register (1 channel)", await gasOf(reg.connect(registrar).register(did, PK("bank"), [CH("c1")], ctl.address))]);
  admin.push(["addChannel", await gasOf(reg.connect(registrar).addChannel(did, CH("c2")))]);
  admin.push(["removeChannel", await gasOf(reg.connect(ctl).removeChannel(did, CH("c2")))]);
  admin.push(["rotateKey", await gasOf(reg.connect(ctl).rotateKey(did, PK("bank-2")))]);
  for (let i = 0; i < carriers.length; i++) {
    const g = await gasOf(reg.connect(registrar).registerHop(CH(`carrier-${i}`), carriers[i].address,
      `https://carrier${i}.example/bvi.json`, i === 2));
    if (i === 0) admin.push(["registerHop", g]);
  }
  const spareHop = ethers.Wallet.createRandom().address;
  await reg.connect(registrar).registerHop(CH("spare"), spareHop, "", false);
  admin.push(["setHopStatus (suspend)", await gasOf(reg.connect(registrar).setHopStatus(spareHop, 2))]);
  const did2 = CH("did:bvi:statusbank");
  await reg.connect(registrar).register(did2, PK("s"), [], other.address);
  admin.push(["setStatus (suspend)", await gasOf(reg.connect(registrar).setStatus(did2, 2))]);
  admin.push(["setStatus (revoke)", await gasOf(reg.connect(other).setStatus(did2, 3))]);
  csv("gas_admin.csv", ["operation", "gas"], admin);
  summary.push("ADMIN"); for (const [n, g] of admin) summary.push(`  ${n.padEnd(24)} ${g.toLocaleString("en-US")}`);

  // ── anchor vs call length and hop count ─────────────────────────────────────
  const anchorRows = [];
  let k = 0;
  for (const seconds of [30, 60, 300, 900, 1800]) {
    for (const hops of [1, 2, 5, 8, 12, 20, 32].filter((h) => h <= MAX)) {
      const frames = seconds * 50;
      const [g, ex] = await gasAndExec(reg.connect(ctl).anchorSession(did, SID(`a${k++}`), CH(`root${k}`), CH(`ptr${k}`), frames, hops));
      anchorRows.push([seconds, frames, hops, g, ex]);
    }
  }
  csv("gas_anchor_grid.csv", ["call_seconds", "frames_T", "hops_Q", "anchor_gas", "execution_gas"], anchorRows);
  const ag = anchorRows.map((r) => r[3]);
  const ex = [...new Set(anchorRows.map((r) => r[4]))];
  summary.push("", `ANCHOR (anchorSession), ${anchorRows.length} combinations of call length 30 s-30 min and |Q| 1-32`);
  summary.push(`  execution gas: ${ex.length === 1 ? ex[0].toLocaleString("en-US") + " in every combination" : "VARIES: " + ex.join(", ")}`);
  summary.push(`  total min ${Math.min(...ag).toLocaleString("en-US")}  max ${Math.max(...ag).toLocaleString("en-US")}  (spread ${Math.max(...ag) - Math.min(...ag)}, calldata bytes only)`);

  // ── attest gas by hop index (one session, distinct carriers) ────────────────
  const sidHop = SID("hop-sweep");
  const hopRows = [];
  for (let h = 0; h < carriers.length; h++) {
    const c = CH(`claim-${h}`);
    hopRows.push([h, await gasOf(reg.connect(carriers[h]).attest(sidHop, h, c, c, 0))]);
  }
  csv("gas_attest_by_hop.csv", ["attestation_order", "attest_gas"], hopRows);
  summary.push("", "ATTEST by order within a session (1st, 2nd, 3rd, ... attestation)");
  summary.push("  " + hopRows.map((r) => `#${r[0] + 1}: ${r[1].toLocaleString("en-US")}`).join(", "));

  // ── per call: 1 anchor + one attestation per participating carrier ──────────
  const callRows = [];
  for (const H of [1, 2, 3, 5, 8, 12]) {
    for (let kk = 0; kk <= H; kk++) {
      const sid = SID(`call-${H}-${kk}`);
      let att = 0;
      for (let h = 0; h < kk; h++) {
        const c = CH("claim");
        att += await gasOf(reg.connect(carriers[h]).attest(sid, h, c, c, 0));
      }
      const anc = await gasOf(reg.connect(ctl).anchorSession(did, sid, CH("root"), CH("ptr"), 3000, kk));
      callRows.push([H, kk, anc, att, anc + att]);
    }
  }
  csv("gas_per_call.csv", ["hops_H", "participating_k", "anchor_gas", "attest_gas_total", "call_total_gas"], callRows);
  summary.push("", "PER CALL = 1 anchor + 1 attestation per participating carrier (all participating)");
  for (const r of callRows.filter((r) => r[0] === r[1])) {
    summary.push(`  H=${String(r[0]).padStart(2)}: anchor ${r[2].toLocaleString("en-US")} + attestations ${r[3].toLocaleString("en-US")} = ${r[4].toLocaleString("en-US")}`);
  }

  // ── batching: N separate anchors vs one anchorSessionBatch ──────────────────
  const batchRows = [];
  for (const N of [1, 5, 10, 25, 50, 100]) {
    let individual = 0;
    for (let i = 0; i < N; i++) {
      individual += await gasOf(reg.connect(ctl).anchorSession(did, SID(`ind-${N}-${i}`), CH(`r${i}`), CH(`p${i}`), 3000, 3));
    }
    const items = Array.from({ length: N }, (_, i) =>
      ({ sid: SID(`bat-${N}-${i}`), root: CH(`r${i}`), ptr: CH(`p${i}`), frames: 3000, hops: 3 }));
    const batch = await gasOf(reg.connect(ctl).anchorSessionBatch(did, items));
    const saving = (100 * (1 - batch / individual)).toFixed(2);
    batchRows.push([N, individual, batch, Math.round(individual / N), Math.round(batch / N), saving]);
  }
  csv("gas_batching.csv", ["N", "individual_total", "batch_total", "individual_per_anchor", "batch_per_anchor", "saving_pct"], batchRows);
  summary.push("", "BATCHING (anchorSessionBatch vs N separate anchorSession transactions)");
  for (const r of batchRows) summary.push(`  N=${String(r[0]).padStart(3)}: ${r[3].toLocaleString("en-US")} -> ${r[4].toLocaleString("en-US")} per anchor (${r[5]}% saved)`);

  const manifest = { contract: "BVIRegistry v2 (bvi_round4/contracts)", solc: "0.8.24, optimizer 200, paris",
    network: network.name, MAX_HOPS: MAX, frames_per_second: 50,
    note: "receipt gasUsed incl. intrinsic and calldata; hardhat network is deterministic",
    generated: new Date().toISOString() };
  fs.writeFileSync(path.join(OUT, "gas_manifest.json"), JSON.stringify(manifest, null, 2));
  fs.writeFileSync(path.join(OUT, "gas_summary.txt"), summary.join("\n") + "\n");
  console.log(summary.join("\n"));
  console.log("\nwrote results/gas_*.csv, gas_manifest.json, gas_summary.txt");
}

main().catch((e) => { console.error(e); process.exit(1); });
