"""Constants for the Haier hOn Extended integration."""

DOMAIN = "addhon"

# Supported platforms
PLATFORMS = ["climate", "sensor", "binary_sensor", "switch", "select", "button", "number"]

# Update interval in seconds
# NOTE: the initial setup + first fetch takes ~22s on a slow cloud.
# 60s gives enough margin without stressing the Haier API.
SCAN_INTERVAL = 60

# hOn appliance types
APPLIANCE_AC = "AC"       # Air conditioner
APPLIANCE_WM = "WM"       # Washing Machine
APPLIANCE_TD = "TD"       # Tumble Dryer
APPLIANCE_WD = "WD"       # Washer-dryer

# ─── Tier 2: read-only types ──────────────────────────────────────────────────
# Additional types exposed as read-only sensors. The parameters come from the
# official app mapping but are NOT validated on real devices (none of the test
# devices are of these types): for this reason the sensors of these types are
# CAPABILITY-GATED (see sensor.py / binary_sensor.py), so they only show up if the
# device actually reports the attribute. Some codes are aliases of the same set
# (FR/FRE as REF, HOB as IH) because, depending on the model/enroll, the cloud may
# return one or the other.
APPLIANCE_REF = "REF"     # Refrigerator / fridge-freezer
APPLIANCE_FR  = "FR"      # Fridge (icon-map alias)
APPLIANCE_FRE = "FRE"     # Freezer
APPLIANCE_OV  = "OV"      # Oven
APPLIANCE_DW  = "DW"      # Dishwasher
APPLIANCE_WC  = "WC"      # Wine cooler
APPLIANCE_IH  = "IH"      # Induction hob
APPLIANCE_HOB = "HOB"     # Hob (alias)
APPLIANCE_HO  = "HO"      # Hood
APPLIANCE_KT  = "KT"      # Coffee machine / kettle
APPLIANCE_WH  = "WH"      # Water heater
APPLIANCE_RVC = "RVC"     # Robot vacuum cleaner

# Groups all washing machine/tumble dryer/washer-dryer appliances
APPLIANCE_WASH_GROUP = (APPLIANCE_WM, APPLIANCE_TD, APPLIANCE_WD)

# Names of the parameters that, in hOn commands, carry the program code/name.
# Shared between the select (options source + choice) and the "Start program"
# button (applies the chosen program to startProgram).
PROGRAM_PARAM_NAMES = ("program", "prCode")

# Key of the volatile store (kept on the coordinator) that holds the program
# chosen by the select but not yet started; the "Start program" button applies it
# to startProgram. The single shared source of truth between select.py and button.py.
PROGRAM_PENDING_STORE = "pending_programs"

# Service to change at runtime the log level of pyhOn's realtime MQTT channel. By
# default the reconnection-attempt noise is silenced (see logging_utils); this
# service re-enables it on demand for debugging. The logger names and the level
# map live in logging_utils.py (testable in isolation).
SERVICE_SET_MQTT_LOG_LEVEL = "set_mqtt_log_level"

# Service to raise/lower at runtime the debug of the integration and of the pyhOn
# loggers useful for discovery/polling. MQTT stays handled by the dedicated
# service above so as not to turn the realtime noise back on when investigating an
# empty device list.
SERVICE_SET_LOG_LEVEL = "set_log_level"
ATTR_LEVEL = "level"

# Option keys (entry.options) of the two debug toggles exposed in the
# Configure/Options screen of the integration. They persist across restarts and
# are applied on the fly (see _apply_debug_options in __init__). enable_debug ->
# integration logger to DEBUG (NOTSET when off); enable_mqtt_debug -> realtime MQTT
# logger to DEBUG (silenced to WARNING when off). The two toggles are independent.
CONF_ENABLE_DEBUG = "enable_debug"
CONF_ENABLE_MQTT_DEBUG = "enable_mqtt_debug"

