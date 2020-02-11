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

import helpers

from database import Database
from helpers import Api

from program.library.aws import Aws

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

        # don't want to items that cost more than the selling price
        # sss means all for sale
        category = item.get('craigslist category', 'sss')

        minimumProfitPercentage = item.get('min profit %', 10)
        minimumProfitPercentage = float(minimumProfitPercentage) / 100

        shipping = item.get('shipping cost', 0)
        shipping = float(shipping)

        priceWant = self.averageSellingPrice / minimumProfitPercentage
        priceWant = priceWant - shipping

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
                matches = self.passesFilters(item, newItem)

                jsonColumn = {
                    'email': self.email,
                    'picture': self.pictureUrl,
                    'picture similarity': '',
                    'things in image': self.thingsInImage
                }

                newItem['matches'] = int(matches)
                newItem['json'] = jsonColumn

                if matches or self.options['onlyOutputMatches'] == 0:
                    self.outputResult(site, item, newItem, database)

                newItem['json'] = json.dumps(newItem['json'])

                database.insert('result', newItem)                

                if matches or self.options['onlyOutputMatches'] == 0:
                    siteName = helpers.getDomainName(site)
                    outputFile = os.path.join(os.getcwd(), self.options['outputFile'])
                    name = newItem.get('name', '')
                    price = newItem.get('price', '')

                    self.notify(f'One or more new results!\n\nCheck {outputFile} for details.\n\nSite: {siteName}\nKeyword: {keyword}\nTitle: {name}\nPrice: ${price}')

            self.waitBetween()

    def picturePassesFilters(self, item, url):
        result = False

        if not url:
            return True

        thingsToFind = item.get('picture must contain one of', '')

        if not thingsToFind:
            return True

        pictureFileName = 'logs/cache/picture'

        if os.path.exists(pictureFileName):
            os.remove(pictureFileName)
        
        helpers.makeDirectory(os.path.dirname(pictureFileName))

        self.api.getBinaryFile(url, pictureFileName)

        if os.stat(pictureFileName).st_size == 0:
            logging.error(f'Failed to download {url}')
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

    def passesFilters(self, searchItem, resultItem):
        result = False

        self.pictureUrl = ''
        self.email = ''
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
            phrasesToAvoid = False

        page = self.downloader.get(url)        
        document = lh.fromstring(page)

        pictures = document.xpath("//a[@class = 'thumb']")
        javascriptContainsPicture = '"thumb":"https://images.craigslist.org/' in page

        if pictures:
            self.pictureUrl = pictures[0].attrib['href']

        if not self.pictureUrl:
            imageList = helpers.findBetween(page, 'var imgList = ', ';\n', True)

            if imageList:
                imageList = json.loads(imageList)

                if imageList:
                    self.pictureUrl = imageList[0].get('url', '')

        if searchItem.get('craigslist ad must contain a picture', '') == 'true' and len(pictures) == 0 and not javascriptContainsPicture:
            logging.info(f'Skipping. It doesn\'t have a picture.')
            return False

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

        if result:
            self.email = self.getEmail(url, document)
            result = self.picturePassesFilters(searchItem, self.pictureUrl)

        self.waitBetween()

        return result

    def getEmail(self, url, document):
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

    def outputResult(self, site, searchItem, newItem, database):
        # write headers
        if not os.path.exists(self.options['outputFile']):
            headers = ['date', 'keyword', 'craigslist category', 'matches']

            for site in self.options['sites']:
                siteName = helpers.getDomainName(site)

                headers.append(siteName + ' price')

            headers.append('profit %')
            headers.append('picture confidence %')
            headers.append('url')
            headers.append('email')
            headers.append('picture')

            line = ','.join(headers)

            helpers.toFile(line, self.options['outputFile'])
            helpers.toFile(line, 'output-backup.csv')

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
        
        profit = revenue / costs
        # as a percentage
        profit = profit * 100
        
        fields.append(helpers.fixedDecimals(profit, 0))
        
        fields.append(self.pictureConfidence)
        
        fields.append(newItem.get('url', ''))
        
        fields.append(helpers.getNested(newItem, ['json', 'email']))
        fields.append(helpers.getNested(newItem, ['json', 'picture']))

        line = ','.join(fields)
    
        helpers.appendToFile(line, self.options['outputFile'])
        helpers.appendToFile(line, 'output-backup.csv')

        self.csvToHtml(self.options['outputFile'])

    def csvToHtml(self, fileName):
        csv = helpers.getCsvFileAsDictionary(fileName)

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

        helpers.toFile(file, htmlFileName)

    def notify(self, message):
        if self.hasNotified:
            return

        logging.info(message)

        when = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())

        helpers.toFile(f'{when} marketplaces.exe: {message}', 'logs/event.txt')

        helpers.run(['notepad', 'logs/event.txt'], False)

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

    def __init__(self, options):
        self.averageSellingPrice = None
        self.hasNotified = False
        self.pictureUrl = ''
        self.email = ''

        self.siteInformation = json.loads(helpers.getFile('craigslist.json'))

        self.downloader = Downloader()
        self.api = Api('')
        
        self.options = options

        self.aws = Aws(self.options)

class Marketplaces:
    def run(self):
        self.initialize()

        for row in helpers.getCsvFileAsDictionary(self.options['inputFile']):
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
        helpers.setUpLogging()

        logging.info('Starting\n')

        self.onItemIndex = 0

        self.database = Database('database.sqlite')

        self.executeDatabaseStatement('create table if not exists result ( siteName text, idInWebsite text, keyword text, gmDate text, url text, name text, price integer, matches integer, json text, primary key(siteName, idInWebsite) )')
        self.executeDatabaseStatement('create table if not exists jobHistory ( siteName text, keyword text, gmDateLastCompleted text, primary key(siteName, keyword) )')

        self.options = {
            'inputFile': 'input.csv',
            'outputFile': 'output.csv',
            'secondsBetweenItems': 30,
            'sites': '',
            'maximumDaysToKeepItems': 60,
            'onlyOutputMatches': 0,
            'resourceUrl': 'http://temporary.info.tm/Pa6Xxwkua9AjYymMOiB6'
        }

        helpers.setOptions('options.ini', self.options)

        self.options['sites'] = self.options['sites'].split(',')

        self.checkaflip = Checkaflip(self.options)
        self.craigslist = Craigslist(self.options)

        self.averageSellingPrice = ''

        if '--debug' in sys.argv:
            self.options['secondsBetweenItems'] = 3

        helpers.addToStartup(__file__)
        self.removeOldItems()

marketplaces = Marketplaces()
marketplaces.run()