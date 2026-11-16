#!/bin/bash
set -euo pipefail

SOURCE="$(cd "$(dirname "$0")/.." && pwd)/build_kernel.sh"
FIXTURE="$(mktemp -d)"
trap 'rm -rf "$FIXTURE"' EXIT
mkdir -p "$FIXTURE/common/arch/arm64/configs" "$FIXTURE/toolchains/clang/bin" "$FIXTURE/bin" "$FIXTURE/tools"
cp "$SOURCE" "$FIXTURE/common/build_kernel.sh"
printf 'CONFIG_KSU=y\nCONFIG_BBG=y\nCONFIG_LSM="selinux,baseband_guard"\n' > "$FIXTURE/common/arch/arm64/configs/test_defconfig"
cat > "$FIXTURE/toolchains/clang/bin/clang" <<'EOF'
#!/bin/bash
echo 'mock clang'
EOF
cat > "$FIXTURE/bin/make" <<'EOF'
#!/bin/bash
if [[ "$*" == *test_defconfig* ]]; then
    mkdir -p ../out
    cp arch/arm64/configs/test_defconfig ../out/.config
else
    touch ../compiled
    mkdir -p ../out/arch/arm64/boot
    echo image > ../out/arch/arm64/boot/Image
fi
EOF
cat > "$FIXTURE/tools/bazel" <<'EOF'
#!/bin/bash
printf '%s\n' "$*" >> bazel-calls
if [[ "$1" == run ]]; then
    mkdir -p dist
    cp common/arch/arm64/configs/test_defconfig dist/.config
    echo image > dist/Image
fi
EOF
chmod +x "$FIXTURE/toolchains/clang/bin/clang" "$FIXTURE/bin/make" "$FIXTURE/tools/bazel"
export PATH="$FIXTURE/bin:$PATH"
export EXPECT_KSU=true EXPECT_BBG=true EXPECT_SUSFS=false
cd "$FIXTURE/common"

PREPARE_ONLY=true bash build_kernel.sh test_defconfig test false
test ! -f ../compiled
EXPECT_SUSFS=true PREPARE_ONLY=true bash build_kernel.sh test_defconfig test false > ../missing-feature.log 2>&1 && exit 1
grep -q 'Requested CONFIG_KSU_SUSFS=y missing' ../missing-feature.log
bash build_kernel.sh test_defconfig test false
test -s ../out/arch/arm64/boot/Image
BUILD_WITH_BAZEL=true PREPARE_ONLY=true bash build_kernel.sh test_defconfig test false
grep -qx 'query //common:kernel_aarch64_dist' ../bazel-calls
grep -qx 'build --nobuild //common:kernel_aarch64_dist' ../bazel-calls
test ! -d ../dist
BUILD_WITH_BAZEL=true bash build_kernel.sh test_defconfig test false
test -s ../dist/Image
sed -i '/CONFIG_KSU=/d' arch/arm64/configs/test_defconfig
BUILD_WITH_BAZEL=true bash build_kernel.sh test_defconfig test false > ../invalid-config.log 2>&1 && exit 1
grep -q 'Requested CONFIG_KSU=y missing' ../invalid-config.log
echo 'Build script checks passed'
