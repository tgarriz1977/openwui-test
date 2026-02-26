#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

eksctl create nodegroup -f "${SCRIPT_DIR}/gpu-nodegroup-config.yaml"

echo "Node group gpu-spot creado."
