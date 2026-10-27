// Generates the shreder_binary (preconf flavour) client + server stubs from the vendored proto.
// protoc comes from the protoc-bin-vendored crate, so no system protoc is needed.
fn main() {
    if std::env::var("PROTOC").is_err() {
        let protoc = protoc_bin_vendored::protoc_bin_path().expect("vendored protoc");
        std::env::set_var("PROTOC", protoc);
    }
    let wkt = protoc_bin_vendored::include_path().expect("vendored protoc include path");
    println!("cargo:rerun-if-changed=proto/shreder_preconf.proto");
    tonic_prost_build::configure()
        .build_client(true)
        .build_server(true) // the server stub is used only by the local fake-server test
        .compile_protos(
            &[std::path::PathBuf::from("proto/shreder_preconf.proto")],
            &[std::path::PathBuf::from("proto"), wkt],
        )
        .expect("compile shreder_preconf.proto");
}
