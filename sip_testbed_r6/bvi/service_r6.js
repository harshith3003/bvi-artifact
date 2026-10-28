/**
 * Round-6 chain service for the SIP testbed (local Hardhat node, BVIRegistry with attestLinked).
 *
 *   POST /setup          {pubKey, numbers[]}                      register the organisation (or rotate its key)
 *   POST /attest         {sid, hop, did, inId, outId, scenario}    carrier `hop` writes a LINKED attestation
 *   POST /offpath        {sid, did, kind}                          an off-path registered carrier writes a record
 *   POST /verify         {did, presentedId, sid}                   Layer 1 + positional route rule (round 5)
 *   POST /verify_linked  {did, presentedId, sid, signedCallingId}  linked route rule, with and without binding
 *   POST /thresholds     {sid, originV1, originV2, terminatingHop} carrier (BVI-0) and chain (BVI-R) thresholds
 *   GET  /resolve?did=   pubKeyHash for the key-message check
 *
 * Carrier behaviour per scenario (the network being simulated, never seen by the recipient):
 *   missing_records   only p2 attests              transcode_silent   p2 (the transcoder) does not attest
 *   transcode_declared p2 declares AMR-NB 12.2, p3 G.711 mu-law
 *   mobile_origin     p1 declares G.711 mu-law (it transcodes the mobile AMR leg)
 *   rewrite / launder p2 rewrites and does not attest (in the Kamailio config)
 * Signers: 0 registrar, 1 organisation controller, 2..4 carriers p1..p3, 5 off-path translator, 6 off-path carrier.
 */
const http = require("http");
const fs = require("fs");
const { ethers } = require("hardhat");
const V = require("./test/verifier");
const R = require("./test/verifier_r");

const THRESHOLDS = JSON.parse(fs.readFileSync(process.env.THRESHOLDS || "/app/thresholds.json"));
const TH = { pooled: THRESHOLDS.pooled, g711u: THRESHOLDS.g711u, g711a: THRESHOLDS.g711a, opus16: THRESHOLDS.opus16,
             amr122: THRESHOLDS.amr122, amr475: THRESHOLDS.amr475 };
const ORIGIN = ethers.keccak256(ethers.toUtf8Bytes(R.ORIGIN_TAG));
const RECIPIENT = ethers.keccak256(ethers.toUtf8Bytes(R.RECIPIENT_TAG));
const IDS = [0, 1, 2].map((h) => V.CH(`carrier-p${h + 1}`));
const OFF_TRANSLATOR = V.CH("carrier-offpath-translator"), OFF_PLAIN = V.CH("carrier-offpath");
const SKIP = { missing_records: [0, 2], transcode_silent: [1] };
const DECLARE = { transcode_declared: { 1: V.CODEC.AMR122, 2: V.CODEC.G711U }, transcode_silent: { 2: V.CODEC.G711U },
                  mobile_origin: { 0: V.CODEC.G711U } };
let registry, signers;
const did = V.CH("did:bvi:testbank");
const ms = (t0) => Number(process.hrtime.bigint() - t0) / 1e6;

async function deploy() {
  signers = await ethers.getSigners();
  registry = await (await ethers.getContractFactory("BVIRegistry")).deploy(signers[0].address);
  await registry.waitForDeployment();
  for (let h = 0; h < 3; h++) {
    await (await registry.connect(signers[0]).registerHop(IDS[h], signers[2 + h].address, `https://p${h + 1}.bvi.test/meta.json`, false)).wait();
  }
  await (await registry.connect(signers[0]).registerHop(OFF_TRANSLATOR, signers[5].address, "https://off-t.bvi.test/meta.json", true)).wait();
  await (await registry.connect(signers[0]).registerHop(OFF_PLAIN, signers[6].address, "https://off.bvi.test/meta.json", false)).wait();
  console.log(`BVIRegistry at ${await registry.getAddress()}; carriers p1-p3 and two off-path carriers registered`);
}

