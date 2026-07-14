# OpenMiniCarWorks Instructions

## Communication

- Respond to the user in Japanese unless they request another language.
- Explain assumptions, especially when hardware specifications are not present in the repository.
- Use SI units in code, documentation, and explanations. State whether angles are degrees or radians.

## Project Overview

This repository contains software and mechanical data for a Raspberry Pi-based RC car.
The active handoff in this file is steering calibration and steering command
verification. Do not assume any autonomous-driving runner is currently in use unless
the user explicitly says so.

Important files:

- `docs/senior`: inherited notebooks and notes from previous work.
- `scripts/device_test`: hardware test and calibration scripts. Check their GPIO
  configuration before use because some scripts use different pins.

## Development And Verification

There is currently no automated test suite. For behavior changes, add focused tests
when practical and report which checks were actually run.

For the current steering check script, run PC-side checks from its directory:

```bash
cd scripts/device_test/rccar_tests/test_PWM/pigpio
python3 -m py_compile steering_check.py
python3 steering_check.py
```

When `USE_HARDWARE = False`, the second command should only print calculated duty
ratios and must not output PWM.

Generated files and `__pycache__` content are ignored outputs and must not be committed
unless the user explicitly requests them.

## Hardware Configuration

GPIO assignments are script-specific. Always check the active script before hardware
use. Treat all servo, ESC, steering, wheel, encoder, and chassis values as calibration
values rather than universal constants.

## Hardware Safety

- Keep `use_hardware = False` by default. Do not enable hardware output or run a command
  that can move the vehicle unless the user explicitly requests it and confirms the
  vehicle is prepared.
- Never increase throttle, steering limits, or pulse-width safety limits without stating
  the risk and obtaining explicit confirmation.
- Preserve fail-safe cleanup: Ctrl-C and exceptions must command neutral steering and
  neutral throttle before GPIO or pigpio shutdown.
- Raspberry Pi GPIO is 3.3 V logic. Never recommend feeding a 5 V encoder output directly
  into a GPIO input; require a compatible encoder output or level shifting.
- The Raspberry Pi, encoder, servo controller/BEC, and ESC signal ground must share a
  common ground. Do not power a motor or steering servo from a GPIO or 3.3 V pin.
- Do not infer connector pin order from wire color or repository photographs. Require the
  component datasheet or a measured pinout.
- Test with driven wheels lifted from the floor, low throttle, and an accessible physical
  power cutoff before floor operation.
- `pigpiod` must be running for real servo/ESC output. Avoid starting it or accessing GPIO
  during ordinary PC-side verification.

## Implementation Constraints

- Keep Raspberry Pi-only imports lazy so modules remain importable on a development PC.
- Keep hardware access behind `use_hardware` or a similarly explicit boundary.
- Do not silently change GPIO assignments, pulse widths, steering direction, encoder
  direction, or calibration defaults. Update the relevant README or handoff document
  when documented behavior changes.
- If dead reckoning or a vehicle model is used, state that wheel slip, steering
  calibration error, and mechanical backlash can accumulate as pose drift.

## Current Steering Calibration Status

Use this section as the handoff summary when starting a new chat.

### Current Task

The current work is steering calibration and steering command verification for the RC car.
The active check program is:

```text
scripts/device_test/rccar_tests/test_PWM/pigpio/steering_check.py
```

This program converts target steering angles in degrees to steering PWM duty ratio in percent, then optionally outputs the command to the real vehicle.
ESC output is kept at neutral while steering is tested.

### Current Steering Conversion

The current steering conversion is based on duty ratio, not pulse width.
Angles are handled as degrees for the target list and radians inside the conversion formula.

```text
steer_angle_rad = -0.186785136654 * str_duty_percent + 2.018473280947
```

The inverse conversion used by `steering_check.py` is:

```text
str_duty_percent = (target_steer_rad - 2.018473280947) / -0.186785136654
```

Current coefficient values:

```python
DUTY_FIT_A = -0.186785136654
DUTY_FIT_B = 2.018473280947
```

### Current Verification Angles

`steering_check.py` currently checks these target steering angles:

```python
TARGET_STEER_DEG_LIST = [18.0, 9.4, 0.0, -9.0, -18.0]
```

Expected calculated duty ratios are:

```text
18.0 deg  -> 9.124462718 %
9.4 deg   -> 9.928050831 %
0.0 deg   -> 10.806391328 %
-9.0 deg  -> 11.647355633 %
-18.0 deg -> 12.488319939 %
```

### Steering Check Operation

When `USE_HARDWARE = False`, `steering_check.py` only prints calculated values and does not output PWM.

When checking the real vehicle, explicitly change:

```python
USE_HARDWARE = True
```

The keyboard controls in hardware mode are:

```text
w      output the currently displayed steering duty ratio
n      return steering and ESC to neutral
Enter  move to the next target angle
q      stop the check program
```

At program exit, steering and ESC must return to neutral.

### Current Hardware Values For Steering Check

The current test script uses BCM GPIO numbering:

| Function | BCM GPIO | Notes |
| --- | ---: | --- |
| ESC signal | 12 | Kept neutral during steering check |
| Steering servo signal | 13 | Steering duty output |

Current neutral and safety values in `steering_check.py`:

```python
NEUTRAL_DUTY_PERCENT = 10.895
PWM_NEUTRAL_STR = NEUTRAL_DUTY_PERCENT
PWM_NEUTRAL_SPD = 10.55
PWM_SAFE_MIN = 7.50
PWM_SAFE_MAX = 13.00
```

Always check the script-specific GPIO settings before hardware use.

### Known File Issue To Avoid

`steering_check.py` was previously corrupted by accidentally pasting the whole program into the middle of this return statement:

```python
return (target_steer_rad - DUTY_FIT_B) / DUTY_FIT_A
```

If `python steering_check.py` reports a `SyntaxError` around `import math`, check that the file has not been pasted into itself. The file should contain exactly one top-level copy of the program and exactly one `DUTY_FIT_A` assignment.

Before hardware use, run:

```bash
cd scripts/device_test/rccar_tests/test_PWM/pigpio
python3 -m py_compile steering_check.py
python3 steering_check.py
```

The second command should print the five calculated duty ratios when `USE_HARDWARE = False`.
