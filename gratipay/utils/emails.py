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

def send_email(to_address, to_name, subject, html, text):
    mail_client = mail(env())
    message = {
        'from_email': 'support@gratipay.com',
        'from_name': 'Gratipay',
        'to': [{'email': to_address, 'name': to_name}],
        'subject': subject,
        'html': html,
        'text': text
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
    html = """
Welcome to Gratipay!
<br><br>
<a href="%s">Verify your email address</a>.
""" % link
    text = """
Welcome to Gratipay! Verify your email address:

%s
""" % link
    return send_email(participant.email.address, participant.username, subject, html, text)
