import os
import sys
import time
import json
import dbbckp
import wsbckp
import logging
import paramiko
from datetime import datetime

def resource_path(relative_path):
    # Преобразование путей ресурсов в пригодный для использования формат для PyInstaller
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath('.'), relative_path)

def json_adder():
    # Изменяем словарь дат последнего бэкапа приложений, путём слияния словаря файла настроек и словаря, образованного текущей сессией
    json_file = open(resource_path("settings.json"), "r+", encoding='utf8')
    db_data = json.load(json_file)
    db_data["latest_run"] = current_datetime
    json_file.seek(0)
    json.dump(db_data, json_file, ensure_ascii=False, indent=4)
    json_file.truncate()
    json_file.close()

def get_custom_date(date_format):
    # Записываем время запуска программы в переменную, берём формат записи даты в Json-файле
    c_d = datetime.now().strftime(date_format)
    return c_d

def log_conf():
    # Создаём лог-файл
    try:
        os.stat(config['path_to_local_backups'] + "/logs/")
    except Exception:
        os.makedirs(config['path_to_local_backups'] + "/logs/")
    open(config['path_to_local_backups'] + "/logs/" + current_datetime + ".log", 'w').close()

    # Конфигурация логирования
    logger.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s', '%d.%m.%Y %H:%M:%S')
    fh = logging.FileHandler(f"{config['path_to_local_backups']}/logs/{current_datetime}.log", mode='a', encoding='utf-8')
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(formatter)
    logger.addHandler(fh)

def delete_expired():
    # Удаляем архивы бэкапов на локальном ПК, которым больше чем... (значение в дн. из Json-файла)
    expired_local_files_data = []
    for path, subdirs, files in os.walk(config['path_to_local_backups']):
        if not path.endswith('/server') and not path.endswith('/logs'):
            for file in files:
                if not file.startswith('.'):
                    full_path = os.path.join(path, file)
                    is_expired = os.stat(full_path).st_mtime < (time.time() - int(config['backup_local_age']) * 60 * 60 * 24)
                    if is_expired:
                        expired_local_files_data.append(file)
                        os.remove(full_path)
    if len(expired_local_files_data) != 0:
        logger.info(f'Deleted old backup files on the local PC (after: {config["backup_local_age"]}days), in total: {len(expired_local_files_data)}, {expired_local_files_data}')

    # Удаляем архивы бэкапов на сервере, которым больше чем... (значение в дн. из Json-файла)
    expired_server_files_data = []
    temp_for_del_list = []
    client_del_expired = paramiko.SSHClient()
    # Создаём соединение
    client_del_expired.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client_del_expired.connect(hostname=config['ssh_host'],
                             username=config['ssh_login'],
                             password=config['ssh_password'],
                             port=int(config['ssh_port']))

    for subdir in config['sys_dirs']:
        if subdir != 'server':
            ls_stdin, ls_stdout, ls_stderr = client_del_expired.exec_command(f'cd ../{config["path_to_server_backups"].strip("/")}/{subdir}; ls')
            data = ls_stdout.read()
            temp_for_del_list.extend([f'{subdir}/{file}' for file in data.decode('utf-8').strip('\n').split('\n')])

    for subdir_file in temp_for_del_list:
        if not subdir_file.split('/')[1].startswith('.'):
            stat_stdin, stat_stdout, stat_stderr = client_del_expired.exec_command(f'cd ../{config["path_to_server_backups"].strip("/")}/{subdir_file.split("/")[0]}; stat -c "%Y" {subdir_file.split("/")[1]}')
            is_expired = int(stat_stdout.read().decode('utf-8').strip('\n').split('\n')[0]) < time.time() - int(config['backup_server_age']) * 60 * 60 * 24
            if is_expired:
                expired_server_files_data.append(subdir_file.split('/')[1])
                rem_stdin, rem_stdout, rem_stderr = client_del_expired.exec_command(f'cd ../{config["path_to_server_backups"].strip("/")}/{subdir_file.split("/")[0]}; rm {subdir_file.split("/")[1]}')
    if len(expired_server_files_data) != 0:
        logger.info(f'Deleted old backup files on the server (after: {config["backup_server_age"]}days), in total: {len(expired_server_files_data)}, {expired_server_files_data}')
    client_del_expired.close()

