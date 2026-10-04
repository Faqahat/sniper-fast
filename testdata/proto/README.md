# Vendored Yellowstone proto text (PLAN WP-03 item 4)

arbx decodes Yellowstone gRPC with hand-written prost structs (`src/feeds/grpc.rs`, no protoc). Their field numbers
are pinned against this text by the tests in `src/feeds/grpc.rs` (`field_numbers_match_the_vendored_proto`, the
round-trip tests) and by the synthetic stream fixture `testdata/grpc/stream.bin`, which is encoded from these files'
field numbers by an encoder that never uses the prost structs (`src/feeds/fixture.rs`).

| File | Source | sha256 |
|---|---|---|
| `geyser.proto` | rpcpool/yellowstone-grpc, `yellowstone-grpc-proto/proto/geyser.proto` (master as fetched 2026-10-03 into a local scratch copy; it has `SubscribeDeshred`, the block footer and the deshred update-parent messages) | 56244cb007a872f28e294eedba0db4ae4bcbfb401035e4fbb8ec9c347d8ee9b3 |
| `solana-storage.proto` | the same repository, `yellowstone-grpc-proto/proto/solana-storage.proto` (same fetch; has `Message.config` for v1 transactions) | e5d16ba9a9e83f6ed8c92a96b6b75dfd64c43f897b976011eb3ec5abe2f3c818 |
| `google/protobuf/timestamp.proto` | protobuf's well-known `Timestamp`, reduced to its message | — |

Updating: replace the files with a newer upstream copy, update the hashes here and run `cargo test --release`; a
renumbered field fails the tests. Regenerate the stream fixture with `ARBX_WRITE_FIXTURES=1 cargo test --release
grpc_stream_fixture` and review the diff.
