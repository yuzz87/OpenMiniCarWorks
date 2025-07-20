# Simplly display the pin-state for encoder 

import multiprocessing
import RPi.GPIO as GPIO
from math import pi
import time


def main():
    # parameters
    A_PIN = 22
    B_PIN = 27
    n_teeth = 36            # number of teeth, 36 for encoder kit of ADRC-CAR
    wheel_diameter = 0.066   # 2 x radius

    print("initialize...")
    # GPIO setup
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(A_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    GPIO.setup(B_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)


    try:
        while True:
            time.sleep(0.01)
            a_flag = 1 if GPIO.input(A_PIN) != 0 else 0
            b_flag = 1 if GPIO.input(B_PIN) != 0 else 0
            print( "A:" + str(a_flag) + " B:" + str(b_flag) )
            
    except KeyboardInterrupt:
        print("\nterminated.")


if __name__ == "__main__":
    main()