# ─── Air conditioner attributes ───────────────────────────────────────────────
# Confirmed from the diagnostics of the AS35PBPHRA-PRE device
AC_ATTR_MODE         = "settings.machMode"
AC_ATTR_TEMP         = "settings.tempSel"
# tempIndoor / tempOutdoor are DIRECT attributes (not in settings), confirmed from diagnostics
AC_ATTR_CURRENT_TEMP     = "tempIndoor"
AC_ATTR_OUTDOOR_TEMP     = "tempOutdoor"
AC_ATTR_HUMIDITY_INDOOR  = "humidityIndoor"          # Ambient humidity (sensor reading)
AC_ATTR_HUMIDITY_SEL     = "settings.humiditySel"   # Target humidity (user setpoint)
AC_ATTR_FAN_SPEED    = "settings.windSpeed"
# Vertical swing. windDirectionVertical is an ENUM of POSITIONS, not a bool:
# 2,4,5,6,7 = fixed louver positions, 8 = SWING (oscillation). The device reports
# 0 when off: 0 is NOT among the enumValues, so sending it raises a ValueError in
# pyhOn's enum setter and the API rejects it, which is the reason swing had been
# disabled. The fix (climate.py): NEVER send 0 (pre-send sanitization) and set
# windDirectionVertical only to allowed values. The real allowed values are read
# at runtime from the parameter's .values (per-device), with
# windDirectionVerticalPositionSequence as the source on the device.
AC_ATTR_SWING_V      = "settings.windDirectionVertical"
AC_ATTR_SWING_H      = "settings.windDirectionHorizontal"
AC_SWING_V_PARAM     = "windDirectionVertical"   # param name in the "settings" command
AC_SWING_H_PARAM     = "windDirectionHorizontal"
AC_SWING_V_ON        = "8"                        # 8 = vertical oscillation
AC_SWING_MODE_ON     = "on"
AC_SWING_MODE_OFF    = "off"
AC_ATTR_ON_OFF       = "settings.onOffStatus"
# ecoMode exists only in startProgram (NOT in settings), confirmed from diagnostics
AC_ATTR_ECO          = "startProgram.ecoMode"
AC_ATTR_RAPID        = "settings.rapidMode"
# silentSleepStatus is the real name; muteStatus is separate (display mute)
AC_ATTR_SLEEP        = "settings.silentSleepStatus"
AC_ATTR_SILENT       = "settings.muteStatus"
AC_ATTR_FILTER       = "settings.filterChangeStatusCloud"
AC_ATTR_SELF_CLEAN   = "settings.selfCleaningStatus"
AC_ATTR_LIGHT        = "settings.lightStatus"
AC_ATTR_COMPRESSOR_FREQ = "compressorFrequency"
AC_ATTR_TOTAL_ENERGY = "totalElectricityUsed"
# Air quality (direct attributes, confirmed on Roberto's AC)
AC_ATTR_PM25        = "pm2p5ValueIndoor"   # Indoor PM2.5 (µg/m³)
AC_ATTR_CO2         = "co2ValueIndoor"     # Indoor CO2 (ppm)
AC_ATTR_CH2O        = "ch2oValueIndoor"    # Indoor formaldehyde (mg/m³)

# AC mode mapping -> HA
# Values accepted by the device: [0, 1, 2, 4, 6]
AC_MODE_MAP = {
    "0": "auto",
    "1": "cool",
    "2": "dry",
    "4": "heat",      # FIXED: "4"=HEAT confirmed from AS35PBPHRA-PRE
    "6": "fan_only",  # FIXED: "6"=FAN confirmed from AS35PBPHRA-PRE
}
AC_MODE_MAP_REVERSE = {v: k for k, v in AC_MODE_MAP.items()}

# Fan speed map (confirmed: windSpeed in settings)
AC_FAN_MAP = {
    "0": "auto",
    "3": "low",
    "2": "medium",
    "1": "high",
}
AC_FAN_MAP_REVERSE = {v: k for k, v in AC_FAN_MAP.items()}

# ─── Washing machine attributes ───────────────────────────────────────────────
# Confirmed from the diagnostics of the HW80-B14959TU1IT device
WM_ATTR_STATUS        = "machMode"
WM_ATTR_REMAINING     = "remainingTimeMM"
WM_ATTR_PROGRAM       = "prCode"
WM_ATTR_PROGRAM_NAME  = "programName"              # Textual program name (e.g. "Cotone")
WM_ATTR_PROGRAM_PHASE = "prPhase"                  # Cycle phase (prewash/wash/rinse/spin)
WM_ATTR_TEMP          = "temp"                     # FIXED: "tempLevel" does NOT exist on the device
WM_ATTR_SPIN_SPEED    = "spinSpeed"
WM_ATTR_TOTAL_WASH    = "totalWashCycle"
WM_ATTR_TOTAL_WATER   = "totalWaterUsed"
WM_ATTR_TOTAL_ENERGY  = "totalElectricityUsed"
WM_ATTR_CURRENT_ENERGY = "currentElectricityUsed"  # Energy of the current cycle
WM_ATTR_CURRENT_WATER  = "currentWaterUsed"         # Water of the current cycle
WM_ATTR_ON_OFF        = "onOffStatus"
WM_ATTR_DOOR          = "doorLockStatus"            # Door lock (0=unlocked, 1=locked)
WM_ATTR_DOOR_OPEN     = "doorStatus"                # Physical door (0=closed, 1=open)
WM_ATTR_ERRORS        = "errors"

# ─── Tumble dryer attributes (TD) ─────────────────────────────────────────────
# The tumble dryer does NOT expose totalWashCycle; the cycle counter comes from
# programsCounter (statistics container). Confirmed on the HD100-C367GU1-IT device.
TD_ATTR_CYCLES = "programsCounter"

