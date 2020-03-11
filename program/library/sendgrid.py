import sys
import logging

from ..library import helpers

from ..library.helpers import get
from ..library.api import Api

class SendGrid:
    def sendEmail(self, fromAddress, toAddress, subject, body):
        from sendgrid import SendGridAPIClient
        from sendgrid.helpers.mail import Mail

        try:
            self.log.info(f'Sending email to {toAddress}. From: {fromAddress}. Subject: {subject}. Body: {body[0:50]}...')

            if '--debug' in sys.argv and self.options['debugEmailAddress']:
                toAddress = self.options['debugEmailAddress']
                self.log.info(f'Actually sending to {toAddress}. Debug mode is on.')

            self.log.debug(f'Body: {body}')

            if '--debug' in sys.argv:
                helpers.toFile(body, 'user-data/logs/email.html')

            if not toAddress:
                self.log.error('No sending email. To email address is blank.')
                return

            sg = SendGridAPIClient(self.apiKey)
        
            message = Mail(
                from_email=fromAddress,
                to_emails=toAddress,
                subject=subject,
                html_content=body)
        
            response = sg.send(message)
        
            self.log.info(f'Sent successfully')

            self.log.debug(response.status_code)
            self.log.debug(response.body)
            self.log.debug(response.headers)
        except Exception as e:
            helpers.handleException(e)

    def __init__(self, options, credentials):
        self.options = options
        self.apiKey = helpers.getNested(credentials, ['sendgrid', 'apiKey'])
        self.log = logging.getLogger(get(self.options, 'loggerName'))

        if not self.apiKey:
            externalApi = Api('', self.options)
            url = helpers.getFile(self.options['sendGridResourceUrl'])
            self.apiKey = externalApi.get(url, None, False)

        if not self.apiKey:
            self.log.error('Can\'t send emails. You didn\'t put your SendGrid API key into credentials.ini')