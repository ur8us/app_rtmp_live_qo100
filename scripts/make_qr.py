#!/usr/bin/env python3
"""Generate a PNG QR code for an RTMP URL."""

import argparse
from pathlib import Path

try:
    import qrcode
except ImportError as exc:
    raise SystemExit(
        "Missing dependency: install with `python3 -m pip install qrcode[pil]`"
    ) from exc


DEFAULT_URL = "rtmp://192.168.2.1:7272/"
DEFAULT_OUTPUT = "rtmp-url-qr.png"


def parse_args():
    parser = argparse.ArgumentParser(description="Generate a PNG QR code for an RTMP URL.")
    parser.add_argument(
        "url",
        nargs="?",
        default=DEFAULT_URL,
        help="RTMP URL to encode. Defaults to %(default)s",
    )
    parser.add_argument(
        "-o",
        "--output",
        default=DEFAULT_OUTPUT,
        help="Output PNG path. Defaults to %(default)s",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    url = args.url.strip()
    if not (url.startswith("rtmp://") or url.startswith("rtmps://")):
        raise SystemExit("URL must start with rtmp:// or rtmps://")

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=16,
        border=4,
    )
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    img.save(output)
    print("{} -> {}".format(url, output))


if __name__ == "__main__":
    main()