# ─── Washing machine / tumble dryer states ────────────────────────────────────
WM_STATE_MAP = {
    "0": "In attesa",
    "1": "In esecuzione",
    "2": "In pausa",
    "3": "Completato",
    "4": "Errore",
    "5": "Programmato",
    "6": "Ritardo avvio",
    "7": "Mezzo carico",
}

# ─── Additional sensors/binary for the washing group ──────────────────────────
# Keys CONFIRMED live on Roberto's devices: washing machine HW80-B14959TU1IT and
# tumble dryer HD100-C367GU1-IT. They are direct attributes (not in settings).
WM_ATTR_DIRT_LEVEL       = "dirtyLevel"          # selected soil level (1..3)
WM_ATTR_DRY_LEVEL        = "dryLevel"            # dryness level (WD/TD)
WM_ATTR_LOADING          = "loadingPercentage"  # drum load %
WM_ATTR_DELAY            = "delayTime"           # configured start delay (minutes)
# Binary sensor (0/1). Door/door-lock already defined above: WM_ATTR_DOOR_OPEN
# (doorStatus, door open) and WM_ATTR_DOOR (doorLockStatus, door locked).
WM_ATTR_CHILD_LOCK       = "lockStatus"          # control lock (child safety)
WM_ATTR_DRUM_CLEAN       = "drumCleaning"        # recommended drum-cleaning cycle
WM_ATTR_FILTER_CLEAN     = "filterCleaning"      # recommended filter cleaning
WM_ATTR_DRY_CLEAN_NEEDED = "dryCleaningNeeded"   # recommended condenser cleaning

# Cycle phase (prPhase, raw numeric attribute). The maps translate prPhase ->
# phase label; washing machine/washer-dryer and tumble dryer use distinct tables.
# Values not in the map -> "Fase N".
WASHING_PHASE_MAP = {
    "0": "Pronto",
    "1": "Lavaggio",
    "2": "Lavaggio",
    "3": "Salto fase",
    "4": "Risciacquo",
    "5": "Risciacquo",
    "6": "Risciacquo",
    "7": "Asciugatura",
    "8": "Salto fase",
    "9": "Vapore",
    "10": "Pronto",
    "11": "Centrifuga",
    "12": "Pesatura",
    "14": "Lavaggio",
    "15": "Lavaggio",
    "16": "Lavaggio",
    "20": "Avvio rotazione",
    "24": "Rinfresco",
}
TUMBLE_DRYER_PHASE_MAP = {
    "0": "Pronto",
    "1": "Riscaldamento",
    "2": "Asciugatura",
    "3": "Raffreddamento",
    "13": "Raffreddamento",
    "14": "Riscaldamento",
    "15": "Riscaldamento",
    "16": "Raffreddamento",
    "18": "Rotazione",
    "19": "Asciugatura",
    "20": "Asciugatura",
}

# ─── value→label maps for the Tier 2 types (read-only) ────────────────────────
# Decodings of the hOn enums for the sensors of the additional types. Values not
# in the map -> fallback string (handled by the value_fn in sensor.py).

# Authoritative app machMode (0-10), used by the types that share MachineMode
# (oven, dishwasher, ...). NOTE: it is distinct from WM_STATE_MAP, which stays a
# historic local 0-7 map of the washing group and must not be modified.
MACHINE_MODE_MAP = {
    "0": "Inattivo",
    "1": "Selezione",
    "2": "In esecuzione",
    "3": "In pausa",
    "4": "Avvio ritardato",
    "5": "Avvio ritardato (in corso)",
    "6": "Errore",
    "7": "Terminato",
    "8": "Test",
    "9": "Arresto",
    "10": "Mantieni fresco",
}

# Dishwasher salt / rinse-aid level (saltStatus / rinseAidStatus).
DW_LEVEL_MAP = {
    "0": "OK",
    "1": "Basso",
    "2": "Critico",
    "3": "Non presente",
}

# Water heater phase (prPhase -> reduced EnumWaterHeaterPhase).
WH_PHASE_MAP = {
    "0": "Pronto",
    "1": "Riscaldamento",
    "2": "Mantenimento",
}

# Robot vacuum state (prPhase/machMode -> RVCMachModes).
RVC_STATE_MAP = {
    "0": "In attesa",
    "1": "Pulizia automatica",
    "2": "Pulizia localizzata",
    "3": "In pausa",
    "4": "Full & Go",
    "5": "Pulizia completata",
    "6": "In carica",
}

# Robot suction power (power).
RVC_POWER_MAP = {
    "0": "Auto",
    "1": "Turbo",
    "2": "Silenzioso",
}
