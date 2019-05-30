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
  Validate the given virus name using the given dictionaries. If it is an exact match
  for a scientific name, then return with no comment, otherwise return a comment
  describing how the name should be changed.
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
      scientific_name = taxid_names[taxid]
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

  comment = None
  if is_virus(taxid):
    if automatic_replacement:
      comment = 'Automatically replaced "%s" with "%s".' % (name, scientific_name)
    else:
      comment = 'Suggestion: ' + scientific_name
  elif taxid:
    comment = 'Not the name of a virus'
  else:
    comment = 'Not found in NCBI Taxonomy'

  return comment


def write_records(records, headers, outfile, parents, taxid_names,
                  scientific_names, synonyms, lowercase_names):
  """
  Writes the given records, for which their keys are given in `headers`, to the given outfile.
  In addition, validate the virus name for each record and write the validation comment to the row
  corresponding to the record in the file.
  """
  validated = {}
  for record in records:
    for header in headers:
      print('"{}",'.format(record[header]), end='', file=outfile)

    # Validate a given ('virusStrainReported', 'virusStrainPreferred') combination at most once:
    validation_key = (record['virusStrainReported'], record['virusStrainPreferred'])
    if validation_key not in validated:
      validated[validation_key] = {
        'comment_reported': validate(record['virusStrainReported'], parents, taxid_names,
                                     scientific_names, synonyms, lowercase_names),
        'comment_preferred': validate(record['virusStrainPreferred'], parents, taxid_names,
                                      scientific_names, synonyms, lowercase_names)}

    comment_reported = validated[validation_key]['comment_reported']
    comment_preferred = validated[validation_key]['comment_preferred']
    print('"{}","{}",'.format(comment_reported, comment_preferred), end='', file=outfile)
    if comment_reported == comment_preferred:
      print("Y", file=outfile)
    else:
      print("N", file=outfile)


def main():
  # Basic command-line arguments:
  parser = argparse.ArgumentParser(description='''
  Accepts as input a list of study accession IDs corresponding to Hemagglutination Inhibition (hai)
  studies and/or a list of study IDs corresponding to Neutralizing Antibody Titer (neutAbTiter)
  studies. For each of the study ids of a given type, its details are fetched from ImmPort and the
  virus name reported in the study is validated using the given NCBI nodes.dmp and names.dmp files.
  The output of this script is a series of CSV files, for each given study type, reporting on the
  virus names used in the studies specified. In each report, the virus name reported in the study as
  well as the 'preferred name' of the virus (i.e. the name automatically generated by ImmPort
  when the study was submitted) are indcated. In addition to these columns, this script adds three
  extra columns: (a) the result of validating the reported virus name, (b) the result of validating
  the preferred virus name, and (c) a comparison of the results of these two validations.''')
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

def test_validate():
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

  comment = validate('FOO', parents, taxid_names, scientific_names, synonyms, lowercase_names)
  assert comment == 'Not the name of a virus'

  comment = validate('  FOO  ', parents, taxid_names, scientific_names, synonyms, lowercase_names)
  assert comment == 'Not the name of a virus'

  comment = validate('FO', parents, taxid_names, scientific_names, synonyms, lowercase_names)
  assert comment == 'Not the name of a virus'
