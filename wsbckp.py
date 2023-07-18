import os
import sys
import json
import logging
import ftplib
import paramiko
import subprocess
from time import sleep
from datetime import datetime

logger = logging.getLogger('logger')
EOFFlag = False # Флаг ручного останова бэкапа
client_copy_arch = paramiko.SSHClient()

def resource_path(relative_path):
    # Преобразование путей ресурсов в пригодный для использования формат для PyInstaller
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath('.'), relative_path)

def json_adder(data, json_obj):
    # Изменяем словарь дат последнего бэкапа приложений, путём слияния словаря файла настроек и словаря, образованного текущей сессией
    json_file = open(resource_path("settings.json"), "r+", encoding='utf8')
    ws_data = json.load(json_file)
    if json_obj == 'backups_create':
        merger = ws_data[json_obj]
        merger.update(data)
        ws_data[json_obj] = merger
    elif json_obj == 'latest_wss':
        ws_data[json_obj] = data
    json_file.seek(0)
    json.dump(ws_data, json_file, ensure_ascii=False, indent=4)
    json_file.truncate()
    json_file.close()

def dump(cur_datetime, flag, config, ws_names, dow_file, del_file):
    global EOFFlag
    EOFFlag = False
    # Делаем бэкап (дамп) таблиц из списка в Json-файле
    logger.info('-------WEBSITE BACKUP START-------')

    # Данные подключения по SSH для вывода в лог
    access_ssh_data_log = {'host': config['ssh_host'], 'user': config['ssh_login'], 'port': config['ssh_port'], 'password': '*скрыт*'}
    logger.info(f'Attempt to connect to the server via SSH using data: {access_ssh_data_log}')
    # created_backups = []  # Множество названий проектов с флагом "L", для которых есть новая версия бэкапа
    client_copy_arch = paramiko.SSHClient()
    try:
        # Создаём соединение
        client_copy_arch.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client_copy_arch.connect(hostname=config['ssh_host'],
                                username=config['ssh_login'],
                                password=config['ssh_password'],
                                port=int(config['ssh_port']))
    except Exception as e:
        logger.critical(f'Error connecting to the server via SSH! {e}')
        logger.info('-------WEBSITE BACKUP FINISH WITH ERROR-------')
        client_copy_arch.close()
        handlers = logger.handlers[:]
        for handler in handlers:
            logger.removeHandler(handler)
            handler.close()
        if flag == 'manual':
            return
        else:
            sys.exit()

    # Цикл, перебирающий сайты для копирования
    logger.info(f'SSH connection to server successful')
    logger.info(f'Start backing up websites on the server({len(ws_names)}): {ws_names}')
    for site in ws_names:
        if EOFFlag:
            client_copy_arch.close()
            handlers = logger.handlers[:]
            for handler in handlers:
                logger.removeHandler(handler)
                handler.close()
            break

        try:
            # Создаём список ВС
            stdin, stdout, stderr = client_copy_arch.exec_command(f'mkdir -p /{config["path_to_server_backups"].strip("/")}/site; cd ../www/wwwroot; cp -r {site} /{config["path_to_server_backups"].strip("/")}/site/{cur_datetime}_ws_{site}')
            exit_status = stdout.channel.recv_exit_status()
        except Exception as e:
            logger.critical(f'Website backup error {site}! {e}')
            logger.info('-------WEBSITE BACKUP FINISH WITH ERROR-------')
            client_copy_arch.close()
            handlers = logger.handlers[:]
            for handler in handlers:
                logger.removeHandler(handler)
                handler.close()
            if flag == 'manual':
                break
            else:
                sys.exit()

    if EOFFlag:
        client_copy_arch.close()
        handlers = logger.handlers[:]
        for handler in handlers:
            logger.removeHandler(handler)
            handler.close()
        return

    logger.info(f'Website backups successfully created on the server')
    logger.info(f'Start archiving website backups on the server')
    # Цикл, перебирающий сайты для архивирования на сервере
    for site in ws_names:
        if EOFFlag:
            client_copy_arch.close()
            handlers = logger.handlers[:]
            for handler in handlers:
                logger.removeHandler(handler)
                handler.close()
            break
        # Архивируем файл с бэкапом и удаляем исходник
        try:
            stdin, stdout, stderr = client_copy_arch.exec_command(f'cd ../{config["path_to_server_backups"].strip("/")}/site; tar -czf {cur_datetime}_ws_{site.replace(".", "_")}.tar.gz {cur_datetime}_ws_{site}; rm -r {cur_datetime}_ws_{site}')
            exit_status = stdout.channel.recv_exit_status()
        except Exception as e:
            logger.critical(f'Ошибка архивации файла бэкапа! {e}')
            logger.info('-------WEBSITE BACKUP FINISH WITH ERROR-------')
            client_copy_arch.close()
            handlers = logger.handlers[:]
            for handler in handlers:
                logger.removeHandler(handler)
                handler.close()
            if flag == 'manual':
                break
            else:
                sys.exit()

    if EOFFlag:
        client_copy_arch.close()
        handlers = logger.handlers[:]
        for handler in handlers:
            logger.removeHandler(handler)
            handler.close()
        return

    logger.info(f'Website backups successfully archived on the server')

    if dow_file:
        # Скачиваем файлы бэкапов на локальный ПК, если таковая опция включена
        # Данные подключения по FTP для вывода в лог
        access_ftp_data_log = {'host': config['ftp_host'], 'user': config['ftp_login'], 'port': config['ftp_port'], 'password': '*скрыт*'}
        logger.info(f'Attempt to connect to FTP server using data: {access_ftp_data_log}')
        # Создаём соединение
        server_dow = ftplib.FTP()
        try:
            server_dow.connect(config['ftp_host'], int(config['ftp_port']))
            server_dow.login(config['ftp_login'], config['ftp_password'])
            server_dow.encoding = "utf-8"
            server_dow.cwd(f'/{config["path_to_server_backups"].strip("/")}/site')
        except Exception as e:
            logger.critical(f'FTP server connection error! {e}')
            logger.info('-------WEBSITE BACKUP FINISH WITH ERROR-------')
            server_dow.quit()
            client_copy_arch.close()
            handlers = logger.handlers[:]
            for handler in handlers:
                logger.removeHandler(handler)
                handler.close()
            if flag == 'manual':
                return
            else:
                sys.exit()
        logger.info(f'FTP connection to server successful')
        logger.info(f'Start downloading website backups to your local PC')
        if not os.path.isdir(f'{config["path_to_local_backups"]}/site'):
            os.makedirs(f'{config["path_to_local_backups"]}/site')
        # Цикл, перебирающий сайты для скачивания на локальный ПК
        for site in ws_names:
            if EOFFlag:
                client_copy_arch.close()
                handlers = logger.handlers[:]
                for handler in handlers:
                    logger.removeHandler(handler)
                    handler.close()
                break
            with open(f'{config["path_to_local_backups"]}/site/{cur_datetime}_ws_{site.replace(".", "_")}.tar.gz', 'wb') as my_file:
                server_dow.retrbinary('RETR ' + f'{cur_datetime}_ws_{site.replace(".", "_")}.tar.gz', my_file.write, 1024)
        server_dow.quit()
        logger.info(f'Website backups successfully downloaded to local PC')

        if EOFFlag:
            client_copy_arch.close()
            handlers = logger.handlers[:]
            for handler in handlers:
                logger.removeHandler(handler)
                handler.close()
            return
        unbroken_backups = []  # Бэкапы, скаченные с неправильным размером (нецельные)
        broken_backups = []  # Бэкапы, скаченные с правильным размером (цельные)

        if EOFFlag:
            client_copy_arch.close()
            handlers = logger.handlers[:]
            for handler in handlers:
                logger.removeHandler(handler)
                handler.close()
            return
        for site in ws_names:
            # Сравниваем размеры бэкапов на сервере и локальном ПК (проверка на целосность)
            s_size_stdin, s_size_stdout, s_size_stderr = client_copy_arch.exec_command(
                f'cd ../{config["path_to_server_backups"]}/site; stat --printf="%s" {cur_datetime}_ws_{site.replace(".", "_")}.tar.gz')
            exit_status = s_size_stdout.channel.recv_exit_status()
            server_stat_size = int(
                s_size_stdout.read().decode('utf-8').strip('\n').split('\n')[0])  # Размер файла на сервере
            local_stat_size = int(os.stat(
                f'{config["path_to_local_backups"]}/site/{cur_datetime}_ws_{site.replace(".", "_")}.tar.gz').st_size)  # Размер файла на локальном ПК
            if server_stat_size != local_stat_size:
                broken_backups.append(site)
            else:
                unbroken_backups.append(site)
        if EOFFlag:
            client_copy_arch.close()
            handlers = logger.handlers[:]
            for handler in handlers:
                logger.removeHandler(handler)
                handler.close()
            return
        if len(broken_backups) > 0:
            logger.warning(f'Mismatch of the sizes of websites backups, in total: {len(broken_backups)}, {broken_backups}')
        actual_value = {(ws, cur_datetime) for ws in unbroken_backups}
        actual_value_wss = unbroken_backups
    else:
        # # Записываем в json-файл актуальные значения по проектам/бэкапам
        actual_value = {(ws, cur_datetime) for ws in ws_names}
        actual_value_wss = ws_names

    if del_file:
        # Удаляем файлы бэкапов на сервере, если таковая опция включена
        logger.info(f'Start deleting website backups on the server')
        for site in ws_names:
            if EOFFlag:
                client_copy_arch.close()
                handlers = logger.handlers[:]
                for handler in handlers:
                    logger.removeHandler(handler)
                    handler.close()
                break
                # Архивируем файл с бэкапом и удаляем исходник
            try:
                stdin, stdout, stderr = client_copy_arch.exec_command(
                    f'cd ../{config["path_to_server_backups"].strip("/")}/site; rm {cur_datetime}_ws_{site.replace(".", "_")}.tar.gz')
                exit_status = stdout.channel.recv_exit_status()
            except Exception as e:
                logger.critical(f'Error deleting backup file! {e}')
                logger.info('-------WEBSITE BACKUP FINISH WITH ERROR-------')
                client_copy_arch.close()
                handlers = logger.handlers[:]
                for handler in handlers:
                    logger.removeHandler(handler)
                    handler.close()
                if flag == 'manual':
                    break
                else:
                    sys.exit()
        logger.info(f'Website backups successfully deleted on the server')

    json_adder(actual_value, 'backups_create')
    json_adder(actual_value_wss, 'latest_wss')
    # Закрываем SSH соединение

    client_copy_arch.close()
    logger.info('-------WEBSITE BACKUP FINISH-------')

    # logger.info(f'Начало сборки и сохранения данных о содержимом бэкапов веб-сайтов {site}')

    # # Формальности и запись данных о произведённых бэкапах веб-сайтов
    # try:
    #     pass
    #     if EOFFlag:
    #
    #         client_copy_arch.close()
    #         handlers = logger.handlers[:]
    #         for handler in handlers:
    #             logger.removeHandler(handler)
    #             handler.close()
    #         break
    #
    #     logger.info(f'Данные о содержимом бэкапа веб-сайта {site} успешно собраны и сохранены')
    # except Exception as e:
    #     logger.critical(f'Ошибка выполнения запроса к серверу по FTP! {e}')
    #     logger.info('-------ФИНИШ БЭКАПА ВЕБ-САЙТОВ С ОШИБКОЙ-------')
    #
    #     client_copy_arch.close()
    #     handlers = logger.handlers[:]
    #     for handler in handlers:
    #         logger.removeHandler(handler)
    #         handler.close()
    #     if flag == 'manual':
    #         break
    #     else:
    #         sys.exit()

    # # Записываем в json-файл актуальные значения по проектам/бэкапам
    # latest_stencil = {(str(x), dbs_for_dbbckp_dict[x]) for x in dbs_for_dbbckp_dict}
    # actual_value = {(str(x), cur_datetime) for x in dbs_for_dbbckp_dict}
    # latest_dbs = [str(x[0]) for x in dbs_for_dbbckp_tuple]
    # json_adder(actual_value, 'backups_create')
    # json_adder(latest_stencil, 'latest_stencil')
    # json_adder(latest_dbs, 'latest_dbs')
    # Закрываем SSH соединение



