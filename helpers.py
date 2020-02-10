import sys
import io
import logging
import os.path
import csv
import subprocess
import random
import time
import configparser
import datetime
import json
import traceback
from logging.handlers import RotatingFileHandler
from collections import OrderedDict

def getFile(fileName):
    if not os.path.isfile(fileName):
        return ""

    f = open(fileName, "r")
    return f.read()


def getLines(fileName):
    if not os.path.isfile(fileName):
        return []

    with open(fileName) as f:
        return f.readlines()


def toFile(s, fileName):
    with io.open(fileName, "w", encoding="utf-8") as text_file:
        print(s, file=text_file)


def appendToFile(s, fileName):
    with io.open(fileName, "a", encoding="utf-8") as text_file:
        print(s, file=text_file)

def toBinaryFile(s, fileName):
    with io.open(fileName, "wb") as file:
        file.write(s)

def getJsonFile(fileName):
    result = {}

    try:
        import json

        file = getFile(fileName)

        if not file:
            return result

        result = json.loads(file)
    except Exception as e:
        handleException(e)

    return result

def get(item, key):
    if not item:
        return ''

    result = item.get(key, '')

    # to avoid null values
    if not result and result != 0:
        result = ''

    return result

def numbersOnly(s):
    return ''.join(filter(lambda x: x.isdigit(), s))

def fixedDecimals(n, numberOfDecimalPlaces):
    result = ''

    try:
        formatString = f'{{:.{numberOfDecimalPlaces}f}}'

        result = formatString.format(n)
    except Exception as e:
        logging.error(e)

    return result

def findBetween(s, first, last, strict=False):
    start = 0

    if strict and first and not first in s:
        return ''

    if first and first in s:
        start = s.index(first) + len(first)

    end = len(s)

    if strict and last and not last in s[start:]:
        return ''

    if last and last in s[start:]:
        end = s.index(last, start)

    return s[start:end]

def getNested(j, keys):
    result = ''

    try:
        element = j

        i = 0

        for key in keys:
            if not element:
                break

            # might be an integer index
            if isinstance(key, str) and not key in element:
                break

            if isinstance(key, int):
                if not isinstance(element, list):
                    break
                
                if key < 0 or key >= len(element):
                    break

            element = element[key]

            if i == len(keys) - 1:
                return element

            i += 1
    except:
        return ''

    return result

def stringToFloatingPoint(s):
    result = 0.0

    temporary = ""

    for c in s:
        if c.isdigit() or c == ".":
            temporary += c

    try:
        result = float(temporary)
    except:
        result = 0.0

    return result

def getCsvFile(fileName):
    result = []

    with open('input.csv') as inputFile:
        csvReader = csv.reader(inputFile, delimiter=',')
            
        # skip the headers
        next(csvReader, None)

        for row in csvReader:
            if len(row) == 0:
                continue

            result.append(row)

    return result

def getCsvFileAsDictionary(fileName):
    result = []

    with open(fileName) as inputFile:
        csvReader = csv.DictReader(inputFile, delimiter=',')
            
        for row in csvReader:
            if len(row) == 0:
                continue

            result.append(row)

    return result

def makeDirectory(directoryName):
    if not os.path.exists(directoryName):
        os.mkdir(directoryName)


def run(command, wait=True):
    try:
        line = ' '.join(command)
        
        logging.info(f'Running {line}')

        if wait:
            return subprocess.run(command)
        else:
            return subprocess.Popen(command, shell=True)
    except Exception as e:
        logging.error(e)

def getStandardOutput(command):
    try:
        result = subprocess.run(command, stdout=subprocess.PIPE)
    except Exception as e:
        logging.error(e)
        return ''
    
    return result.stdout.decode('utf-8')

def runWithInput(command, input):
    try:
        result = subprocess.run(command, input=input, encoding='ascii')
    except Exception as e:
        logging.error(e)
        return None

    return result

