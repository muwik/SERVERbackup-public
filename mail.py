import os
import sys
import json
import base64
import logging
import memcache
import requests
from hashlib import md5
from datetime import datetime

# Встроенный логгер от SendPulse (логи выходят в консоль, не используются)
logger = logging.getLogger(__name__)
logger.propagate = False
ch = logging.StreamHandler()
ch.setFormatter(logging.Formatter('%(levelname)-8s [%(asctime)s]  %(message)s'))
logger.addHandler(ch)

def resource_path(relative_path):
    # Преобразование путей ресурсов в пригодный для использования формат для PyInstaller
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath('.'), relative_path)

class PySendPulse:
    """ SendPulse REST API python wrapper
    """
    __api_url = "https://api.sendpulse.com"
    __user_id = None
    __secret = None
    __token = None
    __token_file_path = ""
    __token_hash_name = None
    __storage_type = "FILE"
    __refresh_token = 0
    __memcached_host = "127.0.0.1:11211"

    MEMCACHED_VALUE_TIMEOUT = 3600
    ALLOWED_STORAGE_TYPES = ['FILE', 'MEMCACHED']

    def __init__(self, user_id, secret, storage_type="FILE", token_file_path="", memcached_host="127.0.0.1:11211"):
        """ SendPulse API constructor

        @param user_id: string REST API ID from SendPulse settings
        @param secret: string REST API Secret from SendPulse settings
        @param storage_type: string FILE|MEMCACHED
        @param memcached_host: string Host for Memcached server, default is 127.0.0.1:11211
        @raise: Exception empty credentials or get token failed
        """
        logger.info("Initialization SendPulse REST API Class")
        if not user_id or not secret:
            raise Exception("Empty ID or SECRET")

        self.__user_id = user_id
        self.__secret = secret
        self.__storage_type = storage_type.upper()
        self.__token_file_path = token_file_path
        self.__memcached_host = memcached_host
        m = md5()
        m.update("{}::{}".format(user_id, secret).encode('utf-8'))
        self.__token_hash_name = m.hexdigest()
        if self.__storage_type not in self.ALLOWED_STORAGE_TYPES:
            logger.warning("Wrong storage type '{}'. Allowed storage types are: {}".format(storage_type, self.ALLOWED_STORAGE_TYPES))
            logger.warning("Try to use 'FILE' instead.")
            self.__storage_type = 'FILE'
        logger.debug("Try to get security token from '{}'".format(self.__storage_type, ))
        if self.__storage_type == "MEMCACHED":
            mc = memcache.Client([self.__memcached_host])
            self.__token = mc.get(self.__token_hash_name)
        else:  # file
            filepath = "{}{}".format(self.__token_file_path, self.__token_hash_name)
            if os.path.isfile(filepath):
                with open(filepath, 'rb') as f:
                    self.__token = f.readline()

            else:
                logger.error("Can't find file '{}' to read security token.".format(filepath))
        logger.debug("Got: '{}'".format(self.__token, ))
        if not self.__token and not self.__get_token():
            raise Exception("Could not connect to API. Please, check your ID and SECRET")

    def __get_token(self):
        """ Get new token from API server and store it in storage
        @return: boolean
        """
        logger.debug("Try to get new token from server")
        self.__refresh_token += 1
        data = {
            "grant_type": "client_credentials",
            "client_id": self.__user_id,
            "client_secret": self.__secret,
        }
        response = self.__send_request("oauth/access_token", "POST", data, False)
        if response.status_code != 200:
            return False
        self.__refresh_token = 0
        self.__token = response.json()['access_token']
        logger.debug("Got: '{}'".format(self.__token, ))
        if self.__storage_type == "MEMCACHED":
            logger.debug("Try to set token '{}' into 'MEMCACHED'".format(self.__token, ))
            mc = memcache.Client([self.__memcached_host])
            mc.set(self.__token_hash_name, self.__token, self.MEMCACHED_VALUE_TIMEOUT)
        else:
            filepath = "{}{}".format(self.__token_file_path, self.__token_hash_name)
            try:
                if not os.path.isdir(self.__token_file_path):
                    os.makedirs(self.__token_file_path, exist_ok=True)

                with open(filepath, 'w') as f:
                    f.write(self.__token)
                    logger.debug("Set token '{}' into 'FILE' '{}'".format(self.__token, filepath))
            except IOError:
                logger.warning("Can't create 'FILE' to store security token. Please, check your settings.")
        if self.__token:
            return True
        return False

    def __send_request(self, path, method="GET", params=None, use_token=True, use_json_content_type=False):
        """ Form and send request to API service

        @param path: sring what API url need to call
        @param method: HTTP method GET|POST|PUT|DELETE
        @param params: dict argument need to send to server
        @param use_token: boolean need to use token or not
        @param use_json_content_type: boolean need to convert params data to json or not
        @return: HTTP requests library object http://www.python-requests.org/
        """
        url = "{}/{}".format(self.__api_url, path)
        method.upper()
        logger.debug("__send_request method: {} url: '{}' with parameters: {}".format(method, url, params))
        if type(params) not in (dict, list):
            params = {}
        if use_token and self.__token:
            headers = {'Authorization': 'Bearer {}'.format(self.__token)}
        else:
            headers = {}
        if use_json_content_type and params:
            headers['Content-Type'] = 'application/json'
            params = json.dumps(params)

        if method == "POST":
            response = requests.post(url, headers=headers, data=params)
        elif method == "PUT":
            response = requests.put(url, headers=headers, data=params)
        elif method == "DELETE":
            response = requests.delete(url, headers=headers, data=params)
        else:
            response = requests.get(url, headers=headers, params=params)
        if response.status_code == 401 and self.__refresh_token == 0:
            self.__get_token()
            return self.__send_request(path, method, params)
        elif response.status_code == 404:
            logger.warning("404: Sorry, the page you are looking for could not be found.")
            logger.debug("Raw_server_response: {}".format(response.text, ))
        elif response.status_code == 500:
            logger.critical("Whoops, looks like something went wrong on the server. Please contact with out support tech@sendpulse.com.")
        else:
            try:
                logger.debug("Request response: {}".format(response.json(), ))
            except:
                logger.critical("Raw server response: {}".format(response.text, ))
        return response

    def __handle_result(self, data):
        """ Process request results

        @param data:
        @return: dictionary with response message and/or http code
        """
        if 'status_code' not in data:
            if data.status_code == 200:
                logger.debug("Hanle result: {}".format(data.json(), ))
                return data.json()
            elif data.status_code == 404:
                response = {
                    'is_error': True,
                    'http_code': data.status_code,
                    'message': "Sorry, the page you are looking for {} could not be found.".format(data.url, )
                }
            elif data.status_code == 500:
                response = {
                    'is_error': True,
                    'http_code': data.status_code,
                    'message': "Whoops, looks like something went wrong on the server. Please contact with out support tech@sendpulse.com."
                }
            else:
                response = {
                    'is_error': True,
                    'http_code': data.status_code
                }
                response.update(data.json())
        else:
            response = {
                'is_error': True,
                'http_code': data
            }
        logger.debug("Hanle result: {}".format(response, ))
        return {'data': response}

    def __handle_error(self, custom_message=None):
        """ Process request errors

        @param custom_message:
        @return: dictionary with response custom error message and/or error code
        """
        message = {'is_error': True}
        if custom_message is not None:
            message['message'] = custom_message
        logger.error("Hanle error: {}".format(message, ))
        print(message)
        return message

    def smtp_send_mail(self, email):
        """ SMTP: send email

        @param email: string valid email address. We will send an email message to the specified email address with a verification link.
        @return: dictionary with response message
        """
        logger.info("Function call: smtp_send_mail")
        if (not email.get('html') or not email.get('text')) and not email.get('template'):
            return self.__handle_error('Seems we have empty body')
        elif not email.get('subject'):
            return self.__handle_error('Seems we have empty subject')
        elif not email.get('from') or not email.get('to'):
            return self.__handle_error(
                "Seems we have empty some credentials 'from': '{}' or 'to': '{}' fields".format(email.get('from'),
                                                                                                email.get('to')))
        email['html'] = base64.b64encode(email.get('html').encode('utf-8')).decode('utf-8') if email['html'] else None
        return self.__handle_result(self.__send_request('smtp/emails', 'POST', {'email': json.dumps(email)}))