def manual_start(scenario, db_tuple, ws_tuple, opt_dow, opt_del):
    # Сценарий старта бэкапа
    global config
    global logger
    global current_datetime
    config_file = open(resource_path("settings.json"), 'r')
    config = json.load(config_file)  # json-файл конфигурации
    config_file.close()
    logger = logging.getLogger('logger') # Логирование
    current_datetime = get_custom_date(config['dateFormat']) # Время запуска сессии для именования папок (архивов) с документами
    json_adder()  # Обновляем значение времени последнего запуска бэкапа
    log_conf()  # Включаем логирование

    # Сценарии запуска (БД, ВС, СВ или комбинации)
    if scenario == 1:
        dbbckp.dump(cur_datetime=current_datetime, flag='manual', config=config, db_names=db_tuple, dow_file=opt_dow, del_file=opt_del) # Бэкап БД
    elif scenario == 2:
        wsbckp.dump(cur_datetime=current_datetime, flag='manual', config=config, ws_names=ws_tuple, dow_file=opt_dow, del_file=opt_del) # Бэкап ВС
    elif scenario == 3:
        dbbckp.dump(cur_datetime=current_datetime, flag='manual', config=config, db_names=db_tuple, dow_file=opt_dow, del_file=opt_del) # Бэкап БД
        if not dbbckp.EOFFlag:
            wsbckp.dump(cur_datetime=current_datetime, flag='manual', config=config, ws_names=ws_tuple, dow_file=opt_dow, del_file=opt_del) # Бэкап ВС
    else:
        pass

    if dbbckp.EOFFlag or wsbckp.EOFFlag:
        pass
    else:
        delete_expired()  # Удаляем устаревшие архивы бэкапов

    # Удаляем хендлеры логирования (для предотвращения записи логов в предыдущий(щие) файл(ы)
    handlers = logger.handlers[:]
    for handler in handlers:
        logger.removeHandler(handler)
        handler.close()

    logging.shutdown() # Выключаем логирование

# def cron_start(db_tuple, db_combo):
#     # Сценарий старта бэкапа
#     global config
#     global logger
#     global current_datetime
#     config_file = open(resource_path("settings.json"), 'r')
#     config = json.load(config_file)  # json-файл конфигурации
#     config_file.close()
#     logger = logging.getLogger('logger') # Логирование
#     current_datetime = get_custom_date(config['dateFormat']) # Время запуска сессии для именования папок (архивов) с документами
#     json_adder() # Обновляем значение времени последнего запуска бэкапа
#     log_conf() # Включаем логирование
#
#     # Сценарии запуска (БД или ФС или ФБ и ФС вместе)
#     if config['cron_db'] and not config['cron_fs']:
#         dbbckp.dump(cur_datetime=current_datetime, flag='manual', config=config, db_names=db_tuple, db_all=db_combo) #Бэкап БД
#     elif not config['cron_db'] and config['cron_fs']:
#         wsbckp.mysqlconnect(cur_datetime=current_datetime, flag='manual', config=config, up_to_date=config['cron_act_check'])  # Бэкап ФС
#     else:
#         dbbckp.dump(cur_datetime=current_datetime, flag='manual', config=config, db_names=db_tuple, db_all=db_combo)  # Бэкап БД
#         if not dbbckp.EOFFlag:
#             wsbckp.mysqlconnect(cur_datetime=current_datetime, flag='manual', config=config, up_to_date=config['cron_act_check'])  # Бэкап ФС
#
#     if not dbbckp.EOFFlag:
#         delete_expired()  # Удаляем устаревшие архивы бэкапов
#
#     # Удаляем хендлеры логирования (для предотвращения записи логов в предыдущий(щие) файл(ы)
#     handlers = logger.handlers[:]
#     for handler in handlers:
#         logger.removeHandler(handler)
#         handler.close()
#
#     logging.shutdown() # Выключаем логирование