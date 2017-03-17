# HIPC Validation

This Python script is a simple demonstration of how a column of taxon names can be validated against the NCBI Taxonomy to ensure an exact scientific name is used, and that they fall under the correct branch of the taxonomy.

## Requirements

- Python 3
- [openpyxl](http://openpyxl.readthedocs.io) module for reading `.xslx` files

## Usage

Download and unzip NCBI Taxonomy data from <ftp://ftp.ncbi.nih.gov/pub/taxonomy/taxdmp.zip>. Then run the script in a terminal:

    ./validate.py nodes.dmp names.dmp sample.xlsx result.xlsx

The script will load the NCBI Taxonomy data, then look in the spreadsheet for a column with the title 'Virus Strain'. It will check each value in that column and write an Excel file that highlights and offers suggestions for those values:

1. green: exact match to the NCBI Taxonomy scientific name for a virus
2. blue: automatic replacement of an unambiguous match with the exact scientific name for a virus
3. orange: suggestion for manual replacement
4. red: not recognized as a name for a virus
