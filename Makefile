python := "$(shell { command -v python2.7 || command -v python; } 2>/dev/null)"

# Set the relative path to installed binaries under the project virtualenv.
# NOTE: Creating a virtualenv on Windows places binaries in the 'Scripts' directory.
bin_dir := $(shell $(python) -c 'import sys; bin = "Scripts" if sys.platform == "win32" else "bin"; print(bin)')
env_bin := env/$(bin_dir)
venv := "./vendor/virtualenv-1.9.1.py"
test_env_files := defaults.env,tests/test.env,tests/local.env
py_test := ./$(env_bin)/honcho -e $(test_env_files) run ./$(env_bin)/py.test

postgression_api_url := http://api.postgression.com/

define postgression_database
$(shell ./$(env_bin)/python -c '
import requests
response=requests.get("$(postgression_api_url)")
if response.status_code == 200:
	print "\"DATABASE_URL=%s\\n\"" % response.text
')
endef

env:
	$(python)  $(venv)\
				--unzip-setuptools \
				--prompt="[gittip] " \
				--never-download \
				--extra-search-dir=./vendor/ \
				--distribute \
				./env/
	./$(env_bin)/pip install -r requirements.txt
	./$(env_bin)/pip install -r requirements_tests.txt
	./$(env_bin)/pip install -e ./

clean:
	rm -rf env *.egg *.egg-info
	find . -name \*.pyc -delete

cloud-db: env
	echo -n $(postgression_database) >> local.env

schema: env
	./$(env_bin)/honcho -e defaults.env,local.env run ./recreate-schema.sh

data:
	./$(env_bin)/honcho -e defaults.env,local.env run ./$(env_bin)/fake_data fake_data

db: cloud-db schema data

run: env
	./$(env_bin)/honcho -e defaults.env,local.env run ./$(env_bin)/aspen

test-cloud-db: env
	echo -n $(postgression_database) >> tests/local.env

test-schema: env
	./$(env_bin)/honcho -e $(test_env_files) run ./recreate-schema.sh

test-db: test-cloud-db test-schema

pyflakes: env
	./$(env_bin)/pyflakes bin gittip tests

test: pytest jstest

pytest: env test-schema
	$(py_test) ./tests/py/
	@$(MAKE) --no-print-directory pyflakes

retest: env
	$(py_test) ./tests/py/ --lf
	@$(MAKE) --no-print-directory pyflakes

test-cov: env test-schema
	$(py_test) --cov gittip ./tests/py/

tests: test

node_modules: package.json
	npm install
	@if [ -d node_modules ]; then touch node_modules; fi

jstest: node_modules
	./node_modules/.bin/grunt test

