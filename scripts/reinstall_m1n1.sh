#!/bin/bash
# reinstall_m1n1.sh — Install m1n1 into the Linux stub volume and set it as boot target.
#
# Run this from 1TR (One True RecoveryOS):
#   1. Boot holding power, select Options
#   2. Open Terminal from the Utilities menu
#   3. Run this script:
#        sh /Volumes/Data/Users/rusch/Projects/asahi_neo/scripts/reinstall_m1n1.sh
#      (If the Data volume isn't mounted yet, the script will unlock and mount it.)

set -euo pipefail

# Auto-detect by volume name — override by setting DATA_DEV or STUB_DEV in the environment.
#   e.g.: DATA_DEV=disk3s5 STUB_DEV=disk2s1 sh reinstall_m1n1.sh
_dl=$(diskutil list)
: "${DATA_DEV:=$(echo "$_dl" | awk '/APFS Volume[[:space:]]+Data[[:space:]]/ { print $NF; exit }')}"
: "${STUB_DEV:=$(echo "$_dl" | awk '/APFS Volume[[:space:]]+Linux[[:space:]]/ { print $NF; exit }')}"
[ -n "$DATA_DEV" ] || die "could not find APFS volume named 'Data' — run 'diskutil list' or set DATA_DEV"
[ -n "$STUB_DEV" ] || die "could not find APFS volume named 'Linux' — run 'diskutil list' or set STUB_DEV"
echo "==> Detected: DATA=$DATA_DEV  STUB=$STUB_DEV"
DATA_MOUNT="/Volumes/Data"
M1N1_BIN="$DATA_MOUNT/Users/rusch/Projects/m1n1/build/m1n1.bin"
STUB_MOUNT="/Volumes/Linux"
M1N1_MIN_BYTES=524288  # 512 KB — a valid m1n1.bin is ~1 MB; reject obviously wrong files

die() { echo "ERROR: $*" >&2; exit 1; }

echo "==> m1n1 reinstall script"

# --- Preflight checks -------------------------------------------------------

# Must run as root (automatic in 1TR Terminal, but guard against accidents)
[ "$(id -u)" -eq 0 ] || die "must run as root (are you in 1TR Terminal?)"

# Required tools
for tool in diskutil kmutil bputil bless; do
    command -v "$tool" >/dev/null 2>&1 || die "$tool not found — is this 1TR?"
done

# Disk devices must exist
diskutil info "$DATA_DEV" >/dev/null 2>&1 \
    || die "$DATA_DEV not found — check DATA_DEV at top of script (run 'diskutil list')"
diskutil info "$STUB_DEV" >/dev/null 2>&1 \
    || die "$STUB_DEV not found — check STUB_DEV at top of script (run 'diskutil list')"
diskutil info "$STUB_DEV" | grep -q "APFS" \
    || die "$STUB_DEV does not appear to be an APFS volume"

# --- Credentials ------------------------------------------------------------

# bputil needs local admin credentials to authorize the boot policy change.
printf "    macOS admin username: "; read -r ADMIN_USER
printf "    macOS admin password: "; read -rs ADMIN_PASS; echo

[ -n "$ADMIN_USER" ] || die "username cannot be empty"
[ -n "$ADMIN_PASS" ] || die "password cannot be empty"

# --- Mount volumes ----------------------------------------------------------

# Unlock Data volume if not already mounted (FileVault encrypted)
if ! diskutil info "$DATA_DEV" | grep -q "Mounted:.*Yes"; then
    echo "==> Unlocking Data volume ($DATA_DEV) — enter login password when prompted ..."
    diskutil apfs unlockVolume "$DATA_DEV"
else
    echo "==> Data volume already mounted at $DATA_MOUNT"
fi

# Verify m1n1.bin exists and is large enough to be a real binary
[ -f "$M1N1_BIN" ] || die "m1n1.bin not found at $M1N1_BIN"
M1N1_SIZE=$(stat -f%z "$M1N1_BIN")
[ "$M1N1_SIZE" -ge "$M1N1_MIN_BYTES" ] \
    || die "m1n1.bin is only ${M1N1_SIZE} bytes — looks truncated or wrong file"
echo "    m1n1.bin: $(ls -lh "$M1N1_BIN" | awk '{print $5, $6, $7, $8}')"

# Mount stub volume if not already mounted
if ! diskutil info "$STUB_DEV" | grep -q "Mounted:.*Yes"; then
    echo "==> Mounting stub volume ($STUB_DEV) ..."
    diskutil mount "$STUB_DEV"
else
    echo "==> Stub volume already mounted at $STUB_MOUNT"
fi

[ -d "$STUB_MOUNT" ] || die "stub mount point $STUB_MOUNT does not exist after mount"

# --- Check / set boot policy ------------------------------------------------

# Get the Linux stub's volume group UUID — bputil targets this container,
# not the macOS one.
STUB_UUID=$(diskutil info "$STUB_DEV" | awk '/APFS Volume Group/{print $NF}') || true

# Check current security policy — skip bputil if already Permissive.
ALREADY_PERMISSIVE=false
if [ -n "$STUB_UUID" ]; then
    if bputil -display -v "$STUB_UUID" 2>/dev/null | grep -qi "permissive"; then
        ALREADY_PERMISSIVE=true
    fi
fi

if [ "$ALREADY_PERMISSIVE" = true ]; then
    echo "==> Security policy already Permissive — skipping bputil"
else
    echo "==> Setting Permissive Security for stub volume ..."
    # Use -kuo (not -akuo): -a requires Apple ID/internet and is not needed here.
    if [ -n "$STUB_UUID" ]; then
        echo "    Targeting Linux stub volume group $STUB_UUID"
        bputil -kuo -v "$STUB_UUID" -u "$ADMIN_USER" -p "$ADMIN_PASS" \
            || die "bputil failed — cannot set Permissive Security"
    else
        echo "    Could not determine stub UUID — bputil will ask you to pick"
        bputil -kuo -u "$ADMIN_USER" -p "$ADMIN_PASS" \
            || die "bputil failed — cannot set Permissive Security"
    fi
fi

# --- Install m1n1 -----------------------------------------------------------

install_m1n1() {
    printf 'y\n%s\n%s\n' "$ADMIN_USER" "$ADMIN_PASS" | kmutil configure-boot \
        -c "$M1N1_BIN" \
        --raw \
        --entry-point 2048 \
        --lowest-virtual-address 0 \
        -v "$STUB_MOUNT"
}

echo "==> Installing m1n1 into stub volume ..."
install_m1n1 || die "kmutil configure-boot failed"

# Scrub credentials from shell variables now that they're no longer needed
ADMIN_PASS=""

# --- Set boot target --------------------------------------------------------

echo "==> Setting stub as boot volume ..."
printf '%s\n%s\n' "$ADMIN_USER" "$ADMIN_PASS" | bless --mount "$STUB_MOUNT" --setBoot \
    || die "bless failed — stub may not boot; try running 'bless --mount $STUB_MOUNT --setBoot' manually"

echo ""
echo "Done. Rebooting in 5 seconds — press Ctrl-C to cancel."
for i in 5 4 3 2 1; do
    printf "\r  %d... " $i
    sleep 1
done
echo ""
reboot
