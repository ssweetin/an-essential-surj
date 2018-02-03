#!/usr/bin/env python3
# sudo python3 -m pip install restnavigator

# restnavigator:
#     Library for interacting with HAL+JSON APIs of which OSDI conforms
# Docs at https://github.com/deontologician/restnavigator
#

import argparse
import json
import csv
import logging
from datetime import datetime
from restnavigator import Navigator

# Find your token at Start Organizing > Details > API & Sync

flag_log = True          # Print what happens - NOT FLLLY IMPLEMENTED YET - prefer python logging!

importFile = 'sample.csv'

default_chapter = "SURJ Bay Area"

############################################################
#  usage: import_an_people.py [inputfile]
#
parser = argparse.ArgumentParser(
    description='Import activities in .csv format (native NationBuilder import)')
group = parser.add_mutually_exclusive_group()
parser.add_argument('--group', '-g', help='Action Network Group')
parser.add_argument('--start', '-s', default=1, type=int,
                    help='First row to process (starting at 1)')
group.add_argument('--end', '-e', type=int, help='Last row to process')
group.add_argument('--count', '-c', type=int, help='Number of rows to process')
parser.add_argument('--verbose', '-v', action="store_true", help="Show data")
parser.add_argument('--unsubscribed', '-u', action="store_true", help="Include unsubscribed users")
parser.add_argument('--force', '-f', action="store_true", help="Force subscribe of existing users")
parser.add_argument('--dry_run', '-d', action="store_true",
                    help="Process imported data but don't send to Action Network")
parser.add_argument('profile', default=default_chapter, nargs='?',
                    help='The profile name in an_profiles.py')
parser.add_argument('inputFile', help='Importable CSV file')

args = parser.parse_args()

CONFIG_CHAPTER = args.group
CONFIG_PROFILE = args.profile
CONFIG_IMPORTFILE = args.inputFile
CONFIG_VERBOSE = args.verbose
CONFIG_FORCE = args.force
CONFIG_START_INDEX = args.start
CONFIG_INCLUDE_UNSUBSCRIBED = args.unsubscribed
CONFIG_DRY_RUN = args.dry_run
MAXINDEX = 1000000
if args.end is not None:
    CONFIG_END_INDEX = args.end
elif args.count is not None:
    CONFIG_END_INDEX = CONFIG_START_INDEX + args.count - 1
else:
    CONFIG_END_INDEX = MAXINDEX

####################################

'''
CONFIG_PROFILEs file contains:
profiles = {
    "SURJ Action"       : "12343132412341341234123412342342",
    "SURJ Bay Area"     : "12343132412341341234123412342342"
    }
'''
import an_profiles
api_token = an_profiles.profiles.get(CONFIG_PROFILE, "Not Found")
if api_token == "Not Found":
    assert api_token != "Not Found", CONFIG_PROFILE + ": API Token not found"
else:
    if flag_log:
        print("an_profiles: " + CONFIG_PROFILE + ": API Token found")

aep = 'https://actionnetwork.org/api/v2/people/'

tag_mapping_file = 'maptags-curated.csv'

# Indicates which tags to map to
chapter_import = CONFIG_PROFILE

AN = Navigator.hal(aep)
AN.headers['OSDI-API-Token'] = api_token


#################################################################
# Migration helper functions

def get_primary_address(row_primary):
    return get_address(row_primary, 'primary')

def get_billing_address(row_billing):
    return get_address(row_billing, 'billing')

def get_user_submitted_address(row_user_submitted):
    return get_address(row_user_submitted, 'user_submitted')

def get_address(row_address, address_type):
    _address = {}

    _address_lines = []
    if row_address[address_type + '_address1'] != '':
        _address_lines.append(row_address[address_type + '_address1'])
    if row_address[address_type + '_address2'] != '':
        _address_lines.append(row_address[address_type + '_address2'])
    if row_address[address_type + '_address3'] != '':
        _address_lines.append(row_address[address_type + '_address3'])
    if _address_lines:
        _address["address_lines"] = _address_lines

    if row_address[address_type + '_city'] != '':
        _address["locality"] = row_address[address_type + '_city']
    if row_address[address_type + '_state'] != '':
        _address["region"] = row_address[address_type + '_state']
    if row_address[address_type + '_zip'] != '':
        _address["postal_code"] = row_address[address_type + '_zip']

    return _address

def get_action_network_tags():
    ''' Return dict of tags from Action Network for the group we are on
        WARNNG: Only returns tags that have been used so far in group
    '''
    _rn = Navigator.hal('https://actionnetwork.org/api/v2/tags')
    _rn.headers['OSDI-API-Token'] = api_token

    #pdb.set_trace()

    _osdi_tags = _rn['osdi:tags']

    _an_tags = {}
    for tag in _osdi_tags:
        tag_name = tag.state['name']
        _an_tags[tag_name] = True

    return _an_tags

def get_tag_mapping(_importFile, _chapter):
    ''' .csv file:
    old_tag                               new_tags                  SURJ Action
    #maestro_upload                       IGNORE                    Maestro
    #trump-organize                       "#Trump,?Organizing"
    #NYC_Skills_Photo	                  ?Photo Video
    #SURJ Action - Phone Bank - Training  "?Phone Bank,!Training Phone Bank"
    '''
    _map = {}
    with open(_importFile, 'r') as file:
        _reader = csv.DictReader(file)
        for _row in _reader:
            #print 'MAPPING:', _row['old_tag'], _row['new_tags'], _row[_chapter]
            _new_tags = []
            for new_tag in _row['new_tags'].split(","):
                _new_tags.append(new_tag.strip())
            if _row[_chapter] != '':
                for new_tag in _row[_chapter].split(","):
                    _new_tags.append(new_tag.strip())

            _map[_row['old_tag']] = _new_tags  # an array

            #print(_row['old_tag'], _new_tags)
    return _map


