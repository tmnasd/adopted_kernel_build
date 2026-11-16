# Rodin Android 15 / Linux 6.6 builds

Run the build from the Actions tab using **Build kernel for Rodin - A15 6.6**.
The workflow supports Make and Bazel/Kleaf with the selected source and patches.

- **prepare_only** applies the selected patches and checks preparation without
  compiling or creating a flashable ZIP. Make resolves the defconfig and checks
  requested KSU, SUSFS and BBG settings. Bazel queries and analyzes the dist target;
  its prepare-only check reads the edited defconfig, not the final generated config.
- Normal builds check requested feature flags in the generated configuration.
  BBG also requires `baseband_guard` in `CONFIG_LSM`. A Kleaf dist target must export
  `.config` to permit verification before packaging.
- Artifacts are uploaded on success and failure. They include the build log when
  compilation/validation started, original/prepared defconfigs, available generated
  configs, patch rejects, resource information and ccache statistics when available.
- `manifest.json` records selected inputs, resolved repository commits, compiler
  information for Make builds, result and kernel image checksum. Source/toolchain
  URLs are excluded because they may contain credentials. Kleaf builds also save
  the resolved repo manifest. Floating setup scripts and downloaded patches still
  need pinning for fully reproducible builds; this report provides traceability.
- `SHA256SUMS` covers the artifact files. Verify after downloading and extracting
  the Actions artifact with `sha256sum -c SHA256SUMS`.
- **draft_release** optionally creates a draft release after a successful full
  build, containing ZIPs, metadata and checksums. Prepare-only runs never publish.

The Actions summary shows the outcome and package sizes. Logs and diagnostics may
contain source details; review them before sharing artifacts outside the project.

Local checks (Python 3.11+ and Bash):

```bash
bash tests/build_kernel_test.sh
python -m unittest discover -s tests -p 'test_*.py'
```

Suggested presets for the existing dispatch form (other settings retain defaults):

| Preset | KernelSU | SUSFS | BBG | Prepare only | Draft release |
| --- | --- | --- | --- | --- | --- |
| Minimal | None | false | false | false | false |
| Daily | KowSU | true | true | false | false |
| Experimental preparation | Your selected variant | As needed | As needed | true | false |

These are documented recipes; each input remains explicitly selectable in Actions.
