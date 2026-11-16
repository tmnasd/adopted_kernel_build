"""Record build provenance and collect bounded diagnostics without repository URLs."""

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from datetime import datetime, timezone


def command(*args, cwd=None):
    result = subprocess.run(args, cwd=cwd, text=True, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, check=False)
    if result.returncode:
        raise RuntimeError(f"{args[0]} exited {result.returncode}: {result.stdout}")
    return result.stdout.strip()


def snapshot(workspace, artifacts):
    config = os.environ.get("CONFIG", "android15-6.6")
    inputs = json.loads(os.environ.get("BUILD_INPUTS", "{}"))
    # Source/toolchain URLs can contain credentials; resolved commits identify sources.
    inputs.pop("custom_kernel_source", None)
    inputs.pop("clang_custom_link", None)
    repositories = {}
    roots = [workspace, workspace / config]
    for root in roots:
        for path in sorted(root.iterdir()):
            if path.is_dir() and (path / ".git").exists():
                repositories[str(path.relative_to(workspace))] = {
                    "commit": command("git", "rev-parse", "HEAD", cwd=path),
                    "changes": command("git", "diff", "--stat", "HEAD", cwd=path),
                }
    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "workflow_commit": os.environ.get("GITHUB_SHA"),
        "run_url": f"{os.environ.get('GITHUB_SERVER_URL', 'https://github.com')}/"
                   f"{os.environ.get('GITHUB_REPOSITORY', '')}/actions/runs/"
                   f"{os.environ.get('GITHUB_RUN_ID', '')}",
        "inputs": inputs,
        "repositories": repositories,
        "validation": "Bazel analysis only" if inputs.get("use_bazel") and inputs.get("prepare_only")
                      else "Generated kernel configuration",
    }
    clang = workspace / config / "toolchains" / "clang" / "bin" / "clang"
    if clang.is_file() and not inputs.get("use_bazel"):
        manifest["compiler"] = command(str(clang), "--version")
    repo = workspace / "git-repo" / "repo"
    if inputs.get("use_bazel") and repo.is_file():
        (artifacts / "kleaf-manifest.xml").write_text(
            command(str(repo), "manifest", "-r", cwd=workspace / config), encoding="utf-8")
    (artifacts / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def finalize(workspace, artifacts):
    config = workspace / os.environ.get("CONFIG", "android15-6.6")
    kernel = config / "common"
    defconfig = os.environ.get("DEFCONFIG", "")
    if defconfig:
        source = kernel / "arch" / "arm64" / "configs" / defconfig
        if source.is_file():
            shutil.copy2(source, artifacts / "defconfig.prepared")
    for root, label in [(config / "out", "make"), (config / "dist", "kleaf")]:
        if root.is_dir():
            for path in root.rglob("*"):
                if path.is_file() and (path.name == ".config" or path.suffix == ".config"):
                    target = artifacts / "configs" / label / path.relative_to(root)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(path, target)
    if kernel.is_dir():
        for path in kernel.rglob("*.rej"):
            target = artifacts / "patch-rejects" / path.relative_to(kernel)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
    (artifacts / "resources.txt").write_text(
        command("df", "-h") + "\n\n" + command("free", "-h") + "\n", encoding="utf-8")
    if shutil.which("ccache"):
        (artifacts / "ccache.txt").write_text(command("ccache", "--show-stats") + "\n", encoding="utf-8")
    manifest_path = artifacts / "manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    else:
        manifest = {"note": "Preparation failed before source snapshot"}
    manifest["result"] = os.environ.get("BUILD_RESULT", "unknown")
    manifest["duration_seconds"] = os.environ.get("BUILD_DURATION_SECONDS")
    image = os.environ.get("KERNEL_IMAGE")
    if image and Path(image).is_file():
        with open(image, "rb") as stream:
            manifest["kernel_image"] = {"name": Path(image).name,
                                        "bytes": Path(image).stat().st_size,
                                        "sha256": hashlib.file_digest(stream, "sha256").hexdigest()}
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    summary = [f"Build result: **{manifest['result']}**", "",
               f"Prepare only: `{os.environ.get('PREPARE_ONLY', 'false')}`", "",
               f"Build/validation duration: {os.environ.get('BUILD_DURATION_SECONDS', 'unavailable')} seconds", "",
               "Artifacts include source revisions, configuration, checksums and diagnostics.", ""]
    for name, repository in manifest.get("repositories", {}).items():
        summary.append(f"- `{name}`: `{repository['commit']}`")
    summary.extend(["", "Selected settings:", "", "```json",
                    json.dumps(manifest.get("inputs", {}), indent=2), "```", ""])
    if (artifacts / "ccache.txt").exists():
        summary.extend(["ccache statistics:", "```text",
                        (artifacts / "ccache.txt").read_text(encoding="utf-8"), "```", ""])
    for archive in sorted(artifacts.glob("*.zip")):
        summary.append(f"- {archive.name}: {archive.stat().st_size:,} bytes")
    summary.extend(["", "See build.log for build duration and compiler output."])
    (artifacts / "release-notes.md").write_text("\n".join(summary) + "\n", encoding="utf-8")
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as stream:
            stream.write("\n".join(summary) + "\n")
    hashes = []
    for path in sorted(artifacts.rglob("*")):
        if path.is_file() and path.name != "SHA256SUMS":
            with path.open("rb") as stream:
                hashes.append(f"{hashlib.file_digest(stream, 'sha256').hexdigest()}  {path.relative_to(artifacts).as_posix()}")
    (artifacts / "SHA256SUMS").write_text("\n".join(hashes) + "\n", encoding="utf-8")


if __name__ == "__main__":
    workspace = Path(os.environ["GITHUB_WORKSPACE"])
    artifacts = workspace / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    if sys.argv[1:] == ["snapshot"]:
        snapshot(workspace, artifacts)
    elif sys.argv[1:] == ["finalize"]:
        finalize(workspace, artifacts)
    else:
        raise SystemExit("Usage: build_report.py snapshot|finalize")
