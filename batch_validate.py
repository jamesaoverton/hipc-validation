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


def validate(name, parents, taxid_names, scientific_names, synonyms, lowercase_names):
  """
  Determine the preferred name of the given virus name
  """
  taxid = None
  scientific_name = None
  automatic_replacement = False
  iname = name.strip().lower().replace('  ', ' ') if name else ''

  if name:
    # 1. 'name' matches the scientific name of a virus:
    if name in scientific_names:
      taxid = scientific_names[name]
      scientific_name = name
    # 2. 'name' is a close case-insensitive match for a virus:
    elif iname in lowercase_names:
      taxid = lowercase_names[iname]
      scientific_name = taxid_names[taxid]
      automatic_replacement = True
    # 3. 'name' is the exact synonym of some taxon
    elif name in synonyms:
      taxid = synonyms[name]
      scientific_name = id_to_scientific_name[taxid]
    # 4. 'name' is a substring of exactly one scientific name:
    else:
      matches = []
      for scientific_name in scientific_names.keys():
        if name in scientific_name:
          matches.append(scientific_name)
          if len(matches) > 1:
            break
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
    if name == scientific_name:
      preferred = name
    elif automatic_replacement:
      preferred = scientific_name
      comment = 'Automatically replaced "%s" with "%s".' % (name, scientific_name)
    else:
      preferred = name
      comment = 'Suggestion: ' + scientific_name
  elif taxid:
    preferred = name
    comment = 'Not the name of a virus'
  else:
    preferred = name
    comment = 'Not found in NCBI Taxonomy'

  return comment


def write_records(records, headers, outfile, parents, taxid_names,
                  scientific_names, synonyms, lowercase_names):
  """
  Writes the given records, for which their keys are given in `headers`, to the given outfile.
  In addition, determine the preferred virus name for each record and write that too.
  """
  processed = set()
  for record in records:
    # Ignore this record if the combination of its 'virusStrainReported' and
    # 'virusStrainPreferred' fields has already been processed:
    if (record['virusStrainReported'], record['virusStrainPreferred']) not in processed:
      for header in headers:
        print('"{}",'.format(record[header]), end='', file=outfile)

      comment_reported = validate(record['virusStrainReported'], parents, taxid_names,
                                  scientific_names, synonyms, lowercase_names)
      comment_preferred = validate(record['virusStrainPreferred'], parents, taxid_names,
                                   scientific_names, synonyms, lowercase_names)
      print('"{}","{}",'.format(comment_reported, comment_preferred), end='', file=outfile)

      if comment_reported == comment_preferred:
        print("Y", file=outfile)
      else:
        print("N", file=outfile)

      processed.add((record['virusStrainReported'], record['virusStrainPreferred']))


def main():
  # Basic command-line arguments:
  parser = argparse.ArgumentParser(description='''
  Accepts as input a list of study IDs corresponding to Hemagglutination Inhibition (hai) studies
  and/or a list of study IDs corresponding to Neutralizing Antibody Titer (neutAbTiter) studies.
  For each of the study ids of a given type, its details are fetched from ImmPort and the virus name
  reported in the study is validated using the given NCBI nodes.dmp and names.dmp files. The output
  of this script is a report for each type of study (hai, neutAbTiter) requested to be validated. In
  each report, in addition to the virus name given in the study, the preferred name of the virus is
  also indicated, as well as the preferred name of the virus that was automatically generated by
  ImmPort upon submission. The report also indicates whether the preferred name determined by this
  script differs from the preferred name that was generated by ImmPort.''')
  parser.add_argument('--username', metavar='USERNAME', type=str,
                      help='username for ImmPort API. If unspecified the script will prompt for it')
  parser.add_argument('--password', metavar='PASSWORD', type=str,
                      help='password for ImmPort API. If unspecified the script will prompt for it')
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
    username = input("Enter username for API calls to ImmPort: ")
  password = args['password']
  if not password:
    password = getpass.getpass('Enter password for API calls to ImmPort: ')

  # Get the start time of the execution for later logging the total elapsed time:
  start = time.time()

  # Get an authentication token from ImmPort:
  print("Retrieving authentication token from Immport ...")
  resp = requests.post('https://auth.immport.org/auth/token',
                       data={'username': username, 'password': password})
  if resp.status_code != requests.codes.ok:
    resp.raise_for_status()
  token = resp.json()['token']

  # Now request data for the given study ids:
  print("Extracting NCBI data ...")
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
      resp = requests.get(query, headers={"Authorization": "bearer " + token})
      if resp.status_code != requests.codes.ok:
        resp.raise_for_status()

      # Write the header of the CSV using the data returned:
      headers = sorted([key for key in resp.json()[0]])
      for header in headers:
        print("{},".format(header), end='', file=outfile)
      print("Comment on virusStrainReported,", end='', file=outfile)
      print("Comment on virusStrainPreferred,", end='', file=outfile)
      print("Comments match", file=outfile)

      # Now write the actual data:
      for sid in args[endpoint]:
        records = [r for r in resp.json() if r['studyAccession'] == sid]
        print("Received {} records for {} ID: {}".format(len(records), endpoint, sid))
        write_records(records, headers, outfile, parents, taxid_names, scientific_names,
                      synonyms, lowercase_names)

  end = time.time()
  print("Processing completed. Total execution time: {0:.2f} seconds.".format(end - start))


if __name__ == "__main__":
  main()


# Unit tests:

def test_determine_preferred():
  parents = {}
  taxid_names = {}
  scientific_names = {}
  synonyms = {}
  lowercase_names = {}

  scientific_names['FOO'] = '1'
  taxid_names['1'] = 'FOO'
  synonyms['bAR'] = '1'
  lowercase_names['foo'] = '1'
  lowercase_names['bar'] = '1'

  (name, comment) = determine_preferred(
    'FOO', parents, taxid_names, scientific_names, synonyms, lowercase_names)
  assert name == 'FOO'
  assert comment == 'Not the name of a virus'

  (name, comment) = determine_preferred(
    '  FOO  ', parents, taxid_names, scientific_names, synonyms, lowercase_names)
  assert name == '  FOO  '
  assert comment == 'Not the name of a virus'

  (name, comment) = determine_preferred(
    'FO', parents, taxid_names, scientific_names, synonyms, lowercase_names)
  assert name == 'FO'
  assert comment == 'Not the name of a virus'
