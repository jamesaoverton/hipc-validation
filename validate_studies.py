#!/usr/bin/env python3

import argparse
import getpass
import requests
import sys


def determine_preferred(reported):
  pass


def write_record(record, headers, outfile):
  for header in headers:
    print('"{}",'.format(record[header]), end='', file=outfile)

  preferred = determine_preferred(record['unitReported'])
  print('"{}",'.format(preferred), end='', file=outfile)
  print("Y", file=outfile) if record['unitPreferred'] == preferred else print("N", file=outfile)


def main():
  parser = argparse.ArgumentParser(description='Validate studies submitted to ImmPort')
  parser.add_argument('--output', metavar='CSV', type=argparse.FileType('w'),
                      help='The output CSV file (or STDOUT if unspecified)')
  parser.add_argument('--username', metavar='USERNAME', type=str,
                      help='username for authentication to ImmPort API')
  parser.add_argument('--password', metavar='PASSWORD', type=str,
                      help='password for authentication to ImmPort API')
  parser.add_argument('study_ids', metavar='STUDY_ID', type=str, nargs='+',
                      help='id of study to validate')
  args = parser.parse_args()

  # If the username and/or password have not been specified on the command line, prompt for them:
  username = args.username
  if not username:
    username = input("Enter username for API calls: ")
  password = args.password
  if not password:
    password = getpass.getpass('Enter password for API calls: ')

  # If no output file has been specified, then just use STDOUT:
  outfile = args.output
  if not outfile:
    outfile = sys.stdout

  # Get the authentication token:
  resp = requests.post('https://auth.immport.org/auth/token',
                       data={'username': username, 'password': password})
  if resp.status_code != requests.codes.ok:
    resp.raise_for_status()
  token = resp.json()['token']

  # Now request data for the given study ids:
  query = ("https://api.immport.org/data/query/result/elisa?studyAccession={}"
           .format(','.join(args.study_ids)))
  print("Sending request: " + query, file=sys.stderr)
  resp = requests.get(query, headers={"Authorization":"bearer " + token})
  if resp.status_code != requests.codes.ok:
    resp.raise_for_status()

  # Write the header of the CSV using the data returned:
  headers = sorted([key for key in resp.json()[0]])
  for header in headers:
    print("{},".format(header), end='', file=outfile)
  print("Preferred (determined),", end='', file=outfile)
  print("Preferred (determined) matches unitPreferred", file=outfile)

  # Now write the actual data:
  for sid in args.study_ids:
    records = [r for r in resp.json() if r['studyAccession'] == sid]
    print("Received {} records for Study ID: {}".format(len(records), sid), file=sys.stderr)
    for record in records:
      write_record(record, headers, outfile)


if __name__ == "__main__":
  main()

