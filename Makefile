# Makefile for HIPC Validation
# Michael E. Cuffaro <consulting@michaelcuffaro.com>
#
# WARN: This file contains significant whitespace, i.e. tabs!
# Ensure that your text editor shows you those characters.
#
# Requirements:
#
# - GNU Make <https://www.gnu.org/software/make/>
# - Python 3
# - pytest <https://pytest.org> for running automated tests

### GNU Make Configuration
#
# These are standard options to make Make sane:
# <http://clarkgrubb.com/makefile-style-guide#toc2>

MAKEFLAGS += --warn-undefined-variables
SHELL := bash
.SHELLFLAGS := -eu -o pipefail -c
.DEFAULT_GOAL := all
.DELETE_ON_ERROR:
.SUFFIXES:
.SECONDARY:


### Set Up

build:
	mkdir $@

cache:
	mkdir $@

# NCBI data
cache/%.dmp: cache/taxdmp.zip | cache
	unzip -u $< -d $|

# .zip file from which the NCBI .dmp files are extracted
cache/taxdmp.zip: | cache
	curl -k -L -o $@ "ftp://ftp.ncbi.nih.gov/pub/taxonomy/taxdmp.zip"

# File containing general info on various HIPC studies:
build/HIPC_Studies.tsv: | build
	curl -k -L -o $@ "https://www.immport.org/documentation/data/hipc/HIPC_Studies.tsv"


### Validation scripts

build/result.xlsx: validate.py cache/nodes.dmp cache/names.dmp sample.xlsx
	$^ $@

build/hai.tsv: batch_validate.py build/HIPC_Studies.tsv cache/nodes.dmp cache/names.dmp | build cache
	$^ $| --hai

build/neutAbTiter.tsv: batch_validate.py build/HIPC_Studies.tsv cache/nodes.dmp cache/names.dmp | build cache
	$^ $| --neutAbTiter


### Cleanup scripts

clean:
	rm -f build/*.tsv

cleancache:
	rm -rf cache

test:
	pytest *.py
