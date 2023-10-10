if (-not(Test-Path -Path "plex-hide-spoilers.py")) {
    Write-Host "Script should be executed from the project root folder!"
    exit 0
}

rm -Recurse -Force build -ErrorAction SilentlyContinue
rm -Recurse -Force dist\plex-hide-spoilers -ErrorAction SilentlyContinue

pyinstaller.exe --contents-directory data -p .\env\Lib\site-packages\ .\plex-hide-spoilers.py

if ($LASTEXITCODE -ne 0) {
    Write-Host "PyInstaller failed, exiting build script"
    exit $LASTEXITCODE
}

cp -Recurse config_sample.toml,README.md,licenses -Destination .\dist\plex-hide-spoilers
Write-Host "Creating zip file"
Compress-Archive -DestinationPath dist\plex-hide-spoilers.zip -Path dist\plex-hide-spoilers -CompressionLevel Optimal -Force