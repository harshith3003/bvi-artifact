// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import {IBVIRegistry} from "./IBVIRegistry.sol";

/// @title BVIRegistry v2
/// @notice Layer 1 identity, Layer 2 attestations and Layer 3 anchors.
///
/// Write-path rule: every write function performs ALL of its checks before it
/// touches storage, so an unauthorised call reverts having written nothing.
///
/// Principals:
///  - registrar: onboards organisations and carriers, authorises channels
///    (number ownership is vetted by the registrar), may suspend or revoke.
///  - controller: the organisation's OWN key. Rotates the organisation's key,
///    writes its anchors, may suspend or revoke its own credential. The registrar
///    cannot be an organisation's controller, so the two revocation principals
///    are always independent.
///  - hop key: a carrier's attesting key, bound to a carrierId by the registrar.
contract BVIRegistry is IBVIRegistry {
    error NotRegistrar();
    error NotController();
    error NotAuthorised();
    error NotAuthorisedToSetStatus();
    error AlreadyRegistered();
    error UnknownDid();
    error DidNotActive();
    error RevokedIsTerminal();
    error CannotSetUnregistered();
    error NoStatusChange();
    error EmptyPublicKey();
    error ZeroDid();
    error ZeroSession();
    error ZeroAddress();
    error ZeroCarrier();
    error EmptyCommitment();
    error ControllerIsRegistrar();
    error ChannelAlreadyAuthorised();
    error ChannelNotAuthorised();
    error TooManyChannels();
    error HopAlreadyRegistered();
    error NotRegisteredHop();
    error HopNotActive();
    error HopOutOfRange();
    error AlreadyAttested();
    error CarrierAlreadyAttested();
    error TooManyAttestations();
    error SessionAlreadyAnchored();
    error EmptyBatch();
    error BatchTooLarge();

    uint8 public constant MAX_HOPS = 32;
    uint256 public constant MAX_CHANNELS_PER_REGISTER = 16;
    uint256 public constant MAX_BATCH = 100;

    address public immutable registrar;

    mapping(bytes32 did => Record) private _records;
    mapping(bytes32 did => address) private _controllers;
    mapping(bytes32 did => mapping(bytes32 channelHash => bool)) private _channels;

    mapping(address hopKey => Hop) private _hopRecs;

    mapping(bytes32 sid => mapping(address attester => Attestation)) private _att;
    mapping(bytes32 sid => mapping(bytes32 carrierId => bool)) private _carrierAttested;
    mapping(bytes32 sid => address[]) private _attesters;

    mapping(bytes32 key => Anchor) private _anchors; // key = anchorKey(did, sid)

    constructor(address registrar_) {
        if (registrar_ == address(0)) revert ZeroAddress();
        registrar = registrar_;
    }

    // ────────────────────────────── organisations ──────────────────────────────

    function register(
        bytes32 did,
        bytes calldata pubKey,
        bytes32[] calldata channelHashes,
        address controller
    ) external override {
        if (msg.sender != registrar) revert NotRegistrar();
        if (did == bytes32(0)) revert ZeroDid();
        if (pubKey.length == 0) revert EmptyPublicKey();
        if (controller == address(0)) revert ZeroAddress();
        if (controller == registrar) revert ControllerIsRegistrar();
        if (_records[did].status != Status.Unregistered) revert AlreadyRegistered();
        if (channelHashes.length > MAX_CHANNELS_PER_REGISTER) revert TooManyChannels();

        bytes32 pkh = keccak256(pubKey);
        _records[did] = Record({
            pubKeyHash: pkh,
            status: Status.Active,
            keyEpoch: 1,
            registeredAt: uint64(block.timestamp),
            updatedAt: uint64(block.timestamp)
        });
        _controllers[did] = controller;
        uint256 n = channelHashes.length;
        for (uint256 i = 0; i < n; ++i) {
            bytes32 ch = channelHashes[i];
            if (!_channels[did][ch]) {
                _channels[did][ch] = true;
                emit ChannelAdded(did, ch);
            }
        }
        emit Registered(did, pkh, pubKey, controller);
        emit StatusChanged(did, Status.Unregistered, Status.Active);
    }

    /// Only the organisation can rotate its own key.
    function rotateKey(bytes32 did, bytes calldata newPubKey) external override {
        Record storage r = _requireKnown(did);
        if (msg.sender != _controllers[did]) revert NotController();
        if (newPubKey.length == 0) revert EmptyPublicKey();

        bytes32 pkh = keccak256(newPubKey);
        uint32 epoch = r.keyEpoch + 1;
        r.pubKeyHash = pkh;
        r.keyEpoch = epoch;
        r.updatedAt = uint64(block.timestamp);
        emit KeyRotated(did, pkh, epoch, newPubKey);
    }

    /// Only the registrar can authorise a number for an organisation: number
    /// ownership is what the registrar vets, so an organisation cannot claim
    /// someone else's number by adding it to itself.
    function addChannel(bytes32 did, bytes32 channelHash) external override {
        _requireKnown(did);
        if (msg.sender != registrar) revert NotRegistrar();
        if (_channels[did][channelHash]) revert ChannelAlreadyAuthorised();

        _channels[did][channelHash] = true;
        _records[did].updatedAt = uint64(block.timestamp);
        emit ChannelAdded(did, channelHash);
    }

    /// Either principal can withdraw a number.
    function removeChannel(bytes32 did, bytes32 channelHash) external override {
        _requireKnown(did);
        if (msg.sender != _controllers[did] && msg.sender != registrar) revert NotAuthorised();
        if (!_channels[did][channelHash]) revert ChannelNotAuthorised();

        _channels[did][channelHash] = false;
        _records[did].updatedAt = uint64(block.timestamp);
        emit ChannelRemoved(did, channelHash);
    }

    /// Either principal can suspend or revoke without the other. Revoked is terminal.
    function setStatus(bytes32 did, Status newStatus) external override {
        Record storage r = _requireKnown(did);
        if (msg.sender != _controllers[did] && msg.sender != registrar) {
            revert NotAuthorisedToSetStatus();
        }
        if (newStatus == Status.Unregistered) revert CannotSetUnregistered();
        Status old = r.status;
        if (old == Status.Revoked) revert RevokedIsTerminal();
        if (old == newStatus) revert NoStatusChange();

        r.status = newStatus;
        r.updatedAt = uint64(block.timestamp);
        emit StatusChanged(did, old, newStatus);
    }

    // ──────────────────────────────── carriers ─────────────────────────────────

    function registerHop(
        bytes32 carrierId,
        address hopKey,
        string calldata metaURI,
        bool translator
    ) external override {
        if (msg.sender != registrar) revert NotRegistrar();
        if (carrierId == bytes32(0)) revert ZeroCarrier();
        if (hopKey == address(0)) revert ZeroAddress();
        if (_hopRecs[hopKey].status != Status.Unregistered) revert HopAlreadyRegistered();

        _hopRecs[hopKey] = Hop({
            carrierId: carrierId,
            status: Status.Active,
            translator: translator,
            registeredAt: uint64(block.timestamp),
            updatedAt: uint64(block.timestamp)
        });
        emit HopRegistered(hopKey, carrierId, translator, metaURI);
    }

    function setHopStatus(address hopKey, Status newStatus) external override {
        if (msg.sender != registrar) revert NotRegistrar();
        Hop storage h = _hopRecs[hopKey];
        if (h.status == Status.Unregistered) revert NotRegisteredHop();
        if (newStatus == Status.Unregistered) revert CannotSetUnregistered();
        Status old = h.status;
        if (old == Status.Revoked) revert RevokedIsTerminal();
        if (old == newStatus) revert NoStatusChange();

        h.status = newStatus;
        h.updatedAt = uint64(block.timestamp);
        emit HopStatusChanged(hopKey, old, newStatus);
    }

    /// Only an Active registered carrier can attest. The slot is keyed by the
    /// attester, so nobody can occupy another carrier's slot, and each carrier
    /// attests at most once per session. Registration is per carrier and does not
    /// require any other carrier to join, so it adds no participation threshold.
    /// `codec` declares the codec this carrier encodes to (0 = passed through).
    function attest(bytes32 sid, uint8 hop, bytes32 inClaim, bytes32 outClaim, uint8 codec) external override {
        if (sid == bytes32(0)) revert ZeroSession();
        if (hop >= MAX_HOPS) revert HopOutOfRange();
        if (inClaim == bytes32(0) || outClaim == bytes32(0)) revert EmptyCommitment();
        Hop storage h = _hopRecs[msg.sender];
        if (h.status == Status.Unregistered) revert NotRegisteredHop();
        if (h.status != Status.Active) revert HopNotActive();
        if (_att[sid][msg.sender].attestor != address(0)) revert AlreadyAttested();
        if (_carrierAttested[sid][h.carrierId]) revert CarrierAlreadyAttested();
        if (_attesters[sid].length >= MAX_HOPS) revert TooManyAttestations();

        _att[sid][msg.sender] = Attestation({
            attestor: msg.sender,
            carrierId: h.carrierId,
            inClaim: inClaim,
            outClaim: outClaim,
            blockTime: uint64(block.timestamp),
            hop: hop,
            translator: h.translator,
            codec: codec
        });
        _carrierAttested[sid][h.carrierId] = true;
        _attesters[sid].push(msg.sender);
        emit Attested(sid, hop, msg.sender, h.carrierId, inClaim, outClaim, codec);
    }

    // ───────────────────────────────── anchors ─────────────────────────────────

    /// Anchor carries (did, sid, root, ptr, T, |Q|); only the organisation's
    /// controller can write it, and only while the credential is Active.
    function anchorSession(
        bytes32 did,
        bytes32 sid,
        bytes32 root,
        bytes32 ptr,
        uint32 frames,
        uint8 hops
    ) external override {
        bytes32 key = _checkAnchor(did, sid, root, ptr, hops);
        _writeAnchor(key, did, sid, root, ptr, frames, hops);
    }

    /// All-or-nothing: any invalid entry reverts the whole batch. Only the
    /// organisation can anchor under its DID, so no third party can poison a batch.
    function anchorSessionBatch(bytes32 did, AnchorInput[] calldata items) external override {
        uint256 n = items.length;
        if (n == 0) revert EmptyBatch();
        if (n > MAX_BATCH) revert BatchTooLarge();
        for (uint256 i = 0; i < n; ++i) {
            AnchorInput calldata it = items[i];
            bytes32 key = _checkAnchor(did, it.sid, it.root, it.ptr, it.hops);
            _writeAnchor(key, did, it.sid, it.root, it.ptr, it.frames, it.hops);
        }
    }

    function _checkAnchor(
        bytes32 did,
        bytes32 sid,
        bytes32 root,
        bytes32 ptr,
        uint8 hops
    ) private view returns (bytes32 key) {
        if (sid == bytes32(0)) revert ZeroSession();
        if (root == bytes32(0) || ptr == bytes32(0)) revert EmptyCommitment();
        Record storage r = _records[did];
        if (r.status == Status.Unregistered) revert UnknownDid();
        if (msg.sender != _controllers[did]) revert NotController();
        if (r.status != Status.Active) revert DidNotActive();
        if (hops > MAX_HOPS) revert HopOutOfRange();
        key = anchorKey(did, sid);
        if (_anchors[key].anchoredBy != address(0)) revert SessionAlreadyAnchored();
    }

    function _writeAnchor(
        bytes32 key,
        bytes32 did,
        bytes32 sid,
        bytes32 root,
        bytes32 ptr,
        uint32 frames,
        uint8 hops
    ) private {
        _anchors[key] = Anchor({
            did: did,
            root: root,
            ptr: ptr,
            frames: frames,
            hops: hops,
            anchoredBy: msg.sender,
            blockTime: uint64(block.timestamp)
        });
        emit SessionAnchored(did, sid, root, ptr, frames, hops);
    }

    // ────────────────────────────────── reads ──────────────────────────────────

    function resolve(bytes32 did) external view override returns (Record memory) {
        return _records[did];
    }

    function isAuthorisedChannel(bytes32 did, bytes32 channelHash) external view override returns (bool) {
        return _channels[did][channelHash];
    }

    function controllerOf(bytes32 did) external view override returns (address) {
        return _controllers[did];
    }

    function hopOf(address hopKey) external view override returns (Hop memory) {
        return _hopRecs[hopKey];
    }

    /// Attestations sorted by hop index (insertion sort; at most MAX_HOPS entries).
    function getAttestations(bytes32 sid) external view override returns (Attestation[] memory) {
        address[] storage who = _attesters[sid];
        uint256 n = who.length;
        Attestation[] memory out = new Attestation[](n);
        for (uint256 i = 0; i < n; ++i) {
            out[i] = _att[sid][who[i]];
        }
        for (uint256 i = 1; i < n; ++i) {
            Attestation memory cur = out[i];
            uint256 j = i;
            while (j > 0 && out[j - 1].hop > cur.hop) {
                out[j] = out[j - 1];
                --j;
            }
            out[j] = cur;
        }
        return out;
    }

    function attestationCount(bytes32 sid) external view override returns (uint256) {
        return _attesters[sid].length;
    }

    function getAnchor(bytes32 did, bytes32 sid) external view override returns (Anchor memory) {
        return _anchors[anchorKey(did, sid)];
    }

    /// Anchors are keyed by (did, sid, chainid): an anchor cannot be presented as
    /// belonging to another organisation or to another chain.
    function anchorKey(bytes32 did, bytes32 sid) public view override returns (bytes32) {
        return keccak256(abi.encode(did, sid, block.chainid));
    }

    function _requireKnown(bytes32 did) private view returns (Record storage r) {
        r = _records[did];
        if (r.status == Status.Unregistered) revert UnknownDid();
    }
}
