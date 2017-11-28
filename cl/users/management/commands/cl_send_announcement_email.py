import ast
import sys
import time

from django.conf import settings
from django.core.mail import send_mass_mail
from django.template import loader

from cl.lib.argparse_types import csv_list
from cl.lib.command_utils import VerboseCommand, logger
from cl.lib.utils import chunks
from cl.stats.utils import tally_stat
from cl.users.models import UserProfile

CHUNK_SIZE = 50


class Command(VerboseCommand):
    help = ('Sends a PR email to the people listed in recipients field and/or '
            'that are subscribed to the CL newsletter')

    def add_arguments(self, parser):
        parser.add_argument(
            '--recipients',
            type=csv_list,
            required=True,
            help='A list of recipients you wish to send the email to as comma '
                 'separated values.'
        ),
        parser.add_argument(
            '--subject',
            required=True,
            help='The subject of the email you wish to send.',
        ),
        parser.add_argument(
            '--sender',
            default=settings.DEFAULT_FROM_EMAIL,
            help='The sender for the email, default is from your settings.py '
                 'file.'
        ),
        parser.add_argument(
            '--template',
            required=True,
            help='What is the path, relative to the template directory, where '
                 'your email template lives?'
        ),
        parser.add_argument(
            '--context',
            default='{}',
            help='A dict containing the context for the email, if desired.'
        ),
        parser.add_argument(
            '--simulate',
            action='store_true',
            default=False,
            help="Don\'t send any emails, just pretend.",
        )

    def send_emails(self, recipients):
        """Send the emails using the templates and contexts requested."""
        email_subject = self.options['subject']
        email_sender = self.options['sender']
        txt_template = loader.get_template(self.options['template'])
        context = ast.literal_eval(self.options['context'])
        email_txt = txt_template.render(context)

        emails_sent_count = 0
        messages = []
        for recipient in recipients:
            messages.append((
                email_subject,
                email_txt,
                email_sender,
                [recipient],
            ))
            emails_sent_count += 1

        if not self.options['simulate']:
            send_mass_mail(messages, fail_silently=False)
            tally_stat('pr.emails.sent', inc=emails_sent_count)
            logger.info("Sent %s pr emails." % emails_sent_count)
        else:
            sys.stdout.write('Simulation mode. Imagine that we just sent %s '
                             'emails!\n' % emails_sent_count)

    def handle(self, *args, **options):
        super(Command, self).handle(*args, **options)
        self.options = options

        recipients = set()

        if options.get('subscribers'):
            for up in UserProfile.objects.filter(wants_newsletter=True):
                recipients.add(up.user.email)
        if options.get('recipients'):
            recipients.update(options['recipients'])
        if 'courtlistener' not in self.options['sender']:
            press_on = raw_input(
                "'CourtListener' isn't in your sender email address. In the "
                "past this has resulted in a lot of emails being marked as "
                "spam. Continue [y/n]? "
            )
            if press_on.lower() != 'y':
                exit(1)
        if not options['subject']:
            sys.stderr.write('No subject provided. Aborting.\n')
            exit(1)
        if not options['template']:
            sys.stderr.write('No template provided. Aborting.\n')
            exit(1)
        if recipients:
            if options['simulate']:
                sys.stdout.write("**********************************\n")
                sys.stdout.write("* SIMULATE MODE - NO EMAILS SENT *\n")
                sys.stdout.write("**********************************\n")
            if not options['simulate']:
                for chunk in chunks(list(recipients), CHUNK_SIZE):
                    self.send_emails(chunk)
                    logger.info("Waiting 300s before sending another chunk of "
                                "%s emails." % CHUNK_SIZE)
                    time.sleep(300)
            else:
                self.send_emails(recipients)
        else:
            sys.stderr.write("No recipients defined. Aborting.\n")
            exit(1)
