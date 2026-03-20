#!/bin/bash
# reinstall_m1n1.sh — Install m1n1 into the Linux stub volume.
#
# Original simple approach (confirmed working on A18 Pro, macOS 26):
#   1. Create a simple APFS volume (no volume group needed)
#   2. From macOS 1TR: csrutil disable, bputil -nkcas, kmutil, bless
#   3. Subsequent updates just overwrite the boot object (no 1TR needed)
#
# Modes:
#
#   FAST UPDATE (default) — overwrites the boot object on Preboot.
#     Works from macOS or 1TR. No bputil/kmutil needed.
#       sudo sh reinstall_m1n1.sh
#
#   FIRST-TIME SETUP — bputil + kmutil + bless from macOS 1TR.
#     Run from macOS 1TR (hold power → Options → Terminal).
#     Requires csrutil disable + bputil -nkcas to have been run first.
#       sh reinstall_m1n1.sh --setup
#
#   CREATE STUB — creates the Linux APFS partition from macOS.
#     After this, reboot to macOS 1TR for --setup.
#       sudo sh reinstall_m1n1.sh --create-stub

set -euo pipefail

die() { echo "ERROR: $*" >&2; exit 1; }

MODE="fast"
[ "${1:-}" = "--setup" ]       && MODE="setup"
[ "${1:-}" = "--create-stub" ] && MODE="create-stub"

# --- Config -----------------------------------------------------------------

_dl=$(diskutil list)
: "${DATA_DEV:=$(echo "$_dl" | awk '/APFS Volume[[:space:]]+Data[[:space:]]/ { print $NF; exit }')}"
[ -n "$DATA_DEV" ] || die "could not find APFS volume named 'Data' — set DATA_DEV"

MACOS_CONTAINER=$(diskutil info "$DATA_DEV" | awk '/APFS Container/{print $NF}') || true

# Find Linux stub volume (any volume named exactly "Linux")
STUB_DEV=""
for _dev in $(echo "$_dl" | awk '/APFS Volume[[:space:]]+Linux/ { print $NF }'); do
    _info=$(diskutil info "$_dev" 2>/dev/null) || continue
    _name=$(echo "$_info" | awk -F: '/Volume Name/{gsub(/^[[:space:]]+/,"",$2); print $2}')
    [ "$_name" = "Linux" ] || continue
    STUB_DEV="$_dev"
    break
done

if [ -z "$STUB_DEV" ] && [ "$MODE" != "create-stub" ]; then
    die "could not find Linux volume — run --create-stub from macOS first"
fi

DATA_MOUNT="/Volumes/Data"
STUB_MOUNT="/Volumes/Linux"
M1N1_RAW="$DATA_MOUNT/Users/rusch/Projects/m1n1/build/m1n1.bin"
XNU_KC="$DATA_MOUNT/Users/rusch/Projects/asahi_neo/research/firmware/kernelcache.mac17g.bin"
M1N1_BIN="$DATA_MOUNT/Users/rusch/Projects/m1n1/build/m1n1-xnu-payload.bin"
M1N1_MIN_BYTES=524288

STUB_UUID=""
PREBOOT_DEV=""
PREBOOT_MOUNT=""
BOOT_KC=""

echo "==> m1n1 reinstall ($MODE mode)"
echo "    DATA=$DATA_DEV  STUB=${STUB_DEV:-(not found)}"

# --- Helpers ----------------------------------------------------------------

mount_data() {
    if ! diskutil info "$DATA_DEV" | grep -q "Mounted:.*Yes"; then
        echo "==> Unlocking Data volume ($DATA_DEV) ..."
        diskutil apfs unlockVolume "$DATA_DEV"
    else
        echo "==> Data volume already mounted"
    fi
}

verify_m1n1() {
    [ -f "$M1N1_RAW" ] || die "m1n1.bin not found at $M1N1_RAW"
    M1N1_SIZE=$(stat -f%z "$M1N1_RAW")
    [ "$M1N1_SIZE" -ge "$M1N1_MIN_BYTES" ] \
        || die "m1n1.bin is only ${M1N1_SIZE} bytes — looks wrong"
    echo "    m1n1.bin: $(ls -lh "$M1N1_RAW" | awk '{print $5}')"
}

