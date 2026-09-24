"""Drive the M5 pocket window and grab colour screenshots from its framebuffer.

Gestures sent here are injected over USB and counted separately from real
button presses on the device, so a capture is never evidence of a hand test.

    python tools/m5_screen.py shot out.png
    python tools/m5_screen.py photo out-dir     # received -> replied timeline
    python tools/m5_screen.py gesture a_tap out.png --after 0.4
"""

import sys
import time
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image  # noqa: E402

from bridge.m5_link import M5Link  # noqa: E402


def shot(link: M5Link, path: Path) -> None:
    """Freeze the screen, read all 240 rows as RGB565, save a 3x PNG."""
    link.request({"type": "screen_freeze", "on": True}, "screen_freeze_ack", 1.0)
    image = Image.new("RGB", (135, 240))
    for row in range(240):
        for _ in range(4):
            reply = link.request({"type": "screen_row_rgb", "row": row}, "screen_rgb", 0.6, row=row)
            if reply:
                break
        else:
            raise RuntimeError(f"row {row} never came back")
        hexes = reply["px"]
        for x in range(135):
            c = int(hexes[x * 4:x * 4 + 4], 16)
            image.putpixel((x, row), (((c >> 11) & 31) * 255 // 31, ((c >> 5) & 63) * 255 // 63, (c & 31) * 255 // 31))
    link.send({"type": "screen_freeze", "on": False})
    path.parent.mkdir(parents=True, exist_ok=True)
    image.resize((405, 720), Image.NEAREST).save(path)
    print(f"saved {path}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port")
    sub = parser.add_subparsers(dest="command", required=True)
    s = sub.add_parser("shot"); s.add_argument("out", type=Path)
    s = sub.add_parser("photo"); s.add_argument("out", type=Path)
    s.add_argument("--expression", default="delighted"); s.add_argument("--line", default="这片云像棉花糖！")
    s = sub.add_parser("gesture"); s.add_argument("name"); s.add_argument("out", type=Path, nargs="?")
    s.add_argument("--after", type=float, default=0.5)
    s = sub.add_parser("menu"); s.add_argument("out", type=Path)
    s = sub.add_parser("status")
    args = parser.parse_args()

    link = M5Link(args.port)
    hello = link.request({"type": "hello_request"}, "hello", 2.0)
    print("hello:", hello)
    if args.command == "status":
        print(link.request({"type": "ui_query"}, "ui_status", 1.0)); return 0
    if args.command == "shot":
        shot(link, args.out); return 0
    if args.command == "gesture":
        print(link.request({"type": "ui_inject", "gesture": args.name}, "ui_inject_ack", 1.0))
        if args.out:
            time.sleep(args.after); shot(link, args.out)
        return 0
    if args.command == "menu":
        def inject(name): return link.request({"type": "ui_inject", "gesture": name}, "ui_inject_ack", 1.0)
        inject("b_hold"); time.sleep(0.4); shot(link, args.out / "1-menu-photo.png")
        for _ in range(5): inject("a_tap"); time.sleep(0.05)
        time.sleep(0.3); shot(link, args.out / "2-menu-snack.png")
        inject("b_tap"); time.sleep(1.0); shot(link, args.out / "3-snack-demo.png")
        time.sleep(2.2); inject("a_tap"); time.sleep(0.05); inject("b_tap"); time.sleep(1.2); shot(link, args.out / "4-dance-demo.png")
        inject("b_hold")
        return 0
    if args.command == "photo":
        event = f"qa-{int(time.time())}"
        seen = link.position(); link.photo_received(event); print(link.wait_for("photo_ack", 1.0, since=seen))
        time.sleep(0.05); shot(link, args.out / "1-flash.png")
        time.sleep(2.0); shot(link, args.out / "2-waiting.png")
        seen = link.position(); link.photo_replied(event, args.expression, 0.9, args.line); print(link.wait_for("photo_ack", 1.0, since=seen))
        time.sleep(0.9); shot(link, args.out / "3-laugh.png")
        time.sleep(1.2); shot(link, args.out / "4-laugh.png")
        time.sleep(4.5); shot(link, args.out / "5-line.png")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
