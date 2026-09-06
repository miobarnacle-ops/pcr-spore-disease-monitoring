const { contextBridge } = require("electron");

contextBridge.exposeInMainWorld("suixunDesktop", {
  platform: "windows",
  mode: "showcase",
});
