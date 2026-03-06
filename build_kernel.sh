#!/bin/bash
set -e

# Configuration
USING_CCACHE="$2"
DIR=$(readlink -f .)
MAIN=$(readlink -f ${DIR}/..)
KERNEL_DEFCONFIG=rodin_defconfig
CLANG_DIR="$MAIN/toolchains/clang"
KERNEL_DIR=$(pwd)
OUT_DIR="$MAIN/out"
ZIMAGE_DIR="$OUT_DIR/arch/arm64/boot"
DTB_DTBO_DIR="$ZIMAGE_DIR/dts/vendor/qcom"
BUILD_START=$(date +"%s")

#KSU setup has already been done
#curl -LSs "https://raw.githubusercontent.com/KernelSU-Next/KernelSU-Next/next/kernel/setup.sh" | bash -

# Function to check for existing Clang
check_clang() {
    if [ -d "$CLANG_DIR" ] && [ -f "$CLANG_DIR/bin/clang" ]; then
        export PATH="$CLANG_DIR/bin:$PATH"
        export KBUILD_COMPILER_STRING="$($CLANG_DIR/bin/clang --version | head -n 1 | perl -pe 's/\(http.*?\)//gs' | sed -e 's/  */ /g' -e 's/[[:space:]]*$//')"
        echo "Found existing Clang: $KBUILD_COMPILER_STRING"
        return 0
    fi
    return 1
}

echo $MAIN
echo $CLANG_DIR

# Install Clang if needed
if ! check_clang; then
    echo "Clang not found :("

    if ! check_clang; then
        echo "Clang installation failed. Exiting..."
        exit 1
    fi
fi

# Set up toolchain
export LD=ld.lld
export ARCH=arm64
export SUBARCH=arm64
export CROSS_COMPILE=aarch64-linux-gnu-

# Include paths
export KERNEL_SRC="$KERNEL_DIR"
INCLUDE_PATHS="
    -I$KERNEL_DIR/include
    -I$KERNEL_DIR/arch/arm64/include
    -I$KERNEL_DIR/drivers/base/regmap
"

# Build flags
# Build flags
if [[ "$USING_CCACHE" == "true" ]] ; then
  MAKE_OPTS=(
    CC="ccache clang"
    STRIP=llvm-strip
    LD=ld.lld
    AR=llvm-ar
    NM=llvm-nm
    OBJCOPY=llvm-objcopy
    OBJDUMP=llvm-objdump
    HOSTCC="ccache clang"
    HOSTCXX="ccache clang++"
    HOSTAR=llvm-ar
    HOSTLD=ld.lld
    LLVM=1
    LLVM_IAS=1
  )
else
  MAKE_OPTS=(
    CC=clang
    STRIP=llvm-strip
    LD=ld.lld
    AR=llvm-ar
    NM=llvm-nm
    OBJCOPY=llvm-objcopy
    OBJDUMP=llvm-objdump
    HOSTCC=clang
    HOSTCXX=clang++
    HOSTAR=llvm-ar
    HOSTLD=ld.lld
    LLVM=1
    LLVM_IAS=1
  )
fi

# Apply YYLLOC workaround
echo "Applying YYLLOC workaround..."
YYLL1="$KERNEL_DIR/scripts/dtc/dtc-lexer.lex.c_shipped"
YYLL2="$KERNEL_DIR/scripts/dtc/dtc-lexer.l"
[ -f "$YYLL1" ] && sed -i "s/extern YYLTYPE yylloc/YYLTYPE yylloc/g;s/YYLTYPE yylloc/extern YYLTYPE yylloc/g" "$YYLL1"
[ -f "$YYLL2" ] && sed -i "s/extern YYLTYPE yylloc/YYLTYPE yylloc/g;s/YYLTYPE yylloc/extern YYLTYPE yylloc/g" "$YYLL2"

# Start build process
echo "**** Building with $KBUILD_COMPILER_STRING ****"
echo "**** Defconfig: $KERNEL_DEFCONFIG ****"

# Build kernel
make O="$OUT_DIR" $KERNEL_DEFCONFIG "${MAKE_OPTS[@]}" $INCLUDE_PATHS || exit 1
make -j$(nproc --all) O="$OUT_DIR" "${MAKE_OPTS[@]}" || exit 1


# Restore YYLL files if in git repo
[ -d "$KERNEL_DIR"/.git ] && git restore "$YYLL1" "$YYLL2" 2>/dev/null || true

# Create temporary anykernel directory
TIME=$(date "+%Y%m%d-%H%M%S")
TEMP_ANY_KERNEL_DIR=$(readlink -f ${DIR}/../../AnyKernel3)

# Copy kernel image
if [ -f "$ZIMAGE_DIR/Image.gz-dtb" ]; then
    cp -v "$ZIMAGE_DIR/Image.gz-dtb" "$TEMP_ANY_KERNEL_DIR/"
elif [ -f "$ZIMAGE_DIR/Image.gz" ]; then
    cp -v "$ZIMAGE_DIR/Image.gz" "$TEMP_ANY_KERNEL_DIR/"
elif [ -f "$ZIMAGE_DIR/Image" ]; then
    cp -v "$ZIMAGE_DIR/Image" "$TEMP_ANY_KERNEL_DIR/"
fi

# Create zip file in kernel root directory
echo "Creating zip package..."
ZIP_NAME="rodin-6.6.102-$1-$TIME-AnyKernel3.zip"
cd "$TEMP_ANY_KERNEL_DIR"
zip -r9 "$KERNEL_DIR/$ZIP_NAME" ./*
cd ..

# Clean up temporary directory

BUILD_END=$(date +"%s")
DIFF=$((BUILD_END - BUILD_START))
echo -e "\nBuild completed in $((DIFF / 60))m $((DIFF % 60))s"
echo "Final zip: $KERNEL_DIR/$ZIP_NAME"
echo "Zip size: $(du -h "$KERNEL_DIR/$ZIP_NAME" | cut -f1)"
