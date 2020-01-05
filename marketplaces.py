import sys
import json
import logging
import time
import configparser
import urllib
import datetime
import os
import random
from collections import OrderedDict
import requests
import lxml.html as lh
import helpers
from database import Database
from helpers import Api

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

        price = response.get('slot1', '')

        if price == '':
            logging.error('Stopping. Wrong or no response.')
            return

        price = int(price)

        jsonColumn = {
            'sellThroughRate': response.get('slot2', '')
        }

        newItem = {
            'siteName': helpers.getDomainName(site),
            'idInWebsite': self.getId(keyword),
            'keyword': item.get('keyword', ''),
            'gmDate': str(datetime.datetime.utcnow()),
            'price': price,
            'json': json.dumps(jsonColumn)
        }
    
        if newItem['price'] <= 0:
            logging.info('Skipping price is less than or equal to zero')
            return

        sellThroughRate = jsonColumn.get('sellThroughRate', '')
        logging.info(f'Price: {price}. Sell through rate: {sellThroughRate}.')

        database.insert('result', newItem)

        # will use it later to filter search results
        return price

    def waitBetween(self):
        secondsBetweenItems = self.options['secondsBetweenItems']

        logging.info(f'Waiting {secondsBetweenItems} seconds')

        time.sleep(secondsBetweenItems)

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
    def getResults(self, site, item, page):
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

        i = 0

        keyword = item.get('keyword', '')

        keywords = urllib.parse.quote_plus(keyword);
        
        minimumPrice = item.get('min price', '')
        minimumPrice = int(minimumPrice)
        
        maximumPrice = item.get('max price', '')
        maximumPrice = int(maximumPrice)
        
        # sss means all for sale
        category = item.get('craigslist category', 'sss')

        minimumPercentageDifference = item.get('min percentage difference', 100.0)
        minimumPercentageDifference = float(minimumPercentageDifference)
        minimumPercentageDifference = minimumPercentageDifference / 100.0

        priceWant = averageSellingPrice * (1.0 - minimumPercentageDifference)
        priceWant = int(priceWant)

        if priceWant < maximumPrice:
            maximumPrice = priceWant

        if priceWant < minimumPrice:
            minimumPrice = 1

        for city in self.siteInformation['cities']:
            cityName = city.get('name', '');

            logging.info(f'Keyword {onItemIndex}: {keyword}. Site: craigslist. City {i + 1}: {cityName}.')
            i += 1

            urlToGet = city.get('url', '')
            urlToGet += f'/search/{category}?query={keywords}&sort=rel&min_price={minimumPrice}&max_price={maximumPrice}'

            page = self.downloader.get(urlToGet)
            items = self.getResults(site, item, page)

            for newItem in items:
                database.insert('result', newItem)

            self.waitBetween()

    def waitBetween(self):
        secondsBetweenItems = self.options['secondsBetweenItems']

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
        self.siteInformation = json.loads(helpers.getFile('craigslist.json'))

        self.downloader = Downloader()

        self.options = options

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

                self.addToReport(item)
                self.markDone(site, item)
                self.waitBetween()
            except Exception as e:
                logging.error(f'Skipping. Something went wrong.')
                logging.error(e)

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

    def addToReport(self, item):
        if not os.path.exists(self.options['outputFile']):
            headers = ['keyword', 'date']

            for site in self.options['sites']:
                siteName = helpers.getDomainName(site)

                headers.append(siteName + ' price')

            headers.append('difference')
            headers.append('percentage')
            headers.append('url')

            line = ','.join(headers)

            helpers.toFile(line, self.options['outputFile'])

        keyword = item.get('keyword', '')

        now = datetime.datetime.utcnow()
        today = now.strftime('%Y-%m-%d')

        minimumDate = helpers.getDateStringSecondsAgo(24 * 60 * 60, True)
               
        for site in self.options['sites']:
            siteName = helpers.getDomainName(site)

            if siteName == 'checkaflip.com':
                continue

            rows = self.database.get('result', '*', f"keyword = '{keyword}' and gmDate >= '{minimumDate}' and siteName = '{siteName}'", 'price', 'asc')

            for row in rows:
                fields = [keyword, today]

                fields.append(str(self.averageSellingPrice))
                fields.append(str(row.get('price', '')))

                difference = self.averageSellingPrice - row.get('price', '')
                fields.append(helpers.fixedDecimals(difference, 2))
            
                percentage = row.get('price', '') / self.averageSellingPrice
                percentage = percentage * 100.0
                fields.append(helpers.fixedDecimals(percentage, 0))
                
                fields.append(row.get('url', ''))

                line = ','.join(fields)
            
                helpers.appendToFile(line, self.options['outputFile'])

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

        logging.info(f'Waiting {secondsBetweenItems} seconds')

        time.sleep(secondsBetweenItems)

    def executeDatabaseStatement(self, statement):
        try:
            c = self.database.cursor
            c.execute(statement)
        except Exception as e:
            logging.error('Database error:')
            logging.error(e)
    
    def cleanUp(self):
        self.database.close()

        logging.info('Done')

    def initialize(self):
        helpers.setUpLogging()

        logging.info('Starting\n')

        self.onItemIndex = 0

        self.database = Database('database.sqlite')

        self.executeDatabaseStatement('create table if not exists result ( siteName text, idInWebsite text, keyword text, gmDate text, url text, name text, price integer, country text, state text, city text, json text, primary key(siteName, idInWebsite) )')
        self.executeDatabaseStatement('create table if not exists jobHistory ( siteName text, keyword text, gmDateLastCompleted text, primary key(siteName, keyword) )')

        self.options = {
            'inputFile': 'input.csv',
            'outputFile': 'output.csv',
            'secondsBetweenItems': 30,
            'sites': '',
            'maximumDaysToKeepItems': 60
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