import re
from time import sleep

import requests


sess = requests.Session()
r = sess.get('https://www.paypal.com/webapps/mpp/country-worldwide')
country_codes = set(re.findall(r"/([a-z]{2})/home", r.text))
for cc in sorted(country_codes):
    print(f"Requesting info for country code {cc.upper()}")
    r = sess.get(f"https://www.paypal.com/{cc}/home")
    if "Please wait while we perform security check" in r.text:
        raise Exception("PayPal blocked the request")
    if f"/{cc}/webapps/" not in r.text:
        raise Exception("PayPal's response doesn't seem to contain the expected information")
    is_supported = (
        f"/{cc}/webapps/mpp/accept-payments-online" in r.text or
        f"/{cc}/business/accept-payments" in r.text
    )
    if not is_supported:
        country_codes.remove(cc)
    sleep(1.5)

country_codes.remove('uk')
country_codes.add('gb')
print(f"PayPal should be available to creators in the following {len(country_codes)} countries:")
print(' '.join(map(str.upper, sorted(country_codes))))
