#!/bin/bash

# Builds for plain Windows, but this script requires WSL/similar

if [[ ! -f "plex-hide-spoilers.py" ]]; then
    echo "Build script is meant to be executed from the project root directory, e.g.: bash buildscripts/pyinstaller_wsl.sh"
    exit 1
fi

rm -rf dist build

pyinstaller.exe --contents-directory 'data' plex-hide-spoilers.py
cp config_sample.toml README.md dist/plex-hide-spoilers
cp -Rp licenses dist/plex-hide-spoilers

cd dist

echo "Creating .zip"
zip -9 -r plex-hide-spoilers plex-hide-spoilers
