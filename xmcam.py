#!/usr/bin/env python3
"""Command-line client for Xiongmai (XMEye) cameras over DVRIP. Standard library only.

    export XM_HOST=192.168.1.x XM_PASSWORD=...   # XM_USER defaults to admin
    ./xmcam.py info
    ./xmcam.py get Detect.MotionDetect
    ./xmcam.py set Detect.DetectTrack '{"Enable": 1, "ReturnTime": 300, "Sensitivity": 1}'
    ./xmcam.py snapshot out.jpg
    ./xmcam.py ptz left 0.5        ./xmcam.py preset goto 1        ./xmcam.py watch
"""
import argparse
import asyncio
import importlib.util
import json
import os
import sys
from datetime import datetime
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "xm_api", Path(__file__).resolve().parent / "custom_components" / "xm_ptz" / "api.py")
api = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(api)


def dump(value) -> None:
    print(json.dumps(value, indent=1, ensure_ascii=False))


async def main(args: argparse.Namespace) -> None:
    cam = api.XMCamera(args.host, args.user, args.password, args.port)
    try:
        match args.cmd:
            case "info":
                dump(await cam.system_info())
            case "get":
                dump(await cam.get_config(args.name))
            case "set":
                await cam.set_config(args.name, json.loads(args.value))
                dump(await cam.get_config(args.name))
            case "ability":
                dump(await cam.ability(args.name))
            case "raw":
                dump(await cam.request(args.msg_id, args.name, json.loads(args.body) if args.body else None))
            case "snapshot":
                Path(args.file).write_bytes(await cam.snapshot())
                print(f"saved {args.file}")
            case "time":
                print(await cam.get_time())
            case "settime":
                await cam.set_time(datetime.now())
                print(await cam.get_time())
            case "ptz":
                if args.direction == "stop":
                    await cam.ptz_stop()
                else:
                    await cam.ptz_step(args.direction, args.speed, args.seconds)
            case "preset":
                await cam.preset({"goto": "GotoPreset", "set": "SetPreset", "clear": "ClearPreset"}[args.action],
                                 args.number)
            case "tour":
                await cam.tour(args.action == "start")
            case "rtsp":
                print(cam.rtsp_url(args.stream))
            case "reboot":
                await cam.reboot()
            case "watch":
                cam.on_alarm = lambda info: print(datetime.now().strftime("%X"), json.dumps(info), flush=True)
                await cam.connect()
                print("Subscribed to alarms, Ctrl+C to stop", file=sys.stderr)
                await cam.run()
    finally:
        await cam.close()


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--host", default=os.environ.get("XM_HOST"), required="XM_HOST" not in os.environ)
    p.add_argument("--port", type=int, default=api.DEFAULT_PORT)
    p.add_argument("--user", default=os.environ.get("XM_USER", "admin"))
    p.add_argument("--password", default=os.environ.get("XM_PASSWORD", ""))
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("info", help="SystemInfo")
    sub.add_parser("get", help="read a config section").add_argument("name")
    s = sub.add_parser("set", help="write a whole config section (JSON)")
    s.add_argument("name")
    s.add_argument("value")
    sub.add_parser("ability", help="read an ability/capability section").add_argument("name")
    s = sub.add_parser("raw", help="send any message id")
    s.add_argument("msg_id", type=int)
    s.add_argument("name")
    s.add_argument("body", nargs="?")
    sub.add_parser("snapshot", help="save a JPEG").add_argument("file")
    sub.add_parser("time", help="camera clock")
    sub.add_parser("settime", help="set camera clock to this computer's local time")
    s = sub.add_parser("ptz", help="move for a moment")
    s.add_argument("direction", choices=[*api.PTZ_COMMANDS, "stop"])
    s.add_argument("seconds", type=float, nargs="?", default=0.5)
    s.add_argument("--speed", type=int, default=5)
    s = sub.add_parser("preset")
    s.add_argument("action", choices=["goto", "set", "clear"])
    s.add_argument("number", type=int)
    sub.add_parser("tour").add_argument("action", choices=["start", "stop"])
    sub.add_parser("rtsp", help="print the RTSP URL").add_argument("stream", type=int, nargs="?", default=0)
    sub.add_parser("reboot")
    sub.add_parser("watch", help="print alarms as they arrive")
    return p


if __name__ == "__main__":
    try:
        asyncio.run(main(parser().parse_args()))
    except KeyboardInterrupt:
        pass
    except api.XMError as err:
        sys.exit(f"error: {err}")
