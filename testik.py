import os
import sys
import json
from _datetime import datetime
import time
import paramiko
import subprocess
#
def resource_path(relative_path):
    # Преобразование путей ресурсов в пригодный для использования формат для PyInstaller
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath('.'), relative_path)

config_file = open(resource_path("settings.json"), 'r')
config = json.load(config_file)  # json-файл конфигурации
config_file.close()

# temp_for_del_list = []
# client_del = paramiko.SSHClient()
# # Создаём соединение
# client_del.set_missing_host_key_policy(paramiko.AutoAddPolicy())
# client_del.connect(hostname=config['ssh_host'],
#                            username=config['ssh_login'],
#                            password=config['ssh_password'],
#                            port=int(config['ssh_port']))
#
# for subdir in config['sys_dirs']:
#     if subdir != 'server':
#         ls_stdin, ls_stdout, ls_stderr = client_del.exec_command(f'cd ../{config["path_to_server_backups"].strip("/")}/{subdir}; ls')
#         data = ls_stdout.read()
#         temp_for_del_list.extend([f'{subdir}/{file}' for file in data.decode('utf-8').strip('\n').split('\n')])
#
# for subdir_file in temp_for_del_list:
#     if subdir_file.split('/')[1].startswith(config['latest_run']):
#         rem_stdin, rem_stdout, rem_stderr = client_del.exec_command(f'cd ../{config["path_to_server_backups"].strip("/")}/{subdir_file.split("/")[0]}; rm -r {subdir_file.split("/")[1]}')

print(str(datetime.fromtimestamp(os.stat('/Users/ivannochovkin/suslikbackups/database/2022_11_07_19_25_db_montes_radutsky.tar.gz').st_birthtime)).split('.')[0])
print(str(datetime.fromtimestamp(os.path.getmtime('/Users/ivannochovkin/suslikbackups/database/2022_11_07_19_25_db_montes_radutsky.tar.gz'))).split('.')[0])