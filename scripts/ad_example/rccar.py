# Setup PWM
#
# Copyright (c) 2023 MODECO
# Released under the MIT license.
# see https://opensource.org/licenses/MIT

import time
import utilities
import pigpio

# global calibration parameters 
PWM_Hz = 70 
PWM_NeutralStr = 10.00  #@70Hz
PWM_NeutralSpd = 10.29 #@70Hz
#PWM_CruiseSpd = PWM_NeutralSpd - 0.5 #@70Hz # Cruising speed 

# PWM ioutput pins (hardware PWM works only with 12/13(or 18/19) in RPi)
PWM_PinSpd = 12
PWM_PinStr = 13

# start hardware PWM
pi = pigpio.pi()
pi.set_mode(PWM_PinSpd, pigpio.OUTPUT)
pi.set_mode(PWM_PinStr, pigpio.OUTPUT)

# parameter class
class PWM_Parameters:
    def __init__(self, Pi, Hz, StrPin, SpdPin, StrN, SpdN):
        self.Pi = Pi
        self.Hz = Hz
        self.StrPin = StrPin
        self.SpdPin = SpdPin
        # steering constants
        self.StrN = StrN
        self.StrLMax = StrN + 8
        self.StrRMax = StrN - 8
        self.SpdN = SpdN
        self.SpdFMax = SpdN - 0.05 # Around 6 is physical max, but too fast. limitting 2
        self.SpdBMax = SpdN + 2

pwm_param = PWM_Parameters(pi, PWM_Hz, PWM_PinStr, PWM_PinSpd, PWM_NeutralStr, PWM_NeutralSpd)

# in pigpio, 1000,000 = 100% 
# then duty100(100) = 100% duty rate
def duty100(rate):
    # min and max for safety input
    PWM_SAFE_MIN = 7.50 
    PWM_SAFE_MAX = 13.00 
    if rate > PWM_SAFE_MAX:
        rate = PWM_SAFE_MAX
    if rate < PWM_SAFE_MIN:
        rate = PWM_SAFE_MIN
    return int(rate * 10000)

# functions for simple control

# rccar stop
def rccar_reset():
    global pwm_param
    
    # GPIO12: Hz, duty ratio for ACC
    pwm_param.Pi.hardware_PWM(pwm_param.SpdPin, pwm_param.Hz, duty100(pwm_param.SpdN))
    # GPIO13: Hz, duty ratio for STR
    pwm_param.Pi.hardware_PWM(pwm_param.StrPin, pwm_param.Hz, duty100(pwm_param.StrN))

# rccar drive, N_Speed = [0 - 1], normalized speed
def rccar_forward(N_Speed):
    global pwm_param
    
    n_spd = N_Speed
    if n_spd < 0:
        n_sped = 0
    if n_spd > 1:
        n_spd = 1
    # GPIO12: Hz, duty ratio for ACC
    Delta = pwm_param.SpdN - pwm_param.SpdFMax
    pwm_param.Pi.hardware_PWM(pwm_param.SpdPin, pwm_param.Hz, duty100(pwm_param.SpdN - n_spd*Delta))

# rccar steering, N_Steering = [-1 - 1], normalized steering angle
def rccar_steer(N_Steering):
    global pwm_param
    
    n_str = N_Steering
    if n_str < -1:
        n_str = -1
    if n_str > 1:
        n_str = 1
    # GPIO12: Hz, duty ratio for ACC
    Delta = pwm_param.StrN - pwm_param.StrLMax
    pwm_param.Pi.hardware_PWM(pwm_param.StrPin, pwm_param.Hz, duty100(pwm_param.StrN - n_str*Delta))


# initialize
spd_ref = PWM_NeutralSpd
str_ref = PWM_NeutralStr

gppin_acc = PWM_PinSpd
gppin_str = PWM_PinStr

Delta_Jog = 0.10 # jog stepping

rccar_reset()
time.sleep(1)

def write_help():
    print("n: stop, w&d:speed, a&d:steering")

write_help()

