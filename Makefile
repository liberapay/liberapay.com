python := "$(shell { command -v python2.7 || command -v python; } 2>/dev/null)"

# Set the relative path to installed binaries under the project virtualenv.
# NOTE: Creating a virtualenv on Windows places binaries in the 'Scripts' directory.
bin_dir := $(shell $(python) -c 'import sys; bin = "Scripts" if sys.platform == "win32" else "bin"; print(bin)')
env_bin := env/$(bin_dir)
venv := "./vendor/virtualenv-1.11.6.py"
test_env_files := defaults.env,tests/test.env,tests/local.env
pip := $(env_bin)/pip
honcho := $(env_bin)/honcho
honcho_run := $(honcho) run -e defaults.env,local.env
py_test := $(honcho) run -e $(test_env_files) $(env_bin)/py.test

ifdef PYTEST
	pytest = ./tests/py/$(PYTEST)
else
	pytest = ./tests/py/
endif

env: requirements.txt requirements_tests.txt setup.py
	$(python) $(venv) \
				--prompt="[gratipay] " \
				--extra-search-dir=./vendor/ \
				--always-copy \
				./env/
	$(pip) install -r requirements.txt --no-index
	$(pip) install -r requirements_tests.txt --no-index
	$(pip) install -e ./

clean:
	rm -rf env *.egg *.egg-info
	find . -name \*.pyc -delete

schema: env
	$(honcho_run) ./recreate-schema.sh

schema-diff: test-schema
	pg_dump -sO `heroku config:get DATABASE_URL -a gratipay` >prod.sql
	$(honcho) run -e $(test_env_files) sh -c 'pg_dump -sO "$$DATABASE_URL"' >local.sql
	diff -uw prod.sql local.sql
	rm prod.sql local.sql

data:
	$(honcho_run) $(env_bin)/fake_data fake_data

run: env
	PATH=$(env_bin):$(PATH) $(honcho_run) web

stop:
	pkill gunicorn

py: env
	$(honcho_run) $(env_bin)/python -i gratipay/main.py

test-schema: env
	$(honcho) run -e $(test_env_files) ./recreate-schema.sh

pyflakes: env
	$(env_bin)/pyflakes bin gratipay tests

test: test-schema pytest jstest

pytest: env
	$(py_test) --cov gratipay $(pytest)
	@$(MAKE) --no-print-directory pyflakes

retest: env
	$(py_test) ./tests/py/ --lf
	@$(MAKE) --no-print-directory pyflakes

test-cov: env
	$(py_test) --cov-report html --cov gratipay ./tests/py/

tests: test

node_modules: package.json
	npm install --no-bin-links
	@if [ -d node_modules ]; then touch node_modules; fi

jstest: node_modules
	node_modules/grunt-cli/bin/grunt test

transifexrc:
	@echo '[https://www.transifex.com]' >.transifexrc
	@echo 'hostname = https://www.transifex.com' >>.transifexrc
	@echo "password = $$TRANSIFEX_PASS" >>.transifexrc
	@echo 'token = ' >>.transifexrc
	@echo "username = $$TRANSIFEX_USER" >>.transifexrc

tx:
	@if [ ! -x $(env_bin)/tx ]; then $(env_bin)/pip install transifex-client; fi

i18n: env tx
	$(env_bin)/pybabel extract -F .babel_extract --no-wrap -o i18n/core.pot emails gratipay templates www

i18n_upload: i18n
	$(env_bin)/tx push -s
	rm i18n/*.pot

i18n_download: env tx
	$(env_bin)/tx pull -a -f --mode=reviewed --minimum-perc=50
	@for f in i18n/*/*.po; do \
	    sed -E -e '/^"POT?-[^-]+-Date: /d' \
	           -e '/^"Last-Translator: /d' \
	           -e '/^#: /d' "$$f" >"$$f.new"; \
	    mv "$$f.new" "$$f"; \
	done
