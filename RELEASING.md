# Verilumen - ATE: Release & Delta Update Guide

This document describes how to package, publish, and ship delta (differential) auto-updates for **Verilumen - ATE** to end-users without requiring full-app re-downloads.

---

## 1. Versioning Strategy (Single Source of Truth)

Versions follow strict **Semantic Versioning** (`MAJOR.MINOR.PATCH`):
- **PATCH** (`1.1.0` -> `1.1.1`): Bug fixes, telemetry corrections, minor UI adjustments.
- **MINOR** (`1.1.0` -> `1.2.0`): New agent integrations, data schema extensions, feature additions.
- **MAJOR** (`1.1.0` -> `2.0.0`): Architecture overhauls or breaking changes.

The single source of truth is kept in:
- `desktop/package.json` (`"version": "1.1.0"`)
- Synced automatically with `version.json` and the in-app footer/header badges.

---

## 2. How to Build a Release

Run the one-command build script from the repository root:

```powershell
# Using PowerShell:
.\build_release.ps1

# Or double-click / run:
build_release.bat
```

This pipeline automatically:
1. Validates and compiles the Next.js production frontend.
2. Stages the offline Python & Node runtime bundles.
3. Invokes `electron-builder` with NSIS packaging.
4. Generates three release assets in `desktop/dist/`:
   - `Verilumen-ATE-Setup-<version>.exe` (Full per-user offline installer).
   - `Verilumen-ATE-Setup-<version>.exe.blockmap` (Byte-level differential blockmap).
   - `latest.yml` (Metadata hash file that powers delta updates).

---

## 3. How to Publish an Update (e.g. 1.1.1)

### Manual Publishing via GitHub Releases:
1. Update `"version"` in `desktop/package.json` (e.g., from `1.1.0` to `1.1.1`).
2. Run `.\build_release.ps1`.
3. Go to your GitHub repository -> **Releases** -> **Draft a new release**.
4. Set Tag to `v1.1.1` (create tag on publish).
5. Set Release title to `Verilumen - ATE v1.1.1`.
6. Attach all 3 generated files from `desktop/dist/`:
   - `Verilumen-ATE-Setup-1.1.1.exe`
   - `Verilumen-ATE-Setup-1.1.1.exe.blockmap`
   - `latest.yml`
7. Click **Publish release**.

### Automated Publishing via Git Tag:
When you push a tag matching `v*.*.*`:
```bash
git tag v1.1.1
git push origin v1.1.1
```
The included GitHub Actions workflow (`.github/workflows/release.yml`) builds the installer and differential blockmaps on Windows and publishes the release automatically.

---

## 4. How the Delta Auto-Update Works

1. On app startup, `electron-updater` checks the GitHub repository for `latest.yml`.
2. If a higher version exists, `electron-updater` downloads **only the changed chunks** using the `.blockmap` file (typically only 5–30 MB instead of the full ~500 MB installer).
3. The app displays an update dialog:
   ```
   Update Available: A new version of Verilumen - ATE (v1.1.1) has been downloaded.
   Restart now to apply?
   [ Restart to Update ]    [ Later ]
   ```
4. Clicking **Restart to Update** cleanly stops local agent processes and relaunches on the new version.
5. If the user is offline, the update check silently bypasses without blocking the user.

---

## 5. Windows Defender & SmartScreen Guidance

Because this installer is built directly for Windows users, Windows Defender and SmartScreen evaluate executable reputation:

### (a) Production Code Signing (Zero SmartScreen Warnings)
For corporate / production distribution without warnings, sign the executable:
- **Option 1: Standard Certificate (OV or EV):**
  Set environment variables on your build machine before running `build_release.ps1`:
  ```powershell
  $env:CSC_LINK = "C:\path\to\certificate.pfx"     # or base64 string
  $env:CSC_KEY_PASSWORD = "YourCertPassword"
  ```
  `electron-builder` automatically detects these variables and signs the setup executable and uninstaller.
- **Option 2: Microsoft Azure Trusted Signing:**
  Cloud-based HSM code signing requiring no physical USB dongle. Ideal for CI/CD GitHub Actions pipelines.

### (b) Early Testers & Internal Distribution (Unsigned)
When sharing initial builds with colleagues or testers before purchasing a certificate:
1. Windows SmartScreen may show: *"Windows protected your PC"*.
2. Instruct users to click **"More info"** -> **"Run anyway"**.
3. The app will install cleanly into `%LOCALAPPDATA%\Verilumen-ATE` without requiring administrator privileges.

### (c) Submitting False Positives to Microsoft
To eliminate warnings even on unsigned or newly published binaries:
1. Go to the [Microsoft Security Intelligence File Submission Portal](https://www.microsoft.com/en-us/wdsi/filesubmission).
2. Choose **"Software developer"**, upload `Verilumen-ATE-Setup-<version>.exe`, and select **"Incorrectly detected as malware / false positive"**.
3. Microsoft's automated scanner typically approves the binary within a few hours, clearing Defender and SmartScreen definitions worldwide.
