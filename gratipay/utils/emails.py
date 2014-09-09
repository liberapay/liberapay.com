import mandrill
from environment import Environment
from aspen import log_dammit

class BadEnvironment(SystemExit):
    pass

def env():
    env = Environment(MANDRILL_KEY=unicode)
    if env.malformed:
        raise BadEnvironment("Malformed envvar: MANDRILL_KEY")
    if env.missing:
        raise BadEnvironment("Missing envvar: MANDRILL_KEY")
    return env

class MandrillError(Exception): pass

def mail(env):
    mandrill_client = mandrill.Mandrill(env.mandrill_key)
    return mandrill_client

def send_email(to_address, to_name, subject, body):
    mail_client = mail(env())
    message = {
        'from_email': 'notifications@gratipay.com',
        'from_name': 'Gratipay',
        'to': [{'email': to_address,
             'name': to_name
            }],
        'subject': subject,
        'html': body
    }
    try:
        result = mail_client.messages.send(message=message)
        return result
    except mandrill.Error, e:
        log_dammit('A mandrill error occurred: %s - %s' % (e.__class__, e))
        raise MandrillError

def send_verification_email(participant):
    subject = "Welcome to Gratipay!"
    link = participant.get_verification_link()
    # TODO - Improve body text
    body = """
        Welcome to Gratipay!

        <a href="%s">Click on this link</a> to verify your email.

    """ % link
    return send_email(participant.email.address, participant.username, subject, body)
