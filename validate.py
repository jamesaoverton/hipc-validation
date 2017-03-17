#!/usr/bin/env python3
#
# This script reads NCBI Taxonomy names.dmp and an Excel (xlsx) file,
# looks a column named 'Virus Strain',
# then checks that every value in that column is a valid NCBI Taxonomy name.
# A report is printed, classifying each distinct value
# as with valid or invalid, with an optional suggestion.
#
# Download NCBI Taxonomy data from:
# <ftp://ftp.ncbi.nih.gov/pub/taxonomy/taxdmp.zip>
#
# Requirements:
# - Python 3
# - [openpyxl](http://openpyxl.readthedocs.io)

import argparse, string, re
from openpyxl import load_workbook

# Handle command-line arguments
parser = argparse.ArgumentParser(
    description='Validate taxon names in a spreadsheet. Download NCBI Taxonomy from ftp://ftp.ncbi.nih.gov/pub/taxonomy/taxdmp.zip')
parser.add_argument('nodes',
    type=argparse.FileType('r'),
    help='The NCBI nodes.dmp file')
parser.add_argument('names',
    type=argparse.FileType('r'),
    help='The NCBI names.dmp file')
parser.add_argument('sheet',
    type=str,
    help='The xlsx file to check')
args = parser.parse_args()

# Load NCBI Taxonomy data into various dictionaries
parents = {}
id_to_scientific_name = {}
exact_scientific_names = {}
exact_synonyms = {}
lowercase_names = {}

# Load parentage
for line in args.nodes:
  (taxid, parent, other) = re.split('\s*\|\s*', line.strip('|\n\t '), 2)
  parents[taxid] = parent

# Load scientific names and synonyms
for line in args.names:
  (taxid, name, unique, kind) = re.split('\s*\|\s*', line.strip('|\n\t '), 3)
  if kind == 'scientific name':
    id_to_scientific_name[taxid] = name
    exact_scientific_names[name] = taxid
  else:
    exact_synonyms[name] = taxid
  lowercase_names[name.lower()] = taxid

def is_virus(taxid):
  """Given a taxonomy ID, return true if it is a virus, false otherwise."""
  if not taxid:
    return False
  if taxid == '1':
    return False
  if taxid == '10239':
    return True
  return is_virus(parents[taxid])

def match_taxon(name):
  """Given a name, try to match it and print a brief report."""
  iname = name.strip().lower()

  # Is this the exact scientific name of a virus?
  if name in exact_scientific_names:
    taxid = exact_scientific_names[name]
    if is_virus(taxid):
      print('MATCHED VIRUS "%s"' % name)
    else:
      print('NOT A VIRUS "%s"' % name)

  # Is this the exact synonym of some taxon?
  elif name in exact_synonyms:
    taxid = exact_synonyms[name]
    scientific_name = id_to_scientific_name[taxid]
    print('SUGGEST "%s" INSTEAD OF "%s"' % (scientific_name, name))

  # Is this a variation on a synony? Strip whitespace and ignore case.
  elif iname in lowercase_names:
    taxid = lowercase_names[iname]
    scientific_name = id_to_scientific_name[taxid]
    print('SUGGEST "%s" INSTEAD OF "%s"' % (scientific_name, name))

  # Is this a substring of exactly on scientific name?
  else:
    matches = []
    for scientific_name in exact_scientific_names.keys():
      if name in scientific_name:
        matches.append(scientific_name)
    if len(matches) == 1:
      print('SUGGEST "%s" INSTEAD OF "%s"' % (matches[0], name))
    else:
      print('NO MATCH FOR "%s"' % name)

# Load an Excel file, search for the 'Taxon Virus Strain' column,
# then validate each virus name.
wb = load_workbook(args.sheet)
ws = wb.active
column = None
for row in ws:
  if column:
    name = row[column].value
    match_taxon(name)
  else:
    for cell in row:
      if cell.value == 'Virus Strain':
        column = cell.col_idx - 1
