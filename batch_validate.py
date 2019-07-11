#!/usr/bin/env python3

import argparse
import csv
import getpass
import json
import os
import re
import requests
import sys
import time


def get_study_ids(studiesinfo, technique):
  """
  Given a list of records containing study information, return those which are instances of the
  given experimental measurement technique.
  """
  study_ids = set()
  for row in studiesinfo:
    techniques = row['Experiment Measurement Techniques']
    if re.search(technique, techniques, flags=re.IGNORECASE):
      study_ids.add(row['Supporting Data'].strip())

  print("Found {} {} studies: {}".format(len(study_ids), technique, study_ids))
  return study_ids


def filter_study_ids(all_ids, requested_ids):
  """
  Given the list `all_ids` of available study ids, and the list `requested_ids`, return those in
  the latter that exist in the former.
  """
  print("Validation of {} requested ...".format(requested_ids))
  bad_ids = [sid for sid in requested_ids if sid not in all_ids]
  requested_ids = [sid for sid in requested_ids if sid not in bad_ids]
  if bad_ids:
    print("{} are not valid studies of this type; ignoring ...".format(bad_ids))
  print("Validating: {} ...".format(requested_ids))
  return requested_ids


def fetch_immport_data(auth_token, endpoint_name, sid, jsonpath):
  """
  Fetches the data for the given `sid` from ImmPort, caching it in the file at the location
  `jsonpath` for later reuse before returning the data to the caller.
  """
  print("Fetching {} JSON data for {} from ImmPort ...".format(endpoint_name, sid))
  # Send the request:
  query = ("https://api.immport.org/data/query/result/{}?studyAccession={}"
           .format(endpoint_name, sid))
  resp = requests.get(query, headers={"Authorization": "bearer " + auth_token})
  if resp.status_code != requests.codes.ok:
    resp.raise_for_status()

  # Save the JSON data from the response, and write it to a file at the location `jsonpath` that
  # can be reused later if this script is called again.
  data = resp.json()
  with open(jsonpath, 'w') as f:
    json.dump(data, f)
  return data