const handlers = {
  "/setup": async ({ pubKey, numbers }) => {
    const rec = await registry.resolve(did);
    if (Number(rec.status) === 0) {
      await (await registry.connect(signers[0]).register(did, pubKey, numbers.map(V.CH), signers[1].address)).wait();
    } else if (rec.pubKeyHash !== ethers.keccak256(pubKey)) {
      await (await registry.connect(signers[1]).rotateKey(did, pubKey)).wait();
    }
    return { did, registered: true };
  },
  "/attest": async ({ sid, hop, did: d, inId, outId, scenario }) => {
    if ((SKIP[scenario] || []).includes(hop)) return { skipped: true };
    const t0 = process.hrtime.bigint();
    const codec = (DECLARE[scenario] || {})[hop] || V.CODEC.PASSTHROUGH;
    const tx = await registry.connect(signers[2 + hop]).attestLinked(sid, hop, V.claimOf(d, V.CH(inId), sid),
      V.claimOf(d, V.CH(outId), sid), codec, { prevCarrier: hop === 0 ? ORIGIN : IDS[hop - 1], nextCarrier: hop === 2 ? RECIPIENT : IDS[hop + 1] });
    await tx.wait();
    return { ms: ms(t0), codec };
  },
  "/offpath": async ({ sid, did: d, kind, inId, outId }) => {
    // launder: a registered TRANSLATOR not on the path bridges the rewriter's hop, naming the real neighbours
    // false:   a registered carrier not on the path writes a contradicting record during an honest call
    const signer = kind === "launder" ? signers[5] : signers[6];
    const tx = await registry.connect(signer).attestLinked(sid, 1, V.claimOf(d, V.CH(inId), sid), V.claimOf(d, V.CH(outId), sid),
      V.CODEC.PASSTHROUGH, { prevCarrier: IDS[0], nextCarrier: IDS[2] });
    await tx.wait();
    return { written: kind };
  },
  "/verify": async ({ did: d, presentedId, sid }) => {
    const t0 = process.hrtime.bigint();
    const v = await V.verify(registry, { did: d, presentedChid: V.CH(presentedId), sid, content: V.Tri.UNKNOWN, detector: "live" });
    return { l1: v.l1, l2: v.l2, reason: v.reason, ms: ms(t0) };
  },
  "/verify_linked": async ({ did: d, presentedId, sid, signedCallingId }) => {
    const t0 = process.hrtime.bigint();
    const recs = await R.linkedRecords(registry, sid);
    const base = { terminatingCarrier: IDS[2], presentedClaim: V.claimOf(d, V.CH(presentedId), sid), ORIGIN, RECIPIENT };
    const unbound = R.linkedPathStatus(recs, base);
    const bound = R.linkedPathStatus(recs, { ...base, signedCallingClaim: V.claimOf(d, V.CH(signedCallingId), sid) });
    return { bound: bound.status, unbound: unbound.status, complete: unbound.complete, reason: bound.reason, ms: ms(t0) };
  },
  "/thresholds": async ({ sid, originV1, originV2, terminatingHop }) => {
    const counted = V.pathStatus(await V.trustedAttestations(registry, sid)).counted;
    const carrier = V.contentThreshold({ thresholds: TH, originCodec: originV1, counted, terminatingHop });
    const linked = R.linkedPathStatus(await R.linkedRecords(registry, sid), { terminatingCarrier: IDS[2], ORIGIN, RECIPIENT });
    const chain = R.chainThreshold({ thresholds: TH, originCodec: originV2, linked });
    return { carrier: carrier.theta, carrier_basis: carrier.basis, chain: chain.theta, chain_basis: chain.basis };
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
  }).listen(8080, "0.0.0.0", () => console.log("BVI round-6 service on :8080"));
  await new Promise(() => {});
}

main().catch((e) => { console.error(e); process.exit(1); });
