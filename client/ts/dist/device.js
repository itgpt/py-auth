"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.loadPersistedDeviceId = loadPersistedDeviceId;
exports.persistDeviceId = persistDeviceId;
exports.buildDeviceId = buildDeviceId;
exports.collectDeviceInfo = collectDeviceInfo;
const node_os_1 = __importDefault(require("node:os"));
const node_path_1 = __importDefault(require("node:path"));
const node_crypto_1 = __importDefault(require("node:crypto"));
const node_fs_1 = __importDefault(require("node:fs"));
const node_machine_id_1 = require("node-machine-id");
function deviceIdStorePath(serverUrl, softwareName) {
    const home = node_os_1.default.homedir();
    const base = node_path_1.default.join(home, ".py_auth_device");
    try {
        node_fs_1.default.mkdirSync(base, { recursive: true });
    }
    catch {
        // ignore
    }
    const serverHash = node_crypto_1.default.createHash("sha256").update(serverUrl, "utf8").digest("hex").slice(0, 12);
    const softwareHash = softwareName
        ? node_crypto_1.default.createHash("sha256").update(softwareName, "utf8").digest("hex").slice(0, 8)
        : "default";
    return node_path_1.default.join(base, `device_${serverHash}_${softwareHash}.txt`);
}
function loadPersistedDeviceId(serverUrl, softwareName) {
    try {
        const p = deviceIdStorePath(serverUrl, softwareName);
        if (!node_fs_1.default.existsSync(p))
            return null;
        const content = node_fs_1.default.readFileSync(p, "utf8").trim();
        return content || null;
    }
    catch {
        return null;
    }
}
function persistDeviceId(serverUrl, softwareName, deviceId) {
    try {
        const p = deviceIdStorePath(serverUrl, softwareName);
        node_fs_1.default.writeFileSync(p, deviceId, "utf8");
    }
    catch {
        // ignore
    }
}
function buildDeviceId(serverUrl, providedDeviceId, softwareName) {
    if (providedDeviceId) {
        persistDeviceId(serverUrl, softwareName, providedDeviceId);
        return providedDeviceId;
    }
    const persisted = loadPersistedDeviceId(serverUrl, softwareName);
    if (persisted)
        return persisted;
    // Node 环境下用机器 ID 做稳定输入；再混入 softwareName 保证同机不同软件不同 device_id
    let base = "";
    try {
        base = (0, node_machine_id_1.machineIdSync)();
    }
    catch {
        base = node_crypto_1.default.randomUUID();
    }
    const deviceId = node_crypto_1.default.createHash("sha256").update(`${base}-${softwareName}`, "utf8").digest("hex").slice(0, 32);
    persistDeviceId(serverUrl, softwareName, deviceId);
    return deviceId;
}
function collectDeviceInfo() {
    const info = {
        hostname: node_os_1.default.hostname(),
        system: node_os_1.default.platform(),
        release: node_os_1.default.release(),
        machine: node_os_1.default.arch(),
    };
    try {
        info.username = node_os_1.default.userInfo().username;
    }
    catch {
        // ignore
    }
    return info;
}
