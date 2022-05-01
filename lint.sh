#!/bin/bash

set -e

BASE="$(dirname $0)"
cd "$BASE"

echo 'Black...'
black --diff --check .
echo 'flake8...'
flake8
echo 'pylint...'
pylint ./*.py
