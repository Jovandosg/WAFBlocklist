#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_DIR="${ROOT_DIR}/.build/lambda"
ZIP_PATH="${ROOT_DIR}/.build/wafblocklist-lambda.zip"

rm -rf "${BUILD_DIR}" "${ZIP_PATH}"
mkdir -p "${BUILD_DIR}"

python3 -m pip install \
  --disable-pip-version-check \
  --no-cache-dir \
  --target "${BUILD_DIR}" \
  -r "${ROOT_DIR}/backend/requirements.txt"

cp -R "${ROOT_DIR}/backend" "${BUILD_DIR}/backend"
rm -rf "${BUILD_DIR}/backend/__pycache__" "${BUILD_DIR}/backend/app/__pycache__"

(
  cd "${BUILD_DIR}"
  zip -q -r "${ZIP_PATH}" . \
    -x '*/__pycache__/*' '*.pyc' '*.pyo' '*.dist-info/RECORD'
)

echo "Lambda package created: ${ZIP_PATH}"