def getUrl(url):
    response = ''

    try:
        import requests
        response = requests.get(url)
    except Exception as e:
        logging.error(e)
        return ''
        
    return response.text

def sleep(seconds):
    time.sleep(int(seconds))

def setOptions(fileName, options):
    try:
        if '--optionsFile' in sys.argv:
            index = sys.argv.index('--optionsFile')
            if index < len(sys.argv):
                fileName = sys.argv[index + 1]

        optionsReader = configparser.ConfigParser()
        optionsReader.read(fileName)

        if not 'main' in optionsReader:
            return

        for key in options:
            if key in optionsReader['main']:
                if optionsReader['main'][key].isdigit():
                    options[key] = int(optionsReader['main'][key])
                else:
                    options[key] = optionsReader['main'][key]
    except Exception as e:
        logging.error(e)

def timeAgo(time=False):
    """
    Get a datetime object or a int() Epoch timestamp and return a
    pretty string like 'an hour ago', 'Yesterday', '3 months ago',
    'just now', etc
    """
    diff = 0

    now = datetime.now()
    if type(time) is float:
        diff = now - datetime.fromtimestamp(time)
    elif isinstance(time,datetime):
        diff = now - time
    elif not time:
        diff = now - now
    second_diff = diff.seconds
    day_diff = diff.days

    if day_diff < 0:
        return ''

    if day_diff == 0:
        if second_diff < 10:
            return "just now"
        if second_diff < 60:
            return str(second_diff) + " seconds ago"
        if second_diff < 120:
            return "a minute ago"
        if second_diff < 3600:
            return str(second_diff / 60) + " minutes ago"
        if second_diff < 7200:
            return "an hour ago"
        if second_diff < 86400:
            return str(second_diff / 3600) + " hours ago"
    if day_diff == 1:
        return "Yesterday"
    if day_diff < 7:
        return str(day_diff) + " days ago"
    if day_diff < 31:
        return str(day_diff / 7) + " weeks ago"
    if day_diff < 365:
        return str(day_diff / 30) + " months ago"
    return str(day_diff / 365) + " years ago"

def fileNameOnly(fileName, includeExtension):
    result = os.path.basename(fileName)

    if not includeExtension:
        result = os.path.splitext(result)[0]

    return result

def addToStartup(fileName):
    import getpass
    
    userName = getpass.getuser()

    directoryName = os.path.abspath(fileName)
    directoryName = os.path.dirname(directoryName)

    batFileName = fileNameOnly(fileName, False) + '.bat'
    
    # uses same file name twice
    startupScriptFileName = os.path.join(directoryName, batFileName)

    batPath = r'C:\Users\%s\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup' % userName
    
    with open(batPath + '\\' + batFileName, 'w+') as file:
        file.write(os.path.splitdrive(directoryName)[0] + '\n')
        file.write('cd ' + directoryName + '\n')
        file.write(r'start /min %s' % startupScriptFileName)

def setUpLogging():
    logFormatter = logging.Formatter('[%(asctime)s] [%(levelname)s] %(message)s', '%Y-%m-%d %H:%M:%S')
    rootLogger = logging.getLogger()
    rootLogger.setLevel(logging.INFO)

    if '--debug' in sys.argv:
        rootLogger.setLevel(logging.DEBUG)

    consoleHandler = logging.StreamHandler()
    consoleHandler.setFormatter(logFormatter)        
    rootLogger.addHandler(consoleHandler)

    logDirectory = 'logs'

    makeDirectory(logDirectory)

    # 2 rotating files of maximum 1 million bytes each        
    fileHandler = RotatingFileHandler(f'{logDirectory}/log.txt', maxBytes=1000 * 1000, backupCount=1, encoding='utf-8')
    fileHandler.setFormatter(logFormatter)
    rootLogger.addHandler(fileHandler)

