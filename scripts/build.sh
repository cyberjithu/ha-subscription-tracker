#!/usr/bin/env sh
# Build the add-on image for one platform (or all) with the matching Home Assistant base from build.yaml.
#   scripts/build.sh aarch64          # Raspberry Pi 4/5 and other 64-bit ARM (loads into local Docker)
#   scripts/build.sh amd64            # Intel/AMD PCs, NUCs, VMs
#   scripts/build.sh all --push       # both, pushed to ghcr.io (needs `docker login ghcr.io`)
set -eu
cd "$(dirname "$0")/.."

ARCH="${1:-}"
PUSH="${2:-}"
DEFAULT_IMAGE="ghcr.io/cyberjithu/{arch}-subtracker"  # same pattern as `image:` in config.yaml
IMAGE="${IMAGE:-$DEFAULT_IMAGE}"
VERSION=$(sed -n 's/^version: *"\{0,1\}\([^"]*\)"\{0,1\}$/\1/p' subtracker/config.yaml)

case "$ARCH" in
  aarch64|amd64) ARCHES="$ARCH" ;;
  all) ARCHES="aarch64 amd64" ;;
  *) echo "usage: $0 <aarch64|amd64|all> [--push]" >&2; exit 2 ;;
esac

for a in $ARCHES; do
  base=$(sed -n "s/^ *$a: *//p" subtracker/build.yaml)
  platform=$( [ "$a" = aarch64 ] && echo linux/arm64 || echo linux/amd64 )
  name=$(echo "$IMAGE" | sed "s/{arch}/$a/")
  echo ">> $a ($platform) from $base -> $name:$VERSION"
  docker buildx build --platform "$platform" --build-arg "BUILD_FROM=$base" \
    --label "io.hass.arch=$a" --label "io.hass.version=$VERSION" --label "io.hass.type=addon" \
    --label "org.opencontainers.image.source=https://github.com/cyberjithu/ha-subscription-tracker" \
    -t "$name:$VERSION" -t "$name:latest" \
    $( [ "$PUSH" = "--push" ] && echo --push || echo --load ) subtracker
done
