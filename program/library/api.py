import sys
import logging
import os.path
import random
import json
import urllib.parse

from collections import OrderedDict

from . import helpers

from .helpers import get

class Api:
    def get(self, url, parameters=None, responseIsJson=True, returnResponseObject=False, requestType=None):
        import requests

        result = ''

        if responseIsJson:
            result = {}

        try:
            self.log.debug(f'Get {url}')

            verify = True
            
            fileName = ''
            
            if '--debug' in sys.argv:
                self.log.debug(f'Request headers: {self.headers}')

                if self.proxies and 'localhost:' in self.proxies.get('http', ''):
                    verify = False

                fileName = self.getCacheFileName(url, parameters, responseIsJson)

                if not returnResponseObject and not '--noCache' in sys.argv and os.path.exists(fileName):
                    self.log.debug('Using cached version')
                    result = helpers.getFile(fileName)

                    if responseIsJson:
                        return json.loads(result)
                    else:
                        return result

            if requestType == 'DELETE':
                response = requests.delete(self.urlPrefix + url, params=parameters, headers=self.headers, proxies=self.proxies, timeout=self.timeout, verify=verify)
            else:
                response = requests.get(self.urlPrefix + url, params=parameters, headers=self.headers, proxies=self.proxies, timeout=self.timeout, verify=verify)

            self.handleResponseLog(url, parameters, response, fileName)
            
            if returnResponseObject:
                result = response
            elif responseIsJson:
                result = json.loads(response.text)
            else:
                result = response.text
        
        except Exception as e:
            if 'Max retries exceeded with url' in str(e):
                helpers.handleException(e, None, self.log.name, True)
            else:
                helpers.handleException(e, None, self.log.name)
        
        return result

    def getPlain(self, url):
        result = self.get(url, None, False)

        return result

    def getFinalUrl(self, url):
        if not url:
            return ''

        response = self.get(url, None, False, returnResponseObject=True)

        if not response:
            return ''

        result = response.url

        # because the protocol can change in the above steps
        if helpers.findBetween(result, '://', '') == helpers.findBetween(url, '://', ''):
            # for javascript redirects
            redirect = helpers.findBetween(response.text, 'location.replace("', '")', strict=True)
            
            if redirect:
                result = redirect.replace(r'\/', '/')

        return result

    def post(self, url, data, responseIsJson=True):
        import requests
        
        result = {}

        if not responseIsJson:
            result = ''

        try:
            self.log.debug(f'Post {url}')

            verify = True
            
            fileName = ''
            
            if '--debug' in sys.argv:
                self.log.debug(f'Request headers: {self.headers}')
                self.log.debug(f'Request body: {data}')
                
                if self.proxies and 'localhost:' in self.proxies.get('http', ''):
                    verify = False
                
                # don't want to read files for post, just write them
                fileName = self.getCacheFileName(url, {}, responseIsJson)

            response = requests.post(self.urlPrefix + url, headers=self.headers, proxies=self.proxies, data=data, timeout=self.timeout, verify=verify)

            self.handleResponseLog(url, {}, response, fileName)

            if responseIsJson:
                result = json.loads(response.text)
            else:
                result = response.text
        except Exception as e:
            helpers.handleException(e)

        return result

    def downloadBinaryFile(self, url, destinationFileName):       
        result = False
        
        import wget
        
        self.log.debug(f'Download {url} to {destinationFileName}')
        
        try:
            wget.download(url, destinationFileName)
            result = True
        except Exception as e:
            self.log.error(e)
        
        return result

    def handleResponseLog(self, url, parameters, response, fileName):
        if not response:
            self.log.debug(f'Something went wrong with the response. Response: {response}.')
            return
                
        self.log.debug(f'Response headers: {response.headers}')

        if response.text != None:
            self.log.debug(f'Response: {response.text[0:500]}...')
               
        if '--debug' in sys.argv and ('maps.google' in self.urlPrefix and 'INVALID_REQUEST' in response.text):
            return

        if '--debug' in sys.argv:
            parameterString = ''

            if parameters:
                parameterString += '?' + urllib.parse.urlencode(parameters)
            
            helpers.toBinaryFile(response.content, fileName)

            # avoid duplicates when using returnResponseObject
            if not f' {self.urlPrefix}{url}{parameterString}' in helpers.getFile('user-data/logs/cache.txt'):
                helpers.appendToFile(f'{fileName} {self.urlPrefix}{url}{parameterString}', 'user-data/logs/cache.txt')
        # normal log
        else:
            number = '{:02d}'.format(self.requestIndex)
            
            helpers.makeDirectory('user-data/logs/cache')

            fileName = f'user-data/logs/cache/{helpers.lettersAndNumbersOnly(self.urlPrefix)}-{number}.json'
            
            self.requestIndex += 1

            if self.requestIndex >= 100:
                self.requestIndex = 0

            self.log.debug(f'Writing response to {fileName}')
            helpers.toBinaryFile(response.content, fileName)

    def getCacheFileName(self, url, parameters, responseIsJson):
        result = ''

        file = helpers.getFile('user-data/logs/cache.txt')

        urlToFind = self.urlPrefix + url
       
        if parameters:
            urlToFind += '?' + urllib.parse.urlencode(parameters)

        for line in file.splitlines():
            fileName = helpers.findBetween(line, '', ' ')
            lineUrl = helpers.findBetween(line, ' ', '')

            if lineUrl == urlToFind:
                result = fileName
                break

        if not result:
            fileName = helpers.lettersAndNumbersOnly(url)
            fileName = fileName[0:25]
            
            for i in range(0, 16):  
                fileName += str(random.randrange(0, 10))
            
            extension = 'json'

            if not responseIsJson:
                extension = 'html'

            result = f'user-data/logs/cache/{fileName}.{extension}'

        helpers.makeDirectory('user-data/logs/cache')

        return result

    def getHeadersFromTextFile(self, fileName):
        result = OrderedDict()

        lines = helpers.getFile(fileName).splitlines()

        list = []
        cookies = []

        foundCookie = False

        for line in lines:
            name = helpers.findBetween(line, '', ': ')
            value = helpers.findBetween(line, ': ', '')

            if name.lower() == 'cookie':
                if not foundCookie:
                    foundCookie = True                    
                else:
                    cookies.append(value)
                    continue
            
            item = (name, value)

            list.append(item)

        if list:
            result = OrderedDict(list)

            if foundCookie and cookies:
                result['cookie'] += '; ' + '; '.join(cookies)

        return result

    def setHeadersFromHarFile(self, fileName, urlMustContain):
        if not os.path.exists(fileName):
            return

        try:
            from pathlib import Path
            
            headersList = []
            
            if Path(fileName).suffix == '.har':
                from haralyzer import HarParser
            
                file = helpers.getFile(fileName)

                j = json.loads(file)

                har_page = HarParser(har_data=j)

                # find the right url
                for page in har_page.pages:
                    for entry in page.entries:
                        if urlMustContain in entry['request']['url']:
                            headersList = entry['request']['headers']
                            break

            else:
                headersList = helpers.getJsonFile(fileName)
                headersList = get(headersList, 'headers')

            headers = []

            for header in headersList:
                name = header.get('name', '')
                value = header.get('value', '')

                # ignore pseudo-headers
                if name.startswith(':'):
                    continue

                if name.lower() == 'content-length' or name.lower() == 'host':
                    continue

                # otherwise response will stay compressed and unreadable
                if name.lower() == 'accept-encoding' and not self.hasBrotli:
                    value = value.replace(', br', '')

                newHeader = (name, value)

                headers.append(newHeader)

            self.headers = OrderedDict(headers)
        
        except Exception as e:
            helpers.handleException(e)

    def getHeadersFromFile(self, fileName):
        file = helpers.getFile(fileName)

        if not file:
            return

        j = json.loads(file)

        newHeaders = []

        for header in j.get('headers', ''):
            name = header.get('name', '')

            # ignore pseudo-headers
            if name.startswith(':'):
                continue

            if name.lower() == 'content-length' or name.lower() == 'host':
                continue

            newHeader = (name, header.get('value', ''))

            newHeaders.append(newHeader)

        return OrderedDict(newHeaders)

    def randomizeHeaders(self):
        number = random.randrange(1, 2)

        self.headers = self.getHeadersFromFile(f'resources/headers-{number}.txt')

    def __init__(self, urlPrefix='', options=None):
        self.urlPrefix = urlPrefix
        self.timeout = 45
        self.requestIndex = 0
        self.log = logging.getLogger(get(options, 'loggerName'))

        self.randomizeHeaders()

        if not self.headers:
            self.userAgentList = [
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/79.0.3945.88 Safari/537.36'
            ]

            userAgent = random.choice(self.userAgentList)

            self.headers = OrderedDict([
                ('user-agent', userAgent),
                ('accept', 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9'),
                ('accept-language', 'en-US,en;q=0.9')
            ])

        self.proxies = None
        self.hasBrotli = True

        try:
            import brotli
        except ImportError as e:
            self.hasBrotli = False
            helpers.handleException(e, 'You should run "pip3 install brotli" or "pip install brotli" first, then restart this script')