build_payload() {
    if [ -f "$XNU_KC" ]; then
        echo "==> Building m1n1 + XNU kernelcache payload ..."
        cat "$M1N1_RAW" "$XNU_KC" > "$M1N1_BIN"
        echo "    payload: $(ls -lh "$M1N1_BIN" | awk '{print $5}')"
    else
        echo "==> No XNU kernelcache — using plain m1n1"
        cp "$M1N1_RAW" "$M1N1_BIN"
    fi
}

find_boot_object() {
    STUB_UUID=$(diskutil info "$STUB_DEV" | awk '/Volume UUID/{print $NF}') || true
    [ -n "$STUB_UUID" ] || die "cannot determine stub volume UUID"

    local container
    container=$(diskutil info "$STUB_DEV" | awk '/APFS Container/{print $NF}') || true
    [ -n "$container" ] || die "cannot determine stub container"

    PREBOOT_DEV=$(diskutil list "$container" | awk '/APFS Volume[[:space:]]+Preboot/ {print $NF}') || true
    [ -n "$PREBOOT_DEV" ] || die "cannot find Preboot volume in $container"

    if ! diskutil info "$PREBOOT_DEV" | grep -q "Mounted:.*Yes"; then
        echo "==> Mounting Preboot ($PREBOOT_DEV) ..."
        diskutil mount "$PREBOOT_DEV"
    fi
    PREBOOT_MOUNT=$(diskutil info "$PREBOOT_DEV" | awk -F: '/Mount Point/{gsub(/^[[:space:]]+/,"",$2); print $2}')
    [ -d "$PREBOOT_MOUNT" ] || die "Preboot mount point not found"

    local boot_dir="$PREBOOT_MOUNT/$STUB_UUID/boot"
    if [ ! -d "$boot_dir" ]; then
        echo "    boot directory not found at $boot_dir (fresh volume)"
        return 1
    fi

    local hash_dir
    hash_dir=$(find "$boot_dir" -maxdepth 1 -mindepth 1 -type d 2>/dev/null | head -1)
    if [ -z "$hash_dir" ]; then
        echo "    no boot hash directory in $boot_dir (kmutil will create it)"
        return 1
    fi

    local kc_dir="$hash_dir/System/Library/Caches/com.apple.kernelcaches"
    BOOT_KC_DIR="$kc_dir"
    BOOT_KC=""
    local custom_count
    custom_count=$(find "$kc_dir" -name "kernelcache.custom.*" 2>/dev/null | wc -l | tr -d ' ')

    if [ "$custom_count" -eq 1 ]; then
        BOOT_KC=$(find "$kc_dir" -name "kernelcache.custom.*" 2>/dev/null)
        echo "    boot object: $BOOT_KC"
        echo "    size: $(ls -lh "$BOOT_KC" | awk '{print $5}')"
    elif [ "$custom_count" -gt 1 ]; then
        BOOT_KC=$(ls -t "$kc_dir"/kernelcache.custom.* 2>/dev/null | head -1)
        echo "    boot object: $BOOT_KC (newest of $custom_count)"
    else
        echo "    no kernelcache.custom.* found — need --setup"
    fi
}

# --- Fast update mode -------------------------------------------------------

if [ "$MODE" = "fast" ]; then
    [ "$(id -u)" -eq 0 ] || die "must run as root (use sudo)"
    mount_data
    verify_m1n1
    build_payload
    find_boot_object || die "no boot structure — run --setup from 1TR first"
    [ -n "$BOOT_KC" ] && [ -f "$BOOT_KC" ] \
        || die "no kernelcache.custom.* — run --setup from 1TR first"

    first_byte=$(xxd -l 1 -p "$BOOT_KC")
    if [ "$first_byte" = "30" ]; then
        echo "    format: im4p/img4 (DER-wrapped)"
        echo "==> Wrapping payload in im4p container ..."
        WRAPPED="/tmp/m1n1_im4p_$$.bin"
        python3 "$DATA_MOUNT/Users/rusch/Projects/asahi_neo/scripts/wrap_im4p.py" \
            "$M1N1_BIN" "$WRAPPED" rkrn \
            || die "im4p wrapping failed"
        echo "==> Overwriting boot object in place ..."
        cp "$WRAPPED" "$BOOT_KC"
        rm -f "$WRAPPED"
    else
        echo "    format: raw binary"
        echo "==> Overwriting boot object in place ..."
        cp "$M1N1_BIN" "$BOOT_KC"
    fi
    echo "    done: $(ls -lh "$BOOT_KC" | awk '{print $5}')"

    active_name=$(basename "$BOOT_KC")
    stale_count=$(find "$BOOT_KC_DIR" -name "kernelcache.custom.*" ! -name "$active_name" 2>/dev/null | wc -l | tr -d ' ')
    if [ "$stale_count" -gt 0 ]; then
        echo "==> Cleaning $stale_count stale kernelcache.custom.* files ..."
        find "$BOOT_KC_DIR" -name "kernelcache.custom.*" ! -name "$active_name" -delete
    fi

    echo ""
    echo "Done. Reboot to test (hold power → select Linux)."
    exit 0
