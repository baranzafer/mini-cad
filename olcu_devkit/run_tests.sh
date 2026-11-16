#!/usr/bin/env bash
# Ölçü Ustası testleri: gerçek Blender Python modülü (pip 'bpy') ile, pencere olmadan.
# Kullanım:  bash olcu_devkit/run_tests.sh [--shots <klasör>]
#   OLCU_HEAVY=1  -> 2M+ yüzlü performans testi
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
VENV="${OLCU_VENV:-/tmp/olcu_bpy}"
if [ ! -x "$VENV/bin/python" ]; then
  python3.13 -m venv "$VENV"
  "$VENV/bin/pip" install -q "bpy==5.2.3"
fi
"$VENV/bin/python" "$HERE/test_olcu.py" 2>&1 | grep -v "^Read prefs\|^$\|blender.org\|^Info:"
if [ "${1:-}" = "--shots" ]; then
  # yazılımsal GPU gerekir: apt-get install -y libegl1 libegl-mesa0 libgl1-mesa-dri libgbm1
  "$VENV/bin/python" "$HERE/render_overlay.py" "${2:-/tmp/olcu_shots}" 2>&1 | grep "yazıldı"
fi
