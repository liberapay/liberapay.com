import threading

def get_last_email(mailer):
    return {
        'to': mailer.call_args[1]['message']['to'][0]['email'],
        'message_text': mailer.call_args[1]['message']['text'],
        'message_html': mailer.call_args[1]['message']['html']
    }

def wait_for_email_thread():
        # Emails are processed in a thread, wait for it to complete
        email_thread = filter(lambda x: x.name == 'email', threading.enumerate())
        if email_thread:
            email_thread[0].join()
