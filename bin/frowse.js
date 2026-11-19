#!/usr/bin/env node
"use strict";

const { execFileSync, spawnSync } = require("child_process");
const fs = require("fs");
const os = require("os");
const path = require("path");

const pkgRoot = path.resolve(__dirname, "..");

function hasFrowse(pythonBin) {
  try {
    execFileSync(pythonBin, ["-c", "import frowse"], { stdio: "ignore" });
    return true;
  } catch {
    return false;
  }
}

function findPython() {
  if (process.env.FROWSE_PYTHON && fs.existsSync(process.env.FROWSE_PYTHON)) {
    return process.env.FROWSE_PYTHON;
  }

  const localVenv = path.join(pkgRoot, ".venv", "bin", "python");
  if (fs.existsSync(localVenv) && hasFrowse(localVenv)) {
    return localVenv;
  }

  const userVenv = path.join(os.homedir(), ".frowse", "venv", "bin", "python");
  if (fs.existsSync(userVenv) && hasFrowse(userVenv)) {
    return userVenv;
  }

  for (const candidate of ["python3", "python"]) {
    if (hasFrowse(candidate)) {
      return candidate;
    }
  }

  return bootstrapUserVenv();
}

function bootstrapUserVenv() {
  const venvDir = path.join(os.homedir(), ".frowse", "venv");
  const venvPython = path.join(venvDir, "bin", "python");

  console.error("[frowse] First-run setup: creating Python environment in ~/.frowse/venv...");
  fs.mkdirSync(path.dirname(venvDir), { recursive: true });

  const py = ["python3", "python"].find((c) => {
    try {
      execFileSync(c, ["--version"], { stdio: "ignore" });
      return true;
    } catch {
      return false;
    }
  });

  if (!py) {
    console.error("[frowse] Error: Python 3.10+ is required to run frowse.");
    process.exit(1);
  }

  execFileSync(py, ["-m", "venv", venvDir], { stdio: "inherit" });
  execFileSync(venvPython, ["-m", "pip", "install", "--quiet", "--upgrade", "pip"], {
    stdio: "inherit",
  });
  execFileSync(venvPython, ["-m", "pip", "install", "--quiet", pkgRoot], {
    stdio: "inherit",
  });

  return venvPython;
}

const pythonBin = findPython();
const result = spawnSync(pythonBin, ["-m", "frowse.cli", ...process.argv.slice(2)], {
  stdio: "inherit",
});

if (result.error) {
  console.error(`[frowse] Failed to launch: ${result.error.message}`);
  process.exit(1);
}

process.exit(result.status ?? 1);
