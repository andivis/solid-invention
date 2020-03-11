import sys
import json
import logging
import time
import configparser
import urllib
import datetime
import os
import random
import requests
import traceback
import html

# pip packages
import lxml.html as lh

from collections import OrderedDict

import program.library.helpers as helpers

from program.library.database import Database
from program.library.api import Api
from program.library.aws import Aws
from program.library.sendgrid import SendGrid
from program.library.gmail import Gmail

def getFirst(element, xpath, attribute=None):
    result = ''

    elements = element.xpath(xpath)

    if len(elements) > 0:
        if not attribute:
            result = elements[0].text_content()
        else:
            result = elements[0].attrib[attribute]

    return result

def toDollars(s):
    result = helpers.findBetween(s, '$', '.')

    return int(result)

class Downloader:
    def get(self, url):
        userAgent = random.choice(self.userAgentList)
        
        self.headers = OrderedDict([
            ('user-agent', userAgent),
            ('accept', 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'),
            ('accept-language', 'en-US,en;q=0.5'),
            ('dnt', '1'),
            ('upgrade-insecure-requests', '1'),
            ('te', 'trailers')
        ])

        self.proxies = None

        response = ''

        try:
            logging.debug(f'Getting {url}')
            response = requests.get(url, headers=self.headers, proxies=self.proxies)
        except Exception as e:
            response = ''
        
        return response.text

    def __init__(self):
        self.userAgentList = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:71.0) Gecko/20100101 Firefox/71.0"
        ]

class Checkaflip:
    def search(self, onItemIndex, site, item, database):
        keyword = item.get('keyword', '')

        s = '{"instance":"SearchCompleted","slot1":"%s","slot2":true,"slot3":{"instance":"Returns"}}' % (keyword)
        
        body = {
            'json': s
        }

        response = self.api.post('/api', body)

        if not response:
            logging.error('Stopping. Wrong or no response.')            
            return

        # to avoid items that are not what the user wants
        topItems = self.getTopPercentOfItems(response, 50, 'itemCurrentPrice')

        sumOfPrices = float(sum(d['itemCurrentPrice'] for d in topItems))
        averagePrice = sumOfPrices / len(topItems)
        averagePrice = int(round(averagePrice))

        if averagePrice < 1:
            logging.error('Stopping. Wrong or no response.')
            return

        jsonColumn = {
            'averagePrice': response.get('slot1', ''),
            'sellThroughRate': response.get('slot2', '')
        }

        newItem = {
            'siteName': helpers.getDomainName(site),
            'idInWebsite': self.getId(keyword),
            'keyword': item.get('keyword', ''),
            'gmDate': str(datetime.datetime.utcnow()),
            'price': averagePrice,
            'json': json.dumps(jsonColumn)
        }
    
        if newItem['price'] <= 0:
            logging.info('Skipping price is less than or equal to zero')
            return

        sellThroughRate = jsonColumn.get('sellThroughRate', '')
        logging.info(f'Site: checkaflip.com. Keyword: {keyword}. Average price of top 50%: {averagePrice}. Sell through rate: {sellThroughRate}.')

        database.insert('result', newItem)

        # will use it later to filter search results
        return averagePrice

    def getTopPercentOfItems(self, j, percent, keyName):
        result = []

        list = j.get('slot3', '')

        if not list:
            return result

        newList = sorted(list, key=lambda k: k[keyName])

        cutoff = len(newList) * (percent / 100)
        cutoff = int(cutoff)

        result = newList[cutoff:]

        return result

    def getId(self, keyword):
        result = keyword

        now = datetime.datetime.utcnow()
        timeString = now.strftime('%Y-%m-%d')

        result += '-' + timeString

        return result

    def __init__(self, options):
        self.api = Api('http://www.checkaflip.com')

        self.options = options

