import sys
import logging
import pickle
import os
import json
import base64
import mimetypes

from email.mime.audio import MIMEAudio
from email.mime.base import MIMEBase
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime

from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

from ..library import helpers

from ..library.helpers import get
from ..library.api import Api

class Gmail:
    def export(self, inputRows):
        emailAddresses = inputRows.split(',')

        queryParts = []

        for emailAddress in emailAddresses:
            queryParts.append(f'to:{emailAddress.strip()}')

        query = ' OR '.join(queryParts)

        threads = self.searchForThreads(query)

        for threadMetadata in threads:
            threadId = get(threadMetadata, 'id')

            thread = self.service.users().threads().get(userId='me', id=threadId).execute()

            for message in get(thread, 'messages'):
                self.outputMessageInformation(message, False)

    def getCancelList(self, outputFile):
        threads = self.searchForThreads(self.options['searchTerm'])

        for threadMetadata in threads:
            threadId = get(threadMetadata, 'id')

            thread = self.service.users().threads().get(userId='me', id=threadId).execute()

            for message in get(thread, 'messages'):
                emailAddress = self.getBody(message)
                emailAddress = helpers.findBetween(emailAddress, '', ' wants to cancel.', True)

                if emailAddress and not emailAddress in helpers.getFile(outputFile):
                    helpers.appendToFile(emailAddress, outputFile)

                # only need first message in each thread
                continue

    def sendReplies(self):
        self.initialize()

        logging.info(f'Searching for {self.options["searchTerm"]}')

        threads = self.service.users().threads().list(userId='me', q=self.options['searchTerm']).execute()

        logging.info(f'Got {len(get(threads, "threads"))}')

        for threadMetadata in get(threads, 'threads'):
            threadId = get(threadMetadata, 'id')

            thread = self.service.users().threads().get(userId='me', id=threadId).execute()

            if self.shouldReply(thread):
                try:
                    body = self.whatToSay(thread)
                    self.reply(thread, body)
                except Exception as e:
                    helpers.handleException(e)            

    def reply(self, thread, body):
        messages = get(thread, 'messages')

        if not messages:
            return

        messages.reverse()

        threadId = get(thread, 'id')
        messageId = ''
        references = ''
        toAddress = ''
        subject = ''
        
        for i, message in enumerate(messages):
            if not subject:
                subject = self.getHeader(message, 'Subject')

                if not subject.lower().startswith('re: '):
                    subject = 'Re: ' + subject

            # to avoid replying to automatic replies
            if i == 0 or self.messageType(message) == 'someone else':
                messageId = self.getHeader(message, 'Message-Id')
                references = self.getHeader(message, 'References')
                
                # for some live chat emails
                toAddress = self.getHeader(message, 'Reply-To')

                if not toAddress:
                    toAddress = self.getHeader(message, 'To')

                if toAddress == self.options['supportToEmailAddress']:
                    toAddress = self.getBody(message)
                    toAddress = helpers.findBetween(toAddress, 'Email: ', '<br>')

        if not threadId:
            return

        if '--debug' in sys.argv:
            toAddress = 'account.test123@mailinator.com'

        toAddress = helpers.findBetween(toAddress, '<', '>')

        message = MIMEText(body, 'html')
        message['To'] = toAddress
        message['From'] = self.options['userEmailAddress']
        message['Subject'] = subject
        message['In-Reply-To'] = messageId

        # as required
        references = references + ' ' + messageId
        references = references.strip()
        message['References'] = references
        
        messageToSend = {
            'threadId': threadId,
            'raw': base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
        }
        
        self.send(messageToSend, toAddress, subject, body)

        self.changeLabels(thread)

    def changeLabels(self, thread):
        threadId = get(thread, 'id')
        
        msg_labels =  {'removeLabelIds': ['INBOX'], 'addLabelIds': [self.options['labelToAdd']]}

        thread = self.service.users().threads().modify(userId='me', id=threadId, body=msg_labels).execute()

    def searchForThreads(self, query):
        self.initialize()
        
        logging.info(f'Searching for {query}')

        threads = []
        
        request = self.service.users().threads().list(userId='me', q=query)

        while request is not None:
            response = request.execute()

            # Do something with the activities
            threads += get(response, 'threads')
            logging.info(f'Found {len(threads)} threads')

            request = self.service.users().threads().list_next(request, response)

        return threads

    def whatToSay(self, thread):
        body = helpers.getFile('user-data/input/standard.html')
        body = body.replace('\n', '<br>\n')

        return body

    def getMessageObject(self, fromAddress, toAddress, subject, body, threadId=None, replyingToMessageId=None):
        message = MIMEText(body, 'html')
        message['To'] = toAddress
        message['From'] = fromAddress
        message['Subject'] = subject

        if replyingToMessageId:
            message['In-Reply-To'] = replyingToMessageId

            # as required
            references = references + ' ' + replyingToMessageId
            references = references.strip()
            message['References'] = references
        
        messageToSend = {
            'raw': base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
        }

        if threadId:
            messageToSend['threadId'] = threadId

        return messageToSend

    def sendEmail(self, fromAddress, toAddress, subject, body):
        messageObject = self.getMessageObject(fromAddress, toAddress, subject, body)

        self.send(messageObject, toAddress, subject, body)

    def send(self, messageToSend, toAddress, subject, body):
        result = False

        try:
            logging.info(f'Sending email to {toAddress}. Subject: {subject}. Body: {body[0:50]}...')
            message = self.service.users().messages().send(userId='me', body=messageToSend).execute()
            
            logging.info(f'Sent successfully. Message id: {get(message, "id")}.')
            
            result = True
        except Exception as e:
            logging.error('Something went wrong while sending the email')
            helpers.handleException(e)            

        return result

    def shouldReply(self, thread):
        result = not self.hasManualMessage(thread)

        return result

    def hasManualMessage(self, thread, includeCanned=False):
        result = False

        for message in get(thread, 'messages'):
            if self.messageType(message) == 'manual':
                result = True
                break

        return result

    def messageType(self, message):
        result = 'someone else'
        
        fromAddress = self.getHeader(message, 'From')
        fromAddress = helpers.findBetween(fromAddress, '<', '>')

        toAddress = self.getHeader(message, 'To')
        toAddress = helpers.findBetween(toAddress, '<', '>')

        mailedBy = self.getHeader(message, 'Mailed-By')

        # from website or automatic reply from gmail
        if fromAddress == self.options['automaticResponseAddress'] or toAddress == self.options['supportToEmailAddress']:
            result = 'automatic'
        elif fromAddress == self.options['userEmailAddress'] and toAddress != self.options['supportToEmailAddress'] and mailedBy != self.options['emailProviderDomain']:
            result = 'manual'
        
        return result

    def outputMessageInformation(self, message, shouldGetBody=True):
        information = self.getMessageInformation(message, shouldGetBody)

        self.showMessageInformation(message, shouldGetBody)

        outputFile = self.options['outputFile']

        helpers.makeDirectory(os.path.dirname(outputFile))

        fields = ['date', 'from', 'from first name', 'from last name', 'from country', 'to', 'to first name', 'to last name']

        if not os.path.exists(outputFile):
            printableFields = []
            
            for field in fields:
                printableName = helpers.addBeforeCapitalLetters(field).lower()
                
                printableFields.append(printableName)
            
            helpers.toFile(','.join(printableFields), outputFile)

        values = []

        for field in fields:
            values.append(get(information, field))

        # this quotes fields that contain commas
        helpers.appendCsvFile(values, outputFile)
    
    def showMessageInformation(self, message, shouldGetBody=True):
        information = self.getMessageInformation(message)

        bodyPart = ''

        if shouldGetBody:
            bodyPart = f'Body: {get(information, "body")[0:50]}.'

        print(f'From: {get(information, "from")}. To: {get(information, "to")}. Date: {get(information, "date")}.{bodyPart}')

    def getMessageInformation(self, message, shouldGetBody=True):
        fromInformation = self.getSenderInformation(message, 'From')
        toInformation = self.getSenderInformation(message, 'To')

        internalDate = int(get(message, 'internalDate')) / 1000
        date = datetime.utcfromtimestamp(internalDate)
        dateString = date.strftime('%Y-%m-%d %H:%M:%S')

        body = self.getBody(message)

        result = {
            'date': dateString,
            'from': get(fromInformation, 'emailAddress'),
            'from first name': get(fromInformation, 'firstName'),
            'from last name': get(fromInformation, 'lastName'),
            'to': get(toInformation, 'emailAddress'),
            'to first name': get(toInformation, 'firstName'),
            'to last name': get(toInformation, 'lastName'),
            'from country': self.getCountry(get(fromInformation, 'emailAddress')),
            'body': body
        }

        return result

    def getCountry(self, emailAddress):
        result = ''
        
        if not self.domains:
            self.domains = helpers.getCsvFile('program/resources/domains.csv')

        domainToFind = helpers.getLastAfterSplit(emailAddress, '.')

        if domainToFind == 'com':
            return result

        for row in self.domains:
            if get(row, 'domain') == domainToFind:
                result = get(row, 'country')
                break

        return result

    def getSenderInformation(self, message, senderType):
        value = self.getHeader(message, senderType)
        
        emailAddress = helpers.findBetween(value, '<', '>')
        
        name = helpers.findBetween(value, '', '<', True)
        name = name.strip()
        
        firstName = helpers.findBetween(name, '', ' ')
        lastName = helpers.getLastAfterSplit(name, ' ', minimumFieldCount=2)

        result = {
            'emailAddress': emailAddress,
            'firstName': firstName,
            'lastName': lastName
        }

        return result

    def getBody(self, message):
        base64String = helpers.getNested(message, ['payload', 'body', 'data'])

        if not base64String:
            for part in helpers.getNested(message, ['payload', 'parts']):
                base64String += helpers.getNested(part, ['body', 'data'])

        if not base64String:
            base64String = get(message, 'raw')

        body = base64.urlsafe_b64decode(base64String.encode('ASCII'))
        return body.decode("utf-8") 

    def getHeader(self, message, headerName):
        result = ''
        
        for header in helpers.getNested(message, ['payload', 'headers']):
            if get(header, 'name') == headerName:
                result = get(header, 'value')
                break

        return result

    def getLabels(self):
        # Call the Gmail API
        results = self.service.users().labels().list(userId='me').execute()
        labels = results.get('labels', [])

        if not labels:
            print('No labels found.')
        else:
            print('Labels:')
            for label in labels:
                print(label['name'])

    def getService(self):
        # If modifying these scopes, delete the file token.pickle.
        SCOPES = ['https://www.googleapis.com/auth/gmail.modify']

        if self.scopes:
            SCOPES = self.scopes

        creds = None
        # The file token.pickle stores the user's access and refresh tokens, and is
        # created automatically when the authorization flow completes for the first
        # time.
        if os.path.exists('user-data/token.pickle'):
            with open('user-data/token.pickle', 'rb') as token:
                creds = pickle.load(token)
        # If there are no (valid) credentials available, let the user log in.
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                credentialsInformation = helpers.getJsonFile('user-data/credentials/credentials.json')
                
                if not credentialsInformation and get(self.options, 'gmailResourceUrl'):
                    externalApi = Api('', self.options)
                    url = helpers.getFile(self.options['gmailResourceUrl'])
                    credentialsInformation = externalApi.get(url)

                flow = InstalledAppFlow.from_client_config(credentialsInformation, SCOPES)
                creds = flow.run_local_server(port=0)
            # Save the credentials for the next run
            with open('user-data/token.pickle', 'wb') as token:
                pickle.dump(creds, token)

        service = build('gmail', 'v1', credentials=creds, cache_discovery=False)

        return service

    def initialize(self):
        if self.initialized:
            return

        self.initialized = True
        
        self.service = self.getService()

    def __init__(self, options):
        self.options = options
        self.initialized = False
        self.log = logging.getLogger(get(self.options, 'loggerName'))
        self.scopes = None
        self.domains = None

        if get(self.options, 'readOnly'):
            self.scopes = ['https://www.googleapis.com/auth/gmail.readonly']

        self.replies = None
        
        if get(self.options, 'repliesFile'):
            self.replies = helpers.getJsonFile(get(self.options, 'repliesFile'))