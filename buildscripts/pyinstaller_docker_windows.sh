#!/bin/bash

if [[ ! -f "plex-hide-spoilers.py" ]]; then
    echo "Build script is meant to be executed from the project root directory, e.g.: bash buildscripts/pyinstaller_docker_windows.sh"
    exit 1
fi

SUFFIX="-master-windows"

if [[ $# == 1 ]]; then
	SUFFIX="-$1-windows"
fi

FILENAME="plex-hide-spoilers${SUFFIX}.zip"

rm -rf dist/windows/plex-hide-spoilers build "${FILENAME}.zip"

# 3.8 is the latest Python version that easily runs under Wine at the moment
docker run --rm -v "$(pwd):/src/" pyinstaller-3.8-win64

cp config_sample.toml README.md dist/windows/plex-hide-spoilers
cp -Rp licenses dist/windows/plex-hide-spoilers

cd dist/windows

echo "Creating dist/windows/${FILENAME}"
zip -9 -r "$FILENAME" plex-hide-spoilers
