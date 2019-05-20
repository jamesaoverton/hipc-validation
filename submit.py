#!/usr/bin/env python3
#
# Use [Flask](http://flask.pocoo.org) to validate Excel files.
# Files are saved in the `static` directory.

# To run in development mode, do:
# export FLASK_DEBUG=1


from flask import Flask, request, render_template, redirect, url_for
import datetime
import os
import validate

app = Flask(__name__)


@app.route('/', methods=['GET', 'POST'])
def my_app():
  if request.method != 'POST':
    return render_template('/submit.html')

  f = request.files['input']
  if not f:
    return 'No file submitted'
  tempdir = 'static/' + datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')
  in_path = tempdir + '/input.xlsx'
  out_path = tempdir + '/result.xlsx'
  os.makedirs(tempdir)
  f.save(in_path)
  validate.process_workbook(in_path, out_path)
  return redirect(out_path)


if __name__ == '__main__':
  validate.load_nodes('nodes.dmp')
  validate.load_names('names.dmp')
  app.run()
