# Vaccine Finder Emailer

## Usage:
```
$ python check.py <your zip code> <max distance in miles> [--debug]
```

_Note: Passing `--debug` will prevent the email from being sent_

## Credentials file
You must create a `credentials.txt` file with the following format:
```
[sendgrid]
API_KEY = <Your SendGrid API Key>
TO_ADDR = <Email to send to when appointments are found>
FROM_ADDR = <Email address to send from>
```

Note: With Sendgrid, your `FROM_ADDR` *must* match your verified email address or you will get a 403.
