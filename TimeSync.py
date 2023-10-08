#!/usr/bin/env python3
import argparse
from paramiko.client import SSHClient
from datetime import datetime
def time_sync_remote_system(address:str, user:str, password:str, check_only:bool=False):
    client = SSHClient()
    client.load_system_host_keys()
    client.connect(address, username=user, password=password)

    now = datetime.now()
    _, out, err = client.exec_command('date +"%Y %m %d %H %M %S %N"')
    err = err.read().decode('utf-8')
    out = out.read().decode('utf-8')

    if err:
        print(f'error: {err}')
        return
    parts = out.split()
    print(f'Remote Datetime: {parts}')

    microsecond = int(int(parts[6])/1000)
    print(f'nano: {parts[6]}, micro: {microsecond}')
    remote_time = datetime(int(parts[0]), int(parts[1]), int(parts[2]),
                           hour=int(parts[3]), minute=int(parts[4]), second=int(parts[5]),
                           microsecond=int(int(parts[6])/1000))
    print(f'rem time: {remote_time}')
    time_diff = abs(remote_time - now)
    print(f'diff: {time_diff.seconds}')
    print(f'diff: {abs(remote_time - now)}')
    if time_diff.seconds < 1:
        print('Less than one second difference. Close enough')
    now = datetime.now()
    _, out, err = \
        client.exec_command(f'sudo date -s "{now.year}-{now.month}-{now.day} {now.hour}:{now.minute}:{now.second}"')
    print(f'{err.read().decode("utf-8")}')
    print(f'{out.read().decode("utf-8")}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--user', type=str,
                        help='User name to use when logging in to remote system')
    parser.add_argument('--password', type=str,
                        help='Password to use when logging in to remote system')
    parser.add_argument('--host', type=str,
                        help='IP address or hostname of system to time-sync with this computer')
    parser.add_argument('--check', action='store_true',
                        help='Do not set the remote system\'s time. Just report the difference.')
    args = parser.parse_args()
    # print(f'args: {args}')

    time_sync_remote_system(args.host, args.user, args.password, args.check)