fi

# --- Create stub mode (macOS only) ------------------------------------------

if [ "$MODE" = "create-stub" ]; then
    [ "$(id -u)" -eq 0 ] || die "must run as root (use sudo)"

    if [ -n "$STUB_DEV" ]; then
        echo "Linux volume already exists at $STUB_DEV — delete it first if you want to recreate"
        exit 0
    fi

    # Create a new partition with APFS container
    echo "==> Creating Linux partition ..."
    diskutil addPartition disk0s2 apfs Linux 2.5GB \
        || die "failed to create partition"

    echo ""
    echo "Done. Now reboot to macOS 1TR (hold power → Options → Terminal) and run:"
    echo ""
    echo "  # 1. Disable SIP and set permissive security:"
    echo "  csrutil disable"
    echo "  bputil -nkcas"
    echo "  #    (select Linux when prompted, enter your macOS credentials)"
    echo ""
    echo "  # 2. Install m1n1:"
    echo "  diskutil apfs unlockVolume disk4s5"
    echo "  sh /Volumes/Data/Users/rusch/Projects/asahi_neo/scripts/reinstall_m1n1.sh --setup"
    exit 0
fi

# --- First-time setup mode (macOS 1TR) --------------------------------------
# Prerequisite: csrutil disable + bputil -nkcas already run from 1TR.

[ -n "$STUB_DEV" ] || die "Linux volume not found"
[ "$(id -u)" -eq 0 ] || die "must run as root (are you in 1TR Terminal?)"

mount_data
verify_m1n1
build_payload

# Mount stub
if ! diskutil info "$STUB_DEV" | grep -q "Mounted:.*Yes"; then
    echo "==> Mounting stub volume ($STUB_DEV) ..."
    diskutil mount "$STUB_DEV"
fi
STUB_MOUNT_ACTUAL=$(diskutil info "$STUB_DEV" | awk -F: '/Mount Point/{gsub(/^[[:space:]]+/,"",$2); print $2}')
[ -d "$STUB_MOUNT_ACTUAL" ] || die "stub mount point not found"

# Credentials for kmutil
printf "    macOS admin username: "; read -r ADMIN_USER
printf "    macOS admin password: "; read -rs ADMIN_PASS; echo
[ -n "$ADMIN_USER" ] || die "username cannot be empty"
[ -n "$ADMIN_PASS" ] || die "password cannot be empty"

# Install m1n1 via kmutil
echo "==> Installing m1n1 via kmutil ..."
printf 'y\n%s\n%s\n' "$ADMIN_USER" "$ADMIN_PASS" | kmutil configure-boot \
    -c "$M1N1_BIN" \
    --raw \
    --entry-point 2048 \
    --lowest-virtual-address 0 \
    -v "$STUB_MOUNT_ACTUAL" \
    || die "kmutil configure-boot failed"

# Bless so it appears in the boot picker
echo "==> Blessing stub volume ..."
bless --mount "$STUB_MOUNT_ACTUAL" --setBoot \
    || echo "    WARNING: bless failed — stub may not appear in boot picker"

ADMIN_PASS=""

echo ""
echo "Done. Select macOS from boot picker (hold power) to restore normal boot."
echo "Then test m1n1: hold power → select Linux."
echo ""
echo "Subsequent m1n1 updates from macOS: sudo sh reinstall_m1n1.sh"
