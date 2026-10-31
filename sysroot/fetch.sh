#!/bin/bash
# The cross sysroot for native carts (docs/native.md): download the packages in
# sysroot.lock from the Debian and Arduino archives, verify each hash, extract them, make
# absolute symlinks relative. No device needed.
#   sysroot/fetch.sh        -> sysroot/out/{aarch64,cache}   (SYSROOT_OUT=DIR to change)
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
OUT=${SYSROOT_OUT:-$HERE/out}
CACHE=$OUT/cache SYSROOT=$OUT/aarch64
mkdir -p "$CACHE"
for t in curl bsdtar; do command -v $t > /dev/null || { echo "need $t" >&2; exit 1; }; done

# The lock records the hash the archive publishes: SHA256 for Debian, SHA512 for Arduino's.
check() {  # file, "ALGO:hex"
    local tool
    case ${2%%:*} in SHA256) tool=sha256sum ;; SHA512) tool=sha512sum ;; *) return 1 ;; esac
    [ -f "$1" ] && [ "$($tool "$1" | cut -d' ' -f1)" = "${2#*:}" ]
}

echo "downloading $(wc -l < "$HERE/sysroot.lock") packages into $CACHE"
awk '{print $1, $2, $4}' "$HERE/sysroot.lock" | while read -r uri file sum; do
    check "$CACHE/$file" "$sum" || echo "$uri $CACHE/$file"
done | xargs -r -P 8 -n 2 sh -c 'curl -sSfL --retry 3 -o "$1.part" "$0" && mv "$1.part" "$1"'

bad=0
while read -r uri file size sum; do
    check "$CACHE/$file" "$sum" || { echo "checksum mismatch: $file" >&2; bad=1; }
done < "$HERE/sysroot.lock"
[ $bad = 0 ] || exit 1

echo "extracting into $SYSROOT"
rm -rf "$SYSROOT.new" && mkdir -p "$SYSROOT.new"
while read -r uri file size sum; do
    data=$(bsdtar -tf "$CACHE/$file" | grep '^data\.tar')
    bsdtar -xOf "$CACHE/$file" "$data" | bsdtar -xf - -C "$SYSROOT.new"
done < "$HERE/sysroot.lock"

# Debian's symlinks point at absolute paths (libfoo.so -> /lib/aarch64-linux-gnu/libfoo.so.1);
# inside a sysroot they must stay inside it.
find "$SYSROOT.new" -type l -lname '/*' | while read -r link; do
    target=$(readlink "$link")
    ln -sfn "$(realpath -m --relative-to="$(dirname "$link")" "$SYSROOT.new$target")" "$link"
done
# merged /usr, as on the device
for d in lib bin sbin; do [ -e "$SYSROOT.new/$d" ] || ln -s "usr/$d" "$SYSROOT.new/$d"; done
rm -rf "$SYSROOT" && mv "$SYSROOT.new" "$SYSROOT"
echo "sysroot ready: $(du -sh "$SYSROOT" | cut -f1) in $SYSROOT"
