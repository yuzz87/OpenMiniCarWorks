# Lidar test

import time
import utilities
import pigpio
import math

from rplidar import RPLidar
lidar = RPLidar('/dev/ttyUSB0')

print('Getting RPLidar info...')
info = lidar.get_info()
print(info)

health = lidar.get_health()
print(health)

import rccar

print('done.')
time.sleep(2)

MaxIteration = 10000
DriveSpeedN = 0 # 0.3
Dist_Bin_Div = 16
try:                        # try:の部分にループ処理を書く
    distance_bin = [] # list of list: measured distances for each bin
    distance_avg = [] # average distance for each angle
    for binidx in range(0, Dist_Bin_Div):
        distance_bin.append(list())
        distance_avg.append(0)
        
    for i, scan in enumerate(lidar.iter_scans()):
        print('%d: Got %d measurments' % (i, len(scan)))
        # limited length 
        if i > MaxIteration:
            break
        rccar.rccar_forward(DriveSpeedN)
        
        # put measurement into bin
        for point in range(1, len(scan), 10):
            angle = scan[point][1]
            dist = scan[point][2]
            binidx = math.floor(angle / 360 * Dist_Bin_Div)
            if binidx >= Dist_Bin_Div:
                binidx = Dist_Bin_Div - 1
            # print(angle, binidx)
            distance_bin[binidx].append(dist)
            #print("a:", angle, "d:", dist)
            
        # take average
        for binidx in range(0, Dist_Bin_Div):
            distance_avg[binidx] = 0
            cnt = len(distance_bin[binidx])
            if cnt > 0:
                for data in distance_bin[binidx]:
                    distance_avg[binidx] = distance_avg[binidx] + data / cnt
            else:
                distance_avg[binidx] = 5000
        print("i:", i, " ", distance_avg)            
        
        # move steering
        rccar.rccar_steer(-0.5)
            
        # clear bin
        for binidx in range(0, Dist_Bin_Div):
            distance_bin[binidx]=[] 

except KeyboardInterrupt:   # exceptに例外処理を書く
    print('stop!')
    
lidar.stop()
lidar.stop_motor()
lidar.disconnect()
rccar.rccar_reset()