def getDateStringSecondsAgo(secondsAgo, useGmTime):
    now = None

    if useGmTime:
        now = datetime.datetime.utcnow()
    else:
        now = datetime.datetime.now()

    result = now - datetime.timedelta(seconds=secondsAgo)
    
    return str(result)

def getDomainName(url):
    result = ''

    from urllib.parse import urlparse
    parsed_uri = urlparse(url)
    location = '{uri.netloc}'.format(uri=parsed_uri)

    fields = location.split('.')

    if len(fields) >= 2:
        result = fields[-2] + '.' + fields[-1]

    return result

class Api:
    def get(self, url):
        import requests

        result = ''

        try:
            logging.debug(f'Get {url}')

            response = requests.get(self.urlPrefix + url, headers=self.headers, proxies=self.proxies, timeout=30)

            result = json.loads(response.text)
        except Exception as e:
            logging.error(e)
            logging.debug(traceback.format_exc())

        return result

    def post(self, url, data):
        import requests
        
        result = ''

        try:
            logging.debug(f'Post {url}')

            response = requests.post(self.urlPrefix + url, headers=self.headers, proxies=self.proxies, data=data, timeout=30)

            result = json.loads(response.text)
        except Exception as e:
            logging.error(e)
            logging.debug(traceback.format_exc())

        return result

    def getBinaryFile(self, url, outputFileName):
        import requests
        
        response = requests.get(url, headers=self.headers, proxies=self.proxies, timeout=30)

        if response and response.content:
            toBinaryFile(response.content, outputFileName)
    
    def setHeadersFromHarFile(self, fileName, urlMustContain):
        try:
            from pathlib import Path
            
            headersList = []
            
            if Path(fileName).suffix == '.har':
                from haralyzer import HarParser
            
                file = getFile(fileName)

                j = json.loads(file)

                har_page = HarParser(har_data=j)

                # find the right url
                for page in har_page.pages:
                    for entry in page.entries:
                        if urlMustContain in entry['request']['url']:
                            headersList = entry['request']['headers']
                            break

            else:
                headersList = getJsonFile(fileName)
                headersList = get(headersList, 'headers')

            headers = []

            for header in headersList:
                name = header.get('name', '')

                # ignore pseudo-headers
                if name.startswith(':'):
                    continue

                if name.lower() == 'content-length' or name.lower() == 'host':
                    continue

                newHeader = (name, header.get('value', ''))

                headers.append(newHeader)

            self.headers = OrderedDict(headers)
        
        except Exception as e:
            handleException(e)

    def __init__(self, urlPrefix):
        self.urlPrefix = urlPrefix

        self.userAgentList = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:71.0) Gecko/20100101 Firefox/71.0"
        ]

        userAgent = random.choice(self.userAgentList)

        self.headers = OrderedDict([
            ('user-agent', userAgent),
            ('accept', 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'),
            ('accept-language', 'en-US,en;q=0.5'),
            ('dnt', '1'),
            ('upgrade-insecure-requests', '1'),
            ('te', 'trailers')
        ])

        self.setHeadersFromHarFile('program/resources/headers.txt', '')

        self.proxies = None
        
def fileNameOnly(fileName, includeExtension):
    result = os.path.basename(fileName)

    if not includeExtension:
        result = os.path.splitext(result)[0]

    return result

def addToStartup(fileName):
    import getpass
    
    userName = getpass.getuser()

    directoryName = os.path.abspath(fileName)
    directoryName = os.path.dirname(directoryName)

    batFileName = fileNameOnly(fileName, False) + '.bat'
    
    # uses same file name twice
    startupScriptFileName = os.path.join(directoryName, batFileName)

    batPath = r'C:\Users\%s\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup' % userName
    
    with open(batPath + '\\' + batFileName, 'w+') as file:
        file.write(os.path.splitdrive(directoryName)[0] + '\n')
        file.write('cd ' + directoryName + '\n')
        file.write(r'start /min %s' % startupScriptFileName)