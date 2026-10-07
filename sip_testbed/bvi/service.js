/**
 * BVI chain service for the SIP testbed. Runs against a local Hardhat node (JSON-RPC),
 * with the round-5 BVIRegistry and the same verifier.js the unit tests use.
 *
 *   POST /setup      {pubKey, numbers[]}        registrar registers the organisation and 3 carriers
 *   POST /attest     {sid, hop, did, inId, outId}  carrier `hop` attests (its own key)
 *   POST /verify     {did, presentedId, sid}    live L1 + route check (trusted filter on)
 *   POST /threshold  {sid, originCodec, terminatingHop}  content threshold policy
 *   GET  /resolve?did=0x..                      pubKeyHash for the key-message check
 *
 * Signers: 0 registrar, 1 organisation controller, 2..4 carriers p1..p3.
 */
const http = require("http");
const fs = require("fs");
const { ethers } = require("hardhat");
const V = require("./test/verifier");

const THRESHOLDS = JSON.parse(fs.readFileSync(process.env.THRESHOLDS || "/app/thresholds.json"));
let registry, signers;
const did = V.CH("did:bvi:testbank");

async function deploy() {
  signers = await ethers.getSigners();
  registry = await (await ethers.getContractFactory("BVIRegistry")).deploy(signers[0].address);
  await registry.waitForDeployment();
  for (let h = 0; h < 3; h++) {
    await (await registry.connect(signers[0]).registerHop(V.CH(`carrier-p${h + 1}`), signers[2 + h].address,
      `https://p${h + 1}.bvi.test/meta.json`, false)).wait();
  }
  console.log(`BVIRegistry at ${await registry.getAddress()}; 3 carriers registered`);
}

const handlers = {
  "/setup": async ({ pubKey, numbers }) => {
    const rec = await registry.resolve(did);
    if (Number(rec.status) === 0) {
      await (await registry.connect(signers[0]).register(did, pubKey, numbers.map(V.CH), signers[1].address)).wait();
    } else if (rec.pubKeyHash !== ethers.keccak256(pubKey)) {
      // a re-run brings a fresh organisation key: the organisation (controller) rotates it
      await (await registry.connect(signers[1]).rotateKey(did, pubKey)).wait();
    }
    return { did, registered: true };
  },
  "/attest": async ({ sid, hop, did: d, inId, outId }) => {
    const t0 = process.hrtime.bigint();
    const tx = await registry.connect(signers[2 + hop]).attest(sid, hop, V.claimOf(d, V.CH(inId), sid),
      V.claimOf(d, V.CH(outId), sid), V.CODEC.PASSTHROUGH);
    await tx.wait();
    return { ms: Number(process.hrtime.bigint() - t0) / 1e6 };
  },
  "/verify": async ({ did: d, presentedId, sid }) => {
    const t0 = process.hrtime.bigint();
    const v = await V.verify(registry, { did: d, presentedChid: V.CH(presentedId), sid, content: V.Tri.UNKNOWN, detector: "live" });
    return { l1: v.l1, l2: v.l2, reason: v.reason, ms: Number(process.hrtime.bigint() - t0) / 1e6 };
  },
  "/threshold": async ({ sid, originCodec, terminatingHop }) => {
    const counted = V.pathStatus(await V.trustedAttestations(registry, sid)).counted;
    const t = V.contentThreshold({ thresholds: THRESHOLDS, originCodec, counted, terminatingHop });
    return { theta: t.theta, basis: t.basis };
  },
};

async function main() {
  await deploy();
  http.createServer(async (req, res) => {
    try {
      const url = new URL(req.url, "http://x");
      let out;
      if (req.method === "GET" && url.pathname === "/resolve") {
        const r = await registry.resolve(url.searchParams.get("did"));
        out = { pubKeyHash: r.pubKeyHash, status: Number(r.status) };
      } else if (req.method === "GET" && url.pathname === "/health") {
        out = { ok: true };
      } else {
        let body = "";
        for await (const c of req) body += c;
        const h = handlers[url.pathname];
        if (!h) { res.writeHead(404); return res.end(); }
        out = await h(JSON.parse(body || "{}"));
      }
      res.writeHead(200, { "content-type": "application/json" });
      res.end(JSON.stringify(out, (k, v) => (typeof v === "bigint" ? v.toString() : v)));
    } catch (e) {
      console.error(e);
      res.writeHead(500, { "content-type": "application/json" });
      res.end(JSON.stringify({ error: String(e.shortMessage || e.message) }));
    }
  }).listen(8080, "0.0.0.0", () => console.log("BVI service on :8080"));
  await new Promise(() => {}); // keep running under `hardhat run`
}

main().catch((e) => { console.error(e); process.exit(1); });
