import logging
import random

from collections import OrderedDict

from . import helpers

from .helpers import get

class Website:
    def getXpath(self, page, xpath, firstOnly=False, attribute=None, document=None, strip=True):
        result = []

        if firstOnly:
            result = ''
        
        try:
            import lxml.html as lh

            result = ''

            if document == None:
                document = lh.fromstring(page)

            # get matching elements
            elements = document.xpath(xpath)

            if firstOnly:
                if len(elements) > 0:
                    if not attribute:
                        result = elements[0].text_content()

                        if strip:
                            result = result.strip()
                    else:
                        result = elements[0].attrib[attribute]
            else:
                result = elements
        except Exception as e:
            self.log.error(e)

        return result

    # xpath should start with "./" instead of "//"
    def getXpathInElement(self, rootElement, xpath, firstOnly=False, attribute=None, strip=True):
        result = ''

        try:
            elements = rootElement.xpath(xpath)

            if firstOnly:
                if len(elements) > 0:
                    if not attribute:
                        result = elements[0].text_content()

                        if strip:
                            result = result.strip()
                    else:
                        result = elements[0].attrib[attribute]
            else:
                result = elements
        except Exception as e:
            self.log.error(e)

        return result

    def removeTags(self, document):
        import lxml
        
        from lxml.html.clean import Cleaner

        cleaner = Cleaner()
        cleaner.javascript = True # This is True because we want to activate the javascript filter
        cleaner.style = True         

        return cleaner.clean_html(document)

    def __init__(self, options):
        self.proxies = None
        self.log = logging.getLogger(get(options, 'loggerName'))

        self.userAgentList = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/79.0.3945.88 Safari/537.36'
        ]

        userAgent = random.choice(self.userAgentList)

        self.headers = OrderedDict([
            ('user-agent', userAgent),
            ('accept', 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9'),
            ('accept-language', 'en-US,en;q=0.9')
        ])