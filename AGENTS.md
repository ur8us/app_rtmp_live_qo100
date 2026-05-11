# Agent Notes

## Project Scope

This repository contains a standalone MaixCAM/MaixCAM2 app named `RTMP Live QO-100`.

The app was made from the upstream Sipeed MaixPy `RTMP Live` application and converted into a separate app with:

- App id: `rtmp_live_qo100`
- App name: `RTMP Live QO-100`
- Manifest: `app.yaml`
- Main program: `main.py`

The project was prepared for Denis UR8US/S58UA with help from Codex 5.5.

## Main Implementation Details

The original MaixPy `maix.rtmp.Rtmp` helper takes `(host, port, app, stream, bitrate)` and is H.264-oriented. This app uses `maix.video.Encoder` directly so that H.264 and H.265 can both be selected, then pipes encoded frames into FFmpeg:

```text
ffmpeg -hide_banner -loglevel warning -use_wallclock_as_timestamps 1 -f h264|hevc -r 15 -i pipe:0 -c:v copy -an -flvflags no_duration_filesize -f flv <rtmp-url>
```

H.265 is emitted as HEVC-in-FLV/RTMP and requires receiver support. H.264 is the compatible default path for most QO-100 PlutoDVB and Portsdown workflows.

Current video settings:

- Resolution: `640x480`
- Frame rate: `15 fps`
- GOP: `15`
- Audio: none

Selectable codecs:

- `H.264`
- `H.265`

Selectable video bitrates:

- `33 kbps`
- `66 kbps`
- `125 kbps`
- `250 kbps`
- `333 kbps`
- `500 kbps`
- `1 Mbps`
- `1.5 Mbps`
- `2 Mbps`

The default bitrate is `333 kbps`.

## Persistent State

The app stores settings on the camera in:

```text
/root/.config/rtmp_live_qo100/settings.json
```

Saved fields include:

- Selected codec label and index
- Selected bitrate value, label, and index
- Last RTMP URL
- Up to 10 most recent RTMP URLs

The app saves state immediately after a codec or bitrate change and after each valid scanned or selected RTMP URL.

## UI Behavior

- The idle page shows codec and bitrate buttons near the top.
- The no-URL page keeps the QR scan workflow and places `History` under `Click icon to start scan`.
- The URL-present page shows `Scan`, `Run`, the current URL, and `History`.
- The history page lists up to 10 URLs and selecting one moves it to the top.
- Button text was enlarged relative to the upstream app for readability on the camera display.

## Headless Test Mode

The app can be run directly on the camera for automated streaming tests using environment variables:

```text
QO100_RTMP_URL=<rtmp-url>
QO100_CODEC=h264|h265
QO100_BITRATE=<bits-per-second>
QO100_TEST_SECONDS=<seconds>
```

When `QO100_RTMP_URL` is present, the app streams for the requested duration and exits.

## Packaging

Create the app package with:

```sh
./scripts/package.sh
```

The package is written to:

```text
dist/rtmp_live_qo100.zip
```

## Deployment

Deploy over SSH with:

```sh
./scripts/deploy.sh root@<camera-ip>
```

The script copies the zip to the camera and installs it with:

```sh
app_store_cli install /tmp/rtmp_live_qo100.zip
```

## Validation Performed

A live-camera RTMP matrix test was run with every codec and bitrate combination:

- 2 codecs: H.264 and H.265
- 9 bitrates
- 18 total cases
- 10-second capture per case

Each case produced 640x480 video and the expected codec when probed with FFmpeg/ffprobe.

On 2026-05-11 a second live-camera matrix test was run with 15-second captures for each case. Results are stored in `test-results/matrix_20260511_183749_15s`. All 18 cases passed:

- H.264 at `33`, `66`, `125`, `250`, `333`, `500 kbps`, `1`, `1.5`, and `2 Mbps`
- H.265/HEVC at `33`, `66`, `125`, `250`, `333`, `500 kbps`, `1`, `1.5`, and `2 Mbps`
- Every recording probed as 640x480 with the expected codec

## Documentation Notes

The public README intentionally avoids workstation-specific paths and camera credentials. Use placeholders such as `<camera-ip>`, `<pluto-ip>`, and `<callsign>` in public-facing examples.
