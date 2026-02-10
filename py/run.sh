#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
source .venv/bin/activate
python acquire_scope_data.py config.json
