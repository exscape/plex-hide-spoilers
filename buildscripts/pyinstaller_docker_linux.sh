#!/bin/bash

if [[ ! -f "plex-hide-spoilers.py" ]]; then
    echo "Build script is meant to be executed from the project root directory, e.g.: bash buildscripts/pyinstaller_linux.sh"
    exit 1
fi

rm -rf dist/linux/plex-hide-spoilers build

# Uses Docker to improve compatibility with older Linux systems
# If we run Pyinstaller on Debian 12, the resulting files won't run on still-supported systems a year or two old.
docker run -v "$(pwd):/src/" pyinstaller-3.12-linux-amd64

cp config_sample.toml README.md dist/linux/plex-hide-spoilers
cp -Rp licenses dist/linux/plex-hide-spoilers

cd dist/linux

echo "Creating .tar.bz2"
tar cjf plex-hide-spoilers.tar.bz2 plex-hide-spoilers
