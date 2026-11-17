const { contextBridge } = require("electron");
const pkg = require("../package.json");

contextBridge.exposeInMainWorld("verilumenDesktop", {
  offline: true,
  appVersion: pkg.version,
});
