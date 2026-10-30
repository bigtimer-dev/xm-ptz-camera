# Xiongmai (XMEye / "Sofia") DVRIP API notes

Tested on `IPC_NT98566_N8F-LQ`, firmware `V2.00.R02.000749TG.10010.140300.0020000` (build 2024-08-02),
a 4K PTZ camera with dual (IR + white) light, sold under many brands. The web page on port 80 is only a
shell for a Windows plugin; everything goes over **DVRIP on TCP 34567**.

## Ports

| Port | Use |
|------|-----|
| 80 | Web viewer shell, `/cgi-bin/login.cgi` (`{"Name":"GetPreLoginInfo"}` → TCP port + language, no auth), `/webcapture.jpg?command=snap&channel=1&user=..&password=..` |
| 554 | RTSP, digest auth. `rtsp://HOST:554/user=U&password=P&channel=1&stream=0.sdp` (0 = 3840×2160 H.265, 1 = 704×576 H.265, both with G.711A audio) |
| 8899 | ONVIF (WS-Security digest). PTZ, media profiles, PullPoint events (`RuleEngine/CellMotionDetector/Motion`) |
| 34567 | DVRIP (TCP), the real API |

## Framing

20-byte little-endian header, then the body:

```
B  0xFF            head
B  0x00            version
2x reserved
I  session id      0 before login, then the value from the login reply
I  sequence        incremented per request
2x total/current packet
H  message id
I  body length
```

The body is JSON followed by `\n\0`. The reply's message id is the request id + 1. Every request after
login carries `"SessionID": "0x0000000N"` in the JSON. Snapshot replies are raw JPEG bytes.
Success is `"Ret": 100` (515 is also treated as OK). Common errors: 203 wrong password, 205 unknown user,
206 locked, 103 not supported, 607 unknown config name.

## Login (1000)

```json
{"EncryptType": "MD5", "LoginType": "DVRIP-Web", "UserName": "admin", "PassWord": "<sofia hash>"}
→ {"AliveInterval": 30, "ChannelNum": 1, "DeviceType ": "IPC", "Ret": 100, "SessionID": "0x00000002"}
```

Sofia hash: `md5(password)` → 16 bytes; for i in 0..7, `chars[(b[2i] + b[2i+1]) % 62]` with
`chars = 0-9A-Za-z`. Send KeepAlive (1006, `{"Name":"KeepAlive"}`) within `AliveInterval` seconds.

## Messages

| Id | Name | Body / notes |
|----|------|--------------|
| 1020 | `SystemInfo`, `StorageInfo`, `WorkState` | info reads |
| 1042 | config get, `{"Name": "<section>"}` | value is under the section name |
| 1040 | config set, `{"Name": s, s: <whole section>}` | read-modify-write the full section |
| 1360 | ability get (`SystemFunction`, `Camera`, `EncodeCapability`, `MultiLanguage`) | |
| 1400 | `OPPTZControl` | see PTZ |
| 1450 | `OPTimeSetting` `"YYYY-MM-DD HH:MM:SS"` (local time); `OPMachine` `{"Action":"Reboot"}` | |
| 1452 | `OPTimeQuery` | `"2026-01-01 12:00:00"` |
| 1500 | guard, `{"Name": ""}` | subscribe this connection to alarms |
| 1504 | alarm (camera → client) | `{"AlarmInfo": {"Channel", "Event", "StartTime", "Status": "Start"/"Stop"}}` |
| 1560 | `OPSNAP` `{"Channel": 0}` | JPEG 704×576 |

## Useful config sections (1042/1040)

| Section | Fields |
|---------|--------|
| `Detect.MotionDetect` | `[0].Enable`, `Level` 1–6, `EventHandler` {`AlarmOutEnable` (light/output), `VoiceEnable`, `VoiceType` (see `Ability.VoiceTipType`), `RecordEnable`, `SnapEnable`, `MessageEnable` (cloud push), `PtzEnable`} |
| `Detect.HumanDetection` | `[0].Enable`, `Sensitivity`, `PedRule[]` regions/lines (0–8191 coordinates), `ShowTrack` |
| `Detect.FaceDetection`, `Detect.CarShapeDetection`, `Detect.BlindDetect` | `[0].Enable` + `EventHandler` |
| `Detect.DetectTrack` | auto tracking `Enable` 0/1, `ReturnTime` s, `Sensitivity` |
| `Camera.Param` | `[0].PictureFlip` / `PictureMirror` `"0x00000001"`, `DayNightColor`, `IRCUTMode`, exposure/gain |
| `Camera.ParamEx` | WDR/low-light/day-night schedule |
| `Camera.WhiteLight` | `WorkMode` (seen: `Intelligent`), `Brightness` 0–100, `MoveTrigLight.Duration`, `WorkPeriod` |
| `Simplify.Encode` | main/extra stream codec, resolution, FPS, bitrate |
| `Ability.VoiceTipType` | built-in voice prompts (520 "Alert area, please leave", 523, 524, 526, 529 siren, 550 custom) |
| `NetWork.NetCommon` | IP (hex, little-endian: `0x0A01A8C0` = 192.168.1.10), ports, MAC |
| `NetWork.NetNTP` | `Enable`, `Server.Name`, `UpdatePeriod` (NTP is off by default) |
| `NetWork.PMS` | cloud push (`push.umeye.cn`), `NetWork.Nat` cloud P2P (`secu100.net`) |
| `NetWork.OnlineUpgrade` | auto firmware upgrade from `upgrade.secu100.net:8083` (enabled by default) |
| `System.TimeZone` | `timeMin` (UTC offset in minutes) |

## PTZ (1400)

```json
{"Name": "OPPTZControl", "OPPTZControl": {"Command": "DirectionLeft", "Parameter": {
  "AUX": {"Number": 0, "Status": "On"}, "Channel": 0, "MenuOpts": "Enter",
  "POINT": {"bottom": 0, "left": 0, "right": 0, "top": 0}, "Pattern": "SetBegin",
  "Preset": 65535, "Step": 5, "Tour": 0}}}
```

`Preset: 65535` starts a continuous move and `Preset: -1` with the same command stops it.
Commands: `DirectionUp/Down/Left/Right/LeftUp/LeftDown/RightUp/RightDown`, `ZoomTile`, `ZoomWide`,
`FocusNear/Far`, `IrisLarge/Small`, `SetPreset`/`GotoPreset`/`ClearPreset` (`Preset: n`),
`StartTour`/`StopTour`. Live-tested: pan left/right. Preset and tour commands come from the
protocol's public documentation and were not exercised on this camera yet.
Preset names are not readable over DVRIP (`Uart.PTZPreset` → 607); ONVIF `GetPresets` lists them.

## Alarms (1500 → 1504)

After `{"Name": ""}` on message 1500, the connection receives pushes like this one, captured when a
person walked past:

```json
{"AlarmInfo": {"Channel": 0, "Event": "appEventHumanDetectAlarm",
               "StartTime": "2026-01-01 12:00:00", "Status": "Start"}, "Name": "AlarmInfo"}
```

`Start`/`Stop` pairs arrive about a second apart while the person keeps moving, and there is no
separate `VideoMotion` event while human detection is on. The integration keeps a sensor on until
10 s after the last `Stop` (or 30 s after a `Start` with no `Stop`). Alarms require `Detect.MotionDetect[0].Enable = true`.
