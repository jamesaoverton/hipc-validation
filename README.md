# HIPC Validation

This Python script is a simple demonstration of how a column of taxon names can be validated against the NCBI Taxonomy to ensure an exact scientific name is used, and that they fall under the correct branch of the taxonomy.

## Requirements

- Python 3
- [openpyxl](http://openpyxl.readthedocs.io) module for reading `.xslx` files

## Usage

Download and unzip NCBI Taxonomy data from <ftp://ftp.ncbi.nih.gov/pub/taxonomy/taxdmp.zip>. Then run the script in a terminal:

    ./validate.py nodes.dmp names.dmp sample.xlsx

The script will load the NCBI Taxonomy data, then look in the spreadsheet for a column with the title 'Virus Strain'. It will check each value in that column and print a report to the terminal, suggesting the right scientific name, and verifying that the taxon is a virus.
