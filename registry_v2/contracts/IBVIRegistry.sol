// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

/// @title IBVIRegistry v2
/// @notice The interface both the TIFS and SDLT papers describe.
///
/// Changes from v1:
///  - register() takes the organisation's own controller; the registrar onboards
///    but does not hold the organisation's key (two independent revocation principals).
///  - Carriers are registered with registerHop(carrierId, hopKey, metaURI, translator).
///    Only Active registered carriers can attest; slots are keyed by the attester,
///    and one attestation per carrier per session.
///  - attest() carries the identifier received and the identifier sent on (declared
///    translations). Only carriers registered with the translator role may declare
///    a change; the verifier treats any other declared change as an inconsistency.
///  - anchorSession() carries (did, sid, root, ptr, T, |Q|), is keyed by
///    (did, sid, chainid) and can be written only by the organisation's controller.
///    ptr = H(T_c), the commitment to the path transcript.
///  - A carrier that transcodes declares the codec it encodes to in attest(); the
///    verifier uses the worst declared codec's content threshold (round 5).
///  - Every unauthorised write is rejected before any storage is written.
interface IBVIRegistry {
    enum Status {
        Unregistered, // 0 - default for an unknown DID or hop key
        Active,       // 1
        Suspended,    // 2 - reversible
        Revoked       // 3 - terminal
    }

    struct Record {
        bytes32 pubKeyHash;
        Status status;
        uint32 keyEpoch;
        uint64 registeredAt;
        uint64 updatedAt;
    }

    struct Hop {
        bytes32 carrierId;
        Status status;
        bool translator;
        uint64 registeredAt;
        uint64 updatedAt;
    }

    struct Attestation {
        address attestor;
        bytes32 carrierId;
        bytes32 inClaim;   // H(did || chid received || sid)
        bytes32 outClaim;  // H(did || chid sent on || sid); equal to inClaim unless translated
        uint64 blockTime;
        uint8 hop;
        bool translator;   // translator role of the attester at the time of writing
        uint8 codec;       // codec this carrier encodes to (0 = media passed through unchanged)
    }

    struct Anchor {
        bytes32 did;
        bytes32 root;      // Merkle root over the per-session fingerprint stream
        bytes32 ptr;       // H(T_c), commitment to the path transcript
        uint32 frames;     // T, number of fingerprint frames
        uint8 hops;        // |Q|, number of participating hops in T_c
        address anchoredBy;
        uint64 blockTime;
    }

    struct AnchorInput {
        bytes32 sid;
        bytes32 root;
        bytes32 ptr;
        uint32 frames;
        uint8 hops;
    }

    event Registered(bytes32 indexed did, bytes32 pubKeyHash, bytes pubKey, address indexed controller);
    event KeyRotated(bytes32 indexed did, bytes32 newPubKeyHash, uint32 keyEpoch, bytes newPubKey);
    event ChannelAdded(bytes32 indexed did, bytes32 indexed channelHash);
    event ChannelRemoved(bytes32 indexed did, bytes32 indexed channelHash);
    event StatusChanged(bytes32 indexed did, Status oldStatus, Status newStatus);
    event HopRegistered(address indexed hopKey, bytes32 indexed carrierId, bool translator, string metaURI);
    event HopStatusChanged(address indexed hopKey, Status oldStatus, Status newStatus);
    event Attested(bytes32 indexed sid, uint8 indexed hop, address indexed attestor,
                   bytes32 carrierId, bytes32 inClaim, bytes32 outClaim, uint8 codec);
    event SessionAnchored(bytes32 indexed did, bytes32 indexed sid, bytes32 root, bytes32 ptr,
                          uint32 frames, uint8 hops);

    // organisations (Layer 1)
    function register(bytes32 did, bytes calldata pubKey, bytes32[] calldata channelHashes, address controller) external;
    function rotateKey(bytes32 did, bytes calldata newPubKey) external;
    function addChannel(bytes32 did, bytes32 channelHash) external;
    function removeChannel(bytes32 did, bytes32 channelHash) external;
    function setStatus(bytes32 did, Status newStatus) external;

    // carriers (Layer 2)
    function registerHop(bytes32 carrierId, address hopKey, string calldata metaURI, bool translator) external;
    function setHopStatus(address hopKey, Status newStatus) external;
    function attest(bytes32 sid, uint8 hop, bytes32 inClaim, bytes32 outClaim, uint8 codec) external;

    // anchors (Layer 3)
    function anchorSession(bytes32 did, bytes32 sid, bytes32 root, bytes32 ptr, uint32 frames, uint8 hops) external;
    function anchorSessionBatch(bytes32 did, AnchorInput[] calldata items) external;

    // reads (all gasless for the verifier)
    function resolve(bytes32 did) external view returns (Record memory);
    function isAuthorisedChannel(bytes32 did, bytes32 channelHash) external view returns (bool);
    function controllerOf(bytes32 did) external view returns (address);
    function hopOf(address hopKey) external view returns (Hop memory);
    function getAttestations(bytes32 sid) external view returns (Attestation[] memory);
    function attestationCount(bytes32 sid) external view returns (uint256);
    function getAnchor(bytes32 did, bytes32 sid) external view returns (Anchor memory);
    function anchorKey(bytes32 did, bytes32 sid) external view returns (bytes32);
}
