#!/usr/bin/env python3

import argparse
import getpass
import os.path
import re
import requests
import sys
import time


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
  `taxid_names`, `scientific_names`, `synonyms`, and `lowercase_names`
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


def determine_preferred(reported, parents, taxid_names, scientific_names, synonyms,
                        lowercase_names):
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
    """
    Given a taxonomy ID, return true if it is a virus, false otherwise.
    """
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

  preferred, comment = determine_preferred(record['virusStrainReported'], parents, taxid_names,
                                           scientific_names, synonyms, lowercase_names)
  print('"{}","{}",'.format(preferred, comment), end='', file=outfile)
  print("Y", file=outfile) if record['virusStrainPreferred'] == preferred else print("N", file=outfile)


def main():
  # Basic command-line arguments:
  parser = argparse.ArgumentParser(description='Validate studies submitted to ImmPort')
  parser.add_argument('--username', metavar='USERNAME', type=str,
                      help='username for authentication to ImmPort API')
  parser.add_argument('--password', metavar='PASSWORD', type=str,
                      help='password for authentication to ImmPort API')
  parser.add_argument('--nodes', metavar='NODES', type=argparse.FileType('r'), required=True,
                      help='The NCBI nodes.dmp file')
  parser.add_argument('--names', metavar='NAMES', type=argparse.FileType('r'), required=True,
                      help='The NCBI names.dmp file')
  parser.add_argument('--clobber', dest='clobber', action='store_true',
                      help='If CSV files exist, overwrite them without prompting')
  # Command-line arguments used to specify the study ids to validate.
  # ---
  # For each type of study that will be validated (e.g. 'hai', 'neutAbTiter'), a separate
  # command-line option must be specified. Whenever more study types are added, a new
  # command-line option corresponding to that study type should be added to `study_type_group`,
  # and the function `get_requested_endpoints()` should be modified accordingly.
  def get_requested_endpoints(args):
    endpoints = []
    if args.get('hai'):
      endpoints.append('hai')
    if args.get('neutAbTiter'):
      endpoints.append('neutAbTiter')
    return endpoints

  study_type_group = parser.add_argument_group()
  study_type_group.add_argument('--hai', metavar='ID', type=str, nargs='+',
                                help='ids of Hemagglutination Inhibition studies to validate')
  study_type_group.add_argument('--neutAbTiter', metavar='ID', type=str, nargs='+',
                                help='ids of Neutralizing Antibody Titer studies to validate')

  args = vars(parser.parse_args())

  endpoints = get_requested_endpoints(args)
  if not endpoints:
    print("At least one study type must be specified")
    sys.exit(1)

  # If the username and/or password have not been specified on the command line, prompt for them:
  username = args['username']
  if not username:
    username = input("Enter username for API calls: ")
  password = args['password']
  if not password:
    password = getpass.getpass('Enter password for API calls: ')

  # Get the start time of the execution for later logging the total elapsed time:
  start = time.time()

  # Get the authentication token:
  resp = requests.post('https://auth.immport.org/auth/token',
                       data={'username': username, 'password': password})
  if resp.status_code != requests.codes.ok:
    resp.raise_for_status()
  token = resp.json()['token']

  # Now request data for the given study ids:
  parents = extract_nodes(args['nodes'])
  taxid_names, scientific_names, synonyms, lowercase_names = extract_names(args['names'])
  for endpoint in endpoints:
    if os.path.exists(endpoint + '.csv') and args['clobber'] is False:
      reply = input('{}.csv exists. Do you want really want to overwrite it? (y/n): '
                    .format(endpoint))
      reply = reply.lower().strip()
      if reply == 'n':
        continue
    with open(endpoint + '.csv', 'w') as outfile:
      query = ("https://api.immport.org/data/query/result/{}?studyAccession={}"
               .format(endpoint, ','.join(args[endpoint])))
      print("Sending request: " + query)
      resp = requests.get(query, headers={"Authorization":"bearer " + token})
      if resp.status_code != requests.codes.ok:
        resp.raise_for_status()

      # Write the header of the CSV using the data returned:
      headers = sorted([key for key in resp.json()[0]])
      for header in headers:
        print("{},".format(header), end='', file=outfile)
      print("Preferred (determined),", end='', file=outfile)
      print("Comment,", end='', file=outfile)
      print("Preferred (determined) matches virusStrainPreferred", file=outfile)

      # Now write the actual data:
      for sid in args[endpoint]:
        records = [r for r in resp.json() if r['studyAccession'] == sid]
        print("Received {} records for {} ID: {}".format(len(records), endpoint, sid))
        for record in records:
          write_record(
            record, headers, outfile, parents, taxid_names, scientific_names, synonyms, lowercase_names)

  end = time.time()
  print("Processing completed. Total execution time: {0:.2f} seconds.".format(end - start))


if __name__ == "__main__":
  main()
