"""Constants for the XM PTZ camera integration."""

DOMAIN = "xm_ptz"

CONF_SYNC_TIME = "sync_time"

SCAN_INTERVAL_SECONDS = 30
# Set the camera clock from Home Assistant when it drifts more than this.
CLOCK_TOLERANCE_SECONDS = 30

EVENT_ALARM = f"{DOMAIN}_alarm"
SIGNAL_ALARM = f"{DOMAIN}_alarm_{{}}"

# Seconds after which an alarm sensor turns off if the camera never sends the "Stop" event.
ALARM_AUTO_OFF = 30
# The camera sends Start/Stop pairs about a second apart while someone moves; hold "on" this long after Stop.
ALARM_HOLD = 10

# Config sections polled by the coordinator (DVRIP ConfigGet names).
SECTIONS = [
    "Detect.MotionDetect",
    "Detect.HumanDetection",
    "Detect.DetectTrack",
    "Camera.Param",
    "Camera.WhiteLight",
]

PTZ_DIRECTIONS = [
    "up", "down", "left", "right", "left_up", "left_down", "right_up", "right_down",
    "zoom_in", "zoom_out", "focus_near", "focus_far", "iris_open", "iris_close",
]
