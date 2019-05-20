.PHONY: validate clean cleanall test

validate: validate.py nodes.dmp names.dmp sample.xlsx
	$^ result.xlsx

%.dmp: taxdmp.zip
	unzip -u $<

taxdmp.zip:
	curl -k -L -o $@ "ftp://ftp.ncbi.nih.gov/pub/taxonomy/taxdmp.zip"

clean:
	rm -f taxdmp.zip *.dmp gc.prt readme.txt

cleanall: clean
	rm -Rf static

test:
	pytest-3 *.py