class Craigslist:
    def getResults(self, site, item, page, database):
        results = []

        document = lh.fromstring(page)

        # get items
        elements = document.xpath("//ul[@class = 'rows']/*")
            
        i = 0
        # get information about each item
        for element in elements:
            i += 1
            
            if 'ban nearby' in element.attrib['class']:
                logging.info("Stopping. Found few local results message.")
                break

            if element.tag != 'li':
                continue

            newItem = {}
    
            newItem['siteName'] = helpers.getDomainName(site)
            newItem['keyword'] = item.get('keyword', '')
            newItem['url'] = getFirst(element, ".//a[contains(@class, 'result-title')]", 'href')
            newItem['name'] = getFirst(element, ".//a[contains(@class, 'result-title')]")
                
            newItem['price'] = getFirst(element, ".//span[contains(@class, 'result-price')]")
            newItem['price'] = toDollars(newItem['price'])
            
            newItem['gmDate'] = str(datetime.datetime.utcnow())

            newItem['idInWebsite'] = self.getId(newItem['url'])

            # avoid duplicates
            if self.isInDatabase(site, newItem, database):
                logging.info('Stopping. Already saw the subsequent results.')
                break

            if newItem['price'] <= 0:
                logging.info('Skipping price is less than or equal to zero')
                continue

            results.append(newItem)

            price = newItem['price']
            name = newItem['name']

            logging.info(f'Results: {len(results)}. Name: {name}. Price: {price}.')

        return results
    
    def search(self, onItemIndex, site, item, database, averageSellingPrice):
        if not averageSellingPrice:
            return

        self.averageSellingPrice = averageSellingPrice
        
        i = 0

        keyword = item.get('keyword', '')

        keywords = urllib.parse.quote_plus(keyword);
        
        minimumPrice = item.get('min price', '')
        minimumPrice = int(minimumPrice)

        # don't want items that cost more than the selling price
        # sss means all for sale
        category = item.get('craigslist category', 'sss')

        minimumProfit = item.get('min profit', 10)
        minimumProfit = int(minimumProfit)

        shipping = item.get('shipping cost', 0)
        shipping = float(shipping)

        priceWant = self.averageSellingPrice - minimumProfit - shipping
        priceWant = int(round(priceWant))

        maximumPrice = priceWant

        if priceWant < minimumPrice:
            minimumPrice = 1

        for city in self.siteInformation['cities']:
            if '--debug' in sys.argv:
                if city.get('url', '') == 'https://albanyga.craigslist.org':
                    logging.info('Stopping')
                    break

            cityName = city.get('name', '');

            logging.info(f'Keyword {onItemIndex}: {keyword}. Site: craigslist. City {i + 1}: {cityName}. Price: {minimumPrice} to {maximumPrice}.')
            i += 1

            urlToGet = city.get('url', '')
            urlToGet += f'/search/{category}?query={keywords}&sort=rel&min_price={minimumPrice}&max_price={maximumPrice}'

            page = self.downloader.get(urlToGet)
            items = self.getResults(site, item, page, database)

            for newItem in items:
                wordMatches = self.passesWordFilters(item, newItem)
                pictureMatches = False
                
                # no point looking these up if words don't match
                if wordMatches:
                    self.email = self.getEmail(newItem, self.document)
                    pictureMatches = self.picturePassesFilters(item, self.document)

                jsonColumn = {
                    'email': self.email,
                    'picture': self.pictureUrl,
                    'picture similarity': '',
                    'things in image': self.thingsInImage
                }

                matches = wordMatches and pictureMatches

                newItem['matches'] = int(matches)
                newItem['json'] = jsonColumn

                # only output to csv/html files if words match
                if wordMatches and (pictureMatches or self.options['onlyOutputPictureMatches'] == 0):
                    self.outputResult(site, item, newItem)

                    url = newItem.get('url', '')
                    name = newItem.get('name', '')
                    price = newItem.get('price', '')

                    self.notify('New result', f'Link: {url}\nKeyword: {keyword}\nTitle: {name}\nPrice: ${price}\n\nCheck the output directory for details. This app will not send any more notifications today.')

                newItem['json'] = json.dumps(newItem['json'])

                # store to database so can skip it next time
                database.insert('result', newItem)     

            self.waitBetween()

    def picturePassesFilters(self, item, document):
        result = False

        pictures = document.xpath("//a[@class = 'thumb']")

        if pictures:
            self.pictureUrl = pictures[0].attrib['href']

        if not self.pictureUrl:
            imageList = helpers.findBetween(self.page, 'var imgList = ', ';\n', True)

            if imageList:
                imageList = json.loads(imageList)

                if imageList:
                    self.pictureUrl = imageList[0].get('url', '')

        if not self.pictureUrl:
            return True

        thingsToFind = item.get('picture must contain one of', '')

        if not thingsToFind:
            return True

        pictureFileName = 'user-data/logs/cache/picture'

        if os.path.exists(pictureFileName):
            os.remove(pictureFileName)
        
        helpers.makeDirectory(os.path.dirname(pictureFileName))

        response = self.api.get(self.pictureUrl, None, False, True)

        helpers.toBinaryFile(response.content, pictureFileName)

        if os.stat(pictureFileName).st_size == 0:
            logging.error(f'Failed to download {self.pictureUrl}')
            return False
        
        self.thingsInImage = self.aws.detect_labels_local_file(pictureFileName)

        minimumConfidence = item.get('picture confidence %', '')

        if minimumConfidence != '':
            minimumConfidence = float(minimumConfidence)

        # show labels
        toLog = []
        
        for thing in self.thingsInImage:
            name = thing.get('Name', '').lower()
            confidence = thing.get('Confidence', 0)
            confidence = helpers.fixedDecimals(confidence, 0)

            toLog.append(f'{name}: {confidence}')

        toLog = ', '.join(toLog)
        logging.info('In picture: ' + toLog)

        for thing in self.thingsInImage:
            name = thing.get('Name', '').lower()
            confidence = thing.get('Confidence', 0)

            nameMatches = False
            
            for toFind in thingsToFind.split(';'):
                if toFind.lower().strip() == name:
                    nameMatches = True
                    break

            if not nameMatches:
                continue

            if confidence < minimumConfidence:
                continue

            self.pictureConfidence = helpers.fixedDecimals(confidence, 0)
            
            result = True

            logging.info(f'The picture contains {name}. Confidence: {self.pictureConfidence}%. Considering it a match.')
            break

        if not result:
            logging.info(f'Skipping. The picture doesn\'t contain any the specified things.')

        return result
    
    def isInDatabase(self, site, newItem, database):
        result = False

        siteName = helpers.getDomainName(site)
        idInWebsite = newItem.get('idInWebsite', '')
        existingItem = database.getFirst('result', '*', f"siteName= '{siteName}' and idInWebsite = '{idInWebsite}'", '', '')

        if existingItem:
            logging.info(f'Skipping. {siteName} ID {idInWebsite} is already in the database.')
            result = True

        return result

    def containsCaseInsensitive(self, listOfPhrases, s):
        result = None

        if not listOfPhrases:
            return result
        
        s = s.lower()

        for item in listOfPhrases:
            if item.lower() in s:
                result = item
                break

        return result

    def passesWordFilters(self, searchItem, resultItem):
        result = False

        self.pictureUrl = ''
        self.email = ''
        self.page = None
        self.document = None
        self.thingsInImage = []
        self.pictureConfidence = ''

        phrasesToFind = searchItem.get('craigslist ad must contain', '')
        phrasesToAvoid = searchItem.get('craigslist ad must not contain', '')

        if not phrasesToFind and not phrasesToAvoid:
            return True

        url = resultItem.get('url', '')
        
        logging.info(f'Seeing if {url} contains at least one of "{phrasesToFind}" and none of "{phrasesToAvoid}"')

        if phrasesToFind:
            phrasesToFind = phrasesToFind.split(';')
        else:
            phrasesToFind = []

        if phrasesToAvoid:
            phrasesToAvoid = phrasesToAvoid.split(';')
        else:
            phrasesToAvoid = []

        containsPhraseToFind = False
        containsPhraseToAvoid = False

        if not phrasesToFind:
            containsPhraseToFind = True

        if not phrasesToAvoid:
            containsPhraseToAvoid = False

        page = self.downloader.get(url)
        self.page = page
        document = lh.fromstring(page)
        self.document = document

        elements = document.xpath("//body")

        if elements:
            # get plain text
            for element in elements[0].findall(".//script"):
                element.getparent().remove(element)
            
            page = elements[0].text_content()

        phraseToFind = self.containsCaseInsensitive(phrasesToFind, page)
        phraseToAvoid = self.containsCaseInsensitive(phrasesToAvoid, page)

        if phraseToFind:
            logging.info(f'It contains a specified phrase: {phraseToFind}')
            containsPhraseToFind = True
        elif phrasesToFind:
            logging.info(f'Skipping. It does not contain at least one of: {phrasesToFind}.')

        if phraseToAvoid:
            logging.info(f'Skipping. It contains a phrase to avoid: {phraseToAvoid}')
            containsPhraseToAvoid = True

        if containsPhraseToFind and not containsPhraseToAvoid:
            logging.info(f'Passed phrase filters')
            result = True
        
        return result

    def getEmail(self, newItem, document):
        url = newItem.get('url', '')
        
        urlToGet = getFirst(document, "//button[contains(@data-href, '/__SERVICE_ID__/')]", 'data-href')

        if not urlToGet:
            return ''
        
        baseOfUrl = helpers.findBetween(url, '', '.org/') + '.org/contactinfo/'

        urlToGet = urlToGet.replace('/__SERVICE_ID__/', baseOfUrl)
        
        response = self.api.post(urlToGet, '')

        string = response.get('replyContent', '')
        string = helpers.findBetween(string, '<a href="', '"')

        if not string:
            return ''

        return string

    def outputResult(self, site, searchItem, newItem):
        helpers.makeDirectory(self.options['outputDirectory'])

        fileName = datetime.datetime.now().strftime('%Y.%m.%d') + ' ' + helpers.lettersNumbersAndSpacesOnly(searchItem.get('keyword', '')) + '.csv'
        fileName = os.path.join(self.options['outputDirectory'], fileName)

        # write headers
        if not os.path.exists(fileName):
            headers = ['date', 'keyword', 'craigslist category', 'matches']

            for site in self.options['sites']:
                siteName = helpers.getDomainName(site)

                headers.append(siteName + ' price')

            headers.append('profit')
            headers.append('picture confidence %')
            headers.append('url')
            headers.append('email')
            headers.append('picture')

            line = ','.join(headers)

            helpers.toFile(line, fileName)
            helpers.toFile(line, fileName + '-backup.csv')

        keyword = searchItem.get('keyword', '')

        now = datetime.datetime.utcnow()
        today = now.strftime('%Y-%m-%d')

        siteName = helpers.getDomainName(site)
        fields = [today, keyword, searchItem.get('craigslist category', '')]

        fields.append(str(newItem.get('matches', '')))

        fields.append(str(self.averageSellingPrice))
        fields.append(str(newItem.get('price', '')))

        revenue = self.averageSellingPrice 
        costs = newItem.get('price', '') + float(searchItem.get('shipping cost', 0))
        
        profit = revenue - costs
        profit = int(round(profit))
        
        fields.append(str(profit))
        
        fields.append(self.pictureConfidence)
        
        fields.append(newItem.get('url', ''))
        
        fields.append(helpers.getNested(newItem, ['json', 'email']))
        fields.append(helpers.getNested(newItem, ['json', 'picture']))

        line = ','.join(fields)
    
        helpers.appendToFile(line, fileName)
        helpers.appendToFile(line, fileName + '-backup.csv')

        self.csvToHtml(fileName)

    def csvToHtml(self, fileName):
        csv = helpers.getCsvFile(fileName)

        file = helpers.getFile('program/resources/style.html')

        file += '<table>\n'
        file += '    <thead>\n'

        isFirstRow = True

        for row in csv:
            if not row.get('picture', ''):
                continue

            file += f'        <tr>\n'

            if isFirstRow:
                tag = 'th'

                for column in row:
                    file += f'            <{tag}>{column}</{tag}>\n'

                isFirstRow = False
                
                file += '        </tr>\n'
                file += '    </thead>\n'
                file += '    <tbody>\n'
                file += '        <tr>\n'
            
            for column in row:

                if column == 'url':
                    row[column] = f'<a href="{row[column]}">{row[column]}</a>'
                elif column == 'email':
                    shortUrl = helpers.findBetween(row[column], 'mailto:', '?')
                    
                    row[column] = f'<a href="{row[column]}">{shortUrl}</a>'
                elif column == 'picture':
                    row[column] = f'<a href="{row[column]}"><img src="{row[column]}"/></a>'
                else:
                    row[column] = html.escape(row[column], quote=False)

                tag = 'td'
                
                file += f'            <{tag}>{row[column]}</{tag}>\n'

            file += '        </tr>\n'

        file += '    </tbody>\n'
        file += '</table>'

        # Save to file
        htmlFileName = helpers.fileNameOnly(fileName, False) + '.html'
        htmlFileName = self.options['outputDirectory'] + '/' + htmlFileName
        helpers.toFile(file, htmlFileName)

    def notify(self, subject, message):
        if self.hasNotified:
            return

        logging.info(message)

        if self.emailer:
            emailMessage = message.replace('\n', '<br>\n')
            self.emailer.sendEmail(self.options['fromEmailAddress'], self.options['toEmailAddress'], subject, emailMessage)
        
        when = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())

        helpers.toFile(f'{when} marketplaces.exe: {subject}\n\n{message}', 'user-data/logs/marketplaces.txt')

        helpers.run(['notepad', 'user-data/logs/marketplaces.txt'], False)

        self.hasNotified = True

    def waitBetween(self):
        secondsBetweenItems = self.options['secondsBetweenItems']

        if '--debug' in sys.argv:
            secondsBetweenItems = 3

        logging.info(f'Waiting {secondsBetweenItems} seconds')

        time.sleep(secondsBetweenItems)

    def getId(self, url):
        result = ''

        fields = url.split('/')

        if len(fields) == 0:
            return result

        result = fields[-1]
        return helpers.findBetween(result, '', '.')

    def __init__(self, options, emailer):
        self.averageSellingPrice = None
        self.hasNotified = False
        self.pictureUrl = ''
        self.email = ''
        self.page = None
        self.document = None
        self.emailer = emailer

        self.siteInformation = json.loads(helpers.getFile('craigslist.json'))

        self.downloader = Downloader()
        self.api = Api('')
        
        self.options = options

        self.aws = Aws(self.options)