found_old_tag_already = {}
def map_person_tags(tag_list):
    ''' Look through a comma separated string of old tags
        to find new tags.
        tag_mapping[old_tag]:
        IGNORE - there are no new replacement tags
        tag1 - there is one replacement tag
        tag2, tag3 - there are two replacement tags
    '''
    _new_tags = []
    for old_tag in tag_list.split(","):
        old_tag = old_tag.strip()
        if old_tag == "":
            continue
        # Just because the tag doesn't exist doesn't mean it's not defined
        if not old_tag in tag_mapping:
            if not old_tag in found_old_tag_already:
                warn_str = "WARNING: Unknown tag not mapped: <" + old_tag + ">"
                print(warn_str)
                logging.warning(warn_str)
                found_old_tag_already[old_tag] = True
            continue
        if not tag_mapping[old_tag]:
            continue
        #print "Map_tags from <" + old_tag + "> to ", str(tag_mapping[old_tag])
        if tag_mapping[old_tag][0] == 'IGNORE':
            continue
        _new_tags += tag_mapping[old_tag]

    return _new_tags

# These are the tags we looked up that are used in the current group
# but they don't represent all the available tags - especially
# the ones from the parent.
#tags_existing = get_action_network_tags()
#print tags_existing
#exit()

tag_mapping = get_tag_mapping(tag_mapping_file, _chapter=CONFIG_CHAPTER)

#print tag_mapping

starttime = datetime.now()
rowid = 0
activists = 0

with open(CONFIG_IMPORTFILE, 'r') as ifile:
    reader = csv.DictReader(ifile)
    for row in reader:
        rowid = rowid + 1
        if not CONFIG_START_INDEX <= rowid <= CONFIG_END_INDEX:
            continue

        print("IMPORTING[{}]: {} <{}> opt-in {} WITH TAGS {}".format(rowid,
                                                                     row['full_name'],
                                                                     row['email'],
                                                                     row['email_opt_in'],
                                                                     row['tag_list']))

        # Action Network people import via an API must have an email
        # (exception is importnig a donation where AN will generate a fake email)
        if row['email'] == '':
            print("NO EMAIL - IMPORT SKIPPED")
            continue

        # Clear the new_person dict and set the only required field
        new_person = {
            "person" : {
                "email_addresses" : [{"address" : row['email']}]
            }
        }
        # We want to import folks that opt-out because if they have donations
        # they would get automatically subscribed.
        if row['email_opt_in'] == 'FALSE':
            new_person["person"]["email_addresses"][0]["status"] = 'unsubscribed'
            if not CONFIG_INCLUDE_UNSUBSCRIBED:
                print("UNSUBSCRIBED - IMPORT SKIPPED")
                continue
        else:
            if CONFIG_FORCE:
                new_person["person"]["email_addresses"][0]["status"] = 'subscribed'

        # Add first and last name if available
        if row['last_name'] != '':
            new_person["person"]['family_name'] = row['last_name']
        if row['first_name'] != '':
            new_person["person"]['given_name'] = row['first_name']

        address = get_primary_address(row)
        if address:
            address["primary"] = True
            new_person["person"]["postal_addresses"] = [address]

        # In NationBuilder the billing address may have more detail than the
        # primary address
        address = get_billing_address(row)
        if address:
            if "postal_addresses" not in new_person["person"]:
                new_person["person"]["postal_addresses"] = []
            new_person["person"]["postal_addresses"].append(address)

        new_person["add_tags"] = map_person_tags(row['tag_list'])

        custom_fields = {}
        if row['mobile_number'] != '' and \
           not row['is_mobile_bad'] and \
           row['mobile_opt_in']:
            custom_fields['mobile'] = row['mobile_number']
        if row['phone_number'] != '' and not row['do_not_call']:
            custom_fields['Phone'] = row['phone_number']
        # Mapping employer field to organization (custom field)
        if row['employer'] != '':
            custom_fields['organization'] = row['employer']
        # Pull in social media handles NationBuilder may have
        if row['facebook_username'] != '':
            custom_fields['facebook_username'] = row['facebook_username']
        if row['twitter_login'] != '':
            custom_fields['twitter_login'] = row['twitter_login']

        #print json.dumps(new_person, indent=4)

        # This request uses the Person Helper
        # (which doesn't support custom fields or multiple addresses?)
        response = {}
        if not CONFIG_DRY_RUN:
            an_self = AN['self']
            user = an_self.create(new_person)
            response = user

        # Need to do a Person PUT to add custom fields.
        if custom_fields:
            custom_fields['tag_list'] = None
            if not CONFIG_DRY_RUN:
                response = user['self'].upsert({"custom_fields" : custom_fields})

        activists = activists + 1

        if CONFIG_VERBOSE:
            if not CONFIG_DRY_RUN:
                print("RESPONSE[{}] {}".format(rowid, json.dumps(response.state, indent=4)))
            else:
                print("NOT EXECUTED[{}] {}".format(rowid, json.dumps(new_person, indent=4)))
            print("ADD_TAGS:" + str(new_person["add_tags"]))

ENDTIME = datetime.now()
duration = ENDTIME - starttime

print('Processed {} activists in {}'.format(activists, duration))

duration_microseconds = duration.seconds * 1000000 + duration.microseconds

if activists > 0:
    print('Activists per second: {:.0f}'.format(1000000.0 / (duration_microseconds / activists)))
