def get_last_email(mailer):
    return {
        'to': mailer.call_args[1]['message']['to'][0]['email'],
        'message_text': mailer.call_args[1]['message']['text'],
        'message_html': mailer.call_args[1]['message']['html']
    }
