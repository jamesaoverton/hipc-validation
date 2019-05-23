#!/usr/bin/env python3

import argparse
import getpass
import re
import requests
import sys


def extract_nodes(nodes_file):
  """
  Given the NCBI nodes.dmp file handle, return the `parents` dictionary
  """
  parents = {}
  for line in nodes_file:
    (taxid, parent, other) = re.split('\s*\|\s*', line.strip('|\n\t '), 2)
    parents[taxid] = parent

  return parents


def extract_names(names_file):
  """
  Given the NCBI names.dmp file handle, return four dictionaries:
  taxid_names, scientific_names, synonyms, and lowercase_names
  """
  taxid_names = {}
  scientific_names = {}
  synonyms = {}
  lowercase_names = {}
  for line in names_file:
    (taxid, name, unique, kind) = re.split('\s*\|\s*', line.strip('|\n\t '), 3)
    if kind == 'scientific name':
      taxid_names[taxid] = name
      scientific_names[name] = taxid
    else:
      synonyms[name] = taxid
    lowercase_names[name.lower()] = taxid

  return taxid_names, scientific_names, synonyms, lowercase_names


def determine_preferred(reported, taxid_names, scientific_names, synonyms, lowercase_names):
  taxid = None
  scientific_name = None
  automatic_replacement = False
  ireported = reported.strip().lower().replace('  ', ' ')

  if reported:
    # 1. 'reported' matches the scientific name of a virus:
    if reported in scientific_names:
      taxid = scientific_names[reported]
      scientific_name = reported
    # 2. 'reported' is a close case-insensitive match for a virus:
    elif ireported in lowercase_names:
      taxid = lowercase_names[ireported]
      scientific_name = taxid_names[taxid]
      automatic_replacement = True
    # 3. 'reported' is the exact synonym of some taxon
    elif reported in synonyms:
      taxid = synonyms[reported]
      scientific_name = id_to_scientific_name[taxid]
    # 4. 'reported' is a substring of exactly one scientific name:
    else:
      # IF THIS IS FASTER DO IT LIKE THIS IN VALIDATE.PY ALSO:
      matches = [scientific_name for scientific_name in scientific_names
                 if reported in scientific_name]
      # matches = []
      # for scientific_name in scientific_names.keys():
      #   if reported in scientific_name:
      #     matches.append(scientific_name)
      #     if len(matches) > 1:
      #       break
      if len(matches) == 1:
        scientific_name = matches[0]
        taxid = scientific_names[scientific_name]

  def is_virus(taxid):
    """Given a taxonomy ID, return true if it is a virus, false otherwise."""
    return taxid and taxid != '1' and (taxid == '10239' or is_virus(parents[taxid]))

  preferred = None
  comment = None
  if is_virus(taxid):
    if reported == scientific_name:
      preferred = reported
    elif automatic_replacement:
      preferred = scientific_name
      comment = 'Automatically replaced "%s" with "%s".' % (reported, scientific_name)
    else:
      preferred = reported
      comment = 'Suggestion: ' + scientific_name
  elif taxid:
    preferred = reported
    comment = 'Not the name of virus'
  else:
    preferred = reported
    comment = 'Not found in NCBI Taxonomy'

  return preferred, comment


def write_record(record, headers, outfile, parents, taxid_names,
                 scientific_names, synonyms, lowercase_names):
  for header in headers:
    print('"{}",'.format(record[header]), end='', file=outfile)

  preferred, comment = determine_preferred(record['unitReported'], taxid_names, scientific_names,
                                           synonyms, lowercase_names)
  print('"{}","{}",'.format(preferred, comment), end='', file=outfile)
  print("Y", file=outfile) if record['unitPreferred'] == preferred else print("N", file=outfile)


def main():
  parser = argparse.ArgumentParser(description='Validate studies submitted to ImmPort')
  parser.add_argument('--output', metavar='CSV', type=argparse.FileType('w'),
                      help='The output CSV file (or STDOUT if unspecified)')
  parser.add_argument('--username', metavar='USERNAME', type=str,
                      help='username for authentication to ImmPort API')
  parser.add_argument('--password', metavar='PASSWORD', type=str,
                      help='password for authentication to ImmPort API')
  parser.add_argument('nodes', metavar='NODES', type=argparse.FileType('r'),
                      help='The NCBI nodes.dmp file')
  parser.add_argument('names', metavar='NAMES', type=argparse.FileType('r'),
                      help='The NCBI names.dmp file')
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
  print("Comment,", end='', file=outfile)
  print("Preferred (determined) matches unitPreferred", file=outfile)
  
  # Now write the actual data:
  parents = extract_nodes(args.nodes)
  taxid_names, scientific_names, synonyms, lowercase_names = extract_names(args.names)
  for sid in args.study_ids:
    records = [r for r in resp.json() if r['studyAccession'] == sid]
    print("Received {} records for Study ID: {}".format(len(records), sid), file=sys.stderr)
    for record in records:
      write_record(
        record, headers, outfile, parents, taxid_names, scientific_names, synonyms, lowercase_names)


if __name__ == "__main__":
  main()

