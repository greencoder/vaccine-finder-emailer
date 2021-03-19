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
    """ Fetch the JSON API """
    url = 'https://www.vaccinespotter.org/api/v0/states/CO.json'
    response = requests.get(url, headers={'User-Agent': 'Mozilla 1.0'})
    assert response.ok, 'Could not fetch URL'
    return response.json()


def load_zips_as_points(filepath):
    """ Loads the zip codes file into a dictionary """
    zip_codes_dict = {}
    lines = pathlib.Path(filepath).read_text().strip().split('\n')[1:]

    for line in lines:
        zip_code, latitude, longitude = line.split(',')
        zip_codes_dict[zip_code] = (float(latitude),float(longitude))

    return zip_codes_dict


def distance_from_zip_code(src_zip_code, dst_zip_code, zips):
    """ Determines the distance (in miles) between two zip codes """
    dst_point = zips.get(dst_zip_code)
    src_point = zips.get(src_zip_code)

    if src_point and dst_point:
        distance = int(geopy.distance.great_circle(src_point, dst_point).mi)
    else:
        distance = None

    return distance


def send_email(html, api_key, to_addr, from_addr):
    """ Sends the email to the recipient via SendGrid """
    subject = 'Vaccine Appointments Available'
    message = sendgrid.helpers.mail.Mail(from_email=from_addr, to_emails=to_addr, subject=subject, html_content=html)
    sg = sendgrid.SendGridAPIClient(api_key)
    response = sg.send(message)
    return response.status_code in range(200, 300)


def parse_feature(location_dict, src_zip_code, zip_codes):
    """ Parses the GeoJSON feature into a dictionary """
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
    if not pathlib.Path('credentials.txt').exists():
        sys.exit('Error! credentials.txt not found. See README for details.')
    else:
        config = configparser.ConfigParser()
        config.read('credentials.txt')

    try:
        API_KEY = config['sendgrid']['API_KEY']
        TO_ADDR = config['sendgrid']['TO_ADDR']
        FROM_ADDR = config['sendgrid']['FROM_ADDR']
    except KeyError:
        sys.exit('Error reading credentials.txt. See README for details.')

    # Make sure we got the values needed from the credentials file
    assert API_KEY, 'Could not load SendGrid API_KEY. See README for details.'
    assert TO_ADDR, 'Could not load TO_ADDR email address. See README for details.'
    assert FROM_ADDR, 'Could not load FROM_ADDR email address. See README for details.'

    # Load up the zip codes into a dictionary keyed by the zip code with a value of lng,lat
    points_by_zip = load_zips_as_points('zip_codes.txt')

    # Fetch the web API
    print('Fetching JSON')
    data = fetch_vaccine_json()
    pathlib.Path('result.json').write_text(json.dumps(data, indent=2))

    # Parse the locations from the GeoJSON
    features = data.get('features', [])
    all_locations = [parse_feature(feat, args.src_zip_code, points_by_zip) for feat in features]

    # Filter out any locations that don't have a distance (because the zip code was not found)
    locations_with_distances = filter(lambda v: v.get('distance') is not None, all_locations)

    # Filter only locations that are within the desired distance
    nearby_locations = list(filter(lambda v: v.get('distance') <= args.max_distance, locations_with_distances))

    # Filter only nearby locations that have appointments
    locations = list(filter(lambda v: v.get('has_appts') == True, nearby_locations))

    if len(locations) == 0:
        sys.exit('No nearby locations with appointments found.')

    # Create a a table of the results
    headers = {'pharmacy': 'Pharmacy', 'address': 'Address', 'zip_code': 'Zip Code', 'distance': 'Distance'}
    table = tabulate.tabulate(locations, headers=headers)

    # Only send the email if we are not in debug mode
    if not args.debug:
        html = f'<pre>{table}</pre>'
        result = send_email(html, API_KEY, TO_ADDR, FROM_ADDR)
        print(table)
        print('Email sent:', result)
    else:
        print(table)
