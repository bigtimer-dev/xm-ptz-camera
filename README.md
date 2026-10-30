# XM PTZ Camera (DVRIP) for Home Assistant

Local control of Xiongmai-based ("XMEye" app, web page that asks for *VideoPlayTool*) PTZ cameras over
their native DVRIP protocol on TCP 34567. Unlike ONVIF this gives person-detection alarms, auto
tracking, white-light and detection settings. No cloud and no extra Python packages.

Tested on `IPC_NT98566_N8F-LQ` (4K dual-light PTZ), firmware V2.00.R02 (2024-08).

## Install

Copy `custom_components/xm_ptz` into your Home Assistant `config/custom_components/` (or add this repo
to HACS as a custom repository), restart, then **Settings → Devices & services → Add integration →
XM PTZ Camera**. Enter the camera IP, port 34567, and the admin login.

## Entities

| Type | Entities |
|------|----------|
| Camera | main stream (4K RTSP), sub stream (disabled by default); snapshots over DVRIP |
| Binary sensor | Motion, Person (pushed by the camera instantly), Camera blocked (disabled) |
| Switch | Motion detection, Person detection, Auto tracking, Motion alarm light/output, Motion voice warning, Record on motion, Flip, Mirror |
| Number | Motion sensitivity, Tracking return time, White light brightness, White light on-motion duration |
| Button | PTZ up/down/left/right, Zoom in/out (disabled), Tour start/stop, Sync clock, Reboot |
| Sensor | Clock offset |

The camera has no working clock source by default, so the integration keeps its clock in sync with
Home Assistant (option, on by default).

Every alarm also fires an `xm_ptz_alarm` event (`event`, `active`, `raw`) for automations.

## Actions

On the camera entity: `xm_ptz.ptz` (direction, speed, duration; 0 = until `stop`),
`xm_ptz.goto_preset` / `save_preset` / `delete_preset`, `xm_ptz.tour`, `xm_ptz.get_config` (returns any
config section) and `xm_ptz.set_config` (writes one; see [API.md](API.md)).

> Person/motion alarms only fire while **Motion detection** is on: person detection is a filter on
> top of it in this firmware.

## Command line

`xmcam.py` uses only the standard library:

```sh
export XM_HOST=192.168.1.x XM_PASSWORD=...
./xmcam.py info
./xmcam.py get Detect.MotionDetect
./xmcam.py ptz left 0.5
./xmcam.py snapshot now.jpg
./xmcam.py watch          # print alarms live
```

## Tips

These cameras phone home: cloud P2P (`secu100.net`), push (`push.umeye.cn`) and **automatic firmware
upgrades** (`upgrade.secu100.net`). Block the camera's internet access in your router if you only use
it locally.

## Tests

```sh
pip install pytest-homeassistant-custom-component
XM_HOST=192.168.1.x XM_PASSWORD=... pytest -s
```

Runs the integration against a real camera, reading settings and writing back unchanged values only.

## License

MIT
