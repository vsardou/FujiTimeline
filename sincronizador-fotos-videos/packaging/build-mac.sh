#!/bin/zsh
# Build on Apple Silicon with Python/Tk installed. Tool root is never embedded as a runtime path.
set -eu
project_dir="${0:A:h:h}"
cd "$project_dir"
: "${FUJI_TOOLS_DIR:?Set FUJI_TOOLS_DIR to the folder containing ffprobe and Image-ExifTool-13.61}"
python_bin="${FUJI_BUILD_PYTHON:-.venv/bin/python}"
staging_dir="$project_dir/build/mac-tools"
mkdir -p "$staging_dir/exiftool"
cp "$FUJI_TOOLS_DIR/Image-ExifTool-13.61/exiftool" "$staging_dir/exiftool/exiftool.pl"
cp -R "$FUJI_TOOLS_DIR/Image-ExifTool-13.61/lib" "$staging_dir/exiftool/"
printf '%s\n' '#!/bin/sh' 'exec /usr/bin/perl "$(dirname "$0")/exiftool.pl" "$@"' > "$staging_dir/exiftool/exiftool"
chmod +x "$staging_dir/exiftool/exiftool"
"$python_bin" -m PyInstaller --noconfirm --windowed --onedir --name FujiTimeline \
 --osx-bundle-identifier com.vsardou.fujitimeline --target-architecture arm64 \
 --collect-all opentimelineio --collect-all otio_fcpx_xml_adapter --collect-all tzdata \
 --copy-metadata fujitimeline --add-data "$staging_dir/exiftool:tools/exiftool" \
 --add-binary "$FUJI_TOOLS_DIR/ffprobe:tools" --paths "$project_dir/src" \
 --distpath "$project_dir/dist" --workpath "$project_dir/build/pyinstaller" \
 --specpath "$project_dir/build" "$project_dir/packaging/mac_entry.py"