def run(test=False):
    # Функция запуска отправки письма
    config_file = open(resource_path("settings.json"), 'r')
    config = json.load(config_file)  # json-файл конфигурации
    config_file.close()
    SPApiProxy = PySendPulse(user_id=config['mail_user_id'], secret=config['mail_user_secret'], storage_type='memcached')

    # HTML-шаблон
    template_file = open(resource_path("templates/SUSLIK-mail.html"), 'r')
    template = template_file.read()
    template_file.close()

    if not test:
        logs_file = open(config['path_to_local_backups'] + "/logs/" + config['latest_run'] + ".log", 'r') # Файл логов
    else:
        logs_file = ''

    # Сценарий для тестового письма и письма при возникновении ошибки
    if not test:
        content = logs_file.read()
        header_right = config['latest_run'] # Элемент в правом верхнем углу хеадера
        subject = f'IHostBackup - Backup execution error {config["latest_run"]}'
        sub_list = content.split('\n')

        # Окрашиваем абзац лога, если в нём есть ошибка
        for i, sentence in enumerate(sub_list):
            if 'WARNING' in sentence:
                sub_list[i] = '<font style="color:Orange;">' + sentence + '</font>'
            elif 'ERROR' in sentence:
                sub_list[i] = '<font style="color:OrangeRed;">' + sentence + '</font>'
            elif 'CRITICAL' in sentence:
                sub_list[i] = '<font style="color:Crimson;">' + sentence + '</font>'
            else:
                pass
        content = '<br>'.join(sub_list) # Соединяем логи, уже с HTML-переносом строки (тег <br>)
        logs_file.close()
    else:
        content = 'This is a test message sent by IHostBaclup desktop application.'
        header_right = 'ТЕSТ-ТЕSТ-ТЕSТ!'
        subject = f'IHostBackup - Email sending test {datetime.now().strftime(config["dateFormat"])}'
    template = template.replace('{DATE_HERE}', header_right).replace('{CONTENT_HERE}', content)
    email = {
        'subject': subject,
        'html': template,
        'text': template,
        'from': {'name': 'SUSLIK', 'email': config['mail_email']},
        'to': [
            {'name': config["report_email"].split('@')[0], 'email': config["report_email"]}
        ]
    }
    SPApiProxy.smtp_send_mail(email)

def diag():
    # Диагностика, тест ID и Secret`a, получение токена
    config_file = open(resource_path("settings.json"), 'r')
    config = json.load(config_file)  # json-файл конфигурации
    config_file.close()
    PySendPulse(user_id=config['mail_user_id'], secret=config['mail_user_secret'], storage_type='memcached') # Запрос на получение токена
