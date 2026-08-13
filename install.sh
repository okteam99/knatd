#!/bin/sh
set -eu

REPOSITORY="okteam99/knatd"
BRANCH="${KNATD_BRANCH:-main}"
BASE_URL="${KNATD_BASE_URL:-https://raw.githubusercontent.com/${REPOSITORY}/${BRANCH}}"
CONFIG_DIR="/etc/knatd"
PROGRAM_PATH="/usr/local/sbin/knatd"
SERVICE_PATH="/etc/systemd/system/knatd.service"
DEFAULT_CONFIG_PATH="${CONFIG_DIR}/default.conf"

if [ "$(id -u)" -ne 0 ]; then
    echo "error: run this installer as root" >&2
    exit 1
fi

for program in python3 systemctl; do
    if ! command -v "${program}" >/dev/null 2>&1; then
        echo "error: required program not found: ${program}" >&2
        exit 1
    fi
done

if ! command -v iptables >/dev/null 2>&1 || \
   ! command -v iptables-save >/dev/null 2>&1 || \
   ! command -v iptables-restore >/dev/null 2>&1; then
    echo "error: iptables, iptables-save, and iptables-restore are required" >&2
    exit 1
fi

TEMP_DIR="$(mktemp -d)"
trap 'rm -rf "${TEMP_DIR}"' EXIT HUP INT TERM

download() {
    source_url="$1"
    destination="$2"
    if command -v curl >/dev/null 2>&1; then
        curl -fsSL "${source_url}" -o "${destination}"
    elif command -v wget >/dev/null 2>&1; then
        wget -qO "${destination}" "${source_url}"
    else
        echo "error: curl or wget is required" >&2
        exit 1
    fi
}

download "${BASE_URL}/knatd" "${TEMP_DIR}/knatd"
download "${BASE_URL}/knatd.service" "${TEMP_DIR}/knatd.service"
download "${BASE_URL}/examples/knatd.conf" "${TEMP_DIR}/knatd.conf"

python3 -m py_compile "${TEMP_DIR}/knatd"
install -d -m 0755 /usr/local/sbin "${CONFIG_DIR}" /etc/systemd/system
install -m 0755 "${TEMP_DIR}/knatd" "${PROGRAM_PATH}"
install -m 0644 "${TEMP_DIR}/knatd.service" "${SERVICE_PATH}"

if ! find "${CONFIG_DIR}" -maxdepth 1 -type f -name '*.conf' -print -quit | grep -q .; then
    install -m 0644 "${TEMP_DIR}/knatd.conf" "${DEFAULT_CONFIG_PATH}"
    echo "created default reference configuration: ${DEFAULT_CONFIG_PATH}"
else
    echo "kept existing configuration under ${CONFIG_DIR}"
fi

"${PROGRAM_PATH}" check
systemctl daemon-reload
systemctl enable --now knatd.service

echo "knatd installed and started"
echo "edit ${CONFIG_DIR}/*.conf, then run: systemctl reload knatd"
