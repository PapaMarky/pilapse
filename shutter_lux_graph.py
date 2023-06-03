import argparse
import logging
import math

import matplotlib.pyplot as plt
import numpy as np

shutter0 = 0.1
#shutter0 = 6
shutter1 = 0.000955

lux0 = 0
lux1 = 3250

# lux, shutterspeed table
table1 = [
    (0.1152, 6),
    (0.1728, 3),
    (1, 1),
    (20, 0.5),
    (50, 0.0959),
    (224, 0.033),
    (400, 0.016),
    (474, 0.012),
    (594, 0.0094),
    (982, 0.005),
    (1200, 0.004),
    (1320, 0.0035),
    (1692, 0.0019),
    (1983, 0.00127),
    (2500, 0.00106),
    (3252, 0.00099)
]
table = [
    (0.1152, 10),
    (0.1728, 5),
    (1, 1),
    (10, 0.097),
    (50, 0.0347),
    (224, 0.022),
    (400, 0.016),
    (474, 0.012),
    (575, 0.0024),
    (982, 0.005),
    (1200, 0.004),
    (1320, 0.0035),
    (1692, 0.0019),
    (1983, 0.00127),
    (2500, 0.00106),
    (3252, 0.00099)
]
def shutter_function(lux):
    for i in range(len(table)):
        (l1, s1) = table[i]
        if l1 >= lux:
            if i == 0:
                return s1
            l0, s0 = table[i-1]
            p = (lux - l0) / (l1 - l0)
            return s0 + p * (s1 - s0)
    return s1

if __name__ == '__main__':
    logging.basicConfig(
        filename=None,
        level=logging.INFO,
        format='%(asctime)s|%(levelname)s|%(threadName)s|%(message)s'
    )

    parser = argparse.ArgumentParser('Tool for developing lux to shutter speed function')
    parser.add_argument('--input', type=str,
                        help='Path to CSV file containing lux, shutter-speed pairs ordered by lux')

    config = parser.parse_args()

    lux_list = []
    shutter_list = []
    shutter_min_max = None
    lux_min_max = None
    try:
        with open(config.input) as input_file:
            for line in input_file.readlines():
                lux, shutter = line.split(',')
                if lux == 'lux':
                    continue
                lux = float(lux)
                shutter = float(shutter)
                lux_list.append(lux)
                shutter_list.append(shutter)
    except Exception as e:
        logging.exception(e)


    logging.info(f'    lux range {lux_list[0]} - {lux_list[-1]}')
    logging.info(f'shutter range {shutter_list[0]} - {shutter_list[-1]}')

    tx_list = []
    ty_list = []
    for x, y in table:
        tx_list.append(x)
        ty_list.append(y)

    dx_list = lux_list
    dy_list = []
    for x in lux_list:
        dy_list.append(shutter_function(x))
    plt.scatter(lux_list, shutter_list)
    x = np.linspace(lux_list[0], lux_list[-1])
    # plt.plot(x, shutter_function(x), color='green')
    plt.plot(lux_list, dy_list, color='green')
    #plt.plot(tx_list, ty_list, color='red')
    plt.xlabel('lux')
    plt.ylabel('shutter speed')
    plt.grid()
    plt.show()

