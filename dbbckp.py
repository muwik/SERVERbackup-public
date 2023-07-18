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
    db_data = json.load(json_file)
    if json_obj == 'backups_create':
        merger = db_data[json_obj]
        merger.update(data)
        db_data[json_obj] = merger
    elif json_obj == 'latest_dbs':
        db_data[json_obj] = data
    json_file.seek(0)
    json.dump(db_data, json_file, ensure_ascii=False, indent=4)
    json_file.truncate()
    json_file.close()

def dump(cur_datetime, flag, config, db_names, dow_file, del_file):
    global EOFFlag
    EOFFlag = False
    # Делаем бэкап (дамп) таблиц из списка в Json-файле
    logger.info('-------BACKUP DATABASES START-------')

    # Данные подключения по SSH для вывода в лог
    access_ssh_data_log = {'host': config['ssh_host'], 'user': config['ssh_login'], 'port': config['ssh_port'], 'password': '*скрыт*'}
    logger.info(f'Attempt to connect to the server via SSH using data: {access_ssh_data_log}')
    # created_backups = []  # Множество названий проектов с флагом "L", для которых есть новая версия бэкапа
    try:
        # Создаём соединение
        client_copy_arch.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client_copy_arch.connect(hostname=config['ssh_host'],
                                username=config['ssh_login'],
                                password=config['ssh_password'],
                                port=int(config['ssh_port']))
    except Exception as e:
        logger.critical(f'SSH error server connecting! {e}')
        logger.info('-------DATABASE BACKUP FINISH WITH ERROR-------')
        client_copy_arch.close()
        handlers = logger.handlers[:]
        for handler in handlers:
            logger.removeHandler(handler)
            handler.close()
        if flag == 'manual':
            return
        else:
            sys.exit()

    # Цикл, перебирающий базы данных для копирования
    logger.info(f'SSH connection to server successful')
    logger.info(f'Starting a database backup on the server ({len(db_names)}): {db_names}')
    for database in db_names:
        if EOFFlag:
            client_copy_arch.close()
            handlers = logger.handlers[:]
            for handler in handlers:
                logger.removeHandler(handler)
                handler.close()
            break

        try:
            # Создаём список БД
            stdin, stdout, stderr = client_copy_arch.exec_command(f'mkdir -p {config["path_to_server_backups"].strip("/")}/database; cp {database} /{config["path_to_server_backups"].strip("/")}/database/{cur_datetime}_db_{database}')
            exit_status = stdout.channel.recv_exit_status()
        except Exception as e:
            logger.critical(f'Database backup error {database}! {e}')
            logger.info('-------DATABASE BACKUP FINISH WITH ERROR-------')
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

    logger.info(f'Database backups successfully created on the server')
    logger.info(f'Start archiving database backups on the server')
    # Цикл, перебирающий базы данных для архивирования на сервере
    for database in db_names:
        if EOFFlag:
            client_copy_arch.close()
            handlers = logger.handlers[:]
            for handler in handlers:
                logger.removeHandler(handler)
                handler.close()
            break
        # Архивируем файл с бэкапом и удаляем исходник
        try:
            stdin, stdout, stderr = client_copy_arch.exec_command(f'cd ../{config["path_to_server_backups"].strip("/")}/database; tar -czf {cur_datetime}_db_{database.replace(".sql", ".tar.gz")} {cur_datetime}_db_{database}; rm {cur_datetime}_db_{database}')
            exit_status = stdout.channel.recv_exit_status()
        except Exception as e:
            logger.critical(f'Backup file backup error! {e}')
            logger.info('-------DATABASE BACKUP FINISH WITH ERROR-------')
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

    logger.info(f'Database backups successfully archived on the server')

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
            if f'/{config["path_to_server_backups"].strip("/")}/database' not in server_dow.nlst(f'/{config["path_to_server_backups"].strip("/")}'):
                server_dow.mkd(f'/{config["path_to_server_backups"].strip("/")}/database')
            server_dow.cwd(f'/{config["path_to_server_backups"].strip("/")}')
        except Exception as e:
            logger.critical(f'FTP server connection error! {e}')
            logger.info('-------DATABASE BACKUP FINISH WITH ERROR-------')
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
        logger.info(f'Start downloading database backups to a local PC')
        if not os.path.isdir(f'{config["path_to_local_backups"]}/database'):
            os.makedirs(f'{config["path_to_local_backups"]}/database')
        # Цикл, перебирающий базы данных для скачивания на локальный ПК
        for database in db_names:
            if EOFFlag:
                client_copy_arch.close()
                handlers = logger.handlers[:]
                for handler in handlers:
                    logger.removeHandler(handler)
                    handler.close()
                break
            with open(f'{config["path_to_local_backups"]}/database/{cur_datetime}_db_{database.replace(".sql", ".tar.gz")}', 'wb') as my_file:
                server_dow.retrbinary('RETR ' + f'{config["path_to_server_backups"]}/database/{cur_datetime}_db_{database.replace(".sql", ".tar.gz")}', my_file.write, 1024)
        server_dow.quit()
        logger.info(f'Database backups successfully downloaded to local PC')

        if EOFFlag:
            client_copy_arch.close()
            handlers = logger.handlers[:]
            for handler in handlers:
                logger.removeHandler(handler)
                handler.close()
            return

        unbroken_backups = [] # Бэкапы, скаченные с неправильным размером (нецельные)
        broken_backups = [] # Бэкапы, скаченные с правильным размером (цельные)
        for database in db_names:
            # Сравниваем размеры бэкапов на сервере и локальном ПК (проверка на целосность)
            s_size_stdin, s_size_stdout, s_size_stderr = client_copy_arch.exec_command(f'cd ../{config["path_to_server_backups"]}/database; stat --printf="%s" {cur_datetime}_db_{database.replace(".sql", ".tar.gz")}')
            exit_status = s_size_stdout.channel.recv_exit_status()
            server_stat_size = int(s_size_stdout.read().decode('utf-8').strip('\n').split('\n')[0]) # Размер файла на сервере
            local_stat_size = int(os.stat(f'{config["path_to_local_backups"]}/database/{cur_datetime}_db_{database.replace(".sql", ".tar.gz")}').st_size) # Размер файла на локальном ПК

            if server_stat_size != local_stat_size:
                broken_backups.append(database)
            else:
                unbroken_backups.append(database)

        if EOFFlag:
            client_copy_arch.close()
            handlers = logger.handlers[:]
            for handler in handlers:
                logger.removeHandler(handler)
                handler.close()
            return

        if len(broken_backups) > 0:
            logger.warning(f'Database backup size mismatch, in total: {len(broken_backups)}, {broken_backups}')

        actual_value = {(db, cur_datetime) for db in unbroken_backups}
        actual_value_dbs = unbroken_backups

    else:
        # # Записываем в json-файл актуальные значения по проектам/бэкапам
        actual_value = {(db, cur_datetime) for db in db_names}
        actual_value_dbs = db_names

    if del_file:
        # Удаляем файлы бэкапов на сервере, если таковая опция включена
        logger.info(f'Start deleting database backups on the server')
        for database in db_names:
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
                    f'cd ../{config["path_to_server_backups"].strip("/")}/database; rm {cur_datetime}_db_{database.replace(".sql", ".tar.gz")}')
                exit_status = stdout.channel.recv_exit_status()
            except Exception as e:
                logger.critical(f'Error deleting backup file! {e}')
                logger.info('-------DATABASE BACKUP FINISH WITH ERROR-------')
                client_copy_arch.close()
                handlers = logger.handlers[:]
                for handler in handlers:
                    logger.removeHandler(handler)
                    handler.close()
                if flag == 'manual':
                    break
                else:
                    sys.exit()
        logger.info(f'Database backups successfully deleted on the server')

    json_adder(actual_value, 'backups_create')
    json_adder(actual_value_dbs, 'latest_dbs')
    # Закрываем SSH соединение
    client_copy_arch.close()
    logger.info('-------DATA BACKUP FINISH-------')
        # logger.info(f'Начало сборки и сохранения данных о содержимом бэкапа БД {database}')

        # # Формальности и запись данных о произведённом бэкапе в БД
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
        #     logger.info(f'Данные о содержимом бэкапа БД {database} успешно собраны и сохранены')
        # except Exception as e:
        #     logger.critical(f'Ошибка выполнения запроса к серверу по FTP! {e}')
        #     logger.info('-------ФИНИШ БЭКАПА БАЗ ДАННЫХ С ОШИБКОЙ-------')
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





