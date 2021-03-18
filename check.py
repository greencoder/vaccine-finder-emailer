import argparse
import configparser
import geopy.distance
import json
import pathlib
import requests
import sendgrid
import sys
import tabulate


def fetch_vaccine_json():
    url = 'https://www.vaccinespotter.org/api/v0/states/CO.json'
    response = requests.get(url, headers={'User-Agent': 'Mozilla 1.0'})
    assert response.ok, 'Could not fetch URL'
    return response.json()


def load_zips_as_points(filepath):
    zips = {}
    data = json.loads(pathlib.Path(filepath).read_text())

    for result in data:
        key = result.get('fields', {}).get('zip')
        value = result.get('fields', {}).get('geopoint')
        zips[key] = value

    return zips


def distance_from_zip_code(src_zip_code, dst_zip_code, zips):
    dst_point = zips.get(dst_zip_code)
    src_point = zips.get(src_zip_code)

    if src_point and dst_point:
        distance = int(geopy.distance.great_circle(src_point, dst_point).mi)
    else:
        distance = 99999 # Return a huge distance if not found

    return distance


def send_email(html, api_key):
    to_addr = 'snewman18@gmail.com'
    from_addr = 'scott@getnewman.com'
    subject = 'Vaccine Appointments Available'
    message = sendgrid.helpers.mail.Mail(from_email=from_addr, to_emails=to_addr, subject=subject, html_content=html)
    sg = sendgrid.SendGridAPIClient(api_key)
    response = sg.send(message)
    return response.status_code in range(200, 300)


def parse_feature(location_dict, src_zip_code, zip_codes):
    props = location_dict.get('properties', {})
    lng, lat = location_dict.get('geometry', {}).get('coordinates')
    url = props.get('url')
    city = props.get('city')
    state = props.get('state')
    postal = props.get('postal_code')
    address = props.get('address')
    name = props.get('name')
    appointments_available = props.get('appointments_available')
    distance = distance_from_zip_code(src_zip_code, postal, zip_codes)

    return {
        'provider': name,
        'address': f'{address}, {city} {state} {postal}',
        'zip_code': postal,
        'distance': distance,
        'has_appts': appointments_available,
    }


if __name__ == '__main__':

    # Read command-line arguments
    argparser = argparse.ArgumentParser()
    argparser.add_argument('src_zip_code')
    argparser.add_argument('max_distance', type=int)
    argparser.add_argument('--debug', action='store_true', default=False)
    args = argparser.parse_args()

    # Load the credentials
    config = configparser.ConfigParser()
    config.read('credentials.txt')

    API_KEY = config['sendgrid']['API_KEY']
    assert API_KEY, 'Could not load Sendgrid API key'

    # Load up the Colorado zip codes
    points_by_zip = load_zips_as_points('colorado_zip_codes.json')

    # Fetch or load the web page
    if not args.debug:
        print('Fetching JSON')
        data = fetch_vaccine_json()
        pathlib.Path('result.json').write_text(json.dumps(data, indent=2))
    else:
        print('Loading JSON')
        data = json.loads(pathlib.Path('result.json').read_text())

    # Parse the locations from the GeoJSON
    features = data.get('features', [])
    all_locations = [parse_feature(feat, args.src_zip_code, points_by_zip) for feat in features]

    # Filter only locations that are within the desired distance
    nearby_locations = list(filter(lambda v: v.get('distance') <= args.max_distance, all_locations))

    # Filter only nearby locations that have appointments
    locations = list(filter(lambda v: v.get('has_appts') == True, nearby_locations))

    if len(locations) == 0:
        sys.exit('No nearby locations with appointments found.')

    # Print a table of the results
    headers = {'pharmacy': 'Pharmacy', 'address': 'Address', 'zip_code': 'Zip Code', 'distance': 'Distance'}
    table = tabulate.tabulate(locations, headers=headers)
    html = f'<pre>{table}</pre>'

    if not args.debug:
        result = send_email(html, API_KEY)
        print(table)
        print('Email sent:', result)
    else:
        print(table)
