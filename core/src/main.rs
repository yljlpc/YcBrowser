//! OmniBrowser 核心守护进程：通过 stdin/stdout 提供行式 JSON-RPC。
//!
//! 由 PyQt6 前端以子进程方式拉起，长连接复用。用法：
//!   echo '{"cmd":"ping"}' | omnibrowser-core

fn main() {
    omnibrowser_core::ipc::run();
}
