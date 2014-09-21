from __future__ import absolute_import, division, print_function, unicode_literals

from gratipay.elsewhere import PlatformOAuth2
from gratipay.elsewhere._extractors import key


class Google(PlatformOAuth2):

    # Platform attributes
    name = 'google'
    display_name = 'Google'
    account_url = 'https://www.facebook.com/{user_name}'

    # Auth attributes

    auth_url = 'https://accounts.google.com/o/oauth2/auth'
    access_token_url = 'https://accounts.google.com/o/oauth2/token'
    oauth_default_scope = ['https://www.googleapis.com/auth/userinfo.email',
    	'https://www.googleapis.com/auth/userinfo.profile']

    # API attributes
    api_format = 'json'
    api_url = 'https://www.googleapis.com/plus/v1'
    api_user_info_path = '/{user_id}'
    api_user_self_info_path = '/people/me'

    # User info extractors
    x_user_name = key('id') # Google doesn't provide a username, so we're using ID here.
    x_display_name = key('displayName')

    def x_avatar_url(self,extracted,info,default):
    	try:
    	    image_dict = info.pop('image')
    	except KeyError:
    	    msg = 'Unable to find key "%s" in %s API response:\n%s'
    	    log(msg % (k, self.name, json.dumps(info, indent=4)))
    	    raise
    	return image_dict.get('url')

    def x_email(self,extracted,info,default):
    	try:
    	    emails = info.pop('emails')
    	except KeyError:
    	    msg = 'Unable to find key "%s" in %s API response:\n%s'
    	    log(msg % (k, self.name, json.dumps(info, indent=4)))
    	    raise
    	return emails[0].get('value')