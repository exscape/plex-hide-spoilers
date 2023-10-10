#!/bin/bash

if [[ ! -f "plex-hide-spoilers.py" ]]; then
    echo "Build script is meant to be executed from the project root directory, e.g.: bash buildscripts/pyinstaller_linux.sh"
    exit 1
fi

rm -rf dist/plex-hide-spoilers build

pyinstaller --contents-directory 'data' plex-hide-spoilers.py
cp config_sample.toml README.md dist/plex-hide-spoilers
cp -Rp licenses dist/plex-hide-spoilers

cd dist

echo "Creating .tar.bz2"
tar cjf plex-hide-spoilers.tar.bz2 plex-hide-spoilers
