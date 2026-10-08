#!/usr/bin/env bash
# Install (or update) Metadata Cleaner as a systemd service.
# Tested on Debian 13 (trixie). Needs qpdf >= 11.10 for --remove-info/--remove-metadata.
#
# Usage: sudo ./deploy/install.sh
set -euo pipefail

APP_NAME=exiftool-webtool
APP_DIR=/opt/$APP_NAME
CACHE_DIR=/var/cache/$APP_NAME
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ $EUID -ne 0 ]]; then
  echo "Run as root: sudo $0" >&2
  exit 1
fi

echo "==> Installing packages"
apt-get update
apt-get install -y \
  libimage-exiftool-perl libarchive-zip-perl \
  qpdf mat2 file \
  python3-flask gunicorn

qpdf_version="$(qpdf --version | head -n1 | awk '{print $3}')"
if ! printf '11.10\n%s\n' "$qpdf_version" | sort -V -C; then
  echo "qpdf $qpdf_version is too old: --remove-info/--remove-metadata need qpdf >= 11.10" >&2
  exit 1
fi

echo "==> Creating system user $APP_NAME"
if ! id -u "$APP_NAME" >/dev/null 2>&1; then
  useradd --system --home-dir "$CACHE_DIR" --no-create-home --shell /usr/sbin/nologin "$APP_NAME"
fi

echo "==> Copying application to $APP_DIR"
install -d -m 755 "$APP_DIR"
rm -rf "$APP_DIR/cleaner" "$APP_DIR/templates" "$APP_DIR/static"
cp -r "$SRC_DIR/app.py" "$SRC_DIR/storage.py" "$SRC_DIR/cleaner" "$SRC_DIR/templates" "$SRC_DIR/static" "$APP_DIR/"
find "$APP_DIR" -name __pycache__ -prune -exec rm -rf {} +
chown -R root:root "$APP_DIR"
chmod -R u=rwX,go=rX "$APP_DIR"

echo "==> Installing systemd unit"
if [[ ! -f /etc/default/$APP_NAME ]]; then
  install -m 644 "$SRC_DIR/deploy/$APP_NAME.env" "/etc/default/$APP_NAME"
fi
install -m 644 "$SRC_DIR/deploy/$APP_NAME.service" "/etc/systemd/system/$APP_NAME.service"
systemctl daemon-reload
systemctl enable "$APP_NAME"
systemctl restart "$APP_NAME"

sleep 2
if systemctl is-active --quiet "$APP_NAME"; then
  bind="$(. "/etc/default/$APP_NAME"; echo "${CLEANER_BIND:-0.0.0.0:8777}")"
  echo "==> $APP_NAME is running on http://$bind"
  echo "    Settings: /etc/default/$APP_NAME   Logs: journalctl -u $APP_NAME -f"
else
  echo "==> $APP_NAME failed to start; check: journalctl -u $APP_NAME -e" >&2
  exit 1
fi
