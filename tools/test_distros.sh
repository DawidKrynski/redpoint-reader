#!/bin/bash
# Runs the AppImage self-test (X11 under Xvfb: rendering, IPC, global shortcut via xdotool,
# PRIMARY selection via xclip) in clean containers of several distributions.
#   tools/test_distros.sh dist/Redpoint-*.AppImage [out-dir]
set -uo pipefail
APPIMAGE=$(readlink -f "$1")
OUT=$(readlink -f "${2:-build/distro-tests}")
mkdir -p "$OUT"
declare -A SETUP=(
  [ubuntu:22.04]="apt-get update -qq && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq xvfb xauth xdotool xclip libgl1 libegl1 fontconfig fonts-dejavu-core"
  [ubuntu:24.04]="apt-get update -qq && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq xvfb xauth xdotool xclip libgl1 libegl1 fontconfig fonts-dejavu-core"
  [debian:12]="apt-get update -qq && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq xvfb xauth xdotool xclip libgl1 libegl1 fontconfig fonts-dejavu-core"
  [fedora:42]="dnf -y -q install xorg-x11-server-Xvfb xorg-x11-xauth xdotool xclip mesa-libGL mesa-libEGL fontconfig dejavu-sans-fonts which"
  [archlinux:latest]="pacman -Sy --noconfirm --needed -q xorg-server-xvfb xorg-xauth xdotool xclip mesa fontconfig ttf-dejavu which >/dev/null"
  [opensuse/tumbleweed]="zypper -q -n install xvfb-run xauth xdotool xclip Mesa-libGL1 Mesa-libEGL1 fontconfig dejavu-fonts which"
  [linuxmintd/mint22-amd64]="apt-get update -qq && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq xvfb xauth xdotool xclip libgl1 libegl1 fontconfig fonts-dejavu-core"
)
TEST='set -e
export APPIMAGE_EXTRACT_AND_RUN=1 QT_QPA_PLATFORM=xcb
printf "Selected on %s" "$DISTRO" | xclip -selection primary
export REDPOINT_EXPECT_SELECTION="Selected on $DISTRO"
export REDPOINT_TEST_HOTKEY=ctrl+alt+r REDPOINT_TEST_PRESS="xdotool key ctrl+alt+r"
/app/Redpoint.AppImage --self-test /out/$SLUG'
pass=0; fail=0
for img in "${!SETUP[@]}"; do
  slug=${img//[:\/]/-}
  log="$OUT/$slug.log"
  docker run --rm --init -e DISTRO="$img" -e SLUG="$slug" -v "$APPIMAGE":/app/Redpoint.AppImage:ro -v "$OUT":/out "$img" \
    bash -c "${SETUP[$img]} >/dev/null 2>&1 && xvfb-run -a -s '-screen 0 1600x900x24' bash -c '$TEST'" >"$log" 2>&1
  if [ $? -eq 0 ]; then pass=$((pass+1)); echo "PASS $img"; else fail=$((fail+1)); echo "FAIL $img (see $log)"; fi
done
echo "passed $pass, failed $fail"
[ $fail -eq 0 ]