def extract_nodes(nodes_file):
  """
  Given the NCBI nodes.dmp file handle, return the `parents` dictionary
  """
  parents = {}
  for line in nodes_file:
    (taxid, parent, other) = re.split(r'\s*\|\s*', line.strip('|\n\t '), 2)
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
    (taxid, name, unique, kind) = re.split(r'\s*\|\s*', line.strip('|\n\t '), 3)
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
      print('"{}"'.format(record[header]), end='\t', file=outfile)

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
    print('"{}"\t"{}"'.format(comment_reported, comment_preferred), end='\t', file=outfile)
    if comment_reported == comment_preferred:
      print('"Y"', file=outfile)
    else:
      print('"N"', file=outfile)


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

  parser.add_argument('studiesinfo', type=argparse.FileType(mode='r', encoding='ISO-8859-1'),
                      help='A TSV file containing general information on various studies')
  parser.add_argument('nodes', type=argparse.FileType('r'),
                      help='The NCBI nodes.dmp file')
  parser.add_argument('names', type=argparse.FileType('r'),
                      help='The NCBI names.dmp file')
  parser.add_argument('output_dir', type=str,
                      help='directory for output TSV files')
  parser.add_argument('cache_dir', type=str,
                      help='directory containing cached JSON files')

  # Command-line arguments used to specify the study ids to validate.
  # ---
  # For each type of study that will be validated (e.g. 'hai', 'neutAbTiter'), a separate
  # command-line option must be specified. Whenever more study types are added, a new
  # command-line option corresponding to that study type should be added to `study_type_group`,
  # and the function `get_requested_endpoints()` should be modified accordingly.
  def get_requested_endpoints(args):
    endpoints = []
    if args.get('hai') is not None:
      endpoints.append({'name': 'hai', 'description': 'Hemagglutination Inhibition'})
    if args.get('neutAbTiter') is not None:
      endpoints.append({'name': 'neutAbTiter', 'description': 'Virus Neutralization'})
    return endpoints

  study_type_group = parser.add_argument_group()
  study_type_group.add_argument('--hai', metavar='ID', type=str, nargs='*',
                                help='ids of Hemagglutination Inhibition studies to validate')
  study_type_group.add_argument('--neutAbTiter', metavar='ID', type=str, nargs='*',
                                help=('ids of Neutralizing Antibody Titer (Virus Neutralization) '
                                      'studies to validate'))

  args = vars(parser.parse_args())

  endpoints = get_requested_endpoints(args)
  if not endpoints:
    print("At least one study type must be specified")
    sys.exit(1)

  # If the username and/or password haven't been set in environment variables, prompt for them:
  username = os.environ.get('IMMPORT_USERNAME')
  if not username:
    username = input("IMMPORT_USERNAME not set. Enter ImmPort username: ")
  password = os.environ.get('IMMPORT_PASSWORD')
  if not password:
    password = getpass.getpass('IMMPORT_PASSWORD not set. Enter ImmPort password: ')

  # Get the start time of the execution for later logging the total elapsed time:
  start = time.time()

  # Read in the information from the file containing general info on studies.
  studiesinfo = list(csv.DictReader(args['studiesinfo'], delimiter='\t'))

  # Get the nodes and names data from the given files:
  print("Extracting NCBI data ...")
  parents = extract_nodes(args['nodes'])
  taxid_names, scientific_names, synonyms, lowercase_names = extract_names(args['names'])

  # Get an authentication token from ImmPort:
  print("Retrieving authentication token from Immport ...")
  resp = requests.post('https://auth.immport.org/auth/token',
                       data={'username': username, 'password': password})
  if resp.status_code != requests.codes.ok:
    resp.raise_for_status()
  auth_token = resp.json()['token']

  # Now request data for the given study ids, for each endpoint:
  for endpoint in endpoints:
    print("Validating {} studies".format(endpoint['name']))
    outpath = os.path.normpath('{}/{}.tsv'.format(args['output_dir'], endpoint['name']))
    # Find all of the studies corresponding to the given endpoint to validate:
    study_ids = get_study_ids(studiesinfo, endpoint['description'])
    # But validate only those that the user has requested (validate them all if none are specified):
    if len(args[endpoint['name']]) > 0:
      study_ids = filter_study_ids(study_ids, args[endpoint['name']])

    data = {}
    for sid in study_ids:
      cachedir = '{}/{}/'.format(args['cache_dir'], endpoint['name'])
      os.makedirs(cachedir, exist_ok=True)
      jsonpath = os.path.normpath('{}/{}.json'.format(cachedir, sid))
      # Check to see if there is an existing file for this study id. If so, reuse it, otherwise
      # send an API call to ImmPort to retrieve the data:
      try:
        with open(jsonpath) as f:
          data[sid] = json.load(f)
          print("Retrieved JSON data for {} from cached file {}".format(sid, jsonpath))
      except FileNotFoundError:
        print("No cached data for {} found ({} does not exist)".format(sid, jsonpath))
        data[sid] = fetch_immport_data(auth_token, endpoint['name'], sid, jsonpath)

    if not any([data[sid] for sid in data]):
      print("No data found for endpoint '{}'".format(endpoint['name']))
      continue

    # Write the header of the output TSV file by using the data returned plus extra fields
    # determined on its basis. Every sid in the data set should have the same fields, so we can just
    # use the first one (that has data) to get the header fields from. We can assume that there will
    # be at least one of these since we checked for this above.
    first_sid_with_data = [sid for sid in data if data[sid]].pop()
    headers = sorted([key for key in data[first_sid_with_data][0]])
    with open(outpath, 'w') as outfile:
      for header in headers:
        print('"{}"'.format(header), end='\t', file=outfile)
      print('"Comment on virusStrainReported"', end='\t', file=outfile)
      print('"Comment on virusStrainPreferred"', end='\t', file=outfile)
      print('"Comments match"', file=outfile)

      # Now write the actual data:
      for sid in study_ids:
        records = data.get(sid)
        if not records:
          print("No data found for " + sid)
          continue
        print("Processing {} records for {} ID: {}".format(len(records), endpoint['name'], sid))
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
