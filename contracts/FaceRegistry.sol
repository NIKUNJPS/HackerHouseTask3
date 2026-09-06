// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @title FaceRegistry
/// @notice Tamper-evident, append-only registry of face-identification records.
///         Each record is stored under a 32-byte fingerprint (keccak256 of a
///         canonical JSON describing: the scanned face, the matching social-media
///         post that was discovered, and the match score). Once written a record
///         can never be altered or removed, which is exactly what makes it a
///         verifiable, tamper-evident proof.
contract FaceRegistry {
    struct Record {
        uint64  timestamp;   // block time the record was anchored
        address submitter;   // account that anchored it
        string  uri;         // human-readable pointer (the social post URL)
    }

    // fingerprint => record
    mapping(bytes32 => Record) private _records;
    // ordered list of every fingerprint ever anchored (for enumeration / audit)
    bytes32[] private _fingerprints;

    event RecordAnchored(
        bytes32 indexed fingerprint,
        address indexed submitter,
        uint64  timestamp,
        string  uri
    );

    /// @notice Anchor a new record. Reverts if the fingerprint already exists,
    ///         guaranteeing immutability (a fingerprint maps to exactly one record).
    function anchor(bytes32 fingerprint, string calldata uri) external {
        require(fingerprint != bytes32(0), "empty fingerprint");
        require(_records[fingerprint].timestamp == 0, "already anchored");

        _records[fingerprint] = Record({
            timestamp: uint64(block.timestamp),
            submitter: msg.sender,
            uri: uri
        });
        _fingerprints.push(fingerprint);

        emit RecordAnchored(fingerprint, msg.sender, uint64(block.timestamp), uri);
    }

    /// @notice True if a record has been anchored under this fingerprint.
    function exists(bytes32 fingerprint) external view returns (bool) {
        return _records[fingerprint].timestamp != 0;
    }

    /// @notice Read a record back for verification.
    function getRecord(bytes32 fingerprint)
        external
        view
        returns (uint64 timestamp, address submitter, string memory uri)
    {
        Record storage r = _records[fingerprint];
        return (r.timestamp, r.submitter, r.uri);
    }

    /// @notice Total number of records anchored.
    function recordCount() external view returns (uint256) {
        return _fingerprints.length;
    }

    /// @notice Fingerprint at a given index (audit / enumeration).
    function fingerprintAt(uint256 index) external view returns (bytes32) {
        require(index < _fingerprints.length, "index out of range");
        return _fingerprints[index];
    }
}
