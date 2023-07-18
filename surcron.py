import os
import sys
import json
from crontab import CronTab
from datetime import datetime

def resource_path(relative_path):
    # Преобразование путей ресурсов в пригодный для использования формат для PyInstaller
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath('.'), relative_path)

def __json_adder(data):
    # Изменяем значение последнего изменение параметров CRON'a
    json_file = open(resource_path("settings.json"), "r+", encoding='utf8')
    db_data = json.load(json_file)
    db_data["cron_last_schedule"] = data
    db_data["cron_schedule_time"] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    json_file.seek(0)
    json.dump(db_data, json_file, ensure_ascii=False, indent=4)
    json_file.truncate()
    json_file.close()

def __show_cron():
    # Вывести все задания CRON (не используется)
    surokcron = CronTab(user=True)
    for job in surokcron:
        print(job)

def create_cron(path_to_app):
    # Создаём задание CRON
    config_file = open(resource_path("settings.json"), 'r')
    config = json.load(config_file)  # json-файл конфигурации
    config_file.close()
    surokcron = CronTab(user=True)
    path_to_app = path_to_app.replace('/Contents/MacOS/surokGUI.py', '') # Удаление части пути, внутри пакета приложения (.app)
    bckp_job = surokcron.new(command=f'killall {str(path_to_app).split("/")[-1].replace(".app", "")} ; open {path_to_app} --args CRON', comment='surok_unique_cron') # !!! - КОМАНДА - !!!
    dow_stencil = {"Понедельник": '1', "Вторник": '2', "Среда": '3', "Четверг": '4', "Пятница": '5', "Суббота": '6', "Воскресенье": '0'} # "Лекало" для получения правильного числа для конфигурации задания CRON

    # Проверка частоты установки CRON`a
    if config['cron_mode'] != "Еженедельно":
        expression = f"{config['cron_minute']} {config['cron_hour']} * * *"
        bckp_job.setall(expression)
        __json_adder(expression)
    else:
        expression = f"{config['cron_minute']} {config['cron_hour']} * * {dow_stencil[config['cron_dow']]}"
        bckp_job.setall(expression)
        __json_adder(expression)

    surokcron.write() # Сохранить изменения

def find_cron():
    # Найти задание крон по уникальному комментарию от SUROK
    surokcron = CronTab(user=True)
    found_job = surokcron.find_comment('surok_unique_cron')
    return found_job

def remove_cron():
    # Удалить задание CRON
    if list(find_cron()):
        surokcron = CronTab(user=True)
        found_job = find_cron()
        surokcron.remove(found_job)
        surokcron.write() # Сохранить изменения