.PHONY: validate batch_validate clean cleanall test

validate: validate.py nodes.dmp names.dmp sample.xlsx
	$^ result.xlsx

batch_validate: hai.csv neutAbTiter.csv

hai.csv: batch_validate.py nodes.dmp names.dmp
	$< --clobber --nodes nodes.dmp --names names.dmp \
	--hai SDY113 SDY144 SDY180 SDY202 SDY212 SDY312 SDY387 SDY404 SDY514 SDY515 SDY519 SDY67

neutAbTiter.csv: batch_validate.py nodes.dmp names.dmp
	$< --clobber --nodes nodes.dmp --names names.dmp \
	--neutAbTiter SDY144 SDY180 SDY387 SDY522 SDY67

%.dmp: taxdmp.zip
	unzip -u $<

taxdmp.zip:
	curl -k -L -o $@ "ftp://ftp.ncbi.nih.gov/pub/taxonomy/taxdmp.zip"

clean:
	rm -f taxdmp.zip *.dmp gc.prt readme.txt *.csv

cleanall: clean
	rm -Rf static

test:
	pytest-3 *.py
