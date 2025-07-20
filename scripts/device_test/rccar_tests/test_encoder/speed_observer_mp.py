import multiprocessing
from multiprocessing import Value, Array, Process 
import RPi.GPIO as GPIO
from math import pi
import time

# speed observer program 
# copyright 2025 @ MODECO LLC
# 
# measure encoder A\B phase with simple logit
# count up/down only A phase changes at rising edge
# [basic logic]
# if A=true & pre-A=false:    # true @ A rises up 
#     if B=false:    # phase A advances to phase B
#          count-up
#     else:          # phase B advances to phase A
#          count-down

class SpeedObserver(object):
    @staticmethod
    def updateSpeed(
            q_speed: multiprocessing.Value,
            q_count: multiprocessing.Value,
            A_PIN, B_PIN, n_teeth, wheel_diameter
        ):
        '''
        q_speed: shared info for speed (m/s)
        q_count: shared info for count (pulse)
        A_PIN: pin number of encoder A
        B_PIN: pin number of encoder B
        n_teeth: number of teeth on encoder
        wheel_diameter: wheel diameter in meters
        '''
        # GPIO setup
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(A_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.setup(B_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)

        # initialize variables
        speed = 0
        last_a_flag = GPIO.input(A_PIN)
        last_fwd_time = 0
        last_bwd_time = 0

        while True:
            a_flag = GPIO.input(A_PIN)
            b_flag = GPIO.input(B_PIN)

            # check rise A phase
            if a_flag and not last_a_flag:
                if not b_flag:
                    # forward
                    q_count.value = q_count.value + 1
                    dt = time.time() - last_fwd_time
                    last_fwd_time = time.time()
                else:
                    # backward
                    q_count.value = q_count.value - 1                    
                    dt = last_bwd_time - time.time()
                    last_bwd_time = time.time()
                # update speed
                speed = (pi * wheel_diameter / n_teeth) / dt
            else:
                # check timeout
                if (time.time() - max(last_fwd_time, last_bwd_time) ) > 0.1:
                     speed = 0

            last_a_flag = a_flag

            # add speed to queue
            q_speed.value = speed

def printQueue(q: multiprocessing.Value, c: multiprocessing.Value):
    DeltaT = 0.1
    while True:
        speed = q.value
        count = c.value
        print( str(count) +" : "+ str(speed) )
        time.sleep(DeltaT)

def logQueue(q: multiprocessing.Value, c: multiprocessing.Value):
    path = 'latest_speedlog.csv'
    DeltaT = 0.01
    skip = 10
    cnt = 0
    with open(path, mode='w') as f:
        f.write("step, count, speed\n")
        while True:
            # get speed and log to csv file
            # print(q.get())
            speed = q.value
            count = c.value
            f.write(str(cnt*DeltaT)+","+str(count)+ ","+str(speed))
            f.write("\n")

            # show speed every (deltaT * skip) steps
            #if cnt % skip==0:
            #    print(speed)
            time.sleep(DeltaT)
            cnt = cnt + 1

def main():
    # parameters
    A_PIN = 22
    B_PIN = 27
    n_teeth = 36
    wheel_diameter = 0.066

    # create shared memory 
    shared_speed = multiprocessing.Value('d', 0)
    shared_count = multiprocessing.Value('i', 0)

    # create processes
    processes = [
        multiprocessing.Process(
            target=SpeedObserver.updateSpeed,
            args=(shared_speed, shared_count, A_PIN, B_PIN, n_teeth, wheel_diameter,)
        ),
        multiprocessing.Process(
            target=printQueue,
            args=(shared_speed, shared_count)
        ),
        multiprocessing.Process(
            target=logQueue,
            args=(shared_speed, shared_count)
        )        
    ]

    # start processes
    for process in processes:
        process.start()

    try:
        while True:
            # wait for measurement
            time.sleep(1)
    except KeyboardInterrupt:
        # close processes
        for process in processes:
            process.terminate()
            process.join()
        print("\nclosed all processes")


if __name__ == "__main__":
    main()