class Marketplaces:
    def run(self):
        self.initialize()

        for row in helpers.getCsvFile(self.options['inputFile']):
            self.showStatus(row)
            self.doItem(row)

        self.cleanUp()

    def doItem(self, item):
        i = 0

        keyword = item.get('keyword', '')

        for site in self.options['sites']:
            logging.info(f'Keyword {self.onItemIndex}: {keyword}. Site {i + 1}: {site}.')
            i += 1

            if self.isDone(site, item):
                continue

            try:
                self.lookUpItem(site, item)

                if not self.averageSellingPrice:
                    logging.error(f'Skipping. Did not find average selling price.')
                    continue

                self.markDone(site, item)

                if site == 'craigslist':
                    self.waitBetween()
            except Exception as e:
                logging.error(f'Skipping. Something went wrong.')
                logging.error(e)
                logging.debug(traceback.format_exc())

    def lookUpItem(self, site, item):
        if 'checkaflip' in site:
            self.averageSellingPrice = ''

            self.averageSellingPrice = self.checkaflip.search(self.onItemIndex, site, item, self.database)
        elif 'craigslist' in site:
            self.getAverageSellingPrice(item)

            self.craigslist.search(self.onItemIndex, site, item, self.database, self.averageSellingPrice)

    def showStatus(self, row):
        keyword = row.get('keyword', '')

        logging.info(f'On item {self.onItemIndex + 1}: {keyword}')
        
        self.onItemIndex += 1

    def getAverageSellingPrice(self, item):
        # already have it?
        if self.averageSellingPrice:
            return

        # get from database
        keyword = item.get('keyword', '')
        hours = item.get('hours between runs', '')

        minimumDate = helpers.getDateStringSecondsAgo(int(hours) * 60 * 60, True)

        row = self.database.getFirst('result', 'price', f"siteName= 'checkaflip.com' and keyword = '{keyword}' and gmDate >= '{minimumDate}'", '', '')

        self.averageSellingPrice = row.get('price', '')

    def isDone(self, site, item):
        result = False;

        siteName = helpers.getDomainName(site)
        keyword = item.get('keyword', '')
        hours = item.get('hours between runs', '')

        if not hours:
            logging.error('Hours between runs is blank for this line')
            return result

        minimumDate = helpers.getDateStringSecondsAgo(int(hours) * 60 * 60, True)

        gmDateLastCompleted = self.database.getFirst('jobHistory', '*', f"siteName= '{siteName}' and keyword = '{keyword}' and gmDateLastCompleted >= '{minimumDate}'", '', '')

        if gmDateLastCompleted:
            logging.info(f'Skipping. Too soon since last completed this job.')
            result = True

        return result

    def markDone(self, site, item):
        siteName = helpers.getDomainName(site)

        item = {
            'siteName': siteName,
            'keyword': item.get('keyword', ''),
            'gmDateLastCompleted': str(datetime.datetime.utcnow())
        }

        logging.info(f'Inserting into database')
        logging.debug(item)
            
        self.database.insert('jobHistory', item)

    def removeOldItems(self):
        maximumDaysToKeepItems = self.options['maximumDaysToKeepItems']
        
        minimumDate = helpers.getDateStringSecondsAgo(maximumDaysToKeepItems * 24 * 60 * 60, False)
        
        logging.debug(f'Deleting items older than {maximumDaysToKeepItems} days')
        self.executeDatabaseStatement(f"delete from result where gmDate < '{minimumDate}'")

    def waitBetween(self):
        secondsBetweenItems = self.options['secondsBetweenItems']

        if '--debug' in sys.argv:
            secondsBetweenItems = 3
    
        logging.info(f'Waiting {secondsBetweenItems} seconds')

        time.sleep(secondsBetweenItems)

    def executeDatabaseStatement(self, statement):
        try:
            c = self.database.cursor
            c.execute(statement)
        except Exception as e:
            logging.error('Database error:')
            logging.error(e)
            logging.debug(traceback.format_exc())
    
    def cleanUp(self):
        self.database.close()

        logging.info('Done')

    def initialize(self):
        helpers.setUpLogging('user-data/logs')

        logging.info('Starting\n')

        self.onItemIndex = 0

        self.database = Database('database.sqlite')

        self.executeDatabaseStatement('create table if not exists result ( siteName text, idInWebsite text, keyword text, gmDate text, url text, name text, price integer, matches integer, json text, primary key(siteName, idInWebsite) )')
        self.executeDatabaseStatement('create table if not exists jobHistory ( siteName text, keyword text, gmDateLastCompleted text, primary key(siteName, keyword) )')

        self.options = {
            'inputFile': 'input.csv',
            'outputDirectory': 'output',
            'secondsBetweenItems': 30,
            'sites': '',
            'maximumDaysToKeepItems': 60,
            'onlyOutputPictureMatches': 0,
            'emailProvider': 'sendgrid',
            'fromEmailAddress': '',
            'debugEmailAddress': '',
            'toEmailAddress': '',
            'awsResourceUrl': 'program/resources/resource',
            'smartProxyResourceUrl': 'program/resources/resource2',
            'sendGridResourceUrl': 'program/resources/resource3',
        }

        helpers.setOptions('options.ini', self.options)

        self.options['sites'] = self.options['sites'].split(',')

        self.credentials = {}

        helpers.setOptions('user-data/credentials/credentials.ini', self.credentials, '')

        self.emailer = None
        
        if self.options['emailProvider'] == 'sendgrid':
            self.emailer = SendGrid(self.options, self.credentials)
        elif self.options['emailProvider'] == 'gmail':
            self.emailer = Gmail(self.options)
        
        self.checkaflip = Checkaflip(self.options)
        self.craigslist = Craigslist(self.options, self.emailer)

        self.averageSellingPrice = ''

        if '--debug' in sys.argv:
            self.options['secondsBetweenItems'] = 3

        helpers.addToStartup(__file__)
        self.removeOldItems()

marketplaces = Marketplaces()
marketplaces.